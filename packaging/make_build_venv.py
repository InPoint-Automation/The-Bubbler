#!/usr/bin/env python3
# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Builds .build-venv for Nuitka from the per-OS requirements.
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import venv
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OS = platform.system()
VENV = REPO / ".build-venv"

REQ_FILE = {
    "Linux": "requirements-build-linux.txt",
    "Windows": "requirements-build-windows.txt",
    "Darwin": "requirements-build-macos.txt",
}

def ort_line(req: Path) -> tuple[str, str] | None:
    """(package, version range) of the onnxruntime line in `req`."""
    pat = re.compile(r"^\s*(onnxruntime(?:-[a-z]+)?)\s*([<>=!~][^#\s]*)")
    for line in req.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if m:
            return m.group(1), m.group(2)
    return None


def venv_python() -> str:
    sub = "Scripts" if OS == "Windows" else "bin"
    exe = "python.exe" if OS == "Windows" else "python"
    return str(VENV / sub / exe)


def run(*cmd: str) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    if OS not in REQ_FILE:
        print(f"Unsupported OS: {OS}")
        return 1
    req = REPO / REQ_FILE[OS]
    if not req.exists():
        print(f"Missing requirements file: {req}")
        return 1

    marker = VENV / ("Scripts" if OS == "Windows" else "bin")
    if marker.exists():
        print(f"=== Reusing existing build venv: {VENV} ===")
    else:
        print(f"=== Creating build venv: {VENV} ===")
        venv.create(VENV, with_pip=True)

    py = venv_python()
    run(py, "-m", "pip", "install", "--upgrade", "pip")
    run(py, "-m", "pip", "install", "-r", str(req))
    run(py, "-m", "pip", "install", "nuitka")

    got = ort_line(req)
    if not got:
        print(f"No pinned onnxruntime line in {req.name}; refusing.")
        return 1
    ep, spec = got
    if OS == "Windows" and os.environ.get("BUBBLER_DML", "1") in ("0", "false"):
        ep = "onnxruntime"   # pure-CPU Windows build
    print(f"=== Pinning onnxruntime EP: {ep}{spec} ===")
    # rapidocr pulls plain onnxruntime beside the EP
    run(py, "-m", "pip", "uninstall", "-y",
        "onnxruntime", "onnxruntime-gpu", "onnxruntime-directml")
    run(py, "-m", "pip", "install", "--no-deps", ep + spec)

    print("\n=== build venv ready ===")
    print("Build with:")
    print(f"  {py} packaging/build.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
