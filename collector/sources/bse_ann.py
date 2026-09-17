"""BSE corporate announcements for one scrip code over a date window.

Endpoint (from nse-bse.md, the `bse` package's announcements() method):
  GET https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w
      ?pageno=1&strCat=-1&subcategory=-1&strPrevDate=YYYYMMDD&strToDate=YYYYMMDD
      &strSearch=P&strscrip=500325&strType=C
Response: {"Table": [ {NEWSID, SCRIP_CD, NEWSSUB, DT_TM, NEWS_DT, ATTACHMENTNAME "<guid>.pdf", HEADLINE,
           CATEGORYNAME, SUBCATNAME, SLONGNAME, ...} ], "Table1": [{"ROWCNT": n}]}
Paginated: loop pageno until len(rows) >= Table1[0].ROWCNT.
ATTACHMENTNAME is a bare filename; the public URL convention is
  https://www.bseindia.com/xml-data/corpfiling/AttachLive/<ATTACHMENTNAME>

Zero rows for a scrip is a legitimate answer (a parent that said nothing in the window), so this
parser raises SourceChanged only on a malformed shape, never on an empty Table.
"""
from __future__ import annotations

import datetime as dt

from ..errors import SourceChanged
from ..http import Session

PATH = "/AnnSubCategoryGetData/w"
ATTACH_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
MAX_PAGES = 5


def _ymd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def params_for(scrip: str, from_date: dt.date, to_date: dt.date, page: int = 1) -> dict:
    return {
        "pageno": page, "strCat": "-1", "subcategory": "-1",
        "strPrevDate": _ymd(from_date), "strToDate": _ymd(to_date),
        "strSearch": "P", "strscrip": str(scrip), "strType": "C",
    }


def _iso_date(row: dict) -> str | None:
    for k in ("NEWS_DT", "DT_TM", "News_submission_dt", "DissemDT"):
        v = row.get(k)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return None


def attachment_url(name: str | None) -> str | None:
    if not name or not isinstance(name, str):
        return None
    name = name.strip()
    if not name:
        return None
    if name.lower().startswith("http"):
        return name
    return ATTACH_BASE + name


def parse_page(payload, *, source: str = "bse_ann", url: str | None = None) -> tuple[list[dict], int]:
    """Return (rows, rowcnt). Raises SourceChanged if the shape is not the documented one."""
    if not isinstance(payload, dict) or "Table" not in payload:
        raise SourceChanged(source, "response lacks 'Table'", url)
    table = payload.get("Table")
    if not isinstance(table, list):
        raise SourceChanged(source, "'Table' is not a list", url)
    t1 = payload.get("Table1")
    rowcnt = None
    if isinstance(t1, list) and t1 and isinstance(t1[0], dict) and "ROWCNT" in t1[0]:
        try:
            rowcnt = int(t1[0]["ROWCNT"])
        except (TypeError, ValueError):
            rowcnt = None
    if rowcnt is None:
        if table:
            raise SourceChanged(source, "Table1[0].ROWCNT missing", url)
        rowcnt = 0
    rows = []
    for r in table:
        if not isinstance(r, dict):
            continue
        headline = (r.get("HEADLINE") or r.get("NEWSSUB") or "").strip()
        if not headline:
            raise SourceChanged(source, "announcement row without HEADLINE/NEWSSUB", url)
        rows.append({
            "headline": headline,
            "subject": (r.get("NEWSSUB") or "").strip() or None,
            "date": _iso_date(r),
            "url": attachment_url(r.get("ATTACHMENTNAME")),
            "category": (r.get("CATEGORYNAME") or "").strip() or None,
            "subcategory": (r.get("SUBCATNAME") or "").strip() or None,
            "scrip": str(r.get("SCRIP_CD") or "").strip() or None,
            "company": (r.get("SLONGNAME") or "").strip() or None,
            "newsId": r.get("NEWSID"),
        })
    return rows, rowcnt


def fetch(session: Session, scrip: str, from_date: dt.date, to_date: dt.date, *,
          source: str = "bse_ann", max_pages: int = MAX_PAGES) -> list[dict]:
    """All announcements for `scrip` in [from_date, to_date], following pagination via ROWCNT."""
    rows: list[dict] = []
    page = 1
    while page <= max_pages:
        payload = session.bse_json(PATH, params_for(scrip, from_date, to_date, page), source=source)
        got, rowcnt = parse_page(payload, source=source, url=PATH)
        rows.extend(got)
        if not got or len(rows) >= rowcnt:
            break
        page += 1
    return rows
