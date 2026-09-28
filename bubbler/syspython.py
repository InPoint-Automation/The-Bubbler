# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# System Python probe for pack venvs.

import os
import shutil
import subprocess
import sys

MIN_VERSION = (3, 10)

# real path + version
_PROBE = ("import sys, venv; print(sys.executable); "
          "print(sys.version_info[0], sys.version_info[1])")
# no console flash
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_NAMES = ("python3.12", "python3.11", "python3.10", "python3", "python")
_WIN_LAUNCHER = ("-3.12", "-3.11", "-3.10", "-3")


def candidates(windows=None, names=_NAMES):
    if windows is None:
        windows = sys.platform.startswith("win")
    out = [["py", v] for v in _WIN_LAUNCHER] if windows else []
    return out + [[n] for n in names]


def usable(argv, env=None, timeout=20):
    try:
        r = subprocess.run(list(argv) + ["-c", _PROBE], env=env,
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=_NO_WINDOW)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    # read from end
    lines = (r.stdout or "").strip().splitlines()
    if len(lines) < 2 or not lines[-2].strip():
        return None
    try:
        ver = tuple(int(x) for x in lines[-1].split()[:2])
    except ValueError:
        return None
    if len(ver) < 2 or ver < MIN_VERSION:
        return None
    return lines[-2].strip()


def find(cands, env=None):
    tried = []
    path = (env or os.environ).get("PATH")
    own = os.path.realpath(sys.executable)
    for argv in cands:
        tried.append(" ".join(argv))
        exe = shutil.which(argv[0], path=path)
        if not exe:
            continue
        found = usable([exe] + list(argv[1:]), env=env)
        # never our own
        if found and os.path.realpath(found) != own:
            return found, tried
    return None, tried


def not_found(tried, linux_hint):
    msg = "no usable Python %d.%d+ found (tried: %s)" % (
        MIN_VERSION + (", ".join(tried) or "nothing",))
    if linux_hint:
        msg += "; install python3 and python3-venv"
    return msg
