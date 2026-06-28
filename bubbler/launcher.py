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

from .common import APP_NAME
from .config import load_cfg, save_cfg
from .sheet import ensure_xlsx
from .icons import make_pixmap
from .theme import OFFICE, apply_office_theme
from .app import MainWindow


def _pdf_status(pdf):
    """Side-car counts: bubbles, saved rows, sheet present."""
    base = os.path.splitext(pdf)[0]
    n = saved = 0
    try:
        with open(base + "_bubbles.json", "r", encoding="utf-8") as f:
            ledger = json.load(f).get("ledger", [])
        n = len(ledger)
        saved = sum(1 for d in ledger if d.get("sheet_row") is not None)
    except Exception:
        pass
    return n, saved, os.path.isfile(base + "_Inspection.xlsx")


def _recent_row_widget(pdf):
    """Recent-list row. Name, folder, status chip."""
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
        label = "%d bubble%s" % (n, "" if n == 1 else "s")
        if unsaved:
            label += " - %d unsaved" % unsaved
        chip_bg, chip_fg, chip_bd = "#dbe7f8", OFFICE["accent"], "#9bbce6"
    else:
        label = "no bubbles yet"
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
        sheet = QLabel("sheet")
        sheet.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["green"])
    else:
        sheet = QLabel("no sheet")
        sheet.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["muted"])
    row.addWidget(sheet, 0, Qt.AlignVCenter)
    w.setToolTip(pdf)
    return w


def _pick_pdf(cfg):
    initdir = cfg.get("last_dir") or os.path.expanduser("~")
    recent = [p for p in (cfg.get("recent") or []) if os.path.isfile(p)]
    if not recent:
        path, _ = QFileDialog.getOpenFileName(
            None, "PDF print / Rysunek PDF", initdir, "PDF (*.pdf)")
        return path
    dlg = QDialog()
    dlg.setWindowTitle("%s - open / otwórz" % APP_NAME)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)

    title = QLabel("Open a drawing / Otwórz rysunek")
    title.setStyleSheet("font-size:14pt; font-weight:bold; color:%s;"
                        % OFFICE["text"])
    lay.addWidget(title)
    sub = QLabel("Pick a recent drawing or browse for a PDF. The chip shows "
                 "how many bubbles it already has.")
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
            dlg, "PDF print / Rysunek PDF", initdir, "PDF (*.pdf)")
        if p:
            sel["path"] = p
            dlg.accept()

    lst.itemDoubleClicked.connect(lambda _i: use())
    bw = QWidget()
    bl = QHBoxLayout(bw)
    bl.setContentsMargins(0, 0, 0, 0)
    b_browse = QPushButton("Browse... / Przeglądaj...")
    b_browse.clicked.connect(browse)
    b_cancel = QPushButton("Cancel / Anuluj")
    b_cancel.clicked.connect(dlg.reject)
    b_open = QPushButton("Open / Otwórz")
    b_open.clicked.connect(use)
    b_open.setDefault(True)
    bl.addWidget(b_browse)
    bl.addStretch(1)
    bl.addWidget(b_cancel)
    bl.addWidget(b_open)
    lay.addWidget(bw)
    dlg.resize(620, 320)
    dlg.exec()
    return sel["path"]


def main():
    cfg = load_cfg()
    app = QApplication(sys.argv)
    apply_office_theme(app)
    pdf = sys.argv[1] if len(sys.argv) > 1 else _pick_pdf(cfg)
    if not pdf:
        sys.exit("No PDF.")
    base = os.path.splitext(pdf)[0] + "_Inspection"
    xlsx = sys.argv[2] if len(sys.argv) > 2 else base + ".xlsx"
    try:
        created = ensure_xlsx(xlsx, str(cfg.get("company") or ""))
    except RuntimeError as e:
        QMessageBox.critical(None, "Template", str(e))
        xlsx, _ = QFileDialog.getOpenFileName(
            None, "Inspection sheet / Karta kontroli (xlsx)",
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
        win.set_status("created / utworzono: %s" % os.path.basename(xlsx))
    sys.exit(app.exec())
