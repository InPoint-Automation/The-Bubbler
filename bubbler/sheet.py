# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Writes inspection .xlsx atomically

import os
import shutil

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .common import SHEET, FIRST_ROW, LAST_ROW, TIERS, TYPES
from .i18n import available_langs, sheet_label, sheet_value
from .reportrow import Row
from .sheet_build import (BANNER_CELL, FORMULA_COLS, HEAD_ROW, LABEL_ROWS,
                          OWNED_DESIGNATORS, REQUIREMENT_COL, RESULT_COL,
                          REPORT_CELL, RESULT_RULES, SHEET_GEN, SUMMARY_ROW,
                          TIER_DESIGNATOR, TITLE_VALUE_CELLS, UNIT_TEXT, UNITS_CELL, active_columns,
                          apply_print_setup, banner_text,
                          build_workbook, column_letters, dropdown_specs,
                          header_dropdown_spec,
                          generation_of, header_fields, label_cells,
                          number_formats, result_range,
                          row_height,
                          stamp_generation)

# author stamp on Bubbler's own cell note
NOTE_AUTHOR = "Bubbler"
CONFLICT_NOTE = "Bubbler read"

# (value cell, English key) per header box
HEADER_FIELDS = list(header_fields())


def ensure_xlsx(path, company="", sheet_lang="both", units="iso_mm"):
    """Create workbook if absent, True when created."""
    if os.path.isfile(path):
        return False
    build_workbook(sheet_lang=sheet_lang, company=company,
                   units=units).save(path)
    return True


# every possible sheet language
SHEET_LANGS = ("both", "en") + tuple(available_langs())

# "requirement" header renderings mark GEN-3 layout
_REQUIREMENT_HEADERS = {sheet_label("requirement", l) for l in SHEET_LANGS}


def _vocab():
    """Every rendering of TYPE/TIER value -> English key."""
    out = {}
    for key in list(TYPES) + [t for t in TIERS if t]:
        for lang in SHEET_LANGS:
            out[sheet_value(key, lang)] = key
    return out


VOCAB = _vocab()


# RENAMED label -> old keys it was spelled under
RETIRED_LABEL_KEYS = {"Inspection type": ("FAI type",),
                      # FAIR = report only
                      "Report #": ("FAIR #",)}


def _renderings(key):
    """Every rendering of one label key, all languages."""
    out = set()
    for k in (key,) + tuple(RETIRED_LABEL_KEYS.get(key, ())):
        out.update(sheet_value(k, lang) for lang in SHEET_LANGS)
        out.add(sheet_label(k, "both"))
    return out


class SheetWriter(object):
    # ledger keys app WRITES, in layout order
    WRITTEN_KEYS = ("bubble", "feature", "requirement", "measured", "type",
                    "method", "tier", "gage")
    # ------------------------------------------------- who owns which column
    HUMAN_KEYS = ("measured", "gage")
    LOC_KEYS = {"type", "tier", "method"}

    def __init__(self, path, sheet_lang="both", tier_designator=False,
                 tier_column=False, inspections=(), refzone_column=False,
                 ncr_column=False, gage_column=False, method_column=False,
                 type_column=False, units="iso_mm", cfg=None):
        self.path = path
        self.sheet_lang = sheet_lang or "both"
        # units+cfg let write_row match report string
        self.units = units if units in UNIT_TEXT else "iso_mm"
        self.cfg = dict(cfg or {})
        # sheet_tier_designator: tier maps to designator col
        self.tier_designator = bool(tier_designator)
        # sheet_tier_column: does tier reach sheet
        self.tier_column = bool(tier_column)
        # Inspection type dropdown names (H6)
        self.inspections = tuple(inspections or ())
        # which OPTIONAL columns layout carries
        self.flags = {
            "sheet_tier_designator": self.tier_designator,
            "sheet_tier_column": self.tier_column,
            "sheet_refzone_column": bool(refzone_column),
            "sheet_ncr_column": bool(ncr_column),
            "sheet_gage_column": bool(gage_column),
            "sheet_method_column": bool(method_column),
            "sheet_type_column": bool(type_column),
        }
        self.cols = active_columns(self.flags)
        self.col_of = {col.key: letter for letter, col in self.cols}
        # (letter, ledger key) per app-written column
        self.COLS = tuple((self.col_of[k], k) for k in self.WRITTEN_KEYS
                          if k in self.col_of)
        self.NUMCOLS = frozenset(letter for letter, col in self.cols
                                 if col.numfmt == "num")
        self.HUMAN_COLS = tuple(self.col_of[k] for k in self.HUMAN_KEYS
                                if k in self.col_of)
        self.TIER_COL = self.col_of.get("tier")
        self.DESIGNATOR_COL = self.col_of.get("designator")
        # cleared row reused, must carry nothing
        self.CLEAR_COLS = tuple(letter for letter, col in self.cols
                                if not col.formula)
        self.wb = load_workbook(path)
        if SHEET not in self.wb.sheetnames:
            raise ValueError("No '%s' sheet in %s" % (SHEET, path))
        self.ws = self.wb[SHEET]
        self._repair()

    # ------------------------------------------------ legacy repair
    def _repair(self):
        """Bring older workbook up to date, idempotent."""
        self._fix_dropdowns()
        self._fix_inspections()
        self._fix_rules()
        self._fix_vocab()
        self._fix_labels()
        if generation_of(self.wb) is None:
            stamp_generation(self.wb)      # current layout, old file

    def _fix_dropdowns(self):
        have = self.ws.data_validations.dataValidation
        for col, ref, values in dropdown_specs(self.sheet_lang, self.flags):
            if any(v.type == "list" and _covers(v.sqref, col) for v in have):
                continue                 # keep existing
            v = DataValidation(type="list", allow_blank=True,
                               formula1='"%s"' % ",".join(values),
                               showDropDown=False, showErrorMessage=False,
                               showInputMessage=False)
            v.sqref = ref
            self.ws.add_data_validation(v)

    def _fix_inspections(self):
        """Keep H6 dropdown listing today's presets."""
        spec = header_dropdown_spec(self.inspections)
        if not spec:
            return
        cell, values = spec
        mine = set(values)
        for v in list(self.ws.data_validations.dataValidation):
            if v.type != "list" or not _covers_cell(v.sqref, cell):
                continue
            was = _list_values(v.formula1)
            if set(was) - mine:
                return                   # foreign list, hands off
            if was == list(values):
                return                   # already current
            self.ws.data_validations.dataValidation.remove(v)
        dv = DataValidation(type="list", allow_blank=True,
                            formula1='"%s"' % ",".join(values),
                            showDropDown=False, showErrorMessage=False,
                            showInputMessage=False)
        dv.sqref = cell
        self.ws.add_data_validation(dv)

    def _fix_rules(self):
        for rng in self.ws.conditional_formatting:
            if _covers(rng.sqref, RESULT_COL) and rng.rules:
                return                   # already coloured, edits kept
        for word, colour in RESULT_RULES:
            self.ws.conditional_formatting.add(result_range(), CellIsRule(
                operator="equal", formula=['"%s"' % word],
                fill=PatternFill(start_color=colour, end_color=colour,
                                 fill_type="solid")))

    def _fix_vocab(self):
        """One vocabulary per column, re-render known type/tier."""
        for col, key in self.COLS:
            if key not in self.LOC_KEYS:
                continue
            for r in range(FIRST_ROW, LAST_ROW + 1):
                c = self.ws["%s%d" % (col, r)]
                en = VOCAB.get(c.value) if isinstance(c.value, str) else None
                if en is None:
                    continue             # blank or user-typed
                want = sheet_value(en, self.sheet_lang)
                if c.value != want:
                    c.value = want

    def _fix_labels(self):
        """Static labels follow export language, like data."""
        for cell, key in label_cells(self.flags):
            c = self.ws[cell]
            want = sheet_label(key, self.sheet_lang)
            if c.value != want and c.value in _renderings(key):
                c.value = want
                a = c.alignment
                c.alignment = Alignment(horizontal=a.horizontal,
                                        vertical=a.vertical, wrap_text=True)
        self._fix_label_rows()
        self._fix_banner()

    def _fix_label_rows(self):
        """Label rows taller when labels stack two lines."""
        for r in tuple(LABEL_ROWS) + (SUMMARY_ROW, HEAD_ROW):
            self.ws.row_dimensions[r].height = row_height(self.sheet_lang)

    def _fix_banner(self):
        """Row 1: re-render title, keep company prefix."""
        v = self.ws[BANNER_CELL].value
        if not isinstance(v, str):
            return
        for was in _renderings("Inspection Sheet"):
            if v == was:
                company = ""
            elif v.endswith(" - " + was):
                company = v[:-len(" - " + was)]
            else:
                continue
            self.ws[BANNER_CELL] = banner_text(company, self.sheet_lang)
            return

    def set_units(self, units):
        """Label sheet with DRAWING units and reformat D..J."""
        if units not in UNIT_TEXT:
            return False
        self.units = units
        want = UNIT_TEXT[units]
        fmts = number_formats(units, self.flags)
        changed = self.ws[UNITS_CELL].value != want
        self.ws[UNITS_CELL] = want
        for r in range(FIRST_ROW, LAST_ROW + 1):
            for col in self.NUMCOLS:
                cell = self.ws["%s%d" % (col, r)]
                if cell.number_format != fmts[col]:
                    cell.number_format = fmts[col]
                    changed = True
        return changed

    def set_report_id(self, rid):
        """Stamp run's report id, True when changed."""
        rid = str(rid or "").strip()
        if not rid:
            return False                 # never blank stamped id
        cell = self.ws[REPORT_CELL]
        if cell.value == rid:
            return False
        cell.value = rid
        return True

    def report_id(self):
        """Id stamped on sheet, "" when none."""
        return str(self.ws[REPORT_CELL].value or "").strip()

    def get_header(self):
        return {cell: (self.ws[cell].value or "")
                for cell, _ in HEADER_FIELDS}

    def set_header(self, values):
        for cell, v in values.items():
            self.ws[cell] = v

    # ---------------------------------------------- ingest human edits
    # human-authored columns -> ledger key, read on OPEN
    READ_KEYS = {"measured": "measured", "gage": "gage",
                 "comments": "comment", "ncr": "ncr", "refzone": "refzone"}

    def read_human(self, r):
        """Human-authored values on row `r`, keyed by LEDGER key."""
        out = {}
        for col_key, ledger_key in self.READ_KEYS.items():
            letter = self.col_of.get(col_key)
            if not letter:
                continue
            v = self.ws["%s%d" % (letter, r)].value
            if v not in (None, "") and not str(v).startswith("="):
                out[ledger_key] = v
        return out

    def _row_free(self, r):
        """Is row `r` empty across EVERY writable column?"""
        for col in self.CLEAR_COLS:
            if self.ws["%s%d" % (col, r)].value not in (None, ""):
                return False
        return True

    def next_row(self):
        for r in range(FIRST_ROW, LAST_ROW + 1):
            if self._row_free(r):
                return r
        return None

    def free_rows(self):
        """Unused rows (new-bubble capacity)."""
        return sum(1 for r in range(FIRST_ROW, LAST_ROW + 1)
                   if self._row_free(r))

    @staticmethod
    def _safe_text(v):
        s = str(v)
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    def write_row(self, r, d):
        """Push one ledger row into sheet, per ownership rule."""
        row = Row.from_ledger(d, self.cfg, self.units)
        for col, key in self.COLS:
            if key == "requirement":
                v = row.requirement
            elif key == "method":
                v = row.method or None
            else:
                v = d.get(key, None)
            if key in self.LOC_KEYS and v not in (None, ""):
                v = sheet_value(str(v), self.sheet_lang)
            if col == self.TIER_COL:
                self._set_tier(r, v if self.writes_tier else None)
            elif col in self.HUMAN_COLS:
                self._set_human(r, col, key, v)
            else:
                self._put(r, col, v)
        if self.DESIGNATOR_COL:
            self._set_designator(r, d.get("tier") if self.tier_designator
                                 else None)

    @property
    def writes_tier(self):
        """Tier reaches column M, designator column off."""
        return self.tier_column and not self.tier_designator

    def _put(self, r, col, v):
        """App-owned cell: ledger value, blank included."""
        cell = self.ws["%s%d" % (col, r)]
        if v in (None, ""):
            cell.value = None
        elif col in self.NUMCOLS:
            cell.value = self._num_or_text(v)
        else:
            cell.value = self._safe_text(v)

    def _num_or_text(self, v):
        """Numeric if parses else escaped text."""
        try:
            return float(str(v).replace(",", "."))
        except ValueError:
            return self._safe_text(v)

    def _set_tier(self, r, v):
        """Column M: owned over tier vocabulary only."""
        c = self.ws["%s%d" % (self.TIER_COL, r)]
        cur = c.value
        if cur not in (None, "") and VOCAB.get(str(cur).strip()) not in TIERS:
            return
        c.value = self._safe_text(v) if v not in (None, "") else None

    def _set_human(self, r, col, key, v):
        """Inspector's record columns are add-only."""
        c = self.ws["%s%d" % (col, r)]
        cur = c.value
        if v in (None, ""):
            return                       # nothing to add/erase
        new = self._num_or_text(v) if key == "measured" else self._safe_text(v)
        if cur in (None, "") or cur == new:
            c.value = new
            self._drop_note(c)
        else:
            self._note(c, new)

    def _note(self, cell, value):
        """Leave unwritten reading on cell."""
        cur = cell.comment
        if cur is not None and cur.author != NOTE_AUTHOR:
            return                       # foreign note stays
        cell.comment = Comment(
            "%s: %s" % (sheet_value(CONFLICT_NOTE, self.sheet_lang), value),
            NOTE_AUTHOR)

    @staticmethod
    def _drop_note(cell):
        """Drop stale conflict note once agree."""
        cur = cell.comment
        if cur is not None and cur.author == NOTE_AUTHOR:
            cell.comment = None

    def _set_designator(self, r, tier):
        """Map balloon tier onto R designator column."""
        c = self.ws["%s%d" % (self.DESIGNATOR_COL, r)]
        cur = c.value
        if cur not in (None, "") and str(cur).strip() not in OWNED_DESIGNATORS:
            return
        c.value = TIER_DESIGNATOR.get(str(tier or "").strip()) or None

    def clear_row(self, r):
        """Free entire row A..T, every column."""
        for col in self.CLEAR_COLS:
            cell = self.ws["%s%d" % (col, r)]
            cell.value = None
            cell.comment = None          # note part of record
        # built formulas read blank on their own

    def last_used_row(self):
        """Highest row with bubble number, floor FIRST_ROW."""
        last = FIRST_ROW
        for r in range(FIRST_ROW, LAST_ROW + 1):
            if self.ws["A%d" % r].value not in (None, ""):
                last = r
        return last

    def save(self):
        apply_print_setup(self.ws, part=self.ws["B3"].value or "",
                          last_row=self.last_used_row(),
                          report_id=self.report_id(), cols=self.cols)
        tmp = self.path + ".tmp"
        self.wb.save(tmp)
        try:
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


# ------------------------------------------------ re-lay (old workbooks)
# retired/GEN-1 layout, letter -> ledger key
_OLD_LAYOUT = (
    ("A", "bubble"), ("B", "type"), ("C", "feature"), ("D", "nominal"),
    ("E", "tol_sym"), ("F", "tol_max"), ("G", "tol_min"),
    ("K", "measured"), ("M", "tier"), ("N", "gage"),
    ("Q", "refzone"), ("R", "designator"), ("S", "ncr"), ("T", "comment"),
)
# optional column carried key must turn on
_KEY_NEEDS_COLUMN = {"tier": "sheet_tier_column", "gage": "sheet_gage_column",
                     "refzone": "sheet_refzone_column",
                     "designator": "sheet_tier_designator",
                     "ncr": "sheet_ncr_column", "type": "sheet_type_column"}
# ledger key each column lands in
_KEY_OF_COL = {"comments": "comment"}

# non-formula columns of DEFAULT layout, as letters
CARRY_COLS = tuple(L for L in column_letters() if L not in FORMULA_COLS)


def _carried(ws):
    """Old workbook's human data as (title dict, rows)."""
    title = {}
    for cell in TITLE_VALUE_CELLS:
        v = ws[cell].value
        if v not in (None, ""):
            title[cell] = v
    rows = []
    for r in range(FIRST_ROW, LAST_ROW + 1):
        d = {}
        for col, key in _OLD_LAYOUT:
            v = ws["%s%d" % (col, r)].value
            if v not in (None, "") and not str(v).startswith("="):
                d[key] = v
        if d:
            rows.append((r, d))
    return title, rows


def _carry_cfg(rows):
    """cfg turning on optional columns carried rows need."""
    cfg = {}
    for _r, d in rows:
        for key in d:
            flag = _KEY_NEEDS_COLUMN.get(key)
            if flag:
                cfg[flag] = True
    return cfg


def needs_relay(path):
    """Is workbook older than today's layout?"""
    try:
        wb = load_workbook(path)
    except Exception:
        return False
    if SHEET not in wb.sheetnames:
        return False
    if generation_of(wb) is not None:
        return generation_of(wb) < SHEET_GEN
    # unstamped: GEN-3 marked by REQUIREMENT header
    ws = wb[SHEET]
    head = str(ws["%s%d" % (REQUIREMENT_COL, HEAD_ROW)].value or "")
    return not any(head == r for r in _REQUIREMENT_HEADERS)


def relay(path, sheet_lang="both", company="", units="iso_mm", backup=True):
    """Rebuild `path` on current layout, carry human data BY KEY."""
    title, rows = _carried(load_workbook(path)[SHEET])
    bak = None
    if backup:
        bak = os.path.splitext(path)[0] + ".bak.xlsx"
        shutil.copy2(path, bak)
    cfg = _carry_cfg(rows)
    wb = build_workbook(sheet_lang=sheet_lang, company=company, units=units,
                        cfg=cfg)
    ws = wb[SHEET]
    for cell, v in title.items():
        ws[cell] = v
    cols = active_columns(cfg)
    # ledger key each active column carries
    key_of = {col.key: _KEY_OF_COL.get(col.key, col.key) for _l, col in cols}
    for r, d in rows:
        # old nominal/tol grid -> one requirement string
        row = Row.from_ledger(d, cfg, units)
        for letter, col in cols:
            if col.formula:
                continue
            if col.key == "requirement":
                if row.requirement:
                    _relay_put(ws, letter, r, row.requirement, col)
                continue
            if col.key == "method":
                if row.method:
                    _relay_put(ws, letter, r, row.method, col)
                continue
            key = key_of[col.key]
            if key in d:
                _relay_put(ws, letter, r, d[key], col)
    tmp = path + ".tmp"
    wb.save(tmp)
    os.replace(tmp, path)
    return bak


def _relay_put(ws, letter, r, v, col):
    """Place one carried value, numeric where column numeric."""
    cell = ws["%s%d" % (letter, r)]
    if col.numfmt == "num":
        try:
            cell.value = float(str(v).replace(",", "."))
            return
        except ValueError:
            pass
    cell.value = v


def _list_values(formula1):
    """Entries of inline list validation, as written."""
    t = str(formula1 or "").strip()
    if t.startswith('"') and t.endswith('"'):
        t = t[1:-1]
    return [x for x in t.split(",") if x]


def _covers_cell(sqref, cell):
    """Does validation range name exactly ONE cell?"""
    return str(cell) in str(sqref or "").split()


def _covers(sqref, letter):
    """Does validation/formatting range touch data column?"""
    try:
        cells = str(sqref).split()
    except Exception:
        return False
    for part in cells:
        head = part.split(":")[0]
        col = "".join(ch for ch in head if ch.isalpha())
        if col.upper() == letter:
            return True
    return False
