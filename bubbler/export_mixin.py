# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Export + close mixin. Writes xlsx + ballooned PDF.

import os

import fitz
from PySide6.QtWidgets import QMessageBox

from .common import RADIUS, FONTSZ, RED, WHITE, LEADER_EXITS, base_of
from .scanpos import xform_pt


class ExportMixin:
    def unsaved(self):
        return sum(1 for d in self.ledger if d.get("sheet_row") is None)

    def closeEvent(self, e):
        if self.unsaved():
            r = QMessageBox.question(
                self, "Unsaved / Niezapisane",
                "%d unsaved row(s). Quit anyway? / Wyjść mimo to?"
                % self.unsaved())
            if r != QMessageBox.Yes:
                e.ignore()
                return
        self._save_session()
        e.accept()

    def save(self):
        try:
            for d in self.ledger:
                if d.get("sheet_row") is None:
                    r = self.writer.next_row()
                    if r is None:
                        raise ValueError("Sheet full")
                    d["sheet_row"] = r
                self.writer.write_row(d["sheet_row"], d)
            self.writer.save()
        except Exception as e:
            QMessageBox.critical(self, "Sheet error / Błąd arkusza", str(e))
            return
        out_pdf = os.path.splitext(self.pdf_path)[0] + "_Inspection.pdf"
        try:
            doc = fitz.open(self.pdf_path)
            rad = float(self.cfg.get("radius", RADIUS))
            fsz = float(self.cfg.get("fontsz", FONTSZ))
            for pi in range(doc.page_count):
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
                        sh.finish(color=RED, width=0.9)
                        sh.draw_circle(pt(ax, ay), 1.2)
                        sh.finish(color=RED, fill=RED, width=0.5)
                    sh.draw_circle(pt(bx, by), rad)
                    sh.finish(color=RED, fill=WHITE, width=1.2)
                    sh.commit()
                    c = pt(bx, by)
                    rect = fitz.Rect(c.x - rad, c.y - rad,
                                     c.x + rad, c.y + rad)
                    page.insert_textbox(rect, str(b), fontsize=fsz,
                                        color=RED, align=1, rotate=prot)
            tmp = out_pdf + ".tmp"
            doc.save(tmp)
            doc.close()
            os.replace(tmp, out_pdf)
        except Exception as e:
            QMessageBox.critical(
                self, "PDF error / Błąd PDF",
                "%s\n\nSheet rows are saved; the ballooned PDF was not "
                "written. Close it in your PDF viewer and save again. / "
                "Wiersze zapisane; zamknij PDF w przeglądarce i zapisz "
                "ponownie." % e)
            self._save_session()
            self.refresh_panel()
            return
        self._save_session()
        self.refresh_panel()
        self.set_status("saved / zapisano → %s (+ .xlsx) in %s"
                        % (os.path.basename(out_pdf),
                           os.path.dirname(out_pdf) or "."))
