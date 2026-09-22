"""anchorbook — every IPO's anchor allocation, frozen. Fixtures: real records (Jindal Supreme full; Shadowfax, truncated by the feed)."""
import datetime as dt
import json
import pathlib

from collector import assemble, layout, schema
from collector.errors import SourceBlocked, SourceDown
from collector.modules import anchorbook
from collector.result import Result
from collector.sources import investorgain as ig

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/investorgain"
JINDAL = json.loads((FX / "ipo-detail-2057-JINDAL-full.json").read_text())
SHADOW = json.loads((FX / "ipo-detail-1599-SHADOWFAX-anchors.json").read_text())
TODAY = dt.date(2026, 9, 22)


class S:
    def __init__(self, blocked=False, fail=()):
        self.blocked, self.fail, self.calls = blocked, set(fail), []

    def get_json(self, url, *, source=None, headers=None, **kw):
        self.calls.append(url)
        i = url.rstrip("/").rsplit("/", 1)[1]
        if self.blocked:
            raise SourceBlocked("investorgain", "HTTP 403", url, 403)
        if i in self.fail:
            raise SourceDown("investorgain", "HTTP 503", url, 503)
        if i == "2057":
            return JINDAL
        if i == "1599":
            return SHADOW
        return {"ipoData": [{"anchor_investor_detail": ""}]}          # an SME with no anchor round


def doc():
    return {"listedPerf": [{"igId": "2057", "name": "Jindal Supreme (India)", "date": "2026-09-22", "sme": False},
                           {"igId": "1599", "name": "Shadowfax Technologies", "date": "2026-01-28", "sme": False},
                           {"igId": "3000", "name": "Tiny SME", "date": "2026-09-01", "sme": True},
                           {"igId": "2900", "name": "Old SME", "date": "2025-01-01", "sme": True}],
            "mainboard": [{"igId": "2057", "name": "Jindal Supreme (India)", "status": "Listed", "listing": "2026-09-22"}], "sme": []}


def run(s, prev=None, d=None):
    return anchorbook.run(s, prev or {}, Result(module="anchorbook", doc=d or doc()), today=TODAY)


def test_the_table_is_parsed_as_a_table_and_a_partial_book_is_marked_partial():
    b = ig.parse_anchor_book(JINDAL["ipoData"][0]["anchor_investor_detail"])
    assert b["bidDate"] == "2026-09-15" and b["price"] == 93.0 and b["totalShares"] == 4028400.0 and b["pctQib"] == 60.0
    assert b["locked30"] == 2014200.0 and b["locked90"] == 2014200.0 and b["complete"] is True and len(b["rows"]) == 5
    assert b["rows"][0] == {"name": "CRAFT EMERGING MARKET FUND PCC-ARBITRAGE STRATEGY FUND", "shares": 1340104.0, "amtCr": 12.46, "pctAlloc": 33.27, "pctIssue": 9.98}
    s = ig.parse_anchor_book(SHADOW["ipoData"][0]["anchor_investor_detail"])
    assert len(s["rows"]) == 2 and s["complete"] is False and s["totalShares"] == 69033955.0, "two names of a Rs 856 Cr book: partial, not small"
    assert ig.parse_anchor_book("") is None and ig.parse_anchor_book(None) is None


def test_investor_key_matches_spellings():
    k = anchorbook.investor_key
    assert k("HDFC TRUSTEE CO. LTD. A/C HDFC SMALL CAP FUND") == "HDFC SMALL CAP FUND"
    assert k("SBI LIFE INSURANCE CO.LTD.") == k("SBI Life Insurance Company Limited") == "SBI LIFE INSURANCE"
    assert k("Societe Generale - ODI") == "SOCIETE GENERALE ODI"


def test_books_are_fetched_newest_first_frozen_and_never_refetched():
    s = S()
    res = run(s)
    assert res.ok and [u.rsplit("/", 1)[1] for u in s.calls] == ["2057", "3000", "1599", "2900"], "newest listing first"
    A = res.replace["anchorBooks"]
    assert set(A["books"]) == {"2057", "1599"} and A["n"] == 2 and set(A["none"]) == {"3000", "2900"}
    j = A["books"]["2057"]
    assert j["name"] == "Jindal Supreme (India)" and j["sme"] is False and j["listedOn"] == "2026-09-22" and j["complete"] is True
    assert j["rows"][1]["key"] == "CRAFT EMERGING MARKET FUND PCC CITADEL CAPITAL FUND" and j["fetchedOn"] == "2026-09-22"
    assert A["books"]["1599"]["complete"] is False
    data = schema.empty_data(); assemble.apply(data, res); layout.check_groups()
    assert data["anchorBooks"]["n"] == 2 and "books" in layout.GROUPS and "anchorBooks" in layout.GROUPS["books"]
    # next run: nothing to fetch except the young 'none' after two weeks
    s2 = S()
    res2 = run(s2, prev={"anchorBooks": A})
    assert res2.ok and s2.calls == [] and res2.replace["anchorBooks"]["books"] == A["books"]
    s3 = S()
    later = anchorbook.run(s3, {"anchorBooks": A}, Result(module="anchorbook", doc=doc()), today=dt.date(2026, 10, 10))
    assert later.ok and [u.rsplit("/", 1)[1] for u in s3.calls] == ["3000"], "the young 'none' is retried after two weeks; the old one never"


def test_a_403_stops_at_once_and_a_bad_record_is_skipped():
    res = run(S(blocked=True))
    assert not res.ok and "anchorBooks" not in res.replace
    res = run(S(fail=["2057"]))
    assert res.ok and "1599" in res.replace["anchorBooks"]["books"] and "2057" not in res.replace["anchorBooks"]["books"]
    assert any("1 failed" in n for n in res.notes)


def test_three_failures_in_a_row_stop_the_run_and_keep_what_came():
    s = S(fail=["3000", "1599", "2900"])                # newest first: 2057 ok, then three failures, then one never tried
    d = doc(); d["listedPerf"].append({"igId": "2800", "name": "Oldest", "date": "2024-06-01", "sme": False})
    res = run(s, d=d)
    assert res.ok and "2057" in res.replace["anchorBooks"]["books"] and any("failed in a row" in n for n in res.notes)
    assert [u.rsplit("/", 1)[1] for u in s.calls] == ["2057", "3000", "1599", "2900"] and anchorbook.BUDGET_SECONDS <= 300
