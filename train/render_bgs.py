# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Drawing PDFs -> PNG backgrounds.
# python train/render_bgs.py --pdfs /path/to/pdfs --out train/bgs --dpi 150
import argparse
import glob
import os

import fitz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", required=True, help="dir of .pdf drawings")
    ap.add_argument("--out", default="train/bgs", help="output dir for PNG pages")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    m = fitz.Matrix(args.dpi / 72.0, args.dpi / 72.0)
    n = 0
    for pdf in sorted(glob.glob(os.path.join(args.pdfs, "*.pdf"))):
        stem = os.path.splitext(os.path.basename(pdf))[0]
        try:
            doc = fitz.open(pdf)
        except Exception as e:
            print("skip %s (%s)" % (pdf, e))
            continue
        for i in range(doc.page_count):
            pix = doc[i].get_pixmap(matrix=m, alpha=False)
            pix.save(os.path.join(args.out, "%s_p%02d.png" % (stem, i)))
            n += 1
        doc.close()
    print("rendered %d pages -> %s" % (n, args.out))


if __name__ == "__main__":
    main()
