# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble lifecycle from canvas clicks.

import re

from PySide6.QtWidgets import QMenu, QInputDialog, QMessageBox

from .common import base_of, fnum, tier_for_type
from .config import save_cfg, units_of
from .iso286 import fit_limits, is_fit_code
from .iso2768 import is_angle_feature
from .scanlib import (expand_hole_row, scan_parse, scan_normalize,
                      general_tol)
from .dialogs import BubbleDialog
from .units import format_nominal
from .i18n import tr


class BubbleMixin:
    def _row_tier(self, row):
        """tier row gets before written"""
        row = row or {}
        return tier_for_type(row.get("type"), self.cfg, row.get("tier", ""))

    def on_click(self, sp):
        p = self._page_xy(sp)
        if p is None or self.measure_mode:
            return
        x, y = self._snap_point(*p)
        self._new_bubble_at(x, y, None)

    def _new_bubble_at(self, x, y, at_screen, prefill=None, rect=None):
        if self._edit_blocked():          # sealed drops input
            return
        at = tuple(self.dlg_pos) if self.dlg_pos else at_screen
        nxt = self.store.next_number(self.page_i)
        dlg = BubbleDialog(self, nxt, last=self.last, at=at, cfg=self.cfg,
                           session=self.drawing, gtols=self.gtols_now(),
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
        want = bool(dlg.result_rows[0].get("leader", self.use_leaders())) \
            if dlg.result_rows else self.use_leaders()
        tier0 = self._row_tier(dlg.result_rows[0] if dlg.result_rows else {})
        bx, by, lead = self.place_bubble(x, y, rect=rect, lead=want,
                                         tier=tier0)
        uid = self.store.new_uid()
        for d in dlg.result_rows:
            rows = [d] if d.pop("_expanded", False) \
                else expand_hole_row(d, self.cfg)
            for rr in rows:
                if not rr.get("gage"):
                    rr["gage"] = self.suggest(rr)
                rr["leader"] = lead          # flag matches offset
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
            tr('Nominal (sticky values)'))
        if not ok:
            return
        try:
            nom = fnum(s)
        except ValueError:
            QMessageBox.critical(self, tr('Error'), "Bad number: %s" % s)
            return
        self._commit_sticky_bubble(p, nom, dp_src=s)

    def _commit_sticky_bubble(self, p, nom, dp_src=""):
        """place bubble using sticky ribbon values"""
        if self._edit_blocked():          # sealed drops input
            return
        nxt = self.store.next_number(self.page_i)
        t = self.last.get("type", "dim")
        is_hole = t.startswith(("hole", "thru"))
        u = units_of(self.cfg, self.drawing)
        if is_hole and nom is not None:
            feat = u"Ø%s" % format_nominal(nom, u)
        elif is_angle_feature(dp_src):
            feat = str(dp_src).strip()     # "45 deg" stays ANGLE
        elif nom is not None:
            feat = format_nominal(nom, u)
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
        metric = units_of(self.cfg, self.drawing) == "iso_mm"
        if metric and is_fit_code(raw_sym):
            lim = fit_limits(nom, raw_sym) if nom is not None else None
            if lim is None:
                QMessageBox.critical(
                    self, "ISO 286",
                    tr('%s: needs nominal ≤ 500 mm') % raw_sym)
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
        else:
            # shared answer every path
            res = general_tol({"type": t, "feature": d["feature"],
                               "v": dp_src or d["feature"], "nominal": nom},
                              self.gtols_now(), self.cfg, self.drawing,
                              icls=self.last.get("icls"),
                              iso_on=bool(self.last.get("iso_on")))
            if res.value:
                d["tol_sym"] = float(res.value)
        x, y = self._snap_point(*p)
        bx, by, lead = self.place_bubble(x, y, tier=self._row_tier(d))
        d["gage"] = self.suggest(d)
        d["leader"] = lead
        self.snapshot()
        uid = self.store.new_uid()
        for rr in expand_hole_row(d, self.cfg):
            if not rr.get("gage"):
                rr["gage"] = self.suggest(rr)
            rr["leader"] = lead
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
        """read nominal from PDF text"""
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
            # whole callout preserved
            return fnum(m.group(0)), src.strip()
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
        if self._edit_blocked():          # sealed sheet stays issued
            return
        self.snapshot()
        uids = set()
        for d in self.ledger:
            if base_of(d["bubble"]) in bases:
                uids.add(d["uid"])
                if d.get("sheet_row"):
                    self.writer.clear_row(d["sheet_row"])
        for u in uids:
            self.store.remove(u)
            self.sel.discard(u)
        self._resync_sheet_rows()
        self._qbar_refresh()
        self._save_session()
        self.refresh_panel()
        self.render()

    def toggle_sel_leaders(self):
        """flip leader flag on selected bubbles"""
        bases = self._sel_bases()
        if not bases:
            return
        # any off -> all on
        want = not all(self._leader_of(b) for b in bases)
        self.snapshot()
        n = 0
        for b in sorted(bases):
            rows = [d for d in self.ledger
                    if base_of(d["bubble"]) == b and
                    d.get("page") == self.page_i]
            if not rows:
                continue
            ax, ay = rows[0]["x"], rows[0]["y"]
            bx, by, lead = self.place_bubble(ax, ay, lead=want,
                                             tier=self._row_tier(rows[0]))
            for d in rows:
                d["leader"] = lead
                d["bx"], d["by"] = bx, by
            n += 1
        if not n:
            return
        self._qbar_refresh()
        self._save_session()
        self.refresh_panel()
        self.render()
        self.set_status((tr('leaders on for %d bubble(s)') if want
                         else tr('leaders off for %d bubble(s)')) % n)

    def group_selection(self):
        """H7 one balloon over selected callouts"""
        bases = self._sel_bases()
        rows = [d for d in self.ledger
                if base_of(d["bubble"]) in bases
                and d.get("page") == self.page_i]
        uids = {d["uid"] for d in rows}
        if len(uids) < 2:
            self.set_status(tr('select 2 or more bubbles to group'))
            return
        self.snapshot()
        gid = min(uids)                         # stable group id
        ax = sum(d["x"] for d in rows) / len(rows)
        ay = sum(d["y"] for d in rows) / len(rows)
        want = all(d.get("leader") for d in rows)   # only if all had
        bx, by, lead = self.place_bubble(ax, ay, lead=want,
                                         tier=self._row_tier(rows[0]))
        for d in rows:
            d.setdefault("_pre_group_xy", [d["x"], d["y"]])  # for ungroup
            d["bgroup"] = gid
            d["user_group"] = True
            d["x"], d["y"] = ax, ay
            d["bx"], d["by"] = bx, by
            d["leader"] = lead
        self.store.renumber()
        self.sel.clear()
        self._resync_sheet_rows()
        self._qbar_refresh()
        self._save_session()
        self.refresh_panel()
        self.render()
        self.set_status(tr('grouped %d bubbles into one') % len(uids))

    def ungroup_selection(self):
        """H7 reverse user Group per uid"""
        bases = self._sel_bases()
        rows = [d for d in self.ledger
                if base_of(d["bubble"]) in bases
                and d.get("page") == self.page_i
                and d.get("user_group")]
        if not rows:
            self.set_status(tr('no grouped bubble selected'))
            return
        self.snapshot()
        for d in rows:
            d.pop("bgroup", None)
            xy = d.pop("_pre_group_xy", None)
            if xy:
                d["x"], d["y"] = xy[0], xy[1]
            d.pop("user_group", None)
        groups = {}
        for d in rows:
            groups.setdefault(d["uid"], []).append(d)
        for grp in groups.values():
            ax, ay = grp[0]["x"], grp[0]["y"]
            want = all(g.get("leader") for g in grp)
            bx, by, lead = self.place_bubble(ax, ay, lead=want,
                                             tier=self._row_tier(grp[0]))
            for d in grp:
                d["bx"], d["by"] = bx, by
                d["leader"] = lead
        self.store.renumber()
        self.sel.clear()
        self._resync_sheet_rows()
        self._qbar_refresh()
        self._save_session()
        self.refresh_panel()
        self.render()
        self.set_status(tr('ungrouped into %d bubble(s)') % len(groups))

    def delete_selection(self):
        bases = self._sel_bases()
        if not bases:
            return
        if len(bases) > 1 and QMessageBox.question(   # Enter must not delete
                self, tr('Delete'),
                tr('Delete %d bubble(s)?') % len(bases),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        n = len(bases)
        self._delete_bases(bases)
        self.set_status(tr('deleted %d') % n)
