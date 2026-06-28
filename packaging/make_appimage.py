#!/usr/bin/env python3
# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Wrap bin/Bubbler.dist into .AppImage. Run after build.py.
from __future__ import annotations

import datetime
import os
import re
import shutil
import stat
import subprocess
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "bin"
CACHE = REPO / ".cache"
ARCH = os.environ.get("ARCH", "x86_64")

_txt = (REPO / "bubbler" / "common.py").read_text(encoding="utf-8")
_m = re.search(r'^APP_NAME\s*=\s*"([^"]*)"', _txt, re.MULTILINE)
NAME = _m.group(1) if _m else "Bubbler"
_v = re.search(r'^VERSION\s*=\s*"([^"]*)"', _txt, re.MULTILINE)
if not _v:
    raise RuntimeError("VERSION not found in bubbler/common.py")
VERSION = _v.group(1)

CATEGORIES = "Graphics;Engineering;"
ICON_SRC = REPO / "img" / "TheBubbler.png"
APPID = "com.inpointautomation.Bubbler"
META_SRC = REPO / "packaging" / f"{APPID}.metainfo.xml"

APPIMAGETOOL_URL = (
    "https://github.com/AppImage/appimagetool/releases/download/continuous/"
    f"appimagetool-{ARCH}.AppImage"
)


def _appimagetool() -> Path:
    CACHE.mkdir(exist_ok=True)
    tool = CACHE / f"appimagetool-{ARCH}.AppImage"
    if not tool.exists():
        print(f"Fetching appimagetool -> {tool}")
        urllib.request.urlretrieve(APPIMAGETOOL_URL, tool)
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    return tool


def main() -> int:
    src = BIN / f"{NAME}.dist"
    if not src.is_dir():
        print(f"ERROR: {src} not found. Run build.py first (Linux standalone).")
        return 1

    appdir = BIN / f"{NAME}.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    (appdir / "usr" / "bin").mkdir(parents=True)
    shutil.copytree(src, appdir / "usr" / "bin", dirs_exist_ok=True)

    if ICON_SRC.exists():
        shutil.copy(ICON_SRC, appdir / f"{NAME}.png")
    else:
        print(f"WARNING: {ICON_SRC} missing; AppImage will have no icon.")

    apprun = appdir / "AppRun"
    apprun.write_text(
        '#!/bin/sh\n'
        'HERE="$(dirname "$(readlink -f "${0}")")"\n'
        f'exec "${{HERE}}/usr/bin/{NAME}" "$@"\n'
    )
    apprun.chmod(0o755)

    (appdir / f"{APPID}.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NAME}\n"
        f"Exec={NAME}\n"
        f"Icon={NAME}\n"
        f"Categories={CATEGORIES}\n"
        "Terminal=false\n"
    )

    if META_SRC.exists():
        metadir = appdir / "usr" / "share" / "metainfo"
        metadir.mkdir(parents=True, exist_ok=True)
        date = os.environ.get("RELEASE_DATE") or datetime.date.today().isoformat()
        rel = (f'  <releases>\n    <release version="{VERSION}" date="{date}"/>\n'
               '  </releases>\n')
        xml = META_SRC.read_text(encoding="utf-8").replace(
            "</component>", rel + "</component>")
        (metadir / META_SRC.name).write_text(xml, encoding="utf-8")
    else:
        print(f"WARNING: {META_SRC} missing; no AppStream metadata.")

    out = BIN / f"{NAME}-{ARCH}.AppImage"
    if out.exists():
        out.unlink()

    tool = _appimagetool()
    cmd = [str(tool), "--appimage-extract-and-run", "--no-appstream",
           str(appdir), str(out)]
    print("Running:", " ".join(cmd))
    rc = subprocess.run(cmd, env={**os.environ, "ARCH": ARCH}).returncode
    if rc != 0:
        print("appimagetool FAILED.")
        return rc

    out.chmod(out.stat().st_mode | stat.S_IEXEC)
    print(f"\nAppImage OK: {out}")
    print("Test it RAN, not just built:  ./%s" % out.relative_to(REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
