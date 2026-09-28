# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Words -> lines. Merges callout pieces.

import re as _re
from bubbler.reader import geometry  # noqa: E402


def _ltext(line):
    return " ".join(t["t"] for t in line["toks"])


def _lrect(line):
    return geometry._union_all([t["r"] for t in line["toks"]])


def _lheight(line):
    hs = [t["r"][3] - t["r"][1] for t in line["toks"]]
    hs.sort()
    return max(2.0, hs[len(hs) // 2])


def lines_from_words(words):
    groups = {}
    for w in words:
        x0, y0, x1, y1, text, blk, ln, wn = w[:8]
        groups.setdefault((blk, ln), []).append(
            (wn, {"t": str(text), "r": (float(x0), float(y0),
                                        float(x1), float(y1))}))
    lines = []
    for key in sorted(groups):
        toks = [t for _, t in sorted(groups[key], key=lambda kv: kv[0])]
        lines.append({"key": key, "toks": toks})
    return lines


# deviation under 10, or DMS angle
_DMS_DEV = ("[+\\-]\\s*(?:\\d{1,2}(?:[.,]\\d+)?\\s*\u00b0"
            "(?:\\s*[0-5]?\\d\\s*['\u2032])?|[0-5]?\\d\\s*['\u2032])")
_DEV_LINE = _re.compile(r"^(?:[+\-]\s*(?:\d(?:[.,]\d+)?|[.,]\d+)|0(?:[.,]\d+)?"
                        "|" + _DMS_DEV + ")$")
_NX_LINE = _re.compile(r"^\d+[Xx\u00d7]$")
_NUMONLY_LINE = _re.compile(r"^[.\d]+$")
_FIT_LINE = _re.compile(
    r"^([A-Za-z]{1,2}[ ]?\d{1,2})"
    r"(?:\s*/\s*[A-Za-z]{1,2}[ ]?\d{1,2})?$")
# raised fit code plus its band
_FIT_DEV_LINE = _re.compile(
    r"^([A-Za-z]{1,2}[ ]?\d{1,2})((?:\s+[+\-\u00b1]\s*[\d.,]+"
    r"(?:\s*/\s*[+\-]?\s*[\d.,]+)?)+)$")


def _split_lines_on_gaps(lines, factor=4.0):
    out = []
    for l in lines:
        toks = l["toks"]
        if len(toks) < 2:
            out.append(l)
            continue
        h = _lheight(l)
        cur = [toks[0]]
        for t in toks[1:]:
            if t["r"][0] - cur[-1]["r"][2] > factor * h:
                out.append({"key": l["key"], "toks": cur})
                cur = [t]
            else:
                cur.append(t)
        out.append({"key": l["key"], "toks": cur})
    return out


_DEPTH_MARK = _re.compile(r"\bDEEP\b", _re.I)


def _depth_marker_idxs(lines):
    return [i for i, l in enumerate(lines) if _DEPTH_MARK.search(_ltext(l))]


def _depth_marker_rect(line):
    """From DEEP on, not whole line."""
    toks = line["toks"]
    for k, t in enumerate(toks):
        if _DEPTH_MARK.search(t["t"]):
            return geometry._union_all([x["r"] for x in toks[k:]])
    return _lrect(line)


def _depth_owned(idx, lines, markers):
    r = _lrect(lines[idx])
    h = max(r[3] - r[1], 2.0)
    for mi in markers:
        if mi == idx:
            continue
        rm = _depth_marker_rect(lines[mi])
        if min(r[2], rm[2]) - max(r[0], rm[0]) <= 0:
            continue
        if max(rm[1] - r[3], r[1] - rm[3], 0.0) <= 2.0 * h:
            return True
    return False


_STACK_REACH = 12       # text heights
# tail tolerance = complete line
_HAS_TOL = _re.compile(r"(?:\u00b1|[+\-])\s*[\d.,]*\d\s*$")
_LONE_NOMINAL = _re.compile(
    r"^(?:\d+[Xx\u00d7]\s*)?(?:\u00d8|\u2300|SR|R)?\s*\d+(?:[.,]\d+)?$")
_PM_LINE = _re.compile(r"^\u00b1\s*[\d.,]*\d$")


def _follows(ra, rd, h):
    """Straight above/below is another callout."""
    cx = (rd[0] + rd[2]) / 2.0
    cy = (rd[1] + rd[3]) / 2.0
    dx = cx - ra[2]
    dy = abs(cy - (ra[1] + ra[3]) / 2.0)
    return dx > 0 and dy <= dx + 0.25 * h


def merge_pm_stack(lines):
    used = set()
    for di, D in enumerate(lines):
        td = _ltext(D).strip()
        if not _PM_LINE.match(td):
            continue
        rd = _lrect(D)
        h = max(rd[3] - rd[1], 2.0)
        best = None
        for ai, A in enumerate(lines):
            if ai == di or ai in used:
                continue
            ta = _ltext(A)
            if not _LONE_NOMINAL.match(ta.strip()):
                continue
            ra = _lrect(A)
            if rd[1] < ra[1] - 0.5 * h:
                continue              # never above
            vgap = max(rd[1] - ra[3], ra[1] - rd[3], 0.0)
            if vgap > 1.5 * h:
                continue
            # after it, never straight under
            hgap = rd[0] - ra[2]
            if not (-h <= hgap <= 4 * h) or not _follows(ra, rd, h):
                continue
            score = vgap + max(hgap, 0.0)
            if best is None or score < best[0]:
                best = (score, ai)
        if best is not None:
            lines[best[1]]["toks"].append(
                {"t": td.replace(" ", ""), "r": rd})
            used.add(di)
    return [l for i, l in enumerate(lines) if i not in used]


def _bare_fit_code(t):
    """`R3`, `M6`, `O 20` are sizes."""
    from bubbler.reader.grammar import _fit_ok
    t = t.strip()
    return bool(_FIT_LINE.match(t)) and _fit_ok(t.replace(" ", "")) \
        and not _re.match(r"[CRMST]", t, _re.I)


def _dev_val(t):
    """Signed value, degrees for DMS."""
    m = _re.fullmatch(r"([+\-\u2212]?)\s*(\d*[.,]?\d+)", t.strip())
    if m:
        v = float(m.group(2).replace(",", "."))
        return -v if m.group(1) in ("-", "\u2212") else v
    if _re.fullmatch(_DMS_DEV, t.strip()):
        from bubbler.reader.grammar import dms_degrees
        v = dms_degrees(t.strip()[1:])
        if v is None:
            return None
        return -v if t.strip()[0] == "-" else v
    return None


def merge_stacked(lines):
    used = set()
    markers = _depth_marker_idxs(lines)
    devs = [i for i, l in enumerate(lines)
            if _DEV_LINE.match(_ltext(l).strip())
            and not _depth_owned(i, lines, markers)]
    for bi in devs:
        if bi in used:
            continue
        rb = _lrect(lines[bi])
        tb = _ltext(lines[bi]).strip()
        for ci in devs:
            if ci in used or ci == bi:
                continue
            rc = _lrect(lines[ci])
            tc = _ltext(lines[ci]).strip()
            if not (tb.startswith(("+", "-")) or
                    tc.startswith(("+", "-"))):
                continue
            h = max(rb[3] - rb[1], rc[3] - rc[1], 2.0)
            if min(rb[2], rc[2]) - max(rb[0], rc[0]) <= 0:
                continue
            if rc[1] < rb[1]:
                continue
            if rc[1] - rb[3] > 1.5 * h:
                continue
            # upper deviation on top
            if _dev_val(tb) is not None and _dev_val(tc) is not None \
                    and _dev_val(tb) < _dev_val(tc):
                continue
            top, bot = min(rb[1], rc[1]), max(rb[3], rc[3])
            best = None
            for ai, A in enumerate(lines):
                if ai in used or ai in (bi, ci):
                    continue
                ta = _ltext(A)
                if not _re.search("[\\d\u00b0'\u2032]\\s*$", ta):
                    continue
                if _DEV_LINE.match(ta.strip()):
                    continue
                if _bare_fit_code(ta):
                    continue      # fit code, no size
                if _re.search(r"\d\s*:\s*\d", ta):    # ratio
                    continue
                if _HAS_TOL.search(ta):
                    continue
                ra = _lrect(A)
                cy = (ra[1] + ra[3]) / 2.0
                if not (top - h <= cy <= bot + h):
                    continue
                gap = min(rb[0], rc[0]) - ra[2]
                # only onto incomplete nominal
                if gap < -h or gap > _STACK_REACH * h:
                    continue
                if not _follows(ra, geometry._union(rb, rc), h):
                    continue      # another callout
                # level with stack, not gap alone
                off = min(abs(cy - (rc[1] + rc[3]) / 2.0),
                          abs(cy - (top + bot) / 2.0))
                if best is None or gap + off < best[0]:
                    best = (gap + off, ai)
            if best is not None:
                A = lines[best[1]]
                txt = (tb + "/" + tc).replace(" ", "")
                A["toks"].append({"t": txt, "r": geometry._union(rb, rc)})
                used.add(bi)
                used.add(ci)
                break
    return [l for i, l in enumerate(lines) if i not in used]


_SIGNED_TOK = _re.compile(r"^(?:[+\-][\d.,]*\d|" + _DMS_DEV + ")$")
_GLUED_DEV = _re.compile("[\\d\u00b0'\u2032]\\s*[+\\-][\\d.,]*\\d"
                         "(?:\\s*\u00b0(?:\\s*[0-5]?\\d\\s*['\u2032])?"
                         "|\\s*['\u2032])?$")


def merge_halfstack(lines):
    """Joins aligned token, not only last."""
    used = set()
    markers = _depth_marker_idxs(lines)
    for di, Dv in enumerate(lines):
        td = _ltext(Dv).strip()
        if not _DEV_LINE.match(td):
            continue
        if _depth_owned(di, lines, markers):
            continue
        rd = _lrect(Dv)
        h = max(rd[3] - rd[1], 2.0)
        best = None
        for ai, A in enumerate(lines):
            if ai == di or ai in used:
                continue
            ra = _lrect(A)
            vgap = max(rd[1] - ra[3], ra[1] - rd[3], 0.0)
            if vgap > 1.5 * h:
                continue
            if rd[2] < ra[0] or rd[0] > ra[2] + 4 * h:
                continue
            for k, tok in enumerate(A["toks"]):
                # score by alignment, trailing `/` open
                tt = tok["t"][:-1] if tok["t"].endswith("/") else tok["t"]
                glued = _GLUED_DEV.search(tt)     # `56-0,055`
                if not glued and (not _SIGNED_TOK.match(tt) or k == 0
                                  or not _re.search("[\\d\u00b0'\u2032]$",
                                                    A["toks"][k - 1]["t"])):
                    continue
                if "/" in tt:
                    continue
                tr = tok["r"]
                tv = max(rd[1] - tr[3], tr[1] - rd[3], 0.0)
                align = min(abs(rd[0] - tr[0]), abs(rd[2] - tr[2]))
                score = tv + align
                if best is None or score < best[0]:
                    best = (score, ai, k)
        if best is not None:
            A = lines[best[1]]
            k = best[2]
            tok = A["toks"][k]
            A["toks"][k] = {"t": tok["t"].rstrip("/") + "/"
                                 + td.replace(" ", ""),
                            "r": geometry._union(tok["r"], rd)}
            used.add(di)
    return [l for i, l in enumerate(lines) if i not in used]


_TOL_OPENS = _re.compile("^(?:\u00b1\\s*\\d*[.,]?\\d+|[+\\-]\\s*\\d*[.,]?\\d+\\s*"
                        "\u00b0?\\s*/?\\s*[+\\-]\\s*\\d*[.,]?\\d+)")


def _opens_kw(t, KW):
    """Whole word, `THRUST` does not."""
    return bool(_re.match(r"(?:%s)\b" % "|".join(KW), t.strip(), _re.I))


def _hole_takes_tol_below(lines, KW):
    """Before block merge hides keyword."""
    used = set()
    for i, L in enumerate(lines):
        if i in used or not _opens_kw(_ltext(L), KW):
            continue
        rl, h = _lrect(L), max(_lheight(L), 2.0)
        for j, M in enumerate(lines):
            if j == i or j in used:
                continue
            if not _TOL_OPENS.match(_ltext(M).strip()):
                continue
            rm = _lrect(M)
            if rm[1] < rl[1] or rm[1] - rl[3] > 1.6 * h:
                continue
            if min(rl[2], rm[2]) - max(rl[0], rm[0]) <= 0:
                continue
            L["toks"].extend(M["toks"])
            used.add(j)
            break
    return [l for k, l in enumerate(lines) if k not in used]


def merge_callout_block(lines):
    KW = ("THRU", "DEEP", "CBORE", "CSINK")
    lines = _hole_takes_tol_below(lines, KW)
    for _ in range(3):
        used = set()
        moved = False
        for i, L in enumerate(lines):
            if i in used:
                continue
            tl = _ltext(L).strip()
            if not _opens_kw(tl, KW) or len(L["toks"]) > 6:
                continue
            rl = _lrect(L)
            h = max(_lheight(L), 2.0)
            best = None
            for j, M in enumerate(lines):
                if j == i or j in used:
                    continue
                tm = _ltext(M)
                if not _re.search(r"\d", tm):
                    continue
                if _opens_kw(tm, KW):
                    continue
                rm = _lrect(M)
                ov = min(rl[2], rm[2]) - max(rl[0], rm[0])
                if ov <= 0:
                    continue
                vgap = max(rm[1] - rl[3], rl[1] - rm[3], 0.0)
                if vgap > 1.6 * h:
                    continue
                frac = ov / max(min(rl[2] - rl[0], rm[2] - rm[0]), 1e-6)
                score = (-round(frac, 2), vgap)
                if best is None or score < best[0]:
                    best = (score, j)
            if best is not None:
                M = lines[best[1]]
                rm = _lrect(M)
                if rl[1] >= rm[1]:
                    M["toks"].extend(L["toks"])
                else:
                    M["toks"][0:0] = L["toks"]
                used.add(i)
                moved = True
        lines = [l for i, l in enumerate(lines) if i not in used]
        if not moved:
            break
    for L in lines:
        _fuse_devs(L)
    return lines


def _fuse_devs(line):
    toks = line["toks"]
    k = 1
    while k < len(toks) - 1:
        a, b = toks[k]["t"], toks[k + 1]["t"]
        # partner signed or true zero
        if (_DEV_LINE.match(a) and _DEV_LINE.match(b)
                and (b[:1] in "+-" or _re.match(r"^0(?:[.,]0+)?$", b))
                and a[:1] in "+-" and "/" not in a
                and _re.search("[\\d\u00b0'\u2032]$", toks[k - 1]["t"])
                and not _DEV_LINE.match(toks[k - 1]["t"])):
            toks[k] = {"t": a + "/" + b,
                       "r": geometry._union(toks[k]["r"], toks[k + 1]["r"])}
            del toks[k + 1]
        k += 1


def merge_fit(lines):
    from bubbler.reader.grammar import _fit_ok
    used = set()
    for i, L in enumerate(lines):
        if i in used:
            continue
        tl = _ltext(L).strip()
        m = _FIT_LINE.match(tl) or _FIT_DEV_LINE.match(tl)
        if not m or not _fit_ok(m.group(1).replace(" ", "")):
            continue
        # R10, M10 are own callouts
        if _RADIUS_RE.match(tl) or _re.match(r"M\s?\d", tl):
            continue
        rl = _lrect(L)
        if m.re is _FIT_DEV_LINE:
            # code rect, not band
            rl = L["toks"][0]["r"]
        h = max(rl[3] - rl[1], 2.0)
        best = None
        for j, M in enumerate(lines):
            if j == i or j in used:
                continue
            tm = _ltext(M)
            # inch mark, leading dot ok
            if not _re.search(r"(?:^|\s)\u00d8?\s*(?:\d+(?:[.,]\d+)?"
                              r"|[.,]\d+)\s*(?:\"|\u2033)?\s*$", tm):
                continue
            if _re.search(r"DEEP\s*[\d.,]+\s*$", tm):
                continue
            rm = _lrect(M)
            vgap = max(rm[1] - rl[3], rl[1] - rm[3], 0.0)
            if vgap > 1.5 * h:
                continue
            xgap = max(rm[0] - rl[2], rl[0] - rm[2], 0.0)
            if xgap > 4 * h:
                continue
            score = vgap + xgap
            if best is None or score < best[0]:
                best = (score, j)
        if best is not None:
            M = lines[best[1]]
            code = m.group(1) if m.re is _FIT_DEV_LINE else _ltext(L)
            M["toks"].append({"t": code.replace(" ", ""), "r": rl})
            used.add(i)
        elif m.re is _FIT_DEV_LINE and not _re.match(r"[CRMST]", tl, _re.I):
            used.add(i)
    return [l for i, l in enumerate(lines) if i not in used]


def _gdt_opens(t):
    from bubbler.reader.grammar import _GDT_SYMBOLS
    t = t.strip()
    return any(t.startswith(g) or t.upper().startswith(n.strip())
               for g, n in _GDT_SYMBOLS)


def merge_nx(lines):
    used = set()
    for i, L in enumerate(lines):
        if i in used or not _NX_LINE.match(_ltext(L)):
            continue
        rl = _lrect(L)
        h = max(rl[3] - rl[1], 2.0)
        best = None
        for j, M in enumerate(lines):
            if j == i or j in used:
                continue
            tm = _ltext(M)
            starts_num = bool(_re.match(r"^[.\d\u00d8]", tm)) or (
                _gdt_opens(tm))
            if not starts_num:
                continue
            rm = _lrect(M)
            # count never reaches up
            if rm[3] <= rl[1] + 0.25 * h:
                continue
            vgap = max(rm[1] - rl[3], rl[1] - rm[3], 0.0)
            if vgap > 1.5 * h:
                continue
            xgap = max(rm[0] - rl[2], rl[0] - rm[2], 0.0)
            if xgap > 4 * h:
                continue
            score = vgap + xgap
            if best is None or score < best[0]:
                best = (score, j)
        if best is not None:
            M = lines[best[1]]
            M["toks"].insert(0, {"t": _ltext(L), "r": rl})
            used.add(i)
    return [l for i, l in enumerate(lines) if i not in used]
_RADIUS_RE = _re.compile(r"^R\s?\d", _re.I)    # R12 not fit
