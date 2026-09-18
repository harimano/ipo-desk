"""The live loop. Fixtures are real responses (18 Sep 2026)."""
import datetime as dt
import json
import pathlib

from collector import live
from collector.errors import SourceDown

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures"
SUBS = json.loads((FX / "investorgain/report-566-subscription.json").read_text())
GMP = json.loads((FX / "live-2026-09-17/ig.json").read_text())
PRE = json.loads((FX / "nse/special-preopen-listing.json").read_text())
NOW = dt.datetime(2026, 9, 18, 9, 40, tzinfo=live.IST)
DOC = {"mainboard": [{"name": "Hero Motors", "igId": "1688", "symbol": "HEROMOTORS", "open": "2026-09-16", "close": "2026-09-18"},
                     {"name": "Veegaland Developers", "igId": "1750", "symbol": "VEEGALAND", "open": "2026-09-10", "close": "2026-09-15", "listing": "2026-09-18"},
                     {"name": "Closed Long Ago", "igId": "1", "open": "2026-08-01", "close": "2026-08-05"}],
       "sme": [{"name": "Axiom Gas Engineering", "igId": "1682", "open": "2026-09-18", "close": "2026-09-22"}]}


class S:
    def __init__(self, subs=SUBS, gmp=GMP, pre=PRE):
        self.subs, self.gmp, self.pre, self.calls = subs, gmp, pre, []

    def get_json(self, url, *, source=None, headers=None, **kw):
        self.calls.append("566" if "/566/" in url else "331")
        v = self.subs if "/566/" in url else self.gmp
        if isinstance(v, Exception):
            raise v
        return v

    def nse_json(self, path, params=None, *, source="nse", referer=None):
        self.calls.append("preopen")
        return self.pre


def test_one_tick_is_three_calls_and_matches_by_id():
    s = S()
    out = live.tick(s, DOC, {}, NOW)
    assert s.calls == ["566", "331", "preopen"] and out["sources"] == {"subscription": "ok", "gmp": "ok", "preopen": "ok"}
    assert out["rows"]["Axiom Gas Engineering"]["sub"] == {"qib": 0.8, "snii": 0.5, "bnii": 0.58, "nii": 0.55, "retail": 0.64,
                                                          "total": 0.62, "asOf": "2026-09-18T17:57:00+05:30"}
    assert "Closed Long Ago" not in out["rows"], "only issues that can still move"
    assert out["preopen"] == [{"name": "Veegaland Developers", "symbol": "VEEGALAND", "iep": 154.0, "pct": 10.0, "base": 140.0,
                               "qty": 3102806.0, "status": "Close", "asOf": "2026-09-18T09:55:00+05:30"}]
    assert out["timeline"]["Axiom Gas Engineering"] == [["09:40", 0.62, 0.8, 0.64]]


def test_the_timeline_grows_only_when_the_book_moves_and_a_failed_source_costs_only_its_part():
    first = live.tick(S(), DOC, {}, NOW)
    again = live.tick(S(subs=SourceDown("investorgain", "HTTP 503", "u", 503)), DOC, first, NOW + dt.timedelta(minutes=5))
    assert again["rows"]["Axiom Gas Engineering"]["sub"]["total"] == 0.62, "the last good book stays, with its own timestamp"
    assert again["sources"]["subscription"].startswith("down") and len(again["timeline"]["Axiom Gas Engineering"]) == 1
    moved = json.loads(json.dumps(SUBS))
    moved["reportTableData"][0]["Total"] = "<b>0.9x</b>"
    third = live.tick(S(subs=moved), DOC, again, NOW + dt.timedelta(minutes=10))
    assert [p[:2] for p in third["timeline"]["Axiom Gas Engineering"]] == [["09:40", 0.62], ["09:50", 0.9]]


def test_outside_the_pre_open_window_nse_is_not_asked_and_a_new_day_starts_clean():
    s = S()
    out = live.tick(s, DOC, {}, NOW.replace(hour=11))
    assert "preopen" not in s.calls and out["preopen"] == []
    stale = {"asOf": "2026-09-17T17:00:00+05:30", "rows": {"Old": {}}, "timeline": {"Old": [["10:00", 1, 1, 1]]}, "preopen": [{"name": "x"}]}
    out = live.tick(S(), DOC, stale, NOW.replace(hour=11))
    assert "Old" not in out["rows"] and "Old" not in out["timeline"] and out["preopen"] == []
