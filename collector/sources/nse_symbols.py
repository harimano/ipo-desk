"""NSE's own lists of traded equities: company name -> symbol. Mainboard EQUITY_L.csv and Emerge
SME_EQUITY_L.csv on nsearchives (seen live 17 Sep 2026: 2,577 and 572 rows). The two files spell their
headers differently ("NAME OF COMPANY" / "NAME_OF_COMPANY"), so columns are found by meaning."""
from __future__ import annotations

import csv
import io

from ..errors import SourceChanged, SourceError
from ..http import NSE_ARCHIVES

SRC = "nsearchives"
LISTS = (NSE_ARCHIVES + "/content/equities/EQUITY_L.csv",
         NSE_ARCHIVES + "/emerge/corporates/content/SME_EQUITY_L.csv")


def parse(text: str, *, url: str = "") -> list[dict]:
    rows = list(csv.reader(io.StringIO(text or "")))
    if not rows:
        raise SourceChanged(SRC, "equity list is empty", url)
    head = [h.strip().upper().replace("_", " ") for h in rows[0]]
    if "SYMBOL" not in head or "NAME OF COMPANY" not in head:
        raise SourceChanged(SRC, f"equity list header changed: {rows[0][:6]}", url)
    si, ni = head.index("SYMBOL"), head.index("NAME OF COMPANY")
    out = [{"symbol": r[si].strip().upper(), "name": r[ni].strip()} for r in rows[1:]
           if len(r) > max(si, ni) and r[si].strip() and r[ni].strip()]
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
