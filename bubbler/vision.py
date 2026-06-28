# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Lazy vision assist. Vector-stroke symbols + OCR fallback.

import re

# Synthetic block ids above any real one.
_VBLOCK = 900000


def augment_words(page, words, cfg):
    """Words plus enabled vision passes. Never raises."""
    cfg = cfg or {}
    if not cfg.get("vision_assist"):
        return words
    out = list(words)
    try:
        out = _geometry_symbols(page, out, cfg)        # Tier 0: vector Ø/R
    except Exception as e:                              # pragma: no cover
        _warn("geometry pass failed: %s" % e)
    text_is_sparse = _sparse(out)
    try:
        if cfg.get("vision_ocr", True) and (text_is_sparse or
                                            cfg.get("vision_ocr_always")):
            out += _ocr_words(page, cfg)               # Tier 1: scanned pages
    except Exception as e:                              # pragma: no cover
        _warn("ocr pass failed: %s" % e)
    try:
        if cfg.get("vision_symbols", True):
            out = _symbol_words(page, out, cfg)        # Tier 2: GD&T symbols
    except Exception as e:                              # pragma: no cover
        _warn("symbol pass failed: %s" % e)
    return out


def available(cfg=None):
    """Per-pass availability booleans for the settings UI."""
    geom = _fitz() is not None
    vlm = False
    try:
        from . import florence, paddlevl
        vlm = geom and (florence.can_load(cfg or {})
                        or paddlevl.can_load(cfg or {}))
    except Exception:
        vlm = False
    return {"geometry": geom,
            "ocr": geom and _ocr_engine() is not None,
            "symbols": geom and _symbol_session(cfg or {}) is not None,
            "region": geom and _region_session(cfg or {}) is not None,
            "vlm": vlm,
            "gpu": _has_gpu_ep()}


def _warn(msg):
    import sys, os
    line = "bubbler.vision: %s" % msg
    print(line, file=sys.stderr)
    # Mirror to ~/.bubbler.log; GUI builds discard stderr.
    try:
        logp = os.path.join(os.path.expanduser("~"), ".bubbler.log")
        with open(logp, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


_EP_LOGGED = False


def _providers(cfg):
    """Providers for cfg['vision_ep']. Always ends in CPU."""
    try:
        import onnxruntime as ort
        avail = set(ort.get_available_providers())
    except Exception:
        return ["CPUExecutionProvider"]
    pref = {
        "cpu":      ["CPUExecutionProvider"],
        "directml": ["DmlExecutionProvider", "CPUExecutionProvider"],
        "cuda":     ["CUDAExecutionProvider", "CPUExecutionProvider"],
        "auto":     ["CUDAExecutionProvider", "DmlExecutionProvider",
                     "CPUExecutionProvider"],
    }.get(str((cfg or {}).get("vision_ep", "auto")).lower(),
          ["CPUExecutionProvider"])
    out = [p for p in pref if p in avail]
    return out or ["CPUExecutionProvider"]


def _has_gpu_ep():
    """GPU provider (DirectML/CUDA) installed?"""
    try:
        import onnxruntime as ort
        avail = set(ort.get_available_providers())
    except Exception:
        return False
    return bool(avail & {"DmlExecutionProvider", "CUDAExecutionProvider"})


def reset_sessions():
    """Drop cached sessions so next call rebuilds."""
    global _SYM_SESS, _SYM_TRIED, _RGN_SESS, _RGN_TRIED, _OCR, _OCR_TRIED
    global _PADDLE, _PADDLE_TRIED, _VLM, _VLM_TRIED, _EP_LOGGED
    _SYM_SESS = _RGN_SESS = _OCR = _PADDLE = _VLM = None
    _SYM_TRIED = _RGN_TRIED = _OCR_TRIED = _PADDLE_TRIED = _VLM_TRIED = False
    _EP_LOGGED = False


def _sparse(words, threshold=4):
    """Few text tokens -> probably scanned, worth OCR."""
    return sum(1 for w in words if str(w[4]).strip()) < threshold


def _fitz():
    try:
        import fitz
        return fitz
    except Exception:
        return None


def _scale(cfg):
    try:
        dpi = float(cfg.get("vision_dpi", 200))
    except (TypeError, ValueError):
        dpi = 200.0
    return max(1.0, dpi) / 72.0


def _pixmap(page, cfg):
    """Render displayed page -> (np.uint8 HxWx3, scale), or None."""
    fitz = _fitz()
    if fitz is None:
        return None
    try:
        import numpy as np
    except Exception:
        return None
    s = _scale(cfg)
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    elif pix.n == 1:
        img = np.repeat(img, 3, axis=2)
    return img, s


def _rot_matrix(page):
    """page.rotation_matrix when rotated, else None."""
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    return page.rotation_matrix if rot else None


def _xform_rect(m, x0, y0, x1, y1):
    from .scanpos import xform_rect
    return xform_rect(m, x0, y0, x1, y1)


def _attach_or_append(out, rect, symbol):
    """Prepend symbol to nearest number right, else append."""
    from .scanpos import _GLYPHS                        # ⌀/∅/ø -> Ø

    def _lead(s):
        """First char, folded through the glyph map."""
        c = s[:1]
        return _GLYPHS.get(c, c)

    x0, y0, x1, y1 = rect
    cy = (y0 + y1) / 2.0
    h = max(y1 - y0, 2.0)
    best = None
    for i, w in enumerate(out):
        wt = str(w[4])
        if not wt or not re.match(r"^[.\dØR]", _lead(wt)):
            continue
        wy = (w[1] + w[3]) / 2.0
        if abs(wy - cy) > 0.7 * h:
            continue                                   # different row
        gap = w[0] - x1
        if gap < -0.5 * h or gap > 3.0 * h:
            continue                                   # not just to the right
        if best is None or gap < best[0]:
            best = (gap, i)
    if best is not None:
        i = best[1]
        w = out[i]
        wt = str(w[4])
        # Dup-guard across glyph lookalikes via folded leads.
        dup = wt.startswith(symbol) or (
            len(symbol) == 1 and _lead(wt) == _GLYPHS.get(symbol, symbol))
        if not dup:
            out[i] = (min(x0, w[0]), min(y0, w[1]), max(x1, w[2]),
                      max(y1, w[3]), symbol + wt) + tuple(w[5:8])
        return
    n = len(out)
    out.append((x0, y0, x1, y1, symbol, _VBLOCK + n, 0, 0))


# Tier 0: geometry

def _geometry_symbols(page, words, cfg):
    """Detect vector Ø/R marks, attach to adjacent number."""
    fitz = _fitz()
    if fitz is None:
        return words
    try:
        paths = page.get_drawings()
    except Exception:
        return words
    rm = _rot_matrix(page)
    out = list(words)
    for p in paths:
        items = p.get("items") or []
        r = p.get("rect")
        if r is None or r.width <= 0 or r.height <= 0:
            continue
        # diameter glyph: square-ish circle, one slash
        ncurve = sum(1 for it in items if it[0] == "c")
        nline = sum(1 for it in items if it[0] == "l")
        squareish = 0.6 <= (r.width / max(r.height, 1e-6)) <= 1.6
        small = r.width <= 60 and r.height <= 60
        if small and squareish and ncurve >= 3 and 1 <= nline <= 2:
            rc = (r.x0, r.y0, r.x1, r.y1)
            if rm is not None:
                rc = _xform_rect(rm, *rc)
            _attach_or_append(out, rc, "Ø")
    return out


# Tier 1: OCR

_OCR = None
_OCR_TRIED = False


def _ocr_engine():
    """Lazily build RapidOCR. None if wheel absent."""
    global _OCR, _OCR_TRIED
    if _OCR_TRIED:
        return _OCR
    _OCR_TRIED = True
    try:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    except Exception as e:
        _warn("RapidOCR unavailable (%s); OCR pass disabled" % e)
        _OCR = None
    return _OCR


def _ocr_words(page, cfg):
    """OCR rendered page -> word tuples, one per line."""
    eng = _ocr_engine()
    pm = _pixmap(page, cfg)
    if eng is None or pm is None:
        return []
    img, s = pm
    result, _elapse = eng(img)
    if not result:
        return []
    out = []
    for n, (box, text, conf) in enumerate(result):
        try:
            if float(conf) < float(cfg.get("vision_ocr_conf", 0.5)):
                continue
        except (TypeError, ValueError):
            pass
        xs = [pt[0] / s for pt in box]
        ys = [pt[1] / s for pt in box]
        out.append((min(xs), min(ys), max(xs), max(ys),
                    str(text), _VBLOCK + 1000 + n, 0, 0))
    return out


# Per-block OCR
_PADDLE = None
_PADDLE_TRIED = False


def _paddle_engine():
    """Lazily build PaddleOCR 'latin'. None if wheel absent."""
    global _PADDLE, _PADDLE_TRIED
    if _PADDLE_TRIED:
        return _PADDLE
    _PADDLE_TRIED = True
    try:
        from paddleocr import PaddleOCR
        _PADDLE = PaddleOCR(use_angle_cls=True, lang="latin", show_log=False)
    except Exception as e:
        _warn("PaddleOCR unavailable (%s)" % e)
        _PADDLE = None
    return _PADDLE


def _ocr_engine_for(cfg):
    """-> (kind, engine) for the configured OCR engine, RapidOCR fallback."""
    if str((cfg or {}).get("vision_ocr_engine", "rapidocr")).lower() == "paddle":
        eng = _paddle_engine()
        if eng is not None:
            return "paddle", eng
        _warn("falling back to RapidOCR for this run")
    eng = _ocr_engine()
    return ("rapidocr", eng) if eng is not None else (None, None)


def _ocr_read(kind, eng, sub):
    """OCR an image crop, normalised to [(box4, text, conf)]."""
    if kind == "paddle":
        out = []
        for page in (eng.ocr(sub, cls=True) or []):
            for line in (page or []):
                box, (text, conf) = line[0], line[1]
                out.append((box, text, conf))
        return out
    res, _elapse = eng(sub)
    return [(box, text, conf) for (box, text, conf) in (res or [])]


def _ocr_block(img, s, rect, kind, eng, conf_min, blk):
    """OCR one block crop -> word tuples (displayed points)."""
    x0 = max(0, int(rect[0] * s))
    y0 = max(0, int(rect[1] * s))
    x1 = int(rect[2] * s)
    y1 = int(rect[3] * s)
    sub = img[y0:y1, x0:x1]
    if sub.size == 0:
        return []
    out = []
    for n, (box, text, conf) in enumerate(_ocr_read(kind, eng, sub)):
        try:
            if float(conf) < conf_min:
                continue
        except (TypeError, ValueError):
            pass
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append(((min(xs) + x0) / s, (min(ys) + y0) / s,
                    (max(xs) + x0) / s, (max(ys) + y0) / s,
                    str(text), blk + n, 0, 0))
    return out


# Optional Florence-2 VLM reader, explicit actions only.
_VLM = None
_VLM_TRIED = False


def _vlm_module(cfg):
    """Reader module for cfg['vision_vlm_engine']."""
    if str((cfg or {}).get("vision_vlm_engine", "florence")).lower() \
            == "paddleocr_vl":
        from . import paddlevl
        return paddlevl, paddlevl.PaddleOCRVL
    from . import florence
    return florence, florence.Florence2


def _vlm_engine(cfg):
    """Lazily load + warm the VLM reader. None if absent."""
    global _VLM, _VLM_TRIED
    if _VLM_TRIED:
        return _VLM
    _VLM_TRIED = True
    try:
        mod, cls = _vlm_module(cfg)
        _VLM = cls.load(_providers(cfg), mod.model_dir(cfg))
        if _VLM is not None:
            _warn("VLM reader loaded: %s"
                  % str(cfg.get("vision_vlm_engine", "florence")))
            _VLM.warmup()
    except Exception as e:
        _warn("VLM reader unavailable (%s)" % e)
        _VLM = None
    return _VLM


def _vlm_read_block(img, s, rect, eng, blk):
    """VLM-read one block crop -> word tuples (displayed points)."""
    x0 = max(0, int(rect[0] * s))
    y0 = max(0, int(rect[1] * s))
    x1 = int(rect[2] * s)
    y1 = int(rect[3] * s)
    sub = img[y0:y1, x0:x1]
    if sub.size == 0:
        return []
    out = []
    for n, (box, text, _conf) in enumerate(eng.read_regions(sub)):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append(((min(xs) + x0) / s, (min(ys) + y0) / s,
                    (max(xs) + x0) / s, (max(ys) + y0) / s,
                    str(text), blk + n, 0, 0))
    return out


# Tier 2: GD&T symbols

_SYM_SESS = None
_SYM_TRIED = False

# order must match train/classes.txt
_SYM_CLASSES = (
    "Ø", "R",
    "⌖", "▱", "◯", "⌭",          # position, flatness, circularity, cylindricity
    "⟂", "∥", "∠",                # perpendicularity, parallelism, angularity
    "◎", "⌒", "⌓", "⌰", "↗",      # concentricity, profile-line/surf, runouts
    "Ra",                          # surface_roughness -> Ra (SURFACE pattern)
    "DEEP ", "CBORE ", "CSINK ",   # depth / counterbore / countersink callouts
)


def _model_path(cfg):
    import os, sys
    p = cfg.get("vision_model")
    if p and os.path.exists(p):
        return p
    # __file__-relative, then legacy freezer dir.
    roots = [os.path.dirname(os.path.abspath(__file__))]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        roots += [os.path.join(base, "bubbler"), base]
    for root in roots:
        cand = os.path.join(root, "models", "gdt_symbols.onnx")
        if os.path.exists(cand):
            return cand
    return None


def _symbol_session(cfg):
    """Lazily open ONNX symbol detector. None if runtime/model absent."""
    global _SYM_SESS, _SYM_TRIED, _EP_LOGGED
    if _SYM_TRIED:
        return _SYM_SESS
    _SYM_TRIED = True
    path = _model_path(cfg or {})
    if path is None:
        _warn("symbol model not found (bundled gdt_symbols.onnx missing); "
              "symbol pass disabled")
        return None
    try:
        import onnxruntime as ort
        _SYM_SESS = ort.InferenceSession(path, providers=_providers(cfg))
        if not _EP_LOGGED:
            _warn("execution provider: %s" % ", ".join(_SYM_SESS.get_providers()))
            _EP_LOGGED = True
    except Exception as e:
        _warn("onnxruntime/model unavailable (%s); symbol pass disabled" % e)
        _SYM_SESS = None
    return _SYM_SESS


def _symbol_dets(page, cfg):
    """-> [(env_rect, token), ...] GD&T symbol detections in displayed points."""
    sess = _symbol_session(cfg)
    pm = _pixmap(page, cfg)
    if sess is None or pm is None:
        return []
    try:
        import numpy as np
    except Exception:
        return []
    img, s = pm
    imgsz = int(cfg.get("vision_imgsz", 640))
    blob, pad, ratio = _letterbox(img, imgsz, np)
    name = sess.get_inputs()[0].name
    pred = np.asarray(sess.run(None, {name: blob})[0])
    if pred.ndim == 3:
        pred = pred[0]
    if pred.size == 0:
        return []
    conf_min = float(cfg.get("vision_sym_conf", 0.35))
    dets = _nms(_decode(pred, len(_SYM_CLASSES), conf_min, np),
                float(cfg.get("vision_nms_iou", 0.45)))
    px, py = pad
    out = []
    for x0, y0, x1, y1, _conf, ci in dets:
        if not (0 <= ci < len(_SYM_CLASSES)):
            continue
        # undo letterbox -> render pixels -> displayed points
        env = ((x0 - px) / ratio / s, (y0 - py) / ratio / s,
               (x1 - px) / ratio / s, (y1 - py) / ratio / s)
        out.append((env, _SYM_CLASSES[ci]))
    return out


def _symbol_words(page, words, cfg):
    """Add GD&T symbol tokens, each attached to its number."""
    out = list(words)
    for env, tok in _symbol_dets(page, cfg):
        _attach_or_append(out, env, tok)
    return out


# order must match generate_regions.REGION_CLASSES
_REGION_CLASSES = (
    "hole_note", "feature_control_frame", "dim_tol", "hole_table",
    "surface_finish", "datum_feature", "gentol_block", "note",
)

_RGN_SESS = None
_RGN_TRIED = False


def _region_model_path(cfg):
    import os, sys
    p = (cfg or {}).get("vision_region_model")
    if p and os.path.exists(p):
        return p
    roots = [os.path.dirname(os.path.abspath(__file__))]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        roots += [os.path.join(base, "bubbler"), base]
    for root in roots:
        cand = os.path.join(root, "models", "gdt_regions.onnx")
        if os.path.exists(cand):
            return cand
    return None


def _region_session(cfg):
    """Lazily open callout-block detector. None if runtime/model absent."""
    global _RGN_SESS, _RGN_TRIED, _EP_LOGGED
    if _RGN_TRIED:
        return _RGN_SESS
    _RGN_TRIED = True
    path = _region_model_path(cfg or {})
    if path is None:
        _warn("region model not found (gdt_regions.onnx); "
              "block grouping falls back to geometry")
        return None
    try:
        import onnxruntime as ort
        _RGN_SESS = ort.InferenceSession(path, providers=_providers(cfg))
        if not _EP_LOGGED:
            _warn("execution provider: %s" % ", ".join(_RGN_SESS.get_providers()))
            _EP_LOGGED = True
    except Exception as e:
        _warn("region model unavailable (%s); block grouping uses geometry" % e)
        _RGN_SESS = None
    return _RGN_SESS


def _region_boxes(page, cfg):
    """-> [(x0, y0, x1, y1, conf, cls)] callout-block rects in displayed points, or []."""
    sess = _region_session(cfg)
    pm = _pixmap(page, cfg)
    if sess is None or pm is None:
        return []
    try:
        import numpy as np
    except Exception:
        return []
    img, s = pm
    imgsz = int(cfg.get("vision_imgsz", 640))
    blob, pad, ratio = _letterbox(img, imgsz, np)
    name = sess.get_inputs()[0].name
    pred = np.asarray(sess.run(None, {name: blob})[0])
    if pred.ndim == 3:
        pred = pred[0]
    if pred.size == 0:
        return []
    conf_min = float(cfg.get("vision_region_conf", 0.35))
    dets = _nms(_decode(pred, len(_REGION_CLASSES), conf_min, np),
                float(cfg.get("vision_nms_iou", 0.45)))
    px, py = pad
    out = []
    for x0, y0, x1, y1, conf, ci in dets:
        if not (0 <= ci < len(_REGION_CLASSES)):
            continue
        # undo letterbox -> render pixels -> displayed points
        out.append(((x0 - px) / ratio / s, (y0 - py) / ratio / s,
                    (x1 - px) / ratio / s, (y1 - py) / ratio / s, conf, ci))
    return out


# Path A assembly

def _center_in(word, rect):
    cx = (word[0] + word[2]) / 2.0
    cy = (word[1] + word[3]) / 2.0
    return rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]


def _rects_overlap(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _region_regex_hits(page, cfg, rect=None, include_bare=False, words=None,
                       allow_vlm=False, on_slow=None):
    """Scan pipeline per detected block. None defers to legacy."""
    if _region_session(cfg) is None:
        return None
    boxes = _region_boxes(page, cfg)
    if rect is not None:
        boxes = [b for b in boxes if _rects_overlap(b[:4], rect)]
    if not boxes:
        return None
    from bubbler import scanpos
    if words is None:
        words = scanpos.page_words(page)
    pm = _pixmap(page, cfg)
    img, s = pm if pm else (None, None)
    kind, eng = _ocr_engine_for(cfg)
    conf_min = float(cfg.get("vision_ocr_conf", 0.5))
    vlm = _vlm_engine(cfg) if (allow_vlm and cfg.get("vision_vlm")) else None
    force_vlm = bool(vlm is not None and cfg.get("vision_vlm_always"))
    # symbols to inject into off-page blocks
    sym_dets = _symbol_dets(page, cfg) if cfg.get("vision_symbols", True) else []
    table_cls = _REGION_CLASSES.index("hole_table")
    from . import common
    all_hits = []
    for bi, b in enumerate(boxes):
        brect = (b[0], b[1], b[2], b[3])
        in_block = [w for w in words if _center_in(w, brect)]
        has_text = [w for w in in_block if str(w[4]).strip()]
        # region class -> kind + reader constraint
        region_cls = (_REGION_CLASSES[int(b[5])]
                      if len(b) > 5 and 0 <= int(b[5]) < len(_REGION_CLASSES)
                      else None)
        cat = common.CATEGORY.get(region_cls)
        cat_kind = cat[0] if cat else None
        constraint = cat[2] if cat else None
        if cat_kind == common.KIND_META:
            continue                                     # not a measurement
        reader = "text"
        if len(has_text) >= 2 and not force_vlm:      # vector PDF: text layer
            block_words = in_block
        elif vlm is not None and img is not None:      # premium VLM reader
            if on_slow:                                 # toast before the freeze
                on_slow()
                on_slow = None                          # once, on first slow block
            block_words = _vlm_read_block(img, s, brect, vlm,
                                          _VBLOCK + 7000 + bi * 100)
            reader = "vlm"
            if not block_words and has_text:           # VLM read nothing -> text
                block_words, reader = in_block, "text"
        elif img is not None and eng is not None:      # scanned: det+rec OCR
            if on_slow:
                on_slow()
                on_slow = None
            block_words = _ocr_block(img, s, brect, kind, eng, conf_min,
                                     _VBLOCK + 5000 + bi * 100)
            reader = "ocr"
        else:
            block_words = in_block
        # inject only for off-page readers
        inject = bool(sym_dets) and reader != "text"
        if reader == "vlm" and not cfg.get("vision_sym_inject_vlm", True):
            inject = False
        if inject:
            block_words = list(block_words)
            for env, tok in sym_dets:
                if not _center_in((env[0], env[1], env[2], env[3]), brect):
                    continue
                if cat is not None and not common.admits(constraint, tok):
                    continue                            # category forbids token
                _attach_or_append(block_words, env, tok)
        hits = scanpos.scan_words(block_words, include_bare=include_bare)
        # container: keep only rows overlapping capture rect
        if cat_kind == common.KIND_CONTAINER and rect is not None:
            hits = [h for h in hits
                    if h.get("rect") is None or _rects_overlap(h["rect"], rect)]
        is_table = len(b) > 5 and int(b[5]) == table_cls
        for h in hits:
            # disjoint cg band per block
            h["cg"] = bi * 1000 + (h["cg"] if is_table else 0)
        all_hits.extend(hits)
    # [] -> defer to legacy scan_words path.
    return scanpos.dedup_hits(all_hits) or None


def extract_hits(page, cfg, rect=None, include_bare=False, words=None,
                 allow_vlm=False, on_slow=None):
    """Structured hits for page or rect. None -> legacy path."""
    if not cfg.get("vision_assist") or not cfg.get("vision_region", True):
        return None
    try:
        return _region_regex_hits(page, cfg, rect, include_bare, words,
                                   allow_vlm, on_slow)
    except Exception as e:
        _warn("region path failed (%s); falling back to legacy" % e)
        return None


def meta_region_at(page, cfg, rect):
    """META region class under the click, else None."""
    from . import common
    if not cfg.get("vision_assist") or not cfg.get("vision_region", True):
        return None
    if _region_session(cfg) is None:
        return None
    try:
        boxes = _region_boxes(page, cfg)
    except Exception:
        return None
    cx = (rect[0] + rect[2]) / 2.0
    cy = (rect[1] + rect[3]) / 2.0
    meta_cls, meta_area = None, None
    for b in boxes:
        if len(b) <= 5 or not (b[0] <= cx <= b[2] and b[1] <= cy <= b[3]):
            continue                                   # click not inside this box
        ci = int(b[5])
        cls = _REGION_CLASSES[ci] if 0 <= ci < len(_REGION_CLASSES) else None
        cat = common.CATEGORY.get(cls)
        if cat is None:
            continue
        if cat[0] != common.KIND_META:
            return None                                # a real callout here
        area = (b[2] - b[0]) * (b[3] - b[1])
        if meta_area is None or area < meta_area:
            meta_cls, meta_area = cls, area
    return meta_cls


def _decode(pred, nc, conf_min, np):
    """-> [(x0, y0, x1, y1, conf, cls)] envelopes in letterboxed pixels."""
    # NMS-reduced rows: (N, 6+) = x1,y1,x2,y2,conf,cls
    if pred.ndim == 2 and pred.shape[1] in (6, 7) and pred.shape[0] < pred.shape[1] + 10000:
        out = []
        for r in pred:
            if r[4] >= conf_min:
                out.append((float(r[0]), float(r[1]), float(r[2]),
                            float(r[3]), float(r[4]), int(round(r[5]))))
        return out
    # raw head: channels-first (C, A) -> (A, C)
    if pred.shape[0] < pred.shape[1]:
        pred = pred.T
    C = pred.shape[1]
    has_angle = (C == 4 + nc + 1)
    cls = pred[:, 4:4 + nc]
    conf = cls.max(1)
    cid = cls.argmax(1)
    keep = conf >= conf_min
    pred, conf, cid = pred[keep], conf[keep], cid[keep]
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    if has_angle:
        a = pred[:, 4 + nc]
        dx = np.abs(w / 2 * np.cos(a)) + np.abs(h / 2 * np.sin(a))
        dy = np.abs(w / 2 * np.sin(a)) + np.abs(h / 2 * np.cos(a))
    else:
        dx, dy = w / 2, h / 2
    out = []
    for i in range(len(conf)):
        out.append((float(cx[i] - dx[i]), float(cy[i] - dy[i]),
                    float(cx[i] + dx[i]), float(cy[i] + dy[i]),
                    float(conf[i]), int(cid[i])))
    return out


def _nms(dets, iou_thr):
    """Greedy per-class NMS on axis-aligned envelopes."""
    dets = sorted(dets, key=lambda d: d[4], reverse=True)
    kept = []
    for d in dets:
        if all(d[5] != k[5] or _iou(d, k) < iou_thr for k in kept):
            kept.append(d)
    return kept


def _iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _letterbox(img, size, np):
    """Aspect-resize and pad to square -> NCHW blob, (pad_x, pad_y), ratio."""
    h, w = img.shape[:2]
    ratio = min(size / h, size / w)
    nh, nw = int(round(h * ratio)), int(round(w * ratio))
    try:
        import cv2
        resized = cv2.resize(img, (nw, nh))
    except Exception:
        # nearest-neighbour fallback without OpenCV
        ys = (np.arange(nh) / ratio).astype(int).clip(0, h - 1)
        xs = (np.arange(nw) / ratio).astype(int).clip(0, w - 1)
        resized = img[ys][:, xs]
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[py:py + nh, px:px + nw] = resized
    blob = canvas.astype("float32") / 255.0
    blob = blob.transpose(2, 0, 1)[None]               # NCHW
    return blob, (px, py), ratio
