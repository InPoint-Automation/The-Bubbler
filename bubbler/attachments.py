# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Run report images: pick, caption, order.

import os

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QPushButton, QLineEdit, QLabel,
                               QFileDialog, QDialogButtonBox)
from PySide6.QtCore import Qt

from .i18n import tr

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"


class AttachmentsDialog(QDialog):
    """Items {file, caption}, file relative to base_dir."""

    def __init__(self, parent, items, base_dir, readonly=False):
        super().__init__(parent)
        self.setWindowTitle(tr('Report images'))
        self.resize(520, 380)
        self._base = base_dir
        self._ro = readonly
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr('Shown after the report rows, in this '
                                'order. They belong to this run only.')))
        self.lst = QListWidget()
        for it in items or ():
            self._add_item(dict(it))
        self.lst.currentRowChanged.connect(self._show_caption)
        lay.addWidget(self.lst)
        cap = QHBoxLayout()
        cap.addWidget(QLabel(tr('Caption')))
        self.cap = QLineEdit()
        self.cap.textEdited.connect(self._set_caption)
        cap.addWidget(self.cap)
        lay.addLayout(cap)
        row = QHBoxLayout()
        self._buttons = []
        for label, fn in ((tr('Add...'), self.add_files),
                          (tr('Remove'), self.remove),
                          (tr('Up'), lambda: self.move(-1)),
                          (tr('Down'), lambda: self.move(1))):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
            self._buttons.append(b)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        if readonly:
            for w in self._buttons + [self.cap]:
                w.setEnabled(False)
        if self.lst.count():
            self.lst.setCurrentRow(0)

    def _label(self, it):
        name = os.path.basename(it.get("src") or it.get("file") or "")
        cap = it.get("caption") or ""
        return "%s  --  %s" % (name, cap) if cap else name

    def _add_item(self, it):
        w = QListWidgetItem(self._label(it))
        w.setData(Qt.UserRole, it)
        self.lst.addItem(w)

    def _show_caption(self, i):
        it = self.lst.item(i).data(Qt.UserRole) if i >= 0 else None
        self.cap.setText((it or {}).get("caption") or "")

    def _set_caption(self, text):
        w = self.lst.currentItem()
        if w is None:
            return
        it = dict(w.data(Qt.UserRole))
        it["caption"] = text
        w.setData(Qt.UserRole, it)
        w.setText(self._label(it))

    def add_files(self, paths=None):
        if paths is None:
            paths, _f = QFileDialog.getOpenFileNames(
                self, tr('Add report images'), "", IMAGE_FILTER)
        for p in paths or ():
            self._add_item({"src": p, "caption": ""})
        if self.lst.count() and self.lst.currentRow() < 0:
            self.lst.setCurrentRow(0)

    def remove(self):
        i = self.lst.currentRow()
        if i >= 0:
            self.lst.takeItem(i)

    def move(self, step):
        i = self.lst.currentRow()
        j = i + step
        if i < 0 or not 0 <= j < self.lst.count():
            return
        w = self.lst.takeItem(i)
        self.lst.insertItem(j, w)
        self.lst.setCurrentRow(j)

    def items(self):
        return [dict(self.lst.item(i).data(Qt.UserRole))
                for i in range(self.lst.count())]
