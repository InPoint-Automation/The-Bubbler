# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# User config defaults + JSON load/save at ~/.bubbler.json.

import copy
import os
import json
import sys

CFG_PATH = os.path.join(os.path.expanduser("~"), ".bubbler.json")
CFG_DEFAULT = {
    "radius": 9.0,
    "fontsz": 10.0,
    "default_type": "dim",
    "default_tier": "",
    "default_iso_class": "m",
    "rib_iso_on": False,
    "gages": {},
    "last_dir": "",
    "dlg_pos": None,
    "panel_cols": ["bubble", "feature", "nominal", "tol"],
    "icon_color": "#1F3864",
    "leaders": False,
    "company": "",
    "ui_scale": 0,
    "recent": [],
    "cmm_tol": 0.01,
    "micrometer_tol": 0.03,
    "ops_list": ["op1", "op2", "op3", "final"],
    "measure_skip_filled": True,
    "cmm_import_op": "",           # "" = ask each time
    "oot_report_sheet": False,
    "hole_pin_auto": False,
    "units": "iso_mm",
    "mode": "advanced",
    "qc_subdir": "qc",       # "" = beside PDF
    "titleblock_autofill": True,
    "dp_on": False,
    "dp_tols": {"0": 0.5, "1": 0.2, "2": 0.05, "3": 0.01},
    "dp_tols_inch": {"1": 0.03, "2": 0.01, "3": 0.005, "4": 0.0005},
    "dp_angle": 1.0,         # +/- deg
    "snap_geom": True,
    "tier_shapes": True,
    "tier_shape_map": {"red": "circle", "blue": "square",
                       "green": "triangle"},
    "type_tier_auto": False,
    "type_tier_map": {"dim": "red", "hole": "red", "thread": "red",
                      "thru": "red", "slot": "red", "depth": "red",
                      "position": "red", "GD&T": "red", "finish": "red"},
    "offset_dir": "auto",
    "hotbar_on": True,
    "win_geometry": "",      # base64 saved window size/position

    "obstacle_min_w": 0.5,   # pt
    "language": "en",
    "sheet_lang": "both",
    "capture_radius": 12.0,  # pt
    "vision_assist": True,
    "vision_ocr": True,
    "vision_ocr_always": False,
    "vision_ocr_conf": 0.5,
    "vision_ocr_engine": "rapidocr",
    "vision_symbols": True,
    "vision_sym_conf": 0.35,
    "vision_nms_iou": 0.45,
    "vision_dpi": 200,
    "vision_imgsz": 640,
    "vision_tile": True,
    "vision_tile_overlap": 0.2,  # must exceed largest symbol
    "vision_merge": "wbf",
    "vision_fcf_rerun": True,    # unrotated only
    "vision_fcf_dpi": 600,
    "vision_fcf_conf": 0.25,
    "vision_fcf_structural": True,
    "vision_fcf_divider_min": 0.6,
    "vision_fcf_proj_gap": 2,       # px
    "collect_corrections": False,
    "corrections_dir": "",          # blank -> ~/.bubbler/corrections
    "corrections_github_url":
        "https://github.com/InPoint-Automation/The-Bubbler/issues/new",
    "corrections_email": "",        # blank hides the Email button
    "vision_model": "",      # blank = bundled
    "vision_ep": "auto",
    "vision_region": True,
    "vision_region_conf": 0.35,
    "vision_region_model": "",    # blank = bundled
    "vision_vlm": False,
    "vision_vlm_always": False,
    "vision_vlm_engine": "florence",
    "vision_vlm_model": "",       # blank = bundled
    "vision_sym_inject_vlm": True,
    "vision_sym_inject_text": True,   # inject glyphs into text-layer
    "vision_paddlevl_model": "",  # blank = paddle cache
}


def load_cfg():
    cfg = copy.deepcopy(CFG_DEFAULT)
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("bubbler: config load failed (%s); using defaults" % e,
              file=sys.stderr)
        return cfg
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def units_of(cfg, session=None):
    for src in (session, cfg):
        if not src:
            continue
        u = src.get("units")
        if u in ("iso_mm", "asme_inch"):
            return u
    return "iso_mm"


def save_cfg(cfg):
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except Exception as e:
        print("bubbler: config save failed (%s)" % e, file=sys.stderr)
