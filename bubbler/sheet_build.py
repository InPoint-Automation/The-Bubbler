# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Inspection workbook built in code.

from collections import namedtuple

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.packaging.custom import IntProperty
from openpyxl.styles import Alignment, Border, Color, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.utils import get_column_letter

from .common import (SHEET, FIRST_ROW, LAST_ROW, GO_WORDS, METHODS,
                     NOGO_WORDS, ROUND_DP, TIERS, TYPES)
from .i18n import sheet_label, sheet_value

NAVY = "FF1F3864"
GREEN_BAND = "FF548235"
CREAM = "FFFFF2CC"
PEACH = "FFFCE4D6"
GREY = "FFEAEAEA"
PALE_GREEN = "FFE2EFDA"
PASS_FILL = "FFC6EFCE"
FAIL_FILL = "FFFFC7CE"
GRID = "FFBFBFBF"

SHEET_GEN = 3
GEN_PROP = "BubblerSheetGen"

TITLE_ROW = 1
BANNER_CELL = "A1"
LABEL_ROWS = (3, 4, 5, 6, 7)
SUMMARY_ROW = 8
HEAD_ROW = 10

Col = namedtuple("Col",
                 "key header width numfmt fill band flag formula hidden")


def _c(key, header, width, numfmt, fill, band="navy", flag=None,
       formula=False, hidden=False):
    return Col(key, header, width, numfmt, fill, band, flag, formula, hidden)


COLUMN_MODEL = (
    _c("bubble",   "bubble#",  9.0,        "@",       CREAM),
    _c("feature",  "feature",  26.0,       "General", CREAM),   # ~31 char string
    _c("requirement", "requirement", 22.0, "General", CREAM),   # exact precision
    _c("measured", "measured", 13.5,       "General", CREAM),
    _c("deviation", "deviation", 12.0,     "num",     GREY, formula=True),
    _c("result",   "result",   12.0,       "General", GREY, formula=True),
    _c("type",     "type",     17.0,       "General", CREAM,    # widest 20 chars
       flag="sheet_type_column"),
    _c("method",   "method",   13.0,       "General", CREAM,
       flag="sheet_method_column"),
    _c("tier",     "tier",     17.0,       "General", CREAM,    # widest 16 chars
       flag="sheet_tier_column"),
    _c("gage",     "gage",     16.0,       "General", CREAM,    # fits gage name
       flag="sheet_gage_column"),
    _c("refzone",  "ref / zone", 11.28125, "General", PALE_GREEN, band="green",
       flag="sheet_refzone_column"),
    _c("designator", "designator", 10.00390625, "General", PALE_GREEN,
       band="green", flag="sheet_tier_designator"),
    _c("ncr",      "NCR #",    11.0,       "General", PALE_GREEN, band="green",
       flag="sheet_ncr_column"),                                # > 5-char head
    _c("comments", "comments", 18.0,       "General", PALE_GREEN, band="green"),
)

REQ_HELPERS = ("_nom", "_tol", "_up", "_dn", "_lo", "_hi")
_TITLE_BLOCK_LASTCOL = 10        # reaches column J


def helper_columns(cfg=None):
    """(letter, key) per parse helper past visible columns and title block."""
    n = len(active_columns(cfg))
    start = max(n + 1, _TITLE_BLOCK_LASTCOL + 1)
    return tuple((get_column_letter(start + i), key)
                 for i, key in enumerate(REQ_HELPERS))


def full_letter_of(cfg=None):
    out = {col.key: letter for letter, col in active_columns(cfg)}
    out.update({key: letter for letter, key in helper_columns(cfg)})
    return out


def active_columns(cfg=None):
    cfg = cfg or {}
    out = []
    for col in COLUMN_MODEL:
        if col.flag and not cfg.get(col.flag):
            continue
        out.append((get_column_letter(len(out) + 1), col))
    return tuple(out)


HEAD_CHARS_PER_UNIT = 1.3
DATA_CHARS_PER_UNIT = 1.2

# "num" follows cfg["units"]
NUM_FMTS = {"iso_mm": "0.00", "asme_inch": "0.0000"}
UNIT_TEXT = {"iso_mm": "mm", "asme_inch": "in"}

TITLE_LABELS = (
    ("A3", "Part #"), ("D3", "Part Name"), ("G3", "Report #"),
    ("I3", "Report #"),                  # minted not typed
    ("A4", "Drawing #"), ("D4", "Dwg Rev"), ("G4", "Part Rev"),
    ("A5", "PO #"), ("D5", "Material"), ("G5", "Serial/Lot"),
    ("A6", "Inspector"), ("D6", "Date"), ("G6", "Inspection type"), ("I6", "Stage"),
    ("A7", "Customer"), ("D7", "Units (mm/in)"),
    ("G7", "Approved by"), ("I7", "Approval Date"),
)
TITLE_VALUE_CELLS = ("B3", "E3", "H3", "J3", "B4", "E4", "H4",
                     "B5", "E5", "H5", "B6", "E6", "H6", "J6",
                     "B7", "E7", "H7", "J7")
UNITS_CELL = "E7"                       # from cfg not typed
REPORT_CELL = "J3"                      # stamped not typed
APP_OWNED_VALUES = (REPORT_CELL, UNITS_CELL)


def value_cell(label_cell):
    return chr(ord(label_cell[0]) + 1) + label_cell[1:]


def header_fields():
    return tuple((value_cell(cell), key) for cell, key in TITLE_LABELS
                 if value_cell(cell) not in APP_OWNED_VALUES)

BUBBLE_COL = "A"
REQUIREMENT_COL = "C"
MEASURED_COL = "D"
DEVIATION_COL = "E"
RESULT_COL = "F"
# GEN 1 type-dropdown column
TYPE_COL = "B"

# built columns SheetWriter skips
FORMULA_COLS = (DEVIATION_COL, RESULT_COL)


SUMMARY_LABELS = (("A8", "Chars:"), ("C8", "Pass:"), ("E8", "Fail:"),
                  ("G8", "Yield:"), ("I8", "Disposition:"))
SUMMARY_FORMATS = {"H8": "0.0%"}
YIELD_FORMULA = '=IF(D8+F8>0,D8/(D8+F8),"")'


def disposition_formula(lang="en"):
    """J8 verdict, reportrow.summary rule in Excel."""
    from .reportrow import ACCEPTED, REJECTED, IN_PROGRESS
    w = [sheet_value(e, lang) for e in (REJECTED, ACCEPTED, IN_PROGRESS)]
    return '=IF(F8>0,"%s",IF(AND(B8>0,D8=B8),"%s","%s"))' % tuple(w)


def summary_formulas(letter_of, lang="en"):
    """Row-8 counters over inspectable rows only."""
    a, b = FIRST_ROW, LAST_ROW
    A = letter_of["bubble"]
    C = letter_of["requirement"]
    F = letter_of["result"]
    LO, HI = letter_of["_lo"], letter_of["_hi"]
    fres = "%s%d:%s%d" % (F, a, F, b)
    chars = ('=SUMPRODUCT((%s%d:%s%d<>"")*('
             '((%s%d:%s%d<>"")+(%s%d:%s%d<>"")+(%s%d:%s%d="GO/NOGO")'
             '+(%s<>""))>0))'
             % (A, a, A, b, LO, a, LO, b, HI, a, HI, b, C, a, C, b, fres))
    return (("B8", chars),
            ("D8", '=COUNTIF(%s,"PASS")' % fres),
            ("F8", '=COUNTIF(%s,"FAIL")' % fres),
            ("H8", YIELD_FORMULA),
            ("J8", disposition_formula(lang)))

def chars_formulas_before(chars):
    """Old B8 spellings a patch may replace."""
    i = chars.rindex('+(')
    return (chars[:i] + chars[chars.index(')>0))', i):],)

DESIGNATORS = ("MAJOR", "MINOR", "KEY", "CRITICAL")


TIER_DESIGNATOR = {"red": "CRITICAL", "blue": "MAJOR", "green": "MINOR"}
OWNED_DESIGNATORS = frozenset(TIER_DESIGNATOR.values())

ROW_H_TITLE = 16.5
ROW_H = 15.0
ROW_H_STACKED = 27.0


# wrap_text renders "\n"
STACKED = Alignment(horizontal="left", vertical="center", wrap_text=True)
HEAD_STACKED = Alignment(horizontal="center", vertical="center",
                         wrap_text=True)


def row_height(lang, base=None):
    return ROW_H_STACKED if lang == "both" else (base or ROW_H)


def _ge(limit):
    """measured >= limit on rounded difference"""
    return "ROUND(H{r}-(%s),%d)>=0" % (limit, ROUND_DP)


def _le(limit):
    """measured <= limit on rounded difference"""
    return "ROUND((%s)-H{r},%d)>=0" % (limit, ROUND_DP)


def _words(words):
    return "OR(%s)" % ",".join('UPPER(H{r})="%s"' % w for w in words)


def _words_tail():
    return ('IF(' + _words(GO_WORDS) + ',"PASS",'
            'IF(' + _words(NOGO_WORDS) + ',"FAIL",""))')


def result_formula(r, limit=None):
    """PASS/FAIL from measured (H) vs tolerance band centred on nominal (D)."""
    if limit == "max":                   # upper limit lower open
        chk = _le('D{r}+IF(F{r}<>"",F{r},0)')
        gate = 'IF(D{r}="","",'
    elif limit == "min":                 # lower limit upper open
        chk = _ge('D{r}+IF(G{r}<>"",G{r},0)')
        gate = 'IF(D{r}="","",'
    else:
        lo = ('IF(E{r}<>"",' + _ge('D{r}-ABS(E{r})') + ','
              'IF(AND(F{r}<>"",G{r}<>""),' + _ge('D{r}+MIN(F{r},G{r})') + ','
              'IF(G{r}<>"",' + _ge('D{r}+G{r}') + ',' + _ge('D{r}') + ')))')
        hi = ('IF(E{r}<>"",' + _le('D{r}+ABS(E{r})') + ','
              'IF(AND(F{r}<>"",G{r}<>""),' + _le('D{r}+MAX(F{r},G{r})') + ','
              'IF(F{r}<>"",' + _le('D{r}+F{r}') + ',' + _le('D{r}') + ')))')
        chk = 'AND(' + lo + ',' + hi + ')'
        gate = 'IF(OR(D{r}="",AND(E{r}="",F{r}="",G{r}="")),"",'
    return (
        '=IF(OR(A{r}="",H{r}=""),"",IF(ISNUMBER(H{r}),'
        + gate
        + 'IF(' + chk + ',"PASS","FAIL")),'
        + _words_tail() + '))'
    ).format(r=r)


_SEP = 'MID(1/2,2,1)'          # local decimal separator
_PM = u'±'


def _startpos(req):
    """1-based index where nominal begins past prefix."""
    def is_num_start(p):
        c = 'MID(%s,%d,1)' % (req, p)
        return ('OR(IFERROR(VALUE(%s)>=0,FALSE),%s="-",%s=".")'
                % (c, c, c))
    return 'IF(%s,1,IF(%s,2,3))' % (is_num_start(1), is_num_start(2))


def _spacepos(req):
    return 'IFERROR(FIND(" ",%s,%s),LEN(%s)+1)' % (req, _startpos(req), req)


def _numval(texpr):
    """VALUE of period-decimal number text locale-independently."""
    return 'VALUE(SUBSTITUTE(%s,".",%s))' % (texpr, _SEP)


def _signed(tok):
    return ('(IF(LEFT(%s,1)="+",1,-1))*%s'
            % (tok, _numval('TRIM(MID(%s,2,99))' % tok)))


def req_nom_formula(req):
    """Nominal parsed from requirement string. Blank for GO/NOGO."""
    st, sp = _startpos(req), _spacepos(req)
    txt = 'MID(%s,%s,(%s)-(%s))' % (req, st, sp, st)
    return '=IF(EXACT(TRIM(%s),"GO/NOGO"),"",IFERROR(%s,""))' % (req,
                                                                 _numval(txt))


def req_tol_formula(req):
    """Tolerance part of string ""/±t/+a/-b/MAX/MIN."""
    return ('=IF(EXACT(TRIM(%s),"GO/NOGO"),"",TRIM(MID(%s,(%s)+1,99)))'
            % (req, req, _spacepos(req)))


def req_up_formula(tol):
    """Upper offset token of +/- form before slash else whole."""
    sl = 'IFERROR(FIND("/",%s),0)' % tol
    return '=IF(%s=0,%s,TRIM(LEFT(%s,FIND("/",%s)-1)))' % (sl, tol, tol, tol)


def req_dn_formula(tol):
    """Lower offset token of +/- form. "" means lower side at nominal."""
    sl = 'IFERROR(FIND("/",%s),0)' % tol
    return ('=IF(%s=0,IF(LEFT(%s,1)="+","",%s),TRIM(MID(%s,FIND("/",%s)+1,99)))'
            % (sl, tol, tol, tol, tol))


def req_lo_formula(nom, tol, dn):
    """Lower acceptance limit. "" when lower side open (MAX)."""
    pm = 'IF(%s="",%s,%s+%s)' % (dn, nom, nom, _signed(dn))
    mag = _numval('TRIM(MID(%s,2,99))' % tol)
    return ('=IF(%s="","",IF(%s="","",IF(UPPER(%s)="MAX","",'
            'IF(UPPER(%s)="MIN",%s,IF(LEFT(%s,1)="%s",%s-%s,%s)))))'
            % (nom, tol, tol, tol, nom, tol, _PM, nom, mag, pm))


def req_hi_formula(nom, tol, up):
    """Upper limit, blank when open (MIN)."""
    two = 'IFERROR(FIND("/",%s),0)>0' % tol
    pm = ('IF(OR(LEFT(%s,1)="+",AND(%s,LEFT(%s,1)="-")),%s+%s,%s)'
          % (up, two, up, nom, _signed(up), nom))
    return _hi_wrap(nom, tol, pm)


def req_hi_formula_v1(nom, tol, up):
    """Old upper-limit formula, recognised for upgrade."""
    pm = 'IF(LEFT(%s,1)="+",%s+%s,%s)' % (up, nom, _signed(up), nom)
    return _hi_wrap(nom, tol, pm)


def _hi_wrap(nom, tol, pm):
    mag = _numval('TRIM(MID(%s,2,99))' % tol)
    return ('=IF(%s="","",IF(%s="","",IF(UPPER(%s)="MIN","",'
            'IF(UPPER(%s)="MAX",%s,IF(LEFT(%s,1)="%s",%s+%s,%s)))))'
            % (nom, tol, tol, tol, nom, tol, _PM, nom, mag, pm))


def req_deviation_formula(meas, nom):
    """measured - nominal. Blank for attribute or non-numeric reading."""
    return '=IF(OR(%s="",NOT(ISNUMBER(%s))),"",%s-%s)' % (nom, meas, meas, nom)


def req_result_formula(bubble, meas, lo, hi):
    """PASS/FAIL from parsed limits. Open side not checked."""
    ge = 'ROUND(%s-%s,%d)>=0' % (meas, lo, ROUND_DP)
    le = 'ROUND(%s-%s,%d)>=0' % (hi, meas, ROUND_DP)
    lo_ok = 'IF(%s="",TRUE,%s)' % (lo, ge)
    hi_ok = 'IF(%s="",TRUE,%s)' % (hi, le)
    words = ('IF(OR(%s),"PASS",IF(OR(%s),"FAIL",""))'
             % (','.join('UPPER(%s)="%s"' % (meas, w) for w in GO_WORDS),
                ','.join('UPPER(%s)="%s"' % (meas, w) for w in NOGO_WORDS)))
    return ('=IF(OR(%s="",%s=""),"",IF(NOT(ISNUMBER(%s)),%s,'
            'IF(AND(%s="",%s=""),"",IF(AND(%s,%s),"PASS","FAIL"))))'
            % (bubble, meas, meas, words, lo, hi, lo_ok, hi_ok))


def fits_header(width, longest):
    return width * HEAD_CHARS_PER_UNIT >= longest


def fits_value(width, longest):
    return width * DATA_CHARS_PER_UNIT >= longest


def number_formats(units, cfg=None):
    fmt = NUM_FMTS.get(units or "iso_mm", NUM_FMTS["iso_mm"])
    return {letter: (fmt if col.numfmt == "num" else col.numfmt)
            for letter, col in active_columns(cfg)}


def _list_formula(values):
    return '"%s"' % ",".join(values)


def type_choices(sheet_lang):
    return [sheet_value(t, sheet_lang) for t in TYPES]


def tier_choices(sheet_lang):
    return [sheet_value(t, sheet_lang) for t in TIERS if t]


def stamp_generation(wb, gen=SHEET_GEN):
    props = wb.custom_doc_props
    try:
        old = props[GEN_PROP]
    except KeyError:
        old = None
    if old is not None:
        props.props.remove(old)
    props.append(IntProperty(name=GEN_PROP, value=int(gen)))


def generation_of(wb):
    """Workbook generation or None when unstamped."""
    try:
        return int(wb.custom_doc_props[GEN_PROP].value)
    except (KeyError, TypeError, ValueError):
        return None


def _thin():
    s = Side(style="thin", color=GRID)
    return Border(left=s, right=s, top=s, bottom=s)


def build_workbook(sheet_lang="both", company="", units="iso_mm",
                   inspections=(), cfg=None):
    lang = sheet_lang or "both"
    cols = active_columns(cfg)
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET

    grid = _thin()
    mid = Alignment(horizontal="center", vertical="center")
    label_font = Font(name="Arial", size=10, bold=True)
    data_font = Font(name="Arial", size=10)
    head_font = Font(name="Arial", size=9, bold=True, color=Color(indexed=65))

    helpers = helper_columns(cfg)
    letter_of = full_letter_of(cfg)
    _title(ws, lang, company, mid, cols)
    _titleblock(ws, lang, units, label_font, grid)
    _summary(ws, lang, label_font, letter_of)
    _headrow(ws, lang, head_font, mid, grid, cols)
    _datarows(ws, data_font, mid, grid, number_formats(units, cfg), cols,
              helpers, letter_of)
    _layout(ws, cols)
    apply_print_setup(ws, cols=cols)
    _validations(ws, lang, inspections, cols)
    _rules(ws)
    stamp_generation(wb)
    return wb


def banner_text(company, lang):
    """Row 1 text. One builder so re-render can undo it."""
    title = sheet_value("Inspection Sheet", lang)
    return "%s - %s" % (company, title) if company else title


def label_cells(cfg=None):
    return (tuple(TITLE_LABELS) + tuple(SUMMARY_LABELS)
            + tuple(("%s%d" % (letter, HEAD_ROW), col.header)
                    for letter, col in active_columns(cfg)))


def _title(ws, lang, company, mid, cols):
    ws[BANNER_CELL] = banner_text(company, lang)
    ws[BANNER_CELL].font = Font(name="Arial", size=14, bold=True, color=NAVY)
    ws[BANNER_CELL].alignment = Alignment(horizontal="left",
                                          vertical="center")
    ws.merge_cells("A1:%s1" % _last_visible(cols))
    ws.row_dimensions[TITLE_ROW].height = ROW_H_TITLE


def _titleblock(ws, lang, units, label_font, grid):
    for cell, key in TITLE_LABELS:
        ws[cell] = sheet_label(key, lang)
        ws[cell].font = label_font
        ws[cell].alignment = STACKED
    for cell in TITLE_VALUE_CELLS:
        ws[cell].fill = PatternFill("solid", fgColor=CREAM)
        ws[cell].border = grid
    ws[UNITS_CELL] = UNIT_TEXT.get(units or "iso_mm", UNIT_TEXT["iso_mm"])
    for r in LABEL_ROWS:
        ws.row_dimensions[r].height = row_height(lang)


def _summary(ws, lang, label_font, letter_of):
    formulas = summary_formulas(letter_of, lang)
    for cell, key in SUMMARY_LABELS:
        ws[cell] = sheet_label(key, lang)
        ws[cell].alignment = STACKED
    for cell, f in formulas:
        ws[cell] = f
        if cell in SUMMARY_FORMATS:
            ws[cell].number_format = SUMMARY_FORMATS[cell]
    for cell, _ in list(SUMMARY_LABELS) + list(formulas):
        ws[cell].font = label_font
    ws.row_dimensions[SUMMARY_ROW].height = row_height(lang)


def _last_visible(cols):
    vis = [letter for letter, col in cols if not col.hidden]
    return vis[-1] if vis else cols[-1][0]


def _headrow(ws, lang, head_font, mid, grid, cols):
    for letter, col in cols:
        if col.hidden:
            continue
        c = ws["%s%d" % (letter, HEAD_ROW)]
        c.value = sheet_label(col.header, lang)
        c.font = head_font
        c.alignment = HEAD_STACKED
        c.border = grid
        band = GREEN_BAND if col.band == "green" else NAVY
        c.fill = PatternFill("solid", fgColor=band)
    ws.row_dimensions[HEAD_ROW].height = row_height(lang)


def write_row_formulas(ws, r, letter_of):
    def cell(key):
        return "%s%d" % (letter_of[key], r)
    req, meas = cell("requirement"), cell("measured")
    nom, tol = cell("_nom"), cell("_tol")
    up, dn = cell("_up"), cell("_dn")
    lo, hi = cell("_lo"), cell("_hi")
    ws[nom] = req_nom_formula(req)
    ws[tol] = req_tol_formula(req)
    ws[up] = req_up_formula(tol)
    ws[dn] = req_dn_formula(tol)
    ws[lo] = req_lo_formula(nom, tol, dn)
    ws[hi] = req_hi_formula(nom, tol, up)
    ws[cell("deviation")] = req_deviation_formula(meas, nom)
    ws[cell("result")] = req_result_formula(cell("bubble"), meas, lo, hi)


def _datarows(ws, data_font, mid, grid, fmts, cols, helpers, letter_of):
    fills = {letter: PatternFill("solid", fgColor=col.fill)
             for letter, col in cols}
    for r in range(FIRST_ROW, LAST_ROW + 1):
        for letter, _col in cols:
            c = ws["%s%d" % (letter, r)]
            c.font = data_font
            c.alignment = mid
            c.border = grid
            c.fill = fills[letter]
            c.number_format = fmts[letter]
        write_row_formulas(ws, r, letter_of)
        ws.row_dimensions[r].height = ROW_H
    for letter, _key in helpers:
        ws.column_dimensions[letter].hidden = True
        ws.column_dimensions[letter].width = 8.0


def _layout(ws, cols):
    for letter, col in cols:
        ws.column_dimensions[letter].width = col.width
        if col.hidden:
            ws.column_dimensions[letter].hidden = True
    ws.sheet_format.defaultColWidth = 8.6796875
    ws.sheet_format.defaultRowHeight = 14.25
    ws.freeze_panes = "A%d" % FIRST_ROW
    ws.auto_filter.ref = "A%d:%s%d" % (HEAD_ROW, _last_visible(cols), LAST_ROW)
    ws.protection.sheet = False          # form filled not locked


def _hf_text(s):
    """One header/footer field doubling & control character"""
    return str(s or "").replace("&", "&&").replace("\n", " ")[:120]


def apply_print_setup(ws, part="", last_row=FIRST_ROW, report_id="",
                      cols=None):
    last_col = _last_visible(cols or active_columns())
    end = max(int(last_row or FIRST_ROW), FIRST_ROW)
    ws.print_area = "A1:%s%d" % (last_col, end)
    ws.print_title_rows = "%d:%d" % (HEAD_ROW, HEAD_ROW)
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.paperSize = 9                  # A4
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0                # as many as needed
    ws.page_setup.scale = None                   # ignored under fitToPage
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.6
    ws.page_margins.header = ws.page_margins.footer = 0.3
    ws.oddHeader.left.text = _hf_text(ws["A1"].value)
    ws.oddHeader.right.text = "Part #: %s" % _hf_text(part)
    # None not empty string
    rid = _hf_text(report_id)
    ws.oddHeader.center.text = ("Report #: %s" % rid) if rid else None
    ws.oddFooter.right.text = "Page &P of &N"
    ws.oddFooter.left.text = "&D"                # printed-on date
    ws.oddFooter.center.text = rid or None


def _dv(values, ref):
    """One plain (non-x14) list dropdown."""
    v = DataValidation(type="list", formula1=_list_formula(values),
                       allow_blank=True, showDropDown=False,
                       showErrorMessage=False, showInputMessage=False)
    v.sqref = ref
    return v


def _span(letter):
    return "%s%d:%s%d" % (letter, FIRST_ROW, letter, LAST_ROW)


INSPECTION_CELL = "H6"


def header_dropdown_spec(names):
    names = fit_list([str(n).strip() for n in (names or ())
                      if str(n).strip() and "," not in str(n)
                      and '"' not in str(n)])
    return (INSPECTION_CELL, tuple(names)) if names else None


_DROPDOWN_VALUES = {
    "type": lambda lang: type_choices(lang),
    "tier": lambda lang: tier_choices(lang),
    "designator": lambda _lang: list(DESIGNATORS),
    "method": lambda lang: [sheet_value(m, lang) for m in METHODS],
}


def gage_names(cfg=None):
    """Gage list minus comma or quote names."""
    out = []
    for t in (cfg or {}).get("metrology_tools") or ():
        n = str((t or {}).get("name") or "").strip()
        if n and "," not in n and '"' not in n and n not in out:
            out.append(n)
    return fit_list(out)


# Excel inline list max
LIST_MAX = 255


def fit_list(names):
    out = []
    for n in names:
        if len('"%s"' % ",".join(out + [n])) > LIST_MAX:
            break
        out.append(n)
    return out


def dropdown_specs(lang, cfg=None):
    out = []
    for letter, col in active_columns(cfg):
        make = _DROPDOWN_VALUES.get(col.key)
        if make:
            out.append((letter, _span(letter), make(lang)))
    return tuple(out)


def _validations(ws, lang, inspections=(), cols=None):
    """Dropdowns as plain objects that survive save"""
    for letter, col in (cols or active_columns()):
        make = _DROPDOWN_VALUES.get(col.key)
        if make:
            ws.add_data_validation(_dv(make(lang), _span(letter)))
    spec = header_dropdown_spec(inspections)
    if spec:
        ws.add_data_validation(_dv(spec[1], spec[0]))


RESULT_RULES = (("PASS", PASS_FILL), ("FAIL", FAIL_FILL))


def result_range():
    return _span(RESULT_COL)


def _rules(ws):
    ref = _span(RESULT_COL)
    for word, colour in (("PASS", PASS_FILL), ("FAIL", FAIL_FILL)):
        ws.conditional_formatting.add(ref, CellIsRule(
            operator="equal", formula=['"%s"' % word],
            fill=PatternFill(start_color=colour, end_color=colour,
                             fill_type="solid")))


def column_letters(cfg=None):
    return [letter for letter, _col in active_columns(cfg)]
