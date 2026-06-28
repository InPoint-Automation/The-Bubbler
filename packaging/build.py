#!/usr/bin/env python3
# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Cross-platform Nuitka build, single file per OS.
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "bin"
OS = platform.system()


def _meta() -> dict:
    """Parse common.py metadata without importing it."""
    txt = (REPO / "bubbler" / "common.py").read_text(encoding="utf-8")

    def grab(key, default):
        m = re.search(r'^%s\s*=\s*"([^"]*)"' % key, txt, re.MULTILINE)
        return m.group(1) if m else default

    ver = re.search(r'^VERSION\s*=\s*"([^"]*)"', txt, re.MULTILINE)
    if not ver:
        raise RuntimeError("VERSION not found in bubbler/common.py")
    return {
        "name": grab("APP_NAME", "Bubbler"),
        "org": grab("ORG", "InPoint Automation Sp. z o.o."),
        "version": ver.group(1),
    }


META = _meta()

APP = {
    "name": META["name"],
    "entry": "Bubbler.py",
    "icon": "img/TheBubbler.png",

    "include_packages": [],

    "include_package_data": [
        "rapidocr_onnxruntime",
        "onnxruntime",
        "paddleocr",
        "paddle",
    ],

    "include_modules": [
        "openpyxl.cell._writer",
    ],

    "data_dirs": [
        ("bubbler/icons_svg", "bubbler/icons_svg"),
    ] + ([
        ("bubbler/models", "bubbler/models"),
    ] if (REPO / "bubbler" / "models").is_dir() else []),

    "data_files": [],

    "noinclude_data": [
        "paddle/libs/*.so*",
    ],

    "nofollow": [
        "torch", "ultralytics", "onnx", "onnxsim",
        "scipy", "pandas", "matplotlib",
        "PyQt5", "PySide2", "tkinter", "pytest", "tornado", "IPython",
    ],
}


def _win_versions() -> tuple[str, str]:
    """Pad VERSION to Nuitka's four-part X.Y.Z.W."""
    parts = (META["version"].split(".") + ["0", "0", "0", "0"])[:4]
    v = ".".join(parts)
    return v, v


def flags() -> list[str]:
    """Assemble the Nuitka command line."""
    f = [
        sys.executable, "-m", "nuitka",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        f"--output-dir={BIN}",
        f"--output-filename={APP['name']}",
        "--show-progress",
        "--show-modules",
    ]

    if OS == "Linux" and os.environ.get("BUBBLER_CLANG", "1") not in ("0", "false"):
        f.append("--clang")
    if os.environ.get("BUBBLER_LOWMEM", "0") in ("1", "true"):
        f.append("--low-memory")
    else:
        f.append(f"--jobs={os.environ.get('BUBBLER_JOBS', '6')}")
    f.append(f"--lto={os.environ.get('BUBBLER_LTO', 'no')}")

    for pkg in APP["include_packages"]:
        f.append(f"--include-package={pkg}")
    for pkg in APP["include_package_data"]:
        f.append(f"--include-package-data={pkg}")
    for mod in APP["include_modules"]:
        f.append(f"--include-module={mod}")
    for pkg in APP["nofollow"]:
        f.append(f"--nofollow-import-to={pkg}")
    for src, dest in APP["data_dirs"]:
        f.append(f"--include-data-dir={REPO / src}={dest}")
    for src, dest in APP["data_files"]:
        f.append(f"--include-data-file={REPO / src}={dest}")
    for pat in APP["noinclude_data"]:
        f.append(f"--noinclude-data-files={pat}")

    if OS == "Windows":
        f.append("--onefile")
        f.append("--windows-console-mode=disable")
        fv, pv = _win_versions()
        f += [
            f"--company-name={META['org']}",
            f"--product-name={META['name']}",
            f"--file-version={fv}",
            f"--product-version={pv}",
            f"--file-description={META['name']} - PDF balloon & inspection sheet",
        ]
        if APP["icon"] and (REPO / APP["icon"]).exists():
            f.append(f"--windows-icon-from-ico={REPO / APP['icon']}")

    elif OS == "Linux":
        f.append("--standalone")
        f.append("--static-libpython=no")

    elif OS == "Darwin":
        f.append("--macos-create-app-bundle")
        f.append(f"--macos-app-name={APP['name']}")
        if APP["icon"] and (REPO / APP["icon"]).exists():
            f.append(f"--macos-app-icon={REPO / APP['icon']}")

    f.append(str(REPO / APP["entry"]))
    return f


def main() -> int:
    print("=== Nuitka build: %s %s (os=%s) ===" % (
        APP["name"], META["version"], OS))

    for stale in (
        BIN / f"{APP['name']}.exe",
        BIN / f"{APP['name']}.bin",
        BIN / f"{APP['name']}.app",
        BIN / f"{APP['name']}.dist",
        BIN / f"{APP['name']}.build",
        BIN / f"{APP['name']}.onefile-build",
    ):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
        elif stale.exists():
            stale.unlink()

    cmd = flags()
    print("Running Nuitka:\n  " + " \\\n  ".join(cmd) + "\n")

    result = subprocess.run(cmd, cwd=REPO)
    if result.returncode != 0:
        print("\nBUILD FAILED. Read the last Nuitka lines for the missing module/DLL.")
        return result.returncode

    print(f"\nBuild OK. Output in: {BIN}")
    print("Run it and watch for runtime 'No module named ...' -> add to include_modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())