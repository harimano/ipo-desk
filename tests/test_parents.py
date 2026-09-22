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


def test_nse_equity_lists_parse_both_header_spellings():
    import pathlib
    import pytest
    from collector.errors import SourceChanged
    from collector.sources import nse_symbols
    fx = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/live-2026-09-17"
    main = nse_symbols.parse((fx / "EQUITY_L.csv").read_text() * 3)      # the fixture keeps 39 rows; the floor is 50
    sme = nse_symbols.parse((fx / "SME_EQUITY_L.csv").read_text() * 3)
    assert main[0] == {"symbol": "20MICRONS", "name": "20 Microns Limited", "listedOn": "2008-10-06"} and sme[0]["symbol"] == "VINOD"
    for bad in ("", "A,B\n1,2\n", "SYMBOL,NAME OF COMPANY\nX,Y\n"):
        with pytest.raises(SourceChanged):
            nse_symbols.parse(bad)


def test_investor_symbols_are_remembered_and_the_list_is_only_fetched_for_new_names():
    from collector.modules import parents
    from collector.result import Result

    class S:
        calls = 0

        def get_text(self, url, **kw):
            S.calls += 1
            rows = "\n".join(f"SYM{i},Filler Company {i} Limited,EQ" for i in range(60))
            return "SYMBOL,NAME OF COMPANY, SERIES\nASIANENE,Asian Energy Services Limited,EQ\n" + rows + "\n"

    prev = {"investors": {"moves": [{"stock": "Asian Energy"}, {"stock": "Beta Drugs"}, {"stock": "Nowhere Listed Co"}],
                          "prices": {"Beta Drugs": {"symbol": "BETA", "value": 1, "asOf": "2026-09-16"}}}}
    res = Result(module="parents")
    got = parents.resolve_symbols(S(), prev, res)
    assert got == {"Beta Drugs": "BETA", "Asian Energy": "ASIANENE"} and S.calls == 2
    assert any("Nowhere Listed Co" in u for u in res.unresolved)
    S.calls = 0
    prev["investors"]["moves"] = prev["investors"]["moves"][:2]
    prev["investors"]["prices"]["Asian Energy"] = {"symbol": "ASIANENE"}
    assert parents.resolve_symbols(S(), prev, Result(module="parents")) == {"Asian Energy": "ASIANENE", "Beta Drugs": "BETA"}
    assert S.calls == 0, "every name already resolved: no fetch"


def test_every_live_quota_parent_is_priced_in_the_same_batch(no_angel, monkeypatch):
    monkeypatch.setattr(yahoo, "_download", lambda tickers, days: yahoo_frame(BARS, tickers))
    prev = make_prev()
    prev["quota"] = [{"name": "SBI Funds Management", "parent": "SBI", "ticker": "SBIN.NS", "bucket": "drhp"},
                     {"name": "Old Listing", "parent": "Gone Co", "ticker": "RELIANCE", "bucket": "done"},
                     {"name": "No Ticker", "parent": "Mystery", "bucket": "awaited"}]
    assert parents.quota_parents(prev) == {"SBI": "SBIN"}, "live rows with a ticker only; .NS stripped"
    res = parents.run(FakeSession(), prev, Result(module="parents"))
    assert res.ok and res.merge["investors"]["prices"]["SBI"] == {"symbol": "SBIN", "value": 815.3, "asOf": "2026-09-16"}
    assert res.merge["sheets"]["Jio Platforms"]["parentPrice"]["value"] == 2955.9, "the sheets' own prices are untouched by it"
