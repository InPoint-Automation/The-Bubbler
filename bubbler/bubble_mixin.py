# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble lifecycle from canvas clicks.

import re

from PySide6.QtWidgets import QMenu, QInputDialog, QMessageBox

from .common import base_of, fnum, dp_tol, tier_for_type
from .config import save_cfg, units_of
from .iso286 import fit_limits, is_fit_code
from .iso2768 import iso2768_tol
from .scanlib import expand_hole_row, scan_parse, scan_normalize
from .dialogs import BubbleDialog
from .i18n import tr


class BubbleMixin:
    def on_click(self, sp):
        p = self._page_xy(sp)
        if p is None or self.measure_mode:
            return
        x, y = self._snap_point(*p)
        self._new_bubble_at(x, y, None)

    def _new_bubble_at(self, x, y, at_screen, prefill=None, rect=None):
        at = tuple(self.dlg_pos) if self.dlg_pos else at_screen
        nxt = self.store.next_number(self.page_i)
        dlg = BubbleDialog(self, nxt, last=self.last, at=at, cfg=self.cfg,
                           prefill=prefill,
                           leader_default=self.use_leaders())
        dlg.exec()
        if dlg.last_geo:
            self.dlg_pos = dlg.last_geo
            self.cfg["dlg_pos"] = list(self.dlg_pos)
            save_cfg(self.cfg)
        if dlg.result_rows is None:
            return
        self.snapshot()
        self.last.update(getattr(dlg, "last_out", {}))
        self._rib_sync()
        bx, by = ((self.auto_offset(x, y, rect=rect))
                  if (self.use_leaders() or rect is not None)
                  else (x, y))
        uid = self.store.new_uid()
        for d in dlg.result_rows:
            rows = [d] if d.pop("_expanded", False) \
                else expand_hole_row(d, self.cfg)
            for rr in rows:
                if not rr.get("gage"):
                    rr["gage"] = self.suggest(rr)
                rr["tier"] = tier_for_type(rr.get("type"), self.cfg,
                                           rr.get("tier", ""))
                rr.update({"uid": uid, "page": self.page_i, "x": x, "y": y,
                           "bx": bx, "by": by, "sheet_row": None})
                self.ledger.append(rr)
        self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()

    def on_double(self, sp, gpos):
        p = self._page_xy(sp)
        if p is None:
            return
        hit = self.hit_bubble(*p)
        if hit is None:
            return
        rows = [(i, d) for i, d in enumerate(self.ledger)
                if base_of(d["bubble"]) == hit and
                d.get("page") == self.page_i]
        if not rows:
            return
        if len(rows) == 1:
            self.edit_ledger_row(rows[0][0])
            return
        m = QMenu(self)
        for i, d in rows:
            m.addAction("#%s  %s  %s" % (
                d["bubble"], d.get("feature", ""),
                "" if d.get("nominal") is None else "%g" % d["nominal"]),
                lambda i=i: self.edit_ledger_row(i))
        m.exec(gpos.toPoint())

    def select_in_panel(self, basenum):
        if not self.panel_visible:
            self.toggle_panel()
        for i, d in enumerate(self.ledger):
            if base_of(d["bubble"]) == basenum:
                self._panel_highlight(i, scroll=True, mute=True)
                return

    def on_shift_click(self, sp, gpos):
        self._swallow = True
        p = self._page_xy(sp)
        if p is None or self.measure_mode:
            return
        if self.hit_bubble(*p) is not None:
            return
        nxt = self.store.next_number(self.page_i)
        s, ok = QInputDialog.getText(
            self, "Bubble #%d" % nxt,
            tr('Nominal (sticky values'))
        if not ok:
            return
        try:
            nom = fnum(s)
        except ValueError:
            QMessageBox.critical(self, tr('Error'), "Bad number: %s" % s)
            return
        self._commit_sticky_bubble(p, nom, dp_src=s)

    def _commit_sticky_bubble(self, p, nom, dp_src=""):
        """Place a bubble at page-point p using sticky ribbon values."""
        nxt = self.store.next_number(self.page_i)
        t = self.last.get("type", "dim")
        is_hole = t.startswith(("hole", "thru"))
        if is_hole and nom is not None:
            feat = u"Ø%.2f" % nom
        elif nom is not None:
            feat = "%.2f" % nom
        else:
            feat = ""
        pin = fnum(self.last.get("pin", "") or "")
        d = {"bubble": str(nxt), "type": t, "feature": feat,
             "nominal": nom, "tier": self.last.get("tier", ""),
             "pin": pin, "offset": None, "measured": None,
             "tol_sym": None, "tol_max": None, "tol_min": None}
        tmax = fnum(self.last.get("tmax", ""))
        tmin = fnum(self.last.get("tmin", ""))
        raw_sym = str(self.last.get("tsym", "") or "").strip()
        metric = units_of(self.cfg) == "iso_mm"
        if metric and is_fit_code(raw_sym):
            lim = fit_limits(nom, raw_sym) if nom is not None else None
            if lim is None:
                QMessageBox.critical(
                    self, "ISO 286",
                    "%s: needs a supported nominal ≤ 500 mm / wymaga "
                    "nominału" % raw_sym)
                return
            d["tol_max"], d["tol_min"] = lim
            d["feature"] = (feat + " " + raw_sym).strip()
        elif tmax is not None or tmin is not None:
            d["tol_max"], d["tol_min"] = tmax, tmin
        elif raw_sym:
            try:
                d["tol_sym"] = fnum(raw_sym)
            except ValueError:
                QMessageBox.critical(self, tr('Error'),
                                     "Bad tolerance: %s" % raw_sym)
                return
        elif metric and self.last.get("iso_on"):
            t2 = iso2768_tol(nom, self.last.get("icls", "m"))
            if t2 is None:
                t2 = dp_tol(dp_src, self.cfg)
            if t2 is not None:
                d["tol_sym"] = t2
        else:
            t2 = dp_tol(dp_src, self.cfg)
            if t2 is not None:
                d["tol_sym"] = t2
        x, y = self._snap_point(*p)
        bx, by = ((self.auto_offset(x, y)) if self.use_leaders()
                  else (x, y))
        d["gage"] = self.suggest(d)
        d["leader"] = self.use_leaders()
        self.snapshot()
        uid = self.store.new_uid()
        for rr in expand_hole_row(d, self.cfg):
            if not rr.get("gage"):
                rr["gage"] = self.suggest(rr)
            rr.setdefault("leader", self.use_leaders())
            rr["tier"] = tier_for_type(rr.get("type"), self.cfg,
                                       rr.get("tier", ""))
            rr.update({"uid": uid, "page": self.page_i, "x": x, "y": y,
                       "bx": bx, "by": by, "sheet_row": None})
            self.ledger.append(rr)
        self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()

    def _capture_nominal(self, p):
        """Read numeric nominal from PDF text at page-point p."""
        px, py = p
        box = self._capture_box(px, py)
        res = self._run_capture(self.page_i, box, box,
                                want_meta=False, want_hits=True)
        if res is None:
            return None, ""
        sel = res["sel"]
        if not sel:
            return None, ""
        text = res["text"]
        hits = res["hits"] or []
        if not hits:
            hits = scan_parse(scan_normalize(text), self.cfg)
        src = str(hits[0].get("v")) if hits and hits[0].get("v") else \
            scan_normalize(text)
        m = re.search(r"\d+(?:[.,]\d+)?", src)
        if not m:
            return None, ""
        try:
            return fnum(m.group(0)), m.group(0)
        except ValueError:
            return None, ""

    def on_alt_shift_click(self, sp):
        self._swallow = True
        if self.measure_mode:
            return
        p = self._page_xy(sp)
        if p is None or self.hit_bubble(*p) is not None:
            return
        nom, src = self._capture_nominal(p)
        if nom is None:
            self.set_status(tr('no number here'))
            return
        self._commit_sticky_bubble(p, nom, dp_src=src)
        self.set_status(tr('captured %s') % src)

    def on_ctrl_click(self, sp):
        self._swallow = True
        p = self._page_xy(sp)
        if p is None:
            return
        hit = self.hit_bubble(*p)
        if hit is None:
            return
        self._active_tool.ctrl_click_bubble(hit)

    def _delete_bases(self, bases):
        if not bases:
            return
        self.snapshot()
        uids = set()
        for d in self.ledger:
            if base_of(d["bubble"]) in bases:
                uids.add(d["uid"])
                if d.get("sheet_row"):
                    self.writer.clear_row(d["sheet_row"])
        try:
            self.writer.save()
        except Exception:
            pass
        for u in uids:
            self.store.remove(u)
            self.sel.discard(u)
        self._qbar_refresh()
        self._save_session()
        self.refresh_panel()
        self.render()

    def delete_selection(self):
        bases = self._sel_bases()
        if not bases:
            return
        if len(bases) > 1 and QMessageBox.question(
                self, "Delete / Usuń",
                tr('Delete %d selected bubble(s)?')
                % len(bases)) != QMessageBox.Yes:
            return
        n = len(bases)
        self._delete_bases(bases)
        self.set_status(tr('deleted %d') % n)
