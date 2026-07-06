# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Multi-page thumbnail navigator. Dockable, click to jump.

import fitz

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QDockWidget, QListWidget, QListWidgetItem,
                               QListView)

from .i18n import tr

_THUMB_W = 120       # px


class NavMixin:
    def _build_nav(self):
        self.nav_dock = QDockWidget(tr('Pages'), self)
        self.nav_dock.setAllowedAreas(Qt.LeftDockWidgetArea
                                      | Qt.RightDockWidgetArea)
        self.nav_dock.setFeatures(QDockWidget.DockWidgetClosable
                                  | QDockWidget.DockWidgetMovable)
        lst = QListWidget()
        lst.setViewMode(QListView.IconMode)
        lst.setIconSize(QSize(_THUMB_W, int(_THUMB_W * 1.4)))
        lst.setResizeMode(QListWidget.Adjust)
        lst.setMovement(QListView.Static)
        lst.setSpacing(6)
        lst.setUniformItemSizes(True)
        lst.itemClicked.connect(lambda it: self.goto_page(it.data(Qt.UserRole)))
        self._nav_list = lst
        self._nav_built = False
        self.nav_dock.setWidget(lst)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.nav_dock)
        self.nav_dock.hide()
        self.nav_dock.visibilityChanged.connect(self._nav_vis)

    def goto_page(self, i):
        i = max(0, min(int(i), self.doc.page_count - 1))
        if i != self.page_i:
            self.page_i = i
            self.render()
        self._nav_highlight()

    def toggle_nav(self):
        if self.nav_dock.isVisible():
            self.nav_dock.hide()
        else:
            self._nav_populate()
            self.nav_dock.show()

    def _nav_populate(self):
        if self._nav_built:
            return
        lst = self._nav_list
        lst.clear()
        for i in range(self.doc.page_count):
            page = self.doc[i]
            s = _THUMB_W / max(1.0, page.rect.width)
            pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
            fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
            img = QImage(bytes(pix.samples), pix.width, pix.height,
                         pix.stride, fmt)
            it = QListWidgetItem(QIcon(QPixmap.fromImage(img)), str(i + 1))
            it.setData(Qt.UserRole, i)
            it.setTextAlignment(Qt.AlignHCenter)
            lst.addItem(it)
        self._nav_built = True
        self._nav_highlight()

    def _nav_highlight(self):
        lst = getattr(self, "_nav_list", None)
        if lst is not None and 0 <= self.page_i < lst.count():
            lst.setCurrentRow(self.page_i)

    def _nav_vis(self, vis):
        btn = getattr(self, "btn_nav", None)
        if btn is not None and btn.isChecked() != vis:
            btn.setChecked(vis)
