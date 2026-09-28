# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Rects, containment, reading frames.


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]),
            max(a[2], b[2]), max(a[3], b[3]))


def _union_all(rects):
    r = rects[0]
    for x in rects[1:]:
        r = _union(r, x)
    return r


def words_in_rect(words, rx0, ry0, rx1, ry1):
    """One test for capture, scan worker, eval."""
    out = []
    for w in words:
        wx0, wy0, wx1, wy1 = w[0], w[1], w[2], w[3]
        ix = min(rx1, wx1) - max(rx0, wx0)
        iy = min(ry1, wy1) - max(ry0, wy0)
        if ix <= 0 or iy <= 0:
            continue
        area = max((wx1 - wx0) * (wy1 - wy0), 1e-6)
        cx, cy = (wx0 + wx1) / 2.0, (wy0 + wy1) / 2.0
        if (ix * iy) / area >= 0.30 or (rx0 <= cx <= rx1 and ry0 <= cy <= ry1):
            out.append(w)
    return out


def xform_pt(m, x, y):
    return (x * m.a + y * m.c + m.e, x * m.b + y * m.d + m.f)


def xform_rect(m, x0, y0, x1, y1):
    ax, ay = xform_pt(m, x0, y0)
    bx, by = xform_pt(m, x1, y1)
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


def _iou(a, b):
    ow = min(a[2], b[2]) - max(a[0], b[0])
    oh = min(a[3], b[3]) - max(a[1], b[1])
    if ow <= 0 or oh <= 0:
        return 0.0
    inter = ow * oh
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _rect_holds(r, x, y):
    return r is not None and r[0] <= x <= r[2] and r[1] <= y <= r[3]


def _rect_covers(outer, inner):
    """Transitive, unlike centre-in-rect."""
    return (outer is not None and inner is not None
            and outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def _rect_mostly_in(a, b, frac=0.7):
    if a is None or b is None:
        return False
    ow = min(a[2], b[2]) - max(a[0], b[0])
    oh = min(a[3], b[3]) - max(a[1], b[1])
    if ow <= 0 or oh <= 0:
        return False
    small = min((a[2] - a[0]) * (a[3] - a[1]),
                (b[2] - b[0]) * (b[3] - b[1]))
    return small > 0 and (ow * oh) / small >= frac


_UP = (0.0, -1.0)      # reads bottom-to-top


def _touching(a, b):
    pad = 0.5 * min(a[2] - a[0], a[3] - a[1])
    return (b[0] - pad <= a[2] and a[0] - pad <= b[2]
            and b[1] - pad <= a[3] and a[1] - pad <= b[3])


def _shape_dir(w):
    # tight pair box looks tall
    if len(str(w[4]).strip()) < 3:
        return None
    wd, ht = w[2] - w[0], w[3] - w[1]
    if ht > 1.5 * wd:
        return _UP
    if wd > 1.5 * ht:
        return (1.0, 0.0)
    return None


def fill_dirs(words):
    """Line order, then touching word, then shape."""
    words = [tuple(w) for w in words]
    has = [w[8] if len(w) > 8 and w[8] else None for w in words]
    lines = {}
    for i, w in enumerate(words):
        if not has[i] and len(w) >= 8:
            lines.setdefault((w[5], w[6]), []).append(i)
    for idx in lines.values():
        if len(idx) < 2:
            continue
        idx.sort(key=lambda i: words[i][7])
        a, b = words[idx[0]], words[idx[-1]]
        dx = (b[0] + b[2] - a[0] - a[2]) / 2.0
        dy = (b[1] + b[3] - a[1] - a[3]) / 2.0
        if abs(dx) + abs(dy) > 0:
            d = ((1.0 if dx > 0 else -1.0), 0.0) if abs(dx) >= abs(dy) \
                else (0.0, (1.0 if dy > 0 else -1.0))
            for i in idx:
                has[i] = d
    known = [(w, d) for w, d in zip(words, has) if d]
    for i, w in enumerate(words):
        if has[i]:
            continue
        shape = _shape_dir(w)
        for k, kd in known:
            if _touching(w, k) and (shape is None
                                    or (abs(kd[0]) > 0.5) == (abs(shape[0]) > 0.5)):
                has[i] = kd
                break
        else:
            has[i] = shape
    for i, w in enumerate(words):
        if has[i] is None and len(str(w[4]).strip()) < 3:
            for j, v in enumerate(words):
                if j != i and has[j] and _touching(w, v):
                    has[i] = has[j]
                    break
    return [tuple(w[:8]) + ((d,) if d else ()) for w, d in zip(words, has)]


def _dir_quarter(w):
    """0/1/2/3 = the word reads at 0/90/180/270 degrees (display y down)."""
    d = w[8] if len(w) > 8 else None
    if not d:
        return 0
    import math
    a = math.degrees(math.atan2(d[1], d[0])) % 360.0
    return int(((a + 45.0) % 360.0) // 90.0)


_QUARTER = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}


def _to_frame(q, x, y):
    c, s = _QUARTER[q]
    return (x * c + y * s, -x * s + y * c)


def _from_frame(q, x, y):
    c, s = _QUARTER[q]
    return (x * c - y * s, x * s + y * c)


def _rect_map(fn, q, r):
    ax, ay = fn(q, r[0], r[1])
    bx, by = fn(q, r[2], r[3])
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


_DIAG_MIN = 8.0         # deg off quarter


def _diag_angle(w):
    """Snapping leader text to quarter splits callouts."""
    d = w[8] if len(w) > 8 else None
    if not d or len(d) < 3 or not d[2]:
        return None
    import math
    a = math.degrees(math.atan2(d[1], d[0])) % 360.0
    off = a % 90.0
    if min(off, 90.0 - off) <= _DIAG_MIN:
        return None
    return int(round(a)) % 360


def _diag_box(w, deg):
    import math
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
    fx, fy = cx * c + cy * s, -cx * s + cy * c
    h = float(w[8][2])
    ac, as_ = abs(c), abs(s)
    if ac >= as_:
        ln = ((w[2] - w[0]) - h * as_) / max(ac, 1e-6)
    else:
        ln = ((w[3] - w[1]) - h * ac) / max(as_, 1e-6)
    ln = max(ln, 0.3 * h)
    return (fx - ln / 2.0, fy - h / 2.0, fx + ln / 2.0, fy + h / 2.0)


def _diag_back(r, deg):
    import math
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    pts = [(x * c - y * s, x * s + y * c)
           for x in (r[0], r[2]) for y in (r[1], r[3])]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def _point_in_quad(px, py, quad):
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


def _overlap_frac(word, rect, quad=None):
    if quad is not None:                 # centre decides
        return 1.0 if _center_in(word, rect, quad) else 0.0
    area = (word[2] - word[0]) * (word[3] - word[1])
    if area <= 0:
        return 1.0 if _center_in(word, rect) else 0.0
    ix = min(word[2], rect[2]) - max(word[0], rect[0])
    iy = min(word[3], rect[3]) - max(word[1], rect[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    return min(1.0, (ix * iy) / area)


# below half recovers clipped
_WORD_MIN_FRAC = 0.25


_WORD_FULL_FRAC = 0.9


def _rects_overlap(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])
