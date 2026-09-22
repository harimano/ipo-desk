"""BSE's deal files and end-of-day prices — the half of the market NSE's files do not see.

  bulk_deals / block_deals   api.bseindia.com/BseIndiaAPI/api/BulkDeal_Beta/w and BlockDeal_Beta/w (found in the site's own
                             network calls, 22 Sep 2026): today's deals as {Table: [{DEAL_DATE dd/mm/yyyy, SCRIP_CODE,
                             ScripName, CLIENT_NAME, TRANSACTION_TYPE B|S, QUANTITY, PRICE, SENDTOWEBSITE}]}. Rows come back
                             in the same shape as nsearchives.parse_deals_csv, with the BSE scrip code as `symbol`.
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

from ..errors import SourceChanged, SourceDown
from ..http import BSE_WEB

SOURCE = "bse"
BHAV_URL = BSE_WEB + "/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV"
_SIDE = {"B": "BUY", "S": "SELL"}


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _date(v) -> str | None:
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", str(v or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def parse_deals(data, what: str) -> list[dict]:
    rows = data.get("Table") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise SourceChanged(SOURCE, f"{what}: no Table in the answer ({str(data)[:80]!r})", what)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        side = _SIDE.get(str(r.get("TRANSACTION_TYPE") or "").strip().upper())
        if not side or not r.get("SCRIP_CODE"):
            continue
        out.append({"date": _date(r.get("DEAL_DATE")), "symbol": str(r["SCRIP_CODE"]).strip(), "security": str(r.get("ScripName") or "").strip(),
                    "client": str(r.get("CLIENT_NAME") or "").strip(), "side": side, "qty": _num(r.get("QUANTITY")), "price": _num(r.get("PRICE"))})
    if rows and not out:
        raise SourceChanged(SOURCE, f"{what}: {len(rows)} rows, none with a side and a scrip code (keys: {sorted(rows[0])[:6]})", what)
    return out                                            # an empty Table is a quiet day


def bulk_deals(session) -> list[dict]:
    return parse_deals(session.bse_json("/BulkDeal_Beta/w", source=SOURCE), "BulkDeal_Beta")


def block_deals(session) -> list[dict]:
    return parse_deals(session.bse_json("/BlockDeal_Beta/w", source=SOURCE), "BlockDeal_Beta")


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
