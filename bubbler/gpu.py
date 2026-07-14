# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# System-python venv runs onnxruntime-gpu in a subprocess

import os
import shutil
import subprocess
import sys
import threading

from .gpu_worker import send as _send, recv as _recv

_PRISTINE_ENV = dict(os.environ)

GPU_PIN = "onnxruntime-gpu==1.26.0"
MIN_DRIVER = 525


def is_linux():
    return sys.platform.startswith("linux")


def gpu_root():
    return os.path.join(os.path.expanduser("~"), ".bubbler", "gpu")


def venv_dir():
    return os.path.join(gpu_root(), "venv")


def venv_python():
    return os.path.join(venv_dir(), "bin", "python")


def _child_env():
    """Scrubbed env"""
    env = dict(_PRISTINE_ENV)
    for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE",
              "PYTHONNOUSERSITE", "LD_PRELOAD",
              "NUITKA_ONEFILE_PARENT", "NUITKA_LAUNCH_TOKEN"):
        env.pop(k, None)
    orig = _PRISTINE_ENV.get("LD_LIBRARY_PATH")
    if orig:
        env["LD_LIBRARY_PATH"] = orig
    else:
        env.pop("LD_LIBRARY_PATH", None)
    for k in [k for k in env if k.startswith("QT_")]:
        env.pop(k, None)
    return env


def system_python():
    """system python3"""
    env = _child_env()
    for name in ("python3.12", "python3.11", "python3.10", "python3"):
        p = shutil.which(name, path=env.get("PATH"))
        if p and os.path.realpath(p) != os.path.realpath(sys.executable):
            return p
    return None


def worker_script():
    """Find loose gpu_worker.py"""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(here, "gpu_worker.py")]
    try:
        cands.append(os.path.join(__compiled__.containing_dir,
                                  "gpu_worker.py"))
    except NameError:
        pass
    cands.append(os.path.join(os.path.dirname(sys.argv[0]), "gpu_worker.py"))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def has_system_cuda():
    import ctypes.util
    return bool(ctypes.util.find_library("cudart"))


def is_installed():
    return os.path.exists(venv_python()) and worker_script() is not None


def install(want_cuda_wheels=True, on_line=None):
    """Build venv, pip-install onnxruntime-gpu"""
    if not is_linux():
        return False, "GPU pack is Linux only"
    py = system_python()
    if not py:
        return False, "no system python3 (install python3 + python3-venv)"
    try:
        os.makedirs(gpu_root(), exist_ok=True)
    except OSError as e:
        return False, "cannot create %s: %s" % (gpu_root(), e)
    env = _child_env()

    def run(cmd):
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, env=env, cwd=gpu_root(),
                             text=True, bufsize=1)
        for line in p.stdout:
            if on_line:
                on_line(line.rstrip())
        return p.wait()

    if not os.path.exists(venv_python()):
        if run([py, "-m", "venv", venv_dir()]) != 0:
            return False, "venv failed (need the python3-venv package)"
    vpy = venv_python()
    run([vpy, "-m", "pip", "install", "--upgrade", "pip"])
    pkg = ("onnxruntime-gpu[cuda,cudnn]==1.26.0" if want_cuda_wheels
           else GPU_PIN)
    if run([vpy, "-m", "pip", "install", "numpy", pkg]) != 0:
        return False, "onnxruntime-gpu install failed"
    return True, "installed"


def uninstall():
    shutil.rmtree(gpu_root(), ignore_errors=True)


class GpuRunner:
    """Worker subprocess"""

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()

    def _start(self):
        vpy, scr = venv_python(), worker_script()
        if not (os.path.exists(vpy) and scr):
            return False
        try:
            self._proc = subprocess.Popen(
                [vpy, "-u", scr], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0, close_fds=True, env=_child_env(), cwd=gpu_root())
        except Exception:
            self._proc = None
            return False
        threading.Thread(target=self._drain,
                         args=(self._proc.stderr,), daemon=True).start()
        return True

    @staticmethod
    def _drain(stream):
        try:
            for _ in iter(stream.readline, b""):
                pass
        except Exception:
            pass

    def _rpc(self, header, blobs=()):
        with self._lock:
            if not (self._proc and self._proc.poll() is None):
                if not self._start():
                    return None
            try:
                _send(self._proc.stdin, header, blobs)
                return _recv(self._proc.stdout)
            except Exception:
                self._kill()
                return None

    def ping(self):
        r = self._rpc({"cmd": "ping"})
        return r[0] if r and r[0].get("ok") else None

    def meta(self, model):
        r = self._rpc({"cmd": "meta", "model": model})
        return r[0] if r and r[0].get("ok") else None

    def run(self, model, feed):
        import numpy as np
        names = list(feed)
        arrs = [np.ascontiguousarray(feed[n]) for n in names]
        specs = [{"dtype": str(a.dtype), "shape": list(a.shape)} for a in arrs]
        r = self._rpc({"cmd": "run", "model": model, "input_names": names,
                       "input_specs": specs, "output_names": None},
                      [a.tobytes() for a in arrs])
        if not r or not r[0].get("ok"):
            return None
        header, oblobs = r
        return [np.frombuffer(b, dtype=s["dtype"]).reshape(s["shape"])
                for s, b in zip(header["output_specs"], oblobs)]

    def _kill(self):
        p, self._proc = self._proc, None
        if p:
            for fn in (lambda: p.stdin.close(), p.terminate):
                try:
                    fn()
                except Exception:
                    pass

    def close(self):
        with self._lock:
            self._kill()


_RUNNER = None


def runner():
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = GpuRunner()
    return _RUNNER


def shutdown():
    global _RUNNER
    if _RUNNER is not None:
        _RUNNER.close()
        _RUNNER = None


def status():
    if not is_linux():
        return "GPU pack is Linux only"
    if not is_installed():
        return "not installed"
    p = runner().ping()
    if not p:
        return "installed, worker not responding"
    cuda = "CUDAExecutionProvider" in (p.get("providers") or [])
    return "ready - onnxruntime %s (%s)" % (
        p.get("ort", "?"), "CUDA available" if cuda else "CPU only")
