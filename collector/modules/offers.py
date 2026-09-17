"""offers — owns `offers` {asOf, rights[], buybacks[], ofs[], ncd[]}.

Source: BSE's public-issues list with a blank ir_flag — one call returns every live and forthcoming
rights issue (RI), offer to buy (OTB: buyback and takeover tenders), OFS and public debt issue (DPI).
There is no second source; when BSE fails the section is carried forward like any other.

What BSE knows is the window and the price. What it does not know — the ratio, the record date, TERP,
the reading — was written by hand in the db era and lives on the row. So this is a merge, not a rebuild:

  * a BSE row matched to an existing row (collector.names) refreshes open / close / price / status and
    leaves every other field alone;
  * a BSE row with no match becomes a new row in the house spelling;
  * a row whose window closed more than KEEP_CLOSED_DAYS ago is dropped, whoever wrote it;
  * a row BSE does not list and that has no dates (`tba`) is kept — it is a note about the future that
    only a human can retire — but it is reported in `unresolved` once it is older than STALE_TBA_DAYS.
"""
from __future__ import annotations

import datetime as dt
import logging
import pathlib
from zoneinfo import ZoneInfo

from ..errors import SourceChanged
from ..http import Session
from ..names import Matcher, display_name, load_aliases
from ..result import Result, try_chain
from ..sources import bse_issues

log = logging.getLogger("collector.offers")
IST = ZoneInfo("Asia/Kolkata")
KEEP_CLOSED_DAYS = 3
ALIASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"
BSE_PAGE = "https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx"

SECTION = {"RI": "rights", "OTB": "buybacks", "OFS": "ofs", "DPI": "ncd"}
SECTIONS = ("rights", "buybacks", "ofs", "ncd")


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def status_for(section: str, open_: dt.date | None, close: dt.date | None, today: dt.date) -> str:
    """The page's vocabulary: position | open-holders | live | upcoming | tba | closed."""
    if not open_ and not close:
        return "tba"
    if close and close < today:
        return "closed"
    if open_ and open_ > today:
        return "upcoming"
    return "open-holders" if section == "rights" else "live"     # an open rights issue is past its record date


def merge(prev_offers: dict, bse_rows: list[dict], today: dt.date) -> tuple[dict, dict]:
    out = {k: [dict(r) for r in (prev_offers.get(k) or []) if isinstance(r, dict) and r.get("name")] for k in SECTIONS}
    stats = {"refreshed": 0, "new": 0, "dropped": 0}
    for section in SECTIONS:
        matcher = Matcher(out[section], load_aliases(ALIASES_DIR))
        by_name = {r["name"]: r for r in out[section]}
        for b in (r for r in bse_rows if SECTION.get(r.get("kind")) == section):
            name = matcher.match(b["name"])
            row = by_name.get(name) if name else None
            if row is None:
                row = {"name": display_name(b["name"]), "open": None, "close": None, "price": None, "record": None,
                       "deal": None, "detail": None, "note": "BSE public issues list", "url": BSE_PAGE}
                if section == "buybacks":
                    row["type"] = "Tender / open offer"      # BSE's OTB covers buyback tenders and takeover offers alike
                out[section].append(row)
                by_name[row["name"]] = row
                stats["new"] += 1
            else:
                stats["refreshed"] += 1
            row["open"] = b.get("open") or row.get("open")
            row["close"] = b.get("close") or row.get("close")
            if b.get("bandHigh") is not None:
                row["price"] = b["bandHigh"]
            row["bseIpoNo"] = b.get("bseIpoNo") or row.get("bseIpoNo")
        kept = []
        for r in out[section]:
            o, c = _date(r.get("open")), _date(r.get("close"))
            if c and (today - c).days > KEEP_CLOSED_DAYS:
                stats["dropped"] += 1
                continue
            if r.get("status") != "position" or c and c < today:      # "can position" is a human judgement: keep it
                r["status"] = status_for(section, o, c, today)
            kept.append(r)
        kept.sort(key=lambda r: (r.get("close") or r.get("open") or "9999", r["name"]))
        out[section] = kept
    out["asOf"] = today.isoformat()
    return out, stats


def _from_bse(session: Session, prev: dict, res: Result, today: dt.date) -> str:
    rows = bse_issues.public_offers_json(session)
    if not rows:
        raise SourceChanged("bse", "public issues list has no rights / buyback / OFS / debt rows")
    offers, stats = merge(prev.get("offers") or {}, rows, today)
    res.replace["offers"] = offers
    counts = ", ".join(f"{len(offers[k])} {k}" for k in SECTIONS)
    res.notes.append(f"bse rows={len(rows)}: {counts}; {stats['refreshed']} refreshed, {stats['new']} new, "
                     f"{stats['dropped']} closed windows dropped")
    undated = [r["name"] for k in SECTIONS for r in offers[k] if r.get("status") == "tba"]
    if undated:
        res.unresolved.append(f"offers with no dates, not on BSE's list — confirm or retire: {', '.join(undated[:8])}")
    return today.isoformat()


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = today or dt.datetime.now(IST).date()
    return try_chain(res, [("bse", lambda: _from_bse(session, prev, res, t))])
