"""planner — owns `calendar`: every dated event that needs the reader, and what one application blocks, in one part.

The page's capital planner and week strip read this and compute nothing: the money each category blocks, the day it comes
back, how many days that is, and which earlier issues' money is back in time, are all written here.

    calendar = {asOf, from, to,                           the window: today - BACK_DAYS .. today + AHEAD_DAYS
                events[{date, kind, name, igId?, sme?, src, amountCr?}],
                issues{igId: {name, sme, status, open, close, allotment, refund, listing, lockIn30?, lockIn90?,
                              blocks{retail|snii|bnii|employee|shareholder: {amount, shares, lots, discount?, offered?}},
                              releaseDate, releaseSrc, blockedDays, retailSlots?, retailSizeCr?, fundReuse[igId]}},
                unlinked[{name, igId, kinds[]}], conflicts[{igId, name, kind, record, report}],
                sources{ig554: {months[], events}, ig607: {rows}}}

Events, in order of authority:
  * the board rows (mainboard, sme — the per-IPO record via `details`): open, close, allotment, refund (the unblock day),
    listing. Each row's dates are the record's; they are what the Board shows, so they win.
  * `anchors[]`: lockIn30 / lockIn90 (half the anchor book free, then the rest) — kinds lockin30 / lockin90.
  * `quota[]`: recordDate (a shareholder quota needs the parent held on this day) — kind record.
  * InvestorGain report 554, the event calendar (one call a month, the months the window touches): the same five kinds for
    every issue the site dates. An event for an issue on the board is checked against the row: a different day is recorded
    in `conflicts` and the row's day stands — never swapped silently. An issue not on the board (past the board's grace,
    or not yet in list-read) is added from the report alone, marked `src: "ig554"`, and listed in `unlinked`.
  * report 607, the allotment planner (mainboard only): retailSlots (the most retail allottees the quota can take),
    retailSizeCr, and fundReuse — the issues whose unblock lands before this one closes.

Money blocked per category comes from the row's `apply` (details copies it from the record's own figures; the record speaks
at the cap price). `blockedDays` is refund minus close: the shortest stretch the money is away for someone applying on the
last day. Allotment odds are NOT here: the page quotes `sub` and `apps` on the row, as the Board does.

The report is the module's source: when 554 fails the module fails and yesterday's calendar stands, stamped stale. 607 is
optional — mainboard only, five rows — and its absence is a note.
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from ..errors import SourceError
from ..http import Session
from ..names import Matcher
from ..result import Result
from ..sources import investorgain

log = logging.getLogger("collector.planner")
IST = ZoneInfo("Asia/Kolkata")
BACK_DAYS, AHEAD_DAYS = 7, 45
ROW_KINDS = (("open", "open"), ("close", "close"), ("allotment", "allotment"), ("refund", "refund"), ("listing", "listing"))
KIND_ORDER = {k: i for i, k in enumerate(("open", "close", "allotment", "refund", "listing", "lockin30", "lockin90", "record"))}


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def months_touching(frm: dt.date, to: dt.date) -> list[dt.date]:
    out, d = [], frm.replace(day=1)
    while d <= to:
        out.append(d)
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


def _is_sme(row: dict) -> bool:
    return "SME" in str(row.get("type") or "").upper()


def build(doc: dict, events_554: list[dict], planner_607: list[dict], today: dt.date, months: list[dt.date]) -> dict:
    frm, to = today - dt.timedelta(days=BACK_DAYS), today + dt.timedelta(days=AHEAD_DAYS)
    inside = lambda day: day is not None and frm.isoformat() <= day <= to.isoformat()
    rows = [r for k in ("mainboard", "sme") for r in (doc.get(k) or []) if isinstance(r, dict) and r.get("name")]
    by_id = {str(r["igId"]): r for r in rows if r.get("igId") is not None}
    matcher = Matcher(rows)
    by_name = {r["name"]: r for r in rows}
    # a listing that has left the board (anchors rows live 150 days) is still known by id and segment through listedPerf
    perf = {p["name"]: p for p in (doc.get("listedPerf") or []) if isinstance(p, dict) and p.get("name")}
    ident = lambda name, row: (row.get("igId"), _is_sme(row)) if row else (perf.get(name, {}).get("igId"), perf.get(name, {}).get("sme")) if name in perf else (None, None)
    events: list[dict] = []
    seen: set[tuple] = set()

    def add(ev: dict) -> None:
        key = (ev["date"], ev["kind"], ev.get("igId") or ev["name"])
        if key in seen:
            return
        seen.add(key)
        events.append(ev)

    issues: dict[str, dict] = {}
    for r in rows:
        sme = _is_sme(r)
        for field, kind in ROW_KINDS:
            day = str(r.get(field) or "")[:10]
            if inside(day):
                add({"date": day, "kind": kind, "name": r["name"], "igId": r.get("igId"), "sme": sme, "src": "record"})
        if r.get("status") == "Listed" or r.get("igId") is None:
            continue
        close, refund = _date(r.get("close")), _date(r.get("refund"))
        release = refund or (_date(r.get("allotment")) + dt.timedelta(days=1) if _date(r.get("allotment")) else None)
        issues[str(r["igId"])] = {k: v for k, v in {
            "name": r["name"], "sme": sme, "status": r.get("status"), "open": r.get("open"), "close": r.get("close"),
            "allotment": r.get("allotment"), "refund": r.get("refund"), "listing": r.get("listing"),
            "blocks": dict(r.get("apply") or {}) or None,
            "releaseDate": release.isoformat() if release else None, "releaseSrc": "refund" if refund else "allotment+1" if release else None,
            "blockedDays": (release - close).days if release and close else None, "fundReuse": []}.items() if v is not None}

    for a in doc.get("anchors") or []:
        if not isinstance(a, dict) or not a.get("name"):
            continue
        row = by_name.get(a["name"]) or by_name.get(matcher.match(a["name"]) or "")
        ig_id, sme = ident(a["name"], row)
        for field, kind in (("lockIn30", "lockin30"), ("lockIn90", "lockin90")):
            day = str(a.get(field) or "")[:10]
            if inside(day):
                add({"date": day, "kind": kind, "name": a["name"], "igId": ig_id, "sme": sme, "src": "anchors",
                     "amountCr": round(a["amountCr"] / 2, 2) if a.get("amountCr") else None})
        if row and str(row.get("igId")) in issues:
            for field in ("lockIn30", "lockIn90"):
                if a.get(field):
                    issues[str(row["igId"])][field] = a[field]
    for q in doc.get("quota") or []:
        if isinstance(q, dict) and q.get("name") and inside(str(q.get("recordDate") or "")[:10]):
            add({"date": str(q["recordDate"])[:10], "kind": "record", "name": q["name"], "src": "quota", "parent": q.get("parent")})

    conflicts, unlinked = [], {}
    for e in events_554:
        if not inside(e["date"]):
            continue
        row = by_id.get(e["igId"])
        if row is None:
            name = matcher.match(e["name"])
            row = by_name.get(name) if name else None
            if row is not None and row.get("igId") not in (None, e["igId"]):
                row = None                                        # same spelling, another id: not this issue
        if row is None:
            u = unlinked.setdefault(e["igId"], {"name": e["name"], "igId": e["igId"], "kinds": []})
            u["kinds"].append(e["kind"])
            add({"date": e["date"], "kind": e["kind"], "name": e["name"], "igId": e["igId"], "src": "ig554"})
            continue
        ours = str(row.get(e["kind"]) or "")[:10]
        if ours and ours != e["date"]:
            conflicts.append({"igId": e["igId"], "name": row["name"], "kind": e["kind"], "record": ours, "report": e["date"]})
        elif not ours:
            add({"date": e["date"], "kind": e["kind"], "name": row["name"], "igId": row.get("igId"), "sme": _is_sme(row), "src": "ig554"})

    matched_607 = 0
    for p in planner_607:
        it = issues.get(p["igId"])
        if it is None:
            continue
        matched_607 += 1
        for k in ("retailSlots", "retailSizeCr"):
            if p.get(k):
                it[k] = p[k]
        it["fundReuse"] = [i for i in p.get("fundReuse") or [] if i in issues or i in by_id]

    events.sort(key=lambda e: (e["date"], KIND_ORDER.get(e["kind"], 9), e["name"]))
    return {"asOf": today.isoformat(), "from": frm.isoformat(), "to": to.isoformat(), "events": events, "issues": issues,
            "unlinked": sorted(unlinked.values(), key=lambda u: u["name"]), "conflicts": conflicts,
            "sources": {"ig554": {"months": [m.strftime("%Y-%m") for m in months], "events": len(events_554)},
                        "ig607": {"rows": len(planner_607), "matched": matched_607}}}


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    today = today or dt.datetime.now(IST).date()
    doc = res.doc if res.doc is not None else prev
    months = months_touching(today - dt.timedelta(days=BACK_DAYS), today + dt.timedelta(days=AHEAD_DAYS))
    events: list[dict] = []
    try:
        for m in months:
            got = investorgain.fetch_event_calendar(session, m)
            if m.year == today.year and m.month == today.month and not got:
                raise investorgain.SourceChanged(investorgain.SOURCE, f"report 554: the current month {m:%Y-%m} has no events", "report 554")
            events.extend(got)
    except SourceError as e:
        return res.fail(e, "investorgain")
    planner: list[dict] = []
    try:
        planner = investorgain.fetch_allotment_planner(session, today)
    except SourceError as e:
        res.notes.append(f"report 607 (retail slots, fund reuse) did not answer: {e.detail} — carried nothing")
    cal = build(doc, events, planner, today, months)
    res.replace["calendar"] = cal
    n_issues, n_ev = len(cal["issues"]), len(cal["events"])
    res.notes.append(f"{n_ev} events {cal['from']}..{cal['to']}, {n_issues} issues with terms, {len(cal['unlinked'])} from the report only"
                     + (f", {len(cal['conflicts'])} date conflicts (the record's day stands)" if cal["conflicts"] else ""))
    for c in cal["conflicts"][:5]:
        res.unresolved.append(f"[planner] {c['name']}: {c['kind']} is {c['record']} on the record, {c['report']} on report 554")
    return res.won("investorgain", today.isoformat())
