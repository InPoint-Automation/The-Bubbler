# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# UI string translation lookup

from .pl import CATALOG as _PL

_LANG = "en"
_CATALOGS = {"pl": _PL}


def set_lang(lang):
    global _LANG
    code = str(lang).lower()[:2]
    _LANG = code if code in _CATALOGS else "en"


def get_lang():
    return _LANG


def available_langs():
    return ("en",) + tuple(_CATALOGS)


def _dual(s):
    parts = s.split(" / ")
    return (parts[0], parts[1]) if len(parts) == 2 else None


def tr(s):
    if not isinstance(s, str):
        return s
    cat = _CATALOGS.get(_LANG)
    if cat is not None and s in cat:
        return cat[s]
    d = _dual(s)
    if d:
        return d[1] if cat is not None else d[0]
    return s


_REV = {lang: {v: k for k, v in cat.items()} for lang, cat in _CATALOGS.items()}


def _in_catalog(key):
    return any(key in cat for cat in _CATALOGS.values())


def translate(text, lang):
    cat = _CATALOGS.get(str(lang)[:2])
    return cat[text] if cat and text in cat else text


def bilingual(en, sep=" / "):
    """'English / Polski' for bilingual sheet else English."""
    pl = translate(en, "pl")
    return "%s%s%s" % (en, sep, pl) if pl != en else en


def sheet_value(en, sheet_lang, stacked=False):
    if sheet_lang == "both":
        return bilingual(en, "\n" if stacked else " / ")
    if sheet_lang in (None, "", "en"):
        return en
    return translate(en, sheet_lang)


def sheet_label(en, sheet_lang):
    """Static label stacks bilingual two lines."""
    return sheet_value(en, sheet_lang, stacked=True)


def english_of(text, prev=None):
    if prev:
        # switch knows text's language
        if prev == "en" and any(text in c for c in _CATALOGS.values()):
            return text
        got = _REV.get(prev, {}).get(text)
        if got is not None:
            return got
    got = _REV.get(_LANG, {}).get(text)
    if got is not None:
        return got
    # key wins over reverse map
    if any(text in cat for cat in _CATALOGS.values()):
        return text
    for rev in _REV.values():
        if text in rev:
            return rev[text]
    return text


def retranslate(root, prev=None):
    """`prev` is language being left."""
    from PySide6.QtWidgets import (QLabel, QAbstractButton, QGroupBox,
                                   QWidget)

    specs = ((QLabel, "text", "setText"),
             (QAbstractButton, "text", "setText"),
             (QGroupBox, "title", "setTitle"))
    for cls, get, setn in specs:
        for w in root.findChildren(cls):
            _retr(w, getattr(w, get), getattr(w, setn), "i18n_src", prev)
    # tooltips separate source prop
    for w in root.findChildren(QWidget):
        _retr(w, w.toolTip, w.setToolTip, "i18n_tip", prev)


def _retr(w, getter, setter, prop, prev=None):
    if w.property("i18n_skip"):
        return
    src = w.property(prop)
    if src is None:
        cur = getter()
        if not isinstance(cur, str) or not cur:
            return
        if _dual(cur):
            src = cur
        else:
            key = english_of(cur, prev)
            if not _in_catalog(key):
                return
            src = key
        w.setProperty(prop, src)
    setter(tr(src))
