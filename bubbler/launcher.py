# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# App entry + drawing picker.

import os
import sys
import json

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                               QLabel, QFileDialog, QDialog, QListWidget,
                               QListWidgetItem, QPushButton, QMessageBox)

from .common import APP_NAME, qc_path
from .config import load_cfg, save_cfg
from .sheet import ensure_xlsx
from .icons import make_pixmap
from .theme import OFFICE, apply_office_theme
from .app import MainWindow
from .i18n import tr


def _pdf_status(pdf):
    n = saved = 0
    try:
        with open(qc_path(pdf, "_bubbles.json"), "r", encoding="utf-8") as f:
            ledger = json.load(f).get("ledger", [])
        n = len(ledger)
        saved = sum(1 for d in ledger if d.get("sheet_row") is not None)
    except Exception:
        pass
    return n, saved, os.path.isfile(qc_path(pdf, "_Inspection.xlsx"))


def _recent_row_widget(pdf):
    n, saved, has_sheet = _pdf_status(pdf)
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(10, 6, 10, 6)
    row.setSpacing(10)

    txt = QWidget()
    tv = QVBoxLayout(txt)
    tv.setContentsMargins(0, 0, 0, 0)
    tv.setSpacing(1)
    name = QLabel(os.path.basename(pdf))
    name.setStyleSheet("font-weight:bold; font-size:10pt; color:%s;"
                       % OFFICE["text"])
    folder = QLabel(os.path.dirname(pdf) or "-")
    folder.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["muted"])
    tv.addWidget(name)
    tv.addWidget(folder)
    row.addWidget(txt, 1)

    if n:
        unsaved = n - saved
        label = (tr('%d bubble') if n == 1 else tr('%d bubbles')) % n
        if unsaved:
            label += " - " + tr('%d unsaved') % unsaved
        chip_bg, chip_fg, chip_bd = "#dbe7f8", OFFICE["accent"], "#9bbce6"
    else:
        label = tr('no bubbles yet')
        chip_bg, chip_fg, chip_bd = "#e6eaf1", OFFICE["muted"], "#cdd5e2"
    chip = QLabel(label)
    chip.setStyleSheet(
        "background:%s; color:%s; border:1px solid %s; border-radius:9px;"
        "padding:2px 10px; font-size:8pt; font-weight:bold;"
        % (chip_bg, chip_fg, chip_bd))
    row.addWidget(chip, 0, Qt.AlignVCenter)

    if has_sheet:
        sheet_ic = QLabel()
        sheet_ic.setPixmap(make_pixmap("check", color=OFFICE["green"], px=12))
        row.addWidget(sheet_ic, 0, Qt.AlignVCenter)
        sheet = QLabel(tr('sheet'))
        sheet.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["green"])
    else:
        sheet = QLabel(tr('no sheet'))
        sheet.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["muted"])
    row.addWidget(sheet, 0, Qt.AlignVCenter)
    w.setToolTip(pdf)
    return w


def _pdf_from_drop(mime):
    if not mime.hasUrls():
        return ""
    for u in mime.urls():
        p = u.toLocalFile()
        if p.lower().endswith(".pdf") and os.path.isfile(p):
            return p
    return ""


class _DropDialog(QDialog):
    dropped = ""

    def dragEnterEvent(self, e):
        if _pdf_from_drop(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        p = _pdf_from_drop(e.mimeData())
        if p:
            self.dropped = p
            self.accept()


def _pick_pdf(cfg):
    initdir = cfg.get("last_dir") or os.path.expanduser("~")
    recent = [p for p in (cfg.get("recent") or []) if os.path.isfile(p)]
    if not recent:
        path, _ = QFileDialog.getOpenFileName(
            None, tr('PDF print'), initdir, "PDF (*.pdf)")
        return path
    dlg = _DropDialog()
    dlg.setAcceptDrops(True)
    dlg.setWindowTitle(tr('%s - open') % APP_NAME)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)

    title = QLabel(tr('Open a drawing'))
    title.setStyleSheet("font-size:14pt; font-weight:bold; color:%s;"
                        % OFFICE["text"])
    lay.addWidget(title)
    sub = QLabel(tr("Pick a recent drawing or browse for a PDF. The chip shows "
                    "how many bubbles it already has."))
    sub.setStyleSheet("color:%s; font-size:9pt;" % OFFICE["muted"])
    sub.setWordWrap(True)
    lay.addWidget(sub)

    lst = QListWidget()
    lst.setAlternatingRowColors(True)
    lst.setIconSize(QSize(0, 0))
    for p in recent:
        it = QListWidgetItem()
        rw = _recent_row_widget(p)
        it.setSizeHint(rw.sizeHint())
        it.setData(Qt.UserRole, p)
        lst.addItem(it)
        lst.setItemWidget(it, rw)
    lst.setCurrentRow(0)
    lay.addWidget(lst)
    sel = {"path": ""}

    def use():
        it = lst.currentItem()
        if it:
            sel["path"] = it.data(Qt.UserRole)
        dlg.accept()

    def browse():
        p, _ = QFileDialog.getOpenFileName(
            dlg, tr('PDF print'), initdir, "PDF (*.pdf)")
        if p:
            sel["path"] = p
            dlg.accept()

    lst.itemDoubleClicked.connect(lambda _i: use())
    bw = QWidget()
    bl = QHBoxLayout(bw)
    bl.setContentsMargins(0, 0, 0, 0)
    b_browse = QPushButton(tr('Browse...'))
    b_browse.clicked.connect(browse)
    b_cancel = QPushButton(tr('Cancel'))
    b_cancel.clicked.connect(dlg.reject)
    b_open = QPushButton(tr('Open'))
    b_open.clicked.connect(use)
    b_open.setDefault(True)
    bl.addWidget(b_browse)
    bl.addStretch(1)
    bl.addWidget(b_cancel)
    bl.addWidget(b_open)
    lay.addWidget(bw)
    dlg.resize(620, 320)
    dlg.exec()
    return dlg.dropped or sel["path"]


def _selftest():
    """fail if any pass is down."""
    from . import vision
    av = vision.available({})
    need = ("geometry", "ocr", "symbols", "region")
    for k in ("geometry", "ocr", "symbols", "region", "vlm"):
        print("%-9s %s" % (k, "ok" if av.get(k) else "MISSING"))
    for msg in (av.get("reasons") or {}).values():
        print("  ! " + msg)
    missing = [k for k in need if not av.get(k)]
    if missing:
        print("selftest FAILED: " + ", ".join(missing))
        return 1
    print("selftest OK")
    return 0


def main():
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    cfg = load_cfg()
    app = QApplication(sys.argv)
    apply_office_theme(app)
    pdf = sys.argv[1] if len(sys.argv) > 1 else _pick_pdf(cfg)
    if not pdf:
        sys.exit("No PDF.")
    sub = cfg.get("qc_subdir", "qc")
    default_xlsx = qc_path(pdf, "_Inspection.xlsx", subdir=sub)
    xlsx = sys.argv[2] if len(sys.argv) > 2 else default_xlsx
    d = os.path.dirname(xlsx)
    if d and not os.path.isdir(d):
        try:
            os.makedirs(d, exist_ok=True)
        except PermissionError:
            xlsx = qc_path(pdf, "_Inspection.xlsx", subdir="")
    try:
        created = ensure_xlsx(xlsx, str(cfg.get("company") or ""),
                              sheet_lang=cfg.get("sheet_lang", "both"))
    except RuntimeError as e:
        QMessageBox.critical(None, tr('Template'), str(e))
        xlsx, _ = QFileDialog.getOpenFileName(
            None, tr('Inspection sheet'),
            os.path.dirname(pdf), "Excel (*.xlsx)")
        if not xlsx:
            sys.exit("No xlsx.")
        created = False
    cfg["last_dir"] = os.path.dirname(pdf)
    rec = [pdf] + [p for p in (cfg.get("recent") or []) if p != pdf]
    cfg["recent"] = rec[:8]
    save_cfg(cfg)
    win = MainWindow(pdf, xlsx, cfg=cfg)
    win.show()
    if created:
        win.set_status(tr('created: %s') % os.path.basename(xlsx))
    sys.exit(app.exec())
