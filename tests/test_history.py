"""history — the evidence base, built from fetched reports. Fixtures are real responses (18-19 Sep 2026)."""
import datetime as dt
import json
import pathlib

import pytest

from collector import assemble
from collector.errors import SourceChanged, SourceDown
from collector.modules import history
from collector.result import Result
from collector.sources import investorgain as ig

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/investorgain"
PERF = json.loads((FX / "report-377-gmp-performance.json").read_text())
SUBS = json.loads((FX / "report-566-subscription.json").read_text())
TODAY = dt.date(2026, 9, 19)


class S:
    def __init__(self, perf=PERF, subs=SUBS, old_years=None):
        self.perf, self.subs, self.old, self.calls = perf, subs, old_years, []

    def get_json(self, url, *, source=None, headers=None, **kw):
        rep, year = ("566", None) if "/566/" in url else ("377", int(url.split("/12/")[1][:4]))
        self.calls.append(f"{rep}:{year}")
        v = self.subs if rep == "566" else self.perf if year == 2026 else (self.old if self.old is not None else SourceDown("investorgain", "HTTP 503", url, 503))
        if isinstance(v, Exception):
            raise v
        return v


def test_real_report_parses_to_typed_rows():
    rows = ig.parse_performance_report(PERF)
    k = next(r for r in rows if r["name"] == "Karamtara Engineering")
    assert k == {"igId": "1622", "name": "Karamtara Engineering", "date": "2026-09-17", "sme": False, "issue": 254.0, "gmp": 46.0,
                 "gmpImplied": 300.0, "listing": 320.0, "close1": 352.0, "ltp": 352.0, "total": 66.01, "sizeCr": 875.0, "bseCode": "544917"}
    assert any(r["sme"] for r in rows) and all(r["date"][:4] == "2026" for r in rows)
    for bad in ({}, {"msg": "API not found"}, {"reportTableData": [{"IPO": "x"}]}):
        with pytest.raises(SourceChanged):
            ig.parse_performance_report(bad)


def test_both_collections_are_built_and_joined_by_id():
    s = S()
    res = history.run(s, {}, Result(module="history"), today=TODAY)
    assert res.ok and s.calls[0] == "377:2026" and "566:None" in s.calls
    perf, comps = res.replace["listedPerf"], res.replace["comps"]
    assert len(perf) == len(comps) == len(ig.parse_performance_report(PERF)) and perf[0]["date"] >= perf[-1]["date"]
    k = next(c for c in comps if c["name"] == "Karamtara Engineering")
    assert (k["year"], k["sme"], k["total"], k["ret"], k["retClose"]) == (2026, False, 66.01, 25.98, 38.58)
    joined = [c for c in comps if c.get("qib") is not None]
    assert joined and all({"qib", "retail"} <= set(c) for c in joined), "this year's category book comes from report 566"
    data = {"listedPerf": [], "comps": []}
    assemble.apply(data, res)                                        # ownership: history owns both
    assert len(data["comps"]) == len(comps)


def test_a_finished_year_is_fetched_once_and_its_category_book_is_kept():
    old = {"listedPerf": [{"name": "Old Co", "igId": "9", "date": "2025-03-04", "sme": False, "issue": 100.0, "gmp": 10.0,
                           "gmpImplied": 110.0, "listing": 120.0, "close1": 118.0, "ltp": 90.0}],
           "comps": [{"name": "Old Co", "igId": "9", "year": 2025, "sme": False, "total": 40.0, "qib": 88.0, "retail": 12.0, "ret": 20.0, "retClose": 18.0}]}
    s = S()
    res = history.run(s, old, Result(module="history"), today=TODAY)
    assert "377:2025" not in s.calls, "2025 is on file: not asked for again"
    c = next(x for x in res.replace["comps"] if x["name"] == "Old Co")
    assert (c["qib"], c["retail"], c["total"], c["ret"]) == (88.0, 12.0, 40.0, 20.0)


def test_failure_changes_nothing():
    down = SourceDown("investorgain", "HTTP 503", "u", 503)
    res = history.run(S(perf=down), {}, Result(module="history"), today=TODAY)
    assert not res.ok and res.replace == {}
    res = history.run(S(subs=down), {}, Result(module="history"), today=TODAY)       # categories down: totals still land
    assert res.ok and any("category subscription unavailable" in n for n in res.notes)


def test_report_377_is_read_in_its_september_2026_shape_too():
    import json
    import pathlib

    from collector.sources import investorgain as ig
    fx = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/investorgain"
    rows = ig.parse_performance_report(json.loads((fx / "report-377-gmp-performance-2026-09-22.json").read_text()))
    assert len(rows) >= 15
    v = next(r for r in rows if r["name"] == "Vama Wovenfab")
    assert v["igId"] == "1969" and v["sme"] is True and v["date"] == "2026-09-22" and v["issue"] == 341.0 and v["listing"] == 341.0 and v["gmp"] == 3.0
    assert v["gmpImplied"] == 344.0 and v["sizeCr"] == 49.54 and v["total"] == 2.53
    assert any(not r["sme"] for r in rows), "mainboard rows have no badge and read as mainboard"


def test_a_listing_the_report_stops_returning_is_kept_from_the_previous_document():
    """4 Nov 2026, 20:50: report 377 answered seven rows short for one fetch (the 2–4 Nov listings) and they vanished."""
    full = history.run(S(), {}, Result(module="history"), today=TODAY)
    prev = {"listedPerf": full.replace["listedPerf"], "comps": full.replace["comps"]}
    newest = sorted(prev["listedPerf"], key=lambda r: r["date"], reverse=True)[:3]
    short = {**PERF, "reportTableData": [r for r in PERF["reportTableData"] if str(r.get("~id")) not in {n["igId"] for n in newest}]}
    res = history.run(S(perf=short), prev, Result(module="history"), today=TODAY)
    assert res.ok
    ids = {r["igId"] for r in res.replace["listedPerf"]}
    assert all(n["igId"] in ids for n in newest)
    assert len(res.replace["listedPerf"]) == len(prev["listedPerf"])
    assert any("did not return 3 of this year" in n and newest[0]["name"] in n for n in res.notes)
    # and the same prev against the full report: nothing is kept, no note
    again = history.run(S(), prev, Result(module="history"), today=TODAY)
    assert not any("did not return" in n for n in again.notes)


def test_report_377_is_read_in_its_november_2026_shape():
    """Real response of 5 Nov 2026 (302 rows): the seven listings of 2–4 Nov that one fetch on 4 Nov left out are all here."""
    rows = ig.parse_performance_report(json.loads((FX / "report-377-gmp-performance-2026-11-05.json").read_text()))
    assert len(rows) == 302
    names = {r["name"] for r in rows}
    assert {"Ajwa Projects", "Carver Roboweld", "M.K.Sons Fine Jewels", "BLS Polymers", "SFC Environmental Technologies",
            "Wiscon Industries", "EAAA India Alternatives", "Jio Platforms"} <= names
    assert max(r["date"] for r in rows) == "2026-11-04"


def test_the_shareholder_book_is_frozen_from_the_board_at_listing_and_never_revised():
    from collector.modules import history
    perf = [{"name": "Jio", "igId": "1", "date": "2026-10-28", "sme": False, "issue": 1119.0, "gmp": 30, "gmpImplied": 2.7, "listing": 1200.0, "close1": 1180.0, "ltp": None, "total": 21.36},
            {"name": "New", "igId": "2", "date": "2026-11-04", "sme": False, "issue": 100.0, "gmp": 5, "gmpImplied": 5.0, "listing": 110.0, "close1": 108.0, "ltp": None, "total": 3.0},
            {"name": "Plain", "igId": "3", "date": "2026-11-03", "sme": True, "issue": 50.0, "gmp": 0, "gmpImplied": 0.0, "listing": 50.0, "close1": 49.0, "ltp": None, "total": 1.2}]
    board = {"mainboard": [{"name": "Jio", "igId": "1", "sub": {"total": 21.36, "retail": 1.1, "shareholder": 9.99}},
                           {"name": "New", "igId": "2", "sub": {"total": 3.0, "shareholder": 7.59, "employee": 2.1}}],
             "sme": [{"name": "Plain", "igId": "3", "sub": {"total": 1.2, "retail": 1.0, "shareholder": 0}}]}
    reserved = history.reserved_books(board)
    assert reserved == {"1": {"shareholder": 9.99}, "2": {"shareholder": 7.59, "employee": 2.1}}, "a zero is no book; a row without one is absent"
    cats = {"1": {"igId": "1", "qib": 40.0, "retail": 1.2}}                      # report 566: public categories only, the fresher copy
    books = {"1": {"qib": 39.0, "shareholder": 7.59}}                            # what comps froze on an earlier run
    _, comps = history.build(perf, cats, books, None, reserved)
    by = {c["igId"]: c for c in comps}
    assert (by["1"]["shareholder"], by["1"]["qib"], by["1"]["retail"]) == (7.59, 40.0, 1.2), "frozen shareholder book wins over the board; 566 wins for QIB / retail"
    assert (by["2"]["shareholder"], by["2"]["employee"]) == (7.59, 2.1), "first sighting: taken from the board"
    assert "shareholder" not in by["3"] and "employee" not in by["2"] or by["2"]["employee"] == 2.1
    assert "shareholder" not in by["3"]
