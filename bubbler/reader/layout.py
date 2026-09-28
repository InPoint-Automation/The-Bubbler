# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Page layout: reading order, sections, box growth.

import re as _re
from bubbler.reader import geometry, textlayer, textlines  # noqa: E402


_CONT_KW_RE = _re.compile(
    r"\b(?:THRU|DEEP|DEPTH|C'?BORE|CBORE|CSINK|SPOTFACE|SFACE)\b", _re.I)


def _is_continuation(text, max_toks=4):
    t = text.strip()
    if not t:
        return False
    if textlines._DEV_LINE.match(t) or textlines._NX_LINE.match(t):
        return True
    if textlines._FIT_LINE.match(t) and not textlines._RADIUS_RE.match(t):
        return True
    if len(t.split()) <= max_toks and _CONT_KW_RE.search(t):
        return True
    return False


def words_by_frame(words):
    by_q = {}
    for w in geometry.fill_dirs(words or ()):
        by_q.setdefault(geometry._dir_quarter(w), []).append(w)
    return [(q, [geometry._rect_map(geometry._to_frame, q, w) + tuple(w[4:8]) for w in ws])
            for q, ws in sorted(by_q.items())]


_OCR_BLOCK = 900000  # OCR/VLM word block base


def reading_order_lines(words):
    """OCR/VLM words by position in own frame, PDF words by own order."""
    words = list(words or ())
    # geometric only when ALL words OCR/VLM
    if not words or not all(int(w[5]) >= _OCR_BLOCK for w in words):
        lines, key = [], None
        for w in sorted(words, key=lambda w: (w[5], w[6], w[7])):
            if (w[5], w[6]) != key:
                lines.append([])
                key = (w[5], w[6])
            lines[-1].append(str(w[4]))
        return lines
    out = []
    for _q, fw in words_by_frame(words):
        fw.sort(key=lambda w: ((w[1] + w[3]) / 2.0, w[0]))
        rows = []
        for w in fw:
            cy, h = (w[1] + w[3]) / 2.0, max(w[3] - w[1], 1.0)
            if rows and abs(cy - rows[-1][0]) <= 0.5 * h:
                rows[-1][1].append(w)
            else:
                rows.append([cy, [w]])
        out += [[str(w[4]) for w in sorted(r[1], key=lambda w: w[0])]
                for r in rows]
    return out


def reading_order_first(hits, fb=None):
    """First in own text frame, not topmost."""
    def key(h):
        q = int(h.get("text_dir") or 0) // 90
        r = geometry._rect_map(geometry._to_frame, q, h.get("rect") or fb)
        return (r[1], r[0])
    return min(hits, key=key)


def sections_from_words(words, cfg=None):
    """Each direction in own frame. Sections carry quarter `q`."""
    out = []
    for q, fw in words_by_frame(words):
        for sec in _sections_level(fw, cfg):
            sec["rect"] = geometry._rect_map(geometry._from_frame, q, sec["rect"])
            for ln in sec["lines"]:
                for t in ln["toks"]:
                    if t.get("r") is not None:
                        t["r"] = geometry._rect_map(geometry._from_frame, q, t["r"])
            sec["q"] = q
            out.append(sec)
    out.sort(key=lambda s: (s["rect"][1], s["rect"][0]))
    return out


def _sections_level(words, cfg=None):
    cfg = cfg or {}
    vgap_k = float(cfg.get("vision_section_vgap", 1.6))
    hpad_k = float(cfg.get("vision_section_hpad", 0.5))
    lines = textlines._split_lines_on_gaps(textlines.lines_from_words(words))
    lines = [l for l in lines if textlines._ltext(l).strip()]
    order = sorted(range(len(lines)),
                   key=lambda i: (textlines._lrect(lines[i])[1], textlines._lrect(lines[i])[0]))
    sections = []
    for i in order:
        li = lines[i]
        ri = textlines._lrect(li)
        h = max(ri[3] - ri[1], 2.0)
        best = None
        if _is_continuation(textlines._ltext(li)):
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
            s["rect"] = geometry._union(s["rect"], ri)
        else:
            sections.append({"lines": [li], "rect": ri})
    out = [{"rect": s["rect"], "lines": s["lines"], "n": len(s["lines"])}
           for s in sections]
    out.sort(key=lambda s: (s["rect"][1], s["rect"][0]))
    return out


def page_sections(page, cfg=None):
    return sections_from_words(textlayer.page_words(page), cfg)


def _box_quarter(brect, words):
    """Majority reading direction inside box, 0 if none."""
    count = {}
    for w in geometry.fill_dirs(words or ()):
        cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
        if brect[0] <= cx <= brect[2] and brect[1] <= cy <= brect[3]:
            q = geometry._dir_quarter(w)
            count[q] = count.get(q, 0) + 1
    return max(count, key=count.get) if count else 0


def grow_box_stack(brect, words, vgap_k=1.0, hpad_k=0.3, max_grow=4.0):
    """In box's own text direction."""
    q = _box_quarter(brect, words)
    if q:
        fw = [f for qq, ws in words_by_frame(words) if qq == q for f in ws]
        grown = _grow_level(geometry._rect_map(geometry._to_frame, q, brect), fw, vgap_k,
                            hpad_k, max_grow)
        return geometry._rect_map(geometry._from_frame, q, grown)
    return _grow_level(brect, [w for w in geometry.fill_dirs(words or ())
                               if geometry._dir_quarter(w) == 0],
                       vgap_k, hpad_k, max_grow)


def _grow_level(brect, words, vgap_k, hpad_k, max_grow):
    x0, y0, x1, y1 = brect
    bh0 = max(y1 - y0, 2.0)
    lines = textlines._split_lines_on_gaps(textlines.lines_from_words(words))
    rects = [textlines._lrect(l) for l in lines if textlines._ltext(l).strip()]
    # reach fixed at one text line, else compounds
    inner = sorted(w[3] - w[1] for w in words
                   if str(w[4]).strip()
                   and x0 <= (w[0] + w[2]) / 2.0 <= x1
                   and y0 <= (w[1] + w[3]) / 2.0 <= y1)
    h = min(inner[len(inner) // 2], bh0) if inner else bh0
    h = max(h, 2.0)
    changed = True
    while changed:
        changed = False
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
    best = None
    for s in sections:
        sr = s["rect"]
        ox = min(brect[2], sr[2]) - max(brect[0], sr[0])
        oy = min(brect[3], sr[3]) - max(brect[1], sr[1])
        if ox <= 0 or oy <= 0:
            continue
        inter = ox * oy
        if best is None or inter > best[0]:
            best = (inter, sr, s.get("q", 0))
    if best is None:
        return brect
    sr = best[1]
    grown = (min(brect[0], sr[0]), min(brect[1], sr[1]),
             max(brect[2], sr[2]), max(brect[3], sr[3]))
    # cap across text, not display
    q = best[2]
    fb = geometry._rect_map(geometry._to_frame, q, brect)
    fg = geometry._rect_map(geometry._to_frame, q, grown)
    if fg[3] - fg[1] > max_grow * max(fb[3] - fb[1], 2.0):
        return brect
    return grown
