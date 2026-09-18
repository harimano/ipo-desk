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
                 "gmpImplied": 300.0, "listing": 320.0, "close1": 352.0, "ltp": 352.0, "total": 66.01, "sizeCr": 875.0}
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
