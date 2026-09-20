# Bubbler - Copyright (C) 2026 InPoint Automation Sp. z o.o.
# Licensed under the GNU General Public License v3 or later; see LICENSE.
#
# ONE row for sheet and FAI report.

from dataclasses import dataclass, field
from typing import Optional, Union

from .common import (GO_WORDS, NOGO_WORDS, ROUND_DP, base_of, latest_op,
                     method_for_gage, op_value, prefix_of, requirement_text,
                     tol_offsets)
from .config import ops_seq
from .scanlib import basic_ref_kind
from .units import NOMINAL_DP

PASS = "PASS"
FAIL = "FAIL"


def decimals(units="iso_mm"):
    """Requirement decimal places matching app nominal precision."""
    return NOMINAL_DP.get(units or "iso_mm", 2)


def _num(v):
    """Float or None when blank or not number."""
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _measured(v):
    """Reading as row carries it: float | "GO" | "NOGO" | None."""
    if v is None or str(v).strip() == "":
        return None
    f = _num(v)
    if f is not None:
        return f
    s = str(v).strip().upper()
    if s in GO_WORDS:
        return "GO"
    if s in NOGO_WORDS:
        return "NOGO"
    return str(v).strip()                 # unjudgeable word


@dataclass
class Row:
    """One characteristic: required vs found."""

    bubble: str = ""
    feature: str = ""
    prefix: str = ""
    nominal: Optional[float] = None
    tol_plus: Optional[float] = None
    tol_minus: Optional[float] = None
    limit: Optional[str] = None           # max | min | None(two-sided)
    measured: Union[float, str, None] = None
    method: str = ""
    comment: str = ""
    units: str = "iso_mm"
    tier: str = field(default="", repr=False)
    op: str = field(default="", repr=False)

    # ------------------------------------------------------- requirement
    @property
    def requirement(self):
        """`Ø12.50 ±0.05`, `20.00 +0.10/-0.00`, `GO/NOGO`."""
        return requirement_text(self.nominal, self.tol_plus, self.tol_minus,
                                self.prefix, decimals(self.units),
                                limit=self.limit)

    @property
    def limits(self):
        """(low, high) acceptance limits matching common.limits_of."""
        t = self.nominal
        if t is None:
            return (None, None)
        if self.limit == "max":          # lower open
            return (None, t + (self.tol_plus or 0.0))
        if self.limit == "min":          # upper open
            return (t - (self.tol_minus or 0.0), None)
        if self.tol_plus is None and self.tol_minus is None:
            return (None, None)
        lo = t - (0.0 if self.tol_minus is None else self.tol_minus)
        hi = t + (0.0 if self.tol_plus is None else self.tol_plus)
        return (lo, hi)

    @property
    def toleranced(self):
        """Has tolerance to judge against."""
        return (self.nominal is not None
                and (self.limit in ("max", "min")
                     or self.tol_plus is not None
                     or self.tol_minus is not None))

    # ------------------------------------------------------------ verdict
    @property
    def result(self):
        """PASS / FAIL / "" (no verdict) matching column L."""
        m = self.measured
        if str(self.bubble or "").strip() == "" or m is None:
            return ""
        if isinstance(m, str):
            u = m.upper()
            if u in GO_WORDS:
                return PASS
            if u in NOGO_WORDS:
                return FAIL
            return ""
        if not self.toleranced:
            return ""
        lo, hi = self.limits
        if lo is not None and round(m - lo, ROUND_DP) < 0:
            return FAIL
        if hi is not None and round(hi - m, ROUND_DP) < 0:
            return FAIL
        return PASS

    @property
    def deviation(self):
        """measured - nominal or None when nothing to subtract."""
        if not isinstance(self.measured, float) or self.nominal is None:
            return None
        return self.measured - self.nominal

    # ------------------------------------------------------------ sources
    @classmethod
    def from_ledger(cls, d, cfg=None, units="iso_mm"):
        """Build row from ledger entry with tol triple via common.tol_offsets."""
        cfg = cfg or {}
        d = d or {}
        nom = _num(d.get("nominal"))
        plus, minus = tol_offsets(d)
        op = latest_op(d.get("ops"), ops_seq(cfg))
        feature = str(d.get("feature") or "")
        if cfg.get("sheet_basic_ref_label"):
            kind = basic_ref_kind(feature)
            if kind:
                feature = "%s %s" % (feature, kind)
        return cls(
            bubble=str(d.get("bubble") or ""),
            feature=feature,
            prefix=prefix_of(feature),
            nominal=nom, tol_plus=plus, tol_minus=minus,
            limit=(d.get("limit") or None),
            measured=_measured(op_value(op[1], d) if op
                               else d.get("measured")),
            method=((op[1].get("method") if op else "")
                    or method_for_gage(d.get("gage")) or ""),
            comment=str(d.get("comment") or d.get("comments") or ""),
            units=units,
            tier=str(d.get("tier") or ""), op=(op[0] if op else ""))


def rows_from_ledger(ledger, cfg=None, units="iso_mm"):
    """Every bubbled characteristic, balloon order, no own numbering."""
    rows = [Row.from_ledger(d, cfg, units) for d in (ledger or [])
            if str(d.get("bubble") or "").strip() != ""]
    rows.sort(key=lambda r: (base_of(r.bubble), str(r.bubble)))
    return rows


def summary(rows):
    """{chars, measured, passed, failed, yield, disposition}."""
    rows = list(rows or [])
    verdicts = [r.result for r in rows]
    chars = sum(1 for r in rows if r.toleranced or r.result)
    meas = sum(1 for r in rows if r.measured is not None)
    npass = verdicts.count(PASS)
    nfail = verdicts.count(FAIL)
    if nfail:
        disp = "REJECTED"
    elif chars and npass == chars:
        disp = "ACCEPTED"
    else:
        disp = "IN PROGRESS"
    return {"chars": chars, "measured": meas, "passed": npass,
            "failed": nfail,
            "yield": (npass / float(npass + nfail)) if npass + nfail else None,
            "disposition": disp}
