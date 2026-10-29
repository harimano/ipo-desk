"""A module on its working fallback past a source that is down BY DESIGN (no Angel One secrets; BSE's API refuses the
runners) is a known state, shown lavender in the modules table and kept out of the verdict. A fallback past any other
source still warns."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("audit", pathlib.Path(__file__).resolve().parent.parent / "scripts/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def _doc(*checks):
    return {"integrity": {"checks": [{"area": a, "status": "ok", "method": m, "asOf": "2026-10-30T00:00:00+05:30"} for a, m in checks]}}


def test_a_fallback_past_known_sources_is_known_not_warn():
    mods = audit.modules(_doc(("listings", "angelone:down, yahoo:ok"), ("filings", "bse_ann:changed, nse_ann:ok")))
    assert [m["level"] for m in mods] == ["known", "known"]
    assert "Angel One" in mods[0]["known"] and "bseindia" in mods[1]["known"]
    items = audit.verdict(mods, [], {}, 0)["items"]
    assert not [i for i in items if i["where"] == "modules"]


def test_a_fallback_past_an_unknown_source_still_warns():
    mods = audit.modules(_doc(("filings", "bse_ann:changed, sebi:changed, nse_ann:ok")))
    assert mods[0]["level"] == "warn" and mods[0]["known"] is None
    items = audit.verdict(mods, [], {}, 0)["items"]
    assert items and items[0]["level"] == "warn" and "sebi:changed" in items[0]["text"]


def test_fallback_sources_parses_the_method_string():
    assert audit.fallback_sources("angelone:down, yahoo:ok") == [("angelone", "down")]
    assert audit.fallback_sources("nse:ok") == []
    assert audit.fallback_sources("") == []
