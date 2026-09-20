# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Export mixin writes xlsx and ballooned PDF.

import os
import shutil

import fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .common import (RADIUS, FONTSZ, WHITE, LEADER_EXITS, base_of,
                     fit_fontsz, qc_path, tier_rgb, tier_shape,
                     bubble_shape_points, shape_radius, shape_support,
                     shape_text_rect)
from .config import units_of
from .reportrow import rows_from_ledger
from .scanpos import xform_pt
from .units import unit_suffix
from . import report_pdf
from .i18n import tr


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _copy(src, dst):
    """Copy deliverable without clobbering own source."""
    try:
        if os.path.abspath(src) == os.path.abspath(dst):
            return dst
        shutil.copyfile(src, dst)
        return dst
    except OSError:
        return None


class ExportMixin:
    def unsaved(self):
        return sum(1 for d in self.ledger if d.get("sheet_row") is None)

    def _archive_run_docs(self, out_pdf):
        """Issued run keeps NAMED copy of deliverables (W38)."""
        run = self.store.run() or {}
        rid = str(run.get("report_id") or "").strip()
        if not rid:
            return None
        pdf_dst = os.path.join(os.path.dirname(out_pdf) or ".", rid + ".pdf")
        xlsx_src = self.writer.path
        xlsx_dst = os.path.join(os.path.dirname(xlsx_src) or ".",
                                rid + ".xlsx")
        _copy(out_pdf, pdf_dst)
        _copy(xlsx_src, xlsx_dst)
        return pdf_dst

    # ---- FAI report pages (W39) ----------------------------------------

    # cell -> FAI header field
    _FAI_HEADER_CELLS = {
        "B3": "part_no", "E3": "part_name", "B4": "drawing", "E4": "dwg_rev",
        "H4": "part_rev", "B5": "po", "E5": "material", "H5": "serial",
        "B6": "inspector", "E6": "date", "B7": "customer",
    }

    def _fai_lang(self):
        """cfg fai_lang -> renderer lang."""
        return "en/pl" if self.cfg.get("fai_lang") == "en-pl" \
            else (self.cfg.get("fai_lang") or "en")

    def _fai_logo_bytes(self):
        path = str(self.cfg.get("fai_logo") or "").strip()
        if not path:
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def _fai_header(self):
        """Report header. Title block wins over cfg."""
        hdr = dict.fromkeys(self._FAI_HEADER_CELLS.values(), "")
        for cell, field in self._FAI_HEADER_CELLS.items():
            v = self.store.header.get(cell)
            if v not in (None, ""):
                hdr[field] = str(v)
        # only where blank
        if not hdr["customer"]:
            hdr["customer"] = str(self.cfg.get("fai_customer") or "")
        if not hdr["inspector"]:
            hdr["inspector"] = str(self.cfg.get("fai_inspector") or "")
        run = self.store.run() or {}
        form_id = str(self.cfg.get("fai_form_id") or "")
        rev = str(self.cfg.get("fai_form_rev") or "").strip()
        if rev:
            form_id = ("%s REV %s" % (form_id, rev)).strip()
        hdr.update(
            company=str(self.cfg.get("company") or ""),
            report_id=str(run.get("report_id") or ""),
            units=unit_suffix(units_of(self.cfg, getattr(self, "drawing", None))),
            form_id=form_id,
            # H6 inspection type
            inspection_type=str(self.store.header.get("H6") or ""),
            show=dict(self.cfg.get("fai_show") or {}))
        return hdr

    def _append_fai_report(self, doc):
        """Append FAI report best-effort so failure never costs ballooned PDF."""
        units = units_of(self.cfg, getattr(self, "drawing", None))
        rows = rows_from_ledger(self.ledger, self.cfg, units)
        if not rows:
            return 0
        try:
            return report_pdf.append_report_pages(
                doc, self._fai_header(), rows, lang=self._fai_lang(),
                logo=self._fai_logo_bytes(),
                paper=(self.cfg.get("fai_paper") or "a4"),
                amber_pct=int(self.cfg.get("fai_amber_pct",
                                           report_pdf.AMBER_PCT) or 0),
                step_img=self._step_report_bytes())
        except Exception as e:                # noqa: BLE001 report optional
            self.set_status(tr('Report skipped: %s') % e, icon="warn")
            return 0

    def show_step_preview(self):
        """Data menu two isometric STEP views for drawing."""
        from .stepdialog import StepViewDialog
        StepViewDialog(self, self.cfg, self.pdf_path).exec()

    def _step_report_bytes(self):
        """Two-view STEP preview as PNG bytes for report header."""
        if not self.cfg.get("use_step_preview"):
            return None
        try:
            from . import steppreview
            img = steppreview.preview_image(self.cfg, self.pdf_path, size=300)
            if img is None:
                return None
            import io
            b = io.BytesIO()
            img.save(b, "PNG")
            return b.getvalue()
        except Exception:
            return None

    def _ingest_sheet_edits(self):
        """Pick up offline human xlsx edits into ledger."""
        w = getattr(self, "writer", None)
        if w is None or getattr(self.store, "read_only", False):
            return
        for d in self.ledger:
            r = d.get("sheet_row")
            if not r:
                continue
            human = w.read_human(r)
            for key in ("gage", "comment", "ncr", "refzone"):
                if human.get(key) not in (None, "") and not d.get(key):
                    d[key] = human[key]
            if (human.get("measured") not in (None, "")
                    and not d.get("measured") and not d.get("ops")):
                d["measured"] = human["measured"]

    def _ingest_header(self):
        """Capture workbook title block into session on open (W28)."""
        w = getattr(self, "writer", None)
        if w is None or getattr(self.store, "read_only", False):
            return
        try:
            hdr = w.get_header() or {}
        except Exception:
            return
        for cell, v in hdr.items():
            if v not in (None, "") and not self.store.header.get(cell):
                self.store.header[cell] = v

    def _resync_sheet_rows(self):
        """Rewrite committed rows"""
        dirty = False
        for d in self.ledger:
            if d.get("sheet_row"):
                self.writer.write_row(d["sheet_row"], d)
                dirty = True
        if dirty:
            try:
                self.writer.save()
            except Exception:
                pass

    def docs_written(self):
        """True when run's PDF and sheet on disk and current."""
        if self.unsaved():
            return False
        out = qc_path(self.pdf_path, "_Inspection.pdf",
                      subdir=self.cfg.get("qc_subdir", "qc"))
        return (os.path.isfile(out)
                or os.path.isfile(qc_path(self.pdf_path, "_Inspection.pdf",
                                          subdir="")))

    def _saved_output_pdf(self):
        """Saved ballooned+report PDF on disk or None."""
        for sub in (self.cfg.get("qc_subdir", "qc"), ""):
            p = qc_path(self.pdf_path, "_Inspection.pdf", subdir=sub)
            if os.path.isfile(p):
                return p
        return None

    def preview_output(self):
        """L10 preview and print real output PDF."""
        if self.unsaved():
            r = QMessageBox.question(
                self, tr('Preview output'),
                tr('%d unsaved row(s). Save to update the preview?')
                % self.unsaved(),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Yes and not self.save():
                return
        path = self._saved_output_pdf()
        if not path:
            QMessageBox.information(
                self, tr('Preview output'),
                tr('Nothing to preview yet. Save the drawing first.'))
            return
        from .preview import PreviewDialog
        try:
            dlg = PreviewDialog(self, path)
        except Exception:
            # do not crash
            QMessageBox.warning(
                self, tr('Preview output'),
                tr('Could not open the output for preview.'))
            return
        dlg.exec()

    def closeEvent(self, e):
        if self.unsaved():
            r = QMessageBox.question(     # Enter must not discard
                self, tr('Unsaved'),
                tr('%d unsaved row(s). Quit anyway?')
                % self.unsaved(),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
        # sealed quit is normal
        sealed = (self.store.read_only and self.store.lock_kind == "closed")
        if not sealed and not self._save_session():
            r = QMessageBox.question(     # Enter must not discard
                self, tr('Session not saved'),
                tr('Session could not be written to disk. Every '
                   'bubble on this drawing will be lost when Bubbler '
                   'closes.\n\nQuit anyway?'),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
        try:
            from . import gpu
            gpu.shutdown()
        except Exception:
            pass
        e.accept()

    def save(self):
        """Write ballooned PDF, sheet and session. True on ok."""
        if self.store.read_only:          # cannot persist rows
            if not getattr(self, "_session_ro_warned", False):
                self._show_session_lock()     # once per session
            self.set_status(tr('session read-only'), icon="warn")
            return False
        # abort before write
        need = sum(1 for d in self.ledger if d.get("sheet_row") is None)
        free = self.writer.free_rows()
        if need > free:
            QMessageBox.critical(
                self, tr('Sheet full'),
                tr('%d new bubbles but only %d free rows on the inspection '
                   'sheet. Nothing was saved. Remove bubbles or start a new '
                   'sheet.') % (need, free))
            return False
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
        tmp = out_pdf + ".tmp"
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
                        return False
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
                        tx, ty = ax, ay
                        if self.cfg.get("leader_trim", True):
                            tx, ty = self._leader_target(pi, bx, by, ax, ay)
                        ex = LEADER_EXITS.get(d.get("lexit"))
                        if ex is not None:
                            sup = shape_support(tshape, rad, ex[0], ex[1])
                            p0 = pt(bx + ex[0] * sup, by + ex[1] * sup)
                        else:
                            dx, dy = tx - bx, ty - by
                            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
                            ux, uy = dx / dist, dy / dist
                            sup = shape_support(tshape, rad, ux, uy)
                            p0 = pt(bx + ux * sup, by + uy * sup)
                        sh.draw_line(p0, pt(tx, ty))
                        sh.finish(color=tcol, width=0.9)
                        sh.draw_circle(pt(tx, ty), 1.2)
                        sh.finish(color=tcol, fill=tcol, width=0.5)
                    spts = bubble_shape_points(tshape, bx, by, rad)
                    if spts is None:
                        sh.draw_circle(pt(bx, by), shape_radius(tshape, rad))
                    else:
                        sh.draw_polyline([pt(x, y) for x, y in spts]
                                         + [pt(spts[0][0], spts[0][1])])
                    sh.finish(color=tcol, fill=WHITE, width=1.2)
                    sh.commit()
                    # full-size number every tier
                    # asymmetric box turns too
                    nfs = fit_fontsz(rad, fsz, str(b))
                    tr0 = shape_text_rect(bx, by, rad, nfs)
                    q0, q1 = pt(tr0[0], tr0[1]), pt(tr0[2], tr0[3])
                    rect = fitz.Rect(min(q0.x, q1.x), min(q0.y, q1.y),
                                     max(q0.x, q1.x), max(q0.y, q1.y))
                    page.insert_textbox(rect, str(b), fontsize=nfs,
                                        color=tcol, align=1, rotate=prot)
            if dlg is not None:
                dlg.setValue(npages)
            if self.cfg.get("fai_report_on", True):
                self._append_fai_report(doc)      # report pages after balloons
            doc.save(tmp)
            doc.close()
            doc = None
        except Exception as e:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass
            _rm(tmp)
            if dlg is not None:
                dlg.reset()
            QMessageBox.critical(
                self, tr('PDF error'),
                tr('%s\n\nBallooned PDF could not be written; nothing '
                   'saved. Close it in your PDF viewer and save again.')
                % e)
            self.refresh_panel()
            return False
        finally:
            if dlg is not None:
                dlg.close()
        marked = []
        try:
            # run report id
            run = self.store.run() or {}
            self.writer.set_report_id(run.get("report_id"))
            # push title block back (W28)
            if self.store.header:
                self.writer.set_header(self.store.header)
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
            _rm(tmp)
            QMessageBox.critical(self, tr('Sheet error'), str(e))
            self.refresh_panel()
            return False
        os.replace(tmp, out_pdf)
        self._archive_run_docs(out_pdf)
        try:
            sess_ok = self._save_session()
        except Exception as e:
            sess_ok = False
            self.set_status(tr('session not saved: %s') % e)
        self.refresh_panel()
        if not sess_ok:                   # rows point lost ledger
            QMessageBox.warning(
                self, tr('Session not saved'),
                tr('Ballooned PDF and inspection sheet were '
                   'written, but the session file could not be saved. '
                   'Sheet rows will not match this drawing the next time '
                   'you open it.'))
            self.set_status(tr('session NOT saved'), icon="warn")
            return False
        # F9 capture shipped callouts
        self._collect_acceptances(marked)
        self.set_status(tr('saved -> %s (+ .xlsx) in %s')
                        % (os.path.basename(out_pdf),
                           os.path.dirname(out_pdf) or "."))
        return True

