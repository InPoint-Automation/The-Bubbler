# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# STEP preview chooser and viewer dialogs.

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QHBoxLayout,
                               QLabel, QPushButton, QRadioButton, QScrollArea,
                               QVBoxLayout)

from .i18n import tr
from .stepshade import UP_AXES
from . import step, steppreview

_VIEWS = ("upper_right_front", "upper_left_back")


def _to_pixmap(img):
    img = img.convert("RGB")
    q = QImage(img.tobytes(), img.width, img.height, img.width * 3,
               QImage.Format_RGB888)
    return QPixmap.fromImage(q.copy())


class StepChooseDialog(QDialog):
    """First-open picker for up-axis and list thumb."""

    def __init__(self, parent, step_path, up="z", view="upper_right_front"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(tr('3D preview'))
        self._step = step_path
        self._up = up
        self._view = view
        self._result = None
        v = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr('Which way is up:')))
        self.cb_up = QComboBox()
        self.cb_up.setProperty("i18n_skip", True)
        for a in UP_AXES:
            self.cb_up.addItem(a, a)
        self.cb_up.setCurrentText(up)
        self.cb_up.currentTextChanged.connect(self._reup)
        row.addWidget(self.cb_up)
        row.addStretch(1)
        v.addLayout(row)

        pics = QHBoxLayout()
        self._grp = QButtonGroup(self)
        self._labels = {}
        for name in _VIEWS:
            col = QVBoxLayout()
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumSize(160, 220)
            rb = QRadioButton(tr('Use as list thumb'))
            rb.setChecked(name == view)
            rb.toggled.connect(
                lambda on, nm=name: on and setattr(self, "_view", nm))
            self._grp.addButton(rb)
            col.addWidget(lbl)
            col.addWidget(rb, 0, Qt.AlignHCenter)
            pics.addLayout(col)
            self._labels[name] = lbl
        v.addLayout(pics)

        bw = QHBoxLayout()
        bw.addStretch(1)
        b_ok = QPushButton(tr('Use this preview'))
        b_ok.setDefault(True)
        b_ok.clicked.connect(self._ok)
        b_cancel = QPushButton(tr('Cancel'))
        b_cancel.clicked.connect(self.reject)
        bw.addWidget(b_ok)
        bw.addWidget(b_cancel)
        v.addLayout(bw)
        self._render()

    def _reup(self, up):
        self._up = up
        self._render()

    def _render(self):
        try:
            paths = step.render(self._step, up=self._up, size=260)
        except Exception:
            paths = None
        from PIL import Image
        for name, lbl in self._labels.items():
            if paths and name in paths:
                try:
                    pm = _to_pixmap(Image.open(paths[name]))
                    lbl.setPixmap(pm.scaled(160, 220, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))
                    continue
                except Exception:
                    pass
            lbl.setText(tr('(preview unavailable)'))

    def _ok(self):
        self._result = (self._up, self._view)
        self.accept()

    def result_choice(self):
        return self._result


class StepViewDialog(QDialog):
    """In-app reference panel with two side-by-side views."""

    def __init__(self, parent, cfg, pdf):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(tr('3D preview'))
        self.resize(680, 480)
        v = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        img = steppreview.preview_image(cfg, pdf, size=420)
        if img is not None:
            lbl.setPixmap(_to_pixmap(img))
        else:
            lbl.setText(tr('No 3D preview available.'))
        scroll.setWidget(lbl)
        v.addWidget(scroll)
        b = QPushButton(tr('Close'))
        b.clicked.connect(self.accept)
        v.addWidget(b, 0, Qt.AlignRight)
