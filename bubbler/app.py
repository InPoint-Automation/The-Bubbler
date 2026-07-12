# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Main window. Canvas, balloons, panel, scan, export.

import os

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
                     measure_state)
from .config import load_cfg, save_cfg, units_of
from .scanlib import expand_hole_row, suggest_gage, GAGES, dp_of_value
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
from .store import BubbleStore
from .viewport import Viewport
from .tools import make_tools


class MainWindow(MeasureMixin, GeometryMixin, HistoryMixin, PanelMixin,
                 SettingsMixin, RibbonMixin, ReportMixin, ImportMixin,
                 ExportMixin, ScanMixin, CaptureMixin, InputMixin,
                 BubbleMixin, TitleblockMixin, NavMixin, CorrectionsMixin,
                 CalcMixin, HotbarMixin, QMainWindow):
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

    def __init__(self, pdf_path, xlsx_path, cfg=None):
        super().__init__()
        self.cfg = cfg or load_cfg()
        set_lang(self.cfg.get("language", "en"))
        self.pdf_path = pdf_path
        self.writer = SheetWriter(xlsx_path,
                                  sheet_lang=self.cfg.get("sheet_lang", "both"))
        self.doc = fitz.open(pdf_path)
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
        QTimer.singleShot(500, self._titleblock_autofill)

    def _restore_window(self):
        """Restore saved geometry. True if applied."""
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
            g = bytes(self.saveGeometry().toHex()).decode("ascii")
            if g != self.cfg.get("win_geometry"):
                self.cfg["win_geometry"] = g
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
        """View-level keys (canvas focus). Returns True when handled."""
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
        self.btn_tool_add.setChecked(self.tool == "add")
        self.btn_tool_sel.setChecked(self.tool == "select")
        self.btn_panel.setChecked(self.panel_visible)
        self.btn_measure.setChecked(self.measure_mode)
        self.btn_calc.setChecked(self._calc_dock.isVisible())

    def _style_set(self, key, val):
        lo, hi = (3, 40) if key == "radius" else (4, 30)
        self.cfg[key] = max(lo, min(hi, float(val)))
        save_cfg(self.cfg)
        self.render()

    def _iso_changed(self, on):
        on = bool(on)
        if units_of(self.cfg) == "asme_inch":
            self.cfg["dp_on"] = on
        else:
            self.last["iso_on"] = on
            self.cfg["rib_iso_on"] = on
        save_cfg(self.cfg)
        self._qbar_refresh()

    def _icls_changed(self, _i=None):
        self.last["icls"] = self.cb_icls.currentText()
        self.cfg["default_iso_class"] = self.last["icls"]
        save_cfg(self.cfg)

    def _lead_changed(self, on):
        self.cfg["leaders"] = bool(on)
        save_cfg(self.cfg)
        self._qbar_refresh()

    def use_leaders(self):
        try:
            return bool(self.chk_lead.isChecked())
        except Exception:
            return bool(self.cfg.get("leaders"))

    def suggest(self, d):
        try:
            ct = float(self.cfg.get("cmm_tol", 0.01))
        except (TypeError, ValueError):
            ct = 0.01
        try:
            mt = float(self.cfg.get("micrometer_tol", 0.03))
        except (TypeError, ValueError):
            mt = 0.03
        return suggest_gage(d, self.cfg.get("gages"), ct, mt)

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
        self.cb_tier.setCurrentText(self.last.get("tier", ""))

    def _cell_edit(self, idx, colname):
        d = self.ledger[idx]
        cur = "" if d.get(colname) in (None, "") else str(d[colname])
        if colname == "tier":
            val, ok = QInputDialog.getItem(self, "tier", "tier", TIERS,
                                           max(0, TIERS.index(cur)
                                               if cur in TIERS else 0), False)
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
        d = self.ledger[idx]
        at = tuple(self.dlg_pos) if self.dlg_pos else None
        had_leader = d.get("leader",
                           (d.get("bx", d["x"]), d.get("by", d["y"]))
                           != (d["x"], d["y"]))
        dlg = BubbleDialog(self, d["bubble"], last=None, at=at,
                           cfg=self.cfg, edit_row=d,
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
                                        page_i=d.get("page"))
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
        """Show the animated status-bar spinner with `msg` (already tr'd)."""
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
        self.store.load_session(self.session_path)

    def _save_session(self):
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
        except Exception as e:
            if not getattr(self, "_session_save_failed", False):
                self._session_save_failed = True
                try:
                    QMessageBox.warning(
                        self, tr('Session not saved'),
                        "Could not write\n%s\n\n%s\n\nYour bubbles are NOT "
                        "being saved to disk. Check free space, permissions, "
                        "or whether the file is locked - Bubbler retries on "
                        "the next change. / Bąble NIE są zapisywane na dysk."
                        % (self.session_path, e))
                except Exception:
                    pass
            try:
                self.set_status(tr('session NOT saved'),
                                icon="warn")
            except Exception:
                pass
            return
        if getattr(self, "_session_save_failed", False):
            self._session_save_failed = False
            self.set_status(tr('session saving again'))

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

    def _apply_general_tol(self, rw, h, gtols):
        if rw.get("tol_sym") is not None or rw.get("tol_max") is not None \
                or rw.get("tol_min") is not None:
            return rw
        if rw.get("nominal") is None:
            return rw
        tp = h.get("tp")
        if tp in ("GDT", "SURFACE", "THREAD"):
            return rw
        t = None
        if tp == "ANGLE":
            t = (gtols or {}).get("ang")
        else:
            d = dp_of_value(h.get("v"))
            if d is not None:
                t = (gtols or {}).get(min(d, 4))
                if t is None and self.cfg.get("dp_on"):
                    try:
                        t = float((self.cfg.get("dp_tols") or {})
                                  .get(str(min(d, 3))) or 0) or None
                    except (TypeError, ValueError):
                        t = None
        if t:
            rw["tol_sym"] = float(t)
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

    def hit_bubble(self, x, y):
        rad = float(self.cfg.get("radius", RADIUS)) + 3
        for b, _, _, bx, by in reversed(self.page_bubbles()):
            if abs(bx - x) <= rad and abs(by - y) <= rad:
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

    def _update_title(self):
        try:
            dirty = "• " if self.unsaved() else ""
            self.setWindowTitle(dirty + self._title_base)
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
            img = QImage(bytes(pix.samples), pix.width, pix.height,
                         pix.stride, fmt)
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
        """Balloon body by tier: circle / square / triangle / diamond / star."""
        pts = bubble_shape_points(shape, cx, cy, rad)
        if pts is None:
            painter.drawEllipse(QPointF(cx, cy), rad, rad)
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

        font = QFont("Arial")
        font.setPixelSize(max(8, int(fsz * self.zoom * 0.8)))
        painter.setFont(font)
        for num, ax, ay, bx, by in self.page_bubbles():
            cx, cy = scr(bx, by)
            row = rowmap.get(num, {})
            col = QColor.fromRgbF(*tier_rgb(row.get("tier")))
            shape = tier_shape(row.get("tier"), self.cfg)
            if (bx, by) != (ax, ay) and self._leader_of(num):
                ahx, ahy = scr(ax, ay)
                ex = LEXIT.get(self._lexit_of(num))
                if ex is not None:
                    sx0, sy0 = cx + ex[0] * rad, cy + ex[1] * rad
                else:
                    dx, dy = ahx - cx, ahy - cy
                    dist = (dx * dx + dy * dy) ** 0.5 or 1.0
                    sx0 = cx + dx / dist * rad
                    sy0 = cy + dy / dist * rad
                pen = QPen(col, max(1.2, rad * 0.1))
                painter.setPen(pen)
                painter.drawLine(QPointF(sx0, sy0), QPointF(ahx, ahy))
                painter.setBrush(QBrush(col))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(ahx, ahy), 3, 3)
            if self.measure_mode:
                sc, sw = self._state_ring(measure_state(row))
                if sc is not None:
                    painter.setPen(QPen(sc, sw))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(QPointF(cx, cy), rad + 3, rad + 3)
            painter.setPen(QPen(col, 2))
            painter.setBrush(QBrush(QColor("white")))
            self._draw_bubble_shape(painter, cx, cy, rad, shape)
            if num in sel_bases:
                painter.setPen(QPen(blue, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), rad + 2, rad + 2)
            painter.setPen(QPen(col))
            painter.drawText(QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad),
                             Qt.AlignCenter, str(num))
        if self.measure_mode and self._walk and \
                self._walk_idx < len(self._walk) and \
                self._walk[self._walk_idx] < len(self.ledger):
            d = self.ledger[self._walk[self._walk_idx]]
            if d.get("page") == self.page_i:
                bx, by = d.get("bx", d["x"]), d.get("by", d["y"])
                cx, cy = scr(bx, by)
                rr = rad + 6
                painter.setPen(QPen(blue, 3))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), rr, rr)
        if self._flash_ring and self._flash_ring[0] == self.page_i:
            _, bx, by = self._flash_ring
            cx, cy = scr(bx, by)
            painter.setPen(QPen(blue, 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), rad + 5, rad + 5)
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
        # letter shortcuts fire even when focus sits on a ribbon widget
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
        if self.measure_mode:            # other toggles blocked mid-measure
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
                self, "Delete / Usuń",
                tr('Delete sub-row #%s (%s)?')
                % (d["bubble"], d.get("feature", ""))) != QMessageBox.Yes:
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
        op_lbl = QLabel(tr('op:'))
        op_lbl.setStyleSheet("color:#5a5a5a; font-size:8pt;")
        self.mop_cb = QComboBox()
        self.mop_cb.addItems(self.cfg.get("ops_list") or ["op1"])
        self.mop_cb.setMaximumWidth(80)
        self._measure_op = self.mop_cb.currentText() or "op1"
        self.mop_cb.currentTextChanged.connect(self._mop_changed)
        self.mskip_cb = QCheckBox(tr('skip filled'))
        self.mskip_cb.setChecked(bool(self.cfg.get("measure_skip_filled",
                                                   True)))
        self.mskip_cb.setStyleSheet("font-size:8pt;")
        self.mskip_cb.toggled.connect(self._mskip_toggled)
        b_go = QPushButton("GO")
        b_go.setMaximumWidth(54)
        b_go.setToolTip(tr('Record GO + next'))
        b_go.clicked.connect(lambda: self._measure_quick("GO"))
        b_nogo = QPushButton("NOGO")
        b_nogo.setMaximumWidth(60)
        b_nogo.setToolTip(tr('Record NOGO + next'))
        b_nogo.clicked.connect(lambda: self._measure_quick("NOGO"))
        b_clear = QPushButton("↺")
        b_clear.setMaximumWidth(30)
        b_clear.setToolTip(tr('Clear this reading (re-measure)'))
        b_clear.clicked.connect(self._measure_clear)
        self.mprev = QLabel("")
        self.mprev.setStyleSheet("color:#8a6d3b; font-size:8pt;")
        gage_lbl = QLabel(tr('gage'))
        gage_lbl.setStyleSheet("color:#5a5a5a; font-size:8pt;")
        self.mgage_cb = QComboBox()
        self.mgage_cb.setEditable(True)
        self.mgage_cb.addItems(GAGES)
        self.mgage_cb.setMinimumWidth(140)
        self.mgage_cb.currentTextChanged.connect(self._mgage_changed)
        help_lbl = QLabel(tr('Enter=save+next  G/+=GO  N/-=NOGO  '
                             'Shift+Enter=back  Tab=skip  Esc=exit'))
        help_lbl.setStyleSheet("color:#5a5a5a; font-size:8pt;")
        lay.addWidget(self.mcount)
        lay.addWidget(self.mlab)
        lay.addWidget(op_lbl)
        lay.addWidget(self.mop_cb)
        lay.addWidget(self.ment)
        lay.addWidget(b_go)
        lay.addWidget(b_nogo)
        lay.addWidget(b_clear)
        lay.addWidget(self.mprev)
        lay.addWidget(gage_lbl)
        lay.addWidget(self.mgage_cb)
        lay.addWidget(self.mskip_cb)
        lay.addStretch(1)
        lay.addWidget(help_lbl)
        self._mbar_dock = QDockWidget("", self)
        self._mbar_dock.setTitleBarWidget(QWidget())
        self._mbar_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self._mbar_dock.setWidget(self.mbar)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._mbar_dock)
        self._mbar_dock.hide()

    def _balloon_from_rows(self, rows, x, y, rect=None):
        if not rows:
            return
        self.snapshot()
        bx, by = ((self.auto_offset(x, y, rect=rect))
                  if (self.use_leaders() or rect is not None)
                  else (x, y))
        uid = self.store.new_uid()
        n = 0
        for d in rows:
            for rr in expand_hole_row(d, self.cfg):
                if not rr.get("gage"):
                    rr["gage"] = self.suggest(rr)
                rr.setdefault("bubble", "?")
                rr.setdefault("leader", self.use_leaders())
                rr["tier"] = tier_for_type(rr.get("type"), self.cfg,
                                           rr.get("tier", ""))
                rr.update({"uid": uid, "page": self.page_i, "x": x, "y": y,
                           "bx": bx, "by": by, "sheet_row": None})
                self.ledger.append(rr)
                n += 1
        self.store.renumber()
        self._save_session()
        self.refresh_panel()
        self.render()
        self.set_status(tr('ballooned %d rows') % n)
