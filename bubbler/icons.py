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

from .i18n import tr, translate, available_langs


def _icon_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "icons_svg"),
        os.path.join(os.path.dirname(here), "icons_svg"),
        os.path.join(os.path.dirname(os.path.dirname(here)), "icons_svg"),
    ]
    try:
        candidates.append(os.path.join(__compiled__.containing_dir, "icons_svg"))
    except NameError:
        pass
    candidates.append(os.path.join(os.path.dirname(sys.argv[0]), "icons_svg"))
    for p in candidates:
        if os.path.isdir(p):
            return p
    return os.path.join(here, "icons_svg")


ICON_COLORS = {
    "save": "#217346", "undo": "#c05621", "fit": "#2b6cb0",
    "zoom_in": "#2b6cb0", "zoom_out": "#2b6cb0", "rotate": "#6b46c1",
    "prev": "#4a5568", "next": "#4a5568", "header": "#b7791f",
    "settings": "#4a5568", "help": "#2b6cb0", "measure": "#c53030",
    "panel": "#2c7a7b", "scan": "#6b46c1", "calc": "#2b6cb0",
}

_DEFAULT_COLOR = "#1F3864"
ACCENT = _DEFAULT_COLOR
_svg_cache = {}
_icon_cache = {}


def set_accent(color):
    global ACCENT
    if not color or not QColor(color).isValid():
        return
    if color != ACCENT:
        ACCENT = color
        _icon_cache.clear()

UI_SCALE = 1.0


def set_ui_scale(scale):
    global UI_SCALE
    UI_SCALE = float(scale) if scale and scale > 0 else 1.0


_arrow_cache = {}


def spin_arrow_png(direction, color, px=18):
    import tempfile
    key = (direction, color, px)
    path = _arrow_cache.get(key)
    if path and os.path.isfile(path.replace("/", os.sep)):
        return path

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF

    scale = 3
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


_check_cache = {}


def check_png(color, px=14):
    import tempfile
    key = (color, px)
    path = _check_cache.get(key)
    if path and os.path.isfile(path.replace("/", os.sep)):
        return path

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPen

    scale = 3
    s = max(1, int(px)) * scale
    img = QImage(s, s, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(s * 0.16)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QPointF(s * 0.22, s * 0.52),
                    QPointF(s * 0.42, s * 0.72),
                    QPointF(s * 0.78, s * 0.28)])
    p.end()

    path = os.path.join(
        tempfile.gettempdir(),
        "bubbler_check_%s_%d.png" % (str(color).lstrip("#"), px))
    img.save(path, "PNG")
    path = path.replace(os.sep, "/")
    _check_cache[key] = path
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
    color = color or ICON_COLORS.get(name) or ACCENT
    rend = _renderer(name)
    side = max(1, int(round(px * dpr)))
    img = QImage(side, side, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    if rend is not None:
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        rend.render(p, QRectF(0, 0, side, side))
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
    size = max(1, int(round(size * UI_SCALE)))
    b = QToolButton()
    b.setIcon(make_icon(name, color, size))
    b.setIconSize(QSize(size, size))
    b.setAutoRaise(True)
    b.setFocusPolicy(Qt.NoFocus)
    if label:
        b.setText(tr(label))
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        fm = b.fontMetrics()
        texts = [label] + [translate(label, lg)
                           for lg in available_langs() if lg != "en"]
        need = max(fm.horizontalAdvance(t) for t in texts) + 12
        b.setMinimumWidth(max(size + 8, need))
    else:
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
    if tip:
        b.setToolTip(tr(tip))
    if toggle:
        b.setCheckable(True)
    if callback is not None:
        b.clicked.connect(lambda _checked=False: callback())
    return b


def menu_button(name, tip="", label=None, items=(), color=None, size=22):
    """Flat tool button that pops a menu. items: [(icon, text, callback)]."""
    from PySide6.QtWidgets import QMenu
    size = max(1, int(round(size * UI_SCALE)))
    b = QToolButton()
    isz = max(1, size - 3)
    b.setIcon(make_icon(name, color, isz))
    b.setIconSize(QSize(isz, isz))
    b.setAutoRaise(True)
    b.setFocusPolicy(Qt.NoFocus)
    b.setPopupMode(QToolButton.InstantPopup)
    b.setStyleSheet(
        "QToolButton::menu-indicator {"
        " subcontrol-origin: padding; subcontrol-position: bottom center;"
        " width: 18px; height: 8px; }")
    if label:
        b.setText(tr(label))
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        fm = b.fontMetrics()
        texts = [label] + [translate(label, lg)
                           for lg in available_langs() if lg != "en"]
        need = max(fm.horizontalAdvance(t) for t in texts) + 24
        b.setMinimumWidth(max(size + 8, need))
    else:
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
    if tip:
        b.setToolTip(tr(tip))
    m = QMenu(b)
    for ic, text, cb in items:
        act = m.addAction(make_icon(ic, color, 16) if ic else QIcon(), tr(text))
        act.triggered.connect(lambda _c=False, f=cb: f())
    b.setMenu(m)
    b._menu = m
    return b