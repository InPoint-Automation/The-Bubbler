# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Vector renderers for GD&T symbols. Order matches CLASSES.
import math

CLASSES = [
    "diameter", "radius", "position", "flatness", "circularity",
    "cylindricity", "perpendicularity", "parallelism", "angularity",
    "concentricity", "profile_line", "profile_surface",
    "runout_total", "runout_circular", "surface_roughness",
    "depth", "counterbore", "countersink",
]


def _ell(d, b, w, fill):
    d.ellipse(b, outline=fill, width=w)


def diameter(d, x0, y0, x1, y1, w, fill):          # Ø
    _ell(d, (x0, y0, x1, y1), w, fill)
    d.line((x0, y1, x1, y0), fill=fill, width=w)


def radius(d, x0, y0, x1, y1, w, fill):            # R
    h = y1 - y0
    midx = (x0 + x1) / 2
    d.line((x0, y0, x0, y1), fill=fill, width=w)               # stem
    d.arc((x0, y0, x1, y0 + h * 0.55), 270, 90, fill=fill, width=w)
    d.line((x0, y0 + h * 0.55, x1 - w, y0 + h * 0.55), fill=fill, width=w)
    d.line((midx, y0 + h * 0.55, x1, y1), fill=fill, width=w)  # leg


def position(d, x0, y0, x1, y1, w, fill):          # ⌖
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    _ell(d, (x0 + w, y0 + w, x1 - w, y1 - w), w, fill)
    d.line((x0, cy, x1, cy), fill=fill, width=w)
    d.line((cx, y0, cx, y1), fill=fill, width=w)


def flatness(d, x0, y0, x1, y1, w, fill):          # ▱
    sx = (x1 - x0) * 0.25
    d.line((x0 + sx, y0, x1, y0), fill=fill, width=w)
    d.line((x0, y1, x1 - sx, y1), fill=fill, width=w)
    d.line((x0, y1, x0 + sx, y0), fill=fill, width=w)
    d.line((x1 - sx, y1, x1, y0), fill=fill, width=w)


def circularity(d, x0, y0, x1, y1, w, fill):       # ◯
    _ell(d, (x0, y0, x1, y1), w, fill)


def cylindricity(d, x0, y0, x1, y1, w, fill):      # ⌭
    _ell(d, (x0 + (x1 - x0) * 0.2, y0, x1 - (x1 - x0) * 0.2, y1), w, fill)
    d.line((x0, y1, x0 + (x1 - x0) * 0.45, y0), fill=fill, width=w)
    d.line((x1 - (x1 - x0) * 0.45, y1, x1, y0), fill=fill, width=w)


def perpendicularity(d, x0, y0, x1, y1, w, fill):  # ⟂
    cx = (x0 + x1) / 2
    d.line((cx, y0, cx, y1), fill=fill, width=w)
    d.line((x0, y1, x1, y1), fill=fill, width=w)


def parallelism(d, x0, y0, x1, y1, w, fill):       # ∥
    dx = (x1 - x0) * 0.3
    d.line((x0 + dx, y1, x0 + dx + (x1 - x0) * 0.4, y0), fill=fill, width=w)
    d.line((x1 - dx - (x1 - x0) * 0.4, y1, x1 - dx, y0), fill=fill, width=w)


def angularity(d, x0, y0, x1, y1, w, fill):        # ∠
    d.line((x0, y1, x1, y1), fill=fill, width=w)
    d.line((x0, y1, x1, y0), fill=fill, width=w)


def concentricity(d, x0, y0, x1, y1, w, fill):     # ◎
    _ell(d, (x0, y0, x1, y1), w, fill)
    ix, iy = (x1 - x0) * 0.28, (y1 - y0) * 0.28
    _ell(d, (x0 + ix, y0 + iy, x1 - ix, y1 - iy), w, fill)


def profile_line(d, x0, y0, x1, y1, w, fill):      # ⌒
    d.arc((x0, y0, x1, y1 + (y1 - y0)), 180, 360, fill=fill, width=w)


def profile_surface(d, x0, y0, x1, y1, w, fill):   # ⌓
    d.arc((x0, y0, x1, y1 + (y1 - y0)), 180, 360, fill=fill, width=w)
    d.line((x0, y1, x1, y1), fill=fill, width=w)


def _arrow(d, x0, y0, x1, y1, w, fill, n):
    """n stacked slanted arrows."""
    step = (x1 - x0) / (n + 1)
    for k in range(n):
        ax = x0 + step * (k + 1)
        d.line((ax, y1, ax + step * 0.7, y0), fill=fill, width=w)
        d.line((ax + step * 0.7, y0, ax + step * 0.7 - w * 2,
                y0 + w * 2), fill=fill, width=w)
        d.line((ax + step * 0.7, y0, ax + step * 0.7 + w * 2,
                y0 + w * 2), fill=fill, width=w)


def runout_circular(d, x0, y0, x1, y1, w, fill):   # ↗
    _arrow(d, x0, y0, x1, y1, w, fill, 1)


def runout_total(d, x0, y0, x1, y1, w, fill):      # ⌰
    _arrow(d, x0, y0, x1, y1, w, fill, 2)


def surface_roughness(d, x0, y0, x1, y1, w, fill):  # √  texture tick
    vx = x0 + (x1 - x0) * 0.32
    d.line((x0, y1 - (y1 - y0) * 0.4, vx, y1), fill=fill, width=w)
    d.line((vx, y1, x1, y0), fill=fill, width=w)


def depth(d, x0, y0, x1, y1, w, fill):             # ↧
    cx = (x0 + x1) / 2
    ah = (x1 - x0) * 0.22
    d.line((x0, y0, x1, y0), fill=fill, width=w)    # top stroke
    d.line((cx, y0, cx, y1), fill=fill, width=w)    # shaft
    d.line((cx, y1, cx - ah, y1 - ah), fill=fill, width=w)   # arrowhead
    d.line((cx, y1, cx + ah, y1 - ah), fill=fill, width=w)


def counterbore(d, x0, y0, x1, y1, w, fill):       # ⌴
    d.line((x0, y0, x0, y1), fill=fill, width=w)
    d.line((x0, y1, x1, y1), fill=fill, width=w)
    d.line((x1, y1, x1, y0), fill=fill, width=w)


def countersink(d, x0, y0, x1, y1, w, fill):       # ⌵
    cx = (x0 + x1) / 2
    d.line((x0, y0, cx, y1), fill=fill, width=w)
    d.line((cx, y1, x1, y0), fill=fill, width=w)


RENDERERS = {
    "diameter": diameter, "radius": radius, "position": position,
    "flatness": flatness, "circularity": circularity,
    "cylindricity": cylindricity, "perpendicularity": perpendicularity,
    "parallelism": parallelism, "angularity": angularity,
    "concentricity": concentricity, "profile_line": profile_line,
    "profile_surface": profile_surface, "runout_total": runout_total,
    "runout_circular": runout_circular, "surface_roughness": surface_roughness,
    "depth": depth, "counterbore": counterbore, "countersink": countersink,
}
assert list(RENDERERS) == CLASSES
