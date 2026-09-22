"""NSE's own lists of traded equities: company name -> symbol. Mainboard EQUITY_L.csv and Emerge
SME_EQUITY_L.csv on nsearchives (seen live 17 Sep 2026: 2,577 and 572 rows). The two files spell their
headers differently ("NAME OF COMPANY" / "NAME_OF_COMPANY") and their listing dates differently ("06-OCT-2008" /
"17-Sep-26"), so columns are found by meaning and the date is carried as ISO `listedOn` when it parses."""
from __future__ import annotations

import csv
import io
import re

from ..errors import SourceChanged, SourceError
from ..http import NSE_ARCHIVES

SRC = "nsearchives"
LISTS = (NSE_ARCHIVES + "/content/equities/EQUITY_L.csv",
         NSE_ARCHIVES + "/emerge/corporates/content/SME_EQUITY_L.csv")


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"), 1)}


def parse_listed_on(text: str) -> str | None:
    """'06-OCT-2008' / '17-Sep-26' -> ISO date; None when it does not parse."""
    m = re.match(r"^\s*(\d{1,2})-([A-Za-z]{3})-(\d{2}|\d{4})\s*$", text or "")
    if not m or m.group(2).lower() not in _MONTHS:
        return None
    y = int(m.group(3))
    y = y + 2000 if y < 100 else y
    return f"{y}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


def parse(text: str, *, url: str = "") -> list[dict]:
    """[{symbol, name, listedOn?}] — `listedOn` only when the list carries a parseable listing date."""
    rows = list(csv.reader(io.StringIO(text or "")))
    if not rows:
        raise SourceChanged(SRC, "equity list is empty", url)
    head = [h.strip().upper().replace("_", " ") for h in rows[0]]
    if "SYMBOL" not in head or "NAME OF COMPANY" not in head:
        raise SourceChanged(SRC, f"equity list header changed: {rows[0][:6]}", url)
    si, ni = head.index("SYMBOL"), head.index("NAME OF COMPANY")
    di = head.index("DATE OF LISTING") if "DATE OF LISTING" in head else None
    out = []
    for r in rows[1:]:
        if len(r) <= max(si, ni) or not r[si].strip() or not r[ni].strip():
            continue
        row = {"symbol": r[si].strip().upper(), "name": r[ni].strip()}
        listed = parse_listed_on(r[di]) if di is not None and len(r) > di else None
        if listed:
            row["listedOn"] = listed
        out.append(row)
    if len(out) < 50:
        raise SourceChanged(SRC, f"equity list has only {len(out)} rows", url)
    return out


def companies(session) -> list[dict]:
    """[{name, symbol}] from both lists. The mainboard list is required; the SME list is best effort."""
    out = parse(session.get_text(LISTS[0], source=SRC), url=LISTS[0])
    try:
        out += parse(session.get_text(LISTS[1], source=SRC), url=LISTS[1])
    except SourceError:
        pass
    return out
