"""Offline tests for collector.modules.flows (NSE fiidiiTradeReact)."""
from __future__ import annotations

import copy

import pytest

from _support import FakeSession, blocked, fixture_json

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
