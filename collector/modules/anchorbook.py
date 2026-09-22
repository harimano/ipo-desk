"""anchorbook — owns `anchorBooks`: who took the anchor allocation of every IPO on file, kept for ever.

The track-record layer (evidence, phase 2) needs, for each anchor investor, every IPO they anchored and what it did.
InvestorGain's per-IPO record carries the anchor allocation as an HTML table (`anchor_investor_detail`, parsed AS a
table by sources.investorgain.parse_anchor_book), back to 2022. `details` fetches that record only for rows on the
board and drops the table; this module walks the whole history (`listedPerf` ids, newest first) and freezes each book:

  anchorBooks = {asOf, n, books{igId: {name, sme, listedOn, bidDate, price, totalShares, pctQib, locked30, locked90,
                                        complete, rows[{name, key, shares, amtCr, pctAlloc, pctIssue}], fetchedOn}},
                 none{igId: triedOn}}          # records with no anchor table (no anchor round, or left out)

Backfill: PER_RUN records a run, newest listing first, so 1,300 IPOs take about a month of full runs; then a run costs
only what listed since. A book is fetched once and never rewritten (`complete` says whether the feed gave the whole list:
some records carry only the first two names — a limit of the free feed, cause unknown — so a partial book is stored
as partial, never as a small one). A record with no table is remembered in `none` and retried after RETRY_NONE_DAYS
only while the listing is young. A 403 stops the run at once (prev kept); a failed record is skipped and counted.

`key` is the investor name normalised for matching across spellings (upper, punctuation out, the fund after "A/C"
when a trustee is named) — the one place that rule lives, for evidence and the page.
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

log = logging.getLogger("collector.anchorbook")
IST = ZoneInfo("Asia/Kolkata")
PER_RUN = 80
RETRY_NONE_DAYS = 14
YOUNG_DAYS = 45


def investor_key(name: str) -> str:
    s = (name or "").upper()
    if "A/C" in s:                                       # "XYZ TRUSTEE CO LTD A/C ABC SMALL CAP FUND" -> the fund
        s = s.split("A/C", 1)[1]
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\b(PRIVATE|PVT|LIMITED|LTD|LLP|CO|INC|PLC|THE|TRUSTEE|TRUSTEES|COMPANY)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def listings_on_file(doc: dict) -> list[dict]:
    """Every listed IPO with an InvestorGain id: {igId, name, sme, listedOn}, newest first."""
    seen: dict[str, dict] = {}
    for p in doc.get("listedPerf") or []:
        if isinstance(p, dict) and p.get("igId") and p.get("name") and p.get("date"):
            seen[str(p["igId"])] = {"igId": str(p["igId"]), "name": p["name"], "sme": bool(p.get("sme")), "listedOn": str(p["date"])[:10]}
    for k in ("mainboard", "sme"):
        for r in doc.get(k) or []:
            if isinstance(r, dict) and r.get("igId") and r.get("name") and r.get("status") == "Listed" and r.get("listing"):
                seen.setdefault(str(r["igId"]), {"igId": str(r["igId"]), "name": r["name"], "sme": k == "sme", "listedOn": str(r["listing"])[:10]})
    return sorted(seen.values(), key=lambda r: r["listedOn"], reverse=True)


def due(prev_books: dict, listings: list[dict], today: dt.date) -> list[dict]:
    books, none = prev_books.get("books") or {}, prev_books.get("none") or {}
    out = []
    for r in listings:
        if r["igId"] in books:
            continue
        tried = none.get(r["igId"])
        if tried:
            try:
                age = (today - dt.date.fromisoformat(r["listedOn"])).days
                if age > YOUNG_DAYS or (today - dt.date.fromisoformat(str(tried)[:10])).days < RETRY_NONE_DAYS:
                    continue
            except ValueError:
                continue
        out.append(r)
    return out[:PER_RUN]


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = today or dt.datetime.now(IST).date()
    doc = res.doc or prev
    prev_books = prev.get("anchorBooks") if isinstance(prev.get("anchorBooks"), dict) else {}
    books = dict(prev_books.get("books") or {})
    none = dict(prev_books.get("none") or {})
    listings = listings_on_file(doc)
    todo = due(prev_books, listings, t)
    got = empty = failed = 0
    last_err: SourceError | None = None
    for r in todo:
        try:
            raw = session.get_json(ig.IPO_DETAIL_URL.format(id=r["igId"]), source=ig.SOURCE, headers=ig.HEADERS)
            res.calls += 1
            rec = (raw.get("ipoData") or [{}])[0] if isinstance(raw, dict) else {}
            book = ig.parse_anchor_book(rec.get("anchor_investor_detail"))
        except SourceBlocked as e:
            if not got and not empty:
                return res.fail(e)
            res.notes.append(f"blocked after {got + empty} records; stopping")
            break
        except SourceError as e:
            failed, last_err = failed + 1, e
            continue
        if book is None:
            none[r["igId"]] = t.isoformat()
            empty += 1
            continue
        for row in book["rows"]:
            row["key"] = investor_key(row["name"])
        books[r["igId"]] = {"name": r["name"], "sme": r["sme"], "listedOn": r["listedOn"], **book, "fetchedOn": t.isoformat()}
        none.pop(r["igId"], None)
        got += 1
    if todo and not got and not empty:
        return res.fail(last_err or SourceChanged(ig.SOURCE, "no anchor record could be read"))
    left = len([r for r in listings if r["igId"] not in books and r["igId"] not in none])
    res.replace["anchorBooks"] = {"asOf": t.isoformat(), "n": len(books), "books": books, "none": none}
    partial = sum(1 for b in books.values() if b.get("complete") is False)
    res.notes.append(f"{got} anchor books read ({empty} without an anchor table, {failed} failed); {len(books)} on file, "
                     f"{partial} partial (feed gave only the first names); {left} of {len(listings)} listings still to fetch")
    return res.won(ig.SOURCE, t.isoformat())
