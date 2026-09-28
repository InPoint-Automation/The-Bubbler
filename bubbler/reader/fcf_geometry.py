# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# FCF geometry: find frame, cells, rows.

import re as _re
from bubbler.reader import geometry, grammar, textlayer  # noqa: E402


def _fcf_vector_bands(page, rect, cfg, join=False):
    try:
        paths = page.get_drawings()
    except Exception:
        return [], []
    if not paths:
        return [], []
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    m = None
    if rot:
        try:
            m = page.rotation_matrix
        except Exception:
            return None
    x0, y0, x1, y1 = rect
    w = x1 - x0
    h = y1 - y0
    if w < 4 or h < 4:
        return None
    tol = max(1.0, 0.06 * h)
    xs, ys, xspan, hseg = [], [], [], []
    for p in paths:
        for it in (p.get("items") or []):
            if it[0] != "l":
                continue
            pa, pb = it[1], it[2]
            ax, ay, bx, by = pa.x, pa.y, pb.x, pb.y
            if m is not None:
                ax, ay = geometry.xform_pt(m, ax, ay)
                bx, by = geometry.xform_pt(m, bx, by)
            sx0, sy0 = min(ax, bx), min(ay, by)
            sx1, sy1 = max(ax, bx), max(ay, by)
            dx, dy = sx1 - sx0, sy1 - sy0
            if dy >= 0.5 * h and dx <= tol:
                cx = (sx0 + sx1) / 2.0
                if x0 - tol <= cx <= x1 + tol:
                    xs.append(cx)
                    xspan.append((cx, sy0, sy1))
            elif dy <= tol and dx > 0:
                cy = (sy0 + sy1) / 2.0
                if y0 - tol <= cy <= y1 + tol:
                    hseg.append((cy, sx0, sx1))
    # cell-by-cell edges joined, glyph retry only
    ys = [t for t in (_join_collinear(hseg) if join else hseg)
          if t[2] - t[1] >= 0.5 * w]
    box = None
    if len(xs) >= 2 and len(ys) >= 2:
        # closed box not pairs
        if any(a - tol <= min(xs) and b + tol >= max(xs)
               and abs(a - min(xs)) <= tol + (b - a) * 0.05
               for _y, a, b in ys):
            x0, x1 = min(xs), max(xs)
            y0, y1 = min(t[0] for t in ys), max(t[0] for t in ys)
            tol = max(1.0, 0.06 * (y1 - y0))
            box = (x0, y0, x1, y1)
    if box is not None:
        over = max(3.0, 0.15 * (y1 - y0))
        keep = set(cx for cx, sy0, sy1 in xspan
                   if sy0 <= y0 + tol and sy1 >= y1 - tol
                   and not (sy0 < y0 - over and sy1 > y1 + over))
        xs = [x for x in xs if x in keep]
    inx = _cluster(sorted(x for x in xs if x0 + tol < x < x1 - tol), tol)
    rows = _cluster_spans([t for t in ys if y0 + tol < t[0] < y1 - tol
                           and t[1] >= x0 - tol and t[2] <= x1 + tol], tol)
    return (inx, [t[0] for t in rows], [(t[1], t[2]) for t in rows], box,
            [])            # no enclosing guess


def _longest_ink(mask):
    best = run = None
    for i, v in enumerate(mask):
        if v:
            run = (run[0], i) if run else (i, i)
            if best is None or run[1] - run[0] > best[1] - best[0]:
                best = run
        else:
            run = None
    return best


def _fcf_boxed(dark, vruns, hruns, cover=0.9):
    if len(vruns) < 2 or len(hruns) < 2:
        return None
    l, r = vruns[0][0], vruns[-1][-1]
    side = _longest_ink(dark[:, l:vruns[0][-1] + 1].any(axis=1))
    side2 = _longest_ink(dark[:, vruns[-1][0]:r + 1].any(axis=1))
    if side is None or side2 is None:
        return None
    vtop = min(side[0], side2[0])
    vbot = max(side[1], side2[1])
    tolv = max(2, 0.05 * (vbot - vtop + 1))
    inside = [h for h in hruns
              if vtop - tolv <= h[0] and h[-1] <= vbot + tolv]
    # inner pair else outermost
    if len(inside) >= 2:
        hruns = inside
    t, b = hruns[0][0], hruns[-1][-1]
    if r - l < 2 or b - t < 2:
        return None
    box = dark[t:b + 1, l:r + 1]
    if box.size == 0:
        return None
    hh, ww = box.shape
    # measure side over middle
    my0, my1 = int(hh * 0.1), max(int(hh * 0.9), int(hh * 0.1) + 1)
    mx0, mx1 = int(ww * 0.1), max(int(ww * 0.9), int(ww * 0.1) + 1)
    sides = (box[my0:my1, :vruns[0][-1] - l + 1].any(axis=1).mean(),
             box[my0:my1, vruns[-1][0] - l:].any(axis=1).mean(),
             box[:hruns[0][-1] - t + 1, mx0:mx1].any(axis=0).mean(),
             box[hruns[-1][0] - t:, mx0:mx1].any(axis=0).mean())
    if min(sides) < cover:
        return None
    rr = dark.any(axis=1).nonzero()[0]
    cc = dark.any(axis=0).nonzero()[0]
    if not rr.size or not cc.size:
        return None
    if ww < cover * (cc[-1] - cc[0] + 1) or hh < cover * (rr[-1] - rr[0] + 1):
        return None                    # divider posing as border
    return l, r, t, b


def _fcf_through_border(enclosing, c):
    """Divider runs past border into margin"""
    if enclosing is None:
        return False
    full, l, t, b = enclosing
    h = full.shape[0]
    uc = int(round(l + c))
    if not (0 <= uc < full.shape[1] and t >= 3 and b <= h - 4):
        return False
    return bool(full[:t, uc].mean() > 0.5 and full[b + 1:, uc].mean() > 0.5)


def _fcf_raster_bands(ink, rect, cfg):
    try:
        import numpy as np
    except Exception:
        return None
    a = np.asarray(ink)
    if a.ndim == 3:
        a = a.mean(axis=2)
    if a.ndim != 2 or a.size == 0:
        return None
    lo, hi = float(a.min()), float(a.max())
    thr = lo + 0.5 * (hi - lo) if hi > lo else (hi * 0.5 if hi else 0.5)
    dark = a < thr
    x0, y0, x1, y1 = rect
    hgt, wid = dark.shape
    gap = max(1, int(cfg.get("vision_fcf_proj_gap", 2)))
    frac = float(cfg.get("vision_fcf_divider_min", 0.6))
    vruns = _profile_runs(dark.sum(axis=0).astype(float), hgt * frac, gap)
    hruns = _profile_runs(dark.sum(axis=1).astype(float), wid * frac, gap)
    boxed = _fcf_boxed(dark, vruns, hruns)
    box = None
    enclosing = None
    if boxed:
        px = (x1 - x0) / max(wid, 1)
        py = (y1 - y0) / max(hgt, 1)
        l, r, t, b = boxed
        # untrimmed crop for note-box test
        enclosing = (dark, l, t, b)
        x0, x1 = x0 + l * px, x0 + (r + 1) * px
        y0, y1 = y0 + t * py, y0 + (b + 1) * py
        dark = dark[t:b + 1, l:r + 1]
        hgt, wid = dark.shape
        box = (x0, y0, x1, y1)
    col = dark.sum(axis=0).astype(float)
    row = dark.sum(axis=1).astype(float)
    xs = _profile_lines(col, hgt * frac, gap)
    sx = (x1 - x0) / max(wid, 1)
    sy = (y1 - y0) / max(hgt, 1)
    # 2px border not divider
    tol = max(1.0, 0.06 * (y1 - y0))
    inx = [x0 + c * sx for c in xs
           if x0 + tol < x0 + c * sx < x1 - tol]
    enc = [x0 + c * sx for c in xs
           if x0 + tol < x0 + c * sx < x1 - tol
           and _fcf_through_border(enclosing, c)]
    # divider from symbol cell
    first = min([c for c in xs if 0 < c < wid - 1] or [0])
    # floor stops phantom divider
    yruns = _profile_runs(row, max(wid - first, wid * 0.5) * frac, gap)
    # mask thin frame lines
    vmask = np.zeros(wid, dtype=bool)
    line_w = max(2, int(0.03 * wid))
    for r in _profile_runs(col, hgt * frac, gap):
        if len(r) <= line_w or r[0] <= 1 or r[-1] >= wid - 2:
            vmask[r[0]:r[-1] + 1] = True
    iny, spans = [], []
    for r in yruns:
        yp = y0 + (sum(r) / len(r)) * sy
        if not (y0 + tol < yp < y1 - tol):
            continue
        iny.append(yp)
        band = dark[r[0]:r[-1] + 1].any(axis=0) & ~vmask
        cols = band.nonzero()[0]
        if not cols.size:                      # fully masked read unmasked
            cols = dark[r[0]:r[-1] + 1].any(axis=0).nonzero()[0]
        # unknown fails to bubble
        spans.append((x0 + float(cols[0]) * sx, x0 + float(cols[-1]) * sx)
                     if cols.size else (x1, x1))
    return inx, iny, spans, box, enc


def _profile_runs(prof, thresh, gap):
    idx = [i for i, v in enumerate(prof) if v >= thresh]
    if not idx:
        return []
    runs = [[idx[0]]]
    for i in idx[1:]:
        if i - runs[-1][-1] <= gap:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def _profile_lines(prof, thresh, gap):
    return [sum(r) / len(r) for r in _profile_runs(prof, thresh, gap)]


def _cluster_spans(items, tol):
    groups = []
    for v, a, b in sorted(items):
        if groups and v - groups[-1][-1][0] <= tol:
            groups[-1].append((v, a, b))
        else:
            groups.append([(v, a, b)])
    out = []
    for g in groups:
        out.append((sum(t[0] for t in g) / len(g),
                    min(t[1] for t in g), max(t[2] for t in g)))
    return out


def _cluster(vals, tol):
    out = []
    for v in vals:
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(r) / len(r) for r in out]


def _bands_from_dividers(x0, x1, xs):
    edges = [x0] + list(xs) + [x1]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


FCF_BOX_DPI = 150                # enough for border
FCF_BOX_LOOK = 1.0               # share of box size


def _fcf_rect_from_lines(hlines, vlines, cx, cy, cover=0.95, depth=4,
                         like=None, maxw=None, maxh=None, span=None,
                         limit=8):
    """Closed rectangles around (cx, cy) best IoU first"""
    sw, sh = (span or (None, None))
    up = _near_side([h for h in hlines if h[0] <= cy], cy, depth, span=sw)
    dn = _near_side([h for h in hlines if h[0] > cy], cy, depth, span=sw)
    lf = _near_side([v for v in vlines if v[0] <= cx], cx, depth, span=sh)
    rt = _near_side([v for v in vlines if v[0] > cx], cx, depth, span=sh)
    cand = []
    for t in up:
        for b in dn:
            h = b[0] - t[0]
            if h <= 1:
                continue
            for l in lf:
                for r in rt:
                    w = r[0] - l[0]
                    if w <= 1 or (maxw and w > maxw) or (maxh and h > maxh):
                        continue
                    if not (_covers(t[1], t[2], l[0], r[0], w, cover)
                            and _covers(b[1], b[2], l[0], r[0], w, cover)
                            and _covers(l[1], l[2], t[0], b[0], h, cover)
                            and _covers(r[1], r[2], t[0], b[0], h, cover)):
                        continue
                    box = (l[0], t[0], r[0], b[0])
                    # frame has compartments
                    if not any(l[0] + 1 < v[0] < r[0] - 1
                               and _covers(v[1], v[2], t[0], b[0], h, cover)
                               for v in vlines):
                        continue
                    if like is None:
                        cand.append((w * h, w * h, box))
                        continue
                    cand.append((geometry._iou(box, like), w * h, box))
    if not cand:
        return []
    # prefer biggest plausible rect
    good = [c for c in cand if c[0] >= 0.5]
    if good:
        good.sort(key=lambda c: -c[1])
    else:
        good = sorted(cand, key=lambda c: -c[0])
    out, seen = [], set()
    for _s, _a, box in good:
        if box in seen:
            continue
        seen.add(box)
        out.append(box)
    return out[:limit]


def _near_side(lines, at, depth, keep=0.5, span=None):
    """depth nearest length-filtered candidates for one frame side"""
    if not lines:
        return []
    longest = max(ln[2] - ln[1] for ln in lines)
    floor = keep * longest if not span else min(keep * longest, keep * span)
    real = [ln for ln in lines if ln[2] - ln[1] >= floor]
    if not real:
        return []
    near = sorted(real, key=lambda ln: abs(ln[0] - at))[:depth]
    far = max(real, key=lambda ln: ln[2] - ln[1])
    return near if far in near else near + [far]


def _covers(a0, a1, b0, b1, span, cover):
    return (min(a1, b1) - max(a0, b0)) >= cover * span


def _lines_from_ink(dark, minrun=0.1):
    hgt, wid = dark.shape
    hmin = max(4, int(minrun * wid))
    vmin = max(4, int(minrun * hgt))
    hlines, vlines = [], []
    for y in range(hgt):
        run = _longest_ink(dark[y])
        if run is not None and run[1] - run[0] + 1 >= hmin:
            hlines.append((y, run[0], run[1]))
    for x in range(wid):
        run = _longest_ink(dark[:, x])
        if run is not None and run[1] - run[0] + 1 >= vmin:
            vlines.append((x, run[0], run[1]))
    return _thin(hlines), _thin(vlines)


def _thin(lines, gap=2):
    out = []
    for ln in lines:
        if out and ln[0] - out[-1][0] <= gap:
            prev = out[-1]
            if ln[2] - ln[1] > prev[2] - prev[1]:
                out[-1] = ln
            continue
        out.append(ln)
    return out


def _clamp_page(page, rect):
    try:
        pr = page.rect
        px0, py0, px1, py1 = pr.x0, pr.y0, pr.x1, pr.y1
    except Exception:
        return rect
    return (max(rect[0], px0), max(rect[1], py0),
            min(rect[2], px1), min(rect[3], py1))


def _fcf_reads_as_frame(words, box, vlines):
    """Rect content reads like control frame 0 1 or 2"""
    x0, y0, x1, y1 = box
    inner = sorted(v[0] for v in vlines if x0 + 1 < v[0] < x1 - 1)
    if not inner:
        return 0
    first = inner[0]
    sym = num = False
    for w in words:
        cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        raw = str(w[4])
        t = grammar.scan_normalize(raw)
        if cx <= first:
            if any(g in raw for g in _GDT_SYMBOLS_SET) or \
                    any(k in t for k in _GDT_WORDS):
                sym = True
        elif _NUMISH.search(t):
            num = True
    return (2 if sym and num else 1 if sym else 0)


_GDT_SYMBOLS_SET = frozenset(g for g, _kw in grammar._GDT_SYMBOLS)
_GDT_WORDS = tuple(sorted(set(kw.strip() for _g, kw in grammar._GDT_SYMBOLS
                              if kw.strip()), key=len, reverse=True))
_NUMISH = _re.compile(r"\d")


def _fcf_pick(page, boxes, vlines):
    if not boxes:
        return None
    if len(boxes) == 1:
        return boxes[0]
    try:
        words = textlayer.page_words(page)
    except Exception:
        return boxes[0]
    best, at = -1, 0
    for i, b in enumerate(boxes):
        sc = _fcf_reads_as_frame(words, b, vlines)
        if sc > best:                    # ties keep geometric order
            best, at = sc, i
    return boxes[at]


def _fcf_find_box(page, rect, cfg, centre=None, vector=True, src=None):
    """Drawn frame around detector box, else None. `src` gets search used"""
    x0, y0, x1, y1 = rect
    cx, cy = centre[:2] if centre else ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    px = max(4.0, FCF_BOX_LOOK * (x1 - x0))
    py = max(4.0, FCF_BOX_LOOK * (y1 - y0))
    wide = _clamp_page(page, (x0 - px, y0 - py, x1 + px, y1 + py))
    lim = (x1 - x0 + 2 * px, y1 - y0 + 2 * py)
    span = (x1 - x0, y1 - y0)
    if centre and len(centre) > 2:
        # sides judged against glyph height
        span = (4.0 * centre[2], centre[2])
    # far border many dividers away
    depth = 12 if centre else 4
    boxes, vl = (_fcf_box_vector(page, wide, cx, cy, rect, lim, span, depth)
                 if vector else ([], []))
    if src is not None:
        src["box"] = "vector" if boxes else "raster"
    if not boxes:
        boxes, vl = _fcf_box_raster(page, cfg, wide, cx, cy, rect, lim, span,
                                    depth)
    box = _fcf_pick(page, boxes, vl)
    if box is None:
        return None
    bw, bh = box[2] - box[0], box[3] - box[1]
    ov = (max(0.0, min(box[2], x1) - max(box[0], x0))
          * max(0.0, min(box[3], y1) - max(box[1], y0)))
    if bw < 4 or bh < 4 or ov < 0.5 * bw * bh:
        return None
    # same object, unless glyph-anchored
    if centre is None and geometry._iou(box, rect) < 0.15:
        return None
    if centre is not None and not (box[0] <= cx <= box[2]
                                   and box[1] <= cy <= box[3]):
        return None
    return box


def _fcf_box_vector(page, wide, cx, cy, like=None, lim=None,
                    span=None, depth=4):
    try:
        paths = page.get_drawings()
    except Exception:
        return [], []
    if not paths:
        return [], []
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    m = None
    if rot:                    # same conversion as _fcf_vector_bands
        try:
            m = page.rotation_matrix
        except Exception:
            return [], []
    hl, vl = [], []
    for p in paths:
        for it in (p.get("items") or []):
            if it[0] != "l":
                continue
            ax, ay, bx, by = it[1].x, it[1].y, it[2].x, it[2].y
            if m is not None:
                ax, ay = geometry.xform_pt(m, ax, ay)
                bx, by = geometry.xform_pt(m, bx, by)
            lo, hi = min(ax, bx), max(ax, bx)
            loy, hiy = min(ay, by), max(ay, by)
            if not (wide[0] <= hi and lo <= wide[2]
                    and wide[1] <= hiy and loy <= wide[3]):
                continue
            if abs(by - ay) <= 1.0 and hi - lo > 2.0:
                hl.append(((ay + by) / 2.0, lo, hi))
            elif abs(bx - ax) <= 1.0 and hiy - loy > 2.0:
                vl.append(((ax + bx) / 2.0, loy, hiy))
    if depth > 4:
        # glyph retry only. Else box choice shifts
        hl, vl = _join_collinear(hl), _join_collinear(vl)
    return (_fcf_rect_from_lines(hl, vl, cx, cy, like=like,
                                 maxw=(lim or (None, None))[0],
                                 maxh=(lim or (None, None))[1], span=span,
                                 depth=depth),
            vl)


def _join_collinear(lines, tol=0.6, gap=1.0):
    """Join collinear touching segments. Cell-by-cell frames"""
    out = []
    for at, lo, hi in sorted(lines, key=lambda ln: ln[1]):
        for k, (a0, l0, h0) in enumerate(out):
            if abs(a0 - at) <= tol and lo <= h0 + gap:
                out[k] = (a0, l0, max(h0, hi))
                break
        else:
            out.append((at, lo, hi))
    return out


def _fcf_box_raster(page, cfg, wide, cx, cy, like=None, lim=None,
                    span=None, depth=4):
    try:
        import numpy as np
        from bubbler.reader.vision import render
        pm = render._pixmap_clip(page, cfg, wide,
                                 cfg.get("vision_fcf_box_dpi", FCF_BOX_DPI))
    except Exception:
        return [], []
    if pm is None:
        return [], []
    a = np.asarray(pm[0])
    if a.ndim == 3:
        a = a.mean(axis=2)
    if a.ndim != 2 or a.size == 0:
        return [], []
    lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        return [], []
    dark = a < lo + 0.5 * (hi - lo)
    hgt, wid = dark.shape
    sx = (wide[2] - wide[0]) / max(wid, 1)
    sy = (wide[3] - wide[1]) / max(hgt, 1)
    hl, vl = _lines_from_ink(dark)
    hl = [(wide[1] + y * sy, wide[0] + a0 * sx, wide[0] + a1 * sx)
          for y, a0, a1 in hl]
    vl = [(wide[0] + x * sx, wide[1] + b0 * sy, wide[1] + b1 * sy)
          for x, b0, b1 in vl]
    return (_fcf_rect_from_lines(hl, vl, cx, cy, like=like,
                                 maxw=(lim or (None, None))[0],
                                 maxh=(lim or (None, None))[1], span=span,
                                 depth=depth),
            vl)


# corpus report only. Vector vs raster
COMPARE_GEOMETRY = False


def _fcf_bands_for(page, rect, cfg, crop=None, join=False, geom=None,
                   raster=False, vector=True):
    """Vector bands where drawn, raster otherwise. Vector wins"""
    vec = None
    try:
        vec = _fcf_vector_bands(page, rect, cfg, join) if vector else None
    except Exception:
        vec = None
    if vec is not None and not vec[0]:
        vec = None
    if geom is not None:
        geom["src"] = "vector" if vec is not None else "raster"
    if vec is not None and not (raster or COMPARE_GEOMETRY):
        return vec
    ras = None
    ink = crop
    if ink is None:
        try:
            from bubbler.reader.vision import render
            pm = render._pixmap_clip(page, cfg, rect,
                                     cfg.get("vision_fcf_dpi", 600))
        except Exception:
            pm = None
        ink = pm[0] if pm is not None else None
    if ink is not None:
        try:
            ras = _fcf_raster_bands(ink, rect, cfg)
        except Exception:
            ras = None
    if geom is not None and vec is not None:
        geom.update(_fcf_geom_compare(vec, ras))
    if vec is None:
        return ras
    if ras is not None and ras[4]:
        tol = max(1.5, 0.02 * (rect[2] - rect[0]))
        enc = [x for x in vec[0] if any(abs(x - e) <= tol for e in ras[4])]
        if enc:
            vec = tuple(vec[:4]) + (enc,)
    return vec


def _fcf_geom_compare(vec, ras):
    out = {"vec": None if vec is None else len(vec[0]),
           "ras": None if ras is None else len(ras[0])}
    if vec is not None and ras is not None and len(vec[0]) == len(ras[0]):
        out["delta"] = max([abs(a - b) for a, b in
                            zip(sorted(vec[0]), sorted(ras[0]))] or [0.0])
    return out


# reach for clipped border
_FCF_WIDEN = (0.15, 0.40)
_FCF_WIDEN_MIN = 4.0


def _fcf_widen(page, rect, cfg, bands, raster=False, geom=None, join=False,
               vector=True):
    """Widen crop for clipped border. Wide `geom` replaces narrow"""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    area = max((x1 - x0) * (y1 - y0), 1e-6)
    for k in _FCF_WIDEN:
        px = max(_FCF_WIDEN_MIN, k * (x1 - x0))
        py = max(_FCF_WIDEN_MIN, k * (y1 - y0))
        g = {}
        alt = _fcf_bands_for(
            page, _clamp_page(page, (x0 - px, y0 - py, x1 + px, y1 + py)),
            cfg, None, join=join, geom=g, raster=raster, vector=vector)
        if alt is None or alt[3] is None:
            continue
        bx0, by0, bx1, by1 = alt[3]
        if not (bx0 <= cx <= bx1 and by0 <= cy <= by1):
            continue                       # centred on someone else
        ov = (max(0.0, min(bx1, x1) - max(bx0, x0))
              * max(0.0, min(by1, y1) - max(by0, y0)))
        if ov / area >= 0.6:
            if geom is not None:
                box = geom.get("box")
                geom.clear()
                geom.update(g)
                if box:
                    geom["box"] = box      # search only
            return alt
    return bands


def segment_fcf_cells(page, rect, cfg, crop=None, anchor=None, raster=False,
                      vector=True):
    seg = _segment_fcf(page, rect, cfg, crop, raster=raster, vector=vector)
    # unboxed read retries round glyph
    if (anchor is not None and crop is None and page is not None
            and (seg is None or seg.get("unboxed"))):
        try:
            src = {}
            found = _fcf_find_box(page, rect, cfg or {}, centre=anchor,
                                  vector=vector, src=src)
        except Exception:
            found = None
        if found is not None:
            alt = _segment_fcf(page, rect, cfg, None, found=found,
                               raster=raster, vector=vector)
            # never lose rows
            if alt is not None and not alt.get("unboxed") and (
                    seg is None or len(alt["rows"]) >= len(seg["rows"])):
                alt.setdefault("geom", {}).update(src)
                return alt
    return seg


_UNSET = object()


def _segment_fcf(page, rect, cfg, crop=None, found=_UNSET, raster=False,
                 vector=True):
    cfg = cfg or {}
    retry = found is not _UNSET          # the glyph-anchored pass
    x0, y0, x1, y1 = rect
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    unboxed = False
    box_src = {}
    if crop is None and page is not None:
        if not retry:
            try:
                found = _fcf_find_box(page, rect, cfg, vector=vector,
                                      src=box_src)
            except Exception:
                found = None
        if found is not None:
            # hair wider than box
            m = max(1.5, 0.01 * min(found[2] - found[0],
                                    found[3] - found[1]))
            rect = _clamp_page(page, (found[0] - m, found[1] - m,
                                      found[2] + m, found[3] + m))
            x0, y0, x1, y1 = rect
    geom = dict(box_src) if found is not None else {}
    bands = _fcf_bands_for(page, rect, cfg, crop, join=retry, geom=geom,
                           raster=raster, vector=vector)
    if bands is not None and bands[3] is None and crop is None \
            and page is not None:
        bands = _fcf_widen(page, rect, cfg, bands, raster=raster, geom=geom,
                           join=retry, vector=vector)
    if bands is not None and bands[3] is None:
        # no box but readable
        unboxed = True
    if bands is None:
        return None
    xs, mids, spans, box, enc = bands
    if box is not None:
        # measure cells from frame
        x0, y0, x1, y1 = box
    cells = _bands_from_dividers(x0, x1, sorted(xs))
    if len(cells) < 2:
        return None
    # note-box alternate fallback
    cells_alt = None
    if enc:
        kept = [x for x in xs if x not in enc]
        alt = _bands_from_dividers(x0, x1, sorted(kept))
        if 2 <= len(alt) < len(cells):
            cells_alt = alt
    if not spans:
        spans = [None] * len(mids)
    order = sorted(range(len(mids)), key=lambda i: mids[i])
    ys = [mids[i] for i in order]
    rows = _bands_from_dividers(y0, y1, ys)
    # symbol cell own bands
    half = (cells[0][0] + cells[0][1]) / 2.0
    sym_ys = [y for y, sp in zip(ys, (spans[i] for i in order))
              if sp is None or sp[0] <= half]
    return {"cells": cells, "rows": rows, "unboxed": unboxed,
            "frame": (x0, y0, x1, y1), "cells_alt": cells_alt,
            "sym_rows": _bands_from_dividers(y0, y1, sym_ys),
            "geom": geom}                 # vector vs raster report
