# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Config defaults + JSON load/save at ~/.bubbler.json

import copy
import math
import os
import json
import sys

from .units import other_units

CFG_PATH = os.path.join(os.path.expanduser("~"), ".bubbler.json")

OPS_DEFAULT = ["op1", "op2", "op3", "final"]

FAI_SHOW_FIELDS = ("part_name", "drawing", "dwg_rev", "part_rev", "po",
                   "material", "serial", "units", "customer")
FAI_SHOW_COLUMNS = ("feature", "method", "comments", "dev_bar")
FAI_SHOW_BLOCKS = ("qa_signature",)
FAI_SHOW = FAI_SHOW_FIELDS + FAI_SHOW_COLUMNS + FAI_SHOW_BLOCKS
FAI_PAPERS = ("a4", "letter")
FAI_LANGS = ("en", "pl", "en-pl")

# bump when shipped DEFAULT changes
CFG_VERSION = 4

CFG_RESETS = {
    2: ("dp_tols_inch", "type_tier_map", "tier_shape_map", "type_tier_auto"),
    3: ("vision_sym_conf", "vision_region_conf"),
}

CFG_DEFAULT = {
    "cfg_version": CFG_VERSION,
    "radius": 9.0,
    "fontsz": 10.0,
    "default_type": "dim",
    "default_tier": "",
    "default_iso_class": "m",
    "rib_iso_on": True,
    "last_dir": "",
    "dlg_pos": None,
    "panel_cols": ["bubble", "feature", "nominal", "tol"],
    "panel_col_w": {},  # px widths
    "use_step_preview": False,
    "step_previews": {},
    "icon_color": "#1F3864",
    "leaders": False,
    "company": "",
    "fai_logo": "",  # blank = name only
    "fai_form_id": "",
    "fai_form_rev": "",
    "fai_paper": "a4",  # a4 | letter
    "fai_lang": "en-pl",  # en | pl | en-pl
    "save_output": "both",  # both | print | report
    "report_first": False,
    "run_stats": ["mean"],
    "fai_img_width_pct": 100,
    "fai_img_per_page": "auto",
    "fai_amber_pct": 90,  # %. 0 disables
    "fai_inspector": "",
    "fai_show": {k: (k != "qa_signature") for k in FAI_SHOW},
    "ui_scale": 0,  # 0 = system scale
    "recent": [],
    "metrology_tools": [  # mm
        {"id": "caliper", "name": "caliper", "kind": "caliper",
         "resolution": 0.01, "accuracy": 0.03,
         "range_min": 0.0, "range_max": 150.0,
         "features": ["length", "od", "id", "depth"]},
        {"id": "micrometer", "name": "micrometer", "kind": "micrometer",
         "resolution": 0.001, "accuracy": 0.004,
         "range_min": 0.0, "range_max": 25.0,
         "features": ["length", "od"]},
        {"id": "cmm", "name": "CMM", "kind": "CMM",
         "resolution": 0.0005, "accuracy": 0.002,
         "range_min": 0.0, "range_max": 800.0,
         "features": ["length", "od", "id", "depth", "radius", "angle",
                      "thread", "surface", "gdt"]},
    ],
    "gage_resolution_ratio": 10,  # 0 = no rank
    "ops_list": list(OPS_DEFAULT),
    "measure_skip_filled": True,
    "measure_units": "drawing",  # drawing | other
    "hole_pin_auto": False,
    "units": "iso_mm",
    "qc_subdir": "qc",  # "" = beside PDF
    "titleblock_autofill": True,
    "run_stale_days": 7,  # days. 0 off
    "dp_on": True,
    "units_ask": True,
    "gentol_basic_ref": True,
    "angular_short_side": True,
    "dp_tols": {"1": 0.2, "2": 0.05, "3": 0.01},  # retired, inch-only now
    "dp_tols_inch": {"1": 0.1, "2": 0.01, "3": 0.005, "4": 0.0005},
    "snap_geom": True,
    "tier_shapes": True,
    "tier_shape_map": {"red": "circle", "blue": "star",
                       "green": "diamond"},
    "type_tier_auto": True,
    "type_tier_map": {"dim": "red", "hole": "red", "thread": "green",  # tier per type
                      "thru": "red", "slot": "red", "depth": "red",
                      "position": "blue", "GD&T": "blue", "finish": "blue"},
    "offset_dir": "auto",
    "hotbar_on": True,
    "win_geometry": "",  # base64
    "panel_w": 0,  # 0 = Qt default
    "nav_w": 0,  # 0 = Qt default
    "open_dlg_size": [980, 720],
    "calc_history": [],

    "obstacle_min_w": 0.5,  # pt
    "language": "en",
    "sheet_lang": "both",
    "sheet_tier_designator": False,
    "sheet_tier_column": False,
    "sheet_refzone_column": False,
    "sheet_ncr_column": False,
    "sheet_gage_column": False,
    "sheet_method_column": False,
    "sheet_type_column": False,
    "sheet_basic_ref_label": False,
    "scan_preset": "First article",  # drawing H6 overrides
    "scan_presets": {},
    "capture_radius": 12.0,  # pt
    "click_auto_bubble": True,
    "auto_toast": True,
    "placement_box_obstacles": True,
    "toast_secs": 2.5,  # s
    "toast_stack": 6,
    "hole_facet_skip": ["tap_drill", "tap_drill_depth", "qty"],
    "hole_facet_order": ["hole", "depth", "tap_drill", "tap_drill_depth",
                         "cbore", "cbore_depth", "csink", "csink_depth",
                         "qty"],
    "qty_combine": "worst",  # worst | average
    "vision_assist": True,
    "vision_ocr": True,
    "vision_ocr_always": False,
    "vision_ocr_conf": 0.5,
    "vision_ocr_engine": "rapidocr",
    "vision_lexicon": True,
    "vision_symbols": True,
    "vision_sym_conf": 0.8,
    "vision_nms_iou": 0.45,  # YOLOv5 default
    "vision_dpi": 200,  # dpi
    "vision_imgsz": 2048,  # fallback, ONNX size wins
    "vision_tile": True,
    "vision_tile_overlap": 0.2,  # must exceed largest symbol
    "vision_merge": "wbf",
    "vision_fcf_rerun": True,
    "vision_fcf_dpi": 600,  # dpi
    "vision_fcf_conf": 0.25,
    "vision_fcf_structural": True,
    "vision_fcf_divider_min": 0.6,  # fraction of frame
    "vision_fcf_proj_gap": 2,  # px
    "collect_corrections": False,
    "corrections_dir": "",  # blank = ~/.bubbler/corrections
    "collect_acceptances": False,
    "acceptances_dir": "",  # blank = ~/.bubbler/acceptances
    "corrections_github_url":
        "https://github.com/InPoint-Automation/The-Bubbler/issues/new",
    "corrections_email": "",  # blank hides Email
    "vision_model": "",  # blank = bundled
    "vision_ep": "auto",
    "gpu_hint_off": False,
    "vision_region": True,
    "vision_region_conf": 0.8,
    "vision_region_union": True,
    "vision_union_bare": True,
    "vision_region_model": "",  # blank = bundled
    "vision_region_tile": False,
    "vision_orient_refit": True,
    "vision_gpu": True,
    "capture_drag_ocr": True,
    "leader_trim": True,
    "vision_section_group": True,
    "vision_section_vgap": 1.6,  # line-heights
    "vision_section_hpad": 0.5,  # line-heights
    "vision_debug_overlay": False,
    "vision_debug_on": False,
    "vision_debug_layers": ["sections", "regions", "symbols"],
    "vision_vlm": False,
    "vision_vlm_always": False,
    "vision_vlm_crosscheck": False,
    "vision_vlm_engine": "florence",
    "vision_vlm_model": "",  # blank = bundled
    "vision_sym_inject_vlm": True,
    "vision_sym_inject_text": True,
    "vision_paddlevl_model": "",  # blank = paddle cache
}

SAVE_OUTPUTS = ("both", "print", "report")

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
    # never read, units decide
    cfg.pop("gentol_ladder", None)
    # per drawing / header now
    cfg.pop("fai_customer", None)
    cfg.pop("cmm_import_op", None)
    # measure units per drawing now
    cfg["measure_units"] = CFG_DEFAULT["measure_units"]
    old = cfg.pop("fai_report_on", None)
    if "save_output" not in data and old is False:
        cfg["save_output"] = "print"
    if cfg.get("save_output") not in SAVE_OUTPUTS:
        cfg["save_output"] = CFG_DEFAULT["save_output"]
    return _apply_resets(cfg, data.get("cfg_version"))

def _apply_resets(cfg, stored_ver):
    try:
        ver = int(stored_ver)
    except (TypeError, ValueError):
        ver = 0  # unstamped = oldest
    if ver < CFG_VERSION:
        for v in sorted(CFG_RESETS):
            if v > ver:
                for k in CFG_RESETS[v]:
                    cfg[k] = copy.deepcopy(CFG_DEFAULT[k])
    if ver < 4:
        # count row joined facets, skipped
        skip = list(cfg.get("hole_facet_skip") or [])
        order = list(cfg.get("hole_facet_order") or [])
        if "qty" not in skip:
            cfg["hole_facet_skip"] = skip + ["qty"]
        if order and "qty" not in order:
            cfg["hole_facet_order"] = order + ["qty"]
    cfg["cfg_version"] = CFG_VERSION
    return cfg

UNIT_SYSTEMS = ("iso_mm", "asme_inch")
MEASURE_UNITS = ("drawing", "other")

# cfg key -> drawing key
DRAWING_OVERRIDES = {"units": "units", "measure_units": "measure_units",
                     "dp_tols_inch": "dp_tols_inch", "ops_list": "op_seq",
                     "default_iso_class": "icls_hand",
                     "dp_on": "gentol_auto", "rib_iso_on": "gentol_auto",
                     "leaders": "leaders"}


def gentol_auto(cfg, session=None):
    """Ribbon ISO / Y14.5 switch. Drawing's pick first."""
    v = (session or {}).get("gentol_auto")
    if v is not None:
        return bool(v)
    cfg = cfg or {}
    return bool(cfg.get("dp_on") or cfg.get("rib_iso_on"))


def leaders_on(cfg, session=None):
    for src in (session, cfg):
        if src and src.get("leaders") is not None:
            return bool(src.get("leaders"))
    return False

def measure_units(cfg, session=None):
    mode = None
    for src in (session, cfg):
        if not src:
            continue
        m = src.get("measure_units")
        if m in MEASURE_UNITS:
            mode = m
            break
    drw = units_of(cfg, session)
    return other_units(drw) if mode == "other" else drw

def units_of(cfg, session=None):
    for src in (session, cfg):
        if not src:
            continue
        u = src.get("units")
        if u in UNIT_SYSTEMS:
            return u
    return "iso_mm"

def units_source(session=None):
    """What set drawing's unit system. manual / detected / ""."""
    src = (session or {}).get("units_src")
    return src if src in ("manual", "detected") else ""

def gentol_ladder(cfg, session=None):
    return ("decimal" if units_of(cfg, session) == "asme_inch"
            else "iso2768")

def ops_seq(cfg, session=None):
    for src in (session, cfg):
        if not src:
            continue
        seq = src.get("op_seq") if src is session else src.get("ops_list")
        if isinstance(seq, (list, tuple)):
            clean = [str(x) for x in seq if str(x).strip()]
            if clean:
                return clean
    return list(OPS_DEFAULT)

def register_op(name, cfg, session=None):
    name = str(name or "").strip()
    if not name:
        return ops_seq(cfg, session)
    seq = ops_seq(cfg, session)
    if name not in seq:
        seq = seq + [name]
        if session is not None:
            session["op_seq"] = seq
        elif cfg is not None:
            cfg["ops_list"] = seq
    elif session is not None and "op_seq" not in session:
        session["op_seq"] = seq
    return seq

LADDER_RANGE = {"iso_mm": (0.0005, 5.0), "asme_inch": (0.00005, 0.5)}

def dp_label(key):
    """"2" -> ".XX". Bucket name user reads."""
    try:
        n = int(key)
    except (TypeError, ValueError):
        return str(key)
    return "." + "X" * max(1, n)

def validate_ladder(tols, units="iso_mm"):
    lo, hi = LADDER_RANGE.get(units, LADDER_RANGE["iso_mm"])
    clean = {}
    for k in (tols or {}):
        key = str(k)
        try:
            int(key)
        except (TypeError, ValueError):
            return None, ("bucket", key)
        try:
            v = float(str(tols[k]).replace(",", "."))
        except (TypeError, ValueError):
            return None, ("nan", dp_label(key))
        if not math.isfinite(v) or v <= 0:
            return None, ("nonpositive", dp_label(key))
        if v < lo or v > hi:
            return None, ("range", dp_label(key), v, lo, hi)
        clean[key] = v
    order = sorted(clean, key=lambda k: int(k))
    for a, b in zip(order, order[1:]):
        if clean[b] > clean[a]:
            return None, ("monotonic", dp_label(b), dp_label(a))
    return clean, None

def ladder_key(units="iso_mm"):
    return "dp_tols_inch" if units == "asme_inch" else "dp_tols"

CFG_KEEP_ON_RESET = frozenset((
    "cfg_version", "last_dir", "dlg_pos", "recent", "win_geometry",
    "panel_w", "nav_w", "open_dlg_size", "calc_history", "panel_cols",
    "panel_col_w",
    "step_previews",
))

CFG_CATALOG_KEYS = frozenset((
    "metrology_tools", "scan_presets", "ops_list",
    "type_tier_map", "tier_shape_map", "company", "dp_tols", "dp_tols_inch",
    "fai_logo", "fai_form_id", "fai_form_rev",
    "fai_inspector", "corrections_email",
))

def reset_cfg(cfg, keep_catalogs=False):
    """In place. Live dict shared across mixins."""
    keep = set(CFG_KEEP_ON_RESET)
    if keep_catalogs:
        keep |= CFG_CATALOG_KEYS
    kept = {k: cfg[k] for k in keep if k in cfg}
    cfg.clear()
    cfg.update(copy.deepcopy(CFG_DEFAULT))
    cfg.update(kept)
    return cfg

def save_cfg(cfg):
    cfg["cfg_version"] = CFG_VERSION
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except Exception as e:
        print("bubbler: config save failed (%s)" % e, file=sys.stderr)
