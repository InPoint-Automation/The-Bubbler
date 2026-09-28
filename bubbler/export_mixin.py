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
from .reader.geometry import xform_pt
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
        """Once at close-out, id final. Never overwrites."""
        run = self.store.run() or {}
        rid = str(run.get("report_id") or "").strip()
        if not rid or not out_pdf:
            return None
        xlsx_src = self.writer.path

        def key(p):
            return os.path.normcase(os.path.realpath(p)).lower()
        own = {key(p) for p in (out_pdf, xlsx_src, self.pdf_path)}
        done, skipped = None, []
        for src, dst in ((out_pdf, os.path.join(os.path.dirname(out_pdf)
                                                or ".", rid + ".pdf")),
                         (xlsx_src, os.path.join(os.path.dirname(xlsx_src)
                                                 or ".", rid + ".xlsx"))):
            if key(dst) in own or os.path.exists(dst) or not _copy(src, dst):
                skipped.append(os.path.basename(dst))
            elif dst.endswith(".pdf"):
                done = dst
        if skipped:
            QMessageBox.warning(
                self, tr('Named copy not written'),
                tr('The named copy %s was not written: a file of that name '
                   'already exists or could not be created. The run is '
                   'still closed out; its documents are the working files.')
                % ", ".join(skipped))
        return done

    _FAI_HEADER_CELLS = {
        "B3": "part_no", "E3": "part_name", "B4": "drawing", "E4": "dwg_rev",
        "H4": "part_rev", "B5": "po", "E5": "material", "H5": "serial",
        "B6": "inspector", "E6": "date", "B7": "customer",
    }

    def _fai_lang(self):
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
        """Report header, title block only."""
        hdr = dict.fromkeys(self._FAI_HEADER_CELLS.values(), "")
        for cell, field in self._FAI_HEADER_CELLS.items():
            v = self.store.header.get(cell)
            if v not in (None, ""):
                hdr[field] = str(v)
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
            inspection_type=str(self.store.header.get("H6") or ""),
            show=dict(self.cfg.get("fai_show") or {}))
        return hdr

    def _append_fai_report(self, doc, required=False):
        """Best-effort unless `required` (report-only)."""
        units = units_of(self.cfg, getattr(self, "drawing", None))
        rows = rows_from_ledger(self.ledger, self.cfg, units)
        if not rows:
            if required:
                raise ValueError(tr('No bubbled rows: the report is empty.'))
            return 0
        def build():
            n = report_pdf.append_report_pages(
                doc, self._fai_header(), rows, lang=self._fai_lang(),
                logo=self._fai_logo_bytes(),
                paper=(self.cfg.get("fai_paper") or "a4"),
                amber_pct=int(self.cfg.get("fai_amber_pct",
                                           report_pdf.AMBER_PCT) or 0),
                step_img=self._step_report_bytes())
            imgs = self._attachment_images()
            if n and imgs:
                # after rows, last page first
                before = doc.page_count
                report_pdf.append_images(
                    doc, imgs,
                    width_pct=self.cfg.get("fai_img_width_pct", 100),
                    per_page=str(self.cfg.get("fai_img_per_page", "auto")),
                    paper=(self.cfg.get("fai_paper") or "a4"),
                    first_page=doc[doc.page_count - 1])
                extra = doc.page_count - before
                hdr = self._fai_header()
                for k in range(extra):
                    report_pdf.stamp_footer(
                        doc[before + k], hdr,
                        tr('Attachment page %d of %d') % (k + 1, extra))
                n += extra
            return n
        if required:
            return build()
        try:
            return build()
        except Exception as e:                # noqa: BLE001 report optional
            self.set_status(tr('Report skipped: %s') % e, icon="warn")
            return 0

    def _attachment_dir(self):
        """Beside session so qc/ moves whole."""
        run = self.store.run() or {}
        base = os.path.dirname(self.session_path) or "."
        return os.path.join(base, "attachments", str(run.get("id") or "run"))

    def edit_attachments(self, parent=None):
        from .attachments import AttachmentsDialog
        run = self.store.run() or {}
        ro = bool(run.get("closed")) or self.store.read_only
        base = os.path.dirname(self.session_path) or "."
        dlg = AttachmentsDialog(parent or self, run.get("attachments") or [],
                                base, readonly=ro)
        try:
            if dlg.exec() != dlg.Accepted or ro:
                return False
            items = dlg.items()
        finally:
            dlg.deleteLater()
        dest = self._attachment_dir()
        new = []
        for it in items:
            rel = it.get("file")
            if it.get("src"):
                try:
                    os.makedirs(dest, exist_ok=True)
                    name = os.path.basename(it["src"])
                    stem, ext = os.path.splitext(name)
                    k, dst = 1, os.path.join(dest, name)
                    while os.path.exists(dst):
                        k += 1
                        dst = os.path.join(dest, "%s-%d%s" % (stem, k, ext))
                    shutil.copyfile(it["src"], dst)
                    rel = os.path.relpath(dst, base)
                except OSError as e:
                    QMessageBox.warning(self, tr('Report images'),
                                        tr('Could not copy %s: %s')
                                        % (it["src"], e))
                    continue
            if rel:
                new.append({"file": rel,
                            "caption": str(it.get("caption") or "")})
        if new == (run.get("attachments") or []):
            return False
        run["attachments"] = new
        return bool(self.save())

    def _attachment_images(self):
        run = self.store.run() or {}
        base = os.path.dirname(self.session_path) or "."
        out, missing = [], []
        for a in run.get("attachments") or ():
            p = os.path.join(base, str((a or {}).get("file") or ""))
            try:
                with open(p, "rb") as fh:
                    out.append((fh.read(), str(a.get("caption") or "")))
            except OSError:
                missing.append(os.path.basename(p))
        if missing:
            self.set_status(tr('Report image missing: %s')
                            % ", ".join(missing), icon="warn")
        return out

    def _compose_output(self, drawing):
        mode = self.cfg.get("save_output", "both")
        first = bool(self.cfg.get("report_first", False))
        n_draw = drawing.page_count
        if mode == "print":
            return drawing, {"draw": n_draw, "report": 0,
                             "report_first": False}
        rep = fitz.open()
        try:
            self._append_fai_report(rep, required=(mode == "report"))
        except Exception:
            rep.close()
            raise
        n_rep = rep.page_count
        if mode == "report":
            drawing.close()
            return rep, {"draw": 0, "report": n_rep, "report_first": True}
        if n_rep:
            drawing.insert_pdf(rep, start_at=0 if first else -1)
        rep.close()
        return drawing, {"draw": n_draw, "report": n_rep,
                         "report_first": bool(first and n_rep)}

    def show_step_preview(self):
        from .stepdialog import StepViewDialog
        StepViewDialog(self, self.cfg, self.pdf_path).exec()

    def _step_report_bytes(self):
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
        w = getattr(self, "writer", None)
        if w is None or getattr(self.store, "read_only", False):
            return
        for d in self.ledger:
            r = d.get("sheet_row")
            if not r:
                continue
            human = w.read_human(r)
            for key in ("gage", "ncr", "refzone"):
                if human.get(key) not in (None, "") and not d.get(key):
                    d[key] = human[key]
            # changed cell replaces comment
            c = human.get("comment")
            if (c not in (None, "")
                    and str(c) != str(d.get("comment") or "")
                    and str(c) != str(d.get("sheet_comment") or "")):
                d["comment"] = c
            if (human.get("measured") not in (None, "")
                    and not d.get("measured") and not d.get("ops")):
                d["measured"] = human["measured"]

    def _ingest_header(self):
        """Session wins, fills blanks only."""
        w = getattr(self, "writer", None)
        if w is None or getattr(self.store, "read_only", False):
            return
        try:
            hdr = w.get_header() or {}
        except Exception:
            return
        # several runs: skip run cells
        several = len(getattr(self.store, "runs", None) or ()) > 1
        # inherited fields still read
        inherit = set(getattr(self, "_RUN_INHERITS", ()))
        run_cells = {c for c, f in getattr(self, "_RUN_HEADER_CELLS", ())
                     if f not in inherit}
        for cell, v in hdr.items():
            if several and cell in run_cells:
                continue
            if v not in (None, "") and not self.store.header.get(cell):
                self.store.header[cell] = v

    def _resync_sheet_rows(self):
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
        if self.unsaved():
            return False
        out = qc_path(self.pdf_path, "_Inspection.pdf",
                      subdir=self.cfg.get("qc_subdir", "qc"))
        return (os.path.isfile(out)
                or os.path.isfile(qc_path(self.pdf_path, "_Inspection.pdf",
                                          subdir="")))

    def _saved_output_pdf(self):
        for sub in (self.cfg.get("qc_subdir", "qc"), ""):
            p = qc_path(self.pdf_path, "_Inspection.pdf", subdir=sub)
            if os.path.isfile(p):
                return p
        return None

    def preview_output(self):
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
        import tempfile
        tmp = tempfile.mkdtemp(prefix="bubbler_preview_")
        rounds = [0]

        def attach(parent):
            # fresh folder, old files open
            if not self.edit_attachments(parent):
                return None
            rounds[0] += 1
            sub = os.path.join(tmp, str(rounds[0]))
            os.makedirs(sub, exist_ok=True)
            out = self._saved_output_pdf()
            return self._output_variants(out, sub) if out else None
        try:
            try:
                dlg = PreviewDialog(self, path,
                                    variants=self._output_variants(path, tmp),
                                    save_dir=os.path.dirname(path),
                                    attach=attach,
                                    protect=(path, self.writer.path,
                                             self.pdf_path))
            except Exception:
                QMessageBox.warning(
                    self, tr('Preview output'),
                    tr('Could not open the output for preview.'))
                return
            dlg.exec()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _output_variants(self, path, tmpdir):
        """Split by saved layout. Never raises."""
        out = [(tr('As saved'), path, os.path.basename(path))]
        try:
            saved = fitz.open(path)
        except Exception:
            return out
        try:
            return out + self._split_variants(saved, tmpdir)
        except Exception:
            return out
        finally:
            saved.close()

    def _split_variants(self, saved, tmpdir):
        stem = os.path.splitext(os.path.basename(self.pdf_path))[0]
        out = []
        n = saved.page_count
        lay = self.store.drawing.get("docs_layout") or {}
        nd, nr = int(lay.get("draw", -1)), int(lay.get("report", -1))
        first = bool(lay.get("report_first"))
        if nd < 0 or nr < 0 or nd + nr != n:
            # pre-layout save, report after
            try:
                with fitz.open(self.pdf_path) as src:
                    nd = min(src.page_count, n)
            except Exception:
                nd = n
            nr, first = n - nd, False

        def part(pages, name):
            d = fitz.open()
            try:
                for a, b in pages:
                    d.insert_pdf(saved, from_page=a, to_page=b)
                p = os.path.join(tmpdir, name)
                d.save(p)
            finally:
                d.close()
            return p
        draw = rep = None
        if nd:
            a = nr if first else 0
            draw = part([(a, a + nd - 1)], "drawing.pdf")
        if nr:
            a = 0 if first else nd
            rep = part([(a, a + nr - 1)], "report.pdf")
        else:
            try:
                fresh = fitz.open()
                if self._append_fai_report(fresh):
                    rep = os.path.join(tmpdir, "report.pdf")
                    fresh.save(rep)
                fresh.close()
            except Exception:
                rep = None
        if draw:
            out.append((tr('Drawing only'), draw, stem + "_Drawing.pdf"))
        if rep:
            out.append((tr('Report only'), rep, stem + "_Report.pdf"))
        if draw and rep:
            for label, order, name in (
                    (tr('Drawing, then report'), (draw, rep), "_Combined"),
                    (tr('Report, then drawing'), (rep, draw),
                     "_Combined_report_first")):
                d = fitz.open()
                try:
                    for src in order:
                        with fitz.open(src) as s:
                            d.insert_pdf(s)
                    p = os.path.join(tmpdir, "both_%d.pdf" % len(out))
                    d.save(p)
                finally:
                    d.close()
                out.append((label, p, stem + name + ".pdf"))
        return out

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
            # last window stops GPU worker
            from PySide6.QtWidgets import QApplication
            others = [w for w in QApplication.topLevelWidgets()
                      if w is not self and hasattr(w, "store")
                      and w.isVisible()]
            if not others:
                from . import gpu
                gpu.shutdown()
        except Exception:
            pass
        e.accept()

    def save(self):
        if self.store.read_only:
            if not getattr(self, "_session_ro_warned", False):
                self._show_session_lock()
            self.set_status(tr('session read-only'), icon="warn")
            return False
        # report and sheet print it
        self._mint_report_id()
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
                    tr('Writing the output PDF...'), tr('Cancel'),
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
                    nfs = fit_fontsz(rad, fsz, str(b))
                    tr0 = shape_text_rect(bx, by, rad, nfs)
                    q0, q1 = pt(tr0[0], tr0[1]), pt(tr0[2], tr0[3])
                    rect = fitz.Rect(min(q0.x, q1.x), min(q0.y, q1.y),
                                     max(q0.x, q1.x), max(q0.y, q1.y))
                    page.insert_textbox(rect, str(b), fontsize=nfs,
                                        color=tcol, align=1, rotate=prot)
            if dlg is not None:
                dlg.setValue(npages)
            doc, layout = self._compose_output(doc)
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
            if self.cfg.get("save_output") == "report":
                QMessageBox.critical(
                    self, tr('PDF error'),
                    tr('%s\n\nThe report could not be written; nothing '
                       'saved.') % e)
            else:
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
            self._default_inspector()
            run = self.store.run() or {}
            self.writer.set_report_id(run.get("report_id"))
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
        # stamp only once on disk
        self.store.drawing["docs_layout"] = layout
        (self.store.run() or {})["docs_id"] = \
            (self.store.run() or {}).get("report_id") or ""
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
        self.set_status(tr('saved -> %s (+ .xlsx) in %s')
                        % (os.path.basename(out_pdf),
                           os.path.dirname(out_pdf) or "."))
        return True

