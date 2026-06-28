# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Quick-access bar ("hotbar") for MainWindow.

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMenu

from .common import TYPES, TIERS
from .config import save_cfg
from .hotbar import Hotbar, HotbarAction


class HotbarMixin:
    def _kbd_qbar(self):
        if self._entry_focused() or self.measure_mode:
            return
        if self._qbar is None:
            self._qbar_show()
        else:
            self._qbar_hide()

    def _position_qbar(self):
        if self._qbar is None:
            return
        self._qbar.adjustSize()
        vp = self.view
        x = vp.x() + (vp.width() - self._qbar.width()) // 2
        y = vp.y() + vp.height() - self._qbar.height() - 16
        self._qbar.move(max(0, x), max(0, y))

    def _qbar_show(self, persist=True):
        if self._qbar is not None:
            return
        self._qbar = Hotbar(self, self._hotbar_run, self._qbar_hide)
        self._qbar_refresh()
        self._qbar.show()
        self._position_qbar()
        if persist:
            self.cfg["hotbar_on"] = True
            save_cfg(self.cfg)

    def _qbar_hide(self):
        if self._qbar is not None:
            bar = self._qbar
            self._qbar = None
            # clear drop-shadow ghost
            geo = bar.geometry().adjusted(-32, -32, 32, 32)
            bar.hide()
            bar.deleteLater()
            self.update(geo)
            self.view.viewport().update()
            self.cfg["hotbar_on"] = False
            save_cfg(self.cfg)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_qbar()

    def _cycle_type(self):
        cur = self.last.get("type", TYPES[0])
        i = (TYPES.index(cur) + 1) % len(TYPES) if cur in TYPES else 0
        self._rib_set("type", TYPES[i], group=True)
        self.cb_type.setCurrentText(TYPES[i])

    def _set_type_index(self, i):
        if 0 <= i < len(TYPES):
            self._rib_set("type", TYPES[i], group=True)
            self.cb_type.setCurrentText(TYPES[i])

    def _cycle_tier(self):
        cur = self.last.get("tier", "")
        i = (TIERS.index(cur) + 1) % len(TIERS) if cur in TIERS else 0
        self._rib_set("tier", TIERS[i])
        self.cb_tier.setCurrentText(TIERS[i])

    def _toggle_cfg(self, key):
        self.cfg[key] = not self.cfg.get(key)
        save_cfg(self.cfg)

    def _set_offset_dir(self, d):
        self.cfg["offset_dir"] = d
        save_cfg(self.cfg)
        if self._qbar is not None:
            self._qbar.flash_name("offset")
            QTimer.singleShot(160, self._qbar_refresh)
        self.set_status("bubble offset: %s" % self._OFF_LABEL.get(d, d))

    def _cycle_offset_dir(self):
        order = ["auto", "n", "e", "s", "w"]
        cur = self.cfg.get("offset_dir", "auto")
        i = (order.index(cur) + 1) % len(order) if cur in order else 0
        self._set_offset_dir(order[i])

    def _offset_menu(self):
        m = QMenu(self)
        cur = self.cfg.get("offset_dir", "auto")
        for d in ("auto", "n", "e", "s", "w"):
            a = m.addAction(self._OFF_LABEL.get(d, d))
            a.setCheckable(True)
            a.setChecked(cur == d)
            a.triggered.connect(
                lambda _c=False, dd=d: self._set_offset_dir(dd))
        m.exec(self.cursor().pos())

    def _kbd_arrow(self, d):
        if self._entry_focused() or self.measure_mode:
            return False
        self._set_offset_dir(d)
        return True

    def _hotbar_actions(self):
        A = HotbarAction
        if self.tool == "select":
            n = len(self.sel)
            return [
                A("tool_add", "A", "Add tool / Dodawanie",
                  lambda: self.set_tool("add")),
                A("align_row", "R", "Align row / W rząd",
                  lambda: self.align_sel("h"), enabled=n >= 2),
                A("align_col", "C", "Align col / W kolumnę",
                  lambda: self.align_sel("v"), enabled=n >= 2),
                A("dist_h", "H", "Distribute H / Rozłóż H",
                  lambda: self.distribute_sel("h"), enabled=n >= 3),
                A("dist_v", "W", "Distribute V / Rozłóż V",
                  lambda: self.distribute_sel("v"), enabled=n >= 3),
                A("delete", "Del", "Delete / Usuń",
                  self.delete_selection, enabled=n >= 1),
                A("clear", "Esc", "Clear sel. / Wyczyść",
                  self._esc, enabled=n >= 1),
                A("measure", "M", "Measure / Pomiar",
                  lambda: self._kbd_toggle("m")),
            ]
        return [
            A("type", "1-7", "Type / Typ: %s"
              % self.last.get("type", "?").split(" /")[0], self._cycle_type),
            A("tier", "T", "Tier: %s" % (self.last.get("tier") or "-"),
              self._cycle_tier),
            A("iso", "I", "ISO auto: %s"
              % ("on" if self.last.get("iso_on") else "off"),
              lambda: self.chk_iso.setChecked(not self.chk_iso.isChecked())),
            A("dec", "D", "Dec. tol: %s"
              % ("on" if self.cfg.get("dp_on") else "off"),
              lambda: self._toggle_cfg("dp_on")),
            A("leaders", "L", "Leaders: %s"
              % ("on" if self.use_leaders() else "off"),
              lambda: self.chk_lead.setChecked(not self.chk_lead.isChecked())),
            A("pin", "P", "Pin=Ø: %s"
              % ("on" if self.cfg.get("hole_pin_auto", True) else "off"),
              lambda: self._toggle_cfg("hole_pin_auto")),
            A("snap", "S", "Snap: %s"
              % ("on" if self.cfg.get("snap_geom", True) else "off"),
              lambda: self._toggle_cfg("snap_geom")),
            A("tool_sel", "V", "Select tool / Zaznaczanie",
              lambda: self.set_tool("select")),
            A("offset", u"←↑→↓", "Offset: %s"
              % self._OFF_LABEL.get(self.cfg.get("offset_dir", "auto"),
                                    "auto"),
              self._offset_menu),
        ]

    def _qbar_refresh(self):
        if self._qbar is None:
            return
        try:
            self._qbar.set_actions(self._hotbar_actions())
            self._qbar.set_state_text(
                "tool:%s - sel:%d" % (self.tool, len(self.sel)))
            self._position_qbar()
        except RuntimeError:
            self._qbar = None

    def _hotbar_run(self, action, key):
        try:
            if action.name == "type" and key and str(key).isdigit():
                self._set_type_index(int(key) - 1)
            else:
                action.command()
        finally:
            QTimer.singleShot(160, self._qbar_refresh)
