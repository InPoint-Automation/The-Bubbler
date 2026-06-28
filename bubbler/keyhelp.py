# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# F1 help: keybinding data + HTML renderer.

from .i18n import tr


# Keybinding reference data.
KEY_GROUPS = [
    ("Mouse / Mysz", [
        ("Click (Add)", "Read callout: OCR/VLM + bubble / odczyt"),
        ("Drag empty (Add)", "Capture text region: OCR/VLM / przechwyć"),
        ("Click bubble", "Select / zaznacz"),
        ("Drag bubble", "Move numeral / przesuń numer"),
        ("Drag anchor dot", "Move leader tip / przesuń grot"),
        ("Drag empty (Select)", "Marquee multi-select / ramką"),
        ("Double-click bubble", "Edit (sub-row picker) / edytuj"),
        ("Right-click bubble", "Menu: edit - sub-rows - delete"),
        ("Shift+Click", "Quick bubble (sticky values) / szybki"),
        ("Alt+Shift+Click", "Quick bubble, nominal read from drawing / "
                            "auto nominał"),
        ("Ctrl+Click bubble", "Delete (Add) - toggle select (Select)"),
        ("Alt+Click", "Plain bubble, no prediction / bez odczytu"),
        ("Wheel", "Scroll - Ctrl+Wheel = zoom at cursor"),
        ("Middle / Right drag", "Pan / przesuń"),
    ]),
    ("Keys / Klawisze", [
        ("Ctrl+Z / Ctrl+Y", "Undo / redo - cofnij / ponów"),
        ("Ctrl+S", "Save / zapisz"),
        ("Home", "Fit / dopasuj"),
        ("PgUp / PgDn", "Page / strona"),
        ("+ / -", "Zoom"),
        ("A / V", "Add / Select tool"),
        ("M", "Measure walk / pomiar"),
        ("B", "Bubble panel / panel"),
        ("Q", "Quick access bar / pasek"),
        ("Del", "Delete selected / usuń"),
        ("Esc", "Cancel - clear selection / anuluj"),
        ("F1", "This help / pomoc"),
    ]),
    ("Hotbar - Add tool / Dodawanie", [
        ("1 - 7", "Type / typ"),
        ("T", "Tier"),
        ("I", "ISO 2768 auto"),
        ("D", "Decimal tol / tol. dziesiętna"),
        ("L", "Leaders / linie"),
        ("P", "Pin = Ø"),
        ("S", "Snap to geometry / przyciąganie"),
        ("V", "Select tool"),
        ("←↑→↓", "Bubble offset direction / kierunek"),
    ]),
    ("Hotbar - Select tool / Zaznaczanie", [
        ("A", "Add tool"),
        ("R / C", "Align row / column - w rząd / kolumnę"),
        ("H / W", "Distribute H / V - rozłóż"),
        ("Del", "Delete / usuń"),
        ("Esc", "Clear selection / wyczyść"),
    ]),
    ("Measure walk / Pomiar", [
        ("Enter", "Save + next / zapisz + dalej"),
        ("Shift+Enter", "Back / wstecz"),
        ("Tab", "Skip / pomiń"),
        ("Click bubble", "Jump to it / skocz"),
        ("Esc", "Exit / wyjście"),
    ]),
]

KEY_NOTES = [
    ("Leaders / Linie", "The dialog's 'Leader line' box decides whether a "
     "balloon gets a line (default = ribbon state). Editing a bubble can "
     "add/remove its leader; turning it on offsets the numeral automatically."),
    ("Bubble offset / Odsunięcie", "Captured & scanned bubbles step off the "
     "callout box in the preferred direction (arrow keys), dodging text, "
     "fills, thick edges and other bubbles. Thin leader / dimension lines are "
     "not avoided."),
    ("Capture / Przechwytywanie", "Click or drag a callout to read it "
     "(OCR/VLM) and bubble it; Alt+click drops a plain bubble with no read. "
     "Bare numbers always bubble - they take the ribbon's sticky type and the "
     "title block's general tolerance. With the header editor open, a drag "
     "fills the focused field instead."),
]


def _keybinds_html():
    """Render KEY_GROUPS / KEY_NOTES as light-themed grouped tables."""
    p = ["<body style='font-family:\"Segoe UI\",Arial; font-size:10pt; "
         "color:#1e1e1e;'>"]
    for title, rows in KEY_GROUPS:
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
    p.append("<h3 style='color:#2b579a; margin:12px 0 2px;'>Notes / Uwagi</h3>")
    for title, body in KEY_NOTES:
        p.append("<p style='margin:4px 0;'><b>%s</b> - %s</p>" % (title, body))
    p.append("</body>")
    return "".join(p)
