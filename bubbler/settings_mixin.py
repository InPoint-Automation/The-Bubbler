# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Keybind help, header editor, Settings dialog. Mixed into MainWindow.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QLabel, QLineEdit, QComboBox,
                               QCheckBox, QPushButton, QMessageBox)

from .common import TYPES, TIERS
from .config import save_cfg, CFG_DEFAULT
from .sheet import HEADER_FIELDS
from .scanlib import GAGES
from .i18n import tr, set_lang, retranslate
from .keyhelp import _keybinds_html
from . import vision, florence


class SettingsMixin:
    def show_keys(self):
        from PySide6.QtWidgets import QTextBrowser
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Keybinds / Skróty"))
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

    def header_editor(self):
        if self._hdr_win is not None:
            try:
                self._hdr_win.raise_()
                self._hdr_win.activateWindow()
                return
            except RuntimeError:
                self._hdr_win = None
        win = QDialog(self)
        win.setWindowTitle(tr("Header / Nagłówek"))
        self._hdr_win = win
        g = QGridLayout(win)
        current = self.writer.get_header()
        entries = {}
        for i, (cell, label) in enumerate(HEADER_FIELDS):
            hlab = QLabel(label)
            hlab.setProperty("i18n_skip", True)  # bilingual sheet
            g.addWidget(hlab, i, 0)
            e = QLineEdit(str(current.get(cell, "")))
            # drag-fill target
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
                QMessageBox.critical(win, "Sheet error / Błąd", str(ex))
                return
            self.set_status("header saved / nagłówek zapisany")

        nrow = len(HEADER_FIELDS)
        bw = QWidget()
        bl = QHBoxLayout(bw)
        b_apply = QPushButton("Apply / Zastosuj")
        b_apply.clicked.connect(apply)
        b_close = QPushButton("Close / Zamknij")
        b_close.clicked.connect(win.close)
        bl.addWidget(b_apply)
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
        dlg.setWindowTitle("Settings / Ustawienia")
        g = QGridLayout(dlg)
        vars_ = {}
        r = 0
        g.addWidget(QLabel("Language / Język"), r, 0)
        cb_lang = QComboBox()
        cb_lang.addItem("English", "en")
        cb_lang.addItem("Polski", "pl")
        cb_lang.setCurrentIndex(
            1 if self.cfg.get("language", "en") == "pl" else 0)
        g.addWidget(cb_lang, r, 1)
        r += 1
        for label, key in (("Company / Firma", "company"),
                           ("Accent color / Kolor", "icon_color"),
                           ("UI scale (0=auto)", "ui_scale")):
            g.addWidget(QLabel(label), r, 0)
            e = QLineEdit(str(self.cfg.get(key, CFG_DEFAULT[key])))
            g.addWidget(e, r, 1)
            vars_[key] = e
            r += 1
        ttl = QLabel("Available gages / Dostępne przyrządy:")
        ttl.setStyleSheet("font-weight:bold;")
        g.addWidget(ttl, r, 0, 1, 2)
        r += 1
        tvars = {}
        for label, key in (("CMM if tol ≤ / CMM gdy tol ≤", "cmm_tol"),
                           ("Micrometer if tol ≤ / Mikrometr gdy ≤",
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
            c.setProperty("i18n_skip", True)   # data, not label
            c.setChecked(bool(gcfg.get(gname, True)))
            g.addWidget(c, r, 0, 1, 2)
            gvars[gname] = c
            r += 1
        c_pinauto = QCheckBox("Hole pin Ø = nominal / Pin = nominał")
        c_pinauto.setChecked(bool(self.cfg.get("hole_pin_auto", True)))
        g.addWidget(c_pinauto, r, 0, 1, 2)
        r += 1
        c_snap = QCheckBox("Snap to drawing geometry / Przyciągaj")
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
        # Vision assist
        vttl = QLabel("Vision assist (beta) / Wspomaganie wizyjne:")
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
        g.addWidget(QLabel("        OCR min confidence / Min. pewność OCR"), r, 0)
        e_vocrconf = QLineEdit("%g" % float(
            self.cfg.get("vision_ocr_conf", CFG_DEFAULT["vision_ocr_conf"])))
        g.addWidget(e_vocrconf, r, 1)
        r += 1
        c_vsym = QCheckBox("   • Detect GD&T symbols / Wykryj symbole GD&T")
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
        g.addWidget(QLabel("        Block min confidence / Min. pewność bloku"),
                    r, 0)
        e_vrgnconf = QLineEdit("%g" % float(
            self.cfg.get("vision_region_conf", CFG_DEFAULT["vision_region_conf"])))
        g.addWidget(e_vrgnconf, r, 1)
        r += 1
        g.addWidget(QLabel("   GPU / Execution provider"), r, 0)
        cb_vep = QComboBox()
        cb_vep.addItems(["auto", "cpu", "directml", "cuda"])
        cb_vep.setCurrentText(str(self.cfg.get("vision_ep", "auto")).lower())
        g.addWidget(cb_vep, r, 1)
        r += 1
        g.addWidget(QLabel("   OCR engine / Silnik OCR"), r, 0)
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
        g.addWidget(QLabel("        VLM engine / Silnik VLM"), r, 0)
        cb_vvlmeng = QComboBox()
        cb_vvlmeng.addItems(["florence", "paddleocr_vl"])
        cb_vvlmeng.setCurrentText(
            str(self.cfg.get("vision_vlm_engine", "florence")).lower())
        g.addWidget(cb_vvlmeng, r, 1)
        r += 1
        g.addWidget(QLabel("        VLM model / Model VLM"), r, 0)
        cb_vvlmmodel = QComboBox()
        cb_vvlmmodel.addItem("(default) / (domyślny)", "")
        for _pk in florence.list_packs():
            cb_vvlmmodel.addItem(_pk, _pk)
        _cur_vlmm = str(self.cfg.get("vision_vlm_model", "") or "")
        _vlmm_idx = cb_vvlmmodel.findData(_cur_vlmm)
        if _vlmm_idx < 0:                       # manual path
            cb_vvlmmodel.addItem(_cur_vlmm, _cur_vlmm)
            _vlmm_idx = cb_vvlmmodel.count() - 1
        cb_vvlmmodel.setCurrentIndex(_vlmm_idx)
        g.addWidget(cb_vvlmmodel, r, 1)
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
            vlmhint = QLabel("   Florence-2 VLM pack not installed; the VLM "
                             "reader is unavailable.")
            vlmhint.setProperty("i18n_skip", True)
            vlmhint.setStyleSheet("color:#777; font-size:8pt;")
            g.addWidget(vlmhint, r, 0, 1, 2)
            r += 1
        ephint = QLabel("   Execution provider available: %s"
                        % ("GPU + CPU" if vavail.get("gpu") else "CPU only"))
        ephint.setProperty("i18n_skip", True)
        ephint.setStyleSheet("color:#777; font-size:8pt;")
        g.addWidget(ephint, r, 0, 1, 2)
        r += 1

        def _sync_vision():
            # gate on checkboxes, not backends
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
        for label, key, vals in (("Default type / Typ", "default_type", TYPES),
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
                QMessageBox.critical(dlg, "Error / Błąd",
                                     "UI scale must be a number")
                return
            for key, e in tvars.items():
                try:
                    val = float(e.text().replace(",", "."))
                    if val <= 0:
                        raise ValueError
                except ValueError:
                    QMessageBox.critical(
                        dlg, "Error / Błąd",
                        "Gage tolerance thresholds must be positive "
                        "numbers / Progi muszą być dodatnie")
                    return
                self.cfg[key] = val
            self.cfg["icon_color"] = vars_["icon_color"].text()
            self.cfg["company"] = vars_["company"].text()
            self.cfg["hole_pin_auto"] = bool(c_pinauto.isChecked())
            self.cfg["snap_geom"] = bool(c_snap.isChecked())
            try:
                obsw = float(e_obsw.text().replace(",", "."))
                if obsw < 0:
                    raise ValueError
            except ValueError:
                QMessageBox.critical(
                    dlg, "Error / Błąd",
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
                    dlg, "Error / Błąd",
                    "Capture radius must be a number > 0 / "
                    "Promień musi być liczbą > 0")
                return
            self.cfg["capture_radius"] = caprad
            # confidences 0..1
            try:
                vocrc = float(e_vocrconf.text().replace(",", "."))
                vsymc = float(e_vsymconf.text().replace(",", "."))
                vrgnc = float(e_vrgnconf.text().replace(",", "."))
                if not (0.0 <= vocrc <= 1.0 and 0.0 <= vsymc <= 1.0
                        and 0.0 <= vrgnc <= 1.0):
                    raise ValueError
            except ValueError:
                QMessageBox.critical(
                    dlg, "Error / Błąd",
                    "Vision confidences must be between 0 and 1 / "
                    "Pewność musi być w zakresie 0-1")
                return
            # vision change invalidates caches + sessions
            _vkeys = ("vision_assist", "vision_ocr", "vision_ocr_always",
                      "vision_ocr_conf", "vision_symbols", "vision_sym_conf",
                      "vision_region", "vision_region_conf", "vision_ep",
                      "vision_ocr_engine", "vision_vlm", "vision_vlm_always",
                      "vision_vlm_engine", "vision_vlm_model",
                      "vision_sym_inject_vlm")
            _vnew = (bool(c_vision.isChecked()), bool(c_vocr.isChecked()),
                     bool(c_vocr_all.isChecked()), vocrc,
                     bool(c_vsym.isChecked()), vsymc,
                     bool(c_vregion.isChecked()), vrgnc,
                     cb_vep.currentText(), cb_voeng.currentText(),
                     bool(c_vvlm.isChecked()), bool(c_vvlm_all.isChecked()),
                     cb_vvlmeng.currentText(), cb_vvlmmodel.currentData(),
                     bool(c_vsyminj.isChecked()))
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
            self.cfg["dp_on"] = bool(c_dpon.isChecked())
            dpt2 = {}
            for k, e in dpv.items():
                try:
                    dpt2[k] = float(e.text().replace(",", "."))
                except ValueError:
                    QMessageBox.critical(
                        dlg, "Error / Błąd",
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
            save_cfg(self.cfg)
            self._apply_ui_scale(rebuild=True)
            retranslate(self)   # ribbon skips measure bar + panel
            dlg.accept()
            self.render()
            self.set_status("settings saved / ustawienia zapisane")

        bw = QWidget()
        bl = QHBoxLayout(bw)
        b_ok = QPushButton("OK")
        b_ok.setDefault(True)
        b_ok.clicked.connect(ok)
        b_cancel = QPushButton("Cancel / Anuluj")
        b_cancel.clicked.connect(dlg.reject)
        bl.addWidget(b_ok)
        bl.addWidget(b_cancel)
        g.addWidget(bw, r, 0, 1, 2)
        dlg.setWindowTitle(tr("Settings / Ustawienia"))
        retranslate(dlg)
        dlg.exec()

    # Scan review
