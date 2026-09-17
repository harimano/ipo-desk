"""parents — merge patcher into `sheets`: for every sheet in prev["sheets"] with a `parentTicker`, set
`parentPrice: {value, asOf}`. Nothing else on the sheet is touched (sheets are Claude-owned research).

Chain: angelone LTP -> yahoo last daily close. Tickers may carry a ".NS" suffix; it is stripped.
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from ..errors import SourceChanged
from ..http import Session
from ..result import Result, try_chain
from ..sources import angelone, yahoo

log = logging.getLogger("collector.parents")
IST = ZoneInfo("Asia/Kolkata")


def _tickers(prev: dict) -> dict[str, str]:
    """sheet name -> NSE symbol (uppercase, no .NS)."""
    out = {}
    for name, sheet in (prev.get("sheets") or {}).items():
        if not isinstance(sheet, dict):
            continue
        t = sheet.get("parentTicker")
        if isinstance(t, str) and t.strip():
            out[name] = t.strip().upper().removesuffix(".NS")
    return out


def _apply(res: Result, tickers: dict[str, str], prices: dict[str, tuple[float, str]], source: str) -> str | None:
    """prices: symbol -> (value, asOf). Writes res.merge["sheets"]; raises when nothing matched."""
    res.merge.clear()
    res.notes.clear()
    sheets: dict[str, dict] = {}
    missed = []
    as_of = None
    for name, sym in tickers.items():
        hit = prices.get(sym)
        if not hit:
            missed.append(f"{name} ({sym})")
            continue
        value, when = hit
        sheets[name] = {"parentPrice": {"value": value, "asOf": when}}
        as_of = max(as_of or "", when or "")
    if not sheets:
        raise SourceChanged(source, f"no prices for any of {len(tickers)} parent tickers")
    res.merge["sheets"] = sheets
    res.notes.append(f"{len(sheets)}/{len(tickers)} parent prices")
    if missed:
        res.notes.append("unpriced: " + ", ".join(missed[:5]))
    return as_of or None


def _from_angelone(session: Session, tickers: dict[str, str], res: Result) -> str | None:
    ltp = angelone.ltp(sorted(set(tickers.values())), session)
    when = dt.datetime.now(IST).replace(microsecond=0).isoformat()
    return _apply(res, tickers, {sym: (v, when) for sym, v in ltp.items()}, "angelone")


def _from_yahoo(session: Session, tickers: dict[str, str], res: Result) -> str | None:
    closes = yahoo.daily_closes(sorted(set(tickers.values())), 7)
    prices = {sym: (rows[-1][1], rows[-1][0]) for sym, rows in closes.items() if rows}
    return _apply(res, tickers, prices, "yahoo")


def run(session: Session, prev: dict, res: Result) -> Result:
    tickers = _tickers(prev)
    if not tickers:
        def nothing():
            raise SourceChanged("parents", "no sheet has a parentTicker")
        return try_chain(res, [("none", nothing)])
    return try_chain(res, [("angelone", lambda: _from_angelone(session, tickers, res)),
                           ("yahoo", lambda: _from_yahoo(session, tickers, res))])
