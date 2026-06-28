# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Context-sensitive hotbar. Floating pill of keyed actions.

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QWidget, QLabel, QGridLayout,
                               QHBoxLayout, QVBoxLayout,
                               QGraphicsDropShadowEffect)

MAX_ACTIONS = 10
COLS = 5

GRAD_PILL = ("qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f8fbfe, "
             "stop:1 #dde7f3)")
GRAD_CELL = "transparent"
GRAD_HOVER = ("qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fdfcf6, "
              "stop:0.5 #fdf4cf, stop:0.5 #ffec9d, stop:1 #ffe78e)")
GRAD_FLASH = ("qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #5d8fd4, "
              "stop:0.5 #386bb0, stop:0.5 #2b579a, stop:1 #4377bf)")
GRAD_KEY = ("qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fbfdff, "
            "stop:1 #d4e2f5)")
BG = GRAD_CELL
BG_HOVER = GRAD_HOVER
BG_FLASH = GRAD_FLASH
FG_KEY = "#1f3f73"
FG_LABEL = "#1e1e1e"
FG_MUTED = "#9aa6b6"
FG_STATE = "#1e7c2f"
BORDER = "#9bb4d4"
KEY_BORDER = "#9bbce6"
FLASH_MS = 150


class HotbarAction(object):
    """One hotbar entry. `command` runs on click and on keypress."""

    def __init__(self, name, key, label, command, enabled=True):
        self.name = name
        self.key = key
        self.label = label
        self.command = command
        self.enabled = enabled


class HotbarCell(QWidget):
    """Key badge + label; hover, flash, disabled dimming."""

    def __init__(self, on_click):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)  # paint styled bg
        self._on_click = on_click
        self._action = None
        self._flashing = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 10, 5)
        lay.setSpacing(6)
        self.key_lbl = QLabel("")
        self.key_lbl.setAlignment(Qt.AlignCenter)
        self.txt_lbl = QLabel("")
        lay.addWidget(self.key_lbl)
        lay.addWidget(self.txt_lbl)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._unflash)
        self._paint(BG)

    def set_action(self, action):
        self._action = action
        self._flashing = False
        self.key_lbl.setText(action.key)
        self.txt_lbl.setText(action.label)
        enabled = action.enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self._paint(BG, key_fg=FG_KEY if enabled else FG_MUTED,
                    txt_fg=FG_LABEL if enabled else FG_MUTED)

    def _paint(self, bg, key_fg=FG_KEY, txt_fg=FG_LABEL,
               border="transparent", key_glossy=True):
        self.setStyleSheet(
            "HotbarCell{background:%s; border:1px solid %s;"
            "border-radius:5px;}" % (bg, border))
        if key_glossy:
            self.key_lbl.setStyleSheet(
                "background:%s; color:%s; border:1px solid %s;"
                "padding:1px 6px; border-radius:4px;"
                "font-family:Consolas,monospace; font-weight:bold;"
                % (GRAD_KEY, key_fg, KEY_BORDER))
        else:
            self.key_lbl.setStyleSheet(
                "background:transparent; color:%s; padding:1px 6px;"
                "font-family:Consolas,monospace; font-weight:bold;" % key_fg)
        self.txt_lbl.setStyleSheet(
            "background:transparent; border:0px; color:%s;" % txt_fg)

    def enterEvent(self, _e):
        if self._action and self._action.enabled and not self._flashing:
            self._paint(BG_HOVER, border="#e5c365")

    def leaveEvent(self, _e):
        if self._action and self._action.enabled and not self._flashing:
            self._paint(BG)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._action \
                and self._action.enabled:
            self.flash()
            self._on_click(self._action)

    def flash(self):
        self._flashing = True
        self._paint(BG_FLASH, key_fg="white", txt_fg="white",
                    border="#244c84", key_glossy=False)
        self._timer.start(FLASH_MS)

    def _unflash(self):
        self._flashing = False
        if self._action is not None:
            self.set_action(self._action)


class Hotbar(QFrame):
    """The pill of keyed action cells."""

    def __init__(self, parent, on_action, on_hide):
        super().__init__(parent)
        self._on_action = on_action
        self._actions = []
        self._by_key = {}
        self.setStyleSheet(
            "QFrame{background:%s; border:1px solid %s; border-radius:9px;}"
            % (GRAD_PILL, BORDER))
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 2, 6, 2)
        outer.setSpacing(4)
        gridw = QWidget()
        self._grid = QGridLayout(gridw)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(2)
        self._cells = []
        for i in range(MAX_ACTIONS):
            c = HotbarCell(self._cell_clicked)
            self._grid.addWidget(c, i // COLS, i % COLS)
            c.hide()
            self._cells.append(c)
        outer.addWidget(gridw)
        side = QWidget()
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 4, 6, 4)
        self._hide_btn = QLabel("▾")
        self._hide_btn.setStyleSheet("color:%s; font-size:12pt;" % FG_MUTED)
        self._hide_btn.setCursor(Qt.PointingHandCursor)
        self._hide_btn.mousePressEvent = lambda _e: on_hide()
        self.state_lbl = QLabel("")
        self.state_lbl.setStyleSheet("color:%s; font-size:8pt;" % FG_STATE)
        self.state_lbl.setAlignment(Qt.AlignRight)
        sv.addWidget(self._hide_btn, alignment=Qt.AlignTop)
        sv.addStretch(1)
        sv.addWidget(self.state_lbl, alignment=Qt.AlignBottom)
        outer.addWidget(side)

    def set_actions(self, actions):
        self._actions = list(actions)[:MAX_ACTIONS]
        self._by_key = {}
        for i, cell in enumerate(self._cells):
            if i < len(self._actions):
                a = self._actions[i]
                cell.set_action(a)
                cell.show()
                for k in self._dispatch_keys(a.key):
                    self._by_key[k] = (a, cell)
            else:
                cell.hide()
        self.adjustSize()

    @staticmethod
    def _dispatch_keys(key):
        k = key.strip()
        if any(c in k for c in u"←↑→↓"):
            return []
        if "-" in k and len(k) == 3 and k[0].isdigit() and k[2].isdigit():
            return [str(d) for d in range(int(k[0]), int(k[2]) + 1)]
        if k.upper() == "DEL":
            return ["\x7f", "DEL"]
        return [k.lower(), k.upper()]

    def set_state_text(self, text):
        self.state_lbl.setText(text)

    def press(self, key):
        hit = self._by_key.get(key) or self._by_key.get(str(key).lower())
        if not hit:
            return False
        action, cell = hit
        if not action.enabled:
            return True
        cell.flash()
        self._on_action(action, key)
        return True

    def flash_key(self, key):
        hit = self._by_key.get(key) or self._by_key.get(str(key).lower())
        if hit:
            hit[1].flash()

    def flash_name(self, name):
        for i, a in enumerate(self._actions):
            if a.name == name:
                self._cells[i].flash()
                return

    def _cell_clicked(self, action):
        self._on_action(action, None)
