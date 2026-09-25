"""Offline tests for collector.modules.listings and the angelone / yahoo price sources."""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from _support import FakeSession, FakeSmartConnect, fixture_json, nan_frame, yahoo_frame

from collector import assemble
from collector.errors import SourceBlocked, SourceChanged, SourceDown
from collector.modules import listings
from collector.result import Result
from collector.sources import angelone, yahoo

TODAY = dt.date(2026, 9, 17)
BARS = fixture_json("yahoo", "bars.json")


def make_prev() -> dict:
    return {
        "mainboard": [
            {"name": "NewList Industries", "type": "Mainboard", "status": "Listed", "listing": "2026-09-10",
             "bandLow": 133, "bandHigh": 140, "gmp": 20, "sub": {"qib": 88.4, "total": 42.1}, "symbol": "NEWLIST",
             "sources": ["nse"]},
            {"name": "Upcoming Co", "type": "Mainboard", "status": "Upcoming", "listing": "2026-10-01",
             "bandHigh": 100, "symbol": "UPC"},
        ],
        "sme": [
            {"name": "SmeOne Ltd", "type": "NSE SME", "status": "Listed", "listing": "2026-09-16",
             "bandHigh": 95, "symbol": "SMEONE", "sources": []},
            {"name": "Listed Today Ltd", "type": "NSE SME", "status": "Listed", "listing": "2026-09-17",
             "bandHigh": 60, "symbol": "TODAYL", "sources": []},
        ],
        "recent": [
            {"name": "NewList Industries", "type": "Mainboard", "listingDate": "2026-09-10", "issuePrice": 140,
             "listingPrice": None, "gainPct": None, "closeDay1": None, "closeDay1GainPct": None, "sources": []},
            {"name": "Old Listing", "type": "Mainboard", "listingDate": "2026-07-01", "issuePrice": 50,
             "symbol": "OLDL", "sources": []},
        ],
        "lot": {"Reliance Industries": {"shares": 5, "price": 2940, "listDate": "2025-01-01", "symbol": "RELIANCE"}},
        "priceHistory": {"NewList Industries": [["2026-09-15", 162.8], ["2026-09-16", 165.1]]},
        "listedPerf": [{"name": "Earlier Co", "issue": 100, "gmpImplied": 110, "listing": 120}],
        "comps": [],
    }


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(listings, "today_ist", lambda: TODAY)
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
    monkeypatch.setenv("ANGEL_API_KEY", "k")
    monkeypatch.setenv("ANGEL_CLIENT_CODE", "C123")
    monkeypatch.setenv("ANGEL_PIN", "0000")
    monkeypatch.setenv("ANGEL_TOTP_SECRET", "JBSWY3DPEHPK3PXP")


def patch_yahoo(monkeypatch, fn=None):
    monkeypatch.setattr(yahoo, "_download", fn or (lambda tickers, days: yahoo_frame(BARS, tickers)))


def run_module(prev):
    res = listings.run(FakeSession(), prev, Result(module="listings"))
    return res


# ---------------------------------------------------------------------------------------------
# chain behaviour
# ---------------------------------------------------------------------------------------------
def test_yahoo_wins_when_angelone_not_configured(no_angel, monkeypatch):
    patch_yahoo(monkeypatch)
    prev = make_prev()
    snapshot = copy.deepcopy(prev)
    res = run_module(prev)
    assert res.ok and res.source == "yahoo"
    assert res.tried[0]["source"] == "angelone" and res.tried[0]["kind"] == "down"
    assert "not configured" in res.tried[0]["detail"]
    assert prev == snapshot, "prev must never be mutated"
    # ownership: replace only owned keys, rows only mainboard/sme
    data = copy.deepcopy(prev)
    assemble.apply(data, res)
    assert set(res.replace) == {"recent", "priceHistory"}          # listedPerf / comps belong to `history`


def test_board_row_patch_and_recent_row(no_angel, monkeypatch):
    patch_yahoo(monkeypatch)
    res = run_module(make_prev())
    patch = res.rows["mainboard"]["NewList Industries"]
    assert patch["listingPrice"] == 150.0                 # listing-day open 2026-09-10
    assert patch["listingGainPct"] == 7.14                # vs bandHigh 140
    assert patch["currentPrice"] == 165.1                 # latest close
    assert "Upcoming Co" not in res.rows["mainboard"]
    # SME listed yesterday: patched from its listing-day bar and moved to recent (but not listedPerf)
    assert res.rows["sme"]["SmeOne Ltd"]["listingPrice"] == 101.0
    names = [r["name"] for r in res.replace["recent"]]
    assert "SmeOne Ltd" in names
    # listed today with no bar yet: no patch, not moved, no guess
    assert "Listed Today Ltd" not in res.rows.get("sme", {})
    assert "Listed Today Ltd" not in names


def test_recent_dedupe_by_name_and_cutoff(no_angel, monkeypatch):
    patch_yahoo(monkeypatch)
    res = run_module(make_prev())
    recent = res.replace["recent"]
    names = [r["name"] for r in recent]
    assert names.count("NewList Industries") == 1, "board row + prev recent row must collapse to one"
    assert "Old Listing" not in names, "older than 28 days drops out"
    row = next(r for r in recent if r["name"] == "NewList Industries")
    assert row["listingPrice"] == 150.0 and row["closeDay1"] == 157.3
    assert row["gainPct"] == 7.14 and row["closeDay1GainPct"] == 12.36
    assert row["listingDate"] == "2026-09-10" and row["issuePrice"] == 140



def test_price_history_no_duplicate_dates(no_angel, monkeypatch):
    patch_yahoo(monkeypatch)
    res = run_module(make_prev())
    ph = res.replace["priceHistory"]
    newlist = ph["NewList Industries"]
    assert [p[0] for p in newlist] == ["2026-09-15", "2026-09-16"], "2026-09-16 already present: not appended twice"
    assert ph["Reliance Industries"] == [["2026-09-16", 2955.9]]        # lot name gets a point
    assert ph["SmeOne Ltd"] == [["2026-09-16", 103.2]]
    # run again on the produced data: still one point per date
    prev2 = make_prev()
    prev2["priceHistory"] = copy.deepcopy(ph)
    res2 = run_module(prev2)
    assert res2.replace["priceHistory"]["Reliance Industries"] == [["2026-09-16", 2955.9]]


def test_both_sources_fail_keeps_previous(no_angel, monkeypatch):
    patch_yahoo(monkeypatch, lambda tickers, days: (_ for _ in ()).throw(RuntimeError("boom")))
    prev = make_prev()
    snapshot = copy.deepcopy(prev)
    res = run_module(prev)
    assert not res.ok
    assert [t["source"] for t in res.tried][:2] == ["angelone", "yahoo"]   # fail() re-records the last
    assert res.error["source"] == "yahoo"
    assert prev == snapshot
    data = copy.deepcopy(prev)
    assemble.apply(data, res)
    assert data == snapshot, "a failed module leaves the document untouched"


def test_angelone_wins_when_configured(angel_env, monkeypatch):
    candles = fixture_json("angelone", "candles.json")
    fake = FakeSmartConnect(candles=candles)
    monkeypatch.setattr(angelone, "_connect", lambda api_key: fake)
    monkeypatch.setattr(listings, "_bars_yahoo", lambda *a: (_ for _ in ()).throw(AssertionError("yahoo must not be called")))
    session = FakeSession(json_={"OpenAPIScripMaster.json": fixture_json("angelone", "instrument_master.json")})
    res = listings.run(session, make_prev(), Result(module="listings"))
    assert res.ok and res.source == "angelone"
    assert ("login", "C123") in fake.calls
    assert res.rows["mainboard"]["NewList Industries"]["listingPrice"] == 160.0     # candle open on 09-10
    assert res.rows["mainboard"]["NewList Industries"]["currentPrice"] == 180.3
    assert res.asOf == "2026-09-16"
    # instrument master fetched exactly once for the run
    assert sum("OpenAPIScripMaster" in c for c in session.calls) == 1


def test_angelone_sdk_error_falls_through_to_yahoo(angel_env, monkeypatch):
    fake = FakeSmartConnect(raise_on={"candles"})
    monkeypatch.setattr(angelone, "_connect", lambda api_key: fake)
    patch_yahoo(monkeypatch)
    session = FakeSession(json_={"OpenAPIScripMaster.json": fixture_json("angelone", "instrument_master.json")})
    res = listings.run(session, make_prev(), Result(module="listings"))
    assert res.ok and res.source == "yahoo"
    assert res.tried[0]["source"] == "angelone" and res.tried[0]["kind"] in ("blocked", "down")


def test_rows_without_symbol_are_unresolved_not_guessed(no_angel, monkeypatch):
    patch_yahoo(monkeypatch)
    prev = make_prev()
    del prev["mainboard"][0]["symbol"]
    prev["recent"] = []
    res = run_module(prev)
    assert res.ok
    assert "NewList Industries" not in res.rows.get("mainboard", {})
    assert any("NewList Industries" in u for u in res.unresolved)


# ---------------------------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------------------------
def test_yahoo_all_nan_batch_raises_changed(monkeypatch):
    patch_yahoo(monkeypatch, lambda tickers, days: nan_frame(tickers))
    with pytest.raises(SourceChanged):
        yahoo.daily_closes(["NEWLIST.NS", "SMEONE"], 10)


def test_yahoo_rate_limit_backoff_then_blocked(monkeypatch):
    from yfinance.exceptions import YFRateLimitError
    calls = []

    def dl(tickers, days):
        calls.append(1)
        raise YFRateLimitError()
    patch_yahoo(monkeypatch, dl)
    with pytest.raises(SourceBlocked):
        yahoo.daily_closes(["NEWLIST"], 10)
    assert len(calls) == 1 + len(yahoo.BACKOFF)


def test_yahoo_daily_closes_shape(monkeypatch):
    patch_yahoo(monkeypatch)
    out = yahoo.daily_closes(["NEWLIST", "SMEONE.NS"], 10)
    assert out["NEWLIST"][0] == ["2026-09-10", 157.3]
    assert out["SMEONE"][-1] == ["2026-09-16", 103.2]


def test_angelone_not_configured_raises_down_before_sdk(no_angel, monkeypatch):
    monkeypatch.setattr(angelone, "_connect", lambda api_key: (_ for _ in ()).throw(AssertionError("SDK touched")))
    with pytest.raises(SourceDown) as ei:
        angelone.login()
    assert ei.value.detail == "not configured"
    with pytest.raises(SourceDown):
        angelone.instrument_master(FakeSession())


def test_angelone_instrument_master_filters_nse(angel_env):
    session = FakeSession(json_={"OpenAPIScripMaster.json": fixture_json("angelone", "instrument_master.json")})
    m = angelone.instrument_master(session)
    assert m["RELIANCE"]["token"] == "2885" and m["RELIANCE"]["series"] == "EQ"     # NSE row, not the BSE one
    assert m["SMEONE"]["series"] == "SM"
    assert "NIFTY" not in m


def test_angelone_instrument_master_changed_shape(angel_env):
    session = FakeSession(json_={"OpenAPIScripMaster.json": [{"exch_seg": "BSE", "symbol": "X", "token": "1", "name": "X"}]})
    with pytest.raises(SourceChanged):
        angelone.instrument_master(session)


def test_angelone_login_status_false_is_source_error(angel_env, monkeypatch):
    monkeypatch.setattr(angelone, "_connect", lambda api_key: FakeSmartConnect(login_ok=False))
    with pytest.raises((SourceDown, SourceBlocked)) as ei:
        angelone.login()
    assert "0000" not in str(ei.value) and "JBSWY3DPEHPK3PXP" not in str(ei.value)


def test_angelone_ltp(angel_env, monkeypatch):
    fake = FakeSmartConnect()
    monkeypatch.setattr(angelone, "_connect", lambda api_key: fake)
    session = FakeSession(json_={"OpenAPIScripMaster.json": fixture_json("angelone", "instrument_master.json")})
    out = angelone.ltp(["RELIANCE", "SBIN.NS", "NOSUCH"], session)
    assert out == {"RELIANCE": 2951.4, "SBIN": 812.75}


def test_yahoo_one_empty_batch_keeps_the_others(monkeypatch):
    """25 Sep 2026: VIVEKANAND alone in the last batch came back empty and threw away every name that priced."""
    import pandas as pd
    monkeypatch.setattr(yahoo, "BATCH", 2)
    patch_yahoo(monkeypatch, lambda tickers, days: pd.DataFrame() if "VIVEKANAND.NS" in tickers else yahoo_frame(BARS, tickers))
    out = yahoo.daily_closes(["NEWLIST", "SMEONE", "VIVEKANAND"], 10)
    assert set(out) == {"NEWLIST", "SMEONE"}


def test_yahoo_every_batch_empty_still_raises_changed(monkeypatch):
    import pandas as pd
    monkeypatch.setattr(yahoo, "BATCH", 1)
    patch_yahoo(monkeypatch, lambda tickers, days: pd.DataFrame())
    with pytest.raises(SourceChanged):
        yahoo.daily_closes(["NEWLIST", "SMEONE"], 10)
