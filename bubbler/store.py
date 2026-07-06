# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble ledger, uid counter, session JSON.

import copy
import json
import os
import sys
from datetime import datetime

from .numbering import (ordered_uids, renumber, next_bubble_number,
                        set_number, remove_bubble, migrate_uids)

SESSION_VERSION = 2


def _warn(msg):
    line = "bubbler.store: %s" % msg
    print(line, file=sys.stderr)
    try:
        logp = os.path.join(os.path.expanduser("~"), ".bubbler.log")
        with open(logp, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


class BubbleStore:
    def __init__(self, ledger=None, uid_seq=1):
        self.ledger = ledger if ledger is not None else []
        self.uid_seq = uid_seq
        self._listeners = []

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

    def load_session(self, path):
        if not os.path.isfile(path):
            return True
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            ver = d.get("v")
            if isinstance(ver, int) and ver > SESSION_VERSION:
                _warn("session v%d newer than supported v%d: %s"
                      % (ver, SESSION_VERSION, path))
            ts = datetime.now().isoformat(timespec="minutes")
            ledger = copy.deepcopy(d.get("ledger", []))
            for r in ledger:
                for _k in ("type", "group"):
                    _v = r.get(_k)
                    if isinstance(_v, str) and " / " in _v:
                        r[_k] = _v.split(" / ", 1)[0]
                if r.get("type") == "attr":
                    r["type"] = ("finish"
                                 if str(r.get("group", "")).startswith("finish")
                                 else "GD&T")
                if not r.get("ops") and r.get("measured") not in (None, ""):
                    r["ops"] = {"op1": {"measured": str(r["measured"]),
                                        "gage": r.get("gage"), "ts": ts}}
            uid_seq = int(d.get("uid_seq", d.get("next_num", 1)))
        except Exception as e:
            _warn("session load failed (%s): %s" % (e, path))
            return False
        self.ledger = ledger
        self.uid_seq = uid_seq
        return True

    def save_session(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"v": SESSION_VERSION, "ledger": self.ledger,
                       "uid_seq": self.uid_seq}, f)
