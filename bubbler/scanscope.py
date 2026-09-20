# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Scan-review scope preset editor.

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

from .i18n import tr
from .scanlib import SCAN_BUCKETS, SCAN_PRESETS, scan_presets


def bucket_label(name):
    """Human words plus example per bucket."""
    return {
        "gdt": tr('GD&T and true position'),
        "finish": tr('Surface finish (Ra, Rz)'),
        "basic_ref": tr('BASIC [25] and REFERENCE (75)'),
        "thread": tr('Threads (M8x1.25)'),
        "own_tol": tr('Its own tolerance (25 +/-0.1, 25 H7)'),
        "gentol": tr('On the general-tolerance block only'),
        "bare": tr('No tolerance from anywhere'),
    }.get(name, name)


class ScopeDialog(QDialog):
    """Add retune remove scan-review presets."""

    def __init__(self, parent, cfg=None):
        super().__init__(parent)
        self.setWindowTitle(tr('What to bubble by default'))
        self.presets = {k: list(v) for k, v in scan_presets(cfg).items()}
        self.custom = set((cfg or {}).get("scan_presets") or {})
        self.cur = None

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            tr('A preset sets which callouts start TICKED in scan review. '
               'Nothing is hidden -- every callout found stays listed, so '
               'you can tick it yourself.')))

        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMaximumWidth(220)
        row.addWidget(self.list)

        right = QVBoxLayout()
        self.boxes = {}
        for b in SCAN_BUCKETS:
            c = QCheckBox(bucket_label(b))
            c.stateChanged.connect(self._changed)
            self.boxes[b] = c
            right.addWidget(c)
        right.addStretch(1)
        rw = QWidget()
        rw.setLayout(right)
        row.addWidget(rw, 1)
        lay.addLayout(row)

        btns = QHBoxLayout()
        for label, slot in ((tr('Add...'), self._add),
                            (tr('Rename...'), self._rename),
                            (tr('Remove'), self._remove),
                            (tr('Reset'), self._reset)):   # shared key
            b = QPushButton(label)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._fill()
        self.list.currentTextChanged.connect(self._pick)
        if self.list.count():
            self.list.setCurrentRow(0)

    # ---------------------------------------------------------------- state
    def _fill(self, keep=None):
        self.list.blockSignals(True)
        self.list.clear()
        for name in sorted(self.presets):
            self.list.addItem(name)
        self.list.blockSignals(False)
        if keep:
            hits = self.list.findItems(keep, 0)
            if hits:
                self.list.setCurrentItem(hits[0])

    def _pick(self, name):
        self.cur = name or None
        have = set(self.presets.get(self.cur) or ())
        for b, c in self.boxes.items():
            c.blockSignals(True)
            c.setChecked(b in have)
            c.setEnabled(bool(self.cur))
            c.blockSignals(False)

    def _changed(self):
        """Tick edits current preset makes shop copy."""
        if not self.cur:
            return
        self.presets[self.cur] = [b for b in SCAN_BUCKETS
                                  if self.boxes[b].isChecked()]
        self.custom.add(self.cur)

    # --------------------------------------------------------------- edits
    def _add(self):
        name, ok = QInputDialog.getText(self, tr('Add preset'), tr('Name'))
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in self.presets:
            QMessageBox.information(self, tr('Add preset'),
                                    tr('Preset %s already exists.') % name)
            return
        self.presets[name] = list(self.presets.get(self.cur) or ())
        self.custom.add(name)
        self._fill(keep=name)

    def _rename(self):
        if not self.cur:
            return
        if self.cur in SCAN_PRESETS:
            QMessageBox.information(
                self, tr('Rename preset'),
                tr('%s is built-in and keeps its name -- drawings name it '
                   'in the Inspection type cell. Add a new preset '
                   'instead.') % self.cur)
            return
        name, ok = QInputDialog.getText(self, tr('Rename preset'), tr('Name'),
                                        text=self.cur)
        name = (name or "").strip()
        if not ok or not name or name == self.cur:
            return
        if name in self.presets:
            QMessageBox.information(self, tr('Rename preset'),
                                    tr('Preset %s already exists.') % name)
            return
        self.presets[name] = self.presets.pop(self.cur)
        self.custom.discard(self.cur)
        self.custom.add(name)
        self._fill(keep=name)

    def _remove(self):
        if not self.cur:
            return
        if self.cur in SCAN_PRESETS:
            QMessageBox.information(
                self, tr('Remove preset'),
                tr('%s is built-in and cannot be removed. Reset restores '
                   'it as shipped.') % self.cur)
            return
        self.presets.pop(self.cur, None)
        self.custom.discard(self.cur)
        self._fill()
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._pick("")

    def _reset(self):
        """Forget shop copy of shipped preset."""
        if not self.cur or self.cur not in SCAN_PRESETS:
            return
        self.presets[self.cur] = list(SCAN_PRESETS[self.cur])
        self.custom.discard(self.cur)
        self._pick(self.cur)

    # -------------------------------------------------------------- result
    def result_presets(self):
        """Only what shop changed or added."""
        return {n: list(self.presets[n]) for n in sorted(self.custom)
                if n in self.presets}

    def names(self):
        return sorted(self.presets)
