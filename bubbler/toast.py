# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Auto-mode toasts. Non-blocking, one-click Correct.

from PySide6.QtCore import QObject, QTimer, QEvent, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from .i18n import tr

# defaults for cfg toast_secs / toast_stack
TOAST_MS = 2500
MAX_VISIBLE = 6
_GAP = 6
TEXT_MAX_PX = 360


def toast_timing(cfg):
    """(ms, cap) from cfg, clamped: 0.5-15 s, 1-20 toasts."""
    try:
        ms = int(round(float(cfg.get("toast_secs", TOAST_MS / 1000.0))
                       * 1000))
    except (TypeError, ValueError):
        ms = TOAST_MS
    try:
        cap = int(cfg.get("toast_stack", MAX_VISIBLE))
    except (TypeError, ValueError):
        cap = MAX_VISIBLE
    return min(15000, max(500, ms)), min(20, max(1, cap))


class _Toast(QFrame):
    def __init__(self, stack, text, on_correct, suffix=""):
        super().__init__(stack.host)
        self.setObjectName("bubblerToast")
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        # elide text, suffix kept whole
        self.label = QLabel()
        fm = self.label.fontMetrics()
        room = TEXT_MAX_PX - (fm.horizontalAdvance(suffix) if suffix else 0)
        shown = fm.elidedText(text, Qt.ElideRight, max(room, 40)) + suffix
        self.label.setText(shown)
        if shown != text + suffix:
            self.label.setToolTip(text + suffix)
        lay.addWidget(self.label)
        self.btn = QPushButton(tr('Correct...'))
        self.btn.clicked.connect(lambda: stack._correct(self, on_correct))
        lay.addWidget(self.btn)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(stack.ms)
        self.timer.timeout.connect(lambda: stack._expire(self))
        self.installEventFilter(stack)


class ToastStack(QObject):
    """Hover holds all. Leave restarts full length."""

    def __init__(self, host, ms=TOAST_MS, cap=MAX_VISIBLE):
        super().__init__(host)
        self.host = host
        self.ms, self.cap = int(ms), max(1, int(cap))
        self.toasts = []
        self._held = False
        host.installEventFilter(self)

    def show_toast(self, text, on_correct, suffix=""):
        t = _Toast(self, text, on_correct, suffix)
        self.toasts.append(t)
        while len(self.toasts) > self.cap:
            self._drop(self.toasts[0])
        t.adjustSize()
        t.show()
        t.raise_()
        if not self._held:
            t.timer.start()
        self._layout()
        return t

    def _drop(self, t):
        if t in self.toasts:
            self.toasts.remove(t)
        t.timer.stop()
        t.hide()
        t.deleteLater()
        # dropped toast sends no Leave
        if self._held and not any(x.underMouse() for x in self.toasts):
            self._held = False
            for x in self.toasts:
                x.timer.start()

    def _expire(self, t):
        if self._held:
            return
        self._drop(t)
        self._layout()

    def _correct(self, t, on_correct):
        self._drop(t)
        self._layout()
        on_correct()

    def _layout(self):
        vp = getattr(self.host, "viewport", None)
        area = vp().geometry() if callable(vp) else self.host.rect()
        y = area.bottom() - _GAP
        for t in reversed(self.toasts):
            t.adjustSize()
            y -= t.height()
            t.move(max(area.left() + _GAP,
                       area.right() - t.width() - _GAP * 2), y)
            y -= _GAP

    def eventFilter(self, obj, e):
        et = e.type()
        if obj is self.host and et == QEvent.Resize:
            self._layout()
        elif obj in self.toasts:
            if et == QEvent.Enter:
                self._held = True
                for t in self.toasts:
                    t.timer.stop()
            elif et == QEvent.Leave:
                self._held = False
                for t in self.toasts:
                    t.timer.start()
        return False
