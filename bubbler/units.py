# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Per-drawing mm-vs-inch unit detector.

import re

UNKNOWN = "unknown"
MM = "iso_mm"
INCH = "asme_inch"

# verdict thresholds
MIN_TOTAL = 3.0
MIN_MARGIN = 0.34
MIN_CONF = 0.25
# evidence for full conf
FULL_EVIDENCE = 8.0

_MM_STATED = re.compile(
    r"\b(?:DIM(?:ENSION)?S?|MEASUREMENTS?|UNITS?|WYMIARY|MA(?:SS|ß)E)\b"
    r"[^.\n]{0,40}?\bIN\s+"
    r"(?:MM\b|MILLIMET(?:RE|ER)S?\b|MILIMETR\w*)"
    r"|\bUNITS?\s*[:=]\s*(?:MM\b|MILLIMET(?:RE|ER)S?\b)"
    r"|\bALL\s+DIM(?:ENSION)?S?\b[^.\n]{0,30}\bMM\b"
    r"|\bWYMIARY\s+W\s+MM\b|\bMA(?:SS|ß)E\s+IN\s+MM\b",
    re.I | re.U)
_INCH_STATED = re.compile(
    r"\b(?:DIM(?:ENSION)?S?|MEASUREMENTS?|UNITS?)\b"
    r"[^.\n]{0,40}?\bIN\s+(?:INCH(?:ES)?\b|IN\.)"
    r"|\bUNITS?\s*[:=]\s*INCH(?:ES)?\b"
    r"|\bALL\s+DIM(?:ENSION)?S?\b[^.\n]{0,30}\bINCH(?:ES)?\b"
    r"|\bDECIMAL\s+INCH(?:ES)?\b",
    re.I)

# metric standards imply mm
_METRIC_STD = re.compile(
    r"\bISO\s*[- ]?\s*(?:2768|8015|22081|1101|286)\b"
    r"|\bDIN\s*[- ]?\s*(?:7168|ISO)\b|\bEN\s*22768\b", re.I)
_ASME_STD = re.compile(r"\b(?:ASME|ANSI)\s*[- ]?\s*Y\s*14\.5\b", re.I)

_FRAC_TOL = re.compile(
    r"(?:±|\+/-|\+\s*-)\s*\d{1,2}\s*/\s*\d{1,3}\b"
    r"(?!\s*(?:°|DEG|MIN\b|′))", re.I)
# ASME decimal-place block
_DP_BLOCK = re.compile(
    r"\.X{2,4}\s*[:=]?\s*(?:±|\+/-)?\s*\.?\d"
    r"|\b(?:ONE|TWO|THREE|FOUR)\s+PLACE\s+DECIMAL", re.I)

_MM_SUFFIX = re.compile(r"\d\s*MM\b", re.I)
_INCH_SUFFIX = re.compile(r"\d\s*(?:IN\.|INCH(?:ES)?\b)|\d\s*\"", re.I)

_MM_THREAD = re.compile(r"(?<![A-Z0-9])M\s*\d{1,3}(?:[.,]\d+)?"
                        r"(?:\s*[x×]\s*\d+(?:[.,]\d+)?)?", re.I)
_INCH_THREAD = re.compile(
    r"(?:\d+/\d+|#\d+)\s*-\s*\d+|\bUNC\b|\bUNF\b|\bUNEF\b|\bNPTF?\b", re.I)

_DECIMAL = re.compile(r"\d[.,]\d+")
_NUMBER = re.compile(r"(?<![\d.,])\d+[.,]\d+(?![\d.,])")


def _dp_distribution(text):
    """fine vs coarse decimal counts for inch check"""
    fine = coarse = 0
    for m in _NUMBER.finditer(text):
        dp = len(m.group(0).replace(",", ".").split(".", 1)[1])
        if dp >= 3:
            fine += 1
        else:
            coarse += 1
    return fine, coarse


def detect_units(text):
    """unit-system verdict off drawing's text layer"""
    t = text or ""
    sig = []

    def vote(name, side, weight):
        sig.append((name, side, float(weight)))

    if _MM_STATED.search(t):
        vote("stated_mm", MM, 6)
    if _INCH_STATED.search(t):
        vote("stated_inch", INCH, 6)
    if _METRIC_STD.search(t):
        vote("metric_standard", MM, 4)
    if _ASME_STD.search(t):
        vote("asme_standard", INCH, 1)
    if _FRAC_TOL.search(t):
        vote("fractional_tol_block", INCH, 4)
    if _DP_BLOCK.search(t):
        vote("decimal_place_block", INCH, 3)

    n_mm = len(_MM_SUFFIX.findall(t))
    if n_mm:
        vote("mm_suffix", MM, 2 if n_mm >= 2 else 1)
    n_in = len(_INCH_SUFFIX.findall(t))
    if n_in:
        vote("inch_suffix", INCH, 2 if n_in >= 2 else 1)

    commas = len(re.findall(r"\d,\d", t))
    points = len(re.findall(r"\d\.\d", t))
    if commas >= 3 and commas > points:
        vote("decimal_comma", MM, 2)

    if _MM_THREAD.search(t):
        vote("metric_thread", MM, 2)
    if _INCH_THREAD.search(t):
        vote("inch_thread", INCH, 2)

    fine, coarse = _dp_distribution(t)
    total_n = fine + coarse
    if total_n >= 6:
        if fine >= 0.6 * total_n:
            vote("three_place_decimals", INCH, 2)
        elif coarse >= 0.8 * total_n:
            vote("one_two_place_decimals", MM, 1.5)

    score = {MM: 0.0, INCH: 0.0}
    for _n, side, w in sig:
        score[side] += w
    total = score[MM] + score[INCH]
    if total <= 0:
        return {"units": UNKNOWN, "conf": 0.0, "signals": sig}
    lead = MM if score[MM] >= score[INCH] else INCH
    other = INCH if lead == MM else MM
    margin = (score[lead] - score[other]) / total
    conf = margin * min(1.0, total / FULL_EVIDENCE)
    if total < MIN_TOTAL or margin < MIN_MARGIN or conf < MIN_CONF:
        return {"units": UNKNOWN, "conf": round(conf, 3), "signals": sig}
    return {"units": lead, "conf": round(conf, 3), "signals": sig}


def detect_units_doc(doc, max_pages=4):
    """same verdict over first pages of open fitz doc"""
    parts = []
    try:
        n = min(int(getattr(doc, "page_count", 0) or 0), max_pages)
    except (TypeError, ValueError):
        n = 0
    for i in range(n):
        try:
            parts.append(doc[i].get_text("text") or "")
        except Exception:
            continue
    return detect_units("\n".join(parts))


MM_PER_INCH = 25.4


def unit_suffix(units):
    """unit code mm/in not translated word"""
    return "in" if units == INCH else "mm"


def other_units(units):
    """other system mm <-> inch"""
    return MM if units == INCH else INCH


def convert_units(v, src, dst):
    """scalar between unit systems by ONE multiply or divide"""
    if v is None or src == dst:
        return v
    if src == INCH and dst == MM:
        return v * MM_PER_INCH
    if src == MM and dst == INCH:
        return v / MM_PER_INCH
    return v


DISPLAY_DP = {MM: 4, INCH: 5}


NOMINAL_DP = {MM: 2, INCH: 4}


def format_nominal(v, units):
    """nominal as shown in drawing's own system"""
    if v is None:
        return ""
    return "%.*f" % (NOMINAL_DP.get(units, 2), float(v))


def format_converted(v, units):
    """converted field text with trailing zeros gone"""
    if v is None:
        return ""
    s = "%.*f" % (DISPLAY_DP.get(units, 4), float(v))
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"
