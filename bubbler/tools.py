# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Canvas tool strategies. Per-tool press/click/drag.


class Tool:
    name = ""

    def __init__(self, win):
        self.w = win

    def press_empty(self, sp, predict):
        """Plain press on empty canvas."""

    def click_bubble(self, base):
        """Click on a bubble."""

    def click_empty(self, sp):
        """Click on empty canvas."""

    def drag_bubble(self, base, p):
        """Drag a bubble numeral to page point p."""

    def ctrl_click_bubble(self, base):
        """Ctrl+click on a bubble."""


class AddTool(Tool):
    name = "add"

    def press_empty(self, sp, predict):
        # plain click runs OCR/VLM capture
        if predict:
            self.w.on_capture_press(sp)

    def click_bubble(self, base):
        self.w.select_in_panel(base)

    def click_empty(self, sp):
        self.w.on_click(sp)

    def drag_bubble(self, base, p):
        self.w._set_bubble_pos(base, bx=p[0], by=p[1])

    def ctrl_click_bubble(self, base):
        # undoable, no prompt
        self.w._delete_bases([base])
        self.w.set_status("deleted #%s / usunięto - Ctrl+Z" % base)


class SelectTool(Tool):
    name = "select"

    def press_empty(self, sp, predict):
        self.w._drag = ("marquee", (sp.x(), sp.y()))

    def click_bubble(self, base):
        self.w._select_base(base, add=False)

    def click_empty(self, sp):
        pass    # marquee handles deselect

    def drag_bubble(self, base, p):
        # selected bubble moves whole selection
        if base in self.w._sel_bases():
            self.w._move_selection(base, p)
        else:
            self.w._set_bubble_pos(base, bx=p[0], by=p[1])

    def ctrl_click_bubble(self, base):
        self.w._select_base(base, add=True)


def make_tools(win):
    """name -> tool strategy for a window."""
    return {t.name: t(win) for t in (AddTool, SelectTool)}
