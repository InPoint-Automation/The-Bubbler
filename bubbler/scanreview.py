# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Scan review dialog, edit hits, append balloons.

import math

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QLabel, QLineEdit, QComboBox,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QAbstractItemView, QInputDialog, QMessageBox)

from .common import TYPES, tier_for_type
from .config import units_of
from .corrections import proposal_of
from .gaging import gage_choices
from .gentol import general_tol, gentol_callout
from .reader.grammar import denorm_candidates
from .scanrows import (scan_to_row, expand_hole_row, repeat_count, scan_ticked,
                       with_qty_row,
                       scan_preset_name, scan_presets, strip_repeat,
                       stamp_facets, facet_rank)
from .i18n import tr, retranslate


def insert_general_tol(base, h, cfg, iso_on, icls="m", session=None,
                       gtols=None):
    if base.get("type") != "dim" or base.get("nominal") is None:
        return None
    if (base.get("tol_sym") is not None or base.get("tol_max") is not None
            or base.get("tol_min") is not None):
        return None
    return general_tol(gentol_callout(h, base), gtols, cfg, session,
                       icls=icls, iso_on=iso_on).value


def clockwise_order(items):
    """Sort accepted rows in-place into clockwise numbering order."""
    by_pg = {}
    for it in items:
        by_pg.setdefault(it["pg"], []).append(it)
    for group in by_pg.values():
        pts = [it for it in group if it["anchored"]] or group
        cx = sum(it["ax"] for it in pts) / len(pts)
        cy = sum(it["ay"] for it in pts) / len(pts)
        for it in group:
            ang = math.degrees(math.atan2(cy - it["ay"], it["ax"] - cx)) % 360.0
            it["_cw"] = (225.0 - ang) % 360.0
    items.sort(key=lambda it: (it["pg"], it["_cw"]))


# flags that start a row unticked
FCF_SUSPECT = ("unboxed", "partial", "datum_lost", "zone_suspect",
               "symbol_mixed", "bare_mod",
               # fail-open glyph
               "class_conflict",
               # I, O, Q datum
               "datum_impossible")


def _starts_unticked(h):
    if any(c in FCF_SUSPECT for c in (h.get("fcf_flags") or ())):
        return True
    return h.get("xcheck") == "disagree"


class ScanReview(QDialog):
    COLS = ("use", "pg", "exp", "type", "value", "tol", "gage")
    HEADS = ("use?", "pg", "n×", "type", tr('value'), "tol", "gage")

    def _sheet_header(self):
        """Session cells over workbook's."""
        try:
            out = dict(self.app.writer.get_header() or {})
        except Exception:
            out = {}
        store = getattr(self.app, "store", None)
        for cell, v in (getattr(store, "header", None) or {}).items():
            if v not in (None, ""):
                out[cell] = v
        return out

    def __init__(self, app, found, gtols, all_pages):
        super().__init__(app)
        self.app = app
        self.gtols = gtols
        app.adopt_iso_class(gtols)      # drawing beats ribbon
        self.setWindowTitle(
            tr('Scan review') + " - "
            + (tr('all pages') if all_pages
               else "%s %d" % (tr('page'), app.page_i + 1)))
        self.resize(700, 560)
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.HEADS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().installEventFilter(self)
        lay.addWidget(self.table)

        hdr = self._sheet_header()
        ses = getattr(app, "session", None)
        self.preset = scan_preset_name(app.cfg, ses, hdr)
        self._preset0 = self.preset
        self.rows = []
        self._touched = set()
        self._edited_hits = set()
        # reader's read, pre-edit
        self._proposals = {}
        pages = {}
        for _pg, h in found:
            pages.setdefault(_pg, []).append(h)
        for hs in pages.values():
            stamp_facets(hs)
        for pg, h in found:
            rw = self._to_row(h, pg)
            # read alone, no gentol
            raw = scan_to_row(h, units_of(app.cfg,
                                          getattr(app, "drawing", None)))
            if h.get("sb") == "BARE":
                raw["type"] = None    # number only
            self._proposals[id(h)] = proposal_of(
                dict(raw, feature=strip_repeat(raw.get("feature"))))
            use = scan_ticked(h, rw, app.cfg, ses, hdr)
            if _starts_unticked(h):
                use = False
            self.rows.append([use, h, rw, pg, {}, self._nx(h) > 1])

        self.table.setRowCount(len(self.rows))
        for i in range(len(self.rows)):
            self._fill_row(i)

        self.table.cellDoubleClicked.connect(self._double)
        self.table.itemEntered.connect(self._hover)
        # connect after fill
        self.table.itemChanged.connect(self._item_changed)

        pw = QWidget()
        pl = QHBoxLayout(pw)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(QLabel(tr('Inspection')))
        self.cb_preset = QComboBox()
        self.cb_preset.addItems(sorted(scan_presets(app.cfg)))
        self.cb_preset.setCurrentText(self.preset)
        self.cb_preset.setProperty("i18n_skip", True)
        self.cb_preset.currentTextChanged.connect(self._preset_changed)
        pl.addWidget(self.cb_preset)
        pl.addWidget(QLabel(
            tr('- decides what starts ticked. Kept for this drawing.')))
        pl.addStretch(1)
        lay.addWidget(pw)

        info = QLabel("Tick 'use?' to accept a row - tick 'n×' to expand "
                      "repeats - double-click type/value/tol/gage to edit - "
                      "hover a row to show it on the drawing. Plain numbers "
                      "start unticked; 'ISO 2768 auto' fills tol-less dims.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;")
        lay.addWidget(info)

        bw = QWidget()
        bl = QHBoxLayout(bw)
        b_acc = QPushButton(tr('Accept checked'))
        b_acc.setDefault(True)
        b_acc.clicked.connect(self._accept)
        b_all = QPushButton(tr('Check all'))
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none = QPushButton(tr('Uncheck all'))
        b_none.clicked.connect(lambda: self._set_all(False))
        b_bare = QPushButton(tr('Toggle plain dims'))
        b_bare.clicked.connect(self._toggle_bare)
        b_bulk = QPushButton(tr('Bulk edit checked'))
        b_bulk.setToolTip(
            tr('Set type, gage and tolerance on all checked rows'))
        b_bulk.clicked.connect(self._bulk_edit)
        b_cancel = QPushButton(tr('Cancel'))
        b_cancel.clicked.connect(self.reject)
        bl.addWidget(b_acc)
        bl.addWidget(b_all)
        bl.addWidget(b_none)
        bl.addWidget(b_bare)
        bl.addWidget(b_bulk)
        bl.addWidget(b_cancel)
        lay.addWidget(bw)
        retranslate(self)
        self.finished.connect(lambda _r: self._clear_hl())

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport() and ev.type() == QEvent.Leave:
            self._clear_hl()
        return super().eventFilter(obj, ev)

    def _clear_hl(self):
        self.app._scanhl = None
        self.app.redraw_overlay()

    def _nx(self, h):
        # own count, else R5 shows ×1
        return max(repeat_count(h.get("v")), int(h.get("qty") or 1))

    def _to_row(self, h, pg):
        rw = scan_to_row(h, units_of(self.app.cfg,
                                     getattr(self.app, "drawing", None)))
        self.app._apply_general_tol(rw, h, self.gtols.get(pg) or {})
        rw["gage"] = self.app.suggest(rw)
        return rw

    def _row_values(self, i):
        use, h, rw, pg, ov, expand = self.rows[i]
        n = self._nx(h)
        exp = "×%d" % n if n > 1 else ""
        tp_show = (ov.get("type") or
                   ("plain dim" if h.get("sb") == "BARE" else h["tp"]))
        return ("", pg + 1, exp, tp_show,
                h["v"], h.get("t") or "", rw["gage"])

    def _fill_row(self, i):
        self.table.blockSignals(True)
        use, h, _rw, _pg, _ov, expand = self.rows[i]
        nx = self._nx(h)
        bad = [c for c in (h.get("fcf_flags") or ()) if c in FCF_SUSPECT]
        for c, val in enumerate(self._row_values(i)):
            it = QTableWidgetItem(str(val))
            it.setTextAlignment(Qt.AlignCenter)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if c == 0:
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if use else Qt.Unchecked)
            elif c == 2 and nx > 1:
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if expand else Qt.Unchecked)
            if c == self.COLS.index("value"):
                xchk = h.get("xcheck")
                if bad:
                    # doubt outlives checkbox
                    it.setBackground(QColor("#fff3cd"))
                    it.setToolTip(tr('Uncertain read') + ": "
                                  + ", ".join(bad))
                elif xchk == "disagree":
                    it.setBackground(QColor("#fff3cd"))
                    it.setToolTip(tr('VLM read %s -- disagrees with reader')
                                  % (h.get("xcheck_alt") or "?"))
                elif xchk == "agree":
                    it.setBackground(QColor("#e4efe4"))
                    it.setToolTip(tr('Reader and VLM agree'))
            self.table.setItem(i, c, it)
        self.table.blockSignals(False)

    def _item_changed(self, it):
        i, c = it.row(), it.column()
        if i >= len(self.rows):
            return
        if c == 0:
            self.rows[i][0] = (it.checkState() == Qt.Checked)
            self._touched.add(i)         # hand tick outranks preset
        elif c == 2 and self._nx(self.rows[i][1]) > 1:
            self.rows[i][5] = (it.checkState() == Qt.Checked)

    def _preset_changed(self, name):
        if not name or name == self.preset:
            return
        self.preset = name              # committed on accept
        hdr = self._sheet_header()
        for i, row in enumerate(self.rows):
            if i in self._touched:
                continue
            use, h, rw = row[0], row[1], row[2]
            use = scan_ticked(h, rw, self.app.cfg, {"scan_preset": name}, hdr)
            if _starts_unticked(h):
                use = False
            row[0] = use
            self._set_check(i, 0, use)

    def _set_check(self, i, col, on):
        it = self.table.item(i, col)
        if it is not None:
            self.table.blockSignals(True)
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self.table.blockSignals(False)

    def _set_all(self, on):
        for i in range(len(self.rows)):
            self.rows[i][0] = on
            self._set_check(i, 0, on)

    def _rebuild(self, i):
        use, h, rw, pg, ov, expand = self.rows[i]
        rw = self._to_row(h, pg)
        if ov.get("type"):
            rw["type"] = ov["type"]
        rw["gage"] = ov.get("gage") or self.app.suggest(rw)
        self.rows[i][2] = rw
        self._fill_row(i)

    def _toggle_use(self, i):
        self.rows[i][0] = not self.rows[i][0]
        self._set_check(i, 0, self.rows[i][0])

    def _toggle_bare(self):
        bare = [i for i, r in enumerate(self.rows)
                if r[1].get("sb") == "BARE"]
        if not bare:
            return
        target = not self.rows[bare[0]][0]
        for i in bare:
            self.rows[i][0] = target
            self._set_check(i, 0, target)

    def _bulk_edit(self):
        idx = [i for i, r in enumerate(self.rows) if r[0]]
        if not idx:
            QMessageBox.information(
                self, tr('Bulk edit'),
                tr('No rows checked'))
            return
        KEEP = tr('- keep')
        dlg = QDialog(self)
        dlg.setWindowTitle("%s (%d)" % (tr('Bulk edit checked'),
                                        len(idx)))
        g = QGridLayout(dlg)
        cb_t = QComboBox()
        cb_t.addItem(KEEP, None)
        for _t in TYPES:
            cb_t.addItem(tr(_t), _t)
        cb_g = QComboBox()
        cb_g.setEditable(False)
        cb_g.addItem(KEEP)
        cb_g.addItems(gage_choices(self.app.cfg))
        e_tol = QLineEdit()
        e_tol.setPlaceholderText(KEEP)
        g.addWidget(QLabel(tr('Type')), 0, 0)
        g.addWidget(cb_t, 0, 1)
        g.addWidget(QLabel(tr('Gage')), 1, 0)
        g.addWidget(cb_g, 1, 1)
        g.addWidget(QLabel("Tol"), 2, 0)
        g.addWidget(e_tol, 2, 1)
        bw = QWidget()
        bl = QHBoxLayout(bw)
        b_ok = QPushButton(tr('Apply'))
        b_ok.setDefault(True)
        b_ok.clicked.connect(dlg.accept)
        b_no = QPushButton(tr('Cancel'))
        b_no.clicked.connect(dlg.reject)
        bl.addStretch(1)
        bl.addWidget(b_ok)
        bl.addWidget(b_no)
        g.addWidget(bw, 3, 0, 1, 2)
        retranslate(dlg)
        if not dlg.exec():
            return
        new_t = cb_t.currentData()
        new_g = cb_g.currentText().strip()
        new_tol = e_tol.text().strip()
        for i in idx:
            use, h, rw, pg, ov, expand = self.rows[i]
            if new_t is not None:
                ov["type"] = new_t
            if new_g and new_g != KEEP:
                ov["gage"] = new_g
            if new_tol:
                h["t"] = new_tol
            if new_t is not None or (new_g and new_g != KEEP) or new_tol:
                self._edited_hits.add(id(h))
            self._rebuild(i)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space:
            row = self.table.currentRow()
            if row >= 0:
                self._toggle_use(row)
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept()
            return
        super().keyPressEvent(e)

    def _double(self, row, col):
        name = self.COLS[col]
        if name in ("type", "value", "tol", "gage"):
            self._cell_edit(row, name)

    def _cell_edit(self, i, col):
        use, h, rw, pg, ov, expand = self.rows[i]
        if col == "type":
            val, ok = QInputDialog.getItem(self, "type", "type", TYPES,
                                           TYPES.index(rw["type"])
                                           if rw["type"] in TYPES else 0,
                                           False)
            if ok and val:
                ov["type"] = val
                rw["type"] = val
                self._edited_hits.add(id(h))
                self._fill_row(i)
        elif col == "gage":
            cur = str(rw.get("gage") or "")
            names = gage_choices(self.app.cfg, cur, blank=True)
            val, ok = QInputDialog.getItem(
                self, "gage", "gage", names,
                names.index(cur.strip()) if cur.strip() in names else 0, False)
            if ok:
                ov["gage"] = val
                rw["gage"] = val
                self._edited_hits.add(id(h))
                self._fill_row(i)
        elif col == "tol":
            val, ok = QInputDialog.getText(self, "tol", "tol",
                                           text=h.get("t") or "")
            if ok:
                h["t"] = val.strip() or None
                self._edited_hits.add(id(h))
                self._rebuild(i)
        else:
            val, ok = QInputDialog.getText(self, "value", "value", text=h["v"])
            if ok and val.strip():
                h["v"] = val.strip()
                self._edited_hits.add(id(h))
                self.rows[i][5] = self._nx(h) > 1
                self._rebuild(i)

    def _hover(self, item):
        i = item.row()
        self.app._scanhl = (self.rows[i][3], self.rows[i][1].get("rect")) \
            if self.rows[i][1].get("rect") else None
        self.app.redraw_overlay()

    def _commit_preset(self):
        """On accept only, Cancel restates nothing."""
        if self.preset == getattr(self, "_preset0", self.preset):
            return
        name = self.preset
        store = getattr(self.app, "store", None)
        if store is not None and not getattr(store, "read_only", False):
            store.header["H6"] = name
            run = store.run() if hasattr(store, "run") else None
            if run is not None and not run.get("closed"):
                run["inspection"] = name
            # accept may add no row
            save = getattr(self.app, "_save_session", None)
            if callable(save):
                save()

    def _accept(self):
        app = self.app
        self._commit_preset()
        added = 0
        unanchored = 0
        fy = {}
        snapped = False
        nrows = 0
        items = []
        for use, h, rw, pg, ov, expand in self.rows:
            if not use:
                continue
            page = app.doc[pg]
            ax = ay = None
            rect = h.get("rect")
            if rect:
                ax = (rect[0] + rect[2]) / 2.0
                ay = (rect[1] + rect[3]) / 2.0
            else:
                needles = (denorm_candidates(h["raw"]) +
                           denorm_candidates(h["v"]))
                for needle in needles:
                    try:
                        hits_r = page.search_for(needle)
                    except Exception:
                        hits_r = []
                    if hits_r:
                        r = hits_r[0]
                        ax, ay = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
                        break
            anchored = ax is not None
            if not anchored:
                ax, ay = 16.0, fy.get(pg, 20.0)
                fy[pg] = ay + 24.0
                if fy[pg] > page.rect.height - 20:
                    fy[pg] = 20.0
                unanchored += 1
            items.append({"h": h, "rw": rw, "pg": pg, "expand": expand,
                          "ax": ax, "ay": ay, "rect": rect,
                          "anchored": anchored})

        clockwise_order(items)

        group_anchor = {}
        group_qty = {}
        for it in items:
            cg = it["h"].get("cg")
            it["_key"] = (it["pg"], cg) if cg is not None \
                else ("_", id(it["h"]))
            if it["_key"] not in group_anchor:
                group_anchor[it["_key"]] = it
            q = repeat_count(it["rw"].get("feature"))
            group_qty[it["_key"]] = max(group_qty.get(it["_key"], 1), q)

        first = {}
        for k, it in enumerate(items):
            first.setdefault(it["_key"], k)
        items.sort(key=lambda it: (first[it["_key"]],
                                   facet_rank(it["h"].get("facet"), app.cfg)))

        pending = []
        # batch obstacles, own group excluded
        batch = {}
        for it in items:
            if it.get("rect"):
                ga = group_anchor[it["_key"]]
                batch.setdefault(it["pg"], []).append(
                    (it["rect"], ga["ax"], ga["ay"]))
        app._batch_boxes = batch
        try:
            for it in items:
                h, rw, pg, expand = it["h"], it["rw"], it["pg"], it["expand"]
                anchor = group_anchor[it["_key"]]
                ax, ay, rect = anchor["ax"], anchor["ay"], anchor["rect"]
                if not snapped:
                    app.snapshot()
                    snapped = True
                bx, by, lead = app.place_bubble(
                    ax, ay, page_i=pg, rect=rect,
                    tier=tier_for_type(rw.get("type"), app.cfg,
                                       rw.get("tier", "")))
                base = dict(rw)
                base["leader"] = lead
                t2768 = insert_general_tol(base, h, app.cfg,
                                           app.last.get("iso_on"),
                                           app.last.get("icls", "m"),
                                           session=app.drawing,
                                           gtols=self.gtols.get(pg) or {})
                if t2768 is not None:
                    base["tol_sym"] = t2768
                    base["gage"] = app.suggest(base)
                gq = group_qty.get(it["_key"], 1)
                for d in expand_hole_row(base, app.cfg, repeat=expand):
                    if expand and gq > 1 and not d.get("qty"):
                        d["qty"] = gq
                    if not d.get("gage"):
                        d["gage"] = app.suggest(d)
                    d["leader"] = lead
                    d["tier"] = tier_for_type(d.get("type"), app.cfg,
                                              d.get("tier", ""))
                    d.update({"bubble": "", "page": pg,
                              "x": ax, "y": ay, "bx": bx, "by": by,
                              "sheet_row": None,
                              "rect": list(it["rect"]) if it.get("rect") else None})
                    # for acceptance store
                    d["proposal"] = dict(self._proposals.get(id(h)) or {})
                    pending.append((d, it["_key"]))
                added += 1
        finally:
            app._batch_boxes = None
        # count row per group, Settings decides
        by_key = {}
        for d, key in pending:
            by_key.setdefault(key, []).append(d)
        for key, grp in by_key.items():
            for q in with_qty_row(grp, app.cfg)[len(grp):]:
                pending.append((q, key))

        # one uid per measurable row
        counts = {}
        for _d, key in pending:
            counts[key] = counts.get(key, 0) + 1
        gid_of = {}
        for d, key in pending:
            d["uid"] = app.store.new_uid()
            if counts[key] > 1:
                gid_of.setdefault(key, d["uid"])   # first uid groups
                d["bgroup"] = gid_of[key]
            app.ledger.append(d)
            nrows += 1
        app.store.renumber()
        sess_ok = app._save_session()
        app.refresh_panel()
        app.render()
        self.accept()
        msg = tr("added %d balloon(s), %d row(s)") % (added, nrows)
        if not sess_ok:
            msg += "; " + tr("NOT saved to disk")
        if unanchored:
            msg += "; %d unanchored (left margin) - drag into place" \
                   % unanchored
        app.set_status(msg)


