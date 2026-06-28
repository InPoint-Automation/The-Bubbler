# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Sanity-check exported gdt_symbols.onnx via app decoder.
import argparse
import glob
import os
import sys

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..")))
from bubbler import vision        # noqa: E402

_NC = len(vision._SYM_CLASSES)


def run_one(sess, path, imgsz, conf, verbose=False):
    img = Image.open(path).convert("RGB")
    blob, (px, py), ratio = vision._letterbox(np.asarray(img), imgsz, np)
    pred = np.asarray(sess.run(None, {sess.get_inputs()[0].name: blob})[0])
    if pred.ndim == 3:
        pred = pred[0]
    if verbose:
        print("output shape %s  (expect channel dim = %d for OBB)"
              % (pred.shape, 4 + _NC + 1))
    dets = vision._nms(vision._decode(pred, _NC, conf, np), 0.45)
    draw = ImageDraw.Draw(img)
    out = []
    for x0, y0, x1, y1, c, ci in dets:
        bx0, by0 = (x0 - px) / ratio, (y0 - py) / ratio
        bx1, by1 = (x1 - px) / ratio, (y1 - py) / ratio
        tok = vision._SYM_CLASSES[ci] if 0 <= ci < _NC else "?"
        draw.rectangle((bx0, by0, bx1, by1), outline=(220, 0, 0), width=2)
        draw.text((bx0, by0 - 10), repr(tok), fill=(220, 0, 0))
        out.append((tok, c, (bx0, by0, bx1, by1)))
    return img, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(
        os.path.dirname(__file__), "..", "bubbler", "models",
        "gdt_symbols.onnx"))
    ap.add_argument("--img", default="", help="single image to verify")
    ap.add_argument("--dir", default="", help="folder of real drawing PNGs")
    ap.add_argument("--save", default="", help="overlay path (single-image)")
    ap.add_argument("--out-dir", default="train/preds", help="overlay dir (--dir)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.35)
    args = ap.parse_args()

    if not os.path.exists(args.model):
        sys.exit("model not found: %s" % args.model)
    sess = ort.InferenceSession(args.model,
                                providers=["CPUExecutionProvider"])

    if args.dir:
        os.makedirs(args.out_dir, exist_ok=True)
        paths = sorted(sum((glob.glob(os.path.join(args.dir, e))
                            for e in ("*.png", "*.jpg", "*.jpeg")), []))
        tally = {}
        for p in paths:
            img, dets = run_one(sess, p, args.imgsz, args.conf)
            img.save(os.path.join(args.out_dir, os.path.basename(p)))
            for tok, _c, _b in dets:
                tally[tok] = tally.get(tok, 0) + 1
            print("%-40s %d det" % (os.path.basename(p), len(dets)))
        print("\n%d images -> overlays in %s/" % (len(paths), args.out_dir))
        print("detections per token:", dict(sorted(tally.items())))
        return

    if not args.img:
        sys.exit("pass --img <file> or --dir <folder>")
    img, dets = run_one(sess, args.img, args.imgsz, args.conf, verbose=True)
    print("%d detection(s):" % len(dets))
    for tok, c, b in dets:
        print("  %-8s conf=%.2f  box=(%.0f,%.0f,%.0f,%.0f)"
              % (repr(tok), c, *b))
    if args.save:
        img.save(args.save)
        print("overlay -> %s" % args.save)


if __name__ == "__main__":
    main()
