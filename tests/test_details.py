"""details — the per-IPO record. Every fixture here is a real response recorded on 18 Sep 2026."""
import copy
import datetime as dt
import json
import pathlib

import pytest

from collector import assemble
from collector.errors import SourceBlocked, SourceChanged, SourceDown
from collector.modules import details
from collector.result import Result
from collector.sources import investorgain as ig

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/investorgain"
LIST = json.loads((FX / "list-read.json").read_text())
RECORDS = {"2305": json.loads((FX / "ipo-detail-2305-NSE-open.json").read_text()),
           "2119": json.loads((FX / "ipo-detail-2119-KANOHAR-listed.json").read_text())}
TODAY = dt.date(2026, 9, 18)
NOW = dt.datetime(2026, 9, 18, 6, 45, tzinfo=details.IST)
NSE = "NSE (National Stock Exchange of India)"


class FakeSession:
    def __init__(self, listing=LIST, records=RECORDS):
        self.listing, self.records, self.calls = listing, records, []

    def get_json(self, url, *, source=None, headers=None, **kw):
        if url.endswith("/list-read"):
            self.calls.append("list")
            v = self.listing
        else:
            ig_id = url.rsplit("/", 1)[1]
            self.calls.append(f"detail:{ig_id}")
            v = self.records.get(ig_id, SourceDown("investorgain", "HTTP 404", url, 404))
        if isinstance(v, Exception):
            raise v
        return v

    def get_bytes(self, *a, **kw):
        raise AssertionError("details fetched a file")


def prev():
    return {"mainboard": [
                {"name": NSE, "symbol": "NSE", "type": "Mainboard", "status": "Open", "open": "2026-09-17", "close": "2026-09-21",
                 "allotment": None, "listing": None, "bandLow": 1700.0, "bandHigh": 1785.0, "lotSize": 8, "issueSizeCr": 15822.76,
                 "gmp": 146.0, "sub": {"total": 0.29}},
                {"name": "Kanohar Electricals", "igId": "2119", "symbol": "KANOHAR", "type": "Mainboard", "status": "Listed",
                 "open": "2026-09-08", "close": "2026-09-10", "listing": "2026-09-16", "bandHigh": 632.0, "lotSize": 23,
                 "gmp": 198, "listingPrice": None}],
            "sme": [],
            "anchors": [{"name": "Kanohar Electricals", "source": "nse-anchor-letter", "date": "2026-09-05", "amountCr": 316.72,
                         "issueSizeCr": 1055.74, "count": 42, "topTierShare": 66.69, "anchor": "read from the letter",
                         "investors": [{"name": "SBI MF", "cat": "MF", "amountCr": 40, "pct": 12.6}]}]}


def run(session=None, doc=None, today=TODAY, now=NOW):
    return details.run(session or FakeSession(), doc or prev(), Result(module="details"), today=today, now=now)


def test_the_record_is_typed_and_complete():
    k, n = ig.normalise_detail(RECORDS["2119"]), ig.normalise_detail(RECORDS["2305"])
    assert (k["symbol"], k["bseCode"], k["isin"]) == ("KANOHAR", "544911", "INE877D01025")
    assert (k["open"], k["close"], k["allotment"], k["listing"]) == ("2026-09-08", "2026-09-10", "2026-09-11", "2026-09-16")
    assert (k["issueSizeCr"], k["freshCr"], k["ofsCr"], k["lotSize"], k["listingPrice"]) == (1055.74, 300.0, 755.74, 23, 685.5)
    assert (k["anchorShares"], k["anchorCr"], k["lockIn30"], k["lockIn90"]) == (5011424, 316.72, "2026-10-10", "2026-12-09")
    assert k["sub"] == {"qib": 215.37, "nii": 87.74, "retail": 20.51, "total": 90.59, "asOf": "2026-09-10T18:56:00+05:30"}
    assert k["facts"]["kpis"]["roce"] == 70.13 and k["facts"]["kpis"]["asOf"] == "2026-03-31", "the later of two reporting periods"
    assert set(k["facts"]["docs"]) == {"drhp", "rhp", "prospectus", "anchorLetter", "allotment"}
    assert n["anchorCr"] == 6746.18 and n["sub"]["employee"] == 0.97 and n["listing"] == "2026-09-24"
    assert n["gmp"] == {"value": 142.0, "pct": 7.96, "estListing": 1927.0, "asOf": "2026-09-17T23:37:00+05:30"}
    assert len(ig.parse_ipo_list(LIST)) == 31 and {"igId": "2305", "name": "NSE"}.items() <= next(
        r for r in ig.parse_ipo_list(LIST) if r["igId"] == "2305").items()


def test_every_placeholder_is_filled_and_the_exchange_keeps_what_it_gave():
    before = prev()
    s = FakeSession()
    res = run(s, before)
    assert res.ok and s.calls == ["list", "detail:2305", "detail:2119"], "open issues first; one list call"
    nse = res.rows["mainboard"][NSE]
    assert nse["igId"] == "2305" and (nse["allotment"], nse["listing"]) == ("2026-09-22", "2026-09-24")
    assert (nse["issueSizeCr"], nse["ofsCr"], nse["anchorShares"]) == (22561.57, 22561.57, 37793739)
    assert (nse["gmp"], nse["gmpTrend"], nse["gmpAsOf"]) == (142.0, "down", "2026-09-17T23:37:00+05:30")
    assert nse["sub"]["total"] == 0.43 and nse["facts"]["kpis"]["pe"] == 42.89
    assert "isin" not in nse, "no ISIN before listing: a field the record lacks is left out, never blanked"
    assert not {"bandHigh", "bandLow", "lotSize", "symbol", "open", "close"} & set(nse), "the exchange's own values are not overwritten"
    kan = res.rows["mainboard"]["Kanohar Electricals"]
    assert (kan["listingPrice"], kan["listingGainPct"]) == (685.5, 8.47) and "gmp" not in kan, "no grey-market quote after listing"

    data = copy.deepcopy(before)
    assemble.apply(data, res)                                           # ownership: rows patched, anchors replaced
    assert data["mainboard"][0]["listing"] == "2026-09-24" and before == prev(), "prev is never mutated"


def test_anchor_books_come_from_the_record_and_existing_books_are_left_alone():
    res = run()
    books = {a["name"]: a for a in res.replace["anchors"]}
    nse = books[NSE]
    assert (nse["amountCr"], nse["anchorShares"], nse["price"]) == (6746.18, 37793739, 1785.0)
    assert (nse["date"], nse["lockIn30"], nse["lockIn90"]) == ("2026-09-16", "2026-10-21", "2026-12-20")
    assert nse["investors"] == [] and nse["topTierShare"] is None and "30% of the issue" in nse["anchor"]
    kan, was = books["Kanohar Electricals"], prev()["anchors"][0]
    for f in ("investors", "topTierShare", "count", "amountCr", "anchor", "source", "issueSizeCr", "date"):
        assert kan[f] == was[f], f
    assert (kan["lockIn30"], kan["lockIn90"]) == ("2026-10-10", "2026-12-09")


def test_identity_needs_the_name_and_the_opening_date():
    doc = prev()
    doc["mainboard"][0]["open"] = "2026-11-02"                          # some later issue that merely shares the name
    s = FakeSession()
    res = run(s, doc)
    assert "detail:2305" not in s.calls and NSE not in res.rows.get("mainboard", {})
    assert any(NSE in u for u in res.unresolved)


def test_politeness_open_every_run_others_every_six_hours_settled_never():
    doc = prev()
    doc["mainboard"][0]["igId"] = "2305"
    doc["mainboard"][1]["igFetchedAt"] = (NOW - dt.timedelta(hours=1)).isoformat()
    s = FakeSession()
    assert run(s, doc).ok and s.calls == ["detail:2305"], "ids on file: no list call; Kanohar was fetched an hour ago"
    doc["mainboard"][1]["igFetchedAt"] = (NOW - dt.timedelta(hours=7)).isoformat()
    s = FakeSession()
    run(s, doc)
    assert "detail:2119" in s.calls
    doc["mainboard"][0]["listing"] = "2026-09-24"
    s = FakeSession()
    res = run(s, doc, today=dt.date(2026, 10, 30), now=NOW + dt.timedelta(days=42))
    assert res.ok and s.calls == [] and res.replace == {}, "everything listed long ago: nothing fetched, nothing replaced"


def test_failure_changes_nothing():
    down = SourceDown("investorgain", "HTTP 503", "u", 503)
    res = run(FakeSession(listing=down, records={}), {**prev(), "mainboard": prev()["mainboard"][:1]})
    assert not res.ok and res.rows == {} and res.replace == {}
    s = FakeSession(records={"2305": SourceBlocked("investorgain", "HTTP 403", "u", 403), "2119": RECORDS["2119"]})
    res = run(s)
    assert not res.ok and s.calls == ["list", "detail:2305"], "a 403 ends the conversation for this run"
    res = run(FakeSession(records={"2305": RECORDS["2305"]}))           # one record missing: the other still lands
    assert res.ok and list(res.rows["mainboard"]) == [NSE] and any("Kanohar" in n for n in res.notes)
    for bad in ({}, {"msg": "API not found"}, {"ipoData": []}, {"ipoData": [{"id": 1}]}):
        with pytest.raises(SourceChanged):
            ig.normalise_detail(bad)
    for bad in ({}, {"ipoList": []}, {"ipoList": [{"nothing": 1}]}):
        with pytest.raises(SourceChanged):
            ig.parse_ipo_list(bad)


def test_an_alias_for_a_row_outside_the_list_being_matched_is_not_a_crash():
    """Live, 18 Sep 2026: NSE's row already had its id, so it was not among the rows still to identify — and the
    alias "NSE" -> that row made the lookup blow up, leaving 17 brand-new listings bare."""
    doc = prev()
    doc["mainboard"][0]["igId"] = "2305"
    doc["mainboard"].append({"name": "A-One Steels", "type": "Mainboard", "status": "Upcoming", "open": "2026-09-24", "close": "2026-09-28"})
    s = FakeSession()
    res = run(s, doc)
    assert res.ok and "list" in s.calls
    assert details.assign_ids([doc["mainboard"][2]], ig.parse_ipo_list(LIST), {"NSE": NSE}) == {"A-One Steels": "1611"}


def test_a_zero_gmp_with_no_trade_behind_it_is_no_quote():
    raw = copy.deepcopy(RECORDS["2305"])
    raw["gmpData"] = [{**raw["gmpData"][0], "gmp": "0", "subject_to_sauda": "-", "est_profit": "", "gmp_active_record_flag": "1"}]
    assert ig.normalise_detail(raw)["gmp"] is None
    raw["gmpData"][0].update(subject_to_sauda="9100", est_profit="0")
    assert ig.normalise_detail(raw)["gmp"]["value"] == 0.0, "a traded premium of zero is still a quote"
