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

from . import vision, scanworker
from .scanreview import FCF_SUSPECT, ScanReview
from .scanlib import (scan_to_row, scan_parse, scan_normalize,
                      parse_general_tols, gentol_exempt,
                      inherit_gtols)
from .scanpos import page_words
from .config import CFG_DEFAULT
from .i18n import tr


def _suspect_of(hits):
    """Suspect review flags hits carry."""
    bad = []
    for h in hits or ():
        for c in h.get("fcf_flags") or ():
            if c in FCF_SUSPECT and c not in bad:
                bad.append(c)
    return ", ".join(bad)


class CaptureMixin:
    def _balloon_rows_warned(self, rows, cx, cy, rect, doubt):
        """Balloon rows and warn when reader doubted one."""
        self._balloon_from_rows(rows, cx, cy, rect=rect)
        if doubt:
            self.set_status(tr('Uncertain frame read') + ": " + doubt)

    def _active_hdr_field(self):
        """Header field awaiting capture, only while its dialog is on screen."""
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
            # snap to callout else blind box
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
        # OCR when text layer empty
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
                mnum = re.search(r"\d+(?:[.,]\d+)?", scan_normalize(text))
                if mnum:
                    hits = [{"tp": "LINEAR", "sb": "BARE",
                             "v": mnum.group(0), "t": None, "raw": text,
                             "rect": (rx0, ry0, rx1, ry1)}]
            gtols = self._page_gtols()
            doubt = _suspect_of(hits)
            if not hits and snapped:
                # unparseable callout: bubble the region
                cls = self._region_cls_for((rx0, ry0, rx1, ry1))
                row = self._region_only_row(cls, text, (rx0, ry0, rx1, ry1),
                                            gtols)
                if row is not None:
                    if self.cfg.get("click_auto_bubble", True):
                        self._safe_balloon([row], (rx0 + rx1) / 2.0, ry0,
                                           (rx0, ry0, rx1, ry1), "")
                        self.set_status(tr('bubbled %s')
                                        % (cls or tr('callout')))
                    else:                    # preview/edit
                        self._new_bubble_at((rx0 + rx1) / 2.0, ry0, None,
                                            prefill=row,
                                            rect=(rx0, ry0, rx1, ry1))
                    return
            covered = self._bubbles_in_rect((rx0, ry0, rx1, ry1)) \
                if was_drag else []
            if covered and hits:
                rows = [self._capture_full_row(h, gtols) for h in hits]
                fb = (rx0, ry0, rx1, ry1)
                ax, ay = self._dir_anchor(hits, fb)     # anchor on exit side
                self._regroup_capture(covered, rows, ax, ay, rect=fb)
                # FCF_SUSPECT last warn chance
                if doubt:
                    self.set_status(tr('Uncertain frame read') + ": " + doubt)
                return
            if clicked and snapped and hits:
                # dim one row, stack sub-rows
                from . import common
                cls = self._region_cls_for((rx0, ry0, rx1, ry1))
                kind = (common.CATEGORY.get(cls) or (None,))[0]
                if kind == common.KIND_ATOMIC and len(hits) > 1:
                    row = self._region_only_row(cls, text,
                                                (rx0, ry0, rx1, ry1), gtols)
                    rows = ([row] if row is not None
                            else [self._capture_full_row(hits[0], gtols)])
                else:
                    rows = [self._capture_full_row(h, gtols) for h in hits]
                ax, ay = self._dir_anchor(hits, (rx0, ry0, rx1, ry1))
                if self.cfg.get("click_auto_bubble", True):
                    self._safe_balloon(rows, ax, ay, (rx0, ry0, rx1, ry1), doubt)
                    self.set_status(tr('bubbled %s') % (cls or tr('callout')))
                else:                        # preview/edit
                    self._new_bubble_at(
                        ax, ay, None,
                        prefill=self._capture_prefill(hits[0], gtols),
                        rect=(rx0, ry0, rx1, ry1))
                return
            if len(hits) == 1:
                hr = hits[0].get("rect") or (rx0, ry0, rx1, ry1)
                ax, ay = self._hit_anchor_pt(hits[0], (rx0, ry0, rx1, ry1))
                # FCF_SUSPECT drag skips ScanReview
                bad = [c for c in (hits[0].get("fcf_flags") or ())
                       if c in FCF_SUSPECT]
                self.set_status((tr('Uncertain frame read') + ": "
                                 + ", ".join(bad) + " - " + text[:40])
                                if bad else tr('captured: %s') % text[:50])
                # clean click auto-bubbles else dialog
                if clicked and self.cfg.get("click_auto_bubble", True) \
                        and not bad:
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
                # snapped multi-hit: sub-rows, menu for drag
                if clicked and snapped \
                        and self.cfg.get("click_auto_bubble", True):
                    self._safe_balloon(
                        [self._capture_full_row(h, gtols) for h in hits],
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
                    % len(hits),
                    lambda: self._balloon_rows_warned(
                        [self._capture_full_row(h, gtols) for h in hits],
                        cx, cy, (rx0, ry0, rx1, ry1), doubt))
                m.addSeparator()
                for h in hits:
                    ax, ay = self._hit_anchor_pt(h, (rx0, ry0, rx1, ry1))
                    hr = h.get("rect") or (rx0, ry0, rx1, ry1)
                    # mark doubtful in menu
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
                    (tr('Uncertain frame read') + ": " + doubt) if doubt
                    else tr('captured %d callouts') % len(hits))
                m.exec(gpos.toPoint())
                return
        self.set_status(tr('copied: %s') % text[:50])

    def _own_gtols(self, page_i):
        """Page's OWN general-tolerance block."""
        raw = self.__dict__.setdefault("_gtol_raw", {})
        if page_i not in raw:
            try:
                raw[page_i] = parse_general_tols(
                    self.doc[page_i].get_text("text"))
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
        """Page general-tolerance block never raising."""
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
            # inherits sheet 1 block
            self._gtol_cache[page_i] = g or self._inherited_gtols(page_i)
            self.adopt_iso_class(self._gtol_cache[page_i])
        return self._gtol_cache[page_i]

    def edit_gentol(self):
        """Correct drawing general-tolerance block by hand."""
        from .gentol_edit import GentolDialog, ReapplyDialog
        from .scanlib import gentol_reapply_plan
        if self._edit_blocked():             # sealed run refuses
            return
        page_i = getattr(self, "page_i", 0)
        was = dict(self._own_gtols(page_i) or self.gtols_now())
        d = GentolDialog(self, self.gtols_now(), self.cfg, self.drawing,
                         page_i)
        if not d.exec():
            return
        block = d.result_block()
        if (self.drawing.get("gentol_user") or None) == (block or None):
            return                           # nothing changed
        self.snapshot()
        plan = gentol_reapply_plan(self.ledger, was, self.cfg, self.drawing,
                                   block, icls=self.last.get("icls"))
        if block:
            self.drawing["gentol_user"] = block
        else:
            self.drawing.pop("gentol_user", None)
        self._gtol_cache = {}                # block in force moved
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

    def _capture_prefill(self, h, gtols):
        rw = scan_to_row(h)
        self._apply_general_tol(rw, h, gtols)
        if h.get("sb") == "BARE":
            pre = {"nominal": rw.get("nominal"),
                   "tol_sym": rw.get("tol_sym")}
        else:
            pre = rw
        if gentol_exempt(h, self.cfg):
            # exempt from autofill
            pre["no_gentol"] = True
        return pre

    def _capture_full_row(self, h, gtols):
        # committed not prefilled
        rw = scan_to_row(h)
        self._apply_general_tol(rw, h, gtols,
                                iso_on=bool(self.last.get("iso_on")))
        if h.get("sb") == "BARE":
            rw["type"] = "dim"
            rw["tier"] = self.last.get("tier", "")
        return rw

    def _capture_box(self, cx, cy):
        try:
            hw = float(self.cfg.get("capture_radius",
                                    CFG_DEFAULT["capture_radius"]))
        except (TypeError, ValueError):
            hw = CFG_DEFAULT["capture_radius"]
        hw = max(2.0, hw)
        hh = hw * 0.75
        return cx - hw, cy - hh, cx + hw, cy + hh

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
        """Detected symbol glyphs on the page, [(box, glyph)]. [] on failure."""
        try:
            from . import vision
            return vision._symbol_dets(self.doc[self.page_i], self.cfg)
        except Exception:
            return []

    def _region_confirm_rank(self, b, syms):
        """0 confirmed by its glyph, 1 needs none, 2 needs one and lacks it."""
        from . import vision, common
        ci = int(b[5]) if len(b) > 5 else -1
        cls = (vision._REGION_CLASSES[ci]
               if 0 <= ci < len(vision._REGION_CLASSES) else None)
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
        """Region a click lands in, glyph-confirmed then smallest on overlap."""
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
        syms = self._region_syms()          # split overlaps
        b = min(cands, key=lambda b: (self._region_confirm_rank(b, syms),
                                      _area(b)))
        return (b[0], b[1], b[2], b[3])

    def _region_cls_for(self, rect):
        """Class of the detected region matching this snapped rect, or None."""
        from . import vision
        try:
            dets = self._region_dets()
        except Exception:
            return None
        for b in dets:
            if (abs(b[0] - rect[0]) < 1 and abs(b[1] - rect[1]) < 1
                    and abs(b[2] - rect[2]) < 1 and abs(b[3] - rect[3]) < 1):
                ci = int(b[5]) if len(b) > 5 else -1
                if 0 <= ci < len(vision._REGION_CLASSES):
                    return vision._REGION_CLASSES[ci]
        return None

    def _region_only_row(self, cls, text, rect, gtols):
        """Bubble row for a clicked region whose value would not parse."""
        from . import common
        cat = common.CATEGORY.get(cls)
        if not cat or cat[0] == common.KIND_META:
            return None
        num = re.search(r"[\d.,]*\d", scan_normalize(text or ""))
        h = {"tp": "LINEAR", "sb": "BARE", "v": num.group(0) if num else "",
             "t": None, "raw": text or "", "rect": rect}
        row = self._capture_full_row(h, gtols)
        row["type"] = cat[1]        # clicked item type
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
                words = vision.augment_words(page, list(base), self.cfg)
            except Exception as e:
                print("bubbler: vision assist skipped (%s)" % e,
                      file=sys.stderr)
            added = len(words) - len(base)
            edited = sum(1 for a, b in zip(words, base) if a[4] != b[4])
            print("bubbler.vision: page %d: %d text words, +%d recovered, "
                  "%d edited" % (page_i + 1, len(base), max(0, added), edited),
                  file=sys.stderr)
            cache[page_i] = words
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
            # always clear the guard
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
        words = self._aug_words(page_i)
        out = []
        for w in words:
            wx0, wy0, wx1, wy1 = w[0], w[1], w[2], w[3]
            ix = min(rx1, wx1) - max(rx0, wx0)
            iy = min(ry1, wy1) - max(ry0, wy0)
            if ix <= 0 or iy <= 0:
                continue
            area = max((wx1 - wx0) * (wy1 - wy0), 1e-6)
            cx, cy = (wx0 + wx1) / 2.0, (wy0 + wy1) / 2.0
            if (ix * iy) / area >= 0.30 or \
                    (rx0 <= cx <= rx1 and ry0 <= cy <= ry1):
                out.append(w)
        return out

    @staticmethod
    def _words_text(words):
        words = sorted(words, key=lambda w: (w[5], w[6], w[7]))
        lines, key = [], None
        for w in words:
            k = (w[5], w[6])
            if k != key:
                lines.append([])
                key = k
            lines[-1].append(w[4])
        return "\n".join(" ".join(l) for l in lines)

    @staticmethod
    def _hit_anchor_pt(hit, fallback_rect):
        r = hit.get("rect") or fallback_rect
        return ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0)

    def _dir_anchor(self, hits, fb):
        """Leader anchor"""
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
        top = min(hits, key=lambda h: (h.get("rect") or fb)[1])
        return self._hit_anchor_pt(top, fb)
