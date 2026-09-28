# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Reader package map.
"""Reader: drawing page in, callout hits out.

Hit = dict: `tp` kind, `sb` symbol, `v` value text, `t` tolerance, `cg`
balloon group, `rect` / `arect` (extent, anchor), plus flags. Everything
below makes, merges or checks hits. Start at `pipeline.extract_hits`.

Two readers, one grammar. FLAT reader runs patterns over page plain text
(`parse.scan_parse`). WORD reader works from positioned words
(`textlayer` -> `tokens` -> `textlines` -> `parse.parse_lines` /
`scan_words`). Both end in `grammar.SCAN_PATS`; `tests/fcf_diff.py` proves
same `(v, t)` per frame. Rule with two readers: fix both.

Layers, lowest first. Module uses only layers above it. Exceptions:
fcf_geometry renders clip via vision.render, vision.runtime resets other
vision caches.

  grammar       callout patterns (SCAN_PATS), text normalising, GD&T value
                / modifier / datum grammar, edge-note spelling
  geometry      rects, unions, containment, reading frames, quarters
  dedup         one hit per callout: anchors, containment, doubt carried
                across merge; balloon-group id bands (_VBLOCK, ...)
  textlayer     PDF text layer as words: font glyph repair, directions
  tokens        per-word clean-up: keywords, phi healing, split values
  textlines     words -> lines, every merge joining callout pieces
  layout        reading order, sections, box grown over its stack
  parse         both readers, one place
  holetable     TAG | X | Y | SIZE grids from words and rulings
  fcf_geometry  find feature control frame, prove closed, cut cells
  fcf_read      segmented frame cells -> GD&T hits
  vision/       models: runtime (ONNX sessions, class lists), render,
                detect, regions, symbols (glyphs), ocr_read, vlm_read
  edgemarks     ISO 13715 edge conditions
  holes         hole tables and hole notes as balloon groups
  union         text-layer read merged with region read
  pipeline      page / dragged rect -> hits; general-tolerance block

Outside package, fed by it:

  bubbler.gentol    general tolerances: block read, ISO 2768 / ASME
                    ladders, ONE answer (general_tol)
  bubbler.scanrows  hits -> sheet rows: facets, tolerance strings, scan
                    scope (buckets / presets), hole-row expansion
  bubbler.gaging    which tool measures feature

`bubbler.scanlib`, `bubbler.scanpos`, `bubbler.vision`, `bubbler.holetable`:
COMPATIBILITY re-exports, kept for BubblerHelpers kit imports. App code
imports from owning module.
"""
