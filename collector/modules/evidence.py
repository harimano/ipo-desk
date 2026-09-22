"""evidence — owns `evidence`: what the desk's own history supports, computed once per run so the page quotes it and
never does statistics of its own. Arithmetic, not a model (docs/AI-AND-PREDICTION.md): GMP is already unbiased, so
the value is in the width, the expected value and the named window, not in a better point estimate.

Rules, agreed with Hari on 19 Sep 2026:
  * mainboard and SME are never pooled — 71% of the base is SME, so a pooled band describes neither;
  * every headline rate is a TRAILING WINDOW named on screen (last 12 months, or the last 100 listings of the segment
    when that is more rows); all-years rides along as the secondary figure. 2024 listed positive 85% of the time with
    a +31% median, 2025 63% and +3%: "since 2022" averages different markets;
  * total subscription is the primary band (every year has it). QIB and retail are secondary and carry the years they
    cover — category books exist from 2026 only;
  * a band always shows n and a Wilson 95% interval, so a thin band widens instead of vanishing;
  * the GMP interval comes from a fit of realised on implied return over the window: centre, and the 10th-90th
    percentile of residuals. PROVISIONAL until the desk's own evening-before GMP (`gmpEve`, frozen by `history`) reaches
    MIN_EVE rows in a segment; from then both fits are published side by side — if they differ, that is the look-ahead
    answer about report 377's listing-morning GMP;
  * expected value per application = (lower-bound chance of allotment) x (listing return) - cost of blocked capital,
    as % of the capital ASBA blocks. Reported as median and 10th-90th percentile, never the mean alone: these are
    fat-tailed. The hottest books have the biggest pop and the worst EV;
  * the audit's warnings are data (`evidence.warnings[]`) and render on the page.

The chance of allotment is a LOWER BOUND: true chance = k / retail subscription, where k >= 1 is the average lots per
retail application. No feed carries applications (checked 19 Sep 2026); k can be measured later from basis-of-allotment
documents, which is research-layer work.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import statistics as st
from zoneinfo import ZoneInfo

from ..http import Session
from ..result import Result

log = logging.getLogger("collector.evidence")
IST = ZoneInfo("Asia/Kolkata")
INF = float("inf")
EDGES = {"total": [0, 2, 10, 50, INF], "qib": [0, 5, 25, 100, INF], "retail": [0, 1, 3, 10, 40, INF], "gmp": [-INF, 0.01, 10, 30, INF],
         "open": [-INF, 0, 10, 30, INF],       # the listing-day open, as % over issue price: what to expect from holding to the close
         "anchors": [0, 1, 3, 6, INF]}          # how many of the tracked largest anchors were in the book (players.frozen), accruing since Sep 2026
WINDOW_DAYS, WINDOW_MIN_ROWS = 365, 100
MIN_N = 30                 # below this the page says the band is thin (it still shows it, with its interval)
MIN_EVE = 30               # own-GMP rows in a segment before the second fit is published
RF_ANNUAL = 0.07           # what blocked money would otherwise earn; stated on the page
BLOCK_DAYS_HISTORY = 5     # apply on the last day -> unblocked / credited; T+3 listing


def _q(vals: list[float], q: float) -> float | None:
    s = sorted(vals)
    if not s:
        return None
    i = q * (len(s) - 1)
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | tuple[None, None]:
    if not n:
        return None, None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(100 * max(0.0, c - h), 1), round(100 * min(1.0, c + h), 1)


def band_index(v: float, edges: list[float]) -> int:
    for i in range(len(edges) - 1):
        if edges[i] <= v < edges[i + 1]:
            return i
    return -1


def summarise(rets: list[float]) -> dict:
    n, k = len(rets), sum(1 for r in rets if r > 0)
    lo, hi = wilson(k, n)
    r1 = lambda v: None if v is None else round(v, 1)  # noqa: E731
    return {"n": n, "pos": round(100 * k / n, 1) if n else None, "lo": lo, "hi": hi,
            "med": r1(st.median(rets)) if n else None, "p10": r1(_q(rets, 0.1)), "p90": r1(_q(rets, 0.9))}


def bands(rows: list[dict], key: str) -> list[dict]:
    e = EDGES[key]
    return [summarise([r["ret"] for r in rows if r.get(key) is not None and band_index(r[key], e) == i]) for i in range(len(e) - 1)]


def fit(rows: list[dict], key: str) -> dict | None:
    pts = [(r[key], r["ret"]) for r in rows if r.get(key) not in (None, 0)]     # a GMP of 0 in report 377 is mostly "no quote"
    if len(pts) < MIN_N:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx if sxx else 0.0
    a = my - b * mx
    res = [y - (a + b * x) for x, y in pts]
    sst = sum((y - my) ** 2 for y in ys)
    return {"n": len(pts), "a": round(a, 2), "b": round(b, 3), "r2": round(1 - sum(r * r for r in res) / sst, 2) if sst else None,
            "sd": round(st.pstdev(res), 1), "q10": round(_q(res, 0.1), 1), "q90": round(_q(res, 0.9), 1)}


def ev_bands(rows: list[dict]) -> list[dict]:
    """By retail subscription: the pop, the lower-bound chance of getting it, and what that is worth per application."""
    e, cost = EDGES["retail"], 100 * RF_ANNUAL * BLOCK_DAYS_HISTORY / 365
    out = []
    for i in range(len(e) - 1):
        sel = [r for r in rows if r.get("retail") is not None and band_index(r["retail"], e) == i]
        evs = [min(1.0, 1 / max(r["retail"], 1e-9)) * r["ret"] - cost for r in sel]
        s = summarise([r["ret"] for r in sel])
        s.update({"oddsMed": round(100 * st.median(min(1.0, 1 / max(r["retail"], 1e-9)) for r in sel), 1) if sel else None,
                  "evMed": round(st.median(evs), 2) if evs else None, "evP10": round(_q(evs, 0.1), 2) if evs else None,
                  "evP90": round(_q(evs, 0.9), 2) if evs else None, "evMean": round(st.mean(evs), 2) if evs else None})
        out.append(s)
    return out


def hold_bands(rows: list[dict]) -> list[dict]:
    """By how the stock OPENED: how often the day-1 close beat the open, and by how much (points of issue price).
    A fact about listing day for someone who got an allotment — sell at the open, or hold to the close."""
    e, out = EDGES["open"], []
    for i in range(len(e) - 1):
        d = [r["retClose"] - r["ret"] for r in rows if r.get("retClose") is not None and band_index(r["ret"], e) == i]
        n, k = len(d), sum(1 for x in d if x > 0)
        lo, hi = wilson(k, n)
        out.append({"n": n, "held": round(100 * k / n, 1) if n else None, "lo": lo, "hi": hi, "med": round(st.median(d), 1) if n else None,
                    "p10": None if not n else round(_q(d, 0.1), 1), "p90": None if not n else round(_q(d, 0.9), 1)})
    return out


def anchors_bands(rows: list[dict]) -> dict:
    """By how many of the tracked largest anchors were in the book when it listed. The desk only began freezing line-ups
    in September 2026, so this rests on the listings since then: n is tiny for months and the interval says so."""
    sel = [r for r in rows if r.get("anchors") is not None]
    return {"rows": bands(sel, "anchors"), "n": len(sel), "since": min((r["date"] for r in sel), default=None),
            "of": max((r.get("anchorsOf") or 0 for r in sel), default=None)}


def window_of(rows: list[dict], today: dt.date) -> tuple[list[dict], dict]:
    cut = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    recent = [r for r in rows if r["date"] >= cut]
    rule = "last 12 months"
    if len(recent) < WINDOW_MIN_ROWS:
        recent, rule = sorted(rows, key=lambda r: r["date"], reverse=True)[:WINDOW_MIN_ROWS], f"last {WINDOW_MIN_ROWS} listings"
    return recent, {"rule": rule, "n": len(recent), "from": min((r["date"] for r in recent), default=None),
                    "to": max((r["date"] for r in recent), default=None)}


def unified(doc: dict) -> list[dict]:
    perf = {p["igId"]: p for p in doc.get("listedPerf") or [] if isinstance(p, dict) and p.get("igId") and p.get("date")}
    frozen = (doc.get("players") or {}).get("frozen") or {}
    out = []
    for c in doc.get("comps") or []:
        p = perf.get(c.get("igId")) if isinstance(c, dict) else None
        if not p or c.get("ret") is None or not p.get("issue"):
            continue
        imp = lambda g: round(100 * g / p["issue"], 2) if g is not None else None  # noqa: E731
        out.append({"date": p["date"], "year": int(p["date"][:4]), "sme": bool(p.get("sme")), "ret": c["ret"], "retClose": c.get("retClose"), "total": c.get("total"),
                    "qib": c.get("qib"), "retail": c.get("retail"), "gmp": imp(p.get("gmp")), "gmpEve": imp(p.get("gmpEve")),
                    "anchors": (frozen.get(str(c["igId"])) or {}).get("large"), "anchorsOf": (frozen.get(str(c["igId"])) or {}).get("of")})
    return out


def segment(rows: list[dict], today: dt.date, label: str, warnings: list[dict]) -> dict:
    win, meta = window_of(rows, today)
    cat = [r for r in rows if r.get("qib") is not None or r.get("retail") is not None]
    cat_years = sorted({r["year"] for r in cat})
    seg = {"window": meta, "n": len(rows),
           "bands": {"total": {"window": bands(win, "total"), "all": bands(rows, "total")},
                     "gmp": {"window": bands(win, "gmp"), "all": bands(rows, "gmp")},
                     "qib": {"rows": bands(cat, "qib"), "years": cat_years, "n": sum(1 for r in cat if r.get("qib") is not None)},
                     "retail": {"rows": bands(cat, "retail"), "years": cat_years}},
           "hold": {"window": hold_bands(win), "all": hold_bands(rows)},
           "ev": {"rows": ev_bands(cat), "years": cat_years, "blockDays": BLOCK_DAYS_HISTORY},
           "anchors": anchors_bands(rows),
           "fit": {"r377": fit(win, "gmp"), "eve": None, "provisional": True, "eveRows": sum(1 for r in rows if r.get("gmpEve") is not None)}}
    eve_rows = [r for r in rows if r.get("gmpEve") is not None]
    if len(eve_rows) >= MIN_EVE:
        seg["fit"]["eve"], seg["fit"]["provisional"] = fit(eve_rows, "gmpEve"), False
        both = fit(eve_rows, "gmp")
        seg["fit"]["r377OnSameRows"] = both
        e = seg["fit"]["eve"]
        if e and both and (abs(e["b"] - both["b"]) > 0.15 or abs(e["sd"] - both["sd"]) > 3):
            warnings.append({"code": f"lookahead-{label}", "text": f"{label}: a fit on the desk's own evening-before GMP (slope {e['b']}, sd {e['sd']} pp) "
                             f"differs from one on report 377's listing-morning GMP (slope {both['b']}, sd {both['sd']} pp) over the same "
                             f"{e['n']} listings. Report 377's figure knows something the evening before did not; use the evening fit."})
    else:
        warnings.append({"code": f"gmp-provisional-{label}", "text": f"{label}: the GMP interval is provisional. It is fitted on report 377's GMP, which is "
                         f"stamped on listing morning (about 09:35, before the first trade). A check on 37 recent listings found that update no "
                         f"closer to the outcome than the evening before, but the desk's own evening-before record has only "
                         f"{len(eve_rows)} of the {MIN_EVE} listings needed to confirm it."})
    f = seg["fit"]["r377"]
    if f and (abs(f["b"] - 1) > 0.25 or abs(f["a"]) > 5):
        warnings.append({"code": f"gmp-bias-{label}", "text": f"{label}: in this window GMP is biased (realised = {f['a']:+} + {f['b']} x implied); the centre shown is corrected for it."})
    if len(cat_years) <= 1 and cat:
        warnings.append({"code": f"category-one-year-{label}", "text": f"{label}: QIB and retail bands, and expected value, rest on {len(cat)} listings from "
                         f"{cat_years[0]} alone — category books are not published for earlier years."})
    rates = {y: summarise([r["ret"] for r in rows if r["year"] == y]) for y in sorted({r["year"] for r in rows})}
    ys = [y for y in rates if rates[y]["n"] >= MIN_N]
    for a, b in zip(ys, ys[1:]):
        if abs(rates[a]["pos"] - rates[b]["pos"]) >= 15:
            warnings.append({"code": f"regime-{label}-{b}", "text": f"{label}: {rates[a]['pos']:.0f}% listed positive in {a} (median {rates[a]['med']:+}%), "
                             f"{rates[b]['pos']:.0f}% in {b} ({rates[b]['med']:+}%). All-years figures average different markets; the window is the one to read."})
    seg["byYear"] = {str(y): rates[y] for y in rates}
    return seg


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = today or dt.datetime.now(IST).date()
    rows = unified(res.doc or prev)                       # today's history, when `history` ran before this in the same run
    if len(rows) < MIN_N:
        return res.fail(RuntimeError(f"only {len(rows)} listings with an outcome on file — `history` has not run yet?"))
    warnings: list[dict] = []
    edges = {k: [None if abs(x) == INF else x for x in v] for k, v in EDGES.items()}
    res.replace["evidence"] = {"asOf": t.isoformat(), "rfAnnual": RF_ANNUAL, "minN": MIN_N, "edges": edges,
                               "segments": {"main": segment([r for r in rows if not r["sme"]], t, "mainboard", warnings),
                                            "sme": segment([r for r in rows if r["sme"]], t, "SME", warnings)},
                               "warnings": warnings}
    res.notes.append(f"{len(rows)} listings; windows: mainboard {res.replace['evidence']['segments']['main']['window']['n']}, "
                     f"SME {res.replace['evidence']['segments']['sme']['window']['n']}; {len(warnings)} warnings")
    return res.won("computed", t.isoformat())
