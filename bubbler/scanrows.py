# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Scan hits -> sheet rows, facets, scope.

import re as _re
from bubbler import gentol  # noqa: E402
from bubbler.reader import grammar  # noqa: E402


# hole facets, default sub-row order
HOLE_FACETS = ("hole", "depth", "cbore", "cbore_depth", "csink",
               "csink_depth", "tap_drill", "tap_drill_depth", "qty")

# tap drill and count unbubbled by default
FACET_SKIP_DEFAULT = ("tap_drill", "tap_drill_depth", "qty")

_QTY_KEEP = ("tier", "leader", "page", "x", "y", "bx", "by", "uid",
             "bgroup", "rect", "bubble")


def qty_row(n, like=None):
    """Count check: nominal N exact, no gentol."""
    d = {k: v for k, v in (like or {}).items() if k in _QTY_KEEP}
    d.update(type="dim", feature="%dX" % int(n), nominal=float(int(n)),
             tol_sym=0.0, tol_max=None, tol_min=None, limit=None,
             facet="qty", no_gentol=True, pin=None, offset=None,
             measured=None, gage=None)
    return d


def with_qty_row(rows, cfg=None):
    """Adds count row unless Settings skips it."""
    rows = list(rows or ())
    n = max([int(r.get("qty") or 1) for r in rows] or [1])
    if n < 2 or facet_skipped("qty", cfg) or any(
            r.get("facet") == "qty" for r in rows):
        return rows
    return rows + [qty_row(n, rows[0])]


def facet_skipped(facet, cfg=None):
    skip = (cfg or {}).get("hole_facet_skip")
    if skip is None:
        skip = FACET_SKIP_DEFAULT
    # never the hole itself
    return facet != "hole" and facet in skip


def _thread_major(v):
    """Thread major diameter, own units, inch too."""
    import re
    t = str(v or "")
    m = re.search(r"M\s*(\d+(?:[.,]\d+)?)", t)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"#\s*(\d{1,2})\s*-\s*\d+", t)
    if m:
        return 0.060 + 0.013 * int(m.group(1))
    m = re.search(r"(?<![\d.])(?:(\d+)[ -])?(\d+)/(\d+)\s*-\s*\d+", t)
    if m:
        whole = int(m.group(1) or 0)
        return whole + int(m.group(2)) / float(int(m.group(3)) or 1)
    m = re.search(r"(?<![\d./])(\d+(?:\.\d+)?)\s*-\s*(\d+)\s*UN", t,
                  re.I)
    if m:
        size, tpi = float(m.group(1)), int(m.group(2))
        # number size, not inches
        if (size == int(size) and size < 13 and tpi >= 24
                and (size != 1 or tpi >= 56)):
            return 0.060 + 0.013 * size
        return size
    return None


def _dia_of(v):
    """`2X Ø5.2` -> 5.2, else None."""
    import re
    m = re.search("\u00d8\\s*(\\d+(?:[.,]\\d+)?|[.,]\\d+)", str(v or ""))
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def stamp_facets(hits):
    """Depth belongs to preceding facet, box order. Once per page."""
    groups = {}
    for i, h in enumerate(hits):
        if h.get("tp") in ("DIAMETER", "DEPTH", "FIT", "THREAD"):
            groups.setdefault(h.get("cg", "_"), []).append((i, h))
    for members in groups.values():
        # tap drill under major
        majors = [_thread_major(h.get("v")) for _i, h in members
                  if h.get("tp") == "THREAD"]
        majors = [m for m in majors if m]
        tapped = bool(majors)
        def where(ih):
            r = ih[1].get("rect")
            if not r:
                return (0.0, float(ih[0]))
            from bubbler.reader.geometry import _rect_map, _to_frame
            r = _rect_map(_to_frame, int(ih[1].get("text_dir") or 0) // 90, r)
            return (r[1], r[0])
        last = None
        for _i, h in sorted(members, key=where):
            if h["tp"] in ("DIAMETER", "FIT", "THREAD"):
                last = {"CBORE": "cbore", "CSINK": "csink"}.get(
                    h.get("sb"), "hole") if h["tp"] == "DIAMETER" else "hole"
                if (tapped and last == "hole" and h["tp"] == "DIAMETER"
                        and h.get("cg") is not None
                        and (_dia_of(h.get("v")) or 1e9) < min(majors)):
                    last = "tap_drill"
                h["facet"] = last
            else:
                h["facet"] = {"cbore": "cbore_depth",
                              "csink": "csink_depth",
                              "tap_drill": "tap_drill_depth"}.get(last,
                                                                  "depth")
    return hits


def row_facet(d):
    f = (d or {}).get("facet")
    if f in HOLE_FACETS:
        return f
    feat = str((d or {}).get("feature") or "").strip().lower()
    for pre, name in (("cbore depth", "cbore_depth"),
                      ("csink depth", "csink_depth"),
                      ("tap drill depth", "tap_drill_depth"),
                      ("tap drill", "tap_drill"),
                      ("cbore", "cbore"), ("csink", "csink"),
                      ("depth", "depth")):
        if feat.startswith(pre):
            return name
    t = str((d or {}).get("type") or "")
    if t == "depth":
        return "depth"          # scanned ↧ no word
    # thread is the hole
    if t.startswith(("hole", "thru", "thread")):
        return "hole"
    return None


def facet_order(cfg=None):
    got = [f for f in ((cfg or {}).get("hole_facet_order") or ())
           if f in HOLE_FACETS]
    return tuple(got) + tuple(f for f in HOLE_FACETS if f not in got)


def facet_rank(facet, cfg=None):
    order = facet_order(cfg)
    return order.index(facet) if facet in order else len(order)


def parse_tol_string(t):
    """Tolerance string -> (tol_sym, tol_max, tol_min)."""
    if not t or t in ("BASIC", "REF"):
        return (None, None, None)
    t = t.replace(",", ".").replace("\u00b0", "").replace(" ", "")
    if t.startswith("\u00b1"):
        try:
            return (float(t[1:]), None, None)
        except ValueError:
            return (None, None, None)
    m = _re.match(r"^([+\-]?[\d.]+)/([+\-]?[\d.]+)$", t)
    if m:
        try:
            a, b = float(m.group(1)), float(m.group(2))
        except ValueError:
            return (None, None, None)
        return (None, max(a, b), min(a, b))
    m = _re.match(r"^([+\-])([\d.]+)$", t)
    if m:
        try:
            v = float(m.group(2))
        except ValueError:
            return (None, None, None)
        return ((None, v, 0.0) if m.group(1) == "+"
                else (None, 0.0, -v))
    return (None, None, None)


# scan scope, one bucket per hit
SCAN_BUCKETS = (
    "gdt",          # GD&T own tolerance
    "finish",       # surface roughness
    "basic_ref",    # [25] and (75)
    "thread",       # M8x1.25 gauged
    "own_tol",      # printed tolerance
    "gentol",       # leans on gentol block
    "bare",         # no tolerance anywhere
)

_SCAN_GDT_TP = ("GDT", "POSITION")


def scan_bucket(h, row=None):
    h = h or {}
    tp = str(h.get("tp") or "").upper()
    sb = str(h.get("sb") or "").upper()
    t = str((row or {}).get("type") or "")
    if tp in _SCAN_GDT_TP or t in ("GD&T", "position"):
        return "gdt"
    if tp == "SURFACE" or t == "finish":
        return "finish"
    if sb in ("BASIC", "REF") or gentol.is_basic_ref_feature(h.get("v")):
        return "basic_ref"
    if tp == "THREAD" or t == "thread":
        return "thread"
    if row is not None and (row.get("limit") in ("max", "min")
                            or any(row.get(k) is not None
                                   for k in ("tol_sym", "tol_max",
                                             "tol_min"))):
        return "own_tol"
    if str(h.get("t") or "").strip():
        return "own_tol"
    if sb == "BARE":
        return "bare"
    return "gentol"


SCAN_PRESETS = {
    "First article": ("gdt", "finish", "basic_ref", "thread", "own_tol",
                      "gentol"),
    "In-process": ("gdt", "finish", "own_tol"),
}
SCAN_PRESET_DEFAULT = "First article"


def scan_presets(cfg=None):
    out = {k: tuple(v) for k, v in SCAN_PRESETS.items()}
    for name, buckets in ((cfg or {}).get("scan_presets") or {}).items():
        name = str(name).strip()
        if not name:
            continue
        out[name] = tuple(b for b in (buckets or ())
                          if b in SCAN_BUCKETS)
    return out


def scan_preset_name(cfg=None, session=None, header=None):
    """Which preset applies -> DRAWING's own answer, else shop default."""
    presets = scan_presets(cfg)
    lower = {k.lower(): k for k in presets}
    for v in (((session or {}).get("scan_preset")),
              ((header or {}).get("H6")),
              ((cfg or {}).get("scan_preset"))):
        hit = lower.get(str(v or "").strip().lower())
        if hit:
            return hit
    return (SCAN_PRESET_DEFAULT if SCAN_PRESET_DEFAULT in presets
            else sorted(presets)[0])


def scan_ticked(h, row=None, cfg=None, session=None, header=None):
    name = scan_preset_name(cfg, session, header)
    bucket = scan_bucket(h, row)
    # skipped facet unless own tol
    if facet_skipped((h or {}).get("facet"), cfg) and bucket != "own_tol":
        return False
    return bucket in scan_presets(cfg).get(name, ())


_MM_PER_INCH = 25.4


def fit_in_units(nominal_in, code, units="iso_mm"):
    from bubbler.iso286 import fit_limits
    mm = nominal_in * _MM_PER_INCH
    lim = fit_limits(mm, code) if code and "/" not in code else None
    if units == "asme_inch":
        return nominal_in, (None if lim is None
                            else (lim[0] / _MM_PER_INCH, lim[1] / _MM_PER_INCH))
    return mm, lim


_CHAMFER_LEAD = _re.compile(r"^\s*\d+(?:[.,]\d+)?\s*[xX\u00d7]\s*"
                           r"\d+(?:[.,]\d+)?\s*\u00b0")


def strip_count(text):
    """Repeat count off, "1 x 45°" leg kept."""
    s = str(text or "")
    return s if _CHAMFER_LEAD.match(s) else strip_repeat(s)


def scan_to_row(d, units="iso_mm"):
    sym, tmax, tmin = parse_tol_string(d.get("t"))
    tp = d["tp"]
    row = {"type": "dim", "feature": d["v"],
           "nominal": None, "tol_sym": sym, "tol_max": tmax,
           "tol_min": tmin, "pin": None, "offset": None,
           "measured": None, "tier": "", "limit": None}

    def num(s):
        s = strip_count(s)
        try:
            return float(_re.sub(r"[^\d.,]", "", s).replace(",", "."))
        except ValueError:
            return None

    if tp == "SLOT":
        m = _re.search(r"(\d+(?:[.,]\d+)?)", d["v"])
        row.update(type="slot", nominal=num(m.group(1)) if m else None)
    elif tp == "DEPTH":
        m = _re.search(r"(\d+(?:[.,]\d+)?)", d["v"])
        row.update(type="depth", nominal=num(m.group(1)) if m else None)
    elif tp == "THREAD":
        row.update(type="thread")
    elif tp == "GDT":
        zone = num(d.get("t") or "")
        row.update(type="GD&T", nominal=0.0,
                   tol_sym=None, tol_max=zone, tol_min=0.0)
    elif tp == "LIMIT":
        mm = _re.match(r"\s*(S?\u00d8|S?R)?\s*(\d+(?:[.,]\d+)?)\s*(MIN|MAX)",
                       d["v"], _re.I)
        pre = (mm.group(1) or "") if mm else ""
        row.update(nominal=num(mm.group(2)) if mm else None,
                   limit=("max" if mm and mm.group(3).upper() == "MAX"
                          else "min"))
        if "\u00d8" in pre:
            row.update(type="hole")
    elif tp == "SURFACE":
        row.update(type="finish")
        # lone Ra is MAX
        nums = _re.findall(r"\d+(?:[.,]\d+)?", d["v"])
        if len(nums) >= 2:
            lo, hi = sorted(num(x) for x in nums[:2])
            row.update(nominal=lo, tol_max=round(hi - lo, 6), tol_min=0.0)
        elif nums:
            row.update(nominal=num(nums[0]), limit="max")
    elif tp == "DIAMETER":
        m = _re.search(r"\u00d8\s*(\d+(?:[.,]\d+)?)", d["v"])
        row.update(type="hole",
                   nominal=num(m.group(1)) if m else num(d["v"]))
        if d.get("thru"):
            row.update(type="thru",
                       feature=row["feature"] + " THRU")
    elif tp == "FIT":
        m = _re.match(r"\s*(?:\d+\s*[Xx\u00d7]\s*)?\u00d8?\s*"
                      r"(\d+(?:[.,]\d+)?|[.,]\d+)", d["v"])
        nominal = num(m.group(1)) if m else None
        code = (d.get("t") or "").replace(" ", "")
        is_hole = bool(code) and code[0].isupper()
        row.update(nominal=nominal,
                   feature=d["v"] + " (fit " + (d.get("t") or "") + ")")
        if is_hole:
            row.update(type="hole")
        if nominal is not None and '"' in d["v"]:
            nominal, lim = fit_in_units(nominal, code, units)
            row["nominal"] = nominal
            if lim is not None:
                row.update(tol_max=lim[0], tol_min=lim[1])
        elif code and "/" not in code and nominal is not None:
            from bubbler.iso286 import fit_limits
            lim = fit_limits(nominal, code)
            if lim is not None:
                row.update(tol_max=lim[0], tol_min=lim[1])
    elif tp == "EDGE":
        # zero nominal, note numbers as limits
        row.update(nominal=0.0)
    elif tp == "CHAMFER":
        m = _re.search(r"(\d+(?:[.,]\d+)?)", d["v"])
        row.update(nominal=num(m.group(1)) if m else None)
    elif tp == "RADIUS":
        row.update(nominal=num(d["v"]))
    elif tp == "ANGLE":
        row.update(nominal=grammar.dms_degrees(d["v"]))
    else:
        row.update(nominal=num(d["v"]))
        note = d.get("hole_note")
        if note == "thru":
            row.update(type="thru", feature=row["feature"] + " THRU")
        elif note:
            row.update(type="hole")
    _limit_range(row, d.get("t"), d.get("raw"))
    if int(d.get("qty") or 1) > 1:
        row["qty"] = int(d["qty"])
    if d.get("facet"):
        row["facet"] = d["facet"]
    return row


def _limit_range(row, t=None, raw=None):
    """Huge minus deviation is really upper limit."""
    nom, tmax, tmin = row.get("nominal"), row.get("tol_max"), row.get("tol_min")
    if (nom is None or nom <= 0 or row.get("tol_sym") is not None
            or tmax is None or tmax < 0 or tmin is None or tmin >= 0):
        return
    t = str(t or "")
    if "\u00b0" in str(raw or "") + t:
        return      # size plus angle
    if -tmin > 2.0 * nom and "/" not in t:
        # not a deviation, use gentol
        row.update(tol_max=None, tol_min=None)
        return
    if "/" in t and tmax == 0.0:
        return
    if tmax != 0.0 and "/" not in t:
        return
    # stray +d also a limit
    other = -tmin
    # range errs to false FAIL
    if other / nom < 0.5:
        return
    if not grammar.limit_close(nom, other):
        # wide pair = two callouts
        if "/" not in t:
            row.update(tol_max=None, tol_min=None)
        return
    lo, hi = min(nom, other), max(nom, other)
    row.update(nominal=lo, tol_max=round(hi - lo, 10), tol_min=0.0)


_REPEAT_RE = _re.compile(r"^\s*(\d+)\s*[Xx×](?=\s|Ø|$)")


def repeat_count(feature):
    m = _REPEAT_RE.match(str(feature or ""))
    return max(1, min(999, int(m.group(1)))) if m else 1


def strip_repeat(feature):
    s = str(feature or "")
    m = _REPEAT_RE.match(s)
    return s[m.end():].lstrip() if m else s


def expand_hole_row(row, cfg=None, repeat=True):
    """N× count becomes qty, not N bubbles."""
    if repeat:
        n = max(repeat_count(row.get("feature")), int(row.get("qty") or 1))
        if n > 1:
            row["qty"] = n
        row["feature"] = strip_repeat(row.get("feature"))
    else:
        row.pop("qty", None)
    return [row]


def scan_to_rows(d, cfg=None, repeat=True, units="iso_mm"):
    return expand_hole_row(scan_to_row(d, units), cfg, repeat=repeat)
