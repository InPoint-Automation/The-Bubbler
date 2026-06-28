# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Callout regex, glyph healing, classify to ledger rows.

import re as _re

FITS = ("H", "G", "F", "E", "D", "C", "JS", "J", "K", "M",
        "N", "P", "R", "S", "T", "U")

# GD&T control-frame symbols -> SCAN_PATS keyword.
_GDT_SYMBOLS = (
    ("⌖", " TRUE POSITION "),
    ("⊕", " TRUE POSITION "),         # circled-plus
    ("⨁", " TRUE POSITION "),         # n-ary circled-plus
    ("⌭", " CYLINDRICITY "),
    ("▱", " FLATNESS "),
    ("◎", " CONCENTRICITY "),
    ("◯", " CIRCULARITY "),
    ("⌒", " PROFILE OF A LINE "),
    ("⌓", " PROFILE OF A SURFACE "),
    ("⌰", " RUNOUT "),
    ("↗", " CIRCULAR RUNOUT "),
    ("⟂", " PERPENDICULARITY "),
    ("⊥", " PERPENDICULARITY "),      # up tack
    ("∥", " PARALLELISM "),
    ("∠", " ANGULARITY "),
)


def scan_normalize(t):
    """Heal PDF text-layer artifacts before classification."""
    t = (t.replace("\u00f8", "\u00d8")
         .replace("\u2300", "\u00d8").replace("\u2205", "\u00d8")
         .replace("\uf044", "\u00d8").replace("\uf064", "\u00d8")
         .replace("\uf052", "\u00b1").replace("\uf072", "\u00b1")
         .replace("\uf030", "\u00b0")
         # typographic minus -> ASCII hyphen
         .replace("\u2212", "-").replace("\u2013", "-")
         .replace("\u2011", "-"))
    # US inch leading-zero heal (.531 -> 0.531).
    t = _re.sub(r"(?<![\w.])\.(?=\d)", "0.", t)
    # Æ/æ broken Ø glyph, digit-guarded.
    t = _re.sub("[\u00c6\u00e6](?=\\s*\\d)", "\u00d8", t)
    # lookalike letter glued to dim number.
    t = _re.sub(r"(?<![A-Za-z0-9.,])[OoQ\u03a6\u03c6\u0398\u03b8](?=\d)",
                "\u00d8", t)
    t = _re.sub(r"(?<![\dA-Za-z.,/+\-])0(?=\d{1,3}(?:[.,]\d+)?(?![\d.,\-]))",
                "\u00d8", t)
    # fused signed pair -> separated by "/".
    t = _re.sub(r"([+\-]\d+[.,]\d+)(?=[+\-]\d+[.,]\d+)", r"\1/", t)
    t = _re.sub(r"\bDIAM?\b\.?(?=\s*[\d.])", "\u00d8", t, flags=_re.I)
    t = _re.sub("([0-9.])\u00b1", "\\1 \u00b1", t)
    t = _re.sub("\u00b1([0-9.])", "\u00b1 \\1", t)
    t = _re.sub(r"(\d)\s+\.\s*(\d)", r"\1.\2", t)
    t = _re.sub(r"(\d)\s*\.\s+(\d)", r"\1.\2", t)
    # multilingual keywords -> canonical EN tokens.
    t = _re.sub(r"\bTHROUGH\b", "THRU", t, flags=_re.I)
    # PL through-hole words -> THRU
    t = _re.sub("\\bPRZELOT(?:OWY|OWE)?\\b|\\bPRZEJŚCIOW[YEA]\\b",
                "THRU", t, flags=_re.I)
    # DE through words + compounds -> THRU
    t = _re.sub(r"\bDURCHGANGS(?:LOCH|BOHRUNG)?\b|"
                r"\bDURCHGE(?:HEND|BOHRT)\b|"
                r"\bDURCHBOHR(?:EN|UNG|T)?\b|"
                r"\bDURCHGANG\b|\bDURCH\b", "THRU", t, flags=_re.I)
    # depth words (EN/PL/DE) -> DEEP
    t = _re.sub("\\bG\u0141\u0118B\\.?\\b|\\bG\u0141\\.?\\b", "DEEP",
                t, flags=_re.I)
    t = _re.sub(r"\bTIEFE?\b", "DEEP", t, flags=_re.I)
    t = _re.sub(r"\bDP\.?(?=\s*[\d.])", "DEEP ", t, flags=_re.I)
    # diameter words (DE/PL) -> Ø
    t = _re.sub(r"\bDURCHMESSER\b|\bDMR\.?\b(?=\s*[\d.])", "\u00d8", t,
                flags=_re.I)
    t = _re.sub("\\b\u015aREDNICA\\b|\\b\u015aR\\.?\\b(?=\\s*[\\d.])",
                "\u00d8", t, flags=_re.I)
    # radius words -> R
    t = _re.sub("\\b(?:RADIUS|PROMIE\u0143)\\b\\s*(?=[\\d.])", "R", t,
                flags=_re.I)
    # chamfer words -> C prefix
    t = _re.sub(r"\b(?:FASE|FAZA|FAZOWANIE)\b\s*(?=[\d.])", "C", t,
                flags=_re.I)
    # EN suffix chamfer -> C-prefix
    t = _re.sub(r"(\d+(?:[.,]\d+)?)\s*(?:\"|mm)?\s*"
                r"(?:CHAMFER|CHAM\b\.?)", r"C\1", t, flags=_re.I)
    # counterbore / countersink words -> CBORE / CSINK.
    t = _re.sub("\\bPOG\u0141\u0118BIENIE\\s+WALCOWE\\b|"
                "\\bFLACHSENKUNG\\b|\\bSPOTFACE\\b|"
                "\\bSF\\.?\\b(?=\\s*[\u00d8\\d.])",
                " CBORE ", t, flags=_re.I)
    t = _re.sub("\\bPOG\u0141\u0118BIENIE\\s+STO\u017bKOWE\\b|"
                "\\bANSENKUNG\\b|\\bSENKUNG\\b",
                " CSINK ", t, flags=_re.I)
    # repeat-count words -> 4X
    t = _re.sub("(\\d+)\\s*(?:PLACES|PLCS|OTWOR(?:Y|\u00d3W)|OTW|"
                "STK|ST\u00dcCK|MAL)\\.?", "\\1X", t, flags=_re.I)
    # ISO hole-callout mark variants -> keyword.
    for _s in ("\u2334", "\u2294"):                       # counterbore cup
        t = t.replace(_s, " CBORE ")
    for _s in ("\u2335", "\u2228", "\u22c1"):             # countersink V
        t = t.replace(_s, " CSINK ")
    for _s in ("\u21a7", "\u2913", "\u25bd", "\u25bf",
               "\u25bc", "\u2207"):                        # depth mark
        t = t.replace(_s, " DEEP ")
    # parallelism as two ASCII slashes, tolerance-guarded.
    t = _re.sub(r"//(?=\s*[\d.,])", " PARALLELISM ", t)
    # GD&T Unicode symbols -> spelled keyword.
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
    # cross-line stacked tolerance -> one line
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
    # two-line stacked form -> one line
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


# Material-condition modifier trailing a GD&T tolerance zone.
_GDT_MOD = (r"(?:\s*(?:\(\s*(?P<modp>[MLS])\s*\)"
            r"|(?P<mod>MMC|LMC|RFS|[ⓂⓁⓈ])))?")
_MOD_TXT = {"Ⓜ": "M", "Ⓛ": "L", "Ⓢ": "S",
            "MMC": "M", "LMC": "L", "RFS": "S"}


def _gdt_modifier(m):
    """ ' M' / ' L' / ' S' suffix for a GD&T feature string, or ''. """
    raw = None
    for g in ("modp", "mod"):
        try:
            v = m.group(g)
        except (IndexError, _re.error):
            v = None
        if v:
            raw = v
            break
    return (" " + _MOD_TXT.get(raw.upper(), raw.upper())) if raw else ""


# order matters; earlier patterns claim spans first
SCAN_PATS = [
    ("THREAD", None,
     r"(?<![A-Za-z])M\s*\d+(?:[.,]\d+)?(?:\s*[xX\u00d7]\s*\d+(?:[.,]\d+)?)?"
     r"(?:\s*-\s*[4-8][gGhH])?",
     lambda m: (m.group(0).strip(), None)),
    ("THREAD", None,
     r"(?:\d+/\d+|#\d+)\s*-\s*\d+\s*(?:UNC|UNF|UNEF|NPT|NPTF|BSP)?",
     lambda m: (m.group(0).strip(), None)),
    ("GDT", "POSITION",
     r"(?:TRUE\s*POS(?:ITION)?|T\.P\.)\s*[\u00d8]?\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("POSITION \u00d8" + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "FLATNESS", r"FLATNESS\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("FLATNESS " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "STRAIGHTNESS", r"STRAIGHTNESS\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("STRAIGHTNESS " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "CIRCULARITY", r"(?:CIRCULARITY|ROUNDNESS)\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("CIRCULARITY " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "CYLINDRICITY", r"CYLINDRICITY\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("CYLINDRICITY " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "PARALLELISM", r"PARALLELISM\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("PARALLELISM " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "PERPENDICULARITY",
     r"PERP(?:ENDICUL(?:ARITY)?)?\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("PERPENDICULARITY " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "ANGULARITY", r"ANGULARITY\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("ANGULARITY " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "RUNOUT",
     r"(?:CIRCULAR\s*)?(?:RUNOUT|TIR|FIM)\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("RUNOUT " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "CONCENTRICITY",
     r"(?:CONCENTRICITY|COAXIALITY)\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("CONCENTRICITY " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("GDT", "PROFILE",
     r"PROFILE\s*(?:OF\s*A?\s*(?:LINE|SURFACE))?\s*([\d.,]+)" + _GDT_MOD,
     lambda m: ("PROFILE " + m.group(1) + _gdt_modifier(m), m.group(1))),
    ("SURFACE", None,
     r"(?:Rmax|Rsm|Ra|Rz|Rq|Rt|Rp|Rv)\s*(?:=\s*)?([\d.,]+)\s*"
     r"(?:[\u00b5u]m|micron)?",
     lambda m: (m.group(0).strip(), None)),
    # fits before DIAMETER -> one hit
    ("FIT", None,
     r"(\u00d8?)[ \t]*(\d+(?:[.,]\d+)?)[ \t]*"
     r"((?:[A-Z]{1,2}|[a-z]{1,2})[ ]?\d{1,2}(?:\s*/\s*"
     r"(?:[A-Z]{1,2}|[a-z]{1,2})[ ]?\d{1,2})?)(?![\w\u00b0])",
     lambda m: ((m.group(1) + m.group(2) + " " +
                 m.group(3).replace(" ", ""))
                if _fit_ok(m.group(3).replace(" ", ""))
                else None, m.group(3).replace(" ", ""))),
    ("DIAMETER", "CBORE",
     r"(?:C'?BORE|CBORE)\s*\u00d8?\s*(\d+(?:[.,]\d+)?)",
     lambda m: ("CBORE \u00d8" + m.group(1), None)),
    ("DIAMETER", "CSINK",
     r"(?:C'?SINK|CSK)\s*\u00d8?\s*(\d+(?:[.,]\d+)?)"
     r"(?:\s*[xX\u00d7]\s*(\d+(?:[.,]\d+)?)\s*\u00b0)?",
     lambda m: ("CSINK \u00d8" + m.group(1) +
                (" X" + m.group(2) + "\u00b0" if m.group(2) else ""), None)),
    ("DEPTH", None,
     r"\bDEEP\b\.?\s*\u00d8?\s*(\d+(?:[.,]\d+)?)",
     lambda m: ("DEEP " + m.group(1), None)),
    ("DIAMETER", None,
     r"(?:(\d+)\s*[Xx\u00d7]\s*)?\u00d8\s*(\d+(?:[.,]\d+)?)\s*"
     r"((?:(?<![\d.,])0(?=\s*/)|[+\-\u00b1]\s*\d*[.,]?\d+)"
     r"(?:\s*/\s*(?:0(?:[.,]\d+)?(?![\d.,])|[+\-]\s*\d*[.,]?\d+))?)?",
     lambda m: ((m.group(1) + "X " if m.group(1) else "") +
                "\u00d8" + m.group(2),
                m.group(3).replace(" ", "") if m.group(3) else None)),
    ("RADIUS", None,
     r"(?:^|[\s,(])R\s*(\d+(?:[.,]\d+)?)(?:\s*\u00b1\s*([\d.,]+))?",
     lambda m: ("R" + m.group(1),
                ("\u00b1" + m.group(2)) if m.group(2) else None)),
    # chamfers before ANGLE, not bare angle
    ("CHAMFER", None,
     r"(\d+(?:[.,]\d+)?)\s*[xX\u00d7]\s*45(?:[.,]0{1,2})?\s*\u00b0",
     lambda m: (m.group(0).replace(" ", ""), None)),
    ("CHAMFER", None,
     r"\bC[ \t]?(\d+(?:[.,]\d+)?)(?![\d.,])(?![ \t]*[A-Za-z])",
     lambda m: ("C" + m.group(1), None)),
    ("ANGLE", None,
     r"(\d+(?:[.,]\d+)?)\s*(?:\u00b0|DEG(?:REES?)?\b)"
     r"(?:\s*\u00b1\s*([\d.,]+)\s*(?:\u00b0|DEG(?:REES?)?\b)?)?",
     lambda m: (m.group(1) + "\u00b0",
                ("\u00b1" + m.group(2)) if m.group(2) else None)),
    ("LINEAR", "BASIC", r"\[\s*(\d+(?:[.,]\d+)?)\s*\]",
     lambda m: (m.group(1), "BASIC")),
    ("LINEAR", "REF", r"\(\s*(\d+(?:[.,]\d+)?)\s*\)",
     lambda m: (m.group(1), "REF")),
    ("LINEAR", None,
     r"(\d+(?:[.,]\d+)?)\s*\u00b1\s*(\d*[.,]?\d+)",
     lambda m: (m.group(1), "\u00b1" + m.group(2))),
    ("LINEAR", None,
     r"(\d+(?:[.,]\d+)?)\s*"
     r"((?:(?<![\d.,])0(?:[.,]\d+)?(?=\s*/)|[+\-]\s*\d*[.,]?\d+)\s*/\s*"
     r"(?:0(?:[.,]\d+)?(?![\d.,])|[+\-]\s*\d*[.,]?\d+))",
     lambda m: (m.group(1), m.group(2).replace(" ", ""))),
    ("LINEAR", None,
     r"(\d+(?:[.,]\d+)?)\s*([+\-]\d+[.,]\d+)(?![\d.,/%])",
     lambda m: (m.group(1), m.group(2))),
]


_DP_WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4}


def parse_general_tols(text):
    """Title-block general tolerances -> {decimal_places: ±tol} plus "ang"."""
    out = {}
    t = _re.sub(r"(?<![\w.])\.(?=\d)", "0.", text or "")

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
    m = _re.search(r"\bANGULAR\b[^0-9\u00b1]{0,16}\u00b1?\s*"
                   r"([\d.,]+)", t, _re.I)
    if m:
        v = num(m.group(1))
        if v:
            out["ang"] = v
    return out


def dp_of_value(v):
    """Decimal places of last number in value string."""
    nums = _re.findall(r"\d+(?:[.,]\d+)?", str(v or ""))
    if not nums:
        return None
    s = nums[-1].replace(",", ".")
    return len(s.split(".", 1)[1]) if "." in s else 0


def scan_parse(text):
    out = []
    seen = set()
    spans = []
    for tp, sb, pat, ex in SCAN_PATS:
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
            if key in seen:
                continue
            seen.add(key)
            spans.append((s, e))
            out.append({"tp": tp, "sb": sb, "v": v, "t": t,
                        "raw": m.group(0).strip()})
    if _re.search(r"\bTHRU\b", text, _re.I):
        for h in out:
            if h["tp"] == "DIAMETER" and h["sb"] is None:
                h["thru"] = True
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
        # single deviation = unilateral against zero
        return ((None, v, 0.0) if m.group(1) == "+"
                else (None, 0.0, -v))
    return (None, None, None)


def scan_to_row(d):
    """Classified scan hit -> ledger row dict (no position yet)."""
    sym, tmax, tmin = parse_tol_string(d.get("t"))
    tp = d["tp"]
    row = {"type": "dim", "group": "LWH", "feature": d["v"],
           "nominal": None, "tol_sym": sym, "tol_max": tmax,
           "tol_min": tmin, "pin": None, "offset": None,
           "measured": None, "tier": ""}

    def num(s):
        try:
            return float(_re.sub(r"[^\d.,]", "", s).replace(",", "."))
        except ValueError:
            return None

    if tp == "DEPTH":
        m = _re.search(r"(\d+(?:[.,]\d+)?)", d["v"])
        row.update(type="depth / g\u0142\u0119boko\u015b\u0107",
                   group="holes \u00d8 / otwory",
                   nominal=num(m.group(1)) if m else None)
    elif tp == "THREAD":
        row.update(type="thread / gwint", group="threads / gwinty")
    elif tp == "GDT":
        zone = num(d.get("t") or "")
        row.update(type="GD&T", group="GD&T", nominal=0.0,
                   tol_sym=None, tol_max=zone, tol_min=0.0)
    elif tp == "SURFACE":
        row.update(type="finish / wyko\u0144czenie",
                   group="finish / wyko\u0144czenie")
    elif tp == "DIAMETER":
        m = _re.search(r"\u00d8\s*(\d+(?:[.,]\d+)?)", d["v"])
        row.update(type="hole / otw\u00f3r", group="holes \u00d8 / otwory",
                   nominal=num(m.group(1)) if m else num(d["v"]))
        if d.get("thru"):
            row.update(type="thru / przelot",
                       feature=row["feature"] + " THRU")
    elif tp == "FIT":
        m = _re.match(r"\s*\u00d8?\s*(\d+(?:[.,]\d+)?)", d["v"])
        nominal = num(m.group(1)) if m else None
        code = (d.get("t") or "").replace(" ", "")
        is_hole = bool(code) and code[0].isupper()
        row.update(nominal=nominal,
                   feature=d["v"] + " (fit " + (d.get("t") or "") + ")")
        if is_hole:
            row.update(type="hole / otw\u00f3r",
                       group="holes \u00d8 / otwory")
        if code and "/" not in code and nominal is not None:
            from .iso286 import fit_limits
            lim = fit_limits(nominal, code)
            if lim is not None:
                row.update(tol_max=lim[0], tol_min=lim[1])
    elif tp == "CHAMFER":
        # leg length
        m = _re.search(r"(\d+(?:[.,]\d+)?)", d["v"])
        row.update(group="other / inne",
                   nominal=num(m.group(1)) if m else None)
    elif tp == "RADIUS":
        row.update(nominal=num(d["v"]))
    elif tp == "ANGLE":
        row.update(group="GD&T", nominal=num(d["v"]))
    else:
        row.update(nominal=num(d["v"]))
    return row


def _position_row(axis, pin, tier):
    """Blank X/Y location row carrying gage pin Ø."""
    return {"type": "position / pozycja", "group": "positions / pozycje",
            "feature": axis, "nominal": None, "tol_sym": None,
            "tol_max": None, "tol_min": None, "pin": pin, "offset": None,
            "measured": None, "tier": tier}


# Leading "N×" repeat count, capped at 26.
_REPEAT_RE = _re.compile(r"^\s*(\d+)\s*[Xx×](?=\s|Ø|$)")


def repeat_count(feature):
    """Leading N× repeat count, clamped to 1..26."""
    m = _REPEAT_RE.match(str(feature or ""))
    return max(1, min(26, int(m.group(1)))) if m else 1


def strip_repeat(feature):
    """Drop the leading N× repeat prefix."""
    s = str(feature or "")
    m = _REPEAT_RE.match(s)
    return s[m.end():].lstrip() if m else s


def expand_hole_row(row, cfg=None, repeat=True):
    """Ledger row -> Ø + X/Y rows, honoring N× repeat."""
    cfg = cfg or {}

    def _expand_one(r):
        rows = [r]
        # locating drill only, not cbore/csink
        feat = str(r.get("feature") or "").upper().lstrip()
        is_hole = (str(r.get("type") or "").startswith(("hole", "thru"))
                   and not feat.startswith(("CBORE", "CSINK")))
        if is_hole and cfg.get("hole_position_rows", True):
            # caller pin wins, else hole nominal
            pin = r.get("pin")
            if pin is None and cfg.get("hole_pin_auto", True):
                pin = r.get("nominal")
            r["pin"] = None                     # never on the radius row
            tier = r.get("tier", "")
            rows.append(_position_row("X", pin, tier))
            rows.append(_position_row("Y", pin, tier))
        return rows

    n = repeat_count(row.get("feature")) if repeat else 1
    if n <= 1:
        if repeat:
            row["feature"] = strip_repeat(row.get("feature"))
        return _expand_one(row)
    clean = strip_repeat(row.get("feature"))
    out = []
    for _ in range(n):
        r = dict(row)
        r["feature"] = clean
        out.extend(_expand_one(r))
    return out


def scan_to_rows(d, cfg=None, repeat=True):
    """Classified scan hit -> one or more ledger rows."""
    return expand_hole_row(scan_to_row(d), cfg, repeat=repeat)


# source-text variants of normalized needle
DENORM = {
    "THRU": ("THROUGH", "PRZELOT", "PRZELOTOWY",
             "DURCH", "DURCHGANG", "DURCHGEHEND"),
    "DEEP": ("G\u0141.", "G\u0141\u0118B.", "TIEF", "TIEFE", "DP"),
    "CBORE": ("C'BORE", "SPOTFACE", "FLACHSENKUNG",
              "POG\u0141\u0118BIENIE WALCOWE", "\u2334"),
    "CSINK": ("CSK", "C'SINK", "ANSENKUNG", "SENKUNG",
              "POG\u0141\u0118BIENIE STO\u017bKOWE", "\u2335"),
}


def denorm_candidates(s, limit=12):
    """Search-needle variants of a normalized string."""
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


GAGES = ["CMM", "micrometer", "pin / bore gauge", "GO gauge",
         "height gauge", "caliper"]
# fallback chains when ideal gage off
GAGE_FALLBACK = {
    "CMM": ["height gauge", "micrometer", "caliper"],
    "micrometer": ["caliper"],
    "pin / bore gauge": ["caliper"],
    "GO gauge": ["screw test / wkr\u0119t"],
    "height gauge": ["caliper"],
}


def _allowed(gage, enabled):
    if enabled is None:
        return True
    return bool(enabled.get(gage, True))


def suggest_gage(d, enabled=None, cmm_tol=0.01, mic_tol=0.03):
    t = (d.get("type") or "")
    if t.startswith("thread"):
        ideal = "GO gauge"
    elif (d.get("group") or "").startswith("GD&T") or \
            t.startswith("position") or \
            (d.get("group") or "").startswith("positions"):
        ideal = "CMM"             # location / true position -> CMM
    else:
        tol = d.get("tol_sym")
        if tol is None and d.get("tol_max") is not None and \
                d.get("tol_min") is not None:
            tol = (max(d["tol_max"], d["tol_min"]) -
                   min(d["tol_max"], d["tol_min"])) / 2.0
        if tol is not None and tol <= cmm_tol:
            ideal = "CMM"
        elif tol is not None and tol <= mic_tol:
            ideal = "micrometer"
        elif t.startswith(("hole", "thru")):
            ideal = "pin / bore gauge"
        else:
            ideal = "caliper"
    if _allowed(ideal, enabled):
        return ideal
    for alt in GAGE_FALLBACK.get(ideal, []):
        if _allowed(alt, enabled):
            return alt
    return "caliper"
