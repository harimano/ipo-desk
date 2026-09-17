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
