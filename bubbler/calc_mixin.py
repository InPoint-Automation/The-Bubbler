# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# floating calculator dock and keypad

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDockWidget, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from .calc import format_num, safe_eval
from .i18n import tr
from .units import INCH, MM, convert_units

_ACTIVE = "#2b6cb0"
_IDLE = "#c8c8c8"
HIST_MAX = 10          # dimension stack cap

# a real-calculator look: base keys, then role tints (operator/equals/clear/
# function/send) via the calcrole property
_CALC_QSS = """
#calcframe QPushButton {
    border:1px solid #c3ccd6; border-radius:6px; background:#f7f9fc;
    font-size:12pt; color:#1f2d3d; padding:2px; }
#calcframe QPushButton:hover { background:#eef4fc; border-color:#9bbce6; }
#calcframe QPushButton:pressed { background:#dce8f7; }
#calcframe QPushButton[calcrole="num"] { background:#ffffff; }
#calcframe QPushButton[calcrole="op"] {
    background:#eaf1fb; color:#1f3f73; font-weight:bold; }
#calcframe QPushButton[calcrole="fn"] {
    background:#f0f2f5; color:#334; font-size:10pt; }
#calcframe QPushButton[calcrole="eq"] {
    background:#2b6cb0; color:#ffffff; font-weight:bold; }
#calcframe QPushButton[calcrole="eq"]:hover { background:#3a7cc0; }
#calcframe QPushButton[calcrole="clear"] {
    background:#fbeaea; color:#a03030; font-weight:bold; }
#calcframe QPushButton[calcrole="send"] {
    background:#e6f4ea; color:#217346; font-weight:bold; }
QListWidget#calchist { border:1px solid #d4dae2; border-radius:4px;
    background:#fbfcfe; font-family:monospace; font-size:9pt; }
QListWidget#calchist::item { padding:2px 4px; }
QListWidget#calchist::item:hover { background:#eef4fc; }
"""


class CalcEdit(QLineEdit):
    """Enter evaluates expression"""

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
    """Keypad calculator feeding measure field or clipboard"""

    _KEYS = [
        ("C", "7", "8", "9", "/"),
        ("(", "4", "5", "6", "*"),
        (")", "1", "2", "3", "-"),
        ("<", "0", ".", "=", "+"),
    ]

    # QA/QC function buttons: (label, kind, payload, tooltip)
    #   "ins" inserts a token, "op" applies a function to the current value
    _FUNCS_A = (
        (u"√", "ins", "sqrt(", 'Square root'),
        (u"x²", "op", lambda v: v * v, 'Square the value'),
        ("1/x", "op", lambda v: 1.0 / v, 'Reciprocal'),
        (u"±", "op", lambda v: -v, 'Negate'),
        (u"π", "ins", "pi", 'Pi'),
    )
    _FUNCS_B = (
        ("sin", "ins", "sind(", 'Sine of degrees'),
        ("cos", "ins", "cosd(", 'Cosine of degrees'),
        ("tan", "ins", "tand(", 'Tangent of degrees'),
        ("%", "op", lambda v: v / 100.0, 'Percent'),
        ("TP", "ins", "tp(", 'True position from x, y deviation: tp(x, y)'),
    )

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._just_eval = False
        self.setMinimumSize(300, 430)   # a real calculator, not a strip
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame()
        self.frame.setObjectName("calcframe")
        self.frame.setStyleSheet(_CALC_QSS)
        outer.addWidget(self.frame)
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)
        self.disp = CalcEdit(self)
        self.disp.setAlignment(Qt.AlignRight)
        root.addWidget(self.disp)
        self.res = QLabel("")
        self.res.setStyleSheet("color:#217346; font-size:11pt; font-weight:bold;")
        self.res.setAlignment(Qt.AlignRight)
        root.addWidget(self.res)

        # QA/QC function rows
        for spec in (self._FUNCS_A, self._FUNCS_B):
            fg = QGridLayout()
            fg.setSpacing(4)
            for c, (lab, kind, payload, tip) in enumerate(spec):
                b = QPushButton(lab)
                b.setProperty("i18n_skip", True)
                b.setProperty("calcrole", "fn")
                b.setMinimumSize(46, 30)
                b.setFocusPolicy(Qt.NoFocus)
                b.setToolTip(tr(tip))
                if kind == "ins":
                    b.clicked.connect(lambda _=False, t=payload: self._insert(t))
                else:
                    b.clicked.connect(
                        lambda _=False, f=payload, t=lab: self._apply(f, t))
                fg.addWidget(b, 0, c)
            root.addLayout(fg)

        grid = QGridLayout()
        grid.setSpacing(4)
        for r, row in enumerate(self._KEYS):
            for c, key in enumerate(row):
                b = QPushButton(key)
                b.setProperty("i18n_skip", True)
                b.setProperty("calcrole", self._role(key))
                b.setMinimumSize(46, 38)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(lambda _=False, k=key: self._press(k))
                grid.addWidget(b, r, c)
        root.addLayout(grid)

        # convert display both ways
        row1 = QHBoxLayout()
        self.b_in_mm = QPushButton(u"in → mm")
        self.b_in_mm.setProperty("i18n_skip", True)
        self.b_in_mm.setFocusPolicy(Qt.NoFocus)
        self.b_in_mm.setToolTip(tr('Read value as inches, convert to mm'))
        self.b_in_mm.clicked.connect(lambda: self._convert(INCH, MM))
        self.b_mm_in = QPushButton(u"mm → in")
        self.b_mm_in.setProperty("i18n_skip", True)
        self.b_mm_in.setFocusPolicy(Qt.NoFocus)
        self.b_mm_in.setToolTip(tr('Read value as mm, convert to inches'))
        self.b_mm_in.clicked.connect(lambda: self._convert(MM, INCH))
        row1.addWidget(self.b_in_mm)
        row1.addWidget(self.b_mm_in)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        self.b_send = QPushButton(tr('To measure'))
        self.b_send.setProperty("calcrole", "send")
        self.b_send.setFocusPolicy(Qt.NoFocus)
        self.b_send.setToolTip(tr('Send result to measure field'))
        self.b_send.clicked.connect(self._send)
        b_copy = QPushButton(tr('Copy'))
        b_copy.setFocusPolicy(Qt.NoFocus)
        b_copy.clicked.connect(self._copy)
        row2.addWidget(self.b_send)
        row2.addWidget(b_copy)
        root.addLayout(row2)

        hrow = QHBoxLayout()
        _hl = QLabel(tr('History'))
        _hl.setStyleSheet("color:#666666; font-size:8pt;")
        b_hclr = QPushButton(tr('Clear'))
        b_hclr.setProperty("i18n_skip", True)
        b_hclr.setFocusPolicy(Qt.NoFocus)
        b_hclr.setMaximumWidth(64)
        b_hclr.setToolTip(tr('Clear the history'))
        b_hclr.clicked.connect(self._hist_clear)
        hrow.addWidget(_hl)
        hrow.addStretch(1)
        hrow.addWidget(b_hclr)
        root.addLayout(hrow)
        self.hist = QListWidget()
        self.hist.setObjectName("calchist")
        self.hist.setFocusPolicy(Qt.NoFocus)
        self.hist.setMaximumHeight(120)
        self.hist.setToolTip(tr('Click to reuse the expression; '
                                'double-click to use the result'))
        self.hist.itemClicked.connect(self._hist_pick)
        self.hist.itemDoubleClicked.connect(self._hist_pick_result)
        root.addWidget(self.hist)
        self.load_history(getattr(app, "cfg", {}).get("calc_history"))
        self._set_active(False)

    @staticmethod
    def _role(key):
        if key in "+-*/":
            return "op"
        if key == "=":
            return "eq"
        if key == "C":
            return "clear"
        return "num"

    def _insert(self, text):
        self._just_eval = False
        self.disp.insert(text)
        self.disp.setFocus()

    def _apply(self, fn, tag):
        """Apply a function to the current value, in place."""
        v = safe_eval(self.disp.text())
        if v is None:
            self.res.setText(tr('invalid'))
            return
        try:
            r = fn(v)
        except (ValueError, ZeroDivisionError, OverflowError):
            self.res.setText(tr('invalid'))
            return
        out = format_num(r)
        self._hist_push("%s %s" % (format_num(v), tag), out)
        self.disp.setText(out)
        self.res.setText("= " + out)
        self.disp.setCursorPosition(len(out))
        self._just_eval = True
        self.disp.setFocus()

    def _hist_clear(self):
        self.hist.clear()

    def _hist_pick_result(self, item):
        """Double-click: drop the RESULT into the display, to chain."""
        res = str(item.data(Qt.UserRole + 1))
        self.disp.setText(res)
        self.disp.setCursorPosition(len(res))
        self._just_eval = True
        self.disp.setFocus()

    # ---- history ----

    def load_history(self, rows):
        """Fill list from saved [expr, result] pairs"""
        self.hist.clear()
        for r in (rows or [])[:HIST_MAX]:
            try:
                expr, res = str(r[0]), str(r[1])
            except Exception:
                continue
            if expr and res:
                self._hist_add(expr, res)

    def _hist_add(self, expr, res, at=None):
        it = QListWidgetItem("%s = %s" % (expr, res))
        it.setData(Qt.UserRole, expr)
        it.setData(Qt.UserRole + 1, res)
        if at is None:
            self.hist.addItem(it)
        else:
            self.hist.insertItem(at, it)

    def _hist_push(self, expr, res):
        """Newest first deduped by expression"""
        for i in range(self.hist.count() - 1, -1, -1):
            if self.hist.item(i).data(Qt.UserRole) == expr:
                self.hist.takeItem(i)
        self._hist_add(expr, res, at=0)
        while self.hist.count() > HIST_MAX:
            self.hist.takeItem(self.hist.count() - 1)

    def history(self):
        """Saved form list of [expr, result]"""
        out = []
        for i in range(self.hist.count()):
            it = self.hist.item(i)
            out.append([it.data(Qt.UserRole), it.data(Qt.UserRole + 1)])
        return out

    def _hist_pick(self, item):
        """Reuse expression not result"""
        expr = item.data(Qt.UserRole)
        self.disp.setText(expr)
        self.disp.setCursorPosition(len(expr))
        self.res.setText("= " + str(item.data(Qt.UserRole + 1)))
        self._just_eval = False
        self.disp.setFocus()

    def _set_active(self, on):
        """Highlight panel while focused"""
        col = _ACTIVE if on else _IDLE
        self.frame.setStyleSheet(
            _CALC_QSS
            + "#calcframe { border:2px solid %s; border-radius:6px; }" % col)
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
        expr = self.disp.text().strip()
        v = safe_eval(expr)
        if v is None:
            self.res.setText(tr('invalid'))
            return
        out = format_num(v)
        if expr and expr != out:
            self._hist_push(expr, out)
        self.disp.setText(out)
        self.res.setText("= " + out)
        self.disp.setCursorPosition(len(out))
        self._just_eval = True

    def _convert(self, src, dst):
        """Convert display one scaling no round trip"""
        v = safe_eval(self.disp.text())
        if v is None:
            self.res.setText(tr('invalid'))
            return
        out = format_num(convert_units(v, src, dst))
        tag = "in -> mm" if dst == MM else "mm -> in"
        self._hist_push("%s %s" % (format_num(v), tag), out)
        self.disp.setText(out)
        self.res.setText("= %s %s" % (out, "mm" if dst == MM else "in"))
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
        # float by default
        self._calc_dock.setFloating(True)
        self._calc_dock.resize(320, 470)
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
        self.calc_panel.disp.setFocus()      # ready to type

    def _calc_save_history(self):
        """Persist tape into cfg caller saves"""
        try:
            self.cfg["calc_history"] = self.calc_panel.history()
        except Exception:
            pass

    def _calc_vis_changed(self, on):
        try:
            self.btn_calc.setChecked(bool(on))
        except Exception:
            pass

    def _calc_send(self, value):
        """Result to measure field else clipboard"""
        if getattr(self, "measure_mode", False) and getattr(self, "ment",
                                                            None) is not None:
            self.ment.setText(value)
            self.ment.setFocus()
            self.ment.selectAll()
            self.set_status(tr('result -> measure field'))
        else:
            QApplication.clipboard().setText(value)
            self.set_status(tr('not measuring; result copied'))
