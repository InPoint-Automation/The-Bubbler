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
from .common import GROUP_OF
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
        if rx1 - rx0 < 3 and ry1 - ry0 < 3:
            mx, my = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0
            rx0, ry0, rx1, ry1 = self._capture_box(mx, my)
        # read off-thread
        rect = (rx0, ry0, rx1, ry1)
        sel_rect = (rx0 - 2, ry0 - 2, rx1 + 2, ry1 + 2)
        want_hits = (not self.measure_mode) and (self._hdr_focus is None)
        res = self._run_capture(self.page_i, rect, sel_rect,
                                want_meta=want_hits, want_hits=want_hits)
        if res is None:    # cancelled / failed
            return
        sel = res["sel"]
        if not sel:
            self.set_status("no text here / brak tekstu")
            return
        text = res["text"]
        QApplication.clipboard().setText(" ".join(text.split()))
        if self._hdr_focus is not None:
            try:
                self._hdr_focus.setText(" ".join(text.split()))
            except RuntimeError:
                self._hdr_focus = None
            self.set_status("copied / skopiowano: %s" % text[:50])
            return
        if not self.measure_mode:
            # meta region, no bubble
            meta = res["meta"]
            if meta:
                en, pl = {"gentol_block": ("general tolerance",
                                           "tolerancja ogólna"),
                          "note": ("note", "uwaga")}.get(meta, (meta, meta))
                self.set_status("%s - no bubble (Alt-click to add) / "
                                "%s - bez bąbla (Alt-klik)" % (en, pl))
                return
            hits = res["hits"] or []
            if not hits:
                hits = scan_parse(scan_normalize(text))
                for h in hits:
                    h["rect"] = (rx0, ry0, rx1, ry1)
            if not hits:
                mnum = re.search(r"\d+(?:[.,]\d+)?", scan_normalize(text))
                if mnum:
                    hits = [{"tp": "LINEAR", "sb": "BARE",
                             "v": mnum.group(0), "t": None, "raw": text,
                             "rect": (rx0, ry0, rx1, ry1)}]
            gtols = self._page_gtols()
            if len(hits) == 1:
                hr = hits[0].get("rect") or (rx0, ry0, rx1, ry1)
                ax, ay = self._hit_anchor_pt(hits[0], (rx0, ry0, rx1, ry1))
                self.set_status("captured / przechwycono: %s" % text[:50])
                self._new_bubble_at(ax, ay, None,
                                    prefill=self._capture_prefill(hits[0],
                                                                  gtols),
                                    rect=hr)
                return
            if len(hits) > 1:
                cx, cy = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0
                m = QMenu(self)
                # confirm before spawning rows
                m.addAction(
                    "Review %d callouts... / Przegląd" % len(hits),
                    lambda: ScanReview(
                        self, [(self.page_i, h) for h in hits],
                        {self.page_i: gtols}, False).exec())
                m.addAction(
                    "All %d as sub-rows / Wszystkie jako podwiersze"
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
                self.set_status("captured %d callouts / przechwycono"
                                % len(hits))
                m.exec(gpos.toPoint())
                return
        self.set_status("copied / skopiowano: %s" % text[:50])

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
            t = self.last.get("type", "dim")
            rw["type"] = t
            rw["group"] = GROUP_OF.get(t, rw.get("group", ""))
            rw["tier"] = self.last.get("tier", "")
            nom = rw.get("nominal")
            if nom is not None and t.startswith(("hole", "thru")):
                rw["feature"] = u"Ø%.3f" % nom
                # pin set at commit
        return rw

    def _capture_box(self, cx, cy):
        """Sample box around a single-click point, sized by capture_radius."""
        try:
            hw = float(self.cfg.get("capture_radius",
                                    CFG_DEFAULT["capture_radius"]))
        except (TypeError, ValueError):
            hw = CFG_DEFAULT["capture_radius"]
        hw = max(2.0, hw)
        hh = hw * 0.75
        return cx - hw, cy - hh, cx + hw, cy + hh

    def _aug_words(self, page_i=None):
        """Page words plus vision-recovered symbols, cached per page."""
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
            # Report what vision changed.
            added = len(words) - len(base)
            edited = sum(1 for a, b in zip(words, base) if a[4] != b[4])
            print("bubbler.vision: page %d: %d text words, +%d recovered, "
                  "%d edited" % (page_i + 1, len(base), max(0, added), edited),
                  file=sys.stderr)
            cache[page_i] = words
        return cache[page_i]

    def _run_capture(self, page_i, rect, sel_rect, want_meta, want_hits):
        """Run capture passes off-thread so UI never freezes."""
        if getattr(self, "_cap_loop", None) is not None:
            return None    # capture already in flight
        self._cap_loop = QEventLoop()
        self._cap_state = {}
        dlg = QProgressDialog(
            tr("Reading callout... / Odczyt..."), tr("Cancel / Anuluj"),
            0, 0, self)
        dlg.setWindowTitle(tr("Capture / Przechwyć"))
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.reset()    # fast read never flashes it
        dlg.canceled.connect(self._cap_cancel)
        self._cap_dlg = dlg
        # bind by value, may be None by now
        QTimer.singleShot(
            200, lambda st=self._cap_state, d=dlg:
            None if "done" in st else d.show())
        task = scanworker.CaptureTask(self.pdf_path, copy.deepcopy(self.cfg),
                                      page_i, rect, sel_rect, want_meta,
                                      want_hits)
        task.signals.done.connect(self._cap_done)
        task.signals.failed.connect(self._cap_failed)
        QThreadPool.globalInstance().start(task)
        self._cap_loop.exec()
        # drop handler so completion isn't a cancel
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
            self.set_status("capture cancelled / anulowano")
            return None
        if "error" in state:
            QMessageBox.warning(self, "Capture / Przechwyć",
                                "Capture failed / Nieudane:\n%s"
                                % state["error"])
            return None
        r = state.get("result")
        if r and r.get("vwords"):
            self.__dict__.setdefault("_vword_cache", {}).update(r["vwords"])
        return r

    def _cap_done(self, r):
        if self._cap_state is None:    # late delivery
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
        # only an in-flight read counts
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
