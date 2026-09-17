import datetime as dt
import json
import pathlib

import pytest

from collector.errors import SourceChanged, SourceDown
from collector.modules import anchors
from collector.pdf import anchor as letter        # a bench tool for the research layer; no workflow calls it
from collector.result import Result
from collector.sources import investorgain

ROOT = pathlib.Path(__file__).resolve().parent.parent
SONA = (ROOT / "data/fixtures/anchor/SONA-letter-text.txt").read_text()
TODAY = dt.date(2026, 9, 17)


def test_real_letter_text_every_row_adds_up():
    book = letter.parse_text(SONA)
    assert book["date"] == "2026-09-16" and book["price"] == 99 and book["totalShares"] == 4290000
    assert [(i["name"], i["shares"], i["amountCr"]) for i in book["investors"]] == [
        ("ASTORNE CAPITAL VCC - ARVEN", 2296350, 22.73), ("INDIA MAX INVESTMENT FUND LIMITED", 996900, 9.87),
        ("LORDS MULTIGROWTH FUND", 996750, 9.87)]
    assert book["dropped"] == 0 and abs(sum(i["pct"] for i in book["investors"]) - 100) < 0.01


def test_a_misread_digit_is_dropped_and_a_partial_book_is_refused():
    one_bad = SONA.replace("9,96,750", "9,98,750")            # OCR-style slip: shares x price no longer equals the amount
    with pytest.raises(SourceChanged) as e:
        letter.parse_text(one_bad)                            # 77% coverage: refuse rather than publish a partial book
    assert "refusing a partial book" in str(e.value)
    with pytest.raises(SourceChanged):
        letter.parse_text("x" * 50)
    with pytest.raises(SourceChanged):
        letter.parse_text("Dear Sir, " * 60)


def test_categories():
    c = letter.category
    assert c("SBI Mutual Fund - SBI Small Cap Fund") == "MF" and c("ICICI Prudential Life Insurance Company") == "Insurance"
    assert c("Government of Singapore") == "Pension/Sovereign" and c("Nomura Singapore Limited ODI") == "FPI"
    assert c("WhiteOak Capital Equity Fund") == "AIF" and c("Motilal Oswal Finvest Ltd") == "Other"


# ------------------------------------------------------------------------------------------
# the module: fetched facts only — InvestorGain's calendar (JSON) + NSE's issue information (JSON)
# ------------------------------------------------------------------------------------------
LIVE = ROOT / "data/fixtures/live-2026-09-17"
CALENDAR = json.loads((LIVE / "ig_report480.json").read_text())
NSE_DETAIL = json.loads((LIVE / "nse_ipo-detail-NSE.json").read_text())


class FakeSession:
    """get_json answers InvestorGain's report; nse_json answers ipo-detail by symbol. An Exception is raised."""

    def __init__(self, calendar=CALENDAR, details=None):
        self.calendar, self.details, self.calls = calendar, details or {}, []

    def get_json(self, url, *, source=None, headers=None, **kw):
        self.calls.append("calendar")
        if isinstance(self.calendar, Exception):
            raise self.calendar
        return self.calendar

    def nse_json(self, path, params=None, *, source="nse", referer=None):
        sym = (params or {}).get("symbol")
        self.calls.append(f"detail:{sym}")
        v = self.details.get(sym, SourceDown("nse", "HTTP 404", path, 404))
        if isinstance(v, Exception):
            raise v
        return v

    def get_bytes(self, *a, **kw):                      # the module must never fetch a document
        raise AssertionError("anchors fetched a file")


def prev():
    return {"mainboard": [
                {"name": "NSE (National Stock Exchange of India)", "symbol": "NSE", "series": "EQ", "open": "2026-09-17",
                 "bandHigh": 1785.0, "type": "Mainboard", "status": "Open"},
                {"name": "Hero Motors", "symbol": "HEROMOTORS", "open": "2026-09-16", "bandHigh": 84.0, "type": "Mainboard", "status": "Open"},
                {"name": "Kanohar Electricals", "symbol": "KANOHAR", "open": "2026-09-08", "bandHigh": 632.0, "type": "Mainboard", "status": "Listed"}],
            "sme": [{"name": "Shakti Polytarp", "open": "2026-09-15", "bandHigh": 59.0, "type": "BSE SME", "status": "Open"}],
            "anchors": [{"name": "Kanohar Electricals", "source": "nse-anchor-letter", "date": "2026-09-05", "amountCr": 316.72,
                         "issueSizeCr": 1055.74, "count": 42, "topTierShare": 66.69, "anchor": "read from the letter",
                         "investors": [{"name": "SBI MF", "cat": "MF", "amountCr": 40, "pct": 12.6}], "anchorShares": 5011000},
                        {"name": "Deepa Jewellers", "anchor": "hand-written in the db era", "date": "2026-08-31", "amountCr": 137.91,
                         "investors": [{"name": "y"}]}]}


def test_book_size_and_dates_come_from_json_and_no_file_is_touched():
    s = FakeSession(details={"NSE": NSE_DETAIL})
    res = anchors.run(s, prev(), Result(module="anchors"), today=TODAY)
    assert res.ok, res.error
    rows = {r["name"]: r for r in res.replace["anchors"]}

    nse = rows["NSE (National Stock Exchange of India)"]           # the calendar calls it "NSE": data/aliases.json
    assert nse["anchorShares"] == 37793739 and nse["amountCr"] == 6746.18, "37,793,739 x 1,785 — the letter's own total"
    assert (nse["date"], nse["lockIn30"], nse["lockIn90"]) == ("2026-09-16", "2026-10-21", "2026-12-20")
    assert nse["issueSizeCr"] == 22561.57 and nse["investors"] == [] and nse["topTierShare"] is None
    assert "30% of the issue" in nse["anchor"] and "lock-in ends 21 Oct" in nse["anchor"]
    assert any("nseindia.com" in u for u in nse["sources"]) and any("investorgain.com" in u for u in nse["sources"])

    hero = rows["Hero Motors"]                                      # NSE had no answer for it: dates still arrive
    assert hero["date"] == "2026-09-15" and hero["lockIn30"] == "2026-10-21" and hero["amountCr"] is None

    assert rows["Shakti Polytarp"]["date"] == "2026-09-11", "a BSE-only issue gets its dates without an NSE symbol"
    assert "detail:None" not in s.calls and s.calls.count("calendar") == 1


def test_rows_that_already_carry_a_book_keep_every_word_of_it():
    before = prev()
    res = anchors.run(FakeSession(details={"NSE": NSE_DETAIL}), before, Result(module="anchors"), today=TODAY)
    rows = {r["name"]: r for r in res.replace["anchors"]}
    kan, was = rows["Kanohar Electricals"], before["anchors"][0]
    for k in ("investors", "topTierShare", "count", "amountCr", "anchor", "source", "issueSizeCr"):
        assert kan[k] == was[k], k
    assert kan["lockIn30"] and kan["lockIn90"], "the calendar's lock-in dates are added to a letter-read row"
    assert rows["Deepa Jewellers"]["anchor"] == "hand-written in the db era" and rows["Deepa Jewellers"]["amountCr"] == 137.91


def test_a_name_match_without_agreeing_dates_is_ignored():
    p = prev()
    p["mainboard"][1]["open"] = "2026-11-02"                        # a different Hero Motors issue, months later
    res = anchors.run(FakeSession(details={"NSE": NSE_DETAIL}), p, Result(module="anchors"), today=TODAY)
    assert "Hero Motors" not in {r["name"] for r in res.replace["anchors"]}


def test_the_anchor_portion_is_asked_for_once():
    s1 = FakeSession(details={"NSE": NSE_DETAIL})
    first = anchors.run(s1, prev(), Result(module="anchors"), today=TODAY)
    assert "detail:NSE" in s1.calls and "detail:KANOHAR" not in s1.calls, "Kanohar's portion is on file; it opened 9 days ago anyway"
    again = {**prev(), "anchors": first.replace["anchors"]}
    s2 = FakeSession(details={"NSE": AssertionError("asked twice")})
    assert anchors.run(s2, again, Result(module="anchors"), today=TODAY).ok
    assert "detail:NSE" not in s2.calls


def test_failure_modes():
    down = SourceDown("investorgain", "HTTP 503", "u", 503)
    # calendar down, NSE fine: sizes still arrive, the module succeeds and says what it could not do
    res = anchors.run(FakeSession(calendar=down, details={"NSE": NSE_DETAIL}), prev(), Result(module="anchors"), today=TODAY)
    assert res.ok and any("calendar unavailable" in n for n in res.notes)
    # everything down: nothing is replaced, the previous section stays
    res = anchors.run(FakeSession(calendar=down), prev(), Result(module="anchors"), today=TODAY)
    assert not res.ok and res.replace == {}
    # a changed shape fails loudly rather than emptying the dates
    with pytest.raises(SourceChanged):
        investorgain.parse_anchor_calendar({"msg": 1, "reportTableData": [{"IPO": "X", "Nothing": "useful"}]})
    with pytest.raises(SourceChanged):
        investorgain.parse_anchor_calendar({"msg": "API not found"})


def test_real_scanned_letters_ocr_text():
    """OCR text of two real scans (Tesseract on a GitHub runner, 17 Sep 2026)."""
    hero = letter.parse_text((ROOT / "data/fixtures/anchor/HEROMOTORS-letter-ocr.txt").read_text())
    assert hero["partial"] is False and hero["coverage"] >= 0.90 and hero["price"] == 84 and hero["totalShares"] == 35714284
    assert hero["stated"] == {"mf": {"pct": 81.66, "count": 7}, "insurancePension": {"pct": 6.67, "count": 2}}
    assert all(abs(i["shares"] * 84 - i["amountCr"] * 1e7) < 1e5 for i in hero["investors"])

    nse = letter.parse_text((ROOT / "data/fixtures/anchor/NSE-letter-ocr.txt").read_text())
    assert nse["partial"] is True and 0.5 <= nse["coverage"] < 0.9
    assert nse["amountCr"] == round(37793739 * 1785 / 1e7, 2), "a partial book carries the issuer's total, not our sum"
    assert nse["stated"]["mf"] == {"pct": 36.98, "count": 29} and nse["stated"]["insurancePension"]["pct"] == 16.04
