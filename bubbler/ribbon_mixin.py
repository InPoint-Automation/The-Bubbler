# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Office-style ribbon toolbar, mixed into MainWindow.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QComboBox, QCheckBox, QDoubleSpinBox,
                               QToolBar, QSizePolicy)

from .common import TYPES, GROUPS, TIERS
from .icons import icon_button
from .theme import OFFICE
from .i18n import tr


class RibbonMixin:
    def _rib_group(self, caption, widgets):
        """Ribbon group: control row + caption beneath."""
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
        # checked state from Office stylesheet
        self.addToolBar(Qt.TopToolBarArea, tb)

        # File
        tb.addWidget(self._rib_group("File / Plik", [
            icon_button("save", self.save, "Save  Ctrl+S", "Save"),
            icon_button("header", self.header_editor, "Header", "Header"),
            icon_button("settings", self.settings, "Settings", "Setup"),
            icon_button("help", self.show_keys, "Keybinds  F1", "Keys")]))
        tb.addSeparator()
        # View
        tb.addWidget(self._rib_group("View / Widok", [
            icon_button("prev", lambda: self.flip(-1), "PgUp", "Prev"),
            icon_button("next", lambda: self.flip(1), "PgDn", "Next"),
            icon_button("fit", self.fit, "Fit  Home", "Fit"),
            icon_button("zoom_in", lambda: self.rezoom(1.25), "Zoom +", "In"),
            icon_button("zoom_out", lambda: self.rezoom(0.8), "Zoom -", "Out"),
            icon_button("rotate", self.rotate, "Rotate", "Rot")]))
        tb.addSeparator()
        # Bubble
        self.btn_measure = icon_button("measure", self.toggle_measure,
                                       "Measure mode  M", "Measure",
                                       toggle=True)
        self.btn_panel = icon_button("panel", self.toggle_panel,
                                     "Bubble list  B", "List", toggle=True)
        tb.addWidget(self._rib_group("Bubbles / Bąble", [
            icon_button("undo", self.undo, "Undo  Ctrl+Z", "Undo"),
            self.btn_measure, self.btn_panel,
            icon_button("scan", self.scan_page, "Scan page", "Scan"),
            icon_button("scan", lambda: self.scan_page(True),
                        "Scan all pages", "Scan all")]))
        tb.addSeparator()
        # Tool
        self.btn_tool_add = icon_button("add", lambda: self.set_tool("add"),
                                        "Add bubbles  A", "Add", toggle=True)
        self.btn_tool_add.setChecked(True)
        self.btn_tool_sel = icon_button("select",
                                        lambda: self.set_tool("select"),
                                        "Select/move  V", "Select",
                                        toggle=True)
        tb.addWidget(self._rib_group("Tools / Narzędzia",
                                     [self.btn_tool_add, self.btn_tool_sel]))
        tb.addSeparator()
        # Arrange
        tb.addWidget(self._rib_group("Arrange / Rozmieść", [
            icon_button("align_h", lambda: self.align_sel("h"),
                        "Align row", "Row"),
            icon_button("align_v", lambda: self.align_sel("v"),
                        "Align col", "Col"),
            icon_button("dist_h", lambda: self.distribute_sel("h"),
                        "Distribute H", "Dist H"),
            icon_button("dist_v", lambda: self.distribute_sel("v"),
                        "Distribute V", "Dist V")]))
        tb.addSeparator()

        # next bubble defaults
        self.cb_type = QComboBox()
        self.cb_type.addItems(TYPES)
        self.cb_type.setCurrentText(self.last["type"])
        self.cb_type.setMaximumWidth(110)
        self.cb_type.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_type.activated.connect(
            lambda _i: self._rib_set("type", self.cb_type.currentText(),
                                     group=True))
        self.cb_group = QComboBox()
        self.cb_group.addItems(GROUPS)
        self.cb_group.setCurrentText(self.last["group"])
        self.cb_group.setMaximumWidth(120)
        self.cb_group.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_group.activated.connect(
            lambda _i: self._rib_set("group", self.cb_group.currentText()))

        self.chk_iso = QCheckBox("ISO 2768")
        self.chk_iso.setToolTip("ISO 2768 auto")
        self.chk_iso.setChecked(bool(self.cfg.get("rib_iso_on")))
        self.chk_iso.toggled.connect(self._iso_changed)
        self.cb_icls = QComboBox()
        self.cb_icls.addItems(["f", "m", "c", "v"])
        self.cb_icls.setCurrentText(self.last["icls"])
        self.cb_icls.activated.connect(self._icls_changed)
        isow = self._field("iso class", self.cb_icls, top=self.chk_iso)

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
        tb.addWidget(self._rib_group("Next bubble / Następny", [
            self._field("type / typ", self.cb_type),
            self._field("group / grupa", self.cb_group),
            isow,
            self._field("tol ±", self.e_tsym),
            self._field("tol max", self.e_tmax),
            self._field("tol min", self.e_tmin),
            self._field("tier", self.cb_tier)]))
        tb.addSeparator()

        # bubble style
        self.chk_lead = QCheckBox("Leaders / Linie")
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
        tb.addWidget(self._rib_group("Style / Styl", [
            self._field("", self.chk_lead),
            self._field("radius", self.sp_rad),
            self._field("font", self.sp_fsz)]))

    def _field(self, label, widget, top=None):
        """Captioned ribbon control: label above widget."""
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

