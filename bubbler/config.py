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

# Shipped machining sequence in order
OPS_DEFAULT = ["op1", "op2", "op3", "final"]

# FAI report identity + toggles (M1/M5)
FAI_SHOW_FIELDS = ("part_name", "drawing", "dwg_rev", "part_rev", "po",
                   "material", "serial", "units", "customer")
FAI_SHOW_COLUMNS = ("feature", "method", "comments", "dev_bar")
FAI_SHOW_BLOCKS = ("qa_signature",)
FAI_SHOW = FAI_SHOW_FIELDS + FAI_SHOW_COLUMNS + FAI_SHOW_BLOCKS
FAI_PAPERS = ("a4", "letter")
FAI_LANGS = ("en", "pl", "en-pl")

# bump when shipped DEFAULT changes
CFG_VERSION = 2

# version -> keys whose default changed in it
CFG_RESETS = {
    2: ("dp_tols_inch", "type_tier_map", "tier_shape_map", "type_tier_auto"),
}

CFG_DEFAULT = {
    "cfg_version": CFG_VERSION,
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
    "panel_col_w": {},       # per-column px widths
    # STEP 3D preview opt-in
    "use_step_preview": False,
    "step_previews": {},     # per-pdf STEP choice
    "icon_color": "#1F3864",
    # balloon on callout
    "leaders": False,
    "company": "",
    # FAI report identity
    "fai_logo": "",              # blank = name only
    "fai_form_id": "",
    "fai_form_rev": "",
    "fai_paper": "a4",           # a4 | letter
    "fai_lang": "en-pl",         # en | pl | en-pl
    # on = ballooned PDF + report
    "fai_report_on": True,
    # amber band %. 0 disables
    "fai_amber_pct": 90,
    # header defaults (L5)
    "fai_customer": "",
    "fai_inspector": "",
    # all on except qa_signature
    "fai_show": {k: (k != "qa_signature") for k in FAI_SHOW},
    "ui_scale": 0,
    "recent": [],
    # metrology tool catalog: specific tools with their OWN range, so a big
    # dimension excludes a small-envelope CMM or a caliper you do not own.
    # resolution/accuracy/range in mm; features = what the tool can measure.
    "metrology_tools": [
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
    # prefer a tool whose resolution is this many times finer than the
    # tolerance; 0 = do not rank by capability, just fit by feature + range.
    "gage_resolution_ratio": 10,
    "ops_list": list(OPS_DEFAULT),
    "measure_skip_filled": True,
    "measure_units": "drawing",    # drawing | other
    "cmm_import_op": "",           # "" = ask each time
    "hole_pin_auto": False,
    "units": "iso_mm",
    "mode": "advanced",
    "qc_subdir": "qc",       # "" = beside PDF
    "titleblock_autofill": True,
    # days idle before asked. 0 off
    "run_stale_days": 7,
    "dp_on": False,
    # gentol ladder. auto follows units
    "gentol_ladder": "auto",
    # ask when detector unsure
    "units_ask": True,
    # basic/ref also take general tol?
    "gentol_basic_ref": True,
    # on assumes shortest-side band
    "angular_short_side": True,
    # ".X" loosest rung. no "0"
    "dp_tols": {"1": 0.2, "2": 0.05, "3": 0.01},
    # inch decimal-place ladder
    "dp_tols_inch": {"1": 0.1, "2": 0.01, "3": 0.005, "4": 0.0005},
    "snap_geom": True,
    "tier_shapes": True,
    # one shape per tier
    "tier_shape_map": {"red": "circle", "blue": "star",
                       "green": "diamond"},
    "type_tier_auto": True,
    # red=feature blue=geom/surface green=thread
    "type_tier_map": {"dim": "red", "hole": "red", "thread": "green",
                      "thru": "red", "slot": "red", "depth": "red",
                      "position": "blue", "GD&T": "blue", "finish": "blue"},
    "offset_dir": "auto",
    "hotbar_on": True,
    "win_geometry": "",      # base64 window geometry
    "panel_w": 0,            # 0 = Qt default
    "open_dlg_size": [980, 720],   # picker size
    "calc_history": [],      # [expr, result] newest first

    "obstacle_min_w": 0.5,   # pt
    "language": "en",
    "sheet_lang": "both",
    # tier -> R designator
    "sheet_tier_designator": False,
    # tier is render state
    "sheet_tier_column": False,
    # optional xlsx columns. default off
    "sheet_refzone_column": False,   # GD&T datum/zone ref
    "sheet_ncr_column": False,       # NCR number
    "sheet_gage_column": False,      # gage name
    "sheet_method_column": False,    # method dropdown (GEN 3)
    "sheet_type_column": False,      # type dropdown (GEN 3)
    # spell BASIC/REF beside brackets (W70)
    "sheet_basic_ref_label": False,
    # scan-review default tick. drawing (H6) overrides
    "scan_preset": "First article",
    "scan_presets": {},
    "capture_radius": 12.0,  # pt
    # click a callout -> snap to its detected region and bubble it. off ->
    # open the bubble dialog prefilled (preview/edit) instead of dropping it
    "click_auto_bubble": True,
    "vision_assist": True,
    "vision_ocr": True,
    "vision_ocr_always": False,
    "vision_ocr_conf": 0.5,
    "vision_ocr_engine": "rapidocr",
    "vision_symbols": True,
    "vision_sym_conf": 0.35,
    "vision_nms_iou": 0.45,
    "vision_dpi": 200,
    # fallback. ONNX export size wins
    "vision_imgsz": 2048,
    "vision_tile": True,
    "vision_tile_overlap": 0.2,  # must exceed largest symbol
    "vision_merge": "wbf",
    "vision_fcf_rerun": True,    # unrotated only
    "vision_fcf_dpi": 600,
    "vision_fcf_conf": 0.25,
    "vision_fcf_structural": True,
    # read characteristic off frame image
    "vision_fcf_classify": True,
    # wrong symbol worse than blank
    "vision_fcf_cls_conf": 0.75,
    "vision_fcf_model": "",      # blank = bundled
    "vision_fcf_divider_min": 0.6,
    "vision_fcf_proj_gap": 2,       # px
    "collect_corrections": False,
    "corrections_dir": "",          # blank -> ~/.bubbler/corrections
    # F9: save bubbles as training acceptances
    "collect_acceptances": False,
    "acceptances_dir": "",          # blank -> ~/.bubbler/acceptances
    "corrections_github_url":
        "https://github.com/InPoint-Automation/The-Bubbler/issues/new",
    "corrections_email": "",        # blank hides Email button
    "vision_model": "",      # blank = bundled
    "vision_ep": "auto",
    # GPU offer "do not show again"
    "gpu_hint_off": False,
    "vision_region": True,
    "vision_region_conf": 0.35,
    # union region read with plain text scan
    "vision_region_union": True,
    # union leg proposes bare numbers
    "vision_union_bare": True,
    "vision_region_model": "",    # blank = bundled
    # tile-trained region model only (C2 arm B)
    "vision_region_tile": False,
    # refit a diagonal callout box to its text angle (AP-ROT)
    "vision_orient_refit": True,
    "vision_gpu": True,             # Linux GPU pack
    "capture_drag_ocr": True,       # drag-box capture
    "leader_trim": True,            # stop leader at text
    "vision_section_group": True,   # grow stacked boxes
    "vision_section_vgap": 1.6,     # line-heights vertical
    "vision_section_hpad": 0.5,     # line-heights horizontal
    "vision_debug_overlay": False,  # Debug overlay button
    "vision_debug_on": False,       # overlay drawn
    "vision_debug_layers": ["sections", "regions", "symbols"],
    "vision_vlm": False,
    "vision_vlm_always": False,
    # VLM second opinion. disagreement unticks
    "vision_vlm_crosscheck": False,
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
    return _apply_resets(cfg, data.get("cfg_version"))


def _apply_resets(cfg, stored_ver):
    """Re-default only keys newer CFG_VERSION changed."""
    try:
        ver = int(stored_ver)
    except (TypeError, ValueError):
        ver = 0                      # unstamped = oldest
    if ver < CFG_VERSION:
        for v in sorted(CFG_RESETS):
            if v > ver:
                for k in CFG_RESETS[v]:
                    cfg[k] = copy.deepcopy(CFG_DEFAULT[k])
    cfg["cfg_version"] = CFG_VERSION
    return cfg


UNIT_SYSTEMS = ("iso_mm", "asme_inch")
MEASURE_UNITS = ("drawing", "other")


def measure_units(cfg, session=None):
    """Unit system measure bar reads and writes in."""
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
    """Unit system for drawing. Per-drawing answer wins."""
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
    """The general-tolerance ladder, decided by the drawing STANDARD.

    ISO 2768 on a millimetre drawing, the decimal-place ladder on an inch one;
    the ladder is not a separate setting -- the units decide it.
    """
    return ("decimal" if units_of(cfg, session) == "asme_inch"
            else "iso2768")


def ops_seq(cfg, session=None):
    """Machining sequence for drawing in order. Per-drawing wins."""
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
    """Give op place in sequence first time it is used."""
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


# sane band per rung per unit system
LADDER_RANGE = {"iso_mm": (0.0005, 5.0), "asme_inch": (0.00005, 0.5)}


def dp_label(key):
    """"2" -> ".XX". Bucket name user reads."""
    try:
        n = int(key)
    except (TypeError, ValueError):
        return str(key)
    return "." + "X" * max(1, n)


def validate_ladder(tols, units="iso_mm"):
    """Sanity-check decimal-place ladder -> (clean, reason)."""
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
    """Config key holding ladder for unit system."""
    return "dp_tols_inch" if units == "asme_inch" else "dp_tols"


def save_cfg(cfg):
    cfg["cfg_version"] = CFG_VERSION      # stamp what we wrote
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except Exception as e:
        print("bubbler: config save failed (%s)" % e, file=sys.stderr)
