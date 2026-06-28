# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Train GD&T symbol detector (YOLO-OBB), export raw ONNX.
import argparse
import os
import shutil

from ultralytics import YOLO

# paths relative to this file
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DEFAULT_OUT = os.path.join(_REPO, "bubbler", "models", "gdt_symbols.onnx")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="train/data/data.yaml")
    ap.add_argument("--model", default="yolo11n-obb.pt",
                    help="oriented base checkpoint (yolo11n-obb.pt / "
                         "yolov8n-obb.pt)")
    ap.add_argument("--epochs", type=int, default=80,
                    help="60-80 is plenty; synthetic data plateaus fast and "
                         "more epochs just overfit the render style")
    ap.add_argument("--patience", type=int, default=15,
                    help="early-stop after N epochs without val improvement")
    ap.add_argument("--imgsz", type=int, default=640,
                    help="must match cfg['vision_imgsz']")
    ap.add_argument("--device", default="cpu", help="'cpu' or '0' for GPU")
    ap.add_argument("--batch", type=int, default=16,
                    help="32-64 on a 12 GB GPU (RTX 3080 Ti); ~8 on a 4 GB GPU")
    ap.add_argument("--cache", default="",
                    help="'ram' or 'disk' to cache images (big speedup when "
                         "training on a fast GPU)")
    ap.add_argument("--out", default=_DEFAULT_OUT)
    args = ap.parse_args()

    model = YOLO(args.model)
    model.train(data=args.data, epochs=args.epochs, imgsz=args.imgsz,
                device=args.device, batch=args.batch, patience=args.patience,
                cache=(args.cache or False),
                project="train/runs",
                # don't flip GD&T symbols
                fliplr=0.0, flipud=0.0)
    onnx = model.export(format="onnx", imgsz=args.imgsz,
                        opset=12, simplify=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    shutil.copyfile(onnx, args.out)
    print("exported ONNX -> %s" % args.out)


if __name__ == "__main__":
    main()
