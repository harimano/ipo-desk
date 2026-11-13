"""Offline tests for the GMP sources and the gmp row-patcher module (fixtures under data/fixtures/)."""
from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector import assemble
from collector.errors import SourceChanged, SourceDown
from collector.modules import gmp
from collector.result import Result
from collector.sources import investorgain, ipowatch

FIX = ROOT / "data" / "fixtures"


def fixture(*parts) -> str:
    return (FIX.joinpath(*parts)).read_text(encoding="utf8")


class FakeSession:
    """Same method names as collector.http.Session; answers from fixtures keyed by URL substring."""

    def __init__(self, text: dict[str, str] | None = None, json_: dict[str, object] | None = None):
        self.text, self.json_ = text or {}, json_ or {}
        self.calls: list[str] = []

    def _lookup(self, table, url, source):
        for key, val in table.items():
            if key in url:
                if isinstance(val, Exception):
                    raise val
                return val
        raise SourceDown(source, "no fixture for URL", url)

    def get_text(self, url, *, source, headers=None, params=None):
        self.calls.append(url)
        return self._lookup(self.text, url, source)

    def get_json(self, url, *, source, headers=None, params=None):
        self.calls.append(url)
        return self._lookup(self.json_, url, source)


def board(*rows):
    """Minimal prev document with a mainboard/sme split by 'type'."""
    prev = {"mainboard": [], "sme": []}
    for r in rows:
        row = {"gmp": None, "gmpPct": None, "gmpTrend": None, "status": "Open", "bandHigh": None, **r}
        (prev["sme"] if "SME" in row.get("type", "Mainboard") else prev["mainboard"]).append(row)
    return prev


ALL_OK_JSON = {"webnodejs.investorgain.com": json.loads(fixture("investorgain", "v2.json"))}


def iw_feed(*rows) -> dict:
    """ipowatch's GetIpoGMPHistory shape (the real one is the 13 Nov 2026 fixture), for the module tests:
    (name, gmp text, est-listing text, price band, type, status)."""
    return {"status": 1, "message": "IPO GMP Data Retrieved Successfully", "jwtToken": None, "totalCount": 0, "id": 0,
            "result": [{"id": i + 1, "ipoName": n, "ipo_slug": n.lower().replace(" ", "-"), "ipoGmp": g, "trendIcon": "fa-arrow-up",
                        "trendColor": "#28A745", "priceBand": b, "estListing": e, "IPODate": "18 Nov - 20 Nov", "Type": t,
                        "Status": st, "LastUpdated": "13 Nov, 12:12"} for i, (n, g, e, b, t, st) in enumerate(rows)]}


ALL_OK_IW = {"ipowatch.in": iw_feed(("Dhoot Transmission", "₹245", "₹1,116 (28.13%)", "₹826 - ₹871", "Mainboard", "Upcoming"),
                                    ("LEAP India", "₹4", "₹359 (1.13%)", "₹337 - ₹355", "Mainboard", "Open"),
                                    ("Technocraft Ventures", "₹10", "₹110 (10.00%)", "₹95 - ₹100", "Mainboard", "Upcoming"),
                                    ("MV Electrosystems", "₹100", "₹300 (50.00%)", "₹190 - ₹200", "BSE SME", "Open"),
                                    ("Molbio Diagnostics", "₹0", "₹105 (0.00%)", "₹100 - ₹105", "Mainboard", "Upcoming"))}


# ------------------------------------------------------------------ parsers
def test_ipowatch_parser_on_real_feed():
    """GetIpoGMPHistory, 13 Nov 2026: the one upcoming issue of a quiet week."""
    rows = ipowatch.parse_gmp_history(json.loads(fixture("ipowatch", "gmp-history-2026-11-13.json")))
    assert [r["name"] for r in rows] == ["Crystal Crop Protection"]
    c = rows[0]
    assert c["gmp"] == 45.0 and c["gmpPct"] == 16.54 and c["bandHigh"] == 272.0        # % from estListing, not ipoGmp
    assert c["type"] == "Mainboard" and c["status"] == "Upcoming" and c["dateText"] == "18 Nov - 20 Nov"
    assert c["updated"] == "13 Nov, 12:12" and c["iwId"] == "1149" and c["source"] == "ipowatch"


def test_ipowatch_no_quote_and_sme_rows():
    """'₹0' + '(0.00%)' is "no grey market yet", never a zero premium; SME rows share the list under `Type`."""
    rows = ipowatch.parse_gmp_history(ALL_OK_IW["ipowatch.in"])
    by = {r["name"]: r for r in rows}
    assert by["Molbio Diagnostics"]["gmp"] is None and by["Molbio Diagnostics"]["gmpPct"] is None
    assert by["MV Electrosystems"]["gmp"] == 100.0 and by["MV Electrosystems"]["type"] == "BSE SME"
    assert by["Dhoot Transmission"]["gmpPct"] == 28.13 and by["Dhoot Transmission"]["bandHigh"] == 871.0
    assert all(-50 <= r["gmpPct"] <= 500 for r in rows if r["gmpPct"] is not None)


def test_ipowatch_changed_shape_raises():
    for bad in ({"status": 0, "message": "Something went wrong", "result": None},
                {"status": 1, "result": []},                          # an empty list is never success (rule 5)
                {"status": 1, "result": [{"name": "x", "gmp": 1}]},   # fields renamed
                [], "", None):
        with pytest.raises(SourceChanged):
            ipowatch.parse_gmp_history(bad)


def test_ipowatch_fetch_uses_the_json_feed():
    s = FakeSession(json_=ALL_OK_IW)
    assert len(ipowatch.fetch(s)) == 5 and s.calls == [ipowatch.URL]


def test_investorgain_parser_on_fixture():
    rows = investorgain.parse_investorgain(json.loads(fixture("investorgain", "v2.json")))
    assert len(rows) == 5
    by = {r["name"]: r for r in rows}
    k = by["Kanohar Electricals Ltd IPO"]                     # tags stripped, badge dropped
    assert k["gmp"] == 45.0 and k["gmpPct"] == 12.5 and k["bandHigh"] == 360.0
    assert k["open"] == "2026-09-15" and k["close"] == "2026-09-17" and k["listing"] == "2026-09-22"
    assert k["status"] == "Open" and k["type"] == "Mainline"
    assert by["Anawil Wire & Engineering IPO"]["gmp"] == 80.0
    assert by["Molbio Diagnostics IPO"]["gmp"] is None and by["Molbio Diagnostics IPO"]["open"] is None
    assert investorgain.as_of(rows) == "2026-09-17"


def test_investorgain_api_not_found_raises():
    with pytest.raises(SourceChanged):
        investorgain.parse_investorgain({"msg": "API not found"})
    with pytest.raises(SourceChanged):
        investorgain.parse_investorgain({"reportTableData": []})
    with pytest.raises(SourceChanged):
        investorgain.parse_investorgain([])


def test_investorgain_url_and_fy():
    assert investorgain.fiscal_year(dt.date(2026, 9, 17)) == "2026-27"
    assert investorgain.fiscal_year(dt.date(2027, 2, 1)) == "2026-27"
    assert investorgain.url_for(dt.date(2026, 9, 17)) == (
        "https://webnodejs.investorgain.com/cloud/v2/report/data-read/331/1/9/2026/2026-27/0/all")


def test_investorgain_fetch_uses_session_and_raises_on_retired_endpoint():
    s = FakeSession(json_={"webnodejs.investorgain.com": {"msg": "API not found"}})
    with pytest.raises(SourceChanged):
        investorgain.fetch(s, today=dt.date(2026, 9, 17))
    assert s.calls and "/331/1/9/2026/2026-27/0/all" in s.calls[0]


# ------------------------------------------------------------------ module
def test_chain_falls_through_to_ipowatch_when_investorgain_retired():
    s = FakeSession(json_={"webnodejs.investorgain.com": {"msg": "API not found"}, **ALL_OK_IW})
    prev = board({"name": "Dhoot Transmission", "status": "Upcoming", "gmp": 200},
                 {"name": "LEAP India", "status": "Open"})
    res = gmp.run(s, prev, Result(module="gmp"))
    assert res.ok and res.source == "ipowatch"
    assert res.tried[0]["source"] == "investorgain" and res.tried[0]["kind"] == "changed"
    assert res.rows["mainboard"]["Dhoot Transmission"]["gmp"] == 245.0
    assert res.rows["mainboard"]["LEAP India"]["gmp"] == 4.0


def test_all_sources_fail_leaves_result_not_ok():
    s = FakeSession()
    res = gmp.run(s, board({"name": "LEAP India"}), Result(module="gmp"))
    assert not res.ok and res.error and len(res.tried) == 2 and res.rows == {}        # investorgain, ipowatch — two sources since 5 Nov 2026


def test_name_normalisation_matches_board_spelling():
    assert gmp.normalise("Kanohar Electricals Ltd IPO") == gmp.normalise("Kanohar Electricals")
    assert gmp.normalise("Dhoot Transmission (Mainboard)") == "dhoot transmission"
    assert gmp.normalise("Anawil Wire & Engineering IPO") == gmp.normalise("Anawil Wire and Engineering")
    s = FakeSession(json_={**ALL_OK_JSON, **ALL_OK_IW})
    prev = board({"name": "Kanohar Electricals", "status": "Open", "bandHigh": 360})
    res = gmp.run(s, prev, Result(module="gmp"))
    assert res.ok and res.source == "investorgain"
    assert list(res.rows["mainboard"]) == ["Kanohar Electricals"]          # board's spelling, not the site's
    assert res.rows["mainboard"]["Kanohar Electricals"] == {"gmp": 45.0, "gmpPct": 12.5, "gmpTrend": "flat",
                                                            "issueSizeCr": 480.0}       # the feed's whole-issue figure
    assert any("not on the board" in n and "Dhoot Transmission" in n for n in res.notes)   # off-board -> notes


def test_gmp_trend_against_prev():
    assert gmp.trend(45, 40) == "up" and gmp.trend(45, 50) == "down" and gmp.trend(45, 45) == "flat"
    assert gmp.trend(45, None) == "flat"
    s = FakeSession(json_={**ALL_OK_JSON, **ALL_OK_IW})
    prev = board({"name": "Kanohar Electricals", "gmp": 40},
                 {"name": "Dhoot Transmission", "status": "Upcoming", "gmp": 300},
                 {"name": "LEAP India", "gmp": 4},
                 {"name": "Anawil Wire & Engineering", "type": "NSE SME", "status": "Closed"})
    res = gmp.run(s, prev, Result(module="gmp"))
    mb, sme = res.rows["mainboard"], res.rows["sme"]
    assert mb["Kanohar Electricals"]["gmpTrend"] == "up"
    assert mb["Dhoot Transmission"]["gmpTrend"] == "down"
    assert mb["LEAP India"]["gmpTrend"] == "flat"
    assert sme["Anawil Wire & Engineering"]["gmpTrend"] == "flat" and sme["Anawil Wire & Engineering"]["gmp"] == 80.0
    assert res.asOf == "2026-09-17"


def test_board_row_absent_from_every_source_keeps_prev_gmp():
    s = FakeSession(json_={**ALL_OK_JSON, **ALL_OK_IW})
    prev = board({"name": "Kanohar Electricals", "gmp": 40},
                 {"name": "Zeta Unknown Industries", "gmp": 77, "gmpPct": 5.5, "gmpTrend": "up"},
                 {"name": "Omega Upcoming Co", "status": "Upcoming", "gmp": 12})
    res = gmp.run(s, prev, Result(module="gmp"))
    assert "Zeta Unknown Industries" not in res.rows["mainboard"]
    assert any("Zeta Unknown Industries" in u for u in res.unresolved)    # Open + unmatched -> unresolved
    assert not any("Omega Upcoming Co" in u for u in res.unresolved)      # Upcoming -> not flagged
    data = copy.deepcopy(prev)
    assemble.apply(data, res)                                             # ownership check + row merge
    rows = {r["name"]: r for r in data["mainboard"]}
    assert rows["Zeta Unknown Industries"]["gmp"] == 77 and rows["Zeta Unknown Industries"]["gmpTrend"] == "up"
    assert rows["Kanohar Electricals"]["gmp"] == 45.0 and rows["Kanohar Electricals"]["gmpTrend"] == "up"


def test_low_coverage_winner_is_topped_up_from_next_source():
    """investorgain knows only 1 of 4 active names -> ipowatch is consulted for the rest and merged."""
    s = FakeSession(json_={**ALL_OK_JSON, **ALL_OK_IW})
    prev = board({"name": "Kanohar Electricals", "gmp": 40},
                 {"name": "Technocraft Ventures", "status": "Upcoming"},
                 {"name": "Ardee Industries", "status": "Upcoming"},
                 {"name": "MV Electrosystems", "type": "BSE SME", "status": "Open"})
    res = gmp.run(s, prev, Result(module="gmp"))
    assert res.ok and res.source == "investorgain+ipowatch"
    assert res.rows["mainboard"]["Kanohar Electricals"]["gmp"] == 45.0       # from investorgain (first wins)
    assert res.rows["mainboard"]["Technocraft Ventures"]["gmp"] == 10.0     # topped up from ipowatch
    assert res.rows["sme"]["MV Electrosystems"]["gmp"] == 100.0


def test_gmp_pct_computed_from_board_band_when_source_lacks_it():
    feed = iw_feed(("Kanohar Electricals", "₹36", "₹396", "₹-", "Mainboard", "Open"))      # no % and no band from the site
    s = FakeSession(json_={"ipowatch.in": feed, "webnodejs.investorgain.com": SourceDown("investorgain", "boom")})
    prev = board({"name": "Kanohar Electricals", "bandHigh": 360})
    res = gmp.run(s, prev, Result(module="gmp"))
    assert res.ok and res.rows["mainboard"]["Kanohar Electricals"]["gmpPct"] == 10.0


def test_live_feed_alias_and_whole_issue_size():
    """Real feed, 17 Sep 2026. The site calls NSE's IPO just "NSE" — a name the normaliser reduces to nothing, so
    only data/aliases.json can place it. And the feed's issue size is the whole issue: NSE's list, net of the
    anchor portion, made Hero Motors 744 Cr when the issue is 1,000 Cr."""
    import json
    import pathlib
    live = json.loads((pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/live-2026-09-17/ig.json").read_text())
    prev = {"mainboard": [{"name": "NSE (National Stock Exchange of India)", "status": "Open", "bandHigh": 1785, "gmp": 150, "issueSizeCr": 15822.76},
                          {"name": "Hero Motors", "status": "Open", "bandHigh": 84, "gmp": 5.5, "issueSizeCr": 744.3}], "sme": []}
    res = gmp.run(None, prev, Result(module="gmp"), attempts=[("investorgain", lambda: investorgain.parse_investorgain(live))])
    rows = res.rows["mainboard"]
    assert rows["NSE (National Stock Exchange of India)"]["issueSizeCr"] == 22561.57
    assert rows["NSE (National Stock Exchange of India)"]["gmp"] is not None
    assert rows["Hero Motors"]["issueSizeCr"] == 1000.0
    assert not any("NSE (National" in u for u in res.unresolved)
