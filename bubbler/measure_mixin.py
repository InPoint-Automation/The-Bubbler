# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Measure-walk behaviour mixed into MainWindow

from datetime import datetime

from PySide6.QtCore import Qt, QTimer

from .calc import eval_measure, split_readings
from .common import (base_of, tol_text, limits_of, out_of_tol,
                     mirror_measured, measure_state, op_value,
                     worst_reading, carried_forward, op_scope,
                     split_method_gage, method_for_gage, has_reading,
                     NOGO_WORDS)
from .config import (MEASURE_UNITS, measure_units, save_cfg, units_of,
                     ops_seq, register_op)
from .i18n import tr
from .units import (INCH, convert_units, format_converted,
                    format_nominal, other_units, unit_suffix)


def _num(txt):
    """Reading text -> float or None on GO/NOGO/junk."""
    try:
        return float(str(txt).replace(",", "."))
    except (TypeError, ValueError):
        return None


class MeasureMixin:
    def toggle_measure(self):
        self._set_measure(not self.measure_mode)

    def _set_measure(self, on):
        on = bool(on)
        if on and self._edit_blocked():   # sealed no walk
            try:
                self.btn_measure.setChecked(False)
            except Exception:
                pass
            self.measure_mode = False
            return
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
                    if self._needs_measuring(self.ledger[idx]):
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
               else "   %s %s" % (format_nominal(d["nominal"],
                                                 self._drawing_units()),
                                  tol_text(d)))
        alt = self._alt_readout(d)
        if alt:
            nom += "   [%s]" % alt
        qn = int(d.get("qty") or 1)
        qtag = ("  ×%d" % qn) if qn > 1 else ""
        self.mlab.setText("#%s  %s%s%s" % (d["bubble"],
                                           d.get("feature", ""), qtag, nom))
        oot = self._walk_oot_count()
        self.mcount.setText("%d/%d   OOT %d"
                            % (self._walk_idx + 1, len(self._walk), oot))
        self._update_prev_label(d)
        self._mbar_sync = True
        how = self._how_text(d)
        if how and self.mhow_cb.findText(how) < 0:
            self.mhow_cb.addItem(how)
        self.mhow_cb.setCurrentText(how)
        self._sync_plan(d)
        self._mbar_sync = False
        self._entry_echo = None
        here = self._reading_here(d)
        self.ment.setText("" if here in (None, "")
                          else self._entry_text(here))
        self.ment.setFocus()
        self.ment.selectAll()
        self._center_on(d)
        self.redraw_overlay()
        if self.panel_visible and idx < len(self.ledger):
            self._panel_highlight(idx, scroll=True)

    # ---- entry unit system ----

    def _fill_munits(self):
        """Both choices rebuilt so "other" never goes stale."""
        cb = getattr(self, "munits_cb", None)
        if cb is None:
            return
        drw = self._drawing_units()
        self._mbar_sync = True
        cb.clear()
        cb.addItem(tr('%s (drawing)') % unit_suffix(drw), "drawing")
        cb.addItem(unit_suffix(other_units(drw)), "other")
        self._mbar_sync = False
        self._sync_measure_units()

    def _entry_units(self):
        """Unit system inspector types in."""
        return measure_units(self.cfg, self.drawing)

    def _drawing_units(self):
        return units_of(self.cfg, self.drawing)

    def _set_measure_units(self, mode):
        """Pick entry system without rewriting stored readings."""
        if mode not in MEASURE_UNITS:
            return
        self.cfg["measure_units"] = mode
        save_cfg(self.cfg)
        self._sync_measure_units()
        if self.measure_mode:
            self._walk_show()

    def _sync_measure_units(self):
        """Label entry with system read in."""
        cb = getattr(self, "munits_cb", None)
        if cb is None:
            return
        self._mbar_sync = True
        cb.setCurrentIndex(
            1 if str(self.cfg.get("measure_units")) == "other" else 0)
        self._mbar_sync = False
        u = unit_suffix(self._entry_units())
        self.ment.setPlaceholderText(u)
        self.ment.setToolTip(tr('Type readings in %s') % u)

    def _munits_changed(self, _i=0):
        if self._mbar_sync:
            return
        cb = self.munits_cb
        self._set_measure_units(cb.currentData() or "drawing")

    def _to_drawing_units(self, txt):
        """Typed reading -> drawing units (GO/NOGO pass through)."""
        echo = getattr(self, "_entry_echo", None)
        if echo is not None and txt == echo[0]:
            return echo[1]
        src, dst = self._entry_units(), self._drawing_units()
        if src == dst:
            return txt
        v = _num(txt)
        if v is None:
            return txt
        return format_converted(convert_units(v, src, dst), dst)

    def _from_drawing_units(self, txt):
        """Stored reading -> entry units for field."""
        src, dst = self._drawing_units(), self._entry_units()
        if src == dst:
            return txt
        v = _num(txt)
        if v is None:
            return txt
        return format_converted(convert_units(v, src, dst), dst)

    def _entry_text(self, stored):
        """Field text for stored reading remembering exact pair."""
        txt = self._from_drawing_units(stored)
        self._entry_echo = (txt, str(stored))
        return txt

    def _alt_readout(self, d):
        """Same requirement in entry system or "" when matched."""
        src, dst = self._drawing_units(), self._entry_units()
        if src == dst:
            return ""
        fmt = "%.4f" if dst == INCH else "%.3f"
        lim = limits_of(d)
        if lim is not None:
            lo, hi = lim
            suf = unit_suffix(dst)
            if lo is None:           # open below
                return "<= %s %s" % (fmt % convert_units(hi, src, dst), suf)
            if hi is None:           # open above
                return ">= %s %s" % (fmt % convert_units(lo, src, dst), suf)
            return "%s-%s %s" % (fmt % convert_units(lo, src, dst),
                                 fmt % convert_units(hi, src, dst), suf)
        nom = d.get("nominal")
        if nom is None:
            return ""
        return "%s %s" % (fmt % convert_units(nom, src, dst),
                          unit_suffix(dst))

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
                or str(val).upper() in NOGO_WORDS)
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
        """Record readings on current row."""
        if self._edit_blocked():          # sealed refuse never absorb
            return
        idx = self._walk[self._walk_idx]
        if idx >= len(self.ledger):
            self._walk_show()
            return
        d = self.ledger[idx]
        clean = [self._to_drawing_units(str(r).strip())
                 for r in readings if str(r).strip() != ""]
        here = self._reading_here(d)      # stage reading now
        old = "" if here in (None, "") else str(here)
        new_worst = str(worst_reading(clean, d) or "")
        if new_worst != old:
            self.snapshot()
            self._record_op(d, clean)
            self._save_session()
            self.refresh_panel()
        extra = ""
        level = None
        worst = self._reading_here(d)     # no verdict if unread
        if worst not in (None, ""):
            if out_of_tol(dict(d, measured=worst)):
                lim = limits_of(d)
                if not lim:
                    rng = ""
                elif lim[0] is None:
                    rng = "<=%.4g" % lim[1]
                elif lim[1] is None:
                    rng = ">=%.4g" % lim[0]
                else:
                    rng = "%.4g-%.4g" % lim
                extra = (tr('#%s OUT OF TOL %s')
                         % (d["bubble"], rng)).rstrip()
                level = "warn"
            else:
                # name unit when converted
                u = ("" if self._entry_units() == self._drawing_units()
                     else " " + unit_suffix(self._drawing_units()))
                extra = "#%s = %s%s" % (d["bubble"], worst, u)
                level = "check"
            self._measure_flash(level)
        nxt = self._next_walk_idx(delta)
        if nxt is None:
            # stay verdict stays visible
            self.set_status(("%s   " % extra if extra else "")
                            + self._measure_summary(), icon=level)
            self._walk_show()
            return
        self._walk_idx = nxt
        self._walk_show()
        if extra:
            self.set_status(extra, icon=level)

    def _next_walk_idx(self, delta):
        """Next walk position."""
        n = len(self._walk)
        if self._skip_filled():
            i = self._walk_idx + delta
            while 0 <= i < n:
                if self._needs_measuring(self.ledger[self._walk[i]]):
                    return i
                i += delta
            for k in range(n):
                if self._needs_measuring(self.ledger[self._walk[k]]):
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
                     and not self._needs_measuring(self.ledger[i]))
        return (tr('walk complete: %d/%d measured, %d out of tol')
                % (filled, total, self._walk_oot_count()))

    def _measure_flash(self, level):
        """Tint entry green in-tol / red out."""
        col = "#f8d7da" if level == "warn" else "#d4edda"
        self.ment.setStyleSheet("background:%s;" % col)
        QTimer.singleShot(400, lambda: self.ment.setStyleSheet(""))

    def _update_prev_label(self, d):
        """Op reading or carry-forward known here."""
        lab = getattr(self, "mprev", None)
        if lab is None:
            return
        seq = self._op_seq()
        cur = self._current_op()
        st = op_scope(d, cur, seq)
        if st == "future":
            lab.setText(tr('not made until %s') % (d.get("made_at") or ""))
            return
        rec = (d.get("ops") or {}).get(cur)
        if has_reading(rec):
            g = (rec or {}).get("gage") or (rec or {}).get("method")
            lab.setText(tr('prev: %s') % (rec or {}).get("measured")
                        + (" (%s)" % g if g else ""))
            return
        prev = carried_forward(d, cur, seq)
        if prev is None:
            lab.setText("")
            return
        if st == "carried":
            lab.setText(tr('carried forward from %s: %s') % (prev[0], prev[1]))
        else:
            lab.setText(tr('re-measure: was %s at %s') % (prev[1], prev[0]))

    def _reading_here(self, d):
        """Op own reading only."""
        rec = (d.get("ops") or {}).get(self._current_op())
        return op_value(rec, d) if has_reading(rec) else None

    def _measure_clear(self):
        """Clear current op reading for re-measure."""
        if not self._walk:
            return
        idx = self._walk[self._walk_idx]
        if idx >= len(self.ledger):
            return
        if self._edit_blocked():          # sealed refuse never absorb
            return
        d = self.ledger[idx]
        self.snapshot()
        self._record_op_into(d, self._current_op(), "",
                             *self._how_now(d))
        self._save_session()
        self.refresh_panel()
        self.ment.clear()
        self.ment.setFocus()
        self._walk_show()

    # ---- one control for how measurement taken ----

    def _how_text(self, d):
        """How-combo shows op record else gage."""
        rec = (d.get("ops") or {}).get(self._current_op()) or {}
        return rec.get("gage") or rec.get("method") or d.get("gage") or ""

    def _how_now(self, d=None):
        """(gage, method) bar set to now."""
        cb = getattr(self, "mhow_cb", None)
        txt = cb.currentText() if cb is not None else ""
        method, gage = split_method_gage(txt, (d or {}).get("gage"))
        return (gage, method or method_for_gage(gage))

    def _mhow_changed(self, txt):
        if self._mbar_sync or not self._walk:
            return
        if self._edit_blocked():          # sealed refuse never absorb
            return
        idx = self._walk[self._walk_idx]
        if idx < len(self.ledger):
            d = self.ledger[idx]
            gage, method = self._how_now(d)
            if gage:
                d["gage"] = gage
            rec = d.get("ops", {}).get(self._current_op())
            if rec is not None:
                rec["gage"] = gage or None
                rec["method"] = method or None
            self._save_session()
            self.refresh_panel()

    # ---- per-characteristic plan ----

    def _sync_plan(self, d):
        """Show row made_at / recheck on bar."""
        cb = getattr(self, "mmade_cb", None)
        if cb is not None:
            want = str(d.get("made_at") or "")
            i = cb.findData(want)
            cb.setCurrentIndex(i if i >= 0 else 0)
        chk = getattr(self, "mrecheck_cb", None)
        if chk is not None:
            chk.setChecked(bool(d.get("recheck")))

    def _walk_row(self):
        if not self._walk:
            return None
        idx = self._walk[self._walk_idx]
        return self.ledger[idx] if idx < len(self.ledger) else None

    def _mmade_changed(self, _i=0):
        if self._mbar_sync:
            return
        d = self._walk_row()
        if d is None or self._edit_blocked():
            return
        val = self.mmade_cb.currentData() or ""
        d["made_at"] = val or None
        if val:
            register_op(val, self.cfg, self.drawing)
        self._save_session()
        self.refresh_panel()
        self._update_prev_label(d)

    def _mrecheck_toggled(self, on):
        if self._mbar_sync:
            return
        d = self._walk_row()
        if d is None or self._edit_blocked():
            return
        d["recheck"] = bool(on)
        self._save_session()
        self.refresh_panel()
        self._update_prev_label(d)

    def _measure_quick(self, val):
        if not self._walk:
            return
        self.ment.setText(val)
        self._walk_commit(+1)

    def _current_op(self):
        return getattr(self, "_measure_op", None) or self._op_seq()[0]

    def _op_seq(self):
        """Drawing machining sequence in order."""
        return ops_seq(self.cfg, getattr(self, "drawing", None))

    def _skip_filled(self):
        return bool(self.cfg.get("measure_skip_filled", True))

    def _needs_measuring(self, d):
        """In scope for op and unread here."""
        cur = self._current_op()
        if not op_scope(d, cur, self._op_seq()) in ("machined", "recheck",
                                                    "new"):
            return False
        return not has_reading((d.get("ops") or {}).get(cur))

    def _mop_changed(self, txt):
        """Switch inspected STAGE so scope follows."""
        self._measure_op = txt or self._op_seq()[0]
        if txt:
            register_op(txt, self.cfg, getattr(self, "drawing", None))
        if getattr(self, "measure_mode", False) and self._walk:
            self._walk_show()

    def _mskip_toggled(self, on):
        self.cfg["measure_skip_filled"] = bool(on)
        save_cfg(self.cfg)

    def _record_op(self, d, val):
        gage, method = self._how_now(d)
        self._record_op_into(d, self._current_op(), val, gage, method)

    def _record_op_into(self, d, op, val, gage, method=None):
        """One measurement record of readings method gage op ts."""
        vals = val if isinstance(val, (list, tuple)) else [val]
        readings = [str(v).strip() for v in vals if str(v).strip() != ""]
        seq = register_op(op, self.cfg, getattr(self, "drawing", None))
        ops = d.setdefault("ops", {})
        if readings:
            if method is None:
                method = method_for_gage(gage)
            ops[op] = {"readings": readings,
                       "measured": worst_reading(readings, d),
                       "method": method or None,
                       "gage": gage or None,
                       "ts": datetime.now().isoformat(timespec="minutes")}
            mirror_measured(d, seq)
        else:
            ops.pop(op, None)
            if ops:
                mirror_measured(d, seq)
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
