"""InvestorGain live-IPO-GMP report (id 331) via its cloud JSON backend — the JSON-first GMP source.

  https://webnodejs.investorgain.com/cloud/v2/report/data-read/331/{page}/{month}/{year}/{fy}/0/all

page = 1, month/year = today, fy = Indian financial year "YYYY-YY" (April–March, e.g. "2026-27"),
category = all. No auth; the site wants its own Referer/Origin. The report page itself is Next.js
client-rendered, so plain HTML is empty — hence the XHR endpoint (found via IPOFetch scraper/gmp.py).

Response: {"reportTableData": [ {Name: '<a href="…">Kanohar Electricals Ltd IPO</a>',
           GMP: '&#8377;<b>45</b> (12.5%)' | '--', Sub, "Price (₹)", "IPO Size", Lot, "Updated-On",
           "~ipo_status1": U|O|C, "~IPO_Category", "~Srt_Open", "~Srt_Close", "~Str_Listing", …} ]}
Fields are undocumented and carry HTML fragments — tags are stripped with selectolax.

The v1 endpoint retired in July 2026 by answering {"msg": "API not found"}; v2 may follow, so that body
(or zero rows) raises SourceChanged rather than returning an empty list.
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from selectolax.parser import HTMLParser

from ..errors import SourceChanged
from ._parse import clean, compute_gmp_pct, parse_money, parse_pct, upper_band

SOURCE = "investorgain"
BASE = "https://webnodejs.investorgain.com/cloud/v2/report/data-read/331"
PAGE_URL = "https://www.investorgain.com/report/live-ipo-gmp/331/ipo/"
HEADERS = {"Accept": "application/json", "Referer": PAGE_URL, "Origin": "https://www.investorgain.com"}
IST = ZoneInfo("Asia/Kolkata")

STATUS = {"U": "Upcoming", "O": "Open", "C": "Closed", "L": "Listed"}
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def fiscal_year(d: dt.date) -> str:
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def url_for(d: dt.date, page: int = 1) -> str:
    return f"{BASE}/{page}/{d.month}/{d.year}/{fiscal_year(d)}/0/all"


def strip_tags(fragment) -> str:
    if fragment is None:
        return ""
    if not isinstance(fragment, str):
        return clean(str(fragment))
    return clean(HTMLParser(fragment).text(separator=" "))


def _name(fragment) -> str:
    """Prefer the link text — the cell may carry badges/spans beside the <a>."""
    if isinstance(fragment, str) and "<a" in fragment:
        a = HTMLParser(fragment).css_first("a")
        if a is not None and clean(a.text()):
            return clean(a.text())
    return strip_tags(fragment)


def _date(value) -> str | None:
    """'2026-09-15' / '15-Sep-2026' / '15 Sep 2026' -> ISO date; else the cleaned text or None."""
    s = strip_tags(value)
    if not s or s in ("--", "-"):
        return None
    if _ISO.match(s):
        return s[:10]
    m = re.match(r"^(\d{1,2})[ -]([A-Za-z]{3})[A-Za-z]*[ ,-]+(\d{4})", s)
    if m and m.group(2).lower() in _MONTHS:
        try:
            return dt.date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
        except ValueError:
            return s
    return s


def _pick(row: dict, *keys):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    lower = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, ""):
            return v
    return None


def parse_investorgain(data) -> list[dict]:
    if not isinstance(data, dict):
        raise SourceChanged(SOURCE, f"expected a JSON object, got {type(data).__name__}", BASE)
    if data.get("msg") == "API not found" or (not data.get("reportTableData") and "msg" in data):
        raise SourceChanged(SOURCE, f"endpoint answered {data.get('msg')!r} — v2 retired?", BASE)
    rows = data.get("reportTableData")
    if not isinstance(rows, list) or not rows:
        raise SourceChanged(SOURCE, "reportTableData missing or empty", BASE)
    out: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        name = _name(_pick(raw, "Name", "IPO", "~IPO_Name"))
        if not name:
            continue
        gmp_text = strip_tags(_pick(raw, "GMP", "GMP(₹)", "GMP (₹)"))
        gmp = parse_money(gmp_text.split("(")[0]) if gmp_text and gmp_text not in ("--", "-") else None
        price_text = strip_tags(_pick(raw, "Price (₹)", "Price", "Price (Rs)", "~Price"))
        st = strip_tags(_pick(raw, "~ipo_status1", "Status"))
        r = {
            "name": name,
            "gmp": gmp,
            "gmpPct": parse_pct(gmp_text) if gmp is not None else None,
            "bandHigh": upper_band(price_text),
            "open": _date(_pick(raw, "~Srt_Open", "Open", "~Open")),
            "close": _date(_pick(raw, "~Srt_Close", "Close", "~Close")),
            "listing": _date(_pick(raw, "~Str_Listing", "~Srt_Listing", "Listing", "~Listing")),
            "type": strip_tags(_pick(raw, "~IPO_Category", "Type")),
            "status": STATUS.get(st.upper(), st) if st else "",
            "updated": strip_tags(_pick(raw, "Updated-On", "~Updated_On", "Updated")),
            "source": SOURCE,
        }
        compute_gmp_pct(r)
        out.append(r)
    if not out:
        raise SourceChanged(SOURCE, f"{len(rows)} rows but none had a name — field names changed?", BASE)
    return out


def as_of(rows: list[dict]) -> str | None:
    """Latest 'Updated-On' stamp across rows, as an ISO date when parseable."""
    stamps = [r.get("updated") for r in rows if r.get("updated")]
    if not stamps:
        return None
    iso = [d for d in (_date(s) for s in stamps) if d and _ISO.match(d)]
    return max(iso) if iso else max(stamps)


def fetch(session, today: dt.date | None = None) -> list[dict]:
    d = today or dt.datetime.now(IST).date()
    data = session.get_json(url_for(d), source=SOURCE, headers=HEADERS)
    return parse_investorgain(data)
