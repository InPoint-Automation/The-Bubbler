# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Per-drawing unit system detect and override.

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout,
                               QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QVBoxLayout)

from .config import (CFG_DEFAULT, dp_label, ladder_key,
                     units_of, units_source, validate_ladder)
from .i18n import tr
from .units import INCH, MM, UNKNOWN, detect_units_doc


class UnitsMixin:
    """Owns drawing unit system with config fallback."""

    # session only not persisted
    _units_prompted = False

    def _units_detect(self):
        """Detector verdict cached on session OCR fallback W43."""
        got = self.drawing.get("units_detect")
        if got is None:
            try:
                got = detect_units_doc(self.doc)
            except Exception:
                got = {"units": UNKNOWN, "conf": 0.0, "signals": []}
            if got.get("units", UNKNOWN) == UNKNOWN:
                ocr = self._detect_units_ocr()
                if ocr and ocr.get("units") in (MM, INCH):
                    got = ocr
            got = {"units": got.get("units", UNKNOWN),
                   "conf": float(got.get("conf") or 0.0)}
            self.drawing["units_detect"] = got
        return got

    def _ocr_page_text(self, i):
        """OCR text of one page empty on failure."""
        from . import vision
        words = vision._ocr_words(self.doc[i], self.cfg)
        return " ".join(str(w[4]) for w in words if len(w) > 4)

    def _detect_units_ocr(self):
        """Units from scanned-drawing OCR or None."""
        from . import vision
        from .units import detect_units
        if not self.cfg.get("vision_ocr", True):
            return None
        try:
            if not vision.available(self.cfg).get("ocr"):
                return None
        except Exception:
            return None
        try:
            n = int(getattr(self.doc, "page_count", 0) or 0)
        except (TypeError, ValueError):
            n = 0
        parts = []
        for i in range(n):
            try:
                parts.append(self._ocr_page_text(i))
            except Exception:
                continue
            got = detect_units("\n".join(parts))
            if got.get("units") in (MM, INCH):
                return got
        return detect_units("\n".join(parts)) if parts else None

    def _units_autodetect(self):
        """Detect once on open ask if undecided."""
        if self.drawing.get("units_asked") or self._units_prompted:
            self._sync_sheet_units()
            return
        if units_source(self.drawing) == "manual":
            self.drawing["units_asked"] = True
            self._sync_sheet_units()
            return
        got = self._units_detect()
        if got["units"] in (MM, INCH):
            self._set_drawing_units(got["units"], manual=False)
            self.drawing["units_asked"] = True
            return
        if not self.cfg.get("units_ask", True) or self.store.read_only:
            self._sync_sheet_units()
            return                        # viewing only never block
        self._units_prompted = True       # session only not file
        self._units_ask()

    def _units_box(self):
        """Split out so screenshot can grab it."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr('Unit system'))
        box.setText(tr('Bubbler cannot tell what units this drawing uses.'))
        box.setInformativeText(
            tr('Pick the system it was drawn in. Tolerances, gage choice '
               'and the general-tolerance ladder all follow it. Change it '
               'later from the hotbar or Settings.'))
        box.button_mm = box.addButton(tr('Millimetres (ISO)'),
                                      QMessageBox.AcceptRole)
        box.button_in = box.addButton(tr('Inches (ASME)'),
                                      QMessageBox.AcceptRole)
        box.setDefaultButton(box.button_mm)
        return box

    def _units_ask(self):
        """open() not exec() avoids wedging event loop."""
        box = self._units_box()
        box.finished.connect(lambda _r=0, b=box: self._units_answered(b))
        box.open()
        self._units_prompt = box

    def _units_answered(self, box):
        """Dismissed is not answer next open asks again."""
        btn = box.clickedButton()
        if btn is getattr(box, "button_in", None):
            self.drawing["units_asked"] = True
            self._set_drawing_units(INCH, manual=True)
        elif btn is getattr(box, "button_mm", None):
            self.drawing["units_asked"] = True
            self._set_drawing_units(MM, manual=True)

    def _set_drawing_units(self, units, manual=True):
        """Write drawing unit system manual always wins."""
        if units not in (MM, INCH):
            return
        self.drawing["units"] = units
        self.drawing["units_src"] = "manual" if manual else "detected"
        try:
            self._save_session()
        except Exception:
            pass
        self._sync_sheet_units()
        self._sync_units_controls()
        self._qbar_refresh()
        # redraw stale mm/inch reading
        if getattr(self, "measure_mode", False):
            self._fill_munits()
            self._walk_show()
        self.set_status()

    def _sync_sheet_units(self):
        """Tell workbook which system drawing is in."""
        w = getattr(self, "writer", None)
        if w is None:
            return
        try:
            w.set_units(units_of(self.cfg, self.drawing))
        except Exception:
            pass

    def _units_menu(self):
        """Hotbar menu for current units and change."""
        m = QMenu(self)
        cur = units_of(self.cfg, self.drawing)
        got = self._units_detect()
        head = m.addAction(
            tr('Detected: %s') % (tr('unknown') if got["units"] == UNKNOWN
                                  else self._units_name(got["units"])))
        head.setEnabled(False)
        m.addSeparator()
        for u in (MM, INCH):
            a = m.addAction(self._units_name(u))
            a.setCheckable(True)
            a.setChecked(cur == u)
            a.triggered.connect(
                lambda _c=False, uu=u: self._set_drawing_units(uu))
        m.addSeparator()
        lad = m.addAction(tr('Ladder for this drawing...'))
        lad.triggered.connect(lambda _c=False: self.drawing_ladder_editor())
        m.addSeparator()
        src = m.addAction(tr('Set by you') if units_source(self.drawing)
                          == "manual" else tr('Set by the detector'))
        src.setEnabled(False)
        m.exec(self.cursor().pos())

    def drawing_ladder_editor(self):
        """Decimal-place ladder for drawing only."""
        units = units_of(self.cfg, self.drawing)
        key = ladder_key(units)
        buckets = sorted(CFG_DEFAULT[key], key=int)
        dlg = QDialog(self)
        dlg.setWindowTitle(tr('Ladder for this drawing'))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            tr('Blank rows fall back to Settings. This drawing only.')))
        grid = QGridLayout()
        lay.addLayout(grid)
        cur = self.drawing.get(key) or {}
        fallback = self.cfg.get(key) or CFG_DEFAULT[key]
        edits = {}
        for i, k in enumerate(buckets):
            grid.addWidget(QLabel(dp_label(k) + " ±"), i, 0)
            e = QLineEdit("" if k not in cur else "%g" % float(cur[k]))
            e.setPlaceholderText("%g" % float(
                fallback.get(k, CFG_DEFAULT[key][k])))
            grid.addWidget(e, i, 1)
            edits[k] = e
        b_def = QPushButton(tr('Use the Settings ladder'))
        b_def.clicked.connect(lambda: [e.clear() for e in edits.values()])
        lay.addWidget(b_def)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.rejected.connect(dlg.reject)

        def _ok():
            typed = {k: e.text().strip() for k, e in edits.items()
                     if e.text().strip()}
            if not typed:
                self.drawing.pop(key, None)      # back to global ladder
            else:
                merged = dict(fallback)
                merged.update(typed)
                got, why = validate_ladder(merged, units)
                if why is not None:
                    QMessageBox.critical(dlg, tr('Tolerance ladder refused'),
                                         self._ladder_reason(why))
                    return
                self.drawing[key] = got
            try:
                self._save_session()
            except Exception:
                pass
            dlg.accept()
        bb.accepted.connect(_ok)
        self._drawing_ladder_dlg = dlg
        return dlg

    @staticmethod
    def _ladder_reason(why):
        from .settings_mixin import _ladder_reason
        return _ladder_reason(why)

    @staticmethod
    def _units_name(units):
        return (tr('Inches (ASME)') if units == INCH
                else tr('Millimetres (ISO)'))
