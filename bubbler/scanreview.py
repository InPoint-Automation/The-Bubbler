# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Scan-review dialog. Edit hits, anchor, append balloons.

import math
import re

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QLabel, QLineEdit, QComboBox,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QAbstractItemView, QInputDialog, QMessageBox)

from .common import TYPES, GROUP_OF
from .scanlib import (scan_to_row, expand_hole_row, denorm_candidates,
                      GAGES, repeat_count)
from .iso2768 import iso2768_tol
from .i18n import tr, retranslate


def clockwise_order(items):
    """Sort accepted rows in place into clockwise balloon-numbering order."""
    by_pg = {}
    for it in items:
        by_pg.setdefault(it["pg"], []).append(it)
    for group in by_pg.values():
        pts = [it for it in group if it["anchored"]] or group
        cx = sum(it["ax"] for it in pts) / len(pts)
        cy = sum(it["ay"] for it in pts) / len(pts)
        for it in group:
            # y-up; ~225° leads clockwise
            ang = math.degrees(math.atan2(cy - it["ay"], it["ax"] - cx)) % 360.0
            it["_cw"] = (225.0 - ang) % 360.0
    items.sort(key=lambda it: (it["pg"], it["_cw"]))


class ScanReview(QDialog):
    """Review scan hits before committing them to the ledger."""

    COLS = ("use", "pg", "exp", "type", "value", "tol", "gage")
    HEADS = ("use?", "pg", "n×", "type", "value / wartość", "tol", "gage")

    def __init__(self, app, found, gtols, all_pages):
        super().__init__(app)
        self.app = app
        self.gtols = gtols
        self.setWindowTitle(
            tr("Scan review / Przegląd") + " - "
            + (tr("all pages / wszystkie strony") if all_pages
               else "%s %d" % (tr("page / strona"), app.page_i + 1)))
        self.resize(700, 560)
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.HEADS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # itemEntered needs viewport tracking
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().installEventFilter(self)
        lay.addWidget(self.table)

        # rows: [use, hit, ledger_row, page, overrides, expand]
        self.rows = []
        for pg, h in found:
            rw = self._to_row(h, pg)
            use = h.get("sb") not in ("BASIC", "REF", "BARE") or \
                (h.get("sb") == "BARE" and rw.get("tol_sym") is not None)
            self.rows.append([use, h, rw, pg, {}, self._nx(h) > 1])

        self.table.setRowCount(len(self.rows))
        for i in range(len(self.rows)):
            self._fill_row(i)

        self.table.cellDoubleClicked.connect(self._double)
        self.table.itemEntered.connect(self._hover)
        # connect after fill, else it fires
        self.table.itemChanged.connect(self._item_changed)

        info = QLabel("Tick 'use?' to accept a row - tick 'n×' to expand "
                      "repeats - double-click type/value/tol/gage to edit - "
                      "hover a row to show it on the drawing. Plain numbers "
                      "start unticked; 'ISO 2768 auto' fills tol-less dims.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;")
        lay.addWidget(info)

        bw = QWidget()
        bl = QHBoxLayout(bw)
        b_acc = QPushButton("Accept checked / Zatwierdź")
        b_acc.setDefault(True)
        b_acc.clicked.connect(self._accept)
        b_all = QPushButton("Check all / Zaznacz")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none = QPushButton("Uncheck all / Odznacz")
        b_none.clicked.connect(lambda: self._set_all(False))
        b_bare = QPushButton("Toggle plain dims / Liczby")
        b_bare.clicked.connect(self._toggle_bare)
        b_bulk = QPushButton("Bulk edit checked / Grupowo")
        b_bulk.setToolTip("Set type / gage / tol on every checked row at once")
        b_bulk.clicked.connect(self._bulk_edit)
        b_cancel = QPushButton("Cancel / Anuluj")
        b_cancel.clicked.connect(self.reject)
        bl.addWidget(b_acc)
        bl.addWidget(b_all)
        bl.addWidget(b_none)
        bl.addWidget(b_bare)
        bl.addWidget(b_bulk)
        bl.addWidget(b_cancel)
        lay.addWidget(bw)
        retranslate(self)
        self.finished.connect(lambda _r: self._clear_hl())

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport() and ev.type() == QEvent.Leave:
            self._clear_hl()
        return super().eventFilter(obj, ev)

    def _clear_hl(self):
        self.app._scanhl = None
        self.app.redraw_overlay()

    def _nx(self, h):
        # share repeat_count so display, expansion agree
        return repeat_count(h.get("v"))

    def _to_row(self, h, pg):
        rw = scan_to_row(h)
        self.app._apply_general_tol(rw, h, self.gtols.get(pg) or {})
        rw["gage"] = self.app.suggest(rw)
        return rw

    def _row_values(self, i):
        use, h, rw, pg, ov, expand = self.rows[i]
        n = self._nx(h)
        exp = "×%d" % n if n > 1 else ""
        tp_show = (ov.get("type") or
                   ("plain dim" if h.get("sb") == "BARE" else h["tp"]))
        # cols 0, 2 are checkboxes, text empty
        return ("", pg + 1, exp, tp_show,
                h["v"], h.get("t") or "", rw["gage"])

    def _fill_row(self, i):
        self.table.blockSignals(True)
        use, h, _rw, _pg, _ov, expand = self.rows[i]
        nx = self._nx(h)
        for c, val in enumerate(self._row_values(i)):
            it = QTableWidgetItem(str(val))
            it.setTextAlignment(Qt.AlignCenter)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if c == 0:
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if use else Qt.Unchecked)
            elif c == 2 and nx > 1:
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if expand else Qt.Unchecked)
            self.table.setItem(i, c, it)
        self.table.blockSignals(False)

    def _item_changed(self, it):
        i, c = it.row(), it.column()
        if i >= len(self.rows):
            return
        if c == 0:
            self.rows[i][0] = (it.checkState() == Qt.Checked)
        elif c == 2 and self._nx(self.rows[i][1]) > 1:
            self.rows[i][5] = (it.checkState() == Qt.Checked)

    def _set_check(self, i, col, on):
        it = self.table.item(i, col)
        if it is not None:
            self.table.blockSignals(True)
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self.table.blockSignals(False)

    def _set_all(self, on):
        for i in range(len(self.rows)):
            self.rows[i][0] = on
            self._set_check(i, 0, on)

    def _rebuild(self, i):
        use, h, rw, pg, ov, expand = self.rows[i]
        rw = self._to_row(h, pg)
        if ov.get("type"):
            rw["type"] = ov["type"]
            rw["group"] = GROUP_OF.get(ov["type"], rw["group"])
        rw["gage"] = ov.get("gage") or self.app.suggest(rw)
        self.rows[i][2] = rw
        self._fill_row(i)

    def _toggle_use(self, i):
        self.rows[i][0] = not self.rows[i][0]
        self._set_check(i, 0, self.rows[i][0])

    def _toggle_bare(self):
        bare = [i for i, r in enumerate(self.rows)
                if r[1].get("sb") == "BARE"]
        if not bare:
            return
        target = not self.rows[bare[0]][0]
        for i in bare:
            self.rows[i][0] = target
            self._set_check(i, 0, target)

    def _bulk_edit(self):
        idx = [i for i, r in enumerate(self.rows) if r[0]]
        if not idx:
            QMessageBox.information(
                self, "Bulk edit / Grupowo",
                "No rows checked / brak zaznaczonych wierszy")
            return
        KEEP = "- keep / bez zmian -"
        dlg = QDialog(self)
        dlg.setWindowTitle("%s (%d)" % (tr("Bulk edit checked / Grupowo"),
                                        len(idx)))
        g = QGridLayout(dlg)
        cb_t = QComboBox()
        cb_t.addItem(KEEP)
        cb_t.addItems(TYPES)
        cb_g = QComboBox()
        cb_g.setEditable(True)
        cb_g.addItem(KEEP)
        cb_g.addItems(GAGES)
        e_tol = QLineEdit()
        e_tol.setPlaceholderText(KEEP)
        g.addWidget(QLabel("Type / Typ"), 0, 0)
        g.addWidget(cb_t, 0, 1)
        g.addWidget(QLabel("Gage / Przyrząd"), 1, 0)
        g.addWidget(cb_g, 1, 1)
        g.addWidget(QLabel("Tol"), 2, 0)
        g.addWidget(e_tol, 2, 1)
        bw = QWidget()
        bl = QHBoxLayout(bw)
        b_ok = QPushButton("Apply / Zastosuj")
        b_ok.setDefault(True)
        b_ok.clicked.connect(dlg.accept)
        b_no = QPushButton("Cancel / Anuluj")
        b_no.clicked.connect(dlg.reject)
        bl.addStretch(1)
        bl.addWidget(b_ok)
        bl.addWidget(b_no)
        g.addWidget(bw, 3, 0, 1, 2)
        retranslate(dlg)
        if not dlg.exec():
            return
        new_t = cb_t.currentText()
        new_g = cb_g.currentText().strip()
        new_tol = e_tol.text().strip()
        for i in idx:
            use, h, rw, pg, ov, expand = self.rows[i]
            if new_t != KEEP:
                ov["type"] = new_t
            if new_g and new_g != KEEP:
                ov["gage"] = new_g
            if new_tol:
                h["t"] = new_tol
            self._rebuild(i)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space:
            row = self.table.currentRow()
            if row >= 0:
                self._toggle_use(row)
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept()
            return
        super().keyPressEvent(e)

    def _double(self, row, col):
        # double-click only edits data cells
        name = self.COLS[col]
        if name in ("type", "value", "tol", "gage"):
            self._cell_edit(row, name)

    def _cell_edit(self, i, col):
        use, h, rw, pg, ov, expand = self.rows[i]
        if col == "type":
            val, ok = QInputDialog.getItem(self, "type", "type", TYPES,
                                           TYPES.index(rw["type"])
                                           if rw["type"] in TYPES else 0,
                                           False)
            if ok and val:
                ov["type"] = val
                rw["type"] = val
                rw["group"] = GROUP_OF.get(val, rw["group"])
                self._fill_row(i)
        elif col == "gage":
            cur = rw["gage"]
            val, ok = QInputDialog.getItem(
                self, "gage", "gage", GAGES,
                GAGES.index(cur) if cur in GAGES else 0, True)
            if ok:
                ov["gage"] = val
                rw["gage"] = val
                self._fill_row(i)
        elif col == "tol":
            val, ok = QInputDialog.getText(self, "tol", "tol",
                                           text=h.get("t") or "")
            if ok:
                h["t"] = val.strip() or None
                self._rebuild(i)
        else:
            val, ok = QInputDialog.getText(self, "value", "value", text=h["v"])
            if ok and val.strip():
                h["v"] = val.strip()
                self.rows[i][5] = self._nx(h) > 1
                self._rebuild(i)

    def _hover(self, item):
        i = item.row()
        self.app._scanhl = (self.rows[i][3], self.rows[i][1].get("rect")) \
            if self.rows[i][1].get("rect") else None
        self.app.redraw_overlay()

    def _accept(self):
        app = self.app
        added = 0
        unanchored = 0
        fy = {}
        snapped = False
        nrows = 0
        # resolve each checked row's page anchor (ax, ay)
        items = []
        for use, h, rw, pg, ov, expand in self.rows:
            if not use:
                continue
            page = app.doc[pg]
            ax = ay = None
            rect = h.get("rect")
            if rect:
                ax = (rect[0] + rect[2]) / 2.0
                ay = (rect[1] + rect[3]) / 2.0
            else:
                needles = (denorm_candidates(h["raw"]) +
                           denorm_candidates(h["v"]))
                for needle in needles:
                    try:
                        hits_r = page.search_for(needle)
                    except Exception:
                        hits_r = []
                    if hits_r:
                        r = hits_r[0]
                        ax, ay = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
                        break
            anchored = ax is not None
            if not anchored:
                ax, ay = 16.0, fy.get(pg, 20.0)
                fy[pg] = ay + 24.0
                if fy[pg] > page.rect.height - 20:
                    fy[pg] = 20.0
                unanchored += 1
            items.append({"h": h, "rw": rw, "pg": pg, "expand": expand,
                          "ax": ax, "ay": ay, "rect": rect,
                          "anchored": anchored})

        # number clockwise from bottom-left around each page
        clockwise_order(items)

        # one bubble per callout; (page, cg) share a uid
        group_uid = {}
        group_anchor = {}
        for it in items:
            cg = it["h"].get("cg")
            it["_key"] = (it["pg"], cg) if cg is not None \
                else ("_", id(it["h"]))
            if it["_key"] not in group_uid:
                group_uid[it["_key"]] = app.store.new_uid()
                group_anchor[it["_key"]] = it

        for it in items:
            h, rw, pg, expand = it["h"], it["rw"], it["pg"], it["expand"]
            anchor = group_anchor[it["_key"]]
            ax, ay, rect = anchor["ax"], anchor["ay"], anchor["rect"]
            if not snapped:
                app.snapshot()
                snapped = True
            if app.use_leaders() or rect is not None:
                bx, by = app.auto_offset(ax, ay, page_i=pg, rect=rect)
            else:
                bx, by = ax, ay
            base = dict(rw)
            base.setdefault("leader", app.use_leaders())
            if (app.last.get("iso_on") and base.get("type") == "dim" and
                    base.get("tol_sym") is None and
                    base.get("tol_max") is None and
                    base.get("tol_min") is None and
                    base.get("nominal") is not None):
                t2768 = iso2768_tol(base["nominal"], app.last.get("icls", "m"))
                if t2768 is not None:
                    base["tol_sym"] = t2768
                    base["gage"] = app.suggest(base)
            uid = group_uid[it["_key"]]
            # expand -> Ø+X/Y per repeat; off -> one row
            for d in expand_hole_row(base, app.cfg, repeat=expand):
                if not d.get("gage"):
                    d["gage"] = app.suggest(d)
                d.setdefault("leader", app.use_leaders())
                d.update({"uid": uid, "bubble": "", "page": pg,
                          "x": ax, "y": ay, "bx": bx, "by": by,
                          "sheet_row": None})
                app.ledger.append(d)
                nrows += 1
            added += 1
        app.store.renumber()
        app._save_session()
        app.refresh_panel()
        app.render()
        self.accept()
        msg = "added %d balloon(s), %d row(s)" % (added, nrows)
        if unanchored:
            msg += "; %d unanchored (left margin) - drag into place" \
                   % unanchored
        app.set_status(msg)


