# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble list dock. QTableView over sort/filter proxy.

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QShortcut, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QTableView,
                               QAbstractItemView, QMenu)

from .common import base_of
from .config import save_cfg, CFG_DEFAULT
from .panel_model import (BubbleTableModel, BubbleFilterProxy,
                          PANEL_COLS, INLINE_COLS)


class PanelMixin:
    def _build_panel(self):
        self.dock = QDockWidget("Bubbles / Bąble", self)
        self.dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.dock.setFeatures(QDockWidget.DockWidgetClosable |
                              QDockWidget.DockWidgetMovable)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(2, 2, 2, 2)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Bubbles / Bąble"))
        self.panel_filter = QLineEdit()
        self.panel_filter.setPlaceholderText("filter / filtr...")
        self.panel_filter.setClearButtonEnabled(True)
        self.panel_filter.textChanged.connect(self._filter_rows)
        bar.addWidget(self.panel_filter, 1)
        cols_btn = QPushButton("cols...")
        cols_btn.clicked.connect(self._cols_menu)
        bar.addWidget(cols_btn)
        lay.addLayout(bar)

        # store-backed model -> proxy -> view
        self._model = BubbleTableModel(self.store, self)
        self._proxy = BubbleFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # source rows == ledger indices
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        for i, (_, _, w) in enumerate(PANEL_COLS):
            self.table.setColumnWidth(i, w)
        self.table.doubleClicked.connect(self._panel_double)
        self.table.selectionModel().selectionChanged.connect(
            self._panel_select)
        # Del on table, not canvas
        del_sc = QShortcut(QKeySequence.Delete, self.table)
        del_sc.setContext(Qt.WidgetShortcut)
        del_sc.activated.connect(self._panel_delete)
        lay.addWidget(self.table)
        self.dock.setWidget(body)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()
        self.dock.visibilityChanged.connect(self._dock_vis)
        vis = self.cfg.get("panel_cols", CFG_DEFAULT["panel_cols"])
        self._apply_col_visibility(vis)

    def _filter_rows(self, _text=None):
        self._apply_filter()

    def _apply_filter(self):
        if hasattr(self, "_proxy"):
            self._proxy.set_filter(self.panel_filter.text())

    def _row_to_ledger(self, view_row):
        """Proxy row -> ledger index, -1 if gone."""
        if view_row < 0:
            return -1
        src = self._proxy.mapToSource(self._proxy.index(view_row, 0))
        return src.row() if src.isValid() else -1

    def _ledger_to_row(self, ledger_idx):
        """Ledger index -> proxy row, -1 if filtered out."""
        if ledger_idx < 0 or ledger_idx >= self._model.rowCount():
            return -1
        pr = self._proxy.mapFromSource(self._model.index(ledger_idx, 0))
        return pr.row() if pr.isValid() else -1

    def _panel_highlight(self, ledger_idx, scroll=True, mute=False):
        """Select panel row for a ledger index."""
        if not hasattr(self, "table"):
            return
        vr = self._ledger_to_row(ledger_idx)
        if vr < 0:
            return
        sm = self.table.selectionModel()
        if mute:
            sm.blockSignals(True)
        self.table.selectRow(vr)
        if mute:
            sm.blockSignals(False)
        if scroll:
            self.table.scrollTo(self._proxy.index(vr, 0))

    def _col_index(self, name):
        for i, (c, _, _) in enumerate(PANEL_COLS):
            if c == name:
                return i
        return -1

    def _hidden_cols(self):
        return {i for i in range(len(PANEL_COLS))
                if self.table.isColumnHidden(i)}

    def _apply_col_visibility(self, vis):
        for i, (c, _, _) in enumerate(PANEL_COLS):
            self.table.setColumnHidden(i, c not in vis)
        self._proxy.set_hidden_cols(self._hidden_cols())

    def _dock_vis(self, visible):
        self.panel_visible = bool(visible)
        try:
            self.btn_panel.setChecked(self.panel_visible)
        except Exception:
            pass
        if visible:
            self.refresh_panel()

    def toggle_panel(self):
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()

    def _cols_menu(self):
        m = QMenu(self)
        for c, head, _ in PANEL_COLS:
            a = QAction(head, m, checkable=True)
            a.setChecked(not self.table.isColumnHidden(self._col_index(c)))
            a.toggled.connect(lambda on, name=c: self._col_toggle(name, on))
            m.addAction(a)
        m.exec(self.cursor().pos())

    def _col_toggle(self, name, on):
        self.table.setColumnHidden(self._col_index(name), not on)
        vis = [c for c, _, _ in PANEL_COLS
               if not self.table.isColumnHidden(self._col_index(c))]
        if not vis:
            vis = ["bubble"]
            self.table.setColumnHidden(self._col_index("bubble"), False)
        self._proxy.set_hidden_cols(self._hidden_cols())
        self.cfg["panel_cols"] = vis
        save_cfg(self.cfg)

    def refresh_panel(self):
        if not hasattr(self, "_model"):
            return
        # full re-pull; proxy re-sorts
        self._model.refresh()
        if self.measure_mode:
            self._walk_build()

    def _panel_select(self, *_a):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        idx = self._row_to_ledger(rows[0].row())
        if idx < 0 or idx >= len(self.ledger):
            return
        d = self.ledger[idx]
        if d.get("page") != self.page_i:
            return
        # mirror selection to canvas
        self.sel = {d["uid"]}
        bx, by = d.get("bx", d["x"]), d.get("by", d["y"])
        self._flash_ring = (self.page_i, bx, by)
        self.view.centerOn(self._scr(bx, by))
        self.redraw_overlay()
        self._qbar_refresh()
        QTimer.singleShot(700, self._clear_flash)

    def _panel_delete(self):
        if self._entry_focused():
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        idx = self._row_to_ledger(rows[0].row())
        if 0 <= idx < len(self.ledger):
            self._delete_bases([base_of(self.ledger[idx]["bubble"])])
            self.set_status("deleted / usunięto - Ctrl+Z")

    def _clear_flash(self):
        self._flash_ring = None
        self.redraw_overlay()

    def _panel_double(self, index):
        idx = self._row_to_ledger(index.row())
        if idx < 0 or idx >= len(self.ledger):
            return
        name = PANEL_COLS[index.column()][0]
        if name in INLINE_COLS:
            self._cell_edit(idx, name)
        else:
            self.edit_ledger_row(idx)
