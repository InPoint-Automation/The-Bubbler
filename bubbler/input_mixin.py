# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Pointer input mixin. Zoom, drag, selection.

from PySide6.QtCore import Qt, QPointF

from .common import base_of


class InputMixin:
    def on_wheel(self, e):
        mods = e.modifiers()
        dy = e.angleDelta().y()
        if mods & Qt.ControlModifier:
            self.zoom_at(e, 1.15 if dy > 0 else 1 / 1.15)
        else:
            v = self.view.verticalScrollBar()
            v.setValue(v.value() - (2 if dy > 0 else -2) * 20)

    def zoom_at(self, e, f):
        sp = self.view.mapToScene(e.position().toPoint())
        page = self._page_xy(sp)
        self.zoom = max(0.3, min(8.0, self.zoom * f))
        self.render()
        if page is not None:
            target = self._scr(page[0], page[1])
            vp_pos = e.position()
            new_center_view = QPointF(self.view.viewport().width() / 2.0,
                                      self.view.viewport().height() / 2.0)
            # keep clicked point under cursor
            delta = self.view.mapFromScene(target) - vp_pos.toPoint()
            h = self.view.horizontalScrollBar()
            v = self.view.verticalScrollBar()
            h.setValue(h.value() + delta.x())
            v.setValue(v.value() + delta.y())

    def on_press(self, sp, vpos, predict=True):
        if self._scan_region_mode:
            self._scan_drag = (sp.x(), sp.y(), sp.x(), sp.y())
            return
        self._swallow = False
        self._drag = None
        self._dragged = False
        self._press = vpos
        self._press_scene = sp
        p = self._page_xy(sp)
        if p is None:
            return
        hit = self.hit_anchor(*p)
        if hit is not None:
            self._drag = ("anchor", hit)
            return
        hit = self.hit_bubble(*p)
        if hit is not None:
            self._drag = ("bubble", hit)
            return
        # active tool handles empty space
        self._active_tool.press_empty(sp, predict)

    def on_motion(self, sp, vpos):
        if self._scan_region_mode:
            if self._scan_drag is not None:
                x0, y0, _, _ = self._scan_drag
                self._scan_drag = (x0, y0, sp.x(), sp.y())
                self.redraw_overlay()
            return
        if not self._drag or self._press is None:
            return
        if abs(vpos.x() - self._press.x()) < 5 and \
                abs(vpos.y() - self._press.y()) < 5:
            return
        kind, b = self._drag
        if kind == "marquee":
            x0, y0 = b
            self._marquee = (x0, y0, sp.x(), sp.y())
            self._dragged = True
            self.redraw_overlay()
            return
        p = self._page_xy(sp)
        if p is None:
            return
        if not self._dragged:
            self.snapshot()
        if kind == "bubble":
            self._active_tool.drag_bubble(b, p)
        else:
            ax, ay = self._snap_point(p[0], p[1], quiet=True)
            self._set_bubble_pos(b, ax=ax, ay=ay)
        self._dragged = True
        self.redraw_overlay()

    def _sel_bases(self):
        out = set()
        for d in self.ledger:
            if d["uid"] in self.sel and d.get("page") == self.page_i:
                out.add(base_of(d["bubble"]))
        return out

    def _move_selection(self, lead_base, p):
        lead = None
        for b, _, _, bx, by in self.page_bubbles():
            if b == lead_base:
                lead = (bx, by)
                break
        if lead is None:
            return
        dx, dy = p[0] - lead[0], p[1] - lead[1]
        for b, _, _, bx, by in self.page_bubbles():
            if b in self._sel_bases():
                self._set_bubble_pos(b, bx=bx + dx, by=by + dy)

    def on_release(self, sp, vpos):
        if self._scan_region_mode:
            self._finish_scan_drag(sp)
            return
        if self._swallow:
            # gesture already handled
            self._swallow = False
            self._drag = None
            self._dragged = False
            return
        dragged = self._dragged
        drag = self._drag
        self._drag = None
        self._dragged = False
        if drag is not None and drag[0] == "marquee":
            self._marquee = None
            if dragged:
                self._marquee_select(drag[1], sp)
            else:
                self.sel.clear()
                self.redraw_overlay()
                self._qbar_refresh()
            return
        if dragged:
            self._save_session()
            self.redraw_overlay()
            return
        if drag is not None:
            kind, b = drag
            if self.measure_mode:
                self.measure_bubble(b)
            else:
                self._active_tool.click_bubble(b)
            return
        self._active_tool.click_empty(sp)

    def _uid_of_base(self, basenum):
        for d in self.ledger:
            if base_of(d["bubble"]) == basenum and \
                    d.get("page") == self.page_i:
                return d["uid"]
        return None

    def _select_base(self, basenum, add=False):
        u = self._uid_of_base(basenum)
        if u is None:
            return
        if not add:
            self.sel = {u}
        elif u in self.sel:
            self.sel.discard(u)
        else:
            self.sel.add(u)
        self.select_in_panel(basenum)
        self.redraw_overlay()
        self._qbar_refresh()

    def _marquee_select(self, start, sp):
        x0, y0 = start
        x1, y1 = sp.x(), sp.y()
        lo_x, hi_x = min(x0, x1), max(x0, x1)
        lo_y, hi_y = min(y0, y1), max(y0, y1)
        for b, _, _, bx, by in self.page_bubbles():
            c = self._scr(bx, by)
            if lo_x <= c.x() <= hi_x and lo_y <= c.y() <= hi_y:
                u = self._uid_of_base(b)
                if u is not None:
                    self.sel.add(u)
        self.redraw_overlay()
        self._qbar_refresh()
        self.set_status("%d selected / zaznaczono" % len(self.sel))

