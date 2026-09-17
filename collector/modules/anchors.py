"""anchors — owns `anchors[]`. Fetched facts only: nothing in a run opens or reads a document.

  book size    NSE ipo-detail (JSON): "Issue Size" states the anchor portion in shares; x the upper band
               is the book, to the rupee (NSE's own IPO: 37,793,739 x 1,785 = 6,746.18 Cr — the figure
               in the issuer's letter). One call per issue, once: the portion does not change.
  dates        InvestorGain report 480 (JSON), one call per run: anchor bid date, and the lock-in expiries
               — half the anchor shares are free to sell after 30 days, the rest after 90.
  issue size   InvestorGain's figure for the whole issue, so "anchor as % of issue" divides like by like.

WHO took the book, and how much each took, is published only as the issuer's letter — a PDF, often a
scan — by the exchanges and by every aggregator alike. Turning that into data is reading, not fetching,
and reading does not belong in a scheduled run (17 Sep 2026: even with OCR and arithmetic checks only
76% of NSE's own letter could be verified). So this module never produces `investors[]`. Rows that
already carry one — written by hand in the db era, or read from a text PDF on 17 Sep — keep it; the
facts below are added to them and nothing of theirs is touched. `python -m collector.pdf.anchor` still
exists as a bench tool for the research layer; no workflow calls it.
"""
from __future__ import annotations

import datetime as dt
import logging
import pathlib
from zoneinfo import ZoneInfo

from ..errors import SourceBlocked, SourceError
from ..http import NSE, Session
from ..names import Matcher, load_aliases
from ..result import Result
from ..sources import investorgain, nse_ipo

log = logging.getLogger("collector.anchors")
IST = ZoneInfo("Asia/Kolkata")
ALIASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"
BASIS = "exchange-json"               # marks figures this module computed, so it may refresh them and nothing else
MAX_DETAIL_CALLS = 6
WINDOW_BEFORE_OPEN, WINDOW_AFTER_OPEN = 3, 12     # days around `open` in which the anchor portion is looked up
MAX_BID_TO_OPEN_DAYS = 7              # bid is T-1 working day; a week allows for holidays and a deferred opening
KEEP_DAYS = 150                       # a row outlives its 90-day lock-in, then leaves


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _fmt(v) -> str:
    d = _date(v)
    return f"{d.day} {d:%b}" if d else "—"


def summary(row: dict) -> str:
    """One line for the page, written only for rows this module created."""
    bits = []
    if row.get("amountCr"):
        bits.append(f"₹{row['amountCr']:,.2f} Cr anchor book")
    if row.get("date"):
        bits.append(f"bid {_fmt(row['date'])}")
    if row.get("amountCr") and row.get("issueSizeCr"):
        bits.append(f"{100 * row['amountCr'] / row['issueSizeCr']:.0f}% of the issue")
    if row.get("lockIn30"):
        bits.append(f"lock-in ends {_fmt(row['lockIn30'])} (half) and {_fmt(row.get('lockIn90'))}")
    return " · ".join(bits)


def needs_shares(board_row: dict, anchor_row: dict | None, today: dt.date) -> bool:
    if not board_row.get("symbol") or (anchor_row or {}).get("anchorShares") is not None:
        return False                                    # no symbol to ask with, or already asked (0 = none stated)
    opens = _date(board_row.get("open"))
    return bool(opens) and -WINDOW_BEFORE_OPEN <= (today - opens).days <= WINDOW_AFTER_OPEN


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = today or dt.datetime.now(IST).date()
    aliases = load_aliases(ALIASES_DIR)
    rows = [dict(a) for a in prev.get("anchors") or [] if isinstance(a, dict) and a.get("name")]
    board = [r for k in ("mainboard", "sme") for r in (prev.get(k) or []) if isinstance(r, dict) and r.get("name")]

    # ---- 1. the calendar: one call, every issue of the year -------------------------------------
    cal, cal_err = [], None
    try:
        cal = investorgain.fetch_anchor_calendar(session, t)
        res.tried.append({"source": "investorgain-480", "ok": True})
    except SourceError as e:
        cal_err = e
        res.tried.append({**e.record(), "ok": False})
        log.info("anchor calendar: %s", e.detail)

    # our spelling for each calendar row: a board row first, else an anchors row already on file
    board_by = {b["name"]: b for b in board}
    ours = Matcher(board + [r for r in rows if r["name"] not in board_by], aliases)
    known_date = {**{r["name"]: r.get("date") for r in rows}, **{n: None for n in board_by}}
    cal_for: dict[str, dict] = {}
    for c in cal:
        name = ours.match(c["name"])
        if not name:
            continue
        # a name alone is not enough to hang dates on a row: anchor bidding is the working day before an issue
        # opens, so the calendar's bid date must sit just before our `open` (or beside the date already on file)
        bid, opens, filed = _date(c["bidDate"]), _date((board_by.get(name) or {}).get("open")), _date(known_date.get(name))
        if opens is not None:
            agrees = 0 <= (opens - bid).days <= MAX_BID_TO_OPEN_DAYS
        elif filed is not None:
            agrees = abs((filed - bid).days) <= MAX_BID_TO_OPEN_DAYS
        else:
            agrees = name == c["name"] or aliases.get(c["name"]) == name      # no date to check against: exact or alias only
        if agrees:
            cal_for.setdefault(name, c)
        else:
            log.info("anchor calendar: %r matched %r by name but the dates disagree — ignored", c["name"], name)

    by_name = {r["name"]: r for r in rows}
    on_file = Matcher(rows, aliases)

    def row_for(name: str, create: bool) -> dict | None:
        if name in by_name:                             # includes rows created earlier in this run
            return by_name[name]
        hit = on_file.match(name)
        if hit:
            return by_name[hit]
        if not create:
            return None
        new = {"name": name, "date": None, "amountCr": None, "issueSizeCr": None, "count": None, "topTierShare": None,
               "investors": [], "sources": [], "source": BASIS, "auto": True}
        rows.append(new)
        by_name[name] = new
        return new

    # ---- 2. dates, for every row the calendar knows ----------------------------------------------
    dated = 0
    for name, c in cal_for.items():
        a = row_for(name, create=any(b["name"] == name for b in board))
        if a is None:
            continue
        before = (a.get("lockIn30"), a.get("lockIn90"), a.get("date"))
        a["date"] = a.get("date") or c["bidDate"]
        a["lockIn30"], a["lockIn90"] = c["lockIn30"] or a.get("lockIn30"), c["lockIn90"] or a.get("lockIn90")
        if c.get("issueSizeCr") and (a.get("auto") or not a.get("issueSizeCr")):
            a["issueSizeCr"] = c["issueSizeCr"]
        if c.get("page") and c["page"] not in (a.get("sources") or []):
            a["sources"] = (list(a.get("sources") or []) + [c["page"]])[:4]
        dated += before != (a.get("lockIn30"), a.get("lockIn90"), a.get("date"))

    # ---- 3. book size, once per issue, from NSE's own issue information ---------------------------
    sized, calls, nse_err, blocked = [], 0, None, False
    for b in sorted(board, key=lambda r: r.get("open") or "", reverse=True):
        a = row_for(b["name"], create=False)
        if blocked or calls >= MAX_DETAIL_CALLS or not needs_shares(b, a, t):
            continue
        calls += 1
        try:
            shares = nse_ipo.detail_anchor_shares(nse_ipo.ipo_detail(session, b["symbol"], b.get("series") or "EQ"))
        except SourceBlocked as e:
            nse_err, blocked = e, True                  # one 403 is enough; never ask again in this run
            continue
        except SourceError as e:
            nse_err = e
            log.info("anchor portion %s: %s", b["symbol"], e.detail)
            continue
        a = a or row_for(b["name"], create=True)
        a["anchorShares"] = shares or 0                 # 0 = looked, the issue states no anchor portion: do not ask again
        if not shares or not b.get("bandHigh"):
            continue
        a["price"] = a.get("price") or b["bandHigh"]
        if a.get("amountCr") is None or a.get("amountBasis") == BASIS:
            a["amountCr"], a["amountBasis"] = round(shares * float(b["bandHigh"]) / 1e7, 2), BASIS
        page = f"{NSE}/market-data/issue-information?symbol={b['symbol']}&series={b.get('series') or 'EQ'}&type=Active"
        if page not in (a.get("sources") or []):
            a["sources"] = ([page] + list(a.get("sources") or []))[:4]
        sized.append(f"{b['name']} ₹{a['amountCr']:,.0f} Cr")
    if calls:
        res.tried.append({"source": "nse-ipo-detail", "ok": bool(sized) or nse_err is None,
                          **({"kind": nse_err.kind, "detail": nse_err.detail} if nse_err and not sized else {})})

    # ---- 4. tidy: our own rows get their one-line summary; rows past their lock-ins leave ----------
    kept = []
    for a in rows:
        if a.get("auto"):
            if not (a.get("amountCr") or a.get("date")) and a.get("anchorShares") is None:
                continue                                # nothing learned about it: not a row yet
            a["anchor"] = summary(a) or "No anchor portion stated in NSE's issue information"
            a["note"] = ("Book size is NSE's stated anchor portion × the upper band; dates are InvestorGain's. "
                         "Who took the book is published only as the issuer's letter, which a run does not read.")
        last = _date(a.get("lockIn90")) or _date(a.get("date"))
        if last and (t - last).days > KEEP_DAYS:
            continue
        kept.append(a)
    kept.sort(key=lambda r: r.get("date") or "", reverse=True)

    if cal_err and (nse_err or not calls) and not sized:
        return res.fail(cal_err)                        # nothing answered: keep the previous section as it is
    res.replace["anchors"] = kept
    res.notes.append(f"{len(kept)} books on file; calendar matched {len(cal_for)} of ours, {dated} dates set"
                     + (f"; sized: {', '.join(sized)}" if sized else "")
                     + (f"; {len(rows) - len(kept)} past their lock-ins dropped" if len(rows) != len(kept) else ""))
    if cal_err:
        res.notes.append(f"anchor calendar unavailable ({cal_err.kind}): dates not refreshed")
    if nse_err and not sized:
        res.notes.append(f"NSE issue information unavailable ({nse_err.kind}): book sizes not looked up")
    res.ok, res.source, res.asOf = True, "+".join(s for s, ok in (("investorgain", not cal_err), ("nse", bool(sized))) if ok) or "none", t.isoformat()
    return res
