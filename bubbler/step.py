# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Optional STEP part preview pack.

import hashlib
import os
import shutil
import subprocess
import sys

# build123d wraps OpenCASCADE
STEP_PIN = "build123d>=0.10"

_PRISTINE_ENV = dict(os.environ)


def step_root():
    return os.path.join(os.path.expanduser("~"), ".bubbler", "step")


def venv_dir():
    return os.path.join(step_root(), "venv")


def cache_dir():
    return os.path.join(step_root(), "cache")


def venv_python():
    exe = "python.exe" if sys.platform.startswith("win") else "python"
    sub = "Scripts" if sys.platform.startswith("win") else "bin"
    return os.path.join(venv_dir(), sub, exe)


def _child_env():
    env = dict(_PRISTINE_ENV)
    for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE",
              "PYTHONNOUSERSITE", "LD_PRELOAD",
              "NUITKA_ONEFILE_PARENT", "NUITKA_LAUNCH_TOKEN"):
        env.pop(k, None)
    for k in [k for k in env if k.startswith("QT_")]:
        env.pop(k, None)
    return env


def system_python():
    env = _child_env()
    for name in ("python3.12", "python3.11", "python3.10", "python3",
                 "python"):
        p = shutil.which(name, path=env.get("PATH"))
        if p and os.path.realpath(p) != os.path.realpath(sys.executable):
            return p
    return None


def worker_script():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(here, "step_worker.py")]
    try:
        cands.append(os.path.join(__compiled__.containing_dir,   # noqa: F821
                                  "step_worker.py"))
    except NameError:
        pass
    cands.append(os.path.join(os.path.dirname(sys.argv[0]), "step_worker.py"))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def is_installed():
    return os.path.exists(venv_python()) and worker_script() is not None


def install(on_line=None):
    """Build isolated venv and pip-install OCC + numpy."""
    py = system_python()
    if not py:
        return False, "no system python3 (install python3 + python3-venv)"
    try:
        os.makedirs(step_root(), exist_ok=True)
    except OSError as e:
        return False, "cannot create %s: %s" % (step_root(), e)
    env = _child_env()

    def run(cmd):
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, env=env,
                             cwd=step_root(), text=True, bufsize=1)
        for line in p.stdout:
            if on_line:
                on_line(line.rstrip())
        return p.wait()

    if not os.path.exists(venv_python()):
        if run([py, "-m", "venv", venv_dir()]) != 0:
            return False, "venv failed (need the python3-venv package)"
    vpy = venv_python()
    run([vpy, "-m", "pip", "install", "--upgrade", "pip"])
    if run([vpy, "-m", "pip", "install", "numpy", STEP_PIN]) != 0:  # OCC + numpy
        return False, "3D pack (build123d / OpenCASCADE) install failed"
    return True, "installed"


def uninstall():
    shutil.rmtree(step_root(), ignore_errors=True)


def _cache_key(step_path, up, size):
    try:
        mt = os.path.getmtime(step_path)
    except OSError:
        mt = 0
    raw = "%s|%s|%s|%s" % (os.path.realpath(step_path), mt, up, size)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _cached_pair(key):
    """Both cached PNGs on disk else None."""
    from .stepshade import _VIEWS
    out = {}
    for name in _VIEWS:
        p = os.path.join(cache_dir(), "%s_%s.png" % (key, name))
        if not os.path.exists(p):
            return None
        out[name] = p
    return out


def _shade_to_cache(verts, tris, up, size, key):
    """Shade raw mesh to two cached PNGs."""
    from . import stepshade
    os.makedirs(cache_dir(), exist_ok=True)
    pair = stepshade.render_pair(verts, tris, up=up, size=size)
    out = {}
    for name, img in pair.items():
        p = os.path.join(cache_dir(), "%s_%s.png" % (key, name))
        img.save(p)
        out[name] = p
    return out


def _tessellate(step_path):
    """Run pack worker giving (verts, tris) or None."""
    import numpy as np
    wk = worker_script()
    if not wk or not os.path.exists(venv_python()):
        return None
    out_npz = os.path.join(cache_dir(), "_mesh_%d.npz" % os.getpid())
    try:
        os.makedirs(cache_dir(), exist_ok=True)
        r = subprocess.run([venv_python(), "-u", wk, step_path, out_npz],
                           env=_child_env(), capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.exists(out_npz):
            return None
        with np.load(out_npz) as d:
            verts, tris = d["verts"], d["tris"]
        return verts, tris
    except Exception:
        return None
    finally:
        try:
            os.remove(out_npz)
        except OSError:
            pass


def render(step_path, up="z", size=320):
    """Two isometric thumbs of STEP part or None."""
    if not step_path or not os.path.exists(step_path):
        return None
    key = _cache_key(step_path, up, size)
    hit = _cached_pair(key)
    if hit is not None:
        return hit
    if not is_installed():
        return None
    mesh = _tessellate(step_path)
    if mesh is None:
        return None
    return _shade_to_cache(mesh[0], mesh[1], up, size, key)
