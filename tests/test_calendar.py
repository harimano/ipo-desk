"""Offline tests for collector.sources.nse_ipo, collector.sources.bse_issues and the calendar module.
All fixtures are under data/fixtures/{nse,bse}/ and are dated around TODAY = 2026-09-17."""
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

from collector import assemble, schema  # noqa: E402
from collector.errors import SourceBlocked, SourceChanged, SourceDown  # noqa: E402
from collector.modules import calendar  # noqa: E402
from collector.result import Result  # noqa: E402
from collector.sources import bse_issues, nse_ipo  # noqa: E402

FIX = ROOT / "data" / "fixtures"
TODAY = dt.date(2026, 9, 17)
HAS_SELECTOLAX = bse_issues.HTMLParser is not None
needs_selectolax = pytest.mark.skipif(not HAS_SELECTOLAX, reason="selectolax not installed")


def text(*parts) -> str:
    return FIX.joinpath(*parts).read_text(encoding="utf8")


def load(*parts):
    return json.loads(text(*parts))


class FakeSession:
    """Same method names as collector.http.Session. nse_json answers by path (+symbol for ipo-detail),
    bse_json by path, get_text by URL substring. A value that is an Exception is raised."""

    def __init__(self, nse: dict | None = None, bse: dict | None = None, html: dict | None = None):
        self.nse, self.bse, self.html = nse or {}, bse or {}, html or {}
        self.calls: list[str] = []

    @staticmethod
    def _answer(val):
        if isinstance(val, Exception):
            raise val
        return val

    def nse_json(self, path, params=None, *, source="nse", referer=None):
        self.calls.append(path + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else ""))
        if "ipo-detail" in path:
            key = f"detail:{(params or {}).get('symbol')}"
            if key in self.nse:
                return self._answer(self.nse[key])
            if "detail:*" in self.nse:
                return self._answer(self.nse["detail:*"])
            raise SourceDown(source, "HTTP 404", path, 404)
        if path in self.nse:
            return self._answer(self.nse[path])
        raise SourceDown(source, "HTTP 404", path, 404)

    def bse_json(self, path, params=None, *, source="bse"):
        self.calls.append("bse:" + path)
        if path in self.bse:
            return self._answer(self.bse[path])
        raise SourceDown(source, "HTTP 404", path, 404)

    def get_text(self, url, *, source, headers=None, params=None):
        self.calls.append(url)
        for k, v in self.html.items():
            if k in url:
                return self._answer(v)
        raise SourceDown(source, "HTTP 404", url, 404)

    def get_json(self, url, *, source, headers=None, params=None):
        return self.get_text(url, source=source)

    def post_text(self, url, data, *, source, headers=None):
        raise SourceDown(source, "not wired", url)

    def get_bytes(self, url, *, source, headers=None, expect_pdf=False):
        raise SourceDown(source, "not wired", url)


def nse_ok() -> dict:
    return {
        "/api/ipo-current-issue": load("nse", "ipo-current-issue.json"),
        "/api/all-upcoming-issues": load("nse", "all-upcoming-issues.json"),
        "/api/public-past-issues": load("nse", "public-past-issues.json"),
        "detail:SONASEL": load("nse", "ipo-detail-SONASEL.json"),
        "detail:VIDYAWIRE": load("nse", "ipo-detail-VIDYAWIRE.json"),
        "detail:KABRAJEW": load("nse", "ipo-detail-KABRAJEW.json"),
    }


def nse_blocked() -> dict:
    b = SourceBlocked("nse", "HTTP 403", "https://www.nseindia.com/api/ipo-current-issue", 403)
    return {"/api/ipo-current-issue": b, "/api/all-upcoming-issues": b, "/api/public-past-issues": b, "detail:*": b}


def bse_ok() -> dict:
    return {"/GetPublicIssue_par_updated/w": load("bse", "GetPublicIssue_par_updated.json")}


def html_ok() -> dict:
    return {"IPOIssues_new.aspx": text("bse", "IPOIssues_new.html")}


def prev_board() -> dict:
    """Yesterday's latest.json: Sona is spelled without 'Limited' and already carries gmp/sub/sources."""
    d = schema.empty_data()
    d["mainboard"] = [
        {"name": "Sona Selection India", "slug": "sona-selection-india", "type": "Mainboard", "status": "Open",
         "open": "2026-09-15", "close": "2026-09-17", "allotment": "2026-09-18", "listing": "2026-09-22",
         "bandLow": 95, "bandHigh": 100, "lotSize": 150, "issueSizeCr": 450, "freshCr": 300, "ofsCr": 150,
         "gmp": 18, "gmpPct": 18.0, "gmpTrend": "up",
         "sub": {"qib": 1.2, "nii": 2.1, "retail": 0.6, "total": 1.3, "asOf": "2026-09-16T17:00:00+05:30"},
         "shareholderQuota": None, "listingPrice": None, "listingGainPct": None, "currentPrice": None,
         "sources": ["NSE ipo-current-issue"], "symbol": "SONASEL", "series": "EQ", "bseIpoNo": "7973"},
        {"name": "Anlon Healthcare Limited", "slug": "anlon-healthcare-limited", "type": "Mainboard", "status": "Closed",
         "open": "2026-09-08", "close": "2026-09-10", "allotment": "2026-09-11", "listing": "2026-09-16",
         "bandLow": 86, "bandHigh": 91, "lotSize": 164, "issueSizeCr": 121.03, "freshCr": 121.03, "ofsCr": 0,
         "gmp": 9, "gmpPct": 9.9, "gmpTrend": "flat", "sub": {"qib": 40.1, "nii": 55.2, "retail": 12.3, "total": 32.0, "asOf": "2026-09-10T17:00:00+05:30"},
         "shareholderQuota": None, "listingPrice": 101.0, "listingGainPct": 11.0, "currentPrice": 103.5,
         "sources": ["NSE ipo-current-issue"], "symbol": "ANLON", "series": "EQ"},
        {"name": "Gone Corp Limited", "slug": "gone-corp-limited", "type": "Mainboard", "status": "Listed",
         "open": "2026-08-25", "close": "2026-08-27", "allotment": "2026-08-28", "listing": "2026-09-01",
         "bandLow": 50, "bandHigh": 55, "lotSize": 270, "issueSizeCr": 80, "sources": [], "symbol": "GONE"},
    ]
    d["sme"] = [
        {"name": "Vidya Wires Limited", "slug": "vidya-wires-limited", "type": "NSE SME", "status": "Open",
         "open": "2026-09-16", "close": "2026-09-18", "allotment": None, "listing": "2026-09-23",
         "bandLow": 48, "bandHigh": 52, "lotSize": 2000, "issueSizeCr": 31.2, "gmp": 4, "gmpPct": 7.7, "gmpTrend": "flat",
         "sub": None, "sources": ["NSE ipo-current-issue"], "symbol": "VIDYAWIRE", "series": "SME", "bseIpoNo": "7980"},
    ]
    d["lot"] = {"Sona Selection India": {"shares": 150, "price": 100, "listDate": "2026-09-22"},
                "Gone Corp Limited": {"shares": 270, "price": 55, "listDate": "2026-09-01"}}
    d["expected"] = [{"name": "Reliance Jio", "window": "H1 2027", "stage": "DRHP", "sizeCr": 40000, "sources": []}]
    return d


def run(session, prev, today=TODAY) -> Result:
    return calendar.run(session, prev, Result(module="calendar"), today=today)


def by_name(rows):
    return {r["name"]: r for r in rows}


# ---------------------------------------------------------------------------------------------
# nse_ipo source
# ---------------------------------------------------------------------------------------------
def test_nse_current_issues_normalised():
    rows = nse_ipo.current_issues(FakeSession(nse=nse_ok()))
    assert [r["symbol"] for r in rows] == ["SONASEL", "VIDYAWIRE", "KABRAJEW"]
    sona = rows[0]
    assert sona["open"] == "2026-09-15" and sona["close"] == "2026-09-17"
    assert (sona["bandLow"], sona["bandHigh"]) == (95.0, 100.0)
    assert sona["issueSizeCr"] == 450.0          # 4.5 crore shares x Rs.100 -> crore
    assert sona["totalSub"] == 2.41
    assert rows[1]["board"] == "SME" and sona["board"] == "Mainboard"
    assert rows[2]["totalSub"] is None            # "-" is not a number


def test_nse_past_issues_field_drift_and_debt_filter():
    rows = nse_ipo.past_issues(FakeSession(nse=nse_ok()), TODAY - dt.timedelta(days=45), TODAY)
    names = [r["name"] for r in rows]
    assert "Anlon Healthcare Limited" in names
    assert not any("Muthoot" in n for n in names), "NCD row must be filtered"
    anlon = next(r for r in rows if r["symbol"] == "ANLON")
    assert anlon["open"] == "2026-09-08" and anlon["listing"] == "2026-09-16"      # ipoStartDate spelling
    assert anlon["bandHigh"] == 91.0                                                 # priceRange spelling
    zen = next(r for r in rows if r["symbol"] == "ZENDRONE")
    assert zen["withdrawn"] and zen["name"] == "Zenith Drones Limited"


def test_nse_empty_list_raises_source_changed():
    with pytest.raises(SourceChanged):
        nse_ipo.current_issues(FakeSession(nse={"/api/ipo-current-issue": load("nse", "empty-list.json")}))


def test_nse_changed_shape_raises_source_changed():
    with pytest.raises(SourceChanged) as e:
        nse_ipo.upcoming_issues(FakeSession(nse={"/api/all-upcoming-issues": load("nse", "changed-shape.json")}))
    assert "none had a name" in e.value.detail


def test_nse_past_issues_rejects_reversed_window():
    with pytest.raises(ValueError):
        nse_ipo.past_issues(FakeSession(), TODAY, TODAY - dt.timedelta(days=1))


def test_nse_ipo_detail_lot_and_bids():
    d = nse_ipo.ipo_detail(FakeSession(nse=nse_ok()), "SONASEL", "EQ")
    lot = nse_ipo.detail_lot(d)
    assert lot == {"lotSize": 150, "issueSizeCr": 450.0, "bandLow": 95.0, "bandHigh": 100.0}
    cats = [b["category"] for b in d["bidDetails"]]
    assert "Total" in cats and any("QIB" in c for c in cats)
    assert d["updateTime"] == "17-Sep-2026 15:02"


def test_nse_ipo_detail_upcoming_has_info_but_no_bids():
    d = nse_ipo.ipo_detail(FakeSession(nse=nse_ok()), "KABRAJEW", "EQ")
    assert d["bidDetails"] == [] and nse_ipo.detail_lot(d)["lotSize"] == 117


def test_nse_ipo_detail_sme_tries_both_series():
    s = FakeSession(nse=nse_ok())
    nse_ipo.ipo_detail(s, "VIDYAWIRE", "SME")
    assert s.calls[0].endswith("series=SME")


def test_nse_ipo_detail_empty_raises():
    s = FakeSession(nse={"detail:*": load("nse", "ipo-detail-empty.json")})
    with pytest.raises(SourceChanged):
        nse_ipo.ipo_detail(s, "NOBODY", "EQ")
    assert len(s.calls) == 2, "tries EQ then SME"


@pytest.mark.parametrize("raw,expected", [
    ("15-Sep-2026", "2026-09-15"), ("22-MAR-2024", "2024-03-22"), ("2026-09-15T00:00:00", "2026-09-15"),
    ("16 Sep 2026", "2026-09-16"), ("Sep 17, 2026", "2026-09-17"), ("17/09/2026", "2026-09-17"),
    ("-", None), ("", None), (None, None), ("not a date", None),
])
def test_iso_date(raw, expected):
    assert nse_ipo.iso_date(raw) == expected


def test_number_and_band():
    assert nse_ipo.number("7.5915E7") == 75915000.0
    assert nse_ipo.number("1,57,50,000") == 15750000.0
    assert nse_ipo.number("-") is None
    assert nse_ipo.price_band("Rs.95 to Rs.100") == (95.0, 100.0)
    assert nse_ipo.price_band("118-128") == (118.0, 128.0)
    assert nse_ipo.price_band("91") == (91.0, 91.0)


# ---------------------------------------------------------------------------------------------
# bse_issues source
# ---------------------------------------------------------------------------------------------
def test_bse_json_rows():
    rows = bse_issues.public_issues_json(FakeSession(bse=bse_ok()))
    assert [r["name"] for r in rows] == ["SONA SELECTION INDIA LTD", "Vidya Wires Ltd", "Kabra Jewels Limited"]
    assert rows[0]["bseIpoNo"] == "7973" and rows[0]["open"] == "2026-09-15" and rows[0]["bandHigh"] == 100.0
    assert rows[1]["board"] == "SME"
    assert not any("Reliance" in r["name"] for r in rows), "OTB row is not an IPO"


def test_bse_json_changed_shape():
    with pytest.raises(SourceChanged):
        bse_issues.parse_public_issues_json({"Table": [{"foo": 1}]})
    with pytest.raises(SourceChanged):
        bse_issues.parse_public_issues_json({"Table": []})


@needs_selectolax
def test_bse_legacy_table_rows():
    rows = bse_issues.public_issues_html(FakeSession(html=html_ok()))
    assert [r["name"] for r in rows] == ["Sona Selection India Ltd", "Vidya Wires Ltd", "Kabra Jewels Limited"]
    sona = rows[0]
    assert sona["bseIpoNo"] == "7973" and (sona["bandLow"], sona["bandHigh"]) == (95.0, 100.0)
    assert sona["open"] == "2026-09-15" and sona["close"] == "2026-09-17"
    assert rows[1]["board"] == "SME" and rows[2]["statusHint"] == "Forthcoming"


@needs_selectolax
def test_bse_legacy_table_empty_page_raises():
    with pytest.raises(SourceChanged):
        bse_issues.parse_public_issues_html(text("bse", "IPOIssues_new-empty.html"))


@needs_selectolax
def test_bse_cumulative_demand_rows():
    rows = bse_issues.cumulative_demand(FakeSession(html={"CummDemandSchedule.aspx?ID=7973": text("bse", "CummDemandSchedule-7973.html")}), "7973")
    d = {r["category"]: r["noOfTime"] for r in rows}
    assert any("Qualified" in k and v == 3.91 for k, v in d.items())
    assert any(k.startswith("Total") and v == 2.39 for k, v in d.items())


@needs_selectolax
def test_bse_cumulative_demand_empty_raises():
    with pytest.raises(SourceChanged):
        bse_issues.parse_cumulative_demand(text("bse", "CummDemandSchedule-empty.html"))


# ---------------------------------------------------------------------------------------------
# calendar module
# ---------------------------------------------------------------------------------------------
def test_status_derivation():
    t = TODAY
    assert calendar.derive_status("2026-09-18", "2026-09-22", None, t) == "Upcoming"
    assert calendar.derive_status("2026-09-15", "2026-09-17", "2026-09-22", t) == "Open"
    assert calendar.derive_status("2026-09-08", "2026-09-10", "2026-09-18", t) == "Closed"
    assert calendar.derive_status("2026-09-08", "2026-09-10", None, t) == "Closed"
    assert calendar.derive_status("2026-09-08", "2026-09-10", "2026-09-17", t) == "Listed"


def test_happy_path_nse():
    prev = prev_board()
    before = copy.deepcopy(prev)
    res = run(FakeSession(nse=nse_ok()), prev)
    assert res.ok and res.source == "nse", res.error
    assert prev == before, "prev must never be mutated"
    mb, sme = by_name(res.replace["mainboard"]), by_name(res.replace["sme"])

    # name matching: NSE says "Sona Selection India Limited", the board spelling stays
    assert "Sona Selection India" in mb and "Sona Selection India Limited" not in mb
    sona = mb["Sona Selection India"]
    assert sona["status"] == "Open" and sona["type"] == "Mainboard"
    # carry-forward of fields NSE does not provide
    assert sona["gmp"] == 18 and sona["gmpTrend"] == "up" and sona["freshCr"] == 300
    assert sona["sub"]["qib"] == 1.2 and sona["sub"]["total"] == 2.41    # headline total refreshed from the list
    assert sona["listing"] == "2026-09-22" and sona["allotment"] == "2026-09-18"
    assert sona["bseIpoNo"] == "7973" and sona["symbol"] == "SONASEL"
    assert "NSE ipo-current-issue" in sona["sources"] and len(sona["sources"]) == 1
    assert sona["lotSize"] == 150 and sona["issueSizeCr"] == 450.0

    # upcoming: new row, lot size from ipo-detail, status Upcoming
    assert mb["Kabra Jewels"]["status"] == "Upcoming"
    assert mb["Kabra Jewels"]["lotSize"] == 117
    assert mb["Tejas Cargo Logistics"]["status"] == "Upcoming"
    assert mb["Tejas Cargo Logistics"]["slug"] == "tejas-cargo-logistics"

    # listed yesterday: stays one day, keeps its listingPrice; listed long ago: gone
    assert mb["Anlon Healthcare Limited"]["status"] == "Listed"
    assert mb["Anlon Healthcare Limited"]["listingPrice"] == 101.0
    assert "Gone Corp Limited" not in mb and "Oldco Textiles Limited" not in mb and "Oldco Textiles Limited" not in sme
    assert not any("Muthoot" in n for n in mb) and "Zenith Drones Limited" not in sme

    # SME
    assert list(sme) == ["Vidya Wires Limited"] and sme["Vidya Wires Limited"]["type"] == "NSE SME"
    assert sme["Vidya Wires Limited"]["gmp"] == 4

    # lot + expected
    lot = res.replace["lot"]
    assert lot["Sona Selection India"] == {"shares": 150, "price": 100.0, "listDate": "2026-09-22"}
    assert lot["Kabra Jewels"]["shares"] == 117 and lot["Vidya Wires Limited"]["shares"] == 2000
    assert "Gone Corp Limited" in lot          # lot is never pruned: the Book keys off it
    assert set(res.replace) == {"mainboard", "sme", "lot"}
    assert any("open" in n for n in res.notes)


def test_happy_path_assembles_without_ownership_error():
    prev = prev_board()
    data = copy.deepcopy(prev)
    res = run(FakeSession(nse=nse_ok()), prev)
    assemble.apply(data, res)
    assert [r["name"] for r in data["mainboard"]][:1] == ["Anlon Healthcare Limited"]   # sorted by open date
    assert data["expected"] == prev["expected"]


def test_nse_blocked_bse_wins():
    prev = prev_board()
    res = run(FakeSession(nse=nse_blocked(), bse=bse_ok()), prev)
    assert res.ok and res.source == "bse"
    assert [t["source"] for t in res.tried] == ["nse", "bse"] and res.tried[0]["kind"] == "blocked"
    mb, sme = by_name(res.replace["mainboard"]), by_name(res.replace["sme"])
    assert "Sona Selection India" in mb, "BSE's 'SONA SELECTION INDIA LTD' must map to the board spelling"
    sona = mb["Sona Selection India"]
    assert sona["lotSize"] == 150 and sona["symbol"] == "SONASEL" and sona["gmp"] == 18   # carried forward
    assert "BSE public issues (api)" in sona["sources"] and "NSE ipo-current-issue" in sona["sources"]
    assert sme["Vidya Wires Limited"]["type"] == "NSE SME", "exchange label is not rewritten by a BSE day"
    assert mb["Kabra Jewels"]["status"] == "Upcoming" and mb["Kabra Jewels"]["bseIpoNo"] == "7984"
    assert "Anlon Healthcare Limited" not in mb, "BSE list has no past issues; a Closed row without today's source drops"
    assert res.unresolved and "BSE" in res.unresolved[0]


@needs_selectolax
def test_nse_blocked_bse_api_down_legacy_table_wins():
    prev = prev_board()
    res = run(FakeSession(nse=nse_blocked(), html=html_ok()), prev)
    assert res.ok and res.source == "bse"
    mb = by_name(res.replace["mainboard"])
    assert "Sona Selection India" in mb and mb["Sona Selection India"]["bseIpoNo"] == "7973"
    assert by_name(res.replace["sme"])["Vidya Wires Limited"]["bandHigh"] == 52.0


def test_both_fail_keeps_previous_rows():
    prev = prev_board()
    data = copy.deepcopy(prev)
    res = run(FakeSession(nse=nse_blocked(), bse={"/GetPublicIssue_par_updated/w": SourceDown("bse", "timeout")},
                          html={"IPOIssues_new.aspx": text("bse", "IPOIssues_new-empty.html")}), prev)
    assert not res.ok and res.error["kind"] in ("changed", "down", "blocked")
    assert [t["source"] for t in res.tried][:2] == ["nse", "bse"] and not any(t["ok"] for t in res.tried)
    assemble.apply(data, res)
    assert data == prev, "a failed calendar leaves mainboard/sme/lot/expected exactly as they were"


def test_empty_lists_everywhere_is_source_changed_not_success():
    prev = prev_board()
    empty = load("nse", "empty-list.json")
    res = run(FakeSession(nse={"/api/ipo-current-issue": empty, "/api/all-upcoming-issues": empty,
                               "/api/public-past-issues": empty}), prev)
    assert not res.ok
    assert res.tried[0]["source"] == "nse" and res.tried[0]["kind"] == "changed"
    assert "empty" in res.tried[0]["detail"]


def test_nse_upcoming_empty_is_tolerated_when_current_has_rows():
    n = nse_ok()
    n["/api/all-upcoming-issues"] = load("nse", "empty-list.json")
    res = run(FakeSession(nse=n), prev_board())
    assert res.ok and res.source == "nse"
    assert "Tejas Cargo Logistics" not in by_name(res.replace["mainboard"])


def test_name_matching_helper():
    existing = ["Sona Selection India", "Kabra Jewels & Sons Ltd", "Vidya Wires Limited"]
    assert calendar.match_name("Sona Selection India Limited", existing) == "Sona Selection India"
    assert calendar.match_name("SONA SELECTION INDIA LTD", existing) == "Sona Selection India"
    assert calendar.match_name("Kabra Jewels and Sons Limited IPO", existing) == "Kabra Jewels & Sons Ltd"
    assert calendar.match_name("Vidya Wires Ltd.", existing) == "Vidya Wires Limited"
    assert calendar.match_name("Tejas Cargo Logistics Limited", existing) is None
    assert calendar.match_name("", existing) is None


def test_listed_row_drops_after_grace_day():
    prev = prev_board()
    res = run(FakeSession(nse=nse_ok()), prev, today=dt.date(2026, 9, 18))
    assert res.ok
    assert "Anlon Healthcare Limited" not in by_name(res.replace["mainboard"])
    assert by_name(res.replace["mainboard"])["Sona Selection India"]["status"] == "Closed"


def test_detail_block_does_not_sink_the_calendar():
    n = nse_ok()
    n["detail:*"] = SourceBlocked("nse", "HTTP 403", "x", 403)
    for k in ("detail:SONASEL", "detail:VIDYAWIRE", "detail:KABRAJEW"):
        del n[k]
    res = run(FakeSession(nse=n), prev_board())
    assert res.ok and res.source == "nse"
    mb = by_name(res.replace["mainboard"])
    assert mb["Sona Selection India"]["lotSize"] == 150, "lot carried from prev when ipo-detail is blocked"
    assert mb["Kabra Jewels"]["lotSize"] is None


def test_names_matcher_rules():
    from collector.names import Matcher, display_name
    rows = [{"name": "NSE (National Stock Exchange of India)"}, {"name": "Coal India"},
            {"name": "Hero FinCorp", "symbol": "HEROFIN"}, {"name": "Asset Reconstruction Company (India)"}]
    m = Matcher(rows, {"Sonaselection India Limited": "Sona Selection India"})
    assert m.match("National Stock Exchange of India Limited") == "NSE (National Stock Exchange of India)"
    assert m.match("Asset Reconstruction Company (India) Ltd") == "Asset Reconstruction Company (India)"
    assert m.match("Totally Different Name Ltd", symbol="herofin") == "Hero FinCorp"      # symbol beats spelling
    assert m.match("Sonaselection India Limited") == "Sona Selection India"               # alias, row not on board yet
    assert m.match("Bharat Coking Coal India Limited") is None                             # subset must not match
    assert m.match("Hero Motors Limited") is None
    assert display_name("Hero Motors Limited") == "Hero Motors"
    assert display_name("Jindal Supreme (India) Limited") == "Jindal Supreme (India)"
    assert display_name("Kabra Jewels Pvt. Ltd.") == "Kabra Jewels"


def test_bse_is_merged_into_the_nse_calendar():
    """NSE wins the chain; BSE rows fill gaps on shared names and add what only BSE lists."""
    import json
    import pathlib
    live = json.loads((pathlib.Path(__file__).parent.parent / "data/fixtures/live-2026-09-17/bse_issues.json").read_text())
    n = nse_ok()
    res = run(FakeSession(nse=n, bse={"/GetPublicIssue_par_updated/w": live}), prev_board(), today=TODAY)
    assert res.ok and res.source == "nse"
    sme = by_name(res.replace["sme"])
    bse_only = [r for r in sme.values() if r["type"] == "BSE SME"]
    assert bse_only, "issues only BSE lists must reach the board as BSE SME"
    assert all(r.get("bseIpoNo") for r in bse_only)
    assert not any(r["name"].isupper() or r["name"].endswith("Limited") for r in bse_only), "house spelling for new rows"
    assert sme["Vidya Wires Limited"]["type"] == "NSE SME", "an NSE row is never relabelled by the BSE merge"
    assert any("+bse=" in x for x in res.notes)


def test_nse_sme_detail_uses_its_own_labels():
    """Live, 18 Sep 2026: an NSE Emerge issue page says "Price Range" and "Lot Size", not "Price Band" / "Bid Lot"."""
    import json
    import pathlib
    from collector.sources import nse_ipo
    raw = json.loads((pathlib.Path(__file__).parent.parent / "data/fixtures/nse/ipo-detail-KHERIAAUTO-sme.json").read_text())
    detail = {"dataList": raw["issueInfo"]["dataList"]}
    assert nse_ipo.detail_lot(detail) | {"issueSizeCr": None} == {"lotSize": 1200, "issueSizeCr": None, "bandLow": 96.0, "bandHigh": 101.0}
