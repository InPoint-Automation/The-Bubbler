# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Glyph detection, vector Ø, glyph-to-number attach.

import re
from bubbler.reader import dedup  # noqa: E402
from bubbler.reader.vision import detect, render, runtime  # noqa: E402


def _glyph_keyword(tok):
    from bubbler.reader.grammar import _GDT_SYMBOLS
    for glyph, kw in _GDT_SYMBOLS:
        if glyph == tok:
            return kw.strip().upper()
    return None


def _block_glyphs(block_words):
    return " ".join(str(w[4]) for w in block_words).upper()


def _glyph_present(tok, have_upper):
    t = (tok or "").strip().upper()
    if t and any(w.startswith(t) for w in have_upper.split()):
        return True
    kw = _glyph_keyword(tok)
    if kw and kw in have_upper:
        return True
    return False


_WRAP_SPAN = 0.5


def _wrap_enclosed(out, rect, symbol):
    close = runtime._SYM_WRAP.get(symbol)
    if close is None:
        return False
    x0, y0, x1, y1 = rect
    # counts never enclosed
    counts = set()
    for w in out:
        if str(w[4]).strip() in ("x", "X", "\u00d7") and len(w) > 7:
            counts.add((w[5], w[6], w[7] - 1))
    best = None
    for i, w in enumerate(out):
        wt = str(w[4]).strip()
        if not wt or wt.startswith(symbol):
            continue
        if len(w) > 7 and (w[5], w[6], w[7]) in counts:
            continue
        # enclosure spans number
        ww = max(w[2] - w[0], 1e-6)
        if (min(x1, w[2]) - max(x0, w[0])) < _WRAP_SPAN * ww:
            continue
        cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        area = max(1e-6, (w[2] - w[0]) * (w[3] - w[1]))
        if best is None or area > best[0]:
            best = (area, i)
    if best is None:
        return True                     # nothing enclosed
    i = best[1]
    w = out[i]
    out[i] = (min(x0, w[0]), min(y0, w[1]), max(x1, w[2]), max(y1, w[3]),
              symbol + str(w[4]).strip() + close) + tuple(w[5:])
    return True


_KW_TOKENS = ("CBORE", "CSINK", "DEEP")
_KW_LEAD = re.compile(r"^(?:CBORE|CSINK|DEEP)\s*")


def _diag_frame(w, d, rect):
    import math
    if not d or len(d) < 2:
        return None
    dx, dy = float(d[0]), float(d[1])
    n = math.hypot(dx, dy)
    if n < 1e-6:
        return None
    ux, uy = dx / n, dy / n
    if min(abs(ux), abs(uy)) < 0.26:          # 15 deg of quarter
        return None
    size = float(d[2]) if len(d) > 2 and d[2] else 0.0
    bw, bh = w[2] - w[0], w[3] - w[1]
    ac, as_ = abs(ux), abs(uy)
    if size <= 0:
        return None
    ln = ((bw - size * as_) / ac) if ac >= as_ else ((bh - size * ac) / as_)
    ln = max(ln, 0.0)
    wx, wy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
    gx, gy = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
    along = (gx - wx) * ux + (gy - wy) * uy
    off = abs(-(gx - wx) * uy + (gy - wy) * ux)
    g = max(rect[2] - rect[0], rect[3] - rect[1])
    return off, (-ln / 2.0) - (along + g / 2.0), size


def _attach_or_append(out, rect, symbol):
    """Prepend symbol to nearest right number or append."""
    from bubbler.reader.tokens import _GLYPHS

    def _lead(s):
        s = _KW_LEAD.sub("", s)
        c = s[:1]
        return _GLYPHS.get(c, c)

    if _wrap_enclosed(out, rect, symbol):
        return
    from bubbler.reader.geometry import fill_dirs, _dir_quarter, _rect_map, _to_frame
    from bubbler.reader.grammar import _GDT_SYMBOLS
    x0, y0, x1, y1 = rect
    # characteristic is own token
    own_token = any(symbol.strip() == g for g, _n in _GDT_SYMBOLS)
    best = None
    for i, w in enumerate(out):
        wt = str(w[4])
        if not wt or not re.match(r"^[.\dØR]", _lead(wt)):
            continue
        dw = fill_dirs([w])[0]
        # diagonal frame for Ø only
        diag = (_diag_frame(w, dw[8] if len(dw) > 8 else None, rect)
                if symbol.strip() == "\u00d8" else None)
        if diag is not None:
            off, gap, h = diag
            if off > 0.7 * h or gap < -0.5 * h or gap > 3.0 * h:
                continue
        else:
            q = _dir_quarter(dw)
            gx0, gy0, gx1, gy1 = _rect_map(_to_frame, q, rect)
            fw = _rect_map(_to_frame, q, w)
            h = max(gy1 - gy0, 2.0)
            if abs((fw[1] + fw[3]) / 2.0 - (gy0 + gy1) / 2.0) > 0.7 * h:
                continue
            gap = fw[0] - gx1
            if gap < -0.5 * h or gap > 3.0 * h:
                continue
        if best is None or gap < best[0]:
            best = (gap, i)
    if best is not None:
        i = best[1]
        w = out[i]
        wt = str(w[4])
        dup = wt.startswith(symbol) or (
            len(symbol) == 1 and _lead(wt) == _GLYPHS.get(symbol, symbol))
        if own_token:
            if not dup:
                out.append((x0, y0, x1, y1, symbol, w[5], w[6],
                            float(w[7]) - 0.5) + tuple(w[8:]))
            return
        if not dup:
            # glyph after hole keyword
            kw = _KW_LEAD.match(wt)
            if kw and symbol.strip() not in _KW_TOKENS:
                text = wt[:kw.end()] + symbol + wt[kw.end():]
            else:
                text = symbol + wt
            out[i] = (min(x0, w[0]), min(y0, w[1]), max(x1, w[2]),
                      max(y1, w[3]), text) + tuple(w[5:])
        return
    n = len(out)
    out.append((x0, y0, x1, y1, symbol, dedup._VBLOCK + n, 0, 0))


def _geometry_symbols(page, words, cfg):
    fitz = render._fitz()
    if fitz is None:
        return words
    try:
        paths = page.get_drawings()
    except Exception:
        return words
    rm = render._rot_matrix(page)
    out = list(words)
    for p in paths:
        items = p.get("items") or []
        r = p.get("rect")
        if r is None or r.width <= 0 or r.height <= 0:
            continue
        ncurve = sum(1 for it in items if it[0] == "c")
        nline = sum(1 for it in items if it[0] == "l")
        squareish = 0.6 <= (r.width / max(r.height, 1e-6)) <= 1.6
        small = r.width <= 60 and r.height <= 60
        if small and squareish and ncurve >= 3 and 1 <= nline <= 2:
            rc = (r.x0, r.y0, r.x1, r.y1)
            if rm is not None:
                rc = render._xform_rect(rm, *rc)
            _attach_or_append(out, rc, "Ø")
    return out


def _symbol_dets(page, cfg):
    key = runtime._cache_key(page, cfg, "sym")
    hit = runtime._cache_get(key)
    if hit is not None:
        return hit
    conf = float(cfg.get("vision_sym_conf", runtime.conf_default("vision_sym_conf")))
    out = []
    for x0, y0, x1, y1, _c, ci in detect._detect_page(
            runtime._symbol_session(cfg), page, cfg, len(runtime._SYM_CLASSES), conf, tile=True):
        if 0 <= ci < len(runtime._SYM_CLASSES):
            out.append(((x0, y0, x1, y1), runtime._SYM_CLASSES[ci]))
    # drawn Ø detector missed
    phis = [e for e, t in out if t == "\u00d8"]
    for env, tok in _vector_phis(page):
        cx, cy = (env[0] + env[2]) / 2.0, (env[1] + env[3]) / 2.0
        if not any(e[0] <= cx <= e[2] and e[1] <= cy <= e[3] for e in phis):
            out.append((env, tok))
    runtime._cache_put(key, out)
    return out


def _vector_phis(page, lo=3.0, hi=30.0):
    """Vector Ø, rotation-proof unlike detector."""
    import math
    try:
        paths = page.get_drawings()
    except Exception:
        return []
    rm = render._rot_matrix(page)
    out = []
    for p in paths:
        r = p.get("rect")
        if r is None or r.width > 2 * hi or r.height > 2 * hi:
            continue
        segs = []
        for it in p.get("items") or ():
            if it[0] == "l":
                segs.append((it[1], it[2]))
            elif it[0] == "c":
                segs.append((it[1], it[4]))
        if len(segs) < 9:
            continue
        span = max(r.width, r.height)

        def ln(sg):
            return math.hypot(sg[1].x - sg[0].x, sg[1].y - sg[0].y)
        # slash may overrun circle
        arc = [sg for sg in segs if ln(sg) <= 0.3 * span]
        long_ = [sg for sg in segs if ln(sg) > 0.3 * span]
        if len(arc) < 8 or not long_:
            continue
        xs = [q.x for sg in arc for q in sg]
        ys = [q.y for sg in arc for q in sg]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if not (lo <= w <= hi and lo <= h <= hi
                and 0.75 <= w / max(h, 1e-6) <= 1.33):
            continue
        cx, cy = (max(xs) + min(xs)) / 2.0, (max(ys) + min(ys)) / 2.0
        ds = sorted(math.hypot(x - cx, y - cy) for x, y in zip(xs, ys))
        rad = ds[len(ds) // 2]
        if rad < 1.0 or sum(1 for d in ds if abs(d - rad) <= 0.12 * rad) \
                < 0.85 * len(ds):
            continue
        dirs = []
        for a, b in long_:
            L = ln((a, b))
            if L < 1.4 * rad or abs((b.x - a.x) * (a.y - cy)
                                    - (b.y - a.y) * (a.x - cx)) / L \
                    > 0.3 * rad:
                continue
            t = ((cx - a.x) * (b.x - a.x) + (cy - a.y) * (b.y - a.y)) / (L * L)
            if not 0.15 <= t <= 0.85:
                continue
            t = math.atan2(b.y - a.y, b.x - a.x) % math.pi
            if not any(min(abs(t - u), math.pi - abs(t - u)) < 0.2
                       for u in dirs):
                dirs.append(t)
        if len(dirs) != 1:
            continue
        env = (cx - rad, cy - rad, cx + rad, cy + rad)
        if rm is not None:
            env = render._xform_rect(rm, *env)
        out.append((env, "\u00d8"))
    return out


def _symbol_dets_clip(page, cfg, rect):
    sess = runtime._symbol_session(cfg)
    if sess is None:
        return []
    try:
        import numpy as np
    except Exception:
        return []
    pm = render._pixmap_clip(page, cfg, rect, cfg.get("vision_fcf_dpi", 600))
    if pm is None:
        return []
    img, s, ox, oy = pm
    imgsz = runtime._sess_imgsz(sess, cfg.get("vision_imgsz", runtime.IMGSZ_DEFAULT))
    iou = float(cfg.get("vision_nms_iou", 0.45))
    conf = float(cfg.get("vision_fcf_conf", 0.25))
    out = []
    for x0, y0, x1, y1, _c, ci in detect._run_det(sess, img, imgsz,
                                           len(runtime._SYM_CLASSES), conf, iou, np):
        if 0 <= ci < len(runtime._SYM_CLASSES):
            out.append(((x0 / s + ox, y0 / s + oy,
                         x1 / s + ox, y1 / s + oy), runtime._SYM_CLASSES[ci]))
    return out


def _dedup_syms(primary, extra, iou_thr=0.4):
    out = list(primary)
    for env2, tok2 in extra:
        b2 = (env2[0], env2[1], env2[2], env2[3], 1.0, 0)
        if not any(tok1 == tok2 and detect._iou(
                (e1[0], e1[1], e1[2], e1[3], 1.0, 0), b2) >= iou_thr
                for e1, tok1 in out):
            out.append((env2, tok2))
    return out


def _symbol_words(page, words, cfg):
    out = list(words)
    for env, tok in _symbol_dets(page, cfg):
        _attach_or_append(out, env, tok)
    return out


_ON_TEXT = 0.5


def _on_text(env, words, tok=None):
    """Glyph over text digits is re-found ink."""
    if tok is not None and tok.strip() in runtime._SYM_WRAP:
        return False
    a = max((env[2] - env[0]) * (env[3] - env[1]), 1e-6)
    for w in words or ():
        wt = str(w[4]).strip()
        # plain letters exempt
        if not wt or int(w[5]) >= dedup._VBLOCK or (wt.isascii() and wt.isalpha()):
            continue
        ix = max(0.0, min(env[2], w[2]) - max(env[0], w[0]))
        iy = max(0.0, min(env[3], w[3]) - max(env[1], w[1]))
        if ix * iy >= _ON_TEXT * a:
            return True
    return False
