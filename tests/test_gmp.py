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

from collector import assemble  # noqa: E402
from collector.errors import SourceChanged, SourceDown  # noqa: E402
from collector.modules import gmp  # noqa: E402
from collector.result import Result  # noqa: E402
from collector.sources import investorgain, ipopremium, ipowatch  # noqa: E402

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
ALL_OK_TEXT = {"ipowatch.in": fixture("ipowatch", "board.html"), "ipopremium.in": fixture("ipopremium", "board.html")}


# ------------------------------------------------------------------ parsers
def test_ipowatch_parser_on_fixture():
    rows = ipowatch.parse_ipowatch(fixture("ipowatch", "board.html"))
    assert len(rows) >= 5
    assert all(r["name"] for r in rows)
    by = {r["name"]: r for r in rows}
    d = by["Dhoot Transmission"]
    assert d["gmp"] == 245.0 and d["gmpPct"] == 28.13 and d["bandHigh"] == 871.0   # % from Est. Listing
    assert d["status"] == "Upcoming" and d["type"] == "Mainboard"
    assert by["Molbio Diagnostics"]["gmp"] is None                                  # '₹0' / '₹- (0.00%)' placeholder
    assert sum(1 for r in rows if r["gmpPct"] is not None) >= 3
    assert all(-50 <= r["gmpPct"] <= 500 for r in rows if r["gmpPct"] is not None)


def test_ipowatch_changed_shape_raises():
    with pytest.raises(SourceChanged):
        ipowatch.parse_ipowatch("<html><body><table><tr><th>Foo</th><th>Bar</th></tr><tr><td>x</td><td>y</td></tr></table></body></html>")
    with pytest.raises(SourceChanged):
        ipowatch.parse_ipowatch("")


def test_ipopremium_parser_on_fixture():
    rows = ipopremium.parse_ipopremium(fixture("ipopremium", "board.html"))
    by = {r["name"]: r for r in rows}
    d = by["Dhoot Transmission (Mainboard)"]
    assert d["gmp"] == 249.0 and d["bandHigh"] == 871.0
    assert d["gmpPct"] == round(249 / 871 * 100, 2)          # % computed from band (en-dash)
    assert d["open"] == "19 Sep 2026" and d["listing"] == "26 Sep 2026"
    assert by["Fusion Klassroom (SME)"]["gmp"] is None


def test_ipopremium_changed_shape_raises():
    with pytest.raises(SourceChanged):
        ipopremium.parse_ipopremium("<table><tr><th>Company Name</th><th>Price</th></tr><tr><td>A</td><td>1</td></tr></table>")


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
    s = FakeSession(text=ALL_OK_TEXT, json_={"webnodejs.investorgain.com": {"msg": "API not found"}})
    prev = board({"name": "Dhoot Transmission", "status": "Upcoming", "gmp": 200},
                 {"name": "LEAP India", "status": "Open"})
    res = gmp.run(s, prev, Result(module="gmp"))
    assert res.ok and res.source == "ipowatch"
    assert res.tried[0]["source"] == "investorgain" and res.tried[0]["kind"] == "changed"
    assert res.rows["mainboard"]["Dhoot Transmission"]["gmp"] == 245.0
    assert res.rows["mainboard"]["LEAP India"]["gmp"] == 4.0
    assert not any("ipopremium.in" in c for c in s.calls)      # winner covered the board; no third call


def test_all_sources_fail_leaves_result_not_ok():
    s = FakeSession()
    res = gmp.run(s, board({"name": "LEAP India"}), Result(module="gmp"))
    assert not res.ok and res.error and len(res.tried) == 3 and res.rows == {}


def test_name_normalisation_matches_board_spelling():
    assert gmp.normalise("Kanohar Electricals Ltd IPO") == gmp.normalise("Kanohar Electricals")
    assert gmp.normalise("Dhoot Transmission (Mainboard)") == "dhoot transmission"
    assert gmp.normalise("Anawil Wire & Engineering IPO") == gmp.normalise("Anawil Wire and Engineering")
    s = FakeSession(json_=ALL_OK_JSON, text=ALL_OK_TEXT)
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
    s = FakeSession(json_=ALL_OK_JSON, text=ALL_OK_TEXT)
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
    s = FakeSession(json_=ALL_OK_JSON, text=ALL_OK_TEXT)
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
    s = FakeSession(json_=ALL_OK_JSON, text=ALL_OK_TEXT)
    prev = board({"name": "Kanohar Electricals", "gmp": 40},
                 {"name": "Technocraft Ventures", "status": "Upcoming"},
                 {"name": "Ardee Industries", "status": "Upcoming"},
                 {"name": "MV Electrosystems", "type": "BSE SME", "status": "Open"})
    res = gmp.run(s, prev, Result(module="gmp"))
    assert res.ok and res.source == "investorgain+ipowatch"
    assert res.rows["mainboard"]["Kanohar Electricals"]["gmp"] == 45.0       # from investorgain (first wins)
    assert res.rows["mainboard"]["Technocraft Ventures"]["gmp"] == 10.0     # topped up from ipowatch
    assert res.rows["sme"]["MV Electrosystems"]["gmp"] == 100.0
    assert not any("ipopremium.in" in c for c in s.calls)


def test_gmp_pct_computed_from_board_band_when_source_lacks_it():
    html = ('<table><tr><td><strong>IPO Name</strong></td><td><strong>IPO GMP*</strong></td>'
            '<td><strong>Price Band</strong></td><td><strong>Est. Listing</strong></td></tr>'
            '<tr><td>Kanohar Electricals</td><td>₹36</td><td>₹-</td><td>₹396</td></tr></table>')
    s = FakeSession(text={"ipowatch.in": html}, json_={"webnodejs.investorgain.com": SourceDown("investorgain", "boom")})
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
