# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Hole callouts spanning several boxes.

import re
from bubbler.reader import dedup, edgemarks, geometry  # noqa: E402
from bubbler.reader.vision import symbols, vlm_read  # noqa: E402


def _hole_note_box(brect, words):
    """Notes block that is one hole note. Glyphs need injecting"""
    from bubbler.reader.grammar import scan_normalize
    ws = [w for w in words or () if str(w[4]).strip()
          and geometry._center_in(w, brect)]
    if not ws:
        return False
    h = min(w[3] - w[1] for w in ws)
    if brect[3] - brect[1] > 3.2 * max(h, 1.0):
        return False
    text = scan_normalize(" ".join(str(w[4]) for w in ws))
    return bool(vlm_read._HOLE_KW.search(text)) and bool(re.search(r"\d", text))


def _hole_table_hits(page, cfg, words, rect=None):
    """Hole tables -> one balloon group per row. Returns (hits, rects)"""
    from bubbler.reader import geometry, holetable, parse
    from bubbler import common
    lines = edgemarks._page_lines(page)
    try:
        if int(getattr(page, "rotation", 0) or 0) % 360:
            m = page.rotation_matrix
            lines = [geometry.xform_rect(m, *ln) for ln in lines]
    except Exception:
        pass
    tables = holetable.find_tables(words, lines)
    if rect is not None:
        tables = [t for t in tables if geometry._rects_overlap(t["rect"], rect)]
    if not tables:
        return [], []
    syms = symbols._symbol_dets(page, cfg) if cfg.get("vision_symbols", True) \
        else []
    out, cache = [], {}
    for ti, t in enumerate(tables):
        size = [sp for sp in t["spans"] if sp[2] == "size"]
        for ri, r in enumerate(t["rows"]):
            cg = dedup._TABLE_CG + ti * 1000 + ri
            b = r["band"]
            row = []
            for kind in ("x", "y"):
                if r[kind]:
                    ws = r[kind]
                    wr = (min(w[0] for w in ws), min(w[1] for w in ws),
                          max(w[2] for w in ws), max(w[3] for w in ws))
                    v = " ".join(str(w[4]) for w in ws)
                    row.append({"tp": "LINEAR", "sb": None, "v": v, "t": None,
                                "raw": v, "rect": wr, "arect": wr})
            key = tuple(id(w) for w in r["size"])
            if key and key not in cache:
                cw = list(r["size"])
                cr = (min(w[0] for w in cw), min(w[1] for w in cw),
                      max(w[2] for w in cw), max(w[3] for w in cw))
                have = symbols._block_glyphs(cw)
                cell = [st for st in syms if geometry._center_in(tuple(st[0][:4]), cr)]
                if cfg.get("vision_symbols", True):
                    # small glyphs, re-detect per cell
                    hgt = cr[3] - cr[1]
                    pad = (cr[0] - 2 * hgt, cr[1] - 0.5 * hgt,
                           cr[2] + hgt, cr[3] + 0.5 * hgt)
                    extra = [st for st in symbols._symbol_dets_clip(page, cfg, pad)
                             if geometry._center_in(tuple(st[0][:4]), pad)]
                    cell = symbols._dedup_syms(extra, cell)
                for env, tok in sorted(
                        cell, key=lambda st: st[1].strip() in symbols._KW_TOKENS):
                    if not common.admits("hole", tok) or \
                            symbols._glyph_present(tok, have) or \
                            symbols._on_text(env, cw, tok):
                        continue
                    symbols._attach_or_append(cw, env, tok)
                cache[key] = parse.scan_words(cw)
            sl = (size[0][0], b[1], size[0][1], b[3]) if size else b
            for h in cache.get(key, ()):
                row.append(dict(h, rect=sl, arect=sl))
            for h in row:
                h["cg"] = cg
                h["tag"] = r["tag"]
            out.extend(row)
    return out, [t["rect"] for t in tables]


_HOLE_FACET_TP = ("DIAMETER", "THREAD", "DEPTH", "FIT")


def _hole_facets(hs):
    out = set()
    for h in hs:
        v = str(h.get("v") or "").upper()
        if h["tp"] == "THREAD":
            out.add("thread")
        elif "CBORE" in v:
            out.add("cbore")
        elif "CSINK" in v:
            out.add("csink")
        elif h["tp"] in ("DIAMETER", "FIT"):
            out.add("drill")
    return out


def _join_block_holes(hits, words):
    """Drill-less hole-note group joins adjacent drill group."""
    by = {}
    for h in hits:
        if h.get("rect") is not None:
            by.setdefault(h.get("cg"), []).append(h)
    info = {}
    for cg, hs in by.items():
        if not all(h.get("tp") in _HOLE_FACET_TP for h in hs):
            continue
        bs = set()
        for h in hs:
            bs.update(w[5] for w in words or ()
                      if len(w) > 5 and geometry._center_in(w, h["rect"]))
        if len(bs) != 1:
            continue
        fac = _hole_facets(hs)
        if not fac:
            continue
        r = (min(h["rect"][0] for h in hs), min(h["rect"][1] for h in hs),
             max(h["rect"][2] for h in hs), max(h["rect"][3] for h in hs))
        lh = min(min(h["rect"][2] - h["rect"][0], h["rect"][3] - h["rect"][1])
                 for h in hs)
        info[cg] = (bs.pop(), fac, r, lh)
    gone = set()
    for c2, (b2, f2, r2, l2) in info.items():
        if "drill" in f2:
            continue
        best = None
        for c1, (b1, f1, r1, l1) in info.items():
            if c1 == c2 or c1 in gone or b1 != b2 or "drill" not in f1 \
                    or f1 & f2:
                continue
            gap = max(r1[0] - r2[2], r2[0] - r1[2], r1[1] - r2[3],
                      r2[1] - r1[3])
            if gap <= 1.5 * max(l1, l2) and (best is None or gap < best[0]):
                best = (gap, c1)
        if best is None:
            continue
        c1 = best[1]
        for h in by[c2]:
            h["cg"] = c1
        info[c1] = (info[c1][0], info[c1][1] | f2, info[c1][2], info[c1][3])
        gone.add(c2)


_SIZED_TP = ("RADIUS", "DIAMETER", "SLOT", "FIT", "THREAD")


def _join_trailing_depth(hits, words):
    """Lone depth joins sized feature left on baseline."""
    by = {}
    for h in hits:
        if h.get("rect") is not None:
            by.setdefault(h.get("cg"), []).append(h)

    def block(hs):
        bs = set()
        for h in hs:
            bs.update(w[5] for w in words or ()
                      if len(w) > 5 and geometry._center_in(w, h["rect"]))
        return bs

    for c2, hs2 in list(by.items()):
        if not all(h.get("tp") == "DEPTH" for h in hs2):
            continue
        b2 = block(hs2)
        r2 = hs2[0]["rect"]
        lh = r2[3] - r2[1]
        best = None
        for c1, hs1 in by.items():
            if c1 == c2 or any(h.get("tp") == "DEPTH" for h in hs1):
                continue
            for h in hs1:
                r1 = h["rect"]
                if h.get("tp") not in _SIZED_TP:
                    continue
                gap = r2[0] - r1[2]
                ov = min(r1[3], r2[3]) - max(r1[1], r2[1])
                if -0.2 * lh <= gap <= 1.5 * lh and \
                        ov >= 0.5 * min(lh, r1[3] - r1[1]) and \
                        b2 and b2 == block([h]) and \
                        (best is None or gap < best[0]):
                    best = (gap, c1)
        if best is None:
            continue
        for h in hs2:
            h["cg"] = best[1]
        by[best[1]].extend(hs2)
        by[c2] = []


_COUNT_X = ("x", "X", "\u00d7")
