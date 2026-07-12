# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Measure-walk behaviour, mixed into MainWindow.

from datetime import datetime

from PySide6.QtCore import Qt, QTimer

from .calc import eval_measure, split_readings
from .common import (base_of, tol_text, limits_of, out_of_tol,
                     mirror_measured, measure_state, latest_op,
                     worst_reading, _NOGO_WORDS)
from .config import save_cfg
from .i18n import tr


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
            self._walk_uid = None
            self._readings = []
            self._walk_build()
            if not self._walk:
                self.measure_mode = False
                self.btn_measure.setChecked(False)
                self.set_status(tr('no bubbles to measure'))
                return
            self._mbar_dock.show()
            self._walk_idx = 0
            if self._skip_filled():
                for k, idx in enumerate(self._walk):
                    if not self.ledger[idx].get("ops"):
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
        # re-anchor by uid
        uid = getattr(self, "_walk_uid", None)
        if uid is not None:
            for k, i in enumerate(self._walk):
                if self.ledger[i].get("uid") == uid:
                    self._walk_idx = k
                    break

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
        self._walk_uid = d.get("uid")
        self._readings = []
        nom = ("" if d.get("nominal") is None
               else "   %.2f %s" % (d["nominal"], tol_text(d)))
        qn = int(d.get("qty") or 1)
        qtag = ("  ×%d" % qn) if qn > 1 else ""
        self.mlab.setText("#%s  %s%s%s" % (d["bubble"],
                                           d.get("feature", ""), qtag, nom))
        oot = self._walk_oot_count()
        self.mcount.setText("%d/%d   OOT %d"
                            % (self._walk_idx + 1, len(self._walk), oot))
        self._update_prev_label(d)
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

    def _measure_enter(self):
        """second Enter saves for math"""
        if not self._walk:
            return
        idx = self._walk[self._walk_idx]
        if idx >= len(self.ledger):
            self._walk_show()
            return
        d = self.ledger[idx]
        qty = int(d.get("qty") or 1)
        raw = self.ment.text()
        tokens = split_readings(raw)

        if len(tokens) > 1:
            self._readings = []
            self._walk_commit_readings(
                [self._resolve_token(t) for t in tokens], +1)
            return

        resolved, changed = eval_measure(raw)
        if changed and resolved != raw.strip():
            self.ment.setText(resolved)
            self.ment.selectAll()
            self.set_status(tr('= %s   (Enter again to save)') % resolved)
            return
        val = resolved

        if qty <= 1:
            self._readings = []
            self._walk_commit_readings([val] if val else [], +1)
            return

        acc = list(getattr(self, "_readings", None) or [])
        if val:
            acc.append(val)
        done = (not val or len(acc) >= qty
                or str(val).upper() in _NOGO_WORDS)
        if done:
            self._readings = []
            self._walk_commit_readings(acc, +1)
        else:
            self._readings = acc
            self.ment.clear()
            self.set_status(tr('reading %d/%d  (Enter next)') % (len(acc), qty))

    def _resolve_token(self, tok):
        resolved, _ = eval_measure(tok)
        return resolved

    def _walk_step(self, delta):
        if self._walk:
            self._readings = []
            self._walk_idx += delta
            self._walk_show()

    def _walk_commit(self, delta):
        if not self._walk:
            return
        idx = self._walk[self._walk_idx]
        if idx >= len(self.ledger):
            self._walk_show()
            return
        val, evaluated = eval_measure(self.ment.text())
        if evaluated:
            self.ment.setText(val)
        self._readings = []
        self._walk_commit_readings([val] if val else [], delta)

    def _walk_commit_readings(self, readings, delta):
        """Record readings on current row"""
        idx = self._walk[self._walk_idx]
        if idx >= len(self.ledger):
            self._walk_show()
            return
        d = self.ledger[idx]
        clean = [str(r).strip() for r in readings if str(r).strip() != ""]
        old = ("" if d.get("measured") in (None, "") else str(d["measured"]))
        new_worst = str(worst_reading(clean, d) or "")
        if new_worst != old:
            self.snapshot()
            self._record_op(d, clean)
            self._save_session()
            self.refresh_panel()
        extra = ""
        level = None
        worst = d.get("measured")
        if worst not in (None, ""):
            if out_of_tol(d):
                lim = limits_of(d)
                rng = ("%.4g-%.4g" % lim) if lim else ""
                extra = (tr('#%s OUT OF TOL %s')
                         % (d["bubble"], rng)).rstrip()
                level = "warn"
            else:
                extra = "#%s = %s" % (d["bubble"], worst)
                level = "check"
            self._measure_flash(level)
        nxt = self._next_walk_idx(delta)
        if nxt is None:
            # done: summarize, stay in measure mode so last verdict stays visible
            self.set_status(("%s   " % extra if extra else "")
                            + self._measure_summary(), icon=level)
            self._walk_show()
            return
        self._walk_idx = nxt
        self._walk_show()
        if extra:
            self.set_status(extra, icon=level)

    def _next_walk_idx(self, delta):
        """Next walk position"""
        n = len(self._walk)
        if self._skip_filled():
            i = self._walk_idx + delta
            while 0 <= i < n:
                if not self.ledger[self._walk[i]].get("ops"):
                    return i
                i += delta
            for k in range(n):
                if not self.ledger[self._walk[k]].get("ops"):
                    return k
            return None
        nx = self._walk_idx + delta
        return nx if 0 <= nx <= n - 1 else None

    def _walk_oot_count(self):
        return sum(1 for i in self._walk if i < len(self.ledger)
                   and measure_state(self.ledger[i]) in ("out", "nogo"))

    def _measure_summary(self):
        total = len(self._walk)
        filled = sum(1 for i in self._walk if i < len(self.ledger)
                     and self.ledger[i].get("ops"))
        return (tr('walk complete: %d/%d measured, %d out of tol')
                % (filled, total, self._walk_oot_count()))

    def _measure_flash(self, level):
        """Tint entry green in-tol / red out."""
        col = "#f8d7da" if level == "warn" else "#d4edda"
        self.ment.setStyleSheet("background:%s;" % col)
        QTimer.singleShot(400, lambda: self.ment.setStyleSheet(""))

    def _update_prev_label(self, d):
        lab = getattr(self, "mprev", None)
        if lab is None:
            return
        best = latest_op(d.get("ops") or {})
        if not best:
            lab.setText("")
            return
        op, rec = best
        g = rec.get("gage")
        lab.setText(tr('prev: %s') % rec.get("measured")
                    + (" (%s)" % g if g else ""))

    def _measure_clear(self):
        """Clear current op's reading, re-measure."""
        if not self._walk:
            return
        idx = self._walk[self._walk_idx]
        if idx >= len(self.ledger):
            return
        d = self.ledger[idx]
        self.snapshot()
        self._record_op_into(d, self._current_op(), "",
                             self.mgage_cb.currentText())
        self._save_session()
        self.refresh_panel()
        self.ment.clear()
        self.ment.setFocus()
        self._walk_show()

    def _mgage_changed(self, txt):
        if self._mbar_sync or not self._walk:
            return
        idx = self._walk[self._walk_idx]
        if idx < len(self.ledger):
            d = self.ledger[idx]
            d["gage"] = txt or None
            rec = d.get("ops", {}).get(self._current_op())
            if rec is not None:
                rec["gage"] = txt or None
            self._save_session()
            self.refresh_panel()

    def _measure_quick(self, val):
        if not self._walk:
            return
        self.ment.setText(val)
        self._walk_commit(+1)

    def _current_op(self):
        return getattr(self, "_measure_op", None) or "op1"

    def _skip_filled(self):
        return bool(self.cfg.get("measure_skip_filled", True))

    def _mop_changed(self, txt):
        self._measure_op = txt or "op1"

    def _mskip_toggled(self, on):
        self.cfg["measure_skip_filled"] = bool(on)
        save_cfg(self.cfg)

    def _record_op(self, d, val):
        self._record_op_into(d, self._current_op(), val,
                             self.mgage_cb.currentText())

    def _record_op_into(self, d, op, val, gage):
        vals = val if isinstance(val, (list, tuple)) else [val]
        readings = [str(v).strip() for v in vals if str(v).strip() != ""]
        ops = d.setdefault("ops", {})
        if readings:
            ops[op] = {"readings": readings,
                       "measured": worst_reading(readings, d),
                       "gage": gage or None,
                       "ts": datetime.now().isoformat(timespec="minutes")}
            mirror_measured(d)
        else:
            ops.pop(op, None)
            if ops:
                mirror_measured(d)
            else:
                d.pop("ops", None)
                d["measured"] = None

    def measure_bubble(self, basenum):
        if not self.measure_mode or not self._walk:
            return
        for k, idx in enumerate(self._walk):
            if idx < len(self.ledger) and \
                    base_of(self.ledger[idx]["bubble"]) == basenum:
                self._walk_idx = k
                self._walk_show()
                return
