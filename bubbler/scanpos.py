# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Compat re-export. Kit imports from here.

from bubbler.gentol import (  # noqa: F401
    page_general_tols)
from bubbler.reader.dedup import (  # noqa: F401
    _FRAG_TP,
    _KEEP_ON_MERGE,
    _NEAR_OVERLAP,
    _NUMBER,
    _PATTERN_V,
    _SAME_READ_OVERLAP,
    _TOL_PAIR,
    _carry_doubt,
    _composite_absorbs,
    _digits,
    _drop_claimed_bare,
    _hit_anchor,
    _numbers,
    _tol_key,
    dedup_hits)
from bubbler.reader.fcf_geometry import (  # noqa: F401
    FCF_BOX_DPI,
    FCF_BOX_LOOK,
    _FCF_WIDEN,
    _FCF_WIDEN_MIN,
    _GDT_SYMBOLS_SET,
    _GDT_WORDS,
    _NUMISH,
    _UNSET,
    _bands_from_dividers,
    _clamp_page,
    _cluster,
    _cluster_spans,
    _covers,
    _fcf_bands_for,
    _fcf_box_raster,
    _fcf_box_vector,
    _fcf_boxed,
    _fcf_find_box,
    _fcf_pick,
    _fcf_raster_bands,
    _fcf_reads_as_frame,
    _fcf_rect_from_lines,
    _fcf_through_border,
    _fcf_vector_bands,
    _fcf_widen,
    _join_collinear,
    _lines_from_ink,
    _longest_ink,
    _near_side,
    _profile_lines,
    _profile_runs,
    _segment_fcf,
    _thin,
    segment_fcf_cells)
from bubbler.reader.geometry import (  # noqa: F401
    _DIAG_MIN,
    _QUARTER,
    _UP,
    _diag_angle,
    _diag_back,
    _diag_box,
    _dir_quarter,
    _from_frame,
    _iou,
    _rect_covers,
    _rect_holds,
    _rect_map,
    _rect_mostly_in,
    _shape_dir,
    _to_frame,
    _touching,
    _union,
    _union_all,
    fill_dirs,
    words_in_rect,
    xform_pt,
    xform_rect)
from bubbler.reader.layout import (  # noqa: F401
    _CONT_KW_RE,
    _OCR_BLOCK,
    _box_quarter,
    _grow_level,
    _is_continuation,
    _sections_level,
    expand_to_section,
    grow_box_stack,
    page_sections,
    reading_order_first,
    reading_order_lines,
    sections_from_words,
    words_by_frame)
from bubbler.reader.parse import (  # noqa: F401
    _BARE_NUM,
    _LONE_PREFIX,
    _REF_NOUNS,
    _VALUE_TP,
    _gdt_led,
    _join_split_lines,
    _line_string,
    _scan_frame,
    _year_like,
    parse_lines,
    scan_page_positions,
    scan_words,
    split_value_groups)
from bubbler.reader.textlayer import (  # noqa: F401
    FONT_GLYPHS,
    SPAN_GLYPHS,
    _GID_EXTRA,
    _PM_NUM,
    _drawn_pm_marks,
    _font_key,
    _gid_char,
    _glue_drawn_pm,
    _glyph_fixes,
    _is_gid_span,
    _line_dirs,
    _repair_word,
    _span_glyph,
    page_words)
from bubbler.reader.textlines import (  # noqa: F401
    _DEPTH_MARK,
    _DEV_LINE,
    _FIT_DEV_LINE,
    _FIT_LINE,
    _GLUED_DEV,
    _HAS_TOL,
    _LONE_NOMINAL,
    _NUMONLY_LINE,
    _NX_LINE,
    _PM_LINE,
    _RADIUS_RE,
    _SIGNED_TOK,
    _STACK_REACH,
    _bare_fit_code,
    _depth_marker_idxs,
    _depth_marker_rect,
    _depth_owned,
    _dev_val,
    _follows,
    _lheight,
    _lrect,
    _ltext,
    _split_lines_on_gaps,
    lines_from_words,
    merge_callout_block,
    merge_fit,
    merge_halfstack,
    merge_nx,
    merge_pm_stack,
    merge_stacked)
from bubbler.reader.tokens import (  # noqa: F401
    _COUNT_RE,
    _COUNT_WORDS,
    _DNUM_START,
    _FRAC_HEAD,
    _FRAC_TAIL,
    _GLYPHS,
    _KEYWORDS,
    _LIM_WHOLE,
    _NUM_START,
    _PHI_RE,
    _SDEV_TOK,
    _SYMBOLS,
    _cond_match,
    _drop_inch_marks,
    _fold_limits,
    _frac_ok,
    _glued_ok,
    _heal_phi,
    _kw_key,
    _merge_split_values,
    _norm_token,
    _normalize_line,
    norm_tokens)
from bubbler.reader import parse  # noqa: E402


def _main(argv):
    import fitz
    from bubbler.reader.grammar import scan_normalize
    from bubbler.reader.parse import scan_parse
    if len(argv) < 2:
        print("usage: python -m bubbler.scanpos drawing.pdf")
        return 1
    doc = fitz.open(argv[1])
    for pg in range(doc.page_count):
        page = doc[pg]
        old = scan_parse(scan_normalize(page.get_text("text") or ""))
        new = parse.scan_page_positions(page)

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
