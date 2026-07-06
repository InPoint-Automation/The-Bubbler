# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# CMM/CSV measurement import: values by balloon number into a chosen op.

from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

from .config import save_cfg
from .i18n import tr


class ImportMixin:
    def cmm_import(self):
        from .cmm_import import parse_cmm_csv, match_to_ledger

        seed = self.cfg.get("last_dir") or ""
        path, _ = QFileDialog.getOpenFileName(
            self, tr('Import CMM/CSV'), seed, "CSV (*.csv)")
        if not path:
            return
        try:
            text = open(path, encoding="utf-8-sig").read()
        except OSError as e:
            self.set_status(tr('import failed: %s') % e)
            return
        records, errors = parse_cmm_csv(text)
        m = match_to_ledger(records, self.ledger)
        matched = m["matched"]
        if not matched:
            QMessageBox.information(self, tr('Import CMM/CSV'),
                                    tr('No balloon numbers matched.'))
            return

        ops = self.cfg.get("ops_list") or ["op1"]
        cur = self.cfg.get("cmm_import_op") or ops[0]
        op, ok = QInputDialog.getItem(
            self, tr('Import CMM/CSV'), tr('Import into op:'),
            ops, ops.index(cur) if cur in ops else 0, False)
        if not ok:
            return
        self.cfg["cmm_import_op"] = op
        save_cfg(self.cfg)

        self.snapshot()
        for idx, rec in matched:
            self._record_op_into(self.ledger[idx], op, rec["value"],
                                 rec.get("gage"))
        self._save_session()
        self.refresh_panel()
        self.redraw_overlay()

        parts = [tr('Imported %d into %s') % (len(matched), op)]
        if m["unmatched"]:
            nums = ", ".join(str(r["bubble"]) for r in m["unmatched"][:20])
            parts.append(tr('%d unmatched: %s') % (len(m["unmatched"]), nums))
        if m["duplicates"]:
            parts.append(tr('%d duplicate rows') % len(m["duplicates"]))
        if m["no_base"] or errors:
            parts.append(tr('%d bad rows') % (len(m["no_base"]) + len(errors)))
        QMessageBox.information(self, tr('Import CMM/CSV'), "\n".join(parts))
        self.set_status(tr('imported %d measurements') % len(matched))
