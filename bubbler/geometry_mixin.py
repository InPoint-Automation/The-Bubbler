# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Page geometry: circles, line-ends, obstacles, snap, balloon placement.

from .common import RADIUS
from .scanpos import page_words, xform_pt, xform_rect


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

    @staticmethod
    def _circle_hits_rect(cx, cy, r, rc):
        qx = min(max(cx, rc[0]), rc[2])
        qy = min(max(cy, rc[1]), rc[3])
        return (qx - cx) ** 2 + (qy - cy) ** 2 < r * r

    @staticmethod
    def _circle_hits_seg(cx, cy, r, s):
        x0, y0, x1, y1 = s
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        if L2 <= 1e-9:
            qx, qy = x0, y0
        else:
            t = ((cx - x0) * dx + (cy - y0) * dy) / L2
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            qx, qy = x0 + t * dx, y0 + t * dy
        return (qx - cx) ** 2 + (qy - cy) ** 2 < r * r

    def auto_offset(self, ax, ay, page_i=None, rect=None):
        if page_i is None:
            page_i = self.page_i
        r = float(self.cfg.get("radius", RADIUS))
        g = r * 0.9
        pr = self.doc[page_i].rect
        others = [(bx, by) for _, _, _, bx, by in self.page_bubbles(page_i)]
        try:
            words, segs = self._page_obstacles(page_i)
        except Exception:
            words, segs = [], []
        pref = self.cfg.get("offset_dir", "auto")
        dirs = list(self._DIRS)
        if pref in ("n", "e", "s", "w"):
            dirs.sort(key=lambda d: 0 if d[0] == pref else 1)

        def base_pt(dx, dy, extra):
            bx_, by_ = ax, ay
            if rect is not None:
                if dx > 0:
                    bx_ = rect[2]
                elif dx < 0:
                    bx_ = rect[0]
                if dy > 0:
                    by_ = rect[3]
                elif dy < 0:
                    by_ = rect[1]
            return (bx_ + dx * (r + g + extra),
                    by_ + dy * (r + g + extra))

        def ok(cx, cy, strict):
            if cx - r < 2 or cx + r > pr.width - 2 or \
                    cy - r < 2 or cy + r > pr.height - 2:
                return False
            if any((px - cx) ** 2 + (py - cy) ** 2 < (r * 2.4) ** 2
                   for px, py in others):
                return False
            if not strict:
                return True
            rr = r * 0.92
            if any(self._circle_hits_rect(cx, cy, rr, rc) for rc in words):
                return False
            rs = r * 0.8
            if any(self._circle_hits_seg(cx, cy, rs, s) for s in segs):
                return False
            return True

        diag = 0.7071
        for ring in range(4):
            extra = ring * (r * 1.6)
            cands = [base_pt(dx, dy, extra) for _, dx, dy in dirs]
            if ring:
                cands += [base_pt(sx * diag, sy * diag, extra)
                          for sx in (1, -1) for sy in (-1, 1)]
            for cx, cy in cands:
                if ok(cx, cy, True):
                    return cx, cy
        for _, dx, dy in dirs:
            cx, cy = base_pt(dx, dy, 0)
            if ok(cx, cy, False):
                return cx, cy
        for e in range(1, 9):
            cx = min(ax + r * (1 + e) + g, pr.width - r - 2)
            cy = max(ay - r * e, r + 2)
            if ok(cx, cy, False):
                return cx, cy
        return base_pt(dirs[0][1], dirs[0][2], 0)

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
            self.set_status("snapped %s / przyciągnięto" % best[3])
        return best[1], best[2]
