# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Reader-correction collector, opt-in local-only never phones home.

import os
import json
import zipfile
import hashlib
from datetime import datetime

import fitz

from PySide6.QtCore import QUrl, QSize, Qt
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QMessageBox, QDialog, QVBoxLayout, QHBoxLayout,
                               QTableWidget, QTableWidgetItem, QPushButton,
                               QLabel, QHeaderView, QAbstractItemView)

from . import corrections
from . import common
from .dialogs import BubbleDialog
from .i18n import tr


def _summ(rows):
    parts = []
    for r in rows or ():
        if not r:
            continue
        seg = str(r.get("type") or "")
        if r.get("feature"):
            seg += " " + str(r["feature"])
        elif r.get("nominal") is not None:
            seg += " %g" % r["nominal"]
        if r.get("tol_sym") is not None:
            seg += u" ±%g" % r["tol_sym"]
        seg = seg.strip()
        if seg:
            parts.append(seg)
    return "; ".join(parts)


class CorrectionsMixin:
    def report_bad_read(self):
        if not self.cfg.get("collect_corrections"):
            QMessageBox.information(
                self, tr('Reader corrections'),
                tr('Enable "Collect reader corrections" in '
                   'Settings > Vision first.'))
            return
        self._correct_mode = True
        self._scan_drag = None
        self.set_status(tr('Drag a box around the misread callout'))
        self.redraw_overlay()

    def _finish_correct_drag(self, sp):
        drag = self._scan_drag
        self._correct_mode = None
        self._scan_drag = None
        self.redraw_overlay()
        if drag is None:
            return
        rect = (drag[0], drag[1], sp.x(), sp.y())
        if abs(rect[2] - rect[0]) < 5 or abs(rect[3] - rect[1]) < 5:
            return
        page_rect = self._scene_rect_to_pdf(rect)
        self._collect_correction(page_rect, reader=None)

    def report_misread(self, d):
        if not self.cfg.get("collect_corrections"):
            QMessageBox.information(
                self, tr('Reader corrections'),
                tr('Enable "Collect reader corrections" in '
                   'Settings > Vision first.'))
            return
        rect = d.get("rect")
        if not rect:
            ax, ay = d.get("x", 0.0), d.get("y", 0.0)
            rect = self._capture_box(ax, ay)
        reader = {k: d.get(k) for k in
                  ("type", "feature", "nominal", "tol_sym",
                   "tol_max", "tol_min", "datums", "tier")
                  if d.get(k) is not None}
        self._collect_correction(tuple(rect), reader=reader)

    def _collect_correction(self, rect, reader):
        at = tuple(self.dlg_pos) if self.dlg_pos else None
        nxt = self.store.next_number(self.page_i)
        dlg = BubbleDialog(self, nxt, last=self.last, at=at, cfg=self.cfg,
                           leader_default=self.use_leaders())
        dlg.exec()
        if not dlg.result_rows:
            return
        rows = dlg.result_rows
        x0, y0, x1, y1 = rect
        png, cw, ch = self._crop_png(rect)
        rec = {
            "schema": corrections.SCHEMA,
            "version": common.VERSION,
            "page": self.page_i,
            "rect": [x0, y0, x1, y1],
            "crop": {"w": cw, "h": ch, "dpi": 300},
            "labels": {
                "region_class": corrections.region_class_for(rows),
                "symbols": corrections.symbols_for(rows),
            },
            "correct": rows,
            "reader": reader,
            "drawing": self._drawing_tag(),
        }
        if png:
            rec["crop_sha"] = hashlib.sha1(png).hexdigest()[:16]
        stamp = self._corr_stamp()
        base = corrections.write_correction(
            corrections.corrections_dir(self.cfg), rec, png, stamp)
        if base:
            self.set_status(tr('correction saved'))
        else:
            self.set_status(tr('could not save correction'))

    def _crop_png(self, rect):
        try:
            page = self.doc[self.page_i]
            x0, y0, x1, y1 = rect
            try:
                prot = int(getattr(page, "rotation", 0) or 0) % 360
            except (TypeError, ValueError):
                prot = 0
            if prot:
                from .scanpos import xform_rect
                x0, y0, x1, y1 = xform_rect(
                    page.derotation_matrix, x0, y0, x1, y1)
            s = 300.0 / 72.0
            clip = fitz.Rect(x0, y0, x1, y1)
            pix = page.get_pixmap(clip=clip, matrix=fitz.Matrix(s, s),
                                  alpha=False)
            return pix.tobytes("png"), pix.width, pix.height
        except Exception:
            return None, 0, 0

    def _corr_stamp(self):
        n = getattr(self, "_corr_seq", 0) + 1
        self._corr_seq = n
        return "%s-%03d" % (datetime.now().strftime("%Y%m%d-%H%M%S"), n)

    def _drawing_tag(self):
        tag = getattr(self, "_drawing_id", None)
        if not tag:
            import uuid
            tag = uuid.uuid4().hex[:12]
            self._drawing_id = tag
        return tag

    def review_corrections(self):
        win = getattr(self, "_corr_win", None)
        if win is not None:
            win.raise_()
            win.activateWindow()
            self._corr_fill()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr('Review corrections'))
        lay = QVBoxLayout(dlg)
        self._corr_head = QLabel("")
        self._corr_head.setStyleSheet("font-weight:bold;")
        lay.addWidget(self._corr_head)
        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels(
            [tr('Crop'), tr('Region'), tr('Correct'), tr('Reader was')])
        tbl.setIconSize(QSize(150, 88))
        tbl.verticalHeader().setDefaultSectionSize(92)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._corr_tbl = tbl
        lay.addWidget(tbl)
        bw = QHBoxLayout()
        b_del = QPushButton(tr('Delete selected'))
        b_del.clicked.connect(self._corr_delete_selected)
        b_folder = QPushButton(tr('Open folder'))
        b_folder.clicked.connect(self._corr_open_folder)
        b_exp = QPushButton(tr('Export...'))
        b_exp.clicked.connect(self.export_corrections)
        b_close = QPushButton(tr('Close'))
        b_close.clicked.connect(dlg.reject)
        bw.addWidget(b_del)
        bw.addWidget(b_folder)
        bw.addStretch(1)
        bw.addWidget(b_exp)
        bw.addWidget(b_close)
        lay.addLayout(bw)
        dlg.resize(780, 500)
        dlg.finished.connect(lambda _r: setattr(self, "_corr_win", None))
        self._corr_win = dlg
        self._corr_fill()
        dlg.show()

    def _load_records(self):
        dirp = corrections.corrections_dir(self.cfg)
        out = []
        for stamp in corrections.list_corrections(dirp):
            try:
                rec = json.load(open(os.path.join(dirp, stamp + ".json"),
                                     encoding="utf-8"))
            except (OSError, ValueError):
                continue
            pp = os.path.join(dirp, stamp + ".png")
            out.append((stamp, rec, pp if os.path.isfile(pp) else None))
        return out

    def _corr_fill(self):
        recs = self._load_records()
        self._corr_head.setText(tr('%d corrections collected') % len(recs))
        tbl = self._corr_tbl
        tbl.setRowCount(0)
        for stamp, rec, pp in recs:
            i = tbl.rowCount()
            tbl.insertRow(i)
            thumb = QTableWidgetItem()
            if pp:
                pm = QPixmap()
                pm.load(pp)
                thumb.setIcon(QIcon(pm))
            thumb.setData(Qt.UserRole, stamp)
            tbl.setItem(i, 0, thumb)
            tbl.setItem(i, 1, QTableWidgetItem(
                (rec.get("labels") or {}).get("region_class", "")))
            tbl.setItem(i, 2, QTableWidgetItem(_summ(rec.get("correct"))))
            rd = [rec["reader"]] if rec.get("reader") else []
            tbl.setItem(i, 3, QTableWidgetItem(_summ(rd)))

    def _corr_delete_selected(self):
        tbl = self._corr_tbl
        stamps = [tbl.item(r.row(), 0).data(Qt.UserRole)
                  for r in tbl.selectionModel().selectedRows()]
        if not stamps:
            return
        dirp = corrections.corrections_dir(self.cfg)
        for s in stamps:
            for ext in (".json", ".png"):
                try:
                    os.remove(os.path.join(dirp, s + ext))
                except OSError:
                    pass
        self._corr_fill()

    def _corr_open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(
            corrections.corrections_dir(self.cfg)))

    def export_corrections(self):
        dirp = corrections.corrections_dir(self.cfg)
        stamps = corrections.list_corrections(dirp)
        if not stamps:
            QMessageBox.information(
                self, tr('Export corrections'),
                tr('No corrections collected yet.'))
            return
        zpath = self._zip_corrections(dirp)
        if not zpath:
            QMessageBox.warning(
                self, tr('Export corrections'),
                tr('Could not write the zip.'))
            return
        self._offer_submit(dirp, zpath, len(stamps))

    @staticmethod
    def _zip_corrections(dirp):
        zpath = dirp.rstrip(os.sep) + ".zip"
        try:
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                for name in sorted(os.listdir(dirp)):
                    if name.endswith((".json", ".png")):
                        zf.write(os.path.join(dirp, name), name)
            return zpath
        except OSError:
            return None

    def _offer_submit(self, dirp, zpath, count):
        box = QMessageBox(self)
        box.setWindowTitle(tr('Export corrections'))
        box.setText(tr('Saved %d correction(s) to a zip. Nothing is sent '
                       'automatically; attach the zip yourself.') % count)
        box.setInformativeText("%s\n%s" % (tr('Zip:'), zpath))
        b_folder = box.addButton(tr('Open folder'), QMessageBox.ActionRole)
        b_issue = box.addButton(tr('Open GitHub issue'),
                                QMessageBox.ActionRole)
        email = str(self.cfg.get("corrections_email") or "").strip()
        b_mail = (box.addButton(tr('Email us'), QMessageBox.ActionRole)
                  if email else None)
        box.addButton(QMessageBox.Close)
        box.exec()
        clicked = box.clickedButton()
        import webbrowser
        if clicked is b_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(dirp))
        elif clicked is b_issue:
            url = str(self.cfg.get("corrections_github_url") or "").strip()
            if url:
                webbrowser.open(url)
        elif b_mail is not None and clicked is b_mail:
            webbrowser.open("mailto:" + email)
