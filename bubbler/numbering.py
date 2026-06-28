# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Positional bubble numbering. Derived from order, not stored.

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def ordered_uids(ledger):
    """Unique uids ordered by (page, first appearance)."""
    first = {}
    for i, d in enumerate(ledger):
        u = d["uid"]
        if u not in first:
            first[u] = (d.get("page", 0), i)
    return [u for u, _ in sorted(first.items(), key=lambda kv: kv[1])]


def renumber(ledger):
    """Assign d['bubble'] strings in place. -> uid->number map."""
    order = ordered_uids(ledger)
    num = {u: i + 1 for i, u in enumerate(order)}
    rows_of = {}
    for d in ledger:
        rows_of.setdefault(d["uid"], []).append(d)
    for u, rows in rows_of.items():
        if len(rows) == 1:
            rows[0]["bubble"] = str(num[u])
        else:
            for i, d in enumerate(rows):
                rows[i]["bubble"] = "%d%s" % (num[u],
                                              LETTERS[i % len(LETTERS)])
    return num


def next_bubble_number(ledger, page):
    """Number a new balloon on `page` would receive."""
    order = ordered_uids(ledger)
    pages = {}
    for d in ledger:
        pages.setdefault(d["uid"], d.get("page", 0))
    n = 0
    for u in order:
        if pages[u] <= page:
            n += 1
        else:
            break
    return n + 1


def set_number(ledger, uid, target_number):
    """Move `uid` to `target_number`, clamped to its page block."""
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
    """Delete a balloon's rows and renumber. -> (new, removed)."""
    removed = [d for d in ledger if d["uid"] == uid]
    new = [d for d in ledger if d["uid"] != uid]
    renumber(new)
    return new, removed


def migrate_uids(ledger):
    """Backfill uids on legacy rows, grouped by old base number."""
    from .common import base_of
    seen = {}
    nxt = 1
    for d in ledger:
        if "uid" in d:
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
