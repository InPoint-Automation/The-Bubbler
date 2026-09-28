# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Region boxes, quads, sections, furniture.

from bubbler import common as _common
from bubbler.reader import geometry  # noqa: E402
from bubbler.reader.vision import detect, runtime  # noqa: E402


_FURNITURE_CI = None


def _furniture_indexes():
    global _FURNITURE_CI
    if _FURNITURE_CI is None:
        _FURNITURE_CI = frozenset(
            runtime._REGION_CLASSES.index(c) for c in _common.DETECTED_FURNITURE)
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


def _region_boxes(page, cfg):
    key = runtime._cache_key(page, cfg, "rgn")
    hit = runtime._cache_get(key)
    if hit is not None:
        return hit
    conf = float(cfg.get("vision_region_conf", runtime.conf_default("vision_region_conf")))
    out = []
    for x0, y0, x1, y1, c, ci in detect._detect_page(
            runtime._region_session(cfg), page, cfg, len(runtime._REGION_CLASSES),
            conf, tile=bool(cfg.get("vision_region_tile", False))):
        if 0 <= ci < len(runtime._REGION_CLASSES):
            out.append((x0, y0, x1, y1, c, ci))
    out = _drop_furniture_contents(out)
    out = _orient_refit(out, page, cfg)
    runtime._cache_put(key, out)
    return out


def _orient_refit(boxes, page, cfg):
    """Refit diagonal callout box to quad, 7th field"""
    if not cfg.get("vision_orient_refit", True):
        return [tuple(b) + (None,) for b in boxes]
    from bubbler import orient
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
    import math
    try:
        from bubbler import orient
        from bubbler.reader import geometry
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
        from bubbler.reader import geometry
        m = page.rotation_matrix
        a, b, c, d = m.a, m.b, m.c, m.d
    except Exception:
        return []
    out = []
    for bb, deg, t in lines:
        rb = geometry.xform_rect(m, bb[0], bb[1], bb[2], bb[3])
        dx, dy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        ang = math.degrees(math.atan2(b * dx + d * dy,
                                      a * dx + c * dy)) % 360.0
        out.append((rb, ang, t))
    return out


def _page_sections(page, cfg):
    key = runtime._cache_key(page, cfg, "sec")
    hit = runtime._cache_get(key)
    if hit is not None:
        return hit
    from bubbler.reader import layout
    try:
        out = layout.page_sections(page, cfg)
    except Exception:
        out = []
    runtime._cache_put(key, out)
    return out


def orphan_symbols(region_boxes, symbol_dets):
    return [(box, tok) for box, tok in symbol_dets
            if not any(geometry._center_in(box, r) for r in region_boxes)]
