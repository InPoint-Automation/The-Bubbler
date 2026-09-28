# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Gaging: which tool measures feature.

from bubbler.config import CFG_DEFAULT
from bubbler.config import units_of
from bubbler.i18n import tr


GAGES = ["CMM", "micrometer", tr('pin'), "GO gauge",
         "height gauge", "caliper"]


def gage_choices(cfg=None, current=None, blank=False):
    from bubbler.config import CFG_DEFAULT
    out, seen = ([""] if blank else []), set()
    tools = (cfg or {}).get("metrology_tools") \
        or CFG_DEFAULT.get("metrology_tools") or []
    cur = str(current or "").strip()
    for n in list(GAGES) + [str((t or {}).get("name") or "").strip()
                            for t in tools]:
        if n and n.lower() not in seen and n.lower() != cur.lower():
            out.append(n)
            seen.add(n.lower())
    if cur:
        out.insert(1 if blank else 0, cur)
    return out
def tool_feature(d):
    t = (d.get("type") or "").lower()
    if t.startswith("thread"):
        return "thread"
    if (t.startswith(("gd&t", "gdt", "position", "profile", "runout",
                      "flatness", "perp", "parallel", "angular",
                      "concentric", "coax", "symmetry", "straight",
                      "circular", "cylindric"))):
        return "gdt"
    if t.startswith(("finish", "surface")):
        return "surface"
    if t.startswith(("hole", "thru", "slot", "bore")):
        return "id"
    if t.startswith("depth"):
        return "depth"
    if t.startswith(("radius", "rad")):
        return "radius"
    if t.startswith(("angle", "chamfer")):
        return "angle"
    return "length"


def _band_of(d):
    """Total tolerance band in the drawing's own units, or None."""
    tmax, tmin = d.get("tol_max"), d.get("tol_min")
    if tmax is not None and tmin is not None:
        return abs(float(tmax) - float(tmin))
    ts = d.get("tol_sym")
    return 2.0 * abs(float(ts)) if ts is not None else None


def choose_tool(feature, band_mm, nominal_mm, tools, ratio=10.0):
    """Least capable tool fine enough, never refuse."""
    def _fits(t):
        return (t.get("range_min", 0.0) <= (nominal_mm or 0.0)
                <= t.get("range_max", 1e12))

    def _res(t):
        return float(t.get("resolution") or 1e12)

    elig = [t for t in tools if feature in (t.get("features") or []) and _fits(t)]
    if not elig:
        pool = [t for t in tools if _fits(t)] or list(tools)
        return min(pool, key=_res) if pool else None
    if ratio and band_mm:
        capable = [t for t in elig if _res(t) <= band_mm / ratio]
        if capable:
            return max(capable, key=_res)
    return min(elig, key=_res)


def suggest_gage(d, cfg=None, session=None):
    cfg = cfg or {}
    tools = cfg.get("metrology_tools") or CFG_DEFAULT.get("metrology_tools") or []
    if not tools:
        return "caliper"
    inch = units_of(cfg, session) == "asme_inch"
    k = 25.4 if inch else 1.0
    band = _band_of(d)
    band_mm = band * k if band is not None else None
    nom = d.get("nominal")
    nom_mm = abs(float(nom)) * k if nom is not None else 0.0
    ratio = float(cfg.get("gage_resolution_ratio",
                          CFG_DEFAULT.get("gage_resolution_ratio", 10)) or 0)
    t = choose_tool(tool_feature(d), band_mm, nom_mm, tools, ratio)
    return (t or {}).get("name") or "caliper"
