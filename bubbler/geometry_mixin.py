# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Page geometry: circles, line-ends, obstacles, snap, balloon placement.

from .common import (RADIUS, SHAPES, base_of, shape_body, shape_extent,
                     shape_radius, shape_support, tier_shape)
from .scanpos import page_words, xform_pt, xform_rect
from .i18n import tr

DIAG = 0.7071067811865476
# fixed order = deterministic ties
DIRS = (("e", (1.0, 0.0)), ("w", (-1.0, 0.0)),
        ("s", (0.0, 1.0)), ("n", (0.0, -1.0)),
        ("se", (DIAG, DIAG)), ("sw", (-DIAG, DIAG)),
        ("ne", (DIAG, -DIAG)), ("nw", (-DIAG, -DIAG)))
CARDINALS = ("e", "w", "s", "n")

W_DIST = 1.0        # per r off ring
W_TIP = 0.8         # per 4r visible leader
W_WORD = 12.0       # balloon fully on text
W_WORDHIT = 6.0     # balloon touches text
W_STUB = 2.0        # leader swallowed by balloon
W_TUCK = 2.0        # per r inside ring
W_SEG = 3.0         # per thick stroke touched
W_BUB = 20.0        # per r into neighbour
W_LEADHIT = 3.0     # balloon parked on leader
W_XLEAD = 2.0       # leader crossing leader
W_XWORD = 1.5       # leader crossing text
W_PREF = 2.5        # not preferred side
W_DIAG = 0.4        # diagonal not cardinal
W_PERP = 0.5        # per r sideways shift
W_NEIGH = 1.2       # differs from nearby balloons
W_OFFPAGE = 1000.0  # per r off sheet
MAX_STEPS = 8       # 4r travel each way
NEIGH_REACH = 150.0  # pt neighbour cutoff
MIN_LEADER = 2.5    # pt min visible leader
GAP_F = 0.6         # GAP_F*r off drawn outline
BUB_CLEAR = 0.4     # per r between outlines
# widest reach per r
MAX_EXT = max(shape_extent(s_, 1.0) for s_ in SHAPES)
# rest then out-in turns
_BAND = tuple(v for i in range(MAX_STEPS + 1) for v in ((i,) if i == 0
                                                        else (i, -i)))


def rect_overlap_frac(cx, cy, r, rc):
    """Balloon box over rect 0..1"""
    ox = min(cx + r, rc[2]) - max(cx - r, rc[0])
    oy = min(cy + r, rc[3]) - max(cy - r, rc[1])
    if ox <= 0.0 or oy <= 0.0:
        return 0.0
    return (ox * oy) / (4.0 * r * r)


def circle_hits_rect(cx, cy, r, rc):
    qx = min(max(cx, rc[0]), rc[2])
    qy = min(max(cy, rc[1]), rc[3])
    return (qx - cx) ** 2 + (qy - cy) ** 2 < r * r


def circle_hits_seg(cx, cy, r, s):
    x0, y0, x1, y1 = s
    dx, dy = x1 - x0, y1 - y0
    ll = dx * dx + dy * dy
    if ll <= 1e-9:
        qx, qy = x0, y0
    else:
        t = ((cx - x0) * dx + (cy - y0) * dy) / ll
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        qx, qy = x0 + t * dx, y0 + t * dy
    return (qx - cx) ** 2 + (qy - cy) ** 2 < r * r


def seg_hits_rect(x0, y0, x1, y1, rc):
    """Liang-Barsky clip test"""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - rc[0]), (dx, rc[2] - x0),
                 (-dy, y0 - rc[1]), (dy, rc[3] - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return False
            if t > t0:
                t0 = t
        else:
            if t < t0:
                return False
            if t < t1:
                t1 = t
    return True


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def seg_hits_seg(a, b):
    """Proper segment intersection"""
    x1, y1, x2, y2 = a
    x3, y3, x4, y4 = b
    d1 = _cross(x2 - x1, y2 - y1, x3 - x1, y3 - y1)
    d2 = _cross(x2 - x1, y2 - y1, x4 - x1, y4 - y1)
    d3 = _cross(x4 - x3, y4 - y3, x1 - x3, y1 - y3)
    d4 = _cross(x4 - x3, y4 - y3, x2 - x3, y2 - y3)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def leader_tip(ax, ay, bx, by, words, r, min_len=MIN_LEADER):
    """Anchor walked out of ink toward balloon"""
    dx, dy = bx - ax, by - ay
    ll = (dx * dx + dy * dy) ** 0.5
    if ll < 1e-6:
        return (ax, ay)
    ux, uy = dx / ll, dy / ll
    limit = ll - r - min_len
    if limit <= 0.0:
        return (ax, ay)
    if not words:
        return (ax, ay)
    step = max(1.0, r * 0.2)
    d = 0.0
    while d <= limit:
        px, py = ax + ux * d, ay + uy * d
        if not any(rc[0] <= px <= rc[2] and rc[1] <= py <= rc[3]
                   for rc in words):
            return (px, py)
        d += step
    return (ax + ux * limit, ay + uy * limit)


def _near(items, box, key):
    out = []
    for it in items:
        x0, y0, x1, y1 = key(it)
        if x1 < box[0] or x0 > box[2] or y1 < box[1] or y0 > box[3]:
            continue
        out.append(it)
    return out


def placement_context(ax, ay, rect, occ, r, pref="auto", shape="circle"):
    """Prefiltered occupancy + neighbour direction weights"""
    occ = occ or {}
    rad = shape_radius(shape, r)
    self_reach = shape_extent(shape, r)
    g = r * GAP_F                      # page scale not shape
    reach = rad + g + MAX_STEPS * (r * 0.5) + self_reach + MAX_EXT * r + 4.0
    bx0 = (rect[0] if rect else ax) - reach
    by0 = (rect[1] if rect else ay) - reach
    bx1 = (rect[2] if rect else ax) + reach
    by1 = (rect[3] if rect else ay) + reach
    box = (bx0, by0, bx1, by1)
    words = _near(occ.get("words") or (), box, lambda rc: rc)
    segs = _near(occ.get("segs") or (), box,
                 lambda s: (min(s[0], s[2]), min(s[1], s[3]),
                            max(s[0], s[2]), max(s[1], s[3])))
    centres, leads = [], []
    dirw = {}
    total_w = 0.0
    for b in (occ.get("balloons") or ()):
        oax, oay, obx, oby = b[:4]
        oshape = b[4] if len(b) > 4 else "circle"      # drawn size not r
        if obx is None or oby is None:
            continue
        centres.append((obx, oby, shape_extent(oshape, r)))
        if oax is None or oay is None:
            continue
        if (oax, oay) == (obx, oby):
            continue
        tx, ty = leader_tip(oax, oay, obx, oby, words,
                            shape_radius(oshape, r))
        leads.append((tx, ty, obx, oby))
        d = ((oax - ax) ** 2 + (oay - ay) ** 2) ** 0.5
        if d > NEIGH_REACH:
            continue
        ux, uy = obx - oax, oby - oay
        ln = (ux * ux + uy * uy) ** 0.5 or 1.0
        w = 1.0 / (1.0 + d / 60.0)
        dirw[(ux / ln, uy / ln)] = dirw.get((ux / ln, uy / ln), 0.0) + w
        total_w += w
    centres = _near(centres, box, lambda p: (p[0], p[1], p[0], p[1]))
    return {"words": words, "segs": segs, "centres": centres,
            "leads": leads, "dirw": dirw, "total_w": total_w,
            "page": occ.get("page"), "pref": pref, "r": r, "g": g,
            "rad": rad, "reach": self_reach, "shape": shape,
            "body": shape_body(shape, r),
            "ax": ax, "ay": ay, "rect": rect}


def _support_toward(ctx, vx, vy):
    """Drawn reach toward (vx, vy)"""
    ln = (vx * vx + vy * vy) ** 0.5
    if ln < 1e-9:
        return ctx.get("rad", ctx["r"])
    return shape_support(ctx.get("shape") or "circle", ctx["r"],
                         vx / ln, vy / ln)


def placement_cost(cx, cy, dname, dvec, dist, perp, ctx):
    """Pure cost of one balloon spot"""
    r = ctx["r"]                      # config radius cost scale
    rad = ctx.get("rad", r)           # drawn radius
    reach = ctx.get("reach", rad)     # outermost points
    body = ctx.get("body", rad * 0.92)   # covers ink
    # tuck penalty per r
    cost = W_DIST * (abs(dist) / r) + W_TUCK * (max(0.0, -dist) / r) \
        + W_PERP * (abs(perp) / r)
    page = ctx.get("page")
    if page:
        over = max(0.0, 2.0 + reach - cx, 2.0 + reach - cy,
                   cx + reach + 2.0 - page[0], cy + reach + 2.0 - page[1])
        if over > 0:
            cost += W_OFFPAGE * (over / r)
    frac = 0.0
    for rc in ctx["words"]:
        frac += rect_overlap_frac(cx, cy, body, rc)
    # touching text is expensive
    if frac > 0.0:
        cost += W_WORDHIT + W_WORD * min(1.0, frac)
    nseg = 0
    for s in ctx["segs"]:
        if circle_hits_seg(cx, cy, rad * 0.8, s):
            nseg += 1
            if nseg >= 3:
                break
    cost += W_SEG * nseg
    for c in ctx["centres"]:
        px, py = c[0], c[1]
        # outline to outline
        sep = reach + (c[2] if len(c) > 2 else r) + BUB_CLEAR * r
        d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
        if d < sep:
            cost += W_BUB * ((sep - d) / r)
    ax, ay = ctx["ax"], ctx["ay"]
    # leader enters anchor side
    sup = _support_toward(ctx, ax - cx, ay - cy)
    tx, ty = leader_tip(ax, ay, cx, cy, ctx["words"], sup)
    tip_len = max(0.0, ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5 - sup)
    cost += W_TIP * (tip_len / (4.0 * r))
    if tip_len < MIN_LEADER:
        cost += W_STUB * (1.0 - tip_len / MIN_LEADER)
    if tip_len > 0.5:
        nx = 0
        for rc in ctx["words"]:
            if seg_hits_rect(tx, ty, cx, cy, rc):
                nx += 1
                if nx >= 4:
                    break
        cost += W_XWORD * nx
        nl = 0
        for ld in ctx["leads"]:
            if seg_hits_seg((tx, ty, cx, cy), ld):
                nl += 1
                if nl >= 3:
                    break
        cost += W_XLEAD * nl
    for ld in ctx["leads"]:
        if circle_hits_seg(cx, cy, rad, ld):
            cost += W_LEADHIT
            break
    pref = ctx["pref"]
    if pref in CARDINALS and dname != pref:
        cost += W_PREF
    if dname not in CARDINALS:
        cost += W_DIAG
    if ctx["total_w"] > 0:
        match = 0.0
        for (ux, uy), w in ctx["dirw"].items():
            dot = dvec[0] * ux + dvec[1] * uy
            match += w * max(0.0, dot)
        cost += W_NEIGH * (1.0 - match / ctx["total_w"])
    return cost


def _off_blocked(px, py, dx, dy, body, rc):
    """Ray offsets where body box touches rc"""
    lo, hi = -1e18, 1e18
    for p, c0, c1, q in ((dx, rc[0] - body, rc[2] + body, px),
                         (dy, rc[1] - body, rc[3] + body, py)):
        if abs(p) < 1e-12:
            if not (c0 < q < c1):
                return None
            continue
        a, b = (c0 - q) / p, (c1 - q) / p
        if a > b:
            a, b = b, a
        lo, hi = max(lo, a), min(hi, b)
    return None if lo >= hi else (lo, hi)


def _clear_offsets(px, py, dx, dy, body, words, off0, floor, keep=2):
    """Offsets nearest ring where body clears every word"""
    blocked = []
    for rc in words:
        iv = _off_blocked(px, py, dx, dy, body, rc)
        if iv is not None:
            blocked.append(iv)
    if not blocked:
        return ()
    eps = 0.01
    cand = [off0]
    for lo, hi in blocked:
        cand.append(lo - eps)
        cand.append(hi + eps)
    ok = []
    for off in cand:
        if off < floor:
            continue
        if any(lo <= off <= hi for lo, hi in blocked):
            continue
        ok.append(off)
    ok.sort(key=lambda o: (abs(o - off0), o))
    return tuple(ok[:keep])


def rank_placements(ax, ay, rect, occ, r, pref="auto", limit=8,
                    shape="circle"):
    """Deterministic scored candidates cheapest first"""
    ctx = placement_context(ax, ay, rect, occ, r, pref, shape)
    g, body = ctx["g"], ctx["body"]
    step = r * 0.5
    out = []
    best = None
    edges = {}
    # ring first then out-in
    for i in _BAND:
        dist = i * step
        if best is not None and best < W_DIST * (abs(dist) / r):
            break                                  # wider bands cost more
        for dname, (dx, dy) in DIRS:
            ex, ey = ax, ay
            if rect is not None:
                if dx > 0:
                    ex = rect[2]
                elif dx < 0:
                    ex = rect[0]
                if dy > 0:
                    ey = rect[3]
                elif dy < 0:
                    ey = rect[1]
            back = _support_toward(ctx, -dx, -dy)   # reach on leader side
            edges[dname] = (ex, ey, back)
            off = back + g + i * step
            if off < body:                          # never swallow anchor
                if i >= 0 or back + g + (i + 1) * step < body:
                    continue                        # floor already offered
                off, dist = body, body - (back + g)
            for pk in (0, 1, -1, 2, -2):
                perp = pk * step
                cx = ex + dx * off - dy * perp
                cy = ey + dy * off + dx * perp
                c = placement_cost(cx, cy, dname, (dx, dy), dist, perp, ctx)
                out.append((c, cx, cy, dname))
                if best is None or c < best:
                    best = c
    for dname, (dx, dy) in DIRS:                    # snap into gap
        got = edges.get(dname)
        if got is None:
            continue
        ex, ey, back = got
        off0 = back + g
        far = off0 + MAX_STEPS * step
        for pk in (0, 1, -1, 2, -2):
            perp = pk * step
            px, py = ex - dy * perp, ey + dx * perp
            for off in _clear_offsets(px, py, dx, dy, body, ctx["words"],
                                      off0, body):
                if off > far:
                    continue
                cx, cy = px + dx * off, py + dy * off
                c = placement_cost(cx, cy, dname, (dx, dy),
                                   off - off0, perp, ctx)
                out.append((c, cx, cy, dname))
    out.sort(key=lambda t: t[0])
    return out[:limit]


def best_placement(ax, ay, rect, occ, r, pref="auto", shape="circle"):
    """Cheapest balloon centre per anchor"""
    ranked = rank_placements(ax, ay, rect, occ, r, pref, limit=1, shape=shape)
    if not ranked:
        return (ax + shape_support(shape, r, 1.0, 0.0) + r * GAP_F, ay)
    return (ranked[0][1], ranked[0][2])


def noleader_center(ax, ay, rect, r, shape="circle", pref="auto"):
    """Centre for a leaderless balloon, pushed just outside the callout box."""
    if not rect:
        return ax, ay
    x0, y0, x1, y1 = rect
    cxr, cyr = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    d = {"n": (0.0, -1.0), "s": (0.0, 1.0),
         "e": (1.0, 0.0), "w": (-1.0, 0.0)}.get(pref)
    if d is None:                         # away from box centre
        vx, vy = ax - cxr, ay - cyr
        if abs(vx) >= abs(vy):
            d = (1.0, 0.0) if vx >= 0 else (-1.0, 0.0)
        else:
            d = (0.0, 1.0) if vy >= 0 else (0.0, -1.0)
    dx, dy = d
    gap = shape_support(shape, r, dx, dy) + GAP_F * r
    if dx:
        return (x1 if dx > 0 else x0) + dx * gap, ay
    return ax, (y1 if dy > 0 else y0) + dy * gap


class GeometryMixin:
    def _page_obstacles(self, page_i=None):
        if page_i is None:
            page_i = self.page_i
        if not hasattr(self, "_obs_cache"):
            self._obs_cache = {}
        if page_i in self._obs_cache:
            return self._obs_cache[page_i]
        rects = [(w[0], w[1], w[2], w[3])
                 for w in page_words(self.doc[page_i])]
        _, _, obs = self._page_geom(page_i)
        segs = obs.get("segs", [])
        rects += obs.get("rects", [])
        out = (rects, segs)
        self._obs_cache[page_i] = out
        return out

    _circle_hits_rect = staticmethod(circle_hits_rect)
    _circle_hits_seg = staticmethod(circle_hits_seg)

    def place_bubble(self, ax, ay, page_i=None, rect=None, lead=None,
                     tier=None):
        """Balloon centre + leader flag in step"""
        if lead is None:
            lead = self.use_leaders()
        if not lead:
            r = max(1.0, float(self.cfg.get("radius", RADIUS)))
            bx, by = noleader_center(ax, ay, rect, r,
                                     tier_shape(tier, self.cfg),
                                     self.cfg.get("offset_dir", "auto"))
            return bx, by, False
        bx, by = self.auto_offset(ax, ay, page_i=page_i, rect=rect, tier=tier)
        return bx, by, True

    def _bubble_tiers(self, page_i):
        """base number -> tier per neighbour"""
        out = {}
        for d in (getattr(self, "ledger", None) or ()):
            if d.get("page") != page_i:
                continue
            b = base_of(d.get("bubble"))
            if b not in out:
                out[b] = d.get("tier")
        return out

    def auto_offset(self, ax, ay, page_i=None, rect=None, tier=None):
        if page_i is None:
            page_i = self.page_i
        r = max(1.0, float(self.cfg.get("radius", RADIUS)))   # r=0 div-0
        try:
            pr = self.doc[page_i].rect
            page = (float(pr.width), float(pr.height))
        except Exception:
            page = None
        try:
            words, segs = self._page_obstacles(page_i)
        except Exception:
            words, segs = [], []
        tiers = self._bubble_tiers(page_i)
        balloons = [(oax, oay, obx, oby,
                     tier_shape(tiers.get(n), self.cfg))
                    for n, oax, oay, obx, oby in self.page_bubbles(page_i)]
        occ = {"words": words, "segs": segs, "balloons": balloons,
               "page": page}
        pref = self.cfg.get("offset_dir", "auto")
        return best_placement(ax, ay, rect, occ, r, pref,
                              tier_shape(tier, self.cfg))

    def _leader_target(self, page_i, bx, by, ax, ay):
        """Leader end point"""
        r = float(self.cfg.get("radius", RADIUS))
        key = (page_i, round(bx, 1), round(by, 1), round(ax, 1), round(ay, 1),
               round(r, 1))
        cache = self.__dict__.setdefault("_leadtrim_cache", {})
        if key in cache:
            return cache[key]
        try:
            words, _segs = self._page_obstacles(page_i)
        except Exception:
            words = []
        tip = leader_tip(ax, ay, bx, by, words, r)
        cache[key] = tip
        return tip

    def _page_geom(self, page_i=None):
        if page_i is None:
            page_i = self.page_i
        if not hasattr(self, "_geom_cache"):
            self._geom_cache = {}
        hit = self._geom_cache.get(page_i)
        if hit is not None:
            return hit
        circles, ends = [], []
        page = self.doc[page_i]
        try:
            paths = page.get_drawings()
        except Exception:
            paths = []
        try:
            prot = int(getattr(page, "rotation", 0) or 0) % 360
        except (TypeError, ValueError):
            prot = 0
        rm = page.rotation_matrix if prot else None
        GRID = 8.0
        egrid = {}
        try:
            OBS_W = float(self.cfg.get("obstacle_min_w", 0.5))
        except (TypeError, ValueError):
            OBS_W = 0.5
        obs_segs, obs_rects = [], []
        for p in paths:
            items = p.get("items") or []
            ncurve = sum(1 for it in items if it[0] == "c")
            r = p.get("rect")
            ptype = p.get("type") or ""
            pw = p.get("width") or 0.0
            filled = "f" in ptype
            thick = (not filled) and pw >= OBS_W
            if filled and r is not None and len(obs_rects) < 4000:
                rc = (r.x0, r.y0, r.x1, r.y1)
                if rm is not None:
                    rc = xform_rect(rm, *rc)
                obs_rects.append(rc)
            if r is not None and ncurve >= 3 and \
                    len(items) == ncurve and r.width > 0.5 and \
                    0.8 <= (r.width / max(r.height, 1e-6)) <= 1.25 and \
                    r.width <= 120:
                cx = (r.x0 + r.x1) / 2.0
                cy = (r.y0 + r.y1) / 2.0
                if rm is not None:
                    cx, cy = xform_pt(rm, cx, cy)
                circles.append((cx, cy, (r.width + r.height) / 4.0))
            for it in items:
                if it[0] != "l" or len(ends) >= 30000:
                    continue
                p1, p2 = it[1], it[2]
                x1, y1, x2, y2 = p1.x, p1.y, p2.x, p2.y
                if rm is not None:
                    x1, y1 = xform_pt(rm, x1, y1)
                    x2, y2 = xform_pt(rm, x2, y2)
                if thick and len(obs_segs) < 12000:
                    obs_segs.append((x1, y1, x2, y2))
                for px, py in ((x1, y1), (x2, y2)):
                    ends.append((px, py))
                    egrid.setdefault((int(px // GRID), int(py // GRID)),
                                     []).append((px, py))
        geom = (circles[:5000], egrid,
                {"segs": obs_segs, "rects": obs_rects})
        self._geom_cache[page_i] = geom
        return geom

    def _snap_point(self, x, y, quiet=False):
        if not self.cfg.get("snap_geom", True):
            return x, y
        circles, egrid, _obs = self._page_geom()
        tol_c = 9.0 / max(self.zoom, 0.3)
        best = None
        for cx, cy, r in circles:
            d2 = (cx - x) ** 2 + (cy - y) ** 2
            if d2 <= max(tol_c, min(r, 25.0)) ** 2 and \
                    (best is None or d2 < best[0]):
                best = (d2, cx, cy, "⊕ hole center")
        if best is None:
            tol_e = 5.0 / max(self.zoom, 0.3)
            t2 = tol_e * tol_e
            GRID = 8.0
            gx, gy = int(x // GRID), int(y // GRID)
            reach = max(1, int(tol_e // GRID) + 1)
            for ix in range(gx - reach, gx + reach + 1):
                for iy in range(gy - reach, gy + reach + 1):
                    for ex, ey in egrid.get((ix, iy), ()):
                        d2 = (ex - x) ** 2 + (ey - y) ** 2
                        if d2 <= t2 and (best is None or d2 < best[0]):
                            best = (d2, ex, ey, "⌖ line end")
        if best is None:
            return x, y
        if not quiet:
            self.set_status(tr('snapped %s') % best[3])
        return best[1], best[2]
