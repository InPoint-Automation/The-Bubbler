# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble entry/edit dialog. Tolerance + hole-pattern rows.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QVBoxLayout,
                               QLabel, QLineEdit, QComboBox, QCheckBox,
                               QSpinBox, QPushButton, QFrame, QWidget,
                               QMessageBox)

from .common import TYPES, GROUPS, TIERS, GROUP_OF, fnum, dp_tol
from .numbering import LETTERS
from .iso2768 import iso2768_tol
from .iso286 import fit_limits, is_fit_code
from .i18n import tr, retranslate


class Var(object):
    """.get()/.set() wrapper over a Qt widget."""

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
        self.setWindowTitle((tr("Edit / Edycja") + " #%s" if self.edit
                             else "Bubble #%s") % bubble_no)
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
            last["group"] = GROUP_OF.get(last["type"], GROUPS[0])
        self.iso_on = bool(last.get("iso_on")) and not self.edit
        self.icls = str(last.get("icls", "m"))
        self._tsym_user = False
        self._mm_user = False
        self._tsym_sticky = False
        self._mm_sticky = False
        self._pin_sticky = False

        g = QGridLayout(self)
        r = 0

        self.v_bubnum = None
        if self.edit:
            g.addWidget(QLabel("No. / Nr"), r, 0, Qt.AlignLeft)
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

        g.addWidget(QLabel("Type / Typ"), r, 0, Qt.AlignLeft)
        self.cb_type = QComboBox()
        self.cb_type.addItems(TYPES)
        self.cb_type.setCurrentText(last.get("type", TYPES[0]))
        self.v_type = Var(self.cb_type.currentText, self.cb_type.setCurrentText)
        self.cb_type.activated.connect(lambda _i: self._type_changed(True))
        g.addWidget(self.cb_type, r, 1, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel("Group / Grupa"), r, 0, Qt.AlignLeft)
        self.cb_group = QComboBox()
        self.cb_group.addItems(GROUPS)
        self.cb_group.setCurrentText(last.get("group", GROUPS[0]))
        self.v_group = Var(self.cb_group.currentText,
                           self.cb_group.setCurrentText)
        g.addWidget(self.cb_group, r, 1, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel("Feature / Cecha"), r, 0, Qt.AlignLeft)
        self.e_feat = _line_edit(220)
        self.v_feat = Var(self.e_feat.text, self.e_feat.setText)
        g.addWidget(self.e_feat, r, 1, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel("Nominal"), r, 0, Qt.AlignLeft)
        self.e_nom = _line_edit(110)
        self.v_nom = Var(self.e_nom.text, self.e_nom.setText)
        self.e_nom.textChanged.connect(lambda _t: self._iso_autofill())
        g.addWidget(self.e_nom, r, 1, Qt.AlignLeft)
        r += 1

        self.chk_inv = QCheckBox("Invert from opposite edge / Odwróć")
        self.v_inv = Var(self.chk_inv.isChecked, self.chk_inv.setChecked)
        self.chk_inv.toggled.connect(lambda _b: self._toggle_inv())
        g.addWidget(self.chk_inv, r, 0, 1, 2, Qt.AlignLeft)
        r += 1
        g.addWidget(QLabel("Overall / Całkowity"), r, 0, Qt.AlignLeft)
        self.e_ref = _line_edit(110)
        self.e_ref.setEnabled(False)
        self.v_ref = Var(self.e_ref.text, self.e_ref.setText)
        g.addWidget(self.e_ref, r, 1, Qt.AlignLeft)
        r += 1

        # advanced hole sub-rows
        self.cb_adv = QCheckBox("Hole XY+Ø sub-rows / Podwiersze XY+Ø")
        self.v_adv = Var(self.cb_adv.isChecked, self.cb_adv.setChecked)
        self.cb_adv.toggled.connect(lambda _b: self._toggle_adv())
        g.addWidget(self.cb_adv, r, 0, 1, 2, Qt.AlignLeft)
        r += 1

        advw = QWidget()
        advl = QHBoxLayout(advw)
        advl.setContentsMargins(0, 0, 0, 0)
        advl.addWidget(QLabel("X:"))
        self.e_hx = _line_edit(70)
        self.e_hx.setEnabled(False)
        advl.addWidget(self.e_hx)
        advl.addWidget(QLabel("Y:"))
        self.e_hy = _line_edit(70)
        self.e_hy.setEnabled(False)
        advl.addWidget(self.e_hy)
        advl.addStretch(1)
        self.v_hx = Var(self.e_hx.text, self.e_hx.setText)
        self.v_hy = Var(self.e_hy.text, self.e_hy.setText)
        g.addWidget(advw, r, 0, 1, 2)
        r += 1

        # per-hole X/Y pattern table
        patw = QWidget()
        patl = QVBoxLayout(patw)
        patl.setContentsMargins(0, 0, 0, 0)
        topl = QHBoxLayout()
        topl.setContentsMargins(0, 0, 0, 0)
        topl.addWidget(QLabel("pattern ×"))
        self.sp_pn = QSpinBox()
        self.sp_pn.setRange(1, 99)
        self.sp_pn.setValue(1)
        self.sp_pn.setEnabled(False)
        self.v_pn = Var(lambda: str(self.sp_pn.value()),
                        lambda s: self.sp_pn.setValue(int(float(
                            str(s).replace(",", ".") or 1))))
        topl.addWidget(self.sp_pn)
        topl.addWidget(QLabel("shared:"))
        self.cmb_share = QComboBox()
        self.cmb_share.addItems(["X & Y differ", "same X as #1",
                                 "same Y as #1"])
        self.cmb_share.setEnabled(False)
        topl.addWidget(self.cmb_share)
        topl.addStretch(1)
        patl.addLayout(topl)
        self.holes_box = QWidget()
        self.holes_grid = QGridLayout(self.holes_box)
        self.holes_grid.setContentsMargins(0, 0, 0, 0)
        self.e_hxs, self.e_hys, self.v_hxs, self.v_hys = [], [], [], []
        patl.addWidget(self.holes_box)
        g.addWidget(patw, r, 0, 1, 2)
        r += 1
        self.sp_pn.valueChanged.connect(lambda _v: self._build_holes())
        self.cmb_share.currentIndexChanged.connect(
            lambda _i: self._apply_share())
        self.e_hx.textChanged.connect(lambda _t: self._mirror_shared())
        self.e_hy.textChanged.connect(lambda _t: self._mirror_shared())
        self._build_holes()

        dpw = QWidget()
        dpl = QHBoxLayout(dpw)
        dpl.setContentsMargins(0, 0, 0, 0)
        dpl.addWidget(QLabel("Depth/Gł.:"))
        self.e_dep = _line_edit(70)
        self.e_dep.setEnabled(False)
        dpl.addWidget(self.e_dep)
        dpl.addWidget(QLabel("CBore Ø:"))
        self.e_cbd = _line_edit(70)
        self.e_cbd.setEnabled(False)
        dpl.addWidget(self.e_cbd)
        dpl.addWidget(QLabel("depth:"))
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
            tip = QLabel("Tolerance: ± value, or ISO 286 fit (H7, g6, js9);"
                         " max/min overrides")
            tip.setStyleSheet("color:#777; font-size:8pt;")
            g.addWidget(tip, r, 0, 1, 2, Qt.AlignLeft)
        self.v_ipre = Var(self.lbl_ipre.text, self.lbl_ipre.setText)
        r += 1

        g.addWidget(QLabel("tol ±"), r, 0, Qt.AlignLeft)
        self.e_tsym = _line_edit(110)
        self.e_tsym.setText(last.get("tsym", ""))
        self.v_tsym = Var(self.e_tsym.text, self.e_tsym.setText)
        if self.e_tsym.text():
            self._tsym_user = True
        self.e_tsym.textEdited.connect(lambda _t: self._tsym_typed())
        g.addWidget(self.e_tsym, r, 1, Qt.AlignLeft)
        r += 1
        g.addWidget(QLabel("tol max"), r, 0, Qt.AlignLeft)
        self.e_tmax = _line_edit(110)
        self.e_tmax.setText(last.get("tmax", ""))
        self.v_tmax = Var(self.e_tmax.text, self.e_tmax.setText)
        self.e_tmax.textEdited.connect(lambda _t: self._mm_typed())
        g.addWidget(self.e_tmax, r, 1, Qt.AlignLeft)
        r += 1
        g.addWidget(QLabel("tol min"), r, 0, Qt.AlignLeft)
        self.e_tmin = _line_edit(110)
        self.e_tmin.setText(last.get("tmin", ""))
        self.v_tmin = Var(self.e_tmin.text, self.e_tmin.setText)
        self.e_tmin.textEdited.connect(lambda _t: self._mm_typed())
        g.addWidget(self.e_tmin, r, 1, Qt.AlignLeft)
        if self.e_tmax.text() or self.e_tmin.text():
            self._mm_user = True
        r += 1

        g.addWidget(QLabel("Pin Ø"), r, 0, Qt.AlignLeft)
        self.e_pin = _line_edit(110)
        self.v_pin = Var(self.e_pin.text, self.e_pin.setText)
        if not self.edit and last.get("pin"):
            self.e_pin.setText(str(last["pin"]))
            self._pin_sticky = True
        self.e_pin.textEdited.connect(
            lambda _t: setattr(self, "_pin_sticky", True))
        g.addWidget(self.e_pin, r, 1, Qt.AlignLeft)
        r += 1

        self.chk_leader = QCheckBox("Leader line / Linia odniesienia")
        self.chk_leader.setChecked(True if leader_default is None
                                   else bool(leader_default))
        self.v_leader = Var(self.chk_leader.isChecked,
                            self.chk_leader.setChecked)
        g.addWidget(self.chk_leader, r, 0, 1, 2, Qt.AlignLeft)
        r += 1

        g.addWidget(QLabel("Tier"), r, 0, Qt.AlignLeft)
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
            b_sub = QPushButton("Add sub-dim / Podwymiar")
            # only OK answers Enter
            b_sub.setAutoDefault(False)
            b_sub.clicked.connect(self._sub)
            bl.addWidget(b_sub)
        b_ok = QPushButton("OK")
        b_ok.setDefault(True)
        b_ok.setAutoDefault(True)
        b_ok.clicked.connect(self._ok)
        bl.addWidget(b_ok)
        b_cancel = QPushButton("Cancel / Anuluj")
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

    # result plumbing
    def _record_geo(self):
        self.last_geo = (self.x(), self.y())

    def _prefill(self, d):
        if d.get("type"):
            self.v_type.set(d["type"])
        if d.get("group"):
            self.v_group.set(d["group"])
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
        # clear tol fields, set only d's mode
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

    def _type_changed(self, user=False):
        t = self.v_type.get()
        if user:
            self.v_group.set(GROUP_OF.get(t, self.v_group.get()))
        hole = t.startswith(("hole", "thru"))
        self.cb_adv.setEnabled(hole and not self.edit)
        st = hole and not self.edit
        for e in (self.e_dep, self.e_cbd, self.e_cbz):
            e.setEnabled(st)
        if not hole:
            self.v_adv.set(False)
            self._toggle_adv()
        # non-linear types skip pin/invert
        dimensional = t != "GD&T" and not t.startswith("finish")
        self.e_pin.setEnabled(dimensional)
        self.chk_inv.setEnabled(dimensional)
        if not dimensional:
            self.v_pin.set("")
            if self.v_inv.get():
                self.v_inv.set(False)

    def _toggle_adv(self):
        st = bool(self.v_adv.get())
        for e in (self.e_hx, self.e_hy, self.sp_pn, self.cmb_share):
            e.setEnabled(st)
        self._apply_share()

    def _share_mode(self):
        return ("", "x", "y")[self.cmb_share.currentIndex()]

    def _build_holes(self):
        """Rebuild holes #2..#n table, keeping typed values."""
        old_x = [v.get() for v in self.v_hxs]
        old_y = [v.get() for v in self.v_hys]
        while self.holes_grid.count():
            w = self.holes_grid.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
        self.e_hxs, self.e_hys, self.v_hxs, self.v_hys = [], [], [], []
        n = self.sp_pn.value()
        if n > 1:
            self.holes_grid.addWidget(QLabel("#"), 0, 0)
            self.holes_grid.addWidget(QLabel("X"), 0, 1)
            self.holes_grid.addWidget(QLabel("Y"), 0, 2)
        for k in range(1, n):              # holes #2..#n
            self.holes_grid.addWidget(QLabel("#%d" % (k + 1)), k, 0)
            ex, ey = _line_edit(70), _line_edit(70)
            if k - 1 < len(old_x):
                ex.setText(old_x[k - 1])
            if k - 1 < len(old_y):
                ey.setText(old_y[k - 1])
            self.holes_grid.addWidget(ex, k, 1)
            self.holes_grid.addWidget(ey, k, 2)
            self.e_hxs.append(ex)
            self.e_hys.append(ey)
            self.v_hxs.append(Var(ex.text, ex.setText))
            self.v_hys.append(Var(ey.text, ey.setText))
        self._apply_share()

    def _apply_share(self):
        adv = bool(self.v_adv.get())
        mode = self._share_mode()
        for ex in self.e_hxs:
            ex.setEnabled(adv and mode != "x")
        for ey in self.e_hys:
            ey.setEnabled(adv and mode != "y")
        self._mirror_shared()

    def _mirror_shared(self):
        """Copy hole #1's constant coordinate into the shared column."""
        mode = self._share_mode()
        if mode == "x":
            for ex in self.e_hxs:
                ex.setText(self.e_hx.text())
        elif mode == "y":
            for ey in self.e_hys:
                ey.setText(self.e_hy.text())

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
                self.icls, "poza tabelą / out of table"
                if nom is not None else "auto from nominal"))

    def _resolve_tol(self, nom, raw=None):
        out = {"tol_sym": None, "tol_max": None, "tol_min": None}
        raw_sym = self.v_tsym.get().strip()
        if is_fit_code(raw_sym):
            if nom is None:
                raise ValueError(
                    "Fit %s needs a nominal / pasowanie wymaga nominału"
                    % raw_sym)
            lim = fit_limits(nom, raw_sym)
            if lim is None:
                raise ValueError(
                    "ISO 286: %s not supported at %g mm / "
                    "nieobsługiwane" % (raw_sym, nom))
            out["tol_max"], out["tol_min"] = lim
            return out
        tmax = fnum(self.v_tmax.get())
        tmin = fnum(self.v_tmin.get())
        tsym = fnum(self.v_tsym.get())
        if tmax is not None or tmin is not None:
            out["tol_max"], out["tol_min"] = tmax, tmin
        elif tsym is not None:
            out["tol_sym"] = tsym
        elif self.iso_on:
            t = iso2768_tol(nom, self.icls)
            if t is None:
                raise ValueError("ISO 2768-%s: out of table / poza tabelą"
                                 % self.icls)
            out["tol_sym"] = t
        elif not self.edit:
            t = dp_tol(raw if raw is not None else nom, self.cfg)
            if t is not None:
                out["tol_sym"] = t
        return out

    def _tol_for_feature(self, nom, is_dia=False, raw=None):
        raw_sym = self.v_tsym.get().strip()
        fit = is_fit_code(raw_sym)
        if fit and not is_dia:
            out = {"tol_sym": None, "tol_max": None, "tol_min": None}
            t = iso2768_tol(nom, self.icls) if self.iso_on else None
            if t is None:
                t = dp_tol(raw if raw is not None else nom, self.cfg)
            if t is not None:
                out["tol_sym"] = t
            return out
        typed = (fit or self._tsym_user or self._mm_user or
                 self.v_tmax.get().strip() or self.v_tmin.get().strip() or
                 raw_sym)
        if typed or not self.iso_on:
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
                self.cfg.get("hole_pin_auto", True):
            return nom
        return None

    def _collect(self):
        nom = fnum(self.v_nom.get())
        feat = self.v_feat.get().strip()
        if nom is not None and self.v_inv.get():
            ref = fnum(self.v_ref.get())
            if ref is None:
                raise ValueError("Invert needs overall / wymiar całkowity")
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
        base = {"type": t, "group": self.v_group.get(),
                "tier": self.v_tier.get(), "pin": None,
                "offset": None, "measured": None}
        tol = self._resolve_tol(nom, raw=self.v_nom.get())

        dep = fnum(self.v_dep.get()) if hole else None
        cbd = fnum(self.v_cbd.get()) if hole else None
        cbz = fnum(self.v_cbz.get()) if hole else None
        if cbz is not None and cbd is None:
            raise ValueError("CBore depth needs CBore Ø / "
                             "pogłębienie wymaga Ø")

        def row(grp, ft, nm, is_dia=False, typ=None, raw=None):
            d = dict(base)
            d.update(self._tol_for_feature(nm, is_dia, raw=raw))
            d["group"] = grp
            d["feature"] = ft
            d["nominal"] = nm
            d["pin"] = self._pin_for(nm, is_dia)
            if typ:
                d["type"] = typ
            return d

        def extras(tag=""):
            out = []
            if dep is not None:
                out.append(row("holes Ø / otwory",
                               ("depth%s" % tag), dep,
                               typ="depth / głębokość",
                               raw=self.v_dep.get()))
            if cbd is not None:
                out.append(row("holes Ø / otwory",
                               (u"cbore Ø%s" % tag), cbd, is_dia=True,
                               raw=self.v_cbd.get()))
            if cbz is not None:
                out.append(row("holes Ø / otwory",
                               ("cbore depth%s" % tag), cbz,
                               typ="depth / głębokość",
                               raw=self.v_cbz.get()))
            return out

        if self.v_adv.get() and not self.edit:
            hx, hy = fnum(self.v_hx.get()), fnum(self.v_hy.get())
            if hx is None or hy is None:
                raise ValueError("Advanced hole needs X and Y")
            try:
                n = max(1, int(float(self.v_pn.get().replace(",", "."))))
            except ValueError:
                n = 1
            share = self._share_mode()
            coords = [(hx, hy)]                     # hole #1
            for k in range(1, n):
                vx = self.v_hxs[k - 1] if k - 1 < len(self.v_hxs) else None
                vy = self.v_hys[k - 1] if k - 1 < len(self.v_hys) else None
                kx = hx if share == "x" else fnum(vx.get() if vx else "")
                ky = hy if share == "y" else fnum(vy.get() if vy else "")
                if kx is None or ky is None:
                    raise ValueError("Hole #%d needs X and Y / "
                                     "otwór wymaga X i Y" % (k + 1))
                coords.append((round(kx, 4), round(ky, 4)))
            # gage pin on X/Y rows only
            hole_pin = self._pin_for(nom, True)
            rows = []
            for k, (kx, ky) in enumerate(coords):
                tag = (" H%d" % (k + 1)) if n > 1 else ""
                xr = row("positions / pozycje", "X pos%s" % tag, kx,
                         typ="position / pozycja")
                yr = row("positions / pozycje", "Y pos%s" % tag, ky,
                         typ="position / pozycja")
                xr["pin"] = yr["pin"] = hole_pin
                dia = row("holes Ø / otwory", ((feat or u"Ø") + tag), nom,
                          is_dia=True)
                dia["pin"] = None
                rows.append(xr)
                rows.append(yr)
                rows.append(dia)
                rows.extend(extras(tag))
            for i, d in enumerate(rows):
                d["bubble"] = "%s%s" % (self.bubble_no,
                                        LETTERS[i % len(LETTERS)])
                # skip expand_hole_row on commit
                d["_expanded"] = True
            return rows

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
            QMessageBox.critical(self, "Error / Błąd", str(e))
            return
        self.sub_idx = len(self.rows)
        for v in (self.v_feat, self.v_nom, self.v_pin, self.v_ref,
                  self.v_hx, self.v_hy,
                  self.v_dep, self.v_cbd, self.v_cbz):
            v.set("")
        self.v_pn.set("1")
        self.cmb_share.setCurrentIndex(0)
        self._build_holes()
        self.v_inv.set(False)
        self.v_adv.set(False)
        for v in (self.v_tsym, self.v_tmax, self.v_tmin):
            v.set("")
        self._tsym_user = False
        self._mm_user = False
        self._toggle_inv()
        self._toggle_adv()
        self.setWindowTitle("Bubble #%s%s" % (self.bubble_no,
                                              chr(ord("a") + self.sub_idx)))

    def _snapshot(self):
        out = {"type": self.v_type.get(), "group": self.v_group.get(),
               "tier": self.v_tier.get()}
        raw_sym = self.v_tsym.get().strip()
        if self._tsym_sticky and raw_sym:
            out["tsym"] = raw_sym
            out["tmax"] = out["tmin"] = ""
        elif self._mm_sticky and (self.v_tmax.get().strip() or
                                  self.v_tmin.get().strip()):
            out["tmax"] = self.v_tmax.get().strip()
            out["tmin"] = self.v_tmin.get().strip()
            out["tsym"] = ""
        p = self.v_pin.get().strip()
        if self._pin_sticky and p:
            out["pin"] = p
        elif self._pin_sticky and not p:
            out["pin"] = ""
        return out

    def _ok(self):
        try:
            self._push()
        except ValueError as e:
            QMessageBox.critical(self, "Error / Błąd", str(e))
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

    # Esc behaves like Cancel
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.result_rows is None:
            self._record_geo()
        super().closeEvent(e)
