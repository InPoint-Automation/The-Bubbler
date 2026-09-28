# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Hole tables found from words and rulings.

import re


_TAG_HEAD = re.compile(r"^(TAG|ETIKETT|HOLE|LOCH|OTW(ÓR|OR)?|ID)$",
                       re.I)
_X_HEAD = re.compile(r"^(X|X-?POS(ITION)?|X-?LOC|X-?KOORD\.?)$", re.I)
_Y_HEAD = re.compile(r"^(Y|Y-?POS(ITION)?|Y-?LOC|Y-?KOORD\.?)$", re.I)
_SIZE_HEAD = re.compile(r"^(SIZE|GR(Ö|OE)SSE|DESCRIPTION|BESCHREIBUNG"
                        r"|DIA(METER)?|DURCHMESSER|ROZMIAR|WYMIAR|OPIS)$",
                        re.I)
# `A1`, `C12`, `AA3`, or row number
_TAG_CELL = re.compile(r"^([A-Z]{1,2}\d{1,3}|\d{1,3})$")
_NUM = re.compile(r"^[+\-−]?\d+(?:[.,]\d+)?$")


def _cx(w):
    return (w[0] + w[2]) / 2.0


def _cy(w):
    return (w[1] + w[3]) / 2.0


def _header(words, tag):
    """Header line through tag heading: kind and x-extent per column."""
    h = max(tag[3] - tag[1], 1.0)
    line = sorted((w for w in words
                   if abs(_cy(w) - _cy(tag)) <= 0.6 * h
                   and w[0] >= tag[0] - 1 and w[0] - tag[2] < 60 * h),
                  key=lambda w: w[0])
    cols = []
    head = []
    for w in line:
        t = str(w[4]).strip()
        kind = ("tag" if _TAG_HEAD.match(t) else "x" if _X_HEAD.match(t)
                else "y" if _Y_HEAD.match(t) else "size"
                if _SIZE_HEAD.match(t) else None)
        if kind is not None:
            head.append(w)
        if kind is None:
            if cols and t.upper() in ("LOC", "POS", "POSITION", "KOORD"):
                cols[-1][1] = max(cols[-1][1], w[2])
            continue
        if cols and cols[-1][2] == kind:
            continue
        if kind == "tag" and cols:
            # next table's heading ends this one
            return cols, (tag[1], max(x[3] for x in head[:-1])), w[0]
        cols.append([w[0], w[2], kind])
    # header bottom from headings only
    return cols, (tag[1], max(x[3] for x in head)), None


def _bounds(cols, lines, top, bot, stop=None):
    """Column x-ranges from rulings, else midpoints."""
    # ruling must cross header middle
    mid = (top + bot) / 2.0
    verts = sorted({round(min(x0, x1), 1) for x0, y0, x1, y1 in lines
                    if abs(x0 - x1) < 0.5 and min(y0, y1) <= mid
                    and max(y0, y1) >= mid})
    out = []
    for i, (x0, x1, kind) in enumerate(cols):
        left = out[-1][1] if out else None
        if left is None:
            cand = [v for v in verts if v <= x0]
            left = cand[-1] if cand else x0 - 0.5 * (x1 - x0)
        if i + 1 < len(cols):
            nx = cols[i + 1][0]
            cand = [v for v in verts if x1 <= v <= nx]
            right = cand[0] if cand else (x1 + nx) / 2.0
        else:
            cand = [v for v in verts if v >= x1]
            right = cand[0] if cand else x1 + 4 * (x1 - x0)
            if stop is not None:
                right = min(right, stop - 1)
        out.append((left, right, kind))
    return out


def _cells(col, words, lines, top, bot):
    x0, x1 = col
    ys = sorted({round(y0, 1) for lx0, y0, lx1, y1 in lines
                 if abs(y0 - y1) < 0.5 and top < y0 < bot
                 and min(lx0, lx1) <= x0 + 0.2 * (x1 - x0)
                 and max(lx0, lx1) >= x1 - 0.2 * (x1 - x0)})
    edges = [top] + ys + [bot]
    cells = []
    for a, b in zip(edges, edges[1:]):
        ws = [w for w in words if x0 - 1 <= w[0] and w[2] <= x1 + 1
              and a <= _cy(w) <= b]
        cells.append((a, b, ws))
    return cells, bool(ys)


def find_tables(words, lines=()):
    """Every hole table: `rect` plus `rows` of tag, band, x, y, size."""
    words = [w for w in words if str(w[4]).strip()]
    tables = []
    for tag in words:
        if not _TAG_HEAD.match(str(tag[4]).strip()):
            continue
        cols, (htop, hbot), stop = _header(words, tag)
        kinds = [c[2] for c in cols]
        if kinds[:1] != ["tag"] or not ({"x", "size"} & set(kinds)):
            continue
        spans = _bounds(cols, lines, htop, hbot, stop)
        tcol = spans[0]
        h = max(tag[3] - tag[1], 1.0)
        cand = sorted((w for w in words if tcol[0] <= _cx(w) <= tcol[1]
                       and w[1] >= hbot - 0.2 * h), key=_cy)
        tags = []
        for w in cand:
            t = str(w[4]).strip()
            if re.fullmatch(r"[A-Z]", t):
                continue      # border zone letter
            if not _TAG_CELL.match(t):
                break
            # run ends only at real gap
            if tags and _cy(w) - _cy(tags[-1]) > 6 * max(
                    w[3] - w[1], tags[-1][3] - tags[-1][1]):
                break
            tags.append(w)
        if len(tags) < 2:
            continue
        pitch = sorted(_cy(b) - _cy(a) for a, b in zip(tags, tags[1:]))
        step = pitch[len(pitch) // 2]
        bot = _cy(tags[-1]) + 0.6 * step
        wid = spans[-1][1] - spans[0][0]
        rules = [y0 for x0, y0, x1, y1 in lines
                 if abs(y0 - y1) < 0.5 and y0 > _cy(tags[-1])
                 and min(x0, x1) <= spans[0][0] + 0.2 * wid
                 and max(x0, x1) >= spans[-1][1] - 0.2 * wid]
        # close ruling is bottom, beats pitch
        if rules and min(rules) - _cy(tags[-1]) < 1.5 * step:
            bot = min(rules)
        rows = []
        for i, t in enumerate(tags):
            y0 = hbot if i == 0 else (_cy(tags[i - 1]) + _cy(t)) / 2.0
            y1 = bot if i + 1 == len(tags) else (_cy(t) + _cy(tags[i + 1])) \
                / 2.0
            rows.append({"tag": str(t[4]).strip(), "tag_word": t,
                         "band": (spans[0][0], y0, spans[-1][1], y1),
                         "x": [], "y": [], "size": []})
        for left, right, kind in spans[1:]:
            if kind in ("x", "y"):
                for r in rows:
                    r[kind] = [w for w in words if left <= _cx(w) <= right
                               and r["band"][1] <= _cy(w) <= r["band"][3]
                               and _NUM.match(str(w[4]).strip())]
            elif kind == "size":
                cells, ruled = _cells((left, right), words, lines, hbot, bot)
                for r in rows:
                    mid = (r["band"][1] + r["band"][3]) / 2.0
                    if ruled:
                        own = [c for c in cells if c[0] <= mid <= c[1]]
                        r["size"] = own[0][2] if own else []
                    else:
                        r["size"] = [w for w in words
                                     if left - 1 <= w[0] and w[2] <= right + 1
                                     and r["band"][1] <= _cy(w)
                                     <= r["band"][3]]
        rect = (spans[0][0], htop, spans[-1][1], bot)
        if any(abs(rect[1] - t["rect"][1]) < 1 and abs(rect[0] - t["rect"][0])
               < 1 for t in tables):
            continue
        tables.append({"rect": rect, "rows": rows, "spans": spans,
                       "kinds": [s[2] for s in spans]})
    return tables
