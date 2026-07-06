# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# F1 help: keybinding data + HTML renderer.

from .i18n import tr


def _key_groups():
    return [
        (tr('Mouse'), [
            ("Click (Add)", tr('Read callout: OCR/VLM + bubble')),
            ("Drag empty (Add)", tr('Capture text region: OCR/VLM')),
            ("Click bubble", tr('Select')),
            ("Drag bubble", tr('Move numeral')),
            ("Drag anchor dot", tr('Move leader tip')),
            ("Drag empty (Select)", tr('Marquee multi-select')),
            ("Double-click bubble", tr('Edit (sub-row picker)')),
            ("Right-click bubble", tr('Menu: edit, sub-rows, delete')),
            ("Shift+Click", tr('Quick bubble (sticky values)')),
            ("Alt+Shift+Click", tr('Quick bubble, nominal read from drawing')),
            ("Ctrl+Click bubble", tr('Delete (Add), toggle select (Select)')),
            ("Alt+Click", tr('Plain bubble, no prediction')),
            ("Wheel", tr('Scroll; Ctrl+Wheel = zoom at cursor')),
            ("Middle", tr('Pan')),
        ]),
        (tr('Keys'), [
            ("Ctrl+Z", tr('Undo / redo')),
            ("Ctrl+S", tr('Save')),
            ("Home", tr('Fit')),
            ("PgUp", tr('Page')),
            ("+ / -", tr('Zoom')),
            ("A / V", tr('Add')),
            ("M", tr('Measure walk')),
            ("B", tr('Bubble panel')),
            ("Q", tr('Quick access bar')),
            ("Del", tr('Delete selected')),
            ("Esc", tr('Cancel, clear selection')),
            ("F1", tr('This help')),
        ]),
        (tr('Hotbar - Add tool'), [
            ("1 - 7", tr('Type')),
            ("T", tr('Tier')),
            ("I", tr('ISO 2768 auto')),
            ("D", tr('Decimal tol')),
            ("L", tr('Leaders')),
            ("P", u"Pin = Ø"),
            ("S", tr('Snap to geometry')),
            ("V", tr('Select tool')),
            (u"←↑→↓", tr('Bubble offset direction')),
        ]),
        (tr('Hotbar - Select tool'), [
            ("A", tr('Add tool')),
            ("R", tr('Align row / column')),
            ("H", tr('Distribute H')),
            ("Del", tr('Delete')),
            ("Esc", tr('Clear selection')),
        ]),
        (tr('Measure walk'), [
            ("Enter", tr('Save + next')),
            ("Shift+Enter", tr('Back')),
            ("Tab", tr('Skip')),
            ("Click bubble", tr('Jump to it')),
            ("Esc", tr('Exit')),
        ]),
    ]


def _key_notes():
    return [
        (tr('Leaders'), tr(
            "The dialog's 'Leader line' box decides whether a balloon gets a "
            "line (default = ribbon state). Editing a bubble can add/remove "
            "its leader; turning it on offsets the numeral automatically.")),
        (tr('Bubble offset'), tr(
            "Captured and scanned bubbles step off the callout box in the "
            "preferred direction (arrow keys), dodging text, fills, thick "
            "edges and other bubbles. Thin leader / dimension lines are not "
            "avoided.")),
        (tr('Capture'), tr(
            "Click or drag a callout to read it (OCR/VLM) and bubble it; "
            "Alt+click drops a plain bubble with no read. Bare numbers always "
            "bubble; they take the ribbon's sticky type and the title block's "
            "general tolerance. With the header editor open, a drag fills the "
            "focused field instead.")),
    ]


def _keybinds_html():
    p = ["<body style='font-family:\"Segoe UI\",Arial; font-size:10pt; "
         "color:#1e1e1e;'>"]
    for title, rows in _key_groups():
        p.append("<h3 style='color:#2b579a; margin:10px 0 2px;'>%s</h3>"
                 % title)
        p.append("<table width='100%' cellspacing='0' cellpadding='3'>")
        for i, (k, desc) in enumerate(rows):
            bg = "#eef3fa" if i % 2 else "#ffffff"
            p.append("<tr style='background:%s;'>"
                     "<td width='40%%' style='font-family:Consolas,monospace;"
                     "font-weight:bold; color:#1f3f73;'>%s</td>"
                     "<td>%s</td></tr>" % (bg, k, desc))
        p.append("</table>")
    p.append("<h3 style='color:#2b579a; margin:12px 0 2px;'>%s</h3>"
             % tr('Notes'))
    for title, body in _key_notes():
        p.append("<p style='margin:4px 0;'><b>%s</b> - %s</p>" % (title, body))
    p.append("</body>")
    return "".join(p)
