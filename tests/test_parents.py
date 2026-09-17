"""Offline tests for collector.modules.parents (parentPrice merge into sheets)."""
from __future__ import annotations

import copy

import pytest

from _support import FakeSession, FakeSmartConnect, fixture_json, yahoo_frame

from collector import assemble
from collector.modules import parents
from collector.result import Result
from collector.sources import angelone, yahoo

BARS = fixture_json("yahoo", "bars.json")


def make_prev() -> dict:
    return {
        "sheets": {
            "Jio Platforms": {"parent": "Reliance Industries", "parentTicker": "RELIANCE", "status": "drhp",
                              "parentPrice": {"value": 2900.0, "asOf": "2026-09-01"}, "bull": ["x"]},
            "SBI Funds": {"parent": "State Bank of India", "parentTicker": "SBIN.NS"},
            "No Ticker Co": {"parent": "Private Ltd"},
        }
    }


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(yahoo.time, "sleep", lambda s: None)
    monkeypatch.setattr(angelone.time, "sleep", lambda s: None)
    angelone.reset()
    yield
    angelone.reset()


@pytest.fixture
def no_angel(monkeypatch):
    for k in angelone.ENV_VARS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def angel_env(monkeypatch):
    for k, v in (("ANGEL_API_KEY", "k"), ("ANGEL_CLIENT_CODE", "C123"), ("ANGEL_PIN", "0000"),
                 ("ANGEL_TOTP_SECRET", "JBSWY3DPEHPK3PXP")):
        monkeypatch.setenv(k, v)


def test_yahoo_wins_when_angelone_not_configured(no_angel, monkeypatch):
    monkeypatch.setattr(yahoo, "_download", lambda tickers, days: yahoo_frame(BARS, tickers))
    prev = make_prev()
    snapshot = copy.deepcopy(prev)
    res = parents.run(FakeSession(), prev, Result(module="parents"))
    assert res.ok and res.source == "yahoo"
    assert res.merge["sheets"]["Jio Platforms"] == {"parentPrice": {"value": 2955.9, "asOf": "2026-09-16"}}
    assert res.merge["sheets"]["SBI Funds"]["parentPrice"]["value"] == 815.3
    assert "No Ticker Co" not in res.merge["sheets"]
    assert set(res.merge) == {"sheets"} and not res.replace and not res.rows
    assert prev == snapshot
    data = copy.deepcopy(prev)
    assemble.apply(data, res)
    assert data["sheets"]["Jio Platforms"]["bull"] == ["x"], "only parentPrice touched"
    assert data["sheets"]["Jio Platforms"]["parentPrice"]["value"] == 2955.9


def test_angelone_ltp_wins_when_configured(angel_env, monkeypatch):
    fake = FakeSmartConnect()
    monkeypatch.setattr(angelone, "_connect", lambda api_key: fake)
    monkeypatch.setattr(yahoo, "_download", lambda *a: (_ for _ in ()).throw(AssertionError("yahoo must not run")))
    session = FakeSession(json_={"OpenAPIScripMaster.json": fixture_json("angelone", "instrument_master.json")})
    res = parents.run(session, make_prev(), Result(module="parents"))
    assert res.ok and res.source == "angelone"
    assert res.merge["sheets"]["Jio Platforms"]["parentPrice"]["value"] == 2951.4
    assert res.merge["sheets"]["SBI Funds"]["parentPrice"]["value"] == 812.75
    assert res.merge["sheets"]["Jio Platforms"]["parentPrice"]["asOf"]


def test_both_fail_keeps_previous(no_angel, monkeypatch):
    monkeypatch.setattr(yahoo, "_download", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    prev = make_prev()
    snapshot = copy.deepcopy(prev)
    res = parents.run(FakeSession(), prev, Result(module="parents"))
    assert not res.ok
    data = copy.deepcopy(prev)
    assemble.apply(data, res)
    assert data == snapshot
    assert data["sheets"]["Jio Platforms"]["parentPrice"]["value"] == 2900.0


def test_no_parent_tickers_is_not_success(no_angel):
    res = parents.run(FakeSession(), {"sheets": {"X": {"parent": "Y"}}}, Result(module="parents"))
    assert not res.ok and res.error["kind"] == "changed"
