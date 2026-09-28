# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# ISO 13715 edge conditions: drawn mark and values.

import re


def _edge_hits(brect, block_words):
    """`edge_condition` box -> one EDGE hit or None."""
    from bubbler.reader.grammar import edge_from_values
    got = edge_from_values([str(w[4]) for w in block_words or ()])
    if got is None:
        return None
    v, t = got
    return [{"tp": "EDGE", "sb": None, "v": v, "t": t, "raw": v,
             "rect": tuple(brect), "cg": 0}]


_SIGNED_WORD = re.compile(r"^[+\-\u00b1]\s*\d+(?:[.,]\d+)?$")


def _page_lines(page):
    got = getattr(page, "_bubbler_lines", None)
    if got is not None:
        return got
    out = []
    try:
        for d in page.get_drawings():
            for it in d.get("items", ()):
                if it and it[0] == "l":
                    a, b = it[1], it[2]
                    out.append((float(a.x), float(a.y), float(b.x),
                                float(b.y)))
    except Exception:
        out = []
    try:
        page._bubbler_lines = out
    except Exception:
        pass
    return out


def _edge_mark(page, pr):
    """Drawn L under pair. Found even where detector missed box."""
    h = max(pr[3] - pr[1], 1.0)
    tol = max(2.0, 0.15 * h)
    segs = _page_lines(page)
    for x0, y0, x1, y1 in segs:
        if abs(x0 - x1) > 0.5 or abs(x0 - pr[0]) > tol:
            continue
        top, bot = min(y0, y1), max(y0, y1)
        if bot - top < 0.3 * h or top < pr[1] - tol or bot > pr[3] + tol:
            continue
        for a0, b0, a1, b1 in segs:
            if abs(b0 - b1) > 0.5 or abs(b0 - bot) > tol:
                continue
            left, right = min(a0, a1), max(a0, a1)
            if abs(left - x0) <= tol and right - left >= 0.3 * h:
                return True
    return False


def _pair_words(h, r, words):
    """Closest-stacked pair, so covered second pair stays out."""
    toks = [t.replace(" ", "") for t in str(h.get("t") or "").split("/")]
    if len(toks) != 2:
        return None
    cand = [[w for w in words or ()
             if str(w[4]).replace(" ", "") == tok
             and _SIGNED_WORD.match(str(w[4]).strip())
             and r[0] <= (w[0] + w[2]) / 2.0 <= r[2]
             and r[1] <= (w[1] + w[3]) / 2.0 <= r[3]] for tok in toks]
    best = None
    for a in cand[0]:
        for b in cand[1]:
            if a is b:
                continue
            d = (abs((a[0] + a[2]) - (b[0] + b[2]))
                 + abs((a[1] + a[3]) - (b[1] + b[3])))
            if best is None or d < best[0]:
                best = (d, [a, b])
    return best[1] if best else None


def _edge_marks_split(page, words, legacy):
    """Edge-mark pair is own EDGE row, never size's tolerance."""
    from bubbler.reader.grammar import edge_from_values
    if page is None or not hasattr(page, "get_drawings"):
        return legacy
    out, extra = [], []
    for h in legacy:
        r = h.get("rect")
        if not r or "/" not in str(h.get("t") or ""):
            out.append(h)
            continue
        pair = _pair_words(h, r, words)
        if pair is None:
            out.append(h)
            continue
        pr = (min(w[0] for w in pair), min(w[1] for w in pair),
              max(w[2] for w in pair), max(w[3] for w in pair))
        if not _edge_mark(page, pr):
            out.append(h)
            continue
        got = edge_from_values([str(w[4]) for w in pair])
        if got is not None:
            extra.append({"tp": "EDGE", "sb": None, "v": got[0],
                          "t": got[1], "raw": got[0], "rect": pr,
                          "cg": int(h.get("cg") or 0)})
    # unjoined pair still edge callout
    signed = [w for w in words or () if _SIGNED_WORD.match(str(w[4]).strip())]
    for i, a in enumerate(signed):
        for b in signed[i + 1:]:
            ha = max(a[3] - a[1], 1.0)
            over = min(a[2], b[2]) - max(a[0], b[0])
            if over < 0.5 * min(a[2] - a[0], b[2] - b[0]):
                continue
            if max(b[1] - a[3], a[1] - b[3]) > 0.5 * ha:
                continue
            pr = (min(a[0], b[0]), min(a[1], b[1]),
                  max(a[2], b[2]), max(a[3], b[3]))
            if any(e["rect"][0] <= (pr[0] + pr[2]) / 2.0 <= e["rect"][2]
                   and e["rect"][1] <= (pr[1] + pr[3]) / 2.0 <= e["rect"][3]
                   for e in extra):
                continue
            if not _edge_mark(page, pr):
                continue
            top, bot = (a, b) if a[1] <= b[1] else (b, a)
            got = edge_from_values([str(top[4]), str(bot[4])])
            if got is not None:
                extra.append({"tp": "EDGE", "sb": None, "v": got[0],
                              "t": got[1], "raw": got[0], "rect": pr,
                              "cg": 50000 + len(extra)})
    return out + extra


_GENTOL_KW = re.compile(r"2768|22081|ALLGEMEIN|TOLERAN|GENERAL|OG[ÓO]LN|"
                        r"UNLESS|NIETOLEROWAN", re.I)
