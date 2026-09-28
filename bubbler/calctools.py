# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Inspection tools dialog for calculator.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox,
                               QStackedWidget, QWidget, QFormLayout,
                               QLineEdit, QLabel, QPushButton)

from . import metrology as mt
from .common import fnum
from .i18n import tr

TOOLS = (("tp", "True position (RFS, MMC or LMC)"),
         ("bilat", "Unilateral to bilateral"),
         ("unilat", "Bilateral to unilateral"),
         ("fit", "Fit lookup (ISO 286)"),
         ("ratio", "Gage ratio"),
         ("thread", "Thread pitch diameter and wires"),
         ("taper", "Taper"),
         ("rz", "Ra and Rz"))


def _g(v):
    return "%.6g" % v


def _f(v):
    """Tolerance cells can hold text like "0,1"."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return fnum(str(v))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _s(v):
    x = _f(v)
    return "" if x is None else _g(x)


def _rule(cfg):
    """Shop gage ratio. 0 means no rule."""
    try:
        return float(cfg.get("gage_resolution_ratio", 10) or 0)
    except (TypeError, ValueError):
        return 10.0


class ToolsDialog(QDialog):

    def __init__(self, parent, row=None, cfg=None, units="iso_mm"):
        super().__init__(parent)
        self.setWindowTitle(tr('Inspection tools'))
        self.cfg = cfg or {}
        self.units = units
        self.row = row or {}
        self.result = None
        lay = QVBoxLayout(self)
        self.cb = QComboBox()
        for key, label in TOOLS:
            self.cb.addItem(tr(label), key)
        self.cb.setProperty("i18n_skip", True)
        lay.addWidget(self.cb)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.out = QLabel("")
        self.out.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.out.setWordWrap(True)
        self.out.setStyleSheet("color:#217346; font-weight:bold;")
        lay.addWidget(self.out)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:#666666; font-size:8pt;")
        lay.addWidget(self.note)
        bl = QHBoxLayout()
        b_calc = QPushButton(tr('Calculate'))
        b_calc.setDefault(True)
        b_calc.clicked.connect(self.calculate)
        self.b_use = QPushButton(tr('Use result'))
        self.b_use.setEnabled(False)
        self.b_use.clicked.connect(self.accept)
        b_close = QPushButton(tr('Close'))
        b_close.clicked.connect(self.reject)
        bl.addWidget(b_calc)
        bl.addWidget(self.b_use)
        bl.addStretch(1)
        bl.addWidget(b_close)
        lay.addLayout(bl)
        self.f = {}
        for key, _label in TOOLS:
            self.stack.addWidget(self._form(key))
        self.cb.currentIndexChanged.connect(self._switch)
        self._switch(0)

    def _field(self, form, key, label, value=""):
        e = QLineEdit(value)
        e.returnPressed.connect(self.calculate)
        form.addRow(tr(label), e)
        self.f[key] = e
        return e

    def _form(self, key):
        w = QWidget()
        fl = QFormLayout(w)
        r = self.row
        nom, tsym = _s(r.get("nominal")), _s(r.get("tol_sym"))
        up, dn = _s(r.get("tol_max")), _s(r.get("tol_min"))
        # GD&T zone lives in tol_max
        zone = tsym or (up if str(r.get("type") or "") in ("GD&T",
                                                           "position")
                        else "")
        if key == "tp":
            self._field(fl, "tp_dx", 'X deviation')
            self._field(fl, "tp_dy", 'Y deviation')
            self._field(fl, "tp_tol", 'Position tolerance (dia)', zone)
            self.f["tp_mod"] = QComboBox()
            self.f["tp_mod"].addItems(["RFS", "MMC", "LMC"])
            self.f["tp_mod"].setProperty("i18n_skip", True)
            fl.addRow(tr('Modifier'), self.f["tp_mod"])
            self._field(fl, "tp_size", 'Measured feature size')
            self._field(fl, "tp_mmc", 'MMC size')
            self._field(fl, "tp_lmc", 'LMC size')
        elif key == "bilat":
            self._field(fl, "bi_nom", 'Nominal', nom)
            # missing side is zero
            self._field(fl, "bi_up", 'Upper deviation',
                        up or tsym or ("0" if dn else ""))
            self._field(fl, "bi_dn", 'Lower deviation (signed)',
                        dn or ("-" + tsym if tsym else ("0" if up else "")))
        elif key == "unilat":
            self._field(fl, "un_nom", 'Nominal', nom)
            self._field(fl, "un_half", 'Plus/minus', tsym)
        elif key == "fit":
            self._field(fl, "fit_nom", 'Nominal (mm)', nom)
            self._field(fl, "fit_hole", 'Hole code', "H7")
            self._field(fl, "fit_shaft", 'Shaft code', "g6")
        elif key == "ratio":
            band = ""
            a, b = _f(r.get("tol_max")), _f(r.get("tol_min"))
            if a is not None or b is not None:
                band = _g(abs((a or 0.0) - (b or 0.0)))
            elif _f(r.get("tol_sym")) is not None:
                band = _g(2 * abs(_f(r["tol_sym"])))
            self._field(fl, "gr_band", 'Tolerance band (drawing units)',
                        band)
            self.f["gr_tool"] = QComboBox()
            self.f["gr_tool"].setProperty("i18n_skip", True)
            for t in self.cfg.get("metrology_tools") or ():
                if t.get("resolution"):
                    self.f["gr_tool"].addItem(
                        "%s (%s)" % (t.get("name"), _g(t["resolution"])),
                        float(t["resolution"]))
            self.f["gr_tool"].currentIndexChanged.connect(self._tool_res)
            fl.addRow(tr('Gage'), self.f["gr_tool"])
            self._field(fl, "gr_res", 'Gage resolution (mm)')
            self._tool_res()
        elif key == "thread":
            self._field(fl, "th_d", 'Major diameter', nom)
            self._field(fl, "th_p", 'Pitch')
            self._field(fl, "th_cls", 'Class (6g, 6H...)', "6g")
            self._field(fl, "th_w", 'Wire size (blank = best wire)')
            self._field(fl, "th_m", 'Measured over wires (optional)')
        elif key == "taper":
            self._field(fl, "tp_big", 'Large diameter')
            self._field(fl, "tp_small", 'Small diameter')
            self._field(fl, "tp_len", 'Length')
        elif key == "rz":
            self._field(fl, "rz_ra", 'Ra')
            self._field(fl, "rz_rz", 'Rz')
        return w

    def _tool_res(self, *_a):
        cb, e = self.f.get("gr_tool"), self.f.get("gr_res")
        if cb is not None and e is not None and cb.currentData() is not None:
            e.setText(_g(cb.currentData()))

    def _switch(self, i):
        self.stack.setCurrentIndex(i)
        self.out.setText("")
        self.b_use.setEnabled(False)
        key = self.cb.itemData(i)
        self.note.setText({
            "thread": tr('60 degree thread. Class limits: ISO metric, grade '
                         '6 (6e, 6f, 6g, 6h, 6G, 6H), the coarse sizes M1.6 '
                         'to M39 and the fine pitches in the shipped table; '
                         'anything else (and any inch drawing) gives the '
                         'basic pitch diameter only.'),
            "rz": tr('Rz = 4 x Ra is a rule of thumb with no standard '
                     'behind it: never judge a part on the converted '
                     'number.'),
            "fit": (tr('ISO 286 is a millimetre table: convert an inch '
                       'size first.') if self.units == "asme_inch" else ""),
            "ratio": (tr('Shop rule: %s:1 (Settings).') % _g(_rule(self.cfg))
                      if _rule(self.cfg) else
                      tr('No shop rule is set (Settings).')),
        }.get(key, ""))

    def _n(self, key, required=True):
        txt = self.f[key].text().strip()
        if not txt:
            if required:
                raise ValueError(tr('Fill in every field.'))
            return None
        try:
            v = fnum(txt)
        except (TypeError, ValueError, ZeroDivisionError):
            raise ValueError(tr('%s is not a number.') % txt)
        import math
        if not math.isfinite(v):
            raise ValueError(tr('%s is not a number.') % txt)
        return v

    def calculate(self):
        key = self.cb.currentData()
        try:
            text, res = getattr(self, "_calc_" + key)()
        except ValueError as e:
            self.out.setText(str(e))
            self.result = None
            self.b_use.setEnabled(False)
            return None
        self.out.setText(text)
        self.result = res
        self.b_use.setEnabled(res is not None)
        return text

    def _calc_tp(self):
        mod = self.f["tp_mod"].currentText()
        args = (self._n("tp_size", False), self._n("tp_mmc", False),
                self._n("tp_lmc", False))
        if mod != "RFS" and None in args:
            raise ValueError(tr('%s needs the measured size and both the '
                                'MMC and LMC sizes.') % mod)
        r = mt.true_position(self._n("tp_dx"), self._n("tp_dy"),
                             self._n("tp_tol"), *args, mod=mod)
        if not r["size_ok"]:
            verdict = tr('OUT of size: no bonus')
        else:
            verdict = tr('within tolerance') if r["ok"] \
                else tr('OUT of tolerance')
        return (tr('Position %s   allowed %s (bonus %s)   %s')
                % (_g(r["tp"]), _g(r["allowed"]), _g(r["bonus"]), verdict),
                r["tp"])

    def _calc_bilat(self):
        mid, half = mt.to_bilateral(self._n("bi_nom"), self._n("bi_up"),
                                    self._n("bi_dn"))
        return ("%s ±%s" % (_g(mid), _g(half)), mid)

    def _calc_unilat(self):
        n, h = self._n("un_nom"), self._n("un_half")
        a = mt.to_unilateral(n, h, "+")
        b = mt.to_unilateral(n, h, "-")
        return ("%s +%s/0   %s +0/%s" % (_g(a[0]), _g(a[1]), _g(b[0]),
                                          _g(b[2])), a[0])

    def _calc_fit(self):
        if self.units == "asme_inch":
            raise ValueError(tr('ISO 286 is a millimetre table: convert an '
                                'inch size first.'))
        hole = self.f["fit_hole"].text().strip() or None
        shaft = self.f["fit_shaft"].text().strip() or None
        r = mt.fit(self._n("fit_nom"), hole, shaft)
        if not r:
            raise ValueError(tr('No ISO 286 value for that size and code.'))
        parts = ["%s %s..%s" % (v["code"], _g(v["min"]), _g(v["max"]))
                 for k, v in r.items() if k in ("hole", "shaft")]
        if "clear_max" in r:
            parts.append(tr('clearance %s..%s')
                         % (_g(r["clear_min"]), _g(r["clear_max"])))
        first = r.get("hole") or r.get("shaft")
        return ("   ".join(parts), first["max"])

    def _calc_ratio(self):
        # resolution mm, band inch
        k = 25.4 if self.units == "asme_inch" else 1.0
        res = self._n("gr_res")
        if res <= 0:
            raise ValueError(tr('The gage resolution must be above zero.'))
        ratio = mt.gage_ratio(self._n("gr_band") * k, res)
        need = _rule(self.cfg)
        if not need:
            return ("%s:1" % _g(ratio), ratio)
        ok = tr('meets the shop rule') if ratio >= need \
            else tr('below the shop rule')
        return ("%s:1   %s" % (_g(ratio), ok), ratio)

    def _calc_thread(self):
        p = self._n("th_p")
        d2 = mt.pitch_diameter(self._n("th_d"), p)
        if d2 is None:
            raise ValueError(tr('The diameter and the pitch must be above '
                                'zero.'))
        w = self._n("th_w", False)
        w = mt.best_wire(p) if w is None else w
        if w <= 0:
            raise ValueError(tr('The wire size must be above zero.'))
        m = self._n("th_m", False)
        txt = tr('basic pitch dia %s   wire %s   over wires %s') % (
            _g(d2), _g(w), _g(mt.over_wires(d2, p, w)))
        cls = self.f["th_cls"].text().strip()
        if cls and self.units == "asme_inch":
            txt += "\n" + tr('Class limits are for ISO metric threads: '
                              'not calculated on an inch drawing.')
        elif cls:
            lim = mt.thread_limits(self._n("th_d"), p, cls)
            if lim is None:
                txt += "\n" + tr('%s: not in the shipped ISO 965 table '
                                  '(grade 6, common sizes only).') % cls
            else:
                txt += "\n" + tr('%s pitch dia %s .. %s   over wires '
                                  '%s .. %s') % (
                    cls, _g(lim["min"]), _g(lim["max"]),
                    _g(mt.over_wires(lim["min"], p, w)),
                    _g(mt.over_wires(lim["max"], p, w)))
        if m is not None:
            got = mt.d2_from_wires(m, p, w)
            return (txt + "\n" + tr('measured pitch dia %s') % _g(got), got)
        return (txt, d2)

    def _calc_taper(self):
        r = mt.taper(self._n("tp_big"), self._n("tp_small"),
                     self._n("tp_len"))
        if r is None:
            raise ValueError(tr('The diameters must differ and the length '
                                'be positive.'))
        return (tr('included %s°   half %s°   1:%s')
                % (_g(r["included"]), _g(r["half"]), _g(r["ratio"])),
                r["included"])

    def _calc_rz(self):
        ra, rz = self._n("rz_ra", False), self._n("rz_rz", False)
        if ra is not None:
            v = mt.rz_from_ra(ra)
            return ("Rz ~ %s" % _g(v), v)
        if rz is not None:
            v = mt.ra_from_rz(rz)
            return ("Ra ~ %s" % _g(v), v)
        raise ValueError(tr('Fill in every field.'))
