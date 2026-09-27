"""NSE corporate announcements, market-wide, over a date window. One call per index answers every listed
company at once (live 26 Sep 2026: 3,883 mainboard rows for 22–26 Sep, ~2.8 MB; 842 SME rows), each row
carrying the NSE symbol, so no scrip-code map is needed. Reachable from GitHub's runners, unlike
api.bseindia.com.

Endpoint (docs/mined/nse-bse.md, `announcements`):
  GET https://www.nseindia.com/api/corporate-announcements?index=equities|sme&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY
Response: a list of {symbol, sm_name, desc (category), attchmntText (the summary line), attchmntFile (full PDF URL),
          sort_date "2026-09-25 18:21:31", seq_id, ...}.

NSE's summary is sometimes only "has informed the Exchange about General Updates" (JSW Cement, 25 Sep 2026, whose
BSE headline named the subsidiary's DRHP): the substance is in the PDF, which this pipeline never reads. Recall is
partial by construction; what a row does say is precise.
"""
from __future__ import annotations

import datetime as dt

from ..errors import SourceChanged
from ..http import NSE

PATH = "/api/corporate-announcements"
REFERER = NSE + "/companies-listing/corporate-filings-announcements"


def params_for(index: str, from_date: dt.date, to_date: dt.date) -> dict:
    return {"index": index, "from_date": from_date.strftime("%d-%m-%Y"), "to_date": to_date.strftime("%d-%m-%Y")}


def parse(payload, *, source: str = "nse_ann", url: str | None = None) -> list[dict]:
    """[{symbol, company, category, text, url, date, seqId}]. Raises SourceChanged on a shape that is not the list."""
    if not isinstance(payload, list):
        raise SourceChanged(source, f"expected a list, got {type(payload).__name__}", url)
    out = []
    for r in payload:
        if not isinstance(r, dict):
            continue
        if "symbol" not in r or ("attchmntText" not in r and "desc" not in r):
            raise SourceChanged(source, f"announcement row lacks symbol/attchmntText: {sorted(r)[:8]}", url)
        date = r.get("sort_date") or ""
        out.append({
            "symbol": (r.get("symbol") or "").strip().upper() or None,
            "company": (r.get("sm_name") or "").strip() or None,
            "category": (r.get("desc") or "").strip() or None,
            "text": " ".join((r.get("attchmntText") or "").split()),
            "url": (r.get("attchmntFile") or "").strip() or None,
            "date": date[:10] if len(date) >= 10 else None,
            "seqId": str(r.get("seq_id") or "") or None,
        })
    return out


def fetch(session, index: str, from_date: dt.date, to_date: dt.date, *, source: str = "nse_ann") -> list[dict]:
    payload = session.nse_json(PATH, params_for(index, from_date, to_date), source=source, referer=REFERER)
    return parse(payload, source=source, url=PATH)
