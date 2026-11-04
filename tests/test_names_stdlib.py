"""collector.names must import and match strictly without rapidfuzz: the deploy job installs nothing and runs the
audit (scripts/audit.py -> collector.names) on the standard library alone — 4 Nov 2026, one deploy failed at import."""
import importlib
import sys

import pytest


@pytest.fixture
def names_without_rapidfuzz(monkeypatch):
    monkeypatch.setitem(sys.modules, "rapidfuzz", None)        # `import rapidfuzz` now raises ImportError
    monkeypatch.delitem(sys.modules, "collector.names", raising=False)
    mod = importlib.import_module("collector.names")
    yield mod
    monkeypatch.delitem(sys.modules, "collector.names", raising=False)
    importlib.import_module("collector.names")                 # the real one back for the other tests


def test_strict_tiers_work_and_the_fuzzy_tier_declines(names_without_rapidfuzz):
    m = names_without_rapidfuzz.Matcher([{"name": "Jio Platforms"}, {"name": "Elin Electronics"}], {"Reliance Jio": "Jio Platforms"})
    assert names_without_rapidfuzz.fuzz is None
    assert m.match_strict("Reliance Jio") == "Jio Platforms"
    assert m.match_strict("Jio Platforms") == "Jio Platforms"
    assert m.match("Jio Platforms Ltd") == "Jio Platforms" or m.match("Jio Platforms") == "Jio Platforms"
    assert m.match("ILJIN Electronics") is None
