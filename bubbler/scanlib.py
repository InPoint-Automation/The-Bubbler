# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Callout regex, glyph healing, classify to ledger rows.

import re as _re
from collections import namedtuple

from .common import dp_tol, is_limit_value, mode_admits_tp
from .config import CFG_DEFAULT, gentol_ladder, units_of
from .i18n import tr
from .iso2768 import (iso2768_angle_tol, iso2768_radius_tol, iso2768_tol,
                      is_angle_feature, is_broken_edge)

FITS = ("H", "G", "F", "E", "D", "C", "JS", "J", "K", "M",
        "N", "P", "R", "S", "T", "U")

_GDT_SYMBOLS = (
    ("⌖", " TRUE POSITION "),
    ("⊕", " TRUE POSITION "),
    ("⨁", " TRUE POSITION "),
    ("⌭", " CYLINDRICITY "),
    ("▱", " FLATNESS "),
    ("◎", " CONCENTRICITY "),
    ("◯", " CIRCULARITY "),
    ("⌒", " PROFILE OF A LINE "),
    ("⌓", " PROFILE OF A SURFACE "),
    ("⌰", " TOTAL RUNOUT "),
    ("↗", " CIRCULAR RUNOUT "),
    ("⟂", " PERPENDICULARITY "),
    ("⊥", " PERPENDICULARITY "),
    ("∥", " PARALLELISM "),
    ("∠", " ANGULARITY "),
    ("⏥", " FLATNESS "),          # ASME codepoint
    ("○", " CIRCULARITY "),        # ASME codepoint
    ("⏤", " STRAIGHTNESS "),
    ("⌯", " SYMMETRY "),
)


# DE/PL angular gentol row names, whole words only
_ANG_WORDS_RE = _re.compile(
    r"\bANGULAR\b"
    r"|\bWINKEL(?:GR(?:OE|\u00d6)(?:SS|\u00df)EN)?"
    r"(?:MA(?:SS|\u00df)E?N?|TOLERANZ(?:EN)?|ABWEICHUNG(?:EN)?)\b"
    r"|\bK[\u0104A]TOW(?:E|A|EJ|YCH|YMI|YM|Y)?\b"
    r"|\bK[\u0104A]TY\b", _re.I | _re.U)


def ascii_pm(t):
    """ASCII '+/-' and '+-' -> plus-minus sign."""
    t = _re.sub(r"\+\s*/\s*-(?=\s*[\d.,])", "\u00b1", t or "")
    return _re.sub(r"(?<![\d.,])\+-(?=\s*[\d.,])", "\u00b1", t)


def scan_normalize(t):
    """Heal PDF text-layer artifacts before classification."""
    t = (t.replace("\u00f8", "\u00d8")
         .replace("\u2300", "\u00d8").replace("\u2205", "\u00d8")
         .replace("\uf044", "\u00d8").replace("\uf064", "\u00d8")
         .replace("\uf052", "\u00b1").replace("\uf072", "\u00b1")
         .replace("\uf030", "\u00b0")
         .replace("\u2212", "-").replace("\u2013", "-")
         .replace("\u2011", "-"))
    t = ascii_pm(t)
    t = _re.sub(r"(?<![\w.])\.(?=\d)", "0.", t)
    t = _re.sub("[\u00c6\u00e6](?=\\s*\\d)", "\u00d8", t)
    # phi look-alikes, digit after and no word before
    t = _re.sub(r"(?<![A-Za-z0-9.,])"
                r"[OoQ\u03a6\u03c6\u03d5\u0424\u0398\u03b8](?=\d)",
                "\u00d8", t)
    t = _re.sub(r"(?<![\dA-Za-z.,/+\-])0(?=\d{1,3}(?:[.,]\d+)?(?![\d.,\-]))",
                "\u00d8", t)
    t = _re.sub(r"([+\-]\d+[.,]\d+)(?=[+\-]\d+[.,]\d+)", r"\1/", t)
    t = _re.sub(r"\bDIAM?\b\.?(?=\s*[\d.])", "\u00d8", t, flags=_re.I)
    t = _re.sub("([0-9.])\u00b1", "\\1 \u00b1", t)
    t = _re.sub("\u00b1([0-9.])", "\u00b1 \\1", t)
    t = _re.sub(r"(\d)\s+\.\s*(\d)", r"\1.\2", t)
    t = _re.sub(r"(\d)\s*\.\s+(\d)", r"\1.\2", t)
    t = _re.sub(r"\bTHROUGH\b", "THRU", t, flags=_re.I)
    t = _re.sub("\\bPRZELOT(?:OWY|OWE)?\\b|\\bPRZEJŚCIOW[YEA]\\b",
                "THRU", t, flags=_re.I)
    t = _re.sub(r"\bDURCHGANGS(?:LOCH|BOHRUNG)?\b|"
                r"\bDURCHGE(?:HEND|BOHRT)\b|"
                r"\bDURCHBOHR(?:EN|UNG|T)?\b|"
                r"\bDURCHGANG\b|\bDURCH\b", "THRU", t, flags=_re.I)
    t = _re.sub("\\bG\u0141\u0118B\\.?\\b|\\bG\u0141\\.?\\b", "DEEP",
                t, flags=_re.I)
    t = _re.sub(r"\bTIEFE?\b", "DEEP", t, flags=_re.I)
    t = _re.sub(r"\bDP\.?(?=\s*[\d.])", "DEEP ", t, flags=_re.I)
    t = _re.sub(r"\bDURCHMESSER\b|\bDMR\.?\b(?=\s*[\d.])", "\u00d8", t,
                flags=_re.I)
    t = _re.sub("\\b\u015aREDNICA\\b|\\b\u015aR\\.?\\b(?=\\s*[\\d.])",
                "\u00d8", t, flags=_re.I)
    t = _re.sub("\\b(?:RADIUS|PROMIE\u0143)\\b\\s*(?=[\\d.])", "R", t,
                flags=_re.I)
    t = _re.sub(r"\b(?:FASE|FAZA|FAZOWANIE)\b\s*(?=[\d.])", "C", t,
                flags=_re.I)
    t = _re.sub(r"(\d+(?:[.,]\d+)?)\s*(?:\"|mm)?\s*"
                r"(?:CHAMFER|CHAM\b\.?)", r"C\1", t, flags=_re.I)
    t = _re.sub("\\bPOG\u0141\u0118BIENIE\\s+WALCOWE\\b|"
                "\\bFLACHSENKUNG\\b|\\bSPOTFACE\\b|"
                "\\bSF\\.?\\b(?=\\s*[\u00d8\\d.])",
                " CBORE ", t, flags=_re.I)
    t = _re.sub("\\bPOG\u0141\u0118BIENIE\\s+STO\u017bKOWE\\b|"
                "\\bANSENKUNG\\b|\\bSENKUNG\\b",
                " CSINK ", t, flags=_re.I)
    t = _re.sub("(\\d+)\\s*(?:PLACES|PLCS|OTWOR(?:Y|\u00d3W)|OTW|"
                "STK|ST\u00dcCK|MAL)\\.?", "\\1X", t, flags=_re.I)
    for _s in ("\u2334", "\u2294"):
        t = t.replace(_s, " CBORE ")
    for _s in ("\u2335", "\u2228", "\u22c1"):
        t = t.replace(_s, " CSINK ")
    for _s in ("\u21a7", "\u2913", "\u25bd", "\u25bf",
               "\u25bc", "\u25be", "\u2207", "\u22bd", "\u23f7",
               "\u2304"):
        t = t.replace(_s, " DEEP ")
    t = _re.sub(r"//(?=\s*[\d.,])", " PARALLELISM ", t)
    if any(s in t for s, _ in _GDT_SYMBOLS):
        for _sym, _kw in _GDT_SYMBOLS:
            t = t.replace(_sym, _kw)
    t = _re.sub(r"[ \t]{2,}", " ", t)
    lines = []
    for l in t.split("\n"):
        l = _re.sub(r"(\d)\s+(\.[\d]{2,4})(?!\d)", r"\1\2", l)
        l = _re.sub(r"(\+\s*[\d.]+)\s*(-\s*[\d.]+)", r"\1/\2", l)
        lines.append(l)
    healed = lines
    _DEV = r"^(?:[+\-]\s*[\d.,]+|0(?:[.,]\d+)?)$"
    _SGN = ("+", "-")
    for i in range(len(healed) - 2):
        a = healed[i].strip()
        b = healed[i + 1].strip()
        c = healed[i + 2].strip()
        if (_re.search(r"[\d]$", a) and
                _re.match(_DEV, b) and _re.match(_DEV, c) and
                not (b == "0" and c == "0") and
                (b.startswith(_SGN) or c.startswith(_SGN))):
            healed[i] = a + " " + b.replace(" ", "") + "/" + \
                c.replace(" ", "")
            healed[i + 1] = healed[i + 2] = ""
    for i in range(len(healed) - 1):
        a = healed[i].strip()
        b = healed[i + 1].strip()
        if (a and _re.search(r"\d\s*[+\-][\d.,]*\d$", a) and
                "/" not in a.rsplit(None, 1)[-1] and
                _re.match(_DEV, b)):
            healed[i] = a + "/" + b.replace(" ", "")
            healed[i + 1] = ""
    for i in range(len(healed) - 1):
        a, b = healed[i].strip(), healed[i + 1].strip()
        if _re.match(r"^\d+[Xx\u00d7]$", a) and _re.match(r"^[.\d]", b):
            healed[i] = a + " " + b
            healed[i + 1] = ""
        elif _re.match(r"^[.\d]+$", a) and _re.match(r"^\d+[Xx\u00d7]$", b):
            healed[i] = b + " " + a
            healed[i + 1] = ""
    return "\n".join(l for l in healed if l != "")


def _fit_ok(code):
    return code[:2].rstrip("0123456789").upper() in FITS


# every line-break character
_GDT_NOBREAK = r"[^\S\r\n\v\f\x1c-\x1e\x85\u2028\u2029]"

# projected/unequal zone letter
_MOD_PU =r"(?:\(\s*[PU]\s*\)|[\u24c5\u24ca]|[PU](?![A-Za-z]))"
_MOD_OTHER = (r"(?:\(\s*[MLSPFTUE]\s*\)|MMC|LMC|RFS"
              r"|[\u24c2\u24c1\u24c8\u24c5\u24bb\u24c9\u24ca\u24ba]"
              r"|[MLSP]\b)")
_MOD_NUM = (r"(?:" + _GDT_NOBREAK + r"*(?:\d+(?:[.,]\d+)?|[.,]\d+)"
            r"(?!" + _GDT_NOBREAK + r"*[Xx\u00d7]))?")
_MOD_ONE = r"(?:" + _MOD_PU + _MOD_NUM + r"|" + _MOD_OTHER + r")"
# {0,8} allows doubled OCR glyph
_GDT_MOD =(r"(?P<mods>(?:" + _GDT_NOBREAK + r"*" + _MOD_ONE + r"){0,8})")
# re.I for SCAN_PATS lower case
_MOD_SCAN =_re.compile(r"(" + _MOD_PU + r")(" + _MOD_NUM.rstrip("?") + r")?"
                        r"|(" + _MOD_OTHER + r")", _re.I)

# ONE modifier vocabulary
GDT_MOD_LETTERS = "MLSPFTUE"
# bare letter claimed only here
GDT_MOD_BARE = "MLSPU"
GDT_MOD_TAKES_NUM = "PU"

_MOD_TXT = {"Ⓜ": "M", "Ⓛ": "L", "Ⓢ": "S", "Ⓟ": "P",
            "Ⓕ": "F", "Ⓣ": "T", "Ⓤ": "U", "Ⓔ": "E",
            "MMC": "M", "LMC": "L", "RFS": "S"}

# ISO 1101/14405 zone qualifiers between tolerance and datums
_ISO_ZONE =(r"(?P<zone>(?:\s*(?:UZ\s*[+-]\s*\d+(?:[.,]\d+)?"
             r"|CZ|SZ|OZ|CT|ACS|ACL|VA)(?![A-Za-z0-9])){0,3})")

# ISO 14405-1 size modifiers, non-capturing on purpose
_SIZE_TOKENS =("LP", "LS", "GG", "GX", "GN", "CC", "CA", "CV",
                "SX", "SN", "SA", "SM", "SD", "ACS", "ACL")
_SIZE_MOD = (r"(?:\s*(?:\u24ba|\(\s*E\s*\)|"
             + "|".join(_SIZE_TOKENS) + r")(?![A-Za-z0-9]))?")
_SIZE_MOD_RE = _re.compile(r"(?:^|[\s)])(\u24ba|\(\s*E\s*\)|"
                           + "|".join(_SIZE_TOKENS) + r")(?![A-Za-z0-9])")


# spherical S read off pattern match
_SPH_RE =_re.compile(r"(?:^|[\s,(])S(?=[R\u00d8])")


def _spherical(m):
    """ 'S' when match is spherical radius/diameter, else ''. """
    return "S" if _SPH_RE.search(m.group(0)) else ""


# claim note size before LINEAR re-reads it
_EDGE_SIZE =(r"(?:[ \t:]*(?:R[ \t]*)?(?:MAX[ \t]*)?\d+(?:[.,]\d+)?"
              r"(?:[ \t]*[-\u2013][ \t]*\d+(?:[.,]\d+)?)?)?")
_EDGE_RANGE = _re.compile(r"(\d+(?:[.,]\d+)?)[ \t]*[-\u2013][ \t]*"
                          r"(\d+(?:[.,]\d+)?)")
_EDGE_ONE = _re.compile(r"(?:MAX[ \t]*)?(\d+(?:[.,]\d+)?)", _re.I)


def _edge_num(t):
    return t.replace(",", ".")


def _edge_note(m):
    """ "break sharp edges 0,2-0,5" -> ("EDGE 0.2-0.5", "0.2/0.5"). """
    tail = m.group(0)
    rng = _EDGE_RANGE.search(tail)
    if rng:
        lo, hi = _edge_num(rng.group(1)), _edge_num(rng.group(2))
        return ("EDGE " + lo + "-" + hi, lo + "/" + hi)
    one = _EDGE_ONE.search(tail)
    if one:
        hi = _edge_num(one.group(1))
        return ("EDGE " + hi + " MAX", "0/" + hi)
    return ("EDGE BREAK", None)


_EDGE_SIGNED = _re.compile(r"^([+\-\u00b1]?)[ \t]*(\d+(?:[.,]\d+)?)$")


def edge_from_values(vals):
    """Signed numbers beside edge symbol -> ("EDGE ...", limits) or None."""
    seen = []
    for v in vals or ():
        m = _EDGE_SIGNED.match(str(v).strip())
        if m:
            seen.append((m.group(1) or "", m.group(2).replace(",", ".")))
    if not seen:
        return None
    both = next((n for sg, n in seen if sg == "\u00b1"), None)
    if both is not None:
        return ("EDGE ISO 13715 \u00b1" + both, "-" + both + "/+" + both)
    plus = [n for sg, n in seen if sg == "+"]
    minus = [n for sg, n in seen if sg == "-"]
    # stacked pair can share sign
    if len(plus) > 1 or len(minus) > 1:
        sg = "+" if len(plus) > 1 else "-"
        lo, hi = sorted((plus if sg == "+" else minus)[:2], key=float)
        return ("EDGE %s%s/%s%s" % (sg, lo, sg, hi),
                "%s%s/%s%s" % (sg, lo, sg, hi) if sg == "+"
                else "-%s/-%s" % (hi, lo))
    plus = plus[0] if plus else None
    minus = minus[0] if minus else None
    if plus is not None and minus is not None:
        return ("EDGE +%s/-%s" % (plus, minus), "-%s/+%s" % (minus, plus))
    if plus is not None:
        return ("EDGE ISO 13715 +" + plus, "0/+" + plus)
    if minus is not None:
        return ("EDGE ISO 13715 -" + minus, "-" + minus + "/0")
    bare = seen[0][1]
    return ("EDGE " + bare + " MAX", "0/" + bare)


def _edge_glyph(m):
    """Detected edge symbol plus value(s) beside it."""
    vals = _re.findall(r"[+\-\u00b1][ \t]*\d+(?:[.,]\d+)?", m.group(1))
    got = edge_from_values([v.replace(" ", "").replace("\t", "")
                            for v in vals])
    return got if got else ("EDGE BREAK", None)


def _edge_iso(m):
    """ISO 13715 edge callout, sign gives direction."""
    if not m.group(1):
        return ("EDGE ISO 13715", None)
    val = _edge_num(m.group(2))
    if m.group(1) == "+":
        return ("EDGE ISO 13715 +" + val, "0/+" + val)
    return ("EDGE ISO 13715 -" + val, "-" + val + "/0")


def _size_mod(m):
    """ ' LP' / ' E' ISO 14405 size modifier inside match, or ''. """
    hit = _SIZE_MOD_RE.search(m.group(0))
    if not hit:
        return ""
    tok = _re.sub(r"[\s()]", "", hit.group(1)).upper()
    return " " + ("E" if tok == "\u24ba" else tok)


# circled lead modifier stepped over
_GDT_LEADMOD =(r"(?:[\u24c2\u24c1\u24c8\u24c5\u24bb\u24c9\u24ca\u24ba]"
                + _GDT_NOBREAK + r"*)?")
# step-over on both branches
_GDT_VAL =(r"(?:" + _GDT_NOBREAK + r"*" + _GDT_LEADMOD
            + r"(?:(?<![A-Za-z])S" + _GDT_NOBREAK + r"*)?\u00d8"
            + _GDT_NOBREAK + r"*|\s*" + _GDT_LEADMOD
            + r")(?=[.,]*\d)([\d.,]+)")

# ASME/ISO frame notes between tolerance and datums
_GDT_NOTE =(r"(?:\s*(?:SEP\s*REQT|ST|CF|UF|NC|\u2194|"
             + "|".join(_SIZE_TOKENS) + r")(?![A-Za-z0-9]))*")

# per-unit tolerance "0.05/100" or "0.05/25x25"
_GDT_PER =(r"(?P<per>\s*/\s*\d+(?:[.,]\d+)?"
            r"(?:\s*[Xx\u00d7]\s*\d+(?:[.,]\d+)?)?)?")

_DATUM_MOD = (r"(?:\s*(?:\(\s*[MLSPFT]\s*\)"
              r"|[\u24c2\u24c1\u24c8\u24c5\u24bb\u24c9]))?")
# compound datum "A-B" is one datum
_GDT_DATUM =(r"(?P<datums>(?:\s+[A-Z](?:-[A-Z])*(?![A-Za-z0-9])"
              + _DATUM_MOD + r"){0,3})")

_GDT_MAX_DATUMS = {
    "FLATNESS": 0, "STRAIGHTNESS": 0, "CIRCULARITY": 0, "CYLINDRICITY": 0,
    "POSITION": 3, "PROFILE": 3,
    "PROFILE OF A LINE": 3, "PROFILE OF A SURFACE": 3,
    "CIRCULAR RUNOUT": 2, "TOTAL RUNOUT": 2,
    "PERPENDICULARITY": 3, "PARALLELISM": 3, "ANGULARITY": 3,
    "RUNOUT": 2, "CONCENTRICITY": 2, "SYMMETRY": 3,
}

# characteristics whose zone MAY be cylindrical
GDT_DIA_OK =("POSITION", "STRAIGHTNESS", "PERPENDICULARITY",
              "PARALLELISM", "ANGULARITY", "CONCENTRICITY", "COAXIALITY")


# spherical zone SØ only POSITION
GDT_SPH_OK =("POSITION",)


def gdt_zone_wrong(name, mark):
    """Zone marker impossible for characteristic?"""
    if not mark:
        return False
    if mark.startswith("S"):
        return not any(k in (name or "").upper() for k in GDT_SPH_OK)
    return gdt_no_dia_zone(name)


def gdt_no_dia_zone(name):
    """Zone never cylindrical? Name is string or word sequence."""
    if not isinstance(name, str):
        name = " ".join(name or ())
    name = name.upper()
    return not any(k in name for k in GDT_DIA_OK)


def gdt_flag(h, code):
    """Record review flag on hit (scanreview.FCF_SUSPECT reads it)."""
    fl = h.setdefault("fcf_flags", [])
    if code not in fl:
        fl.append(code)


def _gdt_lead_zero(h):
    """ '.5' -> '0.5', spelling vision._fcf_tol_parts uses. """
    t = h.get("t") or ""
    if not t[:1] in (".", ","):
        return h
    h["t"] = "0" + t
    v = h.get("v") or ""
    h["v"] = v.replace(" " + t, " 0" + t, 1).replace("Ø" + t, "Ø0" + t, 1)
    return h


def gdt_zone_check(h):
    """Ø characteristic cannot have is scan damage."""
    if h.get("tp") != "GDT":
        return h
    _gdt_lead_zero(h)
    if not gdt_zone_wrong(h.get("sb"), _gdt_zone_mark(h.get("raw") or "")):
        return h
    h["fcf_zone_suspect"] = True
    gdt_flag(h, "zone_suspect")
    return h


def _gdt_modifier(m):
    """ ' M P25', modifiers in printed order. """
    try:
        raw = m.group("mods")
    except (IndexError, _re.error):
        return ""
    if not raw or not raw.strip():
        return ""
    out = []
    for hit in _MOD_SCAN.finditer(raw):
        tok = hit.group(1) or hit.group(3) or ""
        tok = _re.sub(r"[\s()]", "", tok).upper()
        if not tok:
            continue
        txt = _MOD_TXT.get(tok, tok)
        num = _re.sub(r"\s+", "", hit.group(2) or "") if hit.group(1) else ""
        if num[:1] in (".", ","):
            num = "0" + num                    # ".5" -> "0.5"
        out.append(txt + num)
    return (" " + " ".join(out)) if out else ""


def _gdt_datums(m, subtype=None):
    """ ' | A | B | C' datum suffix for GD&T feature string, or ''. """
    try:
        raw = m.group("datums")
    except (IndexError, _re.error):
        return ""
    cap = _GDT_MAX_DATUMS.get(subtype, 3)
    if cap == 0 or not raw or not raw.strip():
        return ""
    # keep print spelling W61(c)
    parts = [_re.sub(r"\s+", "", d).upper()
             for d in _re.findall(r"[A-Z](?:-[A-Z])*" + _DATUM_MOD,
                                  raw, _re.I)]
    parts = parts[:cap]
    return (" | " + " | ".join(parts)) if parts else ""


def _chamfer(m):
    """Chamfer 'leg X angle deg' for plausible angle 0 < a <= 60."""
    try:
        a = float(m.group(2).replace(",", "."))
    except ValueError:
        return (None, None)
    if not (0 < a <= 60):
        return (None, None)
    return (m.group(1).replace(",", ".") + "X" + ("%g" % a) + "°", None)


_ZONE_SCAN = _re.compile(r"UZ\s*[+-]\s*\d+(?:[.,]\d+)?"
                         r"|CZ|SZ|OZ|CT|ACS|ACL|VA", _re.I)


def _iso_zone(m):
    """ ' CZ' / ' UZ+0,1 CZ', zone qualifiers. """
    try:
        raw = m.group("zone")
    except (IndexError, _re.error):
        return ""
    if not raw or not raw.strip():
        return ""
    parts = [_re.sub(r"\s+", "", z).upper()
             for z in _ZONE_SCAN.findall(raw)]
    return (" " + " ".join(parts)) if parts else ""


def _gdt_zone_mark(g):
    """Zone marker print drew -> 'SØ', 'Ø' or ''."""
    up = g.upper()
    at = up.find("\u00d8")
    if at < 0:
        return ""
    # OCR splits marker ("S", "Ø0.5")
    pre = up[:at].rstrip()
    # S abuts Ø and is its own token
    if pre.endswith("S") and not (len(pre) > 1 and pre[-2].isalpha()):
        return "S\u00d8"
    return "\u00d8"


def _gdt_per(m):
    """ '/100' or '/25X25' per-unit basis, or ''. """
    try:
        raw = m.group("per")
    except (IndexError, _re.error):
        return ""
    if not raw:
        return ""
    return _re.sub(r"\s+", "", raw).replace("x", "X").replace("×", "X")


def _gdt(name, m):
    """NAME [Ø]value [mod] [zone] [| datums]."""
    val = m.group(1)
    # print marker echoed never invented
    tolzone = _gdt_zone_mark(m.group(0)) + val
    return (name + " " + tolzone + _gdt_per(m) + _gdt_modifier(m)
            + _iso_zone(m) + _gdt_datums(m, name))


# earlier patterns claim spans first
SCAN_PATS = [
    ("THREAD", None,
     r"(?<![A-Za-z])M\s*\d+(?:[.,]\d+)?(?:\s*[xX\u00d7]\s*\d+(?:[.,]\d+)?)?"
     r"(?:\s*-\s*[4-8][gGhH])?",
     lambda m: (m.group(0).strip(), None)),
    ("THREAD", None,
     r"(?:\d+/\d+|#\d+)\s*-\s*\d+\s*(?:UNC|UNF|UNEF|NPT|NPTF|BSP)?",
     lambda m: (m.group(0).strip(), None)),
    ("GDT", "POSITION",
     r"(?:TRUE\s*POS(?:ITION)?|T\.P\.)" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("POSITION", m), m.group(1))),
    ("GDT", "FLATNESS", r"FLATNESS" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("FLATNESS", m), m.group(1))),
    ("GDT", "STRAIGHTNESS", r"STRAIGHTNESS" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("STRAIGHTNESS", m), m.group(1))),
    ("GDT", "CIRCULARITY", r"(?:CIRCULARITY|ROUNDNESS)" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("CIRCULARITY", m), m.group(1))),
    ("GDT", "CYLINDRICITY", r"CYLINDRICITY" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("CYLINDRICITY", m), m.group(1))),
    ("GDT", "PARALLELISM", r"PARALLELISM" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("PARALLELISM", m), m.group(1))),
    ("GDT", "PERPENDICULARITY",
     r"PERP(?:ENDICUL(?:ARITY)?)?" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("PERPENDICULARITY", m), m.group(1))),
    ("GDT", "ANGULARITY", r"ANGULARITY" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("ANGULARITY", m), m.group(1))),
    ("GDT", "CIRCULAR RUNOUT",
     r"CIRCULAR\s*(?:RUNOUT|TIR|FIM)" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("CIRCULAR RUNOUT", m), m.group(1))),
    ("GDT", "TOTAL RUNOUT",
     r"TOTAL\s*(?:RUNOUT|TIR|FIM)" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("TOTAL RUNOUT", m), m.group(1))),
    ("GDT", "RUNOUT",
     r"(?:RUNOUT|TIR|FIM)" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("RUNOUT", m), m.group(1))),
    ("GDT", "SYMMETRY", r"SYMMETRY" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("SYMMETRY", m), m.group(1))),
    ("GDT", "CONCENTRICITY",
     r"(?:CONCENTRICITY|COAXIALITY)" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("CONCENTRICITY", m), m.group(1))),
    ("GDT", "PROFILE OF A SURFACE",
     r"PROFILE\s*OF\s*A?\s*SURFACE" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("PROFILE OF A SURFACE", m), m.group(1))),
    ("GDT", "PROFILE OF A LINE",
     r"PROFILE\s*OF\s*A?\s*LINE" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("PROFILE OF A LINE", m), m.group(1))),
    ("GDT", "PROFILE",
     r"PROFILE" + _GDT_VAL + _GDT_PER + _GDT_MOD + _ISO_ZONE + _GDT_NOTE + _GDT_DATUM,
     lambda m: (_gdt("PROFILE", m), m.group(1))),
    ("SURFACE", None,
     r"(?:Rmax|Rsm|Ra|Rz|Rq|Rt|Rp|Rv)\s*(?:=\s*)?"
     r"([\d.,]+)(?:\s*[-\u2013]\s*([\d.,]+))?\s*"
     r"(?:[\u00b5u]in|[\u00b5u]m|micron)?\s*(MAX|MIN)?",
     lambda m: (_re.sub(r"\s+", " ", m.group(0).strip()), None)),
    ("FIT", None,
     r"(?:(\d+)\s*[Xx\u00d7]\s*)?(\u00d8?)[ \t]*(\d+(?:[.,]\d+)?)[ \t]*"
     r"((?:[A-Z]{1,2}|[a-z]{1,2})[ ]?\d{1,2}(?:\s*/\s*"
     r"(?:[A-Z]{1,2}|[a-z]{1,2})[ ]?\d{1,2})?)(?![\w\u00b0])",
     lambda m: (((m.group(1) + "X " if m.group(1) else "") +
                 m.group(2) + m.group(3) + " " +
                 m.group(4).replace(" ", ""))
                if _fit_ok(m.group(4).replace(" ", ""))
                else None, m.group(4).replace(" ", ""))),
    ("DIAMETER", "CBORE",
     r"(?:C'?BORE|CBORE|\u2334)\s*\u00d8\s*(\d+(?:[.,]\d+)?)",
     lambda m: ("CBORE \u00d8" + m.group(1), None)),
    ("DIAMETER", "CBORE",
     r"\u00d8\s*(\d+(?:[.,]\d+)?)\s*(?:C'?BORE|CBORE|\u2334)",
     lambda m: ("CBORE \u00d8" + m.group(1), None)),
    ("DIAMETER", "CBORE",
     r"(?:C'?BORE|CBORE|\u2334)\s*(\d+(?:[.,]\d+)?)",
     lambda m: ("CBORE " + m.group(1), None)),
    ("DIAMETER", "CSINK",
     r"(?:C'?SINK|CSK|\u2335)\s*\u00d8?\s*(\d+(?:[.,]\d+)?)"
     r"(?:\s*[xX\u00d7]\s*(\d+(?:[.,]\d+)?)\s*\u00b0?)?",
     lambda m: ("CSINK \u00d8" + m.group(1) +
                (" X" + m.group(2) + "\u00b0" if m.group(2) else ""), None)),
    ("DIAMETER", "CSINK",
     r"\u00d8\s*(\d+(?:[.,]\d+)?)\s*[xX\u00d7]\s*(\d+(?:[.,]\d+)?)\s*\u00b0",
     lambda m: ("CSINK \u00d8" + m.group(1) + " X" + m.group(2) + "\u00b0",
                None)),
    # general edge condition, ISO 2768-1 Table 2
    ("EDGE", None,
     r"(?:(?:BREAK|DEBURR)[^\n]{0,24}?EDGES?"
     r"|KANTEN[^\n]{0,12}?BRECHEN"
     r"|ST\u0118PI\u0106[^\n]{0,24}?KRAW\u0118DZI\w*)"
     + _EDGE_SIZE,
     lambda m: _edge_note(m)),
    ("EDGE", None,
     r"ISO[ \t]*13715(?:[^\n]{0,12}?([+\-])[ \t]*(\d+(?:[.,]\d+)?))?",
     lambda m: _edge_iso(m)),
    # injected edge glyph before its value
    ("EDGE", None,
     r"\bEDGE[ \t]*((?:[+\-\u00b1][ \t]*\d+(?:[.,]\d+)?[ \t]*){1,2})",
     lambda m: _edge_glyph(m)),
    ("DEPTH", None,
     r"(?<![\d\u00d8.,\u00b1+\-])(?<!\u00d8 )(\d+(?:[.,]\d+)?)\s*(?:DEEP|DEPTH|\u21a7)\b",
     lambda m: ("DEEP " + m.group(1), None)),
    ("DEPTH", None,
     r"\b(?:DEEP|DEPTH|\u21a7)\b\.?\s*\u00d8?\s*(\d+(?:[.,]\d+)?)",
     lambda m: ("DEEP " + m.group(1), None)),
    # MIN/MAX one-sided-open claimed before DIAMETER/RADIUS
    ("LIMIT", None,
     r"(?<![A-Za-z0-9])(S?\u00d8|S?R)?\s*(\d+(?:[.,]\d+)?)\s*"
     r"(MIN|MAX)\.?(?![A-Za-z])",
     lambda m: ((m.group(1) or "") + m.group(2) + " "
                + m.group(3).upper(), None)),
    ("DIAMETER", None,
     r"(?:(\d+)\s*[Xx\u00d7]\s*)?(?:(?<![A-Za-z0-9])S)?"
     r"\u00d8\s*(\d+(?:[.,]\d+)?)"
     + _SIZE_MOD + r"\s*"
     r"((?:(?<![\d.,])0(?=\s*/)|[+\-\u00b1]\s*\d*[.,]?\d+)"
     r"(?:\s*/\s*(?:0(?:[.,]\d+)?(?![\d.,])|[+\-]\s*\d*[.,]?\d+))?)?"
     + _SIZE_MOD,
     lambda m: ((m.group(1) + "X " if m.group(1) else "") +
                _spherical(m) + "\u00d8" + m.group(2) + _size_mod(m),
                m.group(3).replace(" ", "") if m.group(3) else None)),
    ("RADIUS", None,
     r"(?:^|[\s,(])S?R\s*(\d+(?:[.,]\d+)?)(?:\s*\u00b1\s*([\d.,]+))?",
     lambda m: (_spherical(m) + "R" + m.group(1),
                ("\u00b1" + m.group(2)) if m.group(2) else None)),
    # decimals both sides, integer pair excluded
    ("SLOT", None,
     r"(?<![\u00d8\d,.])(\d+[.,]\d+)\s*[Xx\u00d7]\s*(\d+[.,]\d+)(?!\s*[\u00b0Xx\u00d7\d])",
     lambda m: (m.group(1) + " X " + m.group(2), None)),
    ("CHAMFER", None,
     r"(\d+(?:[.,]\d+)?)\s*[xX\u00d7]\s*(\d+(?:[.,]\d+)?)\s*\u00b0",
     lambda m: _chamfer(m)),
    ("CHAMFER", None,
     r"\bC[ \t]?(\d+(?:[.,]\d+)?)(?![\d.,])(?![ \t]*[A-Za-z])",
     lambda m: ("C" + m.group(1), None)),
    ("ANGLE", None,
     r"(\d+(?:[.,]\d+)?)\s*(?:\u00b0|DEG(?:REES?)?\b)"
     r"(?:\s*\u00b1\s*([\d.,]+)\s*(?:\u00b0|DEG(?:REES?)?\b)?)?",
     lambda m: (m.group(1) + "\u00b0",
                ("\u00b1" + m.group(2)) if m.group(2) else None)),
    # keep brackets, [50] basic (75) ref
    ("LINEAR", "BASIC", r"\[\s*(\d+(?:[.,]\d+)?)\s*\]",
     lambda m: ("[" + m.group(1) + "]", "BASIC")),
    ("LINEAR", "REF", r"\(\s*(\d+(?:[.,]\d+)?)\s*\)",
     lambda m: ("(" + m.group(1) + ")", "REF")),
    ("LINEAR", None,
     r"(\d+(?:[.,]\d+)?)" + _SIZE_MOD + r"\s*\u00b1\s*(\d*[.,]?\d+)"
     + _SIZE_MOD,
     lambda m: (m.group(1) + _size_mod(m), "\u00b1" + m.group(2))),
    ("LINEAR", None,
     r"(\d+(?:[.,]\d+)?)" + _SIZE_MOD + r"\s*"
     r"((?:(?<![\d.,])0(?:[.,]\d+)?(?=\s*/)|[+\-]\s*\d*[.,]?\d+)\s*/\s*"
     r"(?:0(?:[.,]\d+)?(?![\d.,])|[+\-]\s*\d*[.,]?\d+))" + _SIZE_MOD,
     lambda m: (m.group(1) + _size_mod(m), m.group(2).replace(" ", ""))),
    ("LINEAR", None,
     r"(\d+(?:[.,]\d+)?)" + _SIZE_MOD
     + r"\s*([+\-]\d+[.,]\d+)(?![\d.,/%])" + _SIZE_MOD,
     lambda m: (m.group(1) + _size_mod(m), m.group(2))),
]


_DP_WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4}


# angular row states signed value
_ANG_TAIL =(r"(\u00b1[\s\d.,\u00b0\u2032\u2033'\"]+"
             r"|\d+(?:[.,]\d+)?\s*(?:\u00b0|[\u2032']))")
_ANG_VAL_RE = _re.compile(
    r"\bANGULAR\b[^0-9\u00b1]{0,16}" + _ANG_TAIL, _re.I)

# ASME bare row needs separator
_ANG_BARE_RE =_re.compile(
    r"\bANGULAR\b[^0-9\u00b1\n]{0,12}[:=]\s*"
    r"(\u00b1?\s*\d+(?:[.,]\d+)?[\s\d.,\u00b0\u2032\u2033'\"]*)", _re.I)

# ANGLE/ANGLES weak header needs plus-minus
_ANG_WEAK_RE =_re.compile(
    r"\bANGLES?\b[\s:=]{0,4}(±[\s\d.,°′″'\"]+)", _re.I)


def _ang_value(seg, bare_ok=False):
    """Stated angular tolerance in `seg` -> degrees, or None."""
    has_pm = "\u00b1" in seg
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
    """'1/64' or '.015' -> float, None when not tolerance."""
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
    t = _re.sub(r"(?<![\w.])\.(?=\d)", "0.", ascii_pm(text))

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
    ang_t = _ANG_WORDS_RE.sub(" ANGULAR ", t)
    v = None
    m = _ANG_VAL_RE.search(ang_t)
    if m:
        v = _ang_value(m.group(1))
    if v is None:
        m = _ANG_BARE_RE.search(ang_t)
        if m:
            v = _ang_value(m.group(1), bare_ok=True)
    if v is None:
        m = _ANG_WEAK_RE.search(ang_t)          # ANGLE / ANGLES
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
    """Heading word on line -> 'ang' / 'rad' / 'lin', else None."""
    if _KIND_ANG_RE.search(line):
        return "ang"
    if _KIND_RAD_RE.search(line):
        return "rad"
    return "lin" if _KIND_LIN_RE.search(line) else None


def _band_row_ok(line, spans):
    """True when line holds nothing but row and heading words."""
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
                kind = head            # heading sticks below
            continue
        if head:
            kind = head                # labelled on first row
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
        # recorded not applied
        out["bands_ang"] = sorted(rows["ang"])
    if rows["rad"]:
        # radii and chamfers only
        out["bands_rad"] = sorted(rows["rad"])
    return out


# [25] basic (75) ref, brackets survive into feature text
_BASIC_REF_FEAT =_re.compile(
    r"^\s*[\[(]\s*\d+(?:[.,]\d+)?\s*[\])]\s*$")


def is_basic_ref_feature(feature):
    """True when feature text is bracketed BASIC or REFERENCE dim."""
    return bool(_BASIC_REF_FEAT.match(str(feature or "")))


def basic_ref_kind(feature):
    """"BASIC" for [25], "REF" for (75), else ""."""
    t = str(feature or "").strip()
    if not is_basic_ref_feature(t):
        return ""
    return "BASIC" if t.startswith("[") else "REF"


def cfg_on(cfg, key):
    """Boolean config key, falling back to shipped default."""
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
    """".X +/-0.2 .XX +/-0.05" per block's printed decimal places."""
    places = sorted(k for k in g if isinstance(k, int) and 1 <= k <= 4)
    out = [u".%s \u00b1%g" % ("X" * d, g[d]) for d in places[:cap]]
    if len(places) > cap:
        out.append("..")
    return "  ".join(out)


def gentol_readout(gtols, cfg, session=None):
    """(source, value, inherited) LINEAR general tolerance now in force."""
    src, val, inh = _gentol_readout(gtols, cfg, session)
    if gentol_override(session) is not None and src in _GENTOL_PRINTED:
        return (GENTOL_SRC_USER, val, inh)
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
        if cfg.get("dp_on"):
            # decimal ladder is inch-only; a millimetre drawing uses ISO 2768
            tols = cfg.get("dp_tols_inch") or {}
            ladder = {int(k): v for k, v in tols.items() if str(k).isdigit()}
            txt = _places_text(ladder)
            if txt:
                return (GENTOL_SRC_LADDER_DP, txt, False)
    elif cfg.get("rib_iso_on"):
        cls = str(cfg.get("default_iso_class", "m"))
        return (GENTOL_SRC_LADDER_ISO, "-%s  by nominal" % cls, False)
    return (GENTOL_SRC_NONE, "", False)


# which of three gentol tables
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

# band table per kind
GENTOL_BAND_KEY ={"lin": "bands", "rad": "bands_rad", "ang": "bands_ang"}


def band_tol(bands, nominal):
    """Band-table tolerance for nominal, or None."""
    if not bands or nominal is None:
        return None
    best = None
    for lo, hi, tol in bands:
        if lo <= nominal <= hi and (best is None or hi - lo < best[0]):
            best = (hi - lo, tol)
    return best[1] if best else None


def band_tol_shortest(bands):
    """Tolerance of band table's FIRST row, shortest-side band."""
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


# --------------------------------------------------------------------------
# THE general-tolerance answer, every path asks it
# --------------------------------------------------------------------------

# answer sources as English tr() keys
GENTOL_SRC_BAND ="band table on the drawing"
GENTOL_SRC_BLOCK = "decimal-place block"
GENTOL_SRC_FRAC = "printed fractional row"
GENTOL_SRC_LADDER_DP = "settings decimal ladder"
GENTOL_SRC_LADDER_ISO = "settings ISO 2768"
GENTOL_SRC_STD = "cited ISO 2768"
GENTOL_SRC_NONE = "none"
# GENTOL_SRC_USER hand correction beats printed block
GENTOL_SRC_USER = "corrected by hand"

# printed rungs hand correction replaces
_GENTOL_PRINTED =(GENTOL_SRC_BAND, GENTOL_SRC_BLOCK, GENTOL_SRC_FRAC)


def gentol_override(session):
    """General-tolerance block someone CORRECTED, or None."""
    g = (session or {}).get("gentol_user")
    return dict(g) if isinstance(g, dict) and g else None

# value mm or degrees. kind lin/rad/ang/None
GenTol = namedtuple("GenTol", "value source kind inherited")

NO_GENTOL = GenTol(None, GENTOL_SRC_NONE, None, False)


def gentol_callout(h=None, row=None, **over):
    """One callout as resolver sees it, from scan hit and/or row."""
    h = h or {}
    row = row or {}
    c = {"tp": h.get("tp"), "sb": h.get("sb"),
         "type": row.get("type"), "v": h.get("v"),
         "feature": row.get("feature"), "nominal": row.get("nominal"),
         "no_gentol": bool(row.get("no_gentol")),
         # hand-marked radius as edge break
         "edge_break": bool(row.get("edge_break") or h.get("edge_break")),
         # MIN/MAX row states own bound
         "limit": (row.get("limit") or h.get("limit") or None)}
    if c["v"] is None:
        c["v"] = row.get("feature")
    c.update(over)
    return c


# types carrying own tolerance
_GENTOL_NEVER_TP = ("GDT", "SURFACE", "THREAD")


def gentol_exempt(callout, cfg=None):
    """Why callout takes NO general tolerance, or None."""
    c = callout or {}
    if c.get("no_gentol"):
        return "flagged"
    if c.get("limit") in ("max", "min"):    # MIN/MAX states own bound
        return "own tolerance"
    if str(c.get("tp") or "") in _GENTOL_NEVER_TP:
        return "own tolerance"
    t = str(c.get("type") or "")
    if (t.startswith("thread") or t == "GD&T" or t.startswith("finish")
            or t.startswith("position")):
        return "own tolerance"
    # brackets in three vocabularies
    if (str(c.get("sb") or "") in ("BASIC", "REF")
            or is_basic_ref_feature(c.get("feature"))
            or is_basic_ref_feature(c.get("v"))):
        return None if cfg_on(cfg, "gentol_basic_ref") else "basic or ref"
    return None


def _gentol_iso(nom, kind, cls, side_mm):
    """ISO 2768-1 value for kind, mm or degrees."""
    if kind == "ang":
        return None if side_mm is None else iso2768_angle_tol(side_mm, cls)
    if kind == "rad":
        return iso2768_radius_tol(nom, cls)
    return iso2768_tol(nom, cls)


def _gentol_standard(g, cfg, session, kind, nom, raw, cls, iso_on, side_mm):
    """Config ladder, then standard drawing cites. Last two rungs."""
    lad = gentol_ladder(cfg, session)
    if lad == "decimal":
        # decimal ladder mm/inch never angles
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
    # drawing citing 2768 beats settings default
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
        return NO_GENTOL._replace(kind=kind)   # states both limits
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
    # one kind's table only
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


# --------------------------------------------------------------------------
# correcting block already on sheet
# --------------------------------------------------------------------------

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
    """Spelled-out ISO 2768 linear class -> letter, or None."""
    up = (text or "").upper()
    for letter, words in _ISO_CLASS_WORDS:
        for w in words:
            if w in up:
                return letter
    return None


def iso_class_from_gtols(gtols):
    """Linear ISO 2768 class DRAWING declares, or None."""
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
    """ISO general-tolerance class off drawing rather than setting."""
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


def dp_of_value(v):
    """Decimal places of last number in value string."""
    nums = _re.findall(r"\d+(?:[.,]\d+)?", str(v or ""))
    if not nums:
        return None
    s = nums[-1].replace(",", ".")
    return len(s.split(".", 1)[1]) if "." in s else 0


# hole note makes hole without Ø glyph
_HOLE_NOUN_RE =_re.compile(
    r"\b(?:HOLES?|BOHRUNG(?:EN)?|OTW\.?|OTW\u00d3R|OTWOR(?:Y|\u00d3W)?)\b",
    _re.I)


def hole_note(text):
    """Hole wording in line -> 'thru' / 'hole', else None."""
    t = text or ""
    if _re.search(r"\bTHRU\b", t, _re.I):
        return "thru"
    return "hole" if _HOLE_NOUN_RE.search(t) else None


def scan_parse(text, cfg=None):
    out = []
    seen = set()
    spans = []
    at = []
    for tp, sb, pat, ex in SCAN_PATS:
        if not mode_admits_tp(tp, cfg):
            continue
        for m in _re.finditer(pat, text, _re.I | _re.M):
            v, t = ex(m)
            if not v:
                continue
            g = m.group(0)
            s = m.start() + (len(g) - len(g.lstrip()))
            e = m.end() - (len(g) - len(g.rstrip()))
            if any(not (e <= ps or s >= pe) for ps, pe in spans):
                continue
            keyv = _re.sub(r"^\d+[Xx\u00d7]\s*", "", v)
            key = ("%s:%s:%s" % (tp, keyv, t or "")).lower().replace(" ", "")
            # claim span first
            spans.append((s, e))
            if key in seen:
                continue
            seen.add(key)
            at.append((s, e))
            out.append(gdt_zone_check(
                {"tp": tp, "sb": sb, "v": v, "t": t,
                 "raw": m.group(0).strip()}))
    # hole words flag callout on same line
    for h, (s, e) in zip(out, at):
        if h["sb"] is not None or h["tp"] not in ("DIAMETER", "LINEAR"):
            continue
        ls = text.rfind("\n", 0, s) + 1
        le = text.find("\n", e)
        le = len(text) if le < 0 else le
        note = hole_note(text[ls:le])
        if not note:
            continue
        if h["tp"] == "DIAMETER":
            if note == "thru":
                h["thru"] = True
        else:
            h["hole_note"] = note
    return out


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


# ---------------------------------------------------------------- scan scope
# what starts ticked in scan review
# each hit in exactly one bucket
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
    """SCAN_BUCKETS entry for one hit."""
    h = h or {}
    tp = str(h.get("tp") or "").upper()
    sb = str(h.get("sb") or "").upper()
    t = str((row or {}).get("type") or "")
    if tp in _SCAN_GDT_TP or t in ("GD&T", "position"):
        return "gdt"
    if tp == "SURFACE" or t == "finish":
        return "finish"
    if sb in ("BASIC", "REF") or is_basic_ref_feature(h.get("v")):
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


# shipped bucket-name presets
SCAN_PRESETS = {
    # FAI ticks all but bare
    "First article": ("gdt", "finish", "basic_ref", "thread", "own_tol",
                      "gentol"),
    # in-process buckets
    "In-process": ("gdt", "finish", "own_tol"),
}
SCAN_PRESET_DEFAULT = "First article"


def scan_presets(cfg=None):
    """Shipped presets plus user's own, by name."""
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
    """Does hit start TICKED in scan review?"""
    name = scan_preset_name(cfg, session, header)
    return scan_bucket(h, row) in scan_presets(cfg).get(name, ())


def scan_to_row(d):
    """Classified scan hit -> ledger row dict (no position yet)."""
    sym, tmax, tmin = parse_tol_string(d.get("t"))
    tp = d["tp"]
    row = {"type": "dim", "feature": d["v"],
           "nominal": None, "tol_sym": sym, "tol_max": tmax,
           "tol_min": tmin, "pin": None, "offset": None,
           "measured": None, "tier": "", "limit": None}

    def num(s):
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
        # lone Ra is MAX (W10)
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
        m = _re.match(r"\s*(?:\d+\s*[Xx\u00d7]\s*)?\u00d8?\s*(\d+(?:[.,]\d+)?)",
                      d["v"])
        nominal = num(m.group(1)) if m else None
        code = (d.get("t") or "").replace(" ", "")
        is_hole = bool(code) and code[0].isupper()
        row.update(nominal=nominal,
                   feature=d["v"] + " (fit " + (d.get("t") or "") + ")")
        if is_hole:
            row.update(type="hole")
        if code and "/" not in code and nominal is not None:
            from .iso286 import fit_limits
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
        row.update(nominal=num(d["v"]))
    else:
        row.update(nominal=num(d["v"]))
        note = d.get("hole_note")
        if note == "thru":
            row.update(type="thru", feature=row["feature"] + " THRU")
        elif note:
            row.update(type="hole")
    return row


_REPEAT_RE = _re.compile(r"^\s*(\d+)\s*[Xx×](?=\s|Ø|$)")


def repeat_count(feature):
    """Leading N× repeat count."""
    m = _REPEAT_RE.match(str(feature or ""))
    return max(1, min(999, int(m.group(1)))) if m else 1


def strip_repeat(feature):
    """Drop leading N× repeat prefix."""
    s = str(feature or "")
    m = _REPEAT_RE.match(s)
    return s[m.end():].lstrip() if m else s


def expand_hole_row(row, cfg=None, repeat=True):
    """N× count becomes row `qty` not N bubbles."""
    if repeat:
        n = repeat_count(row.get("feature"))
        if n > 1:
            row["qty"] = n
        row["feature"] = strip_repeat(row.get("feature"))
    return [row]


def scan_to_rows(d, cfg=None, repeat=True):
    """Classified scan hit -> one or more ledger rows."""
    return expand_hole_row(scan_to_row(d), cfg, repeat=repeat)


DENORM = {
    "THRU": ("THROUGH", "PRZELOT", "PRZELOTOWY",
             "DURCH", "DURCHGANG", "DURCHGEHEND"),
    "DEEP": ("G\u0141.", "G\u0141\u0118B.", "TIEF", "TIEFE", "DP"),
    "CBORE": ("C'BORE", "SPOTFACE", "FLACHSENKUNG",
              "POG\u0141\u0118BIENIE WALCOWE", "\u2334"),
    "CSINK": ("CSK", "C'SINK", "ANSENKUNG", "SENKUNG",
              "POG\u0141\u0118BIENIE STO\u017bKOWE", "\u2335"),
}

# callout vocabulary (EN/DE/PL), exported for redactor
CALLOUT_TERMS =frozenset({
    # through / thru
    "THRU", "THROUGH", "DURCH", "DURCHGANG", "DURCHGANGSLOCH",
    "DURCHGANGSBOHRUNG", "DURCHGEHEND", "DURCHGEBOHRT", "DURCHBOHREN",
    "DURCHBOHRUNG", "DURCHBOHRT", "PRZELOT", "PRZELOTOWY", "PRZELOTOWE",
    "PRZEJ\u015aCIOWA", "PRZEJ\u015aCIOWE", "PRZEJ\u015aCIOWY", "ALLES", "ALL",
    # deep / depth
    "DEEP", "DEPTH", "TIEF", "TIEFE", "DP", "G\u0141", "G\u0141\u0118B",
    "G\u0141\u0118BOKO\u015a\u0106",
    # diameter
    "DIA", "DIAM", "DIAMETER", "DURCHMESSER", "DMR", "\u015aREDNICA", "\u015aR",
    # radius / chamfer
    "RADIUS", "RAD", "PROMIE\u0143", "CHAMFER", "CHAM", "FASE", "FAZA",
    "FAZOWANIE",
    # counterbore / countersink
    "CBORE", "COUNTERBORE", "SPOTFACE", "FLACHSENKUNG", "POG\u0141\u0118BIENIE",
    "WALCOWE", "SF", "CSINK", "COUNTERSINK", "CSK", "ANSENKUNG", "SENKUNG",
    "STO\u017bKOWE",
    # counts / occurrences
    "PLACES", "PLCS", "PLC", "OTWORY", "OTWOR\u00d3W", "OTW", "STK",
    "ST\u00dcCK", "MAL",
    # features / verbs
    "THREAD", "THREADED", "TAP", "TAPPED", "DRILL", "DRILLED", "BORE",
    "BORED", "REAM", "REAMED", "HOLE", "HOLES", "SLOT", "SLOTS", "TYP",
    "TYPICAL", "REF", "GEWINDE", "BOHRUNG", "BOHREN", "REIBEN",
})


def denorm_candidates(s, limit=12):
    """Search-needle variants of normalized string."""
    out = [s]
    up = s.upper()
    for canon, alts in DENORM.items():
        if canon in up:
            for a in alts:
                v = _re.sub(_re.escape(canon), a, s, flags=_re.I)
                if v not in out:
                    out.append(v)
    glyphed = []
    for v in out:
        if "\u00d8" in v:
            for g in ("\u00f8", "\u2300"):
                w = v.replace("\u00d8", g)
                if w not in out:
                    glyphed.append(w)
    out.extend(glyphed)
    return out[:limit]


GAGES = ["CMM", "micrometer", tr('pin'), "GO gauge",
         "height gauge", "caliper"]
GAGE_FALLBACK = {
    "CMM": ["height gauge", "micrometer", "caliper"],
    "micrometer": ["caliper"],
    tr('pin'): ["caliper"],
    "GO gauge": [tr('screw test')],
    "height gauge": ["caliper"],
}


def _allowed(gage, enabled):
    if enabled is None:
        return True
    return bool(enabled.get(gage, True))


def tool_feature(d):
    """Callout -> the metrology feature family a tool must handle."""
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
    """Pick a catalog tool by feature, range, then capability.

    Range decides eligibility (a 255 mm feature rules out a small CMM or a
    caliper you lack); among tools that fit, prefer the LEAST capable whose
    resolution is `ratio` x finer than the band; if none is that fine, take
    the most capable that fits (never refuse). No feature match -> most
    capable tool that covers the range.
    """
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
            return max(capable, key=_res)     # least capable that still fits
    return min(elig, key=_res)                 # most capable eligible


def suggest_gage(d, cfg=None, session=None):
    """Auto-pick a gage from the tool catalog for one row."""
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
