# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Title-block label->value parser. Pure logic, displayed coords. No app state.

import re

LABEL_MAP = {
    "PART NO": "B3", "PART NUMBER": "B3", "PART": "B3", "PN": "B3",
    "PART NAME": "E3", "NAME": "E3", "NAZWA": "E3",
    "FAIR": "H3", "FAIR NO": "H3",
    "DWG": "B4", "DWG NO": "B4", "DRAWING": "B4", "DRAWING NO": "B4",
    "DRAWING NUMBER": "B4", "RYSUNEK": "B4", "RYS": "B4",
    "REV": "E4", "REVISION": "E4", "DWG REV": "E4",
    "PART REV": "H4",
    "PO": "B5", "PO NO": "B5", "PO NUMBER": "B5",
    "MATERIAL": "E5", "MATERIAŁ": "E5", "MAT": "E5", "MATL": "E5",
    "SERIAL": "H5", "LOT": "H5", "SERIAL LOT": "H5", "PARTIA": "H5",
    "INSPECTOR": "B6", "KONTROLER": "B6",
    "DATE": "E6", "DATA": "E6",
}

_IGNORE = {"SCALE", "SKALA", "SHEET", "ARKUSZ", "TITLE", "TYTUŁ"}


def _norm(s):
    s = re.sub(r"[.:#]+$", "", str(s).strip())
    s = re.sub(r"[^0-9A-Za-zĄĆĘŁŃÓŚŻŹąćęłńóśżź /]", "", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def _match_label(tokens):
    """Longest known label (1-3 tokens) starting here -> (cell, span) or None."""
    for span in (3, 2, 1):
        if span > len(tokens):
            continue
        key = _norm(" ".join(tokens[:span]))
        if key in _IGNORE:
            return ("", span)
        if key in LABEL_MAP:
            return (LABEL_MAP[key], span)
    return None


def parse_titleblock(words):
    """Word tuples (x0,y0,x1,y1,text,...) displayed coords -> {cell: value}; value right of label else row below, unmatched omitted."""
    ws = [w for w in words if str(w[4]).strip()]
    n = len(ws)
    label_idx = set()
    matches = []
    i = 0
    while i < n:
        toks = [str(ws[j][4]) for j in range(i, min(i + 3, n))]
        hit = _match_label(toks)
        if hit is None:
            i += 1
            continue
        cell, span = hit
        for j in range(i, i + span):
            label_idx.add(j)
        if cell:
            matches.append((cell, i, i + span - 1))
        i += span

    out = {}
    for cell, a, b in matches:
        if cell in out:
            continue
        lx0 = min(ws[k][0] for k in range(a, b + 1))
        lx1 = max(ws[k][2] for k in range(a, b + 1))
        ly0 = min(ws[k][1] for k in range(a, b + 1))
        ly1 = max(ws[k][3] for k in range(a, b + 1))
        lyc, lh = (ly0 + ly1) / 2.0, max(1.0, ly1 - ly0)
        val = _value_right(ws, label_idx, lx1, lyc, lh) or \
            _value_below(ws, label_idx, lx0, lx1, ly1)
        if val:
            out[cell] = val
    return out


def _value_right(ws, label_idx, lx1, lyc, lh):
    band = [(k, w) for k, w in enumerate(ws)
            if w[0] >= lx1 - 1
            and abs((w[1] + w[3]) / 2.0 - lyc) <= lh * 0.7]
    band.sort(key=lambda kw: kw[1][0])
    parts = []
    for k, w in band:
        if k in label_idx:
            break
        t = str(w[4]).strip()
        if t:
            parts.append(t)
    return " ".join(parts).strip() or None


def _value_below(ws, label_idx, lx0, lx1, ly1):
    cand = [(k, w) for k, w in enumerate(ws)
            if k not in label_idx and w[1] >= ly1 - 1
            and not (w[2] < lx0 or w[0] > lx1)]
    if not cand:
        return None
    cand.sort(key=lambda kw: kw[1][1])
    y0 = cand[0][1][1]
    row = [w for _, w in cand if abs(w[1] - y0) <= 3]
    row.sort(key=lambda w: w[0])
    return " ".join(str(w[4]).strip() for w in row).strip() or None
