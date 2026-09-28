# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Constants, category model, tolerance helpers.
import math
import os
import re

from .config import (gentol_ladder, gentol_auto, units_of, ops_seq,
                     OPS_DEFAULT)
from .units import NOMINAL_DP

APP_NAME = "Bubbler"
ORG = "InPoint Automation Sp. z o.o."
VERSION = "0.3.1"

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
# no-cfg fallback
TIER_SHAPE = {"red": "circle", "blue": "star", "green": "diamond"}
SHAPES = ["circle", "square", "triangle", "diamond", "star"]
SHAPE_EXTENT = {"circle": 1.0, "square": 1.415, "triangle": 1.15,
                "diamond": 1.28, "star": 1.35}

# one size every tier
SHAPE_GROW = {"circle": 1.05, "square": 1.0, "triangle": 1.80,
              "diamond": 1.08, "star": 1.30}

# centres cap height
TEXT_TOP = 0.724

# ink-covering core
BODY_F = 0.92
REF_DIGITS = 3.0


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


def shape_radius(shape, rad):
    """Drawn radius of `shape` grown so number never shrinks."""
    return rad * SHAPE_GROW.get(shape or "circle", 1.0)


def shape_extent(shape, rad):
    return shape_radius(shape, rad) * SHAPE_EXTENT.get(shape or "circle", 1.0)


def widest_extent(rad, cfg=None):
    if cfg is None:
        shapes = set(TIER_SHAPE.values())
    elif not cfg.get("tier_shapes", True):
        shapes = {"circle"}
    else:
        shapes = set((cfg.get("tier_shape_map") or TIER_SHAPE).values())
    return max([shape_extent(s, rad) for s in shapes] or [rad])


def shape_text_rect(cx, cy, rad, fsz):
    w = max(rad, fsz * 1.2)
    return (cx - w, cy - TEXT_TOP * fsz, cx + w, cy + rad + fsz)


def bubble_shape_points(shape, cx, cy, rad):
    """Already-grown outline of `shape`, ONE point builder."""
    rad = shape_radius(shape, rad)
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
        # ri 0.78 not 0.38
        pts, ro, ri = [], rad * 1.35, rad * 0.78
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rr = ro if i % 2 == 0 else ri
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        return pts
    return None


def _point_in_poly(pts, x, y):
    hit = False
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xc:
                hit = not hit
    return hit


def point_in_bubble(shape, cx, cy, rad, x, y, tol=0.0):
    """Whether (x, y) on DRAWN outline not box."""
    if tol:
        rad = rad + tol / max(SHAPE_GROW.get(shape or "circle", 1.0), 1e-6)
    pts = bubble_shape_points(shape, cx, cy, rad)
    if pts is None:
        r = shape_radius(shape, rad)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    return _point_in_poly(pts, x, y)


def shape_support(shape, rad, ux, uy):
    pts = bubble_shape_points(shape, 0.0, 0.0, rad)
    if pts is None:
        return shape_radius(shape, rad)
    return max(x * ux + y * uy for x, y in pts)


def shape_body(shape, rad):
    """Ink-covering core of `shape` (points not body)."""
    return shape_radius(shape, rad) * BODY_F


def fit_fontsz(rad, fsz, text=""):
    try:
        rad = float(rad)
        fsz = float(fsz)
    except (TypeError, ValueError):
        return FONTSZ
    n = max(1.0, float(len(str(text)))) if text != "" else REF_DIGITS
    scale = max(rad, 0.0) / RADIUS
    return max(1.0, min(fsz, FONTSZ * scale * REF_DIGITS / n,
                        FONTSZ * scale))


LEADER_EXITS = {"n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0)}
SHEET = "Inspection"
FIRST_ROW = 11
LAST_ROW = 310

# TYPE not region class
TYPES = ["dim", "hole", "thread", "thru", "slot", "depth", "position",
         "GD&T", "finish"]
TIERS = ["", "red", "blue", "green"]

KIND_ATOMIC = "atomic"        # one bubble
KIND_STACKED = "stacked"      # section then per row
KIND_CONTAINER = "container"  # one per row
KIND_META = "meta"            # no bubble
KINDS = (KIND_ATOMIC, KIND_STACKED, KIND_CONTAINER, KIND_META)

# BASIC/REFERENCE are MARKS
MODIFIER_MARKS = frozenset({"[", "("})

ADMIT = {
    "linear": {"Ø", "R"} | MODIFIER_MARKS,
    "angular": {"°"} | MODIFIER_MARKS,
    "arc": {"⌒"} | MODIFIER_MARKS,
    "hole": {"Ø", "R", "DEEP", "CBORE", "CSINK"} | MODIFIER_MARKS,
    "gdt": {"Ø", "⌖", "⏥", "○", "⌭", "⟂", "∥", "∠", "◎",
            "⌒", "⌓", "⌰", "↗", "⏤", "⌯",
            "▱", "◯"} | MODIFIER_MARKS,
    "finish": {"Ra"},
    "edge": {"EDGE"},
    "datum": set(),
    "datum_target": {"Ø"},
    None: None,
}

_GDT_CHAR_GLYPHS = frozenset({
    "⌖", "⏥", "○", "⌭", "⟂", "∥", "∠", "◎",
    "⌒", "⌓", "⌰", "↗", "⏤", "⌯", "▱", "◯"})

REGION_NEEDS_SYMBOL = {
    "dim_diameter": frozenset({"Ø"}),
    "dim_radius": frozenset({"R"}),
    "dim_spherical": frozenset({"Ø", "R"}),
    "surface_finish": frozenset({"Ra"}),
    "feature_control_frame": _GDT_CHAR_GLYPHS,
}


def region_needs_symbol(cls):
    return REGION_NEEDS_SYMBOL.get(cls)

# region vocabulary. Order is LABEL INDEX
REGION_CLASSES = (
    "dim_length",
    "dim_diameter",
    "dim_radius",
    "dim_angular",
    "dim_ordinate",
    "dim_arc",
    "dim_spherical",
    "dim_taper",
    "chamfer",
    "hole",
    "slot",
    "hole_table",
    "feature_control_frame",
    "datum_feature",
    "datum_target",
    "surface_finish",
    "weld_symbol",
    "edge_condition",
    "title_block",
    "gentol_block",
    "finish_block",
    "notes_block",
    "revision_table",
    "standard_note",
    "projection_symbol",
    "view_label",
    "section_line",
    "flag_note",
    "border_zone",
    "parts_list",
    "revision_balloon",
    "item_balloon",
    "other",
)

# detected, claimed, not ballooned. App policy
UNBALLOONED_CLASSES = frozenset(("datum_feature",))

GROUP_BUBBLE = "bubble"          # yields ledger rows
GROUP_SUPPRESS = "suppress"      # must be DETECTED
GROUP_BACKGROUND = "background"  # hard negative
GROUP_UNTRAINED = "untrained"    # labeled not negative
REGION_GROUPS = (GROUP_BUBBLE, GROUP_SUPPRESS, GROUP_BACKGROUND,
                 GROUP_UNTRAINED)

REGION_GROUP = {
    "dim_length": GROUP_BUBBLE,
    "dim_diameter": GROUP_BUBBLE,
    "dim_radius": GROUP_BUBBLE,
    "dim_angular": GROUP_BUBBLE,
    "dim_ordinate": GROUP_BUBBLE,
    "dim_arc": GROUP_BUBBLE,
    "dim_spherical": GROUP_BUBBLE,
    "dim_taper": GROUP_BUBBLE,
    "chamfer": GROUP_BUBBLE,
    "hole": GROUP_BUBBLE,
    "slot": GROUP_BUBBLE,
    "hole_table": GROUP_BUBBLE,
    "feature_control_frame": GROUP_BUBBLE,
    "datum_feature": GROUP_BUBBLE,
    "datum_target": GROUP_BUBBLE,
    "surface_finish": GROUP_BUBBLE,
    "weld_symbol": GROUP_BUBBLE,
    "edge_condition": GROUP_BUBBLE,
    "title_block": GROUP_SUPPRESS,
    "gentol_block": GROUP_SUPPRESS,
    "finish_block": GROUP_SUPPRESS,
    "notes_block": GROUP_SUPPRESS,
    "revision_table": GROUP_SUPPRESS,
    "standard_note": GROUP_SUPPRESS,
    "projection_symbol": GROUP_SUPPRESS,
    "view_label": GROUP_SUPPRESS,
    "section_line": GROUP_SUPPRESS,
    "flag_note": GROUP_SUPPRESS,
    "border_zone": GROUP_SUPPRESS,
    "parts_list": GROUP_SUPPRESS,
    "revision_balloon": GROUP_SUPPRESS,
    "item_balloon": GROUP_BACKGROUND,
    "other": GROUP_UNTRAINED,
}


def region_group(group):
    return tuple(c for c in REGION_CLASSES if REGION_GROUP.get(c) == group)


TRAINED_REGION_CLASSES = tuple(
    c for c in REGION_CLASSES
    if REGION_GROUP.get(c) in (GROUP_BUBBLE, GROUP_SUPPRESS))
BACKGROUND_REGION_CLASSES = region_group(GROUP_BACKGROUND)
UNTRAINED_REGION_CLASSES = region_group(GROUP_UNTRAINED)

assert TRAINED_REGION_CLASSES == REGION_CLASSES[:len(TRAINED_REGION_CLASSES)]

FURNITURE_CONTAINERS = ("title_block", "gentol_block", "finish_block",
                        "notes_block", "revision_table", "parts_list",
                        "border_zone")
DETECTED_FURNITURE = tuple(c for c in FURNITURE_CONTAINERS
                           if c in TRAINED_REGION_CLASSES)

# region class -> (kind, type, ADMIT)
CATEGORY = {
    "dim_length":            (KIND_ATOMIC,    "dim",     "linear"),
    "dim_diameter":          (KIND_ATOMIC,    "dim",     "linear"),
    "dim_radius":            (KIND_ATOMIC,    "dim",     "linear"),
    "dim_angular":           (KIND_ATOMIC,    "dim",     "angular"),
    "dim_ordinate":          (KIND_ATOMIC,    "dim",     "linear"),
    "dim_arc":               (KIND_ATOMIC,    "dim",     "arc"),
    "dim_spherical":         (KIND_ATOMIC,    "dim",     "linear"),
    "dim_taper":             (KIND_ATOMIC,    "dim",     "linear"),
    "chamfer":               (KIND_ATOMIC,    "dim",     "linear"),
    "hole":                  (KIND_STACKED,   "hole",    "hole"),
    "slot":                  (KIND_STACKED,   "slot",    "hole"),
    "hole_table":            (KIND_CONTAINER, "hole",    "hole"),
    "feature_control_frame": (KIND_CONTAINER, "GD&T",    "gdt"),
    "datum_feature":         (KIND_ATOMIC,    "GD&T",    "datum"),
    "datum_target":          (KIND_ATOMIC,    "GD&T",    "datum_target"),
    "surface_finish":        (KIND_ATOMIC,    "finish",  "finish"),
    "weld_symbol":           (KIND_ATOMIC,    "finish",  None),
    "edge_condition":        (KIND_ATOMIC,    "dim",     "edge"),
    "title_block":           (KIND_META,      None,      None),
    "gentol_block":          (KIND_META,      None,      None),
    "finish_block":          (KIND_META,      None,      None),
    "notes_block":           (KIND_META,      None,      None),
    "revision_table":        (KIND_META,      None,      None),
    "standard_note":         (KIND_META,      None,      None),
    "projection_symbol":     (KIND_META,      None,      None),
    "view_label":            (KIND_META,      None,      None),
    "section_line":          (KIND_META,      None,      None),
    "flag_note":             (KIND_META,      None,      None),
    "border_zone":           (KIND_META,      None,      None),
    "parts_list":            (KIND_META,      None,      None),
    "revision_balloon":      (KIND_META,      None,      None),
    "item_balloon":          (KIND_META,      None,      None),
    "other":                 (KIND_META,      None,      None),
}


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


_DP_ONE_NUM = r"\d+(?:\.\d+)?|\.\d+"
_DP_NUM_RE = re.compile(_DP_ONE_NUM)
# fraction not limit pair
_DP_SLASH_RE = re.compile(r"(?<![\d.])(%s)\s*/\s*(%s)(?![\d.])"
                          % (_DP_ONE_NUM, _DP_ONE_NUM))


def dp_of(val):
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip().replace(",", ".")
        m = _DP_SLASH_RE.search(s)
        if m:
            if "." in m.group(1) or "." in m.group(2):
                return None       # limit pair
            if float(m.group(2)) == 0:
                return None
            return 1              # fraction loosest rung
        nums = _DP_NUM_RE.findall(s)
        if not nums:
            return None
        s = nums[-1]
    else:
        s = "%g" % float(val)
    d = len(s.split(".", 1)[1]) if "." in s else 0
    return d or 1


def is_limit_value(val):
    """True when callout states BOTH limits ("1.2500/1.2495")."""
    if not isinstance(val, str):
        return False
    m = _DP_SLASH_RE.search(val.strip().replace(",", "."))
    if not m:
        return False
    return "." in m.group(1) or "." in m.group(2)


def dp_tol(val, cfg, session=None):
    if gentol_ladder(cfg, session) != "decimal":
        return None
    if not gentol_auto(cfg, session):
        return None
    d = dp_of(val)
    if d is None:
        return None
    # decimal ladder inch-only
    tols = ((session or {}).get("dp_tols_inch")
            or (cfg or {}).get("dp_tols_inch") or {})
    cap = 4                              # inch reaches .XXXX
    t = tols.get(str(min(d, cap)))
    try:
        t = float(t)
    except (TypeError, ValueError):
        return None
    return t if t > 0 else None


def base_of(bubble):
    m = re.match(r"\d+", str(bubble))
    return int(m.group(0)) if m else 0


def qc_path(pdf_path, suffix, subdir="qc", legacy=True):
    """Output path for drawing sidecar, `qc/` subdir or legacy sibling."""
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


ROUND_DP = 6

# two-letter forms first (SR6 not S+R6)
REQ_PREFIXES = (u"S\u00d8", "SR", u"\u00d8", "R", "M", u"\u2220", u"\u25a1")


def prefix_of(text):
    s = str(text or "").strip()
    s = re.sub(r"^\d+\s*[Xx\u00d7]\s*", "", s)
    for p in REQ_PREFIXES:
        if not s.startswith(p):
            continue
        rest = s[len(p):].lstrip()
        if rest[:1].isdigit() or rest[:1] in (".", ",", "+", "-"):
            return p
    return ""


def fmt_req_num(x, min_dp=2, max_dp=8):
    """Number for requirement string, `min_dp` decimals EXPANDED to exactness."""
    x = float(x)
    for dp in range(int(min_dp), int(max_dp) + 1):
        s = "%.*f" % (dp, x)
        if round(float(s) - x, 9) == 0:
            return s
    return "%.*f" % (int(max_dp), x)


def requirement_text(nominal, tol_plus=None, tol_minus=None, prefix="",
                     dp=2, limit=None):
    """Requirement as ONE string, shared by sheet and report."""
    if nominal is None:
        return "GO/NOGO"
    dp = int(dp)
    if limit in ("max", "min"):
        # printed number IS bound
        if limit == "max":
            b = round(float(nominal) + float(tol_plus or 0.0), 10)
        else:
            b = round(float(nominal) - float(tol_minus or 0.0), 10)
        return "%s%s %s" % (prefix or "", fmt_req_num(b, dp), limit.upper())
    n = "%s%s" % (prefix or "", fmt_req_num(nominal, dp))
    if tol_plus is None and tol_minus is None:
        return n
    if (tol_plus is not None and tol_minus is not None
            and round(float(tol_plus) - float(tol_minus), ROUND_DP) == 0):
        return u"%s \u00b1%s" % (n, fmt_req_num(abs(float(tol_plus)), dp))
    out = n
    if tol_plus is not None:
        # negative upper deviation stays `-`
        up = float(tol_plus)
        out += " %s%s" % ("-" if up < 0 else "+", fmt_req_num(abs(up), dp))
    if tol_minus is not None:
        lo = float(tol_minus)
        sep = "/" if tol_plus is not None else " "
        # above nominal keeps +
        out += "%s%s%s" % (sep, "-" if lo >= 0 else "+",
                           fmt_req_num(abs(lo), dp))
    return out


_LIMIT_WORD = {"max": re.compile(r"\bMAX\b", re.I),
               "min": re.compile(r"\bMIN\b", re.I)}


def keeps_limit(row, limit):
    if limit not in _LIMIT_WORD:
        return False
    feat = str(row.get("feature") or "")
    if _LIMIT_WORD[limit].search(feat):
        return True
    other = "min" if limit == "max" else "max"
    # finish MAX by convention
    return (limit == "max" and str(row.get("type") or "").startswith("finish")
            and not _LIMIT_WORD[other].search(feat))


def tol_offsets(d):
    """(tol_plus, tol_minus) of ledger row, None side = UNBOUNDED."""
    d = d or {}
    tmax, tmin = _tol_num(d.get("tol_max")), _tol_num(d.get("tol_min"))
    # MAX/MIN ignores stray tol_sym
    if d.get("limit") == "max":
        return (tmax, None)
    if d.get("limit") == "min":
        return (None, None if tmin is None else -tmin)
    sym = _tol_num(d.get("tol_sym"))
    if sym is not None:
        return (abs(sym), abs(sym))
    if tmax is not None and tmin is not None:
        return (max(tmax, tmin), -min(tmax, tmin))
    return (tmax, None if tmin is None else -tmin)


def _tol_num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def limits_of(d):
    nom = d.get("nominal")
    if nom is None:
        return None
    lim = d.get("limit")
    if lim == "max":
        return (None, nom + (_tol_num(d.get("tol_max")) or 0.0))
    if lim == "min":
        return (nom + (_tol_num(d.get("tol_min")) or 0.0), None)
    sym = _tol_num(d.get("tol_sym"))
    if sym is not None:
        s = abs(sym)
        return (nom - s, nom + s)
    # cells may hold text
    tmax, tmin = _tol_num(d.get("tol_max")), _tol_num(d.get("tol_min"))
    if tmax is None and tmin is None:
        return None
    hi = tmax if tmax is not None else 0.0
    lo = tmin if tmin is not None else 0.0
    return (nom + min(lo, hi), nom + max(lo, hi))


METHODS = ("CMM", "probe", "GO-NOGO", "visual", "caliper")

_GAGE_METHOD = {"cmm": "CMM", "micrometer": "caliper", "caliper": "caliper",
                "height gauge": "CMM", "go gauge": "GO-NOGO",
                "pin": "GO-NOGO", "screw test": "GO-NOGO",
                "visual": "visual", "probe": "probe"}


def method_for_gage(gage):
    g = str(gage or "").strip().lower()
    if not g:
        return ""
    if g in METHODS:
        return g
    for k, v in _GAGE_METHOD.items():
        if k in g:
            return v
    return ""


_METHOD_ONLY = ("GO-NOGO", "visual")


def split_method_gage(text, fallback_gage=None):
    txt = str(text or "").strip()
    if not txt:
        return ("", fallback_gage or None)
    for m in METHODS:
        if txt.lower() == m.lower():
            return (m, (fallback_gage or None) if m in _METHOD_ONLY else m)
    return (method_for_gage(txt), txt)


def op_natkey(name):
    out = []
    for part in re.split(r"(\d+)", str(name or "")):
        if part == "":
            continue
        out.append((1, int(part), "") if part.isdigit()
                   else (0, 0, part.lower()))
    return tuple(out)


def merge_op_seq(seq, names=()):
    out = [str(x) for x in (seq or []) if str(x).strip()]
    extra = sorted({str(n) for n in (names or []) if str(n) not in out},
                   key=op_natkey)
    return out + extra


def op_rank(name, seq=None):
    seq = merge_op_seq(seq if seq is not None else OPS_DEFAULT)
    name = str(name or "")
    if name in seq:
        return (seq.index(name), ())
    return (len(seq), op_natkey(name))


def has_reading(rec):
    rec = rec or {}
    if rec.get("readings"):
        return True
    return rec.get("measured") not in (None, "")


def op_value(rec, d=None):
    rec = rec or {}
    readings = rec.get("readings")
    if readings:
        return combine_readings(readings, d or {}, rec.get("combine"))
    return rec.get("measured")


def ops_in_order(ops, seq=None):
    """[(op, record)] in MACHINING order (never timestamp)."""
    ops = ops or {}
    full = merge_op_seq(seq if seq is not None else OPS_DEFAULT, ops.keys())
    return sorted(ops.items(), key=lambda kv: op_rank(kv[0], full))


def latest_op(ops, seq=None):
    if not ops:
        return None
    done = [kv for kv in ops_in_order(ops, seq) if has_reading(kv[1])]
    return done[-1] if done else None


def made_at(d):
    """Op that CREATES characteristic (None = exists from start)."""
    v = (d or {}).get("made_at")
    v = str(v).strip() if v not in (None, "") else ""
    return v or None


def machined_ops(d):
    m = made_at(d)
    return [m] if m else []


def carried_forward(d, op, seq=None):
    ops = (d or {}).get("ops") or {}
    full = merge_op_seq(seq if seq is not None else OPS_DEFAULT,
                        list(ops) + machined_ops(d) + [op])
    here = op_rank(op, full)
    best = None
    for name, rec in ops_in_order(ops, full):
        if op_rank(name, full) < here and has_reading(rec):
            best = (name, op_value(rec, d))
    return best


def op_scope(d, op, seq=None):
    ops = (d or {}).get("ops") or {}
    full = merge_op_seq(seq if seq is not None else OPS_DEFAULT,
                        list(ops) + machined_ops(d) + [op])
    here = op_rank(op, full)
    m = made_at(d)
    if m is not None and op_rank(m, full) > here:
        return "future"
    if op in machined_ops(d):
        return "machined"
    if (d or {}).get("recheck"):
        return "recheck"
    if carried_forward(d, op, full) is None:
        return "new"
    return "carried"


def band_center(d):
    lim = limits_of(d)
    if lim is not None:
        return (lim[0] + lim[1]) / 2.0
    return d.get("nominal")


def _as_float(s):
    try:
        v = float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def worst_reading(values, d):
    vals = [str(v).strip() for v in (values or []) if str(v).strip() != ""]
    if not vals:
        return None
    for v in vals:
        if v.upper() in NOGO_WORDS:
            return v
    numeric = [(v, _as_float(v)) for v in vals]
    numeric = [(v, f) for v, f in numeric if f is not None]
    if not numeric:
        return vals[0]
    c = band_center(d)
    if c is None:
        c = sum(f for _, f in numeric) / len(numeric)
    return max(numeric, key=lambda vf: abs(vf[1] - c))[0]


def combine_readings(values, d, how="worst"):
    """Worst, or mean. A no-go always wins."""
    if how != "average":
        return worst_reading(values, d)
    vals = [str(v).strip() for v in (values or []) if str(v).strip() != ""]
    if not vals:
        return None
    for v in vals:
        if v.upper() in NOGO_WORDS:
            return v
    pairs = [(v, _as_float(v)) for v in vals]
    pairs = [(v, f) for v, f in pairs if f is not None]
    if not pairs:
        return vals[0]
    # one digit past the readings
    dp = max(len(v.replace(",", ".").partition(".")[2]) for v, _ in pairs)
    mean = sum(f for _, f in pairs) / len(pairs)
    return ("%%.%df" % (dp + 1)) % mean


def count_rows_of(d, ledger=()):
    """Count rows owned by d."""
    key = d.get("bgroup") or d.get("uid")
    b, pg = base_of(d.get("bubble")), d.get("page")

    def same(r):
        if key is not None and (r.get("bgroup") or r.get("uid")) == key:
            return True
        return (r.get("page") == pg and b not in (None, "")
                and base_of(r.get("bubble")) == b)
    group = [r for r in ledger or () if same(r)]
    rows = [r for r in group if r.get("facet") == "qty"]
    own = d.get("rkey")
    mine = [r for r in rows if own and r.get("qty_of") == own]
    if mine:
        return mine
    owners = [r for r in group if r.get("facet") != "qty"
              and int(r.get("qty") or 1) > 1]
    loose = [r for r in rows if not r.get("qty_of")]
    if len(owners) <= 1:
        return loose
    # merged group: count matches own qty
    n = int(d.get("qty") or 1)
    return [r for r in loose if r.get("nominal") == float(n)][:1]


def qty_readings(d, ledger=()):
    """Readings to take: N only when the count is bubbled."""
    n = int((d or {}).get("qty") or 1)
    if n < 2 or d.get("facet") == "qty":
        return 1
    if count_rows_of(d, ledger):
        return n
    # measured N times before the rule
    if any(len((rec or {}).get("readings") or ()) > 1
           for rec in (d.get("ops") or {}).values()):
        return n
    return 1


def mirror_measured(d, seq=None):
    ops = d.get("ops")
    if not ops:
        return d.get("measured")
    best = latest_op(ops, seq)
    d["measured"] = op_value(best[1], d) if best else None
    return d["measured"]


NOGO_WORDS = ("NOGO", "NO-GO", "NO GO", "NOK", "FAIL", "NIE")
GO_WORDS = ("GO", "OK", "TAK", "PASS")


def measure_state(d):
    """Row inspection state: none | in | out | go | nogo."""
    m = d.get("measured")
    if m in (None, ""):
        return "none"
    s = str(m).strip().upper()
    if s in GO_WORDS:
        return "go"
    if s in NOGO_WORDS:
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
        return s.upper() in NOGO_WORDS
    lim = limits_of(d)
    if lim is None:
        return False
    lo, hi = lim
    if lo is not None and v < lo - 1e-9:
        return True
    if hi is not None and v > hi + 1e-9:
        return True
    return False


def oot_rows(ledger, cfg=None):
    seq = ops_seq(cfg or {})
    rows = []
    for d in ledger:
        st = measure_state(d)
        if not (out_of_tol(d) or st == "nogo"):
            continue
        op = latest_op(d.get("ops"), seq)
        rows.append({
            "bubble": d.get("bubble", ""),
            "base": base_of(d.get("bubble", "")),
            "page": d.get("page"),
            "nominal": d.get("nominal"),
            "tol": tol_text(d),
            "requirement": requirement_text(
                _tol_num(d.get("nominal")), *tol_offsets(d),
                prefix=prefix_of(d.get("feature")),
                dp=NOMINAL_DP.get(units_of(cfg or {}), 2),
                limit=(d.get("limit") or None)),
            "measured": d.get("measured"),
            "op": op[0] if op else "",
            "gage": (op[1].get("gage") if op else None) or d.get("gage") or "",
            "method": ((op[1].get("method") if op else "")
                       or method_for_gage(d.get("gage")) or ""),
            "tier": d.get("tier", ""),
            "state": st,
        })
    rows.sort(key=lambda r: (base_of(r["bubble"]), str(r["bubble"])))
    return rows


def oot_summary(ledger, cfg=None):
    """{rows, n_oot, n_critical}, critical = red-tier OOT."""
    rows = oot_rows(ledger, cfg)
    n_crit = sum(1 for r in rows if r.get("tier") == "red")
    return {"rows": rows, "n_oot": len(rows), "n_critical": n_crit}
