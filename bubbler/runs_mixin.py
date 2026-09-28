# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Inspection runs: report id, close out, start next.

import os

from PySide6.QtWidgets import QMessageBox

from .i18n import tr
from .store import RunClosed, SessionReadOnly


class RunsMixin:

    _RUN_HEADER_CELLS = (("H5", "serial"), ("B6", "inspector"), ("E6", "date"),
                         ("H6", "inspection"))
    # blank run keeps block's
    _RUN_INHERITS = ("inspection",)

    def _stamp_run_identity(self):
        run = self.store.run()
        if run is None or run.get("closed"):
            return
        for cell, field in self._RUN_HEADER_CELLS:
            v = str(self.store.header.get(cell) or "").strip()
            if v:
                run[field] = v

    def _default_inspector(self):
        """Blank header inspector takes Settings default."""
        run = self.store.run()
        who = str(self.cfg.get("fai_inspector") or "").strip()
        if not who or run is None or run.get("closed"):
            return
        if str(self.store.header.get("B6") or "").strip():
            return
        run["inspector"] = who
        self.store.header["B6"] = who

    def _sync_header_from_run(self):
        run = self.store.run() or {}
        for cell, field in self._RUN_HEADER_CELLS:
            v = str(run.get(field) or "")
            if not v and field in self._RUN_INHERITS:
                continue
            self.store.header[cell] = v


    def _run_part_rev(self):
        part = rev = ""
        try:
            hdr = self.writer.get_header()
            part = str(hdr.get("B3") or "").strip()
            rev = str(hdr.get("H4") or "").strip()
        except Exception:
            pass
        if not part:
            part = os.path.splitext(os.path.basename(self.pdf_path))[0]
        return part, rev

    def _run_blocked(self):
        """True when refused FILE not closed run stops us."""
        if self.store.read_only and self.store.lock_kind != "closed":
            self._show_session_lock()
            return True
        return False


    def _mint_report_id(self):
        """Follows part/rev until close-out. Never raises."""
        if self.store.read_only or self.store.run_closed():
            return ""
        part, rev = self._run_part_rev()
        try:
            return self.store.mint_report_id(part=part, rev=rev)
        except (RunClosed, KeyError):
            return ""


    def _close_out_box(self):
        """Confirmation box split out for screenshot."""
        self._mint_report_id()
        run = self.store.run() or {}
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr('Close out inspection'))
        box.setText(tr('Close out this run?'))
        rid = str(run.get("report_id") or "")
        what = (tr('Report %s') % rid) if rid else tr('No report ID yet')
        box.setInformativeText(
            what + "\n\n"
            + tr('Closing out locks this run. Its measured values, '
                 'ballooned PDF and inspection sheet stop changing: '
                 'Bubbler will not save over it, now or when you re-open '
                 'the drawing.\n\nThe drawing is not locked. You can start '
                 'a new run any time and inspect another part against it.'))
        box.button_close = box.addButton(tr('Close out'),
                                         QMessageBox.AcceptRole)
        box.button_keep = box.addButton(tr('Keep working'),
                                        QMessageBox.RejectRole)
        box.setDefaultButton(box.button_keep)
        return box

    def close_out(self):
        if self._run_blocked():
            return False
        if self.store.run_closed():
            self._show_session_lock()
            return False
        box = self._close_out_box()
        box.exec()
        if box.clickedButton() is not box.button_close:
            return False
        # docs before seal, again if id moved
        run = self.store.run() or {}
        moved = ("docs_id" in run
                 and run.get("docs_id") != run.get("report_id"))
        if (moved or not self.docs_written()) and not self.save():
            QMessageBox.warning(
                self, tr('Not closed out'),
                tr('This run was NOT closed out: its ballooned PDF and '
                   'inspection sheet could not be written.\n\nA closed-out '
                   'run refuses every later save, so its documents must be '
                   'written now. Fix the problem above and close out again.'))
            self.set_status(tr('not closed out: documents not written'),
                            icon="warn")
            return False
        self._archive_run_docs(self._saved_output_pdf())
        return self._close_out_now()

    def _close_out_now(self):
        self._collect_acceptances(list(self.ledger))
        try:
            self.store.close_run()
        except (RunClosed, KeyError):
            return False
        self._undo, self._redo = [], []    # nothing undoes a seal
        ok = self._save_session()
        self._apply_lock_chrome()
        self.refresh_panel()
        if ok:
            self.set_status(tr('inspection closed out'), icon="check")
        return ok


    def start_new_run(self):
        if self._run_blocked():
            return ""
        prev = dict(self.store.run() or {})
        kind = (prev.get("inspection")
                or str(self.store.header.get("H6") or ""))
        try:
            rid = self.store.add_run()
        except SessionReadOnly:
            self._show_session_lock()
            return ""
        if kind:
            self.store.run()["inspection"] = kind
        self._sync_header_from_run()      # clear title block
        self._default_inspector()
        # undo is per run
        self._undo, self._redo = [], []
        self._session_ro_warned = False
        self._run_stale_asked = True
        self._save_session()
        self._apply_lock_chrome()
        self.refresh_panel()
        self.render()
        self.set_status(tr('new inspection run started'), icon="check")
        return rid


    def _run_label(self, run, active):
        bits = [str(run.get("id") or "")]
        ident = str(run.get("serial") or "").strip()
        if ident:
            bits.append(ident)
        if run.get("report_id"):
            bits.append(tr('report %s') % run["report_id"])
        if run.get("closed"):
            bits.append(tr('closed'))
        if active:
            rows = ({"measured": r.get("measured")} for r in self.store.ledger)
        else:
            rows = (run.get("rows") or {}).values()
        n = sum(1 for r in rows if str((r or {}).get("measured") or "").strip())
        bits.append(tr('%d measured') % n)
        stamp = str(run.get("touched") or "")[:10]
        if stamp:
            bits.append(stamp)
        return "  -  ".join(bits)

    def switch_run(self):
        from PySide6.QtWidgets import QInputDialog
        if self._run_blocked():
            return ""
        runs = list(self.store.runs)
        if len(runs) < 2:
            self.set_status(tr('this drawing has only one inspection run'),
                            icon="info")
            return ""
        active = self.store.active_run
        ids = [str(r.get("id") or "") for r in runs]
        labels = [("* " if i == active else "") + self._run_label(r, i == active)
                  for r, i in zip(runs, ids)]
        cur = ids.index(active) if active in ids else 0
        choice, ok = QInputDialog.getItem(
            self, tr('Switch inspection run'),
            tr('Every run shares the drawing and its requirements and keeps its '
               'own measured values. Switch to:'), labels, cur, False)
        if not ok:
            return ""
        rid = ids[labels.index(choice)]
        if rid == active:
            return rid
        # persist leaving run first
        if not self.store.read_only:
            self._save_session()
        try:
            self.store.set_active_run(rid)
        except KeyError:
            return ""
        self._sync_header_from_run()
        self._default_inspector()
        # undo is per run
        self._undo, self._redo = [], []
        self._session_ro_warned = False
        self._run_stale_asked = True
        # sealed target refuses save
        if not self.store.run_closed():
            self._save_session()
        self._apply_lock_chrome()
        self.refresh_panel()
        self.render()
        self.set_status(tr('switched to run %s') % rid, icon="check")
        return rid


    def _stale_box(self, days):
        """Question box split out for screenshot."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr('Inspection run'))
        box.setText(tr('This run has not been touched for %d '
                       'days.') % int(days))
        box.setInformativeText(
            tr('Was that inspection finished, and is this a new one?\n\n'
               'A new run keeps the bubbles and requirements and clears '
               'the measured values, so the old readings stay on their '
               'own run. Continuing picks up where you left off.'))
        box.button_new = box.addButton(tr('Start a new run'),
                                       QMessageBox.AcceptRole)
        box.button_keep = box.addButton(tr('Continue this run'),
                                        QMessageBox.RejectRole)
        box.setDefaultButton(box.button_keep)
        return box

    def _run_stale_check(self):
        if getattr(self, "_run_stale_asked", False):
            return
        if self.store.read_only or self.store.run_closed():
            return
        try:
            days = int(self.cfg.get("run_stale_days", 7) or 0)
        except (TypeError, ValueError):
            return
        if days <= 0:
            return
        idle = self.store.run_idle_days()
        if idle is None or idle < days:
            return
        self._run_stale_asked = True
        box = self._stale_box(int(idle))
        box.finished.connect(lambda _r=0, b=box: self._run_stale_answered(b))
        box.open()
        self._run_stale_prompt = box

    def _run_stale_answered(self, box):
        """Continuing re-stamps run so question stays gone."""
        if box.clickedButton() is getattr(box, "button_new", None):
            self.start_new_run()
        elif box.clickedButton() is getattr(box, "button_keep", None):
            self._save_session()
