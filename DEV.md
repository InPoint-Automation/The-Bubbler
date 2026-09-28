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

### Model Training
Will be released as separate repo