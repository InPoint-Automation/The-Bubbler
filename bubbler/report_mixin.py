# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Out-of-tolerance report dialog and CSV export.

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QPushButton,
                               QFileDialog, QHeaderView, QCheckBox)

from .common import oot_summary, qc_path
from .i18n import tr

_COLS = ("#", "Nominal", "Tol", "Measured", "Op", "Gage", "Page", "Tier")

_STAT_LABEL = {"n": "n", "mean": "Mean", "min": "Min", "max": "Max",
               "range": "Range", "stdev": "Std dev"}


def _fmt_stat(v):
    return "" if v is None else ("%d" % v if isinstance(v, int)
                                 else "%.6g" % v)


class ReportMixin:
    def run_stats(self):
        """Per-characteristic stats across runs. Other requirement marked."""
        from .runstats import stats_rows
        which = self.cfg.get("run_stats") or ["mean"]
        dlg = QDialog(self)
        dlg.setWindowTitle(tr('Statistics across runs'))
        lay = QVBoxLayout(dlg)
        head = QLabel("")
        lay.addWidget(head)
        only = QCheckBox(tr('Closed runs only'))
        lay.addWidget(only)
        tbl = QTableWidget(0, 0)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(tbl)
        note = QLabel(tr('* some runs were measured against a different '
                         'requirement; their readings are included.'))
        lay.addWidget(note)
        state = {}

        def fill():
            rows, cols = stats_rows(self.store, which, only.isChecked())
            state["rows"], state["which"] = rows, cols
            runs = [r for r in self.store.runs
                    if r.get("closed") or not only.isChecked()]
            head.setText(tr('%d runs, %d characteristics measured')
                         % (len(runs), len(rows)))
            heads = ["#", tr('Feature'), tr('Nominal'), tr('Runs')] + \
                [tr(_STAT_LABEL[s]) for s in cols]
            tbl.clear()
            tbl.setColumnCount(len(heads))
            tbl.setRowCount(len(rows))
            tbl.setHorizontalHeaderLabels(heads)
            for i, r in enumerate(rows):
                n = str(r["runs"])
                if r.get("other_req"):
                    n += " *"             # see footnote
                cells = [str(r["bubble"] or ""), str(r["feature"] or ""),
                         "" if r["nominal"] is None else "%g" % r["nominal"],
                         n] + [_fmt_stat(r.get(s)) for s in cols]
                for c, txt in enumerate(cells):
                    tbl.setItem(i, c, QTableWidgetItem(txt))
            note.setVisible(any(r.get("other_req") for r in rows))

        only.toggled.connect(lambda _on: fill())
        fill()
        bw = QHBoxLayout()
        b_csv = QPushButton(tr('Export CSV...'))
        b_csv.clicked.connect(lambda: self._stats_csv(
            dlg, state["rows"], state["which"]))
        b_close = QPushButton(tr('Close'))
        b_close.clicked.connect(dlg.reject)
        bw.addWidget(b_csv)
        bw.addStretch(1)
        bw.addWidget(b_close)
        lay.addLayout(bw)
        dlg.resize(640, 400)
        self._stats_win = dlg
        dlg.show()
        return dlg

    def _stats_csv(self, parent, rows, which):
        seed = qc_path(self.pdf_path, "_run_stats.csv",
                       subdir=self.cfg.get("qc_subdir", "qc"))
        path, _ = QFileDialog.getSaveFileName(
            parent, tr('Export CSV...'), seed, "CSV (*.csv)")
        if not path:
            return ""
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["bubble", "feature", "nominal", "runs",
                            "runs_other_requirement"] + list(which))
                for r in rows:
                    w.writerow([r["bubble"], r["feature"], r["nominal"],
                                r["runs"], r.get("other_req", 0)]
                               + [r.get(s) for s in which])
            self.set_status(tr('exported: %s') % path)
            return path
        except OSError as e:
            self.set_status(tr('CSV export failed: %s') % e)
            return ""

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
