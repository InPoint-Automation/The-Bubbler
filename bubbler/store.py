# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Bubble ledger, uid counter, session JSON.

import copy
import json
import os

from .numbering import (ordered_uids, renumber, next_bubble_number,
                        set_number, remove_bubble, migrate_uids)


class BubbleStore:
    def __init__(self, ledger=None, uid_seq=1):
        self.ledger = ledger if ledger is not None else []
        self.uid_seq = uid_seq
        self._listeners = []

    def subscribe(self, fn):
        """Register 0-arg callback fired after mutation."""
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
        """Drop balloon rows, renumber, return removed."""
        self.ledger, removed = remove_bubble(self.ledger, uid)
        self.notify()
        return removed

    def migrate_uids(self):
        """Backfill uids on legacy rows."""
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
        """Read ledger + uid_seq from side-car JSON."""
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.ledger = d.get("ledger", [])
            # migrate legacy type="attr"
            for r in self.ledger:
                if r.get("type") == "attr":
                    r["type"] = ("finish / wykończenie"
                                 if str(r.get("group", "")).startswith("finish")
                                 else "GD&T")
            self.uid_seq = int(d.get("uid_seq", d.get("next_num", 1)))
        except Exception:
            pass

    def save_session(self, path):
        """Write side-car JSON. Raises on failure."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ledger": self.ledger, "uid_seq": self.uid_seq}, f)
