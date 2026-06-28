# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble-panel table model, sort/filter proxy.

from PySide6.QtCore import (Qt, QAbstractTableModel, QModelIndex,
                            QSortFilterProxyModel)
from PySide6.QtGui import QColor

from .common import tol_text, out_of_tol

PANEL_COLS = [("bubble", "#", 45), ("feature", "feature/cecha", 130),
              ("nominal", "nominal", 70), ("tol", "tol", 90),
              ("type", "type/typ", 90), ("group", "group/grupa", 110),
              ("tier", "tier", 50), ("pin", "pin", 50),
              ("gage", "gage/przyrząd", 90),
              ("measured", "measured/pomiar", 90)]
INLINE_COLS = ("measured", "tier", "gage")

SORT_ROLE = Qt.UserRole + 1      # per-cell sort key
LEDGER_ROLE = Qt.UserRole + 2    # row -> ledger index

_OOT_COLOR = QColor("#c00000")
_NEG = float("-inf")


def bubble_sortkey(bub):
    """Numeric sort key for a bubble label."""
    from .common import base_of
    b = str(bub)
    base = base_of(b)
    suf = b[len(str(base)):] if b.startswith(str(base)) else ""
    frac = 0.0
    for ch in suf.lower():
        if "a" <= ch <= "z":
            frac = frac * 26 + (ord(ch) - 96)
    return base + frac / 1000.0


def cell_text(d, key):
    """Display string for one ledger row + column key."""
    if key == "nominal":
        return "" if d.get("nominal") is None else "%.2f" % d["nominal"]
    if key == "tol":
        return tol_text(d)
    if key == "pin":
        return "" if d.get("pin") is None else "%g" % d["pin"]
    if key == "measured":
        m = d.get("measured")
        return "" if m in (None, "") else str(m)
    if key == "bubble":
        return str(d.get("bubble", ""))
    return d.get(key, "") or ""


def _sort_value(d, key):
    """Numeric sort key, else None for display-text fallback."""
    if key == "bubble":
        return bubble_sortkey(d.get("bubble", "0"))
    if key == "nominal":
        return d["nominal"] if d.get("nominal") is not None else _NEG
    if key == "pin":
        return d["pin"] if d.get("pin") is not None else _NEG
    if key == "measured":
        m = d.get("measured")
        try:
            return float(str(m).replace(",", "."))
        except (TypeError, ValueError):
            return None
    return None


class BubbleTableModel(QAbstractTableModel):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.store.ledger)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(PANEL_COLS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        d = self.store.ledger[index.row()]
        key = PANEL_COLS[index.column()][0]
        if role == Qt.DisplayRole:
            return cell_text(d, key)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter)
        if role == Qt.ForegroundRole:
            return _OOT_COLOR if out_of_tol(d) else None
        if role == SORT_ROLE:
            sk = _sort_value(d, key)
            return cell_text(d, key) if sk is None else sk
        if role == LEDGER_ROLE:
            return index.row()
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return PANEL_COLS[section][1]
        return None

    def refresh(self):
        """Full reset."""
        self.beginResetModel()
        self.endResetModel()


class BubbleFilterProxy(QSortFilterProxyModel):
    """Sort by SORT_ROLE numeric-then-text, filter visible cells."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self._filter = ""
        self._hidden_cols = set()

    def set_filter(self, text):
        self._filter = (text or "").strip().lower()
        self.invalidate()

    def set_hidden_cols(self, cols):
        self._hidden_cols = set(cols)
        self.invalidate()

    def lessThan(self, left, right):
        a = left.data(SORT_ROLE)
        b = right.data(SORT_ROLE)
        try:
            return float(a) < float(b)
        except (TypeError, ValueError):
            return str(a) < str(b)

    def filterAcceptsRow(self, row, parent):
        if not self._filter:
            return True
        m = self.sourceModel()
        for c in range(m.columnCount()):
            if c in self._hidden_cols:
                continue
            txt = str(m.index(row, c, parent).data(Qt.DisplayRole) or "")
            if self._filter in txt.lower():
                return True
        return False
