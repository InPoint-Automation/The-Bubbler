# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Lazy vision assist. Vector-stroke symbols + OCR fallback.

import re
import threading

_VBLOCK = 900000

_SESS_LOCK = threading.Lock()  # prewarm thread races the scan pool


def augment_words(page, words, cfg):
    """Words plus enabled vision passes. Never raises."""
    cfg = cfg or {}
    if not cfg.get("vision_assist"):
        return words
    out = list(words)
    try:
        out = _geometry_symbols(page, out, cfg)
    except Exception as e:                              # pragma: no cover
        _warn("geometry pass failed: %s" % e)
    text_is_sparse = _sparse(out)
    try:
        if cfg.get("vision_ocr", True) and (text_is_sparse or
                                            cfg.get("vision_ocr_always")):
            out += _ocr_words(page, cfg)
    except Exception as e:                              # pragma: no cover
        _warn("ocr pass failed: %s" % e)
    try:
        if cfg.get("vision_symbols", True):
            out = _symbol_words(page, out, cfg)
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
            "gpu": _has_gpu_ep(),
            "providers": _ort_providers(),
            "reasons": dict(_REASONS)}


def _ort_providers():
    """Available onnxruntime execution providers"""
    try:
        import onnxruntime as ort
        _REASONS.pop("onnxruntime", None)
        return list(ort.get_available_providers())
    except Exception as e:
        _REASONS["onnxruntime"] = "onnxruntime not importable (%s)" % e
        return []


_REASONS = {}


def _note(key, msg):
    """Record why a pass is unavailabl"""
    _REASONS[key] = msg
    _warn(msg)


def _warn(msg):
    import sys, os
    line = "bubbler.vision: %s" % msg
    print(line, file=sys.stderr)
    try:
        logp = os.path.join(os.path.expanduser("~"), ".bubbler.log")
        try:
            if os.path.getsize(logp) > 256 * 1024:
                os.replace(logp, logp + ".1")
        except OSError:
            pass
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


def _make_session(ort, path, cfg):
    """Open session"""
    prefer = _providers(cfg)
    try:
        return ort.InferenceSession(path, providers=prefer)
    except Exception as e:
        if prefer == ["CPUExecutionProvider"]:
            raise
        _note("ep", "%s failed to init (%s); running vision on CPU"
              % (prefer[0], e))
        return ort.InferenceSession(path, providers=["CPUExecutionProvider"])


def _has_gpu_ep():
    try:
        import onnxruntime as ort
        avail = set(ort.get_available_providers())
    except Exception:
        return False
    return bool(avail & {"DmlExecutionProvider", "CUDAExecutionProvider"})


def reset_sessions():
    global _SYM_SESS, _SYM_TRIED, _RGN_SESS, _RGN_TRIED, _OCR, _OCR_TRIED
    global _PADDLE, _PADDLE_TRIED, _VLM, _VLM_TRIED, _EP_LOGGED
    _SYM_SESS = _RGN_SESS = _OCR = _PADDLE = _VLM = None
    _SYM_TRIED = _RGN_TRIED = _OCR_TRIED = _PADDLE_TRIED = _VLM_TRIED = False
    _EP_LOGGED = False
    _REASONS.clear()


def _sparse(words, threshold=4):
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


def _pixmap_clip(page, cfg, rect, dpi):
    fitz = _fitz()
    if fitz is None:
        return None
    try:
        import numpy as np
    except Exception:
        return None
    if int(getattr(page, "rotation", 0) or 0) % 360:
        return None
    x0, y0, x1, y1 = rect
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    s = max(1.0, float(dpi)) / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s),
                          clip=fitz.Rect(x0, y0, x1, y1), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    elif pix.n == 1:
        img = np.repeat(img, 3, axis=2)
    return img, s, x0, y0


def _rot_matrix(page):
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    return page.rotation_matrix if rot else None


def _xform_rect(m, x0, y0, x1, y1):
    from .scanpos import xform_rect
    return xform_rect(m, x0, y0, x1, y1)


def _glyph_keyword(tok):
    """GD&T keyword"""
    from .scanlib import _GDT_SYMBOLS
    for glyph, kw in _GDT_SYMBOLS:
        if glyph == tok:
            return kw.strip().upper()
    return None


def _block_glyphs(block_words):
    """dedup lookups."""
    return " ".join(str(w[4]) for w in block_words).upper()


def _glyph_present(tok, have_upper):
    """Glyph or its keyword already in text"""
    t = (tok or "").strip().upper()
    if t and any(w.startswith(t) for w in have_upper.split()):
        return True
    kw = _glyph_keyword(tok)
    if kw and kw in have_upper:
        return True
    return False


def _attach_or_append(out, rect, symbol):
    """Prepend symbol to nearest number right, else append."""
    from .scanpos import _GLYPHS

    def _lead(s):
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
            continue
        gap = w[0] - x1
        if gap < -0.5 * h or gap > 3.0 * h:
            continue
        if best is None or gap < best[0]:
            best = (gap, i)
    if best is not None:
        i = best[1]
        w = out[i]
        wt = str(w[4])
        dup = wt.startswith(symbol) or (
            len(symbol) == 1 and _lead(wt) == _GLYPHS.get(symbol, symbol))
        if not dup:
            out[i] = (min(x0, w[0]), min(y0, w[1]), max(x1, w[2]),
                      max(y1, w[3]), symbol + wt) + tuple(w[5:8])
        return
    n = len(out)
    out.append((x0, y0, x1, y1, symbol, _VBLOCK + n, 0, 0))


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
        _REASONS.pop("ocr", None)
    except Exception as e:
        _note("ocr", "RapidOCR unavailable (%s); OCR pass disabled" % e)
        _OCR = None
    return _OCR


def _ocr_words(page, cfg):
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


_VLM = None
_VLM_TRIED = False


def _vlm_module(cfg):
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


def _onnx_roots():
    """Dirs for models"""
    import os, sys
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))]
    try:
        roots.append(__compiled__.containing_dir)   # Nuitka standalone
    except NameError:
        pass
    roots.append(os.path.dirname(sys.argv[0]))
    return roots


def _model_path(cfg):
    import os
    p = (cfg or {}).get("vision_model")
    if p and os.path.exists(p):
        return p
    for root in _onnx_roots():
        cand = os.path.join(root, "models", "gdt_symbols.onnx")
        if os.path.exists(cand):
            return cand
    return None


def _out_nc(sess):
    """YOLO class count: output channels - 4. None if shape unreadable/dynamic."""
    try:
        shape = sess.get_outputs()[0].shape
    except Exception:
        return None
    if len(shape) == 3 and isinstance(shape[1], int):
        return shape[1] - 4
    return None


def _symbol_session(cfg):
    """Lazily open ONNX symbol detector. None if runtime/model absent."""
    global _SYM_SESS, _SYM_TRIED, _EP_LOGGED
    if _SYM_TRIED:
        return _SYM_SESS
    with _SESS_LOCK:                     # prewarm thread races the scan pool
        if _SYM_TRIED:
            return _SYM_SESS
        path = _model_path(cfg or {})
        if path is None:
            _note("symbols", "symbol model not found (bundled gdt_symbols.onnx "
                  "missing); symbol pass disabled")
            _SYM_TRIED = True
            return None
        try:
            import onnxruntime as ort
            _SYM_SESS = _make_session(ort, path, cfg)
            _REASONS.pop("symbols", None)
            if not _EP_LOGGED:
                _warn("execution provider: %s"
                      % ", ".join(_SYM_SESS.get_providers()))
                _EP_LOGGED = True
            nc = _out_nc(_SYM_SESS)
            if nc is None:
                _warn("could not read symbol model class count; guard skipped")
            elif nc != len(_SYM_CLASSES):
                _note("symbols", "symbol model class mismatch: model nc=%d, "
                      "code expects %d (train/classes.txt); reads may "
                      "misclassify -- retrain/re-export recommended"
                      % (nc, len(_SYM_CLASSES)))
        except Exception as e:
            _note("symbols", "onnxruntime/model unavailable (%s); symbol pass "
                  "disabled" % e)
            _SYM_SESS = None
        _SYM_TRIED = True
        return _SYM_SESS


_DET_CACHE = {}
_DET_CACHE_MAX = 64
_CACHE_LOCK = threading.Lock()


def clear_cache():
    """Drop cached detections (call on document open / settings change)."""
    with _CACHE_LOCK:
        _DET_CACHE.clear()


def _model_stat(path):
    """(mtime, size) for a model file"""
    try:
        import os
        st = os.stat(path)
        return (int(st.st_mtime), st.st_size)
    except Exception:
        return None


def _det_sig(cfg):
    keys = ("vision_dpi", "vision_imgsz", "vision_tile", "vision_tile_overlap",
            "vision_merge", "vision_sym_conf", "vision_region_conf",
            "vision_nms_iou", "vision_model", "vision_region_model",
            "vision_ep", "vision_symbols", "vision_region")
    cfg = cfg or {}
    base = tuple(cfg.get(k) for k in keys)
    stamp = (_model_stat(_model_path(cfg)),
             _model_stat(_region_model_path(cfg)))
    return base + stamp


def _cache_key(page, cfg, tag):
    try:
        return (tag, page.parent.name, page.number, _det_sig(cfg))
    except Exception:
        return None


def _cache_get(key):
    if key is None:
        return None
    with _CACHE_LOCK:
        return _DET_CACHE.get(key)


def _cache_put(key, val):
    if key is None:
        return
    with _CACHE_LOCK:
        if len(_DET_CACHE) >= _DET_CACHE_MAX and key not in _DET_CACHE:
            _DET_CACHE.clear()
        _DET_CACHE[key] = val


def prewarm(cfg):
    """Warm ONNX sessions off the first-scan critical path. Never raises."""
    cfg = cfg or {}
    if not cfg.get("vision_assist"):
        return
    try:
        import numpy as np
    except Exception:
        return
    blank = np.full((64, 64, 3), 255, np.uint8)
    imgsz = int(cfg.get("vision_imgsz", 640))
    for get, nc in ((_symbol_session, len(_SYM_CLASSES)),
                    (_region_session, len(_REGION_CLASSES))):
        try:
            sess = get(cfg)
            if sess is not None:
                _run_det(sess, blank, imgsz, nc, 0.99, 0.45, np)
        except Exception:
            pass


def _tile_grid(w, h, tile, overlap):
    if w <= tile and h <= tile:
        return [(0, 0, w, h)]
    step = max(1, int(round(tile * (1.0 - overlap))))

    def _starts(extent):
        if extent <= tile:
            return [0]
        s = list(range(0, extent - tile + 1, step))
        if s[-1] != extent - tile:
            s.append(extent - tile)
        return s

    xs, ys = _starts(w), _starts(h)
    return [(x, y, min(x + tile, w), min(y + tile, h))
            for y in ys for x in xs]


def _run_det(sess, img, imgsz, nc, conf, iou, np):
    blob, pad, ratio = _letterbox(img, imgsz, np)
    pred = np.asarray(sess.run(None, {sess.get_inputs()[0].name: blob})[0])
    if pred.ndim == 3:
        pred = pred[0]
    if pred.size == 0:
        return []
    px, py = pad
    out = []
    for x0, y0, x1, y1, c, ci in _nms(_decode(pred, nc, conf, np), iou):
        out.append(((x0 - px) / ratio, (y0 - py) / ratio,
                    (x1 - px) / ratio, (y1 - py) / ratio, c, int(ci)))
    return out


def _detect_page(sess, page, cfg, nc, conf, tile):
    pm = _pixmap(page, cfg)
    if sess is None or pm is None:
        return []
    try:
        import numpy as np
    except Exception:
        return []
    img, s = pm
    imgsz = int(cfg.get("vision_imgsz", 640))
    iou = float(cfg.get("vision_nms_iou", 0.45))
    h, w = img.shape[:2]
    use_tile = (tile and cfg.get("vision_tile", True)
                and max(h, w) > imgsz * 1.5)
    if not use_tile:
        dets = _run_det(sess, img, imgsz, nc, conf, iou, np)
    else:
        overlap = float(cfg.get("vision_tile_overlap", 0.2))
        dets = []
        for tx0, ty0, tx1, ty1 in _tile_grid(w, h, imgsz, overlap):
            crop = img[ty0:ty1, tx0:tx1]
            for x0, y0, x1, y1, c, ci in _run_det(sess, crop, imgsz, nc,
                                                  conf, iou, np):
                dets.append((x0 + tx0, y0 + ty0, x1 + tx0, y1 + ty0, c, ci))
        dets = _merge(dets, iou, cfg.get("vision_merge", "wbf"))
    return [(x0 / s, y0 / s, x1 / s, y1 / s, c, ci)
            for x0, y0, x1, y1, c, ci in dets]


def _symbol_dets(page, cfg):
    key = _cache_key(page, cfg, "sym")
    hit = _cache_get(key)
    if hit is not None:
        return hit
    conf = float(cfg.get("vision_sym_conf", 0.35))
    out = []
    for x0, y0, x1, y1, _c, ci in _detect_page(
            _symbol_session(cfg), page, cfg, len(_SYM_CLASSES), conf, tile=True):
        if 0 <= ci < len(_SYM_CLASSES):
            out.append(((x0, y0, x1, y1), _SYM_CLASSES[ci]))
    _cache_put(key, out)
    return out


def _symbol_dets_clip(page, cfg, rect):
    sess = _symbol_session(cfg)
    if sess is None:
        return []
    try:
        import numpy as np
    except Exception:
        return []
    pm = _pixmap_clip(page, cfg, rect, cfg.get("vision_fcf_dpi", 600))
    if pm is None:
        return []
    img, s, ox, oy = pm
    imgsz = int(cfg.get("vision_imgsz", 640))
    iou = float(cfg.get("vision_nms_iou", 0.45))
    conf = float(cfg.get("vision_fcf_conf", 0.25))
    out = []
    for x0, y0, x1, y1, _c, ci in _run_det(sess, img, imgsz,
                                           len(_SYM_CLASSES), conf, iou, np):
        if 0 <= ci < len(_SYM_CLASSES):
            out.append(((x0 / s + ox, y0 / s + oy,
                         x1 / s + ox, y1 / s + oy), _SYM_CLASSES[ci]))
    return out


def _dedup_syms(primary, extra, iou_thr=0.4):
    out = list(primary)
    for env2, tok2 in extra:
        b2 = (env2[0], env2[1], env2[2], env2[3], 1.0, 0)
        if not any(tok1 == tok2 and _iou(
                (e1[0], e1[1], e1[2], e1[3], 1.0, 0), b2) >= iou_thr
                for e1, tok1 in out):
            out.append((env2, tok2))
    return out


def _symbol_words(page, words, cfg):
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
    import os
    p = (cfg or {}).get("vision_region_model")
    if p and os.path.exists(p):
        return p
    for root in _onnx_roots():
        cand = os.path.join(root, "models", "gdt_regions.onnx")
        if os.path.exists(cand):
            return cand
    return None


def _region_session(cfg):
    """Lazily open callout-block detector. None if runtime/model absent."""
    global _RGN_SESS, _RGN_TRIED, _EP_LOGGED
    if _RGN_TRIED:
        return _RGN_SESS
    with _SESS_LOCK:
        if _RGN_TRIED:
            return _RGN_SESS
        path = _region_model_path(cfg or {})
        if path is None:
            _note("region", "region model not found (gdt_regions.onnx); "
                  "block grouping falls back to geometry")
            _RGN_TRIED = True
            return None
        try:
            import onnxruntime as ort
            _RGN_SESS = _make_session(ort, path, cfg)
            _REASONS.pop("region", None)
            if not _EP_LOGGED:
                _warn("execution provider: %s"
                      % ", ".join(_RGN_SESS.get_providers()))
                _EP_LOGGED = True
            nc = _out_nc(_RGN_SESS)
            if nc is None:
                _warn("could not read region model class count; guard skipped")
            elif nc != len(_REGION_CLASSES):
                _note("region", "region model class mismatch: model nc=%d, code "
                      "expects %d; reads may misclassify -- retrain/re-export "
                      "recommended" % (nc, len(_REGION_CLASSES)))
        except Exception as e:
            _note("region", "region model unavailable (%s); block grouping uses "
                  "geometry" % e)
            _RGN_SESS = None
        _RGN_TRIED = True
        return _RGN_SESS


def _region_boxes(page, cfg):
    key = _cache_key(page, cfg, "rgn")
    hit = _cache_get(key)
    if hit is not None:
        return hit
    conf = float(cfg.get("vision_region_conf", 0.35))
    out = []
    for x0, y0, x1, y1, c, ci in _detect_page(
            _region_session(cfg), page, cfg, len(_REGION_CLASSES),
            conf, tile=False):
        if 0 <= ci < len(_REGION_CLASSES):
            out.append((x0, y0, x1, y1, c, ci))
    _cache_put(key, out)
    return out


def _center_in(word, rect):
    cx = (word[0] + word[2]) / 2.0
    cy = (word[1] + word[3]) / 2.0
    return rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]


def _rects_overlap(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _fcf_symbol_kw(text):
    from .scanlib import _GDT_SYMBOLS
    for glyph, kw in _GDT_SYMBOLS:
        if glyph in text:
            return kw.split()
    return None


def _fcf_cell_of(word, cells):
    cx = (word[0] + word[2]) / 2.0
    for i, (lo, hi) in enumerate(cells):
        if lo <= cx <= hi:
            return i
    return None


def _fcf_row_of(word, rows):
    cy = (word[1] + word[3]) / 2.0
    for i, (lo, hi) in enumerate(rows):
        if lo <= cy <= hi:
            return i
    return 0 if cy < rows[0][0] else len(rows) - 1


def _fcf_structural_hits(page, cfg, brect, block_words, bi):
    from bubbler import scanpos
    seg = None
    try:
        seg = scanpos.segment_fcf_cells(page, brect, cfg)
    except Exception:
        seg = None
    if not seg:
        return []
    cells, rows = seg["cells"], seg["rows"]
    if len(cells) < 2:
        return []
    joined = " ".join(str(w[4]) for w in block_words)
    sym = _fcf_symbol_kw(joined)
    if not sym:
        return []
    rrect = brect
    per_cell = [[] for _ in cells]
    for w in block_words:
        ci = _fcf_cell_of(w, cells)
        if ci is None:
            continue
        ri = _fcf_row_of(w, rows)
        per_cell[ci].append((ri, w))
    out = []
    for ri in range(len(rows)):
        tol_words = [w for r, w in per_cell[1] if r == ri or len(rows) == 1]
        tol_txt = _fcf_tol_text(tol_words)
        if not tol_txt:
            continue
        datum_txt = []
        for ci in range(2, len(cells)):
            dw = [w for r, w in per_cell[ci] if r == ri or len(rows) == 1]
            for d in _fcf_datum_tokens(dw):
                datum_txt.append(d)
        toks = _fcf_line_tokens(sym, tol_txt, datum_txt, rrect)
        if toks is None:
            continue
        line = {"key": (_VBLOCK + bi, ri), "toks": toks}
        hits = scanpos.parse_lines([line], cfg=cfg)
        for h in hits:
            h["rect"] = rrect
            h["cg"] = _VBLOCK + bi
        out.extend(h for h in hits if h.get("tp") == "GDT")
    return out


def _fcf_tol_text(words):
    from .scanpos import _norm_token
    parts = []
    for w in words:
        s = _norm_token(str(w[4])).strip()
        if s:
            parts.append(s)
    txt = " ".join(parts)
    txt = re.sub(r"[()]", " ", txt)
    # allow leading-dot value
    m = re.search(r"(Ø?\s*(?:\d+(?:[.,]\d+)?|[.,]\d+))(?:\s*([MLSP])\b)?", txt)
    if not m:
        return ""
    tol = re.sub(r"\s+", "", m.group(1))
    tol = re.sub(r"^(Ø?)([.,])", r"\g<1>0\2", tol)   # .5 -> 0.5
    mod = (" " + m.group(2)) if m.group(2) else ""
    return tol + mod


def _fcf_datum_tokens(words):
    # join words first
    txt = " ".join(re.sub(r"[()]", " ", str(w[4])) for w in words)
    out = []
    for mt in re.finditer(r"\b([A-Z](?:-[A-Z])?)\b(?:\s*([MLSP])\b)?", txt):
        d = mt.group(1)
        if mt.group(2):
            d += mt.group(2)
        out.append(d)
    return out


def _fcf_line_tokens(sym, tol_txt, datum_txt, rrect):
    words = list(sym)
    if not tol_txt:
        return None
    tol, _, mod = tol_txt.partition(" ")
    words.append(tol)
    if mod:
        words.append(mod)
    words.extend(datum_txt)
    return [{"t": t, "r": tuple(rrect)} for t in words if t]


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
    sym_dets = _symbol_dets(page, cfg) if cfg.get("vision_symbols", True) else []
    table_cls = _REGION_CLASSES.index("hole_table")
    from . import common
    all_hits = []
    for bi, b in enumerate(boxes):
        brect = (b[0], b[1], b[2], b[3])
        in_block = [w for w in words if _center_in(w, brect)]
        has_text = [w for w in in_block if str(w[4]).strip()]
        region_cls = (_REGION_CLASSES[int(b[5])]
                      if len(b) > 5 and 0 <= int(b[5]) < len(_REGION_CLASSES)
                      else None)
        cat = common.CATEGORY.get(region_cls)
        cat_kind = cat[0] if cat else None
        constraint = cat[2] if cat else None
        if cat_kind == common.KIND_META:
            continue
        if not common.mode_admits_region(region_cls, cfg):
            continue
        reader = "text"
        if len(has_text) >= 2 and not force_vlm:
            block_words = in_block
        elif vlm is not None and img is not None:
            if on_slow:
                on_slow()
                on_slow = None
            block_words = _vlm_read_block(img, s, brect, vlm,
                                          _VBLOCK + 7000 + bi * 100)
            reader = "vlm"
            if not block_words and has_text:
                block_words, reader = in_block, "text"
        elif img is not None and eng is not None:
            if on_slow:
                on_slow()
                on_slow = None
            block_words = _ocr_block(img, s, brect, kind, eng, conf_min,
                                     _VBLOCK + 5000 + bi * 100)
            reader = "ocr"
        else:
            block_words = in_block
        # inject glyphs for any reader
        inject = bool(sym_dets)
        if reader == "vlm" and not cfg.get("vision_sym_inject_vlm", True):
            inject = False
        if reader == "text" and not cfg.get("vision_sym_inject_text", True):
            inject = False
        if inject:
            block_words = list(block_words)
            block_syms = [(env, tok) for env, tok in sym_dets
                          if _center_in((env[0], env[1], env[2], env[3]), brect)]
            if (region_cls == "feature_control_frame"
                    and cfg.get("vision_fcf_rerun", True)):
                crop = _symbol_dets_clip(page, cfg, brect)
                if crop:
                    block_syms = _dedup_syms(crop, block_syms)
            have = _block_glyphs(block_words)
            for env, tok in block_syms:
                if cat is not None and not common.admits(constraint, tok):
                    continue
                if _glyph_present(tok, have):
                    continue
                _attach_or_append(block_words, env, tok)
        hits = None
        if (region_cls == "feature_control_frame"
                and cfg.get("vision_fcf_structural", True)):
            try:
                fcf = _fcf_structural_hits(page, cfg, brect, block_words, bi)
            except Exception:                            # pragma: no cover
                fcf = []
            if fcf and (cat is None or common.admits(constraint, "⌖")):
                hits = fcf
        if hits is None:
            hits = scanpos.scan_words(block_words, include_bare=include_bare,
                                      cfg=cfg)
        if cat_kind == common.KIND_CONTAINER and rect is not None:
            hits = [h for h in hits
                    if h.get("rect") is None or _rects_overlap(h["rect"], rect)]
        is_table = len(b) > 5 and int(b[5]) == table_cls
        for h in hits:
            h["cg"] = bi * 1000 + (h["cg"] if is_table else 0)
        all_hits.extend(hits)
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
            continue
        ci = int(b[5])
        cls = _REGION_CLASSES[ci] if 0 <= ci < len(_REGION_CLASSES) else None
        cat = common.CATEGORY.get(cls)
        if cat is None:
            continue
        if cat[0] != common.KIND_META:
            return None
        area = (b[2] - b[0]) * (b[3] - b[1])
        if meta_area is None or area < meta_area:
            meta_cls, meta_area = cls, area
    return meta_cls


def _decode(pred, nc, conf_min, np):
    """-> [(x0, y0, x1, y1, conf, cls)] envelopes in letterboxed pixels."""
    if pred.ndim == 2 and pred.shape[1] in (6, 7) and pred.shape[0] < pred.shape[1] + 10000:
        out = []
        for r in pred:
            if r[4] >= conf_min:
                out.append((float(r[0]), float(r[1]), float(r[2]),
                            float(r[3]), float(r[4]), int(round(r[5]))))
        return out
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
    dets = sorted(dets, key=lambda d: d[4], reverse=True)
    kept = []
    for d in dets:
        if all(d[5] != k[5] or _iou(d, k) < iou_thr for k in kept):
            kept.append(d)
    return kept


def _soft_nms(dets, iou_thr, sigma=0.5, score_thr=0.05):
    import math
    dets = [tuple(d) for d in dets]
    kept = []
    while dets:
        dets.sort(key=lambda d: d[4], reverse=True)
        best = dets.pop(0)
        kept.append(best)
        rescored = []
        for d in dets:
            if d[5] == best[5]:
                ov = _iou(best, d)
                if ov > 0:
                    d = (d[0], d[1], d[2], d[3],
                         d[4] * math.exp(-(ov * ov) / sigma), d[5])
            if d[4] >= score_thr:
                rescored.append(d)
        dets = rescored
    return kept


def _fuse(members):
    wsum = sum(m[4] for m in members) or 1.0
    return (sum(m[0] * m[4] for m in members) / wsum,
            sum(m[1] * m[4] for m in members) / wsum,
            sum(m[2] * m[4] for m in members) / wsum,
            sum(m[3] * m[4] for m in members) / wsum,
            max(m[4] for m in members), members[0][5])


def _wbf(dets, iou_thr):
    reps, clusters = [], []
    for d in sorted(dets, key=lambda d: d[4], reverse=True):
        for i, rep in enumerate(reps):
            if rep[5] == d[5] and _iou(rep, d) >= iou_thr:
                clusters[i].append(d)
                reps[i] = _fuse(clusters[i])
                break
        else:
            reps.append(tuple(d))
            clusters.append([d])
    return reps


def _merge(dets, iou_thr, mode):
    if mode == "wbf":
        return _wbf(dets, iou_thr)
    if mode == "soft":
        return _soft_nms(dets, iou_thr)
    return _nms(dets, iou_thr)


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
        ys = (np.arange(nh) / ratio).astype(int).clip(0, h - 1)
        xs = (np.arange(nw) / ratio).astype(int).clip(0, w - 1)
        resized = img[ys][:, xs]
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[py:py + nh, px:px + nw] = resized
    blob = canvas.astype("float32") / 255.0
    blob = blob.transpose(2, 0, 1)[None]
    return blob, (px, py), ratio
