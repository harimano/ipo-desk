"""nsearchives.nseindia.com — static files, no cookies needed (unlike www.nseindia.com/api).

  bulk.csv / block.csv   today's bulk and block deals; the body reads "NO RECORDS" on a quiet day,
                         which is a VALID empty (returns []), not an error.
  bhavcopy(date)         the EOD CSV zip (BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip, per the nse
                         package's equityBhavcopy). Best effort: the archive host sometimes 403s
                         datacenter IPs for these; callers must treat a SourceBlocked as "no bhavcopy".
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import re
import zipfile

from ..errors import SourceChanged
from ..http import NSE_ARCHIVES

log = logging.getLogger("collector.sources.nsearchives")

SOURCE = "nsearchives"
BULK_URL = NSE_ARCHIVES + "/content/equities/bulk.csv"
BLOCK_URL = NSE_ARCHIVES + "/content/equities/block.csv"
BHAV_URL = NSE_ARCHIVES + "/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"

# header text -> our field. Matched on a normalised (lowercase, alnum-only) prefix so "Trade Price /
# Wght. Avg. Price" and "Trade Price" both map to price.
_COLS = {
    "date": "date", "symbol": "symbol", "securityname": "security", "clientname": "client",
    "buysell": "side", "quantitytraded": "qty", "tradeprice": "price",
}
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"), 1)}


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def parse_date(text: str) -> str | None:
    """'16-Sep-2026' / '16-SEP-2026' / '2026-09-16' / '16/09/2026' -> ISO date or None."""
    s = (text or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s[:10]
    m = re.match(r"^(\d{1,2})[-/ ]([A-Za-z]{3})[A-Za-z]*[-/ ](\d{4})$", s)
    if m and m.group(2).lower() in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def _num(text) -> float | None:
    try:
        return float(str(text).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_deals_csv(text: str, url: str) -> list[dict]:
    """Rows {date, symbol, security, client, side, qty, price}. [] on 'NO RECORDS'."""
    body = (text or "").strip()
    if not body:
        raise SourceChanged(SOURCE, "empty body", url)
    if "NO RECORDS" in body.upper()[:400] and body.count("\n") < 3:
        return []
    if body.lstrip().startswith("<"):
        raise SourceChanged(SOURCE, "HTML instead of CSV (block page?)", url)
    reader = csv.reader(io.StringIO(body))
    try:
        header = next(reader)
    except StopIteration:
        raise SourceChanged(SOURCE, "no header row", url)
    index: dict[str, int] = {}
    for i, h in enumerate(header):
        n = _norm(h)
        for prefix, field in _COLS.items():
            if n.startswith(prefix) and field not in index:
                index[field] = i
    missing = [f for f in ("date", "symbol", "client", "side", "qty", "price") if f not in index]
    if missing:
        raise SourceChanged(SOURCE, f"header lacks {missing}: {header[:8]}", url)
    rows = []
    for rec in reader:
        if not rec or len(rec) <= max(index.values()):
            continue
        get = lambda f: rec[index[f]].strip() if f in index else ""  # noqa: E731
        side = get("side").upper()
        if side not in ("BUY", "SELL"):
            continue
        rows.append({
            "date": parse_date(get("date")),
            "symbol": get("symbol").upper(),
            "security": get("security"),
            "client": get("client"),
            "side": side,
            "qty": _num(get("qty")),
            "price": _num(get("price")),
        })
    if not rows:
        raise SourceChanged(SOURCE, "header present but no parseable deal rows", url)
    return rows


def bulk_csv(session) -> list[dict]:
    return parse_deals_csv(session.get_text(BULK_URL, source=SOURCE), BULK_URL)


def block_csv(session) -> list[dict]:
    return parse_deals_csv(session.get_text(BLOCK_URL, source=SOURCE), BLOCK_URL)


def bhavcopy(session, date: dt.date) -> dict[str, dict]:
    """{symbol: {date, series, open, high, low, close}} for EQ/SM/ST/BE rows of the day's bhavcopy.
    Raises SourceBlocked/SourceDown from the http layer (best effort), SourceChanged on a bad zip."""
    url = BHAV_URL.format(ymd=date.strftime("%Y%m%d"))
    blob = session.get_bytes(url, source=SOURCE)
    if blob.lstrip().startswith(b"<"):
        raise SourceChanged(SOURCE, "HTML instead of zip", url)
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise SourceChanged(SOURCE, "zip has no csv", url)
            text = z.read(names[0]).decode("utf8", "replace")
    except zipfile.BadZipFile:
        raise SourceChanged(SOURCE, "not a zip", url)
    reader = csv.DictReader(io.StringIO(text))
    out: dict[str, dict] = {}
    for rec in reader:
        rec = {(k or "").strip(): (v or "").strip() for k, v in rec.items()}
        sym = rec.get("TckrSymb") or rec.get("SYMBOL")
        series = rec.get("SctySrs") or rec.get("SERIES") or ""
        if not sym or series not in ("EQ", "SM", "ST", "BE"):
            continue
        out[sym] = {
            "date": parse_date(rec.get("TradDt") or rec.get("TIMESTAMP") or "") or date.isoformat(),
            "series": series,
            "open": _num(rec.get("OpnPric") or rec.get("OPEN")),
            "high": _num(rec.get("HghPric") or rec.get("HIGH")),
            "low": _num(rec.get("LwPric") or rec.get("LOW")),
            "close": _num(rec.get("ClsPric") or rec.get("CLOSE")),
        }
    if not out:
        raise SourceChanged(SOURCE, "bhavcopy parsed to zero equity rows", url)
    return out
