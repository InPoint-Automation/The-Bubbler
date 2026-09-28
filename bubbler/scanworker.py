# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Off-thread page scan worker

import sys

import fitz
from PySide6.QtCore import QObject, QRunnable, Signal

from .reader import pipeline
from .reader.vision import runtime
from .gentol import inherit_gtols
from .reader.grammar import scan_normalize
from .reader.parse import scan_parse
from .gentol import page_general_tols
from .reader.geometry import words_in_rect
from .reader.layout import reading_order_lines
from .reader.parse import scan_words
from .reader.textlayer import page_words


def _aug_words(doc, page_i, cfg, cache):
    page = doc[page_i]
    if not cfg.get("vision_assist"):
        return page_words(page)
    if page_i not in cache:
        base = page_words(page)
        words = base
        try:
            words = pipeline.augment_words(page, list(base), cfg)
        except Exception as e:
            print("bubbler: vision assist skipped (%s)" % e, file=sys.stderr)
        cache[page_i] = words
    return cache[page_i]


def _scan_hits(doc, page_i, cfg, words, include_bare=True, allow_vlm=True):
    try:
        hits = pipeline.extract_hits(doc[page_i], cfg, rect=None,
                                   include_bare=include_bare, words=words,
                                   allow_vlm=allow_vlm, on_slow=None)
        if hits is not None:
            return hits
    except Exception as e:
        print("bubbler: extract_hits skipped (%s)" % e, file=sys.stderr)
    return pipeline.drop_zone_labels(
        doc[page_i], scan_words(words, include_bare=include_bare, cfg=cfg),
        words)


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
            words = _aug_words(doc, pg, cfg, vwords)
            try:
                # OCR words on scans
                gtols[pg] = page_general_tols(page, words)
            except Exception:
                gtols[pg] = {}
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
    inherit_gtols(gtols, pages)
    _inherit_offscan(doc, gtols, pages)
    return {"found": found, "gtols": gtols, "any_text": any_text,
            "vwords": vwords}


def _inherit_offscan(doc, gtols, pages):
    if any(gtols.get(pg) for pg in pages):
        return gtols
    try:
        npages = doc.page_count
    except Exception:
        return gtols
    if len(pages) >= npages:
        return gtols
    seen = set(pages)
    for pg in range(npages):
        if pg in seen:
            continue
        try:
            g = page_general_tols(doc[pg])
        except Exception:
            continue
        if g:
            gtols[pg] = g
            inherit_gtols(gtols, list(pages) + [pg])
            del gtols[pg]
            break
    return gtols


def _words_in_rect(words, rx0, ry0, rx1, ry1):
    return words_in_rect(words, rx0, ry0, rx1, ry1)


def _words_text(words):
    return "\n".join(" ".join(l) for l in reading_order_lines(words))


def capture_region(doc, cfg, page_i, rect, sel_rect, want_meta, want_hits,
                   force_read=None, ocr_fallback=False):
    vcache = {}
    words = None
    sel = None
    forced = False
    if force_read:
        try:
            sel = pipeline.read_rect_words(doc[page_i], cfg, sel_rect,
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
    if not sel and ocr_fallback and not force_read:
        # snapped click, empty text layer: read pixels
        try:
            sel = pipeline.read_rect_words(doc[page_i], cfg, sel_rect,
                                         use_vlm=bool(cfg.get("vision_vlm")))
        except Exception as e:
            print("bubbler: click OCR fallback failed (%s)" % e,
                  file=sys.stderr)
            sel = None
        forced = bool(sel)
    text = _words_text(sel)
    out = {"vwords": vcache, "sel": sel, "text": text,
           "meta": None, "hits": None, "forced": forced}
    if not sel:
        return out
    if want_meta and not forced:
        try:
            out["meta"] = pipeline.meta_region_at(doc[page_i], cfg, rect)
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
            hits = pipeline.extract_hits(doc[page_i], cfg, rect=rect,
                                       include_bare=True, words=words,
                                       allow_vlm=True, on_slow=None)
        except Exception as e:
            print("bubbler: extract_hits skipped (%s)" % e, file=sys.stderr)
        if hits is None:
            hits = pipeline.drop_zone_labels(
                doc[page_i], scan_words(sel, include_bare=True, cfg=cfg),
                words)
        if not hits and ocr_fallback:
            try:
                osel = pipeline.read_rect_words(
                    doc[page_i], cfg, sel_rect,
                    use_vlm=bool(cfg.get("vision_vlm")))
            except Exception as e:
                print("bubbler: click OCR retry failed (%s)" % e,
                      file=sys.stderr)
                osel = None
            if osel:
                out["sel"] = osel
                out["text"] = _words_text(osel)
                out["forced"] = True
                hits = scan_words(osel, include_bare=True, cfg=cfg)
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
            runtime.prewarm(self.cfg)
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
                 want_hits, force_read=None, ocr_fallback=False):
        super().__init__()
        self.pdf_path = pdf_path
        self.cfg = cfg
        self.page_i = page_i
        self.rect = rect
        self.sel_rect = sel_rect
        self.want_meta = want_meta
        self.want_hits = want_hits
        self.force_read = force_read
        self.ocr_fallback = ocr_fallback
        self.signals = _CaptureSignals()

    def run(self):
        doc = None
        try:
            doc = fitz.open(self.pdf_path)
            result = capture_region(doc, self.cfg, self.page_i, self.rect,
                                    self.sel_rect, self.want_meta,
                                    self.want_hits, force_read=self.force_read,
                                    ocr_fallback=self.ocr_fallback)
            self.signals.done.emit(result)
        except Exception as e:
            self.signals.failed.emit(str(e))
        finally:
            if doc is not None:
                doc.close()
