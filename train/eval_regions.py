# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Eval gdt_regions.onnx per-class recall/precision on real callouts.
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import refcallouts                                            # noqa: E402
from bubbler import vision                                    # noqa: E402

GT = refcallouts.GT
EXCLUDE = refcallouts.EXCLUDE


def _predict(sess, img_rgb, np, imgsz, conf, iou):
    blob, pad, ratio = vision._letterbox(img_rgb, imgsz, np)
    pred = np.asarray(sess.run(None, {sess.get_inputs()[0].name: blob})[0])
    if pred.ndim == 3:
        pred = pred[0]
    if pred.size == 0:
        return []
    dets = vision._nms(vision._decode(pred, len(vision._REGION_CLASSES),
                                      conf, np), iou)
    scored = []
    for _x0, _y0, _x1, _y1, c, ci in dets:
        if 0 <= int(ci) < len(vision._REGION_CLASSES):
            scored.append((vision._REGION_CLASSES[int(ci)], float(c)))
    return scored


def _present(scored, thr):
    return {n for n, c in scored if c >= thr}


def _micro(cache, classes, thr):
    tp = fp = fn = exact = 0
    for gt, scored in cache:
        pred = _present(scored, thr)
        if pred == gt:
            exact += 1
        tp += len(gt & pred)
        fn += len(gt - pred)
        fp += len(pred - gt)
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    return rec, prec, exact, len(cache)


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
    ap.add_argument("--sweep", action="store_true",
                    help="scan conf thresholds -> pick an operating point")
    ap.add_argument("--confusion", action="store_true",
                    help="held-out class-set confusion matrix at --conf")
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
    HELD, SEEN = "held-out (never trained)", "seen (in train set)"

    base_conf = 0.05 if args.sweep else args.conf
    cache = {HELD: [], SEEN: []}
    misses = []
    for f, gt_classes in refcallouts.labeled_images(args.images):
        gt = set(gt_classes)
        key = SEEN if len(gt_classes) == 1 else HELD
        img = np.asarray(Image.open(f).convert("RGB"))
        scored = _predict(sess, img, np, args.imgsz, base_conf, args.iou)
        cache[key].append((gt, scored))
        if args.show_misses and _present(scored, args.conf) != gt:
            misses.append((refcallouts.code_of(f), key[0], sorted(gt),
                           sorted((n, round(c, 2)) for n, c in scored)))

    for key in (HELD, SEEN):
        items = cache[key]
        if not items:
            continue
        tp = {c: 0 for c in classes}
        fn = {c: 0 for c in classes}
        fp = {c: 0 for c in classes}
        for gt, scored in items:
            pred = _present(scored, args.conf)
            for c in classes:
                if c in gt and c in pred:
                    tp[c] += 1
                elif c in gt:
                    fn[c] += 1
                elif c in pred:
                    fp[c] += 1
        print("\n=== %s  (conf %.2f) ===" % (key, args.conf))
        print("%-22s %5s %5s %5s  %6s %6s" %
              ("class", "tp", "fn", "fp", "recall", "prec"))
        print("-" * 56)
        for c in classes:
            n = tp[c] + fn[c]
            if n == 0 and fp[c] == 0:
                continue
            rec = tp[c] / n if n else float("nan")
            prec = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else float("nan")
            print("%-22s %5d %5d %5d  %6.2f %6.2f"
                  % (c, tp[c], fn[c], fp[c], rec, prec))
        rec, prec, exact, nimg = _micro(items, classes, args.conf)
        print("-" * 56)
        print("micro recall %.2f  precision %.2f   exact-set %d/%d images"
              % (rec, prec, exact, nimg))

    if args.sweep and cache[HELD]:
        print("\n=== conf sweep (held-out) -- pick an operating point ===")
        print("%6s  %6s %6s  %8s" % ("conf", "recall", "prec", "exact"))
        print("-" * 32)
        for thr in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50):
            rec, prec, exact, nimg = _micro(cache[HELD], classes, thr)
            print("%6.2f  %6.2f %6.2f  %5d/%d" % (thr, rec, prec, exact, nimg))

    if args.confusion and cache[HELD]:
        print("\n=== held-out confusion (GT row -> predicted cols, conf %.2f) ==="
              % args.conf)
        cm = {a: {b: 0 for b in classes + ["<miss>"]} for a in classes}
        fp_only = {c: 0 for c in classes}
        for gt, scored in cache[HELD]:
            pred = _present(scored, args.conf)
            for a in gt:
                if a in pred:
                    cm[a][a] += 1
                else:
                    hit = False
                    for b in pred - gt:
                        cm[a][b] += 1
                        hit = True
                    if not hit:
                        cm[a]["<miss>"] += 1
            for b in pred - gt:
                fp_only[b] += 1
        hdr = [c[:6] for c in classes]
        print("%-18s %s  %5s" % ("", " ".join("%5s" % h for h in hdr), "<miss>"))
        for a in classes:
            if sum(cm[a].values()) == 0:
                continue
            row = " ".join("%5d" % cm[a][b] for b in classes)
            print("%-18s %s  %5d" % (a[:18], row, cm[a]["<miss>"]))
        print("false-positive-only (pred class, GT absent): %s"
              % {c: n for c, n in fp_only.items() if n})
    print("\nTRUST the held-out numbers. surface_finish has no held-out example "
          "(1 real crop, single-class) -- eyeball it via check_onnx.")
    if misses:
        print("\nimperfect images (code [h=held-out/s=seen]: GT -> predicted):")
        for code, tag, gt, scored in misses:
            print("  %s [%s]: %s -> %s" % (code, tag, gt, scored))
    return 0


if __name__ == "__main__":
    sys.exit(main())
