# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Constants, category model, tolerance helpers.
import math
import os
import re

APP_NAME = "Bubbler"
ORG = "InPoint Automation Sp. z o.o."
VERSION = "0.2.1"

RADIUS = 9.0
FONTSZ = 10.0
RED = (0.85, 0.1, 0.1)
WHITE = (1, 1, 1)

TIER_RGB = {
    "": RED,
    "red": RED,
    "blue": (0.13, 0.4, 1.0),
    "green": (0.13, 0.55, 0.24),
}
TIER_SHAPE = {"red": "circle", "blue": "square", "green": "triangle"}
SHAPES = ["circle", "square", "triangle", "diamond", "star"]


def tier_rgb(tier):
    return TIER_RGB.get(tier or "", RED)


def tier_for_type(type_, cfg, fallback=""):
    if fallback:
        return fallback
    if cfg and cfg.get("type_tier_auto"):
        t = (cfg.get("type_tier_map") or {}).get(type_)
        if t in TIERS:
            return t
    return fallback


def tier_shape(tier, cfg=None):
    if cfg is not None:
        if not cfg.get("tier_shapes", True):
            return "circle"
        s = (cfg.get("tier_shape_map") or {}).get(tier or "")
        if s in SHAPES:
            return s
    return TIER_SHAPE.get(tier or "", "circle")


def bubble_shape_points(shape, cx, cy, rad):
    if shape == "square":
        return [(cx - rad, cy - rad), (cx + rad, cy - rad),
                (cx + rad, cy + rad), (cx - rad, cy + rad)]
    if shape == "triangle":
        r = rad * 1.15
        return [(cx, cy - r), (cx - r * 0.87, cy + r * 0.5),
                (cx + r * 0.87, cy + r * 0.5)]
    if shape == "diamond":
        r = rad * 1.28
        return [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    if shape == "star":
        pts, ro, ri = [], rad * 1.35, rad * 0.55
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rr = ro if i % 2 == 0 else ri
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        return pts
    return None

LEADER_EXITS = {"n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0)}
SHEET = "Inspection"
FIRST_ROW = 11
LAST_ROW = 310

TYPES = ["dim", "hole", "thread", "thru", "slot", "depth", "position",
         "GD&T", "finish"]
TIERS = ["", "red", "blue", "green"]

KIND_ATOMIC = "atomic"
KIND_STACKED = "stacked"
KIND_CONTAINER = "container"
KIND_META = "meta"
KINDS = (KIND_ATOMIC, KIND_STACKED, KIND_CONTAINER, KIND_META)

ADMIT = {
    "linear": {"Ø", "R"},
    "hole": {"Ø", "R", "DEEP", "CBORE", "CSINK"},
    "gdt": {"Ø", "⌖", "▱", "◯", "⌭", "⟂", "∥", "∠", "◎", "⌒", "⌓", "⌰", "↗"},
    "finish": {"Ra"},
    "datum": set(),
    None: None,
}

CATEGORY = {
    "dim_tol":               (KIND_ATOMIC,    "dim",     "linear"),
    "hole_note":             (KIND_STACKED,   "hole",    "hole"),
    "hole_table":            (KIND_CONTAINER, "hole",    "hole"),
    "surface_finish":        (KIND_ATOMIC,    "finish",  "finish"),
    "feature_control_frame": (KIND_CONTAINER, "GD&T",    "gdt"),
    "datum_feature":         (KIND_ATOMIC,    "GD&T",    "datum"),
    "gentol_block":          (KIND_META,      None,      None),
    "note":                  (KIND_META,      None,      None),
}


SIMPLE_TPS = frozenset({"LINEAR", "DIAMETER", "RADIUS", "ANGLE", "DEPTH",
                        "GDT", "FIT"})
SIMPLE_REGION_CLASSES = frozenset({"dim_tol", "feature_control_frame",
                                   "datum_feature"})


def is_simple(cfg):
    return bool(cfg) and cfg.get("mode") == "simple"


def mode_admits_tp(tp, cfg):
    return not is_simple(cfg) or tp in SIMPLE_TPS


def mode_admits_region(cls, cfg):
    return not is_simple(cfg) or cls in SIMPLE_REGION_CLASSES


def admits(constraint, token):
    allow = ADMIT.get(constraint)
    if not allow:
        return False
    return token.strip() in allow


_FRAC_RE = re.compile(r"^(?:(?P<w>\d+)[-\s]+)?(?P<n>\d+)/(?P<d>\d+)$")


def fnum(s):
    s = (s or "").strip().replace(",", ".")
    if s == "":
        return None
    m = _FRAC_RE.match(s)
    if m:
        den = float(m.group("d"))
        if den == 0:
            raise ValueError("zero denominator")
        return float(m.group("w") or 0) + float(m.group("n")) / den
    return float(s)


def dp_of(val):
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip().replace(",", ".")
        if not s:
            return None
        return len(s.split(".", 1)[1]) if "." in s else 0
    s = "%g" % float(val)
    return len(s.split(".", 1)[1]) if "." in s else 0


def dp_tol(val, cfg):
    if not cfg or not cfg.get("dp_on"):
        return None
    d = dp_of(val)
    if d is None:
        return None
    if cfg.get("units") == "asme_inch":
        tols = cfg.get("dp_tols_inch") or {}
        cap = 4                          # inch reaches .XXXX
    else:
        tols = cfg.get("dp_tols") or {}
        cap = 3                          # mm clamps at 3
    t = tols.get(str(min(d, cap)))
    try:
        t = float(t)
    except (TypeError, ValueError):
        return None
    return t if t > 0 else None


def base_of(bubble):
    # leading digits only
    m = re.match(r"\d+", str(bubble))
    return int(m.group(0)) if m else 0


def qc_path(pdf_path, suffix, subdir="qc", legacy=True):
    """Output path for a drawing sidecar. `qc/` subdir, sibling if legacy exists.

    Pure path math (one isfile probe). Caller creates the dir lazily.
    """
    base = os.path.splitext(pdf_path)[0]
    sibling = base + suffix
    if not subdir:
        return sibling
    if legacy and os.path.isfile(sibling):
        return sibling
    name = os.path.basename(base) + suffix
    return os.path.join(os.path.dirname(pdf_path), subdir, name)


def tol_text(d):
    if d.get("tol_sym") not in (None, ""):
        return u"\u00b1%g" % d["tol_sym"]
    tmax, tmin = d.get("tol_max"), d.get("tol_min")
    if tmax is None and tmin is None:
        return ""
    val = tmax if tmax is not None else 0.0
    val2 = tmin if tmin is not None else 0.0
    hi, lo = max(val, val2), min(val, val2)
    return "%s/%s" % ("0" if hi == 0 else "%+g" % hi,
                      "0" if lo == 0 else "%+g" % lo)


def limits_of(d):
    """(low, high) acceptance limits of a row, or None when unknown."""
    nom = d.get("nominal")
    if nom is None:
        return None
    if d.get("tol_sym") is not None:
        s = abs(d["tol_sym"])
        return (nom - s, nom + s)
    tmax, tmin = d.get("tol_max"), d.get("tol_min")
    if tmax is None and tmin is None:
        return None
    hi = tmax if tmax is not None else 0.0
    lo = tmin if tmin is not None else 0.0
    return (nom + min(lo, hi), nom + max(lo, hi))


def latest_op(ops):
    """(name, record) of the op with the newest ts, or None. ISO ts sorts."""
    if not ops:
        return None
    items = sorted(ops.items(), key=lambda kv: str(kv[1].get("ts") or ""))
    return items[-1]


def band_center(d):
    """Midpoint of the acceptance band (nominal when there is no band)."""
    lim = limits_of(d)
    if lim is not None:
        return (lim[0] + lim[1]) / 2.0
    return d.get("nominal")


def _as_float(s):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return None


def worst_reading(values, d):
    """Worst of several qty readings"""
    vals = [str(v).strip() for v in (values or []) if str(v).strip() != ""]
    if not vals:
        return None
    for v in vals:
        if v.upper() in _NOGO_WORDS:
            return v
    numeric = [(v, _as_float(v)) for v in vals]
    numeric = [(v, f) for v, f in numeric if f is not None]
    if not numeric:
        return vals[0]
    c = band_center(d)
    if c is None:
        c = sum(f for _, f in numeric) / len(numeric)
    return max(numeric, key=lambda vf: abs(vf[1] - c))[0]


def mirror_measured(d):
    ops = d.get("ops")
    if not ops:
        return d.get("measured")
    best = latest_op(ops)
    rec = best[1] if best else {}
    readings = rec.get("readings")
    d["measured"] = (worst_reading(readings, d) if readings
                     else rec.get("measured"))
    return d["measured"]


_NOGO_WORDS = ("NOGO", "NO-GO", "NO GO", "NOK", "FAIL", "NIE")
_GO_WORDS = ("GO", "OK", "TAK", "PASS")


def measure_state(d):
    """Row inspection state: none | in | out | go | nogo."""
    m = d.get("measured")
    if m in (None, ""):
        return "none"
    s = str(m).strip().upper()
    if s in _GO_WORDS:
        return "go"
    if s in _NOGO_WORDS:
        return "nogo"
    return "out" if out_of_tol(d) else "in"


def out_of_tol(d):
    m = d.get("measured")
    if m in (None, ""):
        return False
    s = str(m).strip()
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        return s.upper() in _NOGO_WORDS
    lim = limits_of(d)
    if lim is None:
        return False
    return not (lim[0] - 1e-9 <= v <= lim[1] + 1e-9)


def oot_rows(ledger, cfg=None):
    """Ordered out-of-tol rows (measured OOT or NOGO) as flat report dicts."""
    rows = []
    for d in ledger:
        st = measure_state(d)
        if not (out_of_tol(d) or st == "nogo"):
            continue
        op = latest_op(d.get("ops"))
        rows.append({
            "bubble": d.get("bubble", ""),
            "base": base_of(d.get("bubble", "")),
            "page": d.get("page"),
            "nominal": d.get("nominal"),
            "tol": tol_text(d),
            "measured": d.get("measured"),
            "op": op[0] if op else "",
            "gage": (op[1].get("gage") if op else None) or d.get("gage") or "",
            "tier": d.get("tier", ""),
            "state": st,
        })
    rows.sort(key=lambda r: (base_of(r["bubble"]), str(r["bubble"])))
    return rows


def oot_summary(ledger, cfg=None):
    """{rows, n_oot, n_critical}. Critical = red-tier OOT (matches status bar)."""
    rows = oot_rows(ledger, cfg)
    n_crit = sum(1 for r in rows if r.get("tier") == "red")
    return {"rows": rows, "n_oot": len(rows), "n_critical": n_crit}
