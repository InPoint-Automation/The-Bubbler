# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Click/drag callout capture, mixed into MainWindow.

import copy
import re
import sys

from PySide6.QtCore import Qt, QEventLoop, QTimer, QThreadPool
from PySide6.QtWidgets import (QApplication, QMenu, QMessageBox,
                               QProgressDialog)

from . import vision, scanworker
from .scanreview import ScanReview
from .scanlib import (scan_to_row, scan_parse, scan_normalize,
                      parse_general_tols)
from .scanpos import page_words
from .config import CFG_DEFAULT
from .i18n import tr


class CaptureMixin:
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
        if not was_drag:
            mx, my = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0
            rx0, ry0, rx1, ry1 = self._capture_box(mx, my)
        rect = (rx0, ry0, rx1, ry1)
        sel_rect = (rx0 - 2, ry0 - 2, rx1 + 2, ry1 + 2)
        want_hits = (not self.measure_mode) and (self._hdr_focus is None)
        # drag
        force_read = None
        if was_drag and self.cfg.get("capture_drag_ocr", True):
            force_read = "vlm" if self.cfg.get("vision_vlm") else "ocr"
        res = self._run_capture(self.page_i, rect, sel_rect,
                                want_meta=want_hits, want_hits=want_hits,
                                force_read=force_read)
        if res is None:
            return
        sel = res["sel"]
        if not sel:
            self.set_status(tr('no text here'))
            return
        text = res["text"]
        QApplication.clipboard().setText(" ".join(text.split()))
        if self._hdr_focus is not None:
            try:
                self._hdr_focus.setText(" ".join(text.split()))
            except RuntimeError:
                self._hdr_focus = None
            self.set_status(tr('copied: %s') % text[:50])
            return
        if not self.measure_mode:
            meta = res["meta"]
            if meta:
                name = {"gentol_block": tr('general tolerance'),
                        "note": tr('note')}.get(meta, tr(meta))
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
            # drag over bubbles
            covered = self._bubbles_in_rect((rx0, ry0, rx1, ry1)) \
                if was_drag else []
            if covered and hits:
                rows = [self._capture_full_row(h, gtols) for h in hits]
                fb = (rx0, ry0, rx1, ry1)
                ax, ay = self._dir_anchor(hits, fb)     # anchor on exit side
                self._regroup_capture(covered, rows, ax, ay, rect=fb)
                return
            if len(hits) == 1:
                hr = hits[0].get("rect") or (rx0, ry0, rx1, ry1)
                ax, ay = self._hit_anchor_pt(hits[0], (rx0, ry0, rx1, ry1))
                self.set_status(tr('captured: %s') % text[:50])
                self._new_bubble_at(ax, ay, None,
                                    prefill=self._capture_prefill(hits[0],
                                                                  gtols),
                                    rect=hr)
                return
            if len(hits) > 1:
                cx, cy = self._dir_anchor(hits, (rx0, ry0, rx1, ry1))
                m = QMenu(self)
                m.addAction(
                    tr('Review %d callouts...') % len(hits),
                    lambda: ScanReview(
                        self, [(self.page_i, h) for h in hits],
                        {self.page_i: gtols}, False).exec())
                m.addAction(
                    tr('All %d as sub-rows')
                    % len(hits),
                    lambda: self._balloon_from_rows(
                        [self._capture_full_row(h, gtols) for h in hits],
                        cx, cy, rect=(rx0, ry0, rx1, ry1)))
                m.addSeparator()
                for h in hits:
                    ax, ay = self._hit_anchor_pt(h, (rx0, ry0, rx1, ry1))
                    hr = h.get("rect") or (rx0, ry0, rx1, ry1)
                    label = "%s  %s" % ("dim" if h.get("sb") == "BARE"
                                        else h["tp"], h["v"])
                    m.addAction(label,
                                lambda h=h, ax=ax, ay=ay, hr=hr:
                                self._new_bubble_at(
                                    ax, ay, None,
                                    prefill=self._capture_prefill(h, gtols),
                                    rect=hr))
                self.set_status(tr('captured %d callouts')
                                % len(hits))
                m.exec(gpos.toPoint())
                return
        self.set_status(tr('copied: %s') % text[:50])

    def _page_gtols(self, page_i=None):
        if page_i is None:
            page_i = self.page_i
        if not hasattr(self, "_gtol_cache"):
            self._gtol_cache = {}
        if page_i not in self._gtol_cache:
            try:
                self._gtol_cache[page_i] = parse_general_tols(
                    self.doc[page_i].get_text("text"))
            except Exception:
                self._gtol_cache[page_i] = {}
        return self._gtol_cache[page_i]

    def _capture_prefill(self, h, gtols):
        rw = scan_to_row(h)
        self._apply_general_tol(rw, h, gtols)
        if h.get("sb") == "BARE":
            return {"nominal": rw.get("nominal"),
                    "tol_sym": rw.get("tol_sym")}
        return rw

    def _capture_full_row(self, h, gtols):
        rw = scan_to_row(h)
        self._apply_general_tol(rw, h, gtols)
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
                     force_read=None):
        if getattr(self, "_cap_loop", None) is not None:
            return None
        self._cap_loop = QEventLoop()
        self._cap_state = {}
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
        task = scanworker.CaptureTask(self.pdf_path, copy.deepcopy(self.cfg),
                                      page_i, rect, sel_rect, want_meta,
                                      want_hits, force_read=force_read)
        task.signals.done.connect(self._cap_done)
        task.signals.failed.connect(self._cap_failed)
        QThreadPool.globalInstance().start(task)
        self._cap_loop.exec()
        try:
            dlg.canceled.disconnect(self._cap_cancel)
        except (RuntimeError, TypeError):
            pass
        dlg.close()
        state = self._cap_state
        self._cap_loop = None
        self._cap_state = None
        self._cap_dlg = None
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
