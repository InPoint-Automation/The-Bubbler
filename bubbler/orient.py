# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Refit a diagonal callout box to its text angle
import math

SQUARE_TOL_DEG = 1.0        # right-angle text: box already exact
PAD = 1.0                   # pt, keep a refit off its glyphs


def line_angle(direction):
    """Text baseline vector to degrees"""
    dx, dy = (direction or (1.0, 0.0))[:2]
    return math.degrees(math.atan2(dy, dx)) % 360.0


def is_square(deg, tol=SQUARE_TOL_DEG):
    """Text along a page axis: bbox is the box"""
    return any(abs((deg % 360.0) - k) <= tol for k in (0.0, 90.0, 180.0,
                                                       270.0, 360.0))


def page_lines(page):
    """[(bbox, degrees, text)] per content text line"""
    try:
        d = page.get_text("dict")
    except Exception:
        return []
    out = []
    for b in d.get("blocks", ()) or ():
        for ln in b.get("lines", ()) or ():
            t = "".join(sp.get("text", "")
                        for sp in (ln.get("spans") or ())).strip()
            if t:
                out.append((tuple(ln["bbox"]), line_angle(ln.get("dir")), t))
    return out


def _rot(pt, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (pt[0] * c - pt[1] * s, pt[0] * s + pt[1] * c)


def true_size(bbox, deg):
    """A diagonal line's own w, h from its axis-aligned bbox"""
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    c = abs(math.cos(math.radians(deg)))
    s = abs(math.sin(math.radians(deg)))
    det = c * c - s * s
    if abs(det) < 1e-3:
        return None
    w = (bw * c - bh * s) / det
    h = (bh * c - bw * s) / det
    if w <= 0.5 or h <= 0.5:
        return None
    return w, h


def line_corners(bbox, deg):
    """Four corners of a line's true oriented box"""
    wh = true_size(bbox, deg)
    if wh is None:
        return None
    w, h = wh
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    out = []
    for dx, dy in ((-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)):
        x, y = _rot((dx, dy), deg)
        out.append((cx + x, cy + y))
    return out


def fit_quad(lines, deg, pad=PAD):
    """Tightest quad round these lines, along deg"""
    pts = []
    for bb, d in lines:
        cor = line_corners(bb, d)
        if cor is None:
            return None                    # 45 deg: keep the bbox
        pts += cor
    if not pts:
        return None
    rot = [_rot(p, -deg) for p in pts]
    x0 = min(p[0] for p in rot) - pad
    x1 = max(p[0] for p in rot) + pad
    y0 = min(p[1] for p in rot) - pad
    y1 = max(p[1] for p in rot) + pad
    return [list(_rot(p, deg)) for p in ((x0, y0), (x1, y0),
                                         (x1, y1), (x0, y1))]


def _centre_in(rect, box):
    cx, cy = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


def region_angle(rect, lines):
    """The one diagonal angle every line in the box shares, else None"""
    mine = [(bb, deg) for bb, deg, _t in lines if _centre_in(bb, rect)]
    if not mine:
        return None
    degs = [deg for _bb, deg in mine]
    if any(is_square(d) for d in degs):
        return None
    lo, hi = min(degs), max(degs)
    if (hi - lo) > 2.0 * SQUARE_TOL_DEG:
        return None                        # mixed angles: not one callout
    return sum(degs) / len(degs)


def _quad_area(q):
    s = 0.0
    for i in range(len(q)):
        x1, y1 = q[i]
        x2, y2 = q[(i + 1) % len(q)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def refit(rect, lines, pad=PAD):
    """Diagonal callout to a tight quad, else None (square, or no shrink)"""
    deg = region_angle(rect, lines)
    if deg is None:
        return None
    mine = [(bb, d) for bb, d, _t in lines if _centre_in(bb, rect)]
    q = fit_quad(mine, deg, pad)
    if q is None:
        return None
    if _quad_area(q) >= (rect[2] - rect[0]) * (rect[3] - rect[1]):
        return None
    return q
