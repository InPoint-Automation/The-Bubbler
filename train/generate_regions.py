# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Synth YOLO-OBB region dataset. Dev-only.
#
#   python train/generate_regions.py --out train/data/region --n 6000 \
#       --bg-dir REAL_DRAWING_PNGS --fonts-dir CAD_FONTS
#   python train/train.py --data train/data/region/data.yaml \
#       --out bubbler/models/gdt_regions.onnx --device 0
import argparse
import glob
import os
import random
import re
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np                                    # noqa: E402
from PIL import Image, ImageDraw                      # noqa: E402

import generate_dataset as gd                         # noqa: E402
import refcallouts                                     # noqa: E402
from generate_dataset import (                        # noqa: E402
    TILE, _font, _ink, _num, _glyph_tile, _clutter, _degrade, _background,
    _rotate_img, _quad_after_paste, _load_font_dir, _REPO_FONTS,
    _callout_lines, _THRU_WORDS, _FITS_HOLE, _THREADS, _TCLASS,
)

# Real hand-labelled callout crops mixed into training.
_REF_CROPS = []
_REF_PROB = 0.0

# Order == label index; mirror in bubbler/vision.py.
REGION_CLASSES = [
    "hole_note",             # drill/cbore/csink/thread
    "feature_control_frame", # boxed GD&T compartments
    "dim_tol",               # dim ± tol
    "hole_table",            # OTWÓR/OPIS grid
    "surface_finish",        # Ra/Rz callout
    "datum_feature",         # boxed datum letter + triangle
    "gentol_block",          # general-tolerance text
    "note",                  # free-text annotation
]

# Oversample the rarer blocks.
_WEIGHTS = {
    "hole_note": 3, "feature_control_frame": 3, "dim_tol": 3, "hole_table": 2,
    "surface_finish": 2, "datum_feature": 2, "gentol_block": 2, "note": 2,
}

# GD&T symbols that can head a feature-control frame.
_FCF_SYMS = ("position", "flatness", "circularity", "cylindricity",
             "perpendicularity", "parallelism", "angularity", "concentricity",
             "profile_line", "profile_surface", "runout_total",
             "runout_circular")

_TABLE_HEAD = (("OTWÓR", "OPIS"), ("HOLE", "DESCRIPTION"),
               ("POS.", "BESCHREIBUNG"), ("NR", "OPIS"), ("ID", "DESCRIPTION"))
_GTOL_TITLES = ("Allgemeintoleranzen ISO 2768-mK",
                "Allgemeintoleranzen ISO 22081", "Tolerancje ogólne ISO 2768-mK",
                "General tolerances ISO 2768-1", "GENERAL TOLERANCES")
_GTOL_LINEAR = ("Linearmaße ±%s", "Lineare Größenmaße: ±%s", "Linear ±%s",
                "Wymiary liniowe ±%s")
_GTOL_ANG = ("Winkelmaße ±%s°", "Winkelgrößenmaße: ±%s°", "Angular ±%s°",
             "Wymiary kątowe ±%s°")
_GTOL_SEE = ("Siehe Tabelle 1", "See table 1", "Patrz tabela 1")
_NOTES = ("ALLE KANTEN ENTGRATEN", "BREAK ALL SHARP EDGES",
          "WSZYSTKIE KRAWĘDZIE STĘPIĆ", "ALLE MAßE IN MM",
          "ALL DIMENSIONS IN MM", "WSZYSTKIE WYMIARY W MM", "NICHT MAßSTÄBLICH",
          "NOT TO SCALE", "SIEHE DETAIL A", "uwaga: nie skalować",
          "Werkstoff: S235JR", "Material: 1.4301", "Gewicht: 0,42 kg")


_NUMRUN = re.compile(r"\d+(?:[.,]\d+)?")        # numeric runs


def _probe():
    """Throwaway draw context for textlength() measurement."""
    return ImageDraw.Draw(Image.new("RGB", (4, 4)))


def _layer(w, h):
    return Image.new("RGBA", (max(1, int(w)), max(1, int(h))), (0, 0, 0, 0))


def _block_angle(rnd, allow_strong=False):
    """Mostly upright; some carry leader skew."""
    r = rnd.random()
    if r < 0.72:
        return 0.0
    if r < 0.94 or not allow_strong:
        return rnd.uniform(-12, 12)
    return rnd.choice((90.0, -90.0)) + rnd.uniform(-5, 5)


def _place_block(base, layer, rnd, allow_strong=False):
    """Crop, rotate, paste; return oriented quad."""
    bb = layer.getbbox()
    if not bb:
        return None
    layer = layer.crop(bb)
    rt, mp = _rotate_img(layer, _block_angle(rnd, allow_strong))
    if rt.width >= TILE - 4 or rt.height >= TILE - 4:
        return None
    px = rnd.randint(2, max(3, TILE - rt.width - 2))
    py = rnd.randint(2, max(3, TILE - rt.height - 2))
    base.paste(rt, (px, py), rt)
    w, h = layer.size
    return _quad_after_paste([(0, 0), (w, 0), (w, h), (0, h)], mp, px, py)


# Block builders.

def _lines_to_layer(lines, rnd, th, indent=False, underline=False,
                    box_numbers=False, circled=None, circled_end=False):
    """Render line tokens; symbols become glyph tiles."""
    font = _font(int(th * 1.25), rnd)
    gap = max(2, th // 5)
    lh = int(th * 1.7)
    m = th
    md = _probe()
    rows, maxw = [], 0
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
    cd = int(th * 1.5) if circled else 0           # balloon diameter
    lpad = (cd + th // 2) if (circled and not circled_end) else 0
    rpad = (cd + th // 2) if (circled and circled_end) else 0
    layer = _layer(maxw + 2 * m + lpad + rpad, lh * len(rows) + 2 * m)
    ld = ImageDraw.Draw(layer)
    ink = _ink(rnd)
    boxes = []
    for r, items in enumerate(rows):
        oy = m + r * lh
        ox = m + lpad + (rnd.randint(th, 3 * th) if (indent and r > 0) else 0)
        for kind, val, x, payload in items:
            if kind == "t":
                ld.text((ox + x, oy), val, fill=ink, font=font)
                if box_numbers:
                    for mt in _NUMRUN.finditer(val):
                        rx = ox + x + md.textlength(val[:mt.start()], font=font)
                        rw = md.textlength(mt.group(0), font=font)
                        boxes.append((rx - 3, oy - 2, rx + rw + 3, oy + th + 3))
            else:
                ty = oy + (th - payload.height) // 2 + th // 6
                layer.paste(payload, (ox + x, ty), payload)
    for bx in boxes:
        ld.rectangle(bx, outline=ink, width=1)
    if underline:
        ly = m + lh * len(rows) - lh // 3
        ld.line((m + lpad, ly, m + lpad + maxw, ly), fill=ink, width=1)
    if circled:
        cy = m + (lh - cd) // 2
        cx = (m + lpad + maxw + th // 4) if circled_end else m
        ld.ellipse((cx, cy, cx + cd, cy + cd), outline=ink, width=rnd.choice((1, 2)))
        dfont = _font(int(cd * 0.7), rnd)
        dw = md.textlength(circled, font=dfont)
        ld.text((cx + (cd - dw) / 2, cy + cd * 0.12), circled, fill=ink, font=dfont)
    return layer


def build_hole_note(rnd):
    th = rnd.randint(13, 26)
    circled = rnd.choice("123456") if rnd.random() < 0.18 else None
    return _lines_to_layer(_callout_lines(rnd), rnd, th,
                           indent=rnd.random() < 0.5,
                           underline=rnd.random() < 0.7,
                           box_numbers=rnd.random() < 0.30,
                           circled=circled,
                           circled_end=rnd.random() < 0.4)


def build_fcf(rnd):
    th = rnd.randint(14, 30)
    sym = _glyph_tile(rnd.choice(_FCF_SYMS), th, rnd)
    tw, thh = sym.size
    H = int(th * 1.6)
    font = _font(int(th * 0.85), rnd)
    pr = _probe()
    c1 = tw + H // 3
    mod = rnd.choice(("", "", "(M)", "(L)", "(P)"))
    zone = rnd.choice(("", "", "", " CZ", " CF"))     # combined/common zone
    tol = ("Ø" if rnd.random() < 0.45 else "") + \
        rnd.choice(("0.1", "0.05", "0.2", "0.02", "0.5", "0.01")) + mod + zone
    c2 = int(pr.textlength(tol, font=font)) + H // 2
    datums = []
    for _ in range(rnd.randint(0, 3)):
        if rnd.random() < 0.7:
            datums.append(rnd.choice("ABCD") + rnd.choice(("", "", "(M)", "(L)")))
    cells = [c1, c2] + [max(H, int(pr.textlength(s, font=font)) + H // 2)
                        for s in datums]
    W = sum(cells)
    m = H // 2 + 6
    layer = _layer(W + 2 * m, H + 2 * m)
    ld = ImageDraw.Draw(layer)
    ink = _ink(rnd)
    ox = oy = m
    ld.rectangle((ox, oy, ox + W, oy + H), outline=ink, width=rnd.choice((1, 2)))
    sx, sy = ox + (c1 - tw) // 2, oy + (H - thh) // 2
    layer.paste(sym, (sx, sy), sym)
    x = ox + c1
    ld.line((x, oy, x, oy + H), fill=ink, width=1)
    ld.text((x + H // 5, oy + (H - thh) // 2), tol, fill=ink, font=font)
    x += c2
    for k, dt in enumerate(datums):
        ld.line((x, oy, x, oy + H), fill=ink, width=1)
        ld.text((x + H // 3, oy + (H - thh) // 2), dt, fill=ink, font=font)
        x += cells[2 + k]
    if rnd.random() < 0.2:                       # all-around circle
        ld.ellipse((ox - H // 3, oy - H // 3, ox, oy), outline=ink, width=1)
    if rnd.random() < 0.35:                       # datum-feature triangle
        tx, ty = ox + rnd.randint(0, W), oy + H
        ld.polygon((tx, ty, tx - 5, ty + 8, tx + 5, ty + 8), fill=ink)
        ld.line((tx, ty + 8, tx, ty + 18), fill=ink, width=1)
        if rnd.random() < 0.7:                    # boxed datum letter
            dl = rnd.choice("ABCD")
            by, bw = ty + 18, th
            ld.rectangle((tx - bw // 2, by, tx + bw // 2, by + bw),
                         outline=ink, width=1)
            lf = _font(int(th * 0.8), rnd)
            lw = ld.textlength(dl, font=lf)
            ld.text((tx - lw / 2, by + bw * 0.1), dl, fill=ink, font=lf)
    return layer


def build_dim_tol(rnd):
    th = rnd.randint(15, 34)
    font = _font(int(th * 1.2), rnd)
    ink = _ink(rnd)
    pr = _probe()
    m = th
    pre = rnd.choice(("Ø", "Ø", "R", "", ""))
    val = _num(rnd, 1, 120, rnd.choice((0, 1, 2)))
    fit = rnd.choice(("", "", "", " H7", " H8", " g6", " k6", " H7"))
    style = rnd.random()
    if style < 0.22:
        # value with stacked upper/lower deviations
        up = "+%s" % _num(rnd, 0.01, 0.2, 2)
        lo = ("+%s" % _num(rnd, 0.0, 0.1, 2)) if rnd.random() < 0.4 \
            else ("-%s" % _num(rnd, 0.01, 0.2, 2))
        base = "%s%s%s " % (pre, val, fit)
        sfont = _font(int(th * 0.72), rnd)
        bw = int(pr.textlength(base, font=font))
        dw = int(max(pr.textlength(up, font=sfont),
                     pr.textlength(lo, font=sfont)))
        layer = _layer(bw + dw + th + 2 * m, int(th * 2.4) + 2 * m)
        ld = ImageDraw.Draw(layer)
        ld.text((m, m + th * 0.25), base, fill=ink, font=font)
        ld.text((m + bw, m), up, fill=ink, font=sfont)
        ld.text((m + bw, m + th * 0.85), lo, fill=ink, font=sfont)
        return layer
    if style < 0.58:
        txt = "%s%s%s ±%s" % (pre, val, fit, _num(rnd, 0.01, 0.5, 2))
    elif style < 0.72:
        txt = "%s%s%s" % (pre, val, fit)                          # bare dim/fit
    elif style < 0.85:
        txt = "%s°" % _num(rnd, 5, 120, rnd.choice((0, 1)))       # angle
    else:
        txt = "%s%s +%s/-%s" % (pre, val, _num(rnd, 0.01, 0.3, 2),
                                _num(rnd, 0.01, 0.3, 2))
    w = int(pr.textlength(txt, font=font))
    layer = _layer(w + 2 * m, int(th * 2.4) + 2 * m)
    ld = ImageDraw.Draw(layer)
    ld.text((m, m), txt, fill=ink, font=font)
    if rnd.random() < 0.6:                        # dimension line + arrowheads
        ly = m + int(th * 1.6)
        ld.line((m, ly, m + w, ly), fill=ink, width=1)
        ld.polygon((m, ly, m + 7, ly - 3, m + 7, ly + 3), fill=ink)
        ld.polygon((m + w, ly, m + w - 7, ly - 3, m + w - 7, ly + 3), fill=ink)
    return layer


def _table_desc(rnd):
    """One hole-table description cell."""
    if rnd.random() < 0.3:
        return "%s - %s" % (rnd.choice(_THREADS), rnd.choice(_TCLASS))
    pre = rnd.choice(("Ø", "Ø", ""))
    d = _num(rnd, 1.5, 12, rnd.choice((1, 2)))
    tail = rnd.choice(("", " " + rnd.choice(_THRU_WORDS),
                       " " + rnd.choice(_FITS_HOLE),
                       " CBORE Ø%s" % _num(rnd, 4, 9, 1)))
    return "%s%s%s" % (pre, d, tail)


def build_hole_table(rnd):
    th = rnd.randint(13, 22)
    font = _font(int(th * 1.2), rnd)
    ink = _ink(rnd)
    pr = _probe()
    nrows = rnd.randint(3, 12)
    head = rnd.choice(_TABLE_HEAD)
    letters = "ABCDEFG"
    ids, descs = [], []
    for i in range(nrows):
        ids.append("%s%d" % (rnd.choice(letters), rnd.randint(1, 4))
                    if rnd.random() < 0.5 else "%d" % (i + 1))
        descs.append(_table_desc(rnd))
    rowh = int(th * 1.7)
    c0 = max([int(pr.textlength(head[0], font=font))] +
             [int(pr.textlength(s, font=font)) for s in ids]) + th
    c1 = max([int(pr.textlength(head[1], font=font))] +
             [int(pr.textlength(s, font=font)) for s in descs]) + th
    W, m = c0 + c1, th
    H = rowh * (nrows + 1)
    layer = _layer(W + 2 * m, H + 2 * m)
    ld = ImageDraw.Draw(layer)
    ox = oy = m
    for r in range(nrows + 2):                    # horizontal rules
        y = oy + r * rowh
        ld.line((ox, y, ox + W, y), fill=ink, width=1)
    for cx in (ox, ox + c0, ox + W):              # vertical rules
        ld.line((cx, oy, cx, oy + H), fill=ink, width=1)
    ld.text((ox + th // 2, oy + th // 4), head[0], fill=ink, font=font)
    ld.text((ox + c0 + th // 2, oy + th // 4), head[1], fill=ink, font=font)
    for i in range(nrows):
        y = oy + (i + 1) * rowh + th // 4
        ld.text((ox + th // 2, y), ids[i], fill=ink, font=font)
        ld.text((ox + c0 + th // 2, y), descs[i], fill=ink, font=font)
    return layer


def build_surface_finish(rnd):
    th = rnd.randint(16, 34)
    sym = _glyph_tile("surface_roughness", th, rnd)
    font = _font(int(th * 0.95), rnd)
    ink = _ink(rnd)
    txt = rnd.choice(("Ra %s", "Rz %s", "%s", "Ra%s")) % _num(rnd, 0.4, 25, 1)
    pr = _probe()
    tw = int(pr.textlength(txt, font=font))
    m = th
    w = sym.width + tw + 3 * m
    h = max(sym.height, int(th * 1.3)) + 2 * m
    layer = _layer(w, h)
    ld = ImageDraw.Draw(layer)
    layer.paste(sym, (m, m), sym)
    ld.text((m + sym.width + m // 2, m), txt, fill=ink, font=font)
    return layer


def build_datum(rnd):
    th = rnd.randint(16, 34)
    font = _font(int(th), rnd)
    ink = _ink(rnd)
    letter = rnd.choice("ABCDEFG")
    pr = _probe()
    lw = int(pr.textlength(letter, font=font))
    box = max(lw, th) + th // 2
    m = th + 6
    layer = _layer(box + 2 * m, box + 2 * m + th * 2)
    ld = ImageDraw.Draw(layer)
    ox = oy = m
    ld.rectangle((ox, oy, ox + box, oy + box), outline=ink, width=rnd.choice((1, 2)))
    ld.text((ox + (box - lw) // 2, oy + box // 6), letter, fill=ink, font=font)
    tx, ty = ox + box // 2, oy + box                # stem + triangle below
    ld.line((tx, ty, tx, ty + th), fill=ink, width=1)
    fy = ty + th
    tri = (tx - th // 2, fy + th // 2, tx + th // 2, fy + th // 2, tx, fy)
    ld.polygon(tri, fill=ink if rnd.random() < 0.6 else None, outline=ink)
    return layer


def build_gentol(rnd):
    th = rnd.randint(13, 22)
    ink = _ink(rnd)
    lines = [rnd.choice(_GTOL_TITLES),
             rnd.choice(_GTOL_LINEAR) % _num(rnd, 0.05, 0.5, 1),
             rnd.choice(_GTOL_ANG) % _num(rnd, 0.2, 1, 1)]
    if rnd.random() < 0.4:
        lines.append(rnd.choice(_GTOL_SEE))
    font = _font(int(th * 1.2), rnd)
    pr = _probe()
    w = max(int(pr.textlength(s, font=font)) for s in lines)
    lh, m = int(th * 1.7), th
    layer = _layer(w + 2 * m, lh * len(lines) + 2 * m)
    ld = ImageDraw.Draw(layer)
    for i, s in enumerate(lines):
        ld.text((m, m + i * lh), s, fill=ink, font=font)
    if rnd.random() < 0.5:
        ld.rectangle((m // 2, m // 2, m + w + m // 2, int(m + lh * len(lines))),
                     outline=ink, width=1)
    return layer


def build_note(rnd):
    th = rnd.randint(13, 24)
    ink = _ink(rnd)
    lines = [rnd.choice(_NOTES) for _ in range(rnd.randint(1, 3))]
    font = _font(int(th * 1.2), rnd)
    pr = _probe()
    w = max(int(pr.textlength(s, font=font)) for s in lines)
    lh, m = int(th * 1.6), th
    layer = _layer(w + 2 * m, lh * len(lines) + 2 * m)
    ld = ImageDraw.Draw(layer)
    for i, s in enumerate(lines):
        ld.text((m, m + i * lh), s, fill=ink, font=font)
    return layer


_BUILDERS = {
    "hole_note": (build_hole_note, True),
    "feature_control_frame": (build_fcf, False),
    "dim_tol": (build_dim_tol, True),
    "hole_table": (build_hole_table, False),
    "surface_finish": (build_surface_finish, False),
    "datum_feature": (build_datum, False),
    "gentol_block": (build_gentol, False),
    "note": (build_note, True),
}
_POOL = [c for c in REGION_CLASSES for _ in range(_WEIGHTS[c])]


# real crops that may carry leader skew
_STRONG_CLASSES = {"hole_note", "dim_tol", "note"}


def _real_crop_block(rnd):
    """Pick real crop, key paper out, random-scale."""
    path, cls = rnd.choice(_REF_CROPS)
    try:
        layer = refcallouts.load_crop_layer(path)
    except Exception:
        return None, None, False
    s = rnd.uniform(0.7, 1.5)
    layer = layer.resize((max(1, int(layer.width * s)),
                          max(1, int(layer.height * s))))
    return cls, layer, cls in _STRONG_CLASSES


def _gen_one_region(rnd):
    img = _background(rnd).copy()
    _clutter(ImageDraw.Draw(img), rnd)         # drawing noise
    labels = []
    for _ in range(rnd.randint(1, 3)):
        if _REF_CROPS and rnd.random() < _REF_PROB:
            cls, layer, strong = _real_crop_block(rnd)
            if layer is None:
                continue
        else:
            cls = rnd.choice(_POOL)
            builder, strong = _BUILDERS[cls]
            try:
                layer = builder(rnd)
            except Exception:
                continue
        quad = _place_block(img, layer, rnd, strong)
        if quad is None:
            continue
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        if max(xs) - min(xs) < 4 or max(ys) - min(ys) < 4:
            continue
        labels.append((REGION_CLASSES.index(cls), quad))
    img = _degrade(img, rnd)
    return img, labels


# Write harness.

def _gen_task_region(job):
    split, i, idir, ldir, seed = job
    rnd = random.Random((seed * 1000003) ^ (i * 2654435761 & 0xFFFFFFFF) ^
                        (hash(split) & 0xFFFFFFFF))
    np.random.seed((seed * 7919 + i) % (2 ** 32 - 1))
    img, labels = _gen_one_region(rnd)
    stem = "%s_%06d" % (split, i)
    img.save(os.path.join(idir, stem + ".png"))
    with open(os.path.join(ldir, stem + ".txt"), "w") as f:
        for ci, quad in labels:
            coords = []
            for px, py in quad:
                coords.append("%.6f" % min(1.0, max(0.0, px / TILE)))
                coords.append("%.6f" % min(1.0, max(0.0, py / TILE)))
            f.write("%d %s\n" % (ci, " ".join(coords)))


def _init_worker(bg_files, font_files, gdt_font_files, ref_crops, ref_prob):
    global _REF_CROPS, _REF_PROB
    gd._BG_FILES, gd._FONT_FILES, gd._GDT_FONT_FILES = \
        bg_files, font_files, gdt_font_files
    _REF_CROPS, _REF_PROB = ref_crops, ref_prob


def _write_serial(split, jobs):
    n = len(jobs)
    for j, job in enumerate(jobs):
        _gen_task_region(job)
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
                                 initargs=(gd._BG_FILES, gd._FONT_FILES,
                                           gd._GDT_FONT_FILES,
                                           _REF_CROPS, _REF_PROB)) as ex:
            done = 0
            for fut in as_completed([ex.submit(_gen_task_region, j) for j in jobs]):
                fut.result()
                done += 1
                if done % 500 == 0:
                    print("  %s %d/%d" % (split, done, n))
    except Exception as e:
        print("  parallel pool failed (%s); falling back to serial" % e)
        _write_serial(split, jobs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("train", "data", "region"))
    ap.add_argument("--n", type=int, default=4000, help="train images")
    ap.add_argument("--val", type=int, default=0,
                    help="val images (default: 15%% of --n)")
    ap.add_argument("--bg-dir", default="",
                    help="dir of real drawing PNGs sampled as backgrounds")
    ap.add_argument("--fonts-dir", default="",
                    help="extra dir of .ttf CAD fonts (osifont/ISOCPEUR/...)")
    ap.add_argument("--no-repo-fonts", action="store_true")
    ap.add_argument("--ref-dir", default=refcallouts.REF_DIR,
                    help="dir of hand-labelled real callout crops to mix in")
    ap.add_argument("--ref-prob", type=float, default=0.25,
                    help="chance a block slot uses a real crop (0 = synth only)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0,
                    help="parallel processes (0 = all cores; 1 = serial)")
    args = ap.parse_args()
    global _REF_CROPS, _REF_PROB
    workers = args.workers or (os.cpu_count() or 1)
    if args.bg_dir:
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            gd._BG_FILES.extend(glob.glob(os.path.join(args.bg_dir, ext)))
        print("background pool: %d real-drawing crops" % len(gd._BG_FILES))
    if args.ref_prob > 0 and os.path.isdir(args.ref_dir):
        _REF_CROPS = refcallouts.single_class_crops(args.ref_dir)
        _REF_PROB = args.ref_prob
        print("real callout pool: %d single-class crops (p=%.2f)"
              % (len(_REF_CROPS), _REF_PROB))
        from collections import Counter
        have = Counter(cls for _, cls in _REF_CROPS)
        print("  real-crop coverage per class:")
        for c in REGION_CLASSES:
            tag = "" if have[c] else "  <- none; synthetic-only in train"
            print("    %-22s %d%s" % (c, have[c], tag))
        if args.ref_prob > 0.5:
            print("  NOTE: high --ref-prob starves classes with no real crop "
                  "(they only come from synthetic builders).")
    elif args.ref_prob > 0:
        print("ref-dir not found (%s); training on pure synthetic" % args.ref_dir)
    if not args.no_repo_fonts and os.path.isdir(_REPO_FONTS):
        _load_font_dir(_REPO_FONTS)
    if args.fonts_dir:
        _load_font_dir(args.fonts_dir)
    if gd._FONT_FILES or gd._GDT_FONT_FILES:
        print("font pool: %d text + %d GD&T-symbol fonts"
              % (len(gd._FONT_FILES), len(gd._GDT_FONT_FILES)))
    nval = args.val or max(1, args.n * 15 // 100)
    print("generating with %d workers..." % workers)
    _write("train", args.n, args.out, args.seed, workers)
    _write("val", nval, args.out, args.seed + 1, workers)
    with open(os.path.join(args.out, "data.yaml"), "w") as f:
        f.write("path: %s\n" % os.path.abspath(args.out))
        f.write("train: images/train\nval: images/val\n")
        f.write("nc: %d\n" % len(REGION_CLASSES))
        f.write("names: [%s]\n" % ", ".join(REGION_CLASSES))
    with open(os.path.join(args.out, "region_classes.txt"), "w") as f:
        f.write("\n".join(REGION_CLASSES) + "\n")
    print("wrote %d train + %d val to %s" % (args.n, nval, args.out))


if __name__ == "__main__":
    main()
