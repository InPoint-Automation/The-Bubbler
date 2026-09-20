# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Hand-correct drawing general-tolerance block.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QRadioButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .common import fnum
from .config import (CFG_DEFAULT, dp_label, ladder_key, units_of,
                     validate_ladder)
from .i18n import tr
from .iso2768 import ISO2768, ISO2768_ANGLE
from .scanlib import (GENTOL_SRC_USER, gentol_readout, parse_gentol_bands)

# coarsest last named full
ISO_CLASSES = (("f", "fine"), ("m", "medium"), ("c", "coarse"),
               ("v", "very coarse"))

# ribbon source words reused
SRC_WORDS = {
    "band table on the drawing": "band table",
    "decimal-place block": "printed .X block",
    "printed fractional row": "printed fractions",
    "cited ISO 2768": "ISO 2768",
    "settings decimal ladder": "settings ladder",
    "settings ISO 2768": "settings ISO 2768",
    GENTOL_SRC_USER: "corrected by hand",
    "none": "no general tol",
}


def _num(e):
    """Line edit number or None when blank or bad."""
    try:
        return fnum(e.text())
    except (ValueError, AttributeError):
        return None


def block_summary(gtols):
    """Reader findings in drawing's own terms."""
    g = gtols or {}
    out = []
    for key, label in (("bands", "linear bands"),
                       ("bands_ang", "angular bands"),
                       ("bands_rad", "radius bands")):
        rows = g.get(key)
        if rows:
            out.append("%s: %s" % (tr(label), ", ".join(
                u"%g-%g ±%g" % r for r in rows)))
    places = sorted(k for k in g if isinstance(k, int) and 1 <= k <= 4)
    if places:
        out.append("%s: %s" % (tr("decimal places"), "  ".join(
            u".%s ±%g" % ("X" * d, g[d]) for d in places)))
    if g.get("ang") is not None:
        out.append(u"%s: ±%g°" % (tr("angular"), g["ang"]))
    if g.get("frac") is not None:
        out.append(u"%s: ±%g" % (tr("fractional"), g["frac"]))
    if g.get("iso_std"):
        out.append("%s %s-%s" % (tr("standard"), g["iso_std"],
                                 g.get("iso_linear") or ""))
    return "\n".join(out)


class GentolDialog(QDialog):
    """Let person correct read block."""

    def __init__(self, parent, gtols=None, cfg=None, session=None,
                 page_i=0):
        super().__init__(parent)
        self.setWindowTitle(tr('General tolerances'))
        self.cfg = dict(cfg or {})
        self.session = dict(session or {})
        self.gtols = dict(gtols or {})
        self.units = units_of(self.cfg, self.session)
        self.inch = self.units == "asme_inch"
        v = QVBoxLayout(self)

        v.addWidget(self._read_group(page_i))
        self.rb_drawing = QRadioButton(tr('Use what the drawing says'))
        self.rb_fix = QRadioButton(tr('Correct it for this drawing'))
        v.addWidget(self.rb_drawing)
        v.addWidget(self.rb_fix)
        self.editor = self._editor_group()
        v.addWidget(self.editor)

        self.btns = QDialogButtonBox(QDialogButtonBox.Ok
                                     | QDialogButtonBox.Cancel)
        self.btns.accepted.connect(self._ok)
        self.btns.rejected.connect(self.reject)
        # one-click revert to auto
        self.b_reset = self.btns.addButton(tr('Reset to auto'),
                                           QDialogButtonBox.ResetRole)
        self.b_reset.setToolTip(tr('Drop hand correction, use the drawing '
                                   '(ISO 2768 class, or decimal ladder on '
                                   'inch drawings).'))
        self.b_reset.clicked.connect(self._reset_auto)
        self.b_reset.setEnabled(bool(self.session.get("gentol_user")))
        v.addWidget(self.btns)

        self.rb_fix.toggled.connect(self._sync)
        self._load()
        self._sync()

    def _reset_auto(self):
        """Drop correction and fall back to drawing."""
        self.rb_drawing.setChecked(True)
        self._block = None
        self.accept()

    # ------------------------------------------------------- what was read
    def _read_group(self, page_i):
        g = QGroupBox(tr('Read off the drawing'))
        lay = QVBoxLayout(g)
        src, val, inh = gentol_readout(self.gtols, self.cfg, self.session)
        head = QLabel("%s %d:  %s  %s" % (tr('page'), page_i + 1,
                                          tr(SRC_WORDS.get(src, src)), val))
        head.setStyleSheet("font-weight:600;")
        lay.addWidget(head)
        if inh:
            note = QLabel(tr('No block on this page -- taken from sheet 1'))
            note.setStyleSheet("color:#b7791f;")
            lay.addWidget(note)
        txt = block_summary(self.gtols)
        body = QLabel(txt or tr('Nothing found on this page'))
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setWordWrap(True)
        lay.addWidget(body)
        return g

    # ------------------------------------------------------- correction
    def _editor_group(self):
        g = QGroupBox(tr('Correction'))
        lay = QVBoxLayout(g)
        lay.addWidget(self._ladder_widget())
        grid = QGridLayout()
        r = 0
        grid.addWidget(QLabel(tr('Angular')), r, 0)
        self.e_ang = QLineEdit()
        self.e_ang.setMaximumWidth(90)
        self.e_ang.setPlaceholderText(tr('deg'))
        grid.addWidget(self.e_ang, r, 1)
        grid.addWidget(QLabel(tr('blank = from the standard')), r, 2)
        r += 1
        if self.inch:
            grid.addWidget(QLabel(tr('Fractional')), r, 0)
            self.e_frac = QLineEdit()
            self.e_frac.setMaximumWidth(90)
            grid.addWidget(self.e_frac, r, 1)
            grid.addWidget(QLabel(tr('a whole-inch dim, e.g. 1/32')), r, 2)
            r += 1
        else:
            self.e_frac = None
        lay.addLayout(grid)

        lay.addWidget(QLabel(tr('Band table, as printed (optional):')))
        self.t_bands = QPlainTextEdit()
        self.t_bands.setMaximumHeight(72)
        self.t_bands.setPlaceholderText(u"0.5 - 6  ±0.1\n"
                                        u"6 - 30  ±0.2")
        lay.addWidget(self.t_bands)
        hint = QLabel(tr('One row per line. A band table overrides the '
                         'ladder above, like a printed one.'))
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:8pt; color:#666;")
        lay.addWidget(hint)
        return g

    def _ladder_widget(self):
        """Ladder this unit system uses."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        if self.inch:
            lay.addWidget(QLabel(tr('Decimal-place tolerances')))
            row = QHBoxLayout()
            self.dp_edits = {}
            for key in ("1", "2", "3", "4"):
                row.addWidget(QLabel(dp_label(key)))
                e = QLineEdit()
                e.setMaximumWidth(80)
                self.dp_edits[key] = e
                row.addWidget(e)
            row.addStretch(1)
            lay.addLayout(row)
            self.cb_class = None
            self.tbl = None
            return w

        self.dp_edits = {}
        row = QHBoxLayout()
        row.addWidget(QLabel(tr('ISO 2768 class')))
        self.cb_class = QComboBox()
        for key, word in ISO_CLASSES:
            self.cb_class.addItem("%s -- %s" % (key, tr(word)), key)
        self.cb_class.currentIndexChanged.connect(lambda _i: self._fill_iso())
        row.addWidget(self.cb_class)
        row.addStretch(1)
        lay.addLayout(row)
        # numbers class means
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(
            [tr('nominal, mm'), tr('linear'), tr('angular, deg')])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setMaximumHeight(190)
        self.tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        lay.addWidget(self.tbl)
        return w

    def _fill_iso(self):
        """Show what chosen class means band by band."""
        if self.tbl is None:
            return
        cls = self.cb_class.currentData() or "m"
        lin = ISO2768.get(cls) or []
        ang = ISO2768_ANGLE.get(cls) or []
        self.tbl.setRowCount(len(lin))
        lo = 0.0
        for r, (hi, tol) in enumerate(lin):
            at = None
            for a_hi, a_tol in ang:
                if hi <= a_hi:
                    at = a_tol
                    break
            cells = (u"%g - %g" % (lo, hi),
                     u"±%g" % tol if tol is not None else tr('n/a'),
                     u"±%.3g" % at if at is not None else "")
            for c, text in enumerate(cells):
                self.tbl.setItem(r, c, QTableWidgetItem(text))
            lo = hi

    # ------------------------------------------------------------ state
    def _load(self):
        """Open on what is in force."""
        ov = self.session.get("gentol_user")
        ov = dict(ov) if isinstance(ov, dict) and ov else None
        self.rb_fix.setChecked(ov is not None)
        self.rb_drawing.setChecked(ov is None)
        src = ov or self.gtols
        if self.inch:
            tols = (src if any(isinstance(k, int) for k in src)
                    else self.cfg.get(ladder_key(self.units))
                    or CFG_DEFAULT[ladder_key(self.units)])
            for key, e in self.dp_edits.items():
                v = src.get(int(key)) if any(
                    isinstance(k, int) for k in src) else tols.get(key)
                e.setText("" if v is None else "%g" % float(v))
        else:
            want = src.get("iso_linear") or CFG_DEFAULT["default_iso_class"]
            for i in range(self.cb_class.count()):
                if self.cb_class.itemData(i) == want:
                    self.cb_class.setCurrentIndex(i)
                    break
            self._fill_iso()
        if src.get("ang") is not None:
            self.e_ang.setText("%g" % src["ang"])
        if self.e_frac is not None and src.get("frac") is not None:
            self.e_frac.setText("%g" % src["frac"])
        rows = []
        for key, unit in (("bands", ""), ("bands_ang", u"°"),
                          ("bands_rad", "")):
            for lo, hi, tol in (src.get(key) or []):
                head = {"bands_ang": "ANGULAR ", "bands_rad": "RADIUS "}
                rows.append(u"%s%g - %g ±%g%s"
                            % (head.get(key, ""), lo, hi, tol, unit))
        self.t_bands.setPlainText("\n".join(rows))

    def _sync(self):
        self.editor.setEnabled(self.rb_fix.isChecked())

    # ----------------------------------------------------------- answer
    def result_block(self):
        """Corrected block or None for use-the-drawing."""
        if not self.rb_fix.isChecked():
            return None
        return self._block

    def _build(self):
        """Editors -> gtols-shaped block or (None, reason)."""
        g = {}
        if self.inch:
            tols = {}
            for key, e in self.dp_edits.items():
                v = _num(e)
                if v is not None:
                    tols[key] = v
            clean, reason = validate_ladder(tols, self.units)
            if reason is not None:
                return None, tr('Decimal-place ladder not usable: '
                                '%s') % str(reason[0])
            for key, v in (clean or {}).items():
                g[int(key)] = v
        else:
            g["iso_std"] = "2768"
            g["iso_linear"] = self.cb_class.currentData() or "m"
        ang = _num(self.e_ang)
        if ang is not None:
            g["ang"] = ang
        if self.e_frac is not None:
            fr = _num(self.e_frac)
            if fr is not None:
                g["frac"] = fr
        txt = self.t_bands.toPlainText().strip()
        if txt:
            bands = parse_gentol_bands(txt)
            if not bands:
                return None, tr('No band row read. Each row needs a '
                                'range and a tolerance, e.g. "6 - 30 '
                                '±0.2".')
            g.update(bands)
        if not g:
            return None, tr('Nothing to apply.')
        return g, None

    def _ok(self):
        if not self.rb_fix.isChecked():
            self._block = None
            self.accept()
            return
        block, reason = self._build()
        if reason is not None:
            QMessageBox.warning(self, tr('General tolerances'), reason)
            return
        self._block = block
        self.accept()


class ReapplyDialog(QDialog):
    """Which bubbled rows take corrected number."""

    def __init__(self, parent, ledger, plan):
        super().__init__(parent)
        self.setWindowTitle(tr('Apply the correction'))
        self.plan = list(plan or [])
        v = QVBoxLayout(self)
        head = QLabel(tr('%d bubbled rows took the old general tolerance. '
                         'Untick any typed by hand.')
                      % len(self.plan))
        head.setWordWrap(True)
        v.addWidget(head)

        self.tbl = QTableWidget(len(self.plan), 4)
        self.tbl.setHorizontalHeaderLabels(
            ["", tr('bubble'), tr('feature'), tr('was -> now')])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self.boxes = []
        for r, (i, old, new) in enumerate(self.plan):
            d = ledger[i] if 0 <= i < len(ledger) else {}
            cb = QCheckBox()
            cb.setChecked(True)
            self.boxes.append(cb)
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(6, 0, 0, 0)
            hl.addWidget(cb)
            self.tbl.setCellWidget(r, 0, holder)
            self.tbl.setItem(r, 1, QTableWidgetItem(str(d.get("bubble") or "")))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(d.get("feature") or "")))
            self.tbl.setItem(r, 3, QTableWidgetItem(
                u"±%g → ±%g" % (old, new)))
        v.addWidget(self.tbl)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        v.addWidget(line)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr('Apply'))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def chosen(self):
        """[(index, new)] for ticked rows only."""
        return [(i, new) for (i, _old, new), cb
                in zip(self.plan, self.boxes) if cb.isChecked()]
