# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Click and drag callout capture mixin.

import copy
import re
import sys

from PySide6.QtCore import Qt, QEventLoop, QTimer, QThreadPool
from PySide6.QtWidgets import (QApplication, QMenu, QMessageBox,
                               QProgressDialog)

from . import scanworker
from .reader import pipeline
from .scanreview import FCF_SUSPECT, ScanReview
from .gentol import gentol_exempt, inherit_gtols
from .reader.grammar import scan_normalize
from .reader.parse import scan_parse
from .scanrows import (scan_to_row, strip_repeat, stamp_facets, facet_rank,
                       strip_count)
from .corrections import proposal_of
from .gentol import page_general_tols
from .reader.geometry import (words_in_rect, fill_dirs, _dir_quarter,
                              _rect_map, _to_frame, _from_frame)
from .reader.layout import (reading_order_first, _box_quarter,
                            reading_order_lines)
from .reader.parse import _VALUE_TP
from .reader.textlayer import page_words
from .common import base_of
from .config import CFG_DEFAULT, units_of
from .i18n import tr


def _suspect_of(hits):
    bad = []
    for h in hits or ():
        for c in h.get("fcf_flags") or ():
            if c in FCF_SUSPECT and c not in bad:
                bad.append(c)
    return ", ".join(bad)



def _rect_dist(rc, x, y):
    dx = max(rc[0] - x, 0.0, x - rc[2])
    dy = max(rc[1] - y, 0.0, y - rc[3])
    return dx * dx + dy * dy

class CaptureMixin:
    def _balloon_rows_warned(self, rows, cx, cy, rect, doubt):
        before = {id(d) for d in self.ledger}
        self._balloon_from_rows(rows, cx, cy, rect=rect)
        if doubt:
            self.set_status(tr('Uncertain read') + ": " + doubt)
        self._auto_toast(before)

    def _auto_toast(self, before):
        if not self.cfg.get("auto_toast", True):
            return
        new = [d for d in self.ledger if id(d) not in before]
        if not new:
            return
        main = new[0]
        uid = main.get("uid")
        text = "#%s  %s" % (main.get("bubble", "?"),
                            main.get("feature") or tr('callout'))
        more = ("  " + tr('(+%d more)') % (len(new) - 1)
                if len(new) > 1 else "")

        def correct():
            # match by identity, undo reuses uid
            for i, d in enumerate(self.ledger):
                if d is main:
                    self.edit_ledger_row(i)
                    return
            self.set_status(tr('That bubble no longer exists'))
        from .toast import toast_timing
        stack = getattr(self, "_toasts", None)
        if stack is None:
            from .toast import ToastStack
            # view not viewport, else scrolls
            stack = self._toasts = ToastStack(self.view)
        stack.ms, stack.cap = toast_timing(self.cfg)
        stack.show_toast(text, correct, more)

    def _active_hdr_field(self):
        ent = getattr(self, "_hdr_focus", None)
        if ent is None:
            return None
        try:
            live = ent.isVisible() and ent.window().isVisible()
        except RuntimeError:                 # deleted
            live = False
        if not live:
            self._hdr_focus = None
            return None
        return ent

    def on_capture_press(self, sp):
        self._capturing = True
        self._capture_start = (sp.x(), sp.y())
        self._capture_cur = (sp.x(), sp.y())
        self.redraw_overlay()

    def on_capture_drag(self, sp):
        if self._capture_start is None:
            return
        self._capture_cur = (sp.x(), sp.y())
        self.redraw_overlay()

    def on_capture_release(self, sp, gpos):
        self._capturing = False
        if self._capture_start is None:
            return
        x0, y0 = self._capture_start
        x1, y1 = sp.x(), sp.y()
        self._capture_start = None
        self._capture_cur = None
        self.redraw_overlay()
        p0 = self.viewport.scene_to_page(min(x0, x1), min(y0, y1))
        p1 = self.viewport.scene_to_page(max(x0, x1), max(y0, y1))
        rx0, ry0 = min(p0[0], p1[0]), min(p0[1], p1[1])
        rx1, ry1 = max(p0[0], p1[0]), max(p0[1], p1[1])
        was_drag = not (rx1 - rx0 < 3 and ry1 - ry0 < 3)
        clicked = not was_drag
        snapped = False
        if clicked:
            mx, my = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0
            rgn = self._region_at(mx, my)
            snapped = rgn is not None
            rx0, ry0, rx1, ry1 = rgn if rgn else self._capture_box(mx, my)
        rect = (rx0, ry0, rx1, ry1)
        sel_rect = (rx0 - 2, ry0 - 2, rx1 + 2, ry1 + 2)
        hdr = self._active_hdr_field()
        want_hits = (not self.measure_mode) and (hdr is None)
        force_read = None
        if was_drag and self.cfg.get("capture_drag_ocr", True):
            force_read = "vlm" if self.cfg.get("vision_vlm") else "ocr"
        res = self._run_capture(self.page_i, rect, sel_rect,
                                want_meta=want_hits, want_hits=want_hits,
                                force_read=force_read, ocr_fallback=snapped)
        if res is None:
            return
        sel = res["sel"]
        if not sel:
            self.set_status(tr('no text here'))
            return
        text = res["text"]
        QApplication.clipboard().setText(" ".join(text.split()))
        if hdr is not None:
            try:
                hdr.setText(" ".join(text.split()))
            except RuntimeError:
                self._hdr_focus = None
            self.set_status(tr('copied: %s') % text[:50])
            return
        if not self.measure_mode:
            meta = res["meta"]
            if meta:
                name = {"gentol_block": tr('general tolerance'),
                        "notes_block": tr('note'),
                        "title_block": tr('title block')}.get(meta, tr(meta))
                self.set_status(tr('%s - no bubble (Alt-click to add)')
                                % name)
                return
            hits = res["hits"] or []
            if not hits:
                hits = scan_parse(scan_normalize(text), self.cfg)
                for h in hits:
                    h["rect"] = (rx0, ry0, rx1, ry1)
            if not hits:
                mnum = re.search(r"\d+(?:[.,]\d+)?",
                                 strip_count(scan_normalize(text)))
                if mnum:
                    hits = [{"tp": "LINEAR", "sb": "BARE",
                             "v": mnum.group(0), "t": None, "raw": text,
                             "rect": (rx0, ry0, rx1, ry1)}]
            gtols = self._page_gtols()
            doubt = _suspect_of(hits)
            if not hits and snapped:
                cls = self._region_cls_for((rx0, ry0, rx1, ry1))
                row = self._region_only_row(cls, text, (rx0, ry0, rx1, ry1),
                                            gtols)
                if row is not None:
                    tx, ty = self._text_top((rx0, ry0, rx1, ry1))
                    if self.cfg.get("click_auto_bubble", True):
                        self._safe_balloon([row], tx, ty,
                                           (rx0, ry0, rx1, ry1), "")
                    else:
                        self._new_bubble_at(tx, ty, None, prefill=row,
                                            rect=(rx0, ry0, rx1, ry1))
                    return
            covered = self._bubbles_in_rect((rx0, ry0, rx1, ry1)) \
                if was_drag else []
            if covered and hits:
                rows = [self._capture_full_row(h, gtols) for h in self._by_facet(hits)]
                fb = (rx0, ry0, rx1, ry1)
                ax, ay = self._dir_anchor(hits, fb)
                before = {id(d) for d in self.ledger}
                self._regroup_capture(covered, rows, ax, ay, rect=fb)
                self._auto_toast(before)
                if doubt:
                    self.set_status(tr('Uncertain read') + ": " + doubt)
                return
            if clicked and snapped and hits:
                from . import common
                cls = self._region_cls_for((rx0, ry0, rx1, ry1))
                kind = (common.CATEGORY.get(cls) or (None,))[0]
                vals = [h for h in hits if h.get("tp") in _VALUE_TP]
                ordinate = cls == "dim_ordinate" or all(
                    h.get("sb") in ("BASIC", "REF") for h in vals)
                if len(vals) > 1 and len(vals) == len(hits) and ordinate \
                        and self.cfg.get("click_auto_bubble", True):
                    # the one clicked, not the whole box
                    h = min(vals, key=lambda v: _rect_dist(
                        v.get("rect") or (rx0, ry0, rx1, ry1), mx, my))
                    hr = h.get("rect") or (rx0, ry0, rx1, ry1)
                    if not self._rebubble_ok(h, hr):
                        return
                    hx, hy = self._hit_anchor_pt(h, hr)
                    self._safe_balloon([self._capture_full_row(h, gtols)],
                                       hx, hy, hr, doubt)
                    return
                if kind == common.KIND_ATOMIC and len(hits) > 1:
                    row = self._region_only_row(cls, text,
                                                (rx0, ry0, rx1, ry1), gtols)
                    rows = ([row] if row is not None
                            else [self._capture_full_row(hits[0], gtols)])
                else:
                    rows = [self._capture_full_row(h, gtols) for h in self._by_facet(hits)]
                ax, ay = self._dir_anchor(hits, (rx0, ry0, rx1, ry1))
                if self.cfg.get("click_auto_bubble", True):
                    self._safe_balloon(rows, ax, ay, (rx0, ry0, rx1, ry1), doubt)
                else:
                    self._new_bubble_at(
                        ax, ay, None,
                        prefill=self._capture_prefill(hits[0], gtols),
                        rect=(rx0, ry0, rx1, ry1))
                return
            if len(hits) == 1:
                hr = hits[0].get("rect") or (rx0, ry0, rx1, ry1)
                ax, ay = self._hit_anchor_pt(hits[0], (rx0, ry0, rx1, ry1))
                bad = [c for c in (hits[0].get("fcf_flags") or ())
                       if c in FCF_SUSPECT]
                self.set_status((tr('Uncertain read') + ": "
                                 + ", ".join(bad) + " - " + text[:40])
                                if bad else tr('captured: %s') % text[:50])
                if clicked and self.cfg.get("click_auto_bubble", True) \
                        and not bad:
                    if not self._rebubble_ok(hits[0], hr):
                        return
                    self._safe_balloon(
                        [self._capture_full_row(hits[0], gtols)],
                        ax, ay, (rx0, ry0, rx1, ry1), doubt)
                else:
                    self._new_bubble_at(ax, ay, None,
                                        prefill=self._capture_prefill(hits[0],
                                                                      gtols),
                                        rect=hr)
                return
            if len(hits) > 1:
                cx, cy = self._dir_anchor(hits, (rx0, ry0, rx1, ry1))
                if clicked and snapped \
                        and self.cfg.get("click_auto_bubble", True):
                    self._safe_balloon(
                        [self._capture_full_row(h, gtols) for h in self._by_facet(hits)],
                        cx, cy, (rx0, ry0, rx1, ry1), doubt)
                    return
                m = QMenu(self)
                m.addAction(
                    tr('Review %d callouts...') % len(hits),
                    lambda: ScanReview(
                        self, [(self.page_i, h) for h in hits],
                        {self.page_i: gtols}, False).exec())
                m.addAction(
                    tr('All %d as sub-rows')
                    % len(self._by_facet(list(hits))),
                    lambda: self._balloon_rows_warned(
                        [self._capture_full_row(h, gtols) for h in self._by_facet(hits)],
                        cx, cy, (rx0, ry0, rx1, ry1), doubt))
                m.addSeparator()
                for h in hits:
                    ax, ay = self._hit_anchor_pt(h, (rx0, ry0, rx1, ry1))
                    hr = h.get("rect") or (rx0, ry0, rx1, ry1)
                    label = "%s%s  %s" % (
                        "\u26a0 " if _suspect_of([h]) else "",
                        "dim" if h.get("sb") == "BARE" else h["tp"], h["v"])
                    m.addAction(label,
                                lambda h=h, ax=ax, ay=ay, hr=hr:
                                self._new_bubble_at(
                                    ax, ay, None,
                                    prefill=self._capture_prefill(h, gtols),
                                    rect=hr))
                self.set_status(
                    (tr('Uncertain read') + ": " + doubt) if doubt
                    else tr('captured %d callouts') % len(hits))
                m.exec(gpos.toPoint())
                return
        self.set_status(tr('copied: %s') % text[:50])

    def on_right_click(self, sp, gpos):
        if (self.measure_mode or self._active_hdr_field() is not None
                or getattr(self, "tool", "add") != "add"
                or getattr(self, "_scan_region_mode", None)
                or getattr(self, "_correct_mode", None)):
            return False
        p = self.viewport.scene_to_page(sp.x(), sp.y())
        rgn = self._region_at(*p) if p else None
        if rgn is None:
            self.set_status(tr('no callout here'))
            return False
        rect = tuple(rgn)
        sel = (rect[0] - 2, rect[1] - 2, rect[2] + 2, rect[3] + 2)
        res = self._run_capture(self.page_i, rect, sel, want_meta=True,
                                want_hits=True, ocr_fallback=True)
        if res is None or res.get("meta"):
            return False
        hits = list(res.get("hits") or ())
        if len(hits) < 2:
            self.set_status(tr('one part here: click it to bubble'))
            return False
        gtols = self._page_gtols()
        stamp_facets(hits)
        hits.sort(key=lambda h: facet_rank(h.get("facet"), self.cfg))
        m = QMenu(self)
        m.addSection(tr('Bubble one part'))
        for h in hits:
            label = "%s%s  %s" % (
                "\u26a0 " if _suspect_of([h]) else "",
                "dim" if h.get("sb") == "BARE" else h["tp"], h["v"])
            m.addAction(label, lambda h=h: self._bubble_part(h, gtols, rect))
        self._exec_menu(m, gpos)
        return True

    def _exec_menu(self, m, gpos):
        m.exec(gpos.toPoint())

    def _bubble_part(self, h, gtols, rect):
        hr = tuple(h.get("rect") or rect)
        ax, ay = self._hit_anchor_pt(h, rect)
        if self.cfg.get("click_auto_bubble", True):
            self._safe_balloon([self._capture_full_row(h, gtols)],
                               ax, ay, hr, "")
        else:
            self._new_bubble_at(ax, ay, None,
                                prefill=self._capture_prefill(h, gtols),
                                rect=hr)

    def _drop_gtols(self, pages=None):
        """Inherited block depends on other pages, cache goes whole."""
        raw = self.__dict__.get("_gtol_raw", {})
        for pg in (list(raw) if pages is None else pages):
            raw.pop(pg, None)
        self._gtol_cache = {}

    def _own_gtols(self, page_i):
        raw = self.__dict__.setdefault("_gtol_raw", {})
        if page_i not in raw:
            try:
                page = self.doc[page_i]
                scanned = not (page.get_text("text") or "").strip()
                # cached scan words only, no UI-thread OCR
                words = (self.__dict__.get("_vword_cache", {}).get(page_i)
                         if scanned else None)
                got = page_general_tols(page, words)
                if scanned and words is None:
                    return got  # not read yet
                raw[page_i] = got
            except Exception:
                raw[page_i] = {}
        return raw[page_i]

    def _inherited_gtols(self, page_i):
        """Sheet 1 block borrowed when sheet prints none."""
        try:
            n = self.doc.page_count
        except Exception:
            return {}
        for pg in range(n):
            if pg == page_i or not self._own_gtols(pg):
                continue
            gt = {pg: self._own_gtols(pg), page_i: {}}
            inherit_gtols(gt, [pg, page_i])
            return gt.get(page_i) or {}
        return {}

    def gtols_now(self):
        try:
            return self._page_gtols()
        except Exception:
            return {}

    def _page_gtols(self, page_i=None):
        if page_i is None:
            page_i = self.page_i
        if not hasattr(self, "_gtol_cache"):
            self._gtol_cache = {}
        if page_i not in self._gtol_cache:
            g = self._own_gtols(page_i)
            self._gtol_cache[page_i] = g or self._inherited_gtols(page_i)
            self.adopt_iso_class(self._gtol_cache[page_i])
        return self._gtol_cache[page_i]

    def edit_gentol(self):
        from .gentol_edit import GentolDialog, ReapplyDialog
        from .gentol import gentol_reapply_plan
        if self._edit_blocked():
            return
        page_i = getattr(self, "page_i", 0)
        was = dict(self._own_gtols(page_i) or self.gtols_now())
        d = GentolDialog(self, self.gtols_now(), self.cfg, self.drawing,
                         page_i)
        if not d.exec():
            return
        block = d.result_block()
        if (self.drawing.get("gentol_user") or None) == (block or None):
            return
        self.snapshot()
        plan = gentol_reapply_plan(self.ledger, was, self.cfg, self.drawing,
                                   block, icls=self.last.get("icls"))
        if block:
            self.drawing["gentol_user"] = block
        else:
            self.drawing.pop("gentol_user", None)
        self._gtol_cache = {}
        n = 0
        if plan:
            r = ReapplyDialog(self, self.ledger, plan)
            if r.exec():
                for i, new in r.chosen():
                    self.ledger[i]["tol_sym"] = new
                    n += 1
        self._save_session()
        self.refresh_panel()
        self._sync_gentol()
        self.render()
        self.set_status(
            tr('general tolerance corrected, %d rows updated') % n if block
            else tr('general tolerance reset to drawing'))

    def _doc_units(self):
        """Only inch-marked FIT reads it."""
        return units_of(self.cfg, getattr(self, "drawing", None))

    def _by_facet(self, hits):
        stamp_facets(hits)
        # unbubbled part stays off unless toleranced
        from .scanrows import facet_skipped, scan_bucket
        kept = [h for h in hits
                if not facet_skipped(h.get("facet"), self.cfg)
                or scan_bucket(h) == "own_tol"] or hits
        return sorted(kept, key=lambda h: facet_rank(h.get("facet"),
                                                      self.cfg))

    def _read_proposal(self, h):
        """Pre-gentol read, no sticky type."""
        raw = scan_to_row(h, self._doc_units())
        if h.get("sb") == "BARE":
            raw["type"] = None
        return proposal_of(dict(raw, feature=strip_repeat(raw.get("feature"))))

    def _capture_prefill(self, h, gtols):
        rw = scan_to_row(h, self._doc_units())
        self._apply_general_tol(rw, h, gtols)
        if h.get("sb") == "BARE":
            pre = {"nominal": rw.get("nominal"),
                   "tol_sym": rw.get("tol_sym")}
            if rw.get("qty"):
                pre["qty"] = rw["qty"]
        else:
            pre = rw
        if gentol_exempt(h, self.cfg):
            pre["no_gentol"] = True
        pre["proposal"] = self._read_proposal(h)
        return pre

    def _capture_full_row(self, h, gtols):
        rw = scan_to_row(h, self._doc_units())
        self._apply_general_tol(rw, h, gtols,
                                iso_on=bool(self.last.get("iso_on")))
        if h.get("sb") == "BARE":
            rw["type"] = "dim"
            rw["tier"] = self.last.get("tier", "")
        rw["proposal"] = self._read_proposal(h)
        return rw

    def _capture_box(self, cx, cy):
        try:
            hw = float(self.cfg.get("capture_radius",
                                    CFG_DEFAULT["capture_radius"]))
        except (TypeError, ValueError):
            hw = CFG_DEFAULT["capture_radius"]
        hw = max(2.0, hw)
        hh = hw * 0.75
        if self._vertical_text_near(cx, cy, hw):
            hw, hh = hh, hw
        return cx - hw, cy - hh, cx + hw, cy + hh

    def _text_top(self, rect):
        try:
            q = _box_quarter(rect, self._aug_words(self.page_i))
        except Exception:
            q = 0
        f = _rect_map(_to_frame, q, rect)
        return _from_frame(q, (f[0] + f[2]) / 2.0, f[1])

    def _vertical_text_near(self, cx, cy, reach):
        try:
            words = fill_dirs(self._aug_words(self.page_i))
        except Exception:
            return False
        best = None
        for w in words:
            dx = max(w[0] - cx, 0.0, cx - w[2])
            dy = max(w[1] - cy, 0.0, cy - w[3])
            dd = dx * dx + dy * dy
            if dd <= reach * reach and (best is None or dd < best[0]):
                best = (dd, w)
        return best is not None and _dir_quarter(best[1]) in (1, 3)

    def _bubbled_as(self, h, rect):
        """Balloon number already on this value, or None."""
        cx, cy = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
        try:
            num = float(str(h.get("v") or "").replace(",", "."))
        except ValueError:
            num = None
        for d in getattr(self, "ledger", None) or ():
            rc = d.get("rect")
            if d.get("page") != self.page_i or not rc:
                continue
            if not (rc[0] - 1 <= cx <= rc[2] + 1
                    and rc[1] - 1 <= cy <= rc[3] + 1):
                continue
            same = str(d.get("feature") or "") == str(h.get("v") or "")
            if not same and num is not None and d.get("nominal") is not None:
                same = abs(float(d["nominal"]) - num) < 1e-9
            if same:
                return base_of(d.get("bubble"))
        return None

    def _rebubble_ok(self, h, rect):
        """Ask before a second balloon on one value."""
        num = self._bubbled_as(h, rect)
        if num is None:
            return True
        ans = QMessageBox.question(
            self, tr('Already ballooned'),
            tr('This value is already balloon #%s. Balloon it again?') % num,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return ans == QMessageBox.Yes

    def _safe_balloon(self, rows, cx, cy, rect, doubt, label=""):
        """Commit rows, surfacing a raised commit instead of swallowing it."""
        try:
            self._balloon_rows_warned(rows, cx, cy, rect, doubt)
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.set_status(tr('Could not add bubble: %s') % e)
            return False

    def _region_syms(self):
        """[(box, glyph)]. [] on failure."""
        try:
            from .reader.vision import symbols
            return symbols._symbol_dets(self.doc[self.page_i], self.cfg)
        except Exception:
            return []

    def _region_confirm_rank(self, b, syms):
        """0 glyph found, 1 none needed, 2 glyph missing."""
        from . import common
        from .reader.vision import runtime
        ci = int(b[5]) if len(b) > 5 else -1
        cls = (runtime._REGION_CLASSES[ci]
               if 0 <= ci < len(runtime._REGION_CLASSES) else None)
        need = common.region_needs_symbol(cls) if cls else None
        if not need:
            return 1
        x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
        for (sx0, sy0, sx1, sy1), tok in syms:
            cx, cy = (sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0
            if x0 <= cx <= x1 and y0 <= cy <= y1 and tok in need:
                return 0
        return 2

    def _region_at(self, px, py):
        """Glyph-confirmed first, then smallest."""
        try:
            dets = self._region_dets()
        except Exception:
            return None
        cands = [b for b in dets
                 if b[0] <= px <= b[2] and b[1] <= py <= b[3]]
        if not cands:
            return None

        def _area(b):
            return (b[2] - b[0]) * (b[3] - b[1])
        if len(cands) == 1:
            b = cands[0]
            return (b[0], b[1], b[2], b[3])
        syms = self._region_syms()
        b = min(cands, key=lambda b: (self._region_confirm_rank(b, syms),
                                      _area(b)))
        return (b[0], b[1], b[2], b[3])

    def _region_cls_for(self, rect):
        from .reader.vision import runtime
        try:
            dets = self._region_dets()
        except Exception:
            return None
        for b in dets:
            if (abs(b[0] - rect[0]) < 1 and abs(b[1] - rect[1]) < 1
                    and abs(b[2] - rect[2]) < 1 and abs(b[3] - rect[3]) < 1):
                ci = int(b[5]) if len(b) > 5 else -1
                if 0 <= ci < len(runtime._REGION_CLASSES):
                    return runtime._REGION_CLASSES[ci]
        return None

    def _region_only_row(self, cls, text, rect, gtols):
        from . import common
        cat = common.CATEGORY.get(cls)
        if not cat or cat[0] == common.KIND_META:
            return None
        body = scan_normalize(text or "")
        if cls != "chamfer":
            body = strip_count(body)
        num = re.search(r"[\d.,]*\d", body)
        h = {"tp": "LINEAR", "sb": "BARE", "v": num.group(0) if num else "",
             "t": None, "raw": text or "", "rect": rect}
        row = self._capture_full_row(h, gtols)
        row["type"] = cat[1]
        if text and text.strip() and not row.get("feature"):
            row["feature"] = " ".join(text.split())[:60]
        return row

    def _aug_words(self, page_i=None):
        if page_i is None:
            page_i = self.page_i
        page = self.doc[page_i]
        if not self.cfg.get("vision_assist"):
            return page_words(page)
        cache = self.__dict__.setdefault("_vword_cache", {})
        if page_i not in cache:
            base = page_words(page)
            words = base
            try:
                words = pipeline.augment_words(page, list(base), self.cfg)
            except Exception as e:
                print("bubbler: vision assist skipped (%s)" % e,
                      file=sys.stderr)
            added = len(words) - len(base)
            edited = sum(1 for a, b in zip(words, base) if a[4] != b[4])
            print("bubbler.vision: page %d: %d text words, +%d recovered, "
                  "%d edited" % (page_i + 1, len(base), max(0, added), edited),
                  file=sys.stderr)
            cache[page_i] = words
            self._drop_gtols([page_i])    # scan block reads these
        return cache[page_i]

    def _run_capture(self, page_i, rect, sel_rect, want_meta, want_hits,
                     force_read=None, ocr_fallback=False):
        if getattr(self, "_cap_loop", None) is not None:
            return None
        self._cap_loop = QEventLoop()
        self._cap_state = {}
        dlg = None
        try:
            dlg = QProgressDialog(
                tr('Reading callout...'), tr('Cancel'),
                0, 0, self)
            dlg.setWindowTitle(tr('Capture'))
            dlg.setWindowModality(Qt.ApplicationModal)
            dlg.reset()
            dlg.canceled.connect(self._cap_cancel)
            self._cap_dlg = dlg
            QTimer.singleShot(
                200, lambda st=self._cap_state, d=dlg:
                None if "done" in st else d.show())
            task = scanworker.CaptureTask(self.pdf_path,
                                          copy.deepcopy(self.cfg),
                                          page_i, rect, sel_rect, want_meta,
                                          want_hits, force_read=force_read,
                                          ocr_fallback=ocr_fallback)
            task.signals.done.connect(self._cap_done)
            task.signals.failed.connect(self._cap_failed)
            QThreadPool.globalInstance().start(task)
            self._cap_loop.exec()
        except Exception as e:
            # never leave the guard set
            print("bubbler: capture setup failed (%s)" % e, file=sys.stderr)
            self._cap_state = self._cap_state or {}
            self._cap_state["error"] = str(e)
        finally:
            self._cap_loop = None
            self._cap_dlg = None
            if dlg is not None:
                try:
                    dlg.canceled.disconnect(self._cap_cancel)
                except (RuntimeError, TypeError):
                    pass
                dlg.close()
        state = self._cap_state or {}
        self._cap_state = None
        if state.get("cancel"):
            self.set_status(tr('capture cancelled'))
            return None
        if "error" in state:
            QMessageBox.warning(self, tr('Capture'),
                                tr('Capture failed: %s')
                                % state["error"])
            return None
        r = state.get("result")
        if r and r.get("vwords"):
            self.__dict__.setdefault("_vword_cache", {}).update(r["vwords"])
            self._drop_gtols(list(r["vwords"]))
            if hasattr(self, "_sync_gentol"):
                self._sync_gentol()
        return r

    def _cap_done(self, r):
        if self._cap_state is None:
            return
        self._cap_state["done"] = True
        self._cap_state["result"] = r
        self._cap_loop.quit()

    def _cap_failed(self, m):
        if self._cap_state is None:
            return
        self._cap_state["done"] = True
        self._cap_state["error"] = m
        self._cap_loop.quit()

    def _cap_cancel(self):
        st = self._cap_state
        if st is None or st.get("done"):
            return
        st["cancel"] = True
        self._cap_loop.quit()

    def _words_in_rect(self, rx0, ry0, rx1, ry1, page_i=None):
        if page_i is None:
            page_i = self.page_i
        return words_in_rect(self._aug_words(page_i), rx0, ry0, rx1, ry1)

    @staticmethod
    def _words_text(words):
        return "\n".join(" ".join(l) for l in reading_order_lines(words))

    @staticmethod
    def _hit_anchor_pt(hit, fallback_rect):
        r = hit.get("rect") or fallback_rect
        return ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0)

    def _dir_anchor(self, hits, fb):
        rects = [h.get("rect") for h in hits if h.get("rect")]
        if rects:
            x0 = min(r[0] for r in rects)
            y0 = min(r[1] for r in rects)
            x1 = max(r[2] for r in rects)
            y1 = max(r[3] for r in rects)
        else:
            x0, y0, x1, y1 = fb
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        pref = self.cfg.get("offset_dir", "auto")
        edge = {"n": (cx, y0), "s": (cx, y1),
                "e": (x1, cy), "w": (x0, cy)}.get(pref)
        if edge is not None:
            return edge
        # reading order, not topmost
        first = reading_order_first(hits, fb)
        return self._hit_anchor_pt(first, fb)
