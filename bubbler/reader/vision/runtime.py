# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# ONNX providers, GPU, model paths, sessions, caches.

import threading
from bubbler import common as _common
from bubbler import config as _config
from bubbler.reader.vision import detect, ocr_read, render, vlm_read  # noqa: E402


_SESS_LOCK = threading.Lock()  # prewarm races scan pool

# dynamic-size model fallback
IMGSZ_DEFAULT = _config.CFG_DEFAULT["vision_imgsz"]


def available(cfg=None):
    geom = render._fitz() is not None
    vlm = False
    try:
        from bubbler import florence, paddlevl
        vlm = geom and (florence.can_load(cfg or {})
                        or paddlevl.can_load(cfg or {}))
    except Exception:
        vlm = False
    return {"geometry": geom,
            "ocr": geom and ocr_read._ocr_engine(cfg) is not None,
            "symbols": geom and _symbol_session(cfg or {}) is not None,
            "region": geom and _region_session(cfg or {}) is not None,
            "vlm": vlm,
            "gpu": _gpu_in_use(cfg or {}),
            "providers": _ort_providers(),
            "reasons": dict(_REASONS)}


TELEMETRY_HOST = b"events.data.microsoft.com"


def telemetry_builds(ort_dir=None):
    import mmap
    import os
    if ort_dir is None:
        try:
            import importlib.util
            spec = importlib.util.find_spec("onnxruntime")
        except Exception:
            spec = None
        if not spec or not spec.origin:
            return []
        ort_dir = os.path.dirname(spec.origin)
    bad = []
    for root, _dirs, files in os.walk(ort_dir):
        for name in files:
            low = name.lower()
            # core lib, EP libs huge
            if "providers_" in low or not (
                    ".so" in low or low.endswith((".dll", ".dylib", ".pyd"))):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as fh, \
                        mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
                    if m.find(TELEMETRY_HOST) != -1:
                        bad.append(path)
            except (OSError, ValueError):
                continue
    return sorted(bad)


def _ort_providers():
    try:
        import onnxruntime as ort
        _REASONS.pop("onnxruntime", None)
        return list(ort.get_available_providers())
    except Exception as e:
        _REASONS["onnxruntime"] = "onnxruntime not importable (%s)" % e
        return []


_REASONS = {}


def _note(key, msg):
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
    def __init__(self, path, cfg):
        from bubbler import gpu
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
        from bubbler import gpu
        return gpu.is_linux() and gpu.is_installed()
    except Exception:
        return False


_CUDA_PRELOADED = False
_CUDA_PRELOADED_N = 0


def _preload_cuda_libs():
    """Preload pip CUDA libs so CUDA EP finds them."""
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


_GPU_FAIL_WORDS = ("out of memory", "failed to allocate", "alloc_failed",
                   "memoryallocation", "bfcarena", "cuda failure", "cudnn",
                   "cublas", "gpu worker run failed")


def _gpu_failure(e):
    """GPU fault not input, worth CPU re-run."""
    s = str(e).lower()
    return any(w in s for w in _GPU_FAIL_WORDS)


_GPU_FELL_BACK = []


def _gpu_fell_back(what, e):
    _note("ep", "the graphics card failed on %s (%s); it now runs on the "
          "CPU -- same reads, slower" % (what, str(e).strip()[:160]))
    _GPU_FELL_BACK.append(what)


def take_gpu_fallback():
    out = list(_GPU_FELL_BACK)
    del _GPU_FELL_BACK[:]
    return out


def _on_cpu(sess):
    try:
        prov = list(sess.get_providers() or [])
    except Exception:
        return False
    return bool(prov) and prov[0].startswith("CPU")


class _CpuFallback:
    def __init__(self, inner, path):
        self._inner = inner
        self._path = path
        self._lock = threading.Lock()

    def __getattr__(self, name):
        if name == "_inner":                # half-built: no recursion
            raise AttributeError(name)
        return getattr(self._inner, name)

    def run(self, output_names, feed, *a, **kw):
        inner = self._inner
        try:
            return inner.run(output_names, feed, *a, **kw)
        except Exception as e:
            if not _gpu_failure(e) or _on_cpu(inner):
                raise
            with self._lock:
                if self._inner is inner:     # one rebuild per model
                    import os
                    import onnxruntime as ort
                    self._inner = ort.InferenceSession(
                        self._path, providers=["CPUExecutionProvider"])
                    _gpu_fell_back(os.path.basename(self._path), e)
            return self._inner.run(output_names, feed, *a, **kw)


def _make_session(ort, path, cfg):
    """Open session. Route to GPU worker on linux when possible."""
    if _gpu_ready(cfg):
        try:
            return _CpuFallback(_RemoteSession(path, cfg), path)
        except Exception as e:
            _note("ep", "gpu worker unavailable (%s); running on CPU" % e)
    prefer = _providers(cfg)
    if any(p.startswith("CUDA") for p in prefer):
        _preload_cuda_libs()
    try:
        sess = ort.InferenceSession(path, providers=prefer)
    except Exception as e:
        if prefer == ["CPUExecutionProvider"]:
            raise
        _note("ep", "%s failed to init (%s); running vision on CPU"
              % (prefer[0], e))
        return ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    return sess if _on_cpu(sess) else _CpuFallback(sess, path)


def _gpu_in_use(cfg=None):
    """True when LOADED detector session runs on non-CPU provider."""
    cfg = cfg or {}
    for get in (_symbol_session, _region_session):
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
    global _SYM_SESS, _SYM_TRIED, _RGN_SESS, _RGN_TRIED
    global _EP_LOGGED
    _SYM_SESS = _RGN_SESS = ocr_read._OCR = ocr_read._PADDLE = vlm_read._VLM = None
    _SYM_TRIED = _RGN_TRIED = ocr_read._OCR_TRIED = ocr_read._PADDLE_TRIED = vlm_read._VLM_TRIED = False
    vlm_read._VLM_DEAD = False
    _EP_LOGGED = False
    _REASONS.clear()


_SYM_SESS = None
_SYM_TRIED = False

# (glyph, kit name), order contractual
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
    ("[", "basic_box"), ("(", "ref_parens"),
    ("EDGE ", "edge_symbol"),
)
_SYM_CLASSES = tuple(g for g, _n in _SYM)
_SYM_NAMES = tuple(n for _g, n in _SYM)

# BASIC/REF marks wrap number
_SYM_WRAP = {"[": "]", "(": ")"}


def _onnx_roots():
    import os, sys
    here = os.path.dirname(os.path.abspath(__file__))
    here = os.path.dirname(os.path.dirname(here))
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
    global _SYM_SESS, _SYM_TRIED, _EP_LOGGED
    if _SYM_TRIED:
        return _SYM_SESS
    with _SESS_LOCK:
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
                      "code expects %d (the kit's classes.txt); this model "
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
    with _CACHE_LOCK:
        _DET_CACHE.clear()


def _model_stat(path):
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
                detect._run_det(sess, blank, _sess_imgsz(sess,
                     cfg.get("vision_imgsz", IMGSZ_DEFAULT)), nc, 0.99, 0.45, np)
        except Exception:
            pass


# Detector head order. ONE definition in common.py
_REGION_CLASSES = _common.TRAINED_REGION_CLASSES

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


def conf_default(key):
    """App default, so partial cfg keeps it."""
    from bubbler.config import CFG_DEFAULT
    return CFG_DEFAULT[key]
