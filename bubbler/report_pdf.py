# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# FAI report page renderer.

import html
import io

import fitz

from .config import FAI_SHOW_COLUMNS, FAI_SHOW_FIELDS
from .reportrow import summary as _summary


LABELS = {
    "en": {
        "title": "First Article Inspection Report",
        "title_inspection": "Inspection Report",
        "report_id": "Report ID", "part_no": "Part #", "part_name": "Part name",
        "drawing": "Drawing #", "dwg_rev": "Dwg rev", "part_rev": "Part rev",
        "po": "PO #", "customer": "Customer", "material": "Material",
        "serial": "Serial / Lot", "inspector": "Inspector", "date": "Date",
        "units": "Units", "chars": "Characteristics", "measured": "Measured",
        "pass": "Pass", "fail": "Fail", "yield": "Yield",
        "disposition": "Disposition", "accepted": "ACCEPTED",
        "rejected": "REJECTED", "in_progress": "IN PROGRESS",
        "col_bubble": "Bubble", "col_feature": "Feature",
        "col_req": "Requirement", "col_meas": "Measured",
        "col_dev": "Deviation", "col_result": "Result", "col_method": "Method",
        "col_comments": "Comments", "sig_inspector": "Inspector",
        "sig_qa": "QA reviewer", "sig_name_date": "Name, date",
        "page": "Page", "of": "of",
    },
    "pl": {
        "title": "Raport kontroli pierwszej sztuki",
        "title_inspection": "Raport kontroli",
        "report_id": "Nr raportu", "part_no": "Nr czesci",
        "part_name": "Nazwa",
        "drawing": "Nr rysunku", "dwg_rev": "Rew. rys.",
        "part_rev": "Rew. czesci",
        "po": "Nr zam.", "customer": "Klient", "material": "Material",
        "serial": "Nr ser. / partia", "inspector": "Kontroler",
        "date": "Data",
        "units": "Jedn.", "chars": "Cechy", "measured": "Zmierzono",
        "pass": "OK", "fail": "NOK", "yield": "Uzysk",
        "disposition": "Decyzja", "accepted": "ZATWIERDZONO",
        "rejected": "ODRZUCONO", "in_progress": "W TOKU",
        "col_bubble": "Nr", "col_feature": "Cecha",
        "col_req": "Wymaganie", "col_meas": "Pomiar",
        "col_dev": "Odchylka", "col_result": "Wynik", "col_method": "Metoda",
        "col_comments": "Uwagi", "sig_inspector": "Kontroler",
        "sig_qa": "Kontrola jakosci", "sig_name_date": "Imie i nazwisko, data",
        "page": "Strona", "of": "z",
    },
}


def L(key, lang):
    """Bilingual label stacks two lines."""
    if lang == "en/pl":
        return "%s<br>%s" % (LABELS["en"][key], LABELS["pl"][key])
    return LABELS.get(lang, LABELS["en"])[key]


def Lt(key, lang):
    """Plain-text label with slash not linebreak."""
    return L(key, lang).replace("<br>", " / ")


OPTIONAL_FIELDS = FAI_SHOW_FIELDS
OPTIONAL_COLUMNS = FAI_SHOW_COLUMNS

# key, label, pt, classes
COLUMNS = (
    ("bubble",   "col_bubble",   26, "ctr", "ctr"),
    ("feature",  "col_feature",  86, "",    ""),
    ("req",      "col_req",      76, "",    ""),
    ("measured", "col_meas",     44, "num", "num"),
    ("dev",      "col_dev",      86, "",    "dev"),
    ("result",   "col_result",   36, "ctr", None),   # class set per row
    ("method",   "col_method",   42, "",    ""),
    ("comments", "col_comments", 52, "",    ""),
)
_BASE_TABLE = sum(c[2] for c in COLUMNS)

DISPOSITION = {"ACCEPTED": ("accepted", "acc"), "REJECTED": ("rejected", "rej"),
               "IN PROGRESS": ("in_progress", "")}

AMBER_PCT = 90              # % of half-width


def _band(row):
    """(lo, center, hi) zone or None when unbounded."""
    if row.nominal is None or not isinstance(row.measured, float):
        return None
    lo, hi = row.limits
    if lo is None or hi is None:
        return None
    return lo, (lo + hi) / 2.0, hi


def _zone_pct(row, band):
    """|measured - center| / half-width in % (100 at limit)."""
    if band is None:
        return None
    lo, c, hi = band
    half = (hi - lo) / 2.0
    return abs(row.measured - c) / half * 100.0 if half else 0.0


def _measured_text(m):
    if isinstance(m, float):
        return "%.3f" % m
    return "" if m is None else str(m)


MARGIN = 36
_W = 523.0                       # A4-tuned body width
W = _W                           # current body width


def _w(pt):
    """Scale A4-tuned width to body width minus padding."""
    return "width:%.0fpt" % (pt * W / _W)


CSS_TEMPLATE = """
body { font-family: sans-serif; font-size: 8pt; color: #000; }
h1 { font-size: 13pt; font-weight: bold; margin: 0; }
.company { font-size: 9pt; }
.rid { font-size: 7pt; color: #333; }
table { border-collapse: collapse; width: {W}pt; }
/* NOTE: Story ignores % widths on cells; use pt widths (body = 523pt). */
td, th { border: 0.4pt solid #000; padding: 2pt 3pt; vertical-align: top; }
th { font-weight: bold; text-align: left; border-bottom: 1.2pt solid #000; background: #e4e4e4; }
.title td { border: none; padding: 0; }
.hdr td { border: 0.4pt solid #000; background: #f4f4f4; }
.hdr .k { font-size: 6.5pt; color: #333; }
.sum td { text-align: center; font-weight: bold; background: #f4f4f4; }
.sum .k { font-weight: normal; font-size: 6.5pt; color: #333; }
.pass { text-align: center; background: #d6ead6; }
.fail { text-align: center; font-weight: bold; background: #f0cfcf; }
.acc { font-size: 10pt; border: 1.2pt solid #000; background: #d6ead6; }
.rej { font-size: 10pt; border: 1.2pt solid #000; background: #f0cfcf; }
.z td { background: #f4f4f4; }
.z td.pass, td.pass { background: #d6ead6; }
.z td.fail, td.fail { background: #f0cfcf; }
.num { text-align: right; }
.dev { text-align: left; }
.ctr { text-align: center; }
.sig td { border: none; padding-top: 44pt; }
.sig .line { border-top: 0.6pt solid #000; padding-top: 2pt; font-size: 7pt; color: #333; }
.spacer { height: 6pt; }
.rule { border-top: 1.2pt solid #000; height: 0; margin: 3pt 0 5pt 0; }
"""


def esc(v):
    return html.escape("" if v is None else str(v))


def _title_key(hdr):
    """First-article type earns AS9102 heading else plain report."""
    t = str(hdr.get("inspection_type") or "").strip().lower()
    return "title" if ("first article" in t or t in ("fai", "first")) \
        else "title_inspection"


def _head_html(hdr, rows, lang, full, step_uri=None):
    h = ["<style>%s</style>" % CSS_TEMPLATE.replace("{W}", str(W))]
    h.append(
        "<table class='title' style='%s'><tr><td style='%s'>"
        "<span class='company'>%s</span><br>"
        "<h1>%s</h1></td>"
        "<td style='text-align:right;%s'><span class='rid'>"
        "%s</span><br><b>%s</b><br>%s</td></tr></table>"
        "<div class='rule'></div>"
        % (_w(510), _w(320), esc(hdr.get("company")).upper(),
           L(_title_key(hdr), lang).upper(), _w(170),
           L("report_id", lang).upper(),
           esc(hdr.get("report_id")), esc(hdr.get("date"))))
    if full and step_uri:
        h.append("<div style='text-align:center;margin:4pt 0;'>"
                 "<img src='%s' style='height:150pt;'></div>"
                 "<div class='rule'></div>" % step_uri)
    opts = hdr.get("show", {})
    if not full:
        bits = ["%s %s" % (Lt("part_no", lang), esc(hdr.get("part_no")))]
        for key in ("part_rev", "serial"):
            if opts.get(key, True):
                bits.append("%s %s" % (Lt(key, lang), esc(hdr.get(key, ""))))
        h.append("<div class='rid'>%s</div><div class='spacer'></div>"
                 % " &middot; ".join(bits))
        return "".join(h)

    s = _summary(rows)
    yld = "%.1f %%" % (s["yield"] * 100.0) if s["yield"] is not None else "\u2014"
    dkey, dcls = DISPOSITION.get(s["disposition"], ("in_progress", ""))

    # fixed then optional, 3 per row
    fields = [("part_no", hdr.get("part_no", ""))]
    for key in OPTIONAL_FIELDS:
        if opts.get(key, True):
            fields.append((key, hdr.get(key, "")))
    fields += [("inspector", hdr.get("inspector", "")),
               ("date", hdr.get("date", ""))]
    cells = ["<td style='%s'><span class='k'>%s</span><br>%s</td>"
             % (_w(165), L(k, lang).upper(), esc(v)) for k, v in fields]
    while len(cells) % 3:
        cells.append("<td style='%s'></td>" % _w(165))
    trs = "".join("<tr>%s</tr>" % "".join(cells[i:i + 3])
                  for i in range(0, len(cells), 3))
    h.append("<table class='hdr'>%s</table><div class='spacer'></div>" % trs)
    h.append(
        "<table class='sum'><tr>"
        "<td class='k' style='%s'>%s</td><td class='k' style='%s'>%s</td>"
        "<td class='k' style='%s'>%s</td><td class='k' style='%s'>%s</td>"
        "<td class='k' style='%s'>%s</td><td class='k' style='%s'>%s</td></tr>"
        "<tr><td>%d</td><td>%d</td><td>%d</td><td>%d</td>"
        "<td>%s</td><td class='%s'>%s</td></tr></table>"
        "<div class='spacer'></div>"
        % (_w(74), L("chars", lang).upper(), _w(74), L("measured", lang).upper(),
           _w(64), L("pass", lang).upper(), _w(64), L("fail", lang).upper(),
           _w(80), L("yield", lang).upper(), _w(117),
           L("disposition", lang).upper(),
           s["chars"], s["measured"], s["passed"], s["failed"],
           yld, dcls, L(dkey, lang)))
    return "".join(h)


def _columns(show):
    cols = [c for c in COLUMNS
            if c[0] not in OPTIONAL_COLUMNS or show.get(c[0], True)]
    widths = {c[0]: c[2] for c in cols}
    if not show.get("dev_bar", True):
        widths["dev"] = 44          # number only
    f = _BASE_TABLE / sum(widths.values())
    return [(k, lk, widths[k] * f, hc, cc) for k, lk, _, hc, cc in cols]


def _table_html(rows, lang, show=None):
    show = show or {}
    cols = _columns(show)
    h = ["<table><thead><tr>"]
    for k, lk, w, hc, _ in cols:
        h.append("<th class='%s' style='%s'>%s</th>"
                 % (hc, _w(w), L(lk, lang).upper()))
    h.append("</tr></thead><tbody>")
    for i, r in enumerate(rows):
        res = r.result
        dev = r.deviation
        vals = {
            "bubble": esc(r.bubble),
            "feature": esc(r.feature),
            "req": esc(r.requirement),
            "measured": _measured_text(r.measured),
            "dev": "%+.3f" % dev if dev is not None else "",
            "result": esc(_result_text(res, lang)),
            "method": esc(r.method),
            "comments": esc(r.comment),
        }
        h.append("<tr%s>" % (" class=z" if i % 2 else ""))
        for k, _, _, _, cc in cols:
            if k == "result":
                cc = {"PASS": "pass", "FAIL": "fail"}.get(res, "ctr")
            attr = (" id='dev%d'" % i
                    if k == "dev" and show.get("dev_bar", True) else "")
            h.append("<td class='%s'%s>%s</td>" % (cc, attr, vals[k]))
        h.append("</tr>")
    h.append("</tbody></table>")
    return "".join(h)


def _result_text(res, lang):
    if res not in ("PASS", "FAIL"):
        return res
    key = "pass" if res == "PASS" else "fail"
    if lang == "en/pl":
        return "%s / %s" % (LABELS["en"][key].upper(), LABELS["pl"][key])
    return LABELS.get(lang, LABELS["en"])[key].upper()


def _sig_line(role_key, lang, name="", date=""):
    name, date = esc(name).strip(), esc(date).strip()
    tail = ("%s&nbsp;&nbsp;&nbsp;&nbsp;%s" % (name, date)).strip() \
        if (name or date) else Lt("sig_name_date", lang)
    return "<div class='line'>%s: %s</div>" % (Lt(role_key, lang), tail)


def _sig_html(lang, qa=True, inspector="", date=""):
    insp = ("<td style='%s'>%s</td>"
            % (_w(229), _sig_line("sig_inspector", lang, inspector, date)))
    if not qa:
        return ("<table class='sig'><tr>%s<td style='%s'></td></tr></table>"
                % (insp, _w(276)))
    return (
        "<table class='sig'><tr>%s<td style='%s'></td>"
        "<td style='%s'>%s</td></tr></table>"
        % (insp, _w(47), _w(229), _sig_line("sig_qa", lang)))


ROWS_MAX = 60  # max tried per page


def _fits(html_, body):
    more, _ = fitz.Story(html=html_).place(body)
    return not more


def _max_rows_fitting(head, rows, lang, body, tail="", show=None):
    lo, hi = 1, min(ROWS_MAX, len(rows))
    if not rows:
        return 0
    if not _fits(head + _table_html(rows[:lo], lang, show) + tail, body):
        return 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _fits(head + _table_html(rows[:mid], lang, show) + tail, body):
            lo = mid
        else:
            hi = mid - 1
    return lo


def append_report_pages(doc, hdr, rows, lang="en", logo=None, paper="a4",
                        amber_pct=AMBER_PCT, step_img=None):
    global W
    rows = list(rows or [])
    if not rows:
        return 0
    rect = fitz.paper_rect(paper)              # "a4" or "letter"
    if rect.width < 100 or rect.height < 100:
        rect = fitz.paper_rect("a4")
    margin = MARGIN
    body = rect + (margin, margin + 8, -margin, -margin - 18)  # footer room
    W = body.width - 10                        # table width
    show = hdr.get("show", {})
    sig = _sig_html(lang, qa=show.get("qa_signature", False),
                    inspector=hdr.get("inspector", ""),
                    date=hdr.get("date", ""))
    step_uri = None
    if step_img:
        import base64
        step_uri = ("data:image/png;base64,"
                    + base64.b64encode(step_img).decode("ascii"))
    pages_html = []
    page_slices = []
    i, first = 0, True
    while True:
        head = _head_html(hdr, rows, lang, full=first, step_uri=step_uri)
        rest = rows[i:]
        k_sig = _max_rows_fitting(head, rest, lang, body, tail=sig, show=show)
        if k_sig >= len(rest):
            pages_html.append(head + _table_html(rest, lang, show) + sig)
            page_slices.append(rest)
            break
        k = _max_rows_fitting(head, rest, lang, body, show=show)
        if k >= len(rest):
            pages_html.append(head + _table_html(rest, lang, show))
            page_slices.append(rest)
            pages_html.append(_head_html(hdr, rows, lang, full=False) + sig)
            page_slices.append([])                  # sign-off-only page
            break
        if k == 0:
            raise RuntimeError("a single row does not fit on a report page")
        pages_html.append(head + _table_html(rest[:k], lang, show))
        page_slices.append(rest[:k])
        i += k
        first = False

    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    bars = []                                   # (pno, row idx, rect)
    def _collector(pno):
        # one-arg callback closes pno
        def _collect(pos):
            if pos.id and pos.id.startswith("dev"):
                bars.append((pno, int(pos.id[3:]), fitz.Rect(pos.rect)))
        return _collect

    for pno, html_ in enumerate(pages_html):
        story = fitz.Story(html=html_)
        dev = writer.begin_page(rect)
        more, _ = story.place(body)
        story.element_positions(_collector(pno))
        story.draw(dev)
        writer.end_page()
    writer.close()

    # build in throwaway doc
    rep = fitz.open("pdf", buf.getvalue())
    added = rep.page_count
    for pno, ridx, cell in bars:
        slc = page_slices[pno]
        if ridx < len(slc):
            _draw_tol_bar(rep[pno], cell, slc[ridx], amber_pct)
    for i in range(added):
        page = rep[i]
        if logo:
            try:
                page.insert_image(
                    fitz.Rect(rect.width - margin - 60, margin - 4,
                              rect.width - margin, margin + 26), stream=logo)
            except Exception:            # bad logo not report
                pass
        prt = hdr.get("show", {}).get("part_rev", True)
        txt = ("%s    %s    %s%s    %s %d / %d"
               % (hdr.get("form_id", ""), esc(hdr.get("report_id")),
                  esc(hdr.get("part_no")),
                  (" rev " + str(hdr.get("part_rev", ""))) if prt else "",
                  Lt("page", lang), i + 1, added))
        page.draw_line((margin, rect.height - margin - 2),
                       (rect.width - margin, rect.height - margin - 2),
                       color=(0, 0, 0), width=0.4)
        page.insert_text((margin, rect.height - margin + 6), txt,
                         fontsize=7, color=(0.35, 0.35, 0.35), fontname="helv")
    doc.insert_pdf(rep)                   # atomic unchanged until here
    rep.close()
    return added


IMG_PER_PAGE = ("auto", "1", "2", "4")
_CAPTION_H = 12.0                 # pt under each image
_GAP = 10.0                       # pt between images


def _used_bottom(page, margin):
    y = margin
    try:
        for b in page.get_text("blocks"):
            if b[3] < page.rect.height - margin - 20:
                y = max(y, b[3])
        for d in page.get_drawings():
            r = d.get("rect")
            if r is not None and r.y1 < page.rect.height - margin - 20:
                y = max(y, r.y1)
    except Exception:
        return page.rect.height                 # unknown: treat as full
    return y


def _img_size(stream):
    try:
        pm = fitz.Pixmap(stream)
        return float(pm.width), float(pm.height)
    except Exception:
        return None


def _place(page, box, stream, caption):
    wh = _img_size(stream)
    if not wh or wh[0] <= 0 or wh[1] <= 0:
        return False
    iw, ih = wh
    room_h = box.height - (_CAPTION_H if caption else 0)
    s = min(box.width / iw, room_h / ih)
    w, h = iw * s, ih * s
    x0 = box.x0 + (box.width - w) / 2.0
    r = fitz.Rect(x0, box.y0, x0 + w, box.y0 + h)
    try:
        page.insert_image(r, stream=stream)
    except Exception:
        return False
    if caption:
        page.insert_textbox(fitz.Rect(box.x0, r.y1 + 1, box.x1,
                                      r.y1 + _CAPTION_H + 1),
                            caption, fontsize=7, fontname="helv", align=1,
                            color=(0.25, 0.25, 0.25))
    return True


def append_images(doc, images, width_pct=100, per_page="auto", paper="a4",
                  first_page=None, margin=None):
    """Report's last page fills first. Returns images drawn."""
    margin = MARGIN if margin is None else margin
    rect = fitz.paper_rect(paper)
    if rect.width < 100 or rect.height < 100:
        rect = fitz.paper_rect("a4")
    width = rect.width - 2 * margin
    bottom = rect.height - margin - 22           # footer room
    todo = [(b, c) for b, c in (images or []) if b]
    drawn = 0

    def new_page():
        return doc.new_page(width=rect.width, height=rect.height)

    if per_page in ("1", "2", "4"):
        n = int(per_page)
        cols = 2 if n == 4 else 1
        rows = n // cols
        cw = (width - _GAP * (cols - 1)) / cols
        ch = (bottom - margin - _GAP * (rows - 1)) / rows
        # report page's free rows first
        cells = []
        if first_page is not None:
            y0 = _used_bottom(first_page, margin) + _GAP
            while y0 + ch <= bottom + 0.5:
                for c_ in range(cols):
                    x = margin + c_ * (cw + _GAP)
                    cells.append((first_page, fitz.Rect(x, y0, x + cw,
                                                        y0 + ch)))
                y0 += ch + _GAP
        for b, c in todo:
            if not cells:
                page = new_page()
                for i in range(n):
                    x = margin + (i % cols) * (cw + _GAP)
                    y = margin + (i // cols) * (ch + _GAP)
                    cells.append((page, fitz.Rect(x, y, x + cw, y + ch)))
            pg, box = cells.pop(0)
            drawn += _place(pg, box, b, c)
        return drawn

    target = width * max(10, min(100, int(width_pct or 100))) / 100.0
    per_row = max(1, int((width + 0.5) // target))
    target = min(target, (width - _GAP * (per_row - 1)) / per_row)
    page, y = None, None
    if first_page is not None:
        page, y = first_page, _used_bottom(first_page, margin) + _GAP
    row = []                                     # [(bytes, caption, h)]

    def flush():
        nonlocal page, y
        if not row:
            return 0
        h = max(r[2] for r in row)
        if page is None or y + h > bottom:
            if page is not None and page is first_page \
                    and bottom - y >= 0.5 * h:
                h = bottom - y
            else:
                page, y = new_page(), margin
        span = len(row) * target + (len(row) - 1) * _GAP
        x = margin + (width - span) / 2.0
        n = 0
        for b, c, _h in row:
            n += _place(page, fitz.Rect(x, y, x + target, y + h), b, c)
            x += target + _GAP
        y += h + _GAP
        del row[:]
        return n
    for b, c in todo:
        wh = _img_size(b)
        if not wh:
            continue
        h = min(target * wh[1] / wh[0] + (_CAPTION_H if c else 0),
                bottom - margin)
        row.append((b, c, h))
        if len(row) >= per_row:
            drawn += flush()
    drawn += flush()
    return drawn


def stamp_footer(page, hdr, label, margin=None):
    """No packet page goes out unnamed."""
    margin = MARGIN if margin is None else margin
    r = page.rect
    txt = "%s    %s    %s    %s" % (hdr.get("form_id", ""),
                                    esc(hdr.get("report_id")),
                                    esc(hdr.get("part_no")), label)
    page.draw_line((margin, r.height - margin - 2),
                   (r.width - margin, r.height - margin - 2),
                   color=(0, 0, 0), width=0.4)
    page.insert_text((margin, r.height - margin + 6), txt, fontsize=7,
                     color=(0.35, 0.35, 0.35), fontname="helv")


BAR_GREEN = (0.15, 0.45, 0.15)
BAR_AMBER = (0.75, 0.55, 0.05)
BAR_RED = (0.70, 0.10, 0.10)
BAR_GREY = (0.55, 0.55, 0.55)


def _bar_color(pct, amber_pct=AMBER_PCT, failed=None):
    if failed:
        return BAR_RED
    if failed is None and pct > 100:
        return BAR_RED
    if amber_pct and 0 < amber_pct < 100 and pct > amber_pct:
        return BAR_AMBER
    return BAR_GREEN


def _draw_tol_bar(page, cell, r, amber_pct=AMBER_PCT):
    band = _band(r)
    pct = _zone_pct(r, band)
    if band is None or pct is None:
        return
    lo, c, hi = band
    span = hi - lo
    over = 0.25 * span if span else 1.0
    x0 = cell.x0 + 34 * W / _W   # room for number
    x1 = cell.x1 - 3
    y = cell.y0 + 6.5            # align first text line
    w = x1 - x0

    def X(v):
        v = max(lo - over, min(hi + over, v))
        return x0 + (v - (lo - over)) / (span + 2 * over) * w

    sh = page.new_shape()
    sh.draw_line((x0, y), (x1, y))
    sh.finish(color=BAR_GREY, width=0.5)
    sh.draw_rect(fitz.Rect(X(lo), y - 3, X(hi), y + 3))
    sh.finish(color=None, fill=(0.90, 0.90, 0.90))
    for v, hh in ((lo, 4), (c, 5), (hi, 4)):
        sh.draw_line((X(v), y - hh), (X(v), y + hh))
    sh.finish(color=(0.25, 0.25, 0.25), width=0.6)
    col = _bar_color(pct, amber_pct, failed=(r.result == "FAIL"))
    mx = X(r.measured)
    sh.draw_polyline([(mx, y - 4), (mx + 3.2, y), (mx, y + 4),
                      (mx - 3.2, y), (mx, y - 4)])
    sh.finish(color=col, fill=col, width=0.5, closePath=True)
    sh.commit()
