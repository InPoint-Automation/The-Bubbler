# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Callout grammar: normalising and SCAN_PATS.

import re as _re


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
    t = _re.sub(r"\+\s*/\s*-(?=\s*[\d.,])", "\u00b1", t or "")
    return _re.sub(r"(?<![\d.,])\+-(?=\s*[\d.,])", "\u00b1", t)


# ASME size without leading zero
LEAD_DOT = (r"(?:(?<=[\u00d8\u2300])|(?<=(?<![A-QT-Za-z])R)|(?<![\w.]))"
            r"\.(?=\d)")

# note list number, not decimal
NOTE_WORDS = r"NOTES?|UWAG[AI]|HINWEIS(?:E)?|ANM(?:ERKUNG)?"
NOTE_NUM = _re.compile(r"\b(?:" + NOTE_WORDS + r")[ \t]+\d{0,2}$", _re.I)


# limit pair with prefix twice
_LIM_PREFIX = _re.compile("(\u00d8[ \t]*(\\d*[.,]?\\d+))[ \t]*-[ \t]*\u00d8"
                          "(?=[ \t]*(\\d*[.,]?\\d+)"
                          "(?![\\d.,]|[ \t]*[A-Za-z]{1,2}\\d{1,2}\\b))")


def limit_close(a, b):
    """Within 5%, or 0.3 on small sizes."""
    lo, hi = min(a, b), max(a, b)
    return lo > 0 and hi != lo and hi - lo <= max(0.05 * lo, 0.3)


# hole callout line
_HOLE_LINE = _re.compile(r"^(?:THRU|DEEP|CBORE|CSINK)\b", _re.I)
# line opening with tolerance
_PM_ONLY = _re.compile("^(?:\u00b1[ \t]*\\d*[.,]?\\d+"
                       "|[+\\-][ \t]*\\d*[.,]?\\d+[ \t]*\u00b0?[ \t]*/?[ \t]*"
                       "[+\\-][ \t]*\\d*[.,]?\\d+"
                       # zero partner
                       "|0(?:[.,]0+)?[ \t]+[+\\-][ \t]*\\d*[.,]?\\d+"
                       "|[+\\-][ \t]*\\d*[.,]?\\d+[ \t]+0(?:[.,]0+)?(?![\\d.,]))")
# deviation pair sides
_PAIR_GAP = _re.compile("^((?:[+\\-][ \t]*)?\\d*[.,]?\\d+)[ \t]+"
                        "(?=[+\\-]|0(?:[.,]0+)?(?![\\d.,]))")


def fold_limit_prefix(s):
    def one(m):
        try:
            a = float(m.group(2).replace(",", "."))
            b = float(m.group(3).replace(",", "."))
        except ValueError:
            return m.group(0)
        return m.group(1) + "-" if limit_close(a, b) else m.group(0)
    return _LIM_PREFIX.sub(one, s)


# inch mark after size
_INCH_MARK = _re.compile("(\\d)[ \t]*[\"\u2033]")
# real ISO 286 letters only
_FIT_NEXT = _re.compile(
    "^[ \t]*(?:CD|EF|FG|JS|ZA|ZB|ZC|cd|ef|fg|js|za|zb|zc"
    "|[A-HJKMNPR-VYZ]|[a-hjkmnpr-vyz])[ ]?\\d{1,2}(?![\\w.,\u00b0])")
# arc-seconds after minutes
_SECONDS = _re.compile("\\d[ \t]*['\u2032][^\\n]*?(?<![\\d.,])[0-5]?\\d$")


def inch_mark_drops(before, after):
    """Not for seconds, angles or fit codes."""
    line = before.rsplit("\n", 1)[-1]
    # angle's `±1.5"` is seconds
    on_angle = "\u00b0" in line and _re.search(
        "\u00b1[ \\t]*[\\d.,]+$", line)
    return not (_SECONDS.search(line) or on_angle or _FIT_NEXT.match(after))


def strip_inch_marks(t):
    def one(m):
        if inch_mark_drops(t[:m.start(1) + 1], t[m.end():]):
            return m.group(1)
        return m.group(0)
    return _INCH_MARK.sub(one, t)


def _post_rejoin(m):
    """`10. 5` -> `10.5`, not after note number."""
    if NOTE_NUM.search(m.string[max(0, m.start() - 16):m.start()]):
        return m.group(0)
    return m.group(1) + "." + m.group(2)

# what may follow split fraction
FRAC_TAIL = (r"(?![\d.,]|[Xx\u00d7](?![ \t]*\d+(?:[.,]\d+)?"
             r"[ \t]*\u00b0)(?![ \t]*(?:[\r\n]|\Z))"
             r"|[ \t]+[Xx\u00d7][ \t]*(?:\u00d8|SR|R|M)\d)")


# count glued to R or M
GLUED_COUNT = _re.compile(r"(?<![\w.,])(\d{1,3}[xX\u00d7])(?=(?:SR|R|M)\d)")


# signed deviation under 10
SIGNED_DEV = r"[+\-](?:\d?[.,]\d+|\d)(?![\d.,])"


def scan_normalize(t):
    t = (t.replace("\u00f8", "\u00d8")
         .replace("\u2300", "\u00d8").replace("\u2205", "\u00d8")
         .replace("\uf044", "\u00d8").replace("\uf064", "\u00d8")
         .replace("\uf052", "\u00b1").replace("\uf072", "\u00b1")
         .replace("\uf030", "\u00b0")
         .replace("\u2212", "-").replace("\u2013", "-")
         .replace("\u2011", "-"))
    t = ascii_pm(t)
    t = strip_inch_marks(t)
    t = GLUED_COUNT.sub(r"\1 ", t)
    # rejoin lone-dot split before phi heal
    t = _re.sub(r"(\d)[ \t]+([.,])[ \t]*(\d+)" + FRAC_TAIL,
                r"\1\2\3", t)
    # leading zero after rejoin
    t = _re.sub(LEAD_DOT, "0.", t)
    t = _re.sub("[\u00c6\u00e6](?=\\s*\\d)", "\u00d8", t)
    # phi look-alikes, digit after and no word before
    t = _re.sub(r"(?<![A-Za-z0-9.,])"
                r"[OoQ\u03a6\u03c6\u03d5\u0424\u0398\u03b8](?=\d)",
                "\u00d8", t)
    t = _re.sub(r"(?<![\dA-Za-z.,/+\-:])0(?=\d{1,3}(?:[.,]\d+)?(?![\d.,\-:]))",
                "\u00d8", t)
    t = fold_limit_prefix(t)
    # lone sign joins its number
    t = _re.sub(r"(?<![^\s])([+\-])[ \t]+(?=[\d.][\d.,]*(?![^\s]))",
                r"\1", t)
    t = _re.sub(r"([+\-]\d+[.,]\d+)(?=[+\-]\d+[.,]\d+)", r"\1/", t)
    # two signed devs after nominal pair
    t = _re.sub(r"(\d[ \t]+" + SIGNED_DEV + r")[ \t]+(?="
                + SIGNED_DEV + r")", r"\1/", t)
    # unsigned zero partner
    t = _re.sub(r"(\d[ \t]+)(0(?:[.,]0+)?)[ \t]+(?=" + SIGNED_DEV + r")",
                r"\1\2/", t)
    t = _re.sub(r"(\d[ \t]+" + SIGNED_DEV
                + r")[ \t]+(0(?:[.,]0+)?)(?![\d.,])", r"\1/\2", t)
    t = _re.sub(r"\bDIAM?\b\.?(?=\s*[\d.])", "\u00d8", t, flags=_re.I)
    t = _re.sub("([0-9.])\u00b1", "\\1 \u00b1", t)
    t = _re.sub("\u00b1([0-9.])", "\u00b1 \\1", t)
    # bare fraction only
    t = _re.sub(r"(\d)\s+\.\s*(\d+)" + FRAC_TAIL, r"\1.\2", t)
    # note number is not split
    t = _re.sub(r"(\d)\s*\.\s+(\d+)" + FRAC_TAIL, _post_rejoin, t)
    t = _re.sub(r"\bTHROUGH\b", "THRU", t, flags=_re.I)
    # `ĝ` is broken-font `Ś`
    t = _re.sub("\\bPRZELOT(?:OWY|OWE)?\\b|\\bPRZEJ[ŚĝS]CIOW[YEA]\\b",
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
    t = _re.sub(r"\b(?:FASE|FAZA|FAZOWANIE|CHAMFER)\b\.?\s*(?=[\d.])", "C", t,
                flags=_re.I)
    t = _re.sub(r"(\d+(?:[.,]\d+)?)\s*(?:\"|mm)?\s*"
                r"(?:CHAMFER|CHAM\b\.?)", r"C\1", t, flags=_re.I)
    t = _re.sub("\\bPOG\u0141\u0118BIENIE\\s+WALCOWE\\b|"
                "\\bFLACHSENKUNG\\b|\\bSPOTFACE\\b|\\bCOUNTERBORED?\\b|"
                "\\bSF\\.?\\b(?=\\s*[\u00d8\\d.])",
                " CBORE ", t, flags=_re.I)
    t = _re.sub("\\bPOG\u0141\u0118BIENIE\\s+STO\u017bKOWE\\b|"
                "\\bANSENKUNG\\b|\\bSENKUNG\\b|\\bCOUNTERSUNK\\b|"
                "\\bCOUNTERSINK\\b",
                " CSINK ", t, flags=_re.I)
    # count words become NX
    t = _re.sub("(\\d+)\\s*(?:PLACES|PLCS|OTWOR(?:Y|\u00d3W)|OTW|"
                "STK|ST\u00dcCK|MAL|HOLES|POSN|POS(?![A-Z])|PCS(?![A-Z]))"
                "\\.?", "\\1X", t, flags=_re.I)
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
        # trailing `/` too
        a2 = _re.sub(r"[ \t]*/$", "", a) if a else a
        if (a2 and _re.search(r"\d\s*[+\-][\d.,]*\d$", a2) and
                "/" not in a2.rsplit(None, 1)[-1] and
                _re.match(_DEV, b)):
            healed[i] = a2 + "/" + b.replace(" ", "")
            healed[i + 1] = ""
    for i in range(len(healed) - 1):
        a, b = healed[i].strip(), healed[i + 1].strip()
        # hole line takes `±t` below
        if a and _HOLE_LINE.match(a) and _PM_ONLY.match(b):
            # slash pair sides
            healed[i] = a + " " + _PAIR_GAP.sub(r"\1/", b, count=1)
            healed[i + 1] = ""
            continue
        # lone count opens frame below
        if _re.match(r"^\d+[Xx\u00d7]$", a) and any(
                b.upper().startswith(n.strip()) for _g, n in _GDT_SYMBOLS):
            healed[i] = a + " " + b
            healed[i + 1] = ""
            continue
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
# X stays on its line
_XSEP = _GDT_NOBREAK + r"*[xX\u00d7]" + _GDT_NOBREAK + r"*"

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
_SPH_RE =_re.compile(r"(?:^|[\s,(\-])S(?=[R\u00d8])")


def _spherical(m):
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
    """ "break edges 0,2-0,5" -> ("EDGE 0.2-0.5", "0.2/0.5")."""
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
    """ISO 14405 size modifier, ' LP' / ' E' or ''."""
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
    """'.5' -> '0.5', structural reader's spelling."""
    t = h.get("t") or ""
    if not t[:1] in (".", ","):
        return h
    h["t"] = "0" + t
    v = h.get("v") or ""
    h["v"] = v.replace(" " + t, " 0" + t, 1).replace("Ø" + t, "Ø0" + t, 1)
    return h


def gdt_zone_check(h):
    if h.get("tp") != "GDT":
        return h
    _gdt_lead_zero(h)
    if not gdt_zone_wrong(h.get("sb"), _gdt_zone_mark(h.get("raw") or "")):
        return h
    h["fcf_zone_suspect"] = True
    gdt_flag(h, "zone_suspect")
    return h


def _gdt_modifier(m):
    """' M P25', printed order."""
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
            num = "0" + num
        out.append(txt + num)
    return (" " + " ".join(out)) if out else ""


# datum letters standards exclude
DATUM_NEVER = frozenset("IOQ")


def impossible_datums(v):
    bad = []
    for seg in str(v or "").split("|")[1:]:
        seg = _re.sub(r"\(\s*[A-Z]\s*\)", "", seg)       # (M) modifiers
        for ch in _re.findall(r"[A-Z]", seg):
            if ch in DATUM_NEVER:
                bad.append(ch)
    return bad


def _gdt_datums(m, subtype=None):
    """' | A | B | C' datum suffix, or ''."""
    try:
        raw = m.group("datums")
    except (IndexError, _re.error):
        return ""
    cap = _GDT_MAX_DATUMS.get(subtype, 3)
    if cap == 0 or not raw or not raw.strip():
        return ""
    parts = [_re.sub(r"\s+", "", d).upper()
             for d in _re.findall(r"[A-Z](?:-[A-Z])*" + _DATUM_MOD,
                                  raw, _re.I)]
    parts = parts[:cap]
    return (" | " + " | ".join(parts)) if parts else ""


def _chamfer(m):
    """Chamfer 'leg X angle', angle 0-60."""
    try:
        a = float(m.group(2).replace(",", "."))
    except ValueError:
        return (None, None)
    if not (0 < a <= 60):
        return (None, None)
    leg = m.group(1).replace(",", ".")
    if "/" in leg:
        whole = _re.match(r"(\d+)(?:[ \t]*-[ \t]*|[ \t]+)(?=\d+/)", leg)
        frac = leg[whole.end():] if whole else leg
        num, den = frac.split("/")
        if not float(den):
            return (None, None)
        leg = "%.10g" % ((float(whole.group(1)) if whole else 0.0)
                         + float(num) / float(den))
    # angle tol is own row
    extra = _angle_row(m.group(2).strip(), m)
    raw = m.group(3)
    t = _cham_t(raw, leg)
    # unmarked `±N` past leg is degrees
    if (raw and t is None and not extra
            and _re.match("^±[ \t]*[\\d.,]*\\d$", raw.strip())):
        d = raw.strip()[1:].strip().replace(",", ".")
        extra = ({"tp": "ANGLE", "sb": None,
                  "v": m.group(2).strip() + "°",
                  "t": "±%.10g" % float(d)},)
    return (leg + "X" + ("%g" % a) + "°", t, extra)


def _angle_row(angle, m):
    gd = m.groupdict()
    ang = str(angle).strip()
    if gd.get("ctail"):
        d = dms_degrees(gd["ctail"])
        if not d:
            return ()
        t = "\u00b1%.10g" % d
    elif gd.get("cp1") and gd.get("cp2"):
        a, b = gd["cp1"].replace(" ", ""), gd["cp2"].replace(" ", "")
        t = "%s%.10g/%s%.10g" % (a[0], dms_degrees(a[1:]) or 0,
                                 b[0], dms_degrees(b[1:]) or 0)
    else:
        return ()
    return ({"tp": "ANGLE", "sb": None, "v": ang + "\u00b0", "t": t},)


def _csink(m, dia, ang, dtol):
    """Tol after angle belongs to angle."""
    v = "CSINK \u00d8" + dia + (" X" + ang + "\u00b0" if ang else "")
    extra = _angle_row(ang, m) if ang else ()
    return (v, dtol, extra)


# chamfer leg tolerance
_CHAM_TOL = (r"(?:[ \t]*(\u00b1[ \t]*[\d.,]*\d"
             r"|[+\-][ \t]*[\d.,]*\d[ \t]*/?[ \t]*[+\-][ \t]*[\d.,]*\d"
             r"|\+[ \t]*[\d.,]*\d[ \t]*/?[ \t]*0(?:[.,]0+)?"
             r"|0(?:[.,]0+)?[ \t]*/[ \t]*-[ \t]*[\d.,]*\d)"
             r"(?![\d.,])(?![ \t]*(?:\u00b0|['\u2032\"\u2033]|DEG)))?")


# inch fraction size
_FRAC_START = r"(?:(?<![^\n])|(?<=[Xx\u00d7][ \t]))"
_FRAC_GUARD = r"(?<![\d/])"
FRAC_SIZE = (r"(?:" + _FRAC_START + r"\d+(?:[ \t]*-[ \t]*|[ \t]+)\d+/\d+"
             r"|" + _FRAC_GUARD + r"\d+-\d+/\d+"
             r"|" + _FRAC_GUARD + r"\d+/\d+)")


def _frac(v):
    """`1/2` -> `0.5`, `1-1/2` -> `1.5`, else as is."""
    if "/" not in v:
        return v
    whole = _re.match(r"(\d+)(?:[ \t]*-[ \t]*|[ \t]+)(?=\d+/)", v)
    num, den = v[whole.end():].split("/") if whole else v.split("/")
    if not float(den):
        return v
    return "%.10g" % ((float(whole.group(1)) if whole else 0.0)
                      + float(num) / float(den))


def _cham_t(t, leg=None, strict=False):
    """None when tol reaches leg itself."""
    if not t:
        return None
    t = t.replace(" ", "")
    try:
        big = max(float(x.replace(",", "."))
                  for x in _re.findall(r"\d*[.,]?\d+", t))
        lim = float(str(leg).replace(",", ".")) if leg is not None else None
        if lim is not None and (big > lim if strict else big >= lim):
            return None
    except ValueError:
        pass
    return t


_ZONE_SCAN = _re.compile(r"UZ\s*[+-]\s*\d+(?:[.,]\d+)?"
                         r"|CZ|SZ|OZ|CT|ACS|ACL|VA", _re.I)


def _iso_zone(m):
    """' CZ' / ' UZ+0,1 CZ' zone qualifiers."""
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
    """'/100' or '/25X25' per-unit basis, or ''."""
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


# signed angle dev, max 5°
_ANG_DEV = r"(?:[0-4](?:[.,]\d+)?|5(?:[.,]0+)?|[.,]\d+)(?![\d.,])"

# angles in DMS
_DEG = r"(?:\u00b0|DEG(?:REES?)?\b)"
_DMS_MIN = r"(?:[ \t]*[0-5]?\d(?:[.,]\d+)?[ \t]*['\u2032])"
# whole seconds after minutes
_DMS_SEC = r"(?:[ \t]*[0-5]?\d[ \t]*[\"\u2033])"
_DMS_MS = "(?:" + _DMS_MIN + _DMS_SEC + "?)"
_NOT_MARKED = "(?![ \\t]*[\"\u2033'\u2032])"
# minutes/seconds tried first
_TOL_DMS = (r"(?:[0-5]?\d(?:[.,]\d+)?[ \t]*['\u2032]" + _DMS_SEC + "?"
            r"|[0-5]?\d[ \t]*[\"\u2033]"
            r"|\d*[.,]?\d+[ \t]*" + _DEG + _DMS_MS + "?"
            r"|\d*[.,]?\d+(?![\d.,])" + _NOT_MARKED + ")")
# signed pair side, cap unmarked
_MARKED_DEV = r"\d{1,2}(?:[.,]\d+)?(?![\d.,])"
_SIGNED_DMS = (r"(?:[0-5]?\d(?:[.,]\d+)?[ \t]*['\u2032]"
               r"|" + _MARKED_DEV + r"[ \t]*\u00b0" + _DMS_MIN + "?"
               r"|" + _ANG_DEV + _NOT_MARKED + ")")
_SIGNED_DMS_MARKED = (r"(?:[0-5]?\d(?:[.,]\d+)?[ \t]*['\u2032]"
                      r"|" + _MARKED_DEV + r"[ \t]*\u00b0" + _DMS_MIN + "?)")
_DMS_PART = _re.compile("(\\d*[.,]?\\d+)[ \\t]*(\u00b0|DEG(?:REES?)?\\b|['\u2032]"
                        "|[\"\u2033])?", _re.I)


def dms_degrees(text):
    """`45°30'` -> 45.5. Unmarked is degrees. None if no number."""
    total, seen = 0.0, False
    for num, unit in _DMS_PART.findall(str(text or "")):
        try:
            v = float(num.replace(",", "."))
        except ValueError:
            continue
        seen = True
        if unit in ("'", "\u2032"):
            v /= 60.0
        elif unit in ('"', "\u2033"):
            v /= 3600.0
        total += v
    return round(total, 9) if seen else None


def _angle(m):
    nom = _re.sub(r"[ \t]+", "", m.group("nom"))
    nom = _re.sub(r"DEG(?:REES?)?", "\u00b0", nom, flags=_re.I)
    if m.group("pm"):
        return nom, "\u00b1%.10g" % dms_degrees(m.group("pm"))
    for a, b in (("p1", "p2"), ("n1", "n2")):
        if m.group(a):
            return nom, "%s%.10g/%s%.10g" % (
                m.group(a)[0], dms_degrees(m.group(a)[1:]),
                m.group(b)[0], dms_degrees(m.group(b)[1:]))
    return nom, None


_NOT_REV = "".join("(?<!\\b%s)" % w for w in (
    "REV ", "REV. ", "REV: ", "REV.: ", "REVISION ", "REVISION: ", "REW ",
    "REW. ", "REWIZJA ", "REWIZJA: "))

# nominal never signed
_NOT_SIGNED = (r"(?<![+\u00b1\d.,])(?<![+\u00b1] )"
               r"(?:(?<![\s(/]-)(?<!^-)|(?=[1-9]))")

# Ø/R tolerance, same line
_DIA_TOL = (r"((?:(?<![\d.,])0(?=[ \t]*/)|[+\-\u00b1][ \t]*(?:\d*[.,]\d+"
            r"(?![\d.,]*[ \t]*\u00b0)|\d+(?![\d.,])(?![ \t]*(?:\u00b0|[Xx\u00d7]"
            r"(?![A-Za-z])|OTW|HOLES|POS))))(?:[ \t]*/[ \t]*(?:0(?:[.,]\d+)?"
            r"(?![\d.,])|[+\-][ \t]*\d*[.,]?\d+"
            # lower side guarded too
            r"(?![\d.,]*[ \t]*(?:\u00b0|[Xx\u00d7](?![A-Za-z])))))?)")

# angle deviation gap
_NEXT_DEV = (r"(?:[ \t]*/?[ \t]*\r?\n[ \t]*(?=[+\-][ \t]*" + _SIGNED_DMS
             + r"[ \t]*(?:\r?\n|\Z))|[ \t]*/?[ \t]*)")

# tolerance after chamfer angle
_ANG_TAIL = (r"(?:[ \t]*\u00b1[ \t]*(?P<ctail>" + _TOL_DMS + ")"
             r"|[ \t]*(?P<cp1>[+\-][ \t]*" + _SIGNED_DMS + r")[ \t]*/?[ \t]*"
             r"(?P<cp2>[+\-][ \t]*" + _SIGNED_DMS + "))")

# first claim wins
SCAN_PATS = [
    ("ANGLE", None,
     # angular pattern, total claimed
     r"(?<![\d.,])(\d{1,3})" + _XSEP + r"(\d+(?:[.,]\d+)?)\s*\u00b0?"
     r"\s*\(\s*=\s*\d+(?:[.,]\d+)?\s*\u00b0\s*\)",
     lambda m: ("%sX %s\u00b0" % (m.group(1), m.group(2)), None)),
    ("LINEAR", None,
     # linear pattern, total claimed
     r"(?<![\d.,])(\d{1,3})" + _XSEP + r"(\d+(?:[.,]\d+)?)"
     r"\s*\(\s*=\s*\d+(?:[.,]\d+)?\s*\)",
     lambda m: ("%sX %s" % (m.group(1), m.group(2)), None)),
    ("THREAD", None,
     # not a scale, same line
     r"(?<![A-Za-z])M[ \t]*\d+(?:[.,]\d+)?(?!\s*:\s*\d)"
     r"(?:" + _XSEP + r"\d+(?:[.,]\d+)?)?"
     r"(?:\s*-\s*[4-8][gGhH])?",
     lambda m: (_re.sub(r"^M\s+", "M", m.group(0).strip()), None)),
    ("THREAD", None,
     # pipe thread, fraction required
     r"(?<![A-Za-z\d])G\s*(\d+[ \t]+\d+/\d+|" + FRAC_SIZE + r")(?![\d/])"
     r"(?:\s*[AB](?![A-Za-z]))?(?:\s*-\s*\d[gGhH])?",
     lambda m: ("G" + _re.sub(r"\s+", " ", m.group(1).strip()), None)),
    ("THREAD", None,
     # series first, DIN style
     r"(?<![A-Za-z])(?:UNC|UNF|UNEF)[ \t]+(?:\d+[ \t]+\d+/\d+|"
     + FRAC_SIZE + r"|#\d+)(?:[ \t]*-[ \t]*\d+)?(?![\d/])",
     lambda m: (_re.sub(r"\s+", " ", m.group(0).strip()), None)),
    ("THREAD", None,
     r"(?:" + FRAC_SIZE + r"|#\d+)\s*-\s*\d+\s*"
     r"(?:UNC|UNF|UNEF|NPT|NPTF|BSP)?",
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
     # digit required, not word tail
     r"(?<![A-Za-z])(?:Rmax|Rsm|Ra|Rz|Rq|Rt|Rp|Rv)\s*(?:=\s*)?"
     r"([\d.,]*\d[\d.,]*)(?:\s*[-\u2013]\s*([\d.,]+))?\s*"
     r"(?:[\u00b5u]in|[\u00b5u]m|micron)?\s*(MAX|MIN)?",
     lambda m: (_re.sub(r"\s+", " ", m.group(0).strip()), None)),
    # fit, inch mark echoed
    ("FIT", None,
     r"(?:(\d+)\s*[Xx\u00d7]\s*)?(\u00d8?)[ \t]*"
     # not after letter or tolerance
     r"(?<![\d.,/A-Za-z+\u00b1])(?<![+\u00b1] )(?<!/-)"
     r"(?:(?<!-)|(?=[1-9]))"
     r"(\d+(?:[.,]\d+)?|[.,]\d+)[ \t]*"
     r"(\"|\u2033)?[ \t]*"
     r"((?:[A-Z]{1,2}|[a-z]{1,2})[ ]?\d{1,2}(?:\s*/\s*"
     r"(?:[A-Z]{1,2}|[a-z]{1,2})[ ]?\d{1,2})?)(?![\w\u00b0]|[.,]\d)",
     lambda m: (((m.group(1) + "X " if m.group(1) else "") +
                 m.group(2) + m.group(3) + ('"' if m.group(4) else "") +
                 " " + m.group(5).replace(" ", ""))
                if _fit_ok(m.group(5).replace(" ", ""))
                else None, m.group(5).replace(" ", ""))),
    # c'bore keeps own tolerance
    ("DIAMETER", "CBORE",
     r"(?:C'?BORE|CBORE|\u2334)\s*\u00d8\s*(\d+(?:[.,]\d+)?)" + _CHAM_TOL,
     lambda m: ("CBORE \u00d8" + m.group(1), _cham_t(m.group(2), m.group(1)))),
    ("DIAMETER", "CBORE",
     r"\u00d8\s*(\d+(?:[.,]\d+)?)\s*(?:C'?BORE|CBORE|\u2334)" + _CHAM_TOL,
     lambda m: ("CBORE \u00d8" + m.group(1), _cham_t(m.group(2), m.group(1)))),
    ("DIAMETER", "CBORE",
     r"(?:C'?BORE|CBORE|\u2334)\s*(\d+(?:[.,]\d+)?)",
     lambda m: ("CBORE " + m.group(1), None)),
    ("DIAMETER", "CSINK",
     # never its angle
     r"(?:C'?SINK|CSK|\u2335)\s*\u00d8?\s*(\d+(?:[.,]\d+)?)"
     r"(?![\d.,]*\s*\u00b0)" + _CHAM_TOL
     + r"(?:" + _XSEP + r"(\d+(?:[.,]\d+)?)\s*\u00b0?"
     + _ANG_TAIL + "?)?",
     lambda m: _csink(m, m.group(1), m.group(3),
                      _cham_t(m.group(2), m.group(1)))),
    # word after size
    ("DIAMETER", "CSINK",
     r"\u00d8\s*(\d+(?:[.,]\d+)?)[ \t]*(?:C'?SINK|CSK|\u2335)"
     r"(?:[ \t]*[xX\u00d7]?[ \t]*(\d+(?:[.,]\d+)?)[ \t]*\u00b0"
     + _ANG_TAIL + "?)?",
     lambda m: _csink(m, m.group(1), m.group(2), None)),
    ("DIAMETER", "CSINK",
     r"\u00d8\s*(\d+(?:[.,]\d+)?)" + _XSEP + r"(\d+(?:[.,]\d+)?)\s*\u00b0"
     + _ANG_TAIL + "?",
     lambda m: _csink(m, m.group(1), m.group(2), None)),
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
     # not a tolerance or prefix number
     r"(?<![\d\u00d8.,\u00b1+\-/A-Za-z])(?<!\u00d8 )(?<!\u00b1 )(?<![+\-] )"
     # not when value follows
     r"(" + FRAC_SIZE + r"|\d+(?:[.,]\d+)?)\s*(?:DEEP|DEPTH|\u21a7)\b"
     r"(?![ \t]*\.?[ \t]*\u00d8?[ \t]*\d+(?:[.,]\d+)?(?![\dXx\u00d7]))",
     lambda m: ("DEEP " + _frac(m.group(1)), None)),
    # depth keeps own tolerance
    ("DEPTH", None,
     # tol may equal depth
     r"\b(?:DEEP|DEPTH|\u21a7)\b\.?[ \t]*\u00d8?[ \t]*"
     r"(\d+(?:[ \t]*-[ \t]*|[ \t]+)\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)" + _CHAM_TOL,
     lambda m: ("DEEP " + _frac(m.group(1)),
                _cham_t(m.group(2), _frac(m.group(1)), strict=True))),
    # MIN/MAX before DIAMETER/RADIUS
    ("LIMIT", None,
     r"(?<![A-Za-z0-9])(S?\u00d8|S?R)?\s*(\d+(?:[.,]\d+)?)\s*"
     r"(MIN|MAX)\.?(?![A-Za-z])",
     lambda m: ((m.group(1) or "") + m.group(2) + " "
                + m.group(3).upper(), None)),
    ("DIAMETER", None,
     r"(?:(\d+)\s*[Xx\u00d7]\s*)?(?:(?<![A-Za-z0-9])S)?"
     r"\u00d8\s*(\d+(?:[.,]\d+)?)"
     # tolerance on own line
     + _SIZE_MOD + r"[ \t]*"
     # never count or angle
     + _DIA_TOL + "?" + _SIZE_MOD,
     lambda m: ((m.group(1) + "X " if m.group(1) else "") +
                _spherical(m) + "\u00d8" + m.group(2) + _size_mod(m),
                m.group(3).replace(" ", "") if m.group(3) else None)),
    ("RADIUS", None,
     # not REV letter, dash ok
     r"(?:^|[\s,(\-])" + _NOT_REV
     # diameter's tolerance rules
     + r"S?R\s*(\d+(?:[.,]\d+)?)(?:[ \t]*" + _DIA_TOL + ")?",
     lambda m: (_spherical(m) + "R" + m.group(1),
                m.group(2).replace(" ", "") if m.group(2) else None)),
    # decimals both sides, integer pair excluded
    ("SLOT", None,
     r"(?<![\u00d8\d,.\u00b1])(?<!\u00b1 )(\d+[.,]\d+)"
     r"(?:[ \t]*\u00b1[ \t]*(\d+(?:[.,]\d+)?))?"
     r"\s*[Xx\u00d7]\s*(\d+[.,]\d+)(?!\s*[\u00b0Xx\u00d7\d])",
     lambda m: (m.group(1) + " X " + m.group(3),
                "\u00b1" + m.group(2) if m.group(2) else None)),
    ("CHAMFER", None,
     # DEG, fraction legs, angle tol claimed
     r"(?<!\d[.,])(?<![\d/])(\d+(?:[ \t]*-[ \t]*|[ \t]+)\d+/\d+|\d+/\d+"
     r"|\d+(?:[.,]\d+)?)" + _XSEP + r"(\d+(?:[.,]\d+)?)\s*"
     r"(?:\u00b0|DEG(?:REES?)?\b)" + _CHAM_TOL + _ANG_TAIL + "?",
     lambda m: _chamfer(m)),
    # leg and angle, no `x`
    ("CHAMFER", None,
     r"\bC[ \t]?(\d+(?:[.,]\d+)?)[ \t]+(\d+(?:[.,]\d+)?)[ \t]*"
     r"(?:\u00b0|DEG(?:REES?)?\b)",
     lambda m: (m.group(1) + "X" + m.group(2) + "\u00b0", None)),
    ("CHAMFER", None,
     r"\bC[ \t]?(\d+(?:[.,]\d+)?)(?![\d.,])" + _CHAM_TOL
     + r"(?![ \t]*[A-Za-z])",
     lambda m: ("C" + m.group(1), _cham_t(m.group(2), m.group(1)))),
    ("ANGLE", None,
     # signed angle is deviation
     r"(?<![+\u00b1\d.,])(?<![+\u00b1] )(?<![\s(/]-)(?<!^-)"
     r"(?P<nom>\d+(?:[.,]\d+)?[ \t]*" + _DEG + _DMS_MS + "?)"
     r"(?:[ \t]*\u00b1[ \t]*(?P<pm>" + _TOL_DMS + ")"
     # signed pair, real deviations
     r"|[ \t]*(?P<p1>\+[ \t]*" + _SIGNED_DMS + r")" + _NEXT_DEV
     + r"(?P<p2>[+\-][ \t]*" + _SIGNED_DMS + r")"
     r"|[ \t]*(?P<n1>-[ \t]*" + _SIGNED_DMS_MARKED + r")" + _NEXT_DEV
     + r"(?P<n2>[+\-][ \t]*" + _SIGNED_DMS + r"))?",
     lambda m: _angle(m)),
    # keep brackets, [50] basic (75) ref
    ("LINEAR", "BASIC", r"\[\s*(\d+(?:[.,]\d+)?)\s*\]",
     lambda m: ("[" + m.group(1) + "]", "BASIC")),
    ("LINEAR", "REF", r"\(\s*(\d+(?:[.,]\d+)?)\s*\)",
     lambda m: ("(" + m.group(1) + ")", "REF")),
    ("LINEAR", None,
     # tolerance on own line
     _NOT_SIGNED + r"(\d+(?:[.,]\d+)?)" + _SIZE_MOD
     + r"[ \t]*\u00b1\s*(\d*[.,]?\d+)"
     + _SIZE_MOD,
     lambda m: (m.group(1) + _size_mod(m), "\u00b1" + m.group(2))),
    ("LINEAR", None,
     _NOT_SIGNED + r"(\d+(?:[.,]\d+)?)" + _SIZE_MOD + r"[ \t]*"
     r"((?:(?<![\d.,])0(?:[.,]\d+)?(?=\s*/)|[+\-]\s*\d*[.,]?\d+)\s*/\s*"
     r"(?:0(?:[.,]\d+)?(?![\d.,])|[+\-]\s*\d*[.,]?\d+))" + _SIZE_MOD,
     lambda m: (m.group(1) + _size_mod(m), m.group(2).replace(" ", ""))),
    ("LINEAR", None,
     _NOT_SIGNED + r"(\d+(?:[.,]\d+)?)" + _SIZE_MOD
     + r"[ \t]*([+\-]\d+[.,]\d+)(?![\d.,/%])" + _SIZE_MOD,
     lambda m: (m.group(1) + _size_mod(m), m.group(2))),
]


DENORM = {
    "THRU": ("THROUGH", "PRZELOT", "PRZELOTOWY",
             "DURCH", "DURCHGANG", "DURCHGEHEND"),
    "DEEP": ("G\u0141.", "G\u0141\u0118B.", "TIEF", "TIEFE", "DP"),
    "CBORE": ("C'BORE", "COUNTERBORE", "SPOTFACE", "FLACHSENKUNG",
              "POG\u0141\u0118BIENIE WALCOWE", "\u2334"),
    "CSINK": ("CSK", "COUNTERSINK", "C'SINK", "ANSENKUNG", "SENKUNG",
              "POG\u0141\u0118BIENIE STO\u017bKOWE", "\u2335"),
}

# callout vocabulary (EN/DE/PL), exported for redactor
CALLOUT_TERMS =frozenset({
    "THRU", "THROUGH", "DURCH", "DURCHGANG", "DURCHGANGSLOCH",
    "DURCHGANGSBOHRUNG", "DURCHGEHEND", "DURCHGEBOHRT", "DURCHBOHREN",
    "DURCHBOHRUNG", "DURCHBOHRT", "PRZELOT", "PRZELOTOWY", "PRZELOTOWE",
    "PRZEJ\u015aCIOWA", "PRZEJ\u015aCIOWE", "PRZEJ\u015aCIOWY", "ALLES", "ALL",
    "DEEP", "DEPTH", "TIEF", "TIEFE", "DP", "G\u0141", "G\u0141\u0118B",
    "G\u0141\u0118BOKO\u015a\u0106",
    "DIA", "DIAM", "DIAMETER", "DURCHMESSER", "DMR", "\u015aREDNICA", "\u015aR",
    "RADIUS", "RAD", "PROMIE\u0143", "CHAMFER", "CHAM", "FASE", "FAZA",
    "FAZOWANIE",
    "CBORE", "COUNTERBORE", "SPOTFACE", "FLACHSENKUNG", "POG\u0141\u0118BIENIE",
    "WALCOWE", "SF", "CSINK", "COUNTERSINK", "CSK", "ANSENKUNG", "SENKUNG",
    "STO\u017bKOWE",
    "PLACES", "PLCS", "PLC", "OTWORY", "OTWOR\u00d3W", "OTW", "STK",
    "ST\u00dcCK", "MAL",
    "THREAD", "THREADED", "TAP", "TAPPED", "DRILL", "DRILLED", "BORE",
    "BORED", "REAM", "REAMED", "HOLE", "HOLES", "SLOT", "SLOTS", "TYP",
    "TYPICAL", "REF", "GEWINDE", "BOHRUNG", "BOHREN", "REIBEN",
})


def denorm_candidates(s, limit=12):
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
