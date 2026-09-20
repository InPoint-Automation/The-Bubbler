# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Polish translation catalog

CATALOG = {
    # ribbon gentol + hotbar leader
    'gen tol': 'tol. og.',
    'General tolerance in force on this page': 'Tolerancja ogólna obowiązująca na tej stronie',
    'General tolerance read from page 1 and reused here': 'Tolerancja ogólna odczytana ze strony 1 i użyta tutaj',
    'Leader on/off': 'Linia wł/wył',
    'Reset': 'Reset',
    'Reset these to defaults': 'Przywróć domyślne',
    'auto': 'auto',
    'band table': 'tabela pasm',
    'inherited': 'dziedziczona',
    'leaders off for %d bubble(s)': 'linie wyłączone dla %d bąbli',
    'leaders on for %d bubble(s)': 'linie włączone dla %d bąbli',
    'next-bubble options reset': 'opcje następnego bąbla zresetowane',
    'no general tol': 'brak tol. ogólnej',
    'printed .X block': 'blok .X z rysunku',
    'printed fractions': 'ułamki z rysunku',
    'settings ISO 2768': 'ISO 2768 z ustawień',
    'settings ladder': 'drabinka z ustawień',
    # inspection-sheet labels
    'Inspection Sheet': 'Karta kontroli',
    'Part Name': 'Nazwa',
    # title block rows 3-7
    'Part #': 'Nr części',
    # RETIRED spelling for sheet.RETIRED_LABEL_KEYS
    'FAIR #': 'Nr FAIR',
    'Drawing #': 'Nr rysunku',
    'Dwg Rev': 'Rew. rysunku',
    'Part Rev': 'Rew. części',
    'PO #': 'Nr zamówienia',
    'Serial/Lot': 'Nr seryjny/partia',
    'Inspector': 'Kontroler',
    'Inspection type': 'Typ kontroli',
    # RETIRED spelling for sheet._renderings
    'FAI type': 'Typ FAI',
    'Stage': 'Etap',
    # counters
    'Pass:': 'Zgodne:',
    'Fail:': 'Niezgodne:',
    'Yield:': 'Uzysk:',
    'Open:': 'Pozostało:',
    # column headers
    'bubble#': 'nr balonu',
    'nominal': 'nominał',
    'pin Ø': 'trzpień Ø',
    'offset': 'odsunięcie',
    'designator': 'oznaczenie',
    'NCR #': 'Nr NCR',
    'Material': 'Materiał',
    'Date': 'Data',
    'Chars:': 'Cechy:',
    'Measured:': 'Pomiary:',
    'feature': 'cecha',
    'requirement': 'wymaganie',
    'deviation': 'odchyłka',
    'method': 'metoda',
    'bench-target': 'cel',
    'measured': 'pomiar',
    'result': 'wynik',
    'inspector': 'kontroler',
    'date': 'data',
    'comments': 'uwagi',
    'dim': 'wymiar',
    'hole': 'otwór',
    'thread': 'gwint',
    'thru': 'przelot',
    'slot': 'rowek',
    'depth': 'głębokość',
    'position': 'pozycja',
    'finish': 'wykończenie',
    'holes Ø': 'otwory',
    'positions': 'pozycje',
    'threads': 'gwinty',
    'other': 'inne',
    '#%s OUT OF TOL %s': 'poza tolerancją %s %s',
    '%d selected': 'zaznaczono %d',
    '%d unsaved row(s). Quit anyway?': '%d niezapisanych wierszy. Wyjść mimo to?',
    '%s\n\nSheet rows are saved; the ballooned PDF was not written. Close it in your PDF viewer and save again.': '%s\n\nWiersze zapisane; zamknij PDF w przeglądarce i zapisz ponownie.',
    '%s - no bubble (Alt-click to add)': '%s - bez bąbla (Alt-klik)',
    '%s - open': '%s - otwórz',
    '%s: needs nominal ≤ 500 mm': '%s: wymaga nominału ≤ 500 mm',
    '(default)': '(domyślny)',
    '- keep': 'bez zmian -',
    'Accent color': 'Kolor',
    'Accept checked': 'Zatwierdź',
    'Add': 'dodaj',
    'Add sub-dim': 'Podwymiar',
    'Add sub-row': 'Dodaj podwiersz',
    'Add tool': 'Dodawanie',
    'Advanced': 'Zaawansowany',
    'Align': 'Wyrównaj',
    'Align col': 'W kolumnę',
    'Align row': 'W rząd',
    'All %d as sub-rows': 'Wszystkie %d jako podwiersze',
    'Apply': 'Zastosuj',
    'Arrange': 'Rozmieść',
    'Available gages': 'Dostępne przyrządy:',
    'Back': 'wstecz',
    'Block min confidence': 'Min. pewność bloku',
    'Browse...': 'Przeglądaj...',
    'Bubble offset': 'Odsunięcie',
    'Bubble offset direction': 'kierunek',
    'Bubble panel': 'panel',
    'Bubbles': 'Bąble',
    'Bubbler read': 'Odczyt Bubblera',

    # Settings tabs + gentol control
    'General': 'Ogólne',
    'Gages': 'Przyrządy',
    'Vision': 'Wizja',
    'Tolerances': 'Tolerancje',
    'class': 'klasa',
    'Tiers': 'Poziomy',
    'Shape-code criticality tiers (colour-blind safe)':
        'Koduj poziomy krytyczności kształtem (bezpieczne dla daltonistów)',
    'On: tiers differ by shape as well as colour. '
    'Off: all balloons are circles (colour only).':
        'Wł.: poziomy różnią się kształtem i kolorem. '
        'Wył.: wszystkie bąble to koła (tylko kolor).',
    'Auto-assign tier by callout type':
        'Automatyczny poziom wg typu elementu',
    'Set each bubble tier from its callout type':
        'Ustaw poziom bąbla wg jego typu',
    "Only fills the tier when the ribbon "
    "'Next bubble' tier is blank; a tier picked "
    "on the ribbon always wins. Off: blank stays "
    "blank.":
        'Uzupełnia poziom tylko wtedy, gdy poziom '
        '"Następny bąbel" na wstążce jest pusty; poziom wybrany '
        'na wstążce zawsze wygrywa. Wył.: pusty zostaje pusty.',
    # tier data identifiers (xlsx)
    'red': 'czerwony',
    'blue': 'niebieski',
    'green': 'zielony',
    'BASIC or REF: no general tolerance':
        'BASIC / REF: brak tolerancji ogólnej',
    'ASME title-block decimal-place tolerance':
        'Tolerancja z tabeli tytułowej (miejsca dziesiętne)',
    'Bulk edit': 'Grupowo',
    'Bulk edit checked': 'Grupowo',
    'CBore depth needs CBore Ø': 'pogłębienie wymaga Ø',
    'CMM if tol ≤': 'CMM gdy tol ≤',
    'Cancel': 'Anuluj',
    'Cancel - clear selection': 'anuluj',
    'Capture': 'Przechwytywanie',
    'Capture failed: %s': 'Nieudane:\n%s',
    'Capture radius must be a number > 0': 'Promień musi być liczbą > 0',
    'Captured & scanned bubbles step off the callout box in the preferred direction (arrow keys), dodging text, fills, thick edges and other bubbles. Thin leader': 'dimension lines are not avoided.',
    'Check all': 'Zaznacz',
    'Clear sel.': 'Wyczyść',
    'Clear selection': 'wyczyść',
    'Close': 'Zamknij',
    'Company': 'Firma',
    'Could not write\n%s\n\n%s\n\nYour bubbles are NOT being saved to disk. Check free space, permissions, or whether the file is locked - Bubbler retries on the next change.': 'Nie można zapisać\n%s\n\n%s\n\nBąble NIE są zapisywane na dysk.',
    'Decimal tol': 'tol. dziesiętna',
    'Decimal-place tolerances must be numbers': 'muszą być liczbami',
    'Default type': 'Typ',
    'Delete': 'usuń',
    'Delete %d bubble(s)?': 'Usunąć %d bąbli?',
    'Delete bubble': 'Usuń bąbel',
    'Delete selected': 'usuń',
    'Delete sub-row': 'Usuń podwiersz',
    'Delete sub-row #%s (%s)?': 'Usunąć podwiersz #%s (%s)?',
    'Distribute H': 'Rozłóż H',
    'Type: %s': 'Typ: %s',

    # Settings hints (settings_mixin._hint)
    'Fills the header of a new sheet and the report, so it is not retyped per drawing.':
        'Wypełnia nagłówek nowego arkusza i raportu, więc nie trzeba go wpisywać przy każdym rysunku.',
    'Block detector (gdt_regions.onnx) not '
    'installed; callout grouping uses geometry.':
        'Detektor bloków (gdt_regions.onnx) nie jest zainstalowany; '
        'grupowanie wymiarów korzysta z geometrii.',
    'Florence-2 VLM pack not installed; use '
    "'Download VLM model' above to fetch one.":
        'Pakiet VLM Florence-2 nie jest zainstalowany; użyj '
        '"Pobierz model VLM" powyżej, aby go pobrać.',
    'Needs an NVIDIA GPU, driver >= 580, and system '
    'python3. Uses your CUDA, else downloads it '
    '(~1.4 GB). Detectors only; OCR/VLM stay CPU.':
        'Wymaga karty NVIDIA, sterownika >= 580 i systemowego '
        'python3. Używa twojej CUDA, w przeciwnym razie pobiera ją '
        '(~1,4 GB). Tylko detektory; OCR i VLM zostają na CPU.',
    'Execution provider in use: %s   (available: %s)':
        'Używany dostawca wykonania: %s   (dostępne: %s)',
    'GPU + CPU': 'GPU + CPU',
    'CPU only': 'tylko CPU',
    'Diagnostics log: %s': 'Dziennik diagnostyczny: %s',
    'Off by default. Records (crop + fields, drawing '
    'name never stored) stay local and are never sent '
    'automatically. Export from the Data menu to share, '
    'or train locally (see DEV.md).':
        'Domyślnie wyłączone. Zapisy (wycinek + pola, nazwa rysunku '
        'nigdy nie jest zapisywana) zostają lokalnie i nigdy nie są '
        'wysyłane automatycznie. Eksportuj z menu Dane, aby je '
        'udostępnić, albo trenuj lokalnie (zobacz DEV.md).',
    'Set type, gage and tolerance on all checked rows':
        'Ustaw typ, przyrząd i tolerancję we wszystkich zaznaczonych wierszach',
    'OCR and symbol passes need the vision build; '
    'geometry pass works now.':
        'Przebiegi OCR i symboli wymagają wersji z wizją; '
        'przebieg geometryczny działa już teraz.',
    'Distribute V': 'Rozłóż V',
    'Drag a GREEN box around the area to scan, then a RED box over any detail to ignore. Enter skips a box, Esc cancels.': 'Przeciągnij ZIELONE pole wokół obszaru do skanowania, potem CZERWONE na szczegół do pominięcia. Enter pomija, Esc anuluje.',
    'Edit': 'Edycja',
    'Edit #%s': 'Edytuj #%s',
    'Edit (sub-row picker)': 'edytuj',
    'Edit sub-row': 'Edytuj podwiersz',
    'Error': 'Błąd',
    'Exit': 'wyjście',
    'Feature': 'Cecha',
    'File': 'Plik',
    'Fit': 'dopasuj',
    'Fit %s needs nominal': 'pasowanie %s wymaga nominału',
    'GPU': 'Execution provider',
    'Gage': 'Przyrząd',
    'Gage tolerance thresholds must be positive numbers': 'Progi muszą być dodatnie',
    'Group': 'Grupa',
    'H': 'W',
    'Header': 'Nagłówek',
    'Hole #%d needs X and Y': 'otwór #%d wymaga X i Y',
    'Hole XY+Ø sub-rows': 'Podwiersze XY+Ø',
    'Hole pin Ø = nominal': 'Pin = nominał',
    'Hotbar - Add tool': 'Dodawanie',
    'Hotbar - Select tool': 'Zaznaczanie',
    'ISO 286: %s not supported at %g mm': 'ISO 286: %s nieobsługiwane przy %g mm',
    'Inspection sheet': 'Karta kontroli (xlsx)',
    # rebuild retired-template workbook
    '%s was made by an older Bubbler.\n\nRebuild it on the current sheet? Your title block and measurements are kept, and a copy is saved next to it. Rows or columns you added, and custom formatting, are NOT kept.':
        '%s został utworzony przez starszą wersję Bubblera.\n\nPrzebudować na bieżącej karcie? Tabliczka i pomiary zostaną zachowane, a kopia zapisana obok. Wiersze i kolumny dodane ręcznie oraz własne formatowanie NIE zostaną zachowane.',
    'Rebuild failed: %s':
        'Przebudowa nie powiodła się: %s',
    'Invert from opposite edge': 'Odwróć',
    'Invert needs overall': 'wymiar całkowity',
    'Jump to it': 'skocz',
    'Keybinds': 'Skróty',
    'Keys': 'Klawisze',
    'Language': 'Język',
    'Leader line': 'Linia odniesienia',
    'Leaders': 'Linie',
    'Line width threshold must be a number >= 0': 'Próg grubości musi być liczbą >= 0',
    'MEASURE MODE': 'TRYB POMIARU',
    'Marquee multi-select': 'ramką',
    'Measure': 'Pomiar',
    'Measure walk': 'pomiar',
    'Micrometer if tol ≤': 'Mikrometr gdy ≤',
    'Mode': 'Tryb',
    'Mouse': 'Mysz',
    'Move leader tip': 'przesuń grot',
    'Move numeral': 'przesuń numer',
    'Next bubble': 'Następny',
    'No callouts in the selected area': 'Brak elementów w zaznaczonym obszarze.',
    'No callouts recognized': 'Nie rozpoznano.',
    'No rows checked': 'brak zaznaczonych wierszy',
    'No text layer': 'Brak warstwy tekstu.',
    'No.': 'Nr',
    'Nominal (sticky values)': 'Nominał (jak poprzednio)',
    'OCR': 'symbol passes need the vision build; geometry pass works now.',
    'OCR engine': 'Silnik OCR',
    'OCR every page, not just sparse ones': 'Każdą stronę',
    'OCR min confidence': 'Min. pewność OCR',
    'Open': 'Otwórz',
    'Open a drawing': 'Otwórz rysunek',
    'Options': 'Opcje',
    'Overall': 'Całkowity',
    'PDF error': 'Błąd PDF',
    'PDF print': 'Rysunek PDF',
    'Page': 'strona',
    'Pan': 'przesuń',
    'Plain bubble, no prediction': 'bez odczytu',
    'Quick access bar': 'pasek',
    'Quick bubble (sticky values)': 'szybki',
    'Quick bubble, nominal read from drawing': 'auto nominał',
    'R': 'C',
    'Reading callout...': 'Odczyt...',
    'Record GO + next': 'zapisz GO',
    'Record NOGO + next': 'zapisz NOGO',
    'Review %d callouts...': 'Przegląd %d wywołań...',
    'Save': 'zapisz',
    'Save + next': 'zapisz + dalej',
    'Scan': 'Skanuj',
    'Scan failed: %s': 'Skan nieudany:\n%s',
    'Scan review': 'Przegląd',
    'Uncertain frame read': 'Niepewny odczyt ramki',
    'Scan: drag a GREEN box around the area to scan': 'Skanuj: zaznacz ZIELONE pole wokół obszaru',
    'Scan: drag a RED box to ignore, or Enter to skip': 'Skanuj: zaznacz CZERWONE pole do pominięcia lub Enter',
    'Scanning...': 'Skanowanie...',
    'Select': 'zaznacz',
    'Select tool': 'Zaznaczanie',
    'Session': 'Sesja',
    'Session not saved': 'Nie zapisano sesji',
    'Session read-only': 'Sesja tylko do odczytu',
    'Start a new session': 'Rozpocznij nową sesję',
    'started over; damaged file kept as %s': 'rozpoczęto od nowa; uszkodzony plik zachowany jako %s',
    'Settings': 'Ustawienia',
    'Sheet error': 'Błąd',
    'Simple': 'Prosty',
    'Skip': 'pomiń',
    'Snap to drawing geometry': 'Przyciągaj',
    'Snap to geometry': 'przyciąganie',
    'Style': 'Styl',
    'Symbol min confidence': 'Min. pewność symbolu',
    'This help': 'pomoc',
    'Toggle plain dims': 'Liczby',
    'Tolerance by decimal places': 'wg miejsc dziesiętnych:',
    'Tools': 'Narzędzia',
    'Type': 'Typ',
    'Uncheck all': 'Odznacz',
    'Units': 'Jednostki',
    'Unsaved': 'Niezapisane',
    'VLM engine': 'Silnik VLM',
    'VLM model': 'Model VLM',
    'Download VLM model': 'Pobierz model VLM',
    'Download': 'Pobierz',
    'Downloading %s...': 'Pobieranie %s...',
    'File %d/%d: %s (%.0f MB)': 'Plik %d/%d: %s (%.0f MB)',
    'Downloaded to:\n%s\n\nSelect OK to save settings and use it.':
        'Pobrano do:\n%s\n\nWybierz OK, aby zapisać ustawienia i użyć.',
    'Download failed: %s': 'Pobieranie nie powiodło się: %s',
    'View': 'Widok',
    'Vision assist (beta)': 'Wspomaganie wizyjne:',
    'Vision confidences must be between 0 and 1': 'Pewność musi być w zakresie 0-1',
    'Warming reader': 'Rozgrzewanie czytnika',
    'all pages': 'wszystkie strony',
    'ballooned %d rows': '%d podwierszy',
    'capture cancelled': 'anulowano',
    'captured: %s': 'przechwycono: %s',
    'captured %d callouts': 'przechwycono %d wywołań',
    'captured %s': 'przechwycono %s',
    'copied: %s': 'skopiowano: %s',
    'created: %s': 'utworzono: %s',
    'deleted': 'usunięto - Ctrl+Z',
    'deleted #%s': 'usunięto #%s - Ctrl+Z',
    'deleted %d': 'usunięto %d - Ctrl+Z',
    'even when a text layer exists': 'nawet gdy jest tekst',
    'filter': 'filtr...',
    'gage': 'przyrząd',
    'header saved': 'nagłówek zapisany',
    'inject detected symbols into VLM reads': 'wstrzykuj symbole do VLM',
    'measure walk complete': 'pomiar zakończony',
    'no bubbles to measure': 'brak bąbli',
    'no number here': 'brak liczby',
    'no text here': 'brak tekstu',
    'page': 'strona',
    'pin': 'bore gauge',
    'redo': 'ponowiono',
    'saved -> %s (+ .xlsx) in %s': 'zapisano → %s (+ .xlsx) in %s',
    'scan cancelled': 'anulowano skanowanie',
    'screw test': 'wkręt',
    'select 2+ bubbles': 'zaznacz 2+',
    'select 3+ bubbles': 'zaznacz 3+',
    'Split into separate bubbles': 'Podziel na osobne dymki',
    'split into %d bubbles': 'podzielono na %d dymkow',
    'nothing to split': 'nie ma czego podzielic',
    'GPU acceleration (Linux)': 'Akceleracja GPU (Linux)',
    'Install or update GPU pack...': 'Zainstaluj lub zaktualizuj pakiet GPU...',
    'GPU pack': 'Pakiet GPU',
    'Installing GPU pack (downloads, can take a while)...':
        'Instalowanie pakietu GPU (pobieranie, moze chwile potrwac)...',
    'GPU pack installed. Detectors run on GPU now, CPU if driver too old.':
        'Zainstalowano pakiet GPU. Detektory dzialaja na GPU, CPU gdy sterownik za stary.',
    'GPU pack install failed: %s': 'Instalacja pakietu GPU nie powiodla sie: %s',
    'Remove GPU pack': 'Usun pakiet GPU',
    'Remove the GPU pack? Detectors fall back to CPU until reinstalled.':
        'Usunac pakiet GPU? Detektory wroca na CPU do ponownej instalacji.',
    'GPU pack removed.': 'Pakiet GPU usuniety.',
    'Missing: %s': 'Brakuje: %s',
    'Debug': 'Debug',
    'Debug overlay': 'Nakładka debugowania',
    'Layers': 'Warstwy',
    'Overlay': 'Nakladka',
    'Callout sections': 'Sekcje wywolan',
    'Detector blocks': 'Bloki detektora',
    'GD&T symbols': 'Symbole GD&T',
    'regrouped %d into one callout (Ctrl+Z to undo)':
        'przegrupowano %d w jedno wywolanie (Ctrl+Z cofa)',
    'Settings saved, but applying them failed: %s':
        'Zapisano ustawienia, ale ich zastosowanie nie powiodlo sie: %s',
    'settings saved (apply failed)':
        'zapisano ustawienia (zastosowanie nie powiodlo sie)',
    'session NOT saved': 'NIE zapisano sesji',
    'session read-only': 'sesja tylko do odczytu',
    'session saving again': 'sesja znów zapisywana',
    'settings saved': 'ustawienia zapisane',
    'skip filled': 'pomiń',
    'snapped %s': 'przyciągnięto %s',
    'type': 'typ',
    'undo': 'cofnięto',
    'value': 'wartość',
    '• Detect GD&T symbols': 'Wykryj symbole GD&T',
    '• Group callouts with the block detector': 'Grupuj wg detektora bloków',
    # ribbon button labels
    'Setup': 'Ustawienia',
    'Prev': 'Poprzednia',
    'Previous page  PgUp': 'Poprzednia strona  PgUp',
    'Next': 'Następna',
    'Next page  PgDn': 'Następna strona  PgDn',
    'In': 'Powiększ',
    'Out': 'Pomniejsz',
    'Rot': 'Obróć',
    'Rotate': 'Obróć',
    'Undo': 'Cofnij',
    'List': 'Lista',
    # ribbon field labels
    'tol ±': 'tol ±',
    'tol max': 'tol max',
    'tol min': 'tol min',
    'tier': 'poziom',
    'radius': 'promień',
    'font': 'czcionka',
    'ISO 2768 auto': 'ISO 2768 auto',
    # measure bar
    'op:': 'op:',
    'Enter=save+next  G/+=GO  N/-=NOGO  Shift+Enter=back  Tab=skip  Esc=exit':
        'Enter=zapisz+dalej  G/+=GO  N/-=NOGO  Shift+Enter=wstecz  '
        'Tab=pomiń  Esc=wyjście',
    'Clear this reading (re-measure)': 'Wyczyść ten pomiar (zmierz ponownie)',
    'prev: %s': 'poprz.: %s',
    'walk complete: %d/%d measured, %d out of tol':
        'zakończono: %d/%d zmierzonych, %d poza tolerancją',
    # status bar
    ' Page %d/%d   next here #%d   zoom %d%%   bubbles here: %d   rows: %d '
    '(crit %d, CMM %d)   unsaved: %d':
        ' Strona %d/%d   tu #%d   zoom %d%%   bąbli tu: %d   wierszy: %d '
        '(kryt %d, CMM %d)   niezapisanych: %d',
    # launcher recent picker
    'no bubbles yet': 'brak bąbli',
    'modified': 'zmodyfikowano',
    'session file damaged': 'uszkodzony plik sesji',
    '%d bubble': '%d bąbel',
    '%d bubbles': '%d bąbli',
    '%d unsaved': '%d niezapisanych',
    'sheet': 'karta',
    'no sheet': 'brak karty',
    'Template': 'Szablon',
    'Pick a recent drawing or browse for a PDF. The chip shows its bubble count.':
        'Wybierz ostatni rysunek lub wskaż plik PDF. Znacznik pokazuje liczbę bąbli.',
    # bubble dialog labels
    'Bubble': 'Bąbel',
    'Nominal': 'Nominał',
    'Qty ×': 'Ilość ×',
    'Number of instances; the measure walk takes that many readings and '
    'keeps the worst.':
        'Liczba wystąpień; pomiar pobiera tyle odczytów i zachowuje najgorszy.',
    'pattern ×': 'wzór ×',
    'shared:': 'wspólne:',
    'X & Y differ': 'X i Y różne',
    'same X as #1': 'X jak #1',
    'same Y as #1': 'Y jak #1',
    'Depth:': 'Głębokość:',
    'CBore Ø:': 'Pogłębienie Ø:',
    'depth:': 'głęb.:',
    'Pin Ø': 'Pin Ø',
    'Tier': 'Poziom',
    'out of table': 'poza tabelą',
    'auto from nominal': 'auto z nominału',
    'ISO 2768 n/a for this type': 'ISO 2768 nie dotyczy tego typu',
    # angular gentol side length
    'Angle side': 'Bok kąta',
    'mm': 'mm',
    'shorter side': 'krótszy bok',
    'longer side': 'dłuższy bok',
    'Shorter side sets the band. With only the longer side, the '
    'shorter is unknown, so the widest band is used.':
        'Krótszy bok wyznacza przedział. Przy samym dłuższym boku krótszy '
        'jest nieznany, więc stosowany jest najszerszy przedział.',
    'Angle: enter side length in mm':
        'Kąt: podaj długość boku w mm',
    'BASIC and REFERENCE dims take the general tolerance':
        'Wymiary teoretyczne i pomocnicze biorą tolerancję ogólną',
    'Off treats them as exact: bracketed dims still get a bubble and '
    'a sheet row, but no tolerance.':
        'Wyłączone traktuje je jako dokładne: wymiary w nawiasach '
        'nadal dostają bąbel i wiersz karty, ale bez tolerancji.',
    'Angles: assume the shortest side band':
        'Kąty: przyjmij przedział najkrótszego boku',
    'ISO 2768 tolerances an angle by its shorter side in mm, which '
    'the callout never carries. Off, the bubble dialog asks.':
        'ISO 2768 toleruje kąt wg krótszego boku w mm, którego opis '
        'wymiaru nigdy nie zawiera. Wyłączone: pyta okno bąbla.',
    'Advanced hole needs X and Y': 'otwór zaawansowany wymaga X i Y',
    'Tolerance: ± value, or ISO 286 fit (H7, g6, js9); max/min overrides':
        'Tolerancja: ± wartość lub pasowanie ISO 286 (H7, g6, js9); '
        'max/min nadpisuje',
    # export / capture
    'Writing ballooned PDF...': 'Zapis PDF z bąblami...',
    'save cancelled': 'anulowano zapis',
    'session not saved: %s': 'nie zapisano sesji: %s',
    'general tolerance': 'tolerancja ogólna',
    "Bundled model is older than this version's class list and needs retraining. Text parsing still works; update Bubbler when a rebuilt model ships.":
        'Dołączony model jest starszy niż lista klas tej wersji i wymaga ponownego trenowania. Odczyt tekstu nadal działa; zaktualizuj Bubbler, gdy pojawi się przebudowany model.',
    'title block': 'tabliczka rysunkowa',
    'note': 'uwaga',
    # keyhelp descriptions
    'Read callout: OCR/VLM + bubble': 'odczyt: OCR/VLM + bąbel',
    'Capture text region: OCR/VLM': 'przechwyć obszar: OCR/VLM',
    'Menu: edit, sub-rows, delete': 'menu: edycja, podwiersze, usuń',
    'Delete (Add), toggle select (Select)':
        'usuń (Dodawanie), zaznacz (Zaznaczanie)',
    'Scroll; Ctrl+Wheel = zoom at cursor':
        'przewijanie; Ctrl+kółko = zoom przy kursorze',
    'Undo or redo': 'cofnij lub ponów',
    'Align row or column': 'Wyrownaj wiersz lub kolumne',
    'Zoom': 'zoom',
    'Zoom in': 'Powiększ',
    'Zoom out': 'Pomniejsz',
    'Notes': 'Uwagi',
    "The dialog's 'Leader line' box sets whether a balloon gets a line (default = ribbon state). Editing a bubble adds or removes its leader; L on the select-tool hotbar flips it for every selected bubble. On offsets the numeral automatically; off parks it on the callout.":
        "Pole 'Linia odniesienia' w oknie ustawia, czy bąbel dostaje linię (domyślnie wg wstążki). Edycja bąbla dodaje lub usuwa linię; L na pasku narzędzia zaznaczania przełącza ją dla każdego zaznaczonego bąbla. Włączona odsuwa numer automatycznie, wyłączona stawia go na wymiarze.",
    'Captured and scanned bubbles step off the callout box in the arrow-key direction, dodging text, fills, thick edges and other bubbles. Thin leader and dimension lines are not avoided.':
        'Przechwycone i zeskanowane bąble odsuwają się od pola wywołania w kierunku strzałek, omijając tekst, wypełnienia, grube krawędzie i inne bąble. Cienkie linie odniesienia i wymiarowe nie są omijane.',
    "Click or drag a callout to read it (OCR/VLM) and bubble it; Alt+click drops a plain bubble, no read. Bare numbers always bubble, taking the ribbon's sticky type and the title block's general tolerance. With the header editor open, a drag fills the focused field instead.":
        'Kliknij lub przeciągnij wywołanie, aby je odczytać (OCR/VLM) i obąblować; Alt+klik stawia zwykły bąbel bez odczytu. Same liczby zawsze się bąblują, biorąc typ ze wstążki i tolerancję ogólną z tabeli tytułowej. Przy otwartym edytorze nagłówka przeciągnięcie wypełnia aktywne pole.',
    # Data + OOT + CMM import
    'Data': 'Dane',
    'Reports and data import': 'Raporty i import danych',
    'OOT report': 'Raport poza tol.',
    'Out-of-tolerance report': 'Raport przekroczeń tolerancji',
    'Import CMM/CSV': 'Import CMM/CSV',
    'Tol': 'Tol',
    'Measured': 'Zmierzone',
    'Op': 'Op',
    'Export CSV...': 'Eksport CSV...',
    'Refresh': 'Odśwież',
    '%d out of tolerance (%d critical)': '%d poza tolerancją (%d krytycznych)',
    'exported: %s': 'wyeksportowano: %s',
    'CSV export failed: %s': 'eksport CSV nieudany: %s',
    'import failed: %s': 'import nieudany: %s',
    'import failed: could not decode file':
        'import nieudany: nie udało się odczytać pliku',
    'No balloon numbers matched.': 'Brak dopasowanych numerów bąbli.',
    'Import into op:': 'Importuj do op:',
    'Imported %d into %s': 'Zaimportowano %d do %s',
    '%d unmatched: %s': '%d niedopasowanych: %s',
    '%d duplicate rows': '%d zduplikowanych wierszy',
    '%d bad rows': '%d błędnych wierszy',
    'imported %d measurements': 'zaimportowano %d pomiarów',
    'No rows in file.': 'Brak wierszy w pliku.',
    'Import preview': 'Podgląd importu',
    'Import': 'Importuj',
    'Status': 'Status',
    'Value': 'Wartość',
    '%d matched, %d unmatched, %d duplicate, %d bad':
        '%d dopasowanych, %d niedopasowanych, %d duplikatów, %d błędnych',
    '-> #%s': '-> #%s',
    'duplicate (superseded)': 'duplikat (zastąpiony)',
    'no bubble on drawing': 'brak bąbla na rysunku',
    'unreadable bubble': 'nieczytelny bąbel',
    # page navigator
    'Pages': 'Strony',
    'Page navigator': 'Nawigator stron',
    # reader-correction collector (flywheel)
    'Reader corrections': 'Poprawki czytnika',
    'Collect corrections and callouts (local, opt-in)':
        'Zbieraj poprawki i wywolania (lokalnie, opcjonalnie)',
    'Corrections folder': 'Folder poprawek',
    'Custom model (.onnx)': 'Własny model (.onnx)',
    'Point Bubbler at a locally-trained detector; blank uses the bundled model.':
        'Wskaż lokalnie wytrenowany detektor; puste = model wbudowany.',
    'Report bad read...': 'Zgłoś błędny odczyt...',
    'Report misread...': 'Zgłoś błędny odczyt...',
    'Export corrections...': 'Eksport poprawek...',
    'Enable "Collect reader corrections" in Settings > Vision first.':
        'Najpierw włącz „Zbieraj poprawki czytnika” w Ustawienia > Wizja.',
    'Drag a box around the misread callout':
        'Zaznacz ramką błędnie odczytane wywołanie',
    'correction saved': 'poprawka zapisana',
    'could not save correction': 'nie udało się zapisać poprawki',
    'correction cancelled': 'anulowano poprawkę',
    'Export corrections': 'Eksport poprawek',
    'No corrections yet.': 'Brak poprawek.',
    'Could not write the zip.': 'Nie udało się zapisać zip.',
    'Saved %d correction(s) to a zip. Nothing is sent; attach the zip yourself.':
        'Zapisano %d poprawek do zip. Nic nie jest wysyłane; dołącz zip samodzielnie.',
    'Zip:': 'Zip:',
    'Open folder': 'Otwórz folder',
    'Open GitHub issue': 'Otwórz zgłoszenie GitHub',
    'Email us': 'Napisz do nas',
    'Review corrections': 'Przegląd poprawek',
    'Review corrections...': 'Przegląd poprawek...',
    # acceptances (training data)
    'Collect shipped callouts as training data (local, opt-in)':
        'Zbieraj wysłane wywołania jako dane treningowe (lokalnie, opcjonalnie)',
    'Acceptances folder': 'Folder akceptacji',
    'Off by default. On save, every bubbled callout becomes a '
    'local labelled example (crop + fields, drawing name never '
    'stored); never sent automatically.':
        'Domyślnie wyłączone. Przy zapisie każde zbalonowane wywołanie staje '
        'się lokalnym oznaczonym przykładem (wycinek + pola, nazwa rysunku nie '
        'jest zapisywana); nic nie jest wysyłane automatycznie.',
    # per-drawing metrics (time + counts)
    'Record time + callout counts per drawing (local, opt-in)':
        'Zapisuj czas + liczby wywołań na rysunek (lokalnie, opcjonalnie)',
    'Metrics folder': 'Folder metryk',
    'Off by default. On save, one local row per drawing '
    '(minutes + counts, no drawing content); the product KPI, '
    'never sent automatically.':
        'Domyślnie wyłączone. Przy zapisie jeden lokalny wiersz na rysunek '
        '(minuty + liczby, bez zawartości rysunku); wskaźnik KPI produktu, '
        'nic nie jest wysyłane automatycznie.',
    'Time and counts': 'Czas i liczby',
    'Time and counts...': 'Czas i liczby...',
    'No metrics yet. Enable "Record time + callout counts per drawing" in Settings, then save a drawing.':
        'Brak metryk. Włącz „Zapisuj czas + liczby wywołań na rysunek” w Ustawieniach, a następnie zapisz rysunek.',
    'Across %(n)d drawing(s):\n\n'
    '  %(min).1f min per drawing (open to saved sheet)\n'
    '  %(bub).1f callouts per drawing (%(tot)d total)\n'
    '  %(edit).0f%% of callouts needed an edit\n\n'
    'Local only, never sent.':
        'Dla %(n)d rysunku/ów:\n\n'
        '  %(min).1f min na rysunek (od otwarcia do zapisu arkusza)\n'
        '  %(bub).1f wywołań na rysunek (razem %(tot)d)\n'
        '  %(edit).0f%% wywołań wymagało poprawki\n\n'
        'Tylko lokalnie, nic nie jest wysyłane.',
    # output preview + print (L10)
    'Preview or print output...': 'Podgląd lub wydruk wyniku...',
    'Preview output': 'Podgląd wyniku',
    'Output preview': 'Podgląd wyniku',
    '%d unsaved row(s). Save to update the preview?':
        '%d niezapisanych wierszy. Zapisać, aby zaktualizować podgląd?',
    'Nothing to preview yet. Save the drawing first.':
        'Nie ma jeszcze czego podglądać. Najpierw zapisz rysunek.',
    'Could not open the output for preview.':
        'Nie udało się otworzyć wyniku do podglądu.',
    'Print...': 'Drukuj...',
    'Printing not available in this build.':
        'Drukowanie niedostępne w tej wersji.',
    # H7 group + ungroup
    'Group into one': 'Zgrupuj w jeden',
    'Ungroup': 'Rozgrupuj',
    # sheet column-layout preview
    'Sheet columns, in order:': 'Kolumny arkusza, w kolejnosci:',
    'Inspection sheet preview:': 'Podglad karty kontroli:',
    # STEP 3D preview (add-on)
    '3D preview (STEP)': 'Podglad 3D (STEP)',
    'Offer a 3D STEP preview when opening a drawing (needs '
    'OpenCASCADE)':
        'Zaproponuj podglad 3D STEP przy otwieraniu rysunku (wymaga OpenCASCADE)',
    'On: the first time a drawing opens, Bubbler asks for a STEP file and renders two isometric views for the report cover and recent-files list. OpenCASCADE (OCCT) installs below.':
        'Wl.: przy pierwszym otwarciu rysunku Bubbler prosi o plik STEP i renderuje dwa widoki izometryczne na okladke raportu i liste ostatnich plikow. OpenCASCADE (OCCT) instaluje sie ponizej.',
    'Install OpenCASCADE (OCCT)...': 'Zainstaluj OpenCASCADE (OCCT)...',
    '3D pack': 'Dodatek 3D',
    'OpenCASCADE reads STEP files. Installed once into ~/.bubbler/step; not part of the app download.':
        'OpenCASCADE czyta pliki STEP. Instalowany raz do ~/.bubbler/step; nie jest czescia pobierania aplikacji.',
    'Installing 3D pack (downloads OpenCASCADE, can take a while)...':
        'Instalowanie dodatku 3D (pobiera OpenCASCADE, moze chwile potrwac)...',
    '3D pack installed. STEP previews can render now.':
        'Dodatek 3D zainstalowany. Podglady STEP moga sie teraz renderowac.',
    '3D pack install failed: %s': 'Instalacja dodatku 3D nie powiodla sie: %s',
    'Remove 3D pack': 'Usun dodatek 3D',
    'Remove the 3D pack? STEP previews stop until reinstalled.':
        'Usunac dodatek 3D? Podglady STEP przestana dzialac do ponownej instalacji.',
    '3D pack removed.': 'Dodatek 3D usuniety.',
    '3D preview': 'Podglad 3D',
    '3D preview...': 'Podglad 3D...',
    'Show a 3D STEP preview instead of the PDF page?':
        'Pokazać podgląd 3D STEP zamiast strony PDF?',
    'STEP file': 'Plik STEP',
    'Which way is up:': 'Ktora strona do gory:',
    'Use as list thumb': 'Uzyj jako miniatury listy',
    'Use this preview': 'Uzyj tego podgladu',
    '(preview unavailable)': '(podglad niedostepny)',
    'No 3D preview available.': 'Brak podgladu 3D.',
    # parallel VLM cross-check
    'Cross-check risk callouts with the VLM (slow)':
        'Sprawdz krzyzowo wywolania ryzyka za pomoca VLM (wolne)',
    'On: run the VLM alongside the ONNX reader on GD&T and '
    'toleranced dimensions as a second opinion. Agreement marks the '
    'row corroborated; a disagreement starts it UNTICKED and shows '
    "the VLM's value, so a doubtful read is asked, not assumed. "
    'Independent of the fallback reader above -- this assists ONNX '
    'without using the VLM as a reader.':
        'Wl.: uruchom VLM obok czytnika ONNX dla GD&T i wymiarow tolerowanych '
        'jako druga opinie. Zgodnosc oznacza wiersz jako potwierdzony; '
        'niezgodnosc zaczyna go ODZNACZONY i pokazuje wartosc VLM, wiec '
        'watpliwy odczyt jest pytany, nie zakladany. Niezalezne od czytnika '
        'zapasowego powyzej -- wspomaga ONNX bez uzywania VLM jako czytnika.',
    'VLM read %s -- disagrees with reader':
        'VLM odczytal %s -- rozni sie od czytnika',
    'Reader and VLM agree': 'Czytnik i VLM sa zgodni',
    # gentol editor revert-to-auto
    'Reset to auto': 'Przywroc automatyczne',
    'Drop hand correction, use the drawing (ISO 2768 class, or decimal ladder on inch drawings).':
        'Usuń ręczną poprawkę, użyj rysunku (klasa ISO 2768 lub drabinka dziesiętna dla rysunków calowych).',
    'Crop': 'Wycinek',
    'Region': 'Region',
    'Correct': 'Poprawnie',
    'Reader was': 'Czytnik odczytał',
    '%d corrections collected': 'zebrano %d poprawek',
    'Export...': 'Eksport...',
    # title-block autofill
    'no title block found': 'nie znaleziono tabelki',
    'Scan title block': 'Skanuj tabelkę',
    'title block scanned': 'tabelka zeskanowana',
    # sheet capacity
    'Sheet full': 'Arkusz pełny',
    '%d new bubbles but only %d free rows on the inspection sheet. Nothing '
    'was saved. Remove bubbles or start a new sheet.':
        'Nowych bąbli: %d, a wolnych wierszy w arkuszu tylko %d. Nic nie '
        'zapisano. Usuń bąble lub rozpocznij nowy arkusz.',
    # calculator
    'Calculator': 'Kalkulator',
    'Calc': 'Kalk.',
    'To measure': 'Do pomiaru',
    'Send result to measure field': 'Wyślij wynik do pola pomiaru',
    'Copy': 'Kopiuj',
    'invalid': 'błędne',
    'result copied': 'wynik skopiowany',
    'Click entry to reuse its expression':
        'Kliknij pozycję, aby użyć jej wyrażenia ponownie',
    'result -> measure field': 'wynik -> pole pomiaru',
    'not measuring; result copied': 'brak pomiaru; wynik skopiowany',
    '= %s   (Enter again to save)': '= %s   (Enter ponownie, aby zapisać)',
    'reading %d/%d  (Enter next)': 'odczyt %d/%d  (Enter = następny)',

    # session lock + not saved
    'READ-ONLY': 'TYLKO DO ODCZYTU',
    'READ-ONLY - NOT SAVING': 'TYLKO DO ODCZYTU - BRAK ZAPISU',
    'File: %s': 'Plik: %s',
    'Details: %s': 'Szczegóły: %s',
    'Bubbles are NOT being saved to disk.':
        'Bąble NIE są zapisywane na dysk.',
    'This file was saved by a newer Bubbler than yours (Bubbler %s).\n\nIt was not loaded and will not be overwritten. Update Bubbler to open this job.':
        'Ten plik zapisała nowsza wersja Bubblera niż twoja (Bubbler %s).\n\nNie został wczytany i nie zostanie nadpisany. Zaktualizuj Bubblera, aby otworzyć to zlecenie.',
    'This file is too old for your Bubbler (Bubbler %s).\n\nIt was not loaded and will not be overwritten. Only an in-between version can upgrade it: open it there, save, then re-open it here. Without that version the bubbles cannot be recovered - move or rename the file below to start the drawing over.':
        'Ten plik jest zbyt stary dla twojego Bubblera (Bubbler %s).\n\nNie został wczytany i nie zostanie nadpisany. Zaktualizować może go tylko wersja pośrednia: otwórz go w niej, zapisz, a potem otwórz tutaj. Bez tej wersji bąbli nie da się odzyskać - przenieś lub zmień nazwę pliku poniżej, aby zacząć rysunek od nowa.',
    'This run was closed out, so it is final and cannot be changed.\n\nIssuing a report does not close a run; closing out does. Start a new run to inspect another part against this drawing.':
        'Ta seria została zamknięta, więc jest ostateczna i nie można jej zmieniać.\n\nWydanie raportu nie zamyka serii; zamyka ją dopiero zamknięcie. Rozpocznij nową serię, aby skontrolować kolejną część według tego rysunku.',

    # inspection run lifecycle
    'Inspection run': 'Seria kontroli',
    'Run': 'Seria',
    'Issue report': 'Wydaj raport',
    'Issue and close out inspection': 'Wydaj raport i zamknij kontrolę',
    'Close out inspection...': 'Zamknij kontrolę...',
    'Close out inspection': 'Zamknij kontrolę',
    'Close out this run?': 'Zamknąć tę serię?',
    'Report %s': 'Raport %s',
    'No report issued yet': 'Nie wydano jeszcze raportu',
    'Closing out locks this run. Its measured values, ballooned PDF and inspection sheet stop changing: Bubbler will not save over it, now or when you re-open the drawing.\n\nThe drawing is not locked. You can start a new run any time and inspect another part against it.':
        'Zamknięcie blokuje tę serię. Jej wartości zmierzone, PDF z bąblami i arkusz kontrolny przestają się zmieniać: Bubbler nie zapisze na niej, teraz ani przy ponownym otwarciu rysunku.\n\nRysunek nie jest zablokowany. W każdej chwili możesz rozpocząć nową serię i skontrolować kolejną część według niego.',
    'Close out': 'Zamknij',
    'Keep working': 'Pracuj dalej',
    'Not closed out': 'Nie zamknięto',
    'This run was NOT closed out: its ballooned PDF and inspection sheet could not be written.\n\nA closed-out run refuses every later save, so its documents must be written now. Fix the problem above and close out again.':
        'Ta seria NIE została zamknięta: nie udało się zapisać jej PDF z bąblami ani arkusza kontrolnego.\n\nZamknięta seria odmawia każdego późniejszego zapisu, więc jej dokumenty trzeba zapisać teraz. Usuń powyższy problem i zamknij kontrolę ponownie.',
    'not closed out: documents not written':
        'nie zamknięto: dokumenty niezapisane',
    'report %s issued': 'wydano raport %s',
    'inspection closed out': 'kontrola zamknięta',
    'new inspection run started': 'rozpoczęto nową serię kontroli',
    'closed out': 'zamknięta',
    'This run has not been touched for %d days.': 'Ta seria nie była ruszana od %d dni.',
    'Was that inspection finished, and is this a new one?\n\nA new run keeps the bubbles and requirements and clears the measured values, so the old readings stay on their own run. Continuing picks up where you left off.':
        'Czy tamta kontrola została zakończona i czy to jest nowa?\n\nNowa seria zachowuje bąble i wymagania, a czyści wartości zmierzone, więc stare odczyty zostają przy swojej serii. Kontynuacja podejmuje pracę tam, gdzie ją przerwałeś.',
    'Start a new run': 'Rozpocznij nową serię',
    'Continue this run': 'Kontynuuj tę serię',
    'This file is damaged and could not be read (Bubbler %s).\n\n'
    'It was not loaded and will not be overwritten. Nothing in it can be '
    'recovered, so you can start the drawing over - the damaged file is kept '
    'alongside it, renamed.':
        'Ten plik jest uszkodzony i nie da się go odczytać '
        '(Bubbler %s).\n\nNie został wczytany i nie zostanie nadpisany. '
        'Nic z niego nie da się odzyskać, więc możesz '
        'zacząć rysunek od nowa - uszkodzony plik zostaje obok, '
        'ze zmienioną nazwą.',
    'Could not write\n%s\n\n%s\n\nCheck free space, permissions, or if the file is open elsewhere. Bubbler retries on the next change.':
        'Nie można zapisać\n%s\n\n%s\n\nSprawdź wolne miejsce, uprawnienia lub czy plik jest otwarty gdzie indziej. Bubbler ponowi próbę przy następnej zmianie.',
    'Session could not be written to disk. Every bubble on this drawing will be lost when Bubbler closes.\n\nQuit anyway?':
        'Nie udało się zapisać sesji na dysk. Wszystkie bąble na tym rysunku zostaną utracone po zamknięciu Bubblera.\n\nZamknąć mimo to?',
    'Ballooned PDF and inspection sheet were written, but the session file could not be saved. Sheet rows will not match this drawing the next time you open it.':
        'Zapisano PDF z bąblami i arkusz kontrolny, ale nie udało się zapisać pliku sesji. Wiersze arkusza nie będą pasować do tego rysunku przy następnym otwarciu.',
    'NOT saved - session file is read-only or write failed.':
        'NIE zapisano - plik sesji jest tylko do odczytu lub zapis nieudany.',
    'added %d balloon(s), %d row(s)':
        'dodano %d balon(ów), %d wiersz(y)',
    'NOT saved to disk':
        'NIE zapisano na dysk',
    'Leader line from balloon to callout':
        'Linia odnośnika od balonu do wymiaru',
    'On: the balloon sits beside the callout, with a line pointing back. Off: it sits on the callout. Same as the ribbon Leaders box and the L key.':
        'Wł.: balon stoi obok wymiaru, linia wskazuje na niego. Wył.: stoi na wymiarze. To samo co pole Odnośniki na wstążce i klawisz L.',
    'Stop the leader at the callout text':
        'Zatrzymaj odnośnik na tekście wymiaru',
    'Preferred balloon side': 'Preferowana strona balonu',
    'auto (best fit)': 'auto (najlepsze dopasowanie)',
    'above': 'nad',
    'below': 'pod',
    'right': 'z prawej',
    'left': 'z lewej',
    'A preference, not a rule: a crowded side loses to a clear one.':
        'To preferencja, nie zasada: zatłoczona strona przegrywa z wolną.',
    # inspection-sheet title block
    'Customer': 'Klient',
    'Units (mm/in)': 'Jednostki (mm/cal)',
    'Approved by': 'Zatwierdził',
    'Approval Date': 'Data zatwierdzenia',

    # "What's available" tab
    "What's available": 'Co działa',
    'What Bubbler can do on this computer. Unavailable features are skipped quietly, so check here first if a scan finds nothing.':
        'Co Bubbler potrafi na tym komputerze. Niedostępne funkcje są po cichu pomijane, więc sprawdź tutaj najpierw, gdy skan nic nie znajduje.',
    'Checking what is available...': 'Sprawdzanie dostępności...',
    'Re-check': 'Sprawdź ponownie',
    'What to do: %s': 'Co zrobić: %s',
    'Working': 'Działa',
    'Turned off': 'Wyłączone',
    'Not available': 'Niedostępne',
    'Needs attention': 'Wymaga uwagi',
    'Check failed': 'Sprawdzenie nie powiodło się',
    'This check itself failed: %s': 'Samo sprawdzenie zawiodło: %s',
    'Send ~/.bubbler.log with your report.':
        'Dołącz plik ~/.bubbler.log do zgłoszenia.',
    'unknown': 'nieznany',
    'CPU': 'procesor (CPU)',
    'NVIDIA GPU (CUDA)': 'karta NVIDIA (CUDA)',
    'NVIDIA GPU (TensorRT)': 'karta NVIDIA (TensorRT)',
    'GPU (DirectML)': 'karta graficzna (DirectML)',
    'Apple GPU (CoreML)': 'karta Apple (CoreML)',
    'AMD GPU (ROCm)': 'karta AMD (ROCm)',
    'Drawing page rendering': 'Renderowanie strony rysunku',
    'Pages render at %d DPI for the detectors.':
        'Strony są renderowane w %d DPI na potrzeby detektorów.',
    'PyMuPDF is missing, so no page image can be made and every vision pass is skipped.':
        'Brakuje PyMuPDF, więc nie da się utworzyć obrazu strony i każde przejście wizyjne jest pomijane.',
    'Reinstall Bubbler; the packaged build includes it.':
        'Zainstaluj Bubbler ponownie; gotowa wersja go zawiera.',
    'Compute device': 'Urządzenie obliczeniowe',
    'onnxruntime is missing, so no detector and no built-in OCR can run.':
        'Brakuje onnxruntime, więc żaden detektor ani wbudowane OCR nie mogą '
        'działać.',
    'onnxruntime %(ver)s is here but no model is loaded, so nothing runs yet.':
        'onnxruntime %(ver)s jest, ale żaden model nie jest wczytany, więc nic jeszcze nie działa.',
    'See the model rows below.': 'Zobacz wiersze modeli poniżej.',
    'Running on %(dev)s (onnxruntime %(ver)s).':
        'Działa na %(dev)s (onnxruntime %(ver)s).',
    'Running on the CPU (onnxruntime %(ver)s). %(why)s':
        'Działa na procesorze (onnxruntime %(ver)s). %(why)s',
    'Running on the CPU (onnxruntime %(ver)s). No usable graphics card was found, so Bubbler uses the CPU. This is a supported setup: everything works, scanning is just slower.':
        'Działa na procesorze (onnxruntime %(ver)s). Nie znaleziono nadającej się karty graficznej, więc Bubbler używa procesora. To wspierana konfiguracja: wszystko działa, skan jest tylko wolniejszy.',
    'Running on the CPU (onnxruntime %(ver)s). This build has no '
    'graphics-card support. This is a supported setup: everything works, '
    'scanning is just slower.':
        'Działa na procesorze (onnxruntime %(ver)s). Ta wersja nie obsługuje '
        'kart graficznych. To wspierana konfiguracja: wszystko działa, skan '
        'jest tylko wolniejszy.',
    'Nothing to do unless you want more speed. With an NVIDIA card, install '
    'the GPU pack lower down this tab.':
        'Nic nie trzeba robić, chyba że chcesz większej szybkości. Mając '
        'kartę NVIDIA, zainstaluj pakiet GPU niżej na tej karcie.',
    'GD&T symbol detector': 'Detektor symboli GD&T',
    'Callout block detector': 'Detektor bloków wymiarowych',
    'Control-frame symbol reader': 'Czytnik symbolu ramki tolerancji',
    'Loaded %s, running on %s.': 'Wczytano %s, działa na %s.',
    '%d classes, as expected': '%d klas, zgodnie z oczekiwaniem',
    'class count could not be read': 'nie udało się odczytać liczby klas',
    '%(classes)s, %(px)d px input. %(hint)s':
        '%(classes)s, wejście %(px)d px. %(hint)s',
    'This model has %(got)d classes but this Bubbler expects %(want)d, so anything it finds is labelled wrong.':
        'Ten model ma %(got)d klas, a ten Bubbler oczekuje %(want)d, więc wszystko co znajdzie będzie źle opisane.',
    'Clear the custom model box in Settings > Vision to use the model that shipped with Bubbler.':
        'Wyczyść pole własnego modelu w Ustawienia > Wizja, aby użyć modelu dostarczonego z Bubblerem.',
    'This pass is skipped. Reason: %s':
        'To przejście jest pomijane. Powód: %s',
    'the model file was not found': 'nie znaleziono pliku modelu',
    'Finds the symbols the text layer leaves out.':
        'Znajduje symbole, których brakuje w warstwie tekstowej.',
    'Groups a callout and its tolerances into one block.':
        'Łączy wymiar i jego tolerancje w jeden blok.',
    'Reads the characteristic symbol from the frame picture when the text layer has none.':
        'Odczytuje symbol cechy z obrazu ramki, gdy warstwa tekstowa go nie ma.',
    'Settings > Vision: clear Custom model, or reinstall Bubbler to restore '
    'the bundled detector.':
        'Ustawienia > Wizja: wyczyść Własny model albo zainstaluj Bubbler '
        'ponownie, aby przywrócić dołączony detektor.',
    'Settings > Vision: clear the region model box, or reinstall Bubbler.':
        'Ustawienia > Wizja: wyczyść pole modelu bloków albo zainstaluj '
        'Bubbler ponownie.',
    'Settings > Vision: clear the frame model box, or reinstall Bubbler.':
        'Ustawienia > Wizja: wyczyść pole modelu ramki albo zainstaluj '
        'Bubbler ponownie.',
    'Switched off, so GD&T glyphs are read from the text layer only.':
        'Wyłączone, więc znaki GD&T są czytane tylko z warstwy tekstowej.',
    'Switched off, so callouts are grouped by geometry alone.':
        'Wyłączone, więc wymiary są grupowane wyłącznie po geometrii.',
    'Switched off, so a control frame keeps whatever symbol the text layer '
    'gives.':
        'Wyłączone, więc ramka tolerancji zachowuje symbol z warstwy '
        'tekstowej.',
    'Settings > Vision: tick Detect GD&T symbols.':
        'Ustawienia > Wizja: zaznacz Wykrywaj symbole GD&T.',
    'Settings > Vision: tick Detect callout blocks.':
        'Ustawienia > Wizja: zaznacz Wykrywaj bloki wymiarowe.',
    'Settings > Vision: tick Read the frame symbol.':
        'Ustawienia > Wizja: zaznacz Odczytuj symbol ramki.',
    'Text reader: built-in OCR': 'Czytnik tekstu: wbudowane OCR',
    'Text reader: Florence-2': 'Czytnik tekstu: Florence-2',
    'Text reader: PaddleOCR-VL': 'Czytnik tekstu: PaddleOCR-VL',
    'Switched off, so a scanned drawing with no text layer reads as empty.':
        'Wyłączone, więc skanowany rysunek bez warstwy tekstowej będzie '
        'pusty.',
    'Settings > Vision: tick Read text from the picture.':
        'Ustawienia > Wizja: zaznacz Czytaj tekst z obrazu.',
    'the OCR engine did not load': 'silnik OCR się nie wczytał',
    'Reinstall Bubbler; the packaged build includes the OCR engine.':
        'Zainstaluj Bubbler ponownie; gotowa wersja zawiera silnik OCR.',
    'on every page': 'na każdej stronie',
    'only where the drawing has no text of its own':
        'tylko tam, gdzie rysunek nie ma własnego tekstu',
    'Ready (RapidOCR), used %(when)s, keeping reads above %(conf).2f '
    'confidence.':
        'Gotowe (RapidOCR), używane %(when)s, zachowuje odczyty powyżej '
        '%(conf).2f pewności.',
    'Not used. Reason: %s': 'Nieużywane. Powód: %s',
    'no Florence-2 model pack is installed':
        'nie zainstalowano żadnego pakietu modelu Florence-2',
    'the model pack is incomplete or a support library is missing':
        'pakiet modelu jest niekompletny albo brakuje biblioteki pomocniczej',
    'Settings > Vision: Download VLM model.':
        'Ustawienia > Wizja: Pobierz model VLM.',
    'Settings > Vision: download the pack again.':
        'Ustawienia > Wizja: pobierz pakiet ponownie.',
    'Installed and ready, but not switched on.':
        'Zainstalowane i gotowe, ale niewłączone.',
    'Settings > Vision: tick Use a VLM reader and pick florence.':
        'Ustawienia > Wizja: zaznacz Użyj czytnika VLM i wybierz florence.',
    'Settings > Vision: tick Use a VLM reader and pick paddle.':
        'Ustawienia > Wizja: zaznacz Użyj czytnika VLM i wybierz paddle.',
    'Ready, reading from %s.': 'Gotowe, czyta z %s.',
    'Ready.': 'Gotowe.',
    'the optional PaddleOCR packages are not installed':
        'opcjonalne pakiety PaddleOCR nie są zainstalowane',
    'Optional. Florence-2 does the same job and is a download away in Settings > Vision.':
        'Opcjonalne. Florence-2 robi to samo i jest do pobrania w Ustawienia > Wizja.',
    'GPU pack (Linux)': 'Pakiet GPU (Linux)',
    'Switched off, so the detectors stay on the CPU.':
        'Wyłączone, więc detektory zostają na procesorze.',
    'Settings > Vision: tick Use the GPU pack.':
        'Ustawienia > Wizja: zaznacz Użyj pakietu GPU.',
    'Not installed, so the detectors run on the CPU. That is a supported '
    'setup.':
        'Niezainstalowane, więc detektory działają na procesorze. To '
        'wspierana konfiguracja.',
    'Optional. With an NVIDIA card and driver 580 or newer, use the GPU pack '
    'button in Settings > Vision.':
        'Opcjonalne. Mając kartę NVIDIA i sterownik 580 lub nowszy, użyj '
        'przycisku pakietu GPU w Ustawienia > Wizja.',
    'Installed but not answering (%s), so the detectors run on the CPU.':
        'Zainstalowane, ale nie odpowiada (%s), więc detektory działają na '
        'procesorze.',
    'Settings > Vision: install the GPU pack again, then restart Bubbler.':
        'Ustawienia > Wizja: zainstaluj pakiet GPU ponownie, potem uruchom '
        'Bubbler jeszcze raz.',
    'Installed and answering: %s': 'Zainstalowane i odpowiada: %s',

    # Units + gentol ladder + validation
    'Unit system': 'Układ jednostek',
    'Bubbler cannot tell what units this drawing uses.':
        'Bubbler nie rozpoznał jednostek tego rysunku.',
    'Pick the system it was drawn in. Tolerances, gage choice and the general-tolerance ladder all follow it. Change it later from the hotbar or Settings.':
        'Wybierz układ, w którym rysunek powstał. Tolerancje, dobór przyrządu i tabela tolerancji ogólnych zależą od tego. Zmienisz go później z paska skrótów albo z Ustawień.',
    'Millimetres (ISO)': 'Milimetry (ISO)',
    'Inches (ASME)': 'Cale (ASME)',
    'Detected: %s': 'Wykryto: %s',
    'Set by you': 'Ustawione przez Ciebie',
    'Set by the detector': 'Ustawione przez detektor',
    'Ladder for this drawing...': 'Tabela dla tego rysunku...',
    'Ladder for this drawing': 'Tabela dla tego rysunku',
    'Blank rows fall back to Settings. This drawing only.':
        'Puste pola biorą wartość z Ustawień. Dotyczy tylko tego rysunku.',
    'Use the Settings ladder': 'Użyj tabeli z Ustawień',
    'General-tolerance ladder': 'Tabela tolerancji ogólnych',
    'Automatic (follow the units)': 'Automatycznie (według jednostek)',
    'ISO 2768 table': 'Tabela ISO 2768',
    'Decimal places': 'Miejsca dziesiętne',
    'None': 'Brak',
    'Automatic uses ISO 2768 on a millimetre drawing and the decimal-place '
    'block on an inch one.':
        'Automatycznie oznacza ISO 2768 na rysunku milimetrowym i tabelę '
        'miejsc dziesiętnych na calowym.',
    'Apply the general tolerance automatically':
        'Nadawaj tolerancję ogólną automatycznie',
    'ISO 2768 class': 'Klasa ISO 2768',
    'Millimetre ladder': 'Tabela milimetrowa',
    'Inch ladder': 'Tabela calowa',
    'Reset ladders to defaults': 'Przywróć domyślne tabele',
    'Tolerance ladder refused': 'Tabela tolerancji odrzucona',
    '%s is not a decimal-place bucket.':
        '%s nie jest przedziałem miejsc dziesiętnych.',
    '%s must be a number.': '%s musi być liczbą.',
    '%s must be greater than zero.': '%s musi być większe od zera.',
    '%s is %g, outside the sane range %g to %g.':
        '%s wynosi %g, poza rozsądnym zakresem od %g do %g.',
    '%s is looser than %s. More decimal places must mean a tighter '
    'tolerance.':
        '%s jest luźniejsze niż %s. Więcej miejsc dziesiętnych musi '
        'oznaczać ciaśniejszą tolerancję.',
    'The tolerance ladder is not usable.':
        'Tabela tolerancji nie nadaje się do użycia.',
    'CMM if tol ≤ (mm)': 'WMP gdy tol ≤ (mm)',
    'Micrometer if tol ≤ (mm)': 'Mikrometr gdy tol ≤ (mm)',
    'CMM if tol ≤ (inch)': 'WMP gdy tol ≤ (cal)',
    'Micrometer if tol ≤ (inch)': 'Mikrometr gdy tol ≤ (cal)',
    'measure in': 'mierzę w',
    '%s (drawing)': '%s (rysunek)',
    'Type readings in %s': 'Wpisz odczyty w %s',
    'Units you measure in. Readings are stored in drawing units.':
        'Jednostki, w których mierzysz. Odczyty są zapisywane w jednostkach rysunku.',
    'Read value as inches, convert to mm':
        'Odczytaj wartość w calach, przelicz na mm',
    'Read value as mm, convert to inches':
        'Odczytaj wartość w mm, przelicz na cale',
    'Write the tier as a designator':
        'Zapisz poziom jako oznaczenie',
    'Off: the tier goes in the tier column. On: it is mapped to the '
    'designator column instead (red CRITICAL, blue MAJOR, '
    'green MINOR). KEY is never written, so it stays hand-entry.':
        'Wyłączone: poziom trafia do kolumny poziomu. Włączone: '
        'jest mapowany na kolumnę oznaczenia (czerwony CRITICAL, '
        'niebieski MAJOR, zielony MINOR). KEY nigdy nie jest zapisywany, '
        'więc pozostaje do wpisania ręcznie.',

    # Settings dialog tabs (L3)
    'Language and mode': 'Język i tryb',
    'Appearance': 'Wygląd',
    'New bubble defaults': 'Domyślne nowego bąbla',
    'Placement': 'Rozmieszczenie',
    'Criticality tiers': 'Poziomy krytyczności',
    'Drawing units': 'Jednostki rysunku',
    'General tolerance': 'Tolerancja ogólna',
    'Decimal-place ladders': 'Drabinki miejsc dziesiętnych',
    'Gage choice thresholds': 'Progi doboru przyrządu',
    'Sheet header': 'Nagłówek karty',
    'Sheet output': 'Zapis karty',
    'Auto-reading': 'Odczyt automatyczny',
    'Text (OCR)': 'Tekst (OCR)',
    'Symbols and blocks': 'Symbole i bloki',
    'Language model (VLM)': 'Model językowy (VLM)',
    'Drag-box capture': 'Przechwytywanie ramką',
    'Hardware': 'Sprzęt',
    'Custom detector model': 'Własny model detektora',
    'UI scale (0 = automatic)': 'Skala interfejsu (0 = automatycznie)',
    'Drawing units and the tolerance ladder are on the Tolerances tab.':
        'Jednostki rysunku i drabinka tolerancji są na karcie Tolerancje.',
    'Bubble avoids lines wider than (pt)':
        'Bąbel omija linie grubsze niż (pt)',
    'Click capture radius (pt)':
        'Promień przechwytywania kliknięcia (pt)',
    'A drawing Bubbler detects as inch keeps its own answer; this is '
    'what a new or undecided drawing gets.':
        'Rysunek rozpoznany jako calowy zachowuje własną odpowiedź; to '
        'ustawienie dostaje rysunek nowy lub nierozpoznany.',
    'Pick this gage when the callout tolerance is at or below the '
    'value. Millimetre and inch drawings need their own numbers.':
        'Wybierz ten przyrząd, gdy tolerancja wywołania jest równa lub '
        'mniejsza od wartości. Rysunki milimetrowe i calowe mają własne '
        'liczby.',
    'Sheet language': 'Język karty',
    'Execution provider': 'Dostawca wykonania',
    'Default tier': 'Domyślny poziom',
    'Micrometer': 'Mikrometr',
    'Recover symbols and dims the PDF text layer misses':
        'Odzyskaj symbole i wymiary pominięte przez warstwę tekstową PDF',
    'OCR scanned and no-text pages':
        'OCR stron skanowanych i bez tekstu',
    'Detect GD&T symbols': 'Wykrywaj symbole GD&T',
    'Group callouts with the block detector':
        'Grupuj wywołania detektorem bloków',
    'Grow stacked callouts to the full stack':
        'Rozszerz wywołania w stosie na cały stos',
    'Inject detected symbols into text-layer reads':
        'Wstrzykuj wykryte symbole do odczytów warstwy tekstowej',
    'Detector debug overlay (adds a ribbon Debug button)':
        'Nakładka diagnostyczna detektorów (dodaje przycisk Debug na '
        'wstążce)',
    'Read callouts with the Florence-2 VLM (slow)':
        'Czytaj wywołania modelem Florence-2 VLM (wolne)',
    'Even when a text layer exists':
        'Nawet gdy istnieje warstwa tekstowa',
    'Inject detected symbols into VLM reads':
        'Wstrzykuj wykryte symbole do odczytów VLM',
    'Drag-box capture reads pixels (OCR or VLM), not the text layer':
        'Przechwytywanie ramką czyta piksele (OCR lub VLM), nie warstwę '
        'tekstową',
    'Use the GPU pack when installed':
        'Używaj pakietu GPU, gdy jest zainstalowany',
    'On: splice GD&T glyphs the detector found into blocks that already '
    'have a PDF text layer (a vector leader symbol is often missing '
    'from the text). Duplicates the text already shows are skipped.':
        'Włączone: wstaw znaki GD&T znalezione przez detektor do bloków, '
        'które mają już warstwę tekstową PDF (wektorowego symbolu przy linii '
        'odniesienia często brakuje w tekście). Duplikaty już widoczne w '
        'tekście są pomijane.',
    'Adds a ribbon Debug group: Overlay toggle plus a Layers menu to '
    'draw sections, detector blocks, and symbol boxes over the page.':
        'Dodaje na wstążce grupę Debug: przełącznik nakładki oraz menu '
        'Warstwy rysujące sekcje, bloki detektora i ramki symboli na '
        'stronie.',
    "On: splice GD&T glyphs the detector found into the VLM's text "
    '(fallback for glyphs the VLM misses). Off: pass only the category '
    'and let the VLM read the callout itself.':
        'Włączone: wstaw znaki GD&T znalezione przez detektor do tekstu '
        'VLM (zapas na znaki pominięte przez VLM). Wyłączone: przekaż '
        'tylko kategorię i pozwól VLM odczytać wywołanie samodzielnie.',
    'On: box drags re-read pixels with OCR or the VLM, ignoring the '
    'text layer. Avoids buried or oversized text. Off: use the text '
    'layer.':
        'Włączone: ramka odczytuje piksele przez OCR lub VLM, pomijając '
        'warstwę tekstową. Omija tekst ukryty lub przeskalowany. '
        'Wyłączone: użyj warstwy tekstowej.',
    'On by default. Once the pack is installed, detectors run on GPU. '
    'Untick to force CPU.':
        'Domyślnie włączone. Po zainstalowaniu pakietu detektory działają '
        'na GPU. Odznacz, aby wymusić CPU.',
    # Measure bar ops (L9)
    'not made until %s': 'powstaje dopiero w %s',
    'carried forward from %s: %s': 'przeniesione z %s: %s',
    're-measure: was %s at %s': 'zmierz ponownie: było %s w %s',
    'Machining stage you are inspecting. Ops run in sequence.':
        'Operacja obróbki, którą kontrolujesz. Operacje idą po kolei.',
    'made at': 'powstaje w',
    'any': 'dowolna',
    'Op that creates this characteristic. Earlier ops do not measure it.':
        'Operacja, w której powstaje ta cecha. Wcześniejsze operacje '
        'jej nie mierzą.',
    'recheck': 'kontrola ponowna',
    'Re-measure at every later op: the part distorts.':
        'Mierz ponownie w każdej kolejnej operacji: część się odkształca.',
    'how': 'czym',
    'Method or gage for this measurement.':
        'Metoda lub przyrząd dla tego pomiaru.',
    # Settings dialog input errors
    'UI scale must be a number': 'Skala interfejsu musi być liczbą',
    # FAI report settings (M1)
    'Report #': 'Raport nr',
    'FAI report': 'Raport FAI',
    'Show on the report': 'Pokaż na raporcie',
    'Logo': 'Logo',
    'Report logo': 'Logo raportu',
    'none (company name only)': 'brak (tylko nazwa firmy)',
    'Form ID': 'Nr formularza',
    'Form revision': 'Wersja formularza',
    'Paper': 'Papier',
    'Report language': 'Język raportu',
    'Part name': 'Nazwa części',
    'Drawing number': 'Numer rysunku',
    'Drawing rev': 'Wersja rysunku',
    'Part rev': 'Wersja części',
    'PO number': 'Numer zamówienia',
    'Serial or lot': 'Numer seryjny lub partia',
    'Feature column': 'Kolumna cechy',
    'Method column': 'Kolumna metody',
    'Comments column': 'Kolumna uwag',
    'Tolerance bar': 'Pasek tolerancji',
    'QA signature block': 'Blok podpisu kontroli',
    # correcting gentol block (gentol_edit)
    'General tolerances': 'Tolerancje ogólne',
    'Read off the drawing': 'Odczytane z rysunku',
    'Use what the drawing says': 'Użyj tego, co podaje rysunek',
    'Correct it for this drawing': 'Popraw dla tego rysunku',
    'Correction': 'Poprawka',
    'No block on this page -- taken from sheet 1':
        'Brak tabeli na tej stronie -- wzięte z arkusza 1',
    'Nothing found on this page': 'Nic nie znaleziono na tej stronie',
    'fine': 'dokładna',
    'medium': 'średnia',
    'coarse': 'zgrubna',
    'very coarse': 'bardzo zgrubna',
    'nominal, mm': 'wymiar nominalny, mm',
    'linear': 'liniowa',
    'angular, deg': 'kątowa, st.',
    'Decimal-place tolerances': 'Tolerancje wg miejsc dziesiętnych',
    'Angular': 'Kątowa',
    'deg': 'st.',
    'blank = from the standard': 'puste = z normy',
    'Fractional': 'Ułamkowa',
    'a whole-inch dim, e.g. 1/32': 'wymiar w calach całkowitych, np. 1/32',
    'Band table, as printed (optional):':
        'Tabela przedziałów, jak wydrukowana (opcjonalnie):',
    'One row per line. A band table overrides the ladder above, like a printed one.':
        'Jeden wiersz w linii. Tabela przedziałów ma pierwszeństwo przed drabinką powyżej, jak wydrukowana.',
    'linear bands': 'przedziały liniowe',
    'angular bands': 'przedziały kątowe',
    'radius bands': 'przedziały promieni',
    'decimal places': 'miejsca dziesiętne',
    'angular': 'kątowa',
    'fractional': 'ułamkowa',
    'standard': 'norma',
    'n/a': 'nd.',
    'Nothing to apply.': 'Nie ma czego zastosować.',
    'No band row read. Each row needs a range and a tolerance, e.g. "6 - 30 ±0.2".':
        'Nie odczytano wiersza. Każdy wiersz potrzebuje zakresu i tolerancji, np. "6 - 30 ±0,2".',
    'Decimal-place ladder not usable: %s':
        'Drabinka miejsc dziesiętnych nieużywalna: %s',
    'Apply the correction': 'Zastosuj poprawę',
    '%d bubbled rows took the old general tolerance. Untick any typed by hand.':
        'Tyle wierszy z balonami wzięło starą tolerancję ogólną: %d. Odznacz wpisane ręcznie.',
    'bubble': 'balon',
    'was -> now': 'było -> jest',
    'Hand-corrected for this drawing. Click to change.':
        'Poprawione ręcznie dla tego rysunku. Kliknij, aby zmienić.',
    'From page 1, reused here. Click to correct.':
        'Ze strony 1, użyte tutaj. Kliknij, aby poprawić.',
    'The general tolerance the next bubble inherits on this '
    'page. Click to correct.':
        'Tolerancja ogolna, ktora dziedziczy nastepny balon na tej '
        'stronie. Kliknij, aby poprawic.',
    'corrected by hand': 'poprawiona ręcznie',
    'general tolerance corrected, %d rows updated':
        'tolerancja ogólna poprawiona, zaktualizowano wierszy: %d',
    'general tolerance reset to drawing':
        'tolerancja ogólna przywrócona wg rysunku',
    'Write the tier in the sheet': 'Zapisz poziom w arkuszu',
    'Off: the tier stays on screen, where it groups balloons. On: the tier '
    'column of the sheet is filled with it. An inspector cannot act on a '
    'colour, so a delivered packet says nothing about it unless you ask.':
        'Wył.: poziom zostaje na ekranie, gdzie grupuje balony. Wł.: '
        'kolumna poziomu w arkuszu zostaje nim wypełniona. Kontroler nie '
        'może działać na podstawie koloru, więc przekazany pakiet nic o '
        'nim nie mówi, o ile o to nie poprosisz.',

    # first-run GPU offer (launcher._offer_gpu)
    'This computer has an NVIDIA card (driver %d) but Bubbler reads drawings on the CPU.':
        'Ten komputer ma kartę NVIDIA (sterownik %d), ale Bubbler czyta rysunki na CPU.',
    'The GPU pack installs separately to keep the download small. It speeds up detectors only; text reading is unchanged.\n\nSettings > Vision > Install or update GPU pack.':
        'Pakiet GPU instaluje się osobno, aby pobieranie było małe. Przyspiesza tylko detektory; czytanie tekstu bez zmian.\n\nUstawienia > Wizja > Zainstaluj lub zaktualizuj pakiet GPU.',
    'Open Settings': 'Otwórz ustawienia',
    'Not now': 'Nie teraz',
    'Do not show this again': 'Nie pokazuj tego ponownie',

    # W70 BASIC/REF on sheet
    'Spell out BASIC or REF on the sheet':
        'Wypisz BASIC lub REF w arkuszu',
    'A bubbled BASIC or REFERENCE dimension is an ordinary row either way. '
    'On: the word is written after the value, because a square bracket is '
    'easy to miss on a printed packet.':
        'Zabalonowany wymiar BASIC lub REFERENCE jest zwykłym wierszem w '
        'obu przypadkach. Wł.: słowo jest zapisywane po wartości, bo '
        'nawias kwadratowy łatwo przeoczyć na wydrukowanym pakiecie.',

    # scan-review scope presets (scanscope.py)
    'What to bubble by default': 'Co domyślnie balonować',
    'Inspection': 'Kontrola',
    'Edit presets...': 'Edytuj ustawienia wstępne...',
    'The sheet says which inspection this is in its Inspection type cell, '
    'and that wins over this default. Nothing is ever hidden from scan '
    'review -- only the starting tick changes.':
        'Arkusz podaje rodzaj kontroli w komórce Typ kontroli i to ma pierwszeństwo '
        'przed tym ustawieniem. Nic nie jest ukrywane w przeglądzie skanu -- '
        'zmienia się tylko początkowe zaznaczenie.',
    'A preset sets which callouts start TICKED in scan review. Nothing is '
    'hidden -- every callout found stays listed, so you can tick it yourself.':
        'Ustawienie wstępne ustala, które oznaczenia są ZAZNACZONE na starcie '
        'w przeglądzie skanu. Nic nie jest ukrywane -- każde znalezione '
        'oznaczenie zostaje na liście, więc możesz je zaznaczyć sam.',
    'GD&T and true position': 'GD&T i pozycja rzeczywista',
    'Surface finish (Ra, Rz)': 'Chropowatość powierzchni (Ra, Rz)',
    'BASIC [25] and REFERENCE (75)': 'BASIC [25] i REFERENCE (75)',
    'Threads (M8x1.25)': 'Gwinty (M8x1.25)',
    'Its own tolerance (25 +/-0.1, 25 H7)':
        'Własna tolerancja (25 +/-0,1, 25 H7)',
    'On the general-tolerance block only':
        'Tylko na bloku tolerancji ogólnych',
    'No tolerance from anywhere': 'Bez tolerancji z jakiegokolwiek źródła',
    'Add...': 'Dodaj...',
    'Rename...': 'Zmień nazwę...',
    'Remove': 'Usuń',
    'Add preset': 'Dodaj ustawienie wstępne',
    'Rename preset': 'Zmień nazwę ustawienia wstępnego',
    'Remove preset': 'Usuń ustawienie wstępne',
    'Name': 'Nazwa',
    'Preset %s already exists.':
        'Ustawienie wstępne %s już istnieje.',
    '%s is built-in and keeps its name -- drawings name it in the Inspection type cell. Add a new preset instead.':
        '%s jest wbudowane i zachowuje nazwę -- rysunki wskazują ją w komórce Typ kontroli. Zamiast tego dodaj nowe.',
    '%s is built-in and cannot be removed. Reset restores it as shipped.':
        '%s jest wbudowane i nie można go usunąć. Przywróć ustawia je jak dostarczono.',

    '- decides what starts ticked. Kept for this drawing.':
        '- decyduje, co jest zaznaczone na starcie. Zapamiętane dla tego '
        'rysunku.',

    # W3 broken-edge radius mark
    'This is a broken edge': 'To jest złamana krawędź',
    'Edge break = the general "break sharp edges" note; ISO '
    '2768-1 gives it a wide table. A dimensioned chamfer, fillet '
    'or spherical radius is a feature and takes the tighter '
    'linear table. Tick only when the callout IS the edge break.':
        'Złamanie krawędzi = ogólny zapis "stępić ostre krawędzie"; '
        'ISO 2768-1 daje mu szeroką tabelę. Wymiarowana faza, zaokrąglenie '
        'lub promień sferyczny to cecha i bierze ciaśniejszą tabelę '
        'liniową. Zaznacz tylko, gdy oznaczenie JEST złamaniem krawędzi.',
}
