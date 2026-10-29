#!/usr/bin/env python3
"""The admin audit: one JSON of facts about the document for the /admin page to render.

  python3 scripts/audit.py                                   # data/latest.json vs the newest earlier data/history/*.json
  python3 scripts/audit.py data/latest.json --prev <path> --out _site/admin/audit.json

site/build.py calls build() for every build, so the page and its audit are always from the same document. Nothing
here decides whether the run was good: it lists what is fresh, what fell back, what moved since yesterday and what
looks odd, each with the rows behind it, and the page shows time-since against the viewer's clock. The verdict line
at the top of the page is this file's `verdict` — an ops call, not a market one (rule 3 is about IPOs, not runners).

Levels: "ok" nothing to do · "warn" worth a look · "bad" something is wrong · "known" a gap CLAUDE.md already lists.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector import layout

BOARDS = ("mainboard", "sme")
KNOWN_BLOCKED = {"offers": "api.bseindia.com answers 403 to GitHub's runners (CLAUDE.md known gaps)"}
FALLBACK_WORDS = ("down", "blocked", "changed", "fallback")
MAX_DOC_BYTES = 6 * 1024 * 1024          # scripts/validate.py MAX_DOC_BYTES
LISTED_GRACE_DAYS = 1                    # collector/modules/calendar.py: a Listed row leaves the board the day after listing
COUNT_KEYS = ("mainboard", "sme", "recent", "expected", "offers", "quota", "anchors", "listedPerf", "priceHistory",
              "quotaLeads", "anchorBooks", "logos")


def _date(v) -> dt.date | None:
    if not isinstance(v, str) or len(v) < 10:
        return None
    try:
        return dt.date.fromisoformat(v[:10])
    except ValueError:
        return None


def _iso(v) -> str | None:
    """A timestamp the browser can parse, or None. Module asOf values are mixed: ISO, a bare date, or a source's own
    stamp like '9-Oct 9:37' (gmp) that nobody should compute an age from."""
    if not isinstance(v, str):
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(T.*)?", v):
        return v
    return None


def _rows(doc: dict) -> list[tuple[str, dict]]:
    return [(b, r) for b in BOARDS for r in (doc.get(b) or []) if isinstance(r, dict)]


def _key(r: dict) -> str:
    return str(r.get("igId") or r.get("name"))


def _size(v) -> int:
    if isinstance(v, (list, dict)):
        return len(v)
    return 1 if v not in (None, "", 0) else 0


# ---------------------------------------------------------------- modules
def modules(doc: dict) -> list[dict]:
    out = []
    for c in (doc.get("integrity") or {}).get("checks") or []:
        area, status, method = c.get("area", "?"), c.get("status", "?"), c.get("method") or ""
        level = "ok"
        if status != "ok":
            level = "known" if area in KNOWN_BLOCKED else ("bad" if status in ("fail", "error", "down") else "warn")
        elif any(w in method for w in FALLBACK_WORDS):
            level = "warn"                                   # it answered, but not from its first source
        out.append({"area": area, "status": status, "method": method, "level": level, "asOf": _iso(c.get("asOf")),
                    "asOfRaw": c.get("asOf"), "elapsed": c.get("elapsed"), "calls": c.get("calls"),
                    "note": c.get("note") or "", "known": KNOWN_BLOCKED.get(area)})
    return out


# ---------------------------------------------------------------- anomalies
def anomalies(doc: dict, logos_dir: pathlib.Path | None = None) -> list[dict]:
    today = _date((doc.get("meta") or {}).get("asOf")) or dt.date.today()
    finds: dict[str, list[str]] = {}

    def add(check, name):
        finds.setdefault(check, []).append(name)

    seen: dict[str, str] = {}
    logos = doc.get("logos") or {}
    for board, r in _rows(doc):
        name, st = r.get("name") or "?", r.get("status")
        o, c, li = _date(r.get("open")), _date(r.get("close")), _date(r.get("listing"))
        label = f"{name} ({board})"
        if name in seen and seen[name] != board:
            add("same name on both boards", name)
        seen[name] = board
        if not r.get("igId"):
            add("row without an InvestorGain id", label)
        if o and c and o > c:
            add("opens after it closes", f"{label} {o} > {c}")
        if c and li and c > li:
            add("closes after it lists", f"{label} {c} > {li}")
        if st == "Open" and c and c < today:
            add("still Open past its close date", f"{label} closed {c}")
        if st == "Upcoming" and o and o < today:
            add("still Upcoming past its open date", f"{label} opened {o}")
        if st == "Closed" and li and li < today:
            add("Closed past its listing date", f"{label} listed {li}")
        if st == "Listed" and r.get("listingPrice") in (None, 0, ""):
            add("Listed with no listing price", label)
        if st == "Open":
            if r.get("gmp") is None:
                add("Open with no GMP quote", label)
            sub = r.get("sub") or {}
            if o and o < today and not sub.get("total"):
                add("Open since yesterday with an empty book", label)
        if st in ("Open", "Closed") and not r.get("lotSize"):
            add("no lot size", label)
        lg = r.get("logo")
        ig = str(r.get("igId") or "")
        if lg and ig and ig not in logos:
            add("logo named but not collected", label)
        if ig in logos and logos[ig].get("missing"):
            add("logo missing at the source", label)
        if logos_dir and ig in logos and not logos[ig].get("missing") and not (logos_dir / f"{ig}.webp").exists():
            add("logo listed but file absent", label)
    return [{"check": k, "level": "bad" if k in BAD_CHECKS else "warn", "rows": v} for k, v in finds.items()]


BAD_CHECKS = {"opens after it closes", "closes after it lists", "still Open past its close date",
              "still Upcoming past its open date", "same name on both boards", "logo listed but file absent"}


# ---------------------------------------------------------------- diff vs the previous document
def diff(doc: dict, prev: dict | None) -> dict:
    if not prev:
        return {"prevAsOf": None}
    today = _date((doc.get("meta") or {}).get("asOf")) or dt.date.today()
    out: dict = {"prevAsOf": (prev.get("meta") or {}).get("asOf"), "boards": {}, "statusMoves": [],
                 "sourceSwitches": [], "warnings": {}, "counts": {}}
    for b in BOARDS:
        new = {_key(r): r for r in doc.get(b) or [] if isinstance(r, dict)}
        old = {_key(r): r for r in prev.get(b) or [] if isinstance(r, dict)}
        added = [new[k]["name"] for k in new if k not in old]
        retired, vanished = [], []
        for k, r in old.items():
            if k in new:
                continue
            li = _date(r.get("listing"))
            if r.get("status") == "Listed" and li and li + dt.timedelta(days=LISTED_GRACE_DAYS) <= today:
                retired.append(r.get("name"))
            else:
                vanished.append(r.get("name"))
        out["boards"][b] = {"prev": len(old), "now": len(new), "added": added, "retired": retired,
                            "vanished": vanished}
        for k, r in new.items():
            if k in old and old[k].get("status") != r.get("status"):
                out["statusMoves"].append({"name": r.get("name"), "board": b, "from": old[k].get("status"),
                                           "to": r.get("status")})
    oldm = {c.get("area"): c for c in (prev.get("integrity") or {}).get("checks") or []}
    for c in (doc.get("integrity") or {}).get("checks") or []:
        o = oldm.get(c.get("area"))
        if o and (o.get("method") != c.get("method") or o.get("status") != c.get("status")):
            out["sourceSwitches"].append({"area": c.get("area"), "from": f"{o.get('method')} ({o.get('status')})",
                                          "to": f"{c.get('method')} ({c.get('status')})"})
    ow = {w.get("code") for w in (prev.get("evidence") or {}).get("warnings") or []}
    nw = {w.get("code") for w in (doc.get("evidence") or {}).get("warnings") or []}
    out["warnings"] = {"added": sorted(nw - ow), "removed": sorted(ow - nw)}
    for k in COUNT_KEYS:
        a, b_ = _size(prev.get(k)), _size(doc.get(k))
        if a or b_:
            out["counts"][k] = [a, b_]
    return out


# ---------------------------------------------------------------- the verdict line
def verdict(mods: list[dict], finds: list[dict], d: dict, size: int) -> dict:
    items = []
    for m in mods:
        if m["level"] == "bad":
            items.append({"level": "bad", "text": f"{m['area']} failed: {m['method'] or m['status']}", "where": "modules"})
        elif m["level"] == "warn":
            items.append({"level": "warn", "text": f"{m['area']} on a fallback: {m['method']}", "where": "modules"})
    for f in finds:
        n = len(f["rows"])
        items.append({"level": f["level"], "text": f"{n} row{'s' if n > 1 else ''} {f['check']}", "where": "audit"})
    for b, v in (d.get("boards") or {}).items():
        if v["vanished"]:
            items.append({"level": "bad", "text": f"{b}: {len(v['vanished'])} row(s) left the board early", "where": "diff"})
    for s in d.get("sourceSwitches") or []:
        items.append({"level": "warn", "text": f"{s['area']} switched source: {s['to']}", "where": "diff"})
    if size > 0.8 * MAX_DOC_BYTES:
        items.append({"level": "warn", "text": f"document at {size / MAX_DOC_BYTES:.0%} of the size cap", "where": "size"})
    level = "bad" if any(i["level"] == "bad" for i in items) else "warn" if items else "ok"
    return {"level": level, "items": items}


# ---------------------------------------------------------------- assembly
def build(doc: dict, prev: dict | None = None, logos_dir: pathlib.Path | None = None) -> dict:
    size = sum(len(b) for b in layout.split(doc).values())
    mods, finds, d = modules(doc), anomalies(doc, logos_dir), diff(doc, prev)
    meta = doc.get("meta") or {}
    counts = {b: {} for b in BOARDS}
    for b, r in _rows(doc):
        counts[b][r.get("status") or "?"] = counts[b].get(r.get("status") or "?", 0) + 1
    return {
        "generated": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds"),
        "doc": {"asOf": meta.get("asOf"), "label": meta.get("label"), "bytesCompact": size, "capBytes": MAX_DOC_BYTES,
                "integrityAsOf": (doc.get("integrity") or {}).get("asOf"), "tapeAsOf": (doc.get("tape") or {}).get("asOf"),
                "tapeLastDay": max((doc.get("tape") or {}).get("dates") or [None]) if isinstance((doc.get("tape") or {}).get("dates"), list) else None,
                "boards": counts},
        "verdict": verdict(mods, finds, d, size),
        "modules": mods,
        "audit": finds,
        "diff": d,
        "warnings": (doc.get("evidence") or {}).get("warnings") or [],
        "unresolved": meta.get("unresolved") or [],
        "awaiting": meta.get("awaitingData") or [],
        "discrepancies": (doc.get("integrity") or {}).get("discrepancies") or [],
    }


def previous(doc: dict, history: pathlib.Path) -> dict | None:
    """The newest history file written before this document (today's evening file may already be the document itself)."""
    as_of = (doc.get("meta") or {}).get("asOf") or ""
    for f in sorted(history.glob("????-??-??.json"), reverse=True):
        try:
            h = json.loads(f.read_text(encoding="utf8"))
        except Exception as e:
            print(f"audit: skipping {f.name}: {e}", file=sys.stderr)
            continue
        if ((h.get("meta") or {}).get("asOf") or "") < as_of:
            return h
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc", nargs="?", default=str(ROOT / "data" / "latest.json"))
    ap.add_argument("--prev")
    ap.add_argument("--history", default=str(ROOT / "data" / "history"))
    ap.add_argument("--logos", default=str(ROOT / "data" / "logos"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    doc = json.loads(pathlib.Path(a.doc).read_text(encoding="utf8"))
    prev = json.loads(pathlib.Path(a.prev).read_text(encoding="utf8")) if a.prev else previous(doc, pathlib.Path(a.history))
    logos = pathlib.Path(a.logos)
    rep = build(doc, prev, logos if logos.is_dir() else None)
    body = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.out:
        p = pathlib.Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf8")
        print(f"audit: {rep['verdict']['level']} · {len(rep['verdict']['items'])} item(s) -> {p}")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
