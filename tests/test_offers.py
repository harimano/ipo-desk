import datetime as dt
import json
import pathlib

import pytest

from collector.errors import SourceChanged
from collector.modules import offers
from collector.result import Result
from collector.sources import bse_issues

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE = json.loads((ROOT / "data/fixtures/live-2026-09-17/bse_issues_ALL.json").read_text())
TODAY = dt.date(2026, 9, 17)


class FakeSession:
    def __init__(self, body):
        self.body, self.calls = body, []

    def bse_json(self, path, params=None, *, source="bse"):
        self.calls.append((path, dict(params or {})))
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


def prev():
    return {"offers": {"asOf": "2026-09-07", "ofs": [], "ncd": [],
                       "rights": [{"name": "NCL Research & Financial Services", "open": "2026-09-03", "close": "2026-09-10",
                                   "price": 1, "record": "2026-08-25", "deal": "1 for 1", "status": "open-holders",
                                   "detail": {"why": "hand-written"}},
                                  {"name": "Long Gone Rights", "open": "2026-08-20", "close": "2026-09-01", "status": "open-holders"},
                                  {"name": "Someday Rights", "open": None, "close": None, "status": "tba"}],
                       "buybacks": [{"name": "Great Eastern Shipping", "type": "Open market", "open": "2026-09-04",
                                     "close": "2026-12-11", "price": 1530, "status": "live"}]}}


def test_live_bse_list_is_split_by_kind():
    rows = bse_issues.parse_public_issues_json(LIVE, kinds=bse_issues.OFFER_KINDS)
    kinds = {r["kind"] for r in rows}
    assert kinds <= set(bse_issues.OFFER_KINDS) and {"RI", "OTB", "DPI"} <= kinds
    assert all(r["kind"] == "IPO" for r in bse_issues.parse_public_issues_json(LIVE))


def test_merge_refreshes_keeps_handwriting_adds_and_drops():
    s = FakeSession(LIVE)
    res = offers.run(s, prev(), Result(module="offers"), today=TODAY)
    assert res.ok and s.calls[0][1]["ir_flag"] == ""
    o = res.replace["offers"]
    assert o["asOf"] == "2026-09-17" and set(o) == {"asOf", "rights", "buybacks", "ofs", "ncd"}
    rights = {r["name"]: r for r in o["rights"]}
    ncl = rights["NCL Research & Financial Services"]                  # BSE: "NCL RESEARCH  FINANCIAL SERVICES LTD"
    assert ncl["close"] == "2026-09-18" and ncl["status"] == "open-holders"
    assert ncl["deal"] == "1 for 1" and ncl["record"] == "2026-08-25" and ncl["detail"] == {"why": "hand-written"}
    assert "Long Gone Rights" not in rights, "a window closed more than three days ago is dropped"
    assert rights["Someday Rights"]["status"] == "tba" and any("Someday Rights" in u for u in res.unresolved)
    assert len(rights) > 2 and not any(n.isupper() or n.endswith(" LTD") for n in rights), "new rows, house spelling"
    assert {r["name"] for r in o["buybacks"]} >= {"Great Eastern Shipping"}
    assert o["ncd"] and all(r["status"] in ("live", "upcoming") for r in o["ncd"])


def test_status_vocabulary():
    d = dt.date
    assert offers.status_for("rights", d(2026, 9, 20), d(2026, 9, 30), TODAY) == "upcoming"
    assert offers.status_for("rights", d(2026, 9, 10), d(2026, 9, 30), TODAY) == "open-holders"
    assert offers.status_for("ncd", d(2026, 9, 10), d(2026, 9, 17), TODAY) == "live"
    assert offers.status_for("ofs", d(2026, 9, 10), d(2026, 9, 16), TODAY) == "closed"
    assert offers.status_for("buybacks", None, None, TODAY) == "tba"


def test_changed_shape_fails_loudly_and_changes_nothing():
    for body in ({"Table": []}, {"nope": 1}, {"Table": [{"IR_flag": "IPO", "Scrip_Name": "X", "Start_Dt": "2026-09-17T00:00:00"}]}):
        res = offers.run(FakeSession(body), prev(), Result(module="offers"), today=TODAY)
        assert not res.ok and res.replace == {}
    with pytest.raises(SourceChanged):
        bse_issues.parse_public_issues_json({"Table": []}, kinds=bse_issues.OFFER_KINDS)
