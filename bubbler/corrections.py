# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Reader-correction store. Local-only crop + label pairs for retraining.

import os
import json

SCHEMA = 1

_TYPE_TO_REGION = {
    "GD&T": "feature_control_frame",
    "finish": "surface_finish",
    "hole": "hole_note",
    "thru": "hole_note",
}
_LABEL_GLYPHS = (u"Ø", "R", u"⌖", u"▱", u"◯", u"⌭", u"⟂", u"∥", u"∠",
                 u"◎", u"⌒", u"⌓", u"⌰", u"↗", "Ra")


def region_class_for(rows):
    for r in rows or ():
        t = r.get("type")
        if t in _TYPE_TO_REGION:
            return _TYPE_TO_REGION[t]
    return "dim_tol"


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
