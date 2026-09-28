# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Page and clip rendering for models.


def _fitz():
    try:
        import fitz
        return fitz
    except Exception:
        return None


def _scale(cfg):
    try:
        dpi = float(cfg.get("vision_dpi", 200))
    except (TypeError, ValueError):
        dpi = 200.0
    return max(1.0, dpi) / 72.0


def _pixmap(page, cfg):
    fitz = _fitz()
    if fitz is None:
        return None
    try:
        import numpy as np
    except Exception:
        return None
    s = _scale(cfg)
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    elif pix.n == 1:
        img = np.repeat(img, 3, axis=2)
    return _ink_to_black(img, np), s


# coloured ink share for colour print
_COLOUR_INK = 0.2


def _ink_to_black(img, np):
    """Colour print to black ink, darkest channel per pixel."""
    try:
        lo = img.min(axis=2)
        ink = lo < 240
        n = int(ink.sum())
        if not n:
            return img
        sat = (img.max(axis=2).astype(np.int16) - lo) > 60
        if float((sat & ink).sum()) / n <= _COLOUR_INK:
            return img
        return np.ascontiguousarray(np.repeat(lo[:, :, None], 3, axis=2))
    except Exception:                                   # pragma: no cover
        return img


def _pixmap_clip(page, cfg, rect, dpi):
    fitz = _fitz()
    if fitz is None:
        return None
    try:
        import numpy as np
    except Exception:
        return None
    # honours /Rotate (display space)
    x0, y0, x1, y1 = rect
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    s = max(1.0, float(dpi)) / 72.0
    try:                                  # unrenderable page -> no-op
        pix = page.get_pixmap(matrix=fitz.Matrix(s, s),
                              clip=fitz.Rect(x0, y0, x1, y1), alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n)
    except Exception:
        return None
    if pix.n == 4:
        img = img[:, :, :3]
    elif pix.n == 1:
        img = np.repeat(img, 3, axis=2)
    return _ink_to_black(img, np), s, x0, y0


def _rot_matrix(page):
    try:
        rot = int(getattr(page, "rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        rot = 0
    return page.rotation_matrix if rot else None


def _xform_rect(m, x0, y0, x1, y1):
    from bubbler.reader.geometry import xform_rect
    return xform_rect(m, x0, y0, x1, y1)
