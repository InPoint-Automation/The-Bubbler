# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Text union: merge text-layer and region reads.

import re
from bubbler.reader import geometry, holes  # noqa: E402
from bubbler.reader.vision import runtime  # noqa: E402


def _clipped_count(h, words):
    """Count alone in box. Word reader never mints it."""
    r = h.get("rect")
    if h.get("tp") != "LINEAR" or h.get("t") or not r or \
            not re.fullmatch(r"\d{1,3}", str(h.get("v") or "")):
        return False
    line = {}
    for w in words or ():
        if len(w) > 7:
            line[(w[5], w[6], w[7])] = w
    for w in words or ():
        if len(w) <= 7 or str(w[4]) != h["v"]:
            continue
        cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
        if not (r[0] <= cx <= r[2] and r[1] <= cy <= r[3]):
            continue
        x = line.get((w[5], w[6], w[7] + 1))
        n = line.get((w[5], w[6], w[7] + 2))
        if x is not None and str(x[4]) in holes._COUNT_X and n is not None \
                and re.match(r"[\d\u00d8]", str(n[4])):
            return True
    return False


_DEC_COMMA = re.compile(r"(?<=\d),(?=\d)")


def _dec_key(s):
    """`3,50` = `3.50`."""
    return None if s is None else _DEC_COMMA.sub(".", str(s))


def _union_fragment(h, hits):
    from bubbler.reader import dedup

    def nums(x):
        return [_dec_key(n) for n in
                dedup._NUMBER.findall(str(x.get("v") or "") + " "
                                        + str(x.get("t") or ""))]

    def key(x):
        return (x.get("tp"), x.get("sb"), _dec_key(x.get("v")),
                _dec_key(x.get("t")))
    r = h.get("rect")
    mine = set(nums(h))
    if not r or not mine:
        return False
    cx, cy = (r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0
    for o in hits:
        q = o.get("rect")
        if not q or not (q[0] <= cx <= q[2] and q[1] <= cy <= q[3]):
            continue
        if key(o) != key(h) and mine <= set(nums(o)):
            return True
    return False


_BALLOON_CLASSES = ("revision_balloon", "item_balloon")


def _balloon_boxes(boxes):
    """Balloon numbers are marks, not callout text."""
    idx = {runtime._REGION_CLASSES.index(c) for c in _BALLOON_CLASSES
           if c in runtime._REGION_CLASSES}
    return [b for b in boxes if len(b) > 5 and int(b[5]) in idx]


def _center_in_any(r, boxes):
    cx, cy = (r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0
    return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)


_DUP_COVER = 0.25


def _owned_elsewhere(brect, words, owned, k):
    area = max((brect[2] - brect[0]) * (brect[3] - brect[1]), 1e-6)
    mine = set(owned[k])
    cover = 0.0
    for i, w in enumerate(words):
        if i in mine or not str(w[4]).strip():
            continue
        ix = max(0.0, min(w[2], brect[2]) - max(w[0], brect[0]))
        iy = max(0.0, min(w[3], brect[3]) - max(w[1], brect[1]))
        cover += ix * iy
    return cover >= _DUP_COVER * area
_PURE_NUM = re.compile(r"^[\d.,]+$")


def _extends(g, h):
    """Same control and tolerance, datums restored. One row."""
    if (g.get("tp"), g.get("sb"), g.get("t")) != (h.get("tp"), h.get("sb"),
                                                   h.get("t")):
        return False
    gv, hv = str(g.get("v") or ""), str(h.get("v") or "")
    if gv == hv or not gv.startswith(hv + " |"):
        return False
    gr, hr = g.get("rect"), h.get("rect")
    return bool(gr and hr and geometry._rects_overlap(gr, hr))


def _is_callout_box(b):
    from bubbler import common
    if len(b) <= 5 or not 0 <= int(b[5]) < len(runtime._REGION_CLASSES):
        return False
    cat = common.CATEGORY.get(runtime._REGION_CLASSES[int(b[5])])
    return bool(cat) and cat[0] not in (common.KIND_META,
                                        common.KIND_CONTAINER)


_BRIDGE_TOUCH = 0.25


def _union_bridges(h, boxes, words=None):
    """Read spanning two separate callouts took words from both."""
    r = h.get("rect")
    if not r:
        return False
    inside = [b for b in boxes
              if r[0] <= (b[0] + b[2]) / 2.0 <= r[2]
              and r[1] <= (b[1] + b[3]) / 2.0 <= r[3]]
    if len(inside) < 2:
        return False
    # only lone SIGN joins
    loose = [w for w in words or ()
             if str(w[4]).strip() in ("+", "-", "\u00b1")
             and r[0] <= (w[0] + w[2]) / 2.0 <= r[2]
             and r[1] <= (w[1] + w[3]) / 2.0 <= r[3]
             and not any(geometry._center_in(w, b[:4]) for b in inside)]

    def gap(a, b):
        return max(a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3])
    clusters = []
    for b in inside:
        s = max(min(b[2] - b[0], b[3] - b[1]), 2.0)
        # cut stack touches other half
        t = _BRIDGE_TOUCH * s
        hit = [c for c in clusters
               if gap(c, b) <= t
               or any(gap(w, b) <= t and gap(w, c) <= t for w in loose)]
        box = [b[0], b[1], b[2], b[3]]
        for c in hit:
            box = [min(box[0], c[0]), min(box[1], c[1]),
                   max(box[2], c[2]), max(box[3], c[3])]
            clusters.remove(c)
        clusters.append(box)
    return len(clusters) > 1
