"""Offline tests for collector.modules.flows (NSE fiidiiTradeReact)."""
from __future__ import annotations

import copy

import pytest
from _support import FakeSession, blocked, fixture, fixture_json

from collector import assemble
from collector.errors import SourceChanged
from collector.modules import flows
from collector.result import Result

FIIDII = fixture_json("nse", "fiidii.json")


def make_prev() -> dict:
    return {
        "flows": {
            "latest": {"date": "2026-09-15", "fiiNetCr": -900.5, "diiNetCr": 1500.0, "previousDay": None,
                       "source": "NSE provisional (fiidiiTradeReact)"},
            "history": [["2026-09-14", -300.0, 800.0], ["2026-09-15", -900.5, 1500.0]],
            "monthly": [["Sep", -4200, "FIIs net sellers for a third month"]],
            "rotation": {"fiiSelling": [["IT", "evidence"]], "diiBuying": [["Banks", "evidence"]]},
            "note": "hand-written note",
        }
    }


def test_parse_fiidii():
    out = flows.parse_fiidii(FIIDII)
    assert out["date"] == "2026-09-16"
    assert out["fii"] == {"buy": 12005.30, "sell": 13690.75, "net": -1685.45}
    assert out["dii"]["net"] == 2332.45


@pytest.mark.parametrize("bad", [[], [{"category": "DII **", "netValue": "1"}], [{"foo": 1}], {"data": []}])
def test_parse_fiidii_changed_shape(bad):
    with pytest.raises(SourceChanged):
        flows.parse_fiidii(bad)


def test_run_sets_latest_and_appends_history():
    prev = make_prev()
    snapshot = copy.deepcopy(prev)
    res = flows.run(FakeSession(nse={"/api/fiidiiTradeReact": FIIDII}), prev, Result(module="flows"))
    assert res.ok and res.source == "nse" and res.asOf == "2026-09-16"
    f = res.replace["flows"]
    assert f["latest"]["date"] == "2026-09-16"
    assert f["latest"]["fiiNetCr"] == -1685.45 and f["latest"]["diiNetCr"] == 2332.45
    assert f["latest"]["previousDay"] == {"date": "2026-09-15", "fiiNetCr": -900.5, "diiNetCr": 1500.0}
    assert f["history"][-1] == ["2026-09-16", -1685.45, 2332.45] and len(f["history"]) == 3
    assert f["monthly"] == prev["flows"]["monthly"]
    assert f["rotation"] == prev["flows"]["rotation"]
    assert f["note"] == "hand-written note"
    assert prev == snapshot
    assemble.apply(copy.deepcopy(prev), res)      # ownership ok


def test_run_does_not_duplicate_history_date():
    prev = make_prev()
    prev["flows"]["history"].append(["2026-09-16", -1685.45, 2332.45])
    prev["flows"]["latest"]["date"] = "2026-09-16"
    res = flows.run(FakeSession(nse={"/api/fiidiiTradeReact": FIIDII}), prev, Result(module="flows"))
    assert res.ok
    dates = [h[0] for h in res.replace["flows"]["history"]]
    assert dates.count("2026-09-16") == 1


def test_nse_blocked_fails_cleanly_and_keeps_prev_flows():
    prev = make_prev()
    snapshot = copy.deepcopy(prev)
    res = flows.run(FakeSession(nse={"/api/fiidiiTradeReact": blocked()}), prev, Result(module="flows"))
    assert res.ok is False
    assert res.error["kind"] == "blocked"
    assert any("only source" in n for n in res.notes)
    data = copy.deepcopy(prev)
    assemble.apply(data, res)
    assert data["flows"] == snapshot["flows"]


def test_non_json_body_is_changed_not_crash():
    res = flows.run(FakeSession(nse={"/api/fiidiiTradeReact": {"unexpected": "shape"}}), make_prev(),
                    Result(module="flows"))
    assert not res.ok and res.error["kind"] == "changed"


# ---- flows.trend: our own months, NSDL's final figures, the facts read off them (18 Nov 2026) ----
NSDL_TEXT = {"RptType=5": fixture("nsdl", "yearwise-fy-2026-11-18.html"),
             "RptType=6": fixture("nsdl", "yearwise-cy-2026-11-18.html"),
             "Monthly.aspx": fixture("nsdl", "monthly-2026-11-18.html")}


def test_own_months_sums_each_month_and_counts_buying_days():
    hist = [["2026-09-29", -100.0, 300.0], ["2026-09-30", 50.0, -20.0], ["2026-10-01", -10.5, 40.25]]
    sep, octo = flows.own_months(hist, [])
    assert sep == {"m": "2026-09", "fii": -50.0, "dii": 280.0, "n": 2, "fiiUp": 1, "diiUp": 1, "from": "2026-09-29", "to": "2026-09-30"}
    assert octo["fii"] == -10.5 and octo["dii"] == 40.25 and octo["n"] == 1 and octo["fiiUp"] == 0


def test_own_months_never_shrinks_when_the_history_cap_drops_old_rows():
    full = [["2026-09-29", -100.0, 300.0], ["2026-09-30", 50.0, -20.0], ["2026-10-01", -10.0, 40.0]]
    kept = flows.own_months(full, [])
    later = flows.own_months(full[1:] + [["2026-10-05", 5.0, 5.0]], kept)      # 29 Sep has aged out of the 40 rows
    assert later[0] == kept[0] and later[0]["n"] == 2
    assert later[1]["n"] == 2 and later[1]["fii"] == -5.0


def test_facts_are_read_off_the_months_and_say_nothing_else():
    view = {"year": 2026, "months": [["2026-08", 29631.0], ["2026-09", -35861.0], ["2026-10", -34843.0], ["2026-11", 106229.0]],
            "years": [["2025-26", -180832.0], ["2026-27", -57796.0]]}
    assert flows.facts(view) == ["Biggest FPI buying month of 2026 so far", "First net-buying month since August",
                                 "Financial year 2026-27 so far: −₹57,796 Cr"]
    view["months"][-1][1] = -200000.0
    assert flows.facts(view)[0] == "Heaviest FPI selling month of 2026 so far" and len(flows.facts(view)) == 2
    assert flows.facts({"year": 2026, "months": [["2026-01", 5.0]], "years": []}) == []


def test_run_adds_the_trend_from_nsdl():
    res = flows.run(FakeSession(nse={"/api/fiidiiTradeReact": FIIDII}, text=NSDL_TEXT), make_prev(), Result(module="flows"))
    assert res.ok and res.source == "nse"
    t = res.replace["flows"]["trend"]
    assert [e["m"] for e in t["own"]] == ["2026-09"] and t["own"][0]["n"] == 3
    n = t["nsdl"]
    assert n["asOf"] == "2026-11-18" and n["year"] == 2026 and n["ytd"] == -188916.0 and n["since"] == "1992-93"
    assert len(n["years"]) == 12 and n["years"][-1] == ["2026-27", -57796.0] and n["months"][-1] == ["2026-11", 106229.0]
    assert n["primary"] == {"month": "2026-11", "net": 5863.52, "days": 12, "top": {"date": "2026-11-18", "net": 5350.82}}
    assert n["days"][-1] == ["2026-11-18", 5914.86, 5350.82]
    assert t["facts"][0] == "Biggest FPI buying month of 2026 so far"
    assemble.apply(make_prev(), res)      # ownership ok


def test_nsdl_refusing_keeps_its_last_figures_and_never_fails_the_module():
    prev = make_prev()
    prev["flows"]["trend"] = {"own": [], "nsdl": {"asOf": "2026-11-17", "months": [["2026-11", 1.0]]}, "facts": ["kept"]}
    res = flows.run(FakeSession(nse={"/api/fiidiiTradeReact": FIIDII}, text={"RptType=5": blocked("nsdl")}), prev, Result(module="flows"))
    assert res.ok and res.source == "nse"
    t = res.replace["flows"]["trend"]
    assert t["nsdl"] == {"asOf": "2026-11-17", "months": [["2026-11", 1.0]]} and t["facts"] == ["kept"]
    assert any("kept those of 2026-11-17" in n for n in res.notes)
    assert any(x.get("source") == "nsdl" and x.get("kind") == "blocked" and x["ok"] is False for x in res.tried)
