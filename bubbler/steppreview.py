# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# App-facing STEP part preview.

_VIEW_ORDER = ("upper_right_front", "upper_left_back")


def stored(cfg, pdf):
    """Remembered choice dict or None."""
    return (cfg.get("step_previews") or {}).get(pdf)

def should_ask(cfg, pdf):
    """Ask for STEP first time drawing opens."""
    if not cfg.get("use_step_preview"):
        return False
    from . import step
    if not step.is_installed():
        return False
    return pdf not in (cfg.get("step_previews") or {})


def set_choice(cfg, pdf, step_path, up="z", view="upper_right_front"):
    d = cfg.setdefault("step_previews", {})
    d[pdf] = {"step": step_path or "", "up": up or "z", "view": view or ""}
    return d[pdf]


def decline(cfg, pdf):
    """Record user declined so not re-asked."""
    return set_choice(cfg, pdf, "", "z", "")


def compose_pair(pair, gap=8, bg=(255, 255, 255)):
    """Two portrait thumbs side by side or None."""
    if not pair:
        return None
    from PIL import Image
    imgs = [pair[k] for k in _VIEW_ORDER if k in pair]
    imgs = [im for im in imgs if im is not None]
    if not imgs:
        return None
    h = max(im.height for im in imgs)
    scaled = []
    for im in imgs:
        if im.height != h:
            w = max(1, int(round(im.width * h / im.height)))
            im = im.resize((w, h))
        scaled.append(im)
    total = sum(im.width for im in scaled) + gap * (len(scaled) - 1)
    out = Image.new("RGB", (total, h), bg)
    x = 0
    for im in scaled:
        out.paste(im, (x, 0))
        x += im.width + gap
    return out


def rendered_pair(cfg, pdf, size=320):
    """{view: PIL Image} for drawing's STEP or None."""
    ch = stored(cfg, pdf)
    if not ch or not ch.get("step"):
        return None
    from . import step
    paths = step.render(ch["step"], up=ch.get("up") or "z", size=size)
    if not paths:
        return None
    from PIL import Image
    out = {}
    for name, p in paths.items():
        try:
            out[name] = Image.open(p)
        except Exception:
            return None
    return out


def preview_image(cfg, pdf, size=320):
    """Composed side-by-side preview or None."""
    return compose_pair(rendered_pair(cfg, pdf, size))


def single_image(cfg, pdf, size=320):
    """Chosen view for recent-files list."""
    pair = rendered_pair(cfg, pdf, size)
    if not pair:
        return None
    ch = stored(cfg, pdf) or {}
    name = ch.get("view") or _VIEW_ORDER[0]
    return pair.get(name) or next(iter(pair.values()))
