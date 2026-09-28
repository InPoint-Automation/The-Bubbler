# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Stats per characteristic across runs.

import math

from .common import fnum, limits_of
from .store import row_key, run_reqs

# descriptive only, no Cpk
STATS = ("n", "mean", "min", "max", "range", "stdev")


def _req(row):
    if not row:
        return None
    lim = limits_of(row)
    return (row.get("nominal"),
            None if lim is None else tuple(round(float(x), 9)
                                           if x is not None else None
                                           for x in lim))


def run_series(store, closed_only=False):
    store._stash()                        # active run readings
    proj = store._carry_proj()            # live, even if closed
    out, live = {}, {}
    for i, pr in enumerate(proj):
        k = str(row_key(pr, i))
        live[k] = _req(pr)
        out[k] = {"bubble": pr.get("bubble"), "feature": pr.get("feature"),
                  "nominal": pr.get("nominal"), "values": [],
                  "other_req": 0}
    for run in store.runs:
        if closed_only and not run.get("closed"):
            continue
        reqs = run_reqs(run, proj)
        own = {} if reqs is proj else {
            str(row_key(r, i)): _req(r) for i, r in enumerate(reqs)}
        for k, m in (run.get("rows") or {}).items():
            if k not in out:
                continue
            raw = m.get("measured")
            if isinstance(raw, bool):
                v = None
            elif isinstance(raw, (int, float)):
                v = float(raw)
            else:
                try:
                    v = fnum(str(raw or ""))
                except (TypeError, ValueError, ZeroDivisionError):
                    v = None              # GO/NOGO or word
            if v is not None:
                out[k]["values"].append((run.get("id"), v))
                if k in own and own[k] != live[k]:
                    out[k]["other_req"] += 1
    return out


def describe(values, which=STATS):
    """Sample stats, stdev needs n 2."""
    xs = [float(v) for v in values]
    out = {}
    n = len(xs)
    for s in which:
        if s == "n":
            out[s] = n
        elif not n:
            out[s] = None
        elif s == "mean":
            out[s] = sum(xs) / n
        elif s == "min":
            out[s] = min(xs)
        elif s == "max":
            out[s] = max(xs)
        elif s == "range":
            out[s] = max(xs) - min(xs)
        elif s == "stdev":
            if n < 2:
                out[s] = None
            else:
                m = sum(xs) / n
                out[s] = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return out


def stats_rows(store, which=("mean",), closed_only=False):
    which = [s for s in STATS if s in set(which or ())] or ["mean"]
    rows = []
    for k, sr in run_series(store, closed_only).items():
        vals = [v for _rid, v in sr["values"]]
        if not vals:
            continue
        row = {"key": k, "bubble": sr["bubble"], "feature": sr["feature"],
               "nominal": sr["nominal"], "runs": len(vals),
               "other_req": sr["other_req"]}
        row.update(describe(vals, which))
        rows.append(row)
    return rows, which
