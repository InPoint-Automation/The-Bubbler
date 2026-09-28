# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# VLM readers and cross-check.

import re
from bubbler.reader import dedup, geometry  # noqa: E402
from bubbler.reader.vision import runtime  # noqa: E402


_VLM = None
_VLM_TRIED = False
# GPU failure latches VLM off
_VLM_DEAD = False


def _is_resource_error(e):
    """A CUDA/GPU out-of-resource failure, not a plain read miss."""
    s = str(e).lower()
    return any(w in s for w in ("cublas", "cuda", "out of memory", "cudnn",
                                "resource", "cudaerror", "gpu"))


def _vlm_died(e):
    global _VLM_DEAD
    if _VLM_DEAD or not _is_resource_error(e):
        return _VLM_DEAD
    _VLM_DEAD = True
    runtime._warn("VLM disabled for this session after a GPU/resource failure (%s)" % e)
    return True


def _vlm_module(cfg):
    if str((cfg or {}).get("vision_vlm_engine", "florence")).lower() \
            == "paddleocr_vl":
        from bubbler import paddlevl
        return paddlevl, paddlevl.PaddleOCRVL
    from bubbler import florence
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
        _VLM = cls.load(runtime._providers(cfg), mod.model_dir(cfg))
        if _VLM is not None:
            runtime._warn("VLM reader loaded: %s"
                  % str(cfg.get("vision_vlm_engine", "florence")))
            _VLM.warmup()
    except Exception as e:
        runtime._warn("VLM reader unavailable (%s)" % e)
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


def _vlm_wanted(cfg, allow_vlm):
    """Which VLM uses are on: (load_engine, is_fallback_reader)."""
    fallback = bool(allow_vlm and cfg.get("vision_vlm"))
    xcheck = bool(allow_vlm and cfg.get("vision_vlm_crosscheck"))
    return (fallback or xcheck, fallback)


def _hits_coincide(a, b, tol=12.0):
    """Two reads of roughly same place. No rect, block match."""
    ra, rb = a.get("rect"), b.get("rect")
    if not ra or not rb:
        return True
    return geometry._rects_overlap(ra, rb)


def _crosscheck_block(region_cls, hits):
    if region_cls == "feature_control_frame":
        return True
    return any((h.get("t") or "").strip() for h in hits)


def _crosscheck_stamp(hits, vhits):
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
    from bubbler.reader import parse
    try:
        vwords = _vlm_read_block(img, s, brect, vlm, dedup._VBLOCK + 9000 + bi * 100)
        vhits = parse.scan_words(vwords, include_bare=include_bare, cfg=cfg)
    except Exception as e:
        _vlm_died(e)                                     # GPU OOM: latch off
        return
    _crosscheck_stamp(hits, vhits)


_HOLE_KW = re.compile(r"\b(?:THRU|DEEP|CBORE|CSINK)\b")
