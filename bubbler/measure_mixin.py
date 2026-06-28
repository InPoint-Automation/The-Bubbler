# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Measure-walk behaviour, mixed into MainWindow.

from PySide6.QtCore import Qt

from .common import base_of, tol_text, limits_of, out_of_tol


class MeasureMixin:
    def toggle_measure(self):
        self._set_measure(not self.measure_mode)

    def _set_measure(self, on):
        on = bool(on)
        self.measure_mode = on
        try:
            self.btn_measure.setChecked(on)
        except Exception:
            pass
        self.view.setCursor(Qt.UpArrowCursor if on else
                            (Qt.ArrowCursor if self.tool == "select"
                             else Qt.CrossCursor))
        if on:
            self._walk_build()
            if not self._walk:
                self.measure_mode = False
                self.btn_measure.setChecked(False)
                self.set_status("no bubbles to measure / brak bąbli")
                return
            self._mbar_dock.show()
            self._walk_idx = 0
            for k, idx in enumerate(self._walk):
                if self.ledger[idx].get("measured") in (None, ""):
                    self._walk_idx = k
                    break
            self._walk_show()
        else:
            self._mbar_dock.hide()
            self.redraw_overlay()
            self.set_status()

    def _walk_build(self):
        def key(i):
            b = str(self.ledger[i].get("bubble") or "0")
            return (base_of(b), b)
        self._walk = sorted(range(len(self.ledger)), key=key)

    def _walk_show(self):
        if not self._walk:
            return
        self._walk_idx = max(0, min(self._walk_idx, len(self._walk) - 1))
        idx = self._walk[self._walk_idx]
        if idx >= len(self.ledger):
            self._walk_build()
            if not self._walk:
                self._set_measure(False)
                return
            self._walk_idx = min(self._walk_idx, len(self._walk) - 1)
            idx = self._walk[self._walk_idx]
        d = self.ledger[idx]
        nom = ("" if d.get("nominal") is None
               else "   %.2f %s" % (d["nominal"], tol_text(d)))
        self.mlab.setText("#%s  %s%s" % (d["bubble"],
                                         d.get("feature", ""), nom))
        self.mcount.setText("%d/%d" % (self._walk_idx + 1, len(self._walk)))
        self._mbar_sync = True
        g = d.get("gage") or ""
        if g and self.mgage_cb.findText(g) < 0:
            self.mgage_cb.addItem(g)
        self.mgage_cb.setCurrentText(g)
        self._mbar_sync = False
        self.ment.setText("" if d.get("measured") in (None, "")
                          else str(d["measured"]))
        self.ment.setFocus()
        self.ment.selectAll()
        self._center_on(d)
        self.redraw_overlay()
        if self.panel_visible and idx < len(self.ledger):
            self._panel_highlight(idx, scroll=True)

    def _center_on(self, d):
        if d.get("page") != self.page_i:
            self.page_i = d.get("page", 0)
            self.render()
        bx, by = d.get("bx", d["x"]), d.get("by", d["y"])
        self.view.centerOn(self._scr(bx, by))

    def _walk_step(self, delta):
        if self._walk:
            self._walk_idx += delta
            self._walk_show()

    def _walk_commit(self, delta):
        if not self._walk:
            return
        idx = self._walk[self._walk_idx]
        if idx >= len(self.ledger):
            self._walk_show()
            return
        d = self.ledger[idx]
        val = self.ment.text().strip()
        old = ("" if d.get("measured") in (None, "") else str(d["measured"]))
        if val != old:
            self.snapshot()
            d["measured"] = val or None
            self._save_session()
            self.refresh_panel()
        extra = ""
        level = None
        if val:
            if out_of_tol(d):
                lim = limits_of(d)
                rng = ("%.4g-%.4g" % lim) if lim else ""
                extra = "#%s OUT OF TOL / poza tolerancją %s" \
                        % (d["bubble"], rng)
                level = "warn"
            else:
                extra = "#%s = %s" % (d["bubble"], val)
                level = "check"
        if self._walk_idx + delta > len(self._walk) - 1:
            nxt = [k for k, i2 in enumerate(self._walk)
                   if self.ledger[i2].get("measured") in (None, "")]
            if nxt:
                self._walk_idx = nxt[0]
                self._walk_show()
            else:
                self.set_status(("%s   " % extra if extra else "") +
                                "measure walk complete / pomiar zakończony",
                                icon=level)
                self._set_measure(False)
                return
        else:
            self._walk_idx += delta
            self._walk_show()
        if extra:
            self.set_status(extra, icon=level)

    def _mgage_changed(self, txt):
        # live gage override mid-walk
        if self._mbar_sync or not self._walk:
            return
        idx = self._walk[self._walk_idx]
        if idx < len(self.ledger):
            self.ledger[idx]["gage"] = txt or None
            self._save_session()
            self.refresh_panel()

    def _measure_quick(self, val):
        # GO / NOGO one-click
        if not self._walk:
            return
        self.ment.setText(val)
        self._walk_commit(+1)

    def measure_bubble(self, basenum):
        if not self.measure_mode or not self._walk:
            return
        for k, idx in enumerate(self._walk):
            if idx < len(self.ledger) and \
                    base_of(self.ledger[idx]["bubble"]) == basenum:
                self._walk_idx = k
                self._walk_show()
                return
