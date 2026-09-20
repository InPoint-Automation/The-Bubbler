# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Headless isometric shader for STEP part preview.


import numpy as np

# steel base light model
_BASE = (176, 190, 205)
_AMBIENT = 0.35
_DIFFUSE = 0.65

# camera eye dirs Z-up
_VIEWS = {
    "upper_right_front": (1.0, -1.0, 1.0),
    "upper_left_back": (-1.0, 1.0, 1.0),
}

# remap chosen axis +Z
_UP_MAP = {
    "z": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "-z": ((1, 0, 0), (0, 1, 0), (0, 0, -1)),
    "y": ((1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "-y": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "x": ((0, 0, 1), (0, 1, 0), (1, 0, 0)),
    "-x": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
}

UP_AXES = ("z", "-z", "y", "-y", "x", "-x")


def _unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n else v


def view_dirs(up="z"):
    """two named views as (eye_dir, up_vec) unit pairs remapped to up axis"""
    m = np.array(_UP_MAP.get(up, _UP_MAP["z"]), dtype=float)
    up_vec = _unit(m[2])
    out = {}
    for name, d in _VIEWS.items():
        out[name] = (_unit(m.T.dot(np.asarray(d, dtype=float))), up_vec)
    return out


def _basis(eye_dir, up_vec):
    """lookAt orthonormal basis (right, up, toward-eye)"""
    zc = _unit(eye_dir)                      # part -> camera
    up_vec = _unit(up_vec)
    if abs(float(np.dot(zc, up_vec))) > 0.999:   # up parallel nudge
        up_vec = _unit(up_vec + np.array([1e-3, 1e-3, 1e-3]))
    xc = _unit(np.cross(up_vec, zc))
    yc = np.cross(zc, xc)
    return xc, yc, zc


def render_iso(verts, tris, eye_dir, up_vec, size=320, margin=10):
    """one shaded isometric view of triangle mesh to PIL RGB Image"""
    from PIL import Image, ImageDraw
    verts = np.asarray(verts, dtype=float).reshape(-1, 3)
    tris = np.asarray(tris, dtype=int).reshape(-1, 3)
    if len(verts) == 0 or len(tris) == 0:
        return Image.new("RGB", (size, size), (255, 255, 255))
    xc, yc, zc = _basis(eye_dir, up_vec)
    sx = verts.dot(xc)
    sy = verts.dot(yc)
    depth = verts.dot(zc)                    # larger = nearer
    lo_x, hi_x = float(sx.min()), float(sx.max())
    lo_y, hi_y = float(sy.min()), float(sy.max())
    rx = max(hi_x - lo_x, 1e-6)
    ry = max(hi_y - lo_y, 1e-6)
    aspect = rx / ry
    if aspect >= 1.0:
        w, h = size, max(1, int(round(size / aspect)))
    else:
        w, h = max(1, int(round(size * aspect))), size
    scale = min((w - 2 * margin) / rx, (h - 2 * margin) / ry)
    px = (sx - lo_x) * scale + (w - rx * scale) / 2.0
    py = (h - 1) - ((sy - lo_y) * scale + (h - ry * scale) / 2.0)   # flip Y

    light = _unit(xc * 0.3 + yc * 0.4 + zc)  # over camera shoulder
    v0 = verts[tris[:, 0]]
    n = np.cross(verts[tris[:, 1]] - v0, verts[tris[:, 2]] - v0)
    nl = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, nl, out=np.zeros_like(n), where=nl > 0)
    # two-sided winding not guaranteed
    inten = _AMBIENT + _DIFFUSE * np.abs(n.dot(light))
    inten = np.clip(inten, 0.0, 1.0)
    order = np.argsort(depth[tris].mean(axis=1))     # far -> near (painter's)

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for t in order:
        a, b, c = tris[t]
        col = tuple(int(_BASE[k] * inten[t]) for k in range(3))
        draw.polygon([(px[a], py[a]), (px[b], py[b]), (px[c], py[c])],
                     fill=col, outline=col)
    return img


def to_portrait(img):
    """rotate 90 deg when wider than tall"""
    if img.width > img.height:
        return img.rotate(90, expand=True)
    return img


def render_pair(verts, tris, up="z", size=320):
    """two side-by-side portrait identification thumbs"""
    vd = view_dirs(up)
    out = {}
    for name, (eye, upv) in vd.items():
        out[name] = to_portrait(render_iso(verts, tris, eye, upv, size=size))
    return out
