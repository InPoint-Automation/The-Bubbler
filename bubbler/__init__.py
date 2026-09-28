# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Package root. Offline guards first.

import os

# before any onnxruntime import, else telemetry
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")


def _preload_cudart():
    """ORT 1.27 wants libcudart at import, wheel hides it."""
    try:
        import ctypes
        import glob
        import importlib.util
        spec = importlib.util.find_spec("nvidia")
        for root in (spec.submodule_search_locations or []) if spec else []:
            for lib in sorted(glob.glob(os.path.join(root, "*", "lib",
                                                     "libcudart.so.*"))):
                try:
                    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                    return
                except OSError:
                    continue
    except Exception:
        pass


_preload_cudart()

from .common import VERSION as __version__  # noqa: E402
