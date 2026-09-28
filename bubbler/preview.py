# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Preview and print output PDF.

import os
import shutil

import fitz

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter, QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
                               QWidget, QLabel, QPushButton, QComboBox,
                               QFileDialog, QMessageBox)

from .i18n import tr

# app zoom step. Scale px per pt
ZOOM_IN, ZOOM_OUT = 1.25, 0.8
MIN_SCALE, MAX_SCALE = 0.02, 8.0       # A0 must still fit
MIN_ZOOM, MAX_ZOOM = 0.25, 16.0        # over fitted size
BASE_SCALE = 96 / 72.0
_PAD = 8                               # px around fitted page
# device px per page
PIXEL_BUDGET = 24e6
# device px all pages
TOTAL_BUDGET = 64e6


def _clamp(s):
    return max(MIN_SCALE, min(MAX_SCALE, s))


def fit_scale(page_w, page_h, vp_w, vp_h, mode="height", pad=_PAD):
    """Fit scale per page. Preview mixes sheet sizes."""
    if page_w <= 0 or page_h <= 0:
        return BASE_SCALE
    if mode == "width":
        return _clamp((vp_w - pad) / float(page_w))
    return _clamp((vp_h - pad) / float(page_h))


def budget_scale(page_w, page_h, scale, dpr=1.0, budget=PIXEL_BUDGET):
    px = page_w * page_h * (scale * dpr) ** 2
    if px <= budget or px <= 0:
        return scale
    return scale * (budget / px) ** 0.5


def render_page_image(page, dpi=96, dpr=1.0):
    s = dpi / 72.0 * dpr
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
    data = bytes(pix.samples)  # outlives .copy() below
    img = QImage(data, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
    img = img.copy()
    if dpr != 1.0:
        img.setDevicePixelRatio(dpr)
    return img


class PreviewDialog(QDialog):

    def __init__(self, parent, pdf_path, dpi=96, variants=None,
                 save_dir=None, attach=None, protect=()):
        """`variants`: [(label, path, default name)] this print job holds."""
        super().__init__(parent)
        self.setWindowTitle(tr('Output preview'))
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._variants = list(variants or [(tr('As saved'), pdf_path,
                                            os.path.basename(pdf_path))])
        self._save_dir = save_dir or os.path.dirname(pdf_path)
        self._attach = attach
        # Save as never overwrites these
        self._protect = {os.path.normcase(os.path.realpath(p)).lower()
                         for p in protect if p}
        self._path = pdf_path
        self._doc = fitz.open(pdf_path)
        self._mode = "height"          # "height" | "width"
        self._zoom = 1.0
        self.resize(720, 840)
        lay = QVBoxLayout(self)

        self._scroll = scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().installEventFilter(self)
        body = QWidget()
        self._col = col = QVBoxLayout(body)
        col.setAlignment(Qt.AlignTop)
        self._pages = []
        self._drawn = {}                   # page -> (scale, dpr)
        self._add_pages()
        scroll.setWidget(body)
        lay.addWidget(scroll)

        row = QHBoxLayout()
        b_out = QPushButton("−")
        b_out.setToolTip(tr('Zoom out'))
        b_out.clicked.connect(lambda: self.zoom_by(ZOOM_OUT))
        b_in = QPushButton("+")
        b_in.setToolTip(tr('Zoom in'))
        b_in.clicked.connect(lambda: self.zoom_by(ZOOM_IN))
        self._pct = QLabel()
        self._pct.setMinimumWidth(48)
        self._pct.setAlignment(Qt.AlignCenter)
        b_fh = QPushButton(tr('Fit height'))
        b_fh.clicked.connect(self.fit_height)
        b_fw = QPushButton(tr('Fit width'))
        b_fw.clicked.connect(self.fit_width)
        for w in (b_out, self._pct, b_in, b_fh, b_fw):
            row.addWidget(w)
        row.addStretch(1)
        self._which = QComboBox()
        for label, _path, _name in self._variants:
            self._which.addItem(label)
        self._which.setProperty("i18n_skip", True)
        self._which.setVisible(len(self._variants) > 1)
        self._which.currentIndexChanged.connect(self._pick)
        row.addWidget(self._which)
        if attach is not None:
            b_img = QPushButton(tr('Report images...'))
            b_img.setToolTip(tr('Add, caption or order the images shown '
                                'after the report rows.'))
            b_img.clicked.connect(self.edit_images)
            row.addWidget(b_img)
        b_save = QPushButton(tr('Save as...'))
        b_save.setToolTip(tr('Save what is shown as its own PDF.'))
        b_save.clicked.connect(self.save_as)
        row.addWidget(b_save)
        b_print = QPushButton(tr('Print...'))
        b_print.clicked.connect(self.print_pages)
        b_close = QPushButton(tr('Close'))
        b_close.clicked.connect(self.accept)
        row.addWidget(b_print)
        row.addWidget(b_close)
        lay.addLayout(row)

        for seq, fn in (("Ctrl+=", lambda: self.zoom_by(ZOOM_IN)),
                        ("Ctrl++", lambda: self.zoom_by(ZOOM_IN)),
                        ("Ctrl+-", lambda: self.zoom_by(ZOOM_OUT)),
                        ("Ctrl+0", self.fit_height)):
            QShortcut(QKeySequence(seq), self).activated.connect(fn)

        # resize storm renders once
        self._relayout_later = QTimer(self)
        self._relayout_later.setSingleShot(True)
        self._relayout_later.setInterval(60)
        self._relayout_later.timeout.connect(self._relayout)
        self._relayout()

    def _add_pages(self):
        for page in self._doc:
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignHCenter)
            self._col.addWidget(lbl)
            self._pages.append((lbl, page))

    def _pick(self, i):
        if not 0 <= i < len(self._variants):
            return
        path = self._variants[i][1]
        if path == self._path:
            return
        for lbl, _page in self._pages:
            self._col.removeWidget(lbl)
            lbl.deleteLater()
        self._pages, self._drawn = [], {}
        try:
            self._doc.close()
        except Exception:                                # pragma: no cover
            pass
        self._path = path
        self._doc = fitz.open(path)
        self._add_pages()
        self._relayout()

    def _release(self):
        """Release doc. Windows blocks re-save while open."""
        for lbl, _page in self._pages:
            self._col.removeWidget(lbl)
            lbl.deleteLater()
        self._pages, self._drawn = [], {}
        try:
            self._doc.close()
        except Exception:                                # pragma: no cover
            pass

    def edit_images(self):
        if not self._attach:
            return False
        shown = self._path
        self._release()
        got = None
        try:
            got = self._attach(self)
        finally:
            if not got:
                self._doc = fitz.open(shown)
                self._add_pages()
                self._relayout()
        if not got:
            return False
        keep = max(0, self._which.currentIndex())
        self._variants = list(got)
        self._which.blockSignals(True)
        self._which.clear()
        for label, _path, _name in self._variants:
            self._which.addItem(label)
        self._which.setVisible(len(self._variants) > 1)
        self._which.blockSignals(False)
        self._path = None
        i = min(keep, len(self._variants) - 1)
        self._which.setCurrentIndex(i)
        self._doc = fitz.open(self._variants[i][1])
        self._path = self._variants[i][1]
        self._add_pages()
        self._relayout()
        return True

    def save_as(self):
        name = self._variants[max(0, self._which.currentIndex())][2]
        dst, _flt = QFileDialog.getSaveFileName(
            self, tr('Save as...'), os.path.join(self._save_dir, name),
            "PDF (*.pdf)")
        if not dst:
            return ""
        if not dst.lower().endswith(".pdf"):
            dst += ".pdf"
        if os.path.normcase(os.path.realpath(dst)).lower() in self._protect:
            QMessageBox.warning(
                self, tr('Save as...'),
                tr('That is the drawing\'s own working file. Choose '
                   'another name.'))
            return ""
        try:
            if os.path.abspath(dst) != os.path.abspath(self._path):
                shutil.copyfile(self._path, dst)
        except OSError as e:
            QMessageBox.warning(self, tr('Save as...'), str(e))
            return ""
        return dst

    def _viewport(self):
        vp = self._scroll.viewport()
        return max(vp.width(), 1), max(vp.height(), 1)

    def _pad(self):
        """Body margins, else fit leaves scrollbar."""
        m = self._col.contentsMargins()
        if self._mode == "width":
            bar = self._scroll.verticalScrollBar()
            extra = 0 if bar.isVisible() else bar.sizeHint().width()
            return m.left() + m.right() + _PAD + extra
        return m.top() + m.bottom() + _PAD

    def _dpr(self):
        return float(self.devicePixelRatioF() or 1.0)

    def _fit(self, i):
        rect = self._pages[i][1].rect
        return fit_scale(rect.width, rect.height, *self._viewport(),
                         mode=self._mode, pad=self._pad())

    def zoom_cap(self):
        """Max zoom all pages fit in budget, so pages grow alike."""
        dpr = self._dpr()
        cap, total = MAX_ZOOM, 0.0
        for i, (_lbl, page) in enumerate(self._pages):
            a = page.rect.width * page.rect.height
            fit = self._fit(i)
            if a <= 0 or fit <= 0:
                continue
            cap = min(cap, (PIXEL_BUDGET / a) ** 0.5 / (fit * dpr))
            total += a * (fit * dpr) ** 2
        if total > 0:
            cap = min(cap, (TOTAL_BUDGET / total) ** 0.5)
        return max(1.0, cap)

    def scale_of(self, i):
        rect = self._pages[i][1].rect
        return budget_scale(rect.width, rect.height,
                            _clamp(self._fit(i) * self.zoom()), self._dpr())

    def zoom(self):
        """Zoom on screen. `_zoom` keeps the ask."""
        return min(self._zoom, self.zoom_cap())

    def _relayout(self):
        if self._doc is None:          # timer outlived dialog
            return
        dpr = self._dpr()
        for i, (lbl, page) in enumerate(self._pages):
            s = self.scale_of(i)
            if self._drawn.get(i) == (s, dpr):
                continue
            lbl.setPixmap(QPixmap.fromImage(
                render_page_image(page, 72.0 * s, dpr)))
            self._drawn[i] = (s, dpr)
        self._pct.setText("%d%%" % round(100.0 * self.zoom()))

    def set_zoom(self, factor):
        self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, factor))
        self._relayout()

    def zoom_by(self, factor):
        # from screen, else dead clicks
        self.set_zoom(self.zoom() * factor)

    def fit_height(self):
        self._mode, self._zoom = "height", 1.0
        self._relayout()

    def fit_width(self):
        self._mode, self._zoom = "width", 1.0
        self._relayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout_later.start()

    def eventFilter(self, obj, e):
        if (e.type() == QEvent.Wheel
                and e.modifiers() & Qt.ControlModifier):
            dy = e.angleDelta().y()
            if dy:
                self.zoom_by(ZOOM_IN if dy > 0 else ZOOM_OUT)
            return True
        return super().eventFilter(obj, e)

    def done(self, r):
        self._relayout_later.stop()
        try:
            self._doc.close()
        except Exception:                                # pragma: no cover
            pass
        self._doc = None
        super().done(r)

    def print_pages(self):
        try:
            from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        except Exception:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, tr('Print...'),
                tr('Printing not available in this build.'))
            return
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        try:
            accepted = dlg.exec() == QPrintDialog.DialogCode.Accepted
        finally:
            dlg.deleteLater()
        if not accepted:
            return
        painter = QPainter(printer)
        doc = fitz.open(self._path)
        try:
            for i, page in enumerate(doc):
                if i:
                    printer.newPage()
                img = render_page_image(page, 200)
                area = painter.viewport()
                scaled = img.scaled(area.size(), Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)
                x = (area.width() - scaled.width()) // 2
                y = (area.height() - scaled.height()) // 2
                painter.drawImage(x, y, scaled)
        finally:
            doc.close()
            painter.end()
