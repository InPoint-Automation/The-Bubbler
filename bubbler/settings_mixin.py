# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Settings dialog, header editor, keybind help

import os

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QLabel, QLineEdit, QComboBox,
                               QCheckBox, QPushButton, QMessageBox,
                               QTabWidget, QScrollArea, QFileDialog,
                               QGroupBox, QProgressDialog, QSpinBox,
                               QTableWidget, QTableWidgetItem,
                               QAbstractItemView)
from PySide6.QtGui import QColor

from .common import TYPES, TIERS, SHAPES
from .config import (save_cfg, CFG_DEFAULT, FAI_SHOW, dp_label,
                     ladder_key, validate_ladder)
from .sheet import HEADER_FIELDS
from .scanlib import GAGES, scan_presets
from .scanscope import ScopeDialog
from .i18n import tr, set_lang, retranslate, sheet_label
from .widgets import fill_keyed, combo_key
from .keyhelp import _keybinds_html
from .statuspanel import StatusPanel
from . import vision, florence, gpu, step


def _ladder_reason(why):
    """Ladder reason tuple to message"""
    code = why[0]
    if code == "bucket":
        return tr('%s is not a decimal-place bucket.') % why[1]
    if code == "nan":
        return tr('%s must be a number.') % why[1]
    if code == "nonpositive":
        return tr('%s must be greater than zero.') % why[1]
    if code == "range":
        return tr('%s is %g, outside the sane range %g to %g.') % why[1:]
    if code == "monotonic":
        return tr('%s is looser than %s. More decimal places must mean a '
                  'tighter tolerance.') % (why[1], why[2])
    return tr('The tolerance ladder is not usable.')


class _DLSignals(QObject):
    progress = Signal(int, int, float, float, str)
    done = Signal(str)
    failed = Signal(str)


class _FlorenceDLTask(QRunnable):
    """Florence-2 download"""

    def __init__(self, pack, dest_root):
        super().__init__()
        self.pack, self.dest_root = pack, dest_root
        self.signals = _DLSignals()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            path = florence.download_pack(
                self.pack, self.dest_root,
                progress=lambda i, n, c, t, nm:
                    self.signals.progress.emit(i, n, c, t, nm),
                should_cancel=lambda: self._cancel)
            self.signals.done.emit(path)
        except Exception as e:
            self.signals.failed.emit(str(e))


# widths fit content
_NUM_W = 84
_CB_W = 190


def _num(val):
    """Short numeric entry field"""
    e = QLineEdit("%g" % float(val))
    e.setMaximumWidth(_NUM_W)
    return e


def _combo(items=None, width=_CB_W):
    """Drop-down capped to content"""
    cb = QComboBox()
    if items:
        cb.addItems(items)
    cb.setMaximumWidth(width)
    cb.setMinimumWidth(min(width, 130))
    return cb


# label per FAI_SHOW toggle
SHOW_LABELS = {
    "part_name": "Part name", "drawing": "Drawing number",
    "dwg_rev": "Drawing rev", "part_rev": "Part rev",
    "po": "PO number", "material": "Material",
    "serial": "Serial or lot", "units": "Units", "customer": "Customer",
    "feature": "Feature column", "method": "Method column",
    "comments": "Comments column", "dev_bar": "Tolerance bar",
    "qa_signature": "QA signature block",
}


def _tab(tabs, title):
    """Scrollable tab page to column layout"""
    page = QWidget()
    col = QVBoxLayout(page)
    col.setContentsMargins(10, 10, 10, 10)
    col.setSpacing(9)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    scroll.setWidget(page)
    tabs.addTab(scroll, tr(title))
    return col


def _sect(col, title):
    """Titled section to grid"""
    box = QGroupBox(tr(title))
    grid = QGridLayout(box)
    grid.setContentsMargins(10, 6, 10, 8)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(4)
    grid.setColumnStretch(2, 1)
    col.addWidget(box)
    return grid


def _tag(w, key):
    """Mark which config key control owns"""
    if key:
        w.setProperty("cfg_key", key)
    return w


def _field(grid, label, w, key=None, tip=None):
    """Label plus one right-sized control"""
    r = grid.rowCount()
    lab = QLabel(label)
    lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    grid.addWidget(lab, r, 0)
    grid.addWidget(w, r, 1)
    if tip:
        lab.setToolTip(tip)
        w.setToolTip(tip)
    return _tag(w, key)


def _full(grid, w, key=None, tip=None):
    """Row spanning whole section"""
    grid.addWidget(w, grid.rowCount(), 0, 1, 3)
    if tip:
        w.setToolTip(tip)
    return _tag(w, key)


def _hint(grid, text, color="#777777"):
    """Grey explanatory line"""
    lab = QLabel(text)
    lab.setProperty("i18n_skip", True)
    lab.setWordWrap(True)
    lab.setStyleSheet("color:%s; font-size:8pt;" % color)
    grid.addWidget(lab, grid.rowCount(), 0, 1, 3)
    return lab


def _mark_missing(cb, name):
    """A gated control whose backend is absent: empty, off, flagged red"""
    cb.setChecked(False)
    cb.setEnabled(False)
    cb.setStyleSheet("color:#c0392b;")
    cb.setText("%s  (%s)" % (cb.text(), tr('Missing: %s') % name))
    cb.setProperty("i18n_skip", True)


def _pairs(items, cols):
    """Label + control pairs packed into `cols` columns"""
    host = QWidget()
    gl = QGridLayout(host)
    gl.setContentsMargins(0, 0, 0, 0)
    gl.setHorizontalSpacing(8)
    gl.setVerticalSpacing(4)
    for i, (label, w) in enumerate(items):
        row, c0 = i // cols, (i % cols) * 2
        lab = QLabel(label)
        lab.setProperty("i18n_skip", True)
        lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        gl.addWidget(lab, row, c0)
        gl.addWidget(w, row, c0 + 1)
    gl.setColumnStretch(cols * 2, 1)
    return host


class SettingsMixin:
    def show_keys(self):
        from PySide6.QtWidgets import QTextBrowser
        dlg = QDialog(self)
        dlg.setWindowTitle(tr('Keybinds'))
        lay = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setOpenExternalLinks(False)
        view.setHtml(_keybinds_html())
        view.setMinimumSize(560, 540)
        lay.addWidget(view)
        b = QPushButton("OK")
        b.setDefault(True)
        b.clicked.connect(dlg.accept)
        lay.addWidget(b)
        dlg.resize(620, 660)
        dlg.exec()

    def header_editor(self, prefill=None):
        if self._hdr_win is not None:
            try:
                self._hdr_win.raise_()
                self._hdr_win.activateWindow()
                return
            except RuntimeError:
                self._hdr_win = None
        win = QDialog(self)
        win.setWindowTitle(tr('Header'))
        self._hdr_win = win
        g = QGridLayout(win)
        current = self.writer.get_header()
        prefill = prefill or {}
        entries = {}
        for i, (cell, key) in enumerate(HEADER_FIELDS):
            # label in UI language
            g.addWidget(QLabel(tr(key)), i, 0)
            seed = prefill[cell] if cell in prefill else current.get(cell, "")
            e = QLineEdit(str(seed))
            e.focusInEvent = (lambda ev, ent=e:
                              (setattr(self, "_hdr_focus", ent),
                               QLineEdit.focusInEvent(ent, ev)))
            g.addWidget(e, i, 1)
            entries[cell] = e

        def apply():
            vals = {c: e.text() for c, e in entries.items()}
            self.writer.set_header(vals)
            self.store.header.update(vals)    # session owns title block
            self._stamp_run_identity()        # run-scoped to active run
            try:
                self.writer.save()
            except Exception as ex:
                QMessageBox.critical(win, tr('Sheet error'), str(ex))
                return
            self._save_session()              # persist header + identity
            self.set_status(tr('header saved'))

        def rescan():
            try:
                page = self.doc[self.page_i]
            except Exception:
                return
            parsed = self._read_titleblock(self.page_i,
                                           self._titleblock_rect(page))
            for cell, val in parsed.items():
                e = entries.get(cell)
                if e is not None:
                    e.setText(str(val))
            if parsed:
                self.set_status(tr('title block scanned'))

        nrow = len(HEADER_FIELDS)
        bw = QWidget()
        bl = QHBoxLayout(bw)
        b_apply = QPushButton(tr('Apply'))
        b_apply.clicked.connect(apply)
        b_scan = QPushButton(tr('Scan title block'))
        b_scan.clicked.connect(rescan)
        b_close = QPushButton(tr('Close'))
        b_close.clicked.connect(win.close)
        bl.addWidget(b_apply)
        bl.addWidget(b_scan)
        bl.addWidget(b_close)
        g.addWidget(bw, nrow, 0, 1, 2)
        tip = QLabel("Tip: drag on the PDF fills the focused field")
        tip.setStyleSheet("color:#555;")
        g.addWidget(tip, nrow + 1, 0, 1, 2)
        # clear both, or clicks hijack a hidden field
        def _closed(_r):
            self._hdr_win = None
            self._hdr_focus = None
        win.finished.connect(_closed)
        retranslate(win)
        win.move(self.x() + 40, self.y() + 110)
        win.setModal(False)
        win.show()

    def settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr('Settings'))
        outer = QVBoxLayout(dlg)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        vars_ = {}

        # ------------------------------------------------------------ General
        col = _tab(tabs, 'General')
        gp = _sect(col, 'Language and mode')
        cb_lang = _field(gp, tr('Language'), _combo(), "language")
        cb_lang.addItem("English", "en")
        cb_lang.addItem("Polski", "pl")
        cb_lang.setCurrentIndex(
            1 if self.cfg.get("language", "en") == "pl" else 0)
        cb_mode = _field(gp, tr('Mode'), _combo(), "mode")
        cb_mode.addItem(tr('Advanced'), "advanced")
        cb_mode.addItem(tr('Simple'), "simple")
        cb_mode.setCurrentIndex(1 if self.cfg.get("mode") == "simple" else 0)

        ap = _sect(col, 'Appearance')
        e_icon = QLineEdit(str(self.cfg.get("icon_color",
                                            CFG_DEFAULT["icon_color"])))
        e_icon.setMaximumWidth(110)
        vars_["icon_color"] = _field(ap, tr('Accent color'), e_icon,
                                     "icon_color")
        e_scale = QLineEdit(str(self.cfg.get("ui_scale",
                                             CFG_DEFAULT["ui_scale"])))
        e_scale.setMaximumWidth(_NUM_W)
        vars_["ui_scale"] = _field(ap, tr('UI scale (0 = automatic)'),
                                   e_scale, "ui_scale")
        _hint(ap, tr('Drawing units and the tolerance ladder are on the '
                     'Tolerances tab.'))

        sp = _sect(col, '3D preview (STEP)')
        c_step = _full(sp, QCheckBox(
            tr('Offer a 3D STEP preview when opening a drawing (needs '
               'OpenCASCADE)')), "use_step_preview",
            tr('On: the first time a drawing opens, Bubbler asks for a STEP '
               'file and renders two isometric views for the report cover '
               'and recent-files list. OpenCASCADE (OCCT) installs below.'))
        c_step.setChecked(bool(self.cfg.get("use_step_preview", False)))
        b_steppack = QPushButton(tr('Install OpenCASCADE (OCCT)...'))
        b_steppack.setMaximumWidth(220)
        b_steppack.clicked.connect(self._install_step_pack)
        b_steprm = QPushButton(tr('Remove'))
        b_steprm.setMaximumWidth(90)
        b_steprm.setEnabled(step.is_installed())
        b_steprm.clicked.connect(lambda: self._uninstall_step_pack(b_steprm))
        _steprow = QWidget()
        _sl = QHBoxLayout(_steprow)
        _sl.setContentsMargins(0, 0, 0, 0)
        _sl.addWidget(b_steppack)
        _sl.addWidget(b_steprm)
        _sl.addStretch(1)
        _field(sp, tr('3D pack'), _steprow)
        _hint(sp, tr('OpenCASCADE reads STEP files. Installed once into '
                     '~/.bubbler/step; not part of the app download.'))
        col.addStretch(1)

        # ------------------------------------------------------------ Bubbles
        col = _tab(tabs, 'Bubbles')
        dp_ = _sect(col, 'New bubble defaults')
        cvars = {}
        cb = _field(dp_, tr('Default type'), _combo(TYPES), "default_type")
        cb.setProperty("i18n_skip", True)
        cb.setCurrentText(self.cfg.get("default_type",
                                       CFG_DEFAULT["default_type"]))
        cvars["default_type"] = cb
        # blank tier means auto
        cb_tier = _field(dp_, tr('Default tier'), _combo(), "default_tier")
        fill_keyed(cb_tier, TIERS,
                   self.cfg.get("default_tier", CFG_DEFAULT["default_tier"]))
        cb_tier.setItemText(0, tr('auto'))
        c_pinauto = _full(dp_, QCheckBox(tr('Hole pin Ø = nominal')),
                          "hole_pin_auto")
        c_pinauto.setChecked(bool(self.cfg.get("hole_pin_auto", False)))

        pl_ = _sect(col, 'Placement')
        c_lead = _full(pl_, QCheckBox(
            tr('Leader line from balloon to callout')), "leaders",
            tr("On: the balloon sits beside the callout, with a line "
               "pointing back. Off: it sits on the callout. Same as the "
               "ribbon Leaders box and the L key."))
        c_lead.setChecked(bool(self.cfg.get("leaders",
                                            CFG_DEFAULT["leaders"])))
        c_ltrim = _full(pl_, QCheckBox(
            tr('Stop the leader at the callout text')), "leader_trim")
        c_ltrim.setChecked(bool(self.cfg.get("leader_trim", True)))
        # preferred balloon side lives in the q hotbar (Offset), not here
        c_snap = _full(pl_, QCheckBox(tr('Snap to drawing geometry')),
                       "snap_geom")
        c_snap.setChecked(bool(self.cfg.get("snap_geom", True)))
        e_obsw = _field(pl_, tr('Bubble avoids lines wider than (pt)'),
                        _num(self.cfg.get("obstacle_min_w",
                                          CFG_DEFAULT["obstacle_min_w"])),
                        "obstacle_min_w")
        e_caprad = _field(pl_, tr('Click capture radius (pt)'),
                          _num(self.cfg.get("capture_radius",
                                            CFG_DEFAULT["capture_radius"])),
                          "capture_radius")

        tr_ = _sect(col, 'Criticality tiers')
        c_shapes = _full(tr_, QCheckBox(
            tr('Shape-code criticality tiers (colour-blind safe)')),
            "tier_shapes",
            tr("On: tiers differ by shape as well as colour. "
               "Off: all balloons are circles (colour only)."))
        c_shapes.setChecked(bool(self.cfg.get("tier_shapes", True)))
        smap = dict(self.cfg.get("tier_shape_map")
                    or CFG_DEFAULT["tier_shape_map"])
        shape_cbs = {}
        _sh_items = []
        for tier in ("red", "blue", "green"):
            cb = _combo(SHAPES, 130)
            cb.setProperty("i18n_skip", True)
            cur = smap.get(tier, "circle")
            cb.setCurrentText(cur if cur in SHAPES else "circle")
            _tag(cb, "tier_shape_map")
            shape_cbs[tier] = cb
            _sh_items.append((tier, cb))
        _full(tr_, _pairs(_sh_items, 3))

        def _sync_shapes():
            for cb in shape_cbs.values():
                cb.setEnabled(c_shapes.isChecked())
        c_shapes.toggled.connect(lambda _b: _sync_shapes())
        _sync_shapes()

        c_typetier = _full(tr_, QCheckBox(
            tr('Set each bubble tier from its callout type')),
            "type_tier_auto",
            tr("Only fills the tier when the ribbon 'Next bubble' tier is "
               "blank; a tier picked on the ribbon always wins. Off: blank "
               "stays blank."))
        c_typetier.setChecked(bool(self.cfg.get("type_tier_auto")))
        ttmap = dict(self.cfg.get("type_tier_map")
                     or CFG_DEFAULT["type_tier_map"])
        _tier_opts = [t for t in TIERS if t]
        tt_cbs = {}
        _tt_items = []
        for tp in TYPES:
            cb = _combo(_tier_opts, 110)
            cb.setProperty("i18n_skip", True)
            cur = ttmap.get(tp, "red")
            cb.setCurrentText(cur if cur in _tier_opts else "red")
            _tag(cb, "type_tier_map")
            tt_cbs[tp] = cb
            _tt_items.append((tp, cb))
        _full(tr_, _pairs(_tt_items, 3))

        def _sync_typetier():
            for cb in tt_cbs.values():
                cb.setEnabled(c_typetier.isChecked())
        c_typetier.toggled.connect(lambda _b: _sync_typetier())
        _sync_typetier()
        col.addStretch(1)

        # --------------------------------------------------------- Tolerances
        col = _tab(tabs, 'Tolerances')
        un = _sect(col, 'Drawing units')
        cb_units = _field(un, tr('Units'), _combo(), "units")
        cb_units.addItem("ISO (mm)", "iso_mm")
        cb_units.addItem("ASME (inch)", "asme_inch")
        cb_units.setCurrentIndex(
            1 if self.cfg.get("units") == "asme_inch" else 0)
        _hint(un, tr('A drawing Bubbler detects as inch keeps its own answer; '
                     'this is what a new or undecided drawing gets.'))

        gt = _sect(col, 'General tolerance')
        # ladder follows the drawing standard: ISO 2768 on mm, decimal on inch
        _hint(gt, tr('The general tolerance follows the drawing standard: '
                     'ISO 2768 by class on a millimetre drawing, the '
                     'decimal-place ladder on an inch one.'))
        c_dpon = _full(gt, QCheckBox(
            tr('Apply the general tolerance automatically')),
            "dp_on,rib_iso_on")
        c_dpon.setChecked(bool(self.cfg.get("dp_on")
                               or self.cfg.get("rib_iso_on")))
        cb_icls = _field(gt, tr('ISO 2768 class'), _combo(["f", "m", "c", "v"],
                                                          110),
                         "default_iso_class")
        cb_icls.setProperty("i18n_skip", True)
        cb_icls.setCurrentText(str(self.cfg.get(
            "default_iso_class", CFG_DEFAULT["default_iso_class"])))
        c_brtol = _full(gt, QCheckBox(
            tr('BASIC and REFERENCE dims take the general tolerance')),
            "gentol_basic_ref",
            tr('Off treats them as exact: bracketed dims still get a bubble '
               'and a sheet row, but no tolerance.'))
        c_brtol.setChecked(bool(self.cfg.get(
            "gentol_basic_ref", CFG_DEFAULT["gentol_basic_ref"])))
        c_angshort = _full(gt, QCheckBox(
            tr('Angles: assume the shortest side band')), "angular_short_side",
            tr('ISO 2768 tolerances an angle by its shorter side in mm, which '
               'the callout never carries. Off, the bubble dialog asks.'))
        c_angshort.setChecked(bool(self.cfg.get(
            "angular_short_side", CFG_DEFAULT["angular_short_side"])))

        lad = _sect(col, 'Decimal-place ladder (inch)')
        dpv = {}

        def _ladder_row(units, buckets):
            """One editable ladder as {bucket: QLineEdit}"""
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            cur = dict(self.cfg.get(ladder_key(units))
                       or CFG_DEFAULT[ladder_key(units)])
            out = {}
            for k in buckets:
                lab = QLabel(dp_label(k) + " ±")
                lab.setProperty("i18n_skip", True)
                lay.addWidget(lab)
                e = QLineEdit("%g" % float(
                    cur.get(k, CFG_DEFAULT[ladder_key(units)][k])))
                e.setMaximumWidth(70)
                _tag(e, ladder_key(units))
                lay.addWidget(e)
                out[k] = e
            lay.addStretch(1)
            return row, out

        # decimal ladders are inch-only; a millimetre drawing uses ISO 2768
        for _units, _lab, _buckets in (
                ("asme_inch", tr('Inch ladder'), ("1", "2", "3", "4")),):
            _row, dpv[_units] = _ladder_row(_units, _buckets)
            _field(lad, _lab, _row)

        b_ladreset = QPushButton(tr('Reset ladders to defaults'))
        b_ladreset.setMaximumWidth(220)

        def _reset_ladders():
            for u, edits in dpv.items():
                for k, e in edits.items():
                    e.setText("%g" % CFG_DEFAULT[ladder_key(u)][k])
            cb_icls.setCurrentText(CFG_DEFAULT["default_iso_class"])
        b_ladreset.clicked.connect(_reset_ladders)
        lad.addWidget(b_ladreset, lad.rowCount(), 1)

        # both the ISO 2768 class default and the inch ladder are always
        # editable; which one a drawing uses is decided by its units
        col.addStretch(1)

        # -------------------------------------------------------------- Gages
        col = _tab(tabs, 'Gages')
        tvars = {}

        gsel = _sect(col, 'Gage selection')
        e_ratio = _num(self.cfg.get("gage_resolution_ratio",
                                    CFG_DEFAULT["gage_resolution_ratio"]))
        e_ratio.setMaximumWidth(70)
        _field(gsel, tr('Resolution finer than tolerance by (x)'),
               e_ratio, "gage_resolution_ratio")
        self._gage_ratio_edit = e_ratio
        _hint(gsel, tr('A tool is chosen by what it MEASURES and whether its '
                       'range covers the size; among those that fit, the least '
                       'capable whose resolution is this many times finer than '
                       'the tolerance. 0 = fit by feature and range only.'))

        cat = _sect(col, 'Tool catalog')
        self._tool_units = ["mm"]
        tbl = QTableWidget()
        _tcols = (tr('Name'), tr('Kind'), tr('Resolution'),
                  tr('Range min'), tr('Range max'), tr('Measures'))
        tbl.setColumnCount(len(_tcols))
        tbl.setHorizontalHeaderLabels(list(_tcols))
        tbl.verticalHeader().setVisible(False)
        tbl.setProperty("i18n_skip", True)
        tbl.setFixedHeight(150)
        _tag(tbl, "metrology_tools")        # reachable for the settings test
        self._tool_table = tbl
        self._fill_tool_table(self.cfg.get("metrology_tools")
                              or CFG_DEFAULT["metrology_tools"], "mm")
        cat.addWidget(tbl, cat.rowCount(), 0, 1, 3)
        _tw = QWidget()
        _tl = QHBoxLayout(_tw)
        _tl.setContentsMargins(0, 0, 0, 0)
        b_add = QPushButton(tr('Add tool'))
        b_add.setMaximumWidth(110)
        b_add.clicked.connect(self._add_tool_row)
        b_del = QPushButton(tr('Remove'))
        b_del.setMaximumWidth(90)
        b_del.clicked.connect(self._remove_tool_row)
        cb_tu = QComboBox()
        cb_tu.setProperty("i18n_skip", True)
        cb_tu.addItem("mm", "mm")
        cb_tu.addItem("inch", "inch")
        cb_tu.currentIndexChanged.connect(
            lambda _i: self._flip_tool_units(cb_tu.currentData()))
        _tl.addWidget(b_add)
        _tl.addWidget(b_del)
        _tl.addStretch(1)
        _ul = QLabel(tr('Units:'))
        _ul.setProperty("i18n_skip", True)
        _tl.addWidget(_ul)
        _tl.addWidget(cb_tu)
        cat.addWidget(_tw, cat.rowCount(), 0, 1, 3)
        _hint(cat, tr('Each tool has its OWN range, so a large dimension rules '
                      'out a small-envelope CMM or a caliper you do not have. '
                      'Measures: comma list of length, od, id, depth, thread, '
                      'radius, angle, surface, gdt. mm/inch converts entered '
                      'values.'))

        av = _sect(col, 'Available gages')
        gcfg = dict(self.cfg.get("gages") or {})
        gvars = {}
        _gw = QWidget()
        _gl = QGridLayout(_gw)
        _gl.setContentsMargins(0, 0, 0, 0)
        for i, gname in enumerate(GAGES):
            c = QCheckBox(gname)
            c.setProperty("i18n_skip", True)
            c.setChecked(bool(gcfg.get(gname, True)))
            _tag(c, "gages")
            _gl.addWidget(c, i // 2, i % 2)
            gvars[gname] = c
        _gl.setColumnStretch(2, 1)
        av.addWidget(_gw, av.rowCount(), 0, 1, 3)
        col.addStretch(1)

        # --------------------------------------------------- Inspection sheet
        col = _tab(tabs, 'Inspection sheet')

        # drawing overrides shop default
        sc = _sect(col, 'Inspection type')
        cb_scope = _field(sc, tr('Inspection'),
                          _combo(scan_presets(self.cfg), 200), "scan_preset")
        cb_scope.setProperty("i18n_skip", True)
        cb_scope.setCurrentText(str(self.cfg.get("scan_preset")
                                    or CFG_DEFAULT["scan_preset"]))
        b_scope = QPushButton(tr('Edit presets...'))
        b_scope.setMaximumWidth(200)
        # button carries tag
        _full(sc, b_scope, "scan_presets",
              tr('The sheet says which inspection this is in its Inspection '
                 'type cell, and that wins over this default. Nothing is '
                 'ever hidden from scan review -- only the starting tick '
                 'changes.'))
        self._scope_presets = dict(self.cfg.get("scan_presets") or {})

        def _edit_scope():
            cfg = dict(self.cfg)
            cfg["scan_presets"] = self._scope_presets
            dlg = ScopeDialog(self, cfg)
            if dlg.exec() != QDialog.Accepted:
                return
            self._scope_presets = dlg.result_presets()
            keep = cb_scope.currentText()
            cb_scope.blockSignals(True)
            cb_scope.clear()
            cb_scope.addItems(dlg.names())
            cb_scope.setCurrentText(
                keep if keep in dlg.names() else CFG_DEFAULT["scan_preset"])
            cb_scope.blockSignals(False)
        b_scope.clicked.connect(_edit_scope)

        sh = _sect(col, 'Sheet header')
        e_comp = QLineEdit(str(self.cfg.get("company",
                                            CFG_DEFAULT["company"])))
        e_comp.setMaximumWidth(280)
        vars_["company"] = _field(sh, tr('Company'), e_comp, "company")
        so = _sect(col, 'Sheet output')
        # drives both sheet and report
        cb_sheet = _field(so, tr('Document language'), _combo(), "sheet_lang")
        cb_sheet.addItem("EN + PL", "both")
        cb_sheet.addItem("English", "en")
        cb_sheet.addItem("Polski", "pl")
        _sl = self.cfg.get("sheet_lang", "both")
        cb_sheet.setCurrentIndex({"both": 0, "en": 1, "pl": 2}.get(_sl, 0))
        c_desig = _full(so, QCheckBox(tr('Write the tier as a designator')),
                        "sheet_tier_designator",
                        tr('Off: the tier goes in the tier column. On: it is '
                           'mapped to the designator column instead (red '
                           'CRITICAL, blue MAJOR, green MINOR). KEY is never '
                           'written, so it stays hand-entry.'))
        c_desig.setChecked(bool(self.cfg.get("sheet_tier_designator")))
        c_tiercol = _full(so, QCheckBox(tr('Write the tier in the sheet')),
                          "sheet_tier_column",
                          tr('Off: the tier stays on screen, where it groups '
                             'balloons. On: the tier column of the sheet is '
                             'filled with it. An inspector cannot act on a '
                             'colour, so a delivered packet says nothing '
                             'about it unless you ask.'))
        c_tiercol.setChecked(bool(self.cfg.get("sheet_tier_column")))
        c_brlab = _full(so, QCheckBox(tr('Spell out BASIC or REF on the sheet')),
                        "sheet_basic_ref_label",
                        tr('A bubbled BASIC or REFERENCE dimension is an '
                           'ordinary row either way. On: the word is written '
                           'after the value, because a square bracket is easy '
                           'to miss on a printed packet.'))
        c_brlab.setChecked(bool(self.cfg.get("sheet_basic_ref_label")))
        # optional columns default off
        c_gage = _full(so, QCheckBox(tr('Add a gage column')),
                       "sheet_gage_column",
                       tr('Off by default. On: the sheet carries a column '
                          'for the gage or instrument each reading was '
                          'taken with.'))
        c_gage.setChecked(bool(self.cfg.get("sheet_gage_column")))
        c_refz = _full(so, QCheckBox(tr('Add a ref or zone column')),
                       "sheet_refzone_column",
                       tr('Off by default. On: the sheet carries a column '
                          'for a hand-written GD&T datum or zone reference.'))
        c_refz.setChecked(bool(self.cfg.get("sheet_refzone_column")))
        c_ncr = _full(so, QCheckBox(tr('Add an NCR column')),
                      "sheet_ncr_column",
                      tr('Off by default. On: the sheet carries a column '
                         'for a nonconformance number.'))
        c_ncr.setChecked(bool(self.cfg.get("sheet_ncr_column")))
        c_method = _full(so, QCheckBox(tr('Add a method column')),
                         "sheet_method_column",
                         tr('Off by default. On: the sheet carries a '
                            'measurement-method dropdown (CMM, probe, etc.).'))
        c_method.setChecked(bool(self.cfg.get("sheet_method_column")))
        c_type = _full(so, QCheckBox(tr('Add a type column')),
                       "sheet_type_column",
                       tr('Off by default. On: the sheet carries the ledger '
                          'type dropdown (dim, hole, thread, GD&T, finish).'))
        c_type.setChecked(bool(self.cfg.get("sheet_type_column")))

        # live column-layout preview
        from . import sheet_build
        _col_flags = {
            "sheet_tier_designator": c_desig,
            "sheet_tier_column": c_tiercol,
            "sheet_gage_column": c_gage,
            "sheet_refzone_column": c_refz,
            "sheet_ncr_column": c_ncr,
            "sheet_method_column": c_method,
            "sheet_type_column": c_type,
        }
        # a real mini-sheet: same columns, widths, bilingual headers and fills
        # as the built xlsx, with sample rows; it re-renders as toggles flip
        prev = QTableWidget()
        prev.setEditTriggers(QAbstractItemView.NoEditTriggers)
        prev.setSelectionMode(QAbstractItemView.NoSelection)
        prev.setFocusPolicy(Qt.NoFocus)
        prev.verticalHeader().setVisible(False)
        prev.setProperty("i18n_skip", True)
        prev.setFixedHeight(150)
        prev.horizontalHeader().setMinimumHeight(36)
        prev.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.AlignTop)
        prev.horizontalHeader().setStyleSheet(
            "QHeaderView::section{background:#1f3864;color:#ffffff;"
            "border:1px solid #16294a;padding:2px;}")   # the sheet's navy band
        self._sheet_preview = prev
        self._sheet_col_preview = prev      # live-update test reads this

        # one sample row per common callout kind, keyed by column
        _SAMPLE = (
            {"bubble": "1", "type": "dim", "feature": "width",
             "requirement": u"12.00 ±0.10", "measured": "12.03",
             "deviation": "+0.03", "result": "PASS", "tier": "MAJOR",
             "method": "caliper", "gage": "CAL-01"},
            {"bubble": "2", "type": "gdt", "feature": "profile",
             "requirement": u"⌓ 0.05 | A", "measured": "0.06",
             "deviation": "+0.01", "result": "FAIL", "tier": "CRITICAL",
             "method": "CMM", "gage": "CMM-1"},
            {"bubble": "3", "type": "hole", "feature": u"Ø5.5",
             "requirement": u"4X Ø5.50 +0.10/0", "measured": "5.55",
             "deviation": "+0.05", "result": "PASS", "tier": "MINOR",
             "method": "pin", "gage": "PIN-55"},
        )
        _PASS, _FAIL = QColor("#d7f0d7"), QColor("#f6d2d2")

        def _refresh_col_preview(*_a):
            tmp = {k: cb.isChecked() for k, cb in _col_flags.items()}
            lang = cb_sheet.currentData() or "both"
            cols = sheet_build.active_columns(tmp)
            prev.setColumnCount(len(cols))
            prev.setRowCount(len(_SAMPLE))
            prev.setHorizontalHeaderLabels(
                [sheet_label(colm.header, lang) for _l, colm in cols])
            for ci, (_l, colm) in enumerate(cols):
                prev.setColumnWidth(ci, max(46, min(240, int(colm.width * 7))))
            for ri, row in enumerate(_SAMPLE):
                for ci, (_l, colm) in enumerate(cols):
                    it = QTableWidgetItem(str(row.get(colm.key, "")))
                    it.setToolTip(it.text())
                    try:
                        it.setBackground(QColor("#" + colm.fill))  # column fill
                    except Exception:
                        pass
                    if colm.key == "result" and it.text():
                        it.setBackground(_PASS if it.text() == "PASS" else _FAIL)
                    prev.setItem(ri, ci, it)

        for _cb in _col_flags.values():
            _cb.stateChanged.connect(_refresh_col_preview)
        cb_sheet.currentIndexChanged.connect(_refresh_col_preview)
        _refresh_col_preview()
        _full(so, QLabel(tr('Inspection sheet preview:')))
        so.addWidget(prev, so.rowCount(), 0, 1, 3)

        # ------------------------------------------------------ FAI report
        # same fields as header (L5)
        fa = _sect(col, 'Inspection report')
        c_faion = _full(fa, QCheckBox(tr('Append the report on save')),
                        "fai_report_on",
                        tr('On by default. One Save produces the ballooned '
                           'PDF with the report pages appended. Off emits the '
                           'ballooned drawing alone.'))
        c_faion.setChecked(bool(self.cfg.get("fai_report_on", True)))
        e_logo = QLineEdit(str(self.cfg.get("fai_logo", "") or ""))
        e_logo.setPlaceholderText(tr('none (company name only)'))
        e_logo.setMaximumWidth(280)
        b_logo = QPushButton(tr('Browse...'))
        b_logo.setMaximumWidth(110)

        def _pick_logo():
            start = e_logo.text() or os.path.expanduser("~")
            f, _ = QFileDialog.getOpenFileName(
                dlg, tr('Report logo'), start,
                "Images (*.png *.jpg *.jpeg *.bmp)")
            if f:
                e_logo.setText(f)
        b_logo.clicked.connect(_pick_logo)
        lgw = QWidget()
        lgl = QHBoxLayout(lgw)
        lgl.setContentsMargins(0, 0, 0, 0)
        lgl.addWidget(e_logo)
        lgl.addWidget(b_logo)
        lgl.addStretch(1)
        _field(fa, tr('Logo'), lgw)
        _tag(e_logo, "fai_logo")
        e_formid = QLineEdit(str(self.cfg.get("fai_form_id", "") or ""))
        e_formid.setMaximumWidth(280)
        _field(fa, tr('Form ID'), e_formid, "fai_form_id")
        e_formrev = QLineEdit(str(self.cfg.get("fai_form_rev", "") or ""))
        e_formrev.setMaximumWidth(280)
        _field(fa, tr('Form revision'), e_formrev, "fai_form_rev")
        cb_paper = _field(fa, tr('Paper'), _combo(), "fai_paper")
        for _p, _lab in (("a4", "A4"), ("letter", "Letter")):
            cb_paper.addItem(_lab, _p)
        cb_paper.setProperty("i18n_skip", True)
        cb_paper.setCurrentIndex(max(0, cb_paper.findData(
            str(self.cfg.get("fai_paper", "a4")))))
        # report language follows document language
        sp_amber = QSpinBox()
        sp_amber.setRange(0, 100)
        sp_amber.setSuffix(" %")
        sp_amber.setSpecialValueText(tr('off'))      # 0 = no amber band
        sp_amber.setValue(int(self.cfg.get("fai_amber_pct", 90) or 0))
        _field(fa, tr('Tolerance-bar amber at'), sp_amber, "fai_amber_pct",
               tr('A reading past this % of the half-tolerance is drawn '
                  'amber (still in tolerance), red once out. Set to off for '
                  'green/red only.'))
        e_cust = QLineEdit(str(self.cfg.get("fai_customer", "") or ""))
        e_cust.setMaximumWidth(280)
        _field(fa, tr('Customer'), e_cust, "fai_customer")
        e_insp = QLineEdit(str(self.cfg.get("fai_inspector", "") or ""))
        e_insp.setMaximumWidth(280)
        _field(fa, tr('Inspector'), e_insp, "fai_inspector")
        _hint(fa, tr('Fills the header of a new sheet and the report, so it '
                     'is not retyped per drawing.'))

        # always-on columns not offered
        sw = _sect(col, 'Show on the report')
        _show = dict(self.cfg.get("fai_show") or {})
        show_cbs = {}
        _sww = QWidget()
        _swl = QGridLayout(_sww)
        _swl.setContentsMargins(0, 0, 0, 0)
        for i, _k in enumerate(FAI_SHOW):
            c = QCheckBox(tr(SHOW_LABELS[_k]))
            c.setChecked(bool(_show.get(_k, True)))
            _tag(c, "fai_show")
            _swl.addWidget(c, i // 3, i % 3)
            show_cbs[_k] = c
        _swl.setColumnStretch(3, 1)
        sw.addWidget(_sww, sw.rowCount(), 0, 1, 3)
        col.addStretch(1)

        # ------------------------------------------------------- Auto-reading
        col = _tab(tabs, 'Vision')

        vavail = vision.available(self.cfg)
        va = _sect(col, 'Vision assist (beta)')
        c_vision = _full(va, QCheckBox(
            tr('Recover symbols and dims the PDF text layer misses')),
            "vision_assist")
        c_vision.setChecked(bool(self.cfg.get("vision_assist")))

        ocr = _sect(col, 'Text (OCR)')
        c_vocr = _full(ocr, QCheckBox(tr('OCR scanned and no-text pages')),
                       "vision_ocr")
        c_vocr.setChecked(bool(self.cfg.get("vision_ocr", True)))
        c_vocr_all = _full(ocr, QCheckBox(
            tr('OCR every page, not just sparse ones')), "vision_ocr_always")
        c_vocr_all.setChecked(bool(self.cfg.get("vision_ocr_always", False)))
        e_vocrconf = _field(ocr, tr('OCR min confidence'),
                            _num(self.cfg.get("vision_ocr_conf",
                                              CFG_DEFAULT["vision_ocr_conf"])),
                            "vision_ocr_conf")
        cb_voeng = _field(ocr, tr('OCR engine'),
                          _combo(["rapidocr", "paddle"], 150),
                          "vision_ocr_engine")
        cb_voeng.setProperty("i18n_skip", True)
        cb_voeng.setCurrentText(
            str(self.cfg.get("vision_ocr_engine", "rapidocr")).lower())

        sy = _sect(col, 'Symbols and blocks')
        # && escapes T mnemonic
        c_vsym = _full(sy, QCheckBox(
            tr('Detect GD&T symbols').replace("&", "&&")), "vision_symbols")
        c_vsym.setProperty("i18n_skip", True)
        c_vsym.setChecked(bool(self.cfg.get("vision_symbols", True)))
        e_vsymconf = _field(sy, tr('Symbol min confidence'),
                            _num(self.cfg.get("vision_sym_conf",
                                              CFG_DEFAULT["vision_sym_conf"])),
                            "vision_sym_conf")
        c_vregion = _full(sy, QCheckBox(
            tr('Group callouts with the block detector')), "vision_region")
        c_vregion.setChecked(bool(self.cfg.get("vision_region", True)))
        e_vrgnconf = _field(
            sy, tr('Block min confidence'),
            _num(self.cfg.get("vision_region_conf",
                              CFG_DEFAULT["vision_region_conf"])),
            "vision_region_conf")
        c_vsecgrp = _full(sy, QCheckBox(
            tr('Grow stacked callouts to the full stack')),
            "vision_section_group")
        c_vsecgrp.setChecked(bool(self.cfg.get("vision_section_group", True)))
        c_vsyminj_t = _full(sy, QCheckBox(
            tr('Inject detected symbols into text-layer reads')),
            "vision_sym_inject_text",
            tr("On: splice GD&T glyphs the detector found into blocks that "
               "already have a PDF text layer (a vector leader symbol is "
               "often missing from the text). Duplicates the text already "
               "shows are skipped."))
        c_vsyminj_t.setChecked(bool(self.cfg.get("vision_sym_inject_text",
                                                 True)))
        c_vsecdbg = _full(sy, QCheckBox(
            tr('Detector debug overlay (adds a ribbon Debug button)')),
            "vision_debug_overlay",
            tr("Adds a ribbon Debug group: Overlay toggle plus a Layers menu "
               "to draw sections, detector blocks, and symbol boxes over the "
               "page."))
        c_vsecdbg.setChecked(bool(self.cfg.get("vision_debug_overlay", False)))
        if not vavail.get("symbols"):
            _mark_missing(c_vsym, "gdt_symbols.onnx")
        if not (vavail["ocr"] and vavail["symbols"]):
            _hint(sy, tr('OCR and symbol passes need the vision build; '
                         'geometry pass works now.'))
        if not vavail.get("region"):
            _mark_missing(c_vregion, "gdt_regions.onnx")
            _hint(sy, tr('Block detector (gdt_regions.onnx) not '
                         'installed; callout grouping uses geometry.'))

        vl = _sect(col, 'Language model (VLM)')
        c_vvlm = _full(vl, QCheckBox(
            tr('Read callouts with the Florence-2 VLM (slow)')), "vision_vlm")
        c_vvlm.setChecked(bool(self.cfg.get("vision_vlm", False)))
        c_vvlm_all = _full(vl, QCheckBox(
            tr('Even when a text layer exists')), "vision_vlm_always")
        c_vvlm_all.setChecked(bool(self.cfg.get("vision_vlm_always", False)))
        c_vxchk = _full(vl, QCheckBox(
            tr('Cross-check risk callouts with the VLM (slow)')),
            "vision_vlm_crosscheck",
            tr('On: run the VLM alongside the ONNX reader on GD&T and '
               'toleranced dimensions as a second opinion. Agreement marks the '
               'row corroborated; a disagreement starts it UNTICKED and shows '
               "the VLM's value, so a doubtful read is asked, not assumed. "
               'Independent of the fallback reader above -- this assists ONNX '
               'without using the VLM as a reader.'))
        c_vxchk.setChecked(bool(self.cfg.get("vision_vlm_crosscheck", False)))
        cb_vvlmeng = _field(vl, tr('VLM engine'),
                            _combo(["florence", "paddleocr_vl"], 170),
                            "vision_vlm_engine")
        cb_vvlmeng.setProperty("i18n_skip", True)
        cb_vvlmeng.setCurrentText(
            str(self.cfg.get("vision_vlm_engine", "florence")).lower())
        cb_vvlmmodel = _field(vl, tr('VLM model'), _combo(None, 220),
                              "vision_vlm_model")
        cb_vvlmmodel.setProperty("i18n_skip", True)
        cb_vvlmmodel.addItem(tr('(default)'), "")
        for _pk in florence.list_packs():
            cb_vvlmmodel.addItem(_pk, _pk)
        _cur_vlmm = str(self.cfg.get("vision_vlm_model", "") or "")
        _vlmm_idx = cb_vvlmmodel.findData(_cur_vlmm)
        if _vlmm_idx < 0:
            cb_vvlmmodel.addItem(_cur_vlmm, _cur_vlmm)
            _vlmm_idx = cb_vvlmmodel.count() - 1
        cb_vvlmmodel.setCurrentIndex(_vlmm_idx)
        _dlw = QWidget()
        dlrow = QHBoxLayout(_dlw)
        dlrow.setContentsMargins(0, 0, 0, 0)
        cb_dlpack = _combo(list(florence.HF_REPOS.keys()), 220)
        cb_dlpack.setProperty("i18n_skip", True)
        b_dl = QPushButton(tr('Download'))
        b_dl.setMaximumWidth(120)
        b_dl.clicked.connect(
            lambda: self._download_vlm(cb_dlpack.currentText(), cb_vvlmmodel))
        dlrow.addWidget(cb_dlpack)
        dlrow.addWidget(b_dl)
        dlrow.addStretch(1)
        _field(vl, tr('Download VLM model'), _dlw)
        c_vsyminj = _full(vl, QCheckBox(
            tr('Inject detected symbols into VLM reads')),
            "vision_sym_inject_vlm",
            tr("On: splice GD&T glyphs the detector found into the VLM's text "
               "(fallback for glyphs the VLM misses). Off: pass only the "
               "category and let the VLM read the callout itself."))
        c_vsyminj.setChecked(bool(self.cfg.get("vision_sym_inject_vlm", True)))
        if not vavail.get("vlm"):
            for _cb in (c_vvlm, c_vvlm_all, c_vxchk, c_vsyminj):
                _mark_missing(_cb, "Florence-2 VLM")
            _hint(vl, tr('Florence-2 VLM pack not installed; use '
                         "'Download VLM model' above to fetch one."))

        cap = _sect(col, 'Drag-box capture')
        c_vdragocr = _full(cap, QCheckBox(
            tr('Drag-box capture reads pixels (OCR or VLM), not the text '
               'layer')), "capture_drag_ocr",
            tr("On: box drags re-read pixels with OCR or the VLM, ignoring "
               "the text layer. Avoids buried or oversized text. Off: use "
               "the text layer."))
        c_vdragocr.setChecked(bool(self.cfg.get("capture_drag_ocr", True)))

        hw = _sect(col, 'Hardware')
        c_vgpu = None
        if gpu.is_linux():
            c_vgpu = _full(hw, QCheckBox(
                tr('Use the GPU pack when installed')), "vision_gpu",
                tr("On by default. Once the pack is installed, detectors run "
                   "on GPU. Untick to force CPU."))
            c_vgpu.setChecked(bool(self.cfg.get("vision_gpu", True)))
            self._gpu_stat = _hint(hw, gpu.status())
            b_gpu = QPushButton(tr('Install or update GPU pack...'))
            b_gpu.setMaximumWidth(260)
            b_gpu.clicked.connect(lambda: self._install_gpu_pack())
            b_gpurm = QPushButton(tr('Remove'))
            b_gpurm.setMaximumWidth(90)
            b_gpurm.setEnabled(gpu.is_installed())
            b_gpurm.clicked.connect(lambda: self._uninstall_gpu_pack(b_gpurm))
            _gpurow = QWidget()
            _gl = QHBoxLayout(_gpurow)
            _gl.setContentsMargins(0, 0, 0, 0)
            _gl.addWidget(b_gpu)
            _gl.addWidget(b_gpurm)
            _gl.addStretch(1)
            hw.addWidget(_gpurow, hw.rowCount(), 0, 1, 3)
            _hint(hw, tr('Needs an NVIDIA GPU, driver >= 580, and system '
                         'python3. Uses your CUDA, else downloads it '
                         '(~1.4 GB). Detectors only; OCR/VLM stay CPU.'))
        cb_vep = _field(hw, tr('Execution provider'),
                        _combo(["auto", "cpu", "directml", "cuda", "coreml"], 150),
                        "vision_ep")
        cb_vep.setProperty("i18n_skip", True)
        cb_vep.setCurrentText(str(self.cfg.get("vision_ep", "auto")).lower())
        provs = vavail.get("providers") or []
        prov_txt = ", ".join(p.replace("ExecutionProvider", "") for p in provs) \
            or "none"
        # actual provider not compiled
        _hint(hw, tr('Execution provider in use: %s   (available: %s)')
                  % (tr('GPU + CPU') if vavail.get("gpu")
                     else tr('CPU only'), prov_txt))
        # why off or degraded
        for _rmsg in (vavail.get("reasons") or {}).values():
            _hint(hw, "! " + _rmsg, "#b7791f")
        _hint(hw, tr('Diagnostics log: %s') % "~/.bubbler.log", "#999999")

        md = _sect(col, 'Custom detector model')
        e_vmodel = QLineEdit(str(self.cfg.get("vision_model", "") or ""))
        e_vmodel.setMaximumWidth(320)
        e_vmodel.setPlaceholderText(tr('(default)'))
        _field(md, tr('Custom model (.onnx)'), e_vmodel, "vision_model",
               tr('Point Bubbler at a locally-trained detector; '
                  'blank uses the bundled model.'))

        co = _sect(col, 'Reader corrections')
        c_corr = _full(co, QCheckBox(
            tr('Collect corrections and callouts (local, opt-in)')),
            "collect_corrections")
        c_corr.setChecked(bool(self.cfg.get("collect_corrections", False)))
        e_corrdir = QLineEdit(str(self.cfg.get("corrections_dir", "") or ""))
        e_corrdir.setPlaceholderText("~/.bubbler/corrections")
        e_corrdir.setMaximumWidth(280)
        b_corrdir = QPushButton(tr('Browse...'))
        b_corrdir.setMaximumWidth(110)

        def _pick_corrdir():
            start = e_corrdir.text() or os.path.expanduser("~")
            d = QFileDialog.getExistingDirectory(
                dlg, tr('Corrections folder'), start)
            if d:
                e_corrdir.setText(d)
        b_corrdir.clicked.connect(_pick_corrdir)
        cdw = QWidget()
        cdl = QHBoxLayout(cdw)
        cdl.setContentsMargins(0, 0, 0, 0)
        cdl.addWidget(e_corrdir)
        cdl.addWidget(b_corrdir)
        cdl.addStretch(1)
        _field(co, tr('Corrections folder'), cdw)
        _tag(e_corrdir, "corrections_dir")
        _hint(co, tr('Off by default. Records (crop + fields, drawing '
                     'name never stored) stay local and are never sent '
                     'automatically. Export from the Data menu to share, '
                     'or train locally (see DEV.md).'))

        e_accdir = QLineEdit(str(self.cfg.get("acceptances_dir", "") or ""))
        e_accdir.setPlaceholderText("~/.bubbler/acceptances")
        e_accdir.setMaximumWidth(280)
        b_accdir = QPushButton(tr('Browse...'))
        b_accdir.setMaximumWidth(110)

        def _pick_accdir():
            start = e_accdir.text() or os.path.expanduser("~")
            d = QFileDialog.getExistingDirectory(
                dlg, tr('Acceptances folder'), start)
            if d:
                e_accdir.setText(d)
        b_accdir.clicked.connect(_pick_accdir)
        adw = QWidget()
        adl = QHBoxLayout(adw)
        adl.setContentsMargins(0, 0, 0, 0)
        adl.addWidget(e_accdir)
        adl.addWidget(b_accdir)
        adl.addStretch(1)
        _field(co, tr('Acceptances folder'), adw)
        _tag(e_accdir, "acceptances_dir")
        _hint(co, tr('Off by default. On save, every bubbled callout becomes a '
                     'local labelled example (crop + fields, drawing name never '
                     'stored); never sent automatically.'))

        # one opt-in drives both corrections and callouts (acceptances)
        def _sync_corr():
            on = c_corr.isChecked()
            for w in (e_corrdir, b_corrdir, e_accdir, b_accdir):
                w.setEnabled(on)
        c_corr.toggled.connect(lambda _b: _sync_corr())
        _sync_corr()

        def _sync_vision():
            on = c_vision.isChecked()
            c_vocr.setEnabled(on)
            c_vocr_all.setEnabled(on and c_vocr.isChecked())
            e_vocrconf.setEnabled(on and c_vocr.isChecked())
            c_vsym.setEnabled(on)
            e_vsymconf.setEnabled(on and c_vsym.isChecked())
            c_vregion.setEnabled(on)
            e_vrgnconf.setEnabled(on and c_vregion.isChecked())
            cb_vep.setEnabled(on)
            cb_voeng.setEnabled(on and c_vocr.isChecked())
            c_vvlm.setEnabled(on)
            c_vvlm_all.setEnabled(on and c_vvlm.isChecked())
            cb_vvlmeng.setEnabled(on and c_vvlm.isChecked())
        c_vision.toggled.connect(lambda _b: _sync_vision())
        c_vocr.toggled.connect(lambda _b: _sync_vision())
        c_vsym.toggled.connect(lambda _b: _sync_vision())
        c_vregion.toggled.connect(lambda _b: _sync_vision())
        c_vvlm.toggled.connect(lambda _b: _sync_vision())
        _sync_vision()
        col.addStretch(1)

        # probes on show
        _stat = StatusPanel(self.cfg)
        _statscroll = QScrollArea()
        _statscroll.setWidgetResizable(True)
        _statscroll.setFrameShape(QScrollArea.NoFrame)
        _statscroll.setWidget(_stat)
        tabs.addTab(_statscroll, tr("Status"))

        def ok():
            # collect + validate before mutating
            try:
                ui_scale_val = float(
                    vars_["ui_scale"].text().replace(",", ".") or 0)
            except ValueError:
                QMessageBox.critical(
                    dlg, tr('Error'), tr('UI scale must be a number'))
                return
            tvar_vals = {}
            for key, e in tvars.items():
                try:
                    val = float(e.text().replace(",", "."))
                    if val <= 0:
                        raise ValueError
                except ValueError:
                    QMessageBox.critical(
                        dlg, tr('Error'),
                        tr('Gage tolerance thresholds must be positive '
                           'numbers'))
                    return
                tvar_vals[key] = val
            try:
                obsw = float(e_obsw.text().replace(",", "."))
                if obsw < 0:
                    raise ValueError
            except ValueError:
                QMessageBox.critical(
                    dlg, tr('Error'),
                    tr('Line width threshold must be a number >= 0'))
                return
            try:
                caprad = float(e_caprad.text().replace(",", "."))
                if caprad <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.critical(
                    dlg, tr('Error'),
                    tr('Capture radius must be a number > 0'))
                return
            try:
                vocrc = float(e_vocrconf.text().replace(",", "."))
                vsymc = float(e_vsymconf.text().replace(",", "."))
                vrgnc = float(e_vrgnconf.text().replace(",", "."))
                if not (0.0 <= vocrc <= 1.0 and 0.0 <= vsymc <= 1.0
                        and 0.0 <= vrgnc <= 1.0):
                    raise ValueError
            except ValueError:
                QMessageBox.critical(
                    dlg, tr('Error'),
                    tr('Vision confidences must be between 0 and 1'))
                return
            # no loose rung ships
            clean = {}
            for u, edits in dpv.items():
                got, why = validate_ladder(
                    {k: e.text() for k, e in edits.items()}, u)
                if why is not None:
                    QMessageBox.critical(
                        dlg, tr('Tolerance ladder refused'),
                        _ladder_reason(why))
                    return
                clean[u] = got

            # apply nothing bails part-way
            self.cfg["ui_scale"] = ui_scale_val
            for key, val in tvar_vals.items():
                self.cfg[key] = val
            self.cfg["icon_color"] = vars_["icon_color"].text()
            self.cfg["company"] = vars_["company"].text()
            self.cfg["hole_pin_auto"] = bool(c_pinauto.isChecked())
            self.cfg["snap_geom"] = bool(c_snap.isChecked())
            self.cfg["leaders"] = bool(c_lead.isChecked())
            self.cfg["leader_trim"] = bool(c_ltrim.isChecked())
            try:
                self.chk_lead.setChecked(self.cfg["leaders"])   # ribbon sync
            except Exception:
                pass
            self.cfg["tier_shapes"] = bool(c_shapes.isChecked())
            self.cfg["tier_shape_map"] = {t: cb.currentText()
                                          for t, cb in shape_cbs.items()}
            self.cfg["type_tier_auto"] = bool(c_typetier.isChecked())
            self.cfg["type_tier_map"] = {tp: cb.currentText()
                                         for tp, cb in tt_cbs.items()}
            if obsw != float(self.cfg.get("obstacle_min_w", 0.5)):
                self._geom_cache = {}
                if hasattr(self, "_obs_cache"):
                    self._obs_cache = {}
                self.__dict__.pop("_leadtrim_cache", None)
            self.cfg["obstacle_min_w"] = obsw
            self.cfg["capture_radius"] = caprad
            _vkeys = ("vision_assist", "vision_ocr", "vision_ocr_always",
                      "vision_ocr_conf", "vision_symbols", "vision_sym_conf",
                      "vision_region", "vision_region_conf", "vision_ep",
                      "vision_ocr_engine", "vision_vlm", "vision_vlm_always",
                      "vision_vlm_engine", "vision_vlm_model",
                      "vision_sym_inject_vlm", "vision_sym_inject_text",
                      "vision_section_group", "vision_gpu")
            _gpu_on = (bool(c_vgpu.isChecked()) if c_vgpu is not None
                       else bool(self.cfg.get("vision_gpu", False)))
            # a gated box marked Missing is disabled: keep its saved value,
            # do not let the empty look overwrite the cfg
            def _cv(cb, key):
                return (bool(cb.isChecked()) if cb.isEnabled()
                        else bool(self.cfg.get(key,
                                               CFG_DEFAULT.get(key, False))))
            _vnew = (bool(c_vision.isChecked()), bool(c_vocr.isChecked()),
                     bool(c_vocr_all.isChecked()), vocrc,
                     _cv(c_vsym, "vision_symbols"), vsymc,
                     _cv(c_vregion, "vision_region"), vrgnc,
                     cb_vep.currentText(), cb_voeng.currentText(),
                     _cv(c_vvlm, "vision_vlm"),
                     _cv(c_vvlm_all, "vision_vlm_always"),
                     cb_vvlmeng.currentText(), cb_vvlmmodel.currentData(),
                     _cv(c_vsyminj, "vision_sym_inject_vlm"),
                     bool(c_vsyminj_t.isChecked()),
                     bool(c_vsecgrp.isChecked()), _gpu_on)
            if _vnew != tuple(self.cfg.get(k) for k in _vkeys):
                self.__dict__.pop("_vword_cache", None)
                vision.reset_sessions()
            self.cfg["vision_assist"] = _vnew[0]
            self.cfg["vision_ocr"] = _vnew[1]
            self.cfg["vision_ocr_always"] = _vnew[2]
            self.cfg["vision_ocr_conf"] = _vnew[3]
            self.cfg["vision_symbols"] = _vnew[4]
            self.cfg["vision_sym_conf"] = _vnew[5]
            self.cfg["vision_region"] = _vnew[6]
            self.cfg["vision_region_conf"] = _vnew[7]
            self.cfg["vision_ep"] = _vnew[8]
            self.cfg["vision_ocr_engine"] = _vnew[9]
            self.cfg["vision_vlm"] = _vnew[10]
            self.cfg["vision_vlm_always"] = _vnew[11]
            self.cfg["vision_vlm_engine"] = _vnew[12]
            self.cfg["vision_vlm_model"] = _vnew[13]
            self.cfg["vision_sym_inject_vlm"] = _vnew[14]
            self.cfg["vision_sym_inject_text"] = _vnew[15]
            self.cfg["vision_section_group"] = _vnew[16]
            self.cfg["vision_gpu"] = _vnew[17]
            self.cfg["vision_vlm_crosscheck"] = _cv(c_vxchk,
                                                    "vision_vlm_crosscheck")
            self.cfg["vision_debug_overlay"] = bool(c_vsecdbg.isChecked())
            if not self.cfg["vision_debug_overlay"]:
                self.cfg["vision_debug_on"] = False
            self.cfg["capture_drag_ocr"] = bool(c_vdragocr.isChecked())
            # one opt-in governs both corrections and callouts (acceptances)
            self.cfg["collect_corrections"] = bool(c_corr.isChecked())
            self.cfg["collect_acceptances"] = bool(c_corr.isChecked())
            self.cfg["corrections_dir"] = e_corrdir.text().strip()
            self.cfg["acceptances_dir"] = e_accdir.text().strip()
            _newmodel = e_vmodel.text().strip()
            if _newmodel != (self.cfg.get("vision_model") or ""):
                self.__dict__.pop("_vword_cache", None)
                vision.reset_sessions()
            self.cfg["vision_model"] = _newmodel
            self.cfg["gentol_ladder"] = "auto"   # ladder follows the units
            _gon = bool(c_dpon.isChecked())
            self.cfg["dp_on"] = _gon      # one master flag
            self.cfg["rib_iso_on"] = _gon  # legacy mirror
            self.cfg["default_iso_class"] = cb_icls.currentText()
            self.cfg["gentol_basic_ref"] = bool(c_brtol.isChecked())
            self.cfg["angular_short_side"] = bool(c_angshort.isChecked())
            for u, got in clean.items():
                self.cfg[ladder_key(u)] = got
            self.cfg["gages"] = {k: bool(c.isChecked())
                                 for k, c in gvars.items()}
            self.cfg["metrology_tools"] = self._read_tool_catalog()
            try:
                self.cfg["gage_resolution_ratio"] = \
                    float(self._gage_ratio_edit.text())
            except ValueError:
                pass
            for key, cb in cvars.items():
                self.cfg[key] = cb.currentText()
            self.cfg["default_tier"] = combo_key(cb_tier)
            new_lang = cb_lang.currentData()
            self.cfg["language"] = new_lang
            set_lang(new_lang)
            self.cfg["mode"] = cb_mode.currentData()
            self.cfg["units"] = cb_units.currentData()
            self.cfg["sheet_lang"] = cb_sheet.currentData()
            # follows document language
            self.cfg["fai_lang"] = {"both": "en-pl", "en": "en",
                                    "pl": "pl"}.get(cb_sheet.currentData(),
                                                    "en-pl")
            self.cfg["sheet_tier_designator"] = c_desig.isChecked()
            self.cfg["sheet_tier_column"] = c_tiercol.isChecked()
            self.cfg["sheet_basic_ref_label"] = c_brlab.isChecked()
            self.cfg["sheet_gage_column"] = c_gage.isChecked()
            self.cfg["sheet_refzone_column"] = c_refz.isChecked()
            self.cfg["sheet_ncr_column"] = c_ncr.isChecked()
            self.cfg["sheet_method_column"] = c_method.isChecked()
            self.cfg["sheet_type_column"] = c_type.isChecked()
            self.cfg["scan_preset"] = cb_scope.currentText()
            self.cfg["scan_presets"] = dict(self._scope_presets)
            self.cfg["fai_logo"] = e_logo.text().strip()
            self.cfg["fai_form_id"] = e_formid.text().strip()
            self.cfg["fai_form_rev"] = e_formrev.text().strip()
            self.cfg["fai_paper"] = cb_paper.currentData() or "a4"
            self.cfg["fai_report_on"] = c_faion.isChecked()
            self.cfg["fai_amber_pct"] = sp_amber.value()
            self.cfg["fai_customer"] = e_cust.text().strip()
            self.cfg["fai_inspector"] = e_insp.text().strip()
            self.cfg["fai_show"] = {k: bool(c.isChecked())
                                    for k, c in show_cbs.items()}
            # save before touching writer
            save_cfg(self.cfg)
            if self.writer is not None:
                self.writer.sheet_lang = self.cfg["sheet_lang"]
                self.writer.tier_designator = \
                    bool(self.cfg["sheet_tier_designator"])
                self.writer.tier_column = bool(self.cfg["sheet_tier_column"])
            dlg.accept()
            try:
                vision.clear_cache()
                self._apply_ui_scale(rebuild=True)
                self._apply_mode()
                retranslate(self)
                self.render()
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.warning(
                    self, tr('Error'),
                    tr('Settings saved, but applying them failed: %s') % e)
                self.set_status(tr('settings saved (apply failed)'))
            else:
                self.set_status(tr('settings saved'))

        bw = QWidget()
        bl = QHBoxLayout(bw)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addStretch(1)
        b_ok = QPushButton("OK")
        b_ok.setDefault(True)
        b_ok.clicked.connect(ok)
        b_cancel = QPushButton(tr('Cancel'))
        b_cancel.clicked.connect(dlg.reject)
        bl.addWidget(b_ok)
        bl.addWidget(b_cancel)
        outer.addWidget(bw)
        dlg.setWindowTitle(tr('Settings'))
        retranslate(dlg)
        avail = self.screen().availableGeometry() if self.screen() else None
        cap_h = int(avail.height() * 0.9) if avail else 900
        cap_w = int(avail.width() * 0.9) if avail else 640
        dlg.setMaximumHeight(cap_h)
        dlg.setMinimumWidth(min(700, cap_w))
        dlg.resize(min(760, cap_w), min(760, cap_h))
        dlg.exec()

    def _install_step_pack(self):
        """Build STEP (OpenCASCADE) venv off-thread"""
        from PySide6.QtCore import QObject, Signal
        prog = QProgressDialog(
            tr('Installing 3D pack (downloads OpenCASCADE, can take a '
               'while)...'), None, 0, 0, self)
        prog.setWindowTitle(tr('3D pack'))
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setCancelButton(None)

        class _Sig(QObject):
            line = Signal(str)
            done = Signal(bool, str)
        sig = _Sig()
        sig.line.connect(lambda s: prog.setLabelText(s[-140:]))

        def _finish(ok, msg):
            prog.close()
            if ok:
                QMessageBox.information(
                    self, tr('3D pack'),
                    tr('3D pack installed. STEP previews can render now.'))
            else:
                QMessageBox.warning(self, tr('3D pack'),
                                    tr('3D pack install failed: %s') % msg)
        sig.done.connect(_finish)

        def _work():
            try:
                ok, msg = step.install(on_line=lambda ln: sig.line.emit(ln))
            except Exception as e:
                ok, msg = False, str(e)
            sig.done.emit(ok, msg)
        import threading
        threading.Thread(target=_work, daemon=True).start()
        prog.exec()

    def _uninstall_step_pack(self, btn=None):
        """Remove the STEP pack, after confirming"""
        if not step.is_installed():
            return
        if QMessageBox.question(
                self, tr('Remove 3D pack'),
                tr('Remove the 3D pack? STEP previews stop until '
                   'reinstalled.')) != QMessageBox.Yes:
            return
        step.uninstall()
        if btn is not None:
            btn.setEnabled(False)
        QMessageBox.information(self, tr('3D pack'), tr('3D pack removed.'))

    def _uninstall_gpu_pack(self, btn=None):
        """Remove the GPU pack, after confirming"""
        if not gpu.is_installed():
            return
        if QMessageBox.question(
                self, tr('Remove GPU pack'),
                tr('Remove the GPU pack? Detectors fall back to CPU until '
                   'reinstalled.')) != QMessageBox.Yes:
            return
        gpu.uninstall()
        if btn is not None:
            btn.setEnabled(False)
        if getattr(self, "_gpu_stat", None) is not None:
            self._gpu_stat.setText(gpu.status())
        QMessageBox.information(self, tr('GPU pack'), tr('GPU pack removed.'))

    # ---- metrology tool catalog editor -------------------------------------

    def _fill_tool_table(self, tools, units):
        """Show the catalog in `units`; stored values are mm."""
        tbl = self._tool_table
        self._tool_units[0] = units
        k = (1.0 / 25.4) if units == "inch" else 1.0
        tbl.setRowCount(len(tools))
        for r, t in enumerate(tools):
            vals = (t.get("name", ""), t.get("kind", ""),
                    "%g" % (float(t.get("resolution", 0) or 0) * k),
                    "%g" % (float(t.get("range_min", 0) or 0) * k),
                    "%g" % (float(t.get("range_max", 0) or 0) * k),
                    ", ".join(t.get("features") or []))
            for c, v in enumerate(vals):
                tbl.setItem(r, c, QTableWidgetItem(str(v)))

    def _add_tool_row(self):
        tbl = self._tool_table
        r = tbl.rowCount()
        tbl.insertRow(r)
        for c, v in enumerate(("New tool", "caliper", "0.01", "0", "150",
                               "length")):
            tbl.setItem(r, c, QTableWidgetItem(v))

    def _remove_tool_row(self):
        r = self._tool_table.currentRow()
        if r >= 0:
            self._tool_table.removeRow(r)

    def _flip_tool_units(self, units):
        if units == self._tool_units[0]:
            return
        self._fill_tool_table(self._read_tool_catalog(), units)  # convert live

    def _read_tool_catalog(self):
        """Read the table back to a catalog list in MILLIMETRES."""
        tbl = self._tool_table
        k = 25.4 if self._tool_units[0] == "inch" else 1.0
        out = []
        for r in range(tbl.rowCount()):
            def cell(c):
                it = tbl.item(r, c)
                return it.text().strip() if it is not None else ""

            name = cell(0)
            if not name:
                continue

            def _f(c, d):
                try:
                    return float(cell(c)) * k
                except ValueError:
                    return d

            feats = [f.strip() for f in cell(5).replace(";", ",").split(",")
                     if f.strip()]
            out.append({"id": name.lower().replace(" ", "_"), "name": name,
                        "kind": cell(1) or name,
                        "resolution": _f(2, 0.01), "accuracy": _f(2, 0.01),
                        "range_min": _f(3, 0.0), "range_max": _f(4, 1e9),
                        "features": feats})
        return out

    def _install_gpu_pack(self):
        """Build GPU venv off-thread"""
        from PySide6.QtCore import QObject, Signal
        want_cuda = not gpu.has_system_cuda()
        prog = QProgressDialog(
            tr('Installing GPU pack (downloads, can take a while)...'),
            None, 0, 0, self)
        prog.setWindowTitle(tr('GPU pack'))
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setCancelButton(None)

        class _Sig(QObject):
            line = Signal(str)
            done = Signal(bool, str)
        sig = _Sig()
        sig.line.connect(lambda s: prog.setLabelText(s[-140:]))

        def _finish(ok, msg):
            prog.close()
            try:
                self._gpu_stat.setText(gpu.status())
            except (RuntimeError, AttributeError):
                pass
            if ok:
                vision.reset_sessions()
                QMessageBox.information(
                    self, tr('GPU pack'),
                    tr('GPU pack installed. Detectors run on GPU now, CPU if '
                       'driver too old.'))
            else:
                QMessageBox.warning(self, tr('GPU pack'),
                                    tr('GPU pack install failed: %s') % msg)
        sig.done.connect(_finish)

        def _work():
            try:
                ok, msg = gpu.install(want_cuda_wheels=want_cuda,
                                      on_line=lambda ln: sig.line.emit(ln))
            except Exception as e:
                ok, msg = False, str(e)
            sig.done.emit(ok, msg)
        import threading
        threading.Thread(target=_work, daemon=True).start()
        prog.exec()

    def _download_vlm(self, pack, model_combo):
        """Fetch Florence-2 pack into ~/.bubbler/models"""
        if getattr(self, "_vlm_dl_task", None) is not None:
            return                               # one download only
        dest = florence.user_models_dir()
        prog = QProgressDialog(
            tr('Downloading %s...') % pack, tr('Cancel'), 0, 100, self)
        prog.setWindowTitle(tr('Download VLM model'))
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setAutoClose(False)
        prog.setAutoReset(False)
        task = _FlorenceDLTask(pack, dest)
        self._vlm_dl_task = task
        self._vlm_dl_prog = prog
        prog.canceled.connect(task.cancel)

        def release():
            prog.reset()
            self._vlm_dl_task = None
            self._vlm_dl_prog = None

        def on_progress(i, n, cur, tot, name):
            base = i / n * 100.0
            step = (cur / tot * 100.0 / n) if tot else 0.0
            prog.setValue(int(base + step))
            short = name.rsplit('/', 1)[-1]
            mb = cur / 1048576.0
            prog.setLabelText(tr('File %d/%d: %s (%.0f MB)')
                              % (i + 1, n, short, mb))

        def on_done(path):
            release()
            if model_combo.findData(pack) < 0:
                model_combo.addItem(pack, pack)
            model_combo.setCurrentIndex(model_combo.findData(pack))
            try:
                vision.clear_cache()
            except Exception:
                pass
            QMessageBox.information(
                self, tr('Download VLM model'),
                tr('Downloaded to:\n%s\n\nSelect OK to save settings and use it.')
                % path)

        def on_failed(msg):
            release()
            if 'cancelled' in msg.lower():
                return
            QMessageBox.warning(self, tr('Download VLM model'),
                                tr('Download failed: %s') % msg)

        task.signals.progress.connect(on_progress)
        task.signals.done.connect(on_done)
        task.signals.failed.connect(on_failed)
        QThreadPool.globalInstance().start(task)
