"""scripts/audit.py — the facts behind /admin — and the integrity carry-forward it relies on."""
import datetime as dt
import importlib.util
import json
import pathlib

from collector import assemble
from collector.result import Result

spec = importlib.util.spec_from_file_location("audit", pathlib.Path(__file__).resolve().parent.parent / "scripts/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

AS_OF = "2026-10-29T15:08:47+05:30"


def row(name, status, igId, open_, close, listing, **k):
    r = {"name": name, "status": status, "igId": igId, "open": open_, "close": close, "listing": listing,
         "lotSize": 100, "gmp": 10.0, "sub": {"total": 2.0}}
    r.update(k)
    return r


def doc(**over):
    d = {"meta": {"asOf": AS_OF, "label": "x", "unresolved": [], "awaitingData": []},
         "mainboard": [row("Good Co", "Open", "1", "2026-10-28", "2026-10-30", "2026-11-04"),
                       row("Done Co", "Listed", "2", "2026-10-20", "2026-10-22", "2026-10-27", listingPrice=120)],
         "sme": [row("Late Co", "Open", "3", "2026-10-20", "2026-10-22", "2026-10-27")],
         "integrity": {"asOf": AS_OF, "checks": [
             {"area": "gmp", "method": "investorgain:ok", "status": "ok", "asOf": "9-Oct 9:37"},
             {"area": "listings", "method": "angelone:down, yahoo:ok", "status": "ok", "asOf": "2026-10-29"},
             {"area": "offers", "method": "bse:blocked", "status": "blocked", "asOf": None},
         ]},
         "evidence": {"warnings": [{"code": "a", "text": "A"}]}, "logos": {"1": {"src": "x"}}, "tape": {"dates": ["2026-10-28"]}}
    d.update(over)
    return d


def test_anomalies_name_the_rows_and_the_check():
    finds = {f["check"]: f for f in audit.anomalies(doc())}
    assert finds["still Open past its close date"]["rows"] == ["Late Co (sme) closed 2026-10-22"]
    assert finds["still Open past its close date"]["level"] == "bad"
    assert "Listed with no listing price" not in finds          # Done Co has one


def test_a_fallback_past_a_by_design_source_is_known_and_a_known_block_is_known():
    m = {x["area"]: x for x in audit.modules(doc())}
    assert m["listings"]["level"] == "known" and "Angel One" in m["listings"]["known"]   # angelone is down by design (no secrets)
    assert m["offers"]["level"] == "warn" and not m["offers"]["known"]         # a blocked offers leg is a finding again (5 Nov 2026: BSE's legacy page answers)
    assert m["gmp"]["asOf"] is None and m["gmp"]["asOfRaw"] == "9-Oct 9:37"      # never an age from a source's own stamp
    d = doc(); d["integrity"]["checks"][0]["method"] = "investorgain:ok, ipowatch:ok, ipopremium:blocked"
    m = {x["area"]: x for x in audit.modules(d)}
    assert m["gmp"]["level"] == "known" and "ipopremium" in m["gmp"]["known"]       # ipopremium 403s by design
    d["integrity"]["checks"][0]["method"] = "investorgain:ok, ipowatch:changed, ipopremium:blocked"
    assert {x["area"]: x for x in audit.modules(d)}["gmp"]["level"] == "warn"       # ipowatch changing is not


def test_a_source_switch_is_a_failed_source_or_a_new_first_source_never_a_longer_chain():
    def switches(old_method, new_method, status="ok"):
        prev, now = doc(), doc()
        prev["integrity"]["checks"][0]["method"], now["integrity"]["checks"][0]["method"] = old_method, new_method
        now["integrity"]["checks"][0]["status"] = status
        return [s["area"] for s in audit.diff(now, prev)["sourceSwitches"]]
    assert switches("investorgain:ok", "investorgain:ok, ipowatch:ok, ipopremium:blocked") == []   # ran further, past a known 403
    assert switches("investorgain:ok", "investorgain:ok, ipowatch:changed") == ["gmp"]            # a source that is not down by design
    assert switches("investorgain:ok", "ipowatch:ok") == ["gmp"]                                   # a different first source
    assert switches("investorgain:ok", "investorgain:ok", status="blocked") == ["gmp"]             # or a status change


def test_diff_tells_a_scheduled_retirement_from_a_vanishing():
    prev = doc()
    prev["meta"]["asOf"] = "2026-10-28T23:45:46+05:30"
    prev["mainboard"].append(row("Gone Co", "Upcoming", "9", "2026-11-02", "2026-11-04", "2026-11-09"))
    prev["mainboard"][0]["status"] = "Upcoming"
    new = doc()
    new["mainboard"] = [r for r in new["mainboard"] if r["name"] != "Done Co"]     # listed 27 Oct: due to retire
    d = audit.diff(new, prev)
    assert d["boards"]["mainboard"]["retired"] == ["Done Co"]
    assert d["boards"]["mainboard"]["vanished"] == ["Gone Co"]
    assert d["statusMoves"] == [{"name": "Good Co", "board": "mainboard", "from": "Upcoming", "to": "Open"}]
    v = audit.verdict(audit.modules(new), [], d, 0)
    assert v["level"] == "bad" and any("left the board early" in i["text"] for i in v["items"])


def test_build_is_ok_when_nothing_is_wrong():
    d = doc(sme=[])
    d["integrity"]["checks"] = [c for c in d["integrity"]["checks"] if c["area"] == "gmp"]
    rep = audit.build(d, None)
    assert rep["verdict"] == {"level": "ok", "items": []}
    assert rep["doc"]["tapeLastDay"] == "2026-10-28" and rep["doc"]["bytesCompact"] > 0
    assert rep["diff"] == {"prevAsOf": None}


def test_previous_picks_the_newest_history_file_before_the_document(tmp_path):
    for day, as_of in (("2026-10-28", "2026-10-28T23:45:46+05:30"), ("2026-10-29", AS_OF)):
        (tmp_path / f"{day}.json").write_text(json.dumps({"meta": {"asOf": as_of}}))
    assert audit.previous(doc(), tmp_path)["meta"]["asOf"].startswith("2026-10-28")


def test_stamp_carries_forward_checks_of_modules_that_did_not_run():
    data = {"integrity": {"asOf": "2026-10-29T06:43:00+05:30", "checks": [
        {"area": "tape", "method": "nsearchives:ok", "status": "ok", "asOf": "2026-10-28"},
        {"area": "gmp", "method": "investorgain:ok", "status": "ok", "asOf": "old"},
        {"area": "run", "method": "collector", "status": "ok", "note": "old run"},
    ]}, "meta": {}}
    r = Result(module="gmp").won("investorgain", "new")
    assemble.stamp(data, [r], dt.datetime(2026, 10, 29, 9, 7, tzinfo=dt.UTC), [], 1, 1.0)
    by = {c["area"]: c for c in data["integrity"]["checks"]}
    assert by["gmp"]["asOf"] == "new" and "carried" not in by["gmp"]
    assert by["tape"]["carried"] is True and by["tape"]["asOf"] == "2026-10-28"
    assert by["run"]["note"] != "old run"


def test_stamp_writes_last_ok_and_due_by_and_keeps_last_ok_through_a_failure():
    t1 = dt.datetime(2026, 10, 29, 9, 40, tzinfo=assemble.IST)          # a Thursday
    data = {"integrity": {"checks": []}, "meta": {}}
    assemble.stamp(data, [Result(module="gmp").won("investorgain", "x"), Result(module="tape").won("nsearchives", "x")],
                   t1, [], 1, 1.0)
    by = {c["area"]: c for c in data["integrity"]["checks"]}
    assert by["gmp"]["lastOk"] == t1.isoformat()
    assert by["gmp"]["dueBy"] == "2026-10-29T10:52:00+05:30"            # next slot 10:07 + 45 min
    assert by["tape"]["dueBy"] == "2026-10-29T18:58:00+05:30"           # daily module: next full run 18:13 + 45 min
    bad = Result(module="gmp")
    bad.ok = False
    bad.error = {"kind": "blocked", "detail": "403"}
    assemble.stamp(data, [bad], t1 + dt.timedelta(hours=1), [], 1, 1.0)
    g = {c["area"]: c for c in data["integrity"]["checks"]}["gmp"]
    assert g["status"] == "blocked" and g["lastOk"] == t1.isoformat() and g["dueBy"] is None


def test_due_by_has_no_intraday_slots_at_weekends():
    fri = dt.datetime(2026, 10, 30, 17, 40, tzinfo=assemble.IST)        # after the 17:37 run
    assert assemble.due_by("gmp", fri) == "2026-10-30T18:58:00+05:30"   # the 18:13 full run still comes today
    sat = dt.datetime(2026, 10, 31, 7, 0, tzinfo=assemble.IST)
    assert assemble.due_by("gmp", sat) == "2026-10-31T18:58:00+05:30"   # no intraday on Saturday
    assert assemble.due_by("gmp", dt.datetime(2026, 11, 1, 19, 0, tzinfo=assemble.IST)) == "2026-11-02T07:28:00+05:30"


def test_a_quota_row_whose_ipo_listed_is_bad_and_an_untouched_row_warns():
    d = doc(quota=[{"name": "Reliance Jio", "bucket": "approved", "stageDate": "2026-08-28"},      # alias -> Jio Platforms
                   {"name": "Fresh Co", "bucket": "drhp", "stageDate": "2026-10-20"},
                   {"name": "Old Co", "bucket": "awaited", "stageDate": "2026-06-01"},
                   {"name": "Undated Co", "bucket": "approved"},
                   {"name": "Done Co Quota", "bucket": "done", "stageDate": "2026-01-01"}],
            listedPerf=[{"name": "Jio Platforms", "igId": "2306", "date": "2026-10-28"}])
    finds = {f["check"]: f for f in audit.anomalies(d)}
    assert finds["quota row whose IPO has listed"]["rows"] == ["Reliance Jio (Jio Platforms)"]
    assert finds["quota row whose IPO has listed"]["level"] == "bad"
    assert finds["quota row untouched for 60+ days"]["rows"] == ["Reliance Jio since 2026-08-28", "Old Co since 2026-06-01"]
    assert finds["quota row untouched for 60+ days"]["level"] == "warn"
    assert finds["quota row with no dated stage"]["rows"] == ["Undated Co"]
    assert "Fresh Co" not in str(finds) and "Done Co Quota" not in str(finds)


def test_quota_found_disagreements_each_warn_with_both_sides():
    """filings.discover's quotaFound against the quota list and the board: four checks, all warn, none a verdict."""
    rec = {"flag": True, "offered": 1000, "src": "ig", "at": "2026-10-29"}
    d = doc(mainboard=[row("Jio Platforms", "Open", "2306", "2026-10-21", "2026-10-23", "2026-10-28", shareholderQuota=rec),
                       row("Hero FinCorp", "Upcoming", "2400", "2026-11-10", "2026-11-12", "2026-11-17",
                           shareholderQuota={"flag": False, "src": "ig", "at": "2026-11-04", "flagOnly": True}),
                       row("Linked Co", "Upcoming", "2500", "2026-11-10", "2026-11-12", "2026-11-17", shareholderQuota=None)],
            quota=[{"name": "Reliance Jio", "bucket": "done", "igId": "2306", "stageDate": "2026-10-28"},
                   {"name": "Hero FinCorp", "bucket": "approved", "igId": "2400", "stageDate": "2026-10-20"},
                   {"name": "Linked Co", "bucket": "approved", "igId": "2500", "stageDate": "2026-10-20"},
                   {"name": "Done Co", "bucket": "done", "igId": "2400", "stageDate": "2026-10-20"}],
            quotaFound=[{"igId": "2306", "name": "Jio Platforms", "board": "mainboard", "parent": "Reliance Industries Limited",
                         "parentSymbol": "RELIANCE", "quotaRow": "Reliance Jio", "witness": {"record": True, "book": False}},
                        {"igId": "2600", "name": "Surprise Co", "board": "sme", "parent": None, "parentSymbol": None,
                         "parentId": "77", "quotaRow": None, "witness": {"record": True, "book": None}},
                        {"igId": "2700", "name": "Book Only Co", "board": "mainboard", "parent": None, "parentSymbol": None,
                         "quotaRow": None, "witness": {"record": False, "book": True}}])
    finds = {f["check"]: f for f in audit.anomalies(d)}
    assert finds["IPO with a shareholder reservation not on the quota list"]["rows"] == ["Surprise Co (sme; ig 77)"]
    assert finds["shareholder reservation the book does not show"]["rows"] == ["Jio Platforms (mainboard; Reliance Industries Limited)"]
    assert finds["shareholder book with no reservation on record"]["rows"] == ["Book Only Co (mainboard; parent unknown)"]
    assert finds["quota row whose record shows no reservation"]["rows"] == ["Hero FinCorp (Hero FinCorp, the dead flag alone, ig 2026-11-04)"]
    assert all(finds[k]["level"] == "warn" for k in finds if "shareholder" in k or "reservation" in k)
    assert "Linked Co" not in str(finds), "no record yet: nothing to say"
    assert "Done Co" not in str(finds), "a done row is not read against the record"
    assert audit.build(d, None)["diff"] == {"prevAsOf": None}


def test_quota_found_counts_in_the_diff():
    prev = doc(quotaFound=[])
    prev["meta"]["asOf"] = "2026-10-28T23:45:46+05:30"
    new = doc(quotaFound=[{"igId": "1", "name": "x", "witness": {}}])
    assert audit.diff(new, prev)["counts"]["quotaFound"] == [0, 1]
