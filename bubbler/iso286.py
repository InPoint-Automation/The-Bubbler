# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# ISO 286-1 fit limits, nominal 0 < D <= 500 mm.

import re as _re

# Band upper bounds, mm
BANDS = (3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500)

# IT grades, µm, per band
IT = {
    4:  (3, 4, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20),
    5:  (4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27),
    6:  (6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40),
    7:  (10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63),
    8:  (14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97),
    9:  (25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155),
    10: (40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250),
    11: (60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400),
    12: (100, 120, 150, 180, 210, 250, 300, 350, 400, 460, 520, 570,
         630),
}

# shaft upper deviations es (µm, <= 0), grade-independent
SHAFT_ES = {
    "d": (-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190,
          -210, -230),
    "e": (-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110,
          -125, -135),
    "f": (-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62,
          -68),
    "g": (-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20),
    "h": (0,) * 13,
}

# shaft lower deviations ei (µm, >= 0), grade-independent
SHAFT_EI = {
    "k": (0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5),
    "m": (2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23),
    "n": (4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40),
    "p": (6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68),
}

# r, s finer sub-bands: (upper_bound, ei)
SHAFT_EI_SPLIT = {
    "r": ((3, 10), (6, 15), (10, 19), (18, 23), (30, 28), (50, 34),
          (65, 41), (80, 43), (100, 51), (120, 54), (140, 63),
          (160, 65), (180, 68), (200, 77), (225, 80), (250, 84),
          (280, 94), (315, 98), (355, 108), (400, 114), (450, 126),
          (500, 132)),
    "s": ((3, 14), (6, 19), (10, 23), (18, 28), (30, 35), (50, 43),
          (65, 53), (80, 59), (100, 71), (120, 79), (140, 92),
          (160, 100), (180, 108), (200, 122), (225, 130), (250, 140),
          (280, 158), (315, 170), (355, 190), (400, 208), (450, 232),
          (500, 252)),
}

_FITCODE = _re.compile(r"^(JS|js|[A-HK-NPRSa-hk-nprs])(\d{1,2})$")


def band_index(D):
    if D is None or D <= 0 or D > BANDS[-1]:
        return None
    for i, hi in enumerate(BANDS):
        if D <= hi:
            return i
    return None


def it_value(D, grade):
    """Standard tolerance ITn in µm, or None outside the tables."""
    bi = band_index(D)
    row = IT.get(grade)
    if bi is None or row is None:
        return None
    return row[bi]


def _split_ei(letter, D):
    for hi, v in SHAFT_EI_SPLIT[letter]:
        if D <= hi:
            return v
    return None


def _shaft_ei(letter, D, grade):
    """Lower deviation ei (µm) of a shaft letter k..s for the rules."""
    bi = band_index(D)
    if bi is None:
        return None
    if letter in ("r", "s"):
        return _split_ei(letter, D)
    if letter == "k":
        return SHAFT_EI["k"][bi] if 4 <= grade <= 7 else 0
    return SHAFT_EI[letter][bi]


def _delta(D, grade):
    """delta = ITn - IT(n-1); 0 for sizes <= 3 mm."""
    if D <= 3:
        return 0
    a = it_value(D, grade)
    b = it_value(D, grade - 1)
    if a is None or b is None:
        return None
    return a - b


def fit_limits(D, code):
    """(upper, lower) deviations in mm for fit `code` at nominal D."""
    if D is None:
        return None
    m = _FITCODE.match(str(code).strip())
    if not m:
        return None
    letter, grade = m.group(1), int(m.group(2))
    bi = band_index(D)
    t = it_value(D, grade)
    if bi is None or t is None:
        return None

    if letter in ("JS", "js"):
        h = t / 2.0
        return (round(h / 1000.0, 4), round(-h / 1000.0, 4))

    if letter.islower():                      # shaft
        if letter in SHAFT_ES:
            es = SHAFT_ES[letter][bi]
            ei = es - t
        else:
            ei = _shaft_ei(letter, D, grade)
            if ei is None:
                return None
            es = ei + t
        return (round(es / 1000.0, 4), round(ei / 1000.0, 4))

    # hole
    L = letter
    if L in ("D", "E", "F", "G", "H"):
        EI = -SHAFT_ES[L.lower()][bi]
        ES = EI + t
    elif L in ("K", "M", "N"):
        if grade <= 8:
            d = _delta(D, grade)
            ei = _shaft_ei(L.lower(), D, grade)
            if d is None or ei is None:
                return None
            ES = -ei + d
            # M6 250-315 mm exception
            if L == "M" and grade == 6 and 250 < D <= 315:
                ES = -9
        elif L == "N":
            ES = 0
        else:
            return None                       # K/M above grade 8
        EI = ES - t
    elif L in ("P", "R", "S"):
        ei = _shaft_ei(L.lower(), D, grade)
        if ei is None:
            return None
        if grade <= 7:
            d = _delta(D, grade)
            if d is None:
                return None
            ES = -ei + d
        else:
            ES = -ei
        EI = ES - t
    else:
        return None
    return (round(ES / 1000.0, 4), round(EI / 1000.0, 4))


def is_fit_code(s):
    """True when `s` looks like a single supported ISO 286 class."""
    return bool(_FITCODE.match(str(s or "").strip()))
