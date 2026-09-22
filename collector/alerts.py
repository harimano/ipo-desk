"""Alerts — evaluated at the end of a run from two documents, the previous one and the new one.

The rules are `docs/project/legacy-briefing-rules.md`. The shape Hari asked for: one message, at most
six lines, the action first, silence when nothing is true.

An alert has a key. What is sent is `keys(new, today) - keys(prev, prev's day)`: a condition alerts when
it *becomes* true, so the 06:45 and 18:15 runs of one day never repeat each other and no state file is
needed. Date windows ("record date within 30 days") would otherwise be true for a month; they carry a
milestone in the key (30/14/7/3/1/0 days) and so speak again only as the date closes in.

    python -m collector.alerts --prev old.json --new data/latest.json          # dry run: print, send nothing
    python -m collector.alerts --prev old.json --new data/latest.json --send   # Telegram / ntfy, if configured

Never in the blocking path: `collect.yml` runs this after the commit with continue-on-error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from dataclasses import dataclass

MAX_LINES = 6
GAP_HOURS = 36
RECORD_WINDOW = (30, 14, 7, 3, 1, 0)
LAPSE_WINDOW = (14, 7, 3, 1, 0)
SUB_MARKS = (1, 10, 50, 100)     # total subscription, while the issue is open
_SIDE = {"BUY": "bought", "SELL": "sold"}


@dataclass(frozen=True)
class Alert:
    key: str
    rank: int          # lower = nearer the top of the message
    line: str


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _day(doc: dict) -> dt.date | None:
    return _date((doc.get("meta") or {}).get("asOf"))


def _fmt(d: dt.date) -> str:
    return f"{d.day} {d:%b}"


def _milestone(days: int, window: tuple[int, ...]) -> int | None:
    """The tightest milestone the date has reached: 9 days out is past the 14-day mark, not yet the 7."""
    if days < 0 or days > window[0]:
        return None
    return min(m for m in window if m >= days)


def _in(days: int) -> str:
    return "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"


def _rows(doc: dict, key: str) -> list[dict]:
    return [r for r in (doc.get(key) or []) if isinstance(r, dict) and r.get("name")]


# ---------------------------------------------------------------------------------------------
# the rules — each yields every alert that is TRUE for `doc` on `today`; novelty is decided later
# ---------------------------------------------------------------------------------------------
def _quota_dates(doc: dict, today: dt.date):
    for q in _rows(doc, "quota"):
        if q.get("bucket") in ("done", "dropped"):
            continue
        who = f"{q.get('parent') or q.get('parentFull') or '?'} ({q.get('ticker') or '?'})"
        rec = _date(q.get("recordDate"))
        if rec and q.get("quota") is not False:
            m = _milestone((rec - today).days, RECORD_WINDOW)
            if m is not None:
                n = (rec - today).days
                yield Alert(f"record:{q['name']}:{rec}:{m}", 10 + n,
                            f"Hold {who} before {_fmt(rec)} — {q['name']} record date {_in(n)}")
        lapse = _date(q.get("lapse"))
        if lapse and q.get("bucket") == "approved":
            m = _milestone((lapse - today).days, LAPSE_WINDOW)
            if m is not None:
                n = (lapse - today).days
                yield Alert(f"lapse:{q['name']}:{lapse}:{m}", 100 + n,
                            f"{q['name']} ({who}): SEBI approval lapses {_fmt(lapse)}, {_in(n)}")


def _quota_stages(doc: dict):
    for q in _rows(doc, "quota"):
        who = f"{q.get('parent') or '?'} ({q.get('ticker') or '?'})"
        yield Alert(f"stage:{q['name']}:{q.get('bucket')}:{q.get('stage')}", 200,
                    f"{q['name']} — {who}: now {q.get('stage') or q.get('bucket')}")


def _board(doc: dict, today: dt.date):
    for b in _rows(doc, "mainboard"):
        o, c, ls = _date(b.get("open")), _date(b.get("close")), _date(b.get("listing"))
        band = f"₹{b['bandHigh']:g}" if isinstance(b.get("bandHigh"), (int, float)) else None
        sub = (b.get("sub") or {}).get("total") if isinstance(b.get("sub"), dict) else None
        gmp = b.get("gmpPct")
        facts = ", ".join(x for x in (band,
                                      f"book {sub:g}x" if isinstance(sub, (int, float)) else None,
                                      f"GMP {gmp:+.1f}%" if isinstance(gmp, (int, float)) else None) if x)
        tail = f" ({facts})" if facts else ""
        if isinstance(sub, (int, float)) and o and c and o <= today <= c:
            crossed = [x for x in SUB_MARKS if sub >= x]
            if crossed:                       # only the highest mark speaks; lower ones are keyed so they stay quiet
                yield Alert(f"sub:{b['name']}:{crossed[-1]}", 350,
                            f"{b['name']} book crossed {crossed[-1]}x — now {sub:g}x, closes {_fmt(c)}")
                for x in crossed[:-1]:
                    yield Alert(f"sub:{b['name']}:{x}", 999, "")
        if c and (c - today).days in (0, 1):
            n = (c - today).days
            yield Alert(f"close:{b['name']}:{c}:{n}", 300 + n, f"{b['name']} closes {_in(n)}{tail}")
        if o and (o - today).days in (0, 1):
            n = (o - today).days
            yield Alert(f"open:{b['name']}:{o}:{n}", 400 + n, f"{b['name']} opens {_in(n)}{tail}")
        if ls and ls == today:
            gain = b.get("listingGainPct")
            how = f" at {gain:+g}%" if isinstance(gain, (int, float)) else ""
            yield Alert(f"list:{b['name']}:{ls}", 500, f"{b['name']} lists today{how}")


def _investors(doc: dict, today: dt.date):
    inv = doc.get("investors") or {}
    watch = {str(w).lower() for w in (inv.get("watchlist") or []) if w}
    for d in inv.get("bulkDeals") or []:
        if isinstance(d, dict) and d.get("investor") and d.get("stock"):
            val = f" ₹{d['valueCr']:g} Cr" if isinstance(d.get("valueCr"), (int, float)) else ""
            yield Alert(f"deal:{d.get('date')}:{d['investor']}:{d['stock']}:{d.get('side')}", 600,
                        f"{d['investor']} {_SIDE.get(str(d.get('side')).upper(), 'traded')} {d['stock']}{val} ({d.get('date')})")
    live = {b["name"] for b in _rows(doc, "mainboard") + _rows(doc, "sme") if b.get("status") in ("Open", "Upcoming")}
    for a in _rows(doc, "anchors"):
        if a["name"] not in live:
            continue
        for i in a.get("investors") or []:
            nm = str((i or {}).get("name") or "")
            if nm and any(w in nm.lower() for w in watch):
                yield Alert(f"anchor:{a['name']}:{nm}", 650, f"{nm} is in the {a['name']} anchor book")


def _lockins(doc: dict, today: dt.date):
    """Anchor lock-in expiry: half the anchor shares become saleable 30 days after allotment, the rest after 90.
    Mainboard names only, one line, the day before (or on the day, if the day before was missed)."""
    main = {r["name"] for r in _rows(doc, "mainboard")} | {r["name"] for r in _rows(doc, "recent") if r.get("type") == "Mainboard"}
    for a in _rows(doc, "anchors"):
        if a["name"] not in main:
            continue
        for key, what in (("lockIn30", "half the anchor book"), ("lockIn90", "the rest of the anchor book")):
            d = _date(a.get(key))
            if d and (d - today).days in (0, 1):
                size = f" (₹{a['amountCr']:,.0f} Cr book)" if isinstance(a.get("amountCr"), (int, float)) else ""
                yield Alert(f"lockin:{a['name']}:{key}:{d}", 550, f"{a['name']}: lock-in on {what} ends {_in((d - today).days)}{size}")


REC_MIN_N, REC_MIN_POS = 5, 70     # an anchor "with a record": this many IPOs on file and this share listed up (stated in the line)


def _records(doc: dict, today: dt.date):
    """A strong-record anchor is in a book that has not listed yet. The record is the collector's (evidence.trackRecords):
    per investor, per segment, with n and its interval; the line carries them. Ranked above "opens tomorrow": it is the edge."""
    from .modules.anchorbook import investor_key
    rows = {r["key"]: r for r in ((doc.get("trackRecords") or {}).get("rows") or []) if isinstance(r, dict) and r.get("key")}
    if not rows:
        return
    books = ((doc.get("players") or {}).get("books") or {})
    letters = {a["name"]: [str((i or {}).get("name") or "") for i in a.get("investors") or []] for a in _rows(doc, "anchors")}
    for seg in ("mainboard", "sme"):
        for b in _rows(doc, seg):
            if b.get("status") not in ("Open", "Upcoming", "Closed"):
                continue
            names = set(letters.get(b["name"]) or []) | {str(x.get("name") or "") for x in (books.get(str(b.get("igId"))) or []) if isinstance(x, dict)}
            for nm in sorted(n for n in names if n):
                r = rows.get(investor_key(nm))
                s = r and r.get("sme" if seg == "sme" else "main")
                if not s or (s.get("n") or 0) < REC_MIN_N or (s.get("pos") or 0) < REC_MIN_POS:
                    continue
                yield Alert(f"rec:{b['name']}:{r['key']}", 380,
                            f"{r['name']} is in the {b['name']} book — {s['n']} {'SME' if seg == 'sme' else 'mainboard'} IPOs anchored, "
                            f"{s['pos']:.0f}% listed up ({s['lo']:.0f}–{s['hi']:.0f}%), median {s['med']:+g}%")


def _all(doc: dict, today: dt.date) -> dict[str, Alert]:
    out: dict[str, Alert] = {}
    for a in (*_quota_dates(doc, today), *_quota_stages(doc), *_board(doc, today), *_lockins(doc, today), *_records(doc, today),
              *_investors(doc, today)):
        out.setdefault(a.key, a)
    return out


# ---------------------------------------------------------------------------------------------
def evaluate(prev: dict, new: dict) -> list[Alert]:
    today = _day(new)
    if today is None:
        raise ValueError("new document has no meta.asOf")
    now = _all(new, today)
    before = _all(prev, _day(prev) or today) if prev else {}
    prev_quota = {q["name"] for q in _rows(prev, "quota")} if prev else set()
    prev_board = {b["name"] for b in _rows(prev, "mainboard")} if prev else set()
    fresh = []
    for key, a in now.items():
        if key in before or not a.line:
            continue
        if key.startswith("sub:") and key.split(":")[1] not in prev_board:
            continue                                       # first sighting is not a crossing
        if key.startswith("stage:"):
            name = key.split(":")[1]
            if not prev:                                   # no baseline: every stage would look new
                continue
            if name not in prev_quota:
                a = Alert(a.key, 150, "New quota IPO: " + a.line)
        fresh.append(a)
    return sorted(fresh, key=lambda a: (a.rank, a.line))


def compose(alerts: list[Alert], prev: dict, new: dict) -> str | None:
    """None = stay silent."""
    if not alerts:
        return None
    lines = [a.line for a in alerts]
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES - 1] + [f"+{len(alerts) - (MAX_LINES - 1)} more on the desk"]
    try:
        gap = (dt.datetime.fromisoformat(new["meta"]["asOf"]) - dt.datetime.fromisoformat(prev["meta"]["asOf"]))
        if gap.total_seconds() > GAP_HOURS * 3600:
            lines[0] = f"⚠ Refresh gap ({gap.total_seconds() / 3600:.0f}h) · " + lines[0]
    except (KeyError, TypeError, ValueError):
        pass
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate alert rules between two documents.")
    ap.add_argument("--prev", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--send", action="store_true", help="send via collector.notify (default: dry run, print only)")
    a = ap.parse_args(argv)
    prev_p = pathlib.Path(a.prev)
    prev = json.loads(prev_p.read_text(encoding="utf8")) if prev_p.exists() else {}
    new = json.loads(pathlib.Path(a.new).read_text(encoding="utf8"))
    alerts = evaluate(prev, new)
    text = compose(alerts, prev, new)
    if text is None:
        print("alerts: nothing new — silent")
        return 0
    print(f"alerts: {len(alerts)} new\n---\n{text}\n---")
    if not a.send:
        print("dry run — nothing sent (pass --send)")
        return 0
    from . import notify
    print("sent:", notify.send(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
