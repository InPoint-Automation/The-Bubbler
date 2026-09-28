# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Parsing: flat-text and line readers.

import re as _re
from bubbler import scanrows  # noqa: E402
from bubbler.reader import dedup, geometry, grammar, textlayer, textlines, tokens  # noqa: E402


# hole note makes hole without Ø glyph
_HOLE_NOUN_RE =_re.compile(
    r"\b(?:HOLES?|BOHRUNG(?:EN)?|OTW\.?|OTW\u00d3R|OTWOR(?:Y|\u00d3W)?)\b",
    _re.I)


def hole_note(text):
    """-> 'thru' / 'hole' / None."""
    t = text or ""
    if _re.search(r"\bTHRU\b", t, _re.I):
        return "thru"
    return "hole" if _HOLE_NOUN_RE.search(t) else None


def scan_parse(text, cfg=None):
    out = []
    seen = set()
    spans = []
    at = []
    for tp, sb, pat, ex in grammar.SCAN_PATS:
        for m in _re.finditer(pat, text, _re.I | _re.M):
            res = ex(m)
            v, t = res[0], res[1]
            extra = res[2] if len(res) > 2 else ()
            if not v:
                continue
            g = m.group(0)
            s = m.start() + (len(g) - len(g.lstrip()))
            e = m.end() - (len(g) - len(g.rstrip()))
            if any(not (e <= ps or s >= pe) for ps, pe in spans):
                continue
            # chamfer `2X` is leg, not count
            keyv = v if tp == "CHAMFER" else _re.sub(
                r"^\d+[Xx\u00d7]\s*", "", v)
            key = ("%s:%s:%s" % (tp, keyv, t or "")).lower().replace(" ", "")
            # claim span first
            spans.append((s, e))
            parent = None
            if key not in seen:
                seen.add(key)
                at.append((s, e))
                parent = grammar.gdt_zone_check(
                    {"tp": tp, "sb": sb, "v": v, "t": t,
                     "raw": m.group(0).strip()})
                out.append(parent)
            # duplicate parent's extras still count
            for x in extra:
                xkey = ("%s:%s:%s" % (x["tp"], x["v"], x["t"] or "")
                        ).lower().replace(" ", "")
                if xkey not in seen:
                    seen.add(xkey)
                    at.append((s, e))
                    out.append(dict(x, raw=m.group(0).strip(),
                                    _extra_of=id(parent)))
    for h, (s, e) in zip(out, at):
        if h["sb"] is not None or h["tp"] not in ("DIAMETER", "LINEAR"):
            continue
        ls = text.rfind("\n", 0, s) + 1
        le = text.find("\n", e)
        le = len(text) if le < 0 else le
        note = hole_note(text[ls:le])
        if not note:
            continue
        if h["tp"] == "DIAMETER":
            if note == "thru":
                h["thru"] = True
        else:
            h["hole_note"] = note
    for h, (s, e) in zip(out, at):
        hit_qty(h, text, s)
    by_line = {}
    for h, (s, e) in zip(out, at):
        by_line.setdefault(text.count("\n", 0, s), []).append((h, s))
    for pairs in by_line.values():
        count_on_angle([h for h, _s in pairs], text, [s for _h, s in pairs])
    return _drop_extras(out)


def _drop_extras(hits):
    """Minus extras whose parent became same row."""
    out = []
    for h in hits:
        if h.pop("_drop", False):
            continue
        h.pop("_extra_of", None)
        out.append(h)
    return out


# `2X 45°` beside sized callout is count
_COUNT_ANGLE = _re.compile(r"^(\d{1,2})X(\d+(?:\.\d+)?)\u00b0$")
_SIZED = ("DIAMETER", "LINEAR", "FIT")


def count_on_angle(line_hits, text, starts):
    """Angle re-read off LINE, not chamfer span. In place."""
    if not any(h["tp"] in _SIZED and h.get("sb") != "BARE"
               for h in line_hits):
        return
    for h, at in zip(line_hits, starts):
        if h["tp"] != "CHAMFER" or h.get("t"):
            continue
        m = _COUNT_ANGLE.match(str(h.get("v") or ""))
        if not m or int(m.group(1)) < 2:
            continue
        lead = _re.match(r"\s*\d{1,2}\s*[Xx\u00d7]\s*", text[at:])
        rest = text[at + (lead.end() if lead else 0):]
        v, t = m.group(2) + "\u00b0", None
        for tp, _sb, pat, ex in grammar.SCAN_PATS:
            if tp != "ANGLE":
                continue
            am = _re.match(pat, rest, _re.I)
            if am:
                got = ex(am)
                if got and got[0]:
                    v, t = got
                break
        h["tp"] = "ANGLE"
        h["v"], h["t"] = v, t
        h["qty"] = int(m.group(1))
        for x in line_hits:
            if x.get("_extra_of") == id(h):
                x["_drop"] = True


# glued place-count opening line, both readers
_QTY_BEFORE = _re.compile(r"^\s*(\d{1,3})[Xx\u00d7]\s*$")
# spaced count, hole features only
_QTY_BEFORE_SPACED = _re.compile(r"^\s*(\d{1,3})\s+[Xx\u00d7]\s*$")
_QTY_SPACED_TP = ("DIAMETER", "THREAD", "DEPTH", "FIT")


def qty_before(text, start, tp=None):
    """Spaced `N x` only before hole. 1 is no count."""
    ls = text.rfind("\n", 0, start) + 1
    m = _QTY_BEFORE.search(text[ls:start])
    if not m and tp in _QTY_SPACED_TP:
        m = _QTY_BEFORE_SPACED.search(text[ls:start])
    if not m or int(m.group(1)) < 2:
        return None, None
    return int(m.group(1)), ls + m.start(1)


def hit_qty(h, text, start):
    n = scanrows.repeat_count(h.get("v"))
    if n < 2:
        n = qty_before(text, start, h.get("tp"))[0] or 1
    if n > 1:
        h["qty"] = n


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


_REF_NOUNS = frozenset((
    "TABLE", "TAB", "TABELLE", "TAFEL", "TABELA", "TABLICA", "SHEET",
    "BLATT", "ARKUSZ", "PAGE", "SEITE", "STRONA", "FIG", "FIGURE", "BILD",
    "ABB", "RYS", "ITEM", "POS", "POZ", "NOTE", "HINWEIS", "UWAGA",
    "REV", "INDEX"))


def _year_like(s):
    return _re.match(r"^(19|20)\d\d$", s) is not None


_VALUE_TP = ("LINEAR", "ANGLE")


def split_value_groups(hits, next_cg):
    """Separate values split. Returns next free group."""
    by = {}
    for h in hits:
        by.setdefault(h.get("cg"), []).append(h)
    for hs in by.values():
        vals = [h for h in hs if h.get("tp") in _VALUE_TP]
        for h in vals[1:]:
            h["cg"] = next_cg
            next_cg += 1
    return next_cg


def parse_lines(lines, include_bare=False, cfg=None):
    out = []
    for cg, line in enumerate(lines):
        s, cmap = _line_string(line)
        spans = []
        claimed = set()
        first = len(out)
        starts = []
        for tp, sb, pat, ex in grammar.SCAN_PATS:
            for m in _re.finditer(pat, s, _re.I):
                res = ex(m)
                if res is None:
                    continue
                v, t = res[0], res[1]
                extra = res[2] if len(res) > 2 else ()
                if not v:
                    continue
                g = m.group(0)
                a = m.start() + (len(g) - len(g.lstrip()))
                e = m.end() - (len(g) - len(g.rstrip()))
                if any(not (e <= ps or a >= pe) for ps, pe in spans):
                    continue
                ti = sorted({cmap[k] for k in range(a, e)})
                rect = geometry._union_all([line["toks"][k]["r"] for k in ti])
                spans.append((a, e))
                claimed.update(ti)
                hit = grammar.gdt_zone_check(
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
                hit_qty(hit, s, a)
                q, qa = qty_before(s, a, tp)
                if q:
                    claimed.update(cmap[k] for k in range(qa, a)
                                   if k < len(cmap))
                out.append(hit)
                starts.append(a)
                for x in extra:
                    xh = dict(x, raw=g.strip(), rect=rect, cg=cg,
                              _extra_of=id(hit))
                    hit_qty(xh, s, a)
                    out.append(xh)
                    starts.append(a)
        count_on_angle(out[first:], s, starts)
        out[first:] = _drop_extras(out[first:])
        if include_bare:
            for k, tok in enumerate(line["toks"]):
                if k in claimed:
                    continue
                txt = tok["t"]
                # all-zero number no size
                if not _BARE_NUM.match(txt) or not txt.strip("0.,") \
                        or _year_like(txt):
                    continue
                nxt = line["toks"][k + 1]["t"] if k + 1 < len(line["toks"]) \
                    else ""
                if nxt in ("X", "x", "\u00d7"):
                    continue  # count, not size
                prv = line["toks"][k - 1]["t"] if k else ""
                if nxt.startswith(":") or prv.endswith(":"):
                    continue  # view scale ratio
                if prv.rstrip(".").upper() in _REF_NOUNS:
                    continue  # reference
                bare = {"tp": "LINEAR", "sb": "BARE", "v": txt,
                        "t": None, "raw": txt, "rect": tok["r"], "cg": cg}
                if k == 1:
                    cm = _re.match(r"^(\d{1,3})[Xx\u00d7]$", prv)
                    if cm and int(cm.group(1)) > 1:
                        bare["qty"] = int(cm.group(1))
                out.append(bare)
    split_value_groups(out, len(lines))
    return out


def scan_words(words, include_bare=False, cfg=None):
    if not words:
        return []
    by_q = {}
    for w in geometry.fill_dirs(words):
        deg = geometry._diag_angle(w)
        key = ("d", deg) if deg is not None else geometry._dir_quarter(w)
        by_q.setdefault(key, []).append(w)
    if list(by_q) == [0]:
        return dedup.dedup_hits(_scan_frame(words, include_bare, cfg))
    out = []
    diag_n = 0
    for key, ws in sorted(by_q.items(), key=lambda kv: str(kv[0])):
        if isinstance(key, tuple):
            deg = key[1]
            fw = [geometry._diag_box(w, deg) + tuple(w[4:8]) for w in ws]
            back = lambda r, deg=deg: geometry._diag_back(r, deg)       # noqa: E731
            diag_n += 1
            off, tdir = 100000 * (3 + diag_n), deg
        else:
            q = key
            fw = [geometry._rect_map(geometry._to_frame, q, w) + tuple(w[4:8]) for w in ws]
            back = lambda r, q=q: geometry._rect_map(geometry._from_frame, q, r)  # noqa: E731
            off, tdir = 100000 * q, q * 90
        hits = _scan_frame(fw, include_bare, cfg)
        for h in hits:
            for k in ("rect", "arect"):
                if h.get(k) is not None:
                    h[k] = back(h[k])
            if h.get("cg") is not None:
                h["cg"] = int(h["cg"]) + off
            if tdir:
                h["text_dir"] = tdir
        out.extend(hits)
    return dedup.dedup_hits(out)


def _gdt_led(ln):
    t = textlines._ltext(ln).lstrip()
    return bool(t) and any(t.startswith(g) for g, _n in grammar._GDT_SYMBOLS)


# size glyph set alone, taller font
_LONE_PREFIX = ("\u00d8", "\u2300", "\u2205", "\u2334", "\u2335", "\u21a7")


def _join_split_lines(lines, gap_k=0.6, band_k=0.8, size_k=0.8, cell_k=2.0,
                      glyph_size_k=0.6):
    """Rejoin one printed line PDF split in two."""
    out = []
    for ln in lines:
        r = textlines._lrect(ln)
        h = max(r[3] - r[1], 1.0)
        for o in out:
            if o["key"][0] != ln["key"][0]:
                continue
            ro = textlines._lrect(o)
            ho = max(ro[3] - ro[1], 1.0)
            left = o if ro[0] <= r[0] else ln
            frame = _gdt_led(left)
            glyph = frame or textlines._ltext(left).strip() in _LONE_PREFIX
            if min(h, ho) < (glyph_size_k if glyph else size_k) * max(h, ho):
                continue  # stacked tol smaller
            band = min(r[3], ro[3]) - max(r[1], ro[1])
            if band < band_k * min(h, ho):
                continue
            gap = max(r[0] - ro[2], ro[0] - r[2])
            if gap > (cell_k if frame else gap_k) * min(h, ho):
                continue
            o["toks"] = sorted(o["toks"] + ln["toks"], key=lambda t: t["r"][0])
            break
        else:
            out.append(ln)
    return out


def _scan_frame(words, include_bare=False, cfg=None):
    lines = _join_split_lines(textlines.lines_from_words(words))
    lines = textlines._split_lines_on_gaps(lines)
    for line in lines:
        tokens._normalize_line(line)
    lines = [l for l in lines if l["toks"]]
    lines = textlines.merge_stacked(lines)
    lines = textlines.merge_halfstack(lines)
    lines = textlines.merge_pm_stack(lines)
    lines = textlines.merge_callout_block(lines)
    lines = textlines.merge_fit(lines)
    lines = textlines.merge_nx(lines)
    return parse_lines(lines, include_bare=include_bare, cfg=cfg)


def scan_page_positions(page, cfg=None):
    return scan_words(textlayer.page_words(page), cfg=cfg)
