# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Synthesise YOLO-OBB GD&T symbol dataset. No manual labels.
import argparse
import glob
import io
import math
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache

import numpy as np                                          # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageFilter    # noqa: E402

from draw_symbols import CLASSES, RENDERERS    # noqa: E402

TILE = 640
WHITE = 255
INK = (30, 30, 30)

_STYLE = "iso"
_SAMPLE_ASME = False


def _resolve_sample_style(rnd):
    global _SAMPLE_ASME
    if _STYLE == "mixed":
        _SAMPLE_ASME = rnd.random() < 0.5
    else:
        _SAMPLE_ASME = _STYLE == "asme"
    return _SAMPLE_ASME

_FONT_NAMES = ("osifont.ttf", "ISOCPEUR.ttf", "isocpeur.ttf", "romans.ttf",
               "DejaVuSans.ttf", "Arial.ttf", "LiberationSans-Regular.ttf")
_FONT_FILES = []
_GDT_FONT_FILES = []
_BG_FILES = []

_GDT_FONT_HINTS = ("amgdt", "gdt")
_GDT_GLYPH = {
    "a": "angularity", "b": "perpendicularity", "c": "flatness",
    "d": "profile_surface", "e": "circularity", "f": "parallelism",
    "g": "cylindricity", "h": "runout_circular", "j": "position",
    "k": "profile_line", "n": "diameter", "r": "concentricity",
    "t": "runout_total", "v": "countersink", "x": "depth",
}
_CLASS_TO_GDT = {v: k for k, v in _GDT_GLYPH.items()}
_GDT_GLYPH_P = 0.4

_REPO_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fonts")


@lru_cache(maxsize=512)
def _truetype(name, size):
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return None


def _font(size, rnd=None):
    cands = list(_FONT_FILES) + list(_FONT_NAMES)
    if rnd is not None and _FONT_FILES:
        cands = [rnd.choice(_FONT_FILES)] + cands
    for name in cands:
        f = _truetype(name, size)
        if f is not None:
            return f
    return ImageFont.load_default()


def _load_font_dir(path):
    for p in sorted(glob.glob(os.path.join(path, "*.ttf"))):
        b = os.path.basename(p).lower()
        pool = _GDT_FONT_FILES if any(h in b for h in _GDT_FONT_HINTS) \
            else _FONT_FILES
        if p not in pool:
            pool.append(p)


SS = 3
INLINE = ("diameter", "radius", "depth", "counterbore", "countersink")


def _ink(rnd):
    v = rnd.randint(15, 70)
    return (v, v, v, 255)


def _clutter(d, rnd):
    for _ in range(rnd.randint(6, 16)):
        x0, y0 = rnd.randint(0, TILE), rnd.randint(0, TILE)
        x1, y1 = rnd.randint(0, TILE), rnd.randint(0, TILE)
        d.line((x0, y0, x1, y1), fill=INK, width=rnd.choice((1, 1, 2)))
    for _ in range(rnd.randint(4, 10)):
        x, y = rnd.randint(0, TILE - 60), rnd.randint(0, TILE - 20)
        if _SAMPLE_ASME and rnd.random() < 0.6:
            txt = rnd.choice((
                _thread_asme(rnd), _frac_inch(rnd), _drill_size_asme(rnd),
                _finish_uin(rnd), _dim_num_asme(rnd), _dual_dim_asme(rnd),
                "%s %s" % (_dia_word(rnd), _dim_num_asme(rnd)),
                "%s%s" % (rnd.choice(_R_WORDS), _dim_num_asme(rnd, 0.05, 2)),
                "%s %s" % (_dim_num_asme(rnd), rnd.choice(_DEEP_WORDS))))
        else:
            txt = rnd.choice((
                "12.5", "12,5", "Ø8", "25", "R3", "0.05", "8H7", "Ø10 H7",
                "100", "45°", "30°", "M6", "M8x1.0", "2X", "4x", "±0,1",
                "25,4", ".531", "1.250", "SR5", "C1", "2x45°", "Rz 16",
                "A", "B", "(20)", "[35]", "12±0.2"))
        d.text((x, y), txt, fill=INK, font=_font(rnd.randint(13, 24), rnd))
    for _ in range(rnd.randint(0, 3)):
        x, y = rnd.randint(0, TILE - 80), rnd.randint(0, TILE - 30)
        d.rectangle((x, y, x + rnd.randint(30, 80), y + rnd.randint(16, 28)),
                    outline=INK, width=1)
    for _ in range(rnd.randint(2, 6)):
        x, y = rnd.randint(10, TILE - 60), rnd.randint(10, TILE - 60)
        r = rnd.randint(10, 40)
        kind = rnd.random()
        if kind < 0.4:
            d.ellipse((x, y, x + r, y + r), outline=INK, width=1)
            if rnd.random() < 0.5:
                cx, cy = x + r // 2, y + r // 2
                d.line((cx - r, cy, cx + r, cy), fill=INK, width=1)
                d.line((cx, cy - r, cx, cy + r), fill=INK, width=1)
        elif kind < 0.7:
            d.line((x, y, x + r * 2, y), fill=INK, width=1)
            d.polygon((x, y, x + 7, y - 3, x + 7, y + 3), fill=INK)
        elif kind < 0.85:
            for a in range(0, 360, 60):
                bx = x + r + int(r * 0.8 * np.cos(np.radians(a)))
                by = y + r + int(r * 0.8 * np.sin(np.radians(a)))
                d.ellipse((bx - 3, by - 3, bx + 3, by + 3), outline=INK, width=1)
        else:
            d.text((x, y), rnd.choice(("O", "0", "L", "//", "T")),
                   fill=INK, font=_font(rnd.randint(16, 30), rnd))


def _render_tile(cls, rnd):
    r = rnd.random()
    if r < 0.18:
        size = rnd.randint(10, 18)
    elif r < 0.85:
        size = rnd.randint(18, 58)
    else:
        size = rnd.randint(58, 112)
    s, pad = size * SS, 6 * SS
    side = s + 2 * pad
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    ink = _ink(rnd)
    w = rnd.choice((2, 3)) * SS
    if cls == "radius" and rnd.random() < 0.85:
        _draw_glyph(td, "R", pad, s, ink, rnd)
    elif cls == "diameter" and rnd.random() < 0.5:
        _draw_glyph(td, "Ø", pad, s, ink, rnd)
    elif not _try_gdt_glyph(td, cls, pad, s, ink, rnd):
        RENDERERS[cls](td, pad, pad, pad + s, pad + s, w, ink)
    tile = tile.resize((side // SS, side // SS), Image.LANCZOS)
    return tile.crop(tile.getbbox()) if tile.getbbox() else tile


def _draw_glyph(td, ch, pad, s, ink, rnd=None):
    td.text((pad, pad), ch, fill=ink, font=_font(int(s * 1.05), rnd))


def _gdt_font(size, rnd):
    if not _GDT_FONT_FILES:
        return None
    return _truetype(rnd.choice(_GDT_FONT_FILES), int(size))


def _try_gdt_glyph(td, cls, pad, s, ink, rnd):
    ch = _CLASS_TO_GDT.get(cls)
    if ch is None or rnd.random() >= _GDT_GLYPH_P:
        return False
    f = _gdt_font(int(s * 1.05), rnd)
    if f is None:
        return False
    td.text((pad, pad), ch, fill=ink, font=f)
    return True


def _rotate_img(img, deg):
    rt = img.rotate(deg, expand=True, resample=Image.BICUBIC)
    w, h = img.size
    ow, oh = rt.size
    rad = math.radians(deg)
    cos, sin = math.cos(rad), math.sin(rad)
    cx, cy, ocx, ocy = w / 2.0, h / 2.0, ow / 2.0, oh / 2.0

    def mp(p):
        vx, vy = p[0] - cx, p[1] - cy
        return (cos * vx + sin * vy + ocx, -sin * vx + cos * vy + ocy)
    return rt, mp


def _pick_angle(rnd):
    r = rnd.random()
    if r < 0.42:
        return 0.0
    if r < 0.68:
        return rnd.uniform(-22, 22)
    if r < 0.80:
        return rnd.uniform(-50, 50)
    if r < 0.92:
        return rnd.choice((90.0, -90.0)) + rnd.uniform(-6, 6)
    return rnd.uniform(-180, 180)


def _quad_after_paste(corners, mp, px, py):
    return [(mp(c)[0] + px, mp(c)[1] + py) for c in corners]


def _inline(base, tile, rnd):
    deg = _pick_angle(rnd)
    rt, mp = _rotate_img(tile, deg)
    pad_r = 90 if deg == 0 else 4
    px = rnd.randint(2, max(3, TILE - rt.width - pad_r))
    py = rnd.randint(2, max(3, TILE - rt.height - 2))
    base.paste(rt, (px, py), rt)
    w, h = tile.size
    if deg == 0 and rnd.random() < 0.85:
        d = ImageDraw.Draw(base)
        if _SAMPLE_ASME:
            val = rnd.choice((
                _dim_num_asme(rnd), _dual_dim_asme(rnd), _frac_inch(rnd),
                "%s DEEP" % _dim_num_asme(rnd), ".250 THRU",
                _finish_uin(rnd), _thread_asme(rnd)))
        else:
            val = rnd.choice(("6.6", "6,6", "12", "25.4", "8", "0.1", "3.2",
                              "10 H7", "5 ±0,05", "0,05 A", "2,90", ".25",
                              "12,5 THRU", "90°"))
        d.text((px + rt.width + 2, py + int(h * 0.12)), val,
               fill=_ink(rnd), font=_font(int(h * 0.8), rnd))
    return _quad_after_paste([(0, 0), (w, 0), (w, h), (0, h)], mp, px, py)


def _frame(base, tile, rnd):
    meas = ImageDraw.Draw(base)
    ink = _ink(rnd)
    tw, th = tile.size
    H = int(th * 1.5)
    font = _font(int(th * 0.8), rnd)
    c1 = tw + H // 3
    mod = rnd.choice(("", "", "(M)", "(L)", "(P)"))
    # keep RNG order: Ø-test then value (matches ISO byte-stream)
    dia = "Ø" if rnd.random() < 0.4 else ""
    tval = _dim_num_asme(rnd, 0.001, 0.03) if _SAMPLE_ASME \
        else rnd.choice(("0.1", "0.05", "0.2", "0.02", "0.5", "0.010"))
    tol = dia + tval + mod
    c2 = int(meas.textlength(tol, font=font)) + H // 2
    datums = []
    for _ in range(rnd.randint(0, 3)):
        if rnd.random() < 0.7:
            datums.append(rnd.choice("ABCD") + rnd.choice(("", "", "(M)", "(L)")))
    cells = [c1, c2] + [max(H, int(meas.textlength(s, font=font)) + H // 2)
                        for s in datums]
    W = sum(cells)
    m = H // 2 + 4
    layer = Image.new("RGBA", (W + 2 * m, H + 2 * m), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ox = oy = m
    ld.rectangle((ox, oy, ox + W, oy + H), outline=ink, width=rnd.choice((1, 2)))
    sx = ox + (c1 - tw) // 2
    sy = oy + (H - th) // 2
    layer.paste(tile, (sx, sy), tile)
    x = ox + c1
    ld.line((x, oy, x, oy + H), fill=ink, width=1)
    ld.text((x + H // 5, oy + (H - th) // 2), tol, fill=ink, font=font)
    x += c2
    for k, dt in enumerate(datums):
        ld.line((x, oy, x, oy + H), fill=ink, width=1)
        ld.text((x + H // 3, oy + (H - th) // 2), dt, fill=ink, font=font)
        x += cells[2 + k]
    if rnd.random() < 0.15:
        ld.ellipse((ox - H // 3, oy - H // 3, ox, oy), outline=ink, width=1)
    if rnd.random() < 0.3:
        tx, ty = ox + rnd.randint(0, W), oy + H
        ld.polygon((tx, ty, tx - 5, ty + 8, tx + 5, ty + 8), fill=ink)
        ld.line((tx, ty + 8, tx, ty + 16), fill=ink, width=1)
    deg = _pick_angle(rnd)
    rt, mp = _rotate_img(layer, deg)
    if rt.width >= TILE - 4 or rt.height >= TILE - 4:
        return _inline(base, tile, rnd)
    px = rnd.randint(2, max(3, TILE - rt.width - 2))
    py = rnd.randint(2, max(3, TILE - rt.height - 2))
    base.paste(rt, (px, py), rt)
    corners = [(sx, sy), (sx + tw, sy), (sx + tw, sy + th), (sx, sy + th)]
    return _quad_after_paste(corners, mp, px, py)


_THRU_WORDS = ("DURCH ALLES", "THRU ALL", "THRU", "THROUGH", "DURCHGANGSLOCH",
               "DURCHGEHEND", "DURCHBOHREN", "Durchbohren", "PRZEJŚCIOWY",
               "PRZELOTOWY", "DRILL THRU")
_TOP_WORDS = ("", "", "", ", Oben", ", Top", ", od góry", ", NEAR SIDE",
              ", FAR SIDE")
_CSK_ANGLES = ("60", "82", "90", "90", "100", "120")
_FITS_HOLE = ("H7", "H8", "H9", "G7", "K7", "N7", "P7", "F8")
_THREADS = ("M1.6", "M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10",
            "M12", "M16", "M20")
_TCLASS = ("6H", "6G", "7H", "4H5H", "6H", "6H")
_COUNTS = ("", "2", "2", "3", "4", "4", "6", "8", "10", "12", "15", "20")
_DATUMS = ("A", "A B", "A B C", "A|B|C", "B A", "A B(M)")


# All values are as-drawn: NO ISO->inch conversion is performed anywhere.
_UNC_UNF = ("1/4-20 UNC", "1/4-28 UNF", "5/16-18 UNC", "5/16-24 UNF",
            "3/8-16 UNC", "3/8-24 UNF", "1/2-13 UNC", "1/2-20 UNF",
            "5/8-11 UNC", "3/4-10 UNC", "#6-32 UNC", "#8-32 UNC",
            "#10-24 UNC", "#10-32 UNF", "10-32 UNF", "1-8 UNC")
_NPT = ("1/8-27 NPT", "1/4-18 NPT", "3/8-18 NPT", "1/2-14 NPT",
        "3/4-14 NPT", "1/8 NPT", "1/4 NPT")
_FRAC_INCH = ("1/2", "1/4", "3/8", "5/8", "3/4", "7/8", "1-1/2", "1-1/4",
              "2-1/2", "27/64", "13/32", "11/16", "9/16", "1/16", "3/16")
_DRILL_SIZE = ("#7", "#21", "#29", "#43", "F", "R", "U", "Q", "#3", "#36",
               ".201", ".257", ".332", ".147")
_DIA_WORDS = ("DIA", "DIA.", "Ø")
_R_WORDS = ("R", "R.", "RAD", "RAD.")
_DEEP_WORDS = ("DEEP", "DP", "DP.", "↓")
_DRILL_WORDS = ("DRILL", "DRILL THRU", "REAM", "C'BORE", "C'SINK", "SPOTFACE")


def _thread_asme(rnd):
    r = rnd.random()
    if r < 0.75:
        return rnd.choice(_UNC_UNF)
    return rnd.choice(_NPT)


def _frac_inch(rnd):
    return rnd.choice(_FRAC_INCH)


def _drill_size_asme(rnd):
    return rnd.choice(_DRILL_SIZE)


def _dim_num_asme(rnd, lo=0.05, hi=6.0):
    dp = rnd.choice((3, 3, 3, 4))
    s = ("%%.%df" % dp) % rnd.uniform(lo, hi)
    if s.startswith("0."):
        s = s[1:]
    return s


def _finish_uin(rnd):
    v = rnd.choice((16, 32, 63, 125, 250, 8, 500))
    unit = rnd.choice(("uin", "uin", "µin", "microinch"))
    return "%d %s" % (v, unit)


def _dual_dim_asme(rnd):
    inch = _dim_num_asme(rnd, 0.1, 4.0)
    mm = _num(rnd, 3, 100, rnd.choice((1, 2)))
    return "%s [%s]" % (inch, mm)


def _dia_word(rnd):
    return rnd.choice(_DIA_WORDS)


def _num(rnd, lo, hi, dp=2):
    s = ("%%.%df" % dp) % rnd.uniform(lo, hi)
    drop_p = 0.85 if _SAMPLE_ASME else 0.12
    if rnd.random() < drop_p and s.startswith("0."):
        s = s[1:]
    if _SAMPLE_ASME:
        return s
    return s.replace(".", ",") if rnd.random() < 0.5 else s


def _count_prefix(rnd):
    n = rnd.choice(_COUNTS)
    if not n:
        return ""
    sep = rnd.choice((" x ", " X ", "x ", " × ", "× ", "X"))
    return "%s%s" % (n, sep)


def _csk_line(rnd, d):
    ang = rnd.choice(_CSK_ANGLES)
    note = rnd.choice(_TOP_WORDS)
    sep = rnd.choice((" X ", " x ", " × ", "X"))
    return [("s", "countersink"), ("t", " "), ("s", "diameter"),
            ("t", " %s%s%s°%s" % (d, sep, ang, note))]


def _cbore_line(rnd, d, with_depth=True):
    toks = [("s", "counterbore"), ("t", " "), ("s", "diameter"),
            ("t", " %s" % d)]
    if with_depth:
        toks += [("t", " "), ("s", "depth"),
                 ("t", " %s" % _num(rnd, 2, 12, rnd.choice((0, 2))))]
    return toks


def _drill_line(rnd, d):
    if _SAMPLE_ASME and rnd.random() < 0.45:
        toks = [("t", _count_prefix(rnd)), ("t", "%s " % _drill_size_asme(rnd)),
                ("s", "diameter"), ("t", " %s" % _dim_num_asme(rnd, 0.1, 1.5))]
    else:
        toks = [("t", _count_prefix(rnd)), ("s", "diameter"), ("t", " %s" % d)]
    r = rnd.random()
    if r < 0.5:
        toks.append(("t", " %s" % rnd.choice(_THRU_WORDS)))
    elif r < 0.7:
        toks.append(("t", " %s" % rnd.choice(_FITS_HOLE)))
    return toks


def _gdt_line(rnd):
    return [("s", "position"), ("t", " "), ("s", "diameter"),
            ("t", " %s %s" % (_num(rnd, 0.05, 0.5, rnd.choice((2, 3))),
                              rnd.choice(_DATUMS)))]


def _callout_lines(rnd):
    d1, d2, d3 = (_num(rnd, 1.5, 14, rnd.choice((1, 2))) for _ in range(3))
    kind = rnd.random()
    if kind < 0.26:
        lines = [_drill_line(rnd, d1), _cbore_line(rnd, d2),
                 _csk_line(rnd, d3)]
    elif kind < 0.48:
        if _SAMPLE_ASME:
            base = "%s%s" % (_count_prefix(rnd), _thread_asme(rnd))
        else:
            base = "%s%s - %s" % (_count_prefix(rnd),
                                  rnd.choice(_THREADS), rnd.choice(_TCLASS))
        if rnd.random() < 0.35:
            base += " %s" % rnd.choice(_THRU_WORDS)
        thr = [("t", base)]
        if rnd.random() < 0.55:
            thr += [("t", " "), ("s", "depth"),
                    ("t", " %s" % _num(rnd, 3, 16, 0))]
        lines = [_drill_line(rnd, d1)]
        if rnd.random() < 0.6:
            lines[0] += [("t", " "), ("s", "depth"),
                         ("t", " %s" % _num(rnd, 4, 18, rnd.choice((0, 2))))]
        lines.append(thr)
    elif kind < 0.64:
        dl = _drill_line(rnd, d1)
        if rnd.random() < 0.4:
            dl += [("t", " "), ("s", "depth"),
                   ("t", " %s" % _num(rnd, 3, 14, rnd.choice((0, 2))))]
        lines = [dl, _csk_line(rnd, d2)]
    elif kind < 0.78:
        lines = [_drill_line(rnd, d1)]
    else:
        lines = [_drill_line(rnd, d1),
                 _cbore_line(rnd, d2, with_depth=rnd.random() < 0.8)]
    if rnd.random() < 0.22:
        lines.append(_gdt_line(rnd))
    return lines


def _glyph_tile(cls, size, rnd):
    s, pad = int(size) * SS, 3 * SS
    side = s + 2 * pad
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    ink = _ink(rnd)
    w = rnd.choice((2, 3)) * SS
    if cls == "radius" and rnd.random() < 0.85:
        _draw_glyph(td, "R", pad, s, ink, rnd)
    elif cls == "diameter" and rnd.random() < 0.6:
        _draw_glyph(td, "Ø", pad, s, ink, rnd)
    elif not _try_gdt_glyph(td, cls, pad, s, ink, rnd):
        RENDERERS[cls](td, pad, pad, pad + s, pad + s, w, ink)
    tile = tile.resize((side // SS, side // SS), Image.LANCZOS)
    bb = tile.getbbox()
    return tile.crop(bb) if bb else tile


def _callout_block(base, rnd):
    lines = _callout_lines(rnd)
    th = rnd.randint(13, 26)
    font = _font(int(th * 1.25), rnd)
    gap = max(2, th // 5)
    lh = int(th * 1.7)
    m = th
    md = ImageDraw.Draw(base)
    rows = []
    maxw = 0
    for line in lines:
        items, x = [], 0
        for kind, val in line:
            if kind == "t":
                w = int(md.textlength(val, font=font))
                items.append(("t", val, x, w))
                x += w
            else:
                tile = _glyph_tile(val, th, rnd)
                items.append(("s", val, x, tile))
                x += tile.width + gap
        rows.append(items)
        maxw = max(maxw, x)
    W = maxw + 2 * m
    H = lh * len(rows) + 2 * m
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ink = _ink(rnd)
    quads = []
    indent = rnd.random() < 0.5
    for r, items in enumerate(rows):
        oy = m + r * lh
        ox = m + (rnd.randint(th, 3 * th) if (indent and r > 0) else 0)
        for kind, val, x, payload in items:
            if kind == "t":
                ld.text((ox + x, oy), val, fill=ink, font=font)
            else:
                tile = payload
                ty = oy + (th - tile.height) // 2 + th // 6
                layer.paste(tile, (ox + x, ty), tile)
                quads.append((CLASSES.index(val),
                              [(ox + x, ty), (ox + x + tile.width, ty),
                               (ox + x + tile.width, ty + tile.height),
                               (ox + x, ty + tile.height)]))
    if rnd.random() < 0.7:
        ly = m + lh * len(rows) - lh // 3
        ld.line((m, ly, m + maxw, ly), fill=ink, width=1)
    deg = 0.0 if rnd.random() < 0.7 else rnd.uniform(-12, 12)
    rt, mp = _rotate_img(layer, deg)
    if rt.width >= TILE - 4 or rt.height >= TILE - 4:
        return []
    px = rnd.randint(2, max(3, TILE - rt.width - 2))
    py = rnd.randint(2, max(3, TILE - rt.height - 2))
    base.paste(rt, (px, py), rt)
    out = []
    for ci, corners in quads:
        out.append((ci, _quad_after_paste(corners, mp, px, py)))
    return out


def _place_symbol(base, cls, rnd):
    tile = _render_tile(cls, rnd)
    if tile.width < 2 or tile.height < 2:
        return None
    if cls in INLINE or rnd.random() < 0.35:
        return _inline(base, tile, rnd)
    return _frame(base, tile, rnd)


_BG_CACHE = {}


def _load_bg(path):
    im = _BG_CACHE.get(path)
    if im is None:
        im = Image.open(path).convert("RGB")
        if len(_BG_CACHE) > 24:
            _BG_CACHE.clear()
        _BG_CACHE[path] = im
    return im


def _background(rnd):
    if _BG_FILES and rnd.random() < 0.6:
        try:
            src = _load_bg(rnd.choice(_BG_FILES))
            if src.width > TILE and src.height > TILE:
                x = rnd.randint(0, src.width - TILE)
                y = rnd.randint(0, src.height - TILE)
                return src.crop((x, y, x + TILE, y + TILE))
            return src.resize((TILE, TILE))
        except Exception:
            pass
    bg = rnd.randint(248, 255)
    return Image.new("RGB", (TILE, TILE), (bg, bg, bg))


def _jpeg(img, quality):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=int(quality))
    buf.seek(0)
    return Image.open(buf).convert("RGB")


# Use ONLY photometric ink/paper/post effects -- NEVER geometric ones (Folding,
# Geometric, PageBorder, Bindings) because they move pixels but not our fixed
# YOLO labels.
_AUGRAPHY_P = float(os.environ.get("BUBBLER_AUGRAPHY_P", "0.6"))
_AUG_PIPE = None
_AUG_TRIED = False


def _augraphy_pipe():
    global _AUG_PIPE, _AUG_TRIED
    if _AUG_TRIED:
        return _AUG_PIPE
    _AUG_TRIED = True
    if _AUGRAPHY_P <= 0:
        return None
    try:
        import augraphy as ag
        ink = [ag.OneOf([ag.InkBleed(p=1), ag.Letterpress(p=1),
                         ag.LowInkPeriodicLines(p=1)], p=0.6),
               ag.BleedThrough(p=0.3),
               ag.OneOf([ag.DirtyRollers(p=1), ag.DirtyDrum(p=1)], p=0.3)]
        paper = [ag.OneOf([ag.NoiseTexturize(p=1),
                           ag.BrightnessTexturize(p=1)], p=0.6),
                 ag.LightingGradient(p=0.3),
                 ag.Brightness(p=0.3), ag.SubtleNoise(p=0.4)]
        post = [ag.OneOf([ag.BadPhotoCopy(p=1), ag.Faxify(p=1),
                          ag.Dithering(p=1)], p=0.4),
                ag.Jpeg(p=0.6)]
        _AUG_PIPE = ag.AugraphyPipeline(ink_phase=ink, paper_phase=paper,
                                        post_phase=post)
    except ImportError:
        _AUG_PIPE = None
    except Exception as e:
        print("bubbler: Augraphy pipeline build failed (%s); using basic "
              "degrade" % e, file=sys.stderr)
        _AUG_PIPE = None
    return _AUG_PIPE


def _degrade(img, rnd):
    pipe = _augraphy_pipe() if rnd.random() < _AUGRAPHY_P else None
    if pipe is not None:
        try:
            out = pipe(np.asarray(img.convert("RGB")))
            if isinstance(out, dict):
                out = out.get("output", out.get("result"))
            arr = np.asarray(out)
            if arr.ndim == 2:
                arr = np.stack([arr] * 3, -1)
            if arr.shape[:2] == (TILE, TILE):   # reject any geometric resize
                return Image.fromarray(arr[..., :3].astype("uint8"))
        except Exception:
            pass
    return _degrade_basic(img, rnd)


def _degrade_basic(img, rnd):
    if rnd.random() < 0.5:
        arr = np.asarray(img).astype("float32")
        lo = rnd.uniform(0, 40)
        arr = lo + arr * (rnd.uniform(0.7, 1.0))
        img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    if rnd.random() < 0.3:
        arr = np.asarray(img).astype("float32")
        h = max(8, TILE // 16)
        tex = np.random.normal(1.0, rnd.uniform(0.02, 0.06), (h, h, 1))
        tex = np.asarray(Image.fromarray(
            np.clip(tex * 255, 0, 255).astype("uint8")[:, :, 0]
        ).resize((TILE, TILE), Image.BILINEAR)).astype("float32")[..., None] / 255.0
        img = Image.fromarray(np.clip(arr * tex, 0, 255).astype("uint8"))
    if rnd.random() < 0.6:
        arr = np.asarray(img).astype("float32")
        arr += np.random.normal(0, rnd.uniform(3, 14), arr.shape)
        img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    if rnd.random() < 0.15:
        arr = np.asarray(img).copy()
        n = rnd.randint(20, 200)
        ys = np.random.randint(0, TILE, n)
        xs = np.random.randint(0, TILE, n)
        arr[ys, xs] = 0 if rnd.random() < 0.5 else 255
        img = Image.fromarray(arr)
    if rnd.random() < 0.4:
        img = img.filter(ImageFilter.GaussianBlur(rnd.uniform(0.3, 1.0)))
    if rnd.random() < 0.7:
        q = rnd.randint(18, 80)
        if rnd.random() < 0.3:
            q = rnd.randint(8, 30)
        img = _jpeg(img, q)
        if rnd.random() < 0.25:
            img = _jpeg(img, rnd.randint(15, 45))
    if rnd.random() < 0.12:
        f = rnd.uniform(0.45, 0.8)
        small = img.resize((max(1, int(TILE * f)),) * 2, Image.BILINEAR)
        img = small.resize((TILE, TILE), Image.BILINEAR)
    if rnd.random() < 0.05:
        arr = 255 - np.asarray(img)
        arr[:, :, 2] = np.clip(arr[:, :, 2].astype(int) + 80, 0, 255)
        img = Image.fromarray(arr.astype("uint8"))
    return img


def _crop_negatives(base, rnd):
    for _ in range(rnd.randint(0, 3)):
        cls = CLASSES[rnd.randrange(len(CLASSES))]
        rt, _mp = _rotate_img(_render_tile(cls, rnd), _pick_angle(rnd))
        w, h = rt.size
        if w >= TILE or h >= TILE:
            continue
        edge = rnd.randrange(4)
        if edge == 0:
            px, py = rnd.randint(-int(w * 0.85), -int(w * 0.4)), rnd.randint(0, TILE - h)
        elif edge == 1:
            px, py = rnd.randint(TILE - int(w * 0.6), TILE - int(w * 0.15)), rnd.randint(0, TILE - h)
        elif edge == 2:
            px, py = rnd.randint(0, TILE - w), rnd.randint(-int(h * 0.85), -int(h * 0.4))
        else:
            px, py = rnd.randint(0, TILE - w), rnd.randint(TILE - int(h * 0.6), TILE - int(h * 0.15))
        base.paste(rt, (px, py), rt)


def _gen_one(rnd):
    _resolve_sample_style(rnd)
    img = _background(rnd).copy()
    d = ImageDraw.Draw(img)
    _clutter(d, rnd)
    labels = []
    placed = []
    if rnd.random() < 0.4:
        placed.extend(_callout_block(img, rnd))
    for _ in range(rnd.randint(1, 4)):
        ci = rnd.randrange(len(CLASSES))
        quad = _place_symbol(img, CLASSES[ci], rnd)
        if quad is not None:
            placed.append((ci, quad))
    for ci, quad in placed:
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        if max(xs) - min(xs) < 2 or max(ys) - min(ys) < 2:
            continue
        labels.append((ci, quad))
    _crop_negatives(img, rnd)
    img = _degrade(img, rnd)
    return img, labels


def _gen_task(job):
    split, i, idir, ldir, seed = job
    rnd = random.Random((seed * 1000003) ^ (i * 2654435761 & 0xFFFFFFFF) ^
                        (hash(split) & 0xFFFFFFFF))
    np.random.seed((seed * 7919 + i) % (2 ** 32 - 1))
    img, labels = _gen_one(rnd)
    stem = "%s_%06d" % (split, i)
    img.save(os.path.join(idir, stem + ".png"))
    with open(os.path.join(ldir, stem + ".txt"), "w") as f:
        for ci, quad in labels:
            coords = []
            for px, py in quad:
                coords.append("%.6f" % min(1.0, max(0.0, px / TILE)))
                coords.append("%.6f" % min(1.0, max(0.0, py / TILE)))
            f.write("%d %s\n" % (ci, " ".join(coords)))


def _init_worker(bg_files, font_files, gdt_font_files, style="iso"):
    global _BG_FILES, _FONT_FILES, _GDT_FONT_FILES, _STYLE
    _BG_FILES, _FONT_FILES = bg_files, font_files
    _GDT_FONT_FILES = gdt_font_files
    _STYLE = style


def _write_serial(split, jobs):
    n = len(jobs)
    for j, job in enumerate(jobs):
        _gen_task(job)
        if (j + 1) % 500 == 0:
            print("  %s %d/%d" % (split, j + 1, n))


def _write(split, n, out, seed, workers):
    idir = os.path.join(out, "images", split)
    ldir = os.path.join(out, "labels", split)
    os.makedirs(idir, exist_ok=True)
    os.makedirs(ldir, exist_ok=True)
    jobs = [(split, i, idir, ldir, seed) for i in range(n)]
    if workers <= 1:
        _write_serial(split, jobs)
        return
    import multiprocessing as mp
    try:
        ctx = mp.get_context("fork")
    except ValueError:
        ctx = None
    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx,
                                 initializer=_init_worker,
                                 initargs=(_BG_FILES, _FONT_FILES,
                                           _GDT_FONT_FILES, _STYLE)) as ex:
            done = 0
            for fut in as_completed([ex.submit(_gen_task, j) for j in jobs]):
                fut.result()
                done += 1
                if done % 500 == 0:
                    print("  %s %d/%d" % (split, done, n))
    except Exception as e:
        print("  parallel pool failed (%s); falling back to serial" % e)
        _write_serial(split, jobs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("train", "data", "symbols"))
    ap.add_argument("--n", type=int, default=4000, help="train images")
    ap.add_argument("--val", type=int, default=0,
                    help="val images (default: 15%% of --n)")
    ap.add_argument("--bg-dir", default="",
                    help="dir of real drawing PNGs to sample as backgrounds "
                         "(domain randomisation; big sim-to-real gain)")
    ap.add_argument("--fonts-dir", default="",
                    help="extra dir of .ttf CAD fonts (osifont/ISOCPEUR/...). "
                         "train/fonts is loaded automatically; AMGDT/gdt fonts "
                         "are routed to the symbol-glyph pool")
    ap.add_argument("--no-repo-fonts", action="store_true",
                    help="skip the auto-loaded train/fonts directory")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--style", choices=("iso", "asme", "mixed"), default="iso",
                    help="content vocab standard (asme = inch/UNC/uin; "
                         "mixed = per-sample coin flip). iso is byte-stable.")
    ap.add_argument("--workers", type=int, default=0,
                    help="parallel processes (0 = all CPU cores; 1 = serial)")
    args = ap.parse_args()
    global _STYLE
    _STYLE = args.style
    workers = args.workers or (os.cpu_count() or 1)
    if args.bg_dir:
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            _BG_FILES.extend(glob.glob(os.path.join(args.bg_dir, ext)))
        print("background pool: %d real-drawing crops" % len(_BG_FILES))
    if not args.no_repo_fonts and os.path.isdir(_REPO_FONTS):
        _load_font_dir(_REPO_FONTS)
    if args.fonts_dir:
        _load_font_dir(args.fonts_dir)
    if _FONT_FILES or _GDT_FONT_FILES:
        print("font pool: %d text + %d GD&T-symbol fonts"
              % (len(_FONT_FILES), len(_GDT_FONT_FILES)))
    nval = args.val or max(1, args.n * 15 // 100)
    print("generating with %d workers..." % workers)
    _write("train", args.n, args.out, args.seed, workers)
    _write("val", nval, args.out, args.seed + 1, workers)
    with open(os.path.join(args.out, "data.yaml"), "w") as f:
        f.write("path: %s\n" % os.path.abspath(args.out))
        f.write("train: images/train\nval: images/val\n")
        f.write("nc: %d\n" % len(CLASSES))
        f.write("names: [%s]\n" % ", ".join(CLASSES))
    print("wrote %d train + %d val to %s" % (args.n, nval, args.out))


if __name__ == "__main__":
    main()
