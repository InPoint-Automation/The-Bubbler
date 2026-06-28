#!/usr/bin/env python3
# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Launcher entry

import sys

try:
    import fitz
    import openpyxl
    import PySide6
except ImportError:
    sys.exit("Missing deps:  pip install pymupdf openpyxl PySide6")

from bubbler.launcher import main

if __name__ == "__main__":
    main()
