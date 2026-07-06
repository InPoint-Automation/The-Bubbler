# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Position-aware scan. Word boxes -> anchored hits.

import re as _re

from .scanlib import SCAN_PATS, _GDT_SYMBOLS
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

# ISO hole-callout marks -> keyword.
_SYMBOLS = {
    "\u2334": "CBORE", "\u2294": "CBORE",
    "\u2335": "CSINK", "\u2228": "CSINK", "\u22c1": "CSINK",
    "\u21a7": "DEEP", "\u2913": "DEEP", "\u25bd": "DEEP",
    "\u25bf": "DEEP", "\u25bc": "DEEP", "\u2207": "DEEP",
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


def _norm_token(s):
    for a, b in _GLYPHS.items():
        s = s.replace(a, b)
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
            if (c is not None and b == "." and
                    _re.match(r"^\d+$", a) and _re.match(r"^\d", c)):
                merge_run(i, i + 2, a + "." + c)
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
        return None
    if not paths:
        return None
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
    xs, ys = [], []
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
            elif dx >= 0.5 * w and dy <= tol:
                cy = (sy0 + sy1) / 2.0
                if y0 - tol <= cy <= y1 + tol:
                    ys.append(cy)
    inx = _cluster(sorted(x for x in xs if x0 + tol < x < x1 - tol), tol)
    iny = _cluster(sorted(y for y in ys if y0 + tol < y < y1 - tol), tol)
    return inx, iny


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
    dark = a < (a.max() * 0.5 if a.max() else 0.5)
    hgt, wid = dark.shape
    x0, y0, x1, y1 = rect
    gap = max(1, int(cfg.get("vision_fcf_proj_gap", 2)))
    col = dark.sum(axis=0).astype(float)
    row = dark.sum(axis=1).astype(float)
    frac = float(cfg.get("vision_fcf_divider_min", 0.6))
    xs = _profile_lines(col, hgt * frac, gap)
    ys = _profile_lines(row, wid * frac, gap)
    sx = (x1 - x0) / max(wid, 1)
    sy = (y1 - y0) / max(hgt, 1)
    inx = [x0 + c * sx for c in xs if 1 < c < wid - 1]
    iny = [y0 + r * sy for r in ys if 1 < r < hgt - 1]
    return inx, iny


def _profile_lines(prof, thresh, gap):
    idx = [i for i, v in enumerate(prof) if v >= thresh]
    if not idx:
        return []
    runs = [[idx[0]]]
    for i in idx[1:]:
        if i - runs[-1][-1] <= gap:
            runs[-1].append(i)
        else:
            runs.append([i])
    return [sum(r) / len(r) for r in runs]


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


def segment_fcf_cells(page, rect, cfg, crop=None):
    cfg = cfg or {}
    x0, y0, x1, y1 = rect
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    bands = None
    try:
        bands = _fcf_vector_bands(page, rect, cfg)
    except Exception:
        bands = None
    if bands is not None and not bands[0]:
        bands = None
    if bands is None:
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
            bands = _fcf_raster_bands(ink, rect, cfg)
        except Exception:
            return None
    if bands is None:
        return None
    xs, mids = bands
    cells = _bands_from_dividers(x0, x1, sorted(xs))
    if len(cells) < 2:
        return None
    if mids:
        my = sorted(mids)[len(mids) // 2]
        rows = [(y0, my), (my, y1)]
    else:
        rows = [(y0, y1)]
    return {"cells": cells, "rows": rows}


def merge_fit(lines):
    from .scanlib import _fit_ok
    used = set()
    for i, L in enumerate(lines):
        if i in used:
            continue
        m = _FIT_LINE.match(_ltext(L).strip())
        if not m or not _fit_ok(m.group(1).replace(" ", "")):
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
                hit = {"tp": tp, "sb": sb, "v": v, "t": t,
                       "raw": g.strip(), "rect": rect, "cg": cg}
                if tp == "DIAMETER" and sb is None and \
                        _re.search(r"\bTHRU\b", s, _re.I):
                    hit["thru"] = True
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


def dedup_hits(hits, tol=8.0):
    out, meta = [], []
    for h in hits:
        r = h.get("rect")
        cx = (r[0] + r[2]) / 2.0 if r else None
        cy = (r[1] + r[3]) / 2.0 if r else None
        key = (h.get("tp"), h.get("sb"), str(h.get("v")), h.get("t"))
        dup = False
        for k2, x2, y2 in meta:
            if k2 != key:
                continue
            if cx is None or x2 is None or \
                    (abs(cx - x2) <= tol and abs(cy - y2) <= tol):
                dup = True
                break
        if dup:
            continue
        out.append(h)
        meta.append((key, cx, cy))
    return out


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
