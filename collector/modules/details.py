"""details — the complete per-listing record. Patches every board row and owns `anchors[]`.

One source, the fullest there is: InvestorGain's per-IPO record (sources/investorgain.py), ~280 fields in one
call. It fills every placeholder a listing has —

    identity   igId, symbol, BSE code, ISIN, sector
    dates      allotment, listing (and open / close when the exchange list had none)
    terms      band, lot, issue size split into fresh and OFS, to the rupee
    anchor     shares, book size (shares x allocation price), bid date, both lock-in expiries  -> anchors[]
    market     GMP with its own timestamp, subscription by category, listing price
    facts      P/E, market cap, ROE, ROCE, D/E, margins, promoter holding, broker views, documents, registrar

— fetched as data and copied field for field. Nothing here reads a document or interprets prose.

Where it sits decides who wins, with no special logic: it runs AFTER `gmp` (its GMP carries a fresher stamp than
the cached report 331, so it overwrites) and BEFORE `subscription` and `listings` (the exchanges' live book and
the traded listing price overwrite its copies when they answer, and its copies stand when they do not — which
retires the broken chittorgarh fallback). If this API vanishes, as its v1 did in July 2026, the module fails,
every row keeps what it had, and the NSE/BSE modules carry the board.

Identity: a row is matched to its record once — by name AND opening date against `list-read` — and the id is
written on the row. From then on it is matched by id; spelling no longer matters.

Politeness: a record is fetched when the issue is Open (every run), otherwise at most every STALE_HOURS, and
never once an issue has been listed for SETTLED_DAYS. Twenty-five calls of 150 KB on a full run, a handful intraday.

Order of the queue (5 Nov 2026), inside MAX_DETAIL_CALLS and BUDGET_SECONDS, so that nothing starves the open book:
    1. Open issues, every run (earliest opened first);
    2. then every identified row with NO record on file — an upcoming issue's record exists weeks before it opens and
       states its reservations, so its first fetch happens the run it reaches the calendar, newest-announced first
       (latest opening date first);
    3. then due refreshes (last fetched more than STALE_HOURS ago), earliest opening first.

Reservation (5 Nov 2026): every row with a record carries `shareholderQuota` — the record's structured reservation
fields (sources/investorgain.shareholder_quota), {flag: false} when the record states none — so "checked, none" is
distinct from None, "no record yet". The shareholder-quota table (`filings`) reads it; nothing here names a parent.
"""
from __future__ import annotations

import datetime as dt
import logging
import pathlib
import time
from zoneinfo import ZoneInfo

from ..errors import SourceBlocked, SourceChanged, SourceError
from ..http import Session
from ..names import Matcher, load_aliases
from ..result import Result
from ..sources import investorgain
from .calendar import derive_status
from .gmp import trend

log = logging.getLogger("collector.details")
IST = ZoneInfo("Asia/Kolkata")
ALIASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"
BOARDS = ("mainboard", "sme")
MAX_DETAIL_CALLS = 25
BUDGET_SECONDS = 150       # a slow InvestorGain hour must not eat the run (23 Sep 2026: 18 minutes of resets and timeouts, job cancelled)
MAX_CONSECUTIVE_FAILURES = 3
STALE_HOURS = 6
SETTLED_DAYS = 3                      # after listing: the record has said everything it will say
MAX_OPEN_DATE_GAP_DAYS = 3            # a name match must also agree on the opening date
BASIS = "exchange-json"               # marks anchor figures computed from fetched fields (kept from the earlier module)
KEEP_ANCHOR_DAYS = 150                # an anchors row outlives its 90-day lock-in, then leaves
IG_PAGE = "https://www.investorgain.com/ipo/{slug}/{id}/"


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _fmt(v) -> str:
    d = _date(v)
    return f"{d.day} {d:%b}" if d else "—"


def settled(row: dict, today: dt.date) -> bool:
    ls = _date(row.get("listing"))
    return bool(ls) and (today - ls).days > SETTLED_DAYS


def due(row: dict, today: dt.date, now: dt.datetime) -> bool:
    if settled(row, today):
        return False
    if derive_status(row.get("open"), row.get("close"), row.get("listing"), today) == "Open":
        return True
    try:
        last = dt.datetime.fromisoformat(str(row.get("igFetchedAt")))
    except ValueError:
        return True
    return (now - last).total_seconds() > STALE_HOURS * 3600


def _status(row: dict, today: dt.date) -> str:
    return derive_status(row.get("open"), row.get("close"), row.get("listing"), today)


def queue(live: list[tuple[str, dict]], ids: dict[str, str], records: dict, today: dt.date, now: dt.datetime) -> list[tuple[str, dict]]:
    """Who is fetched, in what order (the module docstring): open issues, then rows with no record on file newest-announced
    first, then due refreshes. A row past the cap waits for the next run; an open issue never waits behind a refresh."""
    open_, fresh, stale = [], [], []
    for k, r in live:
        if r["name"] not in ids:
            continue
        if _status(r, today) == "Open":
            open_.append((k, r))
        elif ids[r["name"]] not in records:
            fresh.append((k, r))
        elif due(r, today, now):
            stale.append((k, r))
    by_open = lambda kr: kr[1].get("open") or ""
    return sorted(open_, key=by_open) + sorted(fresh, key=by_open, reverse=True) + sorted(stale, key=by_open)


def assign_ids(rows: list[dict], listing: list[dict], aliases: dict) -> dict[str, str]:
    """board name -> igId, for rows that have none yet. Name and opening date must both agree."""
    ours = Matcher(rows, aliases)
    by_name = {r["name"]: r for r in rows}
    out: dict[str, str] = {}
    for c in listing:
        name = ours.match(c["name"])
        if not name or name in out or name not in by_name:        # an alias can name a row that is not among these
            continue
        a, b = _date(by_name[name].get("open")), _date(c.get("open"))
        if a and b and abs((a - b).days) <= MAX_OPEN_DATE_GAP_DAYS:
            out[name] = c["igId"]
        elif a and b:
            log.info("details: %r matched %r by name but opens %s vs %s — not the same issue", c["name"], name, b, a)
    return out


def reservation_disagrees(rec: dict) -> str | None:
    """The record states the shareholder reservation twice: in fields (shareholderQuota) and in its reservation table (the sheet's
    `reservation`, parsed as a table). They agree on every record read; the day InvestorGain renames a field, this is the line that
    says so instead of a silent "no reservation". Returns the disagreement, or None when the two agree or the table is absent."""
    rows = ((rec.get("sheet") or {}).get("reservation") or {}).get("rows") or []
    if not rows:                                                   # no table on the record (or a trimmed fixture): nothing to compare
        return None
    sh = next((r for r in rows if r and str(r[0]).strip().lower().startswith("shareholder")), None)
    q = rec.get("shareholderQuota") or {}
    table = int(investorgain._num(sh[1]) or 0) if sh and len(sh) > 1 else 0
    if bool(table) != bool(q.get("flag")):
        return (f"reservation table says {table:,} shares for shareholders, the record's fields say "
                f"{'a reservation' if q.get('flag') else 'none'} (prefer_shareholders_status / shares_offered_shareholders)")
    if table and q.get("offered") and table != q["offered"]:
        return f"reservation table says {table:,} shares for shareholders, the record's fields say {q['offered']:,}"
    return None


def row_patch(row: dict, rec: dict, today: dt.date, now: dt.datetime, gmp_before=None) -> dict:
    """Fields for one board row. A value is written only when the record has one; nothing is ever blanked."""
    p: dict = {"igId": rec["igId"], "igFetchedAt": now.replace(microsecond=0).isoformat()}
    for ours, theirs in (("allotment", "allotment"), ("listing", "listing"), ("issueSizeCr", "issueSizeCr"), ("freshCr", "freshCr"),
                         ("ofsCr", "ofsCr"), ("refund", "refund"), ("isin", "isin"), ("sector", "sector"), ("anchorShares", "anchorShares"),
                         ("logo", "logo"), ("apply", "apply")):           # apply: what one application blocks, per category
        if rec.get(theirs) not in (None, ""):
            p[ours] = rec[theirs]
    for ours, theirs in (("open", "open"), ("close", "close"), ("bandLow", "bandLow"), ("bandHigh", "bandHigh"), ("lotSize", "lotSize"),
                         ("symbol", "symbol"), ("bseScripCode", "bseCode")):      # the exchange's own value stays when it has one
        if row.get(ours) in (None, "") and rec.get(theirs) not in (None, ""):
            p[ours] = rec[theirs]
    status = derive_status(p.get("open") or row.get("open"), p.get("close") or row.get("close"),
                           p.get("listing") or row.get("listing"), today)
    g = rec.get("gmp")
    if g and status != "Listed":                                   # after listing a grey-market quote is history
        p["gmp"], p["gmpTrend"], p["gmpAsOf"] = g["value"], trend(g["value"], gmp_before if gmp_before is not None else row.get("gmp")), g.get("asOf")
        band = p.get("bandHigh") or row.get("bandHigh")
        p["gmpPct"] = g["pct"] if g.get("pct") is not None else round(100 * g["value"] / band, 2) if band else None
        lists = p.get("listing") or row.get("listing")
        if g.get("asOf") and lists and g["asOf"][:10] < lists:     # the last quote stamped before listing day: `history` freezes it
            p["gmpEve"], p["gmpEveAsOf"] = g["value"], g["asOf"]   # as the desk's own evening-before GMP (the look-ahead check)
    if rec.get("sub"):
        p["sub"] = dict(rec["sub"])
    price = rec.get("priceFinal") or p.get("bandHigh") or row.get("bandHigh")
    if rec.get("listingPrice") and row.get("listingPrice") in (None, ""):
        p["listingPrice"] = rec["listingPrice"]
        if price:
            p["listingGainPct"] = round(100 * (rec["listingPrice"] - price) / price, 2)
    if rec.get("facts"):
        p["facts"] = {**rec["facts"], "asOf": rec.get("updated")}
    if isinstance(rec.get("shareholderQuota"), dict):              # always written once a record is read: {flag: false} is an answer
        p["shareholderQuota"] = {**rec["shareholderQuota"], "at": today.isoformat()}
    return p


# ---------------------------------------------------------------------------------------------
# anchors[] — the same rules as before: rows that already carry a book keep every word of it
# ---------------------------------------------------------------------------------------------
def anchor_summary(a: dict) -> str:
    bits = []
    if a.get("amountCr"):
        bits.append(f"₹{a['amountCr']:,.2f} Cr anchor book")
    if a.get("date"):
        bits.append(f"bid {_fmt(a['date'])}")
    if a.get("amountCr") and a.get("issueSizeCr"):
        bits.append(f"{100 * a['amountCr'] / a['issueSizeCr']:.0f}% of the issue")
    if a.get("lockIn30"):
        bits.append(f"lock-in ends {_fmt(a['lockIn30'])} (half) and {_fmt(a.get('lockIn90'))}")
    return " · ".join(bits)


def upsert_anchor(rows: list[dict], matcher: Matcher, board_name: str, rec: dict) -> bool:
    if not rec.get("anchorShares") and not rec.get("anchorBidDate"):
        return False                                               # the issue has no anchor portion
    hit = matcher.match(board_name)
    a = next((r for r in rows if r["name"] == (hit or board_name)), None)
    if a is None:
        a = {"name": board_name, "date": None, "amountCr": None, "issueSizeCr": None, "count": None, "topTierShare": None,
             "investors": [], "sources": [], "source": BASIS, "auto": True}
        rows.append(a)
    before = (a.get("amountCr"), a.get("lockIn30"), a.get("lockIn90"), a.get("date"), a.get("anchorShares"))
    a["date"] = a.get("date") or rec.get("anchorBidDate")
    a["lockIn30"], a["lockIn90"] = rec.get("lockIn30") or a.get("lockIn30"), rec.get("lockIn90") or a.get("lockIn90")
    if rec.get("anchorShares"):
        a["anchorShares"] = rec["anchorShares"]
        a["price"] = rec.get("priceFinal") or rec.get("bandHigh") or a.get("price")
    if rec.get("anchorCr") and (a.get("amountCr") is None or a.get("amountBasis") == BASIS):
        a["amountCr"], a["amountBasis"] = rec["anchorCr"], BASIS
    if rec.get("issueSizeCr") and (a.get("auto") or not a.get("issueSizeCr")):
        a["issueSizeCr"] = rec["issueSizeCr"]
    letter = ((rec.get("facts") or {}).get("docs") or {}).get("anchorLetter")
    for url in (letter,):                                          # a link for a human to open; a run never does
        if url and url not in (a.get("sources") or []):
            a["sources"] = (list(a.get("sources") or []) + [url])[:4]
    if a.get("auto"):
        a["anchor"] = anchor_summary(a)
        a["note"] = ("Anchor shares, allocation price, bid date and lock-in dates are fields of InvestorGain's IPO record. "
                     "Who took the book is published only as the issuer's letter (linked), which a run does not read.")
    return before != (a.get("amountCr"), a.get("lockIn30"), a.get("lockIn90"), a.get("date"), a.get("anchorShares"))


# ---------------------------------------------------------------------------------------------
def run(session: Session, prev: dict, res: Result, today: dt.date | None = None, now: dt.datetime | None = None) -> Result:
    now = now or dt.datetime.now(IST)
    t = today or now.date()
    aliases = load_aliases(ALIASES_DIR)
    doc = res.doc or prev                                  # today's board: a listing calendar created this run is already there
    board = [(k, r) for k in BOARDS for r in (doc.get(k) or []) if isinstance(r, dict) and r.get("name")]
    was = {r["name"]: r.get("gmp") for k in BOARDS for r in (prev.get(k) or []) if isinstance(r, dict) and r.get("name")}
    live = [(k, r) for k, r in board if not settled(r, t)]
    if not live:
        res.notes.append("every listing on the board is settled; nothing to fetch")
        return res.won("none", t.isoformat())

    # ---- 1. identity: rows without an id are matched once against the list ------------------------
    ids = {r["name"]: str(r["igId"]) for _, r in live if r.get("igId")}
    unknown = [r for _, r in live if not r.get("igId")]
    if unknown:
        try:
            ids.update(assign_ids(unknown, investorgain.fetch_ipo_list(session), aliases))
            res.tried.append({"source": "investorgain-list", "ok": True})
        except SourceError as e:
            res.tried.append({**e.record(), "ok": False})
            if not ids:
                return res.fail(e)
            res.notes.append(f"list unavailable ({e.kind}): {len(unknown)} rows keep waiting for an id")

    # ---- 2. the records ------------------------------------------------------------------------
    anchors = [dict(a) for a in prev.get("anchors") or [] if isinstance(a, dict) and a.get("name")]
    on_file = Matcher(anchors, aliases)
    patches: dict[str, dict[str, dict]] = {}
    got, failed, skipped, booked, last = 0, [], 0, 0, None
    # the sheet behind each listing (`records`, keyed by id): kept while its row is on the board, fetched at once when missing
    on_board = {str(r["igId"]) for _, r in board if r.get("igId")} | set(ids.values())
    records = {i: v for i, v in (prev.get("records") or {}).items() if i in on_board and isinstance(v, dict)}
    todo = queue(live, ids, records, t, now)
    t0, streak, first = time.monotonic(), 0, 0
    for key, row in todo:
        if got + len(failed) >= MAX_DETAIL_CALLS or time.monotonic() - t0 > BUDGET_SECONDS or streak >= MAX_CONSECUTIVE_FAILURES:
            skipped += 1
            continue
        try:
            rec = investorgain.fetch_detail(session, ids[row["name"]])
        except SourceBlocked as e:                                 # a 403 ends the conversation for this run
            last = e
            failed.append(row["name"])
            break
        except SourceError as e:
            last = e
            failed.append(row["name"])
            streak += 1
            log.info("details %s: %s", row["name"], e.detail)
            continue
        streak = 0
        if rec["igId"] != ids[row["name"]]:                        # never hang one issue's facts on another
            last = SourceChanged("investorgain", f"asked for id {ids[row['name']]}, the record says {rec['igId']}")
            failed.append(row["name"])
            continue
        patches.setdefault(key, {})[row["name"]] = row_patch(row, rec, t, now, was.get(row["name"], row.get("gmp")))
        if (why := reservation_disagrees(rec)):
            log.warning("details %s: %s", row["name"], why)
            res.unresolved.append(f"{row['name']}: {why} — read the record before trusting shareholderQuota")
        booked += upsert_anchor(anchors, on_file, row["name"], rec)
        if rec["igId"] not in records and _status(row, t) != "Open":
            first += 1                                             # an upcoming issue's first look, ahead of its opening
        if rec.get("sheet"):
            records[rec["igId"]] = {"name": row["name"], "fetchedAt": now.replace(microsecond=0).isoformat(), **rec["sheet"]}
        got += 1

    if not got:
        if failed:
            return res.fail(last or SourceChanged("investorgain", "no record could be fetched"))
        res.notes.append(f"{len(ids)} listings identified, none due for a refresh")
        return res.won("investorgain", t.isoformat())

    kept = []
    for a in anchors:
        end = _date(a.get("lockIn90")) or _date(a.get("date"))
        if not (end and (t - end).days > KEEP_ANCHOR_DAYS):
            kept.append(a)
    kept.sort(key=lambda a: a.get("date") or "", reverse=True)
    res.rows = patches
    res.replace["anchors"] = kept
    res.replace["records"] = records
    res.notes.append(f"{got} records fetched for {len(ids)} identified listings ({len(live) - len(ids)} without an id); "
                     f"{booked} anchor books updated, {len(kept)} on file")
    if first:
        res.notes.append(f"{first} first records fetched for upcoming issues")
    if failed:
        res.notes.append("no record for: " + ", ".join(failed[:6]))
    if skipped:
        res.notes.append(f"{skipped} left for the next run (cap {MAX_DETAIL_CALLS})")
    # an issue is identified while it is upcoming or open; one that had already listed when this module first met it
    # is not on the list any more, and is complete anyway — only a pre-listing row without a record is worth a look
    no_id = [r["name"] for _, r in live if r["name"] not in ids
             and derive_status(r.get("open"), r.get("close"), r.get("listing"), t) != "Listed"]
    if no_id:
        res.unresolved.append("no InvestorGain record matched (name + opening date): " + ", ".join(no_id[:8]))
    return res.won("investorgain", now.replace(microsecond=0).isoformat())
