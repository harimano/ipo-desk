"""planner — the calendar part. Fixtures are real InvestorGain responses recorded 29 Oct 2026 (reports 554 for Oct / Nov /
Dec and 607) and the per-IPO records already on file."""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from collector import assemble, layout, schema
from collector.errors import SourceChanged, SourceDown
from collector.modules import planner
from collector.result import Result
from collector.sources import investorgain as ig

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/investorgain"
TODAY = dt.date(2026, 10, 29)
R554 = {m: json.loads((FX / f"report-554-event-calendar-2026-{m}.json").read_text()) for m in ("10", "11")}
R554["12"] = json.loads((FX / "report-554-event-calendar-2026-12-empty.json").read_text())
R607 = json.loads((FX / "report-607-allotment-planner-2026-10-29.json").read_text())


class FakeSession:
    def __init__(self, r554=R554, r607=R607):
        self.r554, self.r607, self.calls = r554, r607, []

    def get_json(self, url, *, source=None, headers=None, **kw):
        self.calls.append(url)
        parts = url.split("/")                      # …/data-read/<report>/1/<month>/<year>/<fy>/0/all
        report, month = parts[-7], parts[-5]
        v = self.r607 if report == "607" else self.r554.get(f"{int(month):02d}", SourceDown("investorgain", "HTTP 404", url, 404))
        if isinstance(v, Exception):
            raise v
        return v


def doc():
    return {"mainboard": [
                {"name": "BLS Polymers", "igId": "1849", "type": "Mainboard", "status": "Open", "open": "2026-10-27", "close": "2026-10-29",
                 "allotment": "2026-10-30", "refund": "2026-11-02", "listing": "2026-11-03", "bandHigh": 150.0, "lotSize": 100,
                 "apply": {"retail": {"amount": 15000, "shares": 100, "lots": 1}, "snii": {"amount": 210000, "shares": 1400, "lots": 14},
                           "bnii": {"amount": 1005000, "shares": 6700, "lots": 67}}},
                {"name": "Bombay Coated and Special Steels", "igId": "1936", "type": "Mainboard", "status": "Open", "open": "2026-10-29",
                 "close": "2026-11-02", "allotment": "2026-11-03", "refund": "2026-11-04", "listing": "2026-11-05", "bandHigh": 82.0, "lotSize": 182},
                {"name": "Paras Healthcare", "igId": "1728", "type": "Mainboard", "status": "Listed", "open": "2026-10-21", "close": "2026-10-23",
                 "allotment": "2026-10-26", "refund": "2026-10-27", "listing": "2026-10-28"}],
            "sme": [{"name": "Wiscon Industries", "igId": "2356", "type": "NSE SME", "status": "Open", "open": "2026-10-27", "close": "2026-10-29",
                     "allotment": "2026-10-30", "refund": "2026-11-02", "listing": "2026-11-03", "bandHigh": 204.0, "lotSize": 600,
                     "apply": {"retail": {"amount": 244800, "shares": 1200, "lots": 2}}},
                    {"name": "Core4 Engineers", "igId": "2229", "type": "BSE SME", "status": "Closed", "open": "2026-10-23", "close": "2026-10-27",
                     "allotment": "2026-10-28", "listing": "2026-10-30", "bandHigh": 93.0, "lotSize": 1200}],      # no refund date on this row
            "anchors": [{"name": "BLS Polymers", "amountCr": 76.5, "lockIn30": "2026-12-02", "lockIn90": "2027-01-31"},
                        {"name": "Paras Healthcare", "amountCr": 652.5, "lockIn30": "2026-11-25", "lockIn90": "2027-01-24"},
                        {"name": "Zetwerk", "amountCr": 1000.0, "lockIn30": "2026-11-20", "lockIn90": "2027-01-19"}],
            "listedPerf": [{"name": "Zetwerk", "igId": "2279", "sme": False, "date": "2026-10-23"}],
            "quota": [{"name": "SBI Funds Management", "parent": "SBIN", "recordDate": "2026-11-20"},
                      {"name": "CMPDI", "parent": "COALINDIA", "recordDate": "2026-03-12"}]}


def run(session=None, d=None, today=TODAY):
    res = Result(module="planner", doc=d or doc())
    return planner.run(session or FakeSession(), {}, res, today=today)


def test_report_554_is_one_row_a_day_with_five_link_lists():
    ev = ig.parse_event_calendar(R554["10"], dt.date(2026, 10, 1))
    kinds = {e["kind"] for e in ev}
    assert kinds == {"open", "close", "allotment", "refund", "listing"} and len(ev) == 189
    bls = [e for e in ev if e["igId"] == "1849"]
    assert {e["kind"]: e["date"] for e in bls} == {"open": "2026-10-27", "close": "2026-10-29", "allotment": "2026-10-30"}
    assert bls[0]["name"] == "BLS Polymers", "the title's ' IPO Open' suffix is dropped, the badge text never read"
    assert ig.parse_event_calendar(R554["12"], dt.date(2026, 12, 1)) == [], "a month with rows and no events is a quiet month, not a changed source"


def test_report_554_shape_changes_raise():
    with pytest.raises(SourceChanged):
        ig.parse_event_calendar({"msg": "API not found"}, dt.date(2026, 10, 1))
    with pytest.raises(SourceChanged):
        ig.parse_event_calendar({"reportTableData": []}, dt.date(2026, 10, 1))
    gone = json.loads(json.dumps(R554["10"]))
    for r in gone["reportTableData"]:
        r.pop("Unblock")
    with pytest.raises(SourceChanged):
        ig.parse_event_calendar(gone, dt.date(2026, 10, 1))


def test_report_607_gives_retail_slots_and_the_fund_reuse_chain():
    rows = ig.parse_allotment_planner(R607)
    assert [r["igId"] for r in rows] == ["1635", "1642", "1849", "2288", "1936"] and all(r["sme"] is False for r in rows)
    bls = next(r for r in rows if r["igId"] == "1849")
    assert bls["retailSlots"] == 59500 and bls["retailAmount"] == 15000 and bls["lot"] == 100 and bls["close"] == "2026-10-29"
    bombay = rows[-1]
    assert bombay["fundReuse"] == ["1642", "1849"] and "retailSlots" not in bombay, "an upcoming issue has no allottee count yet — left out, not 0"
    with pytest.raises(SourceChanged):
        ig.parse_allotment_planner({"reportTableData": [{"Name": "no link"}]})


def test_the_record_states_what_one_application_blocks_per_category():
    rec = ig.normalise_detail(json.loads((FX / "ipo-detail-2305-NSE-open.json").read_text()))
    a = rec["apply"]
    assert a["retail"] == {"amount": 14280, "shares": 8, "lots": 1} and a["snii"]["lots"] == 15 and a["bnii"]["amount"] == 1013880
    assert a["employee"]["discount"] == 170.0 and a["employee"]["amount"] == 8 * (1785 - 170), "employee lot at the cap less the discount"
    assert "shareholder" not in a, "no shareholder reservation on this issue: no category, not a zero"
    jindal = ig.normalise_detail(json.loads((FX / "ipo-detail-2057-JINDAL-full.json").read_text()))["apply"]
    assert set(jindal) == {"retail", "snii", "bnii"}, "max_retail_qty is the sNII floor on every record read, so no retail ceiling is published"


def test_the_calendar_part_unites_rows_anchors_quota_and_the_report():
    s = FakeSession()
    res = run(s)
    assert res.ok and res.source == "investorgain"
    assert [(u.split("/")[-7], u.split("/")[-5]) for u in s.calls] == [("554", "10"), ("554", "11"), ("554", "12"), ("607", "10")], "the months the window touches, then 607"
    cal = res.replace["calendar"]
    assert cal["from"] == "2026-10-22" and cal["to"] == "2026-12-13"
    byk = lambda kind, name: [e for e in cal["events"] if e["kind"] == kind and e["name"] == name]
    assert byk("close", "BLS Polymers")[0]["date"] == "2026-10-29" and byk("close", "BLS Polymers")[0]["src"] == "record"
    assert len(byk("close", "BLS Polymers")) == 1, "the report's event for a board row is the same event, not a second one"
    assert byk("lockin30", "BLS Polymers")[0] == {"date": "2026-12-02", "kind": "lockin30", "name": "BLS Polymers", "igId": "1849", "sme": False, "src": "anchors", "amountCr": 38.25}
    assert byk("lockin30", "Paras Healthcare")[0]["date"] == "2026-11-25", "a listed row's anchor lock-in is still an event"
    assert byk("lockin30", "Zetwerk")[0]["igId"] == "2279" and byk("lockin30", "Zetwerk")[0]["sme"] is False, "off the board: identified through listedPerf"
    assert byk("record", "SBI Funds Management") and not byk("record", "CMPDI"), "a record date outside the window is not an event"
    assert byk("close", "EAAA India Alternatives")[0]["src"] == "ig554", "an issue the board no longer carries comes from the report alone"
    assert any(u["igId"] == "1635" for u in cal["unlinked"])
    assert cal["events"] == sorted(cal["events"], key=lambda e: (e["date"], planner.KIND_ORDER[e["kind"]], e["name"]))
    assert all(e["date"] >= cal["from"] and e["date"] <= cal["to"] for e in cal["events"])


def test_issues_carry_the_money_blocked_and_when_it_comes_back():
    cal = run().replace["calendar"]
    bls = cal["issues"]["1849"]
    assert bls["blocks"] == {"retail": {"amount": 15000, "shares": 100, "lots": 1}, "snii": {"amount": 210000, "shares": 1400, "lots": 14},
                             "bnii": {"amount": 1005000, "shares": 6700, "lots": 67}}
    assert bls["releaseDate"] == "2026-11-02" and bls["releaseSrc"] == "refund" and bls["blockedDays"] == 4
    assert bls["retailSlots"] == 59500 and bls["retailSizeCr"] == 90.0 and bls["lockIn30"] == "2026-12-02"
    assert cal["issues"]["1936"]["fundReuse"] == ["1849"], "only reuse links to issues the board knows (1642 is not on this board)"
    assert "blocks" not in cal["issues"]["1936"], "no terms on the row yet: nothing invented"
    core4 = cal["issues"]["2229"]
    assert core4["releaseDate"] == "2026-10-29" and core4["releaseSrc"] == "allotment+1" and core4["blockedDays"] == 2
    assert cal["issues"]["2356"]["sme"] is True and "1728" not in cal["issues"], "a listed row blocks nothing"


def test_a_date_disagreement_is_recorded_and_the_record_stands():
    d = doc()
    d["mainboard"][0]["allotment"] = "2026-10-31"
    res = run(d=d)
    cal = res.replace["calendar"]
    assert cal["conflicts"] == [{"igId": "1849", "name": "BLS Polymers", "kind": "allotment", "record": "2026-10-31", "report": "2026-10-30"}]
    assert [e["date"] for e in cal["events"] if e["kind"] == "allotment" and e["name"] == "BLS Polymers"] == ["2026-10-31"]
    assert any("BLS Polymers" in u for u in res.unresolved)


def test_the_report_is_the_source_and_607_is_optional():
    res = run(FakeSession(r554={}))
    assert not res.ok and res.error["kind"] == "down" and not res.replace
    quiet = {"10": {"reportTableData": [{"~OrderbyEventDt": "01-Oct-2026", "Open": "", "Close": "", "BOA": "", "Unblock": "", "Listing": ""}]}, "11": R554["11"], "12": R554["12"]}
    res = run(FakeSession(r554=quiet))
    assert not res.ok and res.error["kind"] == "changed", "the current month with no event at all is the report having changed"
    res = run(FakeSession(r607=SourceDown("investorgain", "timeout")))
    assert res.ok and "retailSlots" not in res.replace["calendar"]["issues"]["1849"] and any("607" in n for n in res.notes)


def test_ownership_layout_and_the_assembler():
    assert schema.OWNERS["calendar"] == "planner" and "calendar" in layout.GROUPS and layout.GROUPS["calendar"] == ("calendar",)
    layout.check_groups()
    data = schema.empty_data()
    res = run()
    assemble.apply(data, res)
    assert data["calendar"]["issues"]["1849"]["blocks"]["retail"]["amount"] == 15000
    parts = layout.split(data)
    assert "calendar.json" in parts and "calendar" in json.loads(parts["meta.json"])["files"]
    with pytest.raises(assemble.OwnershipError):
        assemble.apply(data, Result(module="calendar", replace={"calendar": {}}))
