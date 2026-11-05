"""A module on its working fallback past a source that is down BY DESIGN is a known state, shown lavender in the
modules table and kept out of the verdict; a fallback past any other source still warns. KNOWN_SOURCES is empty since
5 Nov 2026 (Angel One and ipopremium dropped, BSE answers), so these tests install an entry to exercise the rule."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("audit", pathlib.Path(__file__).resolve().parent.parent / "scripts/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def _doc(*checks):
    return {"integrity": {"checks": [{"area": a, "status": "ok", "method": m, "asOf": "2026-10-30T00:00:00+05:30"} for a, m in checks]}}


def test_a_fallback_past_known_sources_is_known_not_warn(monkeypatch):
    monkeypatch.setattr(audit, "KNOWN_SOURCES", {"angelone": "Angel One (test entry)", "ipopremium": "ipopremium (test entry)"})
    mods = audit.modules(_doc(("listings", "angelone:down, yahoo:ok"), ("gmp", "investorgain:ok, ipowatch:ok, ipopremium:blocked")))
    assert [m["level"] for m in mods] == ["known", "known"]
    assert "Angel One" in mods[0]["known"] and "ipopremium" in mods[1]["known"]
    items = audit.verdict(mods, [], {}, 0)["items"]
    assert not [i for i in items if i["where"] == "modules" and i["kind"] == "fault"]
    assert [i["kind"] for i in items] == ["state", "state"], "known gaps are shown as states, with their reason"


def test_a_fallback_past_an_unknown_source_still_warns():
    assert audit.KNOWN_SOURCES == {}, "nothing is down by design any more; every fallback is a finding"
    mods = audit.modules(_doc(("filings", "bse_ann:changed, sebi:changed, nse_ann:ok"), ("filings2", "bse_ann:changed, nse_ann:ok")))
    assert [m["level"] for m in mods] == ["warn", "warn"] and mods[0]["known"] is None, "bse_ann is a real source again"
    items = audit.verdict(mods, [], {}, 0)["items"]
    assert items and items[0]["level"] == "warn" and "sebi:changed" in items[0]["text"]


def test_fallback_sources_parses_the_method_string():
    assert audit.fallback_sources("angelone:down, yahoo:ok") == [("angelone", "down")]
    assert audit.fallback_sources("nse:ok") == []
    assert audit.fallback_sources("") == []
