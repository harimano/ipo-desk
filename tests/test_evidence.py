"""evidence — what the desk's history supports. Built from the real report 377 / 566 responses (18-19 Sep 2026)."""
import datetime as dt
import json
import pathlib

from collector import assemble, layout, schema
from collector.modules import evidence as ev, history
from collector.result import Result
from collector.sources import investorgain as ig

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/investorgain"
TODAY = dt.date(2026, 9, 19)


def doc():
    perf = ig.parse_performance_report(json.loads((FX / "report-377-gmp-performance.json").read_text()))
    cats = {s["igId"]: s for s in ig.parse_subscription_report(json.loads((FX / "report-566-subscription.json").read_text()), TODAY)}
    listed, comps = history.build(perf, cats, {})
    return {"listedPerf": listed, "comps": comps}


def run(d):
    return ev.run(None, {}, Result(module="evidence", doc=d), today=TODAY)


def test_wilson_widens_a_thin_band_instead_of_hiding_it():
    assert ev.wilson(0, 0) == (None, None)
    lo, hi = ev.wilson(4, 5)
    assert lo < 40 and hi > 95, "4 of 5 is 80% — and anything from the 30s to the high 90s"
    lo2, hi2 = ev.wilson(80, 100)
    assert hi2 - lo2 < (hi - lo) / 3
    assert ev.wilson(5, 5)[1] == 100.0 and ev.wilson(0, 5)[0] == 0.0


def test_segments_are_never_pooled_and_every_band_carries_n_and_an_interval():
    d = doc()
    res = run(d)
    assert res.ok
    e = res.replace["evidence"]
    main, sme = e["segments"]["main"], e["segments"]["sme"]
    assert main["n"] + sme["n"] == sum(1 for c in d["comps"] if c["ret"] is not None) and main["n"] and sme["n"]
    for seg in (main, sme):
        assert seg["window"]["rule"] in ("last 12 months", "last 100 listings") and seg["window"]["from"] <= seg["window"]["to"]
        assert sum(b["n"] for b in seg["bands"]["total"]["all"]) <= seg["n"]
        for b in seg["bands"]["total"]["window"] + seg["bands"]["qib"]["rows"]:
            assert set(b) >= {"n", "pos", "lo", "hi", "med", "p10", "p90"}
            assert (b["pos"] is None) == (b["n"] == 0) and (b["n"] == 0 or b["lo"] <= b["pos"] <= b["hi"])
        assert seg["bands"]["qib"]["years"] == [2026], "category books say which years they cover"
    assert e["edges"]["total"] == [0, 2, 10, 50, None] and e["edges"]["gmp"][0] is None, "no Infinity in the JSON"
    json.dumps(e, allow_nan=False)


def test_the_hottest_retail_book_has_the_biggest_pop_and_not_the_best_expected_value():
    # the shape of 2026's mainboard: 10-40x retail pops ~20%, >40x pops ~35% and allots almost nobody
    rows = [{"retail": 20.0, "ret": r} for r in (12.0, 20.0, 28.0)] + [{"retail": 60.0, "ret": r} for r in (25.0, 35.0, 45.0)] + [{"retail": 0.6, "ret": -4.0}]
    out = ev.ev_bands(rows)
    mid, hot = out[3], out[4]
    assert hot["med"] > mid["med"] and hot["evMed"] < mid["evMed"]
    assert {"evP10", "evP90", "evMean"} <= set(hot), "median and spread, never the mean alone"
    assert out[0]["oddsMed"] == 100.0, "an undersubscribed retail book allots everyone: the chance is capped at 1"


def test_expected_value_nets_out_the_cost_of_blocked_capital():
    rows = [{"retail": 20.0, "ret": 40.0}] * 3
    b = ev.ev_bands(rows)[3]
    cost = 100 * ev.RF_ANNUAL * ev.BLOCK_DAYS_HISTORY / 365
    assert b["evMed"] == round(40.0 / 20 - cost, 2) and b["oddsMed"] == 5.0


def test_the_gmp_interval_is_provisional_until_the_desks_own_gmp_has_thirty_rows():
    d = doc()
    e = run(d).replace["evidence"]
    f = e["segments"]["main"]["fit"]
    assert f["provisional"] and f["eve"] is None and f["r377"]["n"] >= ev.MIN_N and f["r377"]["q10"] < 0 < f["r377"]["q90"]
    assert any(w["code"] == "gmp-provisional-mainboard" for w in e["warnings"])
    assert any(w["code"].startswith("category-one-year") for w in e["warnings"])

    main = [p for p in d["listedPerf"] if not p["sme"] and p.get("gmp")][: ev.MIN_EVE]
    for p in main:                                                # the evening before said half of what the morning did
        p["gmpEve"], p["gmpEveAsOf"] = p["gmp"] / 2, "2026-01-01T18:00:00+05:30"
    e = run(d).replace["evidence"]
    f = e["segments"]["main"]["fit"]
    assert not f["provisional"] and f["eve"]["n"] == f["r377OnSameRows"]["n"], "both fits, same listings, side by side"
    assert f["r377"] is not None, "the 377 fit is not silently replaced"
    assert any(w["code"] == "lookahead-mainboard" for w in e["warnings"]), "a material difference IS the look-ahead answer"
    assert e["segments"]["sme"]["fit"]["provisional"]


def test_a_zero_gmp_is_not_a_point_on_the_fit():
    rows = [{"gmp": 0.0, "ret": 50.0}] * 40 + [{"gmp": float(i), "ret": float(i)} for i in range(1, 41)]
    f = ev.fit(rows, "gmp")
    assert f["n"] == 40 and f["b"] == 1.0 and f["a"] == 0.0


def test_the_window_falls_back_to_the_last_hundred_listings():
    rows = [{"date": f"2024-01-{1 + i % 28:02d}", "ret": 1.0} for i in range(150)]
    win, meta = ev.window_of(rows, TODAY)
    assert len(win) == 100 and meta["rule"] == "last 100 listings"


def test_no_history_is_a_failure_not_an_empty_success():
    res = run({"listedPerf": [], "comps": []})
    assert not res.ok and "evidence" not in res.replace


def test_the_key_is_owned_published_and_frozen_gmp_survives_a_rebuild():
    assert schema.OWNERS["evidence"] == "evidence" and "evidence" in schema.TOP_LEVEL
    layout.check_groups()
    data = schema.empty_data()
    assemble.apply(data, run(doc()))
    assert data["evidence"]["segments"]["main"]["n"]

    perf = ig.parse_performance_report(json.loads((FX / "report-377-gmp-performance.json").read_text()))
    k = next(p for p in perf if p["name"] == "Karamtara Engineering")
    eve = {k["igId"]: {"gmpEve": 44.0, "gmpEveAsOf": "2026-09-16T23:37:00+05:30"},
           perf[0]["igId"]: {"gmpEve": 9.0, "gmpEveAsOf": perf[0]["date"] + "T09:35:00+05:30"}}
    listed, _ = history.build(perf, {}, {}, eve)
    row = next(p for p in listed if p["igId"] == k["igId"])
    assert (row["gmpEve"], row["gmpEveAsOf"][:10]) == (44.0, "2026-09-16")
    assert "gmpEve" not in next(p for p in listed if p["igId"] == perf[0]["igId"]), "a quote stamped on listing day is not the evening before"


def test_hold_or_sell_is_banded_by_how_the_stock_opened():
    rows = [{"ret": 40.0, "retClose": 35.0}] * 3 + [{"ret": 40.0, "retClose": 46.0}] + [{"ret": 5.0, "retClose": 7.0}] * 2 + [{"ret": -3.0, "retClose": None}]
    b = ev.hold_bands(rows)
    assert (b[3]["n"], b[3]["held"], b[3]["med"]) == (4, 25.0, -5.0), "opened +30% or more: the close beat the open once in four"
    assert (b[1]["n"], b[1]["held"]) == (2, 100.0) and b[0]["n"] == 0 and b[0]["held"] is None, "no day-1 close on file: not counted"
    seg = run(doc()).replace["evidence"]["segments"]["main"]
    assert len(seg["hold"]["window"]) == 4 and sum(x["n"] for x in seg["hold"]["all"]) > 0
    assert run(doc()).replace["evidence"]["edges"]["open"] == [None, 0, 10, 30, None]


def test_anchor_line_ups_are_banded_from_the_frozen_record_only():
    d = doc()
    res = run(d)
    a = res.replace["evidence"]["segments"]["main"]["anchors"]
    assert a["n"] == 0 and a["since"] is None and all(b["n"] == 0 for b in a["rows"]), "nothing frozen: every band empty, none hidden"
    ids = [c["igId"] for c in d["comps"] if c.get("ret") is not None and not next(p for p in d["listedPerf"] if p["igId"] == c["igId"]).get("sme")][:5]
    d["players"] = {"frozen": {str(i): {"large": k, "listedOn": "2026-09-20"} for k, i in enumerate(ids)}}
    a = run(d).replace["evidence"]["segments"]["main"]["anchors"]
    assert a["n"] == 5 and [b["n"] for b in a["rows"]] == [1, 2, 2, 0], "bands: none · 1–2 · 3–5 · 6+"
    assert all(b["lo"] is not None and b["hi"] is not None for b in a["rows"] if b["n"]), "a thin band carries its interval"
    assert res.replace["evidence"]["edges"]["anchors"] == [0, 1, 3, 6, None]
    assert run(d).replace["evidence"]["segments"]["sme"]["anchors"]["n"] == 0, "never pooled"


def test_lock_in_outcomes_accrue_from_the_price_path_and_are_frozen():
    d = doc()
    d["anchors"] = [{"name": "A Co", "lockIn30": "2026-09-10"}, {"name": "B Co", "lockIn30": "2026-09-15"}, {"name": "C Co", "lockIn30": "2026-09-30"}]
    d["mainboard"], d["sme"] = [{"name": "A Co"}], [{"name": "B Co"}]
    days = ["2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
    d["priceHistory"] = {"A Co": [[x, 100.0 + i] for i, x in enumerate(days)], "B Co": [[x, 50.0] for x in days[:6]]}
    res = run(d)
    L = res.replace["evidence"]["lockins"]
    assert L["days"] == 5 and [r["name"] for r in L["rows"]] == ["A Co"], "B has only one close after its lock; C has not opened"
    a = L["rows"][0]
    assert a == {"name": "A Co", "sme": False, "date": "2026-09-10", "base": 101.0, "after": 106.0, "ret": 5.0}
    m = res.replace["evidence"]["segments"]["main"]["lockin"]
    assert m["n"] == 1 and m["pos"] == 100.0 and m["lo"] is not None and m["since"] == "2026-09-10"
    assert res.replace["evidence"]["segments"]["sme"]["lockin"]["n"] == 0, "never pooled"
    # frozen: the price path can vanish (90-day cap) and the row stays; a rewrite is never attempted
    d2 = dict(d); d2["priceHistory"] = {}
    prev = {"evidence": res.replace["evidence"]}
    res2 = ev.run(None, prev, Result(module="evidence", doc=d2), today=TODAY)
    assert res2.replace["evidence"]["lockins"]["rows"] == L["rows"]


def test_track_records_come_from_anchor_books_joined_to_outcomes_never_pooled():
    d = doc()
    main = [c for c in d["comps"] if c.get("ret") is not None and not next(p for p in d["listedPerf"] if p["igId"] == c["igId"]).get("sme")][:3]
    sme = [c for c in d["comps"] if c.get("ret") is not None and next(p for p in d["listedPerf"] if p["igId"] == c["igId"]).get("sme")][:1]
    nm = {c["igId"]: c["name"] for c in main + sme}
    row = lambda key, alloc, amt: {"name": key.title(), "key": key, "shares": 1, "amtCr": amt, "pctAlloc": alloc, "pctIssue": 1}
    d["anchorBooks"] = {"books": {
        str(main[0]["igId"]): {"name": nm[main[0]["igId"]], "sme": False, "listedOn": "2026-09-01", "complete": True, "rows": [row("FUND A", 40, 10), row("FUND B", 30, 8), row("FUND C", 30, 8)]},
        str(main[1]["igId"]): {"name": nm[main[1]["igId"]], "sme": False, "listedOn": "2026-09-02", "complete": False, "rows": [row("FUND A", 50, 20), row("FUND D", 50, 20)]},
        str(main[2]["igId"]): {"name": nm[main[2]["igId"]], "sme": False, "listedOn": "2026-09-03", "complete": True, "rows": [row("FUND C", 100, 5)]},
        str(sme[0]["igId"]): {"name": nm[sme[0]["igId"]], "sme": True, "listedOn": "2026-09-04", "complete": True, "rows": [row("FUND A", 100, 2)]},
        "99999": {"name": "No Outcome Yet", "sme": False, "listedOn": "2026-09-20", "complete": True, "rows": [row("FUND A", 100, 9)]},
    }}
    days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09"]
    d["priceHistory"] = {nm[main[0]["igId"]]: [[x, 100.0 + i * 2] for i, x in enumerate(days)]}
    res = run(d)
    T = res.replace["trackRecords"]
    assert T["booksOn"] == 5 and T["withOutcome"] == 4 and T["investors"] == 4 and T["minRows"] == 2
    A = next(r for r in T["rows"] if r["key"] == "FUND A")
    assert A["n"] == 3 and A["cr"] == 32.0 and A["main"]["n"] == 2 and A["sme"]["n"] == 1, "mainboard and SME kept apart; the book with no outcome is not counted"
    assert A["main"]["lead"]["n"] == 2 and A["main"]["d5"]["n"] == 1 and A["main"]["d5"]["med"] == 10.0 and A["main"]["d30"]["n"] == 0
    assert A["main"]["lo"] is not None and A["main"]["hi"] is not None and set(A["main"]) >= {"n", "pos", "lo", "hi", "med", "close1", "d5", "d30", "lead"}
    C = next(r for r in T["rows"] if r["key"] == "FUND C")
    assert C["main"]["lead"]["n"] == 1, "third name of a book is not a lead anchor"
    assert not any(r["key"] in ("FUND B", "FUND D") for r in T["rows"]), "one IPO is not a record"
    assert [r["n"] for r in T["rows"]] == sorted((r["n"] for r in T["rows"]), reverse=True) and len(A["ipos"]) == 3
    from collector import assemble, layout, schema
    data = schema.empty_data(); assemble.apply(data, res); layout.check_groups()
    assert "trackRecords" in layout.GROUPS["books"]
