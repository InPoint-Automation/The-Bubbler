# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# "What's available" tab drawing capability rows

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QLabel, QPushButton, QFrame, QSizePolicy)

from . import capabilities as caps
from .i18n import tr

_COLORS = {caps.OK: "#1a7f37", caps.OFF: "#777777",
           caps.NA: "#9a6700", caps.WARN: "#b42318"}


class _Sig(QObject):
    done = Signal(object)


class _ProbeTask(QRunnable):
    """Off-thread probe"""

    def __init__(self, cfg, sig):
        super().__init__()
        self._cfg = dict(cfg or {})
        self._sig = sig

    def run(self):
        try:
            rows = caps.probe(self._cfg)
        except Exception as e:                          # pragma: no cover
            rows = [{"key": "probe", "label": tr('Check failed'),
                     "state": caps.NA, "detail": str(e), "fix": ""}]
        self._sig.done.emit(rows)


class StatusPanel(QWidget):
    """One row per capability"""

    def __init__(self, cfg, parent=None, auto=True):
        super().__init__(parent)
        self.cfg = dict(cfg or {})
        self._sig = _Sig()
        self._sig.done.connect(self._show_rows)
        lay = QVBoxLayout(self)
        intro = QLabel(tr('What Bubbler can do on this computer. Unavailable '
                          'features are skipped quietly, so check here first '
                          'if a scan finds nothing.'))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setColumnStretch(1, 1)
        self._grid.setContentsMargins(0, 6, 0, 6)
        # else clips bottom row
        pol = self._grid_host.sizePolicy()
        pol.setHeightForWidth(True)
        pol.setVerticalPolicy(QSizePolicy.MinimumExpanding)
        self._grid_host.setSizePolicy(pol)
        lay.addWidget(self._grid_host)
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        self._btn = QPushButton(tr('Re-check'))
        self._btn.clicked.connect(self.start)
        bl.addWidget(self._btn)
        bl.addStretch(1)
        lay.addWidget(bar)
        lay.addStretch(1)
        self._auto = bool(auto)
        cached = caps.cached()
        if cached is not None:
            self._auto = False
            self._show_rows(cached)
        else:
            self._show_busy()

    # ------------------------------------------------------------ drawing

    def rows(self):
        return list(getattr(self, "_rows", []))

    def texts(self):
        """Every line drawn for tests"""
        out = []
        for r in self.rows():
            out.append("%s: %s %s %s" % (r["label"],
                                         caps.state_label(r["state"]),
                                         r["detail"], r.get("fix", "")))
        return out

    def start(self):
        """Kick fresh probe off-thread"""
        self._btn.setEnabled(False)
        self._show_busy()
        QThreadPool.globalInstance().start(_ProbeTask(self.cfg, self._sig))

    def _sync_height(self):
        """Word-wrap height grid sizeHint misses"""
        w = self._grid_host.width() or self.width()
        if w > 1:
            h = self._grid.heightForWidth(w)
            if h > 0:
                self._grid_host.setMinimumHeight(h)

    def showEvent(self, ev):
        """Probe on first show not on build"""
        super().showEvent(ev)
        if self._auto:
            self._auto = False
            self.start()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._sync_height()

    def _clear(self):
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)

    def _show_busy(self):
        self._rows = []
        self._clear()
        lab = QLabel(tr('Checking what is available...'))
        lab.setProperty("i18n_skip", True)
        self._grid.addWidget(lab, 0, 0, 1, 2)

    def _show_rows(self, rows):
        self._rows = list(rows or [])
        self._clear()
        r = 0
        for row in self._rows:
            name = QLabel(row["label"])
            name.setProperty("i18n_skip", True)     # already translated
            name.setStyleSheet("font-weight:bold;")
            name.setWordWrap(True)
            self._grid.addWidget(name, r, 0, Qt.AlignTop)
            st = QLabel(caps.state_label(row["state"]))
            st.setProperty("i18n_skip", True)
            st.setStyleSheet("font-weight:bold; color:%s;"
                             % _COLORS.get(row["state"], "#333333"))
            self._grid.addWidget(st, r, 1, Qt.AlignTop | Qt.AlignRight)
            r += 1
            # embedded newline clips
            lines = [row["detail"]]
            if row.get("fix"):
                lines.append(tr('What to do: %s') % row["fix"])
            for text in lines:
                det = QLabel(text)
                det.setProperty("i18n_skip", True)
                det.setWordWrap(True)
                det.setStyleSheet("color:#555555;")
                self._grid.addWidget(det, r, 0, 1, 2)
                r += 1
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("color:#dddddd;")
            self._grid.addWidget(line, r, 0, 1, 2)
            r += 1
        self._btn.setEnabled(True)
        self._sync_height()
