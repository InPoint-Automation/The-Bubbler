# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Keybind help, header editor, Settings dialog. Mixed into MainWindow.

import os

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QLabel, QLineEdit, QComboBox,
                               QCheckBox, QPushButton, QMessageBox,
                               QTabWidget, QScrollArea, QFileDialog,
                               QProgressDialog)

from .common import TYPES, TIERS, SHAPES
from .config import save_cfg, CFG_DEFAULT
from .sheet import HEADER_FIELDS
from .scanlib import GAGES
from .i18n import tr, set_lang, retranslate
from .keyhelp import _keybinds_html
from . import vision, florence


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
        for i, (cell, label) in enumerate(HEADER_FIELDS):
            hlab = QLabel(label)
            hlab.setProperty("i18n_skip", True)
            g.addWidget(hlab, i, 0)
            seed = prefill[cell] if cell in prefill else current.get(cell, "")
            e = QLineEdit(str(seed))
            e.focusInEvent = (lambda ev, ent=e:
                              (setattr(self, "_hdr_focus", ent),
                               QLineEdit.focusInEvent(ent, ev)))
            g.addWidget(e, i, 1)
            entries[cell] = e

        def apply():
            self.writer.set_header({c: e.text() for c, e in entries.items()})
            try:
                self.writer.save()
            except Exception as ex:
                QMessageBox.critical(win, tr('Sheet error'), str(ex))
                return
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
        win.finished.connect(lambda _r: setattr(self, "_hdr_win", None))
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

        def _page(title):
            page = QWidget()
            grid = QGridLayout(page)
            grid.setColumnStretch(1, 1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setWidget(page)
            tabs.addTab(scroll, tr(title))
            return grid

        vars_ = {}
        g = _page("General")
        r = 0
        g.addWidget(QLabel(tr('Language')), r, 0)
        cb_lang = QComboBox()
        cb_lang.addItem("English", "en")
        cb_lang.addItem("Polski", "pl")
        cb_lang.setCurrentIndex(
            1 if self.cfg.get("language", "en") == "pl" else 0)
        g.addWidget(cb_lang, r, 1)
        r += 1
        g.addWidget(QLabel(tr('Mode')), r, 0)
        cb_mode = QComboBox()
        cb_mode.addItem(tr('Advanced'), "advanced")
        cb_mode.addItem(tr('Simple'), "simple")
        cb_mode.setCurrentIndex(
            1 if self.cfg.get("mode") == "simple" else 0)
        g.addWidget(cb_mode, r, 1)
        r += 1
        g.addWidget(QLabel(tr('Units')), r, 0)
        cb_units = QComboBox()
        cb_units.addItem("ISO (mm)", "iso_mm")
        cb_units.addItem("ASME (inch)", "asme_inch")
        cb_units.setCurrentIndex(
            1 if self.cfg.get("units") == "asme_inch" else 0)
        g.addWidget(cb_units, r, 1)
        r += 1
        g.addWidget(QLabel(tr('Sheet language')), r, 0)
        cb_sheet = QComboBox()
        cb_sheet.addItem("EN + PL", "both")
        cb_sheet.addItem("English", "en")
        cb_sheet.addItem("Polski", "pl")
        _sl = self.cfg.get("sheet_lang", "both")
        cb_sheet.setCurrentIndex({"both": 0, "en": 1, "pl": 2}.get(_sl, 0))
        g.addWidget(cb_sheet, r, 1)
        r += 1
        for label, key in ((tr('Company'), "company"),
                           (tr('Accent color'), "icon_color"),
                           ("UI scale (0=auto)", "ui_scale")):
            g.addWidget(QLabel(label), r, 0)
            e = QLineEdit(str(self.cfg.get(key, CFG_DEFAULT[key])))
            g.addWidget(e, r, 1)
            vars_[key] = e
            r += 1
        g = _page("Gages")
        r = 0
        ttl = QLabel(tr('Available gages'))
        ttl.setStyleSheet("font-weight:bold;")
        g.addWidget(ttl, r, 0, 1, 2)
        r += 1
        tvars = {}
        for label, key in ((tr('CMM if tol ≤'), "cmm_tol"),
                           (tr('Micrometer if tol ≤'),
                            "micrometer_tol")):
            g.addWidget(QLabel(label), r, 0)
            e = QLineEdit("%g" % float(self.cfg.get(key, CFG_DEFAULT[key])))
            g.addWidget(e, r, 1)
            tvars[key] = e
            r += 1
        gcfg = dict(self.cfg.get("gages") or {})
        gvars = {}
        for gname in GAGES:
            c = QCheckBox(gname)
            c.setProperty("i18n_skip", True)
            c.setChecked(bool(gcfg.get(gname, True)))
            g.addWidget(c, r, 0, 1, 2)
            gvars[gname] = c
            r += 1
        g = _page("Bubbles")
        r = 0
        c_pinauto = QCheckBox(tr('Hole pin Ø = nominal'))
        c_pinauto.setChecked(bool(self.cfg.get("hole_pin_auto", False)))
        g.addWidget(c_pinauto, r, 0, 1, 2)
        r += 1
        c_snap = QCheckBox(tr('Snap to drawing geometry'))
        c_snap.setChecked(bool(self.cfg.get("snap_geom", True)))
        g.addWidget(c_snap, r, 0, 1, 2)
        r += 1
        g.addWidget(QLabel("Bubble avoids lines wider than (pt) /\n"
                           "Numerek omija linie grubsze niż"), r, 0)
        e_obsw = QLineEdit("%g" % float(
            self.cfg.get("obstacle_min_w", CFG_DEFAULT["obstacle_min_w"])))
        g.addWidget(e_obsw, r, 1)
        r += 1
        g.addWidget(QLabel("Click capture radius (pt) /\n"
                           "Promień przechwytywania kliknięcia"), r, 0)
        e_caprad = QLineEdit("%g" % float(
            self.cfg.get("capture_radius", CFG_DEFAULT["capture_radius"])))
        g.addWidget(e_caprad, r, 1)
        r += 1
        g = _page("Tiers")
        r = 0
        c_shapes = QCheckBox(tr('Shape-code criticality tiers '
                                '(colour-blind safe)'))
        c_shapes.setChecked(bool(self.cfg.get("tier_shapes", True)))
        c_shapes.setToolTip(tr("On: tiers differ by shape as well as colour. "
                               "Off: all balloons are circles (colour only)."))
        g.addWidget(c_shapes, r, 0, 1, 2)
        r += 1
        smap = dict(self.cfg.get("tier_shape_map")
                    or CFG_DEFAULT["tier_shape_map"])
        shape_cbs = {}
        for tier in ("red", "blue", "green"):
            lab = QLabel(tier)
            lab.setProperty("i18n_skip", True)
            g.addWidget(lab, r, 0)
            cb = QComboBox()
            cb.addItems(SHAPES)
            cur = smap.get(tier, "circle")
            cb.setCurrentText(cur if cur in SHAPES else "circle")
            g.addWidget(cb, r, 1)
            shape_cbs[tier] = cb
            r += 1

        def _sync_shapes():
            for cb in shape_cbs.values():
                cb.setEnabled(c_shapes.isChecked())
        c_shapes.toggled.connect(lambda _b: _sync_shapes())
        _sync_shapes()

        ttl_tt = QLabel(tr('Auto-assign tier by callout type'))
        ttl_tt.setStyleSheet("font-weight:bold;")
        g.addWidget(ttl_tt, r, 0, 1, 2)
        r += 1
        c_typetier = QCheckBox(tr('Set each bubble tier from its callout type'))
        c_typetier.setChecked(bool(self.cfg.get("type_tier_auto")))
        c_typetier.setToolTip(tr("On: new bubbles take a tier from the table "
                                 "below (e.g. GD&T -> blue, threads -> green). "
                                 "Off: tier comes from the ribbon."))
        g.addWidget(c_typetier, r, 0, 1, 2)
        r += 1
        ttmap = dict(self.cfg.get("type_tier_map")
                     or CFG_DEFAULT["type_tier_map"])
        _tier_opts = [t for t in TIERS if t]
        tt_cbs = {}
        for tp in TYPES:
            lab = QLabel(tp)
            lab.setProperty("i18n_skip", True)
            g.addWidget(lab, r, 0)
            cb = QComboBox()
            cb.addItems(_tier_opts)
            cb.setProperty("i18n_skip", True)
            cur = ttmap.get(tp, "red")
            cb.setCurrentText(cur if cur in _tier_opts else "red")
            g.addWidget(cb, r, 1)
            tt_cbs[tp] = cb
            r += 1

        def _sync_typetier():
            for cb in tt_cbs.values():
                cb.setEnabled(c_typetier.isChecked())
        c_typetier.toggled.connect(lambda _b: _sync_typetier())
        _sync_typetier()

        g = _page("Vision")
        r = 0
        vttl = QLabel(tr('Vision assist (beta)'))
        vttl.setStyleSheet("font-weight:bold;")
        g.addWidget(vttl, r, 0, 1, 2)
        r += 1
        vavail = vision.available(self.cfg)
        c_vision = QCheckBox("Recover symbols/dims the PDF text layer misses / "
                             "Odzyskaj brakujące symbole")
        c_vision.setChecked(bool(self.cfg.get("vision_assist")))
        g.addWidget(c_vision, r, 0, 1, 2)
        r += 1
        c_vocr = QCheckBox("   • OCR scanned / no-text pages / Skanowane strony")
        c_vocr.setChecked(bool(self.cfg.get("vision_ocr", True)))
        g.addWidget(c_vocr, r, 0, 1, 2)
        r += 1
        c_vocr_all = QCheckBox("        OCR every page, not just sparse ones / "
                               "Każdą stronę")
        c_vocr_all.setChecked(bool(self.cfg.get("vision_ocr_always", False)))
        g.addWidget(c_vocr_all, r, 0, 1, 2)
        r += 1
        g.addWidget(QLabel(tr('OCR min confidence')), r, 0)
        e_vocrconf = QLineEdit("%g" % float(
            self.cfg.get("vision_ocr_conf", CFG_DEFAULT["vision_ocr_conf"])))
        g.addWidget(e_vocrconf, r, 1)
        r += 1
        c_vsym = QCheckBox(tr('• Detect GD&T symbols'))
        c_vsym.setChecked(bool(self.cfg.get("vision_symbols", True)))
        g.addWidget(c_vsym, r, 0, 1, 2)
        r += 1
        g.addWidget(QLabel("        Symbol min confidence / Min. pewność "
                           "symbolu"), r, 0)
        e_vsymconf = QLineEdit("%g" % float(
            self.cfg.get("vision_sym_conf", CFG_DEFAULT["vision_sym_conf"])))
        g.addWidget(e_vsymconf, r, 1)
        r += 1
        c_vregion = QCheckBox("   • Group callouts with the block detector / "
                              "Grupuj wg detektora bloków")
        c_vregion.setChecked(bool(self.cfg.get("vision_region", True)))
        g.addWidget(c_vregion, r, 0, 1, 2)
        r += 1
        g.addWidget(QLabel(tr('Block min confidence')),
                    r, 0)
        e_vrgnconf = QLineEdit("%g" % float(
            self.cfg.get("vision_region_conf", CFG_DEFAULT["vision_region_conf"])))
        g.addWidget(e_vrgnconf, r, 1)
        r += 1
        g.addWidget(QLabel(tr('GPU')), r, 0)
        cb_vep = QComboBox()
        cb_vep.addItems(["auto", "cpu", "directml", "cuda"])
        cb_vep.setCurrentText(str(self.cfg.get("vision_ep", "auto")).lower())
        g.addWidget(cb_vep, r, 1)
        r += 1
        g.addWidget(QLabel(tr('OCR engine')), r, 0)
        cb_voeng = QComboBox()
        cb_voeng.addItems(["rapidocr", "paddle"])
        cb_voeng.setCurrentText(
            str(self.cfg.get("vision_ocr_engine", "rapidocr")).lower())
        g.addWidget(cb_voeng, r, 1)
        r += 1
        c_vvlm = QCheckBox("   • Read callouts with the Florence-2 VLM "
                           "(slow; on add / scan) / Czytaj VLM-em")
        c_vvlm.setChecked(bool(self.cfg.get("vision_vlm", False)))
        g.addWidget(c_vvlm, r, 0, 1, 2)
        r += 1
        c_vvlm_all = QCheckBox("        even when a text layer exists / "
                               "nawet gdy jest tekst")
        c_vvlm_all.setChecked(bool(self.cfg.get("vision_vlm_always", False)))
        g.addWidget(c_vvlm_all, r, 0, 1, 2)
        r += 1
        g.addWidget(QLabel(tr('VLM engine')), r, 0)
        cb_vvlmeng = QComboBox()
        cb_vvlmeng.addItems(["florence", "paddleocr_vl"])
        cb_vvlmeng.setCurrentText(
            str(self.cfg.get("vision_vlm_engine", "florence")).lower())
        g.addWidget(cb_vvlmeng, r, 1)
        r += 1
        g.addWidget(QLabel(tr('VLM model')), r, 0)
        cb_vvlmmodel = QComboBox()
        cb_vvlmmodel.addItem(tr('(default)'), "")
        for _pk in florence.list_packs():
            cb_vvlmmodel.addItem(_pk, _pk)
        _cur_vlmm = str(self.cfg.get("vision_vlm_model", "") or "")
        _vlmm_idx = cb_vvlmmodel.findData(_cur_vlmm)
        if _vlmm_idx < 0:
            cb_vvlmmodel.addItem(_cur_vlmm, _cur_vlmm)
            _vlmm_idx = cb_vvlmmodel.count() - 1
        cb_vvlmmodel.setCurrentIndex(_vlmm_idx)
        g.addWidget(cb_vvlmmodel, r, 1)
        r += 1
        g.addWidget(QLabel(tr('Download VLM model')), r, 0)
        dlrow = QHBoxLayout()
        cb_dlpack = QComboBox()
        cb_dlpack.addItems(list(florence.HF_REPOS.keys()))
        b_dl = QPushButton(tr('Download'))
        b_dl.clicked.connect(
            lambda: self._download_vlm(cb_dlpack.currentText(), cb_vvlmmodel))
        dlrow.addWidget(cb_dlpack)
        dlrow.addWidget(b_dl)
        _dlw = QWidget()
        _dlw.setLayout(dlrow)
        g.addWidget(_dlw, r, 1)
        r += 1
        c_vsyminj = QCheckBox("        inject detected symbols into VLM reads / "
                              "wstrzykuj symbole do VLM")
        c_vsyminj.setChecked(bool(self.cfg.get("vision_sym_inject_vlm", True)))
        c_vsyminj.setToolTip(
            "On: splice GD&T glyphs the detector found into the VLM's text "
            "(fallback for glyphs the VLM misses). Off: pass only the category "
            "and let the VLM read the callout itself.")
        g.addWidget(c_vsyminj, r, 0, 1, 2)
        r += 1
        c_vsyminj_t = QCheckBox("        inject detected symbols into text-layer "
                                "reads / wstrzykuj symbole do tekstu")
        c_vsyminj_t.setChecked(bool(self.cfg.get("vision_sym_inject_text",
                                                 True)))
        c_vsyminj_t.setToolTip(
            "On: splice GD&T glyphs the detector found into blocks that already "
            "have a PDF text layer (a vector leader symbol is often missing "
            "from the text). Duplicates the text already shows are skipped.")
        g.addWidget(c_vsyminj_t, r, 0, 1, 2)
        r += 1
        if not (vavail["ocr"] and vavail["symbols"]):
            vhint = QLabel("   OCR / symbol passes need the vision build; "
                           "geometry pass works now.")
            vhint.setProperty("i18n_skip", True)
            vhint.setStyleSheet("color:#777; font-size:8pt;")
            g.addWidget(vhint, r, 0, 1, 2)
            r += 1
        if not vavail.get("region"):
            rhint = QLabel("   Block detector (gdt_regions.onnx) not installed; "
                           "callout grouping uses geometry.")
            rhint.setProperty("i18n_skip", True)
            rhint.setStyleSheet("color:#777; font-size:8pt;")
            g.addWidget(rhint, r, 0, 1, 2)
            r += 1
        if not vavail.get("vlm"):
            vlmhint = QLabel("   Florence-2 VLM pack not installed; use "
                             "'Download VLM model' above to fetch one.")
            vlmhint.setProperty("i18n_skip", True)
            vlmhint.setStyleSheet("color:#777; font-size:8pt;")
            g.addWidget(vlmhint, r, 0, 1, 2)
            r += 1
        provs = vavail.get("providers") or []
        prov_txt = ", ".join(p.replace("ExecutionProvider", "") for p in provs) \
            or "none"
        ephint = QLabel("   Execution provider available: %s   (%s)"
                        % ("GPU + CPU" if vavail.get("gpu") else "CPU only",
                           prov_txt))
        ephint.setProperty("i18n_skip", True)
        ephint.setStyleSheet("color:#777; font-size:8pt;")
        g.addWidget(ephint, r, 0, 1, 2)
        r += 1
        # why pass off/degraded
        for _rmsg in (vavail.get("reasons") or {}).values():
            rl = QLabel("   ! " + _rmsg)
            rl.setProperty("i18n_skip", True)
            rl.setWordWrap(True)
            rl.setStyleSheet("color:#b7791f; font-size:8pt;")
            g.addWidget(rl, r, 0, 1, 2)
            r += 1
        loghint = QLabel("   Diagnostics log: ~/.bubbler.log")
        loghint.setProperty("i18n_skip", True)
        loghint.setStyleSheet("color:#999; font-size:8pt;")
        g.addWidget(loghint, r, 0, 1, 2)
        r += 1

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
        ctl = QLabel(tr('Reader corrections'))
        ctl.setStyleSheet("font-weight:bold;")
        g.addWidget(ctl, r, 0, 1, 2)
        r += 1
        c_corr = QCheckBox(tr('Collect reader corrections (local, opt-in)'))
        c_corr.setChecked(bool(self.cfg.get("collect_corrections", False)))
        g.addWidget(c_corr, r, 0, 1, 2)
        r += 1
        g.addWidget(QLabel(tr('Corrections folder')), r, 0)
        e_corrdir = QLineEdit(str(self.cfg.get("corrections_dir", "") or ""))
        e_corrdir.setPlaceholderText("~/.bubbler/corrections")
        b_corrdir = QPushButton(tr('Browse...'))

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
        cdl.addWidget(e_corrdir, 1)
        cdl.addWidget(b_corrdir)
        g.addWidget(cdw, r, 1)
        r += 1
        g.addWidget(QLabel(tr('Custom model (.onnx)')), r, 0)
        e_vmodel = QLineEdit(str(self.cfg.get("vision_model", "") or ""))
        e_vmodel.setPlaceholderText(tr('(default)'))
        e_vmodel.setToolTip(tr('Point Bubbler at a locally-trained detector; '
                               'blank uses the bundled model.'))
        g.addWidget(e_vmodel, r, 1)
        r += 1
        corrhint = QLabel("   Off by default. Records (crop + fields, drawing "
                          "name never stored) stay local and are never sent "
                          "automatically. Export from the Data menu to share, "
                          "or train locally (see DEV.md).")
        corrhint.setProperty("i18n_skip", True)
        corrhint.setStyleSheet("color:#777; font-size:8pt;")
        corrhint.setWordWrap(True)
        g.addWidget(corrhint, r, 0, 1, 2)
        r += 1

        def _sync_corr():
            on = c_corr.isChecked()
            e_corrdir.setEnabled(on)
            b_corrdir.setEnabled(on)
        c_corr.toggled.connect(lambda _b: _sync_corr())
        _sync_corr()
        g = _page("Tolerances")
        r = 0
        c_dpon = QCheckBox("Tolerance by decimal places / wg miejsc "
                           "dziesiętnych:")
        c_dpon.setChecked(bool(self.cfg.get("dp_on")))
        g.addWidget(c_dpon, r, 0, 1, 2)
        r += 1
        dpw = QWidget()
        dpl = QHBoxLayout(dpw)
        dpv = {}
        dpt = dict((self.cfg.get("dp_tols") or CFG_DEFAULT["dp_tols"]))
        for k, lab in (("0", "X"), ("1", "X.X"), ("2", "X.XX"),
                       ("3", "X.XXX")):
            dpl.addWidget(QLabel(lab + " ±"))
            e = QLineEdit("%g" % float(dpt.get(k, CFG_DEFAULT["dp_tols"][k])))
            e.setMaximumWidth(60)
            dpl.addWidget(e)
            dpv[k] = e
        g.addWidget(dpw, r, 0, 1, 2)
        r += 1
        cvars = {}
        for label, key, vals in ((tr('Default type'), "default_type", TYPES),
                                 ("Default tier", "default_tier", TIERS)):
            g.addWidget(QLabel(label), r, 0)
            cb = QComboBox()
            cb.addItems(vals)
            cb.setCurrentText(self.cfg.get(key, CFG_DEFAULT[key]))
            g.addWidget(cb, r, 1)
            cvars[key] = cb
            r += 1

        def ok():
            try:
                self.cfg["ui_scale"] = float(
                    vars_["ui_scale"].text().replace(",", ".") or 0)
            except ValueError:
                QMessageBox.critical(dlg, tr('Error'),
                                     "UI scale must be a number")
                return
            for key, e in tvars.items():
                try:
                    val = float(e.text().replace(",", "."))
                    if val <= 0:
                        raise ValueError
                except ValueError:
                    QMessageBox.critical(
                        dlg, tr('Error'),
                        "Gage tolerance thresholds must be positive "
                        "numbers / Progi muszą być dodatnie")
                    return
                self.cfg[key] = val
            self.cfg["icon_color"] = vars_["icon_color"].text()
            self.cfg["company"] = vars_["company"].text()
            self.cfg["hole_pin_auto"] = bool(c_pinauto.isChecked())
            self.cfg["snap_geom"] = bool(c_snap.isChecked())
            self.cfg["tier_shapes"] = bool(c_shapes.isChecked())
            self.cfg["tier_shape_map"] = {t: cb.currentText()
                                          for t, cb in shape_cbs.items()}
            self.cfg["type_tier_auto"] = bool(c_typetier.isChecked())
            self.cfg["type_tier_map"] = {tp: cb.currentText()
                                         for tp, cb in tt_cbs.items()}
            try:
                obsw = float(e_obsw.text().replace(",", "."))
                if obsw < 0:
                    raise ValueError
            except ValueError:
                QMessageBox.critical(
                    dlg, tr('Error'),
                    "Line width threshold must be a number >= 0 / "
                    "Próg grubości musi być liczbą >= 0")
                return
            if obsw != float(self.cfg.get("obstacle_min_w", 0.5)):
                self._geom_cache = {}
                if hasattr(self, "_obs_cache"):
                    self._obs_cache = {}
            self.cfg["obstacle_min_w"] = obsw
            try:
                caprad = float(e_caprad.text().replace(",", "."))
                if caprad <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.critical(
                    dlg, tr('Error'),
                    "Capture radius must be a number > 0 / "
                    "Promień musi być liczbą > 0")
                return
            self.cfg["capture_radius"] = caprad
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
                    "Vision confidences must be between 0 and 1 / "
                    "Pewność musi być w zakresie 0-1")
                return
            _vkeys = ("vision_assist", "vision_ocr", "vision_ocr_always",
                      "vision_ocr_conf", "vision_symbols", "vision_sym_conf",
                      "vision_region", "vision_region_conf", "vision_ep",
                      "vision_ocr_engine", "vision_vlm", "vision_vlm_always",
                      "vision_vlm_engine", "vision_vlm_model",
                      "vision_sym_inject_vlm", "vision_sym_inject_text")
            _vnew = (bool(c_vision.isChecked()), bool(c_vocr.isChecked()),
                     bool(c_vocr_all.isChecked()), vocrc,
                     bool(c_vsym.isChecked()), vsymc,
                     bool(c_vregion.isChecked()), vrgnc,
                     cb_vep.currentText(), cb_voeng.currentText(),
                     bool(c_vvlm.isChecked()), bool(c_vvlm_all.isChecked()),
                     cb_vvlmeng.currentText(), cb_vvlmmodel.currentData(),
                     bool(c_vsyminj.isChecked()),
                     bool(c_vsyminj_t.isChecked()))
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
            self.cfg["collect_corrections"] = bool(c_corr.isChecked())
            self.cfg["corrections_dir"] = e_corrdir.text().strip()
            _newmodel = e_vmodel.text().strip()
            if _newmodel != (self.cfg.get("vision_model") or ""):
                self.__dict__.pop("_vword_cache", None)
                vision.reset_sessions()
            self.cfg["vision_model"] = _newmodel
            self.cfg["dp_on"] = bool(c_dpon.isChecked())
            dpt2 = {}
            for k, e in dpv.items():
                try:
                    dpt2[k] = float(e.text().replace(",", "."))
                except ValueError:
                    QMessageBox.critical(
                        dlg, tr('Error'),
                        "Decimal-place tolerances must be numbers / "
                        "muszą być liczbami")
                    return
            self.cfg["dp_tols"] = dpt2
            self.cfg["gages"] = {k: bool(c.isChecked())
                                 for k, c in gvars.items()}
            for key, cb in cvars.items():
                self.cfg[key] = cb.currentText()
            new_lang = cb_lang.currentData()
            self.cfg["language"] = new_lang
            set_lang(new_lang)
            self.cfg["mode"] = cb_mode.currentData()
            self.cfg["units"] = cb_units.currentData()
            self.cfg["sheet_lang"] = cb_sheet.currentData()
            self.writer.sheet_lang = self.cfg["sheet_lang"]
            save_cfg(self.cfg)
            try:
                from . import vision
                vision.clear_cache()
            except Exception:
                pass
            self._apply_ui_scale(rebuild=True)
            self._apply_mode()
            retranslate(self)
            dlg.accept()
            self.render()
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
        dlg.setMinimumWidth(min(600, cap_w))
        dlg.resize(min(640, cap_w), min(820, cap_h))
        dlg.exec()

    def _download_vlm(self, pack, model_combo):
        """Fetch a Florence-2 pack into ~/.bubbler/models with a progress bar."""
        if getattr(self, "_vlm_dl_task", None) is not None:
            return                               # one download at a time
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
