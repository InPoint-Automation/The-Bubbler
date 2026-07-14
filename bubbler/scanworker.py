# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Off-thread page scan worker. Own fitz.Document per task.

import sys

import fitz
from PySide6.QtCore import QObject, QRunnable, Signal

from . import vision
from .scanlib import scan_normalize, scan_parse, parse_general_tols
from .scanpos import scan_words, page_words


def _aug_words(doc, page_i, cfg, cache):
    page = doc[page_i]
    if not cfg.get("vision_assist"):
        return page_words(page)
    if page_i not in cache:
        base = page_words(page)
        words = base
        try:
            words = vision.augment_words(page, list(base), cfg)
        except Exception as e:
            print("bubbler: vision assist skipped (%s)" % e, file=sys.stderr)
        cache[page_i] = words
    return cache[page_i]


def _scan_hits(doc, page_i, cfg, words, include_bare=True, allow_vlm=True):
    try:
        hits = vision.extract_hits(doc[page_i], cfg, rect=None,
                                   include_bare=include_bare, words=words,
                                   allow_vlm=allow_vlm, on_slow=None)
        if hits is not None:
            return hits
    except Exception as e:
        print("bubbler: extract_hits skipped (%s)" % e, file=sys.stderr)
    return scan_words(words, include_bare=include_bare, cfg=cfg)


def scan_pages(doc, cfg, pages, progress=None, cancelled=None):
    found = []
    gtols = {}
    vwords = {}
    any_text = False
    total = len(pages)
    for i, pg in enumerate(pages):
        if cancelled is not None and cancelled():
            return None
        try:
            page = doc[pg]
            try:
                gtols[pg] = parse_general_tols(page.get_text("text"))
            except Exception:
                gtols[pg] = {}
            words = _aug_words(doc, pg, cfg, vwords)
            if words:
                any_text = True
                pos_hits = _scan_hits(doc, pg, cfg, words)
                if pos_hits:
                    found.extend((pg, h) for h in pos_hits)
                    if progress is not None:
                        progress(i + 1, total)
                    continue
            try:
                raw = page.get_text("text")
            except Exception:
                raw = ""
            if raw.strip():
                any_text = True
                for h in scan_parse(scan_normalize(raw), cfg):
                    found.append((pg, h))
        except Exception as e:
            print("bubbler: page %d scan skipped (%s)" % (pg, e),
                  file=sys.stderr)
        if progress is not None:
            progress(i + 1, total)
    return {"found": found, "gtols": gtols, "any_text": any_text,
            "vwords": vwords}


def _words_in_rect(words, rx0, ry0, rx1, ry1):
    out = []
    for w in words:
        wx0, wy0, wx1, wy1 = w[0], w[1], w[2], w[3]
        ix = min(rx1, wx1) - max(rx0, wx0)
        iy = min(ry1, wy1) - max(ry0, wy0)
        if ix <= 0 or iy <= 0:
            continue
        area = max((wx1 - wx0) * (wy1 - wy0), 1e-6)
        cx, cy = (wx0 + wx1) / 2.0, (wy0 + wy1) / 2.0
        if (ix * iy) / area >= 0.30 or (rx0 <= cx <= rx1 and ry0 <= cy <= ry1):
            out.append(w)
    return out


def _words_text(words):
    words = sorted(words, key=lambda w: (w[5], w[6], w[7]))
    lines, key = [], None
    for w in words:
        k = (w[5], w[6])
        if k != key:
            lines.append([])
            key = k
        lines[-1].append(w[4])
    return "\n".join(" ".join(l) for l in lines)


def capture_region(doc, cfg, page_i, rect, sel_rect, want_meta, want_hits,
                   force_read=None):
    vcache = {}
    words = None
    sel = None
    forced = False
    if force_read:
        try:
            sel = vision.read_rect_words(doc[page_i], cfg, sel_rect,
                                         use_vlm=(force_read == "vlm"))
        except Exception as e:
            print("bubbler: forced capture read failed (%s)" % e,
                  file=sys.stderr)
            sel = None
        forced = bool(sel)
        if not forced:
            sel = None
    if sel is None:
        words = _aug_words(doc, page_i, cfg, vcache)
        sel = _words_in_rect(words, *sel_rect)
    text = _words_text(sel)
    out = {"vwords": vcache, "sel": sel, "text": text,
           "meta": None, "hits": None, "forced": forced}
    if not sel:
        return out
    if want_meta and not forced:
        try:
            out["meta"] = vision.meta_region_at(doc[page_i], cfg, rect)
        except Exception:
            out["meta"] = None
        if out["meta"]:
            return out
    if want_hits:
        if forced:
            out["hits"] = scan_words(sel, include_bare=True, cfg=cfg)
            return out
        hits = None
        try:
            hits = vision.extract_hits(doc[page_i], cfg, rect=rect,
                                       include_bare=True, words=words,
                                       allow_vlm=True, on_slow=None)
        except Exception as e:
            print("bubbler: extract_hits skipped (%s)" % e, file=sys.stderr)
        if hits is None:
            hits = scan_words(sel, include_bare=True, cfg=cfg)
        out["hits"] = hits
    return out


class _Signals(QObject):
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)


class ScanTask(QRunnable):

    def __init__(self, pdf_path, cfg, pages, cancelled):
        super().__init__()
        self.pdf_path = pdf_path
        self.cfg = cfg
        self.pages = pages
        self._cancelled = cancelled
        self.signals = _Signals()

    def run(self):
        doc = None
        try:
            doc = fitz.open(self.pdf_path)
            result = scan_pages(doc, self.cfg, self.pages,
                                progress=self.signals.progress.emit,
                                cancelled=self._cancelled)
            self.signals.done.emit(result)
        except Exception as e:
            self.signals.failed.emit(str(e))
        finally:
            if doc is not None:
                doc.close()


class _PrewarmSignals(QObject):
    done = Signal()


class PrewarmTask(QRunnable):

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.signals = _PrewarmSignals()

    def run(self):
        try:
            vision.prewarm(self.cfg)
        except Exception:
            pass
        try:
            self.signals.done.emit()
        except RuntimeError:
            pass


class _CaptureSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class CaptureTask(QRunnable):

    def __init__(self, pdf_path, cfg, page_i, rect, sel_rect, want_meta,
                 want_hits, force_read=None):
        super().__init__()
        self.pdf_path = pdf_path
        self.cfg = cfg
        self.page_i = page_i
        self.rect = rect
        self.sel_rect = sel_rect
        self.want_meta = want_meta
        self.want_hits = want_hits
        self.force_read = force_read
        self.signals = _CaptureSignals()

    def run(self):
        doc = None
        try:
            doc = fitz.open(self.pdf_path)
            result = capture_region(doc, self.cfg, self.page_i, self.rect,
                                    self.sel_rect, self.want_meta,
                                    self.want_hits, force_read=self.force_read)
            self.signals.done.emit(result)
        except Exception as e:
            self.signals.failed.emit(str(e))
        finally:
            if doc is not None:
                doc.close()
