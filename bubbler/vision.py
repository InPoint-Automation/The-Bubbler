# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Lazy vision assist. Vector-stroke symbols + OCR fallback.

import collections
import re
import threading

from . import common as _common

_VBLOCK = 900000

_SESS_LOCK = threading.Lock()  # prewarm races scan pool


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
    """Per-pass availability booleans for settings UI."""
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
            "gpu": _gpu_in_use(cfg or {}),
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
    """Record why pass unavailable."""
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
        # macOS wheel carries CoreML
        "coreml":   ["CoreMLExecutionProvider", "CPUExecutionProvider"],
        "auto":     ["CUDAExecutionProvider", "DmlExecutionProvider",
                     "CoreMLExecutionProvider", "CPUExecutionProvider"],
    }.get(str((cfg or {}).get("vision_ep", "auto")).lower(),
          ["CPUExecutionProvider"])
    out = [p for p in pref if p in avail]
    return out or ["CPUExecutionProvider"]


class _RemoteSession:
    """onnxruntime session run() to GPU worker."""

    def __init__(self, path, cfg):
        from . import gpu
        self._path = path
        self._runner = gpu.runner()
        m = self._runner.meta(path)
        if m is None:
            raise RuntimeError("gpu worker meta failed")
        self._in = m["inputs"]
        self._out = m["outputs"]
        self._providers = m.get("providers", [])

    def get_inputs(self):
        return [type("I", (), {"name": n})() for n in self._in]

    def get_outputs(self):
        return [type("O", (), {"name": o["name"], "shape": o["shape"]})()
                for o in self._out]

    def get_providers(self):
        return self._providers

    def run(self, output_names, feed):
        outs = self._runner.run(self._path, feed)
        if outs is None:
            raise RuntimeError("gpu worker run failed")
        return outs


def _gpu_ready(cfg):
    if not cfg.get("vision_gpu", True):
        return False
    try:
        from . import gpu
        return gpu.is_linux() and gpu.is_installed()
    except Exception:
        return False


_CUDA_PRELOADED = False
_CUDA_PRELOADED_N = 0


def _preload_cuda_libs():
    """dlopen pip CUDA libs so CUDA EP finds them. Returns count. Never raises."""
    global _CUDA_PRELOADED, _CUDA_PRELOADED_N
    if _CUDA_PRELOADED:
        return _CUDA_PRELOADED_N       # later caller reports it
    _CUDA_PRELOADED = True
    import ctypes
    import glob as _glob
    import os as _os
    try:
        import nvidia
        roots = list(getattr(nvidia, "__path__", []))
    except Exception:
        return 0
    libs = []
    for root in roots:
        # cu13/lib and pkg/lib layouts
        libs += _glob.glob(_os.path.join(root, "*", "lib", "*.so*"))
        libs += _glob.glob(_os.path.join(root, "*", "*", "lib", "*.so*"))
    if not libs:
        return 0
    done = set()
    # 2 passes for interdeps
    for _ in range(2):
        for lib in libs:
            if lib in done:
                continue
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                done.add(lib)
            except OSError:
                pass
    _CUDA_PRELOADED_N = len(done)
    return _CUDA_PRELOADED_N


def _make_session(ort, path, cfg):
    """Open session. Route to GPU worker on linux when possible."""
    if _gpu_ready(cfg):
        try:
            return _RemoteSession(path, cfg)
        except Exception as e:
            _note("ep", "gpu worker unavailable (%s); running on CPU" % e)
    prefer = _providers(cfg)
    if any(p.startswith("CUDA") for p in prefer):
        _preload_cuda_libs()
    try:
        return ort.InferenceSession(path, providers=prefer)
    except Exception as e:
        if prefer == ["CPUExecutionProvider"]:
            raise
        _note("ep", "%s failed to init (%s); running vision on CPU"
              % (prefer[0], e))
        return ort.InferenceSession(path, providers=["CPUExecutionProvider"])


def _gpu_in_use(cfg=None):
    """True when LOADED detector session runs on non-CPU provider."""
    cfg = cfg or {}
    for get in (_symbol_session, _region_session, _fcf_cls_session):
        try:
            sess = get(cfg)
        except Exception:
            sess = None
        if sess is None:
            continue
        try:
            prov = list(sess.get_providers() or [])
        except Exception:
            prov = []
        if prov and not prov[0].startswith("CPU"):
            return True
    return False


def reset_sessions():
    global _SYM_SESS, _SYM_TRIED, _RGN_SESS, _RGN_TRIED, _OCR, _OCR_TRIED
    global _PADDLE, _PADDLE_TRIED, _VLM, _VLM_TRIED, _EP_LOGGED, _VLM_DEAD
    _SYM_SESS = _RGN_SESS = _OCR = _PADDLE = _VLM = None
    _SYM_TRIED = _RGN_TRIED = _OCR_TRIED = _PADDLE_TRIED = _VLM_TRIED = False
    _VLM_DEAD = False
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
    # honours /Rotate (display space)
    x0, y0, x1, y1 = rect
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    s = max(1.0, float(dpi)) / 72.0
    try:                                  # unrenderable page -> no-op
        pix = page.get_pixmap(matrix=fitz.Matrix(s, s),
                              clip=fitz.Rect(x0, y0, x1, y1), alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n)
    except Exception:
        return None
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
    """Glyph or keyword already in text."""
    t = (tok or "").strip().upper()
    if t and any(w.startswith(t) for w in have_upper.split()):
        return True
    kw = _glyph_keyword(tok)
    if kw and kw in have_upper:
        return True
    return False


def _wrap_enclosed(out, rect, symbol):
    """Wrap number enclosed by BASIC box / REFERENCE parens. True if done."""
    close = _SYM_WRAP.get(symbol)
    if close is None:
        return False
    x0, y0, x1, y1 = rect
    best = None
    for i, w in enumerate(out):
        wt = str(w[4]).strip()
        if not wt or wt.startswith(symbol):
            continue
        cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        area = max(1e-6, (w[2] - w[0]) * (w[3] - w[1]))
        if best is None or area > best[0]:
            best = (area, i)
    if best is None:
        return True                     # nothing enclosed
    i = best[1]
    w = out[i]
    out[i] = (min(x0, w[0]), min(y0, w[1]), max(x1, w[2]), max(y1, w[3]),
              symbol + str(w[4]).strip() + close) + tuple(w[5:8])
    return True


def _attach_or_append(out, rect, symbol):
    """Prepend symbol to nearest right number or append."""
    from .scanpos import _GLYPHS

    def _lead(s):
        c = s[:1]
        return _GLYPHS.get(c, c)

    if _wrap_enclosed(out, rect, symbol):
        return
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
    """Detect vector Ø/R marks and attach to adjacent number."""
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
    """-> (kind, engine) for configured OCR engine. RapidOCR fallback."""
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
# a GPU/resource failure (e.g. CUBLAS out of memory) latches the VLM off for
# the session, so a drag capture does not re-OOM the GPU on every read
_VLM_DEAD = False


def _is_resource_error(e):
    """A CUDA/GPU out-of-resource failure, not a plain read miss."""
    s = str(e).lower()
    return any(w in s for w in ("cublas", "cuda", "out of memory", "cudnn",
                                "resource", "cudaerror", "gpu"))


def _vlm_died(e):
    """Latch the VLM off after a GPU/resource failure. Returns True if latched."""
    global _VLM_DEAD
    if _VLM_DEAD or not _is_resource_error(e):
        return _VLM_DEAD
    _VLM_DEAD = True
    _warn("VLM disabled for this session after a GPU/resource failure (%s)" % e)
    return True


def _vlm_module(cfg):
    if str((cfg or {}).get("vision_vlm_engine", "florence")).lower() \
            == "paddleocr_vl":
        from . import paddlevl
        return paddlevl, paddlevl.PaddleOCRVL
    from . import florence
    return florence, florence.Florence2


def _vlm_engine(cfg):
    """Lazily load + warm VLM reader. None if absent or GPU-latched off."""
    global _VLM, _VLM_TRIED
    if _VLM_DEAD:
        return None
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

# (glyph, kit NAME) pairs. Order contractual = train/classes.txt
_SYM = (
    ("Ø", "diameter"), ("R", "radius"),
    ("⌖", "position"), ("⏥", "flatness"),
    ("○", "circularity"), ("⌭", "cylindricity"),
    ("⟂", "perpendicularity"), ("∥", "parallelism"), ("∠", "angularity"),
    ("◎", "concentricity"),
    ("⌒", "profile_line"), ("⌓", "profile_surface"),
    ("⌰", "runout_total"), ("↗", "runout_circular"),
    ("Ra", "surface_roughness"),                     # -> Ra (SURFACE pattern)
    ("DEEP ", "depth"), ("CBORE ", "counterbore"), ("CSINK ", "countersink"),
    ("⏤", "straightness"), ("⌯", "symmetry"),        # ASME Y14.5
    ("[", "basic_box"), ("(", "ref_parens"),         # wrap
    ("EDGE ", "edge_symbol"),                        # ISO 13715 edge
)
_SYM_CLASSES = tuple(g for g, _n in _SYM)
_SYM_NAMES = tuple(n for _g, n in _SYM)

# BASIC/REF marks wrap number (K4a)
_SYM_WRAP = {"[": "]", "(": ")"}


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


def _sess_imgsz(sess, fallback=640):
    """ONNX exported input size when static or fallback."""
    try:
        shape = sess.get_inputs()[0].shape
    except Exception:
        return int(fallback)
    if len(shape) == 4:
        h, w = shape[2], shape[3]
        if isinstance(h, int) and isinstance(w, int) and h == w and h > 0:
            return int(h)
    return int(fallback)


def _out_nc(sess, expected=None):
    """YOLO class count"""
    try:
        shape = sess.get_outputs()[0].shape
    except Exception:
        return None
    if len(shape) == 3 and isinstance(shape[1], int):
        nc = shape[1] - 4
        if expected is not None and nc == expected + 1:
            return nc - 1
        return nc
    return None


def _symbol_session(cfg):
    """Lazily open ONNX symbol detector. None if runtime/model absent."""
    global _SYM_SESS, _SYM_TRIED, _EP_LOGGED
    if _SYM_TRIED:
        return _SYM_SESS
    with _SESS_LOCK:                     # prewarm races scan pool
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
            nc = _out_nc(_SYM_SESS, len(_SYM_CLASSES))
            if nc is None:
                _warn("could not read symbol model class count; guard skipped")
            elif nc != len(_SYM_CLASSES):
                # mislabels every symbol
                _note("symbols", "symbol model class mismatch: model nc=%d, "
                      "code expects %d (train/classes.txt); this model "
                      "predates the current class list and must be retrained. "
                      "Every read would be mislabelled, so the symbol pass is "
                      "disabled -- text parsing still runs"
                      % (nc, len(_SYM_CLASSES)))
                _SYM_SESS = None
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
    """(mtime, size) for model file"""
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
            "vision_ep", "vision_symbols", "vision_region",
            "vision_region_tile")
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
    """Warm ONNX sessions off first-scan critical path. Never raises."""
    cfg = cfg or {}
    if not cfg.get("vision_assist"):
        return
    try:
        import numpy as np
    except Exception:
        return
    blank = np.full((64, 64, 3), 255, np.uint8)
    for get, nc in ((_symbol_session, len(_SYM_CLASSES)),
                    (_region_session, len(_REGION_CLASSES))):
        try:
            sess = get(cfg)
            if sess is not None:
                _run_det(sess, blank, _sess_imgsz(sess,
                     cfg.get("vision_imgsz", 640)), nc, 0.99, 0.45, np)
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
    imgsz = _sess_imgsz(sess, cfg.get("vision_imgsz", 640))
    iou = float(cfg.get("vision_nms_iou", 0.45))
    h, w = img.shape[:2]
    use_tile = (tile and cfg.get("vision_tile", True)
                and max(h, w) > imgsz * 1.5)
    if not use_tile:
        dets = _run_det(sess, img, imgsz, nc, conf, iou, np)
    else:
        overlap = min(0.9, max(0.0, float(cfg.get("vision_tile_overlap", 0.2))))
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
    imgsz = _sess_imgsz(sess, cfg.get("vision_imgsz", 640))
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


# Detector head order. ONE definition in common.py
_REGION_CLASSES = _common.TRAINED_REGION_CLASSES

# K5 furniture containment
_FURNITURE_CI = None


def _furniture_indexes():
    global _FURNITURE_CI
    if _FURNITURE_CI is None:
        _FURNITURE_CI = frozenset(
            _REGION_CLASSES.index(c) for c in _common.DETECTED_FURNITURE)
    return _FURNITURE_CI


def _drop_furniture_contents(boxes):
    """Drop non-furniture detections inside furniture box. Box kept."""
    furn = _furniture_indexes()
    if not furn:
        return boxes
    rects = [b for b in boxes if len(b) > 5 and int(b[5]) in furn]
    if not rects:
        return boxes
    out = []
    for b in boxes:
        if len(b) > 5 and int(b[5]) in furn:
            out.append(b)
            continue
        cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        if any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in rects):
            continue
        out.append(b)
    return out

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
            nc = _out_nc(_RGN_SESS, len(_REGION_CLASSES))
            if nc is None:
                _warn("could not read region model class count; guard skipped")
            elif nc != len(_REGION_CLASSES):
                # wrong class breaks ADMIT
                _note("region", "region model class mismatch: model nc=%d, "
                      "code expects %d; this model predates the current class "
                      "list (bubbler/common.REGION_CLASSES) and must be "
                      "retrained. Every block would be mislabelled, so the "
                      "region pass is disabled and block grouping falls back "
                      "to geometry" % (nc, len(_REGION_CLASSES)))
                _RGN_SESS = None
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
    # shipped model whole-page
    for x0, y0, x1, y1, c, ci in _detect_page(
            _region_session(cfg), page, cfg, len(_REGION_CLASSES),
            conf, tile=bool(cfg.get("vision_region_tile", False))):
        if 0 <= ci < len(_REGION_CLASSES):
            out.append((x0, y0, x1, y1, c, ci))
    out = _drop_furniture_contents(out)
    out = _orient_refit(out, page, cfg)
    _cache_put(key, out)
    return out


def _orient_refit(boxes, page, cfg):
    """Refit a diagonal callout box to a quad, carried as a 7th field (AP-ROT)"""
    if not cfg.get("vision_orient_refit", True):
        return [tuple(b) + (None,) for b in boxes]
    from . import orient
    lines = _orient_page_lines(page)
    out = []
    for b in boxes:
        quad = None
        if lines:
            try:
                quad = orient.refit((b[0], b[1], b[2], b[3]), lines)
            except Exception:
                quad = None
        out.append((b[0], b[1], b[2], b[3], b[4], b[5], quad))
    return out


def _orient_page_lines(page):
    """orient text lines mapped to display space, matching the region boxes"""
    import math
    try:
        from . import orient
        lines = orient.page_lines(page)
    except Exception:
        return []
    if not lines:
        return []
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    if not rot:
        return lines
    try:
        from . import scanpos
        m = page.rotation_matrix
        a, b, c, d = m.a, m.b, m.c, m.d
    except Exception:
        return []                       # no map to display space: refit skipped
    out = []
    for bb, deg, t in lines:
        rb = scanpos.xform_rect(m, bb[0], bb[1], bb[2], bb[3])
        dx, dy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        ang = math.degrees(math.atan2(b * dx + d * dy,
                                      a * dx + c * dy)) % 360.0
        out.append((rb, ang, t))
    return out


def _page_sections(page, cfg):
    """Cached page-wide callout sections"""
    key = _cache_key(page, cfg, "sec")
    hit = _cache_get(key)
    if hit is not None:
        return hit
    from bubbler import scanpos
    try:
        out = scanpos.page_sections(page, cfg)
    except Exception:
        out = []
    _cache_put(key, out)
    return out


def _point_in_quad(px, py, quad):
    """Point inside a 4-corner polygon, ray cast"""
    inside = False
    n = len(quad)
    j = n - 1
    for i in range(n):
        xi, yi = quad[i]
        xj, yj = quad[j]
        if ((yi > py) != (yj > py)) and \
                (px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _center_in(word, rect, quad=None):
    cx = (word[0] + word[2]) / 2.0
    cy = (word[1] + word[3]) / 2.0
    if quad is not None:
        return _point_in_quad(cx, cy, quad)
    return rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]


def orphan_symbols(region_boxes, symbol_dets):
    """Symbol detections whose CENTRE lies in no region box (K8a)."""
    return [(box, tok) for box, tok in symbol_dets
            if not any(_center_in(box, r) for r in region_boxes)]


def _overlap_frac(word, rect, quad=None):
    """Fraction of word inside rect."""
    if quad is not None:                 # tight quad: centre decides, no bbox clip
        return 1.0 if _center_in(word, rect, quad) else 0.0
    area = (word[2] - word[0]) * (word[3] - word[1])
    if area <= 0:                       # degenerate word
        return 1.0 if _center_in(word, rect) else 0.0
    ix = min(word[2], rect[2]) - max(word[0], rect[0])
    iy = min(word[3], rect[3]) - max(word[1], rect[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    return min(1.0, (ix * iy) / area)


# below half recovers clipped
_WORD_MIN_FRAC = 0.25


def _assign_words(words, rects, quads=None, min_frac=_WORD_MIN_FRAC):
    """Word indexes per block. Each word lands in AT MOST ONE block."""
    out = [[] for _ in rects]
    for wi, w in enumerate(words):
        best = None
        for ri, r in enumerate(rects):
            q = quads[ri] if quads else None
            f = _overlap_frac(w, r, q)
            if f <= 0.0:
                continue
            if f < min_frac and not _center_in(w, r, q):
                continue
            rank = (f, -abs((r[2] - r[0]) * (r[3] - r[1])), -ri)
            if best is None or rank > best[0]:
                best = (rank, ri)
        if best is not None:
            out[best[1]].append(wi)
    return out


def _rects_overlap(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _fcf_glyph_count(text):
    """How many DISTINCT characteristic glyphs in symbol band."""
    from .scanlib import _GDT_SYMBOLS
    return len({g for g, _kw in _GDT_SYMBOLS if g in (text or "")})


def _fcf_symbol_kw(text):
    from .scanlib import _GDT_SYMBOLS
    for glyph, kw in _GDT_SYMBOLS:
        if glyph in text:
            return kw.split()
    return None


# SORTED (ultralytics folder order)
_FCF_CLASSES = tuple(sorted((
    "angularity", "circularity", "concentricity", "cylindricity", "flatness",
    "none", "parallelism", "perpendicularity", "position", "profile_line",
    "profile_surface", "runout_circular", "runout_total", "straightness",
    "symmetry")))

# characteristic -> healed glyph
_FCF_GLYPH = {
    "position": "⌖", "flatness": "⏥", "circularity": "○",
    "cylindricity": "⌭", "perpendicularity": "⟂", "parallelism": "∥",
    "angularity": "∠", "concentricity": "◎", "profile_line": "⌒",
    "profile_surface": "⌓", "runout_total": "⌰", "runout_circular": "↗",
    "straightness": "⏤", "symmetry": "⌯",
}

_FCF_SESS = None
_FCF_TRIED = False


def _fcf_kw_for(name):
    """Characteristic name -> keyword tokens _fcf_symbol_kw returns."""
    from .scanlib import _GDT_SYMBOLS
    glyph = _FCF_GLYPH.get(name)
    if not glyph:
        return None
    for g, kw in _GDT_SYMBOLS:
        if g == glyph:
            return kw.split()
    return None


def _fcf_cls_path(cfg):
    import os
    p = (cfg or {}).get("vision_fcf_model")
    if p and os.path.exists(p):
        return p
    for root in _onnx_roots():
        cand = os.path.join(root, "models", "gdt_fcf.onnx")
        if os.path.exists(cand):
            return cand
    return None


def _fcf_cls_session(cfg):
    """Lazy classifier session. None when absent."""
    global _FCF_SESS, _FCF_TRIED
    if _FCF_TRIED:
        return _FCF_SESS
    with _SESS_LOCK:
        if _FCF_TRIED:
            return _FCF_SESS
        _FCF_TRIED = True
        path = _fcf_cls_path(cfg)
        if not path:
            return None
        try:
            import onnxruntime as ort
            _FCF_SESS = _make_session(ort, path, cfg)
            nc = None
            try:
                shape = _FCF_SESS.get_outputs()[0].shape
                if len(shape) == 2 and isinstance(shape[1], int):
                    nc = shape[1]
            except Exception:
                nc = None
            if nc is not None and nc != len(_FCF_CLASSES):
                _note("fcf", "characteristic model class mismatch: model nc=%d,"
                      " code expects %d; pass disabled"
                      % (nc, len(_FCF_CLASSES)))
                _FCF_SESS = None
        except Exception as e:
            _note("fcf", "characteristic model unavailable (%s)" % e)
            _FCF_SESS = None
        return _FCF_SESS


def _cls_blob(img, size, np):
    """Preprocess for YOLO CLASSIFIER. Short-side resize then centre crop."""
    h, w = img.shape[:2]
    r = float(size) / min(h, w)
    nh, nw = max(size, int(round(h * r))), max(size, int(round(w * r)))
    try:
        import cv2
        resized = cv2.resize(img, (nw, nh))
    except Exception:
        ys = (np.arange(nh) / (nh / float(h))).astype(int).clip(0, h - 1)
        xs = (np.arange(nw) / (nw / float(w))).astype(int).clip(0, w - 1)
        resized = img[ys][:, xs]
    top, left = (nh - size) // 2, (nw - size) // 2
    crop = resized[top:top + size, left:left + size]
    return (crop.astype("float32") / 255.0).transpose(2, 0, 1)[None]


def _fcf_symbol_from_crop(page, cfg, rect):
    """Read geometric characteristic off FRAME image."""
    sess = _fcf_cls_session(cfg)
    if sess is None:
        return None
    try:
        import numpy as np
    except Exception:
        return None
    pm = _pixmap_clip(page, cfg, rect, cfg.get("vision_fcf_dpi", 600))
    if pm is None:
        return None
    img = pm[0]
    size = _sess_imgsz(sess, 224)
    try:
        blob = _cls_blob(img, size, np)
        pred = np.asarray(sess.run(None, {sess.get_inputs()[0].name: blob})[0])
    except Exception as e:                              # pragma: no cover
        _warn("characteristic read failed (%s)" % e)
        return None
    if pred.ndim == 2:
        pred = pred[0]
    if pred.size != len(_FCF_CLASSES):
        return None
    i = int(pred.argmax())
    p = float(pred[i])
    if p < float(cfg.get("vision_fcf_cls_conf", 0.5)):
        return None
    name = _FCF_CLASSES[i]
    if name == "none":
        return None                       # not frame
    return _fcf_kw_for(name)


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


def _fcf_row_rect(brect, row):
    """Row band clipped to frame box."""
    return (brect[0], max(brect[1], row[0]), brect[2], min(brect[3], row[1]))


def _fcf_symbol_for(page, cfg, rect, words):
    """Characteristic from words or crop."""
    sym = _fcf_symbol_kw(" ".join(str(w[4]) for w in words))
    if not sym and cfg.get("vision_fcf_classify", True):
        sym = _fcf_symbol_from_crop(page, cfg, rect)
    return sym


def _fcf_band_of(row, bands):
    """Symbol-cell band holding row"""
    cy = (row[0] + row[1]) / 2.0
    for lo, hi in bands:
        if lo <= cy <= hi:
            return (lo, hi)
    return row


def _fcf_glyph_for(sb):
    """Representative glyph for characteristic"""
    from .scanlib import _GDT_SYMBOLS
    name = (sb or "").upper().strip()
    if name == "TOTAL RUNOUT":
        name = "RUNOUT"                      # bare glyph = total runout
    if name:
        for glyph, kw in _GDT_SYMBOLS:       # exact match first
            if name == kw.strip():
                return glyph
        for glyph, kw in _GDT_SYMBOLS:
            if name in kw.strip():
                return glyph
    return "⌖"


def _fcf_flag(h, code):
    """Record review flag code on hit."""
    from .scanlib import gdt_flag
    gdt_flag(h, code)


def _fcf_bands(rows, sym_rows):
    """[(symbol band, [row indexes])]. Band over >1 row is composite."""
    out = []
    for ri in range(len(rows)):
        band = _fcf_band_of(rows[ri], sym_rows)
        if out and out[-1][0] == band:
            out[-1][1].append(ri)
        else:
            out.append((band, [ri]))
    return out


def _fcf_row_words(per_cell, ci, rows, ri):
    return [w for r, w in per_cell[ci] if r == ri or len(rows) == 1]


def _fcf_takes_datums(sb):
    """Does characteristic accept datums at all?"""
    from .scanlib import _GDT_MAX_DATUMS
    return _GDT_MAX_DATUMS.get(sb, 3) > 0


def _fcf_fix_zone(h, want):
    """Zone marker follows frame over pattern guess."""
    t = h.get("t") or ""
    v = h.get("v") or ""
    if want and (want + t) not in v:
        h["v"] = v.replace("Ø" + t, t, 1).replace(" " + t, " " + want + t, 1)
    elif not want and "Ø" in v:
        h["v"] = v.replace("SØ" + t, t, 1).replace("Ø" + t, t, 1)


def _fcf_apply_mods(h, parts):
    """Put every modifier back. MMC/LMC, projected height, free state."""
    mods = parts.get("mods") or []
    if not mods:
        return
    disp = " ".join(mods)
    head, sep, tail = (h.get("v") or "").partition(" | ")
    fed = mods[0][0] if mods[0][0] in "MLSP" else None
    at = re.search(r"(?<= )" + fed + r"(?= |$)", head) if fed else None
    if at is not None:
        if disp != fed:
            head = head[:at.start()] + disp + head[at.end():]
    else:
        # before zone (print order)
        zone = parts.get("zone") or ""
        if zone and head.rstrip().endswith(zone):
            head = head.rstrip()[:-len(zone)].rstrip() + " " + disp + " " + zone
        else:
            head = head.rstrip() + " " + disp
    h["v"] = head + sep + tail


# family name collapses subtypes. Read glyph refines.
_FCF_CHAR_FULL = ("PROFILE OF A LINE", "PROFILE OF A SURFACE",
                  "CIRCULAR RUNOUT", "TOTAL RUNOUT")


def _fcf_refine_char(h, sym):
    """Restore subtype scanlib's family pattern collapsed."""
    name = " ".join(sym or ()).upper().strip()
    if name == "RUNOUT":
        name = "TOTAL RUNOUT"                # bare glyph = total runout
    if name not in _FCF_CHAR_FULL:
        return
    h["fcf_char"] = name
    sb = h.get("sb") or ""
    v = h.get("v") or ""
    if sb and v.startswith(sb + " "):
        h["v"] = name + v[len(sb):]


def _fcf_compose(segs):
    """Composite frame -> ONE control (ASME Y14.5 / ISO 1101)."""
    h = segs[0]
    # seg rects for dedup
    h["fcf_seg_rects"] = [x.get("arect") or x.get("rect") for x in segs]
    for s in segs[1:]:
        v = s.get("v") or ""
        sb = s.get("sb") or ""
        if sb and v.startswith(sb + " "):
            v = v[len(sb) + 1:]
        h["v"] = (h.get("v") or "") + " // REFINEMENT " + v
        for c in s.get("fcf_flags") or []:
            _fcf_flag(h, c)
        if s.get("fcf_zone_suspect"):
            h["fcf_zone_suspect"] = True
    h["fcf_composite"] = True
    _fcf_flag(h, "composite")
    return h


def _fcf_row_hit(page, cfg, sym, per_cell, cells, rows, ri, rrect, bi):
    """One frame row -> parsed GD&T hits ([] when unreadable)"""
    from bubbler import scanpos
    parts = _fcf_tol_parts(_fcf_row_words(per_cell, 1, rows, ri))
    if not parts["tol"]:
        return []
    datum_txt = []
    datum_bad = False
    for ci in range(2, len(cells)):
        toks, bad = _fcf_datum_parse(_fcf_row_words(per_cell, ci, rows, ri))
        datum_txt.extend(toks)
        datum_bad = datum_bad or bad
    mark = "SØ" if parts["tol"].startswith("SØ") else (
        "Ø" if parts["tol"].startswith("Ø") else "")
    # mirrors text reader
    from .scanlib import gdt_zone_wrong
    suspect = gdt_zone_wrong(" ".join(sym or ()), mark)
    toks = _fcf_line_tokens(sym, parts, datum_txt, rrect)
    if toks is None:
        return []
    line = {"key": (_VBLOCK + bi, ri), "toks": toks}
    hits = [h for h in scanpos.parse_lines([line], cfg=cfg)
            if h.get("tp") == "GDT"]
    for h in hits:
        h["rect"] = rrect
        # arect = row for dedup anchor
        h["arect"] = _fcf_row_rect(rrect, rows[ri]) if ri < len(rows) \
            else rrect
        h["cg"] = _VBLOCK + bi
        _fcf_fix_zone(h, mark)      # frame marker as drawn
        if suspect:
            h["fcf_zone_suspect"] = True     # flat zone read as Ø
            _fcf_flag(h, "zone_suspect")
        if parts.get("bare_mod"):
            _fcf_flag(h, "bare_mod")         # W63: dropped bare F/T/E
        _fcf_apply_mods(h, parts)
        _fcf_refine_char(h, sym)
        if datum_bad or (datum_txt and " | " not in h["v"]
                         and _fcf_takes_datums(h.get("sb"))):
            _fcf_flag(h, "datum_lost")       # datums read not emitted
            h["fcf_partial"] = True
    return hits


def _rect_holds_rect(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def _fcf_words_in(page, rect, have):
    """Re-read words inside FRAME to catch box-clipped."""
    from bubbler import scanpos
    try:
        words = scanpos.page_words(page)
    except Exception:
        return have
    out = [w for w in words
           if rect[0] - 1 <= (w[0] + w[2]) / 2.0 <= rect[2] + 1
           and rect[1] - 1 <= (w[1] + w[3]) / 2.0 <= rect[3] + 1]
    return out or have


# Unread frames for debug overlay. Bounded.
_UNREAD = collections.deque(maxlen=200)


def unread_frames():
    """No-callout frames. Newest last."""
    return list(_UNREAD)


def clear_unread():
    _UNREAD.clear()


def _note_unread(rect, bi, words):
    _UNREAD.append({"rect": tuple(rect) if rect else None, "box": bi,
                    "text": " ".join(str(w[4]) for w in (words or ()))[:200]})


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
    sym_rows = seg.get("sym_rows") or rows
    if len(cells) < 2:
        return []
    # re-collect words box clipped
    rrect = seg.get("frame") or brect
    if rrect is not brect and not _rect_holds_rect(brect, rrect):
        block_words = _fcf_words_in(page, rrect, block_words)
    def _read(cells):
        per_cell = [[] for _ in cells]
        for w in block_words:
            ci = _fcf_cell_of(w, cells)
            if ci is None:
                continue
            ri = _fcf_row_of(w, rows)
            per_cell[ci].append((ri, w))
        out = []
        dropped = False
        for band, ris in _fcf_bands(rows, sym_rows):
            # symbol spans rows read once
            sym_words = [w for _r, w in per_cell[0]
                         if band[0] <= (w[1] + w[3]) / 2.0 <= band[1]]
            sym = _fcf_symbol_for(page, cfg, _fcf_row_rect(brect, band),
                                  sym_words)
            if not sym:                    # never borrow another row's
                dropped = True
                continue
            segs = []
            for ri in ris:
                hits = _fcf_row_hit(page, cfg, sym, per_cell, cells, rows, ri,
                                    rrect, bi)
                if not hits:
                    dropped = True
                    continue
                segs.extend(hits)
            if not segs:
                continue
            if len(ris) > 1:               # one cell one control
                comp = _fcf_compose(segs)
                # 2 glyphs = 2 controls
                if _fcf_glyph_count(" ".join(w[4] for w in sym_words)) > 1:
                    _fcf_flag(comp, "symbol_mixed")
                    comp["fcf_partial"] = True
                out.append(comp)
                if len(segs) < len(ris):
                    dropped = True
            else:
                out.extend(segs)
        return out, dropped

    out, dropped = _read(cells)
    # W55: cells_alt fallback
    if not out and seg.get("cells_alt"):
        alt_out, alt_dropped = _read(seg["cells_alt"])
        if alt_out:
            out, dropped = alt_out, alt_dropped
    if dropped:
        for h in out:
            h["fcf_partial"] = True            # frame read incomplete
            _fcf_flag(h, "partial")
        if not out:
            # all bands failed
            _note_unread(rrect, bi, block_words)
    if seg.get("unboxed"):
        # no drawn box = guessed cells (Y14.5)
        for h in out:
            h["fcf_unboxed"] = True
            # arms legacy text fallback
            h["fcf_partial"] = True
            _fcf_flag(h, "unboxed")
    return out


# ISO 14405/1101 zone qualifiers. Match scanlib._ISO_ZONE
_FCF_ZONE_TOKENS = ("UZ", "CZ", "SZ", "OZ", "CT", "ACS", "ACL", "VA")


def _fcf_tol_parts(words):
    """Tolerance cell -> {tol, mods, zone}. No modifier dropped."""
    from .scanpos import _norm_token
    from .scanlib import (GDT_MOD_BARE, GDT_MOD_LETTERS,
                          GDT_MOD_TAKES_NUM, _MOD_TXT)
    txt = " ".join(_norm_token(str(w[4])).strip() for w in words)
    # S before _MOD_TXT rewrites Ⓢ
    _tk = [_norm_token(str(w[4])).strip().upper() for w in words]
    sph = False
    for _j, _t in enumerate(_tk):
        if not re.search(r"\d", _t):
            continue
        # S Ø 0.1 splits 3 ways
        sph = _t.startswith("S\u00d8") or (
            _t.startswith("\u00d8") and _j and _tk[_j - 1] == "S") or (
            _j > 1 and _tk[_j - 1] == "\u00d8" and _tk[_j - 2] == "S") or (
            _j and _tk[_j - 1] == "S\u00d8")
        break
    # mark circled mods. Bare F/T/E too common to claim.
    for a, b in _MOD_TXT.items():
        if len(a) == 1:
            txt = txt.replace(a, " \u0001" + b + " ")
    txt = re.sub(r"[()]", " ", txt).upper()
    # strip frame notes (SEP REQT etc)
    txt = re.sub(r"\b(?:SEP\s*REQT|SEP|REQT|ST|CF|UF|NC)\b", " ", txt)
    out = {"tol": "", "mods": [], "zone": ""}
    # tol value: SØ/Ø, per-unit, area
    m = re.search(r"((?:SØ|Ø)?\s*(?:\d+(?:\s*[.,]\s*\d+)?|[.,]\s*\d+)"
                  r"(?:\s*/\s*\d+(?:[.,]\d+)?"
                  r"(?:\s*[Xx×]\s*\d+(?:[.,]\d+)?)?)?)", txt)
    if not m:
        return out
    tol = re.sub(r"\s+", "", m.group(1))
    if sph and tol.startswith("Ø"):
        tol = "S" + tol
    out["tol"] = re.sub(r"^(S?Ø?)([.,])", r"\g<1>0\2", tol)  # .5 -> 0.5
    for mt in re.finditer(r"(\u0001?[A-Z]{1,3})"
                          r"\s*([+-]?\s*(?:\d+(?:[.,]\d+)?|[.,]\d+))?",
                          txt[m.end():]):
        tok = mt.group(1)
        circled = tok.startswith("\u0001")
        tok = tok.lstrip("\u0001")
        num = re.sub(r"\s+", "", mt.group(2) or "")
        if tok in _FCF_ZONE_TOKENS:
            if tok == "UZ" and not num[:1] in ("+", "-"):
                continue                   # UZ needs sign
            # printed order (ISO 1101:2017)
            one = tok + (num if tok == "UZ" else "")
            if one not in out["zone"].split():
                out["zone"] = (out["zone"] + " " + one).strip()
        elif tok in _MOD_TXT and len(tok) > 1:
            out["mods"].append(_MOD_TXT[tok])      # MMC / LMC / RFS
        elif len(tok) == 1 and (tok in GDT_MOD_BARE if not circled
                                else tok in GDT_MOD_LETTERS):
            # projected height leading-dot repair
            if num[:1] in (".", ","):
                num = "0" + num
            out["mods"].append(
                tok + (num if tok in GDT_MOD_TAKES_NUM else ""))
        elif (len(tok) == 1 and not circled
              and tok in GDT_MOD_LETTERS and tok not in GDT_MOD_BARE):
            # W63: bare F/T/E dropped
            out["bare_mod"] = True
    return out


def _fcf_tol_text(words):
    """Tolerance cell as one string (tolerance, modifiers, zone)"""
    p = _fcf_tol_parts(words)
    if not p["tol"]:
        return ""
    return " ".join([p["tol"]] + p["mods"] + ([p["zone"]] if p["zone"] else []))


def _fcf_datum_parse(words):
    """(datum tokens, bad). One junk datum must not delete others."""
    from .scanpos import _norm_token
    from .scanlib import _MOD_TXT
    txt = " ".join(_norm_token(str(w[4])) for w in words)
    # keep print spelling per occurrence
    glyph = {}
    for a, b in _MOD_TXT.items():
        if len(a) == 1 and a in txt:
            key = "\x01%s\x02" % b
            glyph[key] = a
            txt = txt.replace(a, " (" + key + ") ")
    out = []
    used = []
    # datum keeps ONE modifier
    for mt in re.finditer(r"\b([A-Z](?:-[A-Z])+|[A-Z])\b"
                          r"(?:\s*(?:\(\s*(\x01?[MLSPFT]\x02?)\s*\)"
                          r"|([MLSP])\b))?"
                          r"(?:\s*\(\s*\x01?[MLSPFT]\x02?\s*\))*", txt):
        d = mt.group(1)
        mod = mt.group(2) or mt.group(3)
        if mod and mod in glyph:
            d += glyph[mod]                     # print drew circle
            mod = mod.strip("\x01\x02")
        elif mod in ("M", "L", "S", "P", "F", "T"):
            # re-attach ASCII modifier incl F/T
            d += "(" + mod + ")"
        out.append(d)
        used.append((mt.start(), mt.end()))
    left = txt
    for a, b in reversed(used):
        left = left[:a] + left[b:]
    return out, bool(re.search(r"[A-Za-z0-9]", left))


def _fcf_datum_tokens(words):
    return _fcf_datum_parse(words)[0]


# Ø-zone table lives in scanlib
def _fcf_no_dia_zone(sym):
    """Zone can never be cylindrical?"""
    from .scanlib import gdt_no_dia_zone
    return gdt_no_dia_zone(sym)


def _fcf_line_tokens(sym, parts, datum_txt, rrect):
    words = list(sym)
    tol = parts.get("tol") or ""
    if not tol:
        return None
    # drop Ø, restored downstream
    tol = tol[2:] if tol.startswith("SØ") else (
        tol[1:] if tol.startswith("Ø") else tol)
    words.append(tol)
    mods = parts.get("mods") or []
    if mods and mods[0][0] in "MLSP":
        words.append(mods[0][0])           # one bare modifier
    if parts.get("zone"):
        words.append(parts["zone"])
    words.extend(datum_txt)
    return [{"t": t, "r": tuple(rrect)} for t in words if t]


# duplicate evidence bands 1.0 apart. Conf <= 0.4
_EV_READER = 3.0     # OCR/VLM/structural read
_EV_AGREE = 2.0      # block class admits
_EV_PLAIN = 1.0      # block has no opinion
_EV_TEXT = 0.5       # plain page text scan
_EV_CONFLICT = 0.0   # block class refuses
_EV_CONF_W = 0.4

_ADMIT_GLYPHS = None


def _admit_glyphs():
    """Every glyph any ADMIT set names"""
    global _ADMIT_GLYPHS
    if _ADMIT_GLYPHS is None:
        from . import common
        out = set()
        for allow in common.ADMIT.values():
            if allow:
                out |= set(allow)
        _ADMIT_GLYPHS = frozenset(out)
    return _ADMIT_GLYPHS


def _hit_glyph(h):
    """Domain glyph read means. None = nothing to check against."""
    tp = h.get("tp")
    if tp == "GDT":
        return _fcf_glyph_for(h.get("fcf_char") or h.get("sb"))
    if tp == "SURFACE":
        return "Ra"
    v = (h.get("v") or "").strip()
    return v[:1] if v[:1] in _admit_glyphs() else None


def _region_evidence(h, region_cls, conf=0.0, reader="text", structural=False):
    """Score region read against its source block."""
    from . import common
    try:
        c = min(1.0, max(0.0, float(conf)))
    except (TypeError, ValueError):
        c = 0.0
    if structural or reader in ("ocr", "vlm"):
        return _EV_READER + _EV_CONF_W * c
    cat = common.CATEGORY.get(region_cls)
    constraint = cat[2] if cat else None
    if not common.ADMIT.get(constraint):
        return _EV_PLAIN + _EV_CONF_W * c
    g = _hit_glyph(h)
    if g is None:
        return _EV_PLAIN + _EV_CONF_W * c
    band = _EV_AGREE if common.admits(constraint, g) else _EV_CONFLICT
    return band + _EV_CONF_W * c


def _evidence(h):
    """Corroboration score. Plain text read is baseline."""
    try:
        return float(h.get("_ev", _EV_TEXT))
    except (TypeError, ValueError):                     # pragma: no cover
        return _EV_TEXT


def _strip_ev(hits):
    """Drop scoring field before hits become ledger data."""
    for h in hits or ():
        h.pop("_ev", None)
    return hits


def _vlm_wanted(cfg, allow_vlm):
    """Which VLM uses are on: (load_engine, is_fallback_reader)."""
    fallback = bool(allow_vlm and cfg.get("vision_vlm"))
    xcheck = bool(allow_vlm and cfg.get("vision_vlm_crosscheck"))
    return (fallback or xcheck, fallback)


def _hits_coincide(a, b, tol=12.0):
    """Two reads of roughly same place. Missing rect falls back to block match."""
    ra, rb = a.get("rect"), b.get("rect")
    if not ra or not rb:
        return True
    return _rects_overlap(ra, rb)


def _crosscheck_block(region_cls, hits):
    """Block worth VLM second opinion? FCFs and toleranced dimensions."""
    if region_cls == "feature_control_frame":
        return True
    return any((h.get("t") or "").strip() for h in hits)


def _crosscheck_stamp(hits, vhits):
    """Stamp `xcheck` on each primary hit from VLM reads (pure)."""
    for h in hits:
        near = [vh for vh in vhits if _hits_coincide(h, vh)]
        if not near:
            h.setdefault("xcheck", "uncorroborated")
            continue
        key = (h.get("tp"), str(h.get("v")), h.get("t") or "")
        if any((vh.get("tp"), str(vh.get("v")), vh.get("t") or "") == key
               for vh in near):
            h["xcheck"] = "agree"
        else:
            vh = near[0]
            alt = str(vh.get("v") or "")
            if vh.get("t"):
                alt = "%s %s" % (alt, vh["t"])
            h["xcheck"] = "disagree"
            h["xcheck_alt"] = alt


def _apply_vlm_crosscheck(img, s, brect, bi, hits, vlm, include_bare, cfg):
    """VLM SECOND opinion on block crop. Adds no rows."""
    from bubbler import scanpos
    try:
        vwords = _vlm_read_block(img, s, brect, vlm, _VBLOCK + 9000 + bi * 100)
        vhits = scanpos.scan_words(vwords, include_bare=include_bare, cfg=cfg)
    except Exception as e:                               # best-effort only
        _vlm_died(e)                                     # GPU OOM: latch off
        return
    _crosscheck_stamp(hits, vhits)


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
    # VLM: fallback + crosscheck
    load_vlm, use_fallback = _vlm_wanted(cfg, allow_vlm)
    vlm = _vlm_engine(cfg) if load_vlm else None
    vlm_fallback = vlm if use_fallback else None
    force_vlm = bool(vlm_fallback is not None and cfg.get("vision_vlm_always"))
    sym_dets = _symbol_dets(page, cfg) if cfg.get("vision_symbols", True) else []
    table_cls = _REGION_CLASSES.index("hole_table")
    from . import common
    sections = (_page_sections(page, cfg)
                if cfg.get("vision_section_group", True) else [])
    # pass 1: assign words once
    blocks = []
    for bi, b in enumerate(boxes):
        brect = (b[0], b[1], b[2], b[3])
        quad = b[6] if len(b) > 6 else None
        region_cls = (_REGION_CLASSES[int(b[5])]
                      if len(b) > 5 and 0 <= int(b[5]) < len(_REGION_CLASSES)
                      else None)
        cat = common.CATEGORY.get(region_cls)
        cat_kind = cat[0] if cat else None
        if cat_kind == common.KIND_META:
            continue
        if not common.mode_admits_region(region_cls, cfg):
            continue
        if cat_kind == common.KIND_STACKED and sections:
            brect = scanpos.expand_to_section(brect, sections)
            quad = None                     # box grew; the refit quad is stale
        elif (region_cls == "feature_control_frame"
              and cfg.get("vision_section_group", True)):
            brect = scanpos.grow_box_stack(brect, words)
            quad = None
        blocks.append((bi, b, brect, region_cls, cat, quad))
    owned = _assign_words(words, [blk[2] for blk in blocks],
                          [blk[5] for blk in blocks])
    all_hits = []
    for k, (bi, b, brect, region_cls, cat, quad) in enumerate(blocks):
        cat_kind = cat[0] if cat else None
        constraint = cat[2] if cat else None
        in_block = [words[i] for i in owned[k]]
        has_text = [w for w in in_block if str(w[4]).strip()]
        reader = "text"
        if len(has_text) >= 2 and not force_vlm:
            block_words = in_block
        elif vlm_fallback is not None and img is not None:
            if on_slow:
                on_slow()
                on_slow = None
            try:
                block_words = _vlm_read_block(img, s, brect, vlm_fallback,
                                              _VBLOCK + 7000 + bi * 100)
                reader = "vlm"
            except Exception as e:                       # GPU OOM: latch off
                _vlm_died(e)
                block_words, reader = in_block, "text"
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
        # inject glyphs any reader
        inject = bool(sym_dets)
        if reader == "vlm" and not cfg.get("vision_sym_inject_vlm", True):
            inject = False
        if reader == "text" and not cfg.get("vision_sym_inject_text", True):
            inject = False
        if inject:
            block_words = list(block_words)
            block_syms = [(env, tok) for env, tok in sym_dets
                          if _center_in((env[0], env[1], env[2], env[3]),
                                        brect, quad)]
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
        if region_cls == "edge_condition":
            hits = _edge_hits(brect, block_words)
        if hits is None and (region_cls == "feature_control_frame"
                and cfg.get("vision_fcf_structural", True)):
            try:
                fcf = _fcf_structural_hits(page, cfg, brect, block_words, bi)
            except Exception:                            # pragma: no cover
                fcf = []
            keep = [h for h in fcf                       # probe ROW glyph
                    if cat is None
                    or common.admits(
                        constraint,
                        _fcf_glyph_for(h.get("fcf_char") or h.get("sb")))]
            if keep:
                for h in keep:
                    h["_ev_struct"] = True     # text layer lacks it
                hits = keep
                if len(keep) < len(fcf) or any(h.get("fcf_partial")
                                               or h.get("fcf_zone_suspect")
                                               for h in keep):
                    # partly-read: add legacy path
                    hits = keep + scanpos.scan_words(
                        block_words, include_bare=include_bare, cfg=cfg)
        if hits is None:
            hits = scanpos.scan_words(block_words, include_bare=include_bare,
                                      cfg=cfg)
        if cat_kind == common.KIND_CONTAINER and rect is not None:
            hits = [h for h in hits
                    if h.get("rect") is None or _rects_overlap(h["rect"], rect)]
        # opt-in VLM crosscheck stamps xcheck
        if (vlm is not None and img is not None
                and cfg.get("vision_vlm_crosscheck")
                and reader in ("text", "ocr")
                and _crosscheck_block(region_cls, hits)):
            if on_slow:
                on_slow()
                on_slow = None
            _apply_vlm_crosscheck(img, s, brect, bi, hits, vlm,
                                  include_bare, cfg)
        is_table = len(b) > 5 and int(b[5]) == table_cls
        conf = float(b[4]) if len(b) > 4 else 0.0
        for h in hits:
            h["cg"] = bi * 1000 + (h["cg"] if is_table else 0)
            h["_ev"] = _region_evidence(h, region_cls, conf, reader,
                                        h.pop("_ev_struct", False))
        all_hits.extend(hits)
    return scanpos.dedup_hits(all_hits, score=_evidence) or None


def _edge_hits(brect, block_words):
    """`edge_condition` box -> one EDGE hit or None."""
    from .scanlib import edge_from_values
    got = edge_from_values([str(w[4]) for w in block_words or ()])
    if got is None:
        return None
    v, t = got
    return [{"tp": "EDGE", "sb": None, "v": v, "t": t, "raw": v,
             "rect": tuple(brect), "cg": 0}]


def extract_hits(page, cfg, rect=None, include_bare=False, words=None,
                 allow_vlm=False, on_slow=None):
    """Structured hits for page or rect. None -> legacy path."""
    if not cfg.get("vision_assist") or not cfg.get("vision_region", True):
        return None
    try:
        hits = _region_regex_hits(page, cfg, rect, include_bare, words,
                                  allow_vlm, on_slow)
    except Exception as e:
        _warn("region path failed (%s); falling back to legacy" % e)
        return None
    if hits is None or not cfg.get("vision_region_union", True):
        return _strip_ev(hits)
    try:
        from bubbler import scanpos
        if words is None:
            words = scanpos.page_words(page)
        bare = include_bare and bool(cfg.get("vision_union_bare", True))
        legacy = scanpos.scan_words(words, include_bare=bare, cfg=cfg)
    except Exception as e:                              # pragma: no cover
        _warn("text union failed (%s); using region hits only" % e)
        return _strip_ev(hits)
    if rect is not None:
        legacy = [h for h in legacy
                  if h.get("rect") is None or _rects_overlap(h["rect"], rect)]
    for h in legacy:
        # text-only callouts, own groups
        h["cg"] = _VBLOCK + int(h.get("cg") or 0)
    merged = scanpos.dedup_hits(list(hits) + legacy, score=_evidence)
    return _strip_ev(merged) or None


def read_rect_words(page, cfg, rect, use_vlm=False):
    """Read box"""
    pm = _pixmap(page, cfg)
    if not pm:
        return None
    img, s = pm
    words = None
    if use_vlm and cfg.get("vision_vlm"):
        eng = _vlm_engine(cfg)
        if eng is not None:
            try:
                words = _vlm_read_block(img, s, rect, eng, _VBLOCK + 9000)
            except Exception as e:
                _note("vlm", "vlm read failed (%s); using OCR" % e)
                words = None
                _vlm_died(e)          # GPU OOM: stop retrying it every drag
    if not words:
        kind, eng = _ocr_engine_for(cfg)
        if eng is None:
            return None
        conf_min = float(cfg.get("vision_ocr_conf", 0.5))
        words = _ocr_block(img, s, rect, kind, eng, conf_min, _VBLOCK + 9000)
    words = list(words)
    if cfg.get("vision_symbols", True):
        try:
            sym_dets = _symbol_dets(page, cfg)
        except Exception:
            sym_dets = []
        have = _block_glyphs(words)
        for env, tok in sym_dets:
            if not _center_in((env[0], env[1], env[2], env[3]), rect):
                continue
            if _glyph_present(tok, have):
                continue
            _attach_or_append(words, env, tok)
    return words


def meta_region_at(page, cfg, rect):
    """META region class under click or None."""
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
