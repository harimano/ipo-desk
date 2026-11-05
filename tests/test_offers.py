import datetime as dt
import pathlib

import pytest

from collector.errors import SourceChanged
from collector.modules import offers
from collector.result import Result
from collector.sources import bse_issues

ROOT = pathlib.Path(__file__).resolve().parent.parent
FX = ROOT / "data/fixtures/bse"
LIVE = (FX / "IPOIssues_form-live-all-2026-11-05.html").read_text(encoding="utf8")               # the real page, 5 Nov 2026
FORTHCOMING = (FX / "IPOIssues_form-forthcoming-all-2026-11-05.html").read_text(encoding="utf8")
TODAY = dt.date(2026, 11, 5)


class FakeSession:
    """The legacy page: GET answers the form page, POST answers by the status radio (L live, F forthcoming)."""

    def __init__(self, page=LIVE, live=LIVE, forthcoming=FORTHCOMING):
        self.page, self.live, self.forthcoming, self.calls = page, live, forthcoming, []

    @staticmethod
    def _answer(v):
        if isinstance(v, Exception):
            raise v
        return v

    def get_text(self, url, *, source="bse", headers=None, params=None):
        self.calls.append(("get", url))
        return self._answer(self.page)

    def post_text(self, url, data, *, source="bse", headers=None):
        self.calls.append(("post", url, data["ctl00$ContentPlaceHolder1$rblIssueStatus"], data["ctl00$ContentPlaceHolder1$ddlIssueType"]))
        assert data["__VIEWSTATE"] and data["__EVENTVALIDATION"] and data["ctl00$ContentPlaceHolder1$btnSubmit"] == "Submit"
        return self._answer(self.live if data["ctl00$ContentPlaceHolder1$rblIssueStatus"] == "L" else self.forthcoming)


def prev():
    return {"offers": {"asOf": "2026-09-07", "ofs": [], "ncd": [],
                       "rights": [{"name": "Shivam Autotech", "open": "2026-10-28", "close": "2026-11-10",
                                   "price": 1, "record": "2026-10-20", "deal": "1 for 1", "status": "open-holders",
                                   "detail": {"why": "hand-written"}},
                                  {"name": "Long Gone Rights", "open": "2026-08-20", "close": "2026-09-01", "status": "open-holders"},
                                  {"name": "Someday Rights", "open": None, "close": None, "status": "tba"}],
                       "buybacks": [{"name": "Great Eastern Shipping", "type": "Open market", "open": "2026-09-04",
                                     "close": "2026-12-11", "price": 1530, "status": "live"}]}}


def test_live_bse_list_is_split_by_kind():
    rows = bse_issues.parse_public_issues_html(LIVE, kinds=bse_issues.OFFER_KINDS)
    kinds = {r["kind"] for r in rows}
    assert kinds <= set(bse_issues.OFFER_KINDS) and {"RI", "OTB", "DPI", "BuyBack"} <= kinds
    assert [r["name"] for r in bse_issues.parse_public_issues_html(LIVE)] == ["ANTALA INDUSTRIES LIMITED"], "IPO only by default"
    assert all(r["bseIpoNo"] is None for r in rows if r["kind"] == "BuyBack"), "an open-market buyback has no issue number"
    assert bse_issues.form_state(LIVE)["__VIEWSTATEGENERATOR"] and len(bse_issues.form_state(LIVE)["__VIEWSTATE"]) > 100


def test_merge_refreshes_keeps_handwriting_adds_and_drops():
    s = FakeSession()
    res = offers.run(s, prev(), Result(module="offers"), today=TODAY)
    assert res.ok and [c[2:] for c in s.calls if c[0] == "post"] == [("L", "0"), ("F", "0")], "one GET for the state, then live and forthcoming"
    o = res.replace["offers"]
    assert o["asOf"] == "2026-11-05" and set(o) == {"asOf", "rights", "buybacks", "ofs", "ncd"}
    rights = {r["name"]: r for r in o["rights"]}
    shivam = rights["Shivam Autotech"]                                    # BSE: "SHIVAM AUTOTECH LTD"
    assert shivam["close"] == "2026-11-19" and shivam["status"] == "open-holders"
    assert shivam["deal"] == "1 for 1" and shivam["record"] == "2026-10-20" and shivam["detail"] == {"why": "hand-written"}
    assert "Long Gone Rights" not in rights, "a window closed more than three days ago is dropped"
    assert rights["Someday Rights"]["status"] == "tba" and any("Someday Rights" in u for u in res.unresolved)
    upcoming = [r for r in o["rights"] if r["status"] == "upcoming"]
    assert len(upcoming) == 3 and all(r["open"] == "2026-11-06" for r in upcoming), "the forthcoming post adds next week's rights"
    assert not any(n.isupper() or n.endswith(" LTD") for n in rights), "new rows, house spelling"
    bb = {r["name"]: r for r in o["buybacks"]}
    assert "Great Eastern Shipping" in bb and {r["type"] for r in o["buybacks"]} == {"Open market", "Tender / open offer"}
    assert bb["Jindal Photo"]["type"] == "Tender / open offer" and bb["Jindal Photo"]["close"] == "2026-11-06" and bb["Jindal Photo"]["price"] == 1119.5
    assert o["ncd"] and all(r["status"] in ("live", "upcoming") for r in o["ncd"]) and o["ofs"] == []


def test_status_vocabulary():
    d = dt.date
    assert offers.status_for("rights", d(2026, 11, 8), d(2026, 11, 18), TODAY) == "upcoming"
    assert offers.status_for("rights", d(2026, 10, 28), d(2026, 11, 18), TODAY) == "open-holders"
    assert offers.status_for("ncd", d(2026, 10, 28), d(2026, 11, 5), TODAY) == "live"
    assert offers.status_for("ofs", d(2026, 10, 28), d(2026, 11, 4), TODAY) == "closed"
    assert offers.status_for("buybacks", None, None, TODAY) == "tba"


def test_changed_shape_fails_loudly_and_changes_nothing():
    empty = (FX / "IPOIssues_form-live-ofs-empty-2026-11-05.html").read_text(encoding="utf8")   # a real post with no rows
    for sess in (FakeSession(page="<html>Access Denied</html>"), FakeSession(live=empty, forthcoming=empty),
                 FakeSession(live=blocked(), forthcoming=blocked())):
        res = offers.run(sess, prev(), Result(module="offers"), today=TODAY)
        assert not res.ok and res.replace == {}
    with pytest.raises(SourceChanged):
        bse_issues.parse_public_issues_html(empty, kinds=bse_issues.OFFER_KINDS)
    with pytest.raises(SourceChanged):
        bse_issues.form_state("<html></html>")


def blocked():
    from collector.errors import SourceBlocked
    return SourceBlocked("bse", "HTTP 403", None, 403)
