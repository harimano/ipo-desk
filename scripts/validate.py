#!/usr/bin/env python3
"""Gate for data/latest.json. Exits non-zero -> CI must NOT commit or deploy.

  python3 scripts/validate.py                              # full check of data/latest.json
  python3 scripts/validate.py --prev <path to previous>    # + delta sanity against what is live
  python3 scripts/validate.py --max-age-hours 6            # freshness

Ported from the db-era validate.py (claude/scripts/validate.py) on 17 Sep 2026, with the one
hardening that day taught: a --prev that resolves to nothing is an ERROR, never a silent skip.
In CI, --prev is the committed latest.json from HEAD and the candidate is the working copy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

TOP_LEVEL = ["meta", "mainboard", "sme", "recent", "expected", "offers", "lot", "comps", "listedPerf",
             "priceHistory", "flows", "news", "integrity", "investors", "anchors", "quota", "current", "sheets"]
STATUSES = {"Open", "Upcoming", "Closed", "Listed"}
BUCKETS = {"approved", "awaited", "done", "drhp", "dropped"}
ISO_FIELDS = {"close", "date", "disclosedDate", "listDate", "listedDate", "listing", "listingDate", "open",
              "recordDate", "stageDate"}
FREE_TEXT = {"dates", "when"}
MAX_DOC_BYTES = 6 * 1024 * 1024      # a static file; generous, but a runaway is still a bug
MAX_ITEM_LOSS = 0.30
MIN_CENSUS = 8

errors: list[str] = []
warnings: list[str] = []


def err(m):
    errors.append(m)


def warn(m):
    warnings.append(m)


def iso(s):
    try:
        dt.date.fromisoformat(s)
        return True
    except Exception:
        return False


def walk_dates(o, where):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in FREE_TEXT:
                continue
            if k in ISO_FIELDS and isinstance(v, str) and v.strip():
                if not iso(v[:10]):
                    err(f"{where}: {k}={v!r} is not YYYY-MM-DD")
            else:
                walk_dates(v, where)
    elif isinstance(o, list):
        for x in o:
            walk_dates(x, where)


def census(o, path="", acc=None, in_row=False):
    """Count every collection so a loss anywhere in the tree is visible.

    Top level: a list's length, a dict's key count (lot, priceHistory, sheets… are dicts keyed by name). Inside the
    rows of a list the measure changes: a nested list is SUMMED across all rows (`anchors[]/investors` = every
    investor on file), and a row's own nested objects are not counted at all. They used to be — overwritten row by
    row, so the figure was whichever row came last, and a board whose last listing had 7 KPI fields instead of 15
    read as a 53% loss (18 Sep 2026). How many keys one listing's `facts.kpis` has is not a collection."""
    acc = {} if acc is None else acc
    key = path or "/"
    if isinstance(o, dict):
        if not in_row:
            acc[key] = len(o)
        for k, v in o.items():
            census(v, f"{path}/{k}", acc, in_row)
    elif isinstance(o, list):
        acc[key] = acc.get(key, 0) + len(o) if in_row else len(o)
        for v in o:
            if isinstance(v, (dict, list)):
                census(v, f"{path}[]", acc, True)
    return acc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="data/latest.json")
    ap.add_argument("--prev", help="previous latest.json to delta-check against")
    ap.add_argument("--max-age-hours", type=float, default=168)
    a = ap.parse_args()
    p = pathlib.Path(a.path)

    # 1. presence + parse + size
    if not p.exists():
        err(f"{p} does not exist")
        return report()
    sz = p.stat().st_size
    if sz > MAX_DOC_BYTES:
        err(f"{p}: {sz:,} B exceeds the {MAX_DOC_BYTES:,} B cap")
    try:
        data = json.loads(p.read_text(encoding="utf8"))
    except Exception as e:
        err(f"{p}: does not parse — {e}")
        return report()
    for k in TOP_LEVEL:
        if k not in data:
            err(f"missing top-level key {k!r}")
    if errors:
        return report()

    # 2. required content
    meta = data.get("meta") or {}
    for k in ("asOf", "label"):
        if not meta.get(k):
            err(f"meta.{k} is missing or empty")
    for k in ("mainboard", "sme"):
        if not isinstance(data.get(k), list) or not data[k]:
            err(f"{k} is missing or empty")

    # 3. enums + row keys
    for k in ("mainboard", "sme", "recent"):
        seen = set()
        for r in data.get(k, []):
            name = r.get("name")
            if not name:
                err(f"{k}: row without a name")
            elif name in seen:
                err(f"{k}: duplicate row name {name!r}")
            seen.add(name)
            if k != "recent" and r.get("status") not in STATUSES:
                err(f"{k} '{name}': status {r.get('status')!r} not in {sorted(STATUSES)}")
    for r in data.get("quota", []):
        if r.get("bucket") not in BUCKETS:
            err(f"quota '{r.get('name', '?')}': bucket {r.get('bucket')!r} not in {sorted(BUCKETS)}")

    # 4. dates
    walk_dates(data, "latest")

    # 5. freshness
    if meta.get("asOf"):
        try:
            ts = dt.datetime.fromisoformat(meta["asOf"])
            now = dt.datetime.now(ts.tzinfo)
            age = (now - ts).total_seconds() / 3600
            if age < -0.5:
                err(f"meta.asOf {meta['asOf']} is in the future")
            elif age > a.max_age_hours:
                err(f"meta.asOf is {age:.1f}h old, limit {a.max_age_hours}h")
        except Exception as e:
            err(f"meta.asOf {meta['asOf']!r} does not parse — {e}")

    # 6. integrity must say something about this run
    checks = (data.get("integrity") or {}).get("checks") or []
    if not checks:
        err("integrity.checks is empty — the run did not record what it did")
    stale = [c["area"] for c in checks if c.get("status") in ("stale", "blocked")]
    if stale:
        warn(f"sections kept from a previous run: {', '.join(stale)}")

    # 7. delta sanity against what is live — and it must actually run
    if a.prev:
        pp = pathlib.Path(a.prev)
        if not pp.exists():
            err(f"--prev {a.prev!r} does not exist. The delta check DID NOT RUN. Fix the path; do not write unchecked data.")
        else:
            try:
                prev = json.loads(pp.read_text(encoding="utf8"))
            except Exception as e:
                err(f"--prev {a.prev!r} does not parse ({e}). The delta check DID NOT RUN.")
                prev = None
            if prev is not None:
                old_c, new_c = census(prev), census(data)
                compared = 0
                for path, old in old_c.items():
                    # /meta/unresolved is a to-do list the collector rebuilds each run; it shrinking is the goal
                    if (old < MIN_CENSUS or path.startswith("/integrity") or path.startswith("/news")
                            or path == "/meta/unresolved"):
                        continue
                    compared += 1
                    new = new_c.get(path, 0)
                    if (old - new) / old > MAX_ITEM_LOSS:
                        err(f"latest{path}: {old} -> {new} items ({100 * (old - new) / old:.0f}% loss, limit {100 * MAX_ITEM_LOSS:.0f}%)")
                if compared == 0:
                    err("--prev had no collection large enough to compare. The delta check DID NOT RUN.")
    return report()


def report() -> int:
    for w in warnings:
        print(f"WARN  {w}")
    if errors:
        print(f"\nFAIL — {len(errors)} error(s); do not write:")
        for e in errors[:25]:
            print(f"  · {e}")
        if len(errors) > 25:
            print(f"  · ... and {len(errors) - 25} more")
        return 1
    print("PASS — data is safe to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
