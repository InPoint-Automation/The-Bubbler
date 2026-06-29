# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Lucide SVGs -> recolored QIcons. Ribbon flat-button factory.

import os
import sys

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QToolButton


def _icon_dir():
    try:
        base = __compiled__.containing_dir
        for p in (os.path.join(base, "icons_svg"),
                  os.path.join(base, "bubbler", "icons_svg")):
            if os.path.isdir(p):
                return p
    except NameError:
        pass
    base = getattr(sys, "_MEIPASS", None)
    if base:
        for p in (os.path.join(base, "icons_svg"),
                  os.path.join(base, "bubbler", "icons_svg")):
            if os.path.isdir(p):
                return p
    return os.path.join(os.path.dirname(__file__), "icons_svg")


# Per-icon accents
ICON_COLORS = {
    "save": "#217346", "undo": "#c05621", "fit": "#2b6cb0",
    "zoom_in": "#2b6cb0", "zoom_out": "#2b6cb0", "rotate": "#6b46c1",
    "prev": "#4a5568", "next": "#4a5568", "header": "#b7791f",
    "settings": "#4a5568", "help": "#2b6cb0", "measure": "#c53030",
    "panel": "#2c7a7b", "scan": "#6b46c1",
}

_DEFAULT_COLOR = "#1F3864"
# Fallback accent
ACCENT = _DEFAULT_COLOR
_svg_cache = {}
_icon_cache = {}


def set_accent(color):
    """Set fallback accent, clear icon cache on change."""
    global ACCENT
    if not color or not QColor(color).isValid():
        return
    if color != ACCENT:
        ACCENT = color
        _icon_cache.clear()

# Global UI scale, 1.0 = 100%
UI_SCALE = 1.0


def set_ui_scale(scale):
    """Set icon scale factor, <= 0 means 1.0."""
    global UI_SCALE
    UI_SCALE = float(scale) if scale and scale > 0 else 1.0


_arrow_cache = {}


def spin_arrow_png(direction, color, px=18):
    """Triangle PNG, forward-slashed for QSS."""
    import tempfile
    key = (direction, color, px)
    path = _arrow_cache.get(key)
    if path and os.path.isfile(path.replace("/", os.sep)):
        return path

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF

    scale = 3  # supersample
    s = max(1, int(px)) * scale
    img = QImage(s, s, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    pad = s * 0.32
    cx = s / 2.0
    if direction == "up":
        pts = [QPointF(cx, pad), QPointF(s - pad, s - pad), QPointF(pad, s - pad)]
    else:
        pts = [QPointF(pad, pad), QPointF(s - pad, pad), QPointF(cx, s - pad)]
    p.drawPolygon(QPolygonF(pts))
    p.end()

    path = os.path.join(
        tempfile.gettempdir(),
        "bubbler_spin_%s_%s_%d.png" % (direction, str(color).lstrip("#"), px))
    img.save(path, "PNG")
    path = path.replace(os.sep, "/")
    _arrow_cache[key] = path
    return path


def _renderer(name):
    if name in _svg_cache:
        return _svg_cache[name]
    path = os.path.join(_icon_dir(), name + ".svg")
    r = QSvgRenderer(path) if os.path.isfile(path) else None
    if r is not None and not r.isValid():
        r = None
    _svg_cache[name] = r
    return r


def make_pixmap(name, color=None, px=20, dpr=1.0):
    """Render SVG icon recolored to `color` at `px`."""
    color = color or ICON_COLORS.get(name) or ACCENT
    rend = _renderer(name)
    side = max(1, int(round(px * dpr)))
    img = QImage(side, side, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    if rend is not None:
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        rend.render(p, QRectF(0, 0, side, side))
        # recolor, keep alpha
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(0, 0, side, side, QColor(color))
        p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def make_icon(name, color=None, px=20):
    key = (name, color or "", px)
    hit = _icon_cache.get(key)
    if hit is None:
        hit = QIcon(make_pixmap(name, color, px))
        _icon_cache[key] = hit
    return hit


def icon_button(name, callback=None, tip="", label=None, color=None,
                toggle=False, size=22):
    """Flat tool button, optional caption + toggle."""
    size = max(1, int(round(size * UI_SCALE)))
    b = QToolButton()
    b.setIcon(make_icon(name, color, size))
    b.setIconSize(QSize(size, size))
    b.setAutoRaise(True)
    b.setFocusPolicy(Qt.NoFocus)
    if label:
        b.setText(label)
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    else:
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
    if tip:
        b.setToolTip(tip)
    if toggle:
        b.setCheckable(True)
    if callback is not None:
        b.clicked.connect(lambda _checked=False: callback())
    return b