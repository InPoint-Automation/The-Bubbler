# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Word token clean-up before line building.

import re as _re
from bubbler.reader import geometry, grammar  # noqa: E402


_GLYPHS = {
    "\u00f8": "\u00d8", "\u2300": "\u00d8", "\u2205": "\u00d8",
    "\uf044": "\u00d8", "\uf064": "\u00d8",
    "\uf052": "\u00b1", "\uf072": "\u00b1",
    "\uf030": "\u00b0",
    "\u2212": "-", "\u2013": "-", "\u2011": "-",
}

# ISO hole marks -> keyword
_SYMBOLS = {
    "\u2334": "CBORE", "\u2294": "CBORE",
    "\u2335": "CSINK", "\u2228": "CSINK", "\u22c1": "CSINK",
    "\u21a7": "DEEP", "\u2913": "DEEP", "\u25bd": "DEEP",
    "\u25bf": "DEEP", "\u25bc": "DEEP", "\u25be": "DEEP",
    "\u2207": "DEEP", "\u22bd": "DEEP", "\u23f7": "DEEP",
    "\u2304": "DEEP",
}

_KEYWORDS = [
    (("THROUGH",), "THRU", None),
    (("PRZELOTOWY",), "THRU", None),
    (("PRZELOTOWE",), "THRU", None),
    (("PRZELOT",), "THRU", None),
    (("PRZEJŚCIOWY",), "THRU", None),
    (("PRZEJŚCIOWE",), "THRU", None),
    (("PRZEJŚCIOWA",), "THRU", None),
    (("DURCHGANGSLOCH",), "THRU", None),
    (("DURCHGANGSBOHRUNG",), "THRU", None),
    (("DURCHGEBOHRT",), "THRU", None),
    (("DURCHBOHREN",), "THRU", None),
    (("DURCHBOHRT",), "THRU", None),
    (("DURCHBOHRUNG",), "THRU", None),
    (("DURCHGANG",), "THRU", None),
    (("DURCHGEHEND",), "THRU", None),
    (("DURCH",), "THRU", None),
    (("//",), "PARALLELISM", "num"),
    (("G\u0141\u0118B",), "DEEP", None),
    (("G\u0141",), "DEEP", None),
    (("TIEFE",), "DEEP", None),
    (("TIEF",), "DEEP", None),
    (("DP",), "DEEP", "num"),
    (("DURCHMESSER",), "\u00d8", None),
    (("DMR",), "\u00d8", "num"),
    (("\u015aREDNICA",), "\u00d8", None),
    (("\u015aR",), "\u00d8", "num"),
    (("DIAM",), "\u00d8", "num"),
    (("DIA",), "\u00d8", "num"),
    (("RADIUS",), "R", "num"),
    (("PROMIE\u0143",), "R", "num"),
    (("FASE",), "C", "num"),
    (("FAZA",), "C", "num"),
    (("FAZOWANIE",), "C", "num"),
    (("CHAMFER",), "C", "num"),
    (("POG\u0141\u0118BIENIE", "WALCOWE"), "CBORE", None),
    (("FLACHSENKUNG",), "CBORE", None),
    (("SPOTFACE",), "CBORE", None),
    (("COUNTERBORE",), "CBORE", None),
    (("COUNTERBORED",), "CBORE", None),
    (("SF",), "CBORE", "dnum"),
    (("POG\u0141\u0118BIENIE", "STO\u017bKOWE"), "CSINK", None),
    (("ANSENKUNG",), "CSINK", None),
    (("SENKUNG",), "CSINK", None),
    (("COUNTERSINK",), "CSINK", None),
    (("COUNTERSUNK",), "CSINK", None),
    (("CSK",), "CSINK", "dnum"),
]

_COUNT_WORDS = ("PLACES", "PLCS", "OTWORY", "OTWOR\u00d3W", "OTW",
                "STK", "ST\u00dcCK", "MAL", "POS", "PCS", "HOLES", "POSN")
_COUNT_RE = _re.compile(
    r"(\d+)\s*(?:%s)\.?$" % "|".join(_COUNT_WORDS), _re.I)

_NUM_START = _re.compile(r"^[\d.]")
_DNUM_START = _re.compile(r"^[\u00d8\d.]")


def _kw_key(text):
    return text.upper().rstrip(".,;:")


def _cond_match(cond, nxt):
    if cond is None:
        return True
    if not nxt:
        return False
    pat = _NUM_START if cond == "num" else _DNUM_START
    return bool(pat.match(nxt))


# phi look-alikes, conditional
_PHI_RE = _re.compile(r"(?<![A-Za-z0-9.,])"
                      r"[\u03a6\u03c6\u03d5\u0424](?=\d)")


def _norm_token(s):
    for a, b in _GLYPHS.items():
        s = s.replace(a, b)
    s = _PHI_RE.sub("\u00d8", s)
    for a, b in _SYMBOLS.items():
        s = s.replace(a, " %s " % b)
    for a, b in grammar._GDT_SYMBOLS:
        if a in s:
            s = s.replace(a, b)
    s = grammar.GLUED_COUNT.sub(r"\1 ", s)
    s = _COUNT_RE.sub(lambda m: m.group(1) + "X", s)
    s = _re.sub(r"\bDIAM?\.?(?=[\d.])", "\u00d8", s, flags=_re.I)
    s = _re.sub(r"[\u00c6\u00e6](?=\s*\d)", "\u00d8", s)
    s = _re.sub(r"([+\-]\d+[.,]\d+)(?=[+\-]\d+[.,]\d+)", r"\1/", s)
    return s


def _heal_phi(s):
    """Ambiguous phi heals. Run after split merge, never per token."""
    s = _re.sub(r"(?<![A-Za-z0-9.,])[OoQ\u03a6\u03c6\u0398\u03b8](?=\d)",
                "\u00d8", s)
    s = _re.sub(r"(?<![\dA-Za-z.,/+\-:])0(?=\d{1,3}(?:[.,]\d+)?(?![\d.,\-:]))",
                "\u00d8", s)
    return s


def norm_tokens(strs):
    """OCR strings -> tokens. One entry, one heal order."""
    toks = []
    for s in strs:
        s = _norm_token(s).strip()
        if s:
            toks.extend({"t": p, "r": None} for p in s.split())
    return [_heal_phi(t["t"]) for t in _merge_split_values(toks)]


def _normalize_line(line):
    toks = []
    for t in line["toks"]:
        s = _norm_token(t["t"]).strip()
        if not s:
            continue
        for part in s.split():
            toks.append({"t": part, "r": t["r"]})

    out = []
    i = 0
    while i < len(toks):
        hit = None
        for words, canon, cond in _KEYWORDS:
            n = len(words)
            if i + n > len(toks):
                continue
            if all(_kw_key(toks[i + j]["t"]) == words[j]
                   for j in range(n)):
                # condition on healed copy
                nxt = (_heal_phi(toks[i + n]["t"]) if i + n < len(toks)
                       else "")
                if _cond_match(cond, nxt):
                    hit = (n, canon)
                    break
        if hit:
            n, canon = hit
            out.append({"t": canon,
                        "r": geometry._union_all([toks[i + j]["r"]
                                         for j in range(n)])})
            i += n
        else:
            out.append(toks[i])
            i += 1
    toks = out
    # size before word, as flat reader
    out = []
    for t in toks:
        if out and _kw_key(t["t"]) in ("CHAMFER", "CHAM") and \
                _re.fullmatch(r"\d+(?:[.,]\d+)?", out[-1]["t"]):
            out[-1] = {"t": "C" + out[-1]["t"],
                       "r": geometry._union_all([out[-1]["r"], t["r"]])}
            continue
        out.append(t)
    toks = out

    toks = _merge_split_values(toks)

    for t in toks:
        t["t"] = _re.sub(grammar.LEAD_DOT, "0.", _heal_phi(grammar.ascii_pm(t["t"])))

    line["toks"] = toks


_FRAC_HEAD = _re.compile(r"\d+")
_FRAC_TAIL = _re.compile(grammar.FRAC_TAIL)


def _frac_ok(toks, k):
    m = _FRAC_HEAD.match(toks[k]["t"])
    if not m:
        return False
    tail = toks[k]["t"][m.end():]
    if not tail:
        tail = " "
    tail += " ".join(t["t"] for t in toks[k + 1:k + 3])
    return bool(_FRAC_TAIL.match(tail))


def _glued_ok(toks, k):
    m = _re.match(r"^[.,]\d{1,4}", toks[k]["t"])
    if not m:
        return False
    tail = toks[k]["t"][m.end():] or " "
    tail += " ".join(t["t"] for t in toks[k + 1:k + 3])
    return bool(_FRAC_TAIL.match(tail))


_SDEV_TOK = _re.compile("^" + grammar.SIGNED_DEV + "$")


def _merge_split_values(toks):
    """Rejoin OCR-split numbers. One implementation, both readers."""
    def merge_run(i, j, text):
        rs = [t["r"] for t in toks[i:j + 1] if t["r"] is not None]
        toks[i] = {"t": text, "r": geometry._union_all(rs) if rs else None}
        del toks[i + 1:j + 1]

    _drop_inch_marks(toks)
    changed = True
    while changed:
        changed = False
        for i in range(len(toks) - 1):
            a, b = toks[i]["t"], toks[i + 1]["t"]
            c = toks[i + 2]["t"] if i + 2 < len(toks) else None
            # `c` must be bare fraction
            if (c is not None and _frac_ok(toks, i + 2) and (
                    (b in (".", ",") and _re.match(r"^\d+$", a)) or
                    # prefixed size split on dot
                    (b in (".", ",") and _re.search(r"\d$", a)))):
                merge_run(i, i + 2, a + b + c)      # OCR-split 0 , 1
            elif (_re.search(r"\d$", a) and _glued_ok(toks, i + 1)):
                # fraction glued to separator
                merge_run(i, i + 1, a + b)
            elif (_re.search(r"\d\.$", a) and _re.match(r"^\d", b)
                    and not _re.match(r"^0\d", b) and _frac_ok(toks, i + 1)
                    and not (i and grammar.NOTE_NUM.search(
                        toks[i - 1]["t"] + " " + a[:-2]))):
                # `10. 5`, `0`-led left alone
                merge_run(i, i + 1, a + b)
            elif a in "+-" and _re.match(r"^[\d.][\d.,]*$", b):
                merge_run(i, i + 1, a + b)
            # signed pair under 10
            elif (_SDEV_TOK.match(a) and _SDEV_TOK.match(b)):
                merge_run(i, i + 1, a + "/" + b)
            elif (a == "0" and _SDEV_TOK.match(b)):
                merge_run(i, i + 1, "0/" + b)
            elif (b == "0" and _SDEV_TOK.match(a)):
                merge_run(i, i + 1, a + "/0")
            elif (_re.match(r"^\d+$", a) and
                    _kw_key(b) in _COUNT_WORDS):
                merge_run(i, i + 1, a + "X")
            else:
                continue
            changed = True
            break
    _fold_limits(toks)
    return toks


def _drop_inch_marks(toks):
    """Strip inch marks before merges."""
    i = 0
    while i < len(toks):
        t = toks[i]["t"]
        prev = " ".join(x["t"] for x in toks[:i])
        nxt = " " + toks[i + 1]["t"] if i + 1 < len(toks) else ""
        if t in ('"', "\u2033"):
            if _re.search(r"\d$", prev) and grammar.inch_mark_drops(prev, nxt):
                del toks[i]
                continue
            i += 1
            continue
        out, pos = [], 0
        for m in _re.finditer("(\\d)[\"\u2033]", t):
            rest = t[m.end():] + (nxt if m.end() == len(t) else "")
            if grammar.inch_mark_drops(prev + " " + t[:m.start(1) + 1], rest):
                out.append(t[pos:m.start(1) + 1])
                pos = m.end()
        if out:
            toks[i] = {"t": "".join(out) + t[pos:], "r": toks[i]["r"]}
        i += 1


_LIM_WHOLE = _re.compile("^\u00d8\\d*[.,]?\\d+-\u00d8\\d*[.,]?\\d+$")


def _fold_limits(toks):
    i = 0
    while i < len(toks):
        for n in range(1, 6):
            if i + n > len(toks):
                break
            cat = "".join(t["t"] for t in toks[i:i + n])
            if not _LIM_WHOLE.match(cat):
                continue
            nxt = toks[i + n]["t"] if i + n < len(toks) else ""
            folded = grammar.fold_limit_prefix(cat + " " + nxt).split(" ", 1)[0]
            if folded != cat:
                rs = [t["r"] for t in toks[i:i + n] if t["r"] is not None]
                toks[i] = {"t": folded,
                           "r": geometry._union_all(rs) if rs else None}
                del toks[i + 1:i + n]
            break
        i += 1
