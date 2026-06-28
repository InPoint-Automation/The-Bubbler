# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# PaddleOCR-VL block reader. Path-B alt to Florence-2.
import os


def model_dir(cfg, model_root=None):
    """Local model dir override, else paddleocr's own cache."""
    p = (cfg or {}).get("vision_paddlevl_model")
    return p if (p and os.path.isdir(p)) else None


def can_load(cfg, model_root=None):
    """Cheap probe, no model load. Needs paddle + paddleocr."""
    try:
        import importlib.util as u
        return u.find_spec("paddle") is not None \
            and u.find_spec("paddleocr") is not None
    except Exception:
        return False


class PaddleOCRVL:
    """Lazily-loaded PaddleOCR-VL reader."""

    def __init__(self, pipeline, np):
        self._p = pipeline
        self._np = np
        self._warmed = False

    @classmethod
    def load(cls, providers, model_path):
        try:
            import numpy as np
            from paddleocr import PaddleOCRVL as _Pipe
        except Exception:
            return None
        try:
            pipe = _Pipe(model_dir=model_path) if model_path else _Pipe()
        except Exception:
            try:
                pipe = _Pipe()
            except Exception:
                return None
        return cls(pipe, np)

    def read_regions(self, img_rgb):
        """OCR one crop -> [(box_points, text, conf)], crop pixel coords."""
        if img_rgb.shape[0] < 2 or img_rgb.shape[1] < 2:
            return []
        bgr = img_rgb[:, :, ::-1]                       # BGR
        try:
            results = self._p.predict(bgr)
        except Exception:
            try:
                results = self._p.predict(input=bgr)
            except Exception:
                return []
        out = []
        for res in (results or []):
            try:
                out.extend(_rows_from_result(res))
            except Exception:
                continue                             # schema drift
        return out

    def warmup(self):
        if self._warmed:
            return
        self._warmed = True
        try:
            import numpy as np
            self.read_regions(np.full((48, 200, 3), 255, dtype="uint8"))
        except Exception:
            pass


def _is_scalar(v):
    try:
        return float(v) == float(v)          # scalars pass, arrays raise
    except (TypeError, ValueError):
        return False


def _to_points(box):
    """[x0,y0,x1,y1] or [[x,y]*N] -> corner points, or None."""
    if box is None:
        return None
    try:
        seq = list(box)
        if len(seq) == 4 and all(_is_scalar(v) for v in seq):
            x0, y0, x1, y1 = (float(v) for v in seq)
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        pts = [(float(p[0]), float(p[1])) for p in seq]
        return pts or None
    except Exception:
        return None


def _first(*vals):
    """First non-None. Avoids numpy truthiness of `a or b`."""
    for v in vals:
        if v is not None:
            return v
    return None


def _rows_from_result(res):
    """Normalise one PaddleOCR-VL result to [(box_points, text, conf)]."""
    d = getattr(res, "json", None)
    if isinstance(d, dict):
        d = d.get("res", d)
    if not isinstance(d, dict):
        d = res if isinstance(res, dict) else {}
    rows = []
    texts = d.get("rec_texts")
    if texts is not None and len(texts):
        polys = _first(d.get("rec_polys"), d.get("rec_boxes"), [])
        scores = _first(d.get("rec_scores"), [])
        for i, t in enumerate(texts):
            pts = _to_points(polys[i] if i < len(polys) else None)
            conf = float(scores[i]) if i < len(scores) else 1.0
            if pts and str(t).strip():
                rows.append((pts, str(t), conf))
        return rows
    for blk in (d.get("parsing_res_list") or []):
        t = _first(blk.get("block_content"), blk.get("content"), "")
        pts = _to_points(_first(blk.get("block_bbox"), blk.get("bbox")))
        if pts and str(t).strip():
            rows.append((pts, str(t), 1.0))
    return rows
