# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# EN/PL UI switch. Splits `"English / Polski"` halves.

_LANG = "en"


def set_lang(lang):
    """Active UI language: 'en' or 'pl'."""
    global _LANG
    _LANG = "pl" if str(lang).lower().startswith("pl") else "en"


def get_lang():
    return _LANG


def tr(s):
    """Active-language half of a `"English / Polski"` literal."""
    if not isinstance(s, str):
        return s
    parts = s.split(" / ")
    if len(parts) != 2:
        return s
    return parts[1] if _LANG == "pl" else parts[0]


def retranslate(root):
    """Swap static bilingual labels under `root`."""
    from PySide6.QtWidgets import QLabel, QAbstractButton, QGroupBox

    for w in root.findChildren(QLabel):
        _retr(w, w.text, w.setText)
    for w in root.findChildren(QAbstractButton):
        _retr(w, w.text, w.setText)
    for w in root.findChildren(QGroupBox):
        _retr(w, w.title, w.setTitle)


def _retr(w, getter, setter):
    if w.property("i18n_skip"):
        return              # data label
    src = w.property("i18n_src")
    if src is None:
        cur = getter()
        if not isinstance(cur, str) or cur.count(" / ") != 1:
            return          # dynamic label
        src = cur
        w.setProperty("i18n_src", src)
    setter(tr(src))
