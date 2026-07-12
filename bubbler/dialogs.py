# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble entry/edit dialog. Tolerance + hole-pattern rows.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QVBoxLayout,
                               QLabel, QLineEdit, QComboBox, QCheckBox,
                               QSpinBox, QPushButton, QFrame, QWidget,
                               QMessageBox)

from .common import TYPES, TIERS, fnum, dp_tol
from .config import units_of
from .widgets import fill_keyed, combo_key, set_combo_key
from .iso2768 import iso2768_tol
from .iso286 import fit_limits, is_fit_code
from .i18n import tr, retranslate


class Var(object):
    """Qt widget as get/set."""

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


class BubbleDialog(QDialog):
    """Entry/edit for one balloon. Create mode can emit sub-rows."""

    def __init__(self, parent, bubble_no, last=None, at=None, cfg=None,
                 edit_row=None, prefill=None, leader_default=None):
        super().__init__(parent)
        self.edit = edit_row is not None
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
        if last is None:
            last = {"type": cfg.get("default_type", TYPES[0]),
                    "tier": cfg.get("default_tier", ""),
                    "iso_on": bool(cfg.get("rib_iso_on")),
                    "icls": cfg.get("default_iso_class", "m")}
        self.iso_on = bool(last.get("iso_on")) and not self.edit
        self.icls = str(last.get("icls", "m"))
        self._tsym_user = False
        self._mm_user = False
        self._tsym_sticky = False
        self._mm_sticky = False

        g = QGridLayout(self)
        r = 0

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
        g.addWidget(self.e_feat, r, 1, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel(tr('Nominal')), r, 0, Qt.AlignLeft)
        self.e_nom = _line_edit(110)
        self.v_nom = Var(self.e_nom.text, self.e_nom.setText)
        self.e_nom.textChanged.connect(lambda _t: self._iso_autofill())
        g.addWidget(self.e_nom, r, 1, Qt.AlignLeft)
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
            tr('Quantity of instances; the measure walk takes that many '
               'readings and keeps the worst.'))
        self.v_qty = Var(lambda: self.sp_qty.value(),
                         lambda s: self.sp_qty.setValue(
                             int(float(str(s).replace(",", ".") or 1))))
        g.addWidget(self.sp_qty, r, 1, Qt.AlignLeft)
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

        self.chk_leader = QCheckBox(tr('Leader line'))
        self.chk_leader.setChecked(True if leader_default is None
                                   else bool(leader_default))
        self.v_leader = Var(self.chk_leader.isChecked,
                            self.chk_leader.setChecked)
        g.addWidget(self.chk_leader, r, 0, 1, 2, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel(tr('Tier')), r, 0, Qt.AlignLeft)
        self.cb_tier = QComboBox()
        self.cb_tier.addItems(TIERS)
        self.cb_tier.setCurrentText(last.get("tier", ""))
        self.v_tier = Var(self.cb_tier.currentText, self.cb_tier.setCurrentText)
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
        elif prefill:
            self._prefill(prefill)

        self._type_changed(False)
        self._iso_autofill()
        if at:
            self.move(int(at[0]), int(at[1]))
        retranslate(self)
        self.e_nom.setFocus()

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
            self.v_nom.set("%g" % d["nominal"])
        if d.get("pin") is not None:
            self.v_pin.set("%g" % d["pin"])
        if "tier" in d and self.edit:
            self.v_tier.set(d.get("tier") or "")
        self.v_tsym.set("")
        self.v_tmax.set("")
        self.v_tmin.set("")
        self._tsym_user = False
        self._mm_user = False
        if d.get("tol_sym") is not None:
            self.v_tsym.set("%g" % d["tol_sym"])
            self._tsym_user = True
        elif d.get("tol_max") is not None or d.get("tol_min") is not None:
            if d.get("tol_max") is not None:
                self.v_tmax.set("%g" % d["tol_max"])
            if d.get("tol_min") is not None:
                self.v_tmin.set("%g" % d["tol_min"])
            self._mm_user = True

    def _iso_excluded(self):
        t = self.v_type.get()
        return (t.startswith("thread") or t == "GD&T"
                or t.startswith("finish") or t.startswith("position"))

    def _iso_auto(self):
        return (self.iso_on and not self._iso_excluded()
                and units_of(self.cfg) == "iso_mm")

    def _type_changed(self, user=False):
        t = self.v_type.get()
        hole = t.startswith(("hole", "thru"))
        st = hole and not self.edit
        for e in (self.e_dep, self.e_cbd, self.e_cbz):
            e.setEnabled(st)
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
        if units_of(self.cfg) != "iso_mm":
            return
        if self._iso_excluded():
            self.v_tsym.set("")
            self.v_ipre.set(tr('ISO 2768 n/a for this type'))
            return
        try:
            nom = fnum(self.v_nom.get())
        except ValueError:
            nom = None
        t = iso2768_tol(nom, self.icls)
        if t is not None:
            self.v_tsym.set("%g" % t)
            self.v_ipre.set("ISO 2768-%s → ±%g" % (self.icls, t))
        else:
            self.v_tsym.set("")
            self.v_ipre.set("ISO 2768-%s: %s" % (
                self.icls, tr('out of table')
                if nom is not None else tr('auto from nominal')))

    def _metric(self):
        return units_of(self.cfg) == "iso_mm"

    def _resolve_tol(self, nom, raw=None):
        out = {"tol_sym": None, "tol_max": None, "tol_min": None}
        raw_sym = self.v_tsym.get().strip()
        if self._metric() and is_fit_code(raw_sym):
            if nom is None:
                raise ValueError(
                    tr('Fit %s needs a nominal')
                    % raw_sym)
            lim = fit_limits(nom, raw_sym)
            if lim is None:
                raise ValueError(
                    tr('ISO 286: %s not supported at %g mm')
                    % (raw_sym, nom))
            out["tol_max"], out["tol_min"] = lim
            return out
        tmax = fnum(self.v_tmax.get())
        tmin = fnum(self.v_tmin.get())
        tsym = fnum(self.v_tsym.get())
        if tmax is not None or tmin is not None:
            out["tol_max"], out["tol_min"] = tmax, tmin
        elif tsym is not None:
            out["tol_sym"] = tsym
        elif self._iso_auto():
            t = iso2768_tol(nom, self.icls)
            if t is None:
                t = dp_tol(raw if raw is not None else nom, self.cfg)
            if t is not None:
                out["tol_sym"] = t
        elif not self.edit:
            t = dp_tol(raw if raw is not None else nom, self.cfg)
            if t is not None:
                out["tol_sym"] = t
        return out

    def _tol_for_feature(self, nom, is_dia=False, raw=None):
        raw_sym = self.v_tsym.get().strip()
        fit = self._metric() and is_fit_code(raw_sym)
        if fit and not is_dia:
            out = {"tol_sym": None, "tol_max": None, "tol_min": None}
            t = iso2768_tol(nom, self.icls) if self._iso_auto() else None
            if t is None:
                t = dp_tol(raw if raw is not None else nom, self.cfg)
            if t is not None:
                out["tol_sym"] = t
            return out
        typed = (fit or self._tsym_user or self._mm_user or
                 self.v_tmax.get().strip() or self.v_tmin.get().strip() or
                 raw_sym)
        if typed or not self._iso_auto():
            return self._resolve_tol(nom, raw=raw)
        out = {"tol_sym": None, "tol_max": None, "tol_min": None}
        t = iso2768_tol(nom, self.icls)
        if t is not None:
            out["tol_sym"] = t
        return out

    def _pin_for(self, nom, is_dia):
        p = fnum(self.v_pin.get())
        if p is not None:
            return p if is_dia else None
        if is_dia and nom is not None and \
                self.cfg.get("hole_pin_auto", False):
            return nom
        return None

    def _collect(self):
        try:
            nom = fnum(self.v_nom.get())
        except ValueError:
            nom = None
        feat = self.v_feat.get().strip()
        if nom is not None and self.v_inv.get():
            ref = fnum(self.v_ref.get())
            if ref is None:
                raise ValueError(tr('Invert needs overall'))
            inv = round(ref - nom, 4)
            feat = (feat + " " if feat else "") + "(inv %g z/of %g)" % (nom, ref)
            nom = inv
        t = self.v_type.get()
        hole = t.startswith(("hole", "thru"))
        if not feat and nom is not None:
            if hole:
                feat = u"Ø%.2f" % nom
            elif t.startswith("slot"):
                feat = "slot %.2f" % nom
            elif t.startswith("depth"):
                feat = "depth %.2f" % nom
            else:
                feat = "%.2f" % nom
        base = {"type": t,
                "tier": self.v_tier.get(), "pin": None,
                "offset": None, "measured": None}
        if self.v_qty.get() > 1:
            base["qty"] = self.v_qty.get()
        tol = self._resolve_tol(nom, raw=self.v_nom.get())

        dep = fnum(self.v_dep.get()) if hole else None
        cbd = fnum(self.v_cbd.get()) if hole else None
        cbz = fnum(self.v_cbz.get()) if hole else None
        if cbz is not None and cbd is None:
            raise ValueError(tr('CBore depth needs CBore Ø'))

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
            out = []
            if dep is not None:
                out.append(row(("depth%s" % tag), dep,
                               typ="depth",
                               raw=self.v_dep.get()))
            if cbd is not None:
                out.append(row((u"cbore Ø%s" % tag), cbd, is_dia=True,
                               raw=self.v_cbd.get()))
            if cbz is not None:
                out.append(row(("cbore depth%s" % tag), cbz,
                               typ="depth",
                               raw=self.v_cbz.get()))
            return out

        suffix = ""
        if self.sub_idx > 0:
            suffix = chr(ord("a") + self.sub_idx - 1)
        d = dict(base)
        d.update(tol)
        d["bubble"] = "%s%s" % (self.bubble_no, suffix)
        d["feature"] = feat
        d["nominal"] = nom
        d["pin"] = self._pin_for(nom, hole)
        rows = [d]
        if not self.edit:
            ex = extras()
            for x in ex:
                x["bubble"] = str(self.bubble_no)
            rows.extend(ex)
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
        except ValueError as e:
            QMessageBox.critical(self, tr('Error'), str(e))
            return
        self.sub_idx = len(self.rows)
        for v in (self.v_feat, self.v_nom, self.v_pin, self.v_ref,
                  self.v_dep, self.v_cbd, self.v_cbz):
            v.set("")
        self.v_qty.set(1)
        self.v_inv.set(False)
        for v in (self.v_tsym, self.v_tmax, self.v_tmin):
            v.set("")
        self._tsym_user = False
        self._mm_user = False
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
