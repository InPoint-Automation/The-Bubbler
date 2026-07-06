# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Out-of-tolerance report. Read-only dialog + CSV export.

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QPushButton,
                               QFileDialog, QHeaderView)

from .common import oot_summary, qc_path
from .i18n import tr

_COLS = ("#", "Nominal", "Tol", "Measured", "Op", "Gage", "Page", "Tier")


class ReportMixin:
    def oot_report(self):
        win = getattr(self, "_oot_win", None)
        if win is not None:
            win.raise_()
            win.activateWindow()
            self._oot_fill()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr('Out-of-tolerance report'))
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        self._oot_head = QLabel("")
        self._oot_head.setStyleSheet("font-size:11pt; font-weight:bold;")
        lay.addWidget(self._oot_head)

        tbl = QTableWidget(0, len(_COLS))
        tbl.setHorizontalHeaderLabels([tr(c) for c in _COLS])
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.itemDoubleClicked.connect(
            lambda it: self._oot_jump(tbl, it.row()))
        self._oot_tbl = tbl
        lay.addWidget(tbl)

        bw = QHBoxLayout()
        b_csv = QPushButton(tr('Export CSV...'))
        b_csv.clicked.connect(self._oot_export_csv)
        b_refresh = QPushButton(tr('Refresh'))
        b_refresh.clicked.connect(self._oot_fill)
        b_close = QPushButton(tr('Close'))
        b_close.clicked.connect(dlg.reject)
        bw.addWidget(b_csv)
        bw.addWidget(b_refresh)
        bw.addStretch(1)
        bw.addWidget(b_close)
        lay.addLayout(bw)

        dlg.resize(680, 420)
        dlg.finished.connect(lambda _r: setattr(self, "_oot_win", None))
        self._oot_win = dlg
        self._oot_fill()
        dlg.show()

    def _oot_fill(self):
        s = oot_summary(self.ledger, self.cfg)
        self._oot_head.setText(
            tr('%d out of tolerance (%d critical)')
            % (s["n_oot"], s["n_critical"]))
        tbl = self._oot_tbl
        tbl.setRowCount(0)
        for r in s["rows"]:
            i = tbl.rowCount()
            tbl.insertRow(i)
            page = "" if r["page"] is None else str(r["page"] + 1)
            nom = "" if r["nominal"] is None else ("%g" % r["nominal"])
            cells = [str(r["bubble"]), nom, r["tol"], str(r["measured"]),
                     r["op"], str(r["gage"]), page, r["tier"]]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if r["state"] == "nogo" or (c == 3 and r["state"] == "out"):
                    it.setForeground(Qt.red)
                tbl.setItem(i, c, it)
            tbl.item(i, 0).setData(Qt.UserRole, r["bubble"])

    def _oot_jump(self, tbl, row):
        it = tbl.item(row, 0)
        if it is None:
            return
        bub = it.data(Qt.UserRole)
        d = next((x for x in self.ledger if x.get("bubble") == bub), None)
        if d is None:
            return
        self._center_on(d)
        self.redraw_overlay()

    def _oot_export_csv(self):
        rows = oot_summary(self.ledger, self.cfg)["rows"]
        seed = qc_path(self.pdf_path, "_OOT.csv",
                       subdir=self.cfg.get("qc_subdir", "qc"))
        path, _ = QFileDialog.getSaveFileName(
            self._oot_win, tr('Export CSV...'), seed, "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["bubble", "nominal", "tol", "measured", "op",
                            "gage", "page", "tier", "state"])
                for r in rows:
                    pg = "" if r["page"] is None else r["page"] + 1
                    w.writerow([r["bubble"], r["nominal"], r["tol"],
                                r["measured"], r["op"], r["gage"], pg,
                                r["tier"], r["state"]])
            self.set_status(tr('exported: %s') % path)
        except OSError as e:
            self.set_status(tr('CSV export failed: %s') % e)
