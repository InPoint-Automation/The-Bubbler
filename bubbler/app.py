# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Main window: canvas, balloons, panel, scan, export.

import os
import sys
import time

import fitz
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QEvent
from PySide6.QtGui import (QImage, QPixmap, QPainter, QPen, QBrush, QColor,
                           QFont, QKeySequence, QShortcut, QPolygonF)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QGraphicsScene, QLabel, QComboBox, QLineEdit,
                               QDoubleSpinBox, QHBoxLayout, QDockWidget, QMenu,
                               QMessageBox, QInputDialog, QPushButton,
                               QCheckBox)

from .common import (APP_NAME, RADIUS, FONTSZ, RED, LEADER_EXITS,
                     TYPES, TIERS,
                     base_of, qc_path,
                     tier_rgb, tier_shape, bubble_shape_points, tier_for_type,
                     fit_fontsz, point_in_bubble, shape_extent, shape_radius,
                     shape_support, widest_extent,
                     measure_state, METHODS)
from .units_mixin import UnitsMixin
from .config import (CFG_DEFAULT, load_cfg, save_cfg, ops_seq)
from .scanlib import (expand_hole_row, suggest_gage, GAGES,
                      general_tol, gentol_callout, scan_presets)
from .sheet import SheetWriter
from .icons import make_pixmap, set_ui_scale, set_accent
from .dialogs import BubbleDialog
from .hotbar_mixin import HotbarMixin
from .i18n import tr, set_lang, retranslate
from .measure_mixin import MeasureMixin
from .geometry_mixin import GeometryMixin
from .history_mixin import HistoryMixin
from .panel_mixin import PanelMixin
from .widgets import PdfView, MeasureEdit, set_combo_key
from .settings_mixin import SettingsMixin
from .ribbon_mixin import RibbonMixin
from .report_mixin import ReportMixin
from .import_mixin import ImportMixin
from .export_mixin import ExportMixin
from .scan_mixin import ScanMixin
from .capture_mixin import CaptureMixin
from .input_mixin import InputMixin
from .bubble_mixin import BubbleMixin
from .titleblock_mixin import TitleblockMixin
from .nav_mixin import NavMixin
from .corrections_mixin import CorrectionsMixin
from .calc_mixin import CalcMixin
from .runs_mixin import RunsMixin
from .store import BubbleStore, SessionReadOnly, session_lock_text
from .viewport import Viewport
from .tools import make_tools


class MainWindow(MeasureMixin, GeometryMixin, HistoryMixin, PanelMixin,
                 SettingsMixin, RibbonMixin, ReportMixin, ImportMixin,
                 ExportMixin, ScanMixin, CaptureMixin, InputMixin,
                 BubbleMixin, TitleblockMixin, NavMixin, CorrectionsMixin,
                 CalcMixin, RunsMixin, HotbarMixin, UnitsMixin,
                 QMainWindow):
    UNDO_DEPTH = 50
    _DIRS = (("n", 0, -1), ("e", 1, 0), ("s", 0, 1), ("w", -1, 0))
    _OFF_LABEL = {"auto": "auto", "n": "↑ N", "e": "→ E",
                  "s": "↓ S", "w": "← W"}

    @property
    def ledger(self):
        return self.store.ledger

    @ledger.setter
    def ledger(self, v):
        self.store.ledger = v

    @property
    def uid_seq(self):
        return self.store.uid_seq

    @uid_seq.setter
    def uid_seq(self, v):
        self.store.uid_seq = v

    @property
    def page_i(self):
        return self.viewport.page_i

    @page_i.setter
    def page_i(self, v):
        self.viewport.page_i = v

    @property
    def zoom(self):
        return self.viewport.zoom

    @zoom.setter
    def zoom(self, v):
        self.viewport.zoom = v

    @property
    def rotation(self):
        return self.viewport.rotation

    @rotation.setter
    def rotation(self, v):
        self.viewport.rotation = v

    @property
    def _active_tool(self):
        return self._tools[self.tool]

    @property
    def drawing(self):
        """Per-drawing settings in session."""
        return self.store.drawing

    def __init__(self, pdf_path, xlsx_path, cfg=None):
        super().__init__()
        self.cfg = cfg or load_cfg()
        set_lang(self.cfg.get("language", "en"))
        self.pdf_path = pdf_path
        self.writer = SheetWriter(
            xlsx_path,
            sheet_lang=self.cfg.get("sheet_lang", "both"),
            tier_designator=self.cfg.get("sheet_tier_designator", False),
            tier_column=self.cfg.get("sheet_tier_column", False),
            refzone_column=self.cfg.get("sheet_refzone_column", False),
            ncr_column=self.cfg.get("sheet_ncr_column", False),
            gage_column=self.cfg.get("sheet_gage_column", False),
            method_column=self.cfg.get("sheet_method_column", False),
            type_column=self.cfg.get("sheet_type_column", False),
            # match FAI requirement string
            units=self.cfg.get("units", "iso_mm"), cfg=self.cfg,
            inspections=sorted(scan_presets(self.cfg)))
        self.doc = fitz.open(pdf_path)
        # H4 monotonic open time
        self._opened_monotonic = time.monotonic()
        self.viewport = Viewport()
        self.store = BubbleStore()
        self.measure_mode = False
        self.tool = "add"
        self._tools = make_tools(self)
        self.sel = set()
        self._qbar = None
        self._undo = []
        self._redo = []
        self.session_path = qc_path(pdf_path, "_bubbles.json",
                                    subdir=self.cfg.get("qc_subdir", "qc"))
        self._load_session()
        self._ingest_sheet_edits()
        self._ingest_header()
        self._stamp_run_identity()        # run inherits title block
        self.store.migrate_uids()
        self.store.renumber()
        self.dlg_pos = self.cfg.get("dlg_pos") or None
        self._hdr_focus = None
        self._hdr_win = None
        self._capturing = False
        self._capture_start = None
        self._capture_cur = None
        self._scan_task = None
        self._cap_loop = None
        self._swallow = False
        self._drag = None
        self._dragged = False
        self._press = None
        self._press_scene = None
        self._marquee = None
        self._scanhl = None
        self._flash_ring = None
        self._scan_region_mode = None
        self._scan_inc = None
        self._scan_exc = None
        self._scan_drag = None
        self._correct_mode = None
        self._corr_seq = 0
        self.panel_visible = False
        self._run_stale_asked = False

        self._title_base = "%s - %s" % (
            APP_NAME, os.path.basename(pdf_path))
        self.setWindowTitle(self._title_base)

        self.scene = QGraphicsScene(self)
        self._pixitem = self.scene.addPixmap(QPixmap())
        self._pixitem.setZValue(-100)
        self.view = PdfView(self.scene, self)
        self.setCentralWidget(self.view)

        self.last = {
            "type": self.cfg.get("default_type", TYPES[0]),
            "tier": self.cfg.get("default_tier", ""),
            "iso_on": bool(self.cfg.get("rib_iso_on")),
            "tsym": "", "tmax": "", "tmin": "",
            "icls": str(self.cfg.get("default_iso_class", "m")),
        }

        self._base_font = QFont(QApplication.instance().font())
        self._apply_ui_scale()

        self._build_ribbon()
        self._build_panel()
        self._build_nav()
        self.store.subscribe(self.refresh_panel)
        self._build_measure_bar()
        self._build_calc()
        self.statusBar()
        self._status_state = QLabel("")
        self.statusBar().addPermanentWidget(self._status_state, 1)
        self._busy_lbl = QLabel("")
        self._busy_lbl.setVisible(False)
        self.statusBar().addPermanentWidget(self._busy_lbl)
        self._busy_msg = ""
        self._busy_i = 0
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(120)
        self._busy_timer.timeout.connect(self._busy_tick)
        self._toast_icon = QLabel("")
        self._toast_icon.setVisible(False)
        self.statusBar().addPermanentWidget(self._toast_icon)
        self.statusBar().messageChanged.connect(self._on_toast_changed)
        self._walk = []
        self._walk_idx = 0
        self._install_shortcuts()
        QApplication.instance().installEventFilter(self)
        retranslate(self)
        self._prewarm_vision()

        self.resize(1500, 950)
        if not self._restore_window():
            self.showMaximized()
        self.render()
        self.refresh_panel()
        QTimer.singleShot(150, self.fit)
        if self.cfg.get("hotbar_on", True):
            QTimer.singleShot(350, lambda: self._qbar_show(persist=False))
        QTimer.singleShot(400, self._units_autodetect)
        QTimer.singleShot(500, self._titleblock_autofill)
        QTimer.singleShot(600, self._run_stale_check)
        self._apply_lock_chrome()
        if getattr(self, "_session_lock_pending", False):
            QTimer.singleShot(0, self._show_session_lock)

    def _restore_window(self):
        """Restore saved window geometry."""
        try:
            from PySide6.QtCore import QByteArray
            g = self.cfg.get("win_geometry")
            if g:
                self.restoreGeometry(QByteArray.fromHex(
                    g.encode("ascii")))
                return True
        except Exception:
            pass
        return False

    def closeEvent(self, e):
        try:
            before = (self.cfg.get("win_geometry"), self.cfg.get("panel_w"),
                      dict(self.cfg.get("panel_col_w") or {}),
                      self.cfg.get("calc_history"))
            g = bytes(self.saveGeometry().toHex()).decode("ascii")
            self.cfg["win_geometry"] = g
            self._save_panel_width()
            self._calc_save_history()
            if before != (g, self.cfg.get("panel_w"),
                          dict(self.cfg.get("panel_col_w") or {}),
                          self.cfg.get("calc_history")):
                save_cfg(self.cfg)
        except Exception:
            pass
        super().closeEvent(e)

    def _install_shortcuts(self):
        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(fn)
            return s
        sc("Ctrl+Z", self.undo)
        sc("Ctrl+Y", self.redo)
        sc("Ctrl+Shift+Z", self.redo)
        sc("Ctrl+S", self.save)
        sc("F1", self.show_keys)
        sc("Ctrl+=", lambda: self.rezoom(1.25))
        sc("Ctrl++", lambda: self.rezoom(1.25))
        sc("Ctrl+-", lambda: self.rezoom(0.8))
        sc("Ctrl+0", self.fit)
        sc("PageUp", lambda: self.flip(-1))
        sc("PageDown", lambda: self.flip(1))

    def on_key(self, e):
        """View-level keys when canvas has focus."""
        k = e.key()
        txt = e.text()
        if self._correct_mode:
            if k == Qt.Key_Escape:
                self._correct_mode = None
                self._scan_drag = None
                self.redraw_overlay()
                self.set_status(tr('correction cancelled'))
            return True
        if self._scan_region_mode:
            if k == Qt.Key_Escape:
                self._cancel_scan_region()
            elif k in (Qt.Key_Return, Qt.Key_Enter):
                if self._scan_region_mode == "include":
                    self._scan_region_mode = "exclude"
                    self.set_status(tr(
                        'Scan: drag a RED box to ignore, or Enter to skip'))
                    self.redraw_overlay()
                else:
                    self._run_scan_regions()
            return True
        if self._qbar is not None and txt and not self.measure_mode:
            ch = txt
            if k == Qt.Key_Delete:
                ch = "DEL"
            if self._qbar.press(ch):
                self.set_status()
                return True
        if k == Qt.Key_Escape:
            self._esc()
            return True
        if k == Qt.Key_Home:
            self.fit(); return True
        if k == Qt.Key_PageUp:
            self.flip(-1); return True
        if k == Qt.Key_PageDown:
            self.flip(1); return True
        if txt in ("+", "="):
            self.rezoom(1.25); return True
        if txt == "-":
            self.rezoom(0.8); return True
        if k == Qt.Key_Up:
            return self._kbd_arrow("n")
        if k == Qt.Key_Right:
            return self._kbd_arrow("e")
        if k == Qt.Key_Down:
            return self._kbd_arrow("s")
        if k == Qt.Key_Left:
            return self._kbd_arrow("w")
        if k == Qt.Key_Delete:
            self._kbd_delete()
            return True
        if txt == "m":
            self._kbd_toggle("m"); return True
        if txt == "b":
            self._kbd_toggle("b"); return True
        if txt == "v":
            self._kbd_tool("select"); return True
        if txt == "a":
            self._kbd_tool("add"); return True
        if txt == "q":
            self._kbd_qbar(); return True
        return False

    def _esc(self):
        if self.measure_mode:
            self._set_measure(False)
        elif self.sel:
            self.sel.clear()
            self.redraw_overlay()
            self._qbar_refresh()
        elif self._qbar is not None:
            self._qbar_hide()

    def _effective_scale(self):
        """0/auto derives from screen DPI."""
        try:
            s = float(self.cfg.get("ui_scale") or 0)
        except (TypeError, ValueError):
            s = 0.0
        if s and s > 0:
            return s
        try:
            scr = QApplication.primaryScreen()
            return max(1.0, scr.logicalDotsPerInch() / 96.0)
        except Exception:
            return 1.0

    def _apply_ui_scale(self, rebuild=False):
        scale = self._effective_scale()
        set_ui_scale(scale)
        set_accent(self.cfg.get("icon_color"))
        app = QApplication.instance()
        base_pt = self._base_font.pointSizeF()
        if base_pt <= 0:
            base_pt = 9.0
        f = QFont(self._base_font)
        f.setPointSizeF(base_pt * scale)
        app.setFont(f)
        if rebuild:
            self._rebuild_ribbon()
            if self._qbar is not None:
                self._qbar_refresh()

    def _rebuild_ribbon(self):
        old = getattr(self, "_ribbon_tb", None)
        if old is not None:
            self.removeToolBar(old)
            old.deleteLater()
        self._build_ribbon()
        self._apply_lock_chrome()
        self.btn_tool_add.setChecked(self.tool == "add")
        self.btn_tool_sel.setChecked(self.tool == "select")
        self.btn_panel.setChecked(self.panel_visible)
        self.btn_measure.setChecked(self.measure_mode)
        self.btn_calc.setChecked(self._calc_dock.isVisible())

    def _style_set(self, key, val):
        lo, hi = (3, 40) if key == "radius" else (4, 30)
        self.cfg[key] = max(lo, min(hi, float(val)))
        if key == "radius":
            self.__dict__.pop("_leadtrim_cache", None)   # trim depends on r
        save_cfg(self.cfg)
        self.render()

    def _iso_changed(self, on):
        # arms drawing ladder
        on = bool(on)
        self.cfg["dp_on"] = on
        self.last["iso_on"] = on
        self.cfg["rib_iso_on"] = on
        save_cfg(self.cfg)
        self._sync_gentol()
        self._qbar_refresh()

    def _icls_changed(self, _i=None):
        self.last["icls"] = self.cb_icls.currentText()
        self.cfg["default_iso_class"] = self.last["icls"]
        save_cfg(self.cfg)

    def _lead_changed(self, on):
        self.cfg["leaders"] = bool(on)
        save_cfg(self.cfg)
        self._qbar_refresh()

    def _autobub_changed(self, on):
        self.cfg["click_auto_bubble"] = bool(on)
        save_cfg(self.cfg)

    def _report_input_error(self, where):
        """Surface an exception Qt would swallow from a mouse-handler slot."""
        import traceback
        tb = traceback.format_exc()
        print("bubbler: input handler failed in %s\n%s" % (where, tb),
              file=sys.stderr)
        try:
            self.set_status(tr('Click failed: %s')
                            % tb.strip().splitlines()[-1])
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, tr('Bubbler'),
                                tr('Something went wrong handling that '
                                   'click:\n\n%s') % tb)
        except Exception:
            pass

    def use_leaders(self):
        try:
            return bool(self.chk_lead.isChecked())
        except Exception:
            return bool(self.cfg.get("leaders"))

    def suggest(self, d):
        return suggest_gage(d, self.cfg, self.drawing)

    def _rib_set(self, key, val):
        self.last[key] = val
        if key in ("type", "tier"):
            self.cfg["default_%s" % key] = val
            save_cfg(self.cfg)

    def _rib_sync(self):
        set_combo_key(self.cb_type, self.last.get("type", TYPES[0]))
        self.e_tsym.setText(self.last.get("tsym", ""))
        self.e_tmax.setText(self.last.get("tmax", ""))
        self.e_tmin.setText(self.last.get("tmin", ""))
        self.cb_icls.setCurrentText(self.last.get("icls", "m"))
        set_combo_key(self.cb_tier, self.last.get("tier", ""))

    # sticky next-bubble keys
    _RIB_STICKY = (("type", "default_type"), ("tier", "default_tier"),
                   ("icls", "default_iso_class"))

    def reset_ribbon(self):
        """Reset next-bubble stickies to shipped defaults."""
        for lkey, ckey in self._RIB_STICKY:
            self.cfg[ckey] = CFG_DEFAULT[ckey]
            self.last[lkey] = CFG_DEFAULT[ckey]
        self.cfg["rib_iso_on"] = CFG_DEFAULT["rib_iso_on"]
        self.cfg["dp_on"] = CFG_DEFAULT["dp_on"]
        self.last["iso_on"] = bool(CFG_DEFAULT["rib_iso_on"])
        self.last.update({"tsym": "", "tmax": "", "tmin": ""})
        save_cfg(self.cfg)
        chk = getattr(self, "chk_iso", None)
        if chk is not None:
            chk.blockSignals(True)
            chk.setChecked(self.last["iso_on"])
            chk.blockSignals(False)
        self._rib_sync()
        self._sync_units_controls()
        self._qbar_refresh()
        self.set_status(tr('next-bubble options reset'))

    def _cell_edit(self, idx, colname):
        if self._edit_blocked():
            return
        d = self.ledger[idx]
        cur = "" if d.get(colname) in (None, "") else str(d[colname])
        if colname == "tier":
            labels = [tr('auto')] + [tr(t) for t in TIERS[1:]]
            val, ok = QInputDialog.getItem(self, "tier", "tier", labels,
                                           max(0, TIERS.index(cur)
                                               if cur in TIERS else 0), False)
            if ok:
                val = TIERS[labels.index(val)] if val in labels else ""
        elif colname == "gage":
            curidx = GAGES.index(cur) if cur in GAGES else 0
            val, ok = QInputDialog.getItem(self, "gage", "gage", GAGES,
                                           curidx, True)
        else:
            val, ok = QInputDialog.getText(self, colname, colname,
                                           text=cur)
        if not ok:
            return
        val = val.strip()
        if val == cur:
            return
        self.snapshot()
        d[colname] = val if val != "" else None
        self._save_session()
        self.refresh_panel()
        self._panel_highlight(idx, scroll=False)
        self.set_status("edited #%s %s" % (d.get("bubble", "?"), colname))

    def edit_ledger_row(self, idx):
        if self._edit_blocked():
            return
        d = self.ledger[idx]
        at = tuple(self.dlg_pos) if self.dlg_pos else None
        had_leader = d.get("leader",
                           (d.get("bx", d["x"]), d.get("by", d["y"]))
                           != (d["x"], d["y"]))
        dlg = BubbleDialog(self, d["bubble"], last=None, at=at,
                           cfg=self.cfg, edit_row=d,
                           session=self.drawing, gtols=self.gtols_now(),
                           leader_default=had_leader)
        dlg.exec()
        if dlg.last_geo:
            self.dlg_pos = dlg.last_geo
            self.cfg["dlg_pos"] = list(self.dlg_pos)
            save_cfg(self.cfg)
        if not dlg.result_rows:
            return
        self.snapshot()
        new = dlg.result_rows[0]
        keep = {k: d.get(k) for k in ("bubble", "uid", "page", "x", "y",
                                      "sheet_row", "measured", "ops", "bx",
                                      "by", "lexit") if k in d}
        d.clear()
        d.update(new)
        d.update(keep)
        lead = bool(new.get("leader", had_leader))
        for r2 in self.ledger:
            if r2.get("uid") == d["uid"]:
                r2["leader"] = lead
        if lead and not had_leader and \
                (d.get("bx", d["x"]), d.get("by", d["y"])) == \
                (d["x"], d["y"]):
            nbx, nby = self.auto_offset(d["x"], d["y"],
                                        page_i=d.get("page"),
                                        tier=d.get("tier"))
            self._set_uid_pos(d["uid"], bx=nbx, by=nby)
        elif not lead:
            self._set_uid_pos(d["uid"], bx=d["x"], by=d["y"])
        want = getattr(dlg, "new_number", None)
        if want is not None and want != base_of(d["bubble"]):
            self.store.set_number(d["uid"], want)
        else:
            self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()

    _SPINNER = "|/-\\"

    def _busy_tick(self):
        self._busy_i = (self._busy_i + 1) % len(self._SPINNER)
        self._busy_lbl.setText("%s %s" % (self._SPINNER[self._busy_i],
                                          self._busy_msg))

    def set_busy(self, msg):
        """Show status-bar spinner with tr'd msg."""
        if getattr(self, "_busy_lbl", None) is None:
            return
        self._busy_msg = msg
        self._busy_lbl.setVisible(True)
        if not self._busy_timer.isActive():
            self._busy_timer.start()
        self._busy_tick()

    def clear_busy(self):
        if getattr(self, "_busy_lbl", None) is None:
            return
        self._busy_timer.stop()
        self._busy_lbl.setVisible(False)
        self._busy_lbl.setText("")

    def _prewarm_vision(self):
        if not self.cfg.get("vision_assist"):
            return
        try:
            from PySide6.QtCore import QThreadPool
            from . import vision, scanworker
            vision.clear_cache()
            self.set_busy(tr('Warming reader'))
            task = scanworker.PrewarmTask(dict(self.cfg))
            task.signals.done.connect(self.clear_busy)
            QThreadPool.globalInstance().start(task)
        except Exception:
            self.clear_busy()

    def _load_session(self):
        """Load session sidecar."""
        ok = self.store.load_session(self.session_path)
        if not ok or self.store.read_only:
            self._session_lock_pending = True
        return ok

    def _show_session_lock(self):
        """Explain refusal once at load time."""
        self._session_lock_pending = False
        self._session_ro_warned = True
        try:
            box = QMessageBox(QMessageBox.Warning, tr('Session read-only'),
                              session_lock_text(self.store),
                              QMessageBox.Ok, self)
            lab = box.findChild(QLabel, "qt_msgbox_label")
            if lab is not None:
                lab.setWordWrap(True)
                lab.setMinimumWidth(460)
            fresh = None
            if self.store.lock_kind == "corrupt":
                fresh = box.addButton(tr('Start a new session'),
                                      QMessageBox.DestructiveRole)
                box.setDefaultButton(QMessageBox.Ok)
            box.exec()
            if fresh is not None and box.clickedButton() is fresh:
                self._session_start_over()
        except Exception:
            pass
        try:
            self.set_status(tr('session read-only'), icon="warn")
        except Exception:
            pass

    def _session_start_over(self):
        """Rename damaged sidecar aside so drawing saves."""
        bak = self.store.start_over(self.session_path)
        if not bak:
            self.set_status(tr('session NOT saved'), icon="warn")
            return
        self._session_ro_warned = False
        self._session_save_failed = False
        self.set_status(tr('started over; damaged file kept as %s')
                        % os.path.basename(bak))
        self._save_session()

    def _edit_blocked(self):
        """Refuse edit session cannot keep."""
        if not self.store.read_only:
            return False
        self._show_session_lock()
        return True

    def _save_session(self):
        """Write session sidecar."""
        if self.store.read_only:
            if not getattr(self, "_session_ro_warned", False):
                self._show_session_lock()
            try:
                self.set_status(tr('session read-only'), icon="warn")
            except Exception:
                pass
            return False
        try:
            d = os.path.dirname(self.session_path)
            if d and not os.path.isdir(d):
                try:
                    os.makedirs(d, exist_ok=True)
                except PermissionError:
                    self.session_path = qc_path(self.pdf_path,
                                                "_bubbles.json", subdir="")
                    self.set_status("qc/ not writable; saving beside PDF")
            self.store.save_session(self.session_path)
        except SessionReadOnly:
            self._session_ro_warned = False
            self._show_session_lock()
            return False
        except Exception as e:
            if not getattr(self, "_session_save_failed", False):
                self._session_save_failed = True
                try:
                    QMessageBox.warning(
                        self, tr('Session not saved'),
                        tr('Could not write\n%s\n\n%s\n\nCheck free space, '
                           'permissions, or if the file is open elsewhere. '
                           'Bubbler retries on the next change.')
                        % (self.session_path, e)
                        + "\n\n" + tr('Bubbles are NOT being saved '
                                       'to disk.'))
                except Exception:
                    pass
            try:
                self.set_status(tr('session NOT saved'),
                                icon="warn")
            except Exception:
                pass
            return False
        if getattr(self, "_session_save_failed", False):
            self._session_save_failed = False
            self.set_status(tr('session saving again'))
        return True

    def page_bubbles(self, page_i=None):
        if page_i is None:
            page_i = self.page_i
        seen = {}
        for d in self.ledger:
            if d.get("page") != page_i:
                continue
            b = base_of(d["bubble"])
            if b not in seen:
                seen[b] = (b, d["x"], d["y"],
                           d.get("bx", d["x"]), d.get("by", d["y"]))
        return list(seen.values())

    def _set_bubble_pos(self, basenum, bx=None, by=None, ax=None, ay=None):
        for d in self.ledger:
            if base_of(d["bubble"]) == basenum and \
                    d.get("page") == self.page_i:
                if bx is not None:
                    d["bx"], d["by"] = bx, by
                if ax is not None:
                    d["x"], d["y"] = ax, ay

    def adopt_iso_class(self, gtols):
        """Drawing-declared ISO 2768 class beats ribbon setting."""
        from .scanlib import iso_class_from_gtols
        cls = iso_class_from_gtols(gtols)
        if not cls or cls == self.last.get("icls"):
            return None
        self.last["icls"] = cls
        cb = getattr(self, "cb_icls", None)
        if cb is not None:
            cb.blockSignals(True)
            cb.setCurrentText(cls)
            cb.blockSignals(False)
        return cls

    def _apply_general_tol(self, rw, h, gtols, iso_on=False):
        """Lay drawing general tolerance on row that has none."""
        if rw.get("tol_sym") is not None or rw.get("tol_max") is not None \
                or rw.get("tol_min") is not None:
            return rw
        last = getattr(self, "last", None) or {}
        res = general_tol(gentol_callout(h, rw), gtols, self.cfg,
                          self.drawing, icls=last.get("icls"),
                          iso_on=bool(iso_on))
        if res.value:
            rw["tol_sym"] = float(res.value)
        return rw

    def _scr(self, px, py):
        x, y = self.viewport.page_to_scene(px, py)
        return QPointF(x, y)

    def _page_xy(self, sp):
        px, py = self.viewport.scene_to_page(sp.x(), sp.y())
        r = self.doc[self.page_i].rect
        if 0 <= px <= r.width and 0 <= py <= r.height:
            return px, py
        return None

    HIT_SLOP = 3.0

    def hit_bubble(self, x, y):
        """Hit-test drawn balloon outline."""
        rad = float(self.cfg.get("radius", RADIUS))
        tiers = self._bubble_tiers(self.page_i)
        for b, _, _, bx, by in reversed(self.page_bubbles()):
            shape = tier_shape(tiers.get(b), self.cfg)
            if point_in_bubble(shape, bx, by, rad, x, y, self.HIT_SLOP):
                return b
        return None

    def hit_anchor(self, x, y):
        tol = max(4.0, 5.0 / self.zoom)
        for b, ax, ay, bx, by in reversed(self.page_bubbles()):
            if (bx, by) == (ax, ay):
                continue
            if abs(ax - x) <= tol and abs(ay - y) <= tol:
                return b
        return None

    def set_status(self, extra="", icon=None):
        extra = tr(extra)
        mm = "  [%s]" % tr('MEASURE MODE') \
            if self.measure_mode else ""
        if self.store.read_only:
            mm = "  [%s]" % tr('READ-ONLY - NOT SAVING') + mm
        ncrit = sum(1 for d in self.ledger if d.get("tier") == "red")
        ncmm = sum(1 for d in self.ledger if d.get("gage") == "CMM")
        state = (tr(" Page %d/%d   next here #%d   zoom %d%%   bubbles here:"
                    " %d   rows: %d (crit %d, CMM %d)   unsaved: %d") + "%s"
                 ) % (self.page_i + 1, self.doc.page_count,
                    self.store.next_number(self.page_i),
                    int(self.zoom * 100), len(self.page_bubbles()),
                    len(self.ledger), ncrit, ncmm, self.unsaved(), mm)
        if getattr(self, "_status_state", None) is not None:
            self._status_state.setText(state)
        else:
            self.statusBar().showMessage(state)
        lp = getattr(self, "lbl_page", None)
        if lp is not None:
            lp.setText("%d/%d" % (self.page_i + 1, self.doc.page_count))
        self._update_title()
        if extra:
            self._set_toast_icon(icon)
            self.statusBar().showMessage(extra, 6000)

    def _set_toast_icon(self, icon):
        lab = getattr(self, "_toast_icon", None)
        if lab is None:
            return
        if icon:
            col = "#c0392b" if icon == "warn" else "#2e7d32"
            lab.setPixmap(make_pixmap(icon, color=col, px=16))
            lab.setVisible(True)
        else:
            lab.clear()
            lab.setVisible(False)

    def _on_toast_changed(self, text):
        if not text:
            self._set_toast_icon(None)

    def _apply_lock_chrome(self):
        """Grey out Save while session refused."""
        b = getattr(self, "btn_save", None)
        if b is not None:
            ro = bool(self.store.read_only)
            b.setEnabled(not ro)
            if ro:
                b.setToolTip(tr('Session read-only') + " - "
                             + tr('Bubbles are NOT being saved '
                                  'to disk.'))
        self._update_title()

    def _update_title(self):
        try:
            dirty = "• " if self.unsaved() else ""
            ro = ("[%s] " % tr('READ-ONLY')) if self.store.read_only else ""
            self.setWindowTitle(dirty + ro + self._title_base)
        except Exception:
            pass

    def fit(self):
        page = self.doc[self.page_i]
        vp = self.view.viewport()
        cw = max(vp.width(), 100)
        ch = max(vp.height(), 100)
        r = page.rect
        w, h = ((r.height, r.width) if self.rotation % 180
                else (r.width, r.height))
        if w > 0 and h > 0:
            self.zoom = max(0.3, min(8.0, min((cw - 20) / w, (ch - 20) / h)))
        self.render()

    PIX_SLOTS = 4
    PIX_MAX_PX = 20_000_000

    def render(self):
        page = self.doc[self.page_i]
        m = fitz.Matrix(self.zoom, self.zoom)
        if self.rotation:
            m = m * fitz.Matrix(self.rotation)
        rr = page.rect * m
        self.viewport.set_transform(m.a, m.b, m.c, m.d, m.e, m.f,
                                    rr.x0, rr.y0)
        key = (self.page_i, round(self.zoom, 4), self.rotation)
        cache = self.viewport.pix_cache
        hit = cache.get(key)
        if hit is not None:
            cache.move_to_end(key)
            pm = hit
        else:
            pix = page.get_pixmap(matrix=m)
            fmt = (QImage.Format_RGBA8888 if pix.alpha
                   else QImage.Format_RGB888)
            data = bytes(pix.samples)
            img = QImage(data, pix.width, pix.height, pix.stride, fmt)
            pm = QPixmap.fromImage(img)
            if pix.width * pix.height <= self.PIX_MAX_PX:
                cache[key] = pm
                while len(cache) > self.PIX_SLOTS:
                    cache.popitem(last=False)
        self._pixitem.setPixmap(pm)
        self.scene.setSceneRect(0, 0, pm.width(), pm.height())
        self.redraw_overlay()

    def redraw_overlay(self):
        self.view.viewport().update()
        self.set_status()

    _STATE_RING = {
        "none": ("#999999", 2),
        "in": ("#1f9e3c", 2),
        "out": ("#d01919", 4),
        "go": ("#0a9e8c", 2),
        "nogo": ("#e08a1e", 4),
    }

    def _state_ring(self, state):
        spec = self._STATE_RING.get(state)
        if spec is None:
            return None, 0
        return QColor(spec[0]), spec[1]

    @staticmethod
    def _draw_bubble_shape(painter, cx, cy, rad, shape):
        """Balloon body by tier."""
        pts = bubble_shape_points(shape, cx, cy, rad)
        if pts is None:
            r = shape_radius(shape, rad)
            painter.drawEllipse(QPointF(cx, cy), r, r)
        else:
            painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))

    def paint_overlay(self, painter):
        painter.setRenderHint(QPainter.Antialiasing, True)
        rad = float(self.cfg.get("radius", RADIUS)) * self.zoom
        fsz = float(self.cfg.get("fontsz", FONTSZ))
        LEXIT = LEADER_EXITS
        sel_bases = self._sel_bases() if self.sel else set()
        blue = QColor("#2266ff")
        red = QColor.fromRgbF(*RED)

        scr = self.viewport.page_to_scene
        rowmap = {}
        for d in self.ledger:
            if d.get("page") == self.page_i:
                rowmap.setdefault(base_of(d["bubble"]), d)

        # one font every tier
        rcfg = float(self.cfg.get("radius", RADIUS))
        fonts = {}

        def _num_font(txt):
            f = fonts.get(len(txt))
            if f is None:
                f = QFont("Arial")
                # pixels not points
                f.setPixelSize(max(1, int(round(fit_fontsz(rcfg, fsz, txt)
                                                * self.zoom))))
                fonts[len(txt)] = f
            return f
        for num, ax, ay, bx, by in self.page_bubbles():
            cx, cy = scr(bx, by)
            row = rowmap.get(num, {})
            col = QColor.fromRgbF(*tier_rgb(row.get("tier")))
            shape = tier_shape(row.get("tier"), self.cfg)
            if (bx, by) != (ax, ay) and self._leader_of(num):
                tx, ty = ((self._leader_target(self.page_i, bx, by, ax, ay))
                          if self.cfg.get("leader_trim", True) else (ax, ay))
                ahx, ahy = scr(tx, ty)
                ex = LEXIT.get(self._lexit_of(num))
                if ex is not None:
                    # start on outline
                    sup = shape_support(shape, rad, ex[0], ex[1])
                    sx0, sy0 = cx + ex[0] * sup, cy + ex[1] * sup
                else:
                    dx, dy = ahx - cx, ahy - cy
                    dist = (dx * dx + dy * dy) ** 0.5 or 1.0
                    sup = shape_support(shape, rad, dx / dist, dy / dist)
                    sx0 = cx + dx / dist * sup
                    sy0 = cy + dy / dist * sup
                pen = QPen(col, max(1.2, rad * 0.1))
                painter.setPen(pen)
                painter.drawLine(QPointF(sx0, sy0), QPointF(ahx, ahy))
                painter.setBrush(QBrush(col))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(ahx, ahy), 3, 3)
            if self.measure_mode:
                sc, sw = self._state_ring(measure_state(row))
                if sc is not None:
                    # ring clears shape points
                    rr = shape_extent(shape, rad) + 3
                    painter.setPen(QPen(sc, sw))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(QPointF(cx, cy), rr, rr)
            painter.setPen(QPen(col, 2))
            painter.setBrush(QBrush(QColor("white")))
            self._draw_bubble_shape(painter, cx, cy, rad, shape)
            if num in sel_bases:
                sr = shape_extent(shape, rad) + 2
                painter.setPen(QPen(blue, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), sr, sr)
            painter.setPen(QPen(col))
            painter.setFont(_num_font(str(num)))   # one size every tier
            tw = max(rad, fit_fontsz(rcfg, fsz, str(num)) * self.zoom * 1.2)
            painter.drawText(QRectF(cx - tw, cy - tw, 2 * tw, 2 * tw),
                             Qt.AlignCenter, str(num))
        if self.measure_mode and self._walk and \
                self._walk_idx < len(self._walk) and \
                self._walk[self._walk_idx] < len(self.ledger):
            d = self.ledger[self._walk[self._walk_idx]]
            if d.get("page") == self.page_i:
                bx, by = d.get("bx", d["x"]), d.get("by", d["y"])
                cx, cy = scr(bx, by)
                rr = shape_extent(tier_shape(d.get("tier"), self.cfg),
                                  rad) + 6
                painter.setPen(QPen(blue, 3))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), rr, rr)
        if self._flash_ring and self._flash_ring[0] == self.page_i:
            _, bx, by = self._flash_ring
            cx, cy = scr(bx, by)
            painter.setPen(QPen(blue, 3))
            painter.setBrush(Qt.NoBrush)
            fr = widest_extent(rad, self.cfg) + 5   # clears every shape
            painter.drawEllipse(QPointF(cx, cy), fr, fr)
        if self._scanhl and self._scanhl[0] == self.page_i:
            rc = self._scanhl[1]
            p0 = scr(rc[0], rc[1])
            p1 = scr(rc[2], rc[3])
            painter.setPen(QPen(blue, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(min(p0[0], p1[0]) - 3, min(p0[1], p1[1]) - 3,
                                    abs(p1[0] - p0[0]) + 6,
                                    abs(p1[1] - p0[1]) + 6))
        if self._marquee is not None:
            x0, y0, x1, y1 = self._marquee
            pen = QPen(blue, 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(min(x0, x1), min(y0, y1),
                                    abs(x1 - x0), abs(y1 - y0)))
        if self._capturing and self._capture_start is not None and \
                self._capture_cur is not None:
            x0, y0 = self._capture_start
            x1, y1 = self._capture_cur
            painter.setPen(QPen(blue, 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(min(x0, x1), min(y0, y1),
                                    abs(x1 - x0), abs(y1 - y0)))
        if (self._scan_region_mode or self._scan_inc or self._scan_exc
                or self._correct_mode):
            green = QColor(34, 170, 34)

            def region_box(r, color):
                x0, y0, x1, y1 = r
                fill = QColor(color.red(), color.green(), color.blue(), 45)
                painter.setPen(QPen(color, 2, Qt.DashLine))
                painter.setBrush(QBrush(fill))
                painter.drawRect(QRectF(min(x0, x1), min(y0, y1),
                                        abs(x1 - x0), abs(y1 - y0)))

            if self._scan_inc is not None:
                region_box(self._scan_inc, green)
            if self._scan_exc is not None:
                region_box(self._scan_exc, red)
            if self._scan_drag is not None:
                if self._correct_mode:
                    region_box(self._scan_drag, QColor(30, 110, 230))
                else:
                    region_box(self._scan_drag,
                               green if self._scan_region_mode == "include"
                               else red)
        if self.cfg.get("vision_debug_on"):
            self._paint_debug(painter, scr)

    def _page_sections(self):
        """Cached callout sections for page (debug)."""
        key = (id(self.doc), self.page_i)
        cache = self.__dict__.get("_sec_cache")
        if cache is not None and cache[0] == key:
            return cache[1]
        from bubbler import scanpos
        try:
            secs = scanpos.page_sections(self.doc[self.page_i], self.cfg)
        except Exception:
            secs = []
        self._sec_cache = (key, secs)
        return secs

    def toggle_debug_overlay(self):
        self.cfg["vision_debug_on"] = not self.cfg.get("vision_debug_on")
        save_cfg(self.cfg)
        self.redraw_overlay()

    _DBG_LAYER_ORDER = ("sections", "regions", "symbols")

    def _toggle_debug_layer(self, key, on):
        layers = set(self.cfg.get("vision_debug_layers") or [])
        layers.add(key) if on else layers.discard(key)
        self.cfg["vision_debug_layers"] = [k for k in self._DBG_LAYER_ORDER
                                           if k in layers]
        save_cfg(self.cfg)
        self.redraw_overlay()

    def _paint_debug(self, painter, scr):
        layers = self.cfg.get("vision_debug_layers") or []
        if "sections" in layers:
            self._paint_sections(painter, scr)
        if "regions" in layers:
            self._paint_regions(painter, scr)
        if "symbols" in layers:
            self._paint_symbols(painter, scr)

    def _paint_box(self, painter, scr, rect, col, label=None, dashed=True):
        p0, p1 = scr(rect[0], rect[1]), scr(rect[2], rect[3])
        painter.setPen(QPen(col, 1, Qt.DashLine if dashed else Qt.SolidLine))
        painter.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(), 28)))
        painter.drawRect(QRectF(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1]))
        if label:
            painter.setPen(QPen(col, 1))
            painter.drawText(QPointF(p0[0] + 2, p0[1] - 2), label)
        return p0, p1

    def _paint_sections(self, painter, scr):
        multi = QColor(170, 40, 200)          # merged stack
        single = QColor(150, 150, 150)         # lone line
        for s in self._page_sections():
            col = multi if s["n"] > 1 else single
            self._paint_box(painter, scr, s["rect"], col,
                            "%dx" % s["n"] if s["n"] > 1 else None)

    def _paint_regions(self, painter, scr):
        col = QColor(30, 110, 230)
        for x0, y0, x1, y1, label in self._page_regions():
            self._paint_box(painter, scr, (x0, y0, x1, y1), col, label,
                            dashed=False)

    def _paint_symbols(self, painter, scr):
        col = QColor(216, 120, 20)
        for x0, y0, x1, y1, tok in self._page_symbols():
            self._paint_box(painter, scr, (x0, y0, x1, y1), col, tok,
                            dashed=False)

    def _region_dets(self, page_i=None):
        """Cached raw region boxes (x0,y0,x1,y1,conf,ci[,quad]). Shared by the
        debug overlay and click-to-bubble so the model runs once per page."""
        if page_i is None:
            page_i = self.page_i
        key = (id(self.doc), page_i)
        c = self.__dict__.get("_rgn_det_cache")
        if c is not None and c[0] == key:
            return c[1]
        from . import vision
        try:
            out = list(vision._region_boxes(self.doc[page_i], self.cfg))
        except Exception:
            out = []
        self._rgn_det_cache = (key, out)
        return out

    def _page_regions(self):
        """Cached detector-block boxes for page (debug)."""
        from . import vision
        out = []
        for b in self._region_dets():
            ci = int(b[5]) if len(b) > 5 else -1
            cls = (vision._REGION_CLASSES[ci]
                   if 0 <= ci < len(vision._REGION_CLASSES) else "?")
            out.append((b[0], b[1], b[2], b[3],
                        "%s %.0f%%" % (cls, float(b[4]) * 100)))
        return out

    def _page_symbols(self):
        """Cached GD&T symbol-detector boxes for page (debug)."""
        key = (id(self.doc), self.page_i)
        c = self.__dict__.get("_sym_dbg_cache")
        if c is not None and c[0] == key:
            return c[1]
        from . import vision
        out = []
        try:
            for env, tok in vision._symbol_dets(self.doc[self.page_i], self.cfg):
                out.append((env[0], env[1], env[2], env[3], str(tok).strip()))
        except Exception:
            out = []
        self._sym_dbg_cache = (key, out)
        return out

    def flip(self, d):
        self.goto_page(self.page_i + d)

    def rezoom(self, f):
        self.zoom = max(0.3, min(8.0, self.zoom * f))
        self.render()

    def rotate(self):
        self.rotation = (self.rotation + 90) % 360
        self.render()

    def set_tool(self, name):
        self.tool = name
        if name != "select":
            self.sel.clear()
        self.view.setCursor(Qt.ArrowCursor if name == "select"
                            else Qt.CrossCursor)
        try:
            self.btn_tool_add.setChecked(name == "add")
            self.btn_tool_sel.setChecked(name == "select")
        except Exception:
            pass
        self.redraw_overlay()
        self._qbar_refresh()
        self.set_status("tool: %s" % name)

    def _entry_focused(self):
        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QComboBox, QDoubleSpinBox)) or \
            (w is not None and w.metaObject().className() == "QSpinBox")

    def _text_input_focused(self):
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QDoubleSpinBox)):
            return True
        if isinstance(w, QComboBox):
            return w.isEditable()
        return bool(w) and w.metaObject().className() in (
            "QSpinBox", "QPlainTextEdit", "QTextEdit")

    def eventFilter(self, obj, e):
        # bypass ribbon focus
        if e.type() == QEvent.KeyPress and self.isActiveWindow() \
                and not QApplication.activeModalWidget() \
                and not self._text_input_focused():
            fw = QApplication.focusWidget()
            vp = getattr(self.view, "viewport", lambda: None)()
            if fw is not self.view and fw is not vp \
                    and self._global_letter(e.text()):
                return True
        return super().eventFilter(obj, e)

    def _global_letter(self, ch):
        if ch == "m":
            self.toggle_measure()
            return True
        if self.measure_mode:
            return False
        if ch == "b":
            self.toggle_panel()
        elif ch == "v":
            self.set_tool("select")
        elif ch == "a":
            self.set_tool("add")
        elif ch == "q":
            self._kbd_qbar()
        else:
            return False
        return True

    def _kbd_tool(self, name):
        if self._entry_focused() or self.measure_mode:
            return
        self.set_tool(name)

    def _kbd_toggle(self, k):
        if self._entry_focused():
            return
        if k == "m":
            self.toggle_measure()
        else:
            self.toggle_panel()

    def _kbd_delete(self):
        if self._entry_focused() or self.measure_mode:
            return
        if self.sel:
            self.delete_selection()

    def on_right_press(self, sp, gpos):
        p = self._page_xy(sp)
        hit = self.hit_bubble(*p) if p else None
        if hit is None:
            return False
        rows = [(i, d) for i, d in enumerate(self.ledger)
                if base_of(d["bubble"]) == hit and
                d.get("page") == self.page_i]
        if not rows:
            return True
        m = QMenu(self)
        if len(rows) == 1:
            i0 = rows[0][0]
            m.addAction(tr('Edit #%s') % rows[0][1]["bubble"],
                        lambda i=i0: self.edit_ledger_row(i))
        else:
            em = m.addMenu(tr('Edit sub-row'))
            for i, d in rows:
                em.addAction("#%s  %s" % (d["bubble"], d.get("feature", "")),
                             lambda i=i: self.edit_ledger_row(i))
        m.addAction(tr('Add sub-row'),
                    lambda: self.add_sub_row(hit))
        if len(rows) > 1:
            dm = m.addMenu(tr('Delete sub-row'))
            for i, d in rows:
                dm.addAction("#%s  %s" % (d["bubble"], d.get("feature", "")),
                             lambda i=i: self.delete_sub_row(i))
        if self.cfg.get("collect_corrections"):
            d0 = rows[0][1]
            m.addAction(tr('Report misread...'),
                        lambda d=d0: self.report_misread(d))
        m.addSeparator()
        if len(rows) > 1:
            m.addAction(tr('Split into separate bubbles'),
                        lambda: self.split_bubble(hit))
            # merge
        m.addSeparator()
        m.addAction(tr('Delete bubble'),
                    lambda: self._delete_bases([hit]))
        m.exec(gpos.toPoint())
        return True

    def add_sub_row(self, basenum):
        rows = [(i, d) for i, d in enumerate(self.ledger)
                if base_of(d["bubble"]) == basenum]
        if not rows:
            return
        ref = rows[0][1]
        at = tuple(self.dlg_pos) if self.dlg_pos else None
        dlg = BubbleDialog(self, "%d+" % basenum, last=self.last,
                           leader_default=self._leader_of(basenum),
                           session=self.drawing, gtols=self.gtols_now(),
                           at=at, cfg=self.cfg)
        dlg.exec()
        if not dlg.result_rows:
            return
        self.snapshot()
        last_i = rows[-1][0]
        for k, d in enumerate(dlg.result_rows):
            if not d.get("gage"):
                d["gage"] = self.suggest(d)
            d["tier"] = tier_for_type(d.get("type"), self.cfg,
                                      d.get("tier", ""))
            d.update({"uid": ref["uid"], "page": ref.get("page", 0),
                      "x": ref["x"], "y": ref["y"],
                      "bx": ref.get("bx", ref["x"]),
                      "by": ref.get("by", ref["y"]), "sheet_row": None})
            self.ledger.insert(last_i + 1 + k, d)
        self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()

    def delete_sub_row(self, idx):
        d = self.ledger[idx]
        if QMessageBox.question(
                self, tr('Delete'),
                tr('Delete sub-row #%s (%s)?')
                % (d["bubble"], d.get("feature", "")),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        self.snapshot()
        if d.get("sheet_row"):
            self.writer.clear_row(d["sheet_row"])
            try:
                self.writer.save()
            except Exception:
                pass
        del self.ledger[idx]
        self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()

    def split_bubble(self, base):
        """Explode multi-row callout."""
        rows = [(i, d) for i, d in enumerate(self.ledger)
                if base_of(d["bubble"]) == base]
        if len(rows) < 2:
            self.set_status(tr('nothing to split'))
            return
        self.snapshot()
        step = float(self.cfg.get("radius", 14)) * 2.2
        for n, (i, d) in enumerate(rows[1:], start=1):
            d["uid"] = self.store.new_uid()
            d["x"] = d["x"] + step * n
            d["y"] = d["y"] + step * n
            d["bx"] = d.get("bx", d["x"]) + step * n
            d["by"] = d.get("by", d["y"]) + step * n
        self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()
        self.set_status(tr('split into %d bubbles') % len(rows))

    def _sel_first_rows(self):
        out = []
        seen = set()
        for d in self.ledger:
            if d["uid"] in self.sel and d.get("page") == self.page_i \
                    and d["uid"] not in seen:
                seen.add(d["uid"])
                out.append(d)
        return out

    def align_sel(self, axis):
        rows = self._sel_first_rows()
        if len(rows) < 2:
            self.set_status(tr('select 2+ bubbles'))
            return
        self.snapshot()
        if axis == "h":
            yy = sum(d.get("by", d["y"]) for d in rows) / len(rows)
            below = sum(1 for d in rows if d["y"] > d.get("by", d["y"]))
            exit_side = "s" if below >= len(rows) / 2.0 else "n"
            for d in rows:
                self._set_uid_pos(d["uid"], by=yy, lexit=exit_side)
        else:
            xx = sum(d.get("bx", d["x"]) for d in rows) / len(rows)
            right = sum(1 for d in rows if d["x"] > d.get("bx", d["x"]))
            exit_side = "e" if right >= len(rows) / 2.0 else "w"
            for d in rows:
                self._set_uid_pos(d["uid"], bx=xx, lexit=exit_side)
        self._save_session()
        self.render()

    def distribute_sel(self, axis):
        rows = self._sel_first_rows()
        if len(rows) < 3:
            self.set_status(tr('select 3+ bubbles'))
            return
        key = (lambda d: d.get("bx", d["x"])) if axis == "h" \
            else (lambda d: d.get("by", d["y"]))
        rows.sort(key=key)
        lo, hi = key(rows[0]), key(rows[-1])
        step = (hi - lo) / (len(rows) - 1)
        self.snapshot()
        for k, d in enumerate(rows):
            v = lo + k * step
            if axis == "h":
                self._set_uid_pos(d["uid"], bx=v)
            else:
                self._set_uid_pos(d["uid"], by=v)
        self._save_session()
        self.render()

    def _set_uid_pos(self, uid, bx=None, by=None, lexit=None):
        for d in self.ledger:
            if d["uid"] == uid and d.get("page") == self.page_i:
                if bx is not None:
                    d["bx"] = bx
                if by is not None:
                    d["by"] = by
                if lexit is not None:
                    d["lexit"] = lexit

    def _leader_of(self, basenum):
        for d in self.ledger:
            if base_of(d["bubble"]) == basenum and \
                    d.get("page") == self.page_i:
                if "leader" in d:
                    return bool(d["leader"])
                return (d.get("bx", d["x"]), d.get("by", d["y"])) != \
                    (d["x"], d["y"])
        return False

    def _lexit_of(self, basenum):
        for d in self.ledger:
            if base_of(d["bubble"]) == basenum and \
                    d.get("page") == self.page_i:
                return d.get("lexit")
        return None

    def _build_measure_bar(self):
        BG = "#fff7e0"
        self.mbar = QWidget()
        self.mbar.setStyleSheet("background:%s;" % BG)
        lay = QHBoxLayout(self.mbar)
        lay.setContentsMargins(8, 4, 8, 4)
        self.mcount = QLabel("")
        self.mcount.setStyleSheet("color:#5a5a5a; font-size:9pt;")
        self.mlab = QLabel("")
        self.mlab.setStyleSheet("font-weight:bold; font-size:10pt;")
        self.ment = MeasureEdit(self)
        self.ment.setMaximumWidth(140)
        self._mbar_sync = False
        self.munits_cb = QComboBox()
        self.munits_cb.setMaximumWidth(110)
        self.munits_cb.setToolTip(
            tr('Units you measure in. Readings are stored in drawing '
               'units.'))
        self.munits_cb.currentIndexChanged.connect(self._munits_changed)
        self.munits_lbl = QLabel(tr('measure in'))
        self.munits_lbl.setStyleSheet("color:#5a5a5a; font-size:8pt;")
        # stage being inspected
        op_lbl = QLabel(tr('op:'))
        op_lbl.setStyleSheet("color:#5a5a5a; font-size:8pt;")
        self.mop_cb = QComboBox()
        seq = ops_seq(self.cfg, self.drawing)
        self.mop_cb.addItems(seq)
        self.mop_cb.setMaximumWidth(80)
        self.mop_cb.setToolTip(tr('Machining stage you are inspecting. '
                                  'Ops run in sequence.'))
        self._measure_op = self.mop_cb.currentText() or seq[0]
        self.mop_cb.currentTextChanged.connect(self._mop_changed)
        made_lbl = QLabel(tr('made at'))
        made_lbl.setStyleSheet("color:#5a5a5a; font-size:8pt;")
        self.mmade_cb = QComboBox()
        self.mmade_cb.setMaximumWidth(78)
        self.mmade_cb.addItem(tr('any'), "")
        for _op in seq:
            self.mmade_cb.addItem(_op, _op)
        self.mmade_cb.setToolTip(tr('Op that creates this characteristic. '
                                    'Earlier ops do not measure it.'))
        self.mmade_cb.currentIndexChanged.connect(self._mmade_changed)
        self.mrecheck_cb = QCheckBox(tr('recheck'))
        self.mrecheck_cb.setStyleSheet("font-size:8pt;")
        self.mrecheck_cb.setToolTip(
            tr('Re-measure at every later op: the part distorts.'))
        self.mrecheck_cb.toggled.connect(self._mrecheck_toggled)
        self.mskip_cb = QCheckBox(tr('skip filled'))
        self.mskip_cb.setChecked(bool(self.cfg.get("measure_skip_filled",
                                                   True)))
        self.mskip_cb.setStyleSheet("font-size:8pt;")
        self.mskip_cb.toggled.connect(self._mskip_toggled)
        b_go = QPushButton("GO")
        b_go.setMaximumWidth(60)
        b_go.setMinimumWidth(60)
        b_go.setToolTip(tr('Record GO + next'))
        b_go.clicked.connect(lambda: self._measure_quick("GO"))
        b_nogo = QPushButton("NOGO")
        b_nogo.setMaximumWidth(72)
        b_nogo.setMinimumWidth(72)
        b_nogo.setToolTip(tr('Record NOGO + next'))
        b_nogo.clicked.connect(lambda: self._measure_quick("NOGO"))
        b_clear = QPushButton("↺")
        b_clear.setMaximumWidth(30)
        b_clear.setToolTip(tr('Clear this reading (re-measure)'))
        b_clear.clicked.connect(self._measure_clear)
        self.mprev = QLabel("")
        self.mprev.setStyleSheet("color:#8a6d3b; font-size:8pt;")
        # method and gage
        gage_lbl = QLabel(tr('how'))
        gage_lbl.setStyleSheet("color:#5a5a5a; font-size:8pt;")
        self.mhow_cb = QComboBox()
        self.mhow_cb.setEditable(True)
        self.mhow_cb.addItems(list(METHODS) + [g for g in GAGES
                                               if g not in METHODS])
        self.mhow_cb.setMinimumWidth(120)
        self.mhow_cb.setToolTip(tr('Method or gage for this measurement.'))
        self.mhow_cb.currentTextChanged.connect(self._mhow_changed)
        help_lbl = QLabel(tr('Enter=save+next  G/+=GO  N/-=NOGO  '
                             'Shift+Enter=back  Tab=skip  Esc=exit'))
        help_lbl.setStyleSheet("color:#5a5a5a; font-size:8pt;")
        lay.addWidget(self.mcount)
        lay.addWidget(self.mlab)
        lay.addWidget(op_lbl)
        lay.addWidget(self.mop_cb)
        lay.addWidget(made_lbl)
        lay.addWidget(self.mmade_cb)
        lay.addWidget(self.mrecheck_cb)
        lay.addWidget(self.munits_lbl)
        lay.addWidget(self.munits_cb)
        lay.addWidget(self.ment)
        lay.addWidget(b_go)
        lay.addWidget(b_nogo)
        lay.addWidget(b_clear)
        lay.addWidget(self.mprev)
        lay.addWidget(gage_lbl)
        lay.addWidget(self.mhow_cb)
        lay.addWidget(self.mskip_cb)
        lay.addStretch(1)
        lay.addWidget(help_lbl)
        self._mbar_dock = QDockWidget("", self)
        self._mbar_dock.setTitleBarWidget(QWidget())
        self._mbar_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self._mbar_dock.setWidget(self.mbar)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._mbar_dock)
        self._mbar_dock.hide()
        self._fill_munits()

    def _append_callout(self, rows, x, y, rect=None):
        """Append rows as one callout."""
        want = bool(rows[0].get("leader", self.use_leaders())) if rows \
            else self.use_leaders()
        bx, by, lead = self.place_bubble(x, y, rect=rect, lead=want,
                                         tier=self._row_tier(rows[0] if rows
                                                             else {}))
        uid = self.store.new_uid()
        n = 0
        for d in rows:
            for rr in expand_hole_row(d, self.cfg):
                if not rr.get("gage"):
                    rr["gage"] = self.suggest(rr)
                rr.setdefault("bubble", "?")
                rr["leader"] = lead          # flag matches offset
                rr["tier"] = tier_for_type(rr.get("type"), self.cfg,
                                           rr.get("tier", ""))
                rr.update({"uid": uid, "page": self.page_i, "x": x, "y": y,
                           "bx": bx, "by": by, "sheet_row": None})
                self.ledger.append(rr)
                n += 1
        return n

    def _balloon_from_rows(self, rows, x, y, rect=None):
        if not rows:
            return
        self.snapshot()
        n = self._append_callout(rows, x, y, rect=rect)
        self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()
        self.set_status(tr('ballooned %d rows') % n)

    def _bubbles_in_rect(self, rect, page_i=None):
        """Bubbles in area."""
        x0, y0, x1, y1 = rect
        out = []
        for num, ax, ay, _bx, _by in self.page_bubbles(page_i):
            if x0 <= ax <= x1 and y0 <= ay <= y1:
                out.append(num)
        return out

    def _regroup_capture(self, bases, rows, x, y, rect=None):
        """Drop bubbles in box."""
        if not rows:
            return
        self.snapshot()
        uids = set()
        for d in self.ledger:
            if base_of(d["bubble"]) in bases:
                uids.add(d["uid"])
                if d.get("sheet_row"):
                    self.writer.clear_row(d["sheet_row"])
        try:
            self.writer.save()
        except Exception:
            pass
        for u in uids:
            self.store.remove(u)
            self.sel.discard(u)
        self._append_callout(rows, x, y, rect=rect)
        self.store.renumber()
        self._resync_sheet_rows()
        self._save_session()
        self.refresh_panel()
        self.render()
        self.set_status(tr('regrouped %d into one callout (Ctrl+Z to undo)')
                        % len(bases))
