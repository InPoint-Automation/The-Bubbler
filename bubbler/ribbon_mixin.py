# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Office-style ribbon toolbar, mixed into MainWindow.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QComboBox, QCheckBox, QDoubleSpinBox,
                               QSizePolicy)

from .common import TYPES, GROUPS, TIERS, is_simple
from .config import units_of
from .widgets import fill_keyed, combo_key
from .icons import icon_button, menu_button
from .theme import OFFICE
from .i18n import tr


class RibbonMixin:
    def _rib_group(self, caption, widgets):
        g = QWidget()
        g.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)
        v = QVBoxLayout(g)
        v.setContentsMargins(3, 2, 3, 1)
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

        tb.addWidget(self._rib_group(tr('File'), [
            icon_button("save", self.save, "Save  Ctrl+S", "Save"),
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
        tb.addWidget(self._rib_group(tr('Page'), [
            icon_button("prev", lambda: self.flip(-1), "PgUp", "Prev"),
            self.lbl_page,
            icon_button("next", lambda: self.flip(1), "PgDn", "Next"),
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
        self.btn_panel = icon_button("panel", self.toggle_panel,
                                     "Bubble list  B", "List", toggle=True)
        self.btn_scan = icon_button("scan", self.scan_page, "Scan page",
                                    "Scan")
        self.btn_scan_all = icon_button("scan", lambda: self.scan_page(True),
                                        "Scan all pages", "Scan all")
        tb.addWidget(self._rib_group(tr('Bubbles'), [
            icon_button("undo", self.undo, "Undo  Ctrl+Z", "Undo"),
            self.btn_measure, self.btn_panel,
            self.btn_scan, self.btn_scan_all]))
        tb.addSeparator()
        tb.addWidget(self._rib_group(tr('Data'), [
            menu_button("report", "Reports and data import", "Data", items=[
                ("report", "OOT report", self.oot_report),
                ("import", "Import CMM/CSV", self.cmm_import),
                ("report", "Report bad read...", self.report_bad_read),
                ("import", "Review corrections...",
                 self.review_corrections)])]))
        tb.addSeparator()
        self.btn_tool_add = icon_button("add", lambda: self.set_tool("add"),
                                        "Add bubbles  A", "Add", toggle=True)
        self.btn_tool_add.setChecked(True)
        self.btn_tool_sel = icon_button("select",
                                        lambda: self.set_tool("select"),
                                        "Select/move  V", "Select",
                                        toggle=True)
        tb.addWidget(self._rib_group(tr('Tools'),
                                     [self.btn_tool_add, self.btn_tool_sel]))
        tb.addSeparator()

        self.cb_type = QComboBox()
        fill_keyed(self.cb_type, TYPES, self.last["type"])
        self.cb_type.setMaximumWidth(110)
        self.cb_type.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_type.activated.connect(
            lambda _i: self._rib_set("type", combo_key(self.cb_type),
                                     group=True))
        self.cb_group = QComboBox()
        fill_keyed(self.cb_group, GROUPS, self.last["group"])
        self.cb_group.setMaximumWidth(120)
        self.cb_group.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_group.activated.connect(
            lambda _i: self._rib_set("group", combo_key(self.cb_group)))

        self.chk_iso = QCheckBox("ISO 2768")
        self.chk_iso.toggled.connect(self._iso_changed)
        self.cb_icls = QComboBox()
        self.cb_icls.addItems(["f", "m", "c", "v"])
        self.cb_icls.setCurrentText(self.last["icls"])
        self.cb_icls.setMaximumWidth(48)
        self.cb_icls.activated.connect(self._icls_changed)
        self._iso_field = self._field("", self.chk_iso)
        self._icls_field = self._field("class", self.cb_icls)
        self._sync_units_controls()

        self.e_tsym = QLineEdit()
        self.e_tsym.setMaximumWidth(60)
        self.e_tsym.editingFinished.connect(
            lambda: self._rib_set("tsym", self.e_tsym.text()))
        self.e_tmax = QLineEdit()
        self.e_tmax.setMaximumWidth(60)
        self.e_tmax.editingFinished.connect(
            lambda: self._rib_set("tmax", self.e_tmax.text()))
        self.e_tmin = QLineEdit()
        self.e_tmin.setMaximumWidth(60)
        self.e_tmin.editingFinished.connect(
            lambda: self._rib_set("tmin", self.e_tmin.text()))
        self.cb_tier = QComboBox()
        self.cb_tier.addItems(TIERS)
        self.cb_tier.setCurrentText(self.last["tier"])
        self.cb_tier.setMaximumWidth(70)
        self.cb_tier.activated.connect(
            lambda _i: self._rib_set("tier", self.cb_tier.currentText()))
        tb.addWidget(self._rib_group(tr('Next bubble'), [
            self._field(tr('type'), self.cb_type),
            self._field(tr('group'), self.cb_group),
            self._iso_field,
            self._icls_field,
            self._field("tol ±", self.e_tsym),
            self._field("tol max", self.e_tmax),
            self._field("tol min", self.e_tmin),
            self._field("tier", self.cb_tier)]))
        tb.addSeparator()

        self.chk_lead = QCheckBox(tr('Leaders'))
        self.chk_lead.setChecked(bool(self.cfg.get("leaders")))
        self.chk_lead.toggled.connect(self._lead_changed)
        self.sp_rad = QDoubleSpinBox()
        self.sp_rad.setRange(3, 40)
        self.sp_rad.setDecimals(0)
        self.sp_rad.setValue(float(self.cfg.get("radius", 9)))
        self.sp_rad.valueChanged.connect(
            lambda v: self._style_set("radius", v))
        self.sp_fsz = QDoubleSpinBox()
        self.sp_fsz.setRange(4, 30)
        self.sp_fsz.setDecimals(0)
        self.sp_fsz.setValue(float(self.cfg.get("fontsz", 10)))
        self.sp_fsz.valueChanged.connect(
            lambda v: self._style_set("fontsz", v))
        tb.addWidget(self._rib_group(tr('Style'), [
            self._field("", self.chk_lead),
            self._field("radius", self.sp_rad),
            self._field("font", self.sp_fsz)]))
        self._apply_mode()

    def _apply_mode(self):
        simple = is_simple(self.cfg)
        for b in (getattr(self, "btn_scan", None),
                  getattr(self, "btn_scan_all", None)):
            if b is not None:
                b.setVisible(not simple)

    def _sync_units_controls(self):
        asme = units_of(self.cfg) == "asme_inch"
        if asme:
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

    def _field(self, label, widget, top=None):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 0, 2, 0)
        v.setSpacing(1)
        if top is not None:
            v.addWidget(top)
        lab = QLabel(tr(label))
        lab.setStyleSheet("font-size:7pt; color:%s;" % OFFICE["muted"])
        v.addWidget(lab)
        v.addWidget(widget)
        return w

