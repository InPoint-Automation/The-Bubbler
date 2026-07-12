# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# CMM/CSV measurement import: values by balloon number into a chosen op.

from PySide6.QtWidgets import (QFileDialog, QMessageBox, QInputDialog,
                               QDialog, QVBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QDialogButtonBox,
                               QAbstractItemView)

from .config import save_cfg
from .i18n import tr


class ImportMixin:
    def _cmm_preview(self, records, m, errors):
        """Show matched/unmatched/duplicate rows before applying. True=proceed."""
        status = {}
        for idx, rec in m["matched"]:
            tgt = self.ledger[idx].get("bubble") if idx < len(self.ledger) else "?"
            status[id(rec)] = tr('-> #%s') % tgt
        for rec in m["duplicates"]:
            status[id(rec)] = tr('duplicate (superseded)')
        for rec in m["unmatched"]:
            status[id(rec)] = tr('no bubble on drawing')
        for rec in m["no_base"]:
            status[id(rec)] = tr('unreadable bubble')

        dlg = QDialog(self)
        dlg.setWindowTitle(tr('Import preview'))
        dlg.resize(560, 420)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(
            tr('%d matched, %d unmatched, %d duplicate, %d bad')
            % (len(m["matched"]), len(m["unmatched"]),
               len(m["duplicates"]), len(m["no_base"]) + len(errors))))
        tbl = QTableWidget(len(records), 4, dlg)
        tbl.setHorizontalHeaderLabels(
            [tr('Bubble'), tr('Value'), tr('gage'), tr('Status')])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.NoSelection)
        for r, rec in enumerate(records):
            cells = [rec.get("bubble", ""), rec.get("value", ""),
                     rec.get("gage") or "", status.get(id(rec), "")]
            for c, txt in enumerate(cells):
                tbl.setItem(r, c, QTableWidgetItem(str(txt)))
        tbl.resizeColumnsToContents()
        v.addWidget(tbl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr('Import'))
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        return dlg.exec() == QDialog.Accepted

    def cmm_import(self):
        from .cmm_import import parse_cmm_csv, match_to_ledger

        seed = self.cfg.get("last_dir") or ""
        path, _ = QFileDialog.getOpenFileName(
            self, tr('Import CMM/CSV'), seed, "CSV (*.csv)")
        if not path:
            return
        text = None
        for enc in ("utf-8-sig", "cp1250", "latin-1"):
            try:
                with open(path, encoding=enc) as fh:
                    text = fh.read()
                break
            except UnicodeDecodeError:
                continue
            except OSError as e:
                self.set_status(tr('import failed: %s') % e)
                return
        if text is None:
            self.set_status(tr('import failed: could not decode file'))
            return
        records, errors = parse_cmm_csv(text)
        if not records:
            QMessageBox.information(self, tr('Import CMM/CSV'),
                                    tr('No rows found in the file.'))
            return
        m = match_to_ledger(records, self.ledger)
        if not self._cmm_preview(records, m, errors):
            return
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
