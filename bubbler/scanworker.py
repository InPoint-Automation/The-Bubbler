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


# Pure passes

def _aug_words(doc, page_i, cfg, cache):
    """Page words plus vision-recovered words, cached per page."""
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
    """Vision hits, else scan_words fallback."""
    try:
        hits = vision.extract_hits(doc[page_i], cfg, rect=None,
                                   include_bare=include_bare, words=words,
                                   allow_vlm=allow_vlm, on_slow=None)
        if hits is not None:
            return hits
    except Exception as e:
        print("bubbler: extract_hits skipped (%s)" % e, file=sys.stderr)
    return scan_words(words, include_bare=include_bare)


def scan_pages(doc, cfg, pages, progress=None, cancelled=None):
    """Scan passes over `pages`. None if cancelled."""
    found = []
    gtols = {}
    vwords = {}
    any_text = False
    total = len(pages)
    for i, pg in enumerate(pages):
        if cancelled is not None and cancelled():
            return None
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
            for h in scan_parse(scan_normalize(raw)):
                found.append((pg, h))
        if progress is not None:
            progress(i + 1, total)
    return {"found": found, "gtols": gtols, "any_text": any_text,
            "vwords": vwords}


# Single-region capture

def _words_in_rect(words, rx0, ry0, rx1, ry1):
    """Words overlapping the capture rect."""
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
    """Reading-order text of the words."""
    words = sorted(words, key=lambda w: (w[5], w[6], w[7]))
    lines, key = [], None
    for w in words:
        k = (w[5], w[6])
        if k != key:
            lines.append([])
            key = k
        lines[-1].append(w[4])
    return "\n".join(" ".join(l) for l in lines)


def capture_region(doc, cfg, page_i, rect, sel_rect, want_meta, want_hits):
    """Vision passes for one region. Meta short-circuits hits."""
    vcache = {}
    words = _aug_words(doc, page_i, cfg, vcache)
    sel = _words_in_rect(words, *sel_rect)
    text = _words_text(sel)
    out = {"vwords": vcache, "sel": sel, "text": text,
           "meta": None, "hits": None}
    if not sel:
        return out
    if want_meta:
        try:
            out["meta"] = vision.meta_region_at(doc[page_i], cfg, rect)
        except Exception:
            out["meta"] = None
        if out["meta"]:
            return out
    if want_hits:
        hits = None
        try:
            hits = vision.extract_hits(doc[page_i], cfg, rect=rect,
                                       include_bare=True, words=words,
                                       allow_vlm=True, on_slow=None)
        except Exception as e:
            print("bubbler: extract_hits skipped (%s)" % e, file=sys.stderr)
        if hits is None:
            hits = scan_words(sel, include_bare=True)
        out["hits"] = hits
    return out


# Qt worker

class _Signals(QObject):
    progress = Signal(int, int)    # pages done, total
    done = Signal(object)          # result dict, or None if cancelled
    failed = Signal(str)


class ScanTask(QRunnable):
    """Runs scan_pages on a pool thread against its own fitz.Document."""

    def __init__(self, pdf_path, cfg, pages, cancelled):
        super().__init__()
        self.pdf_path = pdf_path
        self.cfg = cfg
        self.pages = pages
        self._cancelled = cancelled    # callable -> bool, polled per page
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


class _CaptureSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class CaptureTask(QRunnable):
    """Runs capture_region on a pool thread against its own fitz.Document."""

    def __init__(self, pdf_path, cfg, page_i, rect, sel_rect, want_meta,
                 want_hits):
        super().__init__()
        self.pdf_path = pdf_path
        self.cfg = cfg
        self.page_i = page_i
        self.rect = rect
        self.sel_rect = sel_rect
        self.want_meta = want_meta
        self.want_hits = want_hits
        self.signals = _CaptureSignals()

    def run(self):
        doc = None
        try:
            doc = fitz.open(self.pdf_path)
            result = capture_region(doc, self.cfg, self.page_i, self.rect,
                                    self.sel_rect, self.want_meta,
                                    self.want_hits)
            self.signals.done.emit(result)
        except Exception as e:
            self.signals.failed.emit(str(e))
        finally:
            if doc is not None:
                doc.close()
