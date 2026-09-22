"""deals — merge patcher into `investors`: `bulkDeals`, `listingDeals`, `listingSymbols`.

Sources: nsearchives bulk.csv + block.csv (today's files; "NO RECORDS" is a valid empty day). Two cuts
of the same files:

1. bulkDeals — deals by TRACKED NAMES. Client names are matched, case-insensitively as substrings, against
   * prev["investors"]["watchlist"] — strings, or dicts with name / aliases[] / vehicles[]
   * collector/sources/vehicles.json — known investment vehicles mapped to the investor behind them.
   Rows {date, investor, vehicle, stock, side, qty, price, valueCr, exchange, source}, merged with prev
   deals, deduped on date+vehicle+stock+side, kept 45 days, newest first.
2. listingDeals — EVERY deal whose STOCK is one of this year's IPO listings, whoever the client is (the
   prop desks that churn a listing on day one are the point, not noise). The deal files carry the NSE
   symbol; this year's listings come from the document (board rows carry `symbol`; the rest of
   `listedPerf` is resolved through NSE's own equity lists with names.Matcher, and a fuzzy hit whose
   NSE listing date is not this year is rejected). name -> symbol is remembered in
   `investors.listingSymbols` so the lists are fetched only for names not seen before (a miss is retried
   after a week, and only while the listing is young — BSE-only SME listings never resolve, and that is
   stated in the notes, never hidden). Rows {date, symbol, stock, client, side, qty, price, valueCr,
   exchange, kind, sme, listedOn, daysSinceListing, issuePrice, vsIssuePct}, deduped on
   date+symbol+client+side+qty, kept 60 days, newest first. `sme` rides on every row: never pooled.

One CSV failing is a note; both failing fails the module (prev deals kept). Both empty is a quiet day
and still ok — the previous 45 days of deals are re-emitted unchanged.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import pathlib
from zoneinfo import ZoneInfo

from ..errors import SourceError
from ..http import Session
from ..names import Matcher, load_aliases
from ..result import Result, try_chain
from ..sources import nse_symbols, nsearchives

log = logging.getLogger("collector.deals")

IST = ZoneInfo("Asia/Kolkata")
KEEP_DAYS = 45
LISTING_KEEP_DAYS = 60
RETRY_MISS_DAYS = 7          # a name with no NSE symbol is looked up again after a week…
RESOLVE_WINDOW_DAYS = 90     # …but only while the listing is this young; after that it is BSE-only for good
VEHICLES_FILE = pathlib.Path(__file__).resolve().parent.parent / "sources" / "vehicles.json"
ALIASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"


def load_vehicles(path: pathlib.Path = VEHICLES_FILE) -> list[tuple[str, str]]:
    """[(match substring lowercased, investor)]"""
    try:
        body = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("vehicles.json unreadable (%s); vehicle matching off", e)
        return []
    out = []
    for v in body.get("vehicles") or []:
        if isinstance(v, dict) and v.get("match"):
            out.append((str(v["match"]).lower(), str(v.get("investor") or v["match"])))
    return out


def watch_patterns(prev: dict) -> list[tuple[str, str]]:
    """[(substring lowercased, investor display name)] from the sweep-owned watchlist."""
    out = []
    for w in ((prev.get("investors") or {}).get("watchlist") or []):
        if isinstance(w, str) and w.strip():
            out.append((w.strip().lower(), w.strip()))
        elif isinstance(w, dict):
            name = str(w.get("name") or w.get("investor") or "").strip()
            if not name:
                continue
            out.append((name.lower(), name))
            for alias in (w.get("aliases") or []) + (w.get("vehicles") or []):
                if isinstance(alias, str) and alias.strip():
                    out.append((alias.strip().lower(), name))
    return out


def match_client(client: str, patterns: list[tuple[str, str]]) -> str | None:
    """Longest matching substring wins (so 'Kedia Securities' beats 'Kedia')."""
    c = (client or "").lower()
    best = None
    for sub, investor in patterns:
        if len(sub) >= 4 and sub in c and (best is None or len(sub) > best[0]):
            best = (len(sub), investor)
    return best[1] if best else None


def to_row(deal: dict, investor: str, kind: str) -> dict:
    qty, price = deal.get("qty"), deal.get("price")
    value_cr = round(qty * price / 1e7, 2) if qty and price else None
    return {
        "date": deal.get("date"), "investor": investor, "vehicle": deal.get("client"),
        "stock": deal.get("symbol"), "side": deal.get("side"), "qty": qty, "price": price,
        "valueCr": value_cr, "exchange": "NSE", "source": f"nsearchives {kind}.csv",
    }


def _key(r: dict) -> tuple:
    return (str(r.get("date") or ""), str(r.get("vehicle") or "").strip().lower(),
            str(r.get("stock") or "").upper(), str(r.get("side") or "").upper())


def merge_deals(prev_deals: list[dict], new_rows: list[dict], today: dt.date) -> list[dict]:
    cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    seen: dict[tuple, dict] = {}
    for r in list(prev_deals) + list(new_rows):
        if not isinstance(r, dict):
            continue
        k = _key(r)
        if k in seen:
            seen[k] = {**seen[k], **{kk: vv for kk, vv in r.items() if vv is not None}}
        else:
            seen[k] = copy.deepcopy(r)
    out = [r for r in seen.values() if (r.get("date") or "9999") >= cutoff]
    out.sort(key=lambda r: (r.get("date") or "", r.get("investor") or ""), reverse=True)
    return out


# ---------------------------------------------------------------------------------------------
# listingDeals — every deal in one of this year's listings
# ---------------------------------------------------------------------------------------------
def _num(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def this_years_listings(doc: dict, today: dt.date) -> dict[str, dict]:
    """name -> {listedOn, issuePrice, sme, symbol|None} for every listing dated this year. `listedPerf` (the
    history module's record) is the base; a board row that has already listed adds its NSE symbol."""
    jan1 = f"{today.year}-01-01"
    out: dict[str, dict] = {}
    for r in doc.get("listedPerf") or []:
        if not isinstance(r, dict) or not r.get("name") or str(r.get("date") or "") < jan1:
            continue
        out[r["name"]] = {"listedOn": str(r["date"])[:10], "issuePrice": _num(r.get("issue")),
                          "sme": bool(r.get("sme")), "symbol": None}
    for seg in ("mainboard", "sme"):
        for r in doc.get(seg) or []:
            if not isinstance(r, dict) or not r.get("name") or r.get("status") != "Listed":
                continue
            listed = str(r.get("listing") or "")[:10]
            if not listed or listed < jan1:
                continue
            row = out.setdefault(r["name"], {"listedOn": listed, "issuePrice": _num(r.get("bandHigh")),
                                             "sme": seg == "sme", "symbol": None})
            if r.get("symbol"):
                row["symbol"] = str(r["symbol"]).upper()
    return out


def resolve_listing_symbols(session: Session, prev: dict, listings: dict[str, dict], today: dt.date,
                            res: Result) -> dict[str, dict]:
    """Fills `symbol` on `listings` in place and returns the new `investors.listingSymbols` cache:
    {name: {symbol|None, triedOn}}. NSE's lists are fetched only when some name still needs a lookup."""
    cache = {k: v for k, v in (((prev.get("investors") or {}).get("listingSymbols") or {}).items())
             if isinstance(v, dict) and k in listings}
    for name, row in listings.items():
        if not row["symbol"] and (cache.get(name) or {}).get("symbol"):
            row["symbol"] = cache[name]["symbol"]

    def due(name: str) -> bool:
        row, c = listings[name], cache.get(name) or {}
        try:
            age = (today - dt.date.fromisoformat(row["listedOn"])).days
            if age > RESOLVE_WINDOW_DAYS and c:
                return False
            return (today - dt.date.fromisoformat(str(c.get("triedOn"))[:10])).days >= RETRY_MISS_DAYS
        except (TypeError, ValueError):
            return True
    todo = [n for n, r in listings.items() if not r["symbol"] and due(n)]
    if todo:
        try:
            companies = nse_symbols.companies(session)
            res.calls += 2
        except SourceError as e:
            res.notes.append(f"listing deals: NSE equity lists unavailable ({e.kind}); {len(todo)} names unresolved")
            companies = None
        if companies:
            matcher = Matcher(companies, load_aliases(ALIASES_DIR))
            listed_on = {c["name"]: c.get("listedOn") for c in companies}
            jan1 = f"{today.year}-01-01"
            for name in todo:
                hit = matcher.match(name)
                sym = matcher.symbol_of(hit) if hit else None
                if sym and hit != name and listed_on.get(hit) and listed_on[hit] < jan1:
                    log.warning("listing deals: %r matched %r (%s) but NSE lists it since %s — rejected",
                                name, hit, sym, listed_on[hit])
                    sym = None
                listings[name]["symbol"] = sym
                cache[name] = {"symbol": sym, "triedOn": today.isoformat()}
    for name, row in listings.items():
        if row["symbol"] and (cache.get(name) or {}).get("symbol") != row["symbol"]:
            cache[name] = {"symbol": row["symbol"], "triedOn": today.isoformat()}
    return cache


def listing_row(deal: dict, kind: str, name: str, info: dict) -> dict:
    qty, price = deal.get("qty"), deal.get("price")
    issue = info.get("issuePrice")
    try:
        since = (dt.date.fromisoformat(str(deal.get("date"))) - dt.date.fromisoformat(str(info.get("listedOn")))).days
    except (TypeError, ValueError):
        since = None
    return {
        "date": deal.get("date"), "symbol": deal.get("symbol"), "stock": name, "client": deal.get("client"),
        "side": deal.get("side"), "qty": qty, "price": price,
        "valueCr": round(qty * price / 1e7, 2) if qty and price else None,
        "exchange": "NSE", "kind": kind, "sme": bool(info.get("sme")),
        "listedOn": info.get("listedOn"), "daysSinceListing": since, "issuePrice": issue,
        "vsIssuePct": round((price - issue) / issue * 100, 1) if price and issue else None,
    }


def _lkey(r: dict) -> tuple:
    return (str(r.get("date") or ""), str(r.get("symbol") or "").upper(), str(r.get("client") or "").strip().lower(),
            str(r.get("side") or "").upper(), r.get("qty"))


def merge_listing_deals(prev_rows: list[dict], new_rows: list[dict], today: dt.date) -> list[dict]:
    cutoff = (today - dt.timedelta(days=LISTING_KEEP_DAYS)).isoformat()
    seen: dict[tuple, dict] = {}
    for r in list(prev_rows) + list(new_rows):
        if not isinstance(r, dict):
            continue
        k = _lkey(r)
        seen[k] = {**seen[k], **{kk: vv for kk, vv in r.items() if vv is not None}} if k in seen else copy.deepcopy(r)
    out = [r for r in seen.values() if (r.get("date") or "9999") >= cutoff]
    out.sort(key=lambda r: (r.get("date") or "", r.get("stock") or "", r.get("side") or "", -(r.get("valueCr") or 0)),
             reverse=True)
    return out


def listing_deals(session: Session, prev: dict, doc: dict, deals: list[tuple[str, dict]], today: dt.date,
                  res: Result) -> dict:
    """{listingDeals, listingSymbols} for res.merge['investors']."""
    listings = this_years_listings(doc, today)
    cache = resolve_listing_symbols(session, prev, listings, today, res)
    by_symbol = {r["symbol"]: (n, r) for n, r in listings.items() if r["symbol"]}
    rows = [listing_row(d, kind, *by_symbol[d["symbol"]]) for kind, d in deals if d.get("symbol") in by_symbol]
    prev_rows = (prev.get("investors") or {}).get("listingDeals") or []
    merged = merge_listing_deals(prev_rows, rows, today)
    unresolved = [n for n, r in listings.items() if not r["symbol"]]
    res.notes.append(f"listing deals: {len(rows)} of today's {len(deals)} deals are in this year's listings "
                     f"({len(set(r['symbol'] for r in rows))} stocks); {len(merged)} kept over {LISTING_KEEP_DAYS} days; "
                     f"{len(by_symbol)} of {len(listings)} listings have an NSE symbol"
                     + (f", {len(unresolved)} without one (BSE-only, or not on NSE's list yet)" if unresolved else ""))
    return {"listingDeals": merged, "listingSymbols": cache}


def _from_nsearchives(session: Session, prev: dict, res: Result) -> str | None:
    patterns = watch_patterns(prev) + load_vehicles()
    deals: list[tuple[str, dict]] = []
    errors: list[SourceError] = []
    for kind, fetch in (("bulk", nsearchives.bulk_csv), ("block", nsearchives.block_csv)):
        try:
            rows = fetch(session)
        except SourceError as e:
            errors.append(e)
            res.notes.append(f"{kind}.csv: {e.kind} — {e.detail[:60]}")
            continue
        res.notes.append(f"{kind}.csv: {len(rows)} deals" if rows else f"{kind}.csv: NO RECORDS")
        deals.extend((kind, r) for r in rows)
    if len(errors) == 2:
        raise errors[-1]
    matched = []
    for kind, d in deals:
        investor = match_client(d.get("client", ""), patterns)
        if investor:
            matched.append(to_row(d, investor, kind))
    today = dt.datetime.now(IST).date()
    prev_deals = (prev.get("investors") or {}).get("bulkDeals") or []
    res.merge["investors"] = {"bulkDeals": merge_deals(prev_deals, matched, today)}
    res.notes.append(f"{len(matched)} tracked-investor deals of {len(deals)}; {len(patterns)} patterns")
    try:
        res.merge["investors"].update(listing_deals(session, prev, res.doc or prev, deals, today, res))
    except SourceError as e:                     # never lose the tracked-names cut over the listings cut
        res.notes.append(f"listing deals: {e.kind} — {e.detail[:60]}; previous rows kept")
        res.merge["investors"]["listingDeals"] = (prev.get("investors") or {}).get("listingDeals") or []
    dates = sorted({d.get("date") for _, d in deals if d.get("date")})
    return dates[-1] if dates else None


def run(session: Session, prev: dict, res: Result) -> Result:
    return try_chain(res, [("nsearchives", lambda: _from_nsearchives(session, prev, res))])
