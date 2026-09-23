import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("validate", pathlib.Path(__file__).resolve().parent.parent / "scripts/validate.py")
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


def test_census_counts_collections_not_the_shape_of_whichever_row_came_last():
    rich = {"name": "A", "facts": {"kpis": {str(i): i for i in range(15)}}, "sources": ["u1", "u2", "u3"]}
    thin = {"name": "B", "facts": {"kpis": {str(i): i for i in range(7)}}, "sources": ["u4"]}
    a = validate.census({"mainboard": [thin, rich], "lot": {"A": {"shares": 1}, "B": {"shares": 2}}})
    b = validate.census({"mainboard": [rich, thin], "lot": {"A": {"shares": 1}, "B": {"shares": 2}}})
    assert a == b, "the order of rows is not information"
    assert a["/mainboard"] == 2 and a["/mainboard[]/sources"] == 4 and a["/lot"] == 2
    assert not any(k.startswith("/mainboard[]/facts") for k in a)
    lost = validate.census({"mainboard": [dict(rich, sources=[]), dict(thin, sources=[])], "lot": {}})
    assert lost["/mainboard[]/sources"] == 0 and lost["/lot"] == 0, "a real loss inside rows, or of a top-level dict, still shows"


def test_rows_that_age_off_the_board_on_schedule_are_not_a_loss():
    rows = lambda n, listing: [{"name": f"co{i}-{listing}", "status": "Listed", "listing": listing, "sources": ["a", "b", "c"]} for i in range(n)]  # noqa: E731
    live = [{"name": f"open{i}", "status": "Open", "listing": "2026-09-24", "sources": ["a"]} for i in range(13)]
    prev = {"meta": {"asOf": "2026-09-18T22:48:00+05:30"}, "mainboard": rows(6, "2026-09-17") + live, "sme": []}
    new = {"meta": {"asOf": "2026-09-19T00:07:00+05:30"}, "mainboard": live, "sme": []}
    kept = validate.retire_due(prev, new)
    assert len(kept["mainboard"]) == 13 and len(prev["mainboard"]) == 19, "due rows are left out of the comparison; prev is not mutated"
    assert validate.census(kept) == validate.census(new), "the six that listed on the 17th left on schedule: no loss anywhere"
    early = {"meta": new["meta"], "mainboard": live[:6], "sme": []}                      # rows vanishing BEFORE their time still count
    assert validate.census(validate.retire_due(prev, early))["/mainboard"] == 13 and validate.census(early)["/mainboard"] == 6
    assert validate.retire_due(prev, {"meta": {}}) is prev, "no date to reason from: compare everything"


def test_a_retired_rows_research_record_leaves_with_it():
    prev = {"mainboard": [{"name": "Gone", "listing": "2026-09-18", "igId": 2277}, {"name": "Fresh", "listing": "2026-09-21", "igId": "2300"}],
            "sme": [], "records": {"2277": {"name": "Gone", "financials": {"rows": [1, 2, 3]}}, "2300": {"name": "Fresh"}, "2100": {"name": "No row"}}}
    new = {"meta": {"asOf": "2026-09-22T06:43:00+05:30"}}
    kept = validate.retire_due(prev, new)
    assert [r["name"] for r in kept["mainboard"]] == ["Fresh"]
    assert set(kept["records"]) == {"2300", "2100"}, "the record of a row that aged off on schedule is not a loss"
    assert set(prev["records"]) == {"2277", "2300", "2100"}, "prev is never mutated"


def test_a_records_sheet_table_shrinking_and_a_small_nested_list_are_not_a_loss(tmp_path):
    import json, subprocess, sys
    base = validate.retire_due  # noqa: F841  (module import check)
    doc = {k: [] for k in validate.TOP_LEVEL}
    doc.update({"meta": {"asOf": "2026-09-23T06:43:00+05:30", "label": "x", "unresolved": []}, "lot": {}, "priceHistory": {}, "current": {}, "sheets": {},
                "flows": {"history": []}, "investors": {}, "integrity": {"checks": []}, "offers": {}})
    doc["mainboard"] = [{"name": f"co{i}", "status": "Upcoming", "listing": "2026-12-01", "sources": ["a", "b", "c"], "facts": {"recs": [1, 2, 3]}} for i in range(12)]
    doc["listedPerf"] = [{"name": f"p{i}", "date": "2026-01-01"} for i in range(40)]
    doc["records"] = {str(i): {"name": f"r{i}", "reservation": {"rows": [[1, 2]] * 8}} for i in range(9)}
    prev = json.loads(json.dumps(doc))
    for r in doc["mainboard"][:3]:
        r["facts"]["recs"] = []                                   # 36 -> 27 across rows: 25% but tiny; must not count
    for i in range(9):
        doc["records"][str(i)]["reservation"]["rows"] = [[1, 2]] * 3
    (tmp_path / "prev.json").write_text(json.dumps(prev)); (tmp_path / "new.json").write_text(json.dumps(doc))
    out = subprocess.run([sys.executable, str(validate.__file__), str(tmp_path / "new.json"), "--prev", str(tmp_path / "prev.json"), "--max-age-hours", "999999"], capture_output=True, text=True)
    assert "reservation" not in out.stdout and "facts/recs" not in out.stdout, out.stdout
    doc["records"] = {}                                           # the number of records still counts
    (tmp_path / "new.json").write_text(json.dumps(doc))
    out = subprocess.run([sys.executable, str(validate.__file__), str(tmp_path / "new.json"), "--prev", str(tmp_path / "prev.json"), "--max-age-hours", "999999"], capture_output=True, text=True)
    assert "latest/records: 9 -> 0" in out.stdout
