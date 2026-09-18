"""history — owns `listedPerf` and `comps`: what past issues' signals said, and what then happened.

This is the desk's evidence base — the page bands QIB, total subscription and GMP by how issues in the same band
went on to list — so it has to be ours to publish. Until 19 Sep 2026 it was a seed reshaped from another project's
dataset that states no licence; it is now built from fetched reports and nothing else:

  report 377   every listing of a year, 2022 onward, SME included: issue price, last GMP, estimated price, listing
               open, listing-day close, latest price, total subscription. One call per year; a finished year is
               fetched once and then kept.
  report 566   this year's subscription by category (QIB / sHNI / bHNI / NII / retail), joined on the id.
               Category books exist for the current year only; they are kept on file as years pass, so QIB
               evidence starts with 2026 and grows. Total subscription covers every year.

    listedPerf[]  {name, igId, date, sme, issue, gmp, gmpImplied, listing, close1, ltp}     newest first
    comps[]       {name, igId, year, sme, total, qib?, nii?, retail?, snii?, bnii?, ret, retClose}
                  ret = listing open vs issue, in %: "listed positive" means exactly this.

Names are the source's own short names; both lists use the same ones, so they join on `name` or `igId`.
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from ..errors import SourceBlocked, SourceError
from ..http import Session
from ..result import Result
from ..sources import investorgain

log = logging.getLogger("collector.history")
IST = ZoneInfo("Asia/Kolkata")
FIRST_YEAR = 2022                     # report 377 has nothing earlier


def _pct(a, b) -> float | None:
    return round(100 * (a - b) / b, 2) if a is not None and b else None


def build(perf: list[dict], cats: dict[str, dict], books: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    perf = sorted({p["igId"]: p for p in perf}.values(), key=lambda p: (p["date"], p["igId"]), reverse=True)
    listed = [{k: p.get(k) for k in ("name", "igId", "date", "sme", "issue", "gmp", "gmpImplied", "listing", "close1", "ltp")} for p in perf]
    comps = []
    for p in perf:
        c = {"name": p["name"], "igId": p["igId"], "year": int(p["date"][:4]), "sme": p["sme"], "total": p.get("total"),
             "ret": _pct(p["listing"], p["issue"]), "retClose": _pct(p.get("close1"), p["issue"])}
        book = cats.get(p["igId"]) or books.get(p["igId"]) or {}
        for k in ("qib", "nii", "retail", "snii", "bnii"):
            if book.get(k) is not None:
                c[k] = book[k]
        comps.append(c)
    return listed, comps


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = today or dt.datetime.now(IST).date()
    old_perf = [p for p in prev.get("listedPerf") or [] if isinstance(p, dict) and p.get("igId") and p.get("date")]
    have_years = {int(p["date"][:4]) for p in old_perf}
    perf = [p for p in old_perf if int(p["date"][:4]) < t.year]          # finished years are kept as they are
    old_by = {c["igId"]: c for c in prev.get("comps") or [] if isinstance(c, dict) and c.get("igId")}
    perf_extra = {p["igId"]: {"total": old_by.get(p["igId"], {}).get("total")} for p in perf}

    fetched, last = [], None
    for year in range(t.year, FIRST_YEAR - 1, -1):
        if year < t.year and year in have_years:
            continue
        try:
            rows = investorgain.fetch_performance_report(session, year)
        except SourceBlocked as e:
            last = e
            break
        except SourceError as e:
            last = e
            log.info("history %s: %s", year, e.detail)
            if year == t.year:
                perf += [p for p in old_perf if int(p["date"][:4]) == year]    # keep this year's rows rather than lose them
            continue
        perf = [p for p in perf if int(p["date"][:4]) != year] + [r for r in rows if int(r["date"][:4]) == year or year == t.year]
        fetched.append(f"{year}: {len(rows)}")
    if not fetched:
        return res.fail(last or RuntimeError("no year of report 377 could be fetched"))
    for p in perf:                                                        # rows kept from prev carry no `total` field: restore it
        if "total" not in p:
            p["total"] = (perf_extra.get(p["igId"]) or {}).get("total")

    cats: dict[str, dict] = {}
    try:
        cats = {s["igId"]: s for s in investorgain.fetch_subscription_report(session, t)}
        res.tried.append({"source": "investorgain-566", "ok": True})
    except SourceError as e:
        res.tried.append({**e.record(), "ok": False})
        res.notes.append(f"category subscription unavailable ({e.kind}): this year's QIB / retail not refreshed")

    # a finished year's category book cannot be fetched again (report 566 is this year only; older per-IPO records
    # keep just the total — checked 19 Sep 2026), so what is on file for those issues is kept
    books = {i: {k: c.get(k) for k in ("qib", "nii", "retail", "snii", "bnii")} for i, c in old_by.items() if c.get("qib") is not None}
    listed, comps = build(perf, cats, books)
    res.replace["listedPerf"], res.replace["comps"] = listed, comps
    main = [c for c in comps if not c["sme"]]
    res.notes.append(f"{len(listed)} listings since {FIRST_YEAR} ({len(listed) - len(main)} SME); fetched {', '.join(fetched)}; "
                     f"QIB on file for {sum(1 for c in main if c.get('qib') is not None)} of {len(main)} mainboard issues")
    return res.won("investorgain", t.isoformat())
