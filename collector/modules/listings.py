"""listings — owns `recent`, `listedPerf`, `comps`, `priceHistory`; row-patches `listingPrice`,
`listingGainPct`, `currentPrice` into `mainboard` / `sme`.

Price chain: angelone (SmartAPI daily candles) -> yahoo (yfinance .NS). One source prices every name in
a run; a partial answer from the first is not merged with the second (keeps asOf honest).

What it does each run, from `prev` (never mutated):
  * board rows whose listing date <= today (or status Listed): patch listingPrice (= listing-day open),
    listingGainPct (vs issue price: `issuePrice` else `bandHigh`), currentPrice (= latest close).
    A price the source lacks today keeps yesterday's value (no patch for that field).
  * board rows listed BEFORE today: build the `recent` row (schema: name, type, listingDate, issuePrice,
    listingPrice, gainPct, closeDay1, closeDay1GainPct, sources) and merge it into prev `recent`,
    deduped by name, newest listing first, within 28 days. The board row itself is left alone —
    calendar owns the board and drops it.
  * new listings -> prepend {name, issue, gmpImplied (issue + prev gmp), listing} to `listedPerf`
    (mainboard only, rolling 400) and append {name, qib, ret} to `comps` when the row had a QIB print.
  * `priceHistory`: one [date, close] point per name per day for every name on the board, in `recent`,
    or in `prev["lot"]`; a date already present is never appended twice.

Symbols: rows carry `symbol` (set by calendar from the NSE feed). A row without one cannot be priced and
is reported in res.unresolved rather than guessed.
"""
from __future__ import annotations

import copy
import datetime as dt
import logging
import re
from zoneinfo import ZoneInfo

from ..errors import SourceChanged
from ..http import Session
from ..result import Result, try_chain
from ..sources import angelone, yahoo

log = logging.getLogger("collector.listings")

IST = ZoneInfo("Asia/Kolkata")
BOARDS = ("mainboard", "sme")
RECENT_DAYS = 28
LOOKBACK_DAYS = 45          # enough candles to cover the oldest `recent` listing
LISTED_PERF_ROWS = 400        # the ipo-radar seed is history the page charts; keep it
_DROP_WORDS = re.compile(r"\b(limited|ltd|ipo|mainboard|sme|nse|bse)\b")


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def today_ist() -> dt.date:
    return dt.datetime.now(IST).date()


def normalise(name: str) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = _DROP_WORDS.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def existing_name(name: str, names: list[str]) -> str:
    """Reuse the spelling already in `names` for the same issue, else the given name."""
    key = normalise(name)
    for n in names:
        if normalise(n) == key:
            return n
    return name


def _date(v) -> dt.date | None:
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def symbol_of(row: dict | None) -> str | None:
    if not isinstance(row, dict):
        return None
    for k in ("symbol", "nseSymbol", "ticker"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper().removesuffix(".NS")
    return None


def _pct(price, base) -> float | None:
    try:
        if price is None or not base:
            return None
        return round((float(price) / float(base) - 1.0) * 100.0, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _issue_price(row: dict) -> float | None:
    for k in ("issuePrice", "bandHigh"):
        v = row.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def collect_targets(prev: dict, today: dt.date):
    """-> (board: [(boardKey, row)], recent: [row], lot_names: [str], symbols: {name: symbol})"""
    board, symbols = [], {}
    for key in BOARDS:
        for row in prev.get(key) or []:
            if not isinstance(row, dict) or not row.get("name"):
                continue
            sym = symbol_of(row)
            if sym:
                symbols.setdefault(row["name"], sym)
            ld = _date(row.get("listing"))
            if (ld and ld <= today) or row.get("status") == "Listed":
                board.append((key, row))
    cutoff = today - dt.timedelta(days=RECENT_DAYS)
    recent = []
    for row in prev.get("recent") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        sym = symbol_of(row)
        if sym:
            symbols.setdefault(row["name"], sym)
        ld = _date(row.get("listingDate"))
        if ld and ld >= cutoff:
            recent.append(row)
    lot_names = []
    for name, lot in (prev.get("lot") or {}).items():
        lot_names.append(name)
        sym = symbol_of(lot)
        if sym:
            symbols.setdefault(name, sym)
    return board, recent, lot_names, symbols


# ---------------------------------------------------------------------------------------------
# price fetchers: {symbol: [[date, open, close], ...]} oldest first
# ---------------------------------------------------------------------------------------------
def _bars_angelone(session: Session, symbols: list[str], days: int) -> dict[str, list[list]]:
    master = angelone.instrument_master(session)
    out: dict[str, list[list]] = {}
    unknown = []
    for sym in symbols:
        if sym not in master:
            unknown.append(sym)
            continue
        candles = angelone.daily_candles(sym, days, session)
        rows = [[c[0], c[1], c[4]] for c in candles if c and c[4]]
        if rows:
            out[sym] = rows
    if unknown:
        log.info("angelone: %d symbols not in instrument master: %s", len(unknown), unknown[:5])
    if not out:
        raise SourceChanged("angelone", f"no candles for any of {len(symbols)} symbols")
    return out


def _bars_yahoo(session: Session, symbols: list[str], days: int) -> dict[str, list[list]]:
    return yahoo.daily_bars(symbols, days)


# ---------------------------------------------------------------------------------------------
# build the result from bars
# ---------------------------------------------------------------------------------------------
def _listing_bar(bars: list[list], listing: dt.date | None) -> list | None:
    if not listing:
        return None
    for b in bars:
        d = _date(b[0])
        if d and d >= listing:
            return b if (d - listing).days <= 5 else None
    return None


def _build(prev: dict, res: Result, today: dt.date, bars: dict[str, list[list]],
           board: list, recent: list, lot_names: list[str], symbols: dict[str, str],
           source: str = "prices") -> str | None:
    res.replace.clear()
    res.rows.clear()
    res.notes.clear()
    res.unresolved.clear()

    def bars_for(name: str) -> list[list]:
        sym = symbols.get(name)
        return bars.get(sym) or [] if sym else []

    priced, no_symbol, as_of = 0, [], None
    new_recent: dict[str, dict] = {}
    new_listings: list[tuple[dict, float | None, float | None, float | None]] = []

    # ---- board rows: patch + build recent rows -------------------------------------------------
    for key, row in board:
        name = row["name"]
        if name not in symbols:
            no_symbol.append(name)
            continue
        b = bars_for(name)
        if not b:
            continue
        listing = _date(row.get("listing"))
        lb = _listing_bar(b, listing)
        issue = _issue_price(row)
        listing_price = (lb[1] if lb and lb[1] else None) or row.get("listingPrice")
        close_day1 = lb[2] if lb else None
        current = b[-1][2]
        patch: dict = {}
        if listing_price:
            patch["listingPrice"] = listing_price
            gain = _pct(listing_price, issue)
            if gain is not None:
                patch["listingGainPct"] = gain
        if current:
            patch["currentPrice"] = current
        if patch:
            res.rows.setdefault(key, {})[name] = patch
            priced += 1
            as_of = max(as_of or "", b[-1][0])
        if listing and listing < today:
            rec = {
                "name": name, "type": row.get("type"), "listingDate": listing.isoformat(),
                "issuePrice": issue, "listingPrice": listing_price, "gainPct": _pct(listing_price, issue),
                "closeDay1": close_day1, "closeDay1GainPct": _pct(close_day1, issue),
                "sources": list(row.get("sources") or []),
            }
            if symbols.get(name):
                rec["symbol"] = symbols[name]
            new_recent[name] = rec
            new_listings.append((row, issue, listing_price, close_day1))

    # ---- recent rows: fill gaps from bars ------------------------------------------------------
    prev_recent_names = [r["name"] for r in recent]
    merged: dict[str, dict] = {r["name"]: copy.deepcopy(r) for r in recent}
    for name, rec in new_recent.items():
        target = existing_name(name, prev_recent_names)
        old = merged.pop(target, {})
        merged[target] = {**old, **{k: v for k, v in rec.items() if v is not None}, "name": target}
    for name, row in merged.items():
        if name not in symbols:
            no_symbol.append(name)
            continue
        b = bars_for(name)
        if not b:
            continue
        lb = _listing_bar(b, _date(row.get("listingDate")))
        issue = _issue_price(row)
        if not row.get("listingPrice") and lb and lb[1]:
            row["listingPrice"] = lb[1]
        if row.get("gainPct") is None:
            row["gainPct"] = _pct(row.get("listingPrice"), issue)
        if not row.get("closeDay1") and lb:
            row["closeDay1"] = lb[2]
        if row.get("closeDay1GainPct") is None:
            row["closeDay1GainPct"] = _pct(row.get("closeDay1"), issue)
        priced += 1
        as_of = max(as_of or "", b[-1][0])
    cutoff = today - dt.timedelta(days=RECENT_DAYS)
    recent_out = [r for r in merged.values() if (_date(r.get("listingDate")) or cutoff) >= cutoff]
    recent_out.sort(key=lambda r: r.get("listingDate") or "", reverse=True)

    # ---- listedPerf / comps ---------------------------------------------------------------------
    listed_perf = copy.deepcopy(prev.get("listedPerf") or [])
    comps = copy.deepcopy(prev.get("comps") or [])
    perf_names = {r.get("name") for r in listed_perf if isinstance(r, dict)}
    comp_names = {r.get("name") for r in comps if isinstance(r, dict)}
    for row, issue, listing_price, close_day1 in new_listings:
        name = row["name"]
        if row.get("type") == "Mainboard" and name not in perf_names and issue and listing_price:
            gmp = row.get("gmp")
            implied = round(issue + float(gmp), 2) if isinstance(gmp, (int, float)) else None
            listed_perf.insert(0, {"name": name, "issue": issue, "gmpImplied": implied, "listing": listing_price})
            perf_names.add(name)
        qib = (row.get("sub") or {}).get("qib") if isinstance(row.get("sub"), dict) else None
        ret = _pct(close_day1, issue) if close_day1 else _pct(listing_price, issue)
        if qib is not None and ret is not None and name not in comp_names:
            comps.append({"name": name, "qib": qib, "ret": ret})
            comp_names.add(name)
    listed_perf = listed_perf[:LISTED_PERF_ROWS]

    # ---- priceHistory ---------------------------------------------------------------------------
    history = copy.deepcopy(prev.get("priceHistory") or {})
    names = list(dict.fromkeys([r["name"] for _, r in board] + [r["name"] for r in recent_out] + lot_names))
    appended = 0
    for name in names:
        b = bars_for(name)
        if not b:
            continue
        date, close = b[-1][0], b[-1][2]
        if not close:
            continue
        series = history.setdefault(name, [])
        if any(isinstance(p, list) and p and str(p[0])[:10] == date for p in series):
            continue
        series.append([date, close])
        series.sort(key=lambda p: str(p[0]))
        appended += 1

    if priced == 0 and appended == 0:
        raise SourceChanged(source, "bars came back but matched no board/recent/lot name")

    res.replace["recent"] = recent_out
    res.replace["listedPerf"] = listed_perf
    res.replace["comps"] = comps
    res.replace["priceHistory"] = history
    res.notes.append(f"{priced} names priced, {len(new_recent)} moved to recent, {appended} history points")
    for name in dict.fromkeys(no_symbol):
        res.unresolved.append(f"listings: no NSE symbol on row {name!r} — cannot price")
    return as_of


# ---------------------------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------------------------
def run(session: Session, prev: dict, res: Result) -> Result:
    today = today_ist()
    board, recent, lot_names, symbols = collect_targets(prev, today)
    wanted = sorted({symbols[n] for n in symbols
                     if n in {r["name"] for _, r in board} | {r["name"] for r in recent} | set(lot_names)})
    if not wanted:
        missing = [r["name"] for _, r in board] + [r["name"] for r in recent]
        for name in missing:
            res.unresolved.append(f"listings: no NSE symbol on row {name!r} — cannot price")
        def nothing():
            raise SourceChanged("listings", "nothing to price: no listed/recent/lot names with a symbol")
        return try_chain(res, [("none", nothing)])

    def via(name: str, fetch):
        def go():
            bars = fetch(session, wanted, LOOKBACK_DAYS)
            return _build(prev, res, today, bars, board, recent, lot_names, symbols, source=name)
        return go

    return try_chain(res, [("angelone", via("angelone", _bars_angelone)),
                           ("yahoo", via("yahoo", _bars_yahoo))])
