# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# OCR engines, block reads, text-layer snapping.

import re
from bubbler.reader import dedup  # noqa: E402
from bubbler.reader.vision import render, runtime  # noqa: E402


_OCR = None
_OCR_TRIED = False


def _ocr_cuda(cfg):
    """CUDA only when detectors run CUDA in-process."""
    cfg = cfg or {}
    if runtime._gpu_ready(cfg):
        return False
    if not any(p.startswith("CUDA") for p in runtime._providers(cfg)):
        return False
    runtime._preload_cuda_libs()  # before engine, else silent
    return True


def _rapidocr(cuda):
    from rapidocr_onnxruntime import RapidOCR
    if not cuda:
        return RapidOCR()
    from rapidocr_onnxruntime.utils import infer_engine
    orig = infer_engine.OrtInferSession._get_ep_list

    def eps(self):
        out = orig(self)
        # EXHAUSTIVE 3x slower per new shape
        for name, opts in out:
            if name == "CUDAExecutionProvider":
                opts["cudnn_conv_algo_search"] = "HEURISTIC"
        return out
    infer_engine.OrtInferSession._get_ep_list = eps
    try:
        return RapidOCR(det_use_cuda=True, cls_use_cuda=True,
                        rec_use_cuda=True)
    finally:
        infer_engine.OrtInferSession._get_ep_list = orig


class _OcrCpuFallback:
    """GPU failure re-reads on CPU, stays there."""

    def __init__(self, eng):
        self._eng = eng
        self._cpu = False

    def __getattr__(self, name):
        if name == "_eng":  # half-built, no recursion
            raise AttributeError(name)
        return getattr(self._eng, name)

    def __call__(self, *a, **kw):
        eng = self._eng
        try:
            return eng(*a, **kw)
        except TypeError:
            raise  # argument, not GPU
        except Exception as e:
            if self._cpu or not runtime._gpu_failure(e):
                raise
            with runtime._SESS_LOCK:
                if self._eng is eng:
                    self._eng = _rapidocr(False)
                    self._cpu = True
                    runtime._gpu_fell_back("the OCR", e)
            return self._eng(*a, **kw)


def _ocr_engine(cfg=None):
    global _OCR, _OCR_TRIED
    if _OCR_TRIED:
        return _OCR
    _OCR_TRIED = True
    try:
        try:
            cuda = _ocr_cuda(cfg)
            _OCR = _rapidocr(cuda)
            if cuda:
                _OCR = _OcrCpuFallback(_OCR)
        except Exception as e:
            runtime._note("ep", "OCR on CUDA failed (%s); OCR on CPU" % e)
            _OCR = _rapidocr(False)
        runtime._REASONS.pop("ocr", None)
    except Exception as e:
        runtime._note("ocr", "RapidOCR unavailable (%s); OCR pass disabled" % e)
        _OCR = None
    return _OCR


def _ocr_words(page, cfg):
    eng = _ocr_engine(cfg)
    pm = render._pixmap(page, cfg)
    if eng is None or pm is None:
        return []
    img, s = pm
    result, _elapse = eng(img)
    if not result:
        return []
    out = []
    for n, (box, text, conf) in enumerate(result):
        try:
            if float(conf) < float(cfg.get("vision_ocr_conf", 0.5)):
                continue
        except (TypeError, ValueError):
            pass
        xs = [pt[0] / s for pt in box]
        ys = [pt[1] / s for pt in box]
        out.append((min(xs), min(ys), max(xs), max(ys),
                    str(text), dedup._VBLOCK + 1000 + n, 0, 0))
    return out


_PADDLE = None
_PADDLE_TRIED = False


def _paddle_engine():
    global _PADDLE, _PADDLE_TRIED
    if _PADDLE_TRIED:
        return _PADDLE
    _PADDLE_TRIED = True
    try:
        from paddleocr import PaddleOCR
        _PADDLE = PaddleOCR(use_angle_cls=True, lang="latin", show_log=False)
    except Exception as e:
        runtime._warn("PaddleOCR unavailable (%s)" % e)
        _PADDLE = None
    return _PADDLE


def _ocr_engine_for(cfg):
    """-> (kind, engine). RapidOCR fallback."""
    if str((cfg or {}).get("vision_ocr_engine", "rapidocr")).lower() == "paddle":
        eng = _paddle_engine()
        if eng is not None:
            return "paddle", eng
        runtime._warn("falling back to RapidOCR for this run")
    eng = _ocr_engine(cfg)
    return ("rapidocr", eng) if eng is not None else (None, None)


def _ocr_read(kind, eng, sub):
    if kind == "paddle":
        out = []
        for page in (eng.ocr(sub, cls=True) or []):
            for line in (page or []):
                box, (text, conf) = line[0], line[1]
                out.append((box, text, conf))
        return out
    # per-char boxes, true extents
    try:
        res, _elapse = eng(sub, return_word_box=True)
    except TypeError:  # no char boxes
        res, _elapse = eng(sub)
    out = []
    for ln, r in enumerate(res or ()):
        box, text, conf = r[0], r[1], r[2]
        chars = r[3] if len(r) > 3 else None
        if not chars or len(chars) != len(text) or " " not in text.strip():
            out.append((box, text, conf, ln))
            continue
        for m in re.finditer(r"\S+", text):
            pts = [p for c in chars[m.start():m.end()] for p in c]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            out.append(([(min(xs), min(ys)), (max(xs), min(ys)),
                         (max(xs), max(ys)), (min(xs), max(ys))],
                        m.group(0), conf, ln))
    return out


# rot90 turns to left-to-right
_OCR_TURN = {1: 1, 2: 2, 3: -1}
_QUARTER_DIR = {1: (0.0, 1.0), 2: (-1.0, 0.0), 3: (0.0, -1.0)}


_OCR_NUM_FRAG = re.compile(r"^[\d.,]+$")


_OCR_PHI = re.compile("[\u03a6\u03c6\u03d5]")


def _split_ocr_phrases(words):
    """Phrase split so drawn glyph can join per token."""
    out = []
    for w in words:
        text = _OCR_PHI.sub("\u00d8", str(w[4]))
        toks = [(m.start(), m.end(), m.group(0))
                for m in re.finditer(r"\S+", text)]
        if len(toks) <= 1:
            out.append(w[:4] + (text.strip(),) + tuple(w[5:]))
            continue
        n = max(len(text), 1)
        d = w[8] if len(w) > 8 and w[8] else (1.0, 0.0)
        for i, (a, b, t) in enumerate(toks):
            f0, f1 = a / float(n), b / float(n)
            if abs(d[1]) > abs(d[0]):
                span = w[3] - w[1]
                if d[1] > 0:
                    box = (w[0], w[1] + f0 * span, w[2], w[1] + f1 * span)
                else:
                    box = (w[0], w[3] - f1 * span, w[2], w[3] - f0 * span)
            else:
                span = w[2] - w[0]
                box = (w[0] + f0 * span, w[1], w[0] + f1 * span, w[3])
            out.append(box + (t,) + tuple(w[5:6]) + (w[6] if len(w) > 6
                                                     else 0,)
                       + (float(w[7]) + i / 100.0 if len(w) > 7 else i,)
                       + tuple(w[8:]))
    keep = []
    for w in out:
        t = str(w[4])
        area = max((w[2] - w[0]) * (w[3] - w[1]), 1e-6)
        if any(o is not w and str(o[4]) != t and str(o[4]).startswith(t)
               and len(str(o[4])) > len(t)
               and (max(0.0, min(o[2], w[2]) - max(o[0], w[0]))
                    * max(0.0, min(o[3], w[3]) - max(o[1], w[1])))
               >= 0.25 * area for o in out):
            continue
        keep.append(w)
    return keep


_OCR_NUMERIC = re.compile(r"^[\d.,+\-\u00b1]+$")


def _off_text_layer(ocr, words, rect, partial_only=False):
    near = [w for w in words or () if str(w[4]).strip()
            and int(w[5]) < dedup._VBLOCK and w[2] >= rect[0] - 2
            and w[0] <= rect[2] + 2 and w[3] >= rect[1] - 2
            and w[1] <= rect[3] + 2]
    if not near:
        return ocr
    out, used = [], set()
    for o in ocr:
        ao = max((o[2] - o[0]) * (o[3] - o[1]), 1e-6)
        on = []
        for i, w in enumerate(near):
            aw = max((w[2] - w[0]) * (w[3] - w[1]), 1e-6)
            ov = (max(0.0, min(o[2], w[2]) - max(o[0], w[0]))
                  * max(0.0, min(o[3], w[3]) - max(o[1], w[1])))
            if ov >= 0.5 * min(ao, aw):
                on.append(i)
        t = str(o[4]).strip()
        # drawn parens keep REF
        if on and t != t.strip("()[]") and any(
                t.strip("()[]") == str(near[i][4]).strip() for i in on):
            out.append(o)
            continue
        # never overrule text-layer number
        if on and (not partial_only or any(
                t and (t in str(near[i][4]) or (_OCR_NUMERIC.match(t) and
                       _OCR_NUMERIC.match(str(near[i][4]).strip())))
                for i in on)):
            for i in on:
                if i not in used:
                    used.add(i)
                    out.append(near[i])
            continue
        out.append(o)
    return out


def _join_ocr_fragments(words, gap_k=0.2, band_k=0.6):
    """One number OCR-boxed as two. OCR only."""
    def frame(w):
        d = w[8] if len(w) > 8 and w[8] else (1.0, 0.0)
        if abs(d[1]) > abs(d[0]):
            if d[1] < 0:  # reads up
                return (-w[3], w[0], -w[1], w[2])
            return (w[1], -w[2], w[3], -w[0])
        return (w[0], w[1], w[2], w[3])
    words = sorted(words, key=lambda w: (round((frame(w)[1] + frame(w)[3])
                                               / 2.0), frame(w)[0]))
    out = []
    for w in words:
        if out:
            p = out[-1]
            fp, fw = frame(p), frame(w)
            h = max(min(fp[3] - fp[1], fw[3] - fw[1]), 1.0)
            band = min(fp[3], fw[3]) - max(fp[1], fw[1])
            gap = fw[0] - fp[2]
            if (_OCR_NUM_FRAG.match(str(p[4])) and _OCR_NUM_FRAG.match(str(w[4]))
                    and band >= band_k * h and gap <= gap_k * h
                    and fw[0] > fp[0]):
                t = str(p[4]) + str(w[4])
                t = re.sub(r"([.,])[.,]", r"\1", t)
                out[-1] = (min(p[0], w[0]), min(p[1], w[1]), max(p[2], w[2]),
                           max(p[3], w[3]), t) + tuple(p[5:])
                continue
        out.append(w)
    return out


def _unturn(k, x, y, w, h):
    if k == 1:  # counter-clockwise
        return w - 1 - y, x
    if k == -1:  # clockwise
        return y, h - 1 - x
    if k == 2:
        return w - 1 - x, h - 1 - y
    return x, y


def block_quarter(rect, words):
    """Text-layer direction, tall wordless box unknown (None)."""
    from bubbler.reader.layout import _box_quarter
    if any(str(w[4]).strip() for w in words or ()):
        return _box_quarter(rect, words)
    if (rect[3] - rect[1]) > 0.75 * (rect[2] - rect[0]):
        return None
    return 0


def _ocr_block(img, s, rect, kind, eng, conf_min, blk, q=0):
    """No evidence: read three ways, keep surest."""
    if q is not None:
        return _ocr_block_q(img, s, rect, kind, eng, conf_min, blk, q)
    best = None
    for cand in (0, 3, 1):
        words = _ocr_block_q(img, s, rect, kind, eng, conf_min, blk, cand,
                             keep_conf=True)
        # piecewise read is wrong direction
        score = sum(c * max(len(re.sub(r"[^\w]", "", str(w[4]))), 1)
                    for w, c in words) - 0.5 * max(len(words) - 1, 0)
        if best is None or score > best[0]:
            best = (score, [w for w, _c in words])
    return best[1] if best else []


def _ocr_block_q(img, s, rect, kind, eng, conf_min, blk, q=0,
                 keep_conf=False):
    x0 = max(0, int(rect[0] * s))
    y0 = max(0, int(rect[1] * s))
    x1 = int(rect[2] * s)
    y1 = int(rect[3] * s)
    sub = img[y0:y1, x0:x1]
    if sub.size == 0:
        return []
    k = _OCR_TURN.get(q, 0)
    h, w = sub.shape[:2]
    import numpy as np
    if k:
        sub = np.ascontiguousarray(np.rot90(sub, k))
    # white margin, else splits at comma
    pad = max(12, int(0.35 * min(h, w)))
    fill = ((pad, pad), (pad, pad)) + (((0, 0),) if sub.ndim == 3 else ())
    sub = np.pad(sub, fill, constant_values=255)
    d = _QUARTER_DIR.get(q)
    out = []
    for n, r in enumerate(_ocr_read(kind, eng, sub)):
        box, text, conf = r[0], r[1], r[2]
        ln = r[3] if len(r) > 3 else n
        try:
            if float(conf) < conf_min:
                continue
        except (TypeError, ValueError):
            pass
        pts = [_unturn(k, p[0] - pad, p[1] - pad, w, h) for p in box]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        word = ((min(xs) + x0) / s, (min(ys) + y0) / s,
                (max(xs) + x0) / s, (max(ys) + y0) / s,
                str(text), blk + ln, 0, n) + ((d,) if d else ())
        if keep_conf:
            try:
                word = (word, float(conf))
            except (TypeError, ValueError):
                word = (word, 0.0)
        out.append(word)
    return out


def _ocr_glyph_misread(w, syms):
    t = str(w[4]).strip()
    # never count's `x`
    if not t or len(t) > 2 or any(c.isdigit() or c in "xX\u00d7"
                                  for c in t):
        return False
    cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
    return any(e[0] - 1 <= cx <= e[2] + 1 and e[1] - 1 <= cy <= e[3] + 1
               for e, _t in syms)
