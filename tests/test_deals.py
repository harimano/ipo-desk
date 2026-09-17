"""Offline tests for collector.modules.deals and sources/nsearchives."""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from _support import FakeSession, blocked, fixture

from collector import assemble
from collector.errors import SourceChanged
from collector.modules import deals
from collector.result import Result
from collector.sources import nsearchives

BULK = fixture("nsearchives", "bulk.csv")
BLOCK = fixture("nsearchives", "block.csv")


def make_prev() -> dict:
    return {
        "investors": {
            "watchlist": ["Ashish Kacholia", {"name": "Mukul Agrawal", "aliases": ["Param Capital"]}],
            "bulkDeals": [
                {"date": "2026-09-10", "investor": "Ashish Kacholia", "vehicle": "ASHISH KACHOLIA", "stock": "XYZ",
                 "side": "BUY", "qty": 100000, "price": 50.0, "valueCr": 0.5, "exchange": "NSE", "source": "nsearchives bulk.csv"},
                {"date": "2026-06-01", "investor": "Vijay Kedia", "vehicle": "KEDIA SECURITIES PVT LTD", "stock": "OLD",
                 "side": "SELL", "qty": 1, "price": 1.0, "valueCr": 0.0, "exchange": "NSE", "source": "nsearchives bulk.csv"},
                # same deal as in today's bulk.csv -> must not duplicate
                {"date": "2026-09-16", "investor": "Ashish Kacholia", "vehicle": "ASHISH KACHOLIA", "stock": "ORIENTTECH",
                 "side": "BUY", "qty": 520000, "price": 312.45, "valueCr": 16.25, "exchange": "NSE", "source": "nsearchives bulk.csv"},
            ],
            "notes": ["sweep note"],
        }
    }


def session(bulk=BULK, block=BLOCK):
    return FakeSession(text={"/content/equities/bulk.csv": bulk, "/content/equities/block.csv": block})


# ---------------------------------------------------------------------------------------------
# source parser
# ---------------------------------------------------------------------------------------------
def test_parse_bulk_csv():
    rows = nsearchives.parse_deals_csv(BULK, "bulk")
    assert len(rows) == 6
    assert rows[0] == {"date": "2026-09-16", "symbol": "ORIENTTECH", "security": "Orient Technologies Limited",
                       "client": "ASHISH KACHOLIA", "side": "BUY", "qty": 520000.0, "price": 312.45}


def test_no_records_is_valid_empty():
    assert nsearchives.parse_deals_csv(BLOCK, "block") == []
    assert nsearchives.parse_deals_csv("  NO RECORDS  ", "block") == []


def test_parse_changed_shape_raises():
    with pytest.raises(SourceChanged):
        nsearchives.parse_deals_csv(fixture("nsearchives", "bulk_changed.csv"), "bulk")
    with pytest.raises(SourceChanged):
        nsearchives.parse_deals_csv("<html>blocked</html>", "bulk")
    with pytest.raises(SourceChanged):
        nsearchives.parse_deals_csv("", "bulk")


def test_parse_date_formats():
    assert nsearchives.parse_date("16-Sep-2026") == "2026-09-16"
    assert nsearchives.parse_date("16-SEP-2026") == "2026-09-16"
    assert nsearchives.parse_date("2026-09-16") == "2026-09-16"
    assert nsearchives.parse_date("16/09/2026") == "2026-09-16"
    assert nsearchives.parse_date("junk") is None


# ---------------------------------------------------------------------------------------------
# module
# ---------------------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _today(monkeypatch):
    class FakeDT(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 9, 17, 10, 0, tzinfo=tz)
    monkeypatch.setattr(deals.dt, "datetime", FakeDT)


def test_watchlist_and_vehicle_matches_merge_and_dedupe():
    prev = make_prev()
    snapshot = copy.deepcopy(prev)
    res = deals.run(session(), prev, Result(module="deals"))
    assert res.ok and res.source == "nsearchives" and res.asOf == "2026-09-16"
    assert set(res.merge) == {"investors"} and set(res.merge["investors"]) == {"bulkDeals"}
    rows = res.merge["investors"]["bulkDeals"]
    keys = [(r["date"], r["vehicle"], r["stock"], r["side"]) for r in rows]
    # today's watchlist hit (already in prev) appears exactly once
    assert keys.count(("2026-09-16", "ASHISH KACHOLIA", "ORIENTTECH", "BUY")) == 1
    # vehicle substring match, case-insensitive, attributed to the investor behind it
    bengal = next(r for r in rows if r["vehicle"] == "BENGAL FINANCE & INVESTMENT PVT LTD")
    assert bengal["investor"] == "Ashish Kacholia" and bengal["stock"] == "SAGILITY" and bengal["side"] == "BUY"
    assert bengal["qty"] == 4100000.0 and bengal["price"] == 48.10 and bengal["valueCr"] == 19.72
    assert bengal["exchange"] == "NSE" and bengal["source"] == "nsearchives bulk.csv"
    # untracked counterparties never enter the list
    assert not any(r["vehicle"].startswith(("GRAVITON", "QUANT", "MORGAN", "SAMAYAT")) for r in rows)
    # 45-day window: the June row is gone, the 10 Sep row stays; newest first
    dates = [r["date"] for r in rows]
    assert "2026-06-01" not in dates and "2026-09-10" in dates
    assert dates == sorted(dates, reverse=True)
    assert prev == snapshot
    data = copy.deepcopy(prev)
    assemble.apply(data, res)
    assert data["investors"]["notes"] == ["sweep note"], "only bulkDeals merged"
    assert data["investors"]["watchlist"] == prev["investors"]["watchlist"]


def test_vehicle_match_from_vehicles_json_without_watchlist():
    prev = {"investors": {"watchlist": [], "bulkDeals": []}}
    bulk = ("Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks\n"
            "16-Sep-2026,ABC,ABC Ltd,kedia securities private limited,SELL,10000,99.5,-\n"
            "16-Sep-2026,ABC,ABC Ltd,SOME OTHER FUND,BUY,10000,99.5,-\n")
    res = deals.run(session(bulk=bulk), prev, Result(module="deals"))
    assert res.ok
    rows = res.merge["investors"]["bulkDeals"]
    assert len(rows) == 1 and rows[0]["investor"] == "Vijay Kedia" and rows[0]["side"] == "SELL"


def test_both_no_records_is_ok_quiet_day():
    prev = make_prev()
    res = deals.run(session(bulk="NO RECORDS", block="NO RECORDS"), prev, Result(module="deals"))
    assert res.ok
    assert any("NO RECORDS" in n for n in res.notes)
    rows = res.merge["investors"]["bulkDeals"]
    assert [r["stock"] for r in rows] == ["ORIENTTECH", "XYZ"]     # prev re-emitted within 45 days


def test_one_csv_blocked_is_a_note_both_blocked_fails():
    prev = make_prev()
    res = deals.run(FakeSession(text={"bulk.csv": BULK, "block.csv": blocked("nsearchives")}), prev, Result(module="deals"))
    assert res.ok and any("block.csv: blocked" in n for n in res.notes)
    snapshot = copy.deepcopy(prev)
    res2 = deals.run(FakeSession(text={"bulk.csv": blocked("nsearchives"), "block.csv": blocked("nsearchives")}),
                     prev, Result(module="deals"))
    assert not res2.ok and res2.error["kind"] == "blocked"
    data = copy.deepcopy(prev)
    assemble.apply(data, res2)
    assert data == snapshot


def test_match_client_longest_pattern_wins():
    pats = [("kedia", "Someone Kedia"), ("kedia securities", "Vijay Kedia")]
    assert deals.match_client("KEDIA SECURITIES PVT LTD", pats) == "Vijay Kedia"
    assert deals.match_client("RANDOM LLP", pats) is None
