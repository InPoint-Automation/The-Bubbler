# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# UI translation

from .pl import CATALOG as _PL

_LANG = "en"
_CATALOGS = {"pl": _PL}


def set_lang(lang):
    """Active UI language code (e.g. 'en', 'pl')."""
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
    """Active-language string for an English key"""
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
    """Translate an English key into a specific language."""
    cat = _CATALOGS.get(str(lang)[:2])
    return cat[text] if cat and text in cat else text


def bilingual(en):
    """'English / Polski' for the bilingual sheet, or just English if no PL."""
    pl = translate(en, "pl")
    return "%s / %s" % (en, pl) if pl != en else en


def sheet_value(en, sheet_lang):
    """Localize a data value for the xlsx: both | en | <lang code>."""
    if sheet_lang == "both":
        return bilingual(en)
    if sheet_lang in (None, "", "en"):
        return en
    return translate(en, sheet_lang)


def english_of(text):
    """Recover the English key from a rendered string"""
    if _LANG == "en":
        return text
    return _REV.get(_LANG, {}).get(text, text)


def retranslate(root):
    """Re-apply the active language to static labels + tooltips"""
    from PySide6.QtWidgets import (QLabel, QAbstractButton, QGroupBox,
                                   QWidget)

    specs = ((QLabel, "text", "setText"),
             (QAbstractButton, "text", "setText"),
             (QGroupBox, "title", "setTitle"))
    for cls, get, setn in specs:
        for w in root.findChildren(cls):
            _retr(w, getattr(w, get), getattr(w, setn), "i18n_src")
    # tooltips on any widget, separate source property
    for w in root.findChildren(QWidget):
        _retr(w, w.toolTip, w.setToolTip, "i18n_tip")


def _retr(w, getter, setter, prop):
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
            key = english_of(cur)
            if not _in_catalog(key):
                return
            src = key
        w.setProperty(prop, src)
    setter(tr(src))
