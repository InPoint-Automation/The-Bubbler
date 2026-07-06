# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Export + close mixin. Writes xlsx + ballooned PDF.

import os

import fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .common import (RADIUS, FONTSZ, WHITE, LEADER_EXITS, base_of,
                     qc_path, tier_rgb, tier_shape, bubble_shape_points)
from .scanpos import xform_pt
from .i18n import tr


class ExportMixin:
    def unsaved(self):
        return sum(1 for d in self.ledger if d.get("sheet_row") is None)

    def closeEvent(self, e):
        if self.unsaved():
            r = QMessageBox.question(
                self, tr('Unsaved'),
                tr('%d unsaved row(s). Quit anyway?')
                % self.unsaved())
            if r != QMessageBox.Yes:
                e.ignore()
                return
        self._save_session()
        e.accept()

    def save(self):
        out_pdf = qc_path(self.pdf_path, "_Inspection.pdf",
                          subdir=self.cfg.get("qc_subdir", "qc"))
        od = os.path.dirname(out_pdf)
        if od and not os.path.isdir(od):
            try:
                os.makedirs(od, exist_ok=True)
            except PermissionError:
                out_pdf = qc_path(self.pdf_path, "_Inspection.pdf", subdir="")
        dlg = None
        doc = None
        try:
            doc = fitz.open(self.pdf_path)
            npages = doc.page_count
            if npages > 2:
                dlg = QProgressDialog(
                    tr('Writing ballooned PDF...'), tr('Cancel'),
                    0, npages, self)
                dlg.setWindowTitle(tr('Save'))
                dlg.setWindowModality(Qt.ApplicationModal)
                dlg.setMinimumDuration(0)
                dlg.setValue(0)
            rad = float(self.cfg.get("radius", RADIUS))
            fsz = float(self.cfg.get("fontsz", FONTSZ))
            for pi in range(npages):
                if dlg is not None:
                    dlg.setValue(pi)
                    QApplication.processEvents()
                    if dlg.wasCanceled():
                        doc.close()
                        self.set_status(tr('save cancelled'))
                        return
                page = doc[pi]
                try:
                    prot = int(getattr(page, "rotation", 0) or 0) % 360
                except (TypeError, ValueError):
                    prot = 0
                dm = page.derotation_matrix if prot else None

                def pt(x, y):
                    if dm is not None:
                        x, y = xform_pt(dm, x, y)
                    return fitz.Point(x, y)

                seen = set()
                for d in self.ledger:
                    if d.get("page") != pi:
                        continue
                    b = base_of(d["bubble"])
                    if b in seen:
                        continue
                    seen.add(b)
                    ax, ay = d["x"], d["y"]
                    bx, by = d.get("bx", ax), d.get("by", ay)
                    tcol = tier_rgb(d.get("tier"))
                    tshape = tier_shape(d.get("tier"), self.cfg)
                    sh = page.new_shape()
                    lead = d.get("leader", (bx, by) != (ax, ay))
                    if (bx, by) != (ax, ay) and lead:
                        ex = LEADER_EXITS.get(d.get("lexit"))
                        if ex is not None:
                            p0 = pt(bx + ex[0] * rad, by + ex[1] * rad)
                        else:
                            dx, dy = ax - bx, ay - by
                            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
                            p0 = pt(bx + dx / dist * rad, by + dy / dist * rad)
                        sh.draw_line(p0, pt(ax, ay))
                        sh.finish(color=tcol, width=0.9)
                        sh.draw_circle(pt(ax, ay), 1.2)
                        sh.finish(color=tcol, fill=tcol, width=0.5)
                    spts = bubble_shape_points(tshape, bx, by, rad)
                    if spts is None:
                        sh.draw_circle(pt(bx, by), rad)
                    else:
                        sh.draw_polyline([pt(x, y) for x, y in spts]
                                         + [pt(spts[0][0], spts[0][1])])
                    sh.finish(color=tcol, fill=WHITE, width=1.2)
                    sh.commit()
                    c = pt(bx, by)
                    rect = fitz.Rect(c.x - rad, c.y - rad,
                                     c.x + rad, c.y + rad)
                    page.insert_textbox(rect, str(b), fontsize=fsz,
                                        color=tcol, align=1, rotate=prot)
            if dlg is not None:
                dlg.setValue(npages)
            tmp = out_pdf + ".tmp"
            doc.save(tmp)
            doc.close()
            doc = None
            os.replace(tmp, out_pdf)
        except Exception as e:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass
            if dlg is not None:
                dlg.reset()
            QMessageBox.critical(
                self, tr('PDF error'),
                tr('%s\n\nThe ballooned PDF could not be written; nothing '
                   'was saved. Close it in your PDF viewer and save again.')
                % e)
            self.refresh_panel()
            return
        finally:
            if dlg is not None:
                dlg.close()
        marked = []
        try:
            for d in self.ledger:
                if d.get("sheet_row") is None:
                    r = self.writer.next_row()
                    if r is None:
                        raise ValueError("Sheet full")
                    d["sheet_row"] = r
                    marked.append(d)
                self.writer.write_row(d["sheet_row"], d)
            self.writer.save()
        except Exception as e:
            for d in marked:
                d["sheet_row"] = None
            QMessageBox.critical(self, tr('Sheet error'), str(e))
            self.refresh_panel()
            return
        try:
            self._save_session()
        except Exception as e:
            self.set_status(tr('session not saved: %s') % e)
        self.refresh_panel()
        self.set_status(tr('saved -> %s (+ .xlsx) in %s')
                        % (os.path.basename(out_pdf),
                           os.path.dirname(out_pdf) or "."))
