# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Capability probe rows for status panel

import os

from .i18n import tr

# row states
OK = "ok"        # working
OFF = "off"      # off in settings
NA = "na"        # backend missing
WARN = "warn"    # out of contract

_CACHE = None


def state_label(state):
    """Short word for row state"""
    return {OK: tr('Working'),
            OFF: tr('Turned off'),
            NA: tr('Not available'),
            WARN: tr('Needs attention')}.get(state, state)


def _row(key, label, state, detail, fix=""):
    return {"key": key, "label": label, "state": state,
            "detail": detail, "fix": fix}


def cached():
    """Last probe result or None"""
    return _CACHE


def probe(cfg=None, refresh=True):
    """Every capability row, slow, never raises"""
    global _CACHE
    if not refresh and _CACHE is not None:
        return _CACHE
    cfg = dict(cfg or {})
    rows = []
    for fn in (_row_pdf, _row_device, _row_symbols, _row_regions, _row_fcf,
               _row_ocr, _row_florence, _row_paddle, _row_gpu_pack):
        try:
            r = fn(cfg)
        except Exception as e:                          # pragma: no cover
            r = _row(getattr(fn, "__name__", "?"), tr('Check failed'), NA,
                     tr('This check itself failed: %s') % e,
                     tr('Send ~/.bubbler.log with your report.'))
        if r:
            rows.append(r)
    _CACHE = rows
    return rows


# ---------------------------------------------------------------- helpers

def _ep_name(ep):
    """Plain name for provider"""
    names = {
        "CPUExecutionProvider": tr('CPU'),
        "CUDAExecutionProvider": tr('NVIDIA GPU (CUDA)'),
        "TensorrtExecutionProvider": tr('NVIDIA GPU (TensorRT)'),
        "DmlExecutionProvider": tr('GPU (DirectML)'),
        "CoreMLExecutionProvider": tr('Apple GPU (CoreML)'),
        "ROCMExecutionProvider": tr('AMD GPU (ROCm)'),
    }
    return names.get(ep, ep or tr('unknown'))


def _chosen_ep(sess):
    """Provider onnxruntime used, off session"""
    try:
        prov = list(sess.get_providers() or [])
    except Exception:
        return None
    return prov[0] if prov else None


def _ort():
    try:
        import onnxruntime as ort
        return ort
    except Exception:
        return None


def _offered():
    """Providers onnxruntime build offers"""
    ort = _ort()
    if ort is None:
        return []
    try:
        return list(ort.get_available_providers())
    except Exception:                                   # pragma: no cover
        return []


def _reason(key):
    from . import vision
    return str(vision._REASONS.get(key) or "")


def _short(path):
    """models/<file>"""
    if not path:
        return ""
    return os.path.join(os.path.basename(os.path.dirname(path)),
                        os.path.basename(path))


def _det_row(key, label, cfg, path, sess, nc, want, classes_hint, fix_missing):
    """One detector row with contract check and provider"""
    if sess is None:
        why = _reason(key) or tr('the model file was not found')
        # stale bundled model
        fix = fix_missing
        if "class mismatch" in why:
            fix = tr('Bundled model is older than this version\'s class list '
                     'and needs retraining. Text parsing still works; '
                     'update Bubbler when a rebuilt model ships.')
        return _row(key, label, NA,
                    tr('This pass is skipped. Reason: %s') % why, fix)
    ep = _ep_name(_chosen_ep(sess))
    from . import vision
    imgsz = vision._sess_imgsz(sess, cfg.get("vision_imgsz", 640))
    where = tr('Loaded %s, running on %s.') % (_short(path), ep)
    if nc is not None and nc != want:
        return _row(key, label, WARN,
                    where + " " + tr('This model has %(got)d classes but '
                                     'this Bubbler expects %(want)d, so '
                                     'anything it finds is labelled wrong.')
                    % {"got": nc, "want": want},
                    tr('Clear the custom model box in Settings > Vision to '
                       'use the model that shipped with Bubbler.'))
    known = (tr('%d classes, as expected') % want if nc is not None
             else tr('class count could not be read'))
    return _row(key, label, OK,
                where + " " + tr('%(classes)s, %(px)d px input. %(hint)s')
                % {"classes": known, "px": imgsz, "hint": classes_hint})


# ------------------------------------------------------------------ rows

def _row_pdf(cfg):
    from . import vision
    if vision._fitz() is None:
        return _row("pdf", tr('Drawing page rendering'), NA,
                    tr('PyMuPDF is missing, so no page image can be made and '
                       'every vision pass is skipped.'),
                    tr('Reinstall Bubbler; the packaged build includes it.'))
    return _row("pdf", tr('Drawing page rendering'), OK,
                tr('Pages render at %d DPI for the detectors.')
                % int(cfg.get("vision_dpi", 200)))


def _row_device(cfg):
    """GPU or CPU and provider chosen"""
    label = tr('Compute device')
    ort = _ort()
    if ort is None:
        return _row("device", label, NA,
                    tr('onnxruntime is missing, so no detector and no '
                       'built-in OCR can run.'),
                    tr('Reinstall Bubbler; the packaged build includes it.'))
    from . import vision
    sess = None
    for get in (vision._symbol_session, vision._region_session,
                vision._fcf_cls_session):
        try:
            sess = sess or get(cfg)
        except Exception:                               # pragma: no cover
            pass
    ver = getattr(ort, "__version__", "?")
    offered = _offered()
    gpu_offered = [p for p in offered if not p.startswith("CPU")]
    if sess is None:
        return _row("device", label, NA,
                    tr('onnxruntime %(ver)s is here but no model is loaded, '
                       'so nothing runs yet.') % {"ver": ver},
                    tr('See the model rows below.'))
    chosen = _chosen_ep(sess)
    if chosen and not chosen.startswith("CPU"):
        return _row("device", label, OK,
                    tr('Running on %(dev)s (onnxruntime %(ver)s).')
                    % {"dev": _ep_name(chosen), "ver": ver})
    why = _reason("ep")
    if why:
        detail = tr('Running on the CPU (onnxruntime %(ver)s). %(why)s')
        detail = detail % {"ver": ver, "why": why}
    elif gpu_offered:
        detail = tr('Running on the CPU (onnxruntime %(ver)s). No usable '
                    'graphics card was found, so Bubbler uses the CPU. This '
                    'is a supported setup: everything works, scanning is '
                    'just slower.') % {
                        "ver": ver}
    else:
        detail = tr('Running on the CPU (onnxruntime %(ver)s). This build has '
                    'no graphics-card support. This is a supported setup: '
                    'everything works, scanning is just slower.') % {
                        "ver": ver}
    fix = ""
    if gpu_offered:
        fix = tr('Nothing to do unless you want more speed. With an NVIDIA '
                 'card, install the GPU pack lower down this tab.')
    return _row("device", label, OK, detail, fix)


def _row_symbols(cfg):
    from . import vision
    label = tr('GD&T symbol detector')
    if not cfg.get("vision_assist", True) or not cfg.get("vision_symbols",
                                                         True):
        return _row("symbols", label, OFF,
                    tr('Switched off, so GD&T glyphs are read from the text '
                       'layer only.'),
                    tr('Settings > Vision: tick Detect GD&T symbols.'))
    sess = vision._symbol_session(cfg)
    want = len(vision._SYM_CLASSES)
    return _det_row("symbols", label, cfg, vision._model_path(cfg), sess,
                    vision._out_nc(sess, want) if sess else None, want,
                    tr('Finds the symbols the text layer leaves out.'),
                    tr('Settings > Vision: clear Custom model, or reinstall '
                       'Bubbler to restore the bundled detector.'))


def _row_regions(cfg):
    from . import vision
    label = tr('Callout block detector')
    if not cfg.get("vision_assist", True) or not cfg.get("vision_region",
                                                         True):
        return _row("region", label, OFF,
                    tr('Switched off, so callouts are grouped by geometry '
                       'alone.'),
                    tr('Settings > Vision: tick Detect callout blocks.'))
    sess = vision._region_session(cfg)
    want = len(vision._REGION_CLASSES)
    return _det_row("region", label, cfg, vision._region_model_path(cfg), sess,
                    vision._out_nc(sess, want) if sess else None, want,
                    tr('Groups a callout and its tolerances into one block.'),
                    tr('Settings > Vision: clear the region model box, or '
                       'reinstall Bubbler.'))


def _fcf_nc(sess):
    """Classifier class count off head"""
    try:
        shape = sess.get_outputs()[0].shape
    except Exception:                                   # pragma: no cover
        return None
    return shape[1] if len(shape) == 2 and isinstance(shape[1], int) else None


def _row_fcf(cfg):
    from . import vision
    label = tr('Control-frame symbol reader')
    if not cfg.get("vision_assist", True) or not cfg.get("vision_fcf_classify",
                                                         True):
        return _row("fcf", label, OFF,
                    tr('Switched off, so a control frame keeps whatever '
                       'symbol the text layer gives.'),
                    tr('Settings > Vision: tick Read the frame symbol.'))
    sess = vision._fcf_cls_session(cfg)
    want = len(vision._FCF_CLASSES)
    return _det_row("fcf", label, cfg, vision._fcf_cls_path(cfg), sess,
                    _fcf_nc(sess) if sess else None, want,
                    tr('Reads the characteristic symbol from the frame '
                       'picture when the text layer has none.'),
                    tr('Settings > Vision: clear the frame model box, or '
                       'reinstall Bubbler.'))


def _row_ocr(cfg):
    from . import vision
    label = tr('Text reader: built-in OCR')
    if not cfg.get("vision_assist", True) or not cfg.get("vision_ocr", True):
        return _row("ocr", label, OFF,
                    tr('Switched off, so a scanned drawing with no text layer '
                       'reads as empty.'),
                    tr('Settings > Vision: tick Read text from the picture.'))
    if vision._ocr_engine() is None:
        return _row("ocr", label, NA,
                    tr('This pass is skipped. Reason: %s')
                    % (_reason("ocr") or tr('the OCR engine did not load')),
                    tr('Reinstall Bubbler; the packaged build includes the '
                       'OCR engine.'))
    always = cfg.get("vision_ocr_always")
    when = (tr('on every page') if always
            else tr('only where the drawing has no text of its own'))
    return _row("ocr", label, OK,
                tr('Ready (RapidOCR), used %(when)s, keeping reads above '
                   '%(conf).2f confidence.')
                % {"when": when, "conf": float(cfg.get("vision_ocr_conf",
                                                       0.5) or 0.5)})


def _row_florence(cfg):
    from . import florence
    label = tr('Text reader: Florence-2')
    try:
        ready = florence.can_load(cfg)
    except Exception:                                   # pragma: no cover
        ready = False
    if not ready:
        if florence.model_dir(cfg) is None:
            why = tr('no Florence-2 model pack is installed')
            fix = tr('Settings > Vision: Download VLM model.')
        else:
            why = tr('the model pack is incomplete or a support library is '
                     'missing')
            fix = tr('Settings > Vision: download the pack again.')
        return _row("florence", label, NA,
                    tr('Not used. Reason: %s') % why, fix)
    on = cfg.get("vision_vlm") and str(
        cfg.get("vision_vlm_engine", "florence")).lower() == "florence"
    if not on:
        return _row("florence", label, OFF,
                    tr('Installed and ready, but not switched on.'),
                    tr('Settings > Vision: tick Use a VLM reader and pick '
                       'florence.'))
    where = _short(florence.model_dir(cfg))
    return _row("florence", label, OK, tr('Ready, reading from %s.') % where)


def _row_paddle(cfg):
    from . import paddlevl
    label = tr('Text reader: PaddleOCR-VL')
    try:
        ready = paddlevl.can_load(cfg)
    except Exception:                                   # pragma: no cover
        ready = False
    if not ready:
        return _row("paddle", label, NA,
                    tr('Not used. Reason: %s')
                    % tr('the optional PaddleOCR packages are not installed'),
                    tr('Optional. Florence-2 does the same job and is a '
                       'download away in Settings > Vision.'))
    on = cfg.get("vision_vlm") and str(
        cfg.get("vision_vlm_engine", "florence")).lower() == "paddle"
    if not on:
        return _row("paddle", label, OFF,
                    tr('Installed and ready, but not switched on.'),
                    tr('Settings > Vision: tick Use a VLM reader and pick '
                       'paddle.'))
    return _row("paddle", label, OK, tr('Ready.'))


def _row_gpu_pack(cfg):
    from . import gpu
    label = tr('GPU pack (Linux)')
    if not gpu.is_linux():
        return None
    if not cfg.get("vision_gpu", True):
        return _row("gpupack", label, OFF,
                    tr('Switched off, so the detectors stay on the CPU.'),
                    tr('Settings > Vision: tick Use the GPU pack.'))
    if not gpu.is_installed():
        return _row("gpupack", label, NA,
                    tr('Not installed, so the detectors run on the CPU. '
                       'That is a supported setup.'),
                    tr('Optional. With an NVIDIA card and driver 580 or '
                       'newer, use the GPU pack button in '
                       'Settings > Vision.'))
    st = gpu.status()
    if "ready" not in st:
        return _row("gpupack", label, WARN,
                    tr('Installed but not answering (%s), so the detectors '
                       'run on the CPU.') % st,
                    tr('Settings > Vision: install the GPU pack again, then '
                       'restart Bubbler.'))
    return _row("gpupack", label, OK, tr('Installed and answering: %s') % st)
