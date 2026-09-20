# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Preview and print output PDF

import fitz

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QPainter
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
                               QWidget, QLabel, QPushButton)

from .i18n import tr


def render_page_image(page, dpi=96):
    """One PDF page to QImage detached from pixmap buffer."""
    s = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
    data = bytes(pix.samples)  # outlives .copy() below
    img = QImage(data, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
    return img.copy()


class PreviewDialog(QDialog):
    """Scrollable PDF preview with Print button."""

    def __init__(self, parent, pdf_path, dpi=96):
        super().__init__(parent)
        self.setWindowTitle(tr('Output preview'))
        # frees pixmaps on close
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._path = pdf_path
        self.resize(720, 840)
        lay = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        col = QVBoxLayout(body)
        col.setAlignment(Qt.AlignTop)
        doc = fitz.open(pdf_path)
        try:
            for page in doc:
                lbl = QLabel()
                lbl.setAlignment(Qt.AlignHCenter)
                lbl.setPixmap(QPixmap.fromImage(render_page_image(page, dpi)))
                col.addWidget(lbl)
        finally:
            doc.close()
        scroll.setWidget(body)
        lay.addWidget(scroll)

        row = QHBoxLayout()
        row.addStretch(1)
        b_print = QPushButton(tr('Print...'))
        b_print.clicked.connect(self.print_pages)
        b_close = QPushButton(tr('Close'))
        b_close.clicked.connect(self.accept)
        row.addWidget(b_print)
        row.addWidget(b_close)
        lay.addLayout(row)

    def print_pages(self):
        """Paint rendered pages onto QPrinter."""
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
