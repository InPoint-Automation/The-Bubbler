# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble entry/edit dialog with hole-pattern rows.

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QCheckBox,
                               QSpinBox, QPushButton, QFrame, QWidget,
                               QMessageBox)

from .common import TYPES, TIERS, fnum, keeps_limit
from .scanrows import facet_order, row_facet
from .config import CFG_DEFAULT, gentol_auto, gentol_ladder, units_of
from .widgets import fill_keyed, combo_key, set_combo_key
from .iso2768 import (ANGLE_SHORTEST_SIDE, is_angle_feature,
                      is_broken_edge, is_radius_feature)
from .iso286 import fit_limits, is_fit_code
from .gentol import general_tol, gentol_exempt
from .i18n import tr, retranslate
from .units import format_nominal


def _num(text, what):
    try:
        return fnum(text)
    except (TypeError, ValueError, ZeroDivisionError):
        raise ValueError(tr('%s: %s is not a number.')
                         % (what, str(text or "").strip()))


def _tol_num(text):
    raw = str(text or "").strip()
    if is_fit_code(raw):
        try:
            return fnum(raw)
        except (TypeError, ValueError, ZeroDivisionError):
            raise ValueError(tr('Fit %s: type the fit code in the '
                                '± field, on a millimetre drawing.')
                             % raw)
    return _num(raw, tr('Tolerance'))

class Var(object):

    def __init__(self, getter, setter):
        self._get = getter
        self._set = setter

    def get(self):
        return self._get()

    def set(self, v):
        self._set(v)


def _line_edit(width=None):
    e = QLineEdit()
    if width:
        e.setMaximumWidth(width)
    return e


_UNIT_SUFFIX = re.compile(
    "^\\s*([+\\-\u00b1]?)\\s*(\\d+(?:(?:[ ]+|-)\\d+/\\d+)?(?:[.,]\\d*)?"
    "(?:/\\d+)?|[.,]\\d+)\\s*(mm|in|inch|inches|\"|\u2033)\\s*$", re.I)


def convert_unit_text(text, units):
    """Unit-typed text to drawing units. None if unitless."""
    m = _UNIT_SUFFIX.match(str(text or ""))
    if not m:
        return None
    try:
        # `1-1/4in` is `1 1/4in`
        v = fnum(re.sub(r"^(\d+)-(\d+/\d+)$", r"\1 \2", m.group(2)))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    src_mm = m.group(3).lower() == "mm"
    dst_mm = units != "asme_inch"
    if src_mm and not dst_mm:
        v = v / 25.4
    elif not src_mm and dst_mm:
        v = v * 25.4
    sign = m.group(1) if m.group(1) in ("+", "-") else ""
    # 9 places: 1/128in exact in mm
    return sign + ("%.9f" % v).rstrip("0").rstrip(".")


def _num_text(v):
    """Exact round trip. %g lost digits."""
    return "%.12g" % v


class BubbleDialog(QDialog):

    def __init__(self, parent, bubble_no, last=None, at=None, cfg=None,
                 edit_row=None, prefill=None, leader_default=None,
                 session=None, gtols=None, siblings=None, group_rows=None,
                 group_at=0, qty_on=None):
        super().__init__(parent)
        self.qty_ticked = None
        self.edit = edit_row is not None
        # sub-row balloon edited as one group
        self.switch_to = None
        self._siblings = {row_facet(s): s for s in (siblings or ())
                          if row_facet(s) not in (None, "hole")}
        self._facet_edit = self.edit and siblings is not None
        self.setWindowTitle((tr('Edit') + " #%s" if self.edit
                             else tr('Bubble') + " #%s") % bubble_no)
        self.bubble_no = bubble_no
        self.rows = []
        self.result_rows = None
        self.last_out = {}
        self.new_number = None
        self.sub_idx = 0
        self.last_geo = None
        cfg = cfg or {}
        self.cfg = cfg
        self.session = session or {}
        self.gtols = gtols or {}
        if last is None:
            last = {"type": cfg.get("default_type", TYPES[0]),
                    "tier": cfg.get("default_tier", ""),
                    "iso_on": gentol_auto(cfg),
                    "icls": cfg.get("default_iso_class", "m")}
        self.iso_on = bool(last.get("iso_on")) and not self.edit
        self.icls = str(last.get("icls", "m"))
        self._tsym_user = False
        self._mm_user = False
        self._tsym_sticky = False
        self._mm_sticky = False
        self._no_gentol = False        # capture sets any exemption
        self._ang_short = bool(cfg.get("angular_short_side",
                                       CFG_DEFAULT["angular_short_side"]))

        g = QGridLayout(self)
        r = 0

        self._group_tbl = None
        if self.edit and group_rows and len(group_rows) > 1:
            r = self._build_group(g, r, group_rows, group_at)

        self.v_bubnum = None
        if self.edit:
            g.addWidget(QLabel(tr('No.')), r, 0, Qt.AlignLeft)
            base = str(bubble_no).rstrip("abcdefghijklmnopqrstuvwxyz")
            sp = QSpinBox()
            sp.setRange(1, 999)
            sp.setValue(int(base or 1))
            self._bubnum_sp = sp
            self.v_bubnum = Var(lambda: str(sp.value()),
                                lambda s: sp.setValue(int(float(
                                    str(s).replace(",", ".") or 1))))
            g.addWidget(sp, r, 1, Qt.AlignLeft)
            r += 1

        g.addWidget(QLabel(tr('Type')), r, 0, Qt.AlignLeft)
        self.cb_type = QComboBox()
        fill_keyed(self.cb_type, TYPES, last.get("type", TYPES[0]))
        self.v_type = Var(lambda: combo_key(self.cb_type),
                          lambda v: set_combo_key(self.cb_type, v))
        self.cb_type.activated.connect(lambda _i: self._type_changed(True))
        g.addWidget(self.cb_type, r, 1, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel(tr('Feature')), r, 0, Qt.AlignLeft)
        self.e_feat = _line_edit(220)
        self.v_feat = Var(self.e_feat.text, self.e_feat.setText)
        self.e_feat.textChanged.connect(lambda _t: self._feat_changed())
        g.addWidget(self.e_feat, r, 1, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel(tr('Nominal')), r, 0, Qt.AlignLeft)
        self.e_nom = _line_edit(110)
        self.v_nom = Var(self.e_nom.text, self.e_nom.setText)
        self.e_nom.textChanged.connect(lambda _t: self._iso_autofill())
        g.addWidget(self.e_nom, r, 1, Qt.AlignLeft)
        r += 1

        self.chk_edge = QCheckBox(tr('This is a broken edge'))
        self.chk_edge.setToolTip(
            tr('Edge break = the general "break sharp edges" note; ISO '
               '2768-1 gives it a wide table. A dimensioned chamfer, fillet '
               'or spherical radius is a feature and takes the tighter '
               'linear table. Tick only when the callout IS the edge break.'))
        self.chk_edge.stateChanged.connect(lambda _s: self._iso_autofill())
        g.addWidget(self.chk_edge, r, 1, Qt.AlignLeft)
        r += 1

        self.lbl_angside = QLabel(tr('Angle side'))
        self.w_angside = QWidget()
        _al = QHBoxLayout(self.w_angside)
        _al.setContentsMargins(0, 0, 0, 0)
        self.e_angside = _line_edit(70)
        self.e_angside.setPlaceholderText(tr('mm'))
        self.e_angside.textChanged.connect(lambda _t: self._iso_autofill())
        _al.addWidget(self.e_angside)
        self.cb_angside = QComboBox()
        for _k, _lab in (("shorter", tr('shorter side')),
                         ("longer", tr('longer side'))):
            self.cb_angside.addItem(_lab, _k)
        self.cb_angside.setToolTip(
            tr('Shorter side sets the band. With only the longer side, the '
               'shorter is unknown, so the widest band is used.'))
        self.cb_angside.activated.connect(lambda _i: self._iso_autofill())
        _al.addWidget(self.cb_angside)
        _al.addStretch(1)
        self.v_angside = Var(self.e_angside.text, self.e_angside.setText)
        g.addWidget(self.lbl_angside, r, 0, Qt.AlignLeft)
        g.addWidget(self.w_angside, r, 1, Qt.AlignLeft)
        r += 1

        self.chk_inv = QCheckBox(tr('Invert from opposite edge'))
        self.v_inv = Var(self.chk_inv.isChecked, self.chk_inv.setChecked)
        self.chk_inv.toggled.connect(lambda _b: self._toggle_inv())
        g.addWidget(self.chk_inv, r, 0, 1, 2, Qt.AlignLeft)
        r += 1
        g.addWidget(QLabel(tr('Overall')), r, 0, Qt.AlignLeft)
        self.e_ref = _line_edit(110)
        self.e_ref.setEnabled(False)
        self.v_ref = Var(self.e_ref.text, self.e_ref.setText)
        g.addWidget(self.e_ref, r, 1, Qt.AlignLeft)
        r += 1

        # worst kept
        g.addWidget(QLabel(tr('Qty ×')), r, 0, Qt.AlignLeft)
        self.sp_qty = QSpinBox()
        self.sp_qty.setRange(1, 999)
        self.sp_qty.setValue(1)
        self.sp_qty.setMaximumWidth(70)
        self.sp_qty.setToolTip(
            tr('Number of instances, printed as 2X. Bubble it to count '
               'them and measure each one.'))
        self.v_qty = Var(lambda: self.sp_qty.value(),
                         lambda s: self.sp_qty.setValue(
                             int(float(str(s).replace(",", ".") or 1))))
        qw = QWidget()
        ql = QHBoxLayout(qw)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.addWidget(self.sp_qty)
        from .scanrows import facet_skipped as _fs
        self.chk_qty = QCheckBox(tr('Bubble it'))
        self.chk_qty.setChecked(bool(qty_on) if qty_on is not None
                                else not _fs("qty", self.cfg))
        self.chk_qty.setToolTip(tr(
            'Add a count row, and take a reading per instance. Settings '
            'sets the default and whether the report keeps the worst or '
            'the average.'))
        ql.addWidget(self.chk_qty)
        ql.addStretch(1)
        g.addWidget(qw, r, 1, Qt.AlignLeft)
        r += 1

        dpw = QWidget()
        dpl = QHBoxLayout(dpw)
        dpl.setContentsMargins(0, 0, 0, 0)
        dpl.addWidget(QLabel(tr('Depth:')))
        self.e_dep = _line_edit(70)
        self.e_dep.setEnabled(False)
        dpl.addWidget(self.e_dep)
        dpl.addWidget(QLabel(tr('CBore Ø:')))
        self.e_cbd = _line_edit(70)
        self.e_cbd.setEnabled(False)
        dpl.addWidget(self.e_cbd)
        dpl.addWidget(QLabel(tr('depth:')))
        self.e_cbz = _line_edit(70)
        self.e_cbz.setEnabled(False)
        dpl.addWidget(self.e_cbz)
        dpl.addStretch(1)
        self.v_dep = Var(self.e_dep.text, self.e_dep.setText)
        self.v_cbd = Var(self.e_cbd.text, self.e_cbd.setText)
        self.v_cbz = Var(self.e_cbz.text, self.e_cbz.setText)
        g.addWidget(dpw, r, 0, 1, 2)
        r += 1
        csw = QWidget()
        csl = QHBoxLayout(csw)
        csl.setContentsMargins(0, 0, 0, 0)
        csl.addWidget(QLabel(tr('CSink \u00d8:')))
        self.e_csd = _line_edit(70)
        self.e_csd.setEnabled(False)
        csl.addWidget(self.e_csd)
        csl.addWidget(QLabel(tr('depth:')))
        self.e_csz = _line_edit(70)
        self.e_csz.setEnabled(False)
        csl.addWidget(self.e_csz)
        csl.addStretch(1)
        self.v_csd = Var(self.e_csd.text, self.e_csd.setText)
        self.v_csz = Var(self.e_csz.text, self.e_csz.setText)
        g.addWidget(csw, r, 0, 1, 2)
        r += 1
        tdw = QWidget()
        tdl = QHBoxLayout(tdw)
        tdl.setContentsMargins(0, 0, 0, 0)
        from .scanrows import facet_skipped
        self.chk_tap = QCheckBox(tr('Tap drill \u00d8:'))
        self.chk_tap.setChecked(not facet_skipped("tap_drill", self.cfg))
        self.chk_tap.setToolTip(tr('Bubble the tap drill under this '
                                   'thread too. Settings sets the default.'))
        self.chk_tap.toggled.connect(lambda _on: self._type_changed())
        tdl.addWidget(self.chk_tap)
        self.e_tdd = _line_edit(70)
        self.e_tdd.setEnabled(False)
        tdl.addWidget(self.e_tdd)
        tdl.addWidget(QLabel(tr('depth:')))
        self.e_tdz = _line_edit(70)
        self.e_tdz.setEnabled(False)
        tdl.addWidget(self.e_tdz)
        tdl.addStretch(1)
        self.v_tdd = Var(self.e_tdd.text, self.e_tdd.setText)
        self.v_tdz = Var(self.e_tdz.text, self.e_tdz.setText)
        g.addWidget(tdw, r, 0, 1, 2)
        r += 1

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        g.addWidget(sep, r, 0, 1, 2)
        r += 1

        self.lbl_ipre = QLabel("")
        if self.iso_on:
            self.lbl_ipre.setStyleSheet("color:#1f6e3c;")
            g.addWidget(self.lbl_ipre, r, 0, 1, 2, Qt.AlignLeft)
        else:
            tip = QLabel(tr('Tolerance: ± value, or ISO 286 fit (H7, g6, js9);'
                            ' max/min overrides'))
            tip.setStyleSheet("color:#777; font-size:8pt;")
            g.addWidget(tip, r, 0, 1, 2, Qt.AlignLeft)
        self.v_ipre = Var(self.lbl_ipre.text, self.lbl_ipre.setText)
        r += 1

        g.addWidget(QLabel(tr('tol ±')), r, 0, Qt.AlignLeft)
        self.e_tsym = _line_edit(110)
        self.e_tsym.setText(last.get("tsym", ""))
        self.v_tsym = Var(self.e_tsym.text, self.e_tsym.setText)
        if self.e_tsym.text():
            self._tsym_user = True
        self.e_tsym.textEdited.connect(lambda _t: self._tsym_typed())
        g.addWidget(self.e_tsym, r, 1, Qt.AlignLeft)
        r += 1
        g.addWidget(QLabel(tr('tol max')), r, 0, Qt.AlignLeft)
        self.e_tmax = _line_edit(110)
        self.e_tmax.setText(last.get("tmax", ""))
        self.v_tmax = Var(self.e_tmax.text, self.e_tmax.setText)
        self.e_tmax.textEdited.connect(lambda _t: self._mm_typed())
        g.addWidget(self.e_tmax, r, 1, Qt.AlignLeft)
        r += 1
        g.addWidget(QLabel(tr('tol min')), r, 0, Qt.AlignLeft)
        self.e_tmin = _line_edit(110)
        self.e_tmin.setText(last.get("tmin", ""))
        self.v_tmin = Var(self.e_tmin.text, self.e_tmin.setText)
        self.e_tmin.textEdited.connect(lambda _t: self._mm_typed())
        g.addWidget(self.e_tmin, r, 1, Qt.AlignLeft)
        if self.e_tmax.text() or self.e_tmin.text():
            self._mm_user = True
        r += 1

        g.addWidget(QLabel(tr('Pin Ø')), r, 0, Qt.AlignLeft)
        self.e_pin = _line_edit(110)
        self.v_pin = Var(self.e_pin.text, self.e_pin.setText)
        g.addWidget(self.e_pin, r, 1, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel(tr('Comment')), r, 0, Qt.AlignLeft)
        self.e_comment = _line_edit(220)
        self.v_comment = Var(self.e_comment.text, self.e_comment.setText)
        g.addWidget(self.e_comment, r, 1, Qt.AlignLeft)
        r += 1

        self.chk_leader = QCheckBox(tr('Leader line'))
        self.chk_leader.setChecked(True if leader_default is None
                                   else bool(leader_default))
        self.v_leader = Var(self.chk_leader.isChecked,
                            self.chk_leader.setChecked)
        g.addWidget(self.chk_leader, r, 0, 1, 2, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel(tr('Tier')), r, 0, Qt.AlignLeft)
        self.cb_tier = QComboBox()
        # blank tier means auto
        fill_keyed(self.cb_tier, TIERS, last.get("tier", ""))
        self.cb_tier.setItemText(0, tr('auto'))
        self.v_tier = Var(lambda: combo_key(self.cb_tier),
                          lambda v: set_combo_key(self.cb_tier, v))
        g.addWidget(self.cb_tier, r, 1, Qt.AlignLeft)
        r += 1

        bw = QWidget()
        bl = QHBoxLayout(bw)
        bl.setContentsMargins(0, 8, 0, 0)
        if not self.edit:
            b_sub = QPushButton(tr('Add sub-dim'))
            b_sub.setAutoDefault(False)
            b_sub.clicked.connect(self._sub)
            bl.addWidget(b_sub)
        b_ok = QPushButton(tr('OK'))
        b_ok.setDefault(True)
        b_ok.setAutoDefault(True)
        b_ok.clicked.connect(self._ok)
        bl.addWidget(b_ok)
        b_cancel = QPushButton(tr('Cancel'))
        b_cancel.setAutoDefault(False)
        b_cancel.clicked.connect(self._cancel)
        bl.addWidget(b_cancel)
        g.addWidget(bw, r, 0, 1, 2)

        if edit_row:
            self._prefill(edit_row)
            for f, var in (("depth", self.v_dep), ("cbore", self.v_cbd),
                           ("cbore_depth", self.v_cbz), ("csink", self.v_csd),
                           ("csink_depth", self.v_csz),
                           ("tap_drill", self.v_tdd),
                           ("tap_drill_depth", self.v_tdz)):
                s = self._siblings.get(f)
                if s is not None and s.get("nominal") is not None:
                    var.set(_num_text(s["nominal"]))
            if "tap_drill" in self._siblings:
                self.chk_tap.setChecked(True)
        elif prefill:
            self._prefill(prefill)

        self._type_changed(False)
        self._sync_angside()
        self._iso_autofill()
        if at:
            self.move(int(at[0]), int(at[1]))
        for e in self._unit_fields():
            e.editingFinished.connect(
                lambda e=e: self._convert_units(e))
            if not e.toolTip():
                e.setToolTip(tr('Type a unit to convert it: 1.5in or '
                                '25.4mm becomes the drawing\'s unit.'))
        retranslate(self)
        self.e_nom.setFocus()

    def _unit_fields(self):
        return [getattr(self, n) for n in (
            # not angle side, 2768 angle table mm
            "e_nom", "e_ref", "e_dep", "e_cbd", "e_cbz", "e_csd", "e_csz",
            "e_tdd", "e_tdz", "e_tsym", "e_tmax", "e_tmin", "e_pin")
            if getattr(self, n, None) is not None]

    def _convert_units(self, e):
        out = convert_unit_text(e.text(), units_of(self.cfg, self.session))
        if out is None or out == e.text():
            return False
        e.setText(out)
        if e is self.e_nom:
            self._iso_autofill()
        return True

    def _record_geo(self):
        self.last_geo = (self.x(), self.y())

    def _prefill(self, d):
        if d.get("type"):
            self.v_type.set(d["type"])
        if d.get("qty"):
            self.v_qty.set(d["qty"])
        if d.get("tier"):
            self.v_tier.set(d["tier"])
        if d.get("feature"):
            self.v_feat.set(d["feature"])
        if d.get("nominal") is not None:
            self.v_nom.set(_num_text(d["nominal"]))
        if d.get("pin") is not None:
            self.v_pin.set(_num_text(d["pin"]))
        if d.get("comment"):
            self.v_comment.set(str(d["comment"]))
        # bound rides through, no control
        self._limit = d.get("limit")
        if "tier" in d and self.edit:
            self.v_tier.set(d.get("tier") or "")
        self.v_tsym.set("")
        self.v_tmax.set("")
        self.v_tmin.set("")
        self._tsym_user = False
        self._mm_user = False
        self._no_gentol = bool(d.get("no_gentol"))
        # reader's flag holds while row unchanged
        self._flag_key = (self.v_type.get(), self.v_feat.get())
        self.chk_edge.setChecked(bool(d.get("edge_break")))
        if d.get("tol_sym") is not None:
            self.v_tsym.set(_num_text(d["tol_sym"]))
            self._tsym_user = True
        elif d.get("tol_max") is not None or d.get("tol_min") is not None:
            if d.get("tol_max") is not None:
                self.v_tmax.set(_num_text(d["tol_max"]))
            if d.get("tol_min") is not None:
                self.v_tmin.set(_num_text(d["tol_min"]))
            self._mm_user = True

    def _feat_changed(self):
        self._sync_angside()
        self._iso_autofill()

    def _sync_angside(self):
        on = (not self._ang_short) and is_angle_feature(self.v_feat.get())
        self.lbl_angside.setVisible(on)
        self.w_angside.setVisible(on)
        self._sync_edge()

    def _sync_edge(self):
        feat = self.v_feat.get()
        on = is_radius_feature(feat) and not is_broken_edge(feat)
        self.chk_edge.setVisible(on)
        if not on and self.chk_edge.isChecked():
            self.chk_edge.setChecked(False)

    def _build_group(self, g, r, rows, at):
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
        g.addWidget(QLabel(tr('Rows under this balloon')), r, 0, 1, 2,
                    Qt.AlignLeft)
        r += 1
        t = QTableWidget(len(rows), 4)
        t.setHorizontalHeaderLabels([tr('No.'), tr('Type'), tr('Feature'),
                                     tr('Requirement')])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setSelectionMode(QTableWidget.SingleSelection)
        for i, row in enumerate(rows):
            for c, key in enumerate(("bubble", "type", "feature",
                                     "requirement")):
                txt = str(row.get(key) or "")
                if key == "type":
                    txt = tr(txt) if txt else ""
                t.setItem(i, c, QTableWidgetItem(txt))
        t.resizeColumnsToContents()
        t.setMaximumHeight(min(160, 30 + 24 * len(rows)))
        t.selectRow(max(0, min(at, len(rows) - 1)))
        self._group_at = at
        t.cellClicked.connect(self._group_pick)
        g.addWidget(t, r, 0, 1, 3)
        self._group_tbl = t
        return r + 1

    def _group_pick(self, row, _col=0):
        """Apply this row first, caller opens `switch_to`."""
        if row == self._group_at:
            return
        self.result_rows = None
        self.switch_to = row
        self._ok()
        if self.result_rows is None:
            self.switch_to = None
            self._group_tbl.selectRow(self._group_at)

    def _side_mm(self):
        if self._ang_short:
            return ANGLE_SHORTEST_SIDE
        if self.cb_angside.currentData() != "shorter":
            return ANGLE_SHORTEST_SIDE
        return _num(self.v_angside.get(), tr('Angle side'))

    def _gentol(self, nom, raw=None):
        if self.edit:
            return None
        feat = self.v_feat.get()
        if raw is None:
            raw = self.v_nom.get() or feat
        return general_tol({"type": self.v_type.get(), "feature": feat,
                            "v": raw, "nominal": nom,
                            "edge_break": self.chk_edge.isChecked(),
                            "no_gentol": self._flagged()},
                           self.gtols, self.cfg, self.session,
                           icls=self.icls, iso_on=self.iso_on,
                           side_mm=self._side_mm()).value

    def _gentol_why(self):
        why = gentol_exempt({"type": self.v_type.get(),
                             "feature": self.v_feat.get(),
                             "v": self.v_nom.get() or self.v_feat.get(),
                             "limit": getattr(self, "_limit", None)},
                            self.cfg)
        return why or ("flagged" if self._flagged() else None)

    def _flagged(self):
        """Capture exemption, only while row still as read."""
        return (self._no_gentol and (self.v_type.get(), self.v_feat.get())
                == getattr(self, "_flag_key", None))

    def _iso_excluded(self):
        return self._gentol_why() is not None

    def _iso_ladder(self):
        return gentol_ladder(self.cfg, self.session) == "iso2768"

    def _type_changed(self, user=False):
        t = self.v_type.get()
        hole = t.startswith(("hole", "thru"))
        st = hole and (not self.edit or self._facet_edit)
        for e in (self.e_dep, self.e_cbd, self.e_cbz, self.e_csd, self.e_csz):
            e.setEnabled(st)
        tap = (t.startswith("thread")
               and (not self.edit or self._facet_edit))
        self.chk_tap.setEnabled(tap)
        for e in (self.e_tdd, self.e_tdz):
            e.setEnabled(tap and self.chk_tap.isChecked())
        dimensional = t != "GD&T" and not t.startswith("finish")
        self.e_pin.setEnabled(dimensional)
        self.chk_inv.setEnabled(dimensional)
        if not dimensional:
            self.v_pin.set("")
            if self.v_inv.get():
                self.v_inv.set(False)
        if self.iso_on:
            if self._iso_excluded():
                self.lbl_ipre.setStyleSheet("color:#888;")
            else:
                self.lbl_ipre.setStyleSheet("color:#1f6e3c;")
            self._iso_autofill()

    def _toggle_inv(self):
        self.e_ref.setEnabled(bool(self.v_inv.get()))

    def _tsym_typed(self):
        self._tsym_user = True
        self._tsym_sticky = True

    def _mm_typed(self):
        self._mm_user = True
        self._mm_sticky = True
        self.v_tsym.set("")
        self._tsym_user = False
        self._tsym_sticky = False

    def _iso_autofill(self):
        if not self.iso_on:
            return
        if self._tsym_user or self._mm_user or \
                self.v_tmax.get().strip() or self.v_tmin.get().strip():
            return
        if not self._iso_ladder():
            return
        if units_of(self.cfg, self.session) != "iso_mm":
            return
        why = self._gentol_why()
        if why:
            self.v_tsym.set("")
            self.v_ipre.set(tr('BASIC or REF: no general tolerance')
                            if why == "basic or ref"
                            else tr('ISO 2768 n/a for this type'))
            return
        try:
            nom = fnum(self.v_nom.get())
        except ValueError:
            nom = None
        angle = is_angle_feature(self.v_feat.get())
        t = self._gentol(nom)
        if t is not None:
            self.v_tsym.set("%g" % t)
            self.v_ipre.set("ISO 2768-%s → ±%g%s"
                            % (self.icls, t, "°" if angle else ""))
        else:
            self.v_tsym.set("")
            if angle:
                self.v_ipre.set(tr('Angle: enter side length in mm'))
            else:
                self.v_ipre.set("ISO 2768-%s: %s" % (
                    self.icls, tr('out of table')
                    if nom is not None else tr('auto from nominal')))

    def _metric(self):
        return units_of(self.cfg, self.session) == "iso_mm"

    def _resolve_tol(self, nom, raw=None):
        out = {"tol_sym": None, "tol_max": None, "tol_min": None}
        raw_sym = self.v_tsym.get().strip()
        if self._metric() and is_fit_code(raw_sym):
            if nom is None:
                raise ValueError(
                    tr('Fit %s needs nominal')
                    % raw_sym)
            lim = fit_limits(nom, raw_sym)
            if lim is None:
                raise ValueError(
                    tr('ISO 286: %s not supported at %g mm')
                    % (raw_sym, nom))
            out["tol_max"], out["tol_min"] = lim
            return out
        if is_fit_code(raw_sym):
            # ISO fit on inch drawing unread
            raise ValueError(
                tr('Fit %s is an ISO 286 code for millimetre sizes. This '
                   'drawing is in inches: enter the tolerance as numbers '
                   'instead.') % raw_sym)
        tmax = _tol_num(self.v_tmax.get())
        tmin = _tol_num(self.v_tmin.get())
        tsym = _tol_num(self.v_tsym.get())
        if tmax is not None or tmin is not None:
            out["tol_max"], out["tol_min"] = tmax, tmin
        elif tsym is not None:
            out["tol_sym"] = tsym
        else:
            t = self._gentol(nom, raw=raw)
            if t is not None:
                out["tol_sym"] = t
        return out

    def _tol_for_feature(self, nom, is_dia=False, raw=None):
        raw_sym = self.v_tsym.get().strip()
        if self._metric() and is_fit_code(raw_sym) and not is_dia:
            # fit code is diameter's
            out = {"tol_sym": None, "tol_max": None, "tol_min": None}
            t = self._gentol(nom, raw=raw)
            if t is not None:
                out["tol_sym"] = t
            return out
        return self._resolve_tol(nom, raw=raw)

    def _pin_for(self, nom, is_dia):
        p = _num(self.v_pin.get(), tr('Pin \u00d8'))
        if p is not None:
            return p if is_dia else None
        if is_dia and nom is not None and \
                self.cfg.get("hole_pin_auto", False):
            return nom
        return None

    def _collect(self):
        for e in self._unit_fields():  # OK before leaving
            self._convert_units(e)
        try:
            nom = fnum(self.v_nom.get())
        except ValueError:
            nom = None
        feat = self.v_feat.get().strip()
        if nom is not None and self.v_inv.get():
            ref = _num(self.v_ref.get(), tr('Overall'))
            if ref is None:
                raise ValueError(tr('Invert needs overall'))
            inv = round(ref - nom, 4)
            feat = (feat + " " if feat else "") + "(inv %g z/of %g)" % (nom, ref)
            nom = inv
        t = self.v_type.get()
        hole = t.startswith(("hole", "thru"))
        if not feat and nom is not None:
            un = units_of(self.cfg, self.session)
            if hole:
                feat = u"Ø%s" % format_nominal(nom, un)
            elif t.startswith("slot"):
                feat = "slot %s" % format_nominal(nom, un)
            elif t.startswith("depth"):
                feat = "depth %s" % format_nominal(nom, un)
            else:
                feat = format_nominal(nom, un)
        base = {"type": t,
                "tier": self.v_tier.get(), "pin": None,
                "offset": None, "measured": None}
        if self.chk_edge.isChecked():
            base["edge_break"] = True          # only written when true
        if self.v_qty.get() > 1:
            base["qty"] = self.v_qty.get()
        tol = self._resolve_tol(nom, raw=self.v_nom.get())

        dep = _num(self.v_dep.get(), tr('Depth')) if hole else None
        cbd = _num(self.v_cbd.get(), tr('CBore \u00d8')) if hole else None
        cbz = _num(self.v_cbz.get(), tr('CBore depth')) if hole else None
        if cbz is not None and cbd is None:
            raise ValueError(tr('CBore depth needs CBore Ø'))
        csd = _num(self.v_csd.get(), tr('CSink \u00d8')) if hole else None
        csz = _num(self.v_csz.get(), tr('CSink depth')) if hole else None
        if csz is not None and csd is None:
            raise ValueError(tr('CSink depth needs CSink \u00d8'))
        tapped = t.startswith("thread") and self.chk_tap.isChecked()
        tdd = _num(self.v_tdd.get(), tr('Tap drill \u00d8')) if tapped \
            else None
        tdz = _num(self.v_tdz.get(), tr('Tap drill depth')) if tapped \
            else None
        if tdz is not None and tdd is None:
            raise ValueError(tr('Tap drill depth needs tap drill \u00d8'))

        def row(ft, nm, is_dia=False, typ=None, raw=None):
            d = dict(base)
            d.update(self._tol_for_feature(nm, is_dia, raw=raw))
            d["feature"] = ft
            d["nominal"] = nm
            d["pin"] = self._pin_for(nm, is_dia)
            if typ:
                d["type"] = typ
            return d

        def extras(tag=""):
            made = {}
            if dep is not None:
                made["depth"] = row(("depth%s" % tag), dep, typ="depth",
                                    raw=self.v_dep.get())
            if cbd is not None:
                made["cbore"] = row((u"cbore \u00d8%s" % tag), cbd,
                                    is_dia=True, raw=self.v_cbd.get())
            if cbz is not None:
                made["cbore_depth"] = row(("cbore depth%s" % tag), cbz,
                                          typ="depth", raw=self.v_cbz.get())
            if csd is not None:
                made["csink"] = row((u"csink \u00d8%s" % tag), csd,
                                    is_dia=True, raw=self.v_csd.get())
            if csz is not None:
                made["csink_depth"] = row(("csink depth%s" % tag), csz,
                                          typ="depth", raw=self.v_csz.get())
            if tdd is not None:
                made["tap_drill"] = row((u"tap drill \u00d8%s" % tag), tdd,
                                        is_dia=True, typ="hole",
                                        raw=self.v_tdd.get())
            if tdz is not None:
                made["tap_drill_depth"] = row(("tap drill depth%s" % tag),
                                              tdz, typ="depth",
                                              raw=self.v_tdz.get())
            for f, r_ in made.items():
                r_["facet"] = f
            return [made[f] for f in facet_order(self.cfg) if f in made]

        suffix = ""
        if self.sub_idx > 0:
            suffix = chr(ord("a") + self.sub_idx - 1)
        d = dict(base)
        d.update(tol)
        d["bubble"] = "%s%s" % (self.bubble_no, suffix)
        d["feature"] = feat
        d["nominal"] = nom
        d["pin"] = self._pin_for(nom, hole)
        d["comment"] = self.v_comment.get().strip()  # main row only
        lim = getattr(self, "_limit", None)
        if lim and keeps_limit(d, lim):
            d["limit"] = lim
        rows = [d]
        if self._facet_edit and (hole or t.startswith("thread")):
            # blank facet means removed
            d["facet"] = "hole"
            rows.extend(extras())
        elif not self.edit:
            ex = extras()
            for x in ex:
                x["bubble"] = str(self.bubble_no)
            rows.extend(ex)
            if ex:
                d["facet"] = "hole"
                order = facet_order(self.cfg)
                rows.sort(key=lambda r_: order.index(r_["facet"]))
        for _r in rows:
            _r["leader"] = bool(self.v_leader.get())
        return rows

    def _push(self):
        rows = self._collect()
        self.rows.extend(rows)
        if (len(self.rows) == 2 and
                not str(self.rows[0]["bubble"])[-1:].isalpha()):
            self.rows[0]["bubble"] = "%sa" % self.bubble_no

    def _sub(self):
        try:
            self._push()
            self._limit = None
        except ValueError as e:
            QMessageBox.critical(self, tr('Error'), str(e))
            return
        self.sub_idx = len(self.rows)
        for v in (self.v_feat, self.v_nom, self.v_pin, self.v_ref,
                  self.v_dep, self.v_cbd, self.v_cbz, self.v_csd,
                  self.v_csz, self.v_tdd, self.v_tdz, self.v_comment):
            v.set("")
        self.v_qty.set(1)
        self.v_inv.set(False)
        for v in (self.v_tsym, self.v_tmax, self.v_tmin):
            v.set("")
        self._tsym_user = False
        self._mm_user = False
        self._no_gentol = False        # fresh sub-row not BASIC/REF
        self.v_angside.set("")
        self._sync_angside()
        self._toggle_inv()
        self.setWindowTitle(tr('Bubble') + " #%s%s" % (
            self.bubble_no, chr(ord("a") + self.sub_idx)))

    def _snapshot(self):
        out = {"tier": self.v_tier.get()}
        raw_sym = self.v_tsym.get().strip()
        if self._tsym_sticky and raw_sym:
            out["tsym"] = raw_sym
            out["tmax"] = out["tmin"] = ""
        elif self._mm_sticky and (self.v_tmax.get().strip() or
                                  self.v_tmin.get().strip()):
            out["tmax"] = self.v_tmax.get().strip()
            out["tmin"] = self.v_tmin.get().strip()
            out["tsym"] = ""
        return out

    def _ok(self):
        try:
            self._push()
        except ValueError as e:
            QMessageBox.critical(self, tr('Error'), str(e))
            return
        self.result_rows = self.rows
        self.qty_ticked = bool(self.chk_qty.isChecked())
        self.last_out = self._snapshot()
        self.new_number = None
        if self.v_bubnum is not None:
            try:
                self.new_number = int(
                    float(self.v_bubnum.get().replace(",", ".")))
            except ValueError:
                pass
        self._record_geo()
        self.accept()

    def _cancel(self):
        self.result_rows = None
        self._record_geo()
        self.reject()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.result_rows is None:
            self._record_geo()
        super().closeEvent(e)
