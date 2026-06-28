# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Constants, category model, tolerance helpers.

APP_NAME = "Bubbler"
ORG = "InPoint Automation Sp. z o.o."
VERSION = "0.1.0"

RADIUS = 9.0
FONTSZ = 10.0
RED = (0.85, 0.1, 0.1)
WHITE = (1, 1, 1)

# Leader exit side -> unit step.
LEADER_EXITS = {"n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0)}
SHEET = "Inspection"
FIRST_ROW = 11
LAST_ROW = 310

TYPES = ["dim", "hole / otwór", "thread / gwint", "thru / przelot",
         "slot / rowek", "depth / głębokość", "position / pozycja",
         "GD&T", "finish / wykończenie"]
GROUPS = ["LWH", "positions / pozycje", "holes Ø / otwory",
          "threads / gwinty", "GD&T", "finish / wykończenie", "other / inne"]
TIERS = ["", "red", "blue", "green"]
GROUP_OF = {
    "dim": "LWH",
    "hole / otwór": "holes Ø / otwory",
    "thread / gwint": "threads / gwinty",
    "thru / przelot": "holes Ø / otwory",
    "slot / rowek": "positions / pozycje",
    "depth / głębokość": "LWH",
    "position / pozycja": "positions / pozycje",
    "GD&T": "GD&T",
    "finish / wykończenie": "finish / wykończenie",
}

# Category model: region class -> resolution, preset, tokens.

# Structural kind = what one click yields.
KIND_ATOMIC = "atomic"        # region = 1 measurement        -> one bubble
KIND_STACKED = "stacked"      # region = feature + sub-feats   -> one bubble + sub-rows
KIND_CONTAINER = "container"  # region = N callouts            -> resolve unit under cursor
KIND_META = "meta"            # not a measurement              -> sets defaults, no bubble
KINDS = (KIND_ATOMIC, KIND_STACKED, KIND_CONTAINER, KIND_META)

# tokens each category admits
ADMIT = {
    "linear": {"Ø", "R"},
    "hole": {"Ø", "R", "DEEP", "CBORE", "CSINK"},
    "gdt": {"Ø", "⌖", "▱", "◯", "⌭", "⟂", "∥", "∠", "◎", "⌒", "⌓", "⌰", "↗"},
    "finish": {"Ra"},
    "datum": set(),           # boxed letter only
    None: None,               # meta: reader not run
}

# class -> (kind, preset, constraint)
CATEGORY = {
    "dim_tol":               (KIND_ATOMIC,    "dim",                  "linear"),
    "hole_note":             (KIND_STACKED,   "hole / otwór",         "hole"),
    "hole_table":            (KIND_CONTAINER, "hole / otwór",         "hole"),
    "surface_finish":        (KIND_ATOMIC,    "finish / wykończenie", "finish"),
    "feature_control_frame": (KIND_CONTAINER, "GD&T",                 "gdt"),
    "datum_feature":         (KIND_ATOMIC,    "GD&T",                 "datum"),
    "gentol_block":          (KIND_META,      None,                   None),
    "note":                  (KIND_META,      None,                   None),
}


def admits(constraint, token):
    """True if this constraint may emit `token`. Stripped compare."""
    allow = ADMIT.get(constraint)
    if not allow:
        return False
    return token.strip() in allow


def fnum(s):
    s = (s or "").strip().replace(",", ".")
    if s == "":
        return None
    return float(s)


def dp_of(val):
    """Decimal places of a nominal. Strings keep literal intent."""
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
    """Tolerance by decimal places (title-block style). ± or None."""
    if not cfg or not cfg.get("dp_on"):
        return None
    d = dp_of(val)
    if d is None:
        return None
    tols = cfg.get("dp_tols") or {}
    t = tols.get(str(min(d, 3)))
    try:
        t = float(t)
    except (TypeError, ValueError):
        return None
    return t if t > 0 else None


def base_of(bubble):
    b = str(bubble)
    return int(b.rstrip("abcdefghijklmnopqrstuvwxyz") or 0)


def tol_text(d):
    if d.get("tol_sym") not in (None, ""):
        return u"\u00b1%g" % d["tol_sym"]
    tmax, tmin = d.get("tol_max"), d.get("tol_min")
    if tmax is None and tmin is None:
        return ""
    if tmax is not None and tmin is not None:
        hi, lo = max(tmax, tmin), min(tmax, tmin)
        return "%+g/%+g" % (hi, lo)
    return "%+g/?" % (tmax if tmax is not None else tmin)


def limits_of(d):
    """(low, high) acceptance limits of a row, or None when unknown."""
    nom = d.get("nominal")
    if nom is None:
        return None
    if d.get("tol_sym") is not None:
        s = abs(d["tol_sym"])
        return (nom - s, nom + s)
    tmax, tmin = d.get("tol_max"), d.get("tol_min")
    if tmax is None or tmin is None:
        return None
    return (nom + min(tmax, tmin), nom + max(tmax, tmin))


_NOGO_WORDS = ("NOGO", "NO-GO", "NO GO", "NOK", "FAIL", "NIE")


def out_of_tol(d):
    """True when measured value violates the row's limits."""
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
