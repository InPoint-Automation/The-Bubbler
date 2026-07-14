# Changelog

### Version v0.2.3
- Fix GD&T symbol/region detectors class counts
- Better hole and FCF callout grouping
- Drag a box over a callout to re-analyze, uses OCR/VLM directly
- Bubbles sit closer to the callouts by default
- Reduce chances of leaders overlapping text
- Debug overlay
- Fix inch/ASME drawings getting ISO tolerances
- ISO 2768-1 radius/chamfer general-tolerance table
- Fix THRU applying to unrelated diameters
- Deleting a bubble now updates the inspection-sheet numbers immediately
- Exported-PDF better matches on-screen preview
- Linux/macOS builds ship CPU onnxruntime - to use GPU on Linux needs system CUDA 12.x + cuDNN 9.x (to reduce appimage size)

### Version v0.2.2
- GD&T symbol and region detectors weren't properly loading in Windows builds
- Fix OCR text-reader models in Windows builds
- Add "Download VLM" in Settings -> Vision to fetch Florence-2 (base-ft or large-ft)

### Version v0.2.1
- Add calculator input in measure field and in app calculator
- If enter expression e.g. "25-12" in measure field, first enter calculates result for verification and 2nd saves measurement
- Qty callouts (2x hole etc) take multiple measurements and then pick furthest from of center of tolerance band as 'worst'
- Improve parsing of hole callouts
- Window size and position stored after closing

### Version v0.2.0
- Reorganize the toolbar ribbons
- Auto-tier assign in settings
- Settings tabbed to fit on 1080p
- Add out-of-tolerance report
- Reader-correction capture for misreads
- Add title-block reading
- Add translation support

### Version v0.1.2
- Fix missing SVG icon and bundled model

### Version v0.1.1
- Fix macOS build

### Version v0.1.0
- Initial public release
