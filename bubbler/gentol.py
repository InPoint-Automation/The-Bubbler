# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# General tolerances: block read, ladders, one answer.

import re as _re
from collections import namedtuple
from bubbler.common import dp_tol
from bubbler.common import is_limit_value
from bubbler.config import CFG_DEFAULT
from bubbler.config import gentol_ladder
from bubbler.config import gentol_auto
from bubbler.iso2768 import is_angle_feature
from bubbler.iso2768 import is_broken_edge
from bubbler.iso2768 import iso2768_angle_tol
from bubbler.iso2768 import iso2768_radius_tol
from bubbler.iso2768 import iso2768_tol
from bubbler.reader import geometry, grammar  # noqa: E402


_DP_WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4}


# angular row states signed value
_ANG_TAIL =(r"(\u00b1[\s\d.,/\u00b0\u2032\u2033'\"]+"
             r"|\d+(?:[.,]\d+)?\s*(?:\u00b0|[\u2032']))")
_ANG_VAL_RE = _re.compile(
    r"\bANGULAR\b[^0-9\u00b1]{0,16}" + _ANG_TAIL, _re.I)

# ASME bare row needs separator
_ANG_BARE_RE =_re.compile(
    r"\bANGULAR\b[^0-9\u00b1\n]{0,12}[:=]\s*(?:MACH(?:INED)?\.?\s+)?"
    r"(\u00b1?\s*\d+(?:[.,]\d+)?[\s\d.,/\u00b0\u2032\u2033'\"]*)", _re.I)

# ANGLE/ANGLES weak header needs plus-minus
_ANG_WEAK_RE =_re.compile(
    r"\bANGLES?\b[\s:=]{0,4}(±[\s\d.,/°′″'\"]+)", _re.I)


def _ang_value(seg, bare_ok=False):
    """Stated angular tolerance in `seg` -> degrees, or None."""
    has_pm = "\u00b1" in seg
    # "1/2°" is half a degree
    m = _re.search(r"(\d+)\s*/\s*(\d+)", seg)
    if m and float(m.group(2)):
        return float(m.group(1)) / float(m.group(2))
    deg = mins = secs = None
    m = _re.search(r"(\d+(?:[.,]\d+)?)\s*\u00b0", seg)
    if m:
        deg = float(m.group(1).replace(",", "."))
    m = _re.search(r"(\d+(?:[.,]\d+)?)\s*[\u2032']", seg)
    if m:
        mins = float(m.group(1).replace(",", "."))
    m = _re.search(r"(\d+(?:[.,]\d+)?)\s*[\u2033\"]", seg)
    if m:
        secs = float(m.group(1).replace(",", "."))
    if deg is not None or mins is not None or secs is not None:
        return (deg or 0.0) + (mins or 0.0) / 60.0 + (secs or 0.0) / 3600.0
    if has_pm or bare_ok:
        m = _re.search(r"(\d+(?:[.,]\d+)?)", seg)
        if m:
            return float(m.group(1).replace(",", "."))
    return None

# fractional own bucket not decimal-place 0
_FRAC_TOL_RE =_re.compile(
    r"\bFRACTION(?:AL|S)?\b\.?[^0-9\u00b1\n]{0,12}"
    r"\u00b1?\s*(\d+\s*/\s*\d+|\d*[.,]\d+)", _re.I)


def _frac_num(s):
    s = s.replace(" ", "").replace(",", ".")
    try:
        if "/" in s:
            n, d = s.split("/", 1)
            return float(n) / float(d) if float(d) else None
        return float(s)
    except (ValueError, ZeroDivisionError):
        return None


def parse_general_tols(text):
    """Title-block general tolerances -> {decimal_places: ±tol} plus "ang"."""
    out = {}
    t = _re.sub(grammar.LEAD_DOT, "0.", grammar.ascii_pm(text))

    def num(s):
        try:
            return float(s.replace(",", "."))
        except (TypeError, ValueError):
            return None

    for m in _re.finditer(
            r"\b(ONE|TWO|THREE|FOUR)\s+PLACE\s+DECIMAL\s*[:=]?\s*"
            r"\u00b1?\s*([\d.,]+)", t, _re.I):
        v = num(m.group(2))
        if v:
            out[_DP_WORDS[m.group(1).upper()]] = v
    for m in _re.finditer(
            r"\.(X{1,4})\s*[:=]?\s*\u00b1?\s*([\d.,]+)", t, _re.I):
        v = num(m.group(2))
        if v:
            out.setdefault(len(m.group(1)), v)
    # zero placeholders need ladder or header
    zeros = {}
    for m in _re.finditer(
            r"(?<![\d.,])[0X]?[.,](0{1,4})(?![\d.,])[ \t]*[:=]?[ \t]*"
            r"\u00b1[ \t]*([\d.,]*\d)", grammar.ascii_pm(text), _re.I):
        v = num(m.group(2))
        if v:
            zeros.setdefault(len(m.group(1)), v)
    if len(zeros) >= 2 or (zeros and _re.search(
            r"TOLERANC|UNLESS|DECIMAL|TOLERANZ|TOLERANCJ", t, _re.I)):
        for k, v in zeros.items():
            out.setdefault(k, v)
    ang_t = grammar._ANG_WORDS_RE.sub(" ANGULAR ", t)
    v = None
    m = _ANG_VAL_RE.search(ang_t)
    if m:
        v = _ang_value(m.group(1))
    if v is None:
        m = _ANG_BARE_RE.search(ang_t)
        if m:
            v = _ang_value(m.group(1), bare_ok=True)
    if v is None:
        m = _ANG_WEAK_RE.search(ang_t)
        if m:
            v = _ang_value(m.group(1))
    if v:
        out["ang"] = v
    m = _FRAC_TOL_RE.search(t)
    if m:
        v = _frac_num(m.group(1))
        if v:
            out["frac"] = v
    out.update(parse_gentol_bands(t))
    out.update(parse_iso_general(t))
    return out


# on-drawing band table needs plus-minus
_BAND_RE =_re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*"
    r"(?:-|\u2013|\u2014|\.{2,3}|\u2026|\u00f7|>"
    r"|\bUP\s+TO\b|\bTO\b|\bBIS\b|\bDO\b)\s*"
    r"(\d+(?:[.,]\d+)?)\s*(?:MM|CM|IN|(\u00b0))?\s*[:=]?\s*"
    r"\u00b1\s*(\d+(?:[.,]\d+)?)\s*(\u00b0)?",
    _re.I)

# band-table heading words ride with rows
_KIND_ANG_RE =_re.compile(
    r"\bGRAD\b|\bDEG(?:REES?)?\b|\bANGLES?\b|\bWINKEL\w*\b"
    r"|\bK[\u0104A]TOW\w*\b|\bK[\u0104A]TY\b|\bANGULAR\b", _re.I | _re.U)
_KIND_RAD_RE = _re.compile(
    r"\bRADI(?:US|EN|I)\b|\bRUNDUNG(?:EN|SHALBMESSER)?\b|\bHALBMESSER\b"
    r"|\bPROMIE\u0143\b|\bPROMIENI\w*\b|\bFASE(?:N|NH\u00d6HEN?)?\b"
    r"|\bCHAMFERS?\b|\bZAOKR\u0104GLE\u0143\b", _re.I | _re.U)
_KIND_LIN_RE = _re.compile(
    r"\bLINEAR\b|\bLINIOWE\b|\bNENNMA(?:SS|\u00df)\w*\b"
    r"|\bL(?:\u00c4|AE)NGENMA(?:SS|\u00df)E?\b|\bLENGTHS?\b"
    r"|\bWYMIAR\w*\b", _re.I | _re.U)
# filler words real rows carry
_BAND_FILLER_RE =_re.compile(
    r"\b(?:OVER|ABOVE|UP|TO|FROM|UND|AND|\u00dcBER|UEBER|AB|VON|BIS"
    r"|OD|DO|POWY\u017bEJ|MM|CM|IN|INCH|INCHES)\b", _re.I | _re.U)
_BAND_RESIDUE_RE = _re.compile(r"^[\s()\[\]:;.,/+\u00b0-]*$")


def _band_kind(line):
    if _KIND_ANG_RE.search(line):
        return "ang"
    if _KIND_RAD_RE.search(line):
        return "rad"
    return "lin" if _KIND_LIN_RE.search(line) else None


def _band_row_ok(line, spans):
    rest = ""
    at = 0
    for a, b in spans:
        rest += line[at:a]
        at = b
    rest += line[at:]
    for rx in (_KIND_ANG_RE, _KIND_RAD_RE, _KIND_LIN_RE, _BAND_FILLER_RE):
        rest = rx.sub(" ", rest)
    return bool(_BAND_RESIDUE_RE.match(rest))


def parse_gentol_bands(text):
    """On-drawing band table -> {"bands": [(lo, hi, tol)], "bands_ang": ...}"""
    rows = {"lin": [], "ang": [], "rad": []}
    kind = "lin"
    for line in (text or "").split("\n"):
        hits = list(_BAND_RE.finditer(line))
        head = _band_kind(line)
        if not hits:
            if head:
                kind = head
            continue
        if head:
            kind = head
        got = []
        for m in hits:
            try:
                lo = float(m.group(1).replace(",", "."))
                hi = float(m.group(2).replace(",", "."))
                tol = float(m.group(4).replace(",", "."))
            except ValueError:
                continue
            if hi < lo or not tol:
                continue
            # degree sign on row outranks heading
            k = "ang" if (m.group(3) or m.group(5)) else kind
            got.append((k, (lo, hi, tol)))
        if not got or not _band_row_ok(line, [m.span() for m in hits]):
            continue
        for k, row in got:
            rows[k].append(row)
    out = {}
    if rows["lin"]:
        out["bands"] = sorted(rows["lin"])
    if rows["ang"]:
        out["bands_ang"] = sorted(rows["ang"])
    if rows["rad"]:
        out["bands_rad"] = sorted(rows["rad"])
    return out


# [25] basic, (75) ref
_BASIC_REF_FEAT =_re.compile(
    r"^\s*[\[(]\s*\d+(?:[.,]\d+)?\s*[\])]\s*$")


def is_basic_ref_feature(feature):
    return bool(_BASIC_REF_FEAT.match(str(feature or "")))


def basic_ref_kind(feature):
    t = str(feature or "").strip()
    if not is_basic_ref_feature(t):
        return ""
    return "BASIC" if t.startswith("[") else "REF"


def cfg_on(cfg, key):
    v = (cfg or {}).get(key)
    return bool(CFG_DEFAULT.get(key)) if v is None else bool(v)


def inherit_gtols(gtols, pages):
    """Later sheets inherit first sheet's block, marked "inherited"."""
    src = None
    for pg in pages:
        if gtols.get(pg):
            src = gtols[pg]
            break
    if not src:
        return gtols
    for pg in pages:
        if not gtols.get(pg):
            inh = {k: (list(v) if isinstance(v, list) else v)
                   for k, v in src.items()}
            inh["inherited"] = True
            gtols[pg] = inh
    return gtols


def _places_text(g, cap=2):
    places = sorted(k for k in g if isinstance(k, int) and 1 <= k <= 4)
    out = [u".%s \u00b1%g" % ("X" * d, g[d]) for d in places[:cap]]
    if len(places) > cap:
        out.append("..")
    return "  ".join(out)


def gentol_readout(gtols, cfg, session=None, icls=None):
    """(source, value, inherited) linear tolerance in force."""
    src, val, inh = _gentol_readout(gtols, cfg, session)
    if src == GENTOL_SRC_LADDER_ISO and icls:
        val = "-%s  by nominal" % icls
    if gentol_override(session) is not None and src in _GENTOL_PRINTED:
        return (GENTOL_SRC_USER, val, inh)
    hand = (session or {}).get("icls_hand")
    if src == GENTOL_SRC_STD and hand:
        return (GENTOL_SRC_USER, "-%s by nominal" % hand, inh)
    return (src, val, inh)


def _gentol_readout(gtols, cfg, session=None):
    """Readout rules. Call `gentol_readout` instead."""
    ov = gentol_override(session)
    g = ov if ov is not None else (gtols or {})
    inh = bool(g.get("inherited")) and ov is None
    bands = g.get("bands")
    if bands:
        tols = sorted(t for _lo, _hi, t in bands)
        val = (u"\u00b1%g" % tols[0] if tols[0] == tols[-1]
               else u"\u00b1%g..\u00b1%g" % (tols[0], tols[-1]))
        return (GENTOL_SRC_BAND, val, inh)
    txt = _places_text(g)
    if txt:
        return (GENTOL_SRC_BLOCK, txt, inh)
    if g.get("frac"):
        return (GENTOL_SRC_FRAC, u"\u00b1%g" % g["frac"], inh)
    if g.get("iso_std") == "2768":
        cls = g.get("iso_linear") or ""
        return (GENTOL_SRC_STD, ("-%s" % cls if cls else "") +
                " by nominal", inh)
    cfg = cfg or {}
    if gentol_ladder(cfg, session) == "decimal":
        if gentol_auto(cfg, session):
            # inch only. Drawing's ladder first
            tols = ((session or {}).get("dp_tols_inch")
                    or cfg.get("dp_tols_inch") or {})
            ladder = {int(k): v for k, v in tols.items() if str(k).isdigit()}
            txt = _places_text(ladder)
            if txt:
                return (GENTOL_SRC_LADDER_DP, txt, False)
    elif gentol_auto(cfg, session):
        cls = str(cfg.get("default_iso_class", "m"))
        return (GENTOL_SRC_LADDER_ISO, "-%s  by nominal" % cls, False)
    return (GENTOL_SRC_NONE, "", False)


def gentol_kind(h, feature=None):
    """Scan hit -> 'ang' / 'rad' / 'lin'."""
    tp = (h or {}).get("tp")
    if tp == "ANGLE":
        return "ang"
    feat = feature if feature is not None else (h or {}).get("v")
    # "rad" is broken-edge table (is_broken_edge)
    if tp == "EDGE" or is_broken_edge(feat) or (h or {}).get("edge_break"):
        return "rad"
    # bare hand-typed "45 deg" carries no scan type
    if is_angle_feature(feat):
        return "ang"
    return "lin"


EDGE_NO_SIZE = 0.5      # smallest broken-edge rung

GENTOL_BAND_KEY ={"lin": "bands", "rad": "bands_rad", "ang": "bands_ang"}


def band_tol(bands, nominal):
    if not bands or nominal is None:
        return None
    best = None
    for lo, hi, tol in bands:
        if lo <= nominal <= hi and (best is None or hi - lo < best[0]):
            best = (hi - lo, tol)
    return best[1] if best else None


def band_tol_shortest(bands):
    return min(bands)[2] if bands else None


def angle_side_mm(cfg, side_mm=None):
    """Shorter side to index angular table with, or None for unknown."""
    if side_mm is not None:
        return side_mm
    return 0.0 if cfg_on(cfg, "angular_short_side") else None


def angle_gentol(gtols, cfg, cls=None, side_mm=None):
    """Angular general tolerance in DEGREES, or None."""
    return general_tol({"tp": "ANGLE", "nominal": 0.0}, gtols, cfg,
                       icls=cls, iso_on=cls is not None,
                       side_mm=side_mm).value


# answer sources as English tr() keys
GENTOL_SRC_BAND ="band table on the drawing"
GENTOL_SRC_BLOCK = "decimal-place block"
GENTOL_SRC_FRAC = "printed fractional row"
GENTOL_SRC_LADDER_DP = "settings decimal ladder"
GENTOL_SRC_LADDER_ISO = "settings ISO 2768"
GENTOL_SRC_STD = "cited ISO 2768"
GENTOL_SRC_NONE = "none"
GENTOL_SRC_USER = "corrected by hand"

# printed rungs hand correction replaces
_GENTOL_PRINTED =(GENTOL_SRC_BAND, GENTOL_SRC_BLOCK, GENTOL_SRC_FRAC)


def gentol_override(session):
    g = (session or {}).get("gentol_user")
    return dict(g) if isinstance(g, dict) and g else None

# value mm or degrees. kind lin/rad/ang/None
GenTol = namedtuple("GenTol", "value source kind inherited")

NO_GENTOL = GenTol(None, GENTOL_SRC_NONE, None, False)


def gentol_callout(h=None, row=None, **over):
    h = h or {}
    row = row or {}
    c = {"tp": h.get("tp"), "sb": h.get("sb"),
         "type": row.get("type"), "v": h.get("v"),
         "feature": row.get("feature"), "nominal": row.get("nominal"),
         "no_gentol": bool(row.get("no_gentol")),
         "edge_break": bool(row.get("edge_break") or h.get("edge_break")),
         "limit": (row.get("limit") or h.get("limit") or None)}
    if c["v"] is None:
        c["v"] = row.get("feature")
    c.update(over)
    return c


_GENTOL_NEVER_TP = ("GDT", "SURFACE", "THREAD", "FIT", "LIMIT")


def gentol_exempt(callout, cfg=None):
    """Why callout takes NO general tolerance, or None."""
    c = callout or {}
    if c.get("no_gentol"):
        return "flagged"
    if c.get("limit") in ("max", "min"):
        return "own tolerance"
    if str(c.get("tp") or "") in _GENTOL_NEVER_TP:
        return "own tolerance"
    if "(fit " in str(c.get("feature") or ""):
        return "own tolerance"
    t = str(c.get("type") or "")
    if (t.startswith("thread") or t == "GD&T" or t.startswith("finish")
            or t.startswith("position")):
        return "own tolerance"
    if (str(c.get("sb") or "") in ("BASIC", "REF")
            or is_basic_ref_feature(c.get("feature"))
            or is_basic_ref_feature(c.get("v"))):
        return None if cfg_on(cfg, "gentol_basic_ref") else "basic or ref"
    return None


def _gentol_iso(nom, kind, cls, side_mm):
    if kind == "ang":
        return None if side_mm is None else iso2768_angle_tol(side_mm, cls)
    if kind == "rad":
        return iso2768_radius_tol(nom, cls)
    return iso2768_tol(nom, cls)


def _gentol_standard(g, cfg, session, kind, nom, raw, cls, iso_on, side_mm):
    """Config ladder, then standard drawing cites. Last two rungs."""
    lad = gentol_ladder(cfg, session)
    if lad == "decimal":
        if kind != "ang":
            t = dp_tol(raw, cfg, session)
            if t is not None:
                return GenTol(float(t), GENTOL_SRC_LADDER_DP, kind, False)
        return NO_GENTOL._replace(kind=kind)
    if lad != "iso2768" or not iso_on:
        return NO_GENTOL._replace(kind=kind)
    cls = cls or str((cfg or {}).get("default_iso_class",
                                    CFG_DEFAULT["default_iso_class"]))
    t = _gentol_iso(nom, kind, cls, side_mm)
    if t is None:
        return NO_GENTOL._replace(kind=kind)
    src = (GENTOL_SRC_STD if (g or {}).get("iso_std") == "2768"
           else GENTOL_SRC_LADDER_ISO)
    return GenTol(float(t), src, kind, False)


def general_tol(callout, gtols=None, cfg=None, session=None,
                icls=None, iso_on=True, side_mm=None):
    """THE general tolerance for one callout -> GenTol(value, source, ...)."""
    ov = gentol_override(session)
    if ov is not None:
        icls = ov.get("iso_linear") or icls
        res = _general_tol(callout, ov, cfg, session, icls, iso_on, side_mm)
        # only printed rungs replaced
        return (res._replace(source=GENTOL_SRC_USER)
                if res.source in _GENTOL_PRINTED else res)
    return _general_tol(callout, gtols, cfg, session, icls, iso_on, side_mm)


def _general_tol(callout, gtols=None, cfg=None, session=None,
                 icls=None, iso_on=True, side_mm=None):
    """Rules themselves. Call `general_tol` instead."""
    c = callout or {}
    if gentol_exempt(c, cfg):
        return NO_GENTOL
    g = gtols or {}
    inh = bool(g.get("inherited"))
    feat = c.get("feature")
    raw = c.get("v")
    if raw is None:
        raw = feat
    kind = gentol_kind(c, feat if feat not in (None, "") else raw)
    if kind == "lin" and raw not in (None, "") and raw != feat:
        kind = gentol_kind(c, raw)     # "45 deg" wrote "45"
    if is_limit_value(raw) or is_limit_value(feat):
        return NO_GENTOL._replace(kind=kind)
    nom = c.get("nominal")
    if kind == "ang":
        side = angle_side_mm(cfg, side_mm)
        bands = g.get("bands_ang")
        if bands:
            t = band_tol(bands, side) if side is not None else None
            if t is None and side is not None and side <= min(bands)[0]:
                t = band_tol_shortest(bands)  # under table = shortest
            if t is not None:
                return GenTol(float(t), GENTOL_SRC_BAND, "ang", inh)
        if g.get("ang") is not None:
            return GenTol(float(g["ang"]), GENTOL_SRC_BLOCK, "ang", inh)
        return _gentol_standard(g, cfg, session, "ang", None, raw,
                                icls, iso_on, side)
    if nom is None:
        return NO_GENTOL._replace(kind=kind)
    if kind == "rad" and not nom:
        # sizeless edge note reads smallest rung
        nom = EDGE_NO_SIZE
    bands = g.get(GENTOL_BAND_KEY[kind])
    t = band_tol(bands, nom)
    if t is None and kind == "rad" and bands and nom == EDGE_NO_SIZE:
        t = band_tol_shortest(bands)
    if t is not None:
        return GenTol(float(t), GENTOL_SRC_BAND, kind, inh)
    d = dp_of_value(raw)
    if d is not None:
        t = g.get(min(d, 4))
        if t is not None:
            return GenTol(float(t), GENTOL_SRC_BLOCK, kind, inh)
        if d == 0 and g.get("frac") is not None:
            return GenTol(float(g["frac"]), GENTOL_SRC_FRAC, kind, inh)
    return _gentol_standard(g, cfg, session, kind, nom,
                            raw if raw is not None else nom,
                            icls, iso_on, side_mm)


def gentol_reapply_plan(ledger, gtols, cfg, session, override, icls=None):
    """Rows changed by correction -> [(index, old, new)], row order."""
    was = dict(session or {}, gentol_user=None)
    now = dict(session or {}, gentol_user=override or None)
    out = []
    for i, d in enumerate(ledger or []):
        if not isinstance(d, dict):
            continue
        if d.get("tol_max") is not None or d.get("tol_min") is not None:
            continue
        cur = d.get("tol_sym")
        if cur is None:
            continue
        c = gentol_callout(row=d)
        old = general_tol(c, gtols, cfg, was, icls=icls).value
        if old is None or float(cur) != float(old):
            continue                      # came from elsewhere
        new = general_tol(c, gtols, cfg, now, icls=icls).value
        if new is not None and float(new) != float(old):
            out.append((i, float(old), float(new)))
    return out


# ISO 2768 class in title block, DIN/EN/PN forms
_ISO_GEN_RE =_re.compile(
    r"(?:ISO|DIN|EN|PN)(?:[-\s]*(?:ISO|EN))*[-\s]*2?2768"
    r"(?:\s*-\s*[12])?\s*-?\s*([fmcv])\s*([HKL])?(?![A-Za-z])", _re.I)
_ISO_GEN_SPLIT = _re.compile(
    r"(?:ISO|DIN|EN|PN)(?:[-\s]*(?:ISO|EN))*[-\s]*2?2768\s*-\s*2"
    r"\s*-?\s*([HKL])(?![A-Za-z])", _re.I)
_ISO_STD_RE = _re.compile(
    r"(?:ISO|DIN|EN|PN)(?:[-\s]*(?:ISO|EN))*[-\s]*2?2768", _re.I)
_ISO_22081_RE = _re.compile(
    r"ISO\s*22081(?:[^0-9]{0,24}?([\d.,]+)"
    r"((?:\s+[A-Z](?![A-Za-z0-9])){0,3}))?", _re.I)


# spelled-out class, longest first
_ISO_CLASS_WORDS =(
    ("v", ("SEHR GROB", "VERY COARSE", "BARDZO ZGRUBNA")),
    ("f", ("FEIN", "FINE", "DOK\u0141ADNA", "PRECYZYJNA")),
    ("m", ("MITTEL", "MEDIUM", "\u015aREDNIA")),
    ("c", ("GROB", "COARSE", "ZGRUBNA")),
)


def _iso_class_word(text):
    up = (text or "").upper()
    for letter, words in _ISO_CLASS_WORDS:
        for w in words:
            if w in up:
                return letter
    return None


def iso_class_from_gtols(gtols):
    if not gtols:
        return None
    pages = (list(gtols.values())
             if all(isinstance(v, dict) for v in gtols.values())
             else [gtols])
    for page in pages:
        cls = (page or {}).get("iso_linear")
        if cls:
            return cls
    return None


def parse_iso_general(text):
    out = {}
    t = text or ""
    m = _ISO_GEN_RE.search(t)
    if m:
        out["iso_std"] = "2768"
        out["iso_linear"] = m.group(1).lower()
        if m.group(2):
            out["iso_geom"] = m.group(2).upper()
    elif _ISO_STD_RE.search(t):
        out["iso_std"] = "2768"
        word = _iso_class_word(t)
        if word:
            out["iso_linear"] = word
    m2 = _ISO_GEN_SPLIT.search(t)
    if m2:
        out["iso_std"] = "2768"
        out["iso_geom"] = m2.group(1).upper()
    m3 = _ISO_22081_RE.search(t)
    if m3:
        out["iso_std"] = "22081"
        if m3.group(1):
            try:
                out["iso_geom_tol"] = float(m3.group(1).replace(",", "."))
            except ValueError:
                pass
        if m3.group(2) and m3.group(2).strip():
            out["iso_geom_datums"] = m3.group(2).split()
    return out


_ISO_STD_WORD = _re.compile(r"2?2768(?:\s*-\s*([12]))?(?![\d])", _re.I)
# lone class letter, linear and/or geometric
_ISO_CELL_CLASS = _re.compile(r"^([fmcv])?([HKL])?$")
# issue date, dash or label word
_ISO_CELL_SKIP = _re.compile(
    r"^[:\-–(]*\d{4}(?:[-.:]\d{1,2})*\)?$|^[-–:|/]+$|^[^\W\d_]{2,}[.:]?$",
    _re.U)


def iso_class_cells(words):
    out = {}
    ws = [w for w in words if str(w[4]).strip()]
    for s in ws:
        m = _ISO_STD_WORD.search(str(s[4]))
        if not m:
            continue
        part = m.group(1)
        h = max(s[3] - s[1], 1.0)
        row = sorted((w for w in ws if w[0] >= s[2] - 0.5
                      and w[0] - s[2] <= 25 * h
                      and min(w[3], s[3]) - max(w[1], s[1])
                      >= 0.5 * min(h, w[3] - w[1])), key=lambda w: w[0])
        for w in row:
            t = str(w[4]).strip()
            c = _ISO_CELL_CLASS.match(t)
            if c and t:
                lin, geo = c.group(1), c.group(2)
                if part == "1" and geo or part == "2" and lin:
                    break
                if lin:
                    out.setdefault("iso_linear", lin)
                if geo:
                    out.setdefault("iso_geom", geo)
                break
            if _ISO_STD_WORD.search(t) or not _ISO_CELL_SKIP.match(t):
                break
    return out


def dp_of_value(v):
    nums = _re.findall(r"\d+(?:[.,]\d+)?", str(v or ""))
    if not nums:
        return None
    s = nums[-1].replace(",", ".")
    return len(s.split(".", 1)[1]) if "." in s else 0


def _visual_lines(words):
    """Rows by position. Content order can scramble a block."""
    ws = [w for w in words
          if (w[3] - w[1]) <= 1.5 * (w[2] - w[0]) or len(str(w[4])) < 2]
    ws.sort(key=lambda w: ((w[1] + w[3]) / 2.0, w[0]))
    rows = []
    for w in ws:
        cy, h = (w[1] + w[3]) / 2.0, max(w[3] - w[1], 1.0)
        for r in rows[-6:]:
            if abs(cy - r[0]) <= 0.4 * h:
                r[1].append(w)
                break
        else:
            rows.append([cy, [w]])
    return "\n".join(" ".join(str(w[4]) for w in sorted(r[1],
                                                        key=lambda w: w[0]))
                     for r in rows)


def _ladder(g):
    return {k: v for k, v in g.items() if isinstance(k, int)}


def page_general_tols(page, words=None):
    from bubbler.gentol import parse_general_tols, iso_class_cells
    flat = page.get_text("text") or ""
    if not flat.strip() and words:
        return general_tols_from_words(words)
    out = parse_general_tols(flat)
    try:
        pw = page.get_text("words")
        if int(page.rotation or 0) % 360:
            m = page.rotation_matrix
            pw = [geometry.xform_rect(m, *w[:4]) + tuple(w[4:]) for w in pw]
        seen = _ladder(parse_general_tols(_visual_lines(pw)))
    except Exception:
        seen = {}
    # label and value on one row win
    if len(seen) >= max(2, len(_ladder(out))) and seen != _ladder(out):
        for k in _ladder(out):
            out.pop(k)
        out.update(seen)
    if out.get("iso_std") != "2768" or (
            out.get("iso_linear") and out.get("iso_geom")):
        return out
    try:
        words = page.get_text("words")
        m = page.rotation_matrix if int(page.rotation or 0) % 360 else None
    except Exception:
        return out
    if m is not None:
        words = [geometry.xform_rect(m, *w[:4]) + tuple(w[4:]) for w in words]
    for k, v in iso_class_cells(words).items():
        out.setdefault(k, v)
    return out


def general_tols_from_words(words):
    from bubbler.reader import layout
    text = "\n".join(" ".join(str(t) for t in ln)
                     for ln in layout.reading_order_lines(words))
    out = parse_general_tols(text)
    if out.get("iso_std") == "2768" and not (
            out.get("iso_linear") and out.get("iso_geom")):
        for k, v in iso_class_cells(words).items():
            out.setdefault(k, v)
    if out:
        out["ocr"] = True
    return out
