# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# Demo FAI rows, one of every row kind.

from .reportrow import Row

# (feature, prefix, nominal, plus, minus, limit, measured, method, comment)
_KINDS = (
    ("hole", "Ø", 12.5, 0.05, 0.05, None, 12.51, "CMM", ""),
    ("length", "", 40.0, 0.1, 0.0, None, 40.2, "caliper", "rework"),
    ("M6 thread", "", None, None, None, None, "GO", "GO-NOGO", ""),
    ("Ra max", "", 3.2, 0.0, None, "max", 2.9, "visual", ""),
    ("width", "", 25.0, 0.2, 0.2, None, 25.18, "micrometer", ""),
    ("slot", "", 8.0, 0.1, 0.1, None, None, "", ""),
    ("M8 thread", "", None, None, None, None, "NOGO", "GO-NOGO", "scrap"),
    ("wall", "", 2.0, 0.0, 0.1, "min", 2.05, "caliper", ""),
    ("bore", "Ø", 30.0, 0.021, 0.0, None, 30.01, "CMM", ""),
)


def demo_rows(n=45, units="iso_mm"):
    """Row nominal nudged so no two rows alike."""
    out = []
    for i in range(n):
        feat, pre, nom, plus, minus, lim, meas, meth, com = \
            _KINDS[i % len(_KINDS)]
        bump = (i // len(_KINDS)) * 1.0
        if nom is not None:
            nom = round(nom + bump, 6)
            if isinstance(meas, float):
                meas = round(meas + bump, 6)
        out.append(Row(bubble=str(i + 1), feature=feat, prefix=pre,
                       nominal=nom, tol_plus=plus, tol_minus=minus,
                       limit=lim, measured=meas, method=meth, comment=com,
                       units=units))
    return out


def preview_png(show=None, paper="a4", amber_pct=90, logo=None, lang="en",
                company="", form_id="", customer="", inspector="",
                width_px=520, n=10, inspection_type="First article"):
    """Settings preview page. ~20 ms, UI thread OK."""
    import fitz
    from . import report_pdf
    hdr = dict(company=company, report_id="PN-100-A-20260101",
               part_no="PN-100", part_name="Demo bracket",
               drawing="PN-100-DWG", dwg_rev="A", part_rev="A", po="PO-1",
               customer=customer or "Customer", material="6061-T6",
               serial="SN-001", inspector=inspector or "Inspector",
               date="2026-01-01", units="mm", form_id=form_id,
               inspection_type=inspection_type, show=dict(show or {}))
    doc = fitz.open()
    try:
        report_pdf.append_report_pages(doc, hdr, demo_rows(n), lang=lang,
                                       logo=logo, paper=paper,
                                       amber_pct=amber_pct)
        page = doc[0]
        z = float(width_px) / page.rect.width
        return page.get_pixmap(matrix=fitz.Matrix(z, z),
                               alpha=False).tobytes("png")
    finally:
        doc.close()
