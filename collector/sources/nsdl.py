"""NSDL's FPI Monitor (fpi.nsdl.co.in) — the depository's FINAL foreign-portfolio figures, as HTML tables.

Surveyed 18 Nov 2026 (three plain GETs, no cookie, no form post):
  /web/Reports/Yearwise.aspx?RptType=5   FPI net investment by FINANCIAL year since 1992-93
       <tr><td>2025-26</td><td>-180832</td>…   first figure after the year = Equity, INR crore
  /web/Reports/Yearwise.aspx?RptType=6   the CURRENT calendar year by month (other years need the form post: not used)
       <tr><td>January</td><td>-35962</td>… · "Total - 2026" · "** up to 18 Nov 2026"
  /web/Reports/Monthly.aspx              every reporting day of the current month
       <tr><td>18-Nov-2026</td><td>Equity</td><td>Stock Exchange</td><td>gross buy</td><td>gross sell</td><td>net</td>…
       <tr><td>Primary market &amp; others</td><td>buy</td><td>sell</td><td>net</td>…      negatives as (123.45)

These are NOT NSE's provisional cash figures (`flows.latest`): FPIs only, final, equity incl. the primary market, and
stamped with the REPORTING date. The two series sit side by side on the page and are never merged. There is no DII
equivalent anywhere (SEBI's mutual-fund table is one part of DII and two weeks late).
"""
from __future__ import annotations

import datetime as dt
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..errors import SourceChanged
from ..http import Session

BASE = "https://www.fpi.nsdl.co.in/web/Reports"
YEARS = BASE + "/Yearwise.aspx?RptType=5"
MONTHS = BASE + "/Yearwise.aspx?RptType=6"
DAYS = BASE + "/Monthly.aspx"
SOURCE = "nsdl"

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]
_FY = re.compile(r"^(\d{4})-(\d{2})\b")
_UPTO = re.compile(r"up\s*to\s+(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", re.IGNORECASE)
_DAY = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")


def _num(text: str) -> float | None:
    """'-35962' · '5,350.82' · '(371.45)' -> float; anything else None."""
    s = (text or "").replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return None
    return -v if neg else v


def _date(day: str, mon: str, year: str) -> str | None:
    try:
        return dt.datetime.strptime(f"{int(day):02d} {mon[:3].title()} {year}", "%d %b %Y").date().isoformat()
    except ValueError:
        return None


def _rows(html: str) -> list[list[str]]:
    """Every <tr> of every leaf table as a list of cell texts (the pages nest layout tables)."""
    out = []
    for table in HTMLParser(html or "").css("table"):
        if table.css_first("table table"):
            continue
        for tr in table.css("tr"):
            cells = [c.text(strip=True) for c in tr.css("th,td")]
            if any(cells):
                out.append(cells)
    return out


def _upto(rows: list[list[str]]) -> str | None:
    for r in rows:
        m = _UPTO.search(" ".join(r))
        if m:
            return _date(*m.groups())
    return None


def parse_years(html: str) -> dict:
    """-> {asOf, years: [["2016-17", 55703.0], …]} oldest first; the last one is the year in progress."""
    rows = _rows(html)
    years = []
    for r in rows:
        m = _FY.match(r[0])
        if m and len(r) > 1:
            v = _num(r[1])
            if v is None:
                raise SourceChanged(SOURCE, f"years: no equity figure beside {r[0]!r}", YEARS)
            years.append([f"{m.group(1)}-{m.group(2)}", v])
    if len(years) < 20 or not any("Equity" in c for r in rows for c in r):
        raise SourceChanged(SOURCE, f"years: expected 20+ financial-year rows under an Equity column, got {len(years)}", YEARS)
    return {"asOf": _upto(rows), "years": years}


def parse_months(html: str) -> dict:
    """-> {asOf, year, months: [["2026-01", -35962.0], …], total} for the calendar year the page shows."""
    rows = _rows(html)
    year, total, found = None, None, {}
    for r in rows:
        head = r[0].lower()
        if head.startswith("total") and len(r) > 1:
            m = re.search(r"(\d{4})", r[0])
            year, total = (int(m.group(1)) if m else None), _num(r[1])
            continue
        name = re.sub(r"[^a-z]", "", head)
        if name in _MONTHS and len(r) > 1:
            v = _num(r[1])
            if v is None:
                raise SourceChanged(SOURCE, f"months: no equity figure beside {r[0]!r}", MONTHS)
            found[_MONTHS.index(name) + 1] = v
    if not found or year is None or total is None:
        raise SourceChanged(SOURCE, "months: no month rows or no 'Total - <year>' row", MONTHS)
    if abs(sum(found.values()) - total) > len(found):      # each month is rounded to a crore
        raise SourceChanged(SOURCE, f"months: the months sum to {sum(found.values()):.0f}, the page's total says {total:.0f}", MONTHS)
    return {"asOf": _upto(rows), "year": year, "total": total,
            "months": [[f"{year}-{k:02d}", found[k]] for k in sorted(found)]}


def parse_days(html: str) -> list[dict]:
    """-> [{date, buy, sell, net, primary}] for the current month, oldest first: equity through the exchanges, and the
    primary-market line under it (IPOs, QIPs and other issues — what an IPO desk wants from this page)."""
    out, cur = [], None
    for r in _rows(html):
        m = _DAY.match(r[0])
        if m and len(r) >= 6 and r[1] == "Equity" and r[2].startswith("Stock"):
            cur = {"date": _date(*m.groups()), "buy": _num(r[3]), "sell": _num(r[4]), "net": _num(r[5]), "primary": None}
            if not cur["date"] or cur["net"] is None:
                raise SourceChanged(SOURCE, f"days: unreadable equity row {r[:6]}", DAYS)
            out.append(cur)
        elif cur is not None and r[0].lower().startswith("primary") and len(r) >= 4:
            cur["primary"] = _num(r[3])
            cur = None
        elif m:
            cur = None
    if not out:
        raise SourceChanged(SOURCE, "days: no 'Equity / Stock Exchange' rows", DAYS)
    return sorted(out, key=lambda d: d["date"])


def fetch(session: Session) -> dict:
    """Three GETs -> {years, months, days}. Any page that is empty or reshaped raises SourceChanged."""
    return {
        "years": parse_years(session.get_text(YEARS, source=SOURCE)),
        "months": parse_months(session.get_text(MONTHS, source=SOURCE)),
        "days": parse_days(session.get_text(DAYS, source=SOURCE)),
    }
