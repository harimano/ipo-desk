"""players — owns `players`: which of the largest anchor investors are in the books of issues on the board today.

Source: InvestorGain report 551 (every anchor investor: IPOs anchored, total invested, average ticket — one call) and
report 561 (one investor's IPOs, newest first, each with our own listing id — one call an investor). The free feed gives
only an investor's FIVE most recent IPOs (`fldpage_size: 5`; page 2 repeats page 1 — a members' limit, left alone), which
is exactly enough for one question: is this investor in a book that is open or about to list? It is NOT enough for a track
record, so none is computed and the page shows none.

So: take the TRACK largest investors by money and by count, read each one's latest five, and turn the lists round into
`books{igId: [investor, ...]}` for listings on the board. The anchor list is published the evening before an issue opens —
this is the one signal that exists before the first bid. Coverage is stated, never implied: a book shows "n of the N
largest anchors"; a small SME book taken by local funds will rightly show none.

Runs in full runs only (about 55 calls, 20 s). A 403 stops the module at once; a failed investor is skipped and counted.
Rows kept from `prev` for listings still on the board when their investor could not be read today.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from zoneinfo import ZoneInfo

from ..errors import SourceBlocked, SourceChanged, SourceError
from ..http import Session
from ..result import Result
from ..sources import investorgain as ig

log = logging.getLogger("collector.players")
IST = ZoneInfo("Asia/Kolkata")
BOARDS = ("mainboard", "sme")
TRACK_BY_MONEY, TRACK_BY_COUNT = 40, 30
LIST_URL = "https://webnodejs.investorgain.com/cloud/v2/report/data-read/551/1/{m}/{y}/{fy}/0/all"
ONE_URL = "https://webnodejs.investorgain.com/cloud/v2/report/data-read/561/1/{m}/{y}/{fy}/0/{id}"


def _num(v) -> float | None:
    s = re.sub(r"[^\d.]", "", str(v or ""))
    return float(s) if s and s != "." else None


def parse_investors(data) -> list[dict]:
    rows = data.get("reportTableData") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows or "AnchorName" not in rows[0] or "~id" not in rows[0]:
        raise SourceChanged(ig.SOURCE, "report 551: no anchor-investor rows", LIST_URL)
    out = [{"id": str(r["~id"]), "name": ig.strip_tags(r.get("AnchorName")), "ipos": int(_num(r.get("~totalcount")) or 0),
            "investedCr": _num(r.get("Total Invested")), "ticketCr": _num(r.get("Avg Ticket Size"))} for r in rows if r.get("~id") and r.get("AnchorName")]
    if not out:
        raise SourceChanged(ig.SOURCE, "report 551: rows without id or name", LIST_URL)
    return out


def parse_ipos(data) -> list[str]:
    """The listing ids in one investor's latest IPOs. An investor with no rows is a changed source: 551 listed them for having some."""
    rows = data.get("reportTableData") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows or "~id" not in rows[0]:
        raise SourceChanged(ig.SOURCE, "report 561: no IPO rows for the investor", ONE_URL)
    return [str(r["~id"]) for r in rows if r.get("~id")]


def tracked(investors: list[dict]) -> list[dict]:
    by_money = sorted(investors, key=lambda r: -(r["investedCr"] or 0))[:TRACK_BY_MONEY]
    by_count = sorted(investors, key=lambda r: -r["ipos"])[:TRACK_BY_COUNT]
    seen, out = set(), []
    for r in by_money + by_count:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = today or dt.datetime.now(IST).date()
    doc = res.doc or prev
    live = {str(r["igId"]): r["name"] for k in BOARDS for r in (doc.get(k) or [])
            if isinstance(r, dict) and r.get("igId") and r.get("name") and r.get("status") != "Listed"}
    if not live:
        res.notes.append("no unlisted issue on the board; nothing to look up")
        return res.won("none", t.isoformat())
    fy = ig.fiscal_year(t)
    try:
        investors = parse_investors(session.get_json(LIST_URL.format(m=t.month, y=t.year, fy=fy), source=ig.SOURCE, headers=ig.HEADERS))
    except SourceError as e:
        return res.fail(e)
    watch, books, failed, last = tracked(investors), {}, 0, None
    for inv in watch:
        try:
            ids = parse_ipos(session.get_json(ONE_URL.format(m=t.month, y=t.year, fy=fy, id=inv["id"]), source=ig.SOURCE, headers=ig.HEADERS))
        except SourceBlocked as e:                       # a 403 ends the conversation for this run
            return res.fail(e)
        except SourceError as e:
            failed, last = failed + 1, e
            continue
        for i in ids:
            if i in live:
                books.setdefault(i, []).append({k: inv[k] for k in ("id", "name", "ipos", "investedCr", "ticketCr")})
    if failed == len(watch):
        return res.fail(last or SourceChanged(ig.SOURCE, "no investor could be read"))
    old = (prev.get("players") or {}).get("books") or {}
    for i, rows in old.items():                          # a book read yesterday stands when today's pass missed its investors
        if i in live and i not in books and failed:
            books[i] = rows
    for rows in books.values():
        rows.sort(key=lambda r: -(r["investedCr"] or 0))
    res.replace["players"] = {"asOf": t.isoformat(), "tracked": len(watch), "of": len(investors), "latestPerInvestor": 5,
                              "books": books, "names": {i: live[i] for i in books},
                              "league": [{k: r[k] for k in ("id", "name", "ipos", "investedCr", "ticketCr")} for r in watch[:25]]}
    res.notes.append(f"{len(watch)} of {len(investors)} anchor investors read ({failed} failed); names found for {len(books)} of {len(live)} unlisted issues")
    return res.won("investorgain", t.isoformat())
