"""parents — merge patcher into `sheets`: for every sheet in prev["sheets"] with a `parentTicker`, set
`parentPrice: {value, asOf}`. Nothing else on the sheet is touched (sheets are Claude-owned research).

It also prices the stocks in `investors.moves` and `investors.recentListings`, in the same batch, into
`investors.prices{stock: {symbol, value, asOf}}` — a key of its own, because `moves` belongs to the sweep
file and is overlaid after every run. Stock names become symbols through NSE's equity lists
(sources/nse_symbols.py); a resolved symbol is remembered in `prices`, so the lists are fetched only when
a new name appears. All of this is best effort: it can never cost the parent prices.

Chain: angelone LTP -> yahoo last daily close. Tickers may carry a ".NS" suffix; it is stripped.
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from ..errors import SourceChanged, SourceError
from ..http import Session
from ..names import Matcher
from ..result import Result, try_chain
from ..sources import angelone, nse_symbols, yahoo

log = logging.getLogger("collector.parents")
IST = ZoneInfo("Asia/Kolkata")
RETRY_MISS_DAYS = 7


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


def quota_parents(prev: dict) -> dict[str, str]:
    """parent name -> NSE symbol for every live quota row that names its ticker. The quota planner needs what ONE share of
    each parent costs, and only five parents have a research sheet; these ride in the same batch and land in
    `investors.prices[parent]` like any other stock the collector prices."""
    out = {}
    for q in prev.get("quota") or []:
        if isinstance(q, dict) and q.get("bucket") not in ("done", "dropped") and isinstance(q.get("parent"), str) and isinstance(q.get("ticker"), str) and q["ticker"].strip():
            out[q["parent"]] = q["ticker"].strip().upper().removesuffix(".NS")
    return out


def investor_stocks(prev: dict) -> list[str]:
    inv = prev.get("investors") or {}
    names = [r.get("stock") for k in ("moves", "recentListings") for r in (inv.get(k) or []) if isinstance(r, dict)]
    return list(dict.fromkeys(n for n in names if isinstance(n, str) and n.strip()))


def resolve_symbols(session: Session, prev: dict, res: Result) -> dict[str, str]:
    """stock name -> NSE symbol. Remembered symbols first; NSE's lists only for names not seen before."""
    known = {k: v.get("symbol") for k, v in ((prev.get("investors") or {}).get("prices") or {}).items()
             if isinstance(v, dict) and v.get("symbol")}
    book = (prev.get("investors") or {}).get("prices") or {}
    today = dt.datetime.now(IST).date()

    def tried_lately(s: str) -> bool:            # a miss is remembered too, and looked up again after a week
        try:
            return (today - dt.date.fromisoformat(str((book.get(s) or {}).get("triedOn"))[:10])).days < RETRY_MISS_DAYS
        except ValueError:
            return False
    stocks = investor_stocks(prev)
    out = {s: known[s] for s in stocks if s in known}
    todo = [s for s in stocks if s not in out and not tried_lately(s)]
    res.misses = {s: (book.get(s) or {}).get("triedOn") for s in stocks if s not in out and s not in todo}
    if not todo:
        return out
    try:
        matcher = Matcher(nse_symbols.companies(session))
    except SourceError as e:
        res.notes.append(f"investor prices: NSE equity list unavailable ({e.kind}); {len(todo)} names unresolved")
        return out
    missed = []
    for s in todo:
        hit = matcher.match(s)
        if hit and matcher.symbol_of(hit):
            out[s] = matcher.symbol_of(hit)
        else:
            missed.append(s)
            res.misses[s] = today.isoformat()
    if missed:
        res.unresolved.append(f"no NSE symbol found for investor stocks: {', '.join(missed[:8])} — BSE-only, or add to data/aliases.json")
    return out


def _apply(res: Result, tickers: dict[str, str], prices: dict[str, tuple[float, str]], source: str,
           stocks: dict[str, str] | None = None) -> str | None:
    """prices: symbol -> (value, asOf). Writes res.merge["sheets"] (+ investors.prices); raises when no parent matched."""
    res.merge.clear()
    res.notes[:] = [n for n in res.notes if n.startswith("investor prices:")]
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
    if stocks:
        book = {s: {"symbol": sym, "value": prices[sym][0], "asOf": prices[sym][1]} if sym in prices
                else {"symbol": sym, "value": None, "asOf": None} for s, sym in stocks.items()}
        for s, tried in (getattr(res, "misses", None) or {}).items():
            book[s] = {"symbol": None, "value": None, "asOf": None, "triedOn": tried}
        res.merge["investors"] = {"prices": book}
        res.notes.append(f"{sum(1 for v in book.values() if v['value'] is not None)}/{len(book)} investor stocks priced")
    return as_of or None


def _from_angelone(session: Session, tickers: dict[str, str], stocks: dict[str, str], res: Result) -> str | None:
    ltp = angelone.ltp(sorted(set(tickers.values()) | set(stocks.values())), session)
    when = dt.datetime.now(IST).replace(microsecond=0).isoformat()
    return _apply(res, tickers, {sym: (v, when) for sym, v in ltp.items()}, "angelone", stocks)


def _from_yahoo(session: Session, tickers: dict[str, str], stocks: dict[str, str], res: Result) -> str | None:
    closes = yahoo.daily_closes(sorted(set(tickers.values()) | set(stocks.values())), 7)
    prices = {sym: (rows[-1][1], rows[-1][0]) for sym, rows in closes.items() if rows}
    return _apply(res, tickers, prices, "yahoo", stocks)


def run(session: Session, prev: dict, res: Result) -> Result:
    tickers = _tickers(prev)
    if not tickers:
        def nothing():
            raise SourceChanged("parents", "no sheet has a parentTicker")
        return try_chain(res, [("none", nothing)])
    try:
        stocks = resolve_symbols(session, prev, res)
    except Exception as e:                       # best effort, always: parent prices come first
        log.warning("investor symbol resolution failed: %s", e)
        stocks = {}
    stocks = {**quota_parents(prev), **stocks}
    return try_chain(res, [("angelone", lambda: _from_angelone(session, tickers, stocks, res)),
                           ("yahoo", lambda: _from_yahoo(session, tickers, stocks, res))])
