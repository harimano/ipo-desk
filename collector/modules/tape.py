"""tape — owns `tape`; merge-patches `priceHistory` with one close a day for EVERY listing of this year.

`listings` prices the board, `recent` and the lot names one by one (yahoo / angelone) and stops when a row leaves the
board. A tracker needs the price path of every listing for the 90 days that matter — the day-one churn, the anchor
lock-in at 30 and 90 days, the day a net buyer arrived — and NSE publishes all of it in one file: the EOD bhavcopy
(nsearchives, one zip a trading day, every symbol including the SME series). So: one call per trading day, filled in
newest first.

  tape = {asOf, dates[] (trading days filled, last 90), noFile[] (weekdays with no file: holidays, last 90),
          names{name: symbol} (what was priced), n}
  priceHistory[name] += [date, close]   for every listing of this year with an NSE symbol (board `symbol`, else the
                                        deals module's `investors.listingSymbols` cache), never a date twice.

Each run fetches at most FETCH_PER_RUN missing weekdays of the last LOOKBACK_DAYS, newest first, so a fresh install
backfills over a dozen runs and a steady state costs one call. Today's file is only tried after 18:30 IST (published
around six); a 404 before that is "not yet", not a holiday. A 404 on a past weekday is remembered as noFile. A 403
fails the module (prev kept); nothing is guessed. `history` keeps caps: priceHistory.days trims the series.
"""
from __future__ import annotations

import copy
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from ..errors import SourceBlocked, SourceChanged, SourceDown, SourceError
from ..http import Session
from ..result import Result
from ..sources import nsearchives

log = logging.getLogger("collector.tape")
IST = ZoneInfo("Asia/Kolkata")
LOOKBACK_DAYS = 60
FETCH_PER_RUN = 6
KEEP_DATES = 90
FILE_READY = dt.time(18, 30)


def this_years_names(doc: dict, today: dt.date) -> dict[str, str]:
    """name -> NSE symbol for every listing dated this year the document knows a symbol for."""
    jan1 = f"{today.year}-01-01"
    names: dict[str, str] = {}
    for k in ("mainboard", "sme"):
        for r in doc.get(k) or []:
            if isinstance(r, dict) and r.get("name") and r.get("symbol") and r.get("status") == "Listed" and str(r.get("listing") or "") >= jan1:
                names[r["name"]] = str(r["symbol"]).upper()
    cache = ((doc.get("investors") or {}).get("listingSymbols") or {})
    for p in doc.get("listedPerf") or []:
        if not isinstance(p, dict) or not p.get("name") or str(p.get("date") or "") < jan1 or p["name"] in names:
            continue
        sym = (cache.get(p["name"]) or {}).get("symbol") if isinstance(cache.get(p["name"]), dict) else None
        if sym:
            names[p["name"]] = str(sym).upper()
    return names


def weekdays_back(today: dt.date, n_days: int, now: dt.datetime) -> list[str]:
    """ISO weekdays from today back n_days, newest first; today only once its file can exist."""
    out = []
    for i in range(n_days + 1):
        d = today - dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        if d == today and now.timetz().replace(tzinfo=None) < FILE_READY:
            continue
        out.append(d.isoformat())
    return out


def missing_dates(prev_tape: dict, today: dt.date, now: dt.datetime) -> list[str]:
    have = set(prev_tape.get("dates") or []) | set(prev_tape.get("noFile") or [])
    return [d for d in weekdays_back(today, LOOKBACK_DAYS, now) if d not in have][:FETCH_PER_RUN]


def apply_day(history: dict, names: dict[str, str], day: dict[str, dict], date: str) -> int:
    added = 0
    for name, sym in names.items():
        rec = day.get(sym)
        if not rec or rec.get("close") is None:
            continue
        series = history.setdefault(name, [])
        if any(isinstance(p, list) and p and str(p[0])[:10] == date for p in series):
            continue
        series.append([date, rec["close"]])
        series.sort(key=lambda p: str(p[0]))
        added += 1
    return added


def run(session: Session, prev: dict, res: Result, now: dt.datetime | None = None) -> Result:
    now = now or dt.datetime.now(IST)
    today = now.date()
    doc = res.doc or prev
    prev_tape = prev.get("tape") if isinstance(prev.get("tape"), dict) else {}
    names = this_years_names(doc, today)
    if not names:
        return res.fail(SourceChanged("tape", "no listing of this year has an NSE symbol on file — deals/listingSymbols not run yet?"))
    todo = missing_dates(prev_tape, today, now)
    dates, no_file = list(prev_tape.get("dates") or []), list(prev_tape.get("noFile") or [])
    history: dict = {}
    touched: set[str] = set()
    fetched = added = 0
    for date in todo:
        d = dt.date.fromisoformat(date)
        try:
            day = nsearchives.bhavcopy(session, d)
            res.calls += 1
        except SourceBlocked as e:
            if not fetched:
                return res.fail(e)
            res.notes.append(f"bhavcopy {date}: blocked after {fetched} file(s); stopping")
            break
        except SourceDown as e:
            res.calls += 1
            if e.status == 404 and d < today:
                no_file.append(date)
                continue
            res.notes.append(f"bhavcopy {date}: {e.kind} {e.status or ''} — left for the next run")
            continue
        except SourceChanged as e:
            res.notes.append(f"bhavcopy {date}: {e.detail[:60]}")
            continue
        fetched += 1
        if not history:
            history = copy.deepcopy({n: s for n, s in (doc.get("priceHistory") or {}).items() if n in names})
        added += apply_day(history, names, day, date)
        touched |= {n for n, sym in names.items() if sym in day}
        dates.append(date)
    cutoff = (today - dt.timedelta(days=KEEP_DATES)).isoformat()
    dates = sorted({d for d in dates if d >= cutoff})
    no_file = sorted({d for d in no_file if d >= cutoff})
    if fetched:
        res.merge["priceHistory"] = {n: history[n] for n in touched if history.get(n)}
    res.replace["tape"] = {"asOf": now.replace(microsecond=0).isoformat(), "dates": dates, "noFile": no_file,
                           "names": names, "n": len(names)}
    left = len([d for d in weekdays_back(today, LOOKBACK_DAYS, now) if d not in set(dates) | set(no_file)])
    res.notes.append(f"{len(names)} listings with a symbol; {fetched} bhavcopy file(s) read, {added} closes added; "
                     f"{len(dates)} trading days on file, {left} still to fill")
    return res.won("nsearchives", dates[-1] if dates else None)
