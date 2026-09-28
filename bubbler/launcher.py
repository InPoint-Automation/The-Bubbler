# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# App entry + drawing picker.

import datetime
import os
import sys
import json

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                               QLabel, QFileDialog, QDialog, QListWidget,
                               QListWidgetItem, QPushButton, QMessageBox)

from .common import APP_NAME, qc_path
from .config import CFG_DEFAULT, load_cfg, save_cfg, units_of
from .sheet import ensure_xlsx, needs_relay, relay
from .icons import make_pixmap
from .theme import OFFICE, apply_office_theme
from .app import MainWindow
from .i18n import tr


def _active_run_closed(d):
    runs = d.get("runs")
    if not isinstance(runs, list) or not runs:
        return False
    # app opens newest run
    cur = runs[-1]
    if not isinstance(cur, dict):
        return False
    if "closed" in cur:
        return bool(cur.get("closed"))
    return bool(cur.get("issued"))    # issuing sealed it


def _pdf_status(pdf):
    n = saved = 0
    bad = closed = False
    sp = qc_path(pdf, "_bubbles.json")
    if os.path.isfile(sp):
        try:
            with open(sp, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError("no ledger")
            ledger = ((d.get("project") or {}).get("rows")
                      if "project" in d else d.get("ledger"))
            if not isinstance(ledger, list):
                raise ValueError("no ledger")
            n = len(ledger)
            saved = sum(1 for r in ledger
                        if isinstance(r, dict)
                        and r.get("sheet_row") is not None)
            closed = _active_run_closed(d)
        except Exception:
            bad = True
    return (n, saved, os.path.isfile(qc_path(pdf, "_Inspection.xlsx")),
            bad, closed)


def _mtime_text(pdf):
    try:
        t = datetime.datetime.fromtimestamp(os.path.getmtime(pdf))
    except OSError:
        return "-"
    return t.strftime("%Y-%m-%d %H:%M")


def _size_text(pdf):
    try:
        kb = os.path.getsize(pdf) / 1024.0
    except OSError:
        return ""
    return "%.1f MB" % (kb / 1024.0) if kb >= 1024 else "%d kB" % round(kb)


def _session_lock_msg(pdf, subdir):
    from .store import BubbleStore, session_lock_text
    path = qc_path(pdf, "_bubbles.json", subdir=subdir)
    if not os.path.isfile(path):
        return ""
    st = BubbleStore()
    st.load_session(path)
    return session_lock_text(st)


RECENT_MAX = 30
_THUMB_W, _THUMB_H = 64, 88


def _pdf_thumb(pdf, w=_THUMB_W, h=_THUMB_H):
    """Best-effort first-page thumbnail so damage cannot break row."""
    try:
        import fitz
        doc = fitz.open(pdf)
        try:
            page = doc[0]
            r = page.rect
            scale = min(w / r.width, h / r.height) if r.width and r.height \
                else 1.0
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            data = bytes(pix.samples)   # outlive QImage
            img = QImage(data, pix.width, pix.height, pix.stride,
                         QImage.Format_RGB888)
            return QPixmap.fromImage(img.copy())
        finally:
            doc.close()
    except Exception:
        return None


def _step_thumb(pdf, cfg):
    if not cfg:
        return None
    try:
        from .steppreview import single_image
        img = single_image(cfg, pdf, size=_THUMB_H)
        if img is None:
            return None
        img = img.convert("RGB")
        q = QImage(img.tobytes(), img.width, img.height, img.width * 3,
                   QImage.Format_RGB888)
        pm = QPixmap.fromImage(q.copy())
        return pm.scaled(_THUMB_W, _THUMB_H, Qt.KeepAspectRatio,
                         Qt.SmoothTransformation)
    except Exception:
        return None


def _recent_row_widget(pdf, cfg=None):
    n, saved, has_sheet, bad, closed = _pdf_status(pdf)
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(10, 6, 10, 6)
    row.setSpacing(10)

    thumb = QLabel()
    thumb.setFixedSize(_THUMB_W, _THUMB_H)
    thumb.setAlignment(Qt.AlignCenter)
    thumb.setStyleSheet("border:1px solid %s; background:white;"
                        % OFFICE["muted"])
    pm = _step_thumb(pdf, cfg) or _pdf_thumb(pdf)
    if pm is not None:
        thumb.setPixmap(pm)
    row.addWidget(thumb, 0, Qt.AlignVCenter)

    txt = QWidget()
    tv = QVBoxLayout(txt)
    tv.setContentsMargins(0, 0, 0, 0)
    tv.setSpacing(1)
    name = QLabel(os.path.basename(pdf))
    name.setStyleSheet("font-weight:bold; font-size:10pt; color:%s;"
                       % OFFICE["text"])
    folder = QLabel(os.path.dirname(pdf) or "-")
    folder.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["muted"])
    meta = QLabel("%s %s   %s" % (tr('modified'), _mtime_text(pdf),
                                  _size_text(pdf)))
    meta.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["muted"])
    tv.addWidget(name)
    tv.addWidget(folder)
    tv.addWidget(meta)
    row.addWidget(txt, 1)

    if bad:
        label = tr('session file damaged')
        chip_bg, chip_fg, chip_bd = "#fbe3e3", "#a11", "#e3a2a2"
    elif n:
        unsaved = n - saved
        label = (tr('%d bubble') if n == 1 else tr('%d bubbles')) % n
        if unsaved:
            label += " - " + tr('%d unsaved') % unsaved
        chip_bg, chip_fg, chip_bd = "#dbe7f8", OFFICE["accent"], "#9bbce6"
    else:
        label = tr('no bubbles yet')
        chip_bg, chip_fg, chip_bd = "#e6eaf1", OFFICE["muted"], "#cdd5e2"
    chip = QLabel(label)
    chip.setStyleSheet(
        "background:%s; color:%s; border:1px solid %s; border-radius:9px;"
        "padding:2px 10px; font-size:8pt; font-weight:bold;"
        % (chip_bg, chip_fg, chip_bd))
    row.addWidget(chip, 0, Qt.AlignVCenter)

    if closed:
        seal = QLabel(tr('closed out'))
        seal.setStyleSheet(
            "background:#e4efe4; color:%s; border:1px solid #a9c9a9;"
            "border-radius:9px; padding:2px 10px; font-size:8pt;"
            "font-weight:bold;" % OFFICE["green"])
        row.addWidget(seal, 0, Qt.AlignVCenter)

    if has_sheet:
        sheet_ic = QLabel()
        sheet_ic.setPixmap(make_pixmap("check", color=OFFICE["green"], px=12))
        row.addWidget(sheet_ic, 0, Qt.AlignVCenter)
        sheet = QLabel(tr('sheet'))
        sheet.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["green"])
    else:
        sheet = QLabel(tr('no sheet'))
        sheet.setStyleSheet("font-size:8pt; color:%s;" % OFFICE["muted"])
    row.addWidget(sheet, 0, Qt.AlignVCenter)
    w.setToolTip(pdf)
    return w


def _pdf_from_drop(mime):
    if not mime.hasUrls():
        return ""
    for u in mime.urls():
        p = u.toLocalFile()
        if p.lower().endswith(".pdf") and os.path.isfile(p):
            return p
    return ""


class _DropDialog(QDialog):
    dropped = ""

    def dragEnterEvent(self, e):
        if _pdf_from_drop(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        p = _pdf_from_drop(e.mimeData())
        if p:
            self.dropped = p
            self.accept()


DLG_MIN = (620, 360)


def _dlg_size(cfg):
    try:
        w, h = (int(v) for v in (cfg.get("open_dlg_size") or [])[:2])
    except (TypeError, ValueError):
        w = h = 0
    if w < DLG_MIN[0] or h < DLG_MIN[1]:
        return tuple(CFG_DEFAULT["open_dlg_size"])
    return min(w, 2400), min(h, 1600)


def _pick_pdf(cfg):
    initdir = cfg.get("last_dir") or os.path.expanduser("~")
    recent = [p for p in (cfg.get("recent") or []) if os.path.isfile(p)]
    if not recent:
        path, _ = QFileDialog.getOpenFileName(
            None, tr('PDF print'), initdir, "PDF (*.pdf)")
        return path
    dlg = _DropDialog()
    dlg.setAcceptDrops(True)
    dlg.setWindowTitle(tr('%s - open') % APP_NAME)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)

    title = QLabel(tr('Open a drawing'))
    title.setStyleSheet("font-size:14pt; font-weight:bold; color:%s;"
                        % OFFICE["text"])
    lay.addWidget(title)
    sub = QLabel(tr("Pick a recent drawing or browse for a PDF. The chip shows "
                    "its bubble count."))
    sub.setStyleSheet("color:%s; font-size:9pt;" % OFFICE["muted"])
    sub.setWordWrap(True)
    lay.addWidget(sub)

    lst = QListWidget()
    lst.setAlternatingRowColors(True)
    lst.setIconSize(QSize(0, 0))
    for p in recent[:RECENT_MAX]:
        it = QListWidgetItem()
        rw = _recent_row_widget(p, cfg)
        it.setSizeHint(rw.sizeHint())
        it.setData(Qt.UserRole, p)
        lst.addItem(it)
        lst.setItemWidget(it, rw)
    lst.setCurrentRow(0)
    lst.setMinimumHeight(420)
    lay.addWidget(lst)
    sel = {"path": ""}

    def use():
        it = lst.currentItem()
        if it:
            sel["path"] = it.data(Qt.UserRole)
        dlg.accept()

    def browse():
        p, _ = QFileDialog.getOpenFileName(
            dlg, tr('PDF print'), initdir, "PDF (*.pdf)")
        if p:
            sel["path"] = p
            dlg.accept()

    lst.itemDoubleClicked.connect(lambda _i: use())
    bw = QWidget()
    bl = QHBoxLayout(bw)
    bl.setContentsMargins(0, 0, 0, 0)
    b_browse = QPushButton(tr('Browse...'))
    b_browse.clicked.connect(browse)
    b_cancel = QPushButton(tr('Cancel'))
    b_cancel.clicked.connect(dlg.reject)
    b_open = QPushButton(tr('Open'))
    b_open.clicked.connect(use)
    b_open.setDefault(True)
    bl.addWidget(b_browse)
    bl.addStretch(1)
    bl.addWidget(b_cancel)
    bl.addWidget(b_open)
    lay.addWidget(bw)
    dlg.resize(*_dlg_size(cfg))
    dlg.exec()
    sz = dlg.size()
    want = [int(sz.width()), int(sz.height())]
    if want != list(cfg.get("open_dlg_size") or []):
        cfg["open_dlg_size"] = want
        save_cfg(cfg)
    return dlg.dropped or sel["path"]


def _selftest():
    from .reader.vision import runtime
    av = runtime.available({})
    need = ("geometry", "ocr", "symbols", "region")
    for k in ("geometry", "ocr", "symbols", "region", "vlm"):
        print("%-9s %s" % (k, "ok" if av.get(k) else "MISSING"))
    for msg in (av.get("reasons") or {}).values():
        print("  ! " + msg)
    missing = [k for k in need if not av.get(k)]
    phones = runtime.telemetry_builds()
    for p in phones:
        print("  ! onnxruntime with Microsoft telemetry: " + p)
    if phones:
        missing.append("offline (pin onnxruntime <1.28)")
    if missing:
        print("selftest FAILED: " + ", ".join(missing))
        return 1
    print("selftest OK")
    return 0


def _offer_relay(xlsx, cfg):
    try:
        if not needs_relay(xlsx):
            return
    except Exception:
        return
    ans = QMessageBox.question(
        None, tr('Inspection sheet'),
        tr('%s was made by an older Bubbler.\n\nRebuild it on the current '
           'sheet? Your title block and measurements are kept, and a copy '
           'is saved next to it. Rows or columns you added, and custom '
           'formatting, are NOT kept.')
        % os.path.basename(xlsx),
        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
    if ans != QMessageBox.Yes:
        return
    try:
        relay(xlsx, sheet_lang=cfg.get("sheet_lang", "both"),
              company=str(cfg.get("company") or ""), units=units_of(cfg))
    except Exception as e:
        QMessageBox.warning(None, tr('Inspection sheet'),
                            tr('Rebuild failed: %s') % e)


def _offer_gpu(cfg, win):
    if cfg.get("gpu_hint_off"):
        return
    try:
        from . import gpu
        from .reader.vision import runtime
        if not gpu.is_linux() or gpu.is_installed():
            return
        if not cfg.get("vision_gpu", True):
            return                          # off on purpose
        if runtime._providers(cfg)[0] != "CPUExecutionProvider":
            return
        ver = gpu.driver_version()
        if ver is None or ver < gpu.MIN_DRIVER:
            return
    except Exception:
        return
    box = QMessageBox(win)
    box.setIcon(QMessageBox.Information)
    box.setWindowTitle(tr('GPU'))
    box.setText(tr('This computer has an NVIDIA card (driver %d) but Bubbler '
                   'reads drawings on the CPU.') % ver)
    box.setInformativeText(
        tr('The GPU pack installs separately to keep the download small. '
           'It speeds up detectors only; text reading is unchanged.\n\n'
           'Settings > Vision > Install or update GPU pack.'))
    go = box.addButton(tr('Open Settings'), QMessageBox.AcceptRole)
    box.addButton(tr('Not now'), QMessageBox.RejectRole)
    never = box.addButton(tr('Do not show this again'),
                          QMessageBox.DestructiveRole)
    box.setDefaultButton(go)
    box.exec()
    hit = box.clickedButton()
    if hit is never:
        cfg["gpu_hint_off"] = True
        save_cfg(cfg)
    elif hit is go:
        win.settings()


# one window per drawing, else last writer wins
_WINDOWS = {}


def _win_key(pdf, cfg=None):
    """Sidecar path keys drawing. Spellings share it."""
    sub = (cfg or {}).get("qc_subdir", "qc")
    return os.path.normcase(os.path.realpath(
        qc_path(pdf, "_bubbles.json", subdir=sub)))


def open_drawing(pdf, cfg, xlsx=None, parent=None):
    key = _win_key(pdf, cfg)
    old = _WINDOWS.get(key)
    try:
        alive = old is not None and old.isVisible()
    except RuntimeError:                 # C++ side gone
        alive = False
    if alive:
        if old.isMinimized():
            old.showNormal()              # keeps maximized
        old.raise_()
        old.activateWindow()
        return old
    _WINDOWS.pop(key, None)
    try:
        import fitz
        fitz.open(pdf).close()
    except Exception as e:
        QMessageBox.critical(parent, tr('Open drawing'),
                             tr('Could not open %s:\n%s')
                             % (os.path.basename(pdf), e))
        return None
    sub = cfg.get("qc_subdir", "qc")
    xlsx = xlsx or qc_path(pdf, "_Inspection.xlsx", subdir=sub)
    lock = _session_lock_msg(pdf, sub)
    if lock and not os.path.isfile(xlsx):
        QMessageBox.critical(parent, tr('Session'), lock)
        return None
    d = os.path.dirname(xlsx)
    if d and not os.path.isdir(d):
        try:
            os.makedirs(d, exist_ok=True)
        except PermissionError:
            xlsx = qc_path(pdf, "_Inspection.xlsx", subdir="")
    try:
        created = ensure_xlsx(xlsx, str(cfg.get("company") or ""),
                              sheet_lang=cfg.get("sheet_lang", "both"),
                              units=units_of(cfg))
    except RuntimeError as e:
        QMessageBox.critical(parent, tr('Template'), str(e))
        xlsx, _ = QFileDialog.getOpenFileName(
            parent, tr('Inspection sheet'),
            os.path.dirname(pdf), "Excel (*.xlsx)")
        if not xlsx:
            return None
        created = False
    if not created:
        _offer_relay(xlsx, cfg)
    cfg["last_dir"] = os.path.dirname(pdf)
    rec = [pdf] + [p for p in (cfg.get("recent") or []) if p != pdf]
    cfg["recent"] = rec[:RECENT_MAX]
    save_cfg(cfg)
    win = MainWindow(pdf, xlsx, cfg=cfg)
    # registry holds window
    win.setAttribute(Qt.WA_DeleteOnClose, True)
    _WINDOWS[key] = win
    def _forget(_o=None, k=key, w=win):
        # this window only. Newer one survives
        if _WINDOWS.get(k) is w:
            _WINDOWS.pop(k, None)
    win.destroyed.connect(_forget)
    win.show()
    if created:
        win.set_status(tr('created: %s') % os.path.basename(xlsx))
    return win


def open_new_window(cfg, parent=None):
    pdf = _pick_pdf(cfg)
    if pdf:
        return open_drawing(pdf, cfg, parent=parent)
    return None


def main():
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    cfg = load_cfg()
    app = QApplication(sys.argv)
    apply_office_theme(app)
    pdf = sys.argv[1] if len(sys.argv) > 1 else _pick_pdf(cfg)
    if not pdf:
        sys.exit("No PDF.")
    # CLI workbook first window only
    win = open_drawing(pdf, cfg,
                       xlsx=sys.argv[2] if len(sys.argv) > 2 else None)
    if win is None:
        sys.exit("No drawing opened.")
    _offer_gpu(cfg, win)
    _offer_step(cfg, pdf, win)
    sys.exit(app.exec())


def _offer_step(cfg, pdf, parent=None):
    from .steppreview import should_ask, set_choice, decline
    if not should_ask(cfg, pdf):
        return
    r = QMessageBox.question(
        parent, tr('3D preview'),
        tr('Show a 3D STEP preview instead of the PDF page?'),
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if r != QMessageBox.Yes:
        decline(cfg, pdf)
        save_cfg(cfg)
        return
    start = os.path.dirname(pdf) or os.path.expanduser("~")
    sp, _ = QFileDialog.getOpenFileName(
        parent, tr('STEP file'), start,
        "STEP (*.step *.stp *.STEP *.STP)")
    if not sp:
        decline(cfg, pdf)
        save_cfg(cfg)
        return
    from .stepdialog import StepChooseDialog
    dlg = StepChooseDialog(parent, sp)
    ch = dlg.result_choice() if dlg.exec() else None
    if ch:
        set_choice(cfg, pdf, sp, ch[0], ch[1])
    else:
        set_choice(cfg, pdf, sp)
    save_cfg(cfg)
