"""BSE's deal tables and end-of-day prices — the half of the market NSE's files do not see.

  bulk_deals / block_deals   beta.bseindia.com/markets/equity/EQReports/bulk_deals.aspx and block_deals.aspx: the legacy
                             server-rendered pages, one table of the latest trading day's deals — Deal Date dd/mm/yyyy,
                             Security Code, Security Name, Client Name, Deal Type B|S, Quantity, Price. Rows come back in
                             the same shape as nsearchives.parse_deals_csv, with the BSE scrip code as `symbol`.
                             Until 5 Nov 2026 this read api.bseindia.com/BseIndiaAPI/api/BulkDeal_Beta/w (the site's own
                             call); that host answers 403 "Access Denied" to GitHub's runners and to Cloudflare alike
                             (scripts/probe_bse.py, run from a runner), while the beta pages answer an identified client
                             with the same seven fields. The www. pages are an app shell that calls the blocked API.
  bhavcopy(date)             www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV — the same
                             column layout as NSE's file; keyed by FinInstrmId (the scrip code). SME rows are series MT/M.
                             A missing day answers an HTML page with status 200: that is "no file", raised as SourceDown 404
                             so callers treat it like NSE's holiday 404.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..errors import SourceChanged, SourceDown
from ..http import BSE_BETA, BSE_WEB

SOURCE = "bse"
BHAV_URL = BSE_WEB + "/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV"
BULK_URL = BSE_BETA + "/markets/equity/EQReports/bulk_deals.aspx"
BLOCK_URL = BSE_BETA + "/markets/equity/EQReports/block_deals.aspx"
_SIDE = {"B": "BUY", "S": "SELL"}


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _date(v) -> str | None:
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", str(v or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def parse_deals(html: str, what: str) -> list[dict]:
    """The legacy page's one data table: a header row (Deal Date … Price) and one <tr> per deal, seven direct <td>s.
    The page nests that table inside layout tables, so rows are read by their own cells, never by table. A page with
    the header and no deal rows is a quiet day; a page without the header is a changed source."""
    tree = HTMLParser(html or "")
    header_seen, out = False, []
    for tr in tree.css("tr"):
        cells = [c.text(strip=True) for c in tr.iter() if c.tag in ("td", "th")]
        if not cells:
            continue
        if cells[0].lower().startswith("deal date") and len(cells) >= 7:
            header_seen = True
            continue
        if len(cells) < 7 or not re.match(r"^\d{2}/\d{2}/\d{4}$", cells[0]):
            continue
        side = _SIDE.get(cells[4].strip().upper())
        if not side or not cells[1].strip():
            continue
        out.append({"date": _date(cells[0]), "symbol": cells[1].strip(), "security": cells[2].strip(), "client": cells[3].strip(),
                    "side": side, "qty": _num(cells[5]), "price": _num(cells[6])})
    if not header_seen:
        raise SourceChanged(SOURCE, f"{what}: no deal table on the page ({len(html or '')} B)", what)
    return out                                            # a header with no rows is a quiet day


def bulk_deals(session) -> list[dict]:
    return parse_deals(session.get_text(BULK_URL, source=SOURCE, headers={"Referer": BSE_BETA + "/"}), "bulk_deals")


def block_deals(session) -> list[dict]:
    return parse_deals(session.get_text(BLOCK_URL, source=SOURCE, headers={"Referer": BSE_BETA + "/"}), "block_deals")


def parse_bhavcopy(text: str, url: str, date: dt.date) -> dict[str, dict]:
    body = (text or "").lstrip()
    if body.startswith("<"):
        raise SourceDown(SOURCE, "no file for this date (HTML page)", url, 404)
    reader = csv.DictReader(io.StringIO(body))
    out: dict[str, dict] = {}
    for rec in reader:
        rec = {(k or "").strip(): (v or "").strip() for k, v in rec.items()}
        code = rec.get("FinInstrmId")
        if not code or not rec.get("ClsPric"):
            continue
        out[code] = {"date": rec.get("TradDt") or date.isoformat(), "series": rec.get("SctySrs"), "symbol": rec.get("TckrSymb"),
                     "open": _num(rec.get("OpnPric")), "high": _num(rec.get("HghPric")), "low": _num(rec.get("LwPric")), "close": _num(rec.get("ClsPric"))}
    if not out:
        raise SourceChanged(SOURCE, "bhavcopy parsed to zero rows", url)
    return out


def bhavcopy(session, date: dt.date) -> dict[str, dict]:
    url = BHAV_URL.format(ymd=date.strftime("%Y%m%d"))
    blob = session.get_bytes(url, source=SOURCE, headers={"Referer": BSE_WEB + "/"})
    return parse_bhavcopy(blob.decode("utf8", "replace"), url, date)
