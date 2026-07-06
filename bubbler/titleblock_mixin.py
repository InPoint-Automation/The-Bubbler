# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Title-block region read via bottom-right heuristic.

from .i18n import tr
from .titleblock import parse_titleblock


class TitleblockMixin:
    def _titleblock_rect(self, page):
        r = page.rect
        w, h = r.width, r.height
        x0 = r.x0 + 0.55 * w
        y0 = r.y0 + 0.72 * h
        x1 = r.x1
        y1 = r.y1
        x0 = max(r.x0, min(x0, r.x1))
        y0 = max(r.y0, min(y0, r.y1))
        x1 = max(r.x0, min(x1, r.x1))
        y1 = max(r.y0, min(y1, r.y1))
        return (x0, y0, x1, y1)

    def _read_titleblock(self, page_i, rect):
        x0, y0, x1, y1 = rect
        sel_rect = (x0 - 2, y0 - 2, x1 + 2, y1 + 2)
        res = self._run_capture(page_i, rect, sel_rect,
                                want_meta=False, want_hits=False)
        if res is None or not res.get("sel"):
            self.set_status(tr('no title block found'))
            return {}
        try:
            return parse_titleblock(res["sel"]) or {}
        except Exception:
            return {}

    def _titleblock_autofill(self):
        if getattr(self, "_tb_autofill_done", False):
            return
        if not self.cfg.get("titleblock_autofill", True):
            return
        try:
            cur = self.writer.get_header()
        except Exception:
            return
        if any(str(v).strip() for v in cur.values()):
            return
        self._tb_autofill_done = True
        try:
            page = self.doc[self.page_i]
        except Exception:
            return
        parsed = self._read_titleblock(self.page_i, self._titleblock_rect(page))
        if parsed:
            self.header_editor(prefill=parsed)
