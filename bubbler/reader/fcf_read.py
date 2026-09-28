# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# FCF cells -> GD&T hits.

import collections
import re
from bubbler.reader import dedup  # noqa: E402


def _fcf_glyph_count(text):
    from bubbler.reader.grammar import _GDT_SYMBOLS
    return len({g for g, _kw in _GDT_SYMBOLS if g in (text or "")})


def _fcf_symbol_kw(text):
    from bubbler.reader.grammar import _GDT_SYMBOLS
    for glyph, kw in _GDT_SYMBOLS:
        if glyph in text:
            return kw.split()
    return None


def _fcf_cell_of(word, cells):
    cx = (word[0] + word[2]) / 2.0
    for i, (lo, hi) in enumerate(cells):
        if lo <= cx <= hi:
            return i
    return None


def _fcf_row_of(word, rows):
    cy = (word[1] + word[3]) / 2.0
    for i, (lo, hi) in enumerate(rows):
        if lo <= cy <= hi:
            return i
    return 0 if cy < rows[0][0] else len(rows) - 1


def _fcf_row_rect(brect, row):
    return (brect[0], max(brect[1], row[0]), brect[2], min(brect[3], row[1]))


def _fcf_symbol_for(words):
    return _fcf_symbol_kw(" ".join(str(w[4]) for w in words))


def _fcf_band_of(row, bands):
    cy = (row[0] + row[1]) / 2.0
    for lo, hi in bands:
        if lo <= cy <= hi:
            return (lo, hi)
    return row


def _fcf_glyph_for(sb):
    from bubbler.reader.grammar import _GDT_SYMBOLS
    name = (sb or "").upper().strip()
    if name == "TOTAL RUNOUT":
        name = "RUNOUT"                      # bare = total runout
    if name:
        for glyph, kw in _GDT_SYMBOLS:
            if name == kw.strip():
                return glyph
        for glyph, kw in _GDT_SYMBOLS:
            if name in kw.strip():
                return glyph
    return "⌖"


def _fcf_flag(h, code):
    from bubbler.reader.grammar import gdt_flag
    gdt_flag(h, code)


def _fcf_bands(rows, sym_rows):
    """[(symbol band, [row indexes])]. Band over >1 row is composite."""
    out = []
    for ri in range(len(rows)):
        band = _fcf_band_of(rows[ri], sym_rows)
        if out and out[-1][0] == band:
            out[-1][1].append(ri)
        else:
            out.append((band, [ri]))
    return out


def _fcf_row_words(per_cell, ci, rows, ri):
    return [w for r, w in per_cell[ci] if r == ri or len(rows) == 1]


def _fcf_takes_datums(sb):
    from bubbler.reader.grammar import _GDT_MAX_DATUMS
    return _GDT_MAX_DATUMS.get(sb, 3) > 0


def _fcf_fix_zone(h, want):
    """Zone marker follows frame over pattern guess."""
    t = h.get("t") or ""
    v = h.get("v") or ""
    if want and (want + t) not in v:
        h["v"] = v.replace("Ø" + t, t, 1).replace(" " + t, " " + want + t, 1)
    elif not want and "Ø" in v:
        h["v"] = v.replace("SØ" + t, t, 1).replace("Ø" + t, t, 1)


def _fcf_apply_mods(h, parts):
    mods = parts.get("mods") or []
    if not mods:
        return
    disp = " ".join(mods)
    head, sep, tail = (h.get("v") or "").partition(" | ")
    fed = mods[0][0] if mods[0][0] in "MLSP" else None
    at = re.search(r"(?<= )" + fed + r"(?= |$)", head) if fed else None
    if at is not None:
        if disp != fed:
            head = head[:at.start()] + disp + head[at.end():]
    else:
        # before zone (print order)
        zone = parts.get("zone") or ""
        if zone and head.rstrip().endswith(zone):
            head = head.rstrip()[:-len(zone)].rstrip() + " " + disp + " " + zone
        else:
            head = head.rstrip() + " " + disp
    h["v"] = head + sep + tail


# family name collapses subtypes. Read glyph refines.
_FCF_CHAR_FULL = ("PROFILE OF A LINE", "PROFILE OF A SURFACE",
                  "CIRCULAR RUNOUT", "TOTAL RUNOUT")


def _fcf_refine_char(h, sym):
    name = " ".join(sym or ()).upper().strip()
    if name == "RUNOUT":
        name = "TOTAL RUNOUT"                # bare = total runout
    if name not in _FCF_CHAR_FULL:
        return
    h["fcf_char"] = name
    sb = h.get("sb") or ""
    v = h.get("v") or ""
    if sb and v.startswith(sb + " "):
        h["v"] = name + v[len(sb):]


def _fcf_compose(segs):
    """Composite frame -> ONE control (ASME Y14.5 / ISO 1101)."""
    h = segs[0]
    h["fcf_seg_rects"] = [x.get("arect") or x.get("rect") for x in segs]
    for s in segs[1:]:
        v = s.get("v") or ""
        sb = s.get("sb") or ""
        if sb and v.startswith(sb + " "):
            v = v[len(sb) + 1:]
        h["v"] = (h.get("v") or "") + " // REFINEMENT " + v
        for c in s.get("fcf_flags") or []:
            _fcf_flag(h, c)
        if s.get("fcf_zone_suspect"):
            h["fcf_zone_suspect"] = True
    h["fcf_composite"] = True
    _fcf_flag(h, "composite")
    return h


def _fcf_row_hit(page, cfg, sym, per_cell, cells, rows, ri, rrect, bi):
    from bubbler.reader import parse
    tol_words = list(_fcf_row_words(per_cell, 1, rows, ri))
    # zone token belongs to tol cell
    spill = {}
    for ci in range(2, len(cells)):
        ws = _fcf_row_words(per_cell, ci, rows, ri)
        z = [w for w in ws if str(w[4]).strip().upper() in _FCF_ZONE_TOKENS]
        tol_words.extend(z)
        spill[ci] = [w for w in ws if w not in z]
    parts = _fcf_tol_parts(tol_words)
    if not parts["tol"]:
        return []
    datum_txt = []
    datum_bad = False
    for ci in range(2, len(cells)):
        toks, bad = _fcf_datum_parse(spill[ci])
        datum_txt.extend(toks)
        datum_bad = datum_bad or bad
    mark = "SØ" if parts["tol"].startswith("SØ") else (
        "Ø" if parts["tol"].startswith("Ø") else "")
    # mirrors text reader
    from bubbler.reader.grammar import gdt_zone_wrong
    suspect = gdt_zone_wrong(" ".join(sym or ()), mark)
    toks = _fcf_line_tokens(sym, parts, datum_txt, rrect)
    if toks is None:
        return []
    line = {"key": (dedup._VBLOCK + bi, ri), "toks": toks}
    hits = [h for h in parse.parse_lines([line], cfg=cfg)
            if h.get("tp") == "GDT"]
    for h in hits:
        h["rect"] = rrect
        # arect = row for dedup anchor
        h["arect"] = _fcf_row_rect(rrect, rows[ri]) if ri < len(rows) \
            else rrect
        h["cg"] = dedup._VBLOCK + bi
        _fcf_fix_zone(h, mark)
        if suspect:
            h["fcf_zone_suspect"] = True     # flat zone read Ø
            _fcf_flag(h, "zone_suspect")
        if parts.get("bare_mod"):
            _fcf_flag(h, "bare_mod")
        _fcf_apply_mods(h, parts)
        _fcf_refine_char(h, sym)
        if datum_bad or (datum_txt and " | " not in h["v"]
                         and _fcf_takes_datums(h.get("sb"))):
            _fcf_flag(h, "datum_lost")       # datums read not emitted
            h["fcf_partial"] = True
    return hits


def _rect_holds_rect(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def _fcf_words_in(page, rect, have):
    """Re-read words inside FRAME to catch box-clipped."""
    from bubbler.reader import textlayer
    try:
        words = textlayer.page_words(page)
    except Exception:
        return have
    out = [w for w in words
           if rect[0] - 1 <= (w[0] + w[2]) / 2.0 <= rect[2] + 1
           and rect[1] - 1 <= (w[1] + w[3]) / 2.0 <= rect[3] + 1]
    return out or have


# Unread frames for debug overlay. Bounded.
_UNREAD = collections.deque(maxlen=200)


def unread_frames():
    return list(_UNREAD)


def clear_unread():
    _UNREAD.clear()


def _note_unread(rect, bi, words):
    _UNREAD.append({"rect": tuple(rect) if rect else None, "box": bi,
                    "text": " ".join(str(w[4]) for w in (words or ()))[:200]})


def _fcf_glyph_anchor(words):
    from bubbler.reader.grammar import _GDT_SYMBOLS
    glyphs = {g for g, _n in _GDT_SYMBOLS}
    for w in words or ():
        if str(w[4]).strip() in glyphs:
            return ((w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0,
                    max(w[3] - w[1], 2.0))
    return None


def _fcf_structural_hits(page, cfg, brect, block_words, bi):
    """Frame -> one hit per control, vector unless raster richer."""
    from bubbler.reader import fcf_geometry
    anchor = _fcf_glyph_anchor(block_words)
    seg = None
    try:
        seg = fcf_geometry.segment_fcf_cells(page, brect, cfg, anchor=anchor)
    except Exception:
        seg = None
    res = _fcf_seg_read(page, cfg, brect, block_words, bi, seg)
    if seg is None or _fcf_used_vector(seg):
        try:
            seg_r = fcf_geometry.segment_fcf_cells(
                page, brect, cfg, anchor=anchor, vector=False)
        except Exception:
            seg_r = None
        res_r = _fcf_seg_read(page, cfg, brect, block_words, bi, seg_r)
        if res_r is not None and _fcf_richer(
                res[0] if res else [], res_r[0]):
            res = res_r
    if res is None:
        return []
    out, dropped, seg, rrect, block_words = res
    # NX above frame = count
    n = _fcf_count_above(page, rrect)
    if n:
        for h in out:
            h.setdefault("qty", n)
    if dropped:
        for h in out:
            h["fcf_partial"] = True
            _fcf_flag(h, "partial")
        if not out:
            _note_unread(rrect, bi, block_words)
    if seg.get("unboxed"):
        # no drawn box = guessed cells (Y14.5)
        for h in out:
            h["fcf_unboxed"] = True
            # arms legacy text fallback
            h["fcf_partial"] = True
            _fcf_flag(h, "unboxed")
    return out


def _fcf_count_above(page, frame):
    import re
    from bubbler.reader import textlayer
    if page is None or not frame:
        return None
    try:
        words = textlayer.page_words(page)
    except Exception:
        return None
    x0, y0, x1, y1 = frame
    per_line = {}
    for w in words:
        if len(w) > 6:
            per_line[(w[5], w[6])] = per_line.get((w[5], w[6]), 0) + 1
    best = None
    for w in words:
        m = re.match(r"^(\d{1,3})[Xx\u00d7]$", str(w[4]).strip())
        if not m or int(m.group(1)) < 2:
            continue
        if len(w) > 6 and per_line.get((w[5], w[6]), 0) > 1:
            continue
        h = max(w[3] - w[1], 2.0)
        gap = y0 - w[3]
        if not (-0.25 * h <= gap <= 1.5 * h):
            continue
        if w[2] < x0 - h or w[0] > x0 + 0.5 * (x1 - x0):
            continue
        if best is None or gap < best[0]:
            best = (gap, int(m.group(1)))
    return best[1] if best else None


def _fcf_used_vector(seg):
    g = seg.get("geom") or {}
    return g.get("src") == "vector" or g.get("box") == "vector"


def _fcf_key(h):
    out = []
    for seg in str(h.get("v") or "").split("//"):
        parts = [p.strip() for p in seg.split("|")]
        out.append((parts[0], tuple(parts[1:])))
    return tuple(out)


def _fcf_covers(ka, kb):
    if len(kb) < len(ka):
        return False, False
    more = len(kb) > len(ka)
    for (h1, d1), (h2, d2) in zip(ka, kb):
        if h1 != h2 or d2[:len(d1)] != d1:
            return False, False
        more = more or len(d2) > len(d1)
    return True, more


def _fcf_richer(a, b):
    """Read b strict superset of a, set match."""
    if not b:
        return False
    if not a:
        return True
    ka = [_fcf_key(h) for h in a]
    kb = [_fcf_key(h) for h in b]
    if len(kb) < len(ka):
        return False

    def match(i, used, more):
        if i == len(ka):
            return more or len(kb) > len(ka)
        for j, k in enumerate(kb):
            if j in used:
                continue
            ok, m = _fcf_covers(ka[i], k)
            if ok and match(i + 1, used | {j}, more or m):
                return True
        return False
    return match(0, frozenset(), False)


def _fcf_seg_read(page, cfg, brect, block_words, bi, seg):
    from bubbler.reader import fcf_geometry
    if not seg:
        return None
    cells, rows = seg["cells"], seg["rows"]
    sym_rows = seg.get("sym_rows") or rows
    if len(cells) < 2:
        return None
    # re-collect words box clipped
    rrect = seg.get("frame") or brect
    if rrect is not brect and not _rect_holds_rect(brect, rrect):
        block_words = _fcf_words_in(page, rrect, block_words)
    def _read(cells):
        per_cell = [[] for _ in cells]
        for w in block_words:
            ci = _fcf_cell_of(w, cells)
            if ci is None:
                continue
            ri = _fcf_row_of(w, rows)
            per_cell[ci].append((ri, w))
        out = []
        dropped = False
        for band, ris in _fcf_bands(rows, sym_rows):
            # symbol spans rows read once
            sym_words = [w for _r, w in per_cell[0]
                         if band[0] <= (w[1] + w[3]) / 2.0 <= band[1]]
            sym = _fcf_symbol_for(sym_words)
            if not sym:                    # never borrow another row's
                dropped = True
                continue
            segs = []
            for ri in ris:
                hits = _fcf_row_hit(page, cfg, sym, per_cell, cells, rows, ri,
                                    rrect, bi)
                if not hits:
                    dropped = True
                    continue
                segs.extend(hits)
            if not segs:
                continue
            if len(ris) > 1 and _fcf_glyph_count(
                    " ".join(w[4] for w in sym_words)) > 1:
                # 2+ glyphs = 2+ controls
                segs = []
                for ri in ris:
                    rw = [w for _r, w in per_cell[0] if _r == ri]
                    rs = _fcf_symbol_for(rw)
                    hits = (_fcf_row_hit(page, cfg, rs, per_cell, cells,
                                         rows, ri, rrect, bi) if rs else [])
                    if not hits:
                        dropped = True
                    segs.extend(hits)
                out.extend(segs)
            elif len(ris) > 1:             # one glyph, composite
                comp = _fcf_compose(segs)
                out.append(comp)
                if len(segs) < len(ris):
                    dropped = True
            else:
                out.extend(segs)
        return out, dropped

    out, dropped = _read(cells)
    if (not out and not seg.get("cells_alt")
            and (seg.get("geom") or {}).get("src") == "vector"):
        try:
            seg2 = fcf_geometry.segment_fcf_cells(
                page, brect, cfg, anchor=_fcf_glyph_anchor(block_words),
                raster=True)
        except Exception:
            seg2 = None
        if seg2 and seg2.get("cells_alt"):
            seg = dict(seg, cells_alt=seg2["cells_alt"])
    # note-box divider fallback
    if not out and seg.get("cells_alt"):
        alt_out, alt_dropped = _read(seg["cells_alt"])
        if alt_out:
            out, dropped = alt_out, alt_dropped
    return out, dropped, seg, rrect, block_words


# ISO 14405/1101 zone qualifiers, match grammar
_FCF_ZONE_TOKENS = ("UZ", "CZ", "SZ", "OZ", "CT", "ACS", "ACL", "VA")


def _fcf_tol_parts(words):
    from bubbler.reader.tokens import norm_tokens
    from bubbler.reader.grammar import GDT_MOD_BARE, GDT_MOD_LETTERS, GDT_MOD_TAKES_NUM, _MOD_TXT
    # one normalization, after rejoin
    _parts = norm_tokens([str(w[4]) for w in words])
    txt = " ".join(_parts)
    # S before _MOD_TXT rewrites Ⓢ
    _tk = [p.upper() for p in _parts]
    sph = False
    for _j, _t in enumerate(_tk):
        if not re.search(r"\d", _t):
            continue
        # S Ø 0.1 splits 3 ways
        sph = _t.startswith("S\u00d8") or (
            _t.startswith("\u00d8") and _j and _tk[_j - 1] == "S") or (
            _j > 1 and _tk[_j - 1] == "\u00d8" and _tk[_j - 2] == "S") or (
            _j and _tk[_j - 1] == "S\u00d8")
        break
    # circled mods only, bare F/T/E common
    for a, b in _MOD_TXT.items():
        if len(a) == 1:
            txt = txt.replace(a, " \u0001" + b + " ")
    txt = re.sub(r"[()]", " ", txt).upper()
    txt = re.sub(r"\b(?:SEP\s*REQT|SEP|REQT|ST|CF|UF|NC)\b", " ", txt)
    out = {"tol": "", "mods": [], "zone": ""}
    m = re.search(r"((?:SØ|Ø)?\s*(?:\d+(?:\s*[.,]\s*\d+)?|[.,]\s*\d+)"
                  r"(?:\s*/\s*\d+(?:[.,]\d+)?"
                  r"(?:\s*[Xx×]\s*\d+(?:[.,]\d+)?)?)?)", txt)
    if not m:
        return out
    tol = re.sub(r"\s+", "", m.group(1))
    if sph and tol.startswith("Ø"):
        tol = "S" + tol
    out["tol"] = re.sub(r"^(S?Ø?)([.,])", r"\g<1>0\2", tol)  # .5 -> 0.5
    for mt in re.finditer(r"(\u0001?[A-Z]{1,3})"
                          r"\s*([+-]?\s*(?:\d+(?:[.,]\d+)?|[.,]\d+))?",
                          txt[m.end():]):
        tok = mt.group(1)
        circled = tok.startswith("\u0001")
        tok = tok.lstrip("\u0001")
        num = re.sub(r"\s+", "", mt.group(2) or "")
        if tok in _FCF_ZONE_TOKENS:
            if tok == "UZ" and not num[:1] in ("+", "-"):
                continue                   # UZ needs sign
            # printed order (ISO 1101:2017)
            one = tok + (num if tok == "UZ" else "")
            if one not in out["zone"].split():
                out["zone"] = (out["zone"] + " " + one).strip()
        elif tok in _MOD_TXT and len(tok) > 1:
            out["mods"].append(_MOD_TXT[tok])
        elif len(tok) == 1 and (tok in GDT_MOD_BARE if not circled
                                else tok in GDT_MOD_LETTERS):
            if num[:1] in (".", ","):
                num = "0" + num
            out["mods"].append(
                tok + (num if tok in GDT_MOD_TAKES_NUM else ""))
        elif (len(tok) == 1 and not circled
              and tok in GDT_MOD_LETTERS and tok not in GDT_MOD_BARE):
            out["bare_mod"] = True
    return out


def _fcf_tol_text(words):
    p = _fcf_tol_parts(words)
    if not p["tol"]:
        return ""
    return " ".join([p["tol"]] + p["mods"] + ([p["zone"]] if p["zone"] else []))


def _fcf_datum_parse(words):
    """(datum tokens, bad). One junk datum must not delete others."""
    from bubbler.reader.tokens import _norm_token
    from bubbler.reader.grammar import _MOD_TXT
    txt = " ".join(_norm_token(str(w[4])) for w in words)
    # keep print spelling per occurrence
    glyph = {}
    for a, b in _MOD_TXT.items():
        if len(a) == 1 and a in txt:
            key = "\x01%s\x02" % b
            glyph[key] = a
            txt = txt.replace(a, " (" + key + ") ")
    out = []
    used = []
    # datum keeps ONE modifier
    for mt in re.finditer(r"\b([A-Z](?:-[A-Z])+|[A-Z])\b"
                          r"(?:\s*(?:\(\s*(\x01?[MLSPFT]\x02?)\s*\)"
                          r"|([MLSP])\b))?"
                          r"(?:\s*\(\s*\x01?[MLSPFT]\x02?\s*\))*", txt):
        d = mt.group(1)
        mod = mt.group(2) or mt.group(3)
        if mod and mod in glyph:
            d += glyph[mod]                     # print drew circle
            mod = mod.strip("\x01\x02")
        elif mod in ("M", "L", "S", "P", "F", "T"):
            d += "(" + mod + ")"
        out.append(d)
        used.append((mt.start(), mt.end()))
    left = txt
    for a, b in reversed(used):
        left = left[:a] + left[b:]
    return out, bool(re.search(r"[A-Za-z0-9]", left))


def _fcf_datum_tokens(words):
    return _fcf_datum_parse(words)[0]


def _fcf_no_dia_zone(sym):
    from bubbler.reader.grammar import gdt_no_dia_zone
    return gdt_no_dia_zone(sym)


def _fcf_line_tokens(sym, parts, datum_txt, rrect):
    words = list(sym)
    tol = parts.get("tol") or ""
    if not tol:
        return None
    # drop Ø, restored downstream
    tol = tol[2:] if tol.startswith("SØ") else (
        tol[1:] if tol.startswith("Ø") else tol)
    words.append(tol)
    mods = parts.get("mods") or []
    if mods and mods[0][0] in "MLSP":
        words.append(mods[0][0])
    if parts.get("zone"):
        words.append(parts["zone"])
    words.extend(datum_txt)
    return [{"t": t, "r": tuple(rrect)} for t in words if t]


# evidence bands 1.0 apart, conf <= 0.4
_EV_READER = 3.0     # OCR/VLM/structural read
_EV_AGREE = 2.0      # block class admits
_EV_PLAIN = 1.0      # block has no opinion
_EV_TEXT = 0.5       # plain page text scan
_EV_CONFLICT = 0.0   # block class refuses
_EV_CONF_W = 0.4
