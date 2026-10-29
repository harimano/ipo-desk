"""The weekly digest — one message every Sunday at 18:30 IST that sums up the week on the desk.

Everything in it is read from documents the collector already wrote: the week's last document (`latest.json`, or
`history/<sunday>.json` for a past week) and the week's first (the previous Sunday's snapshot, else the earliest on
file that week) for the pipeline diff. It computes no statistics of its own: every rate quoted is the collector's
(`evidence.segments[x].bands`, with its n and Wilson interval), mainboard and SME never pooled. Evidence and both
sides, never a verdict — the scoring says what the GMP said, what band it sat in, and what the listing then did.

    python -m collector.digest --week 2026-10-26 --dry-run     # print the message, send nothing
    python -m collector.digest --week 2026-10-26 --send        # Telegram / ntfy, if configured (collector.notify)

`--week` is the Monday; the message covers Mon–Sun and next week's calendar. Sections, in order, each skipped when
empty: listings scored · next week's calendar · open now · pipeline moves · desk health (Hari only: `--no-health`
leaves it out when the message goes to a shared topic). Plain text with short lines, under MAX_LINES; ntfy gets
Markdown with a link on every name, Telegram HTML. The deep-link grammar is `alerts.link` (PR 10).
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
CAPS = {"listings": 8, "open": 8, "pipeline": 5, "health": 5}
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
_KIND = {"open": "opens", "close": "closes", "allotment": "allots", "listing": "lists", "record": "record date",
         "lockin30": "lock-in ends", "lockin90": "lock-in ends"}
_KIND_ORDER = ("open", "close", "allotment", "listing", "record", "lockin30", "lockin90")


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


def band_line(doc: dict, sme: bool, key: str, v: float | None, where: str) -> str | None:
    """The collector's band for value `v` of `key` (gmp | total) in segment `sme`, quoted with n and its interval:
    'GMP 10–30%: 91% listed up (76–97, n 32), median +17%'. None when there is no band or no cases in it."""
    ev = doc.get("evidence") or {}
    seg = (ev.get("segments") or {}).get("sme" if sme else "main")
    edges = _edges(doc, key)
    if not seg or not edges or not _num(v):
        return None
    i = _band_index(v, edges)
    bands = ((seg.get("bands") or {}).get(key) or {}).get(where) or []
    if i < 0 or i >= len(bands) or not (bands[i] or {}).get("n"):
        return None
    b = bands[i]
    what = "GMP " if key == "gmp" else "book "
    thin = " thin" if b["n"] < (ev.get("minN") or 30) else ""
    return (f"{what}{_edge_lbl(edges, i, '%' if key == 'gmp' else 'x')}: {b['pos']:.0f}% listed up "
            f"({b['lo']:.0f}–{b['hi']:.0f}, n {b['n']}{thin}), median {_pct(b['med'])}")


def _evidence_for(doc: dict, sme: bool, gmp_pct: float | None, total: float | None) -> str | None:
    """GMP band from the trailing window when a quote exists and is not zero, else the total-book band, all years."""
    if _num(gmp_pct) and gmp_pct != 0:
        s = band_line(doc, sme, "gmp", gmp_pct, "window")
        if s:
            return s
    return band_line(doc, sme, "total", total, "all")


# ---------------------------------------------------------------------------------------------
# the sections — each returns lines; a header is added only when there is something under it
# ---------------------------------------------------------------------------------------------
def listings(doc: dict, mon: dt.date, sun: dt.date) -> list[Line]:
    out: list[Line] = []
    for p in sorted(_rows(doc, "listedPerf"), key=lambda p: (str(p.get("date")), p["name"])):
        d = _date(p.get("date"))
        if not d or not (mon <= d <= sun) or not _num(p.get("issue")) or not p["issue"]:
            continue
        issue, sme = p["issue"], bool(p.get("sme"))
        if _num(p.get("gmpEve")):
            g, src = 100 * p["gmpEve"] / issue, "eve"
        elif _num(p.get("gmp")):
            g, src = 100 * p["gmp"] / issue, "listing morning"
        else:
            g, src = None, None
        bits = [f"{p['name']} ({_seg_lbl(sme)}, {_fmt(d)})"]
        bits.append(f"GMP {src} {_pct(g)}" if g is not None else "no GMP quote")
        ev = band_line(doc, sme, "gmp", g, "window") if g is not None else None
        if ev:
            bits.append(ev)
        if _num(p.get("listing")):
            op = 100 * (p["listing"] - issue) / issue
            s = f"opened {_pct(op)}"
            if _num(p.get("close1")):
                s += f", closed {_pct(100 * (p['close1'] - issue) / issue)}"
            bits.append(s)
        else:
            bits.append("listing print not on file")
        out.append(Line.item(" · ".join(bits), link("sheet", p["name"])))
    return out


def calendar(doc: dict, frm: dt.date, to: dt.date) -> list[Line]:
    """One line a day: opens · closes · allots · lists · record dates · lock-in expiries (mainboard named with the
    amount freed, SME counted). Refund days are left to the planner on the page."""
    events = [e for e in ((doc.get("calendar") or {}).get("events") or []) if isinstance(e, dict)
              and e.get("kind") in _KIND and e.get("name") and (dd := _date(e.get("date"))) and frm <= dd <= to]
    by_day: dict[dt.date, list[dict]] = {}
    for e in events:
        by_day.setdefault(_date(e["date"]), []).append(e)
    out: list[Line] = []
    for day in sorted(by_day):
        ln = Line.plain(f"{day:%a} {_fmt(day)}: ")
        first = True
        for kind in _KIND_ORDER:
            es = [e for e in by_day[day] if e["kind"] == kind]
            if not es:
                continue
            if kind.startswith("lockin"):
                named = [e for e in es if not e.get("sme")]
                folded = len(es) - len(named)
                if not named and folded:
                    ln.add(("" if first else " · ") + f"{folded} SME lock-in{'s' if folded > 1 else ''} end{'' if folded > 1 else 's'}", link("market"))
                    first = False
                    continue
                es = named
            ln.add(("" if first else " · ") + _KIND[kind] + " ")
            first = False
            for j, e in enumerate(sorted(es, key=lambda e: (bool(e.get("sme")), e["name"]))):
                nm = e["name"]
                tag = ""
                if kind == "record" and e.get("parent"):
                    tag = f" ({e['parent']})"
                elif kind.startswith("lockin") and _num(e.get("amountCr")):
                    tag = f" (₹{e['amountCr']:,.0f} Cr)"
                elif e.get("sme") and kind in ("open", "close", "listing"):
                    tag = " (SME)"
                where = "pipe" if kind == "record" else "board" if kind in ("open", "close", "allotment", "listing") else "market"
                if j:
                    ln.add(", ")
                ln.add(nm + tag, link(where, nm) if where != "market" else link("market"))
            if kind.startswith("lockin") and folded:
                ln.add(f" +{folded} SME", link("market"))
        out.append(ln)
    return out


def open_now(doc: dict) -> list[Line]:
    out: list[Line] = []
    for seg in ("mainboard", "sme"):
        sme = seg == "sme"
        for b in _rows(doc, seg):
            if b.get("status") not in ("Open", "Closed"):
                continue
            sub = b.get("sub") if isinstance(b.get("sub"), dict) else {}
            total, gmp = sub.get("total"), b.get("gmpPct")
            when = (f"closes {_fmt(_date(b['close']))}" if b["status"] == "Open" and _date(b.get("close"))
                    else f"closed, lists {_fmt(_date(b['listing']))}" if _date(b.get("listing")) else b["status"].lower())
            bits = [f"{b['name']} ({_seg_lbl(sme)}, {when})",
                    f"book {total:g}x" if _num(total) else "no book yet",
                    f"GMP {_pct(gmp)}" if _num(gmp) and gmp != 0 else "no GMP quote"]
            ev = _evidence_for(doc, sme, gmp, total)
            if ev:
                bits.append(ev)
            out.append(Line.item(" · ".join(bits), link("board", b["name"])))
    return out


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
                out.append(Line.item(f"New: {q['name']} ({who}) — {stage}", here))
            continue
        if (old.get("stage"), old.get("bucket")) != (q.get("stage"), q.get("bucket")):
            out.append(Line.item(f"{q['name']} ({who}): {old.get('stage') or old.get('bucket') or '?'} → {stage}", here))
        rec = _date(q.get("recordDate"))
        if rec and rec != _date(old.get("recordDate")):
            out.append(Line.item(f"{q['name']} ({who}): record date {_fmt(rec)}", here))
        lapse = _date(q.get("lapse"))
        if lapse and mon <= lapse <= sun and q.get("bucket") == "approved":
            out.append(Line.item(f"{q['name']} ({who}): SEBI approval lapsed {_fmt(lapse)}", here))
    was_x = {x["name"]: x for x in _rows(first, "expected")}
    for x in _rows(last, "expected"):
        old = was_x.get(x["name"])
        here = link("pipe", x["name"])
        if old is None:
            if was_x:
                out.append(Line.item(f"New on the pipeline: {x['name']} — {x.get('stage') or x.get('window') or '?'}", here))
            continue
        f, g = x.get("lastFiling") or {}, old.get("lastFiling") or {}
        if isinstance(f, dict) and f.get("date") and f.get("date") != (g.get("date") if isinstance(g, dict) else None):
            out.append(Line.item(f"{x['name']}: {f.get('register') or 'filing'} {_fmt(_date(f['date']))}", here))
    for ld in last.get("quotaLeads") or []:
        d = _date((ld or {}).get("date")) if isinstance(ld, dict) else None
        if d and mon <= d <= sun and ld.get("parentName"):
            out.append(Line.item(f"NSE lead {_fmt(d)}: {ld['parentName']} — {ld.get('kind') or 'offer'}", link("pipe")))
    return out


def health(doc: dict, snapshots: list[dt.date], mon: dt.date, sun: dt.date, now: dt.datetime) -> list[Line]:
    """Desk health from `integrity` (feeds not ok, feeds whose last good answer is old) and the history snapshots on
    file for the week (one a day is written by every full run). "Wrong number?" reports live in D1, which only the
    Worker reads: the collector cannot count them, so the line sends the reader to /admin."""
    out: list[Line] = []
    days = [mon + dt.timedelta(days=i) for i in range((min(sun, now.date()) - mon).days + 1)]
    missed = [d for d in days if d not in set(snapshots)]
    if missed:
        out.append(Line.item(f"Runs missed: no snapshot on {', '.join(_fmt(d) for d in missed)} ({len(missed)} of {len(days)} days)",
                             link("admin")))
    else:
        out.append(Line.item(f"Runs: a snapshot every day, {len(days)} of {len(days)}", link("admin")))
    for c in ((doc.get("integrity") or {}).get("checks") or []):
        if not isinstance(c, dict) or c.get("area") in ("run", "research layer"):
            continue
        last_ok = None
        try:
            last_ok = dt.datetime.fromisoformat(str(c.get("lastOk")))
        except (TypeError, ValueError):
            pass
        if c.get("status") != "ok":
            since = f"since {_fmt(last_ok.date())}" if last_ok else "no good answer on file"
            out.append(Line.item(f"{c['area']}: {c.get('status')} — {str(c.get('note') or '')[:60]} ({since})", link("admin")))
        elif last_ok and (now - last_ok.astimezone(now.tzinfo)).total_seconds() > STALE_HOURS * 3600:
            age = (now - last_ok.astimezone(now.tzinfo)).total_seconds() / 86400
            out.append(Line.item(f"{c['area']}: ok but stale, last good answer {age:.0f} days ago", link("admin")))
    out.append(Line.item("Wrong number? reports: counted on /admin (D1 is the Worker's, the collector cannot read it)", link("admin")))
    return out


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
    out = [Line.item(f"IPO desk · week of {_fmt(mon)} – {_fmt(sun)}", link("today"))]
    sections = [
        ("This week's listings, scored", _cap(listings(last, mon, sun), CAPS["listings"], link("score"))),
        ("Next week", calendar(last, sun + dt.timedelta(days=1), sun + dt.timedelta(days=7))),
        ("Open now", _cap(open_now(last), CAPS["open"], link("board"))),
        ("Pipeline moves this week", _cap(pipeline(first, last, mon, sun), CAPS["pipeline"], link("pipe"))),
    ]
    if personal:
        sections.append(("Desk health (for Hari)", _cap(health(last, snapshots or [], mon, sun, now), CAPS["health"], link("admin"))))
    for title, lines in sections:
        if lines:
            out.append(Line.plain(title))
            out.extend(lines)
    return out


def message(lines: list[Line]) -> Message:
    """The same lines three ways (alerts.Message): plain text, ntfy Markdown (`Markdown: yes`, a link per name),
    Telegram HTML. Blank lines separate the sections so notify.chunk can split a long one cleanly."""
    text, md, html = [], [], []
    for ln in lines:
        header = len(ln.pieces) == 1 and ln.pieces[0][1] is None
        if header and text:
            text.append("")
            md.append("")
            html.append("")
        text.append(ln.text)
        md.append("".join(f"[{_md(t)}]({u})" if u else _md(t) for t, u in ln.pieces) if not header else f"**{_md(ln.text)}**")
        html.append("".join(f'<a href="{_html(u)}">{_html(t)}</a>' if u else _html(t) for t, u in ln.pieces)
                    if not header else f"<b>{_html(ln.text)}</b>")
    # Markdown needs a blank line between lines or ntfy runs them into one paragraph; HTML keeps the plain layout.
    return Message(text="\n".join(text), markdown="\n\n".join(x for x in md if x != ""),
                   html="\n".join(html), click=next((ln.url for ln in lines if ln.url), link("today")))


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
    print("sent:", notify.send(msg.text, html=msg.html, markdown=msg.markdown, click=msg.click))
    return 0


if __name__ == "__main__":
    sys.exit(main())
