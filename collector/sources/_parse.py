"""Number/text helpers shared by the GMP sources.

`parse_money`, `parse_pct`, `upper_band`, `clean` are copied verbatim from chirag127/oriz-ipo
`src/ipo_watch/util.py` (MIT, see THIRD_PARTY.md); `compute_gmp_pct` is adapted from its
`sources/base.py` to work on the plain row dicts used here.

Row dicts use DATA-SCHEMA field names: name, gmp, gmpPct, bandHigh, open, close, listing, status, type,
plus `source`. Missing values are None / "".
"""
from __future__ import annotations

import re

_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_money(text: str | None) -> float | None:
    """'₹154' / '154' / '- (Ni)' -> float or None."""
    if not text:
        return None
    m = _NUM.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def parse_pct(text: str | None) -> float | None:
    """'(30.51%)' / '30.51%' -> 30.51; None if absent."""
    if not text:
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) if m else None


def upper_band(price_band: str | None) -> float | None:
    """'₹100-108' / '100 to 108' -> 108.0 (highest number found)."""
    if not price_band:
        return None
    nums = [float(n.replace(",", "")) for n in _NUM.findall(price_band.replace(",", ""))]
    return max(nums) if nums else None


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def compute_gmp_pct(row: dict) -> None:
    """Fill gmpPct from gmp + upper price band when the site didn't give a %."""
    if row.get("gmpPct") is not None:
        return
    ub = row.get("bandHigh")
    if row.get("gmp") is not None and ub:
        row["gmpPct"] = round(row["gmp"] / ub * 100, 2)
