# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble ledger, uid counter, session JSON.

import copy
import uuid
import json
import os
import sys
from datetime import datetime

from .numbering import (ordered_uids, renumber, next_bubble_number,
                        set_number, remove_bubble, migrate_uids)

SESSION_VERSION = 3

# migrations survive two bumps
MIN_SESSION_VERSION = SESSION_VERSION - 2

RUN_FIELDS = ("measured", "ops", "gage", "comment")


class SessionReadOnly(RuntimeError):
    """Save over session load refused."""


class RunClosed(SessionReadOnly):
    """Save over run closed out."""


def _warn(msg):
    line = "bubbler.store: %s" % msg
    print(line, file=sys.stderr)
    try:
        logp = os.path.join(os.path.expanduser("~"), ".bubbler.log")
        with open(logp, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _migrate_v1(ledger):
    """v1 -> v2: dual types, retired group, attr type, bare measured."""
    ts = datetime.now().isoformat(timespec="minutes")
    for r in ledger:
        _t = r.get("type")
        if isinstance(_t, str) and " / " in _t:
            r["type"] = _t.split(" / ", 1)[0]
        _g = r.pop("group", None)
        if isinstance(_g, str) and " / " in _g:
            _g = _g.split(" / ", 1)[0]
        if r.get("type") == "attr":
            r["type"] = ("finish"
                         if str(_g or "").startswith("finish")
                         else "GD&T")
        if not r.get("ops") and r.get("measured") not in (None, ""):
            r["ops"] = {"op1": {"measured": str(r["measured"]),
                                "gage": r.get("gage"), "ts": ts}}


def heal_dual_types(ledger):
    from .common import TYPES
    n = 0
    for r in ledger:
        t = r.get("type")
        if isinstance(t, str) and " / " in t:
            head = t.split(" / ", 1)[0]
            if head in TYPES:
                r["type"] = head
                n += 1
    if n:
        _warn("healed %d dual-language row type(s); a build before 0.2.5 "
              "wrote display text into the ledger" % n)
    return n


# Letters no decomposition reaches
_FOLD = {u"\u0142": "l", u"\u0141": "L", u"\u00f8": "o", u"\u00d8": "O",
         u"\u0111": "d", u"\u0110": "D", u"\u00df": "ss",
         u"\u00e6": "ae", u"\u00c6": "AE", u"\u0153": "oe",
         u"\u0152": "OE", u"\u00fe": "th", u"\u00de": "TH"}


def _slug(text):
    import unicodedata
    src = "".join(_FOLD.get(ch, ch) for ch in str(text or ""))
    src = unicodedata.normalize("NFKD", src)
    out = []
    for ch in src:
        if unicodedata.combining(ch):
            continue
        out.append(ch if (ch.isascii() and ch.isalnum()) else "_")
    return "_".join(x for x in "".join(out).split("_") if x)


def report_id(part, rev, day=None, taken=()):
    """{part}-{rev}-{YYYYMMDD}, -2/-3 on same-day collision."""
    day = day or datetime.now().strftime("%Y%m%d")
    base = "-".join(x for x in (_slug(part), _slug(rev), _slug(day)) if x)
    if not base:
        base = "report"
    # Windows, macOS: `P-A` is `p-a`
    taken = {str(t).lower() for t in (taken or ())}
    if base.lower() not in taken:
        return base
    n = 2
    while ("%s-%d" % (base, n)).lower() in taken:
        n += 1
    return "%s-%d" % (base, n)


def _now():
    return datetime.now().isoformat(timespec="minutes")


def new_run(rid, **kw):
    run = {"id": str(rid), "serial": "", "lot": "", "date": "",
           "inspector": "", "issued": False, "report_id": "",
           "closed": False, "closed_date": "", "touched": _now(),
           # [{file, caption}], session-relative
           "attachments": [],
           "rows": {}}
    for k, v in kw.items():
        if k in run:
            run[k] = v
    return run


def heal_legacy_issued(runs):
    """Pre-close-out builds SEALED by `issued`, honour that."""
    n = 0
    for r in runs:
        if "closed" not in r and r.get("issued"):
            r["closed"] = True
            n += 1
    if n:
        _warn("read %d issued run(s) written before close-out existed as "
              "closed out; issuing alone used to seal a run" % n)
    return n


def row_key(r, idx):
    k = r.get("rkey")
    if k:
        return str(k)
    u = r.get("uid")
    return str(u) if u is not None else "#%d" % idx


def ensure_rkeys(rows, legacy=False):
    """Minted once, carried with row, cannot drift."""
    seen = set()
    last = {}
    count = {}
    for i, r in enumerate(rows):
        if r.get("uid") is not None:
            last[r.get("uid")] = i
            count[r.get("uid")] = count.get(r.get("uid"), 0) + 1
    taken = {str(r["rkey"]) for r in rows if r.get("rkey")}
    n = 0
    for i, r in enumerate(rows):
        k = r.get("rkey")
        if k and str(k) not in seen:
            seen.add(str(k))
            continue
        u = r.get("uid")
        k = None
        # lone row keys by uid, sub-row fresh
        plain = u is not None and str(u) not in taken and str(u) not in seen
        if plain and (count.get(u) == 1 or (legacy and last.get(u) == i)):
            k = str(u)
        while k is None or k in seen or k in taken:
            n += 1
            k = "%s.%s" % (u if u is not None else "r",
                           uuid.uuid4().hex[:10])
        r["rkey"] = k
        seen.add(k)
    return rows


def split_rows(ledger):
    proj, meas = [], {}
    ensure_rkeys(ledger)
    for i, r in enumerate(ledger):
        key = row_key(r, i)
        pr = {k: v for k, v in r.items() if k not in RUN_FIELDS}
        m = {k: r[k] for k in RUN_FIELDS if k in r}
        proj.append(pr)
        if m:
            meas[key] = m
    return proj, meas


def join_rows(proj_rows, meas):
    meas = meas or {}
    out = []
    ensure_rkeys(proj_rows, legacy=True)
    for i, pr in enumerate(proj_rows):
        key = row_key(pr, i)
        r = dict(pr)
        for k in RUN_FIELDS:
            r.pop(k, None)
        r.update(meas.get(key) or {})
        out.append(r)
    return out


def migrate_comments(proj, runs, active):
    """Each run keeps the comment it showed."""
    ensure_rkeys(proj, legacy=True)
    for run in runs:
        reqs = run.get("reqs") if run.get("closed") else None
        if not isinstance(reqs, list):
            continue
        ensure_rkeys(reqs, legacy=True)
        rows = run.setdefault("rows", {})
        for i, r in enumerate(reqs):
            c = r.pop("comment", None)
            if c not in (None, ""):
                m = rows.setdefault(row_key(r, i), {})
                m.setdefault("comment", c)
    plain = [r for r in runs
             if not (r.get("closed") and isinstance(r.get("reqs"), list))]
    for i, pr in enumerate(proj):
        c = pr.pop("comment", None)
        if c in (None, ""):
            continue
        for run in plain:
            m = run.setdefault("rows", {}).setdefault(row_key(pr, i), {})
            m.setdefault("comment", c)


def run_reqs(run, proj):
    """Closed run's frozen copy, else project's."""
    if run and run.get("closed") and isinstance(run.get("reqs"), list):
        return run["reqs"]
    return proj


def _migrate_v2(ledger):
    """v2 -> v3: flat ledger becomes project plus one run."""
    proj, meas = split_rows(ledger)
    run = new_run("run1")
    run["rows"] = meas
    return proj, [run], "run1"


def session_lock_text(store):
    """Translated read-only reason body, "" if writable."""
    from .common import VERSION
    from .i18n import tr
    if not store.read_only:
        return ""
    det = getattr(store, "lock_detail", None) or {}
    path = det.get("path", "")
    kind = getattr(store, "lock_kind", "")
    if kind == "newer":
        body = tr('This file was saved by a newer Bubbler than yours '
                  '(Bubbler %s).\n\nIt was not loaded and will not be '
                  'overwritten. Update Bubbler to open this job.') % VERSION
    elif kind == "too_old":
        body = tr('This file is too old for your Bubbler (Bubbler %s).'
                  '\n\nIt was not loaded and will not be overwritten. Only '
                  'an in-between version can upgrade it: open it there, '
                  'save, then re-open it here. Without that version the '
                  'bubbles cannot be recovered - move or rename the file '
                  'below to start the drawing over.') % VERSION
    elif kind == "closed":
        body = tr('This run was closed out, so it is final and cannot be '
                  'changed.\n\nIssuing a report does not close a run; '
                  'closing out does. Start a new run to inspect another '
                  'part against this drawing.')
    elif kind == "corrupt":
        body = tr('This file is damaged and could not be read (Bubbler '
                  '%s).\n\nIt was not loaded and will not be overwritten. '
                  'Nothing in it can be recovered, so you can start the '
                  'drawing over - the damaged file is kept alongside it, '
                  'renamed.') % VERSION
        err = det.get("error")
        if err:
            body += "\n\n" + tr('Details: %s') % err
    else:
        body = str(getattr(store, "lock_reason", ""))
    if path:
        body += "\n\n" + tr('File: %s') % path
    return body + "\n\n" + tr('Your bubbles are NOT being saved to disk.')


class BubbleStore:
    def __init__(self, ledger=None, uid_seq=1):
        self.ledger = ledger if ledger is not None else []
        self.uid_seq = uid_seq
        self._listeners = []
        self.read_only = False
        self.lock_kind = ""               # newer|too_old|corrupt|closed
        self.lock_detail = {}
        self.lock_reason = ""
        self.runs = [new_run("run1")]
        self.active_run = "run1"
        self.drawing = {}
        self.header = {}
        self.run_moved_on_load = False
        self._sealed = set()
        self._proj = []


    def run(self, rid=None):
        want = self.active_run if rid is None else str(rid)
        for r in self.runs:
            if r.get("id") == want:
                return r
        return None

    def run_ids(self):
        return [r.get("id") for r in self.runs]

    def _stash(self):
        run = self.run()
        if run is None or run.get("closed"):
            return                        # sealed not in memory
        run["rows"] = split_rows(self.ledger)[1]

    def _carry_proj(self):
        if self.active_run in self._sealed:
            return copy.deepcopy(self._proj)
        return split_rows(self.ledger)[0]

    def _next_run_id(self):
        n, have = 1, set(self.run_ids())
        while ("run%d" % n) in have:
            n += 1
        return "run%d" % n

    def add_run(self, **kw):
        if self.read_only and self.lock_kind != "closed":
            raise SessionReadOnly(self.lock_reason or "session is read-only")
        self._stash()
        run = new_run(self._next_run_id(), **kw)
        # "" = docs unwritten, not in new_run
        run["docs_id"] = ""
        proj = self._carry_proj()
        self.runs.append(run)
        self.active_run = run["id"]
        self.ledger = join_rows(proj, {})
        self._sync_run_lock()
        self.notify()
        return run["id"]

    def set_active_run(self, rid):
        rid = str(rid)
        if self.run(rid) is None:
            raise KeyError("no such run: %s" % rid)
        self._stash()
        proj = self._carry_proj()
        self.active_run = rid
        self.ledger = join_rows(run_reqs(self.run(rid), proj),
                                self.run(rid).get("rows"))
        self._sync_run_lock()
        self.notify()
        return rid

    def run_issued(self, rid=None):
        """Legacy flag, no Issue step now."""
        run = self.run(rid)
        return bool(run and run.get("issued"))

    def run_closed(self, rid=None):
        run = self.run(rid)
        return bool(run and run.get("closed"))

    def run_idle_days(self, rid=None):
        """Days since Bubbler last WROTE run, None when unknown."""
        run = self.run(rid)
        stamp = str((run or {}).get("touched") or "")
        if not stamp:
            return None
        try:
            then = datetime.fromisoformat(stamp)
        except ValueError:
            return None
        return max(0.0, (datetime.now() - then).total_seconds() / 86400.0)

    def mint_report_id(self, part="", rev="", rid=None, day=None):
        """Follows part/rev until close-out, typed id stays."""
        run = self.run(rid)
        if run is None:
            raise KeyError("no such run: %s" % (rid,))
        if run.get("closed"):
            raise RunClosed("run %s was closed out" % run["id"])
        src = run.get("report_src")
        stale = (run.get("report_id") and isinstance(src, list)
                 and len(src) == 3 and [part, rev] != src[:2])
        if not run.get("report_id") or stale:
            day = (src[2] if stale else None) or day \
                or datetime.now().strftime("%Y%m%d")
            taken = [r.get("report_id") for r in self.runs
                     if r.get("report_id") and r is not run]
            run["report_id"] = report_id(part, rev, day=day, taken=taken)
            run["report_src"] = [part, rev, day]
        # no run["date"], id has its day
        return run["report_id"]

    def set_report_id(self, value, rid=None):
        """Typed id stops following, one id per run."""
        run = self.run(rid)
        if run is None:
            raise KeyError("no such run: %s" % (rid,))
        if run.get("closed"):
            raise RunClosed("run %s was closed out" % run["id"])
        value = str(value or "").strip()
        if any(c in value for c in "/\\:*?\"<>|") or value.startswith("."):
            raise ValueError("report id %s is not a file name" % value)
        low = value.lower()
        if value and any(low == str(r.get("report_id") or "").lower()
                         for r in self.runs if r is not run):
            raise ValueError("report id %s is already used by another run"
                             % value)
        run["report_id"] = value
        run.pop("report_src", None)
        return value

    def close_run(self, rid=None, day=None):
        run = self.run(rid)
        if run is None:
            raise KeyError("no such run: %s" % (rid,))
        if run.get("closed"):
            raise RunClosed("run %s was already closed out" % run["id"])
        self._stash()
        # freeze requirements, later edits never re-judge
        if run.get("id") == self.active_run:
            run["reqs"] = copy.deepcopy(split_rows(self.ledger)[0])
        run["closed"] = True
        run["closed_date"] = day or datetime.now().strftime("%Y%m%d")
        return run["id"]

    def subscribe(self, fn):
        self._listeners.append(fn)

    def notify(self):
        for fn in list(self._listeners):
            fn()

    def ordered_uids(self):
        return ordered_uids(self.ledger)

    def renumber(self):
        out = renumber(self.ledger)
        self.notify()
        return out

    def next_number(self, page):
        return next_bubble_number(self.ledger, page)

    def set_number(self, uid, target):
        self.ledger = set_number(self.ledger, uid, target)
        self.notify()

    def remove(self, uid):
        self.ledger, removed = remove_bubble(self.ledger, uid)
        self.notify()
        return removed

    def migrate_uids(self):
        self.uid_seq = max(self.uid_seq, migrate_uids(self.ledger))
        return self.uid_seq

    def new_uid(self):
        u = self.uid_seq
        self.uid_seq += 1
        return u

    def snapshot_state(self):
        return (copy.deepcopy(self.ledger), self.uid_seq)

    def restore_state(self, state):
        self.ledger, self.uid_seq = state

    def _lock(self, kind, msg, **detail):
        self.read_only = True
        self.lock_kind = kind
        self.lock_detail = detail
        self.lock_reason = msg
        _warn(msg)

    def _clear_lock(self):
        self.read_only = False
        self.lock_kind = ""
        self.lock_detail = {}
        self.lock_reason = ""

    def start_over(self, path):
        """CORRUPT sidecar -> rename aside and unlock, new name or ""."""
        if self.lock_kind != "corrupt" or not path:
            return ""
        bak = path + ".bak"
        n = 1
        while os.path.exists(bak):
            bak = "%s.bak%d" % (path, n)
            n += 1
        try:
            os.rename(path, bak)
        except OSError:
            return ""
        self._clear_lock()
        return bak

    def _sync_run_lock(self, path=""):
        """Match lock to active run, refused FILE outranks it."""
        if self.lock_kind not in ("", "closed"):
            return
        if self.active_run in self._sealed:
            run = self.run() or {}
            self._lock("closed",
                       "run %s was closed out%s; it is finalized and will "
                       "not be overwritten: %s"
                       % (self.active_run,
                          (" as report %s" % run.get("report_id"))
                          if run.get("report_id") else "",
                          path),
                       path=path, run=self.active_run,
                       report_id=run.get("report_id") or "")
        elif self.lock_kind == "closed":
            self._clear_lock()

    def load_session(self, path):
        if not os.path.isfile(path):
            self._clear_lock()
            return True
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError("session root is not an object")
        except Exception as e:
            self._lock("corrupt",
                       "cannot read session (%s): %s" % (e, path),
                       path=path, error=str(e))
            return False
        if "v" not in d:
            ver = 1                       # pre-version files
        else:
            ver = d.get("v")
            if isinstance(ver, bool) or not isinstance(ver, int):
                self._lock("corrupt",
                           "session version field is not a number (%r): %s"
                           % (ver, path),
                           path=path,
                           error="bad version field %r" % (ver,))
                return False
        if ver > SESSION_VERSION:
            self._lock("newer",
                       "session v%d was written by a NEWER Bubbler (this "
                       "build reads v%d). Not loaded, and this file will not "
                       "be overwritten - update Bubbler to open it: %s"
                       % (ver, SESSION_VERSION, path),
                       path=path, ver=ver, reads=SESSION_VERSION)
            return False
        if ver < MIN_SESSION_VERSION:
            self._lock("too_old",
                       "session v%d is too old to migrate (this build reads "
                       "v%d-v%d). Not loaded, and this file will not be "
                       "overwritten: %s"
                       % (ver, MIN_SESSION_VERSION, SESSION_VERSION, path),
                       path=path, ver=ver,
                       reads="v%d-v%d" % (MIN_SESSION_VERSION,
                                          SESSION_VERSION))
            return False
        moved = False
        try:
            if ver < 3:
                ledger = copy.deepcopy(d.get("ledger", []))
                if ver < 2:
                    _migrate_v1(ledger)
                heal_dual_types(ledger)   # value repair, any version
                proj, runs, active = _migrate_v2(ledger)
            else:
                proj = copy.deepcopy((d.get("project") or {}).get("rows", []))
                heal_dual_types(proj)
                raw = copy.deepcopy(d.get("runs") or [])
                heal_legacy_issued(raw)
                runs = []
                for i, r in enumerate(raw):
                    one = new_run(r.get("id") or "run%d" % (i + 1))
                    one.update(r)
                    one["id"] = str(one["id"])
                    one["rows"] = one.get("rows") or {}
                    runs.append(one)
                if not runs:
                    runs = [new_run("run1")]
                # newest run, not last active
                active = runs[-1]["id"]
                # missing active_run = moved
                moved = (len(runs) > 1
                         and str(d.get("active_run") or "") != active)
            uid_seq = int(d.get("uid_seq", d.get("next_num", 1)))
            drawing = copy.deepcopy(d.get("drawing") or {})
            if not isinstance(drawing, dict):
                drawing = {}
            # header ADDITIVE, no bump
            header = copy.deepcopy(d.get("header") or {})
            if not isinstance(header, dict):
                header = {}
            migrate_comments(proj, runs, active)
            cur = [r for r in runs if r["id"] == active][0]
            ledger = join_rows(run_reqs(cur, proj), cur.get("rows"))
        except Exception as e:
            self._lock("corrupt",
                       "session load failed (%s): %s" % (e, path),
                       path=path, error=str(e))
            return False
        self.ledger = ledger
        self._proj = copy.deepcopy(proj)
        self.uid_seq = uid_seq
        self.drawing = drawing
        self.header = header
        self.runs = runs
        self.active_run = active
        self.run_moved_on_load = moved
        self._sealed = set(r["id"] for r in runs if r.get("closed"))
        self._clear_lock()
        self._sync_run_lock(path)
        return True

    def save_session(self, path):
        if self.read_only:
            exc = RunClosed if self.lock_kind == "closed" else SessionReadOnly
            raise exc(self.lock_reason or "session is read-only")
        self._stash()
        if self.active_run in self._sealed:
            self._sync_run_lock(path)
            raise RunClosed(self.lock_reason)
        cur = self.run()
        if cur is not None:               # last WORKED stamp
            cur["touched"] = _now()
        proj = split_rows(self.ledger)[0]
        self._proj = copy.deepcopy(proj)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": SESSION_VERSION, "uid_seq": self.uid_seq,
                       "project": {"rows": proj},
                       "drawing": self.drawing,
                       "header": self.header,
                       "runs": self.runs,
                       "active_run": self.active_run}, f)
        os.replace(tmp, path)
        for r in self.runs:
            if r.get("closed"):
                self._sealed.add(r["id"])
        self._sync_run_lock(path)
