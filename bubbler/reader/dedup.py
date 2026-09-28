# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# One hit per callout. Doubt survives merges.

import re as _re
from bubbler.reader import geometry  # noqa: E402


def _hit_anchor(h):
    """Anchor where hit was read not where balloon goes"""
    return h.get("arect") or h.get("rect")


# facts beyond dedup key
_KEEP_ON_MERGE = ("thru", "hole_note", "hole_notes", "qty")


def _carry_doubt(keep, lose):
    """Union doubt onto survivor for scanreview.FCF_SUSPECT untick"""
    for k in ("fcf_partial", "fcf_zone_suspect"):
        if lose.get(k):
            keep[k] = True
    fl = list(keep.get("fcf_flags") or ())
    for c in lose.get("fcf_flags") or ():
        if c not in fl:
            fl.append(c)
    if fl:
        keep["fcf_flags"] = fl


_TOL_PAIR = _re.compile(r"\s*([+\-]?\d+(?:[.,]\d+)?)"
                       r"(?:\s*/\s*([+\-]?\d+(?:[.,]\d+)?))?\s*$")


def _tol_key(t):
    """Numbers not spelling, missing side zero."""
    m = _TOL_PAIR.match(str(t)) if t else None
    if not m:
        return t
    nums = [float(x.replace(",", ".")) for x in m.groups() if x is not None]
    if len(nums) == 1:
        nums.append(0.0)
    return tuple(sorted(nums))


# smaller rect shared for near merge
_NEAR_OVERLAP = 0.25
# same read, one side grew
_SAME_READ_OVERLAP = 0.5


def dedup_hits(hits, tol=8.0, score=None):
    out, meta = [], []
    for h in hits:
        r = _hit_anchor(h)
        cx = (r[0] + r[2]) / 2.0 if r else None
        cy = (r[1] + r[3]) / 2.0 if r else None
        key = (h.get("tp"), h.get("sb"), str(h.get("v")), _tol_key(h.get("t")))
        dup = False
        at = None
        for i, (k2, r2, x2, y2) in enumerate(meta):
            if k2 != key:
                continue
            if cx is None or x2 is None:
                continue          # no geometry to merge
            # near centres must also overlap
            if (abs(cx - x2) <= tol and abs(cy - y2) <= tol
                    and geometry._rect_mostly_in(r2, r, _NEAR_OVERLAP)) or \
                    geometry._rect_covers(r2, r) or geometry._rect_covers(r, r2) or \
                    geometry._rect_mostly_in(r2, r, _SAME_READ_OVERLAP):
                dup = True
                at = i
                break
        if not dup:
            at = _composite_absorbs(out, h)
            dup = at is not None
        if dup:
            lose = h
            if score is not None and score(h) > score(out[at]):
                out[at], lose = h, out[at]
                meta[at] = (key, r, cx, cy)
            if len(str(lose.get("t") or "")) > len(str(out[at].get("t") or "")):
                # longer spelling, rect grown
                out[at]["t"] = lose["t"]
                a, b = out[at].get("rect"), lose.get("rect")
                if a and b:
                    out[at]["rect"] = geometry._union_all([a, b])
            for k in _KEEP_ON_MERGE:
                if out[at].get(k) is None and lose.get(k) is not None:
                    out[at][k] = lose[k]
            _carry_doubt(out[at], lose)
            continue
        out.append(h)
        meta.append((key, r, cx, cy))
        if h.get("fcf_composite"):
            # may arrive after segments
            for j in range(len(out) - 2, -1, -1):
                if _composite_absorbs([h], out[j]) is not None:
                    _carry_doubt(h, out[j])
                    del out[j], meta[j]
    return _drop_claimed_bare(out)


def _digits(s):
    return _re.sub(r"\D", "", str(s or ""))


# kinds that may be fragments
_FRAG_TP = ("LINEAR", "RADIUS", "ANGLE", "CHAMFER")


_NUMBER = _re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(s):
    return [_digits(n) for n in _NUMBER.findall(str(s or ""))]


# `8X 60`, `6X 60°`
_PATTERN_V = _re.compile(r"^(\d{1,3})X (\d+(?:[.,]\d+)?)\u00b0?$")


def _drop_claimed_bare(hits):
    """Fragment inside fuller read is phantom balloon."""
    def claim_rect(o):
        if o.get("tp") == "GDT" and o.get("arect"):
            return o["arect"]
        return o["rect"]

    def inside(h, o):
        cx = (h["rect"][0] + h["rect"][2]) / 2.0
        cy = (h["rect"][1] + h["rect"][3]) / 2.0
        r = claim_rect(o)
        return r[0] - 1 <= cx <= r[2] + 1 and r[1] - 1 <= cy <= r[3] + 1

    def related(h, o):
        if h.get("sb") == "BARE":
            return True
        tp = h.get("tp")
        return tp in _FRAG_TP and (o.get("tp") == tp or (
            tp == "ANGLE" and o.get("tp") == "CHAMFER"))

    def total_of(h, o):
        m = _PATTERN_V.match(str(o.get("v") or ""))
        v = _re.sub(r"[^\d.,]", "", str(h.get("v") or "")).replace(",", ".")
        if not m or h.get("t") or not v:
            return False
        try:
            n = int(m.group(1)) * float(m.group(2).replace(",", "."))
            return abs(float(v) - n) < 1e-6
        except ValueError:
            return False

    def claims(i, h, j, o):
        if total_of(h, o):
            return True
        d = _digits(h.get("v"))
        hb, ob = h.get("sb") == "BARE", o.get("sb") == "BARE"
        if hb and ob:
            od = _digits(o.get("v"))
            return d in od and (len(od) > len(d) or j < i)
        if h.get("t") and _digits(h.get("t")) != _digits(o.get("t")):
            return False
        nums = _numbers(o.get("v")) + (_numbers(o.get("t")) if hb else [])
        if d in nums:
            return (not hb or not ob) and (hb or j < i or len(nums) > 1)
        return (not hb and not h.get("t") and h.get("tp") == o.get("tp")
                and any(n.startswith(d) and len(n) > len(d)
                        for n in _numbers(o.get("v"))))

    geo = [h for h in hits if h.get("rect")]
    drop = set()
    for i, h in enumerate(geo):
        if not _digits(h.get("v")) or (h.get("sb") != "BARE"
                                       and h.get("tp") not in _FRAG_TP):
            continue
        for j, o in enumerate(geo):
            if i == j or j in drop or not o.get("rect") or \
                    not inside(h, o) or not related(h, o):
                continue
            if claims(i, h, j, o):
                drop.add(i)
                break
    gone = {id(geo[i]) for i in drop}
    return [h for h in hits if id(h) not in gone]


def _composite_absorbs(kept, h):
    if h.get("fcf_composite"):
        return None
    r = _hit_anchor(h)
    if r is None:
        return None
    for i, k in enumerate(kept):
        if not k.get("fcf_composite"):
            continue
        for b in (k.get("fcf_seg_rects") or ()):
            if geometry._rect_covers(b, r) or geometry._rect_mostly_in(b, r):
                return i
    return None


# balloon-group id bands
_VBLOCK = 900000


_TABLE_CG = 7000000
