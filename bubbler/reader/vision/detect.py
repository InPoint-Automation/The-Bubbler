# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Detector tiling, decode, NMS / WBF.

from bubbler.reader.vision import render, runtime  # noqa: E402


def _tile_grid(w, h, tile, overlap):
    if w <= tile and h <= tile:
        return [(0, 0, w, h)]
    step = max(1, int(round(tile * (1.0 - overlap))))

    def _starts(extent):
        if extent <= tile:
            return [0]
        s = list(range(0, extent - tile + 1, step))
        if s[-1] != extent - tile:
            s.append(extent - tile)
        return s

    xs, ys = _starts(w), _starts(h)
    return [(x, y, min(x + tile, w), min(y + tile, h))
            for y in ys for x in xs]


def _run_det(sess, img, imgsz, nc, conf, iou, np):
    blob, pad, ratio = _letterbox(img, imgsz, np)
    pred = np.asarray(sess.run(None, {sess.get_inputs()[0].name: blob})[0])
    if pred.ndim == 3:
        pred = pred[0]
    if pred.size == 0:
        return []
    px, py = pad
    out = []
    for x0, y0, x1, y1, c, ci in _nms(_decode(pred, nc, conf, np), iou):
        out.append(((x0 - px) / ratio, (y0 - py) / ratio,
                    (x1 - px) / ratio, (y1 - py) / ratio, c, int(ci)))
    return out


def _detect_page(sess, page, cfg, nc, conf, tile):
    pm = render._pixmap(page, cfg)
    if sess is None or pm is None:
        return []
    try:
        import numpy as np
    except Exception:
        return []
    img, s = pm
    imgsz = runtime._sess_imgsz(sess, cfg.get("vision_imgsz", runtime.IMGSZ_DEFAULT))
    iou = float(cfg.get("vision_nms_iou", 0.45))
    h, w = img.shape[:2]
    use_tile = (tile and cfg.get("vision_tile", True)
                and max(h, w) > imgsz * 1.5)
    if not use_tile:
        dets = _run_det(sess, img, imgsz, nc, conf, iou, np)
    else:
        overlap = min(0.9, max(0.0, float(cfg.get("vision_tile_overlap", 0.2))))
        dets = []
        for tx0, ty0, tx1, ty1 in _tile_grid(w, h, imgsz, overlap):
            crop = img[ty0:ty1, tx0:tx1]
            for x0, y0, x1, y1, c, ci in _run_det(sess, crop, imgsz, nc,
                                                  conf, iou, np):
                dets.append((x0 + tx0, y0 + ty0, x1 + tx0, y1 + ty0, c, ci))
        dets = _merge(dets, iou, cfg.get("vision_merge", "wbf"))
    return [(x0 / s, y0 / s, x1 / s, y1 / s, c, ci)
            for x0, y0, x1, y1, c, ci in dets]


def _decode(pred, nc, conf_min, np):
    """-> [(x0, y0, x1, y1, conf, cls)] envelopes in letterboxed pixels."""
    if pred.ndim == 2 and pred.shape[1] in (6, 7) and pred.shape[0] < pred.shape[1] + 10000:
        out = []
        for r in pred:
            if r[4] >= conf_min:
                out.append((float(r[0]), float(r[1]), float(r[2]),
                            float(r[3]), float(r[4]), int(round(r[5]))))
        return out
    if pred.shape[0] < pred.shape[1]:
        pred = pred.T
    C = pred.shape[1]
    has_angle = (C == 4 + nc + 1)
    cls = pred[:, 4:4 + nc]
    conf = cls.max(1)
    cid = cls.argmax(1)
    keep = conf >= conf_min
    pred, conf, cid = pred[keep], conf[keep], cid[keep]
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    if has_angle:
        a = pred[:, 4 + nc]
        dx = np.abs(w / 2 * np.cos(a)) + np.abs(h / 2 * np.sin(a))
        dy = np.abs(w / 2 * np.sin(a)) + np.abs(h / 2 * np.cos(a))
    else:
        dx, dy = w / 2, h / 2
    out = []
    for i in range(len(conf)):
        out.append((float(cx[i] - dx[i]), float(cy[i] - dy[i]),
                    float(cx[i] + dx[i]), float(cy[i] + dy[i]),
                    float(conf[i]), int(cid[i])))
    return out


def _nms(dets, iou_thr):
    dets = sorted(dets, key=lambda d: d[4], reverse=True)
    kept = []
    for d in dets:
        if all(d[5] != k[5] or _iou(d, k) < iou_thr for k in kept):
            kept.append(d)
    return kept


def _soft_nms(dets, iou_thr, sigma=0.5, score_thr=0.05):
    import math
    dets = [tuple(d) for d in dets]
    kept = []
    while dets:
        dets.sort(key=lambda d: d[4], reverse=True)
        best = dets.pop(0)
        kept.append(best)
        rescored = []
        for d in dets:
            if d[5] == best[5]:
                ov = _iou(best, d)
                if ov > 0:
                    d = (d[0], d[1], d[2], d[3],
                         d[4] * math.exp(-(ov * ov) / sigma), d[5])
            if d[4] >= score_thr:
                rescored.append(d)
        dets = rescored
    return kept


def _fuse(members):
    wsum = sum(m[4] for m in members) or 1.0
    return (sum(m[0] * m[4] for m in members) / wsum,
            sum(m[1] * m[4] for m in members) / wsum,
            sum(m[2] * m[4] for m in members) / wsum,
            sum(m[3] * m[4] for m in members) / wsum,
            max(m[4] for m in members), members[0][5])


def _wbf(dets, iou_thr):
    reps, clusters = [], []
    for d in sorted(dets, key=lambda d: d[4], reverse=True):
        for i, rep in enumerate(reps):
            if rep[5] == d[5] and _iou(rep, d) >= iou_thr:
                clusters[i].append(d)
                reps[i] = _fuse(clusters[i])
                break
        else:
            reps.append(tuple(d))
            clusters.append([d])
    return reps


def _merge(dets, iou_thr, mode):
    if mode == "wbf":
        return _wbf(dets, iou_thr)
    if mode == "soft":
        return _soft_nms(dets, iou_thr)
    return _nms(dets, iou_thr)


def _iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _letterbox(img, size, np):
    """Aspect-resize and pad to square -> NCHW blob, (pad_x, pad_y), ratio."""
    h, w = img.shape[:2]
    ratio = min(size / h, size / w)
    nh, nw = int(round(h * ratio)), int(round(w * ratio))
    try:
        import cv2
        resized = cv2.resize(img, (nw, nh))
    except Exception:
        ys = (np.arange(nh) / ratio).astype(int).clip(0, h - 1)
        xs = (np.arange(nw) / ratio).astype(int).clip(0, w - 1)
        resized = img[ys][:, xs]
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[py:py + nh, px:px + nw] = resized
    blob = canvas.astype("float32") / 255.0
    blob = blob.transpose(2, 0, 1)[None]
    return blob, (px, py), ratio
