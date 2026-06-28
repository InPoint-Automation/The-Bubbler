# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Loader for hand-labelled snippets.
import glob
import os
import re

# repo root
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REF_PARENT = os.path.join(_REPO_ROOT, "referencedata")


def _resolve(parent, name):
    """Path to a child dir matching `name` case-insensitively."""
    cand = os.path.join(parent, name)
    if os.path.isdir(cand) or not os.path.isdir(parent):
        return cand
    low = name.lower()
    for e in os.listdir(parent):
        if e.lower() == low and os.path.isdir(os.path.join(parent, e)):
            return os.path.join(parent, e)
    return cand


REF_DIR = _resolve(_REF_PARENT, "Example callouts")
# Manually cropped single-class pieces, TRAIN only.
CROP_DIR = _resolve(_REF_PARENT, "Cropped Callouts")

# Region classes.
CLASSES = ("hole_note", "feature_control_frame", "dim_tol", "hole_table",
           "surface_finish", "datum_feature", "gentol_block", "note")

# Ground truth keyed by HHMMSS code.
GT = {
    "104929": ["hole_note"], "104938": ["hole_note"], "105005": ["hole_note"],
    "105008": ["hole_note"], "105021": ["surface_finish"],
    "105029": ["gentol_block", "hole_table"],
    "105102": ["gentol_block", "hole_table"], "105115": ["dim_tol"],
    "105123": ["hole_note"], "105149": ["hole_note"],
    "105212": ["hole_note", "feature_control_frame"], "105216": ["hole_note"],
    "105219": ["hole_note"], "105223": ["feature_control_frame"],
    "105229": ["hole_note"], "105237": ["hole_note"], "105409": ["hole_note"],
    "105427": ["hole_note"], "105525": ["feature_control_frame"],
    "105549": ["hole_note", "dim_tol", "note"], "105555": ["dim_tol"],
    "105608": ["dim_tol"], "105743": ["hole_table"], "110042": ["dim_tol"],
    "110048": ["dim_tol"], "110053": ["dim_tol"], "110105": ["dim_tol"],
    "110152": ["hole_note"], "110209": ["hole_note"], "110217": ["hole_note"],
    "110230": ["hole_note"], "110234": ["hole_note"], "110247": ["hole_note"],
    "110300": ["dim_tol"], "110306": ["hole_note"], "110316": ["hole_note"],
    "110327": ["hole_note"], "110331": ["hole_note"],
    "110347": ["dim_tol", "hole_note", "feature_control_frame"],
    "110350": ["feature_control_frame"],
    "110354": ["hole_note", "feature_control_frame"],
    "110401": ["dim_tol", "feature_control_frame"],
    "110405": ["feature_control_frame", "datum_feature"],
    "110412": ["hole_note"], "110425": ["hole_note"], "110519": ["hole_note"],
    "110523": ["hole_note"], "110526": ["hole_note"], "110554": ["hole_note"],
    "110608": ["hole_note"], "110626": ["hole_note"], "110629": ["hole_note"],
    "110635": ["hole_note"], "110648": ["hole_note"], "110654": ["hole_note"],
    "110707": ["hole_note"],
}
EXCLUDE = {"105921"}        # an app screenshot, not a callout
_CODE = re.compile(r"(\d{6})(?=\.png$)")


def code_of(path):
    """HHMMSS code from a snippet filename, or None."""
    m = _CODE.search(os.path.basename(path))
    return m.group(1) if m else None


def labeled_images(ref_dir=REF_DIR):
    """Yield (path, [class, ...]) for every catalogued, non-excluded snippet."""
    for f in sorted(glob.glob(os.path.join(ref_dir, "*.png"))):
        code = code_of(f)
        if code in EXCLUDE or code not in GT:
            continue
        yield f, list(GT[code])


def _class_of_crop(path):
    """Region class from a cropped-snippet filename prefix, or None."""
    stem = os.path.splitext(os.path.basename(path))[0]
    for c in sorted(CLASSES, key=len, reverse=True):   # longest first
        if stem == c or stem.startswith(c + "_") or stem.startswith(c + " "):
            return c
    return None


def cropped_crops(crop_dir=CROP_DIR):
    """(path, class) for manually cropped single-class pieces (TRAIN only)."""
    out = []
    for f in sorted(glob.glob(os.path.join(crop_dir, "*.png"))):
        c = _class_of_crop(f)
        if c is None:
            print("refcallouts: skip un-named crop (no class prefix): %s"
                  % os.path.basename(f))
            continue
        out.append((f, c))
    return out


def single_class_crops(ref_dir=REF_DIR, crop_dir=CROP_DIR):
    """(path, class) real single-class crops for TRAINING."""
    crops = [(f, classes[0]) for f, classes in labeled_images(ref_dir)
             if len(classes) == 1]
    if os.path.isdir(crop_dir):
        crops += cropped_crops(crop_dir)
    return crops


def load_crop_layer(path):
    """Load a snippet as an RGBA layer keyed to transparent paper."""
    import numpy as np
    from PIL import Image
    arr = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    lum = arr.mean(axis=2)
    alpha = np.clip((235 - lum) * 3, 0, 255).astype("uint8")   # dark ink opaque
    rgba = np.dstack([arr.astype("uint8"), alpha])
    return Image.fromarray(rgba, "RGBA")
