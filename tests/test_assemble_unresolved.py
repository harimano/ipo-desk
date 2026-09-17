from collector.assemble import merge_unresolved
from collector.result import Result


def _res(module, ok, notes=()):
    r = Result(module=module)
    r.ok = ok
    r.unresolved = list(notes)
    return r


def test_unresolved_is_current_state_not_a_log():
    prev = ["db-era note nobody can resolve", "[gmp] old gmp note", "[listings] no symbol on X", "[flows] kept"]
    out = merge_unresolved(prev, [_res("gmp", True, ["new gmp note"]), _res("listings", False), _res("news", True)])
    assert out == ["[listings] no symbol on X", "[flows] kept", "[gmp] new gmp note"]
    assert merge_unresolved(out, [_res("gmp", True, ["new gmp note"])]).count("[gmp] new gmp note") == 1


def test_research_overlay_does_not_put_an_old_parent_price_back(tmp_path):
    import json
    from collector.assemble import load_research_layer
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "jio.json").write_text(json.dumps(
        {"name": "Reliance Jio", "kind": "sheet", "business": "telecom", "parentPrice": {"value": 1309.5, "asOf": "2026-09-08"}}))
    data = {"sheets": {"Reliance Jio": {"parentPrice": {"value": 1342.0, "asOf": "2026-09-17"}}}, "current": {}, "quota": []}
    load_research_layer(data, tmp_path)
    assert data["sheets"]["Reliance Jio"]["parentPrice"] == {"value": 1342.0, "asOf": "2026-09-17"}
    assert data["sheets"]["Reliance Jio"]["business"] == "telecom"
