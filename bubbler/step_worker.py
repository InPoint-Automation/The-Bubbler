# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Tessellate STEP file to raw mesh npz.
import sys

import numpy as np


def _read(step_path):
    # build123d wraps OCC for clean tessellate
    from build123d import import_step
    solid = import_step(step_path)
    verts, tris = solid.tessellate(tolerance=0.5)
    v = np.array([tuple(p) for p in verts], dtype="float32")
    f = np.array(tris, dtype="int32")
    return v, f


def main():
    if len(sys.argv) < 3:
        sys.stderr.write("usage: step_worker.py <part.step> <out.npz>\n")
        return 2
    verts, tris = _read(sys.argv[1])
    if len(verts) == 0 or len(tris) == 0:
        sys.stderr.write("empty tessellation\n")
        return 3
    np.savez(sys.argv[2], verts=verts, tris=tris)
    return 0


if __name__ == "__main__":
    sys.exit(main())
