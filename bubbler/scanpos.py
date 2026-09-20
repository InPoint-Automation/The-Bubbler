# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Position-aware scan of word boxes to anchored hits

import re as _re

from .scanlib import (SCAN_PATS, _GDT_SYMBOLS, gdt_zone_check, hole_note,
                      scan_normalize as _heal)
from .common import mode_admits_tp


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]),
            max(a[2], b[2]), max(a[3], b[3]))


def _union_all(rects):
    r = rects[0]
    for x in rects[1:]:
        r = _union(r, x)
    return r


def _ltext(line):
    return " ".join(t["t"] for t in line["toks"])


def _lrect(line):
    return _union_all([t["r"] for t in line["toks"]])


def _lheight(line):
    hs = [t["r"][3] - t["r"][1] for t in line["toks"]]
    hs.sort()
    return max(2.0, hs[len(hs) // 2])


_GLYPHS = {
    "\u00f8": "\u00d8", "\u2300": "\u00d8", "\u2205": "\u00d8",
    "\uf044": "\u00d8", "\uf064": "\u00d8",
    "\uf052": "\u00b1", "\uf072": "\u00b1",
    "\uf030": "\u00b0",
    "\u2212": "-", "\u2013": "-", "\u2011": "-",
}

# ISO hole marks -> keyword
_SYMBOLS = {
    "\u2334": "CBORE", "\u2294": "CBORE",
    "\u2335": "CSINK", "\u2228": "CSINK", "\u22c1": "CSINK",
    "\u21a7": "DEEP", "\u2913": "DEEP", "\u25bd": "DEEP",
    "\u25bf": "DEEP", "\u25bc": "DEEP", "\u25be": "DEEP",
    "\u2207": "DEEP", "\u22bd": "DEEP", "\u23f7": "DEEP",
    "\u2304": "DEEP",
}

_KEYWORDS = [
    (("THROUGH",), "THRU", None),
    (("PRZELOTOWY",), "THRU", None),
    (("PRZELOTOWE",), "THRU", None),
    (("PRZELOT",), "THRU", None),
    (("PRZEJŚCIOWY",), "THRU", None),
    (("PRZEJŚCIOWE",), "THRU", None),
    (("PRZEJŚCIOWA",), "THRU", None),
    (("DURCHGANGSLOCH",), "THRU", None),
    (("DURCHGANGSBOHRUNG",), "THRU", None),
    (("DURCHGEBOHRT",), "THRU", None),
    (("DURCHBOHREN",), "THRU", None),
    (("DURCHBOHRT",), "THRU", None),
    (("DURCHBOHRUNG",), "THRU", None),
    (("DURCHGANG",), "THRU", None),
    (("DURCHGEHEND",), "THRU", None),
    (("DURCH",), "THRU", None),
    (("//",), "PARALLELISM", "num"),
    (("G\u0141\u0118B",), "DEEP", None),
    (("G\u0141",), "DEEP", None),
    (("TIEFE",), "DEEP", None),
    (("TIEF",), "DEEP", None),
    (("DP",), "DEEP", "num"),
    (("DURCHMESSER",), "\u00d8", None),
    (("DMR",), "\u00d8", "num"),
    (("\u015aREDNICA",), "\u00d8", None),
    (("\u015aR",), "\u00d8", "num"),
    (("DIAM",), "\u00d8", "num"),
    (("DIA",), "\u00d8", "num"),
    (("RADIUS",), "R", "num"),
    (("PROMIE\u0143",), "R", "num"),
    (("FASE",), "C", "num"),
    (("FAZA",), "C", "num"),
    (("FAZOWANIE",), "C", "num"),
    (("POG\u0141\u0118BIENIE", "WALCOWE"), "CBORE", None),
    (("FLACHSENKUNG",), "CBORE", None),
    (("SPOTFACE",), "CBORE", None),
    (("SF",), "CBORE", "dnum"),
    (("POG\u0141\u0118BIENIE", "STO\u017bKOWE"), "CSINK", None),
    (("ANSENKUNG",), "CSINK", None),
    (("SENKUNG",), "CSINK", None),
    (("CSK",), "CSINK", "dnum"),
]

_COUNT_WORDS = ("PLACES", "PLCS", "OTWORY", "OTWOR\u00d3W", "OTW",
                "STK", "ST\u00dcCK", "MAL")
_COUNT_RE = _re.compile(
    r"(\d+)\s*(?:%s)\.?$" % "|".join(_COUNT_WORDS), _re.I)

_NUM_START = _re.compile(r"^[\d.]")
_DNUM_START = _re.compile(r"^[\u00d8\d.]")


def _kw_key(text):
    return text.upper().rstrip(".,;:")


def _cond_match(cond, nxt):
    if cond is None:
        return True
    if not nxt:
        return False
    pat = _NUM_START if cond == "num" else _DNUM_START
    return bool(pat.match(nxt))


# phi look-alikes conditional
_PHI_RE = _re.compile(r"(?<![A-Za-z0-9.,])"
                      r"[\u03a6\u03c6\u03d5\u0424](?=\d)")


def _norm_token(s):
    for a, b in _GLYPHS.items():
        s = s.replace(a, b)
    s = _PHI_RE.sub("\u00d8", s)
    for a, b in _SYMBOLS.items():
        s = s.replace(a, " %s " % b)
    for a, b in _GDT_SYMBOLS:
        if a in s:
            s = s.replace(a, b)
    s = _COUNT_RE.sub(lambda m: m.group(1) + "X", s)
    s = _re.sub(r"\bDIAM?\.?(?=[\d.])", "\u00d8", s, flags=_re.I)
    s = _re.sub(r"[\u00c6\u00e6](?=\s*\d)", "\u00d8", s)
    s = _re.sub(r"(?<![A-Za-z0-9.,])[OoQ\u03a6\u03c6\u0398\u03b8](?=\d)",
                "\u00d8", s)
    s = _re.sub(r"(?<![\dA-Za-z.,/+\-])0(?=\d{1,3}(?:[.,]\d+)?(?![\d.,\-]))",
                "\u00d8", s)
    s = _re.sub(r"([+\-]\d+[.,]\d+)(?=[+\-]\d+[.,]\d+)", r"\1/", s)
    return s


def _normalize_line(line):
    toks = []
    for t in line["toks"]:
        s = _norm_token(t["t"]).strip()
        if not s:
            continue
        for part in s.split():
            toks.append({"t": part, "r": t["r"]})

    out = []
    i = 0
    while i < len(toks):
        hit = None
        for words, canon, cond in _KEYWORDS:
            n = len(words)
            if i + n > len(toks):
                continue
            if all(_kw_key(toks[i + j]["t"]) == words[j]
                   for j in range(n)):
                nxt = toks[i + n]["t"] if i + n < len(toks) else ""
                if _cond_match(cond, nxt):
                    hit = (n, canon)
                    break
        if hit:
            n, canon = hit
            out.append({"t": canon,
                        "r": _union_all([toks[i + j]["r"]
                                         for j in range(n)])})
            i += n
        else:
            out.append(toks[i])
            i += 1
    toks = out

    def merge_run(i, j, text):
        toks[i] = {"t": text,
                   "r": _union_all([t["r"] for t in toks[i:j + 1]])}
        del toks[i + 1:j + 1]

    changed = True
    while changed:
        changed = False
        for i in range(len(toks) - 1):
            a, b = toks[i]["t"], toks[i + 1]["t"]
            c = toks[i + 2]["t"] if i + 2 < len(toks) else None
            if (c is not None and b in (".", ",") and
                    _re.match(r"^\d+$", a) and _re.match(r"^\d", c)):
                merge_run(i, i + 2, a + b + c)      # OCR-split 0 , 1
            elif (_re.match(r"^\d+$", a) and
                    _re.match(r"^\.\d{1,4}$", b)):
                merge_run(i, i + 1, a + b)
            elif a in "+-" and _re.match(r"^[\d.][\d.,]*$", b):
                merge_run(i, i + 1, a + b)
            elif (_re.match(r"^[+\-][\d.,]+$", a) and
                    _re.match(r"^[+\-][\d.,]+$", b)):
                merge_run(i, i + 1, a + "/" + b)
            elif (a == "0" and _re.match(r"^[+\-][\d.,]+$", b)):
                merge_run(i, i + 1, "0/" + b)
            elif (b == "0" and _re.match(r"^[+\-][\d.,]+$", a)):
                merge_run(i, i + 1, a + "/0")
            elif (_re.match(r"^\d+$", a) and
                    _kw_key(b) in _COUNT_WORDS):
                merge_run(i, i + 1, a + "X")
            else:
                continue
            changed = True
            break

    for t in toks:
        t["t"] = _re.sub(r"(?<![\w.])\.(?=\d)", "0.", t["t"])

    line["toks"] = toks


def xform_pt(m, x, y):
    return (x * m.a + y * m.c + m.e, x * m.b + y * m.d + m.f)


def xform_rect(m, x0, y0, x1, y1):
    ax, ay = xform_pt(m, x0, y0)
    bx, by = xform_pt(m, x1, y1)
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


def page_words(page):
    try:
        words = page.get_text("words")
    except Exception:
        return []
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    if not rot:
        return list(words)
    try:
        m = page.rotation_matrix
    except Exception:
        return list(words)
    return [xform_rect(m, w[0], w[1], w[2], w[3]) + tuple(w[4:])
            for w in words]


def lines_from_words(words):
    groups = {}
    for w in words:
        x0, y0, x1, y1, text, blk, ln, wn = w[:8]
        groups.setdefault((blk, ln), []).append(
            (wn, {"t": str(text), "r": (float(x0), float(y0),
                                        float(x1), float(y1))}))
    lines = []
    for key in sorted(groups):
        toks = [t for _, t in sorted(groups[key], key=lambda kv: kv[0])]
        lines.append({"key": key, "toks": toks})
    return lines


_DEV_LINE = _re.compile(r"^(?:[+\-]\s*[\d.,]+|0(?:[.,]\d+)?)$")
_NX_LINE = _re.compile(r"^\d+[Xx\u00d7]$")
_NUMONLY_LINE = _re.compile(r"^[.\d]+$")
_FIT_LINE = _re.compile(
    r"^([A-Za-z]{1,2}[ ]?\d{1,2})"
    r"(?:\s*/\s*[A-Za-z]{1,2}[ ]?\d{1,2})?$")


def _split_lines_on_gaps(lines, factor=4.0):
    out = []
    for l in lines:
        toks = l["toks"]
        if len(toks) < 2:
            out.append(l)
            continue
        h = _lheight(l)
        cur = [toks[0]]
        for t in toks[1:]:
            if t["r"][0] - cur[-1]["r"][2] > factor * h:
                out.append({"key": l["key"], "toks": cur})
                cur = [t]
            else:
                cur.append(t)
        out.append({"key": l["key"], "toks": cur})
    return out


_DEPTH_MARK = _re.compile(r"\bDEEP\b", _re.I)


def _depth_marker_idxs(lines):
    return [i for i, l in enumerate(lines) if _DEPTH_MARK.search(_ltext(l))]


def _depth_owned(idx, lines, markers):
    r = _lrect(lines[idx])
    h = max(r[3] - r[1], 2.0)
    for mi in markers:
        if mi == idx:
            continue
        rm = _lrect(lines[mi])
        if min(r[2], rm[2]) - max(r[0], rm[0]) <= 0:
            continue
        if max(rm[1] - r[3], r[1] - rm[3], 0.0) <= 2.0 * h:
            return True
    return False


def merge_stacked(lines):
    used = set()
    markers = _depth_marker_idxs(lines)
    devs = [i for i, l in enumerate(lines)
            if _DEV_LINE.match(_ltext(l).strip())
            and not _depth_owned(i, lines, markers)]
    for bi in devs:
        if bi in used:
            continue
        rb = _lrect(lines[bi])
        tb = _ltext(lines[bi]).strip()
        for ci in devs:
            if ci in used or ci == bi:
                continue
            rc = _lrect(lines[ci])
            tc = _ltext(lines[ci]).strip()
            if not (tb.startswith(("+", "-")) or
                    tc.startswith(("+", "-"))):
                continue
            h = max(rb[3] - rb[1], rc[3] - rc[1], 2.0)
            if min(rb[2], rc[2]) - max(rb[0], rc[0]) <= 0:
                continue
            if rc[1] < rb[1]:
                continue
            if rc[1] - rb[3] > 1.5 * h:
                continue
            top, bot = min(rb[1], rc[1]), max(rb[3], rc[3])
            best = None
            for ai, A in enumerate(lines):
                if ai in used or ai in (bi, ci):
                    continue
                ta = _ltext(A)
                if not _re.search(r"\d\s*$", ta):
                    continue
                if _DEV_LINE.match(ta.strip()):
                    continue
                if _re.search(r"\d\s*:\s*\d", ta):    # a ratio, not a nominal
                    continue
                ra = _lrect(A)
                cy = (ra[1] + ra[3]) / 2.0
                if not (top - h <= cy <= bot + h):
                    continue
                gap = min(rb[0], rc[0]) - ra[2]
                if gap < -h or gap > 6 * h:
                    continue
                if best is None or gap < best[0]:
                    best = (gap, ai)
            if best is not None:
                A = lines[best[1]]
                txt = (tb + "/" + tc).replace(" ", "")
                A["toks"].append({"t": txt, "r": _union(rb, rc)})
                used.add(bi)
                used.add(ci)
                break
    return [l for i, l in enumerate(lines) if i not in used]


def merge_halfstack(lines):
    _TAIL = _re.compile(r"\d\s*[+\-][\d.,]*\d$")
    used = set()
    markers = _depth_marker_idxs(lines)
    for di, Dv in enumerate(lines):
        td = _ltext(Dv).strip()
        if not _DEV_LINE.match(td):
            continue
        if _depth_owned(di, lines, markers):
            continue
        rd = _lrect(Dv)
        h = max(rd[3] - rd[1], 2.0)
        best = None
        for ai, A in enumerate(lines):
            if ai == di or ai in used:
                continue
            ta = _ltext(A)
            tail = ta.rsplit(None, 1)[-1] if ta.split() else ""
            if not _TAIL.search(ta) or "/" in tail:
                continue
            ra = _lrect(A)
            vgap = max(rd[1] - ra[3], ra[1] - rd[3], 0.0)
            if vgap > 1.5 * h:
                continue
            if rd[2] < ra[0] or rd[0] > ra[2] + 4 * h:
                continue
            score = vgap + abs(rd[0] - ra[2])
            if best is None or score < best[0]:
                best = (score, ai)
        if best is not None:
            A = lines[best[1]]
            tok = A["toks"][-1]
            A["toks"][-1] = {"t": tok["t"] + "/" + td.replace(" ", ""),
                             "r": _union(tok["r"], rd)}
            used.add(di)
    return [l for i, l in enumerate(lines) if i not in used]


def merge_callout_block(lines):
    KW = ("THRU", "DEEP", "CBORE", "CSINK")
    for _ in range(3):
        used = set()
        moved = False
        for i, L in enumerate(lines):
            if i in used:
                continue
            tl = _ltext(L).strip()
            up = tl.upper()
            if not up.startswith(KW) or len(L["toks"]) > 6:
                continue
            rl = _lrect(L)
            h = max(_lheight(L), 2.0)
            best = None
            for j, M in enumerate(lines):
                if j == i or j in used:
                    continue
                tm = _ltext(M)
                if not _re.search(r"\d", tm):
                    continue
                if tm.strip().upper().startswith(KW):
                    continue
                rm = _lrect(M)
                ov = min(rl[2], rm[2]) - max(rl[0], rm[0])
                if ov <= 0:
                    continue
                vgap = max(rm[1] - rl[3], rl[1] - rm[3], 0.0)
                if vgap > 1.6 * h:
                    continue
                frac = ov / max(min(rl[2] - rl[0], rm[2] - rm[0]), 1e-6)
                score = (-round(frac, 2), vgap)
                if best is None or score < best[0]:
                    best = (score, j)
            if best is not None:
                M = lines[best[1]]
                rm = _lrect(M)
                if rl[1] >= rm[1]:
                    M["toks"].extend(L["toks"])
                else:
                    M["toks"][0:0] = L["toks"]
                used.add(i)
                moved = True
        lines = [l for i, l in enumerate(lines) if i not in used]
        if not moved:
            break
    return lines


def _fcf_vector_bands(page, rect, cfg):
    try:
        paths = page.get_drawings()
    except Exception:
        return [], []
    if not paths:
        return [], []
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    m = None
    if rot:
        try:
            m = page.rotation_matrix
        except Exception:
            return None
    x0, y0, x1, y1 = rect
    w = x1 - x0
    h = y1 - y0
    if w < 4 or h < 4:
        return None
    tol = max(1.0, 0.06 * h)
    xs, ys, xspan = [], [], []
    for p in paths:
        for it in (p.get("items") or []):
            if it[0] != "l":
                continue
            pa, pb = it[1], it[2]
            ax, ay, bx, by = pa.x, pa.y, pb.x, pb.y
            if m is not None:
                ax, ay = xform_pt(m, ax, ay)
                bx, by = xform_pt(m, bx, by)
            sx0, sy0 = min(ax, bx), min(ay, by)
            sx1, sy1 = max(ax, bx), max(ay, by)
            dx, dy = sx1 - sx0, sy1 - sy0
            if dy >= 0.5 * h and dx <= tol:
                cx = (sx0 + sx1) / 2.0
                if x0 - tol <= cx <= x1 + tol:
                    xs.append(cx)
                    xspan.append((cx, sy0, sy1))
            elif dx >= 0.5 * w and dy <= tol:
                cy = (sy0 + sy1) / 2.0
                if y0 - tol <= cy <= y1 + tol:
                    ys.append((cy, sx0, sx1))
    # trim margin from frame
    box = None
    if len(xs) >= 2 and len(ys) >= 2:
        # closed box not pairs
        if any(a - tol <= min(xs) and b + tol >= max(xs)
               and abs(a - min(xs)) <= tol + (b - a) * 0.05
               for _y, a, b in ys):
            x0, x1 = min(xs), max(xs)
            y0, y1 = min(t[0] for t in ys), max(t[0] for t in ys)
            tol = max(1.0, 0.06 * (y1 - y0))
            box = (x0, y0, x1, y1)
    if box is not None:
        # keep frame-spanning dividers only
        over = max(3.0, 0.15 * (y1 - y0))
        keep = set(cx for cx, sy0, sy1 in xspan
                   if sy0 <= y0 + tol and sy1 >= y1 - tol
                   and not (sy0 < y0 - over and sy1 > y1 + over))
        xs = [x for x in xs if x in keep]
    inx = _cluster(sorted(x for x in xs if x0 + tol < x < x1 - tol), tol)
    # row divider inside frame
    rows = _cluster_spans([t for t in ys if y0 + tol < t[0] < y1 - tol
                           and t[1] >= x0 - tol and t[2] <= x1 + tol], tol)
    return (inx, [t[0] for t in rows], [(t[1], t[2]) for t in rows], box,
            [])            # no enclosing guess


def _longest_ink(mask):
    """First and last of longest unbroken True run else None"""
    best = run = None
    for i, v in enumerate(mask):
        if v:
            run = (run[0], i) if run else (i, i)
            if best is None or run[1] - run[0] > best[1] - best[0]:
                best = run
        else:
            run = None
    return best


def _fcf_boxed(dark, vruns, hruns, cover=0.9):
    """Closed frame box left right top bottom else None"""
    if len(vruns) < 2 or len(hruns) < 2:
        return None
    l, r = vruns[0][0], vruns[-1][-1]
    # longest contiguous border ink
    side = _longest_ink(dark[:, l:vruns[0][-1] + 1].any(axis=1))
    side2 = _longest_ink(dark[:, vruns[-1][0]:r + 1].any(axis=1))
    if side is None or side2 is None:
        return None
    vtop = min(side[0], side2[0])
    vbot = max(side[1], side2[1])
    tolv = max(2, 0.05 * (vbot - vtop + 1))
    inside = [h for h in hruns
              if vtop - tolv <= h[0] and h[-1] <= vbot + tolv]
    # inner pair else outermost
    if len(inside) >= 2:
        hruns = inside
    t, b = hruns[0][0], hruns[-1][-1]
    if r - l < 2 or b - t < 2:
        return None
    box = dark[t:b + 1, l:r + 1]
    if box.size == 0:
        return None
    hh, ww = box.shape
    # measure side over middle
    my0, my1 = int(hh * 0.1), max(int(hh * 0.9), int(hh * 0.1) + 1)
    mx0, mx1 = int(ww * 0.1), max(int(ww * 0.9), int(ww * 0.1) + 1)
    sides = (box[my0:my1, :vruns[0][-1] - l + 1].any(axis=1).mean(),
             box[my0:my1, vruns[-1][0] - l:].any(axis=1).mean(),
             box[:hruns[0][-1] - t + 1, mx0:mx1].any(axis=0).mean(),
             box[hruns[-1][0] - t:, mx0:mx1].any(axis=0).mean())
    if min(sides) < cover:
        return None
    rr = dark.any(axis=1).nonzero()[0]
    cc = dark.any(axis=0).nonzero()[0]
    if not rr.size or not cc.size:
        return None
    if ww < cover * (cc[-1] - cc[0] + 1) or hh < cover * (rr[-1] - rr[0] + 1):
        return None                    # divider posing as border
    return l, r, t, b


def _fcf_through_border(enclosing, c):
    """Divider at column c runs past frame border into margin (W55)"""
    if enclosing is None:
        return False
    full, l, t, b = enclosing
    h = full.shape[0]
    uc = int(round(l + c))
    if not (0 <= uc < full.shape[1] and t >= 3 and b <= h - 4):
        return False                       # no margin beyond border
    return bool(full[:t, uc].mean() > 0.5 and full[b + 1:, uc].mean() > 0.5)


def _fcf_raster_bands(ink, rect, cfg):
    try:
        import numpy as np
    except Exception:
        return None
    a = np.asarray(ink)
    if a.ndim == 3:
        a = a.mean(axis=2)
    if a.ndim != 2 or a.size == 0:
        return None
    # threshold off crop range
    lo, hi = float(a.min()), float(a.max())
    thr = lo + 0.5 * (hi - lo) if hi > lo else (hi * 0.5 if hi else 0.5)
    dark = a < thr
    x0, y0, x1, y1 = rect
    # trim to ink first
    hgt, wid = dark.shape
    gap = max(1, int(cfg.get("vision_fcf_proj_gap", 2)))
    frac = float(cfg.get("vision_fcf_divider_min", 0.6))
    vruns = _profile_runs(dark.sum(axis=0).astype(float), hgt * frac, gap)
    hruns = _profile_runs(dark.sum(axis=1).astype(float), wid * frac, gap)
    boxed = _fcf_boxed(dark, vruns, hruns)
    box = None
    enclosing = None
    if boxed:
        # trim to border runs
        px = (x1 - x0) / max(wid, 1)
        py = (y1 - y0) / max(hgt, 1)
        l, r, t, b = boxed
        # untrimmed crop for W55
        enclosing = (dark, l, t, b)
        x0, x1 = x0 + l * px, x0 + (r + 1) * px
        y0, y1 = y0 + t * py, y0 + (b + 1) * py
        dark = dark[t:b + 1, l:r + 1]
        hgt, wid = dark.shape
        box = (x0, y0, x1, y1)
    col = dark.sum(axis=0).astype(float)
    row = dark.sum(axis=1).astype(float)
    xs = _profile_lines(col, hgt * frac, gap)
    sx = (x1 - x0) / max(wid, 1)
    sy = (y1 - y0) / max(hgt, 1)
    # 2px border not divider
    tol = max(1.0, 0.06 * (y1 - y0))
    inx = [x0 + c * sx for c in xs
           if x0 + tol < x0 + c * sx < x1 - tol]
    # dividers into margin (W55)
    enc = [x0 + c * sx for c in xs
           if x0 + tol < x0 + c * sx < x1 - tol
           and _fcf_through_border(enclosing, c)]
    # divider from symbol cell
    first = min([c for c in xs if 0 < c < wid - 1] or [0])
    # floor stops phantom divider
    yruns = _profile_runs(row, max(wid - first, wid * 0.5) * frac, gap)
    # mask thin frame lines
    vmask = np.zeros(wid, dtype=bool)
    line_w = max(2, int(0.03 * wid))
    for r in _profile_runs(col, hgt * frac, gap):
        if len(r) <= line_w or r[0] <= 1 or r[-1] >= wid - 2:
            vmask[r[0]:r[-1] + 1] = True
    iny, spans = [], []
    for r in yruns:
        yp = y0 + (sum(r) / len(r)) * sy
        if not (y0 + tol < yp < y1 - tol):
            continue
        iny.append(yp)
        # mask verticals off band
        band = dark[r[0]:r[-1] + 1].any(axis=0) & ~vmask
        cols = band.nonzero()[0]                               # divider extent
        if not cols.size:                      # fully masked read unmasked
            cols = dark[r[0]:r[-1] + 1].any(axis=0).nonzero()[0]
        # unknown fails to bubble
        spans.append((x0 + float(cols[0]) * sx, x0 + float(cols[-1]) * sx)
                     if cols.size else (x1, x1))
    return inx, iny, spans, box, enc


def _profile_runs(prof, thresh, gap):
    """Index runs above ink threshold"""
    idx = [i for i, v in enumerate(prof) if v >= thresh]
    if not idx:
        return []
    runs = [[idx[0]]]
    for i in idx[1:]:
        if i - runs[-1][-1] <= gap:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def _profile_lines(prof, thresh, gap):
    return [sum(r) / len(r) for r in _profile_runs(prof, thresh, gap)]


def _cluster_spans(items, tol):
    """Cluster (y, x0, x1) dividers unioning x extent"""
    groups = []
    for v, a, b in sorted(items):
        if groups and v - groups[-1][-1][0] <= tol:
            groups[-1].append((v, a, b))
        else:
            groups.append([(v, a, b)])
    out = []
    for g in groups:
        out.append((sum(t[0] for t in g) / len(g),
                    min(t[1] for t in g), max(t[2] for t in g)))
    return out


def _cluster(vals, tol):
    out = []
    for v in vals:
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(r) / len(r) for r in out]


def _bands_from_dividers(x0, x1, xs):
    edges = [x0] + list(xs) + [x1]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


# Find frame centre-out

FCF_BOX_DPI = 150                # enough for border
FCF_BOX_LOOK = 1.0               # share of box size


def _fcf_rect_from_lines(hlines, vlines, cx, cy, cover=0.95, depth=4,
                         like=None, maxw=None, maxh=None, span=None,
                         limit=8):
    """Closed rectangles around (cx, cy) best IoU first"""
    sw, sh = (span or (None, None))
    up = _near_side([h for h in hlines if h[0] <= cy], cy, depth, span=sw)
    dn = _near_side([h for h in hlines if h[0] > cy], cy, depth, span=sw)
    lf = _near_side([v for v in vlines if v[0] <= cx], cx, depth, span=sh)
    rt = _near_side([v for v in vlines if v[0] > cx], cx, depth, span=sh)
    cand = []
    for t in up:
        for b in dn:
            h = b[0] - t[0]
            if h <= 1:
                continue
            for l in lf:
                for r in rt:
                    w = r[0] - l[0]
                    if w <= 1 or (maxw and w > maxw) or (maxh and h > maxh):
                        continue          # bigger than search window
                    if not (_covers(t[1], t[2], l[0], r[0], w, cover)
                            and _covers(b[1], b[2], l[0], r[0], w, cover)
                            and _covers(l[1], l[2], t[0], b[0], h, cover)
                            and _covers(r[1], r[2], t[0], b[0], h, cover)):
                        continue
                    box = (l[0], t[0], r[0], b[0])
                    # frame has compartments
                    if not any(l[0] + 1 < v[0] < r[0] - 1
                               and _covers(v[1], v[2], t[0], b[0], h, cover)
                               for v in vlines):
                        continue
                    if like is None:
                        cand.append((w * h, w * h, box))
                        continue
                    cand.append((_iou(box, like), w * h, box))
    if not cand:
        return []
    # prefer biggest plausible rect
    good = [c for c in cand if c[0] >= 0.5]
    if good:
        good.sort(key=lambda c: -c[1])
    else:
        good = sorted(cand, key=lambda c: -c[0])
    out, seen = [], set()
    for _s, _a, box in good:
        if box in seen:
            continue
        seen.add(box)
        out.append(box)
    return out[:limit]


def _iou(a, b):
    """Intersection over union of two rects."""
    ow = min(a[2], b[2]) - max(a[0], b[0])
    oh = min(a[3], b[3]) - max(a[1], b[1])
    if ow <= 0 or oh <= 0:
        return 0.0
    inter = ow * oh
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _near_side(lines, at, depth, keep=0.5, span=None):
    """depth nearest length-filtered candidates for one frame side"""
    if not lines:
        return []
    longest = max(ln[2] - ln[1] for ln in lines)
    floor = keep * longest if not span else min(keep * longest, keep * span)
    real = [ln for ln in lines if ln[2] - ln[1] >= floor]
    if not real:
        return []
    near = sorted(real, key=lambda ln: abs(ln[0] - at))[:depth]
    far = max(real, key=lambda ln: ln[2] - ln[1])
    return near if far in near else near + [far]


def _covers(a0, a1, b0, b1, span, cover):
    """Segment covers `cover` of b0..b1 side"""
    return (min(a1, b1) - max(a0, b0)) >= cover * span


def _lines_from_ink(dark, minrun=0.1):
    """Long ink runs in crop to pixel-space hlines and vlines"""
    hgt, wid = dark.shape
    hmin = max(4, int(minrun * wid))
    vmin = max(4, int(minrun * hgt))
    hlines, vlines = [], []
    for y in range(hgt):
        run = _longest_ink(dark[y])
        if run is not None and run[1] - run[0] + 1 >= hmin:
            hlines.append((y, run[0], run[1]))
    for x in range(wid):
        run = _longest_ink(dark[:, x])
        if run is not None and run[1] - run[0] + 1 >= vmin:
            vlines.append((x, run[0], run[1]))
    return _thin(hlines), _thin(vlines)


def _thin(lines, gap=2):
    """One line per band"""
    out = []
    for ln in lines:
        if out and ln[0] - out[-1][0] <= gap:
            prev = out[-1]                       # keep longest of band
            if ln[2] - ln[1] > prev[2] - prev[1]:
                out[-1] = ln
            continue
        out.append(ln)
    return out


def _clamp_page(page, rect):
    """Clip rect to page"""
    try:
        pr = page.rect
        px0, py0, px1, py1 = pr.x0, pr.y0, pr.x1, pr.y1
    except Exception:
        return rect
    return (max(rect[0], px0), max(rect[1], py0),
            min(rect[2], px1), min(rect[3], py1))


def _fcf_reads_as_frame(words, box, vlines):
    """Rect content reads like control frame 0 1 or 2"""
    x0, y0, x1, y1 = box
    inner = sorted(v[0] for v in vlines if x0 + 1 < v[0] < x1 - 1)
    if not inner:
        return 0
    first = inner[0]
    sym = num = False
    for w in words:
        cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        raw = str(w[4])
        t = _heal(raw)
        if cx <= first:
            # match glyph or keyword
            if any(g in raw for g in _GDT_SYMBOLS_SET) or \
                    any(k in t for k in _GDT_WORDS):
                sym = True
        elif _NUMISH.search(t):
            num = True
    return (2 if sym and num else 1 if sym else 0)


_GDT_SYMBOLS_SET = frozenset(g for g, _kw in _GDT_SYMBOLS)
_GDT_WORDS = tuple(sorted(set(kw.strip() for _g, kw in _GDT_SYMBOLS
                              if kw.strip()), key=len, reverse=True))
_NUMISH = _re.compile(r"\d")


def _fcf_pick(page, boxes, vlines):
    """Candidate reading as frame else best geometric"""
    if not boxes:
        return None
    if len(boxes) == 1:
        return boxes[0]
    try:
        words = page_words(page)
    except Exception:
        return boxes[0]
    best, at = -1, 0
    for i, b in enumerate(boxes):
        sc = _fcf_reads_as_frame(words, b, vlines)
        if sc > best:                    # ties keep geometric order
            best, at = sc, i
    return boxes[at]


def _fcf_find_box(page, rect, cfg):
    """Drawn frame around detector box to rect else None"""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    px = max(4.0, FCF_BOX_LOOK * (x1 - x0))
    py = max(4.0, FCF_BOX_LOOK * (y1 - y0))
    wide = _clamp_page(page, (x0 - px, y0 - py, x1 + px, y1 + py))
    lim = (x1 - x0 + 2 * px, y1 - y0 + 2 * py)
    span = (x1 - x0, y1 - y0)
    boxes, vl = _fcf_box_vector(page, wide, cx, cy, rect, lim, span)
    if not boxes:
        boxes, vl = _fcf_box_raster(page, cfg, wide, cx, cy, rect, lim, span)
    box = _fcf_pick(page, boxes, vl)
    if box is None:
        return None
    bw, bh = box[2] - box[0], box[3] - box[1]
    ov = (max(0.0, min(box[2], x1) - max(box[0], x0))
          * max(0.0, min(box[3], y1) - max(box[1], y0)))
    # mostly inside detector box
    if bw < 4 or bh < 4 or ov < 0.5 * bw * bh:
        return None
    # same object not compartment
    if _iou(box, rect) < 0.15:
        return None
    return box


def _fcf_box_vector(page, wide, cx, cy, like=None, lim=None,
                    span=None):
    """Frame candidates off page line work plus their verticals"""
    try:
        paths = page.get_drawings()
    except Exception:
        return [], []
    if not paths:
        return [], []
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    m = None
    if rot:                    # same conversion as _fcf_vector_bands
        try:
            m = page.rotation_matrix
        except Exception:
            return [], []
    hl, vl = [], []
    for p in paths:
        for it in (p.get("items") or []):
            if it[0] != "l":
                continue
            ax, ay, bx, by = it[1].x, it[1].y, it[2].x, it[2].y
            if m is not None:
                ax, ay = xform_pt(m, ax, ay)
                bx, by = xform_pt(m, bx, by)
            lo, hi = min(ax, bx), max(ax, bx)
            loy, hiy = min(ay, by), max(ay, by)
            if not (wide[0] <= hi and lo <= wide[2]
                    and wide[1] <= hiy and loy <= wide[3]):
                continue
            if abs(by - ay) <= 1.0 and hi - lo > 2.0:
                hl.append(((ay + by) / 2.0, lo, hi))
            elif abs(bx - ax) <= 1.0 and hiy - loy > 2.0:
                vl.append(((ax + bx) / 2.0, loy, hiy))
    return (_fcf_rect_from_lines(hl, vl, cx, cy, like=like,
                                 maxw=(lim or (None, None))[0],
                                 maxh=(lim or (None, None))[1], span=span),
            vl)


def _fcf_box_raster(page, cfg, wide, cx, cy, like=None, lim=None,
                    span=None):
    """Frame box off one low-dpi render"""
    try:
        import numpy as np
        from . import vision
        pm = vision._pixmap_clip(page, cfg, wide,
                                 cfg.get("vision_fcf_box_dpi", FCF_BOX_DPI))
    except Exception:
        return [], []
    if pm is None:
        return [], []
    a = np.asarray(pm[0])
    if a.ndim == 3:
        a = a.mean(axis=2)
    if a.ndim != 2 or a.size == 0:
        return [], []
    lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        return [], []
    dark = a < lo + 0.5 * (hi - lo)
    hgt, wid = dark.shape
    sx = (wide[2] - wide[0]) / max(wid, 1)
    sy = (wide[3] - wide[1]) / max(hgt, 1)
    hl, vl = _lines_from_ink(dark)
    hl = [(wide[1] + y * sy, wide[0] + a0 * sx, wide[0] + a1 * sx)
          for y, a0, a1 in hl]
    vl = [(wide[0] + x * sx, wide[1] + b0 * sy, wide[1] + b1 * sy)
          for x, b0, b1 in vl]
    return (_fcf_rect_from_lines(hl, vl, cx, cy, like=like,
                                 maxw=(lim or (None, None))[0],
                                 maxh=(lim or (None, None))[1], span=span),
            vl)


def _fcf_bands_for(page, rect, cfg, crop=None):
    """Vector bands if page draws them else raster off clip"""
    bands = None
    try:
        bands = _fcf_vector_bands(page, rect, cfg)
    except Exception:
        bands = None
    if bands is not None and not bands[0]:
        bands = None
    if bands is not None:
        return bands
    ink = crop
    if ink is None:
        try:
            from . import vision
            pm = vision._pixmap_clip(page, cfg, rect,
                                     cfg.get("vision_fcf_dpi", 600))
        except Exception:
            pm = None
        if pm is None:
            return None
        ink = pm[0]
    try:
        return _fcf_raster_bands(ink, rect, cfg)
    except Exception:
        return None


# reach for clipped border
_FCF_WIDEN = (0.15, 0.40)
_FCF_WIDEN_MIN = 4.0


def _fcf_widen(page, rect, cfg, bands):
    """Widen crop for frame whose border detector box clipped"""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    area = max((x1 - x0) * (y1 - y0), 1e-6)
    for k in _FCF_WIDEN:
        px = max(_FCF_WIDEN_MIN, k * (x1 - x0))
        py = max(_FCF_WIDEN_MIN, k * (y1 - y0))
        alt = _fcf_bands_for(
            page, _clamp_page(page, (x0 - px, y0 - py, x1 + px, y1 + py)),
            cfg, None)
        if alt is None or alt[3] is None:
            continue
        bx0, by0, bx1, by1 = alt[3]
        if not (bx0 <= cx <= bx1 and by0 <= cy <= by1):
            continue                       # centred on someone else
        ov = (max(0.0, min(bx1, x1) - max(bx0, x0))
              * max(0.0, min(by1, y1) - max(by0, y0)))
        if ov / area >= 0.6:               # still mostly given box
            return alt
    return bands


def segment_fcf_cells(page, rect, cfg, crop=None):
    cfg = cfg or {}
    x0, y0, x1, y1 = rect
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    unboxed = False
    if crop is None and page is not None:
        # find drawn frame centre-out
        found = None
        try:
            found = _fcf_find_box(page, rect, cfg)
        except Exception:
            found = None
        if found is not None:
            # hair wider than box
            m = max(1.5, 0.01 * min(found[2] - found[0],
                                    found[3] - found[1]))
            rect = _clamp_page(page, (found[0] - m, found[1] - m,
                                      found[2] + m, found[3] + m))
            x0, y0, x1, y1 = rect
    bands = _fcf_bands_for(page, rect, cfg, crop)
    if bands is not None and bands[3] is None and crop is None \
            and page is not None:
        bands = _fcf_widen(page, rect, cfg, bands)
    if bands is not None and bands[3] is None:
        # no box but readable
        unboxed = True
    if bands is None:
        return None
    xs, mids, spans, box, enc = bands
    if box is not None:
        # measure cells from frame
        x0, y0, x1, y1 = box
    cells = _bands_from_dividers(x0, x1, sorted(xs))
    if len(cells) < 2:
        return None
    # W55 alternate fallback read
    cells_alt = None
    if enc:
        kept = [x for x in xs if x not in enc]
        alt = _bands_from_dividers(x0, x1, sorted(kept))
        if 2 <= len(alt) < len(cells):
            cells_alt = alt
    if not spans:
        spans = [None] * len(mids)
    order = sorted(range(len(mids)), key=lambda i: mids[i])
    ys = [mids[i] for i in order]
    # one band per divider
    rows = _bands_from_dividers(y0, y1, ys)
    # symbol cell own bands
    half = (cells[0][0] + cells[0][1]) / 2.0
    sym_ys = [y for y, sp in zip(ys, (spans[i] for i in order))
              if sp is None or sp[0] <= half]
    return {"cells": cells, "rows": rows, "unboxed": unboxed,
            "frame": (x0, y0, x1, y1), "cells_alt": cells_alt,
            "sym_rows": _bands_from_dividers(y0, y1, sym_ys)}


def merge_fit(lines):
    from .scanlib import _fit_ok
    used = set()
    for i, L in enumerate(lines):
        if i in used:
            continue
        tl = _ltext(L).strip()
        m = _FIT_LINE.match(tl)
        if not m or not _fit_ok(m.group(1).replace(" ", "")):
            continue
        # radius (R10) and metric thread (M10) pass _fit_ok as deviation
        # letters but are own callouts, would fuse a neighbour number
        if _RADIUS_RE.match(tl) or _re.match(r"M\s?\d", tl):
            continue
        rl = _lrect(L)
        h = max(rl[3] - rl[1], 2.0)
        best = None
        for j, M in enumerate(lines):
            if j == i or j in used:
                continue
            tm = _ltext(M)
            if not _re.search(r"(?:^|\s)\u00d8?\s*\d+(?:[.,]\d+)?\s*$",
                              tm):
                continue
            rm = _lrect(M)
            vgap = max(rm[1] - rl[3], rl[1] - rm[3], 0.0)
            if vgap > 1.5 * h:
                continue
            xgap = max(rm[0] - rl[2], rl[0] - rm[2], 0.0)
            if xgap > 4 * h:
                continue
            score = vgap + xgap
            if best is None or score < best[0]:
                best = (score, j)
        if best is not None:
            M = lines[best[1]]
            M["toks"].append({"t": _ltext(L).replace(" ", ""), "r": rl})
            used.add(i)
    return [l for i, l in enumerate(lines) if i not in used]


def merge_nx(lines):
    used = set()
    for i, L in enumerate(lines):
        if i in used or not _NX_LINE.match(_ltext(L)):
            continue
        rl = _lrect(L)
        h = max(rl[3] - rl[1], 2.0)
        best = None
        for j, M in enumerate(lines):
            if j == i or j in used:
                continue
            tm = _ltext(M)
            starts_num = bool(_re.match(r"^[.\d\u00d8]", tm))
            if not starts_num:
                continue
            rm = _lrect(M)
            vgap = max(rm[1] - rl[3], rl[1] - rm[3], 0.0)
            if vgap > 1.5 * h:
                continue
            xgap = max(rm[0] - rl[2], rl[0] - rm[2], 0.0)
            if xgap > 4 * h:
                continue
            score = vgap + xgap
            if best is None or score < best[0]:
                best = (score, j)
        if best is not None:
            M = lines[best[1]]
            M["toks"].insert(0, {"t": _ltext(L), "r": rl})
            used.add(i)
    return [l for i, l in enumerate(lines) if i not in used]


def _line_string(line):
    parts = []
    cmap = []
    for i, t in enumerate(line["toks"]):
        if parts:
            parts.append(" ")
            cmap.append(i - 1)
        parts.append(t["t"])
        cmap.extend([i] * len(t["t"]))
    return "".join(parts), cmap


_BARE_NUM = _re.compile(r"^\d{1,5}(?:[.,]\d+)?$")


def _year_like(s):
    return _re.match(r"^(19|20)\d\d$", s) is not None


def parse_lines(lines, include_bare=False, cfg=None):
    out = []
    for cg, line in enumerate(lines):
        s, cmap = _line_string(line)
        spans = []
        claimed = set()
        for tp, sb, pat, ex in SCAN_PATS:
            if not mode_admits_tp(tp, cfg):
                continue
            for m in _re.finditer(pat, s, _re.I):
                res = ex(m)
                if res is None:
                    continue
                v, t = res
                if not v:
                    continue
                g = m.group(0)
                a = m.start() + (len(g) - len(g.lstrip()))
                e = m.end() - (len(g) - len(g.rstrip()))
                if any(not (e <= ps or a >= pe) for ps, pe in spans):
                    continue
                ti = sorted({cmap[k] for k in range(a, e)})
                rect = _union_all([line["toks"][k]["r"] for k in ti])
                spans.append((a, e))
                claimed.update(ti)
                hit = gdt_zone_check(
                    {"tp": tp, "sb": sb, "v": v, "t": t,
                     "raw": g.strip(), "rect": rect, "cg": cg})
                note = (hole_note(s)
                        if sb is None and tp in ("DIAMETER", "LINEAR")
                        else None)
                if tp == "DIAMETER":
                    if note == "thru":
                        hit["thru"] = True
                elif note:
                    hit["hole_note"] = note
                out.append(hit)
        if include_bare:
            for k, tok in enumerate(line["toks"]):
                if k in claimed:
                    continue
                txt = tok["t"]
                if txt == "0" or not _BARE_NUM.match(txt) \
                        or _year_like(txt):
                    continue
                out.append({"tp": "LINEAR", "sb": "BARE", "v": txt,
                            "t": None, "raw": txt, "rect": tok["r"],
                            "cg": cg})
    return out


def _rect_holds(r, x, y):
    """Rect encloses point"""
    return r is not None and r[0] <= x <= r[2] and r[1] <= y <= r[3]


def _rect_covers(outer, inner):
    """Outer rect wholly encloses inner transitively"""
    return (outer is not None and inner is not None
            and outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def _rect_mostly_in(a, b, frac=0.7):
    """Do a and b overlap over most of smaller one"""
    if a is None or b is None:
        return False
    ow = min(a[2], b[2]) - max(a[0], b[0])
    oh = min(a[3], b[3]) - max(a[1], b[1])
    if ow <= 0 or oh <= 0:
        return False
    small = min((a[2] - a[0]) * (a[3] - a[1]),
                (b[2] - b[0]) * (b[3] - b[1]))
    return small > 0 and (ow * oh) / small >= frac


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


def dedup_hits(hits, tol=8.0, score=None):
    """Drop repeated reads"""
    out, meta = [], []
    for h in hits:
        r = _hit_anchor(h)
        cx = (r[0] + r[2]) / 2.0 if r else None
        cy = (r[1] + r[3]) / 2.0 if r else None
        key = (h.get("tp"), h.get("sb"), str(h.get("v")), h.get("t"))
        dup = False
        at = None
        for i, (k2, r2, x2, y2) in enumerate(meta):
            if k2 != key:
                continue
            if cx is None or x2 is None:
                continue          # no geometry to merge
            # containment plus centre distance
            if (abs(cx - x2) <= tol and abs(cy - y2) <= tol) or \
                    _rect_covers(r2, r) or _rect_covers(r, r2) or \
                    _rect_mostly_in(r2, r):
                dup = True
                at = i
                break
        if not dup:
            at = _composite_absorbs(out, h)
            dup = at is not None
        if dup:
            lose = h                      # copy being discarded
            if score is not None and score(h) > score(out[at]):
                out[at], lose = h, out[at]
                meta[at] = (key, r, cx, cy)
            for k in _KEEP_ON_MERGE:      # facts key omits
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
    return out


def _composite_absorbs(kept, h):
    """Index of kept composite holding hit as segment"""
    if h.get("fcf_composite"):
        return None
    r = _hit_anchor(h)
    if r is None:
        return None
    for i, k in enumerate(kept):
        if not k.get("fcf_composite"):
            continue
        # match segment row band
        for b in (k.get("fcf_seg_rects") or ()):
            if _rect_covers(b, r) or _rect_mostly_in(b, r):
                return i
    return None


def scan_words(words, include_bare=False, cfg=None):
    if not words:
        return []
    lines = lines_from_words(words)
    lines = _split_lines_on_gaps(lines)
    for line in lines:
        _normalize_line(line)
    lines = [l for l in lines if l["toks"]]
    lines = merge_stacked(lines)
    lines = merge_halfstack(lines)
    lines = merge_callout_block(lines)
    lines = merge_fit(lines)
    lines = merge_nx(lines)
    return dedup_hits(parse_lines(lines, include_bare=include_bare, cfg=cfg))


def scan_page_positions(page, cfg=None):
    return scan_words(page_words(page), cfg=cfg)


_CONT_KW_RE = _re.compile(
    r"\b(?:THRU|DEEP|DEPTH|C'?BORE|CBORE|CSINK|SPOTFACE|SFACE)\b", _re.I)
_RADIUS_RE = _re.compile(r"^R\s?\d", _re.I)    # R12 dim not fit


def _is_continuation(text, max_toks=4):
    """True if line modifies callout above"""
    t = text.strip()
    if not t:
        return False
    if _DEV_LINE.match(t) or _NX_LINE.match(t):
        return True
    if _FIT_LINE.match(t) and not _RADIUS_RE.match(t):
        return True
    if len(t.split()) <= max_toks and _CONT_KW_RE.search(t):
        return True
    return False


def sections_from_words(words, cfg=None):
    """Cluster words into callout sections"""
    cfg = cfg or {}
    vgap_k = float(cfg.get("vision_section_vgap", 1.6))
    hpad_k = float(cfg.get("vision_section_hpad", 0.5))
    lines = _split_lines_on_gaps(lines_from_words(words))
    lines = [l for l in lines if _ltext(l).strip()]
    order = sorted(range(len(lines)),
                   key=lambda i: (_lrect(lines[i])[1], _lrect(lines[i])[0]))
    sections = []
    for i in order:
        li = lines[i]
        ri = _lrect(li)
        h = max(ri[3] - ri[1], 2.0)
        best = None
        if _is_continuation(_ltext(li)):
            for s in sections:
                sr = s["rect"]
                if min(ri[2], sr[2]) - max(ri[0], sr[0]) <= -hpad_k * h:
                    continue
                vgap = ri[1] - sr[3]
                if vgap < -h or vgap > vgap_k * h:
                    continue
                if best is None or vgap < best[0]:
                    best = (vgap, s)
        if best is not None:
            s = best[1]
            s["lines"].append(li)
            s["rect"] = _union(s["rect"], ri)
        else:
            sections.append({"lines": [li], "rect": ri})
    out = [{"rect": s["rect"], "lines": s["lines"], "n": len(s["lines"])}
           for s in sections]
    out.sort(key=lambda s: (s["rect"][1], s["rect"][0]))
    return out


def page_sections(page, cfg=None):
    """Page-wide callout sections"""
    return sections_from_words(page_words(page), cfg)


def grow_box_stack(brect, words, vgap_k=1.0, hpad_k=0.3, max_grow=4.0):
    """Grow box to absorb lines stacked above/below"""
    x0, y0, x1, y1 = brect
    bh0 = max(y1 - y0, 2.0)
    lines = _split_lines_on_gaps(lines_from_words(words))
    rects = [_lrect(l) for l in lines if _ltext(l).strip()]
    changed = True
    while changed:
        changed = False
        h = max(y1 - y0, 2.0)
        for r in rects:
            if min(x1, r[2]) - max(x0, r[0]) <= -hpad_k * h:
                continue
            if r[3] < y0 - vgap_k * h or r[1] > y1 + vgap_k * h:
                continue
            nx0, ny0 = min(x0, r[0]), min(y0, r[1])
            nx1, ny1 = max(x1, r[2]), max(y1, r[3])
            if (nx0, ny0, nx1, ny1) == (x0, y0, x1, y1):
                continue
            if ny1 - ny0 > max_grow * bh0:
                continue
            x0, y0, x1, y1 = nx0, ny0, nx1, ny1
            changed = True
    return (x0, y0, x1, y1)


def expand_to_section(brect, sections, max_grow=6.0):
    """Grow box to most-overlapped section"""
    bh = max(brect[3] - brect[1], 2.0)
    best = None
    for s in sections:
        sr = s["rect"]
        ox = min(brect[2], sr[2]) - max(brect[0], sr[0])
        oy = min(brect[3], sr[3]) - max(brect[1], sr[1])
        if ox <= 0 or oy <= 0:
            continue
        inter = ox * oy
        if best is None or inter > best[0]:
            best = (inter, sr)
    if best is None:
        return brect
    sr = best[1]
    grown = (min(brect[0], sr[0]), min(brect[1], sr[1]),
             max(brect[2], sr[2]), max(brect[3], sr[3]))
    if grown[3] - grown[1] > max_grow * bh:
        return brect
    return grown


def _main(argv):
    import fitz
    from .scanlib import scan_normalize, scan_parse
    if len(argv) < 2:
        print("usage: python -m bubbler.scanpos drawing.pdf")
        return 1
    doc = fitz.open(argv[1])
    for pg in range(doc.page_count):
        page = doc[pg]
        old = scan_parse(scan_normalize(page.get_text("text") or ""))
        new = scan_page_positions(page)

        def keyset(hits):
            return sorted("%s:%s" % (h["tp"], h["v"]) for h in hits)

        ko, kn = keyset(old), keyset(new)
        print("page %d: old %d hits, new %d hits (all anchored)"
              % (pg + 1, len(old), len(new)))
        miss = [k for k in ko if k not in kn]
        gain = [k for k in kn if k not in ko]
        if miss:
            print("  old-only (check!):", ", ".join(miss))
        if gain:
            print("  new-only:", ", ".join(gain))
        for h in new:
            r = h["rect"]
            print("  %-9s %-24s tol=%-12s @ (%.0f,%.0f)"
                  % (h["tp"], h["v"], h.get("t") or "",
                     (r[0] + r[2]) / 2, (r[1] + r[3]) / 2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv))
