# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Multi-page thumbnail navigator

import fitz

from PySide6.QtCore import Qt, QSize, QObject, QEvent, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QDockWidget, QListWidget, QListWidgetItem,
                               QListView)

from .i18n import tr

_THUMB_W = 120       # px, before layout
# px, thumb fills one column
_THUMB_MIN, _THUMB_MAX = 90, 400
_SPACING = 6
NAV_MIN_W = 120


def thumb_width(list_w, scrollbar_w, spacing=_SPACING):
    """Scrollbar always reserved, else oscillates."""
    w = int(list_w) - 2 * int(spacing) - int(scrollbar_w)
    return max(_THUMB_MIN, min(_THUMB_MAX, w))


class _ResizeWatch(QObject):
    """Own filter, not MainWindow.eventFilter."""

    def __init__(self, cb, parent=None):
        super().__init__(parent)
        self._cb = cb

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize:
            self._cb()
        return False


class NavMixin:
    def _build_nav(self):
        self.nav_dock = QDockWidget(tr('Pages'), self)
        self.nav_dock.setAllowedAreas(Qt.LeftDockWidgetArea
                                      | Qt.RightDockWidgetArea)
        self.nav_dock.setFeatures(QDockWidget.DockWidgetClosable
                                  | QDockWidget.DockWidgetMovable)
        lst = QListWidget()
        lst.setViewMode(QListView.IconMode)
        # upper bound, fits 1:3 strip
        lst.setIconSize(QSize(_THUMB_MAX, int(_THUMB_MAX * 3)))
        lst.setResizeMode(QListWidget.Adjust)
        lst.setMovement(QListView.Static)
        lst.setSpacing(_SPACING)
        lst.setUniformItemSizes(False)
        lst.itemClicked.connect(lambda it: self.goto_page(it.data(Qt.UserRole)))
        self._nav_list = lst
        self._nav_w = 0
        self._nav_timer = QTimer(self)
        self._nav_timer.setSingleShot(True)
        self._nav_timer.setInterval(150)
        self._nav_timer.timeout.connect(self._nav_refit)
        self._nav_watch = _ResizeWatch(self._nav_timer.start, lst)
        lst.installEventFilter(self._nav_watch)
        self.nav_dock.setWidget(lst)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.nav_dock)
        self.nav_dock.hide()
        self.nav_dock.visibilityChanged.connect(self._nav_vis)

    def goto_page(self, i):
        i = max(0, min(int(i), self.doc.page_count - 1))
        if i != self.page_i:
            self.page_i = i
            self.render()
            self._sync_gentol()
        self._nav_highlight()

    def toggle_nav(self):
        if self.nav_dock.isVisible():
            self.nav_dock.hide()
        else:
            self._apply_nav_width()
            self.nav_dock.show()
            self._nav_populate()

    def _nav_target_w(self):
        lst = self._nav_list
        if lst.width() <= 1:             # not laid out yet
            return _THUMB_W
        sb = lst.verticalScrollBar().sizeHint().width()
        return thumb_width(lst.contentsRect().width(), sb)

    def _nav_refit(self):
        if self.nav_dock.isVisible():
            self._nav_populate()

    def _nav_populate(self, w=None):
        w = int(w or self._nav_target_w())
        lst = self._nav_list
        n = self.doc.page_count
        if w == self._nav_w and lst.count() == n:
            return
        try:
            dpr = float(lst.devicePixelRatioF() or 1.0)
        except Exception:                                # pragma: no cover
            dpr = 1.0
        lst.clear()
        for i in range(n):
            lst.addItem(self._nav_item(self.doc[i], i, w, dpr))
        self._nav_w = w
        self._nav_highlight()

    def _nav_item(self, page, i, w, dpr):
        s = w * dpr / max(1.0, page.rect.width)
        pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
        fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
        data = bytes(pix.samples)          # outlives the .copy() below
        img = QImage(data, pix.width, pix.height, pix.stride, fmt).copy()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        it = QListWidgetItem(QIcon(pm), str(i + 1))
        it.setData(Qt.UserRole, i)
        it.setTextAlignment(Qt.AlignHCenter)
        return it

    def _apply_nav_width(self):
        if getattr(self, "_nav_w_done", False):
            return
        self._nav_w_done = True
        try:
            w = int(self.cfg.get("nav_w") or 0)
        except (TypeError, ValueError):
            return
        if w < NAV_MIN_W:                 # first run
            return
        cap = int(self.width() * 0.6)
        if cap >= NAV_MIN_W:
            w = min(w, cap)
        self.resizeDocks([self.nav_dock], [w], Qt.Horizontal)

    def _save_nav_width(self):
        try:
            if not self.nav_dock.isVisible() or self.nav_dock.isFloating():
                return                    # stale window width
            w = int(self.nav_dock.width())
        except Exception:
            return
        if w >= NAV_MIN_W:
            self.cfg["nav_w"] = w

    def _nav_highlight(self):
        lst = getattr(self, "_nav_list", None)
        if lst is not None and 0 <= self.page_i < lst.count():
            lst.setCurrentRow(self.page_i)

    def _nav_vis(self, vis):
        if not vis:
            # save before hide, not floating
            try:
                w = (0 if self.nav_dock.isFloating()
                     else int(self.nav_dock.width()))
            except Exception:
                w = 0
            if w >= NAV_MIN_W:
                self.cfg["nav_w"] = w
        btn = getattr(self, "btn_nav", None)
        if btn is not None and btn.isChecked() != vis:
            btn.setChecked(vis)
