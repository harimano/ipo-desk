"""calendar — owns `mainboard`, `sme`, `lot`.

Chain: investorgain (its IPO list is the calendar; NSE + BSE enrich it) -> nse (+ BSE merged) -> bse.

Chain: nse (current + upcoming + past-issues window, plus ipo-detail for lot size where the list
lacks it) -> bse (modern JSON api, then the legacy beta table). If both fail the module fails and the
assembler keeps yesterday's board.

Rules enforced here:
  * `name` is the viewer's localStorage key. When today's source spells an issue differently from
    the row already on the board, the existing spelling wins (match_name on a normalised form).
  * Fields today's source does not provide (gmp, sub, listingPrice, currentPrice, sources, ...) are
    carried forward from `prev` by name. Nothing is blanked because one source lacks a column.
  * status is derived from dates only (DATA-SCHEMA.md): Upcoming -> Open -> Closed -> Listed.
  * A row that listed more than one day ago leaves the board (listings owns `recent`).
  * `expected` belongs to `filings`, which builds it from the SEBI registers.
  * `lot{name: {shares, price, listDate}}` is updated from the board and never pruned — the viewer's
    applications and holdings key off it long after a name has left the board.
"""
from __future__ import annotations

import datetime as dt
import logging
import pathlib
import re
from zoneinfo import ZoneInfo

from ..errors import SourceBlocked, SourceChanged, SourceError
from ..http import Session
from ..names import Matcher, display_name, load_aliases, norm_name  # noqa: F401  (norm_name re-exported)
from ..result import Result, try_chain
from ..sources import bse_issues, investorgain, nse_ipo

log = logging.getLogger("collector.calendar")
IST = ZoneInfo("Asia/Kolkata")
ALIASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"   # human-kept config, not collector output
MODULE = "calendar"
PAST_WINDOW_DAYS = 45
LISTED_GRACE_DAYS = 1           # a Listed row stays this many days past its listing date
CARRY_FIELDS = ("gmp", "gmpPct", "gmpTrend", "sub", "listingPrice", "listingGainPct", "currentPrice",
                "sources", "shareholderQuota", "slug", "allotment", "listing", "lotSize", "issueSizeCr",
                "freshCr", "ofsCr", "bandLow", "bandHigh", "symbol", "series", "bseIpoNo", "bseScripCode", "igId")


# ---------------------------------------------------------------------------------------------
# name matching
# ---------------------------------------------------------------------------------------------
def match_name(name: str, existing: list[str], symbol: str | None = None) -> str | None:
    """Return the spelling already on the board for `name`, or None if it is genuinely new."""
    return Matcher([{"name": e} for e in existing]).match(name, symbol)


def slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")[:60]


# ---------------------------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------------------------
def derive_status(open_: str | None, close: str | None, listing: str | None, today: dt.date) -> str:
    t = today.isoformat()
    if listing and listing <= t:
        return "Listed"
    if close and close < t:
        return "Closed"
    if open_ and open_ <= t and (not close or t <= close):
        return "Open"
    return "Upcoming"


def _today(today: dt.date | None) -> dt.date:
    return today or dt.datetime.now(IST).date()


def _row_type(board: str, exchange: str) -> str:
    if board != "SME":
        return "Mainboard"
    return "BSE SME" if exchange == "bse" else "NSE SME"


# ---------------------------------------------------------------------------------------------
# building the board
# ---------------------------------------------------------------------------------------------
def _dedupe(rows: list[dict]) -> list[dict]:
    """Same issue may appear in current AND upcoming AND past; merge by normalised name, later
    entries filling gaps only (current-issue is passed first and is the most authoritative)."""
    out: dict[str, dict] = {}
    for r in rows:
        k = norm_name(r["name"]) or r["name"].lower()
        if k not in out:
            out[k] = dict(r)
            continue
        base = out[k]
        for f, v in r.items():
            if base.get(f) in (None, "", 0) and v not in (None, ""):
                base[f] = v
    return list(out.values())


def build_board(rows: list[dict], prev: dict, today: dt.date, exchange: str) -> tuple[list, list, dict]:
    """Internal rows -> (mainboard, sme, lot). Applies name matching + carry-forward from prev."""
    prev_rows = [r for r in (prev.get("mainboard") or []) + (prev.get("sme") or []) if isinstance(r, dict)]
    matcher = Matcher(prev_rows, load_aliases(ALIASES_DIR))
    prev_by_name = {r["name"]: r for r in prev_rows if r.get("name")}
    prev_lot = prev.get("lot") or {}
    cutoff = (today - dt.timedelta(days=LISTED_GRACE_DAYS)).isoformat()

    mainboard, sme = [], []
    lot = {k: dict(v) for k, v in prev_lot.items() if isinstance(v, dict)}   # never dropped: the Book keys off it
    for r in _dedupe(rows):
        if r.get("withdrawn"):
            continue
        status = derive_status(r.get("open"), r.get("close"), r.get("listing"), today)
        if status == "Listed" and r["listing"] < cutoff:
            continue
        # `_final`: the source path already decided which row this is (by id, or by name AND opening date)
        name = r["name"] if r.get("_final") else matcher.match(r["name"], r.get("symbol")) or display_name(r["name"])
        old = prev_by_name.get(name, {})
        row = {
            "name": name,
            "slug": old.get("slug") or slug(name),
            "type": _row_type(r.get("board") or "Mainboard", r.get("exchange") or exchange),
            "status": status,
            "open": r.get("open"), "close": r.get("close"),
            "allotment": r.get("allotment"), "listing": r.get("listing"),
            "bandLow": r.get("bandLow"), "bandHigh": r.get("bandHigh"),
            "lotSize": r.get("lotSize"), "issueSizeCr": r.get("issueSizeCr"),
            "freshCr": None, "ofsCr": None,
            "gmp": None, "gmpPct": None, "gmpTrend": None, "sub": None,
            "shareholderQuota": None, "listingPrice": None, "listingGainPct": None, "currentPrice": None,
            "sources": [],
            "symbol": r.get("symbol"), "series": r.get("series"), "igId": r.get("igId"),
            "bseIpoNo": r.get("bseIpoNo"), "bseScripCode": r.get("bseScripCode"),
        }
        for f in CARRY_FIELDS:
            if row.get(f) in (None, [], {}) and old.get(f) not in (None, [], {}):
                row[f] = old[f]
        for f, v in old.items():           # any extra field another patcher wrote survives too
            if f not in row:
                row[f] = v
        if old.get("type") and old["type"] != row["type"] and (old["type"].endswith("SME")) == (row["type"].endswith("SME")):
            row["type"] = old["type"]      # keep "NSE SME" when BSE is today's source, and vice versa
        src = r.get("source")
        if src and src not in row["sources"]:
            row["sources"] = list(row["sources"]) + [src]
        if r.get("totalSub") is not None and status in ("Open", "Closed"):
            sub = dict(row.get("sub") or {})
            if not sub.get("total") or status == "Open":
                sub["total"] = r["totalSub"]
                sub.setdefault("asOf", today.isoformat())
                for k in ("qib", "nii", "retail"):
                    sub.setdefault(k, None)
                row["sub"] = sub
        (sme if row["type"] != "Mainboard" else mainboard).append(row)
        shares = row.get("lotSize") or (prev_lot.get(name) or {}).get("shares")
        price = row.get("bandHigh") or (prev_lot.get(name) or {}).get("price")
        if shares or price:
            lot[name] = {"shares": shares, "price": price, "listDate": row.get("listing")}

    key = lambda r: (r.get("open") or "9999", r.get("name"))  # noqa: E731
    mainboard.sort(key=key)
    sme.sort(key=key)
    return mainboard, sme, lot


def _finish(res: Result, mainboard: list, sme: list, lot: dict, prev: dict, label: str) -> str:
    res.replace["mainboard"] = mainboard
    res.replace["sme"] = sme
    res.replace["lot"] = lot
    n_open = sum(1 for r in mainboard + sme if r["status"] == "Open")
    n_up = sum(1 for r in mainboard + sme if r["status"] == "Upcoming")
    res.notes.append(f"{label}: {len(mainboard)} mainboard, {len(sme)} sme; {n_open} open, {n_up} upcoming")
    return dt.datetime.now(IST).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------------------------
CARRY_AFTER_CLOSE_DAYS = 14     # a closed issue no source shows any more, and with no listing date, stays this long
SAME_ISSUE_DAYS = 3             # a name match must also agree on the opening date, within this many days
_BASICS = ("symbol", "series", "bseIpoNo", "bseScripCode", "bandLow", "bandHigh", "lotSize", "listing", "allotment", "issueSizeCr")


def _same_issue(a, b) -> bool:
    try:
        return abs((dt.date.fromisoformat(str(a)[:10]) - dt.date.fromisoformat(str(b)[:10])).days) <= SAME_ISSUE_DAYS
    except ValueError:
        return True                                     # one side has no date: nothing contradicts the name


def _from_investorgain(session: Session, prev: dict, res: Result, today: dt.date) -> str:
    """The calendar is InvestorGain's list — every upcoming, open and closed-not-yet-listed issue on both
    exchanges, SME included, days before NSE or BSE show it, each with a stable id. The exchanges then ENRICH it
    (symbol, series, BSE issue number: what the subscription module needs to ask them for the live book). Rows the
    list has dropped — it forgets an issue the moment it lists — are carried from the previous board until the
    normal expiry. Band, lot and the rest arrive from `details` later in the same run, so nothing here asks for them:
    no past-issues download, no per-row ipo-detail calls."""
    listed = investorgain.fetch_ipo_list(session)       # SourceError here hands the calendar to the NSE path
    aliases = load_aliases(ALIASES_DIR)
    prev_rows = [r for r in (prev.get("mainboard") or []) + (prev.get("sme") or []) if isinstance(r, dict) and r.get("name")]
    by_ig = {str(r["igId"]): r for r in prev_rows if r.get("igId")}
    by_name = {r["name"]: r for r in prev_rows}
    known = Matcher(prev_rows, aliases)

    def blank(**kw) -> dict:
        return {"symbol": None, "series": None, "listing": None, "allotment": None, "bandLow": None, "bandHigh": None,
                "lotSize": None, "issueSizeCr": None, "bseIpoNo": None, "bseScripCode": None, "withdrawn": False,
                "totalSub": None, "_final": True, **kw}

    rows: list[dict] = []
    for c in listed:
        old = by_ig.get(c["igId"])
        if old is None:                                 # first sighting: our row, if the name AND the opening date agree
            old = by_name.get(known.match(c["name"]) or "")          # an alias can name a row that is not on the board
            if old is not None and not _same_issue(old.get("open"), c.get("open")):
                old = None
        name = old["name"] if old else display_name(c["name"])
        if any(r["name"] == name for r in rows):
            continue
        where = c.get("listingAt") or ""
        rows.append(blank(name=name, igId=c["igId"], open=c.get("open"), close=c.get("close"),
                          symbol=(old or {}).get("symbol"), series=(old or {}).get("series"),
                          board="SME" if "sme" in (c.get("category") or "").lower() or "SME" in where else "Mainboard",
                          exchange="bse" if "BSE SME" in where else "nse", source="InvestorGain IPO list"))
    n_list = len(rows)

    cut = (today - dt.timedelta(days=CARRY_AFTER_CLOSE_DAYS)).isoformat()
    for old in prev_rows:                               # what the list has dropped: build_board applies the normal expiry
        if any(r["name"] == old["name"] for r in rows) or (not old.get("listing") and (old.get("close") or "9999") < cut):
            continue
        rows.append(blank(name=old["name"], igId=old.get("igId"), open=old.get("open"), close=old.get("close"), source=None,
                          board="SME" if str(old.get("type", "")).endswith("SME") else "Mainboard",
                          exchange="bse" if old.get("type") == "BSE SME" else "nse",
                          **{f: old.get(f) for f in _BASICS}))
    n_carried = len(rows) - n_list

    ours = Matcher(rows, aliases)
    final = {r["name"]: r for r in rows}
    seen = {"nse": 0, "bse": 0, "new": 0}

    def absorb(found: list[dict], exchange: str) -> None:
        for e in found:
            seen[exchange] += 1
            hit = ours.match(e["name"], e.get("symbol"))
            target = final.get(hit)                     # an alias may name a row that is not on today's board
            if target is not None and not _same_issue(target.get("open"), e.get("open")):
                target = None
            if target is None:                          # an issue only the exchange knows still gets its row
                rows.append({**e, "exchange": exchange, "totalSub": None})
                seen["new"] += 1
                continue
            for f in _BASICS:
                if target.get(f) in (None, "") and e.get(f) not in (None, ""):
                    target[f] = e[f]

    for label, fn in (("current", nse_ipo.current_issues), ("upcoming", nse_ipo.upcoming_issues)):
        try:
            absorb(fn(session), "nse")
        except SourceBlocked as e:
            res.notes.append(f"nse blocked ({e.detail}): symbols for new rows wait for the next run")
            break
        except SourceError as e:                        # an empty upcoming list is normal
            log.info("nse %s: %s", label, e.detail)
    try:
        absorb(bse_issues.public_issues_json(session), "bse")
    except SourceError as e:
        res.notes.append(f"bse not merged ({e.kind}): BSE issue numbers for new rows wait for the next run")

    mainboard, sme, lot = build_board(rows, prev, today, "nse")
    if not mainboard and not sme:
        raise SourceChanged("investorgain", f"{len(listed)} listed issues but none belong on today's board")
    return _finish(res, mainboard, sme, lot, prev,
                   f"investorgain list={n_list} carried={n_carried} +nse={seen['nse']} +bse={seen['bse']} exchange-only={seen['new']}")


def _from_nse(session: Session, prev: dict, res: Result, today: dt.date) -> str:
    rows: list[dict] = []
    failures: list[SourceError] = []

    def grab(label, fn):
        try:
            got = fn()
            rows.extend(got)
            return len(got)
        except SourceChanged as e:          # an empty upcoming list is normal; an empty everything is not
            failures.append(e)
            log.info("nse %s: %s", label, e.detail)
            return 0

    n_cur = grab("current", lambda: nse_ipo.current_issues(session))
    n_up = grab("upcoming", lambda: nse_ipo.upcoming_issues(session))
    n_past = grab("past", lambda: nse_ipo.past_issues(session, today - dt.timedelta(days=PAST_WINDOW_DAYS), today))
    if not rows:
        raise SourceChanged("nse", "current, upcoming and past issues all empty or unparseable: "
                            + "; ".join(f.detail for f in failures))

    # BSE lists what NSE cannot: BSE SME issues, and the IPO_NO that unlocks BSE's subscription page for
    # mainboard rows. Best effort — NSE alone is still a good calendar. NSE rows come first, so on a name
    # both exchanges list, _dedupe keeps NSE's fields and BSE only fills gaps.
    for r in rows:
        r.setdefault("exchange", "nse")
    n_bse = 0
    try:
        for r in bse_issues.public_issues_json(session):
            r["exchange"] = "bse"
            rows.append(r)
            n_bse += 1
    except SourceError as e:
        log.info("bse enrichment skipped: %s", e.detail)
        res.notes.append(f"bse not merged ({e.kind}): BSE SME issues may be missing")

    # lot size is not in the list rows; ipo-detail has it. Only for issues that need it and are live-ish.
    detail_calls = 0
    for r in _dedupe(rows):
        if r.get("lotSize") or not r.get("symbol"):
            continue
        if derive_status(r.get("open"), r.get("close"), r.get("listing"), today) not in ("Open", "Upcoming", "Closed"):
            continue
        if detail_calls >= 12:
            break
        detail_calls += 1
        try:
            d = nse_ipo.ipo_detail(session, r["symbol"], r.get("series") or "EQ")
        except SourceError as e:
            log.info("nse ipo-detail %s: %s", r["symbol"], e.detail)
            if isinstance(e, SourceBlocked):
                break
            continue
        info = nse_ipo.detail_lot(d)
        for x in rows:
            if x.get("symbol") == r["symbol"]:
                x["lotSize"] = x.get("lotSize") or info["lotSize"]
                x["issueSizeCr"] = x.get("issueSizeCr") or info["issueSizeCr"]
                if x.get("bandHigh") is None and info["bandHigh"]:
                    x["bandLow"], x["bandHigh"] = info["bandLow"], info["bandHigh"]

    mainboard, sme, lot = build_board(rows, prev, today, "nse")
    if not mainboard and not sme:
        raise SourceChanged("nse", f"{len(rows)} rows fetched but none belong on today's board")
    return _finish(res, mainboard, sme, lot, prev,
                   f"nse current={n_cur} upcoming={n_up} past={n_past} detail={detail_calls} +bse={n_bse}")


def _from_bse(session: Session, prev: dict, res: Result, today: dt.date) -> str:
    rows = None
    errs = []
    for label, fn in (("api", lambda: bse_issues.public_issues_json(session)),
                      ("legacy", lambda: bse_issues.public_issues_html(session))):
        try:
            rows = fn()
            break
        except SourceError as e:
            errs.append(f"{label}: {e.detail}")
            log.info("bse %s: %s", label, e.detail)
    if rows is None:
        raise SourceChanged("bse", "; ".join(errs))
    mainboard, sme, lot = build_board(rows, prev, today, "bse")
    if not mainboard and not sme:
        raise SourceChanged("bse", f"{len(rows)} rows fetched but none belong on today's board")
    res.unresolved.append("calendar came from BSE (NSE unavailable): NSE SME issues may be missing and "
                          "lot sizes are carried from the previous board")
    return _finish(res, mainboard, sme, lot, prev, f"bse rows={len(rows)}")


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = _today(today)
    return try_chain(res, [("investorgain", lambda: _from_investorgain(session, prev, res, t)),
                           ("nse", lambda: _from_nse(session, prev, res, t)),
                           ("bse", lambda: _from_bse(session, prev, res, t))])
