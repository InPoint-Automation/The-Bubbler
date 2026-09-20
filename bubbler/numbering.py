# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Positional bubble numbering.

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _group_key(d):
    """Balloon-number unit bgroup groups callouts without collapsing uids."""
    g = d.get("bgroup")
    return g if g is not None else d["uid"]


def ordered_uids(ledger):
    """Unique uids ordered by page then first appearance."""
    first = {}
    for i, d in enumerate(ledger):
        u = d["uid"]
        if u not in first:
            first[u] = (d.get("page", 0), i)
    return [u for u, _ in sorted(first.items(), key=lambda kv: kv[1])]


def renumber(ledger):
    """Assign d['bubble'] strings in place. Return uid->number map."""
    first = {}
    for i, d in enumerate(ledger):
        k = _group_key(d)
        if k not in first:
            first[k] = (d.get("page", 0), i)
    order = [k for k, _ in sorted(first.items(), key=lambda kv: kv[1])]
    num = {k: i + 1 for i, k in enumerate(order)}
    rows_of = {}
    for d in ledger:
        rows_of.setdefault(_group_key(d), []).append(d)
    for k, rows in rows_of.items():
        if len(rows) == 1:
            rows[0]["bubble"] = str(num[k])
        else:
            for i, d in enumerate(rows):
                rows[i]["bubble"] = "%d%s" % (num[k],
                                              LETTERS[i % len(LETTERS)])
    # uid -> group number
    return {d["uid"]: num[_group_key(d)] for d in ledger}


def next_bubble_number(ledger, page):
    """Next balloon number on page counted by GROUP not member uid."""
    first = {}
    for i, d in enumerate(ledger):
        k = _group_key(d)
        if k not in first:
            first[k] = (d.get("page", 0), i)
    order = [k for k, _ in sorted(first.items(), key=lambda kv: kv[1])]
    n = 0
    for k in order:
        if first[k][0] <= page:
            n += 1
        else:
            break
    return n + 1


def set_number(ledger, uid, target_number):
    """Move uid to target_number clamped to its page block."""
    order = ordered_uids(ledger)
    if uid not in order:
        return ledger
    pages = {}
    for d in ledger:
        pages.setdefault(d["uid"], d.get("page", 0))
    pg = pages[uid]
    block = [i for i, u in enumerate(order) if pages[u] == pg]
    lo, hi = block[0], block[-1]
    tgt = max(lo, min(hi, int(target_number) - 1))
    order.remove(uid)
    order.insert(tgt, uid)
    rows_of = {}
    for d in ledger:
        rows_of.setdefault(d["uid"], []).append(d)
    new = []
    for u in order:
        new.extend(rows_of[u])
    renumber(new)
    return new


def remove_bubble(ledger, uid):
    """Delete balloon rows and renumber. Return (new, removed)."""
    removed = [d for d in ledger if d["uid"] == uid]
    new = [d for d in ledger if d["uid"] != uid]
    renumber(new)
    return new, removed


def migrate_uids(ledger):
    """Backfill uids on legacy rows grouped by old base number."""
    from .common import base_of
    seen = {}
    nxt = 1
    for d in ledger:
        if isinstance(d.get("uid"), int):
            nxt = max(nxt, d["uid"] + 1)
    for d in ledger:
        if "uid" in d:
            continue
        b = (d.get("page", 0), base_of(d.get("bubble", 0)))
        if b not in seen:
            seen[b] = nxt
            nxt += 1
        d["uid"] = seen[b]
    return nxt
