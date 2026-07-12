# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# calculator

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDockWidget, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from .calc import format_num, safe_eval
from .i18n import tr

_ACTIVE = "#2b6cb0"
_IDLE = "#c8c8c8"


class CalcEdit(QLineEdit):
    """Calculator entry. Enter evaluates"""

    def __init__(self, panel):
        super().__init__()
        self.panel = panel

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.panel.evaluate()
            return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.panel._set_active(True)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.panel._set_active(False)


class CalcPanel(QWidget):
    """Keypad calculator. Result -> measure field or clipboard."""

    _KEYS = [
        ("C", "7", "8", "9", "/"),
        ("(", "4", "5", "6", "*"),
        (")", "1", "2", "3", "-"),
        ("<", "0", ".", "=", "+"),
    ]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._just_eval = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame()
        self.frame.setObjectName("calcframe")
        outer.addWidget(self.frame)
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)
        self.disp = CalcEdit(self)
        self.disp.setAlignment(Qt.AlignRight)
        root.addWidget(self.disp)
        self.res = QLabel("")
        self.res.setStyleSheet("color:#217346; font-size:10pt;")
        self.res.setAlignment(Qt.AlignRight)
        root.addWidget(self.res)
        grid = QGridLayout()
        grid.setSpacing(3)
        for r, row in enumerate(self._KEYS):
            for c, key in enumerate(row):
                b = QPushButton(key)
                b.setMinimumSize(38, 32)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(lambda _=False, k=key: self._press(k))
                grid.addWidget(b, r, c)
        root.addLayout(grid)
        row2 = QHBoxLayout()
        self.b_send = QPushButton(tr('To measure'))
        self.b_send.setFocusPolicy(Qt.NoFocus)
        self.b_send.setToolTip(tr('Send result to the measure field'))
        self.b_send.clicked.connect(self._send)
        b_copy = QPushButton(tr('Copy'))
        b_copy.setFocusPolicy(Qt.NoFocus)
        b_copy.clicked.connect(self._copy)
        row2.addWidget(self.b_send)
        row2.addWidget(b_copy)
        root.addLayout(row2)
        self._set_active(False)

    def _set_active(self, on):
        """Highlight panel while focused."""
        col = _ACTIVE if on else _IDLE
        self.frame.setStyleSheet(
            "#calcframe { border:2px solid %s; border-radius:4px; }" % col)
        self.disp.setStyleSheet(
            "font-size:14pt; padding:4px; border:1px solid %s;"
            "background:%s;" % (col, "#eef6ff" if on else "#ffffff"))

    def _press(self, key):
        if key == "C":
            self.disp.clear()
            self.res.setText("")
            self._just_eval = False
        elif key == "<":
            self.disp.backspace()
        elif key == "=":
            self.evaluate()
        else:
            if self._just_eval and key not in "+-*/":
                self.disp.clear()
            self._just_eval = False
            self.disp.insert(key)
        self.disp.setFocus()

    def evaluate(self):
        v = safe_eval(self.disp.text())
        if v is None:
            self.res.setText(tr('invalid'))
            return
        out = format_num(v)
        self.disp.setText(out)
        self.res.setText("= " + out)
        self.disp.setCursorPosition(len(out))
        self._just_eval = True

    def _result_text(self):
        v = safe_eval(self.disp.text())
        return format_num(v) if v is not None else self.disp.text().strip()

    def _send(self):
        self.app._calc_send(self._result_text())

    def _copy(self):
        QApplication.clipboard().setText(self._result_text())
        self.app.set_status(tr('result copied'))


class CalcMixin:
    def _build_calc(self):
        self.calc_panel = CalcPanel(self)
        self._calc_dock = QDockWidget(tr('Calculator'), self)
        self._calc_dock.setObjectName("calc_dock")
        self._calc_dock.setWidget(self.calc_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self._calc_dock)
        # float by default, not docked
        self._calc_dock.setFloating(True)
        self._calc_dock.resize(230, 300)
        self._calc_dock.hide()
        self._calc_dock.visibilityChanged.connect(self._calc_vis_changed)
        sc = QShortcut(QKeySequence("Ctrl+K"), self)
        sc.activated.connect(self.toggle_calc)

    def toggle_calc(self):
        show = not self._calc_dock.isVisible()
        if show and not self._calc_dock.isFloating():
            self._calc_dock.setFloating(True)
        self._calc_dock.setVisible(show)
        if show:
            self._calc_dock.raise_()
            self.calc_panel.disp.setFocus()

    def _calc_vis_changed(self, on):
        try:
            self.btn_calc.setChecked(bool(on))
        except Exception:
            pass

    def _calc_send(self, value):
        """Result to measure field, else clipboard."""
        if getattr(self, "measure_mode", False) and getattr(self, "ment",
                                                            None) is not None:
            self.ment.setText(value)
            self.ment.setFocus()
            self.ment.selectAll()
            self.set_status(tr('result -> measure field'))
        else:
            QApplication.clipboard().setText(value)
            self.set_status(tr('not measuring; result copied'))
