"""deals — merge patcher into `investors`, for `bulkDeals` only.

Sources: nsearchives bulk.csv + block.csv (today's files; "NO RECORDS" is a valid empty day). Client
names are matched, case-insensitively as substrings, against
  * prev["investors"]["watchlist"] — strings, or dicts with name / aliases[] / vehicles[]
  * collector/sources/vehicles.json — known investment vehicles mapped to the investor behind them.
Matches become bulkDeals rows {date, investor, vehicle, stock, side, qty, price, valueCr, exchange, source},
merged with prev deals, deduped on date+vehicle+stock+side, kept 45 days, newest first.

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
from ..result import Result, try_chain
from ..sources import nsearchives

log = logging.getLogger("collector.deals")

IST = ZoneInfo("Asia/Kolkata")
KEEP_DAYS = 45
VEHICLES_FILE = pathlib.Path(__file__).resolve().parent.parent / "sources" / "vehicles.json"


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
    dates = sorted({d.get("date") for _, d in deals if d.get("date")})
    return dates[-1] if dates else None


def run(session: Session, prev: dict, res: Result) -> Result:
    return try_chain(res, [("nsearchives", lambda: _from_nsearchives(session, prev, res))])
