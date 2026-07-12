# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# CMM / CSV measurement import.

import csv

from bubbler.common import base_of

_BUBBLE = ("bubble", "balloon", "#", "id")
_VALUE = ("value", "measured", "actual", "result")
_GAGE = ("gage", "device")


def _pick(fieldmap, aliases):
    for a in aliases:
        if a in fieldmap:
            return fieldmap[a]
    return None


def _sniff_delim(lines):
    """Delimiter comma/semicolon/tab; comma."""
    sample = "\n".join(lines[:5])
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except (csv.Error, IndexError):
        head = lines[0] if lines else ""
        best = max(";,\t", key=head.count)      # most in header
        return best if head.count(best) else ","


def parse_cmm_csv(text):
    """Parse CMM CSV -> (records, errors); record {bubble,value,gage|None,line}, error {line,reason}."""
    records, errors = [], []
    if isinstance(text, str):
        lines = text.splitlines()
    else:
        lines = list(text)
    reader = csv.DictReader(lines, delimiter=_sniff_delim(lines))
    if not reader.fieldnames:
        return records, errors
    fieldmap = {}
    for name in reader.fieldnames:
        if name is None:
            continue
        fieldmap[name.strip().lower()] = name
    kb = _pick(fieldmap, _BUBBLE)
    kv = _pick(fieldmap, _VALUE)
    kg = _pick(fieldmap, _GAGE)
    for i, row in enumerate(reader):
        line = i + 2
        bubble = (row.get(kb) or "").strip() if kb else ""
        value = (row.get(kv) or "").strip() if kv else ""
        gage = (row.get(kg) or "").strip() if kg else ""
        if not bubble and not value and not gage:
            continue
        if not bubble:
            errors.append({"line": line, "reason": "missing bubble"})
            continue
        if not value:
            errors.append({"line": line, "reason": "missing value"})
            continue
        records.append({
            "bubble": bubble,
            "value": value,
            "gage": gage or None,
            "line": line,
        })
    return records, errors


def _base(bubble):
    try:
        b = base_of(bubble)
    except (TypeError, ValueError):
        return None
    return b if b else None


def match_to_ledger(records, ledger):
    """Match records to ledger by bubble base -> {matched:[(idx,record)], unmatched, duplicates, no_base}."""
    by_base = {}
    for idx, row in enumerate(ledger):
        rb = _base(row.get("bubble"))
        if rb is None:
            continue
        by_base.setdefault(rb, []).append(idx)

    matched, unmatched, duplicates, no_base = [], [], [], []
    resolved = []
    for rec in records:
        rb = _base(rec["bubble"])
        if rb is None:
            no_base.append(rec)
            continue
        rows = by_base.get(rb)
        if not rows:
            unmatched.append(rec)
            continue
        target = None
        for idx in rows:
            if str(ledger[idx].get("bubble")) == rec["bubble"]:
                target = idx
                break
        if target is None:
            for idx in rows:
                b = str(ledger[idx].get("bubble"))
                if b == b.rstrip("abcdefghijklmnopqrstuvwxyz"):
                    target = idx
                    break
        if target is None:
            target = rows[0]
        resolved.append((rb, rec, target))

    last_by_base = {}
    for rb, rec, target in resolved:
        last_by_base[rb] = (rec, target)
    for rb, rec, target in resolved:
        if last_by_base[rb][0] is rec:
            matched.append((target, rec))
        else:
            duplicates.append(rec)

    return {
        "matched": matched,
        "unmatched": unmatched,
        "duplicates": duplicates,
        "no_base": no_base,
    }
