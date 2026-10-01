"""The live loop. Fixtures are real responses (18 Sep 2026)."""
import datetime as dt
import json
import pathlib

from collector import live
from collector.errors import SourceBlocked, SourceDown

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures"
SUBS = json.loads((FX / "investorgain/report-566-subscription.json").read_text())
GMP = json.loads((FX / "live-2026-09-17/ig.json").read_text())
PRE = json.loads((FX / "nse/special-preopen-listing.json").read_text())
CUR = json.loads((FX / "nse/ipo-current-issue.json").read_text())
DETAIL = json.loads((FX / "nse/ipo-detail-SONASEL.json").read_text())
NOW = dt.datetime(2026, 9, 18, 9, 40, tzinfo=live.IST)
DOC = {"mainboard": [{"name": "Hero Motors", "igId": "1688", "symbol": "HEROMOTORS", "open": "2026-09-16", "close": "2026-09-18"},
                     {"name": "Sona Selection India", "igId": "9001", "symbol": "SONASEL", "series": "EQ", "open": "2026-09-15", "close": "2026-09-18"},
                     {"name": "Veegaland Developers", "igId": "1750", "symbol": "VEEGALAND", "open": "2026-09-10", "close": "2026-09-15", "listing": "2026-09-18"},
                     {"name": "Closed Long Ago", "igId": "1", "open": "2026-08-01", "close": "2026-08-05"}],
       "sme": [{"name": "Axiom Gas Engineering", "igId": "1682", "open": "2026-09-18", "close": "2026-09-22"},
               {"name": "Vidya Wires", "igId": "9002", "symbol": "VIDYAWIRE", "series": "SME", "open": "2026-09-16", "close": "2026-09-18"}]}


class S:
    """InvestorGain by URL (566 subscription, 331 GMP); NSE by path (current issues, one issue's detail, pre-open)."""
    def __init__(self, subs=SUBS, gmp=GMP, pre=PRE, cur=CUR, detail=DETAIL):
        self.subs, self.gmp, self.pre, self.cur, self.detail, self.calls = subs, gmp, pre, cur, detail, []

    def get_json(self, url, *, source=None, headers=None, **kw):
        self.calls.append("566" if "/566/" in url else "331")
        v = self.subs if "/566/" in url else self.gmp
        if isinstance(v, Exception):
            raise v
        return v

    def nse_json(self, path, params=None, *, source="nse", referer=None):
        key = "current" if "current-issue" in path else "detail" if "ipo-detail" in path else "preopen"
        self.calls.append(key if key != "detail" else f"detail:{params['symbol']}")
        v = getattr(self, "cur" if key == "current" else key if key != "preopen" else "pre")
        if isinstance(v, Exception):
            raise v
        return v


def test_nse_first_then_investorgain_only_for_what_nse_does_not_carry():
    s = S()
    out = live.tick(s, DOC, {}, NOW)
    assert s.calls == ["current", "detail:SONASEL", "566", "331", "preopen"], "mainboard detail only for an issue NSE lists"
    sona = out["rows"]["Sona Selection India"]["sub"]
    assert sona == {"qib": 3.91, "nii": 4.16, "retail": 0.8, "total": 2.39, "employee": 0.45,
                    "asOf": "2026-09-17T15:02:00+05:30", "src": "nse"}, "mainboard: NSE's category split and its own time"
    assert out["rows"]["Vidya Wires"]["sub"] == {"total": 1.1, "asOf": "2026-09-18T09:40:00+05:30", "src": "nse"}, \
        "NSE SME: the list's total only"
    assert out["rows"]["Axiom Gas Engineering"]["sub"] == {"qib": 0.8, "snii": 0.5, "bnii": 0.58, "nii": 0.55, "retail": 0.64,
                                                          "total": 0.62, "asOf": "2026-09-18T17:57:00+05:30", "src": "investorgain"}
    assert "Closed Long Ago" not in out["rows"], "only issues that can still move"
    assert out["sources"]["subscription"].startswith("nse 1 split + 1 total; investorgain")
    assert out["preopen"] == [{"name": "Veegaland Developers", "symbol": "VEEGALAND", "iep": 154.0, "pct": 10.0, "base": 140.0,
                               "qty": 3102806.0, "status": "Close", "asOf": "2026-09-18T09:55:00+05:30"}]
    assert out["timeline"]["Axiom Gas Engineering"] == [["09:40", 0.62, 0.8, 0.64]]
    assert out["timeline"]["Vidya Wires"] == [["09:40", 1.1, None, None]]


def test_an_all_zero_book_is_never_written(monkeypatch):
    """1 Oct 2026: NSE answered zeros for every SME it does not carry; laid over the page they would blank real books."""
    monkeypatch.setattr(live.nse_ipo, "ipo_detail", lambda session, symbol, series="EQ": {
        "bidDetails": [{"category": "Total", "noOfTime": 0.0}], "rootTotal": 0.0, "updateTime": None})
    cur = json.loads(json.dumps(CUR))
    for r in cur:
        r["noOfTime"] = "0.00"
    zero_566 = json.loads(json.dumps(SUBS))
    for r in zero_566["reportTableData"]:
        for k in ("QIB", "SHNI", "BHNI", "NII", "RII"):
            r[k] = "0x"
        r["Total"] = "<b>0x</b>"
    out = live.tick(S(cur=cur, subs=zero_566), DOC, {}, NOW)
    assert not any("sub" in v for v in out["rows"].values()), out["rows"]


def test_the_timeline_grows_only_when_the_book_moves_and_a_failed_source_costs_only_its_part():
    first = live.tick(S(), DOC, {}, NOW)
    again = live.tick(S(subs=SourceDown("investorgain", "HTTP 503", "u", 503)), DOC, first, NOW + dt.timedelta(minutes=5))
    assert again["rows"]["Axiom Gas Engineering"]["sub"]["total"] == 0.62, "the last good book stays, with its own timestamp"
    assert "investorgain down" in again["sources"]["subscription"] and len(again["timeline"]["Axiom Gas Engineering"]) == 1
    assert again["rows"]["Sona Selection India"]["sub"]["src"] == "nse", "NSE's part of the tick still lands"
    moved = json.loads(json.dumps(SUBS))
    moved["reportTableData"][0]["Total"] = "<b>0.9x</b>"
    third = live.tick(S(subs=moved), DOC, again, NOW + dt.timedelta(minutes=10))
    assert [p[:2] for p in third["timeline"]["Axiom Gas Engineering"]] == [["09:40", 0.62], ["09:50", 0.9]]


def test_an_nse_block_ends_the_nse_pass_and_investorgain_carries_the_rest():
    s = S(cur=SourceBlocked("nse", "HTTP 403", "u", 403))
    out = live.tick(s, DOC, {}, NOW)
    assert not any(c.startswith("detail") for c in s.calls), "never retried, never per-issue after a block"
    assert out["rows"]["Axiom Gas Engineering"]["sub"]["src"] == "investorgain"
    assert "nse blocked" in out["sources"]["subscription"]
    assert "Sona Selection India" not in out["rows"], "no source had it this tick: nothing is invented"


def test_outside_the_pre_open_window_nse_is_not_asked_and_a_new_day_starts_clean():
    s = S()
    out = live.tick(s, DOC, {}, NOW.replace(hour=11))
    assert "preopen" not in s.calls and out["preopen"] == []
    stale = {"asOf": "2026-09-17T17:00:00+05:30", "rows": {"Old": {}}, "timeline": {"Old": [["10:00", 1, 1, 1]]}, "preopen": [{"name": "x"}]}
    out = live.tick(S(), DOC, stale, NOW.replace(hour=11))
    assert "Old" not in out["rows"] and "Old" not in out["timeline"] and out["preopen"] == []


def test_a_trading_holiday_is_read_from_nse_and_a_failed_list_fails_open():
    class H:
        def __init__(self, v):
            self.v = v

        def nse_json(self, path, params=None, *, source="nse", referer=None):
            if isinstance(self.v, Exception):
                raise self.v
            return self.v
    hol = {"CM": [{"tradingDate": "02-Oct-2026", "description": "Mahatma Gandhi Jayanti"}]}
    assert live.trading_holiday(H(hol), dt.date(2026, 10, 2)) == "Mahatma Gandhi Jayanti"
    assert live.trading_holiday(H(hol), dt.date(2026, 10, 1)) is None
    assert live.trading_holiday(H(SourceBlocked("nse", "HTTP 403", "u", 403)), dt.date(2026, 10, 2)) is None
