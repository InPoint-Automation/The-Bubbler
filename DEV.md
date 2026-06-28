## Building from Source
Developed and tested on Ubuntu 26.04. Includes packaging script for Windows machine to generate executable.

1. Clone the repository
```
git clone https://github.com/InPoint-Automation/The-Bubbler.git
cd The-Bubbler
```

2. Create a Python 3.12 virtual environment and install dependencies:

```
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Run the app:

```
python Bubbler.py
```

## Build & package

`packaging/build.py` is the single OS-detecting build path to one shippable item per OS:

    Windows -> bin/Bubbler.exe
    Linux   -> bin/Bubbler-x86_64.AppImage
    macOS   -> bin/Bubbler.app

### Dependencies
- 
- Linux: `sudo apt-get install python3.12-dev patchelf binutils clang`. build.py defaults to clang, GCC likes to OOM
- Windows: python.org 3.12 with the `py` launcher + MSVC Build Tools (Desktop C++).
- macOS: clang from Xcode command-line tools.


### Build

 ```
 python packaging/make_build_venv.py
 .build-venv/bin/python packaging/build.py
 .build-venv/bin/python packaging/make_appimage.py # Linux only
 .build-venv\Scripts\python packaging\build.py # Windows
```

## Train models (Linux, RTX 3080 Ti)
1. Training deps are already in `requirements.txt` (pillow, ultralytics, onnx,
   onnxsim, torch).

2. Region detector

```
python train/generate_regions.py --out train/data/region --n 6000
python train/train.py --data train/data/region/data.yaml --out bubbler/models/gdt_regions.onnx --device 0 --batch 32 --epochs 80
```
3. symbol detector

```
python train/generate_dataset.py --out train/data/symbols --n 6000
python train/train.py --data train/data/symbols/data.yaml --out bubbler/models/gdt_symbols.onnx --device 0 --batch 32 --epochs 80
```
4. Validate:

```
python train/eval_regions.py --model bubbler/models/gdt_regions.onnx --conf 0.35 --show-misses
python train/check_onnx.py --dir train/bgs --out-dir train/preds
```

5. (Offline VLM/OCR) place reader weights under `bubbler/models/`
- Florence-2 (`onnx-community/Florence-2-base-ft` to `models/florence2/`)
- P-OCRv4 + PaddleOCR-VL (run once on Linux, copy the paddle cache in). RapidOCR ships its own ONNX.
