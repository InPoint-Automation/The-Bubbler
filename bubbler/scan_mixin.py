# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Scan mixin. Region select -> off-thread OCR/VLM -> ScanReview.

import copy

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QProgressDialog, QMessageBox

from . import scanworker
from .scanreview import ScanReview
from .i18n import tr


class ScanMixin:
    def scan_page(self, all_pages=False):
        # all-pages skips region boxes
        if all_pages:
            self._run_scan(all_pages=True)
            return
        self._begin_scan_region()

    def _begin_scan_region(self):
        self._scan_inc = None
        self._scan_exc = None
        self._scan_drag = None
        QMessageBox.information(
            self, tr("Scan / Skanuj"),
            tr("Drag a GREEN box around the area to scan, then a RED box "
               "around any print detail to ignore. Enter skips a box, Esc "
               "cancels. / Przeciągnij ZIELONE pole wokół obszaru do "
               "skanowania, potem CZERWONE wokół szczegółu do pominięcia. "
               "Enter pomija, Esc anuluje."))
        self._scan_region_mode = "include"
        self.set_status(
            "Scan: drag a GREEN box around the area to scan / "
            "Skanuj: zaznacz ZIELONE pole wokół obszaru")
        self.redraw_overlay()

    def _finish_scan_drag(self, sp):
        if self._scan_drag is None:
            return
        x0, y0, _, _ = self._scan_drag
        rect = (x0, y0, sp.x(), sp.y())
        self._scan_drag = None
        if abs(rect[2] - rect[0]) < 5 or abs(rect[3] - rect[1]) < 5:
            self.redraw_overlay()    # click, not box
            return
        if self._scan_region_mode == "include":
            self._scan_inc = rect
            self._scan_region_mode = "exclude"
            self.set_status(
                "Scan: drag a RED box to ignore, or Enter to skip / "
                "Skanuj: zaznacz CZERWONE pole do pominięcia lub Enter")
            self.redraw_overlay()
        else:
            self._scan_exc = rect
            self._run_scan_regions()

    def _cancel_scan_region(self):
        self._scan_region_mode = None
        self._scan_inc = self._scan_exc = self._scan_drag = None
        self.redraw_overlay()
        self.set_status("scan cancelled / anulowano skanowanie")

    def _scene_to_pdf(self, x, y):
        return self.viewport.scene_to_page(x, y)

    def _scene_rect_to_pdf(self, rect):
        ax, ay = self._scene_to_pdf(rect[0], rect[1])
        bx, by = self._scene_to_pdf(rect[2], rect[3])
        return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))

    def _run_scan_regions(self):
        inc = self._scene_rect_to_pdf(self._scan_inc) if self._scan_inc else None
        exc = self._scene_rect_to_pdf(self._scan_exc) if self._scan_exc else None
        self._scan_region_mode = None
        self._scan_inc = self._scan_exc = self._scan_drag = None
        self.redraw_overlay()    # clear highlights pre-dialog
        self._run_scan(all_pages=False, inc=inc, exc=exc)

    @staticmethod
    def _hit_in_region(h, inc, exc):
        rc = h.get("rect")
        if not rc:
            return inc is None    # no position info
        cx = (rc[0] + rc[2]) / 2.0
        cy = (rc[1] + rc[3]) / 2.0
        if inc is not None and not (inc[0] <= cx <= inc[2]
                                    and inc[1] <= cy <= inc[3]):
            return False
        if exc is not None and (exc[0] <= cx <= exc[2]
                                and exc[1] <= cy <= exc[3]):
            return False
        return True

    def _run_scan(self, all_pages=False, inc=None, exc=None):
        # one scan at a time
        if getattr(self, "_scan_task", None) is not None:
            return
        pages = (list(range(self.doc.page_count)) if all_pages else [self.page_i])
        self._scan_ctx = (inc, exc, all_pages)
        self._scan_cancel = False
        dlg = QProgressDialog(
            tr("Scanning... / Skanowanie..."), tr("Cancel / Anuluj"),
            0, len(pages), self)
        dlg.setWindowTitle(tr("Scan / Skanuj"))
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        dlg.canceled.connect(self._cancel_scan)
        self._scan_dlg = dlg
        task = scanworker.ScanTask(self.pdf_path, copy.deepcopy(self.cfg),
                                   pages, lambda: self._scan_cancel)
        task.signals.progress.connect(self._on_scan_progress)
        task.signals.done.connect(self._on_scan_done)
        task.signals.failed.connect(self._on_scan_failed)
        self._scan_task = task
        QThreadPool.globalInstance().start(task)

    def _cancel_scan(self):
        # worker polls between pages
        self._scan_cancel = True

    def _teardown_scan(self):
        self._scan_task = None
        dlg = getattr(self, "_scan_dlg", None)
        if dlg is not None:
            dlg.close()
            self._scan_dlg = None

    def _on_scan_progress(self, done, total):
        dlg = getattr(self, "_scan_dlg", None)
        if dlg is not None:
            dlg.setValue(done)

    def _on_scan_failed(self, msg):
        self._teardown_scan()
        QMessageBox.warning(self, "Scan / Skanuj",
                            "Scan failed / Skan nieudany:\n%s" % msg)

    def _on_scan_done(self, result):
        self._teardown_scan()
        if result is None:    # cancelled
            self.set_status("scan cancelled / anulowano skanowanie")
            return
        # warm word cache so accept skips re-run
        if result.get("vwords"):
            self.__dict__.setdefault("_vword_cache", {}).update(result["vwords"])
        inc, exc, all_pages = self._scan_ctx
        found = result["found"]
        gtols = result["gtols"]
        if not result["any_text"]:
            QMessageBox.information(self, "Scan / Skanuj",
                                    "No text layer / Brak warstwy tekstu.")
            return
        if not found:
            QMessageBox.information(self, "Scan / Skanuj",
                                    "No callouts recognized / Nie rozpoznano.")
            return
        if inc is not None or exc is not None:
            found = [(pg, h) for (pg, h) in found
                     if self._hit_in_region(h, inc, exc)]
            if not found:
                QMessageBox.information(
                    self, "Scan / Skanuj",
                    "No callouts in the selected area / "
                    "Brak elementów w zaznaczonym obszarze.")
                return
        ScanReview(self, found, gtols, all_pages).exec()
