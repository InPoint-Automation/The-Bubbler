# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Inspection calculator tools. Pure, mm.

import math

from .iso286 import fit_limits


def gage_ratio(band, resolution):
    """Band over resolution (x:1 rule)."""
    try:
        band, resolution = abs(float(band)), abs(float(resolution))
    except (TypeError, ValueError):
        return None
    return band / resolution if resolution else None


def pitch_diameter(d, pitch):
    """d2 = d - 0.6495 P (ISO 724)."""
    try:
        d, p = float(d), float(pitch)
    except (TypeError, ValueError):
        return None
    if d <= 0 or p <= 0:
        return None
    return d - 0.649519 * p


# ISO 965-1 Table 1 deviations (um)
_EI_G = {0.2: 17, 0.25: 18, 0.3: 18, 0.35: 19, 0.4: 19, 0.45: 20, 0.5: 20,
         0.6: 21, 0.7: 22, 0.75: 22, 0.8: 24, 1: 26, 1.25: 28, 1.5: 32,
         1.75: 34, 2: 38, 2.5: 42, 3: 48, 3.5: 53, 4: 60, 4.5: 63, 5: 71,
         5.5: 75, 6: 80, 8: 100}
_ES = {"g": {p: -v for p, v in _EI_G.items()},
       "f": {0.35: -34, 0.4: -34, 0.45: -35, 0.5: -36, 0.6: -36, 0.7: -38,
             0.75: -38, 0.8: -38, 1: -40, 1.25: -42, 1.5: -45, 1.75: -48,
             2: -52, 2.5: -58, 3: -63, 3.5: -70, 4: -75, 4.5: -80, 5: -85,
             5.5: -90, 6: -95, 8: -118},
       "e": {0.5: -50, 0.6: -53, 0.7: -56, 0.75: -56, 0.8: -60, 1: -60,
             1.25: -63, 1.5: -67, 1.75: -71, 2: -71, 2.5: -80, 3: -85,
             3.5: -90, 4: -95, 4.5: -100, 5: -106, 5.5: -112, 6: -118,
             8: -140}}

# Grade-6 Td2/TD2 (um), from ISO 965-2 limits.
_TD2_EXT = {
    (1.4, 2.8): {0.35: 63, 0.4: 67, 0.45: 71},
    (2.8, 5.6): {0.5: 75, 0.6: 85, 0.7: 90, 0.8: 95},
    (5.6, 11.2): {1: 112, 1.25: 118, 1.5: 132},
    (11.2, 22.4): {1.25: 132, 1.5: 140, 1.75: 150, 2: 160, 2.5: 170},
    (22.4, 45.0): {2: 170, 3: 200, 3.5: 212, 4: 224}}
_TD2_INT = {
    (0.99, 1.4): {0.3: 75},
    (1.4, 2.8): {0.35: 85, 0.4: 90, 0.45: 95},
    (2.8, 5.6): {0.5: 100, 0.6: 112, 0.7: 118, 0.8: 125},
    (5.6, 11.2): {1: 150, 1.25: 160, 1.5: 180},
    (11.2, 22.4): {1.25: 180, 1.5: 190, 1.75: 200, 2: 212, 2.5: 224},
    (22.4, 45.0): {2: 224, 3: 265, 3.5: 280, 4: 300}}


def _in_range(table, d, p):
    for (lo, hi), by_p in table.items():
        if lo < d <= hi:
            return by_p.get(p)
    return None


def thread_limits(d, pitch, cls):
    """Grade 6 only. None off table, never guess."""
    basic = pitch_diameter(d, pitch)
    cls = str(cls or "").strip()
    if basic is None or len(cls) != 2 or cls[0] != "6":
        return None
    d, p, pos = float(d), float(pitch), cls[1]
    if pos in "efgh":
        t = _in_range(_TD2_EXT, d, p)
        dev = 0 if pos == "h" else _ES[pos].get(p)
        if t is None or dev is None:
            return None
        top = basic + dev / 1000.0
        # micron, as ISO 965-2
        return {"basic": basic, "max": round(top, 3),
                "min": round(top - t / 1000.0, 3), "t": t, "dev": dev}
    if pos in "GH":
        t = _in_range(_TD2_INT, d, p)
        dev = 0 if pos == "H" else _EI_G.get(p)
        if t is None or dev is None:
            return None
        low = basic + dev / 1000.0
        return {"basic": basic, "min": round(low, 3),
                "max": round(low + t / 1000.0, 3), "t": t, "dev": dev}
    return None


def best_wire(pitch):
    """Touches at pitch line."""
    return 0.57735 * float(pitch)


def over_wires(d2, pitch, wire):
    """Three-wire M = d2 + 3w - 0.866025 P."""
    return float(d2) + 3.0 * float(wire) - 0.866025 * float(pitch)


def d2_from_wires(m, pitch, wire):
    return float(m) - 3.0 * float(wire) + 0.866025 * float(pitch)


RZ_PER_RA = 4.0     # rule of thumb


def rz_from_ra(ra, k=RZ_PER_RA):
    return float(ra) * k


def ra_from_rz(rz, k=RZ_PER_RA):
    return float(rz) / k


def taper(big, small, length):
    """Diameters and length -> {"included", "half" (deg), "ratio" (1:x)}."""
    big, small, length = float(big), float(small), float(length)
    dd = abs(big - small)
    if length <= 0 or dd == 0:
        return None
    half = math.degrees(math.atan(dd / (2.0 * length)))
    return {"included": 2.0 * half, "half": half, "ratio": length / dd}


def true_position(dx, dy, tol, size=None, mmc=None, lmc=None, mod="RFS"):
    """Out-of-size part earns no bonus."""
    tp = 2.0 * math.hypot(float(dx), float(dy))
    bonus, size_ok = 0.0, True
    if mod in ("MMC", "LMC"):
        if size is None or mmc is None or lmc is None:
            raise ValueError("MMC and LMC need the size and both limits")
        s, a, b = float(size), float(mmc), float(lmc)
        lo, hi = min(a, b), max(a, b)
        size_ok = lo - 1e-12 <= s <= hi + 1e-12
        if size_ok:
            bonus = abs(s - a) if mod == "MMC" else abs(b - s)
    allowed = float(tol) + bonus
    return {"tp": tp, "bonus": bonus, "allowed": allowed, "size_ok": size_ok,
            "ok": size_ok and tp <= allowed + 1e-12}


def to_bilateral(nominal, upper, lower):
    """Lower signed. -> (mid, half)."""
    hi = float(nominal) + float(upper)
    lo = float(nominal) + float(lower)
    return (hi + lo) / 2.0, (hi - lo) / 2.0


def to_unilateral(nominal, half, side="+"):
    """Whole band one side. `+` puts lower limit at nominal."""
    n, h = float(nominal), abs(float(half))
    if side == "+":
        return n - h, 2.0 * h, 0.0
    return n + h, 0.0, -2.0 * h


def fit(nominal, hole=None, shaft=None):
    """ISO 286 fit. Clearance positive, interference negative."""
    out = {}
    for key, code in (("hole", hole), ("shaft", shaft)):
        if not code:
            continue
        lim = fit_limits(float(nominal), code)
        if lim is None:
            return None
        up, dn = lim
        out[key] = {"code": code, "upper": up, "lower": dn,
                    "max": float(nominal) + up, "min": float(nominal) + dn}
    if "hole" in out and "shaft" in out:
        h, s = out["hole"], out["shaft"]
        out["clear_max"] = h["max"] - s["min"]
        out["clear_min"] = h["min"] - s["max"]
    return out or None
