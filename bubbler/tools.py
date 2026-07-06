# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Canvas tool strategies.

from .i18n import tr


class Tool:
    name = ""

    def __init__(self, win):
        self.w = win

    def press_empty(self, sp, predict):
        pass

    def click_bubble(self, base):
        pass

    def click_empty(self, sp):
        pass

    def drag_bubble(self, base, p):
        pass

    def ctrl_click_bubble(self, base):
        pass


class AddTool(Tool):
    name = "add"

    def press_empty(self, sp, predict):
        if predict:
            self.w.on_capture_press(sp)

    def click_bubble(self, base):
        self.w.select_in_panel(base)

    def click_empty(self, sp):
        self.w.on_click(sp)

    def drag_bubble(self, base, p):
        self.w._set_bubble_pos(base, bx=p[0], by=p[1])

    def ctrl_click_bubble(self, base):
        self.w._delete_bases([base])
        self.w.set_status(tr('deleted #%s') % base)


class SelectTool(Tool):
    name = "select"

    def press_empty(self, sp, predict):
        self.w._drag = ("marquee", (sp.x(), sp.y()))

    def click_bubble(self, base):
        self.w._select_base(base, add=False)

    def click_empty(self, sp):
        pass

    def drag_bubble(self, base, p):
        if base in self.w._sel_bases():
            self.w._move_selection(base, p)
        else:
            self.w._set_bubble_pos(base, bx=p[0], by=p[1])

    def ctrl_click_bubble(self, base):
        self.w._select_base(base, add=True)


def make_tools(win):
    return {t.name: t(win) for t in (AddTool, SelectTool)}
