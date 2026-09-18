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
