#!/usr/bin/env python3
# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Regenerate sheet_template.py from the xlsx, per language.
import base64
import io
import os
import re
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, _REPO)
from bubbler.i18n import translate, available_langs         # noqa: E402

_T_RE = re.compile(r"(<t[^>]*>)(.*?)(</t>)", re.S)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _unesc(s):
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


def _localize(inner, lang):
    if " / " in inner:
        parts = inner.split(" / ")
        if len(parts) == 2:
            en, other = parts
            if lang == "both":
                return inner
            if lang == "en":
                return en
            if lang == "pl":
                return other
            key = _unesc(en)
            t = translate(key, lang)
            return _esc(t) if t != key else en
    if lang in ("both", "en"):
        return inner
    key = _unesc(inner)
    t = translate(key, lang)
    return _esc(t) if t != key else inner


def _build(src_bytes, lang):
    zin = zipfile.ZipFile(io.BytesIO(src_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/sharedStrings.xml":
                xml = data.decode("utf-8")
                xml = _T_RE.sub(
                    lambda m: m.group(1) + _localize(m.group(2), lang)
                    + m.group(3), xml)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    return buf.getvalue()


def main():
    src = (sys.argv[1] if len(sys.argv) > 1
           else os.path.join(_HERE, "inspection_sheet_template.xlsx"))
    out = os.path.join(_REPO, "bubbler", "sheet_template.py")
    src_bytes = open(src, "rb").read()
    langs = ["both"] + [l for l in available_langs() if l != "both"]

    with open(out, "w", encoding="utf-8") as f:
        f.write("TEMPLATES = {}\n\n")
        for lang in langs:
            b64 = base64.b64encode(_build(src_bytes, lang)).decode("ascii")
            f.write('TEMPLATES[%r] = """\\\n' % lang)
            for i in range(0, len(b64), 76):
                f.write(b64[i:i + 76] + "\n")
            f.write('"""\n\n')
        f.write('TEMPLATE_B64 = TEMPLATES["both"]\n')
    print("%s written: %s" % (out, ", ".join(langs)))


if __name__ == "__main__":
    main()
