# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# PDF text layer as words, glyphs repaired.

import re as _re
from bubbler.reader import geometry  # noqa: E402


# symbol fonts, goldens-proved glyphs only
FONT_GLYPHS = {
    "AIGDT": {"B": "\u00b1", "P": "\u00d8", "n": "\u00d8", "E": "\u23e5",
              "D": "\u27c2", "H": "\u2225", "K": "\u232f", "L": "\u2316",
              "T": "\u25ce",
              "Z": "\u21a7", "X": "\u2334"},
    "TAHOMA": {"\x83": "\u00b0", "\x91": "\u00d8"},
}

# lone-span glyphs, ISOCPEUR subsets
SPAN_GLYPHS = {"ISOCPEUR": {"n": "\u00b0", "o": "\u00b1",
                            "\u00d9": "\u2264"}}


# raw glyph ids, ASCII is code + 29
_GID_EXTRA = {"\x83": "\u00b0", "\x91": "\u00d8"}


def _is_gid_span(text):
    return any(3 <= ord(c) <= 0x1F for c in str(text or ""))


def _gid_char(c):
    o = ord(c)
    if 3 <= o <= 97:
        return chr(o + 29)
    return _GID_EXTRA.get(c, c)


def _font_key(name):
    """`ABCDEF+AIGDT` / `Tahoma,Bold` -> table key, or None."""
    base = str(name or "").split("+")[-1].split(",")[0].upper()
    for k in FONT_GLYPHS:
        if base.startswith(k):
            return k
    return None


def _span_glyph(sp):
    base = str(sp.get("font") or "").split("+")[-1].split(",")[0].upper()
    text = str(sp.get("text") if "text" in sp else "".join(
        c["c"] for c in sp.get("chars", ()))).strip()
    return SPAN_GLYPHS.get(base, {}).get(text)


def _glyph_fixes(page, blocks):
    """{(block, line): [(char, cx, cy, fixed)]}, {} if no symbol font."""
    if not any(_font_key(sp.get("font")) or _is_gid_span(sp.get("text"))
               or _span_glyph(sp)
               for b in blocks if b.get("type", 0) == 0
               for ln in b.get("lines", ()) for sp in ln.get("spans", ())):
        return {}
    try:
        raw = page.get_text("rawdict").get("blocks", [])
    except Exception:
        return {}
    out, bi = {}, 0
    for b in raw:
        if b.get("type", 0) != 0:
            continue
        for li, ln in enumerate(b.get("lines", ())):
            chars = []
            for sp in ln.get("spans", ()):
                table = FONT_GLYPHS.get(_font_key(sp.get("font")), {})
                raw_text = "".join(c["c"] for c in sp.get("chars", ()))
                gid = _is_gid_span(raw_text)
                lone = _span_glyph(sp)
                for c in sp.get("chars", ()):
                    x0, y0, x1, y1 = c["bbox"]
                    fixed = _gid_char(c["c"]) if gid else lone if lone and \
                        not c["c"].isspace() else table.get(c["c"], c["c"])
                    chars.append((c["c"], (x0 + x1) / 2.0, (y0 + y1) / 2.0,
                                  fixed))
            out[(bi, li)] = chars
        bi += 1
    return out


def _repair_word(w, fixes):
    """Word text with glyphs fixed, only on exact rebuild."""
    chars = fixes.get((w[5], w[6]))
    if not chars:
        return w[4]
    mine = [c for c in chars if w[0] - 0.5 <= c[1] <= w[2] + 0.5
            and w[1] - 0.5 <= c[2] <= w[3] + 0.5 and not c[0].isspace()]
    if "".join(c[0] for c in mine) != str(w[4]):
        return w[4]
    return "".join(c[3] for c in mine)


def _line_dirs(page):
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:
        return {}
    page._bubbler_blocks = blocks       # reused by glyph repair
    out, bi = {}, 0
    for b in blocks:
        if b.get("type", 0) != 0:
            continue
        for li, ln in enumerate(b.get("lines", ())):
            d = ln.get("dir")
            if d:
                # font size, diagonal box lies
                size = max((float(sp.get("size") or 0.0)
                            for sp in ln.get("spans", ())), default=0.0)
                out[(bi, li)] = (float(d[0]), float(d[1]), size)
        bi += 1
    return out


def page_words(page):
    """Display-space words, 9th field `(dx, dy)` direction."""
    try:
        words = page.get_text("words")
    except Exception:
        return []
    dirs = _line_dirs(page)
    fixes = _glyph_fixes(page, getattr(page, "_bubbler_blocks", ()))
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    m = None
    if rot:
        try:
            m = page.rotation_matrix
        except Exception:
            m = None
    out = []
    for w in words:
        d = dirs.get((w[5], w[6]))
        rect = tuple(w[:4])
        if m is not None:
            rect = geometry.xform_rect(m, w[0], w[1], w[2], w[3])
            if d is not None:
                d = (d[0] * m.a + d[1] * m.c, d[0] * m.b + d[1] * m.d) \
                    + tuple(d[2:])
        text = _repair_word(w, fixes) if fixes else w[4]
        out.append(rect + (text,) + tuple(w[5:8])
                   + ((d,) if d is not None else ()))
    return _glue_drawn_pm(out, _drawn_pm_marks(page, m))


_PM_NUM = _re.compile(r"^\d*[.,]?\d+$")


def _drawn_pm_marks(page, m=None):
    """Vector-drawn `±` marks, centres and sizes display space."""
    try:
        draws = page.get_drawings()
    except Exception:
        return []
    out = []
    for dr in draws:
        its = dr.get("items") or ()
        r = dr.get("rect")
        if len(its) != 3 or r is None or max(r.width, r.height) > 20 \
                or max(r.width, r.height) < 2:
            continue
        if any(it[0] != "l" for it in its):
            continue
        segs = [(it[1], it[2]) for it in its]
        hz = [q for q in segs if abs(q[0].y - q[1].y) < 0.05
              * max(abs(q[0].x - q[1].x), 0.1)]
        vt = [q for q in segs if abs(q[0].x - q[1].x) < 0.05
              * max(abs(q[0].y - q[1].y), 0.1)]
        for par, per in ((hz, vt), (vt, hz)):
            if len(par) != 2 or len(per) != 1:
                continue
            ln = [abs(a.x - b.x) + abs(a.y - b.y) for a, b in par]
            lp = abs(per[0][0].x - per[0][1].x) + \
                abs(per[0][0].y - per[0][1].y)
            if min(ln) < 0.8 * max(ln) or not 0.7 * ln[0] <= lp <= 1.3 * ln[0]:
                continue
            pc = ((per[0][0].x + per[0][1].x) / 2,
                  (per[0][0].y + per[0][1].y) / 2)
            if not any(abs((a.x + b.x) / 2 - pc[0]) + abs((a.y + b.y) / 2
                                                          - pc[1])
                       < 0.15 * ln[0] for a, b in par):
                continue      # stroke must cross bar
            x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
            if m is not None:
                x0, y0, x1, y1 = geometry.xform_rect(m, x0, y0, x1, y1)
            out.append((x0, y0, x1, y1))
            break
    return out


def _glue_drawn_pm(words, marks):
    if not marks:
        return words
    out = list(words)
    for mk in marks:
        mc = ((mk[0] + mk[2]) / 2, (mk[1] + mk[3]) / 2)
        best = None
        for i, w in enumerate(out):
            t = str(w[4])
            if not _PM_NUM.match(t):
                continue
            d = w[8][:2] if len(w) > 8 and w[8] else (1.0, 0.0)
            h = min(w[2] - w[0], w[3] - w[1])
            wc = ((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
            along = (wc[0] - mc[0]) * d[0] + (wc[1] - mc[1]) * d[1]
            cross = abs(-(wc[0] - mc[0]) * d[1] + (wc[1] - mc[1]) * d[0])
            gap = max(w[0] - mk[2], mk[0] - w[2], w[1] - mk[3], mk[1] - w[3])
            if along > 0 and cross <= 0.6 * h and gap <= 0.8 * h and \
                    (best is None or along < best[0]):
                best = (along, i)
        if best is not None:
            w = out[best[1]]
            out[best[1]] = tuple(w[:4]) + ("\u00b1" + str(w[4]),) \
                + tuple(w[5:])
    return out


_ZONE_TOK = _re.compile(r"^(?:[A-Z]|\d{1,2})$")


def border_labels(words, page_w, page_h, band=0.06):
    """Frame zone labels: 3+ single chars, evenly spaced, on sheet edge."""
    out = []
    for axis in (0, 1):
        lim = page_h if axis == 0 else page_w
        cand = []
        for w in words:
            if not _ZONE_TOK.match(str(w[4]).strip()):
                continue
            lo, hi = (w[1], w[3]) if axis == 0 else (w[0], w[2])
            if hi < band * lim or lo > (1 - band) * lim:
                cand.append(w)
        def mid(w):
            return (w[1] + w[3]) / 2.0 if axis == 0 else (w[0] + w[2]) / 2.0
        rows = []
        for w in sorted(cand, key=mid):
            if rows and mid(w) - mid(rows[-1][-1]) <= 4.0:
                rows[-1].append(w)
            else:
                rows.append([w])
        along = page_w if axis == 0 else page_h
        for row in rows:
            if len(row) < 3:
                continue
            row.sort(key=lambda w: (w[0] + w[2]) / 2.0 if axis == 0
                     else (w[1] + w[3]) / 2.0)
            pos = [(w[0] + w[2]) / 2.0 if axis == 0
                   else (w[1] + w[3]) / 2.0 for w in row]
            gaps = [b - a for a, b in zip(pos, pos[1:])]
            # zones: wide, even, in sequence
            if min(gaps) < 0.06 * along or min(gaps) < 0.6 * max(gaps):
                continue
            if _in_sequence([str(w[4]).strip() for w in row]):
                out += [tuple(w[:4]) for w in row]
    return out


def _in_sequence(toks):
    try:
        vals = [int(t) if t.isdigit() else ord(t) for t in toks]
    except (TypeError, ValueError):
        return False
    steps = {b - a for a, b in zip(vals, vals[1:])}
    return steps in ({1}, {-1})

