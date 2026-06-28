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
    "hole_pin_auto": True,
    "hole_position_rows": True,  # off = single Ø row
    "dp_on": False,
    "dp_tols": {"0": 0.5, "1": 0.2, "2": 0.05, "3": 0.01},
    "snap_geom": True,
    "offset_dir": "auto",
    "hotbar_on": True,
    "obstacle_min_w": 0.5,   # min stroke width (pt) that repels
    "language": "en",        # "en" or "pl"
    "capture_radius": 12.0,  # click-box half-width, pt
    # vision pipeline
    "vision_assist": True,   # master switch
    "vision_ocr": True,      # OCR sparse-text pages
    "vision_ocr_always": False,  # OCR every page
    "vision_ocr_conf": 0.5,  # min OCR confidence
    "vision_ocr_engine": "rapidocr",  # rapidocr | paddle
    "vision_symbols": True,  # GD&T symbol detector
    "vision_sym_conf": 0.35,  # min confidence
    "vision_nms_iou": 0.45,   # NMS IoU
    "vision_dpi": 200,       # render DPI
    "vision_imgsz": 640,     # detector input size
    "vision_model": "",      # blank = bundled
    "vision_ep": "auto",     # auto | cpu | directml | cuda
    # block detector
    "vision_region": True,        # group via detector
    "vision_region_conf": 0.35,   # min confidence
    "vision_region_model": "",    # blank = bundled
    # VLM reader (slow)
    "vision_vlm": False,          # enable on add/scan
    "vision_vlm_always": False,   # use even with text layer
    "vision_vlm_engine": "florence",  # florence | paddleocr_vl
    "vision_vlm_model": "",       # blank = bundled
    "vision_sym_inject_vlm": True,  # splice GD&T into reads
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
        # merge nested dicts, keep default sub-keys
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def save_cfg(cfg):
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except Exception as e:
        print("bubbler: config save failed (%s)" % e, file=sys.stderr)
