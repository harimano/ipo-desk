#!/usr/bin/env python3
"""Seed listedPerf[] and comps[] from ipo-radar's 979-IPO mainboard dataset.

    python3 scripts/seed_history.py [--src /home/claude/ref/ipo-radar/data] [--out data/seed]

Reads cg_issue.csv + cg_listing.csv + cg_subs.csv + cg_gmp.csv (all keyed by cg_ipo_id; columns per
/home/claude/mine/ipo-radar.md B-section) and writes, in the DATA-SCHEMA shapes:
  data/seed/listedPerf.json  [{name, issue, gmpImplied, listing}]   newest first, deduped by name
  data/seed/comps.json       [{name, qib, ret}]                      listed issues with a QIB print

Rules: mainboard only (Issue Category == Mainboard); `issue` is the final issue price (a band string
like "385.00 to 405.00" means the issue was not priced yet -> skipped); `listing` is the listing-day
open price (the site computes gain as (listing - issue) / issue); `gmpImplied` is Chittorgarh's
estimated_price where present, else null; `ret` is the listing-day close return (% vs issue price),
falling back to the open return. Names are cleaned of Chittorgarh's status suffixes (" O", " P",
" LT") and of "Ltd."/"Limited". The dataset is compiled from Chittorgarh/Yahoo and is not licensed:
this is a bootstrap; the listings module re-derives new rows from primary sources.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import sys

SRC_DEFAULT = pathlib.Path("/home/claude/ref/ipo-radar/data")
OUT_DEFAULT = pathlib.Path(__file__).resolve().parent.parent / "data" / "seed"

_SUFFIX = re.compile(r"\s+(?:O|P|LT|C|L)$")
_LTD = re.compile(r"[\s,]*\b(?:Limited|Ltd\.?|Ltd)\s*$", re.I)


def clean_name(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = re.sub(r"\s*\([^)]*\bIPO\)\s*$", "", s)      # "One 97 Communications Ltd. (Paytm IPO)"
    s = _SUFFIX.sub("", s)
    s = _LTD.sub("", s).strip(" ,.-")
    return s


def num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("₹", "").replace("%", "")
    if not s or s.lower() in ("nan", "none", "-", "--"):
        return None
    if " to " in s or "-" in s.strip("-") and not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None                      # a price band, not a price
    try:
        return float(s)
    except ValueError:
        return None


def date_iso(v) -> str | None:
    s = (v or "").strip()
    if not s:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s[:26 if "T" in s else 11], fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return dt.date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def read_csv(path: pathlib.Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            k = (row.get("cg_ipo_id") or "").strip()
            if k and k not in out:
                out[k] = row
    return out


def first(row: dict, *keys):
    for k in keys:
        if k in row and str(row[k]).strip():
            return row[k]
    return None


def build(src: pathlib.Path) -> tuple[list[dict], list[dict], dict]:
    issue = read_csv(src / "cg_issue.csv")
    listing = read_csv(src / "cg_listing.csv")
    subs = read_csv(src / "cg_subs.csv")
    gmp = read_csv(src / "cg_gmp.csv")
    if not issue and not listing:
        raise SystemExit(f"no cg_issue.csv / cg_listing.csv under {src}")

    ids = set(issue) | set(listing)
    rows = []
    stats = {"ids": len(ids), "not_mainboard": 0, "no_issue_price": 0, "no_listing_price": 0}
    for k in ids:
        i, l, s, g = issue.get(k, {}), listing.get(k, {}), subs.get(k, {}), gmp.get(k, {})
        cat = (first(i, "Issue Category") or first(l, "Issue Category") or "").strip()
        if cat and cat.lower() != "mainboard":
            stats["not_mainboard"] += 1
            continue
        name = clean_name(first(i, "company") or first(l, "company") or first(s, "company") or "")
        if not name:
            continue
        issue_price = num(first(l, "Issue Price (Rs.)")) or num(first(i, "Issue Price (Rs.)"))
        if not issue_price:
            stats["no_issue_price"] += 1
            continue
        open_px = num(first(l, "Open Price on Listing (Rs.)"))
        close_px = num(first(l, "Close Price on Listing (Rs.)"))
        list_date = date_iso(first(l, "Listing Date", "IL_IPO_Listing_date") or first(i, "Listing Date", "ListingDate"))
        open_date = date_iso(first(i, "Opening Date", "Issue_Open_Date") or first(l, "Opening Date"))
        gain_close = num(first(l, "% Gain/Loss (Issue price v/s close price on Listing)"))
        gain_open = num(first(l, "% Gain/Loss (Issue price v/s Open price on Listing)"))
        qib = num(first(s, "QIB (x)"))
        est = num(first(g, "estimated_price"))
        gmp_v = num(first(g, "gmp"))
        gmp_implied = est if est else (round(issue_price + gmp_v, 2) if gmp_v is not None else None)
        rows.append({"id": k, "name": name, "issue": issue_price, "open": open_px, "close": close_px,
                     "listDate": list_date, "openDate": open_date, "gainClose": gain_close, "gainOpen": gain_open,
                     "qib": qib, "gmpImplied": gmp_implied})

    rows.sort(key=lambda r: (r["listDate"] or r["openDate"] or "", r["id"]), reverse=True)

    listed_perf, comps, seen_lp, seen_c = [], [], set(), set()
    for r in rows:
        listing_px = r["open"] if r["open"] else r["close"]
        if not listing_px:
            stats["no_listing_price"] += 1
            continue
        key = r["name"].lower()
        if key not in seen_lp:
            seen_lp.add(key)
            listed_perf.append({"name": r["name"], "issue": r["issue"], "gmpImplied": r["gmpImplied"],
                                "listing": listing_px})
        if r["qib"] is not None and key not in seen_c:
            ret = r["gainClose"]
            if ret is None and r["close"]:
                ret = round((r["close"] - r["issue"]) / r["issue"] * 100, 2)
            if ret is None:
                ret = r["gainOpen"]
            if ret is None and r["open"]:
                ret = round((r["open"] - r["issue"]) / r["issue"] * 100, 2)
            if ret is None:
                continue
            seen_c.add(key)
            comps.append({"name": r["name"], "qib": r["qib"], "ret": ret})
    return listed_perf, comps, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC_DEFAULT))
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    a = ap.parse_args(argv)
    listed_perf, comps, stats = build(pathlib.Path(a.src))
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "listedPerf.json").write_text(json.dumps(listed_perf, ensure_ascii=False, indent=1), encoding="utf8")
    (out / "comps.json").write_text(json.dumps(comps, ensure_ascii=False, indent=1), encoding="utf8")
    print(f"listedPerf: {len(listed_perf)} rows -> {out / 'listedPerf.json'}")
    print(f"comps:      {len(comps)} rows -> {out / 'comps.json'}")
    print("stats:", json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
