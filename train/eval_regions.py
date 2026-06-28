# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Eval gdt_regions.onnx per-class recall/precision on real callouts.
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))   # sibling refcallouts
import refcallouts                                            # noqa: E402
from bubbler import vision                                    # noqa: E402

GT = refcallouts.GT
EXCLUDE = refcallouts.EXCLUDE


def _predict(sess, img_rgb, np, imgsz, conf, iou):
    """Predicted region-class names for one RGB image."""
    blob, pad, ratio = vision._letterbox(img_rgb, imgsz, np)
    pred = np.asarray(sess.run(None, {sess.get_inputs()[0].name: blob})[0])
    if pred.ndim == 3:
        pred = pred[0]
    if pred.size == 0:
        return set(), []
    dets = vision._nms(vision._decode(pred, len(vision._REGION_CLASSES),
                                      conf, np), iou)
    names, scored = set(), []
    for _x0, _y0, _x1, _y1, c, ci in dets:
        if 0 <= int(ci) < len(vision._REGION_CLASSES):
            n = vision._REGION_CLASSES[int(ci)]
            names.add(n)
            scored.append((n, round(float(c), 2)))
    return names, scored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="bubbler/models/gdt_regions.onnx")
    ap.add_argument("--images", default=refcallouts.REF_DIR)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--ep", default="auto", help="auto|cpu|directml|cuda")
    ap.add_argument("--show-misses", action="store_true",
                    help="print per-image GT vs predicted for imperfect matches")
    args = ap.parse_args()
    try:
        import numpy as np
        import onnxruntime as ort
        from PIL import Image
    except Exception as e:
        print("missing dep (%s) -- needs numpy + pillow + onnxruntime" % e)
        return 2
    if not os.path.exists(args.model):
        print("model not found: %s -- train it first (see vision-plan.md C2b)"
              % args.model)
        return 2
    sess = ort.InferenceSession(args.model,
                                providers=vision._providers({"vision_ep": args.ep}))
    print("EP: %s" % ", ".join(sess.get_providers()))

    classes = list(vision._REGION_CLASSES)

    def _fresh():
        return ({c: 0 for c in classes}, {c: 0 for c in classes},
                {c: 0 for c in classes}, [0, 0])      # tp, fn, fp, [n_img, exact]

    # two buckets: seen single-class vs held-out multi-class
    bucket = {"held-out (never trained)": _fresh(), "seen (in train set)": _fresh()}
    misses = []
    for f, gt_classes in refcallouts.labeled_images(args.images):
        gt = set(gt_classes)
        key = "seen (in train set)" if len(gt_classes) == 1 \
            else "held-out (never trained)"
        tp, fn, fp, ctr = bucket[key]
        img = np.asarray(Image.open(f).convert("RGB"))
        pred, scored = _predict(sess, img, np, args.imgsz, args.conf, args.iou)
        ctr[0] += 1
        if pred == gt:
            ctr[1] += 1
        elif args.show_misses:
            misses.append((refcallouts.code_of(f), key[0], sorted(gt),
                           sorted(scored)))
        for c in classes:
            if c in gt and c in pred:
                tp[c] += 1
            elif c in gt:
                fn[c] += 1
            elif c in pred:
                fp[c] += 1

    for key in ("held-out (never trained)", "seen (in train set)"):
        tp, fn, fp, ctr = bucket[key]
        if not ctr[0]:
            continue
        print("\n=== %s ===" % key)
        print("%-22s %5s %5s %5s  %6s %6s" %
              ("class", "tp", "fn", "fp", "recall", "prec"))
        print("-" * 56)
        for c in classes:
            n = tp[c] + fn[c]
            if n == 0 and fp[c] == 0:
                continue                  # class absent from this bucket
            rec = tp[c] / n if n else float("nan")
            prec = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else float("nan")
            print("%-22s %5d %5d %5d  %6.2f %6.2f"
                  % (c, tp[c], fn[c], fp[c], rec, prec))
        tot = sum(tp.values())
        den_r = tot + sum(fn.values())
        den_p = tot + sum(fp.values())
        print("-" * 56)
        print("micro recall %.2f  precision %.2f   exact-set %d/%d images"
              % (tot / den_r if den_r else float("nan"),
                 tot / den_p if den_p else float("nan"), ctr[1], ctr[0]))
    print("\nTRUST the held-out numbers. surface_finish has no held-out example "
          "(1 real crop, single-class) -- eyeball it via check_onnx.")
    if misses:
        print("\nimperfect images (code [h=held-out/s=seen]: GT -> predicted):")
        for code, tag, gt, scored in misses:
            print("  %s [%s]: %s -> %s" % (code, tag, gt, scored))
    return 0


if __name__ == "__main__":
    sys.exit(main())
