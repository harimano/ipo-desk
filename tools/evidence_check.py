#!/usr/bin/env python3
"""evidence_check — audit the evidence base the Board and Scoreboard quote from.

    python3 tools/evidence_check.py [data/latest.json]

A bench tool, not a module: it reads `listedPerf` and `comps` and prints what the desk's own
history actually supports, with the sample size behind every figure. Standard library only.

It answers four questions the page currently answers implicitly:

  1. COVERAGE  — how many rows are behind each band, and from which years and segments.
  2. POOLING   — does a band say the same thing for mainboard and SME? (It often does not.)
  3. REGIME    — does a band say the same thing this year as three years ago? (It does not.)
  4. GMP       — is GMP biased, and how wide is the honest interval around it?

Exit code 1 if any check fails, so it can run in CI as a guard on the evidence base:
a band published with fewer than MIN_N rows, or a calibration whose slope has drifted far from
the window the page quotes, is a number the page should not be stating as fact.
"""
from __future__ import annotations

import json
import pathlib
import statistics as st
import sys

MIN_N = 30            # below this a band is an anecdote, not a base rate
QIB_BANDS = [("<5x", 0, 5), ("5-25x", 5, 25), ("25-100x", 25, 100), (">100x", 100, float("inf"))]
TOTAL_BANDS = [("<2x", 0, 2), ("2-10x", 2, 10), ("10-50x", 10, 50), (">50x", 50, float("inf"))]


# ---------- small stats, no numpy ----------
def rate(rows: list[dict]) -> tuple[int, float, float]:
    """n, % that listed above issue, median listing return."""
    r = [c["ret"] for c in rows if c.get("ret") is not None]
    if not r:
        return 0, 0.0, 0.0
    return len(r), 100 * sum(1 for x in r if x > 0) / len(r), st.median(r)


def ols(xs: list[float], ys: list[float]) -> tuple[float, float, float, float]:
    """intercept, slope, R^2, residual sd."""
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else 0.0
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    sst = sum((y - my) ** 2 for y in ys)
    r2 = 1 - sum(r * r for r in resid) / sst if sst else 0.0
    return a, b, r2, st.pstdev(resid)


def quantile(vals: list[float], q: float) -> float:
    s = sorted(vals)
    if not s:
        return 0.0
    i = q * (len(s) - 1)
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


# ---------- the checks ----------
def load(path: pathlib.Path) -> tuple[list[dict], dict[str, dict]]:
    d = json.loads(path.read_text(encoding="utf8"))
    comps = [c for c in d.get("comps") or [] if isinstance(c, dict) and c.get("igId")]
    perf = {p["igId"]: p for p in d.get("listedPerf") or [] if isinstance(p, dict) and p.get("igId")}
    return comps, perf


def coverage(comps: list[dict], perf: dict[str, dict]) -> list[str]:
    fail = []
    years = sorted({c.get("year") for c in comps if c.get("year")})
    n_sme = sum(1 for c in comps if c.get("sme"))
    qib = [c for c in comps if c.get("qib") is not None]
    qib_years = sorted({c["year"] for c in qib})
    print(f"rows {len(comps)}   years {years[0]}-{years[-1]}   SME {n_sme} ({100*n_sme/len(comps):.0f}%)   "
          f"mainboard {len(comps)-n_sme}")
    print(f"category books (QIB/NII/retail): {len(qib)} rows, years {qib_years}")
    if len(qib_years) <= 1:
        print(f"  ! every QIB band on the page rests on {len(qib)} rows from one year — say so on the page, "
              f"or band by total subscription (n={len(comps)}) until the books go back further")
        fail.append("qib-single-year")
    gmp = [p for p in perf.values() if p.get("gmp") not in (None, 0)]
    print(f"rows with a GMP: {len(gmp)} of {len(perf)}")
    return fail


def pooling(comps: list[dict], key: str, bands) -> list[str]:
    """Does a band mean the same thing for mainboard and SME?"""
    fail = []
    print(f"\n{key} bands — pooled vs split")
    print(f"{'band':9} {'pooled':>22} {'mainboard':>22} {'SME':>22}")
    for lab, lo, hi in bands:
        sel = [c for c in comps if c.get(key) is not None and lo <= c[key] < hi]
        cells = []
        for rows in (sel, [c for c in sel if not c.get("sme")], [c for c in sel if c.get("sme")]):
            n, pos, med = rate(rows)
            cells.append(f"n={n:<4} {pos:4.0f}% med{med:+6.1f}")
        print(f"{lab:9} {cells[0]:>22} {cells[1]:>22} {cells[2]:>22}")
        nm, pm, _ = rate([c for c in sel if not c.get("sme")])
        ns, ps, _ = rate([c for c in sel if c.get("sme")])
        if nm >= MIN_N and ns >= MIN_N and abs(pm - ps) >= 20:
            print(f"          ! mainboard and SME differ by {abs(pm-ps):.0f} points in this band — "
                  f"a pooled figure describes neither")
            fail.append(f"pool-{key}-{lab}")
        n, _, _ = rate(sel)
        if 0 < n < MIN_N:
            print(f"          ! {n} rows — below the {MIN_N} this tool treats as a base rate")
            fail.append(f"thin-{key}-{lab}")
    return fail


def regime(comps: list[dict]) -> list[str]:
    print("\nby year — the same question, a different answer each year")
    prev = None
    fail = []
    for y in sorted({c["year"] for c in comps if c.get("year")}):
        yr = [c for c in comps if c["year"] == y]
        cells = []
        for rows in (yr, [c for c in yr if not c.get("sme")], [c for c in yr if c.get("sme")]):
            n, pos, med = rate(rows)
            cells.append(f"n={n:<4} {pos:4.0f}% med{med:+6.1f}")
        print(f"{y}  all {cells[0]}   mainboard {cells[1]}   SME {cells[2]}")
        _, pos, _ = rate(yr)
        if prev is not None and abs(pos - prev) >= 15:
            fail.append(f"regime-{y}")
        prev = pos
    if fail:
        print("  ! the listed-positive rate moved by 15+ points between consecutive years: a band computed over "
              "all years is an average of different markets. Quote a trailing window and label it.")
    return fail


def gmp_calibration(comps: list[dict], perf: dict[str, dict]) -> list[str]:
    """Is GMP biased (slope != 1, intercept != 0), and how wide is the honest band around it?"""
    rows = []
    for c in comps:
        p = perf.get(c["igId"])
        if not p or not p.get("issue") or p.get("gmpImplied") in (None, 0) or c.get("ret") is None:
            continue
        rows.append((c.get("year"), bool(c.get("sme")), 100 * (p["gmpImplied"] - p["issue"]) / p["issue"], c["ret"]))
    print("\nGMP calibration — realised listing return regressed on GMP-implied return")
    print("(slope 1.00 and intercept 0 = unbiased on average; the residual sd is the honest width)")
    fail = []
    for lab, sel in (("all", rows), ("mainboard", [r for r in rows if not r[1]]), ("SME", [r for r in rows if r[1]])):
        if len(sel) < MIN_N:
            continue
        a, b, r2, sd = ols([r[2] for r in sel], [r[3] for r in sel])
        lo, hi = quantile([r[3] - (a + b * r[2]) for r in sel], 0.1), quantile([r[3] - (a + b * r[2]) for r in sel], 0.9)
        print(f"  {lab:10} n={len(sel):4}  realised = {a:+5.2f} + {b:4.2f} x implied   R2={r2:.2f}   "
              f"resid sd={sd:5.1f}pp   80% band {lo:+.0f} to {hi:+.0f}pp")
        if abs(b - 1) > 0.25 or abs(a) > 5:
            print(f"           ! biased in this window — a point estimate from GMP would be systematically off")
            fail.append(f"gmp-bias-{lab}")
    print("  by year and segment (this is what a rolling fit would use):")
    for y in sorted({r[0] for r in rows if r[0]}):
        for lab, sme in (("mainboard", False), ("SME", True)):
            sel = [r for r in rows if r[0] == y and r[1] == sme]
            if len(sel) < MIN_N:
                continue
            a, b, r2, sd = ols([r[2] for r in sel], [r[3] for r in sel])
            print(f"    {y} {lab:10} n={len(sel):4}  a={a:+5.2f}  b={b:4.2f}  R2={r2:.2f}  sd={sd:5.1f}pp")
    return fail


def lookahead_warning(comps: list[dict], perf: dict[str, dict]) -> list[str]:
    """A GMP stamped at or after listing would make every backtest here a fiction.

    Cannot be settled from this file alone — it needs the desk's own pre-listing GMP, which the live
    loop records. This prints the test to run rather than a verdict.
    """
    print("\nlook-ahead — the one check that decides whether any of the above is real")
    print("  report 377's 'last GMP' is dated by its source, not by us. If it is stamped on or after")
    print("  listing day, the calibration above is fitted on an answer that already knew the result.")
    print("  Test: for listings since this desk went live, compare the GMP the collector itself recorded")
    print("  the evening before listing (data/history/<date>.json, board row `gmp`) with report 377's")
    print("  figure for the same igId. Equal-and-late means look-ahead; close-but-earlier means honest.")
    print("  Until that is done, treat every R2 above as an upper bound.")
    return []


def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "data/latest.json")
    if not path.exists():
        print(f"no {path} — run scripts/pull_data.sh first")
        return 2
    comps, perf = load(path)
    if not comps:
        print("no comps[] in this document")
        return 2
    fail: list[str] = []
    fail += coverage(comps, perf)
    fail += pooling(comps, "qib", QIB_BANDS)
    fail += pooling(comps, "total", TOTAL_BANDS)
    fail += regime(comps)
    fail += gmp_calibration(comps, perf)
    fail += lookahead_warning(comps, perf)
    print("\n" + ("PASS — no evidence-base warnings" if not fail else f"WARNINGS: {', '.join(sorted(set(fail)))}"))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
