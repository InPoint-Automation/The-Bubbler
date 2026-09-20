# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Inspection runs: issue, close out, start next.

import os

from PySide6.QtWidgets import QMessageBox

from .i18n import tr
from .store import RunClosed, SessionReadOnly


class RunsMixin:
    """Issue writes report only close-out seals run."""

    # run-scoped cells (W27/W22)
    _RUN_HEADER_CELLS = (("H5", "serial"), ("B6", "inspector"), ("E6", "date"))

    def _stamp_run_identity(self):
        """Copy run-scoped title-block cells onto active run."""
        run = self.store.run()
        if run is None or run.get("closed"):
            return
        for cell, field in self._RUN_HEADER_CELLS:
            v = str(self.store.header.get(cell) or "").strip()
            if v:
                run[field] = v

    def _sync_header_from_run(self):
        """Reflect active run identity back into title block."""
        run = self.store.run() or {}
        for cell, field in self._RUN_HEADER_CELLS:
            self.store.header[cell] = str(run.get(field) or "")

    # ------------------------------------------------------------ helpers

    def _run_part_rev(self):
        """Part number and revision for report id off sheet."""
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

    # ------------------------------------------------------------- issue

    def issue_report(self, close_out=False):
        """Stamp report id and write documents run still editable."""
        if self._run_blocked():
            return ""
        if self.store.run_closed():
            self._show_session_lock()
            return ""
        part, rev = self._run_part_rev()
        try:
            rid = self.store.issue_run(part=part, rev=rev)
        except (RunClosed, KeyError):
            self._show_session_lock()
            return ""
        self.save()                       # PDF + xlsx + session
        self.set_status(tr('report %s issued') % rid, icon="check")
        if close_out:
            self.close_out()              # sets own status
        return rid

    def issue_and_close(self):
        """Common case inspection finished."""
        return self.issue_report(close_out=True)

    # --------------------------------------------------------- close out

    def _close_out_box(self):
        """Confirmation box split out for screenshot."""
        run = self.store.run() or {}
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr('Close out inspection'))
        box.setText(tr('Close out this run?'))
        rid = str(run.get("report_id") or "")
        what = (tr('Report %s') % rid) if rid else tr('No report issued yet')
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
        """Confirm then seal run returns true when sealed."""
        if self._run_blocked():
            return False
        if self.store.run_closed():
            self._show_session_lock()
            return False
        box = self._close_out_box()
        box.exec()
        if box.clickedButton() is not box.button_close:
            return False
        # write docs before sealing
        if not self.docs_written() and not self.save():
            QMessageBox.warning(
                self, tr('Not closed out'),
                tr('This run was NOT closed out: its ballooned PDF and '
                   'inspection sheet could not be written.\n\nA closed-out '
                   'run refuses every later save, so its documents must be '
                   'written now. Fix the problem above and close out again.'))
            self.set_status(tr('not closed out: documents not written'),
                            icon="warn")
            return False
        return self._close_out_now()

    def _close_out_now(self):
        """Seal and persist run."""
        try:
            self.store.close_run()
        except (RunClosed, KeyError):
            return False
        ok = self._save_session()
        self._apply_lock_chrome()
        self.refresh_panel()
        if ok:
            self.set_status(tr('inspection closed out'), icon="check")
        return ok

    # ----------------------------------------------------------- new run

    def start_new_run(self):
        """Start next run after closed one."""
        if self._run_blocked():
            return ""
        try:
            rid = self.store.add_run()
        except SessionReadOnly:
            self._show_session_lock()
            return ""
        self._sync_header_from_run()      # clear title block
        self._session_ro_warned = False
        self._run_stale_asked = True      # fresh run never stale
        self._save_session()
        self._apply_lock_chrome()
        self.refresh_panel()
        self.render()
        self.set_status(tr('new inspection run started'), icon="check")
        return rid

    # ------------------------------------------------------- switch runs

    def _run_label(self, run, active):
        """One line describing run for switch picker."""
        bits = [str(run.get("id") or "")]
        ident = str(run.get("serial") or "").strip()
        if ident:
            bits.append(ident)            # part inspected (W27)
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
        """Pick existing run and make active way BACK (O1)."""
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
        self._sync_header_from_run()      # follows active run
        self._session_ro_warned = False
        self._run_stale_asked = True      # switch never stale
        # sealed target refuses save
        if not self.store.run_closed():
            self._save_session()
        self._apply_lock_chrome()
        self.refresh_panel()
        self.render()
        self.set_status(tr('switched to run %s') % rid, icon="check")
        return rid

    # --------------------------------------------------------- staleness

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
        """Ask once on open when active run went cold."""
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
            self._save_session()          # touched moves to now
