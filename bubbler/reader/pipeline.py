# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Page or rect -> hits. Start here.

import re as _re
from bubbler.reader import dedup, edgemarks, fcf_read, geometry, grammar, holes, union  # noqa: E402
from bubbler.reader.vision import ocr_read, regions, render, runtime, symbols, vlm_read  # noqa: E402


def augment_words(page, words, cfg):
    """Words plus enabled vision passes. Never raises."""
    cfg = cfg or {}
    if not cfg.get("vision_assist"):
        return words
    out = list(words)
    try:
        out = symbols._geometry_symbols(page, out, cfg)
    except Exception as e:                              # pragma: no cover
        runtime._warn("geometry pass failed: %s" % e)
    text_is_sparse = _sparse(out)
    try:
        if cfg.get("vision_ocr", True) and (text_is_sparse or
                                            cfg.get("vision_ocr_always")):
            out += ocr_read._ocr_words(page, cfg)
    except Exception as e:                              # pragma: no cover
        runtime._warn("ocr pass failed: %s" % e)
    try:
        if cfg.get("vision_symbols", True):
            out = symbols._symbol_words(page, out, cfg)
    except Exception as e:                              # pragma: no cover
        runtime._warn("symbol pass failed: %s" % e)
    return out


def _sparse(words, threshold=4):
    return sum(1 for w in words if str(w[4]).strip()) < threshold


def _assign_words(words, rects, quads=None, min_frac=geometry._WORD_MIN_FRAC):
    """Each word in at most one block."""
    out = [[] for _ in rects]
    for wi, w in enumerate(words):
        best = None
        for ri, r in enumerate(rects):
            q = quads[ri] if quads else None
            f = geometry._overlap_frac(w, r, q)
            if f <= 0.0:
                continue
            if f < min_frac and not geometry._center_in(w, r, q):
                continue
            # near-full in two: smaller wins
            fq = 1.0 if f >= geometry._WORD_FULL_FRAC else f
            rank = (fq, -abs((r[2] - r[0]) * (r[3] - r[1])), -ri)
            if best is None or rank > best[0]:
                best = (rank, ri)
        if best is not None:
            out[best[1]].append(wi)
    return out

_ADMIT_GLYPHS = None


def _admit_glyphs():
    global _ADMIT_GLYPHS
    if _ADMIT_GLYPHS is None:
        from bubbler import common
        out = set()
        for allow in common.ADMIT.values():
            if allow:
                out |= set(allow)
        _ADMIT_GLYPHS = frozenset(out)
    return _ADMIT_GLYPHS


def _hit_glyph(h):
    """Domain glyph read means. None = nothing to check against."""
    tp = h.get("tp")
    if tp == "GDT":
        return fcf_read._fcf_glyph_for(h.get("fcf_char") or h.get("sb"))
    if tp == "SURFACE":
        return "Ra"
    v = (h.get("v") or "").strip()
    # place count is no glyph
    v = _re.sub(r"^\d+\s*[Xx\u00d7]\s*", "", v)
    return v[:1] if v[:1] in _admit_glyphs() else None


def _text_layer_suffices(in_block, has_text, constraint, cfg):
    if len(has_text) >= 2:
        return True
    if not has_text:
        return False
    from bubbler import common
    from bubbler.reader import parse
    for h in parse.scan_words(in_block, include_bare=True, cfg=cfg):
        g = _hit_glyph(h)
        if (g is None or not _has_opinion(constraint)
                or common.admits(constraint, g)):
            return True
    return False


def _has_opinion(constraint):
    """Empty set is an opinion, None is not."""
    from bubbler import common
    return common.ADMIT.get(constraint) is not None


def _claimed_elsewhere(env, tok, blocks, k):
    from bubbler import common
    r = (env[0], env[1], env[2], env[3])
    mine = blocks[k][2]
    for j, blk in enumerate(blocks):
        if j == k:
            continue
        o = blk[2]
        if (o[0] <= mine[0] and o[1] <= mine[1]
                and o[2] >= mine[2] and o[3] >= mine[3]):
            # container is no neighbour
            continue
        cat = blk[4]
        if (common.admits(cat[2] if cat else None, tok)
                and geometry._center_in(r, blk[2], blk[5])):
            return True
    return False


def _lead_phi_of(env, tok, brect, blocks, k):
    """Oriented box clips its leading Ø."""
    if tok.strip() != "\u00d8":
        return False
    if (min(env[2], brect[2]) <= max(env[0], brect[0])
            or min(env[3], brect[3]) <= max(env[1], brect[1])):
        return False
    r = (env[0], env[1], env[2], env[3])
    return not any(geometry._center_in(r, blk[2], blk[5])
                   for j, blk in enumerate(blocks) if j != k)


def _class_contradicted(constraint, block_syms):
    from bubbler import common
    if not _has_opinion(constraint):
        return False
    return any(not common.admits(constraint, tok) for _env, tok in block_syms)


def _region_evidence(h, region_cls, conf=0.0, reader="text", structural=False):
    from bubbler import common
    try:
        c = min(1.0, max(0.0, float(conf)))
    except (TypeError, ValueError):
        c = 0.0
    if structural or reader in ("ocr", "vlm"):
        return fcf_read._EV_READER + fcf_read._EV_CONF_W * c
    cat = common.CATEGORY.get(region_cls)
    constraint = cat[2] if cat else None
    # empty set neutral here
    if not common.ADMIT.get(constraint):
        return fcf_read._EV_PLAIN + fcf_read._EV_CONF_W * c
    g = _hit_glyph(h)
    if g is None:
        return fcf_read._EV_PLAIN + fcf_read._EV_CONF_W * c
    band = fcf_read._EV_AGREE if common.admits(constraint, g) else fcf_read._EV_CONFLICT
    return band + fcf_read._EV_CONF_W * c


def _evidence(h):
    """Corroboration score. Plain text read is baseline."""
    try:
        return float(h.get("_ev", fcf_read._EV_TEXT))
    except (TypeError, ValueError):                     # pragma: no cover
        return fcf_read._EV_TEXT


def _strip_ev(hits):
    for h in hits or ():
        h.pop("_ev", None)
    return hits


def _region_regex_hits(page, cfg, rect=None, include_bare=False, words=None,
                       allow_vlm=False, on_slow=None, skip=()):
    """None defers to legacy. `skip` = hole tables."""
    if runtime._region_session(cfg) is None:
        return None
    boxes = regions._region_boxes(page, cfg)
    if rect is not None:
        boxes = [b for b in boxes if geometry._rects_overlap(b[:4], rect)]
    if skip:
        boxes = [b for b in boxes if not union._center_in_any(b[:4], skip)]
    if not boxes:
        return None
    from bubbler.reader import dedup, layout, parse, textlayer
    if words is None:
        words = textlayer.page_words(page)
    pm = render._pixmap(page, cfg)
    img, s = pm if pm else (None, None)
    kind, eng = ocr_read._ocr_engine_for(cfg)
    conf_min = float(cfg.get("vision_ocr_conf", 0.5))
    load_vlm, use_fallback = vlm_read._vlm_wanted(cfg, allow_vlm)
    vlm = vlm_read._vlm_engine(cfg) if load_vlm else None
    vlm_fallback = vlm if use_fallback else None
    force_vlm = bool(vlm_fallback is not None and cfg.get("vision_vlm_always"))
    sym_dets = symbols._symbol_dets(page, cfg) if cfg.get("vision_symbols", True) else []
    table_cls = runtime._REGION_CLASSES.index("hole_table")
    fcf_cls = runtime._REGION_CLASSES.index("feature_control_frame")
    from bubbler import common
    sections = (regions._page_sections(page, cfg)
                if cfg.get("vision_section_group", True) else [])
    blocks = []
    for bi, b in enumerate(boxes):
        brect = (b[0], b[1], b[2], b[3])
        quad = b[6] if len(b) > 6 else None
        region_cls = (runtime._REGION_CLASSES[int(b[5])]
                      if len(b) > 5 and 0 <= int(b[5]) < len(runtime._REGION_CLASSES)
                      else None)
        if region_cls == "notes_block" and holes._hole_note_box(brect, words):
            region_cls = "hole"
        cat = common.CATEGORY.get(region_cls)
        cat_kind = cat[0] if cat else None
        if cat_kind == common.KIND_META:
            continue
        if cat_kind == common.KIND_STACKED and sections:
            brect = layout.expand_to_section(brect, sections)
            quad = None                     # stale after grow
        elif (region_cls == "feature_control_frame"
              and cfg.get("vision_section_group", True)):
            # grow, never into other callout
            others = [o for oi, o in enumerate(boxes)
                      if oi != bi and (union._is_callout_box(o) or (
                          len(o) > 5 and int(o[5]) == fcf_cls))]
            brect = layout.grow_box_stack(
                brect, [w for w in words
                        if not any(geometry._center_in(w, o[:4]) for o in others)])
            quad = None
        blocks.append((bi, b, brect, region_cls, cat, quad))
    # revision/item balloon owns its number
    marks = union._balloon_boxes(boxes)
    if marks:
        words = [w for w in words if not union._center_in_any(w, marks)]
    owned = _assign_words(words, [blk[2] for blk in blocks],
                          [blk[5] for blk in blocks])
    all_hits = []
    for k, (bi, b, brect, region_cls, cat, quad) in enumerate(blocks):
        cat_kind = cat[0] if cat else None
        constraint = cat[2] if cat else None
        in_block = [words[i] for i in owned[k]]
        has_text = [w for w in in_block if str(w[4]).strip()]
        reader = "text"
        if not force_vlm and _text_layer_suffices(in_block, has_text,
                                                  constraint, cfg):
            block_words = in_block
        elif vlm_fallback is not None and img is not None:
            if on_slow:
                on_slow()
                on_slow = None
            try:
                block_words = vlm_read._vlm_read_block(img, s, brect, vlm_fallback,
                                              dedup._VBLOCK + 7000 + bi * 100)
                reader = "vlm"
            except Exception as e:                       # GPU OOM latches off
                vlm_read._vlm_died(e)
                block_words, reader = in_block, "text"
            if not block_words and has_text:
                block_words, reader = in_block, "text"
        elif not has_text and union._owned_elsewhere(brect, words, owned, k):
            # others' words, never pixels
            block_words = [w for w in words if str(w[4]).strip()
                           and geometry._center_in(w, brect, quad)]
        elif img is not None and eng is not None:
            if on_slow:
                on_slow()
                on_slow = None
            block_words = ocr_read._ocr_block(img, s, brect, kind, eng, conf_min,
                                     dedup._VBLOCK + 5000 + bi * 100,
                                     q=ocr_read.block_quarter(brect, in_block))
            reader = "ocr"
            block_words = ocr_read._join_ocr_fragments(ocr_read._split_ocr_phrases(block_words))
            # text layer wins over OCR
            block_words = ocr_read._off_text_layer(block_words, words, brect,
                                          partial_only=bool(has_text))
            # empty OCR keeps text word
            if not block_words and has_text:
                block_words, reader = in_block, "text"
        else:
            block_words = in_block
        inject = bool(sym_dets)
        fail_open = False
        if reader == "vlm" and not cfg.get("vision_sym_inject_vlm", True):
            inject = False
        if reader == "text" and not cfg.get("vision_sym_inject_text", True):
            inject = False
        if inject:
            block_words = list(block_words)
            block_syms = [(env, tok) for env, tok in sym_dets
                          if geometry._center_in((env[0], env[1], env[2], env[3]),
                                        brect, quad)
                          or _lead_phi_of(env, tok, brect, blocks, k)]
            if (region_cls == "feature_control_frame"
                    and cfg.get("vision_fcf_rerun", True)):
                crop = symbols._symbol_dets_clip(page, cfg, brect)
                if crop:
                    block_syms = symbols._dedup_syms(crop, block_syms)
            # neighbour admitting it owns it
            block_syms = [(env, tok) for env, tok in block_syms
                          if common.admits(constraint, tok)
                          or not _claimed_elsewhere(env, tok, blocks, k)]
            if reader == "ocr":
                block_words = [w for w in block_words
                               if not ocr_read._ocr_glyph_misread(w, block_syms)]
            have = symbols._block_glyphs(block_words)
            # refused glyph: fail open, doubtful
            fail_open = _class_contradicted(constraint, block_syms)
            # size glyphs before hole keywords
            for env, tok in sorted(block_syms, key=lambda st: st[1].strip()
                                   in symbols._KW_TOKENS):
                if (not fail_open and _has_opinion(constraint)
                        and not common.admits(constraint, tok)):
                    continue
                if symbols._glyph_present(tok, have):
                    continue
                # block_words, not in_block
                if symbols._on_text(env, block_words, tok):
                    continue
                symbols._attach_or_append(block_words, env, tok)
        hits = None
        if region_cls == "edge_condition":
            hits = edgemarks._edge_hits(brect, block_words)
        if hits is None and (region_cls == "feature_control_frame"
                and cfg.get("vision_fcf_structural", True)
                and ocr_read.block_quarter(brect, block_words) == 0):
            try:
                fcf = fcf_read._fcf_structural_hits(page, cfg, brect, block_words, bi)
            except Exception:                            # pragma: no cover
                fcf = []
            keep = [h for h in fcf                       # probe ROW glyph
                    if not _has_opinion(constraint)
                    or common.admits(
                        constraint,
                        fcf_read._fcf_glyph_for(h.get("fcf_char") or h.get("sb")))]
            if keep:
                for h in keep:
                    h["_ev_struct"] = True     # not in text layer
                hits = keep
                if len(keep) < len(fcf) or any(h.get("fcf_partial")
                                               or h.get("fcf_zone_suspect")
                                               for h in keep):
                    # partly read: add legacy
                    hits = keep + parse.scan_words(
                        block_words, include_bare=include_bare, cfg=cfg)
                else:
                    # leftover words: second frame
                    rest = [w for w in block_words if not any(
                        geometry._center_in(w, h["rect"]) for h in keep
                        if h.get("rect")) and str(w[4]).strip()]
                    # leftover on read row: clipped
                    clipped = any(
                        h.get("rect") and h["rect"][1] <= (w[1] + w[3]) / 2.0
                        <= h["rect"][3] for w in rest for h in keep)
                    if clipped:
                        more = parse.scan_words(
                            block_words, include_bare=include_bare, cfg=cfg)
                        hits = [h for h in keep
                                if not any(union._extends(g, h) for g in more)] + more
                    elif rest:
                        hits = keep + parse.scan_words(
                            rest, include_bare=include_bare, cfg=cfg)
        if hits is None:
            hits = parse.scan_words(block_words, include_bare=include_bare,
                                      cfg=cfg)
        if cat_kind == common.KIND_CONTAINER and rect is not None:
            hits = [h for h in hits
                    if h.get("rect") is None or geometry._rects_overlap(h["rect"], rect)]
        if (vlm is not None and img is not None
                and cfg.get("vision_vlm_crosscheck")
                and reader in ("text", "ocr")
                and vlm_read._crosscheck_block(region_cls, hits)):
            if on_slow:
                on_slow()
                on_slow = None
            vlm_read._apply_vlm_crosscheck(img, s, brect, bi, hits, vlm,
                                  include_bare, cfg)
        is_table = len(b) > 5 and int(b[5]) == table_cls
        conf = float(b[4]) if len(b) > 4 else 0.0
        for h in hits:
            # table groups stay in own thousand
            cg = int(h.get("cg") or 0)
            h["cg"] = bi * 1000 + ((cg % 100000) % 125
                                   + 125 * min(cg // 100000, 7)
                                   if is_table else 0)
            h["_ev"] = _region_evidence(h, region_cls, conf, reader,
                                        h.pop("_ev_struct", False))
            if fail_open:
                h["_ev"] = min(h["_ev"], fcf_read._EV_PLAIN)
                h["fcf_flags"] = sorted(
                    set(h.get("fcf_flags") or ()) | {"class_conflict"})
            # I/O/Q datum asked, not rewritten
            if (reader in ("ocr", "vlm") and cfg.get("vision_lexicon", True)
                    and grammar.impossible_datums(h.get("v"))):
                h["fcf_flags"] = sorted(
                    set(h.get("fcf_flags") or ()) | {"datum_impossible"})
        if (region_cls in common.UNBALLOONED_CLASSES and not fail_open
                and not any(ch.isdigit() for w in block_words
                            for ch in str(w[4]))):
            # datum claims words, no row
            continue
        if not is_table:
            # one balloon per ordinate
            parse.split_value_groups(hits, bi * 1000 + 500)
        all_hits.extend(hits)
    return dedup.dedup_hits(all_hits, score=_evidence) or None


def extract_hits(page, cfg, rect=None, include_bare=False, words=None,
                 allow_vlm=False, on_slow=None):
    """Structured hits for page or rect. None -> legacy path."""
    hits = _extract_hits(page, cfg, rect, include_bare, words, allow_vlm,
                         on_slow)
    # [] not None: None means legacy
    return hits if hits is None else drop_zone_labels(page, hits, words)


def drop_zone_labels(page, hits, words=None):
    """Frame zone number is no callout."""
    if not hits:
        return hits
    try:
        from bubbler.reader import textlayer
        ws = list(words) if words else textlayer.page_words(page)
        labels = textlayer.border_labels(ws, float(page.rect.width),
                                         float(page.rect.height))
    except Exception:
        labels = []
    if not labels:
        return hits
    return [h for h in hits if not (h.get("sb") == "BARE" and h.get("rect")
                                    and _in_label(h["rect"], labels))]


def _in_label(rc, labels):
    cx, cy = (rc[0] + rc[2]) / 2.0, (rc[1] + rc[3]) / 2.0
    return any(b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1
               for b in labels)


def _extract_hits(page, cfg, rect=None, include_bare=False, words=None,
                  allow_vlm=False, on_slow=None):
    if not cfg.get("vision_assist") or not cfg.get("vision_region", True):
        return None
    tbl_hits, tbl_rects = [], []
    try:
        from bubbler.reader import dedup, parse, textlayer
        if words is None:
            words = textlayer.page_words(page)
        tbl_hits, tbl_rects = holes._hole_table_hits(page, cfg, words, rect)
    except Exception as e:                              # pragma: no cover
        runtime._warn("hole table read failed (%s)" % e)
    if tbl_rects:
        # table reader owns these
        words = [w for w in words if not union._center_in_any(w, tbl_rects)]
    try:
        hits = _region_regex_hits(page, cfg, rect, include_bare, words,
                                  allow_vlm, on_slow, skip=tbl_rects)
    except Exception as e:
        runtime._warn("region path failed (%s); falling back to legacy" % e)
        return None
    if hits is None and tbl_hits:
        hits = []
    if hits is None and _has_gentol_block(page, cfg):
        # gentol block only: stay here
        hits = []
    if hits is None or not cfg.get("vision_region_union", True):
        return _strip_ev(None if hits is None else hits + tbl_hits)
    try:
        from bubbler.reader import dedup, parse, textlayer
        if words is None:
            words = textlayer.page_words(page)
        bare = include_bare and bool(cfg.get("vision_union_bare", True))
        legacy = parse.scan_words(words, include_bare=bare, cfg=cfg)
    except Exception as e:                              # pragma: no cover
        runtime._warn("text union failed (%s); using region hits only" % e)
        return _strip_ev(hits)
    if rect is not None:
        legacy = [h for h in legacy
                  if h.get("rect") is None or geometry._rects_overlap(h["rect"], rect)]
    # nothing in gentol block is callout
    try:
        gci = runtime._REGION_CLASSES.index("gentol_block")
        gen = [b for b in regions._region_boxes(page, cfg)
               if len(b) > 5 and int(b[5]) == gci]
    except Exception:
        gen = []
    try:
        marks = union._balloon_boxes(regions._region_boxes(page, cfg))
    except Exception:
        marks = []
    if marks:
        legacy = [h for h in legacy
                  if not h.get("rect") or not union._center_in_any(h["rect"], marks)]
    if gen:
        gen = [_gentol_extent(g, words) for g in gen]
        legacy = [h for h in legacy if not h.get("rect") or not any(
            g[0] <= (h["rect"][0] + h["rect"][2]) / 2.0 <= g[2]
            and g[1] <= (h["rect"][1] + h["rect"][3]) / 2.0 <= g[3]
            for g in gen)]
    legacy = [h for h in legacy if not union._union_fragment(h, hits)]
    try:
        callout_boxes = [b for b in regions._region_boxes(page, cfg)
                         if union._is_callout_box(b)]
    except Exception:
        callout_boxes = []
    legacy = [h for h in legacy
              if not union._union_bridges(h, callout_boxes, words)]
    legacy = edgemarks._edge_marks_split(page, words, legacy)
    if rect is not None:
        # split adds page-wide marks
        legacy = [h for h in legacy if h.get("rect") is None
                  or geometry._rects_overlap(h["rect"], rect)]
    for h in legacy:
        # text-only, own groups
        h["cg"] = dedup._VBLOCK + int(h.get("cg") or 0)
    merged = dedup.dedup_hits(list(hits) + legacy, score=_evidence)
    merged = [h for h in merged if not union._clipped_count(h, words)]
    holes._join_block_holes(merged, words)
    holes._join_trailing_depth(merged, words)
    # table rows after dedup
    return _strip_ev(merged + tbl_hits) or None


def _word_dir(w):
    d = w[8] if len(w) > 8 and w[8] else (1.0, 0.0)
    return (round(d[0]), round(d[1]))


def _gentol_extent(g, words):
    """Block's own text, not detector box."""
    inside = [w for w in words or ()
              if g[0] <= (w[0] + w[2]) / 2.0 <= g[2]
              and g[1] <= (w[1] + w[3]) / 2.0 <= g[3]]
    kw = [w for w in inside if edgemarks._GENTOL_KW.search(str(w[4]))]
    if not kw:
        return g
    dirs = {_word_dir(w) for w in kw}
    across = {w[5] for w in inside if _word_dir(w) not in dirs}
    note = [w for w in inside if w[5] not in across]
    if not note:
        return g
    return (max(g[0], min(w[0] for w in note)), max(g[1], min(w[1] for w in note)),
            min(g[2], max(w[2] for w in note)), min(g[3], max(w[3] for w in note)))


def _has_gentol_block(page, cfg):
    try:
        gci = runtime._REGION_CLASSES.index("gentol_block")
        return any(len(b) > 5 and int(b[5]) == gci
                   for b in regions._region_boxes(page, cfg))
    except Exception:
        return False


def read_rect_words(page, cfg, rect, use_vlm=False):
    pm = render._pixmap(page, cfg)
    if not pm:
        return None
    img, s = pm
    words = None
    if use_vlm and cfg.get("vision_vlm"):
        eng = vlm_read._vlm_engine(cfg)
        if eng is not None:
            try:
                words = vlm_read._vlm_read_block(img, s, rect, eng, dedup._VBLOCK + 9000)
            except Exception as e:
                runtime._note("vlm", "vlm read failed (%s); using OCR" % e)
                words = None
                vlm_read._vlm_died(e)
    if not words:
        kind, eng = ocr_read._ocr_engine_for(cfg)
        if eng is None:
            return None
        conf_min = float(cfg.get("vision_ocr_conf", 0.5))
        from bubbler.reader.textlayer import page_words
        from bubbler.reader.geometry import words_in_rect
        near = words_in_rect(page_words(page), *rect)
        words = ocr_read._ocr_block(img, s, rect, kind, eng, conf_min, dedup._VBLOCK + 9000,
                           q=ocr_read.block_quarter(rect, near))
    words = list(words)
    if cfg.get("vision_symbols", True):
        try:
            sym_dets = symbols._symbol_dets(page, cfg)
        except Exception:
            sym_dets = []
        have = symbols._block_glyphs(words)
        for env, tok in sym_dets:
            if not geometry._center_in((env[0], env[1], env[2], env[3]), rect):
                continue
            if symbols._glyph_present(tok, have):
                continue
            symbols._attach_or_append(words, env, tok)
    return words


def meta_region_at(page, cfg, rect):
    from bubbler import common
    if not cfg.get("vision_assist") or not cfg.get("vision_region", True):
        return None
    if runtime._region_session(cfg) is None:
        return None
    try:
        boxes = regions._region_boxes(page, cfg)
    except Exception:
        return None
    cx = (rect[0] + rect[2]) / 2.0
    cy = (rect[1] + rect[3]) / 2.0
    meta_cls, meta_area = None, None
    for b in boxes:
        if len(b) <= 5 or not (b[0] <= cx <= b[2] and b[1] <= cy <= b[3]):
            continue
        ci = int(b[5])
        cls = runtime._REGION_CLASSES[ci] if 0 <= ci < len(runtime._REGION_CLASSES) else None
        cat = common.CATEGORY.get(cls)
        if cat is None:
            continue
        if cat[0] != common.KIND_META:
            return None
        area = (b[2] - b[0]) * (b[3] - b[1])
        if meta_area is None or area < meta_area:
            meta_cls, meta_area = cls, area
    return meta_cls
