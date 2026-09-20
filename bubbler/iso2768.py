# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# ISO 2768-1 & -2 general tolerances

import re as _re

ISO2768 = {
    "f": [(3, 0.05), (6, 0.05), (30, 0.1), (120, 0.15), (400, 0.2),
          (1000, 0.3), (2000, 0.5), (4000, None)],
    "m": [(3, 0.1), (6, 0.1), (30, 0.2), (120, 0.3), (400, 0.5),
          (1000, 0.8), (2000, 1.2), (4000, 2.0)],
    "c": [(3, 0.2), (6, 0.3), (30, 0.5), (120, 0.8), (400, 1.2),
          (1000, 2.0), (2000, 3.0), (4000, 4.0)],
    "v": [(3, None), (6, 0.5), (30, 1.0), (120, 1.5), (400, 2.5),
          (1000, 4.0), (2000, 6.0), (4000, 8.0)],
}

ISO2768_RADIUS = {
    "f": [(3, 0.2), (6, 0.5), (1e9, 1.0)],
    "m": [(3, 0.2), (6, 0.5), (1e9, 1.0)],
    "c": [(3, 0.4), (6, 1.0), (1e9, 2.0)],
    "v": [(3, 0.4), (6, 1.0), (1e9, 2.0)],
}

# decimal degrees
ISO2768_ANGLE = {
    "f": [(10, 1.0), (50, 0.5), (120, 1 / 3.0), (400, 1 / 6.0),
          (1e9, 1 / 12.0)],
    "m": [(10, 1.0), (50, 0.5), (120, 1 / 3.0), (400, 1 / 6.0),
          (1e9, 1 / 12.0)],
    "c": [(10, 1.5), (50, 1.0), (120, 0.5), (400, 0.25),   # 0°15'
          (1e9, 1 / 6.0)],
    "v": [(10, 3.0), (50, 2.0), (120, 1.0), (400, 0.5), (1e9, 1 / 3.0)],
}

ISO2768_FLAT = {
    "H": [(10, 0.02), (30, 0.05), (100, 0.1), (300, 0.2), (1000, 0.3),
          (3000, 0.4)],
    "K": [(10, 0.05), (30, 0.1), (100, 0.2), (300, 0.4), (1000, 0.6),
          (3000, 0.8)],
    "L": [(10, 0.1), (30, 0.2), (100, 0.4), (300, 0.8), (1000, 1.2),
          (3000, 1.6)],
}

ISO2768_PERP = {
    "H": [(10, 0.2), (30, 0.3), (100, 0.4), (300, 0.5)],
    "K": [(10, 0.4), (30, 0.6), (100, 0.8), (300, 1.0)],
    "L": [(10, 0.6), (30, 1.0), (100, 1.5), (300, 2.0)],
}

ISO2768_SYM = {
    "H": [(10, 0.5), (30, 0.5), (100, 0.5), (300, 0.5)],
    "K": [(10, 0.6), (30, 0.6), (100, 0.8), (300, 1.0)],
    "L": [(10, 0.6), (30, 1.0), (100, 1.5), (300, 2.0)],
}

ISO2768_RUNOUT = {"H": 0.1, "K": 0.2, "L": 0.5}


def _band(table, nominal, lo_first=0.5):
    if nominal is None or nominal < lo_first:
        return None
    prev = lo_first
    for hi, t in table:
        if prev <= nominal <= hi:
            return t
        prev = hi
    return None


def in_range(nominal, cls="m", lo_first=0.5):
    """Nominal inside 2768-1 table so callers can flag out-of-table."""
    table = ISO2768.get(cls) or ISO2768.get("m") or []
    if nominal is None or nominal < lo_first or not table:
        return False
    return nominal <= table[-1][0]


def iso2768_tol(nominal, cls):
    return _band(ISO2768.get(cls, []), nominal)


def iso2768_radius_tol(nominal, cls):
    return _band(ISO2768_RADIUS.get(cls, []), nominal)


_RADIUS_FEAT = _re.compile(r"^\s*R\s?\d", _re.I)

# chamfer uses radius table
_CHAMFER_FEAT = _re.compile(
    r"^\s*(?:C[ \t]?\d"
    r"|\d+(?:[.,]\d+)?[ \t]*[xX\u00d7][ \t]*"
    r"\d+(?:[.,]\d+)?[ \t]*\u00b0"
    r"|\d+(?:[.,]\d+)?[xX\u00d7](?:15|30|45|60)(?![\d.,]))", _re.I)


# bare angle callout only
_ANGLE_FEAT = _re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*(?:\u00b0|DEG(?:REES?)?)\s*$", _re.I)

# most permissive angular band
ANGLE_SHORTEST_SIDE = 0.0


def is_angle_feature(feature):
    """Feature text is bare angle callout."""
    return bool(_ANGLE_FEAT.match(str(feature or "")))


def is_radius_feature(feature):
    """Glyph test for radius (R8) or chamfer to pick which control shows."""
    feat = str(feature or "")
    return bool(_RADIUS_FEAT.match(feat) or _CHAMFER_FEAT.match(feat))


# edge-break note match
_EDGE_FEAT = _re.compile(r"^\s*EDGE\b", _re.I)


def is_broken_edge(feature):
    """Feature is broken edge for Table 2."""
    return bool(_EDGE_FEAT.match(str(feature or "")))




def iso2768_general_tol(nominal, cls, feature=None,
                        side_mm=ANGLE_SHORTEST_SIDE):
    """General tolerance by nominal (angle in degrees else mm)."""
    if feature is not None:
        feat = str(feature)
        if is_broken_edge(feat):
            return iso2768_radius_tol(nominal, cls)
        if _ANGLE_FEAT.match(feat):
            if side_mm is None:
                return None
            return iso2768_angle_tol(side_mm, cls)
    return iso2768_tol(nominal, cls)


def iso2768_angle_tol(shorter_side_mm, cls):
    """Angular general tolerance in degrees by shorter side mm."""
    return _band(ISO2768_ANGLE.get(cls, []), shorter_side_mm, lo_first=0)


def iso2768_2_flatness(length, cls):
    return _band(ISO2768_FLAT.get(cls, []), length, lo_first=0)


def iso2768_2_perpendicularity(shorter_side, cls):
    return _band(ISO2768_PERP.get(cls, []), shorter_side, lo_first=0)


def iso2768_2_symmetry(length, cls):
    return _band(ISO2768_SYM.get(cls, []), length, lo_first=0)


def iso2768_2_runout(cls):
    return ISO2768_RUNOUT.get(cls)
