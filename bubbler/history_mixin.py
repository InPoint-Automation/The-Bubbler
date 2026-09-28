# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Undo and redo for MainWindow.

from .i18n import tr


class HistoryMixin:
    def snapshot(self):
        self._undo.append(self.store.snapshot_state())
        if len(self._undo) > self.UNDO_DEPTH:
            del self._undo[0]
        self._redo.clear()

    def _restore(self, state):
        old_rows = {d["sheet_row"] for d in self.ledger if d.get("sheet_row")}
        self.store.restore_state(state)
        new_rows = {d["sheet_row"] for d in self.ledger if d.get("sheet_row")}
        dirty = False
        for r in old_rows - new_rows:
            self.writer.clear_row(r)
            dirty = True
        for d in self.ledger:
            if d.get("sheet_row"):
                self.writer.write_row(d["sheet_row"], d)
                dirty = True
        if dirty:
            try:
                self.writer.save()
            except Exception:
                pass
        self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()

    def undo(self):
        # sealed session blocks undo too
        if not self._undo or self._undo_blocked():
            return
        self._redo.append(self.store.snapshot_state())
        self._restore(self._undo.pop())
        self.set_status(tr('undo'))

    def _undo_blocked(self):
        if getattr(self.store, "read_only", False):
            self._undo, self._redo = [], []
            eb = getattr(self, "_edit_blocked", None)
            if callable(eb):
                eb()
            return True
        return False

    def redo(self):
        if not self._redo or self._undo_blocked():
            return
        self._undo.append(self.store.snapshot_state())
        self._restore(self._redo.pop())
        self.set_status(tr('redo'))
