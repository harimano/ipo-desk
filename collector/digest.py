"""The weekly digest — one message every Sunday at 18:30 IST that sums up the week on the desk.

Everything in it is read from documents the collector already wrote: the week's last document (`latest.json`, or
`history/<sunday>.json` for a past week) and the week's first (the previous Sunday's snapshot, else the earliest on
file that week) for the pipeline diff. It computes no statistics of its own: every rate quoted is the collector's
(`evidence.segments[x].bands`, with its n and Wilson interval), mainboard and SME never pooled. Evidence and both
sides, never a verdict — the scoring says what the GMP said, what band it sat in, and what the listing then did.

    python -m collector.digest --week 2026-10-26 --dry-run     # print the message, send nothing
    python -m collector.digest --week 2026-10-26 --send        # Telegram / ntfy, if configured (collector.notify)

`--week` is the Monday; the message covers Mon–Sun and next week's calendar. Sections, in order, each skipped when
empty: listings scored · next week's calendar (opens, closes, listings; mainboard by name, SME counted) · open now ·
what the record says (the bands those issues sit in, each stated once with n and interval) · pipeline moves · desk
health (Hari only: `--no-health` leaves it out when the message goes to a shared topic). One fact set a line, under
MAX_LINES; ntfy gets the plain text with Click and three action buttons (an iPhone renders no Markdown), Telegram HTML
with a link on every name. The deep-link grammar is `alerts.link` (PR 10).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from dataclasses import dataclass, field

from .alerts import Message, _html, _md, link

MAX_LINES = 40
STALE_HOURS = 36                 # a feed whose last good answer is older than this is "stale" in the health line
CAPS = {"listings": 6, "open": 5, "pipeline": 5}
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


@dataclass
class Line:
    """One line of the message: text pieces, each with the link it lands on (None = plain text)."""
    pieces: list[tuple[str, str | None]] = field(default_factory=list)

    @classmethod
    def plain(cls, text: str) -> Line:
        return cls([(text, None)])

    @classmethod
    def item(cls, text: str, url: str) -> Line:
        return cls([(text, url)])

    def add(self, text: str, url: str | None = None) -> Line:
        self.pieces.append((text, url))
        return self

    @property
    def text(self) -> str:
        return "".join(t for t, _ in self.pieces)

    @property
    def url(self) -> str | None:
        return next((u for _, u in self.pieces if u), None)


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _fmt(d: dt.date) -> str:
    return f"{d.day} {d:%b}"


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pct(v: float) -> str:
    return f"{v:+.0f}%"


def _rows(doc: dict, key: str) -> list[dict]:
    return [r for r in (doc.get(key) or []) if isinstance(r, dict) and r.get("name")]


def _seg_lbl(sme: bool) -> str:
    return "SME" if sme else "MB"


def _edges(doc: dict, key: str) -> list[float] | None:
    e = ((doc.get("evidence") or {}).get("edges") or {}).get(key)
    if not e:
        return None
    return [float("-inf") if x is None and i == 0 else float("inf") if x is None else x for i, x in enumerate(e)]


def _band_index(v: float, edges: list[float]) -> int:
    for i in range(len(edges) - 1):
        if edges[i] <= v < edges[i + 1]:
            return i
    return -1


def _edge_lbl(edges: list[float], i: int, unit: str) -> str:
    lo, hi = edges[i], edges[i + 1]
    if lo == float("-inf"):
        return "zero or below"
    if lo == 0 and unit == "x":
        return f"under {hi:g}x"
    if hi == float("inf"):
        return f"over {lo:g}{unit}"
    return f"{0 if lo == 0.01 else lo:g}–{hi:g}{unit}"      # the gmp edge 0.01 means "any positive quote"


# ---------------------------------------------------------------------------------------------
# the sections — each returns lines; a header is added only when there is something under it. One fact set a line:
# the evidence a line would carry is noted as a band key and stated ONCE, in the record block, with n and interval.
# ---------------------------------------------------------------------------------------------
Bands = set  # of (sme, key, index)


def _book(total) -> str:
    return f"book {total:.1f}x" if total < 10 else f"book {total:.0f}x"


def _band_of(doc: dict, sme: bool, gmp_pct, total) -> tuple[bool, str, int] | None:
    """Which band a row's evidence is: the GMP band (trailing window) when a quote exists and is not zero, else the
    total-book band (all years). None when the collector has no band for it."""
    if _num(gmp_pct) and gmp_pct != 0 and (e := _edges(doc, "gmp")) and (i := _band_index(gmp_pct, e)) >= 0:
        return (sme, "gmp", i)
    if _num(total) and (e := _edges(doc, "total")) and (i := _band_index(total, e)) >= 0:
        return (sme, "total", i)
    return None


def listings(doc: dict, mon: dt.date, sun: dt.date, bands: Bands) -> list[Line]:
    out: list[Line] = []
    for p in sorted(_rows(doc, "listedPerf"), key=lambda p: (str(p.get("date")), p["name"])):
        d = _date(p.get("date"))
        if not d or not (mon <= d <= sun) or not _num(p.get("issue")) or not p["issue"]:
            continue
        issue, sme = p["issue"], bool(p.get("sme"))
        if _num(p.get("gmpEve")):
            said = f"GMP said {_pct(100 * p['gmpEve'] / issue)}"
            g = 100 * p["gmpEve"] / issue
        elif _num(p.get("gmp")):
            g = 100 * p["gmp"] / issue
            said = f"GMP said {_pct(g)} (listing morning)"
        else:
            g, said = None, "no GMP quote"
        if g is not None and (b := _band_of(doc, sme, g, None)):
            bands.add(b)
        if _num(p.get("listing")):
            did = f"opened {_pct(100 * (p['listing'] - issue) / issue)}"
            if _num(p.get("close1")):
                did += f", closed {_pct(100 * (p['close1'] - issue) / issue)}"
        else:
            did = "listing print not on file"
        out.append(Line.item(p["name"] + (" (SME)" if sme else ""), link("sheet", p["name"])).add(f" · {said} · {did}"))
    return out


_VERB = {"listing": ("lists", "list"), "open": ("opens", "open"), "close": ("closes", "close")}


def calendar(doc: dict, frm: dt.date, to: dt.date) -> list[Line]:
    """One line a day, opens / closes / listings only (allotments, refunds and lock-ins stay on the page's planner):
    mainboard by name, SME as a count that lands on the board."""
    by_day: dict[dt.date, list[dict]] = {}
    for e in ((doc.get("calendar") or {}).get("events") or []):
        if isinstance(e, dict) and e.get("kind") in _VERB and e.get("name") and (dd := _date(e.get("date"))) and frm <= dd <= to:
            by_day.setdefault(dd, []).append(e)
    out: list[Line] = []
    for day in sorted(by_day):
        ln = Line.plain(f"{day:%a} {day.day}")
        for kind in ("listing", "open", "close"):
            es = [e for e in by_day[day] if e["kind"] == kind]
            main = sorted(e["name"] for e in es if not e.get("sme"))
            n_sme = len(es) - len(main)
            if main:
                ln.add(" · ")
                for j, nm in enumerate(main):
                    if j:
                        ln.add(", ")
                    ln.add(nm, link("board", nm))
                ln.add(" " + _VERB[kind][len(main) > 1])
            if n_sme:
                ln.add(" · ").add(f"{n_sme} SME {_VERB[kind][n_sme > 1]}", link("board"))
        out.append(ln)
    return out


def open_now(doc: dict, bands: Bands) -> list[Line]:
    out: list[Line] = []
    for b in _rows(doc, "mainboard"):
        if b.get("status") not in ("Open", "Closed"):
            continue
        sub = b.get("sub") if isinstance(b.get("sub"), dict) else {}
        total, gmp = sub.get("total"), b.get("gmpPct")
        when = (f"closes {_fmt(_date(b['close']))}" if b["status"] == "Open" and _date(b.get("close"))
                else f"closed, lists {_fmt(_date(b['listing']))}" if _date(b.get("listing")) else b["status"].lower())
        bits = [when, _book(total) if _num(total) else "no book yet",
                f"GMP {_pct(gmp)}" if _num(gmp) and gmp != 0 else "no GMP quote"]
        if bd := _band_of(doc, False, gmp, total):
            bands.add(bd)
        out.append(Line.item(b["name"], link("board", b["name"])).add(" · " + " · ".join(bits)))
    sme = [b for b in _rows(doc, "sme") if b.get("status") in ("Open", "Closed")]
    if sme:
        quiet = sum(1 for b in sme if not (_num(b.get("gmpPct")) and b["gmpPct"] != 0))
        ln = Line.item(f"{len(sme)} SME on the board", link("board"))
        if quiet:
            ln.add(f", {quiet} with no GMP quote")
        out = out[:CAPS["open"]] + ([Line.item(f"+{len(out) - CAPS['open']} more mainboard", link("board"))] if len(out) > CAPS["open"] else []) + [ln]
    return out


def record(doc: dict, bands: Bands) -> list[Line]:
    """The collector's bands the week's issues sit in, each stated once with n and its Wilson interval; mainboard and
    SME under their own header, never pooled."""
    ev = doc.get("evidence") or {}
    out: list[Line] = []
    for sme in (False, True):
        seg = (ev.get("segments") or {}).get("sme" if sme else "main") or {}
        rows: list[Line] = []
        for (s, key, i) in sorted(bands, key=lambda b: (b[1], b[2])):
            if s != sme:
                continue
            where = "window" if key == "gmp" else "all"
            edges = _edges(doc, key) or []
            arr = ((seg.get("bands") or {}).get(key) or {}).get(where) or []
            if i >= len(arr) or not (arr[i] or {}).get("n"):
                continue
            b = arr[i]
            thin = ", thin" if b["n"] < (ev.get("minN") or 30) else ""
            lbl = ("GMP " if key == "gmp" else "book ") + _edge_lbl(edges, i, "%" if key == "gmp" else "x")
            rows.append(Line.item(lbl, link("score")).add(
                f": {b['pos']:.0f}% listed up ({b['lo']:.0f}–{b['hi']:.0f}%, {b['n']} cases{thin}), median {_pct(b['med'])}"))
        if rows:
            win = (seg.get("window") or {}).get("rule") or "trailing window"
            book = any(b[0] == sme and b[1] == "total" for b in bands)
            out.append(Line.plain(f"WHAT THE RECORD SAYS · {'SME' if sme else 'mainboard'}, {win}"
                                  + (" (book bands: all years)" if book else "")))
            out.extend(rows)
    return out


def _short(name: str) -> str:
    """A filing's auto row name, for display only ('INTELLIUS RECODE LIMITED - Notice to Investors' → 'Intellius Recode');
    the link keeps the full name, which is the key."""
    n = name.split(" - ")[0].strip()
    if n.isupper():
        n = n.title()
    return n.removesuffix(" Limited").removesuffix(" Ltd").strip()


def pipeline(first: dict, last: dict, mon: dt.date, sun: dt.date) -> list[Line]:
    """What changed between the week's first and last documents: quota rows new or moved stage, record dates set,
    approvals lapsed; expected rows new or with a fresh filing; NSE leads dated in the week."""
    out: list[Line] = []
    was = {q["name"]: q for q in _rows(first, "quota")}
    for q in _rows(last, "quota"):
        who = q.get("parent") or q.get("parentFull") or "?"
        stage = q.get("stage") or q.get("bucket") or "?"
        here = link("pipe", q["name"])
        old = was.get(q["name"])
        if old is None:
            if was:
                out.append(Line.plain("New: ").add(q["name"], here).add(f" ({who}) · {stage}"))
            continue
        if (old.get("stage"), old.get("bucket")) != (q.get("stage"), q.get("bucket")):
            out.append(Line.item(q["name"], here).add(f" ({who}) · {old.get('stage') or old.get('bucket') or '?'} → {stage}"))
        rec = _date(q.get("recordDate"))
        if rec and rec != _date(old.get("recordDate")):
            out.append(Line.item(q["name"], here).add(f" ({who}) · record date {_fmt(rec)}"))
        lapse = _date(q.get("lapse"))
        if lapse and mon <= lapse <= sun and q.get("bucket") == "approved":
            out.append(Line.item(q["name"], here).add(f" ({who}) · SEBI approval lapsed {_fmt(lapse)}"))
    was_x = {x["name"]: x for x in _rows(first, "expected")}
    for x in _rows(last, "expected"):
        old = was_x.get(x["name"])
        here = link("pipe", x["name"])
        if old is None:
            if was_x:
                out.append(Line.plain("New: ").add(_short(x["name"]), here).add(f" · {x.get('stage') or x.get('window') or '?'}"))
            continue
        f, g = x.get("lastFiling") or {}, old.get("lastFiling") or {}
        if isinstance(f, dict) and f.get("date") and f.get("date") != (g.get("date") if isinstance(g, dict) else None):
            out.append(Line.item(_short(x["name"]), here).add(f" · {f.get('register') or 'filing'} {_fmt(_date(f['date']))}"))
    for ld in last.get("quotaLeads") or []:
        d = _date((ld or {}).get("date")) if isinstance(ld, dict) else None
        if d and mon <= d <= sun and ld.get("parentName"):
            out.append(Line.item(f"NSE lead {_fmt(d)}: {_short(ld['parentName'])}", link("pipe")).add(f" · {ld.get('kind') or 'offer'}"))
    return out


def health(doc: dict, snapshots: list[dt.date], mon: dt.date, sun: dt.date, now: dt.datetime) -> list[Line]:
    """Two lines from `integrity` and the week's snapshots on file (one a day from every full run): days with no
    snapshot, feeds not ok, feeds whose last good answer is old. "Wrong number?" reports live in D1, which only the
    Worker reads: the collector cannot count them, so the second line sends the reader to /admin."""
    days = [mon + dt.timedelta(days=i) for i in range((min(sun, now.date()) - mon).days + 1)]
    have = sum(1 for d in days if d in set(snapshots))
    ln = Line.item(f"Snapshots {have} of {len(days)} days", link("admin"))
    for c in ((doc.get("integrity") or {}).get("checks") or []):
        if not isinstance(c, dict) or c.get("area") in ("run", "research layer"):
            continue
        try:
            last_ok = dt.datetime.fromisoformat(str(c.get("lastOk"))).astimezone(now.tzinfo)
        except (TypeError, ValueError):
            last_ok = None
        if c.get("status") != "ok":
            why = str(c.get("note") or "").split("—")[-1].strip()[:40]
            ln.add(f" · {c['area']} feed {c.get('status')}" + (f" ({why})" if why else ""))
        elif last_ok and (now - last_ok).total_seconds() > STALE_HOURS * 3600:
            ln.add(f" · {c['area']} stale {(now - last_ok).days} days")
    return [ln, Line.item("Wrong number? reports: on /admin", link("admin")).add(" (D1 is the Worker's; the collector cannot count them)")]


# ---------------------------------------------------------------------------------------------
def _cap(lines: list[Line], n: int, more_url: str) -> list[Line]:
    if len(lines) <= n:
        return lines
    return lines[:n - 1] + [Line.item(f"+{len(lines) - (n - 1)} more on the desk", more_url)]


def build(first: dict, last: dict, mon: dt.date, *, snapshots: list[dt.date] | None = None, personal: bool = True,
          now: dt.datetime | None = None) -> list[Line]:
    """The digest's lines for the week starting `mon`, from the week's first and last documents."""
    sun = mon + dt.timedelta(days=6)
    now = now or dt.datetime.now(IST)
    bands: Bands = set()
    out = [Line.item(f"IPO desk · {_fmt(mon)} – {_fmt(sun)}", link("today"))]
    sections = [
        ("LISTED THIS WEEK", _cap(listings(last, mon, sun, bands), CAPS["listings"], link("score"))),
        ("NEXT WEEK", calendar(last, sun + dt.timedelta(days=1), sun + dt.timedelta(days=7))),
        ("OPEN NOW", open_now(last, bands)),
        (None, record(last, bands)),
        ("PIPELINE", _cap(pipeline(first, last, mon, sun), CAPS["pipeline"], link("pipe"))),
    ]
    if personal:
        sections.append(("DESK HEALTH", health(last, snapshots or [], mon, sun, now)))
    for title, lines in sections:
        if lines:
            if title:
                out.append(Line.plain(title))
            out.extend(lines)
    return out


def message(lines: list[Line]) -> Message:
    """The same lines three ways (alerts.Message): plain text (what ntfy gets, with Today / Board / Score buttons — an
    iPhone shows Markdown raw), Markdown (a link per name, built for Android / web readers, not sent today), Telegram
    HTML. A header is a plain upper-case line."""
    text, md, html = [], [], []
    for ln in lines:
        header = len(ln.pieces) == 1 and ln.pieces[0][1] is None
        if header and text:
            text.append("")
            html.append("")
        text.append(ln.text)
        md.append(f"**{_md(ln.text)}**" if header else "".join(f"[{_md(t)}]({u})" if u else _md(t) for t, u in ln.pieces))
        html.append(f"<b>{_html(ln.text)}</b>" if header
                    else "".join(f'<a href="{_html(u)}">{_html(t)}</a>' if u else _html(t) for t, u in ln.pieces))
    return Message(text="\n".join(text), markdown="\n\n".join(md), html="\n".join(html),
                   click=next((ln.url for ln in lines if ln.url), link("today")),
                   actions=(("Today", link("today")), ("Board", link("board")), ("Score", link("score"))))


# ---------------------------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------------------------
def monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf8"))


def load_week(data: pathlib.Path, mon: dt.date) -> tuple[dict, dict, list[dt.date]]:
    """(first, last, snapshot days): `last` is history/<sunday>.json when on file, else latest.json; `first` is the
    previous Sunday's snapshot, else the earliest snapshot of the week, else `last` itself (no diff)."""
    sun = mon + dt.timedelta(days=6)
    hist = data / "history"
    days = sorted(d for f in hist.glob("*.json") if (d := _date(f.stem))) if hist.is_dir() else []
    last_p = hist / f"{sun}.json"
    if not last_p.exists():
        last_p = data / "latest.json"
    last = _load(last_p)
    firsts = [d for d in days if d == mon - dt.timedelta(days=1)] or [d for d in days if mon <= d <= sun]
    first = _load(hist / f"{firsts[0]}.json") if firsts else last
    return first, last, [d for d in days if mon <= d <= sun]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The weekly digest, from the documents the collector wrote this week.")
    ap.add_argument("--data", default="data", help="data directory with latest.json and history/ (default ./data)")
    ap.add_argument("--week", help="the week's Monday, YYYY-MM-DD (default: this week, IST)")
    ap.add_argument("--dry-run", action="store_true", help="print the message, send nothing (the default)")
    ap.add_argument("--send", action="store_true", help="send via collector.notify (Telegram / ntfy, if configured)")
    ap.add_argument("--no-health", action="store_true", help="leave out the desk-health section (a shared topic)")
    a = ap.parse_args(argv)
    now = dt.datetime.now(IST)
    mon = _date(a.week) if a.week else monday_of(now.date())
    if mon is None or mon.weekday() != 0:
        print(f"--week must be a Monday, got {a.week}", file=sys.stderr)
        return 2
    first, last, snaps = load_week(pathlib.Path(a.data), mon)
    lines = build(first, last, mon, snapshots=snaps, personal=not a.no_health, now=now)
    msg = message(lines)
    n = len(msg.text.splitlines())
    print(f"digest: {n} lines, first doc {(first.get('meta') or {}).get('asOf')}, last doc {(last.get('meta') or {}).get('asOf')}"
          f"\n---\n{msg.text}\n---\nclick: {msg.click}")
    if n > MAX_LINES:
        print(f"warning: {n} lines is over MAX_LINES={MAX_LINES}", file=sys.stderr)
    if not a.send:
        print("dry run — nothing sent (pass --send)")
        return 0
    from . import notify
    print("sent:", notify.send(msg.text, html=msg.html, click=msg.click, actions=msg.actions))   # plain text to ntfy: iPhone
    return 0


if __name__ == "__main__":
    sys.exit(main())
