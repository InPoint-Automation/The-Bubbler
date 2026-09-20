# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Office-style ribbon toolbar mixed into MainWindow.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QComboBox, QCheckBox, QDoubleSpinBox,
                               QPushButton, QSizePolicy)

from .common import TYPES, TIERS, is_simple
from .config import gentol_ladder, units_of
from .scanlib import (GENTOL_SRC_BAND, GENTOL_SRC_BLOCK, GENTOL_SRC_FRAC,
                      GENTOL_SRC_LADDER_DP, GENTOL_SRC_LADDER_ISO,
                      GENTOL_SRC_NONE, GENTOL_SRC_STD, GENTOL_SRC_USER,
                      gentol_readout)
from .widgets import fill_keyed, combo_key
from .icons import icon_button, make_icon, menu_button
from .theme import OFFICE
from .i18n import tr


class RibbonMixin:
    def _rib_group(self, caption, widgets):
        g = QWidget()
        g.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)
        v = QVBoxLayout(g)
        v.setContentsMargins(1, 2, 1, 1)
        v.setSpacing(1)
        roww = QWidget()
        row = QHBoxLayout(roww)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        for w in widgets:
            row.addWidget(w)
        v.addWidget(roww, 0, Qt.AlignTop)
        v.addStretch(1)
        cap = QLabel(tr(caption))
        cap.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        cap.setStyleSheet("font-size:7pt; color:%s;" % OFFICE["muted"])
        v.addWidget(cap, 0, Qt.AlignBottom)
        return g

    def _build_ribbon(self):
        from PySide6.QtWidgets import QToolBar
        tb = QToolBar("ribbon")
        self._ribbon_tb = tb
        tb.setObjectName("ribbon")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(Qt.TopToolBarArea, tb)

        self.btn_save = icon_button("save", self.save, "Save  Ctrl+S",
                                    "Save")
        # close-out own explicit action
        self.btn_runs = menu_button(
            "report", "Inspection run", "Run", items=[
                ("report", "Issue report", self.issue_report),
                ("check", "Issue and close out inspection",
                 self.issue_and_close),
                ("check", "Close out inspection...", self.close_out),
                ("add", "Start a new run", self.start_new_run),
                ("pages", "Switch run...", self.switch_run)])
        tb.addWidget(self._rib_group(tr('File'), [
            self.btn_save, self.btn_runs,
            icon_button("header", self.header_editor, "Header", "Header"),
            menu_button("settings", "Options", "Options", items=[
                ("settings", "Settings", self.settings),
                ("help", "Keybinds  F1", self.show_keys)])]))
        tb.addSeparator()
        self.lbl_page = QLabel("1/1")
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.lbl_page.setToolTip(tr('Page'))
        self.lbl_page.setProperty("i18n_skip", True)
        self.lbl_page.setStyleSheet(
            "font-size:8pt; font-weight:bold; color:%s; padding:0 3px;"
            % OFFICE["accent"])
        self.btn_nav = icon_button("pages", self.toggle_nav,
                                   "Page navigator", "Pages", toggle=True)
        self.btn_nav.setEnabled(self.doc.page_count > 1)
        # button not label
        self.lbl_gentol = QPushButton("")
        self.lbl_gentol.setProperty("i18n_skip", True)
        self.lbl_gentol.setFlat(True)
        self.lbl_gentol.setCursor(Qt.PointingHandCursor)
        # drop button default padding
        self.lbl_gentol.setSizePolicy(QSizePolicy.Maximum,
                                      QSizePolicy.Preferred)
        self.lbl_gentol.setMinimumWidth(0)
        self.lbl_gentol.clicked.connect(self.edit_gentol)
        tb.addWidget(self._rib_group(tr('Page'), [
            icon_button("prev", lambda: self.flip(-1),
                        "Previous page  PgUp"),
            self.lbl_page,
            icon_button("next", lambda: self.flip(1), "Next page  PgDn"),
            self.btn_nav]))
        tb.addSeparator()
        tb.addWidget(self._rib_group(tr('View'), [
            menu_button("zoom_in", "View controls", "View", items=[
                ("fit", "Fit  Home", self.fit),
                ("zoom_in", "Zoom in", lambda: self.rezoom(1.25)),
                ("zoom_out", "Zoom out", lambda: self.rezoom(0.8)),
                ("rotate", "Rotate", self.rotate)])]))
        tb.addSeparator()
        tb.addWidget(self._rib_group(tr('Align'), [
            menu_button("align_h", "Align and distribute", "Align", items=[
                ("align_h", "Align row", lambda: self.align_sel("h")),
                ("align_v", "Align col", lambda: self.align_sel("v")),
                ("dist_h", "Distribute H", lambda: self.distribute_sel("h")),
                ("dist_v", "Distribute V", lambda: self.distribute_sel("v"))])]))
        tb.addSeparator()
        self.btn_measure = icon_button("measure", self.toggle_measure,
                                       "Measure mode  M", "Measure",
                                       toggle=True)
        self.btn_calc = icon_button("calc", self.toggle_calc,
                                    "Calculator  Ctrl+K", "Calc",
                                    toggle=True)
        self.btn_panel = icon_button("panel", self.toggle_panel,
                                     "Bubble list  B", "List", toggle=True)
        self.btn_scan = icon_button("scan", self.scan_page, "Scan page",
                                    "Scan")
        self.btn_scan_all = icon_button("scan", lambda: self.scan_page(True),
                                        "Scan all pages", "Scan all")
        tb.addWidget(self._rib_group(tr('Bubbles'), [
            icon_button("undo", self.undo, "Undo  Ctrl+Z", "Undo"),
            self.btn_measure, self.btn_calc, self.btn_panel,
            self.btn_scan, self.btn_scan_all]))
        tb.addSeparator()
        tb.addWidget(self._rib_group(tr('Data'), [
            menu_button("report", "Reports and data import", "Data", items=[
                ("report", "OOT report", self.oot_report),
                ("import", "Import CMM/CSV", self.cmm_import),
                ("report", "Report bad read...", self.report_bad_read),
                ("import", "Review corrections...",
                 self.review_corrections),
                ("report", "Preview or print output...",
                 self.preview_output),
                ("import", "3D preview...", self.show_step_preview)])]))
        tb.addSeparator()
        self.btn_tool_add = icon_button("add", lambda: self.set_tool("add"),
                                        "Add bubbles  A", "Add", toggle=True)
        self.btn_tool_add.setChecked(True)
        self.btn_tool_sel = icon_button("select",
                                        lambda: self.set_tool("select"),
                                        "Select/move  V", "Select",
                                        toggle=True)
        self.btn_autobub = icon_button("check", None,
                                       "Auto-bubble: click a callout to "
                                       "bubble it at once. Off: review it "
                                       "in the dialog first.", None,
                                       toggle=True, size=16)
        self.btn_autobub.setChecked(
            bool(self.cfg.get("click_auto_bubble", True)))
        self.btn_autobub.toggled.connect(self._autobub_changed)
        tb.addWidget(self._rib_group(tr('Tools'),
                                     [self.btn_tool_add, self.btn_tool_sel,
                                      self.btn_autobub]))
        tb.addSeparator()

        self.cb_type = QComboBox()
        fill_keyed(self.cb_type, TYPES, self.last["type"])
        self.cb_type.setMaximumWidth(110)
        self.cb_type.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_type.activated.connect(
            lambda _i: self._rib_set("type", combo_key(self.cb_type)))

        self.chk_iso = QCheckBox("ISO 2768")
        self.chk_iso.toggled.connect(self._iso_changed)
        self.cb_icls = QComboBox()
        self.cb_icls.addItems(["f", "m", "c", "v"])
        self.cb_icls.setCurrentText(self.last["icls"])
        self.cb_icls.setMaximumWidth(38)
        self.cb_icls.activated.connect(self._icls_changed)
        self._iso_field = self._field("", self.chk_iso)
        self._icls_field = self._field("class", self.cb_icls)
        self._sync_units_controls()

        self.e_tsym = QLineEdit()
        self.e_tsym.setMaximumWidth(38)
        self.e_tsym.editingFinished.connect(
            lambda: self._rib_set("tsym", self.e_tsym.text()))
        self.e_tmax = QLineEdit()
        self.e_tmax.setMaximumWidth(38)
        self.e_tmax.editingFinished.connect(
            lambda: self._rib_set("tmax", self.e_tmax.text()))
        self.e_tmin = QLineEdit()
        self.e_tmin.setMaximumWidth(38)
        self.e_tmin.editingFinished.connect(
            lambda: self._rib_set("tmin", self.e_tmin.text()))
        self.cb_tier = QComboBox()
        # "" is AUTO sentinel
        fill_keyed(self.cb_tier, TIERS, self.last["tier"])
        self.cb_tier.setItemText(0, tr('auto'))
        self.cb_tier.setMaximumWidth(70)
        self.cb_tier.activated.connect(
            lambda _i: self._rib_set("tier", combo_key(self.cb_tier)))
        # icon only
        self.btn_rib_reset = icon_button("rotate", self.reset_ribbon,
                                         "Reset these to defaults")
        tb.addWidget(self._rib_group(tr('Next bubble'), [
            self._field(tr('type'), self.cb_type),
            self._iso_field,
            self._icls_field,
            self._field("tol ±", self.e_tsym),
            self._field("tol max", self.e_tmax),
            self._field("tol min", self.e_tmin),
            self._field("tier", self.cb_tier),
            self.lbl_gentol,
            self._field("", self.btn_rib_reset)]))
        self._sync_gentol()
        tb.addSeparator()

        self.chk_lead = QCheckBox(tr('Leaders'))
        self.chk_lead.setChecked(bool(self.cfg.get("leaders")))
        self.chk_lead.toggled.connect(self._lead_changed)
        self.sp_rad = QDoubleSpinBox()
        self.sp_rad.setRange(3, 40)
        self.sp_rad.setDecimals(0)
        self.sp_rad.setMaximumWidth(58)
        self.sp_rad.setValue(float(self.cfg.get("radius", 9)))
        self.sp_rad.valueChanged.connect(
            lambda v: self._style_set("radius", v))
        self.sp_fsz = QDoubleSpinBox()
        self.sp_fsz.setRange(4, 30)
        self.sp_fsz.setDecimals(0)
        self.sp_fsz.setMaximumWidth(58)
        self.sp_fsz.setValue(float(self.cfg.get("fontsz", 10)))
        self.sp_fsz.valueChanged.connect(
            lambda v: self._style_set("fontsz", v))
        tb.addWidget(self._rib_group(tr('Style'), [
            self._field("", self.chk_lead),
            self._field("radius", self.sp_rad),
            self._field("font", self.sp_fsz)]))
        if self.cfg.get("vision_debug_overlay"):
            tb.addWidget(self._debug_ribbon_group())
        self._apply_mode()

    def _debug_ribbon_group(self):
        """debug overlay control"""
        from PySide6.QtWidgets import QToolButton, QMenu
        # saves ribbon width
        b = QToolButton()
        b.setIcon(make_icon("search", None, 22))
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setToolTip(tr('Debug overlay'))
        b.setAutoRaise(True)
        b.setFocusPolicy(Qt.NoFocus)
        b.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(b)
        self.btn_overlay = m.addAction(tr('Overlay'))
        self.btn_overlay.setCheckable(True)
        self.btn_overlay.setChecked(bool(self.cfg.get("vision_debug_on")))
        self.btn_overlay.triggered.connect(self.toggle_debug_overlay)
        m.addSeparator()
        cur = set(self.cfg.get("vision_debug_layers") or [])
        for key, label in (("sections", tr('Callout sections')),
                           ("regions", tr('Detector blocks')),
                           ("symbols", tr('GD&T symbols'))):
            act = m.addAction(label)
            act.setCheckable(True)
            act.setChecked(key in cur)
            act.toggled.connect(
                lambda on, k=key: self._toggle_debug_layer(k, on))
        b.setMenu(m)
        b._menu = m
        return self._rib_group(tr('Debug'), [b])

    # source -> readout name
    _GENTOL_SRC = {
        GENTOL_SRC_BAND: "band table",
        GENTOL_SRC_BLOCK: "printed .X block",
        GENTOL_SRC_FRAC: "printed fractions",
        GENTOL_SRC_STD: "ISO 2768",
        GENTOL_SRC_LADDER_DP: "settings ladder",
        GENTOL_SRC_LADDER_ISO: "settings ISO 2768",
        GENTOL_SRC_NONE: "no general tol",
        GENTOL_SRC_USER: "corrected by hand",
    }

    def _sync_gentol(self):
        """which general tolerance owns current page"""
        lbl = getattr(self, "lbl_gentol", None)
        if lbl is None:
            return
        try:
            g = self._page_gtols()
        except Exception:
            g = {}
        src, val, inh = gentol_readout(g, self.cfg, self.drawing)
        name = tr(self._GENTOL_SRC.get(src, src))
        line2 = (tr('inherited') + "  " + val).strip() if inh else val
        lbl.setText(("%s  %s\n%s" % (tr('gen tol'), name, line2)).strip())
        fixed = src == GENTOL_SRC_USER
        lbl.setStyleSheet(
            "font-size:7pt; padding:0px 2px 0px 5px; margin:0px;"
            "border:none; background:transparent; text-align:left; color:%s;"
            % ("#2b6cb0" if fixed else
               "#b7791f" if inh else OFFICE["muted"]))
        if fixed:
            tip = tr('Hand-corrected for this drawing. Click to change.')
        elif inh:
            tip = tr('From page 1, reused here. Click to correct.')
        else:
            tip = tr('The general tolerance the next bubble inherits on this '
                     'page. Click to correct.')
        lbl.setToolTip(tip)

    def _apply_mode(self):
        simple = is_simple(self.cfg)
        for b in (getattr(self, "btn_scan", None),
                  getattr(self, "btn_scan_all", None)):
            if b is not None:
                b.setVisible(not simple)

    def _sync_units_controls(self):
        # names one ladder
        asme = units_of(self.cfg, self.drawing) == "asme_inch"
        if gentol_ladder(self.cfg, self.drawing) == "decimal":
            src, tip = "Y14.5 tol", "ASME title-block decimal-place tolerance"
            on = bool(self.cfg.get("dp_on"))
        else:
            src, tip = "ISO 2768", "ISO 2768 auto"
            on = bool(self.cfg.get("rib_iso_on"))
        self.chk_iso.setProperty("i18n_src", src)
        self.chk_iso.setText(tr(src))
        self.chk_iso.setToolTip(tr(tip))
        self.chk_iso.blockSignals(True)
        self.chk_iso.setChecked(on)
        self.chk_iso.blockSignals(False)
        self._icls_field.setVisible(not asme)
        self._sync_gentol()          # ladder decides readout too
        self._fill_munits()          # "other" is other system

    def _field(self, label, widget, top=None):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(1, 0, 1, 0)
        v.setSpacing(1)
        if top is not None:
            v.addWidget(top)
        lab = QLabel(tr(label))
        lab.setStyleSheet("font-size:7pt; color:%s;" % OFFICE["muted"])
        v.addWidget(lab)
        v.addWidget(widget)
        return w

