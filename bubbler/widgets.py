# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Canvas + measure-input widgets. Views forward input to `self.app`.

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QGraphicsView, QLineEdit

BUTTON_LEFT = Qt.MouseButton.LeftButton


def fill_keyed(combo, keys, current=None):
    from .i18n import tr
    combo.clear()
    for k in keys:
        combo.addItem(tr(k), k)
    if current is not None:
        set_combo_key(combo, current)


def combo_key(combo):
    return combo.currentData()


def set_combo_key(combo, key):
    i = combo.findData(key)
    combo.setCurrentIndex(i if i >= 0 else 0)


class PdfView(QGraphicsView):
    """Page pixmap + balloon overlay. Forwards input to app."""

    def __init__(self, scene, app):
        super().__init__(scene)
        self.app = app
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setAlignment(Qt.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setBackgroundBrush(QColor("#666666"))
        self._pan_last = None

    def scene_pt(self, ev):
        return self.mapToScene(ev.position().toPoint())

    def drawForeground(self, painter, rect):
        self.app.paint_overlay(painter)

    def mousePressEvent(self, e):
        self.setFocus()
        btn = e.button()
        mods = e.modifiers()
        sp = self.scene_pt(e)
        if btn == BUTTON_LEFT:
            if (mods & Qt.AltModifier) and (mods & Qt.ShiftModifier):
                self.app.on_alt_shift_click(sp)
            elif mods & Qt.ShiftModifier:
                self.app.on_shift_click(sp, e.globalPosition())
            elif mods & Qt.ControlModifier:
                self.app.on_ctrl_click(sp)
            else:
                self.app.on_press(sp, e.position(),
                                  predict=not bool(mods & Qt.AltModifier))
            return
        if btn in (Qt.MiddleButton, Qt.RightButton):
            if btn == Qt.RightButton and self.app.on_right_press(
                    sp, e.globalPosition()):
                return
            self._pan_last = e.position()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        btns = e.buttons()
        if self._pan_last is not None and (btns & (Qt.MiddleButton |
                                                   Qt.RightButton)):
            d = e.position() - self._pan_last
            self._pan_last = e.position()
            h = self.horizontalScrollBar()
            v = self.verticalScrollBar()
            h.setValue(h.value() - int(d.x()))
            v.setValue(v.value() - int(d.y()))
            return
        if btns & BUTTON_LEFT:
            sp = self.scene_pt(e)
            if self.app._capturing:
                self.app.on_capture_drag(sp)
            else:
                self.app.on_motion(sp, e.position())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan_last is not None and e.button() in (Qt.MiddleButton,
                                                         Qt.RightButton):
            self._pan_last = None
            return
        if e.button() == BUTTON_LEFT:
            sp = self.scene_pt(e)
            if self.app._capturing:
                self.app.on_capture_release(sp, e.globalPosition())
            else:
                self.app.on_release(sp, e.position())
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == BUTTON_LEFT and not (e.modifiers() & (
                Qt.AltModifier | Qt.ShiftModifier | Qt.ControlModifier)):
            self.app.on_double(self.scene_pt(e), e.globalPosition())
            return
        super().mouseDoubleClickEvent(e)

    def wheelEvent(self, e):
        self.app.on_wheel(e)

    def keyPressEvent(self, e):
        if self.app.on_key(e):
            return
        super().keyPressEvent(e)


class MeasureEdit(QLineEdit):
    """Measure-walk input. Walk navigation keys."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def keyPressEvent(self, e):
        k = e.key()
        mods = e.modifiers()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            if mods & Qt.ShiftModifier:
                self.app._walk_step(-1)
            else:
                self.app._walk_commit(+1)
            return
        if k == Qt.Key_Tab:
            self.app._walk_step(+1)
            return
        if k == Qt.Key_Backtab:
            self.app._walk_step(-1)
            return
        if k == Qt.Key_Down:
            self.app._walk_step(+1)
            return
        if k == Qt.Key_Up:
            self.app._walk_step(-1)
            return
        if k == Qt.Key_Escape:
            self.app._set_measure(False)
            return
        if not self.text().strip():
            if k in (Qt.Key_G, Qt.Key_Plus):
                self.app._measure_quick("GO")
                return
            if k in (Qt.Key_N, Qt.Key_Minus):
                self.app._measure_quick("NOGO")
                return
        super().keyPressEvent(e)
