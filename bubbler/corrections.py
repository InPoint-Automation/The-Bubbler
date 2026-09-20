# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Reader-correction crop plus label store

import os
import json

# adds predicted_region_class hard negative
SCHEMA = 2

# ledger type -> region class
_TYPE_TO_REGION = {
    "GD&T": "feature_control_frame",
    "finish": "surface_finish",
    "hole": "hole",
    "thru": "hole",
    "thread": "hole",
    "depth": "hole",
    "slot": "slot",
    "position": "feature_control_frame",
}
_LABEL_GLYPHS = (u"Ø", "R", u"⌖", u"▱", u"◯", u"⌭", u"⟂", u"∥", u"∠",
                 u"◎", u"⌒", u"⌓", u"⌰", u"↗", "Ra")


def region_class_for(rows):
    for r in rows or ():
        t = r.get("type")
        if t in _TYPE_TO_REGION:
            return _TYPE_TO_REGION[t]
    return "dim_length"


def predicted_class(reader):
    """Region class model read implied so correction carries wrong answer too (F6)."""
    return region_class_for([reader]) if reader else None


def symbols_for(rows):
    found = []
    for r in rows or ():
        txt = "%s %s" % (r.get("feature") or "", r.get("datums") or "")
        for g in _LABEL_GLYPHS:
            if g in txt and g not in found:
                found.append(g)
    return found


def corrections_dir(cfg):
    d = ((cfg or {}).get("corrections_dir") or "").strip()
    if d:
        return os.path.expanduser(d)
    return os.path.join(os.path.expanduser("~"), ".bubbler", "corrections")


# F9 acceptance positive label
ACC_SCHEMA = 1
_ACC_RECORD_KEYS = ("type", "feature", "nominal", "tol_sym", "tol_max",
                    "tol_min", "datums", "bubble", "tier")


def acceptances_dir(cfg):
    d = ((cfg or {}).get("acceptances_dir") or "").strip()
    if d:
        return os.path.expanduser(d)
    return os.path.join(os.path.expanduser("~"), ".bubbler", "acceptances")


def acceptance_rec(row, page, box, crop_w, crop_h, drawing_tag, version=None):
    """Acceptance record from shipped ledger row."""
    x0, y0, x1, y1 = box
    return {
        "schema": ACC_SCHEMA,
        "version": version,
        "page": page,
        "rect": [x0, y0, x1, y1],
        "crop": {"w": crop_w, "h": crop_h, "dpi": 300},
        "labels": {"region_class": region_class_for([row]),
                   "symbols": symbols_for([row])},
        "record": {k: row.get(k) for k in _ACC_RECORD_KEYS},
        "accepted": True,
        # F9 edited weaker positive
        "edited": bool(row.get("edited")),
        "drawing": drawing_tag,
    }


def write_correction(dirpath, rec, png_bytes, stamp):
    try:
        os.makedirs(dirpath, exist_ok=True)
        base = os.path.join(dirpath, str(stamp))
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        if png_bytes:
            with open(base + ".png", "wb") as f:
                f.write(png_bytes)
        return base
    except OSError:
        return None


def list_corrections(dirpath):
    try:
        names = os.listdir(dirpath)
    except OSError:
        return []
    return sorted(n[:-5] for n in names if n.endswith(".json"))
