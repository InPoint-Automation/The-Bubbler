# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Page <-> scene affine transform + view state.

from collections import OrderedDict


class Viewport:
    def __init__(self):
        self.page_i = 0
        self.zoom = 1.5
        self.rotation = 0
        self.pix_cache = OrderedDict()    # (page, zoom, rot) → QPixmap
        # identity until first render
        self.a = 1.0
        self.b = 0.0
        self.c = 0.0
        self.d = 1.0
        self.e = 0.0
        self.f = 0.0
        self.ox = 0.0
        self.oy = 0.0

    def set_transform(self, a, b, c, d, e, f, ox, oy):
        self.a, self.b, self.c, self.d = a, b, c, d
        self.e, self.f = e, f
        self.ox, self.oy = ox, oy

    def page_to_scene(self, px, py):
        """PDF page point → scene point."""
        x = self.a * px + self.c * py + self.e
        y = self.b * px + self.d * py + self.f
        return (x - self.ox, y - self.oy)

    def scene_to_page(self, sx, sy):
        """Scene point → PDF page point."""
        x = sx + self.ox
        y = sy + self.oy
        det = self.a * self.d - self.b * self.c
        if not det:                       # never 0 for real render
            return (0.0, 0.0)
        px = (self.d * (x - self.e) - self.c * (y - self.f)) / det
        py = (-self.b * (x - self.e) + self.a * (y - self.f)) / det
        return (px, py)
