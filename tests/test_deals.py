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
    assert set(res.merge) == {"investors"} and set(res.merge["investors"]) == {"bulkDeals", "listingDeals", "listingSymbols"}
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
    assert data["investors"]["notes"] == ["sweep note"], "only the deals keys merged"
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


# ---------------------------------------------------------------------------------------------
# listingDeals — every deal in one of this year's listings (real files of 21 Sep 2026)
# ---------------------------------------------------------------------------------------------
LIVE = "live-2026-09-21"
# full paths: "EQUITY_L.csv" alone is a substring of the SME list's URL too
MAIN_LIST, SME_LIST = "/content/equities/EQUITY_L.csv", "/emerge/corporates/content/SME_EQUITY_L.csv"


def listing_doc() -> dict:
    """Today's document as the assembler has it when deals runs: history's listedPerf + the board."""
    return {
        "listedPerf": [
            {"name": "Glass Wall Systems", "date": "2026-09-16", "sme": False, "issue": 182.0},
            {"name": "Kanohar Electricals", "date": "2026-09-16", "sme": False, "issue": 632.0},
            {"name": "Qualiance International", "date": "2026-09-11", "sme": True, "issue": 127.0},
            {"name": "Vinod Texworld", "date": "2026-09-17", "sme": True, "issue": None},
            {"name": "Some BSE SME", "date": "2026-09-10", "sme": True, "issue": 50.0},
            {"name": "Old Listing", "date": "2025-12-30", "sme": False, "issue": 100.0},
        ],
        "mainboard": [{"name": "Veegaland Developers", "status": "Listed", "listing": "2026-09-18", "symbol": "VEEGALAND", "bandHigh": 140},
                      {"name": "Not Yet", "status": "Closed", "listing": "2026-09-25", "symbol": None, "bandHigh": 10}],
        "sme": [{"name": "Maharaja & Speedex India", "status": "Listed", "listing": "2026-09-18", "symbol": "SPEEDEX", "bandHigh": 186}],
    }


def live_session(**extra):
    text = {"/content/equities/bulk.csv": fixture(LIVE, "bulk.csv"), "/content/equities/block.csv": fixture(LIVE, "block.csv"),
            MAIN_LIST: fixture(LIVE, "EQUITY_L.csv"), SME_LIST: fixture(LIVE, "SME_EQUITY_L.csv")}
    text.update(extra)
    return FakeSession(text=text)


def run_listing(prev=None, doc=None, sess=None):
    prev = prev if prev is not None else {"investors": {"watchlist": [], "bulkDeals": []}}
    res = Result(module="deals"); res.doc = doc if doc is not None else listing_doc()
    return deals.run(sess or live_session(), prev, res), res


def test_this_years_listings_come_from_listedperf_and_the_board():
    L = deals.this_years_listings(listing_doc(), dt.date(2026, 9, 21))
    assert "Old Listing" not in L and "Not Yet" not in L
    assert L["Veegaland Developers"] == {"listedOn": "2026-09-18", "issuePrice": 140.0, "sme": False, "symbol": "VEEGALAND"}
    assert L["Maharaja & Speedex India"]["sme"] is True and L["Maharaja & Speedex India"]["symbol"] == "SPEEDEX"
    assert L["Glass Wall Systems"]["symbol"] is None and L["Glass Wall Systems"]["issuePrice"] == 182.0


def test_listing_deals_from_the_real_files():
    res, _ = run_listing()
    assert res.ok
    inv = res.merge["investors"]
    rows = inv["listingDeals"]
    # the NSE lists were fetched once (both files) because names needed resolving
    assert res.calls == 2
    syms = inv["listingSymbols"]
    assert syms["Glass Wall Systems"] == {"symbol": "GLASSWALL", "triedOn": "2026-09-17"}
    assert syms["Qualiance International"]["symbol"] == "QUALIANCE" and syms["Vinod Texworld"]["symbol"] == "VINOD"
    assert syms["Some BSE SME"] == {"symbol": None, "triedOn": "2026-09-17"}
    assert "Old Listing" not in syms and syms["Veegaland Developers"]["symbol"] == "VEEGALAND"
    stocks = {r["stock"] for r in rows}
    assert stocks == {"Glass Wall Systems", "Kanohar Electricals", "Qualiance International", "Veegaland Developers"}
    # 21 Sep: Glass Wall listed 16 Sep — 19 buys and 19 sells, every one a prop-desk round trip
    gw = [r for r in rows if r["stock"] == "Glass Wall Systems"]
    assert len(gw) == 38 and sum(r["side"] == "BUY" for r in gw) == 19
    r = next(x for x in gw if x["client"] == "PLUTUS WEALTH MANAGEMENT LLP" and x["side"] == "BUY")
    assert r == {"date": "2026-09-21", "symbol": "GLASSWALL", "stock": "Glass Wall Systems", "client": "PLUTUS WEALTH MANAGEMENT LLP",
                 "side": "BUY", "qty": 3978937.0, "price": 280.77, "valueCr": 111.72, "exchange": "NSE", "kind": "bulk",
                 "sme": False, "listedOn": "2026-09-16", "daysSinceListing": 5, "issuePrice": 182.0, "vsIssuePct": 54.3}
    q = next(x for x in rows if x["stock"] == "Qualiance International" and x["side"] == "BUY")
    assert q["sme"] is True and q["daysSinceListing"] == 10 and q["vsIssuePct"] == 43.9
    assert all(r["sme"] in (True, False) for r in rows), "segment rides on every row — never pooled"
    # newest first, then by stock
    assert [r["date"] for r in rows] == sorted((r["date"] for r in rows), reverse=True)
    assert any("of today's 217 deals are in this year's listings (4 stocks)" in n for n in res.notes)


def test_listing_symbols_are_remembered_and_lists_not_refetched():
    prev = {"investors": {"watchlist": [], "bulkDeals": [], "listingSymbols": {
        "Glass Wall Systems": {"symbol": "GLASSWALL", "triedOn": "2026-09-16"},
        "Kanohar Electricals": {"symbol": "KANOHAR", "triedOn": "2026-09-16"},
        "Qualiance International": {"symbol": "QUALIANCE", "triedOn": "2026-09-11"},
        "Vinod Texworld": {"symbol": "VINOD", "triedOn": "2026-09-17"},
        "Some BSE SME": {"symbol": None, "triedOn": "2026-09-15"},          # missed 2 days ago: not due yet
        "Gone": {"symbol": "GONE", "triedOn": "2026-01-01"},               # no longer this year's listing: dropped
    }}}
    sess = live_session(**{MAIN_LIST: blocked("nsearchives"), SME_LIST: blocked("nsearchives")})
    res, _ = run_listing(prev=prev, sess=sess)
    assert res.ok and res.calls == 0 and not any("EQUITY_L" in c for c in sess.calls)
    inv = res.merge["investors"]
    assert "Gone" not in inv["listingSymbols"] and inv["listingSymbols"]["Some BSE SME"]["triedOn"] == "2026-09-15"
    assert {r["stock"] for r in inv["listingDeals"]} >= {"Glass Wall Systems", "Kanohar Electricals"}


def test_a_miss_is_retried_after_a_week_and_the_lists_being_down_is_a_note():
    prev = {"investors": {"watchlist": [], "bulkDeals": [], "listingSymbols": {
        "Some BSE SME": {"symbol": None, "triedOn": "2026-09-01"}}}}
    sess = live_session(**{MAIN_LIST: blocked("nsearchives"), SME_LIST: blocked("nsearchives")})
    res, _ = run_listing(prev=prev, sess=sess)
    assert res.ok and any("NSE equity lists unavailable (blocked)" in n for n in res.notes)
    assert res.merge["investors"]["listingDeals"] and {r["stock"] for r in res.merge["investors"]["listingDeals"]} == {"Veegaland Developers"}
    assert res.merge["investors"]["listingSymbols"]["Some BSE SME"]["triedOn"] == "2026-09-01", "a failed lookup is not a fresh try"


def test_fuzzy_hit_on_an_old_company_is_rejected():
    doc = {"listedPerf": [{"name": "20 Microns", "date": "2026-09-10", "sme": False, "issue": 10.0}], "mainboard": [], "sme": []}
    res, _ = run_listing(doc=doc)
    assert res.ok and res.merge["investors"]["listingSymbols"]["20 Microns"]["symbol"] is None


def test_listing_deals_merge_dedupes_and_keeps_60_days():
    prev = {"investors": {"watchlist": [], "bulkDeals": [], "listingSymbols": {}, "listingDeals": [
        # same deal as today's file -> once
        {"date": "2026-09-21", "symbol": "VEEGALAND", "stock": "Veegaland Developers", "client": "NEO APEX SHARE BROKING SERVICES LLP",
         "side": "SELL", "qty": 300004.0, "price": 138.99, "valueCr": 4.17, "exchange": "NSE", "kind": "bulk", "sme": False},
        {"date": "2026-08-01", "symbol": "OLDER", "stock": "Older", "client": "X", "side": "BUY", "qty": 1, "price": 1, "sme": True},
        {"date": "2026-07-01", "symbol": "GONE", "stock": "Gone", "client": "X", "side": "BUY", "qty": 1, "price": 1, "sme": True},
    ]}}
    res, _ = run_listing(prev=prev)
    rows = res.merge["investors"]["listingDeals"]
    keys = [(r["date"], r["symbol"], r["client"], r["side"], r["qty"]) for r in rows]
    assert keys.count(("2026-09-21", "VEEGALAND", "NEO APEX SHARE BROKING SERVICES LLP", "SELL", 300004.0)) == 1
    assert "Older" in {r["stock"] for r in rows} and "Gone" not in {r["stock"] for r in rows}
    # the re-emitted prev row picked up the fields today's computation adds
    v = next(r for r in rows if r["symbol"] == "VEEGALAND" and r["side"] == "SELL")
    assert v["daysSinceListing"] == 3 and v["issuePrice"] == 140.0


def test_quiet_day_keeps_previous_listing_deals():
    prev = {"investors": {"watchlist": [], "bulkDeals": [], "listingSymbols": {}, "listingDeals": [
        {"date": "2026-09-18", "symbol": "VEEGALAND", "stock": "Veegaland Developers", "client": "X", "side": "BUY", "qty": 1, "price": 1, "sme": False}]}}
    res, _ = run_listing(prev=prev, sess=live_session(**{"/content/equities/bulk.csv": "NO RECORDS", "/content/equities/block.csv": "NO RECORDS"}))
    assert res.ok and [r["date"] for r in res.merge["investors"]["listingDeals"]] == ["2026-09-18"]


def test_caps_trim_listing_deals():
    from collector import schema
    data = schema.empty_data()
    data["investors"]["listingDeals"] = [{"date": "2026-09-20", "symbol": "A"}, {"date": "2026-06-01", "symbol": "B"}]
    assemble.enforce_caps(data)
    assert [r["symbol"] for r in data["investors"]["listingDeals"]] == ["A"]
