"""players — who is in today's books. Fixtures are real responses (19 Sep 2026); 551 is cut to its first 120 rows."""
import datetime as dt
import json
import pathlib

import pytest

from collector import assemble, layout, schema
from collector.errors import SourceBlocked, SourceChanged, SourceDown
from collector.modules import players
from collector.result import Result

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/investorgain"
LIST = json.loads((FX / "report-551-anchor-investors.json").read_text())
SOCGEN = json.loads((FX / "report-561-investor-9654-SOCGEN.json").read_text())
TODAY = dt.date(2026, 9, 19)
NSE = "NSE (National Stock Exchange of India)"


class S:
    def __init__(self, one=SOCGEN, fail_ids=(), blocked=False):
        self.one, self.fail_ids, self.blocked, self.calls = one, set(fail_ids), blocked, []

    def get_json(self, url, *, source=None, headers=None, **kw):
        self.calls.append(url)
        if "/551/" in url:
            return LIST
        i = url.rsplit("/", 1)[1]
        if self.blocked:
            raise SourceBlocked("investorgain", "HTTP 403", url, 403)
        if i in self.fail_ids or self.fail_ids == {"*"}:
            raise SourceDown("investorgain", "HTTP 503", url, 503)
        return self.one


def doc():
    return {"mainboard": [{"name": NSE, "igId": "2305", "status": "Open"}, {"name": "Old Co", "igId": "2278", "status": "Listed"}], "sme": []}


def run(s, prev=None):
    return players.run(s, prev or {}, Result(module="players", doc=doc()), today=TODAY)


def test_the_real_reports_parse():
    inv = players.parse_investors(LIST)
    sg = next(r for r in inv if r["name"] == "SOCIETE GENERALE-ODI")
    assert (sg["id"], sg["ipos"], sg["investedCr"], sg["ticketCr"]) == ("9654", 150, 2624.44, 17.5)
    assert "2305" in players.parse_ipos(SOCGEN) and len(players.parse_ipos(SOCGEN)) == 5, "the feed gives an investor's latest five"
    for bad in ({}, {"reportTableData": []}, {"reportTableData": [{"x": 1}]}):
        with pytest.raises(SourceChanged):
            players.parse_investors(bad)
        with pytest.raises(SourceChanged):
            players.parse_ipos(bad)


def test_lists_are_turned_round_into_books_for_unlisted_issues_only():
    s = S()
    res = run(s)
    assert res.ok and "/551/" in s.calls[0] and all(u.rsplit("/", 2)[1] == "0" for u in s.calls[1:]), "the investor id is the LAST segment"
    p = res.replace["players"]
    assert p["tracked"] == len(s.calls) - 1 <= players.TRACK_BY_MONEY + players.TRACK_BY_COUNT and p["latestPerInvestor"] == 5
    assert set(p["books"]) == {"2305"} and p["names"] == {"2305": NSE}, "a listed issue gets no book here"
    book = p["books"]["2305"]
    assert len(book) == p["tracked"] and book[0]["investedCr"] >= book[-1]["investedCr"] and {"id", "name", "ipos", "investedCr", "ticketCr"} == set(book[0])
    data = schema.empty_data()
    assemble.apply(data, res)
    layout.check_groups()
    assert data["players"]["books"]["2305"] and schema.OWNERS["players"] == "players"


def test_a_403_stops_at_once_and_one_bad_investor_is_only_skipped():
    s = S(blocked=True)
    res = run(s)
    assert not res.ok and len(s.calls) == 2 and "players" not in res.replace, "never a second request after a 403"
    first = players.tracked(players.parse_investors(LIST))[0]["id"]
    res = run(S(fail_ids=[first]))
    assert res.ok and len(res.replace["players"]["books"]["2305"]) == res.replace["players"]["tracked"] - 1
    assert not run(S(fail_ids={"*"})).ok, "nobody could be read: a failure, not an empty success"


def test_nothing_unlisted_means_nothing_fetched():
    s = S()
    res = players.run(s, {}, Result(module="players", doc={"mainboard": [{"name": "Old Co", "igId": "1", "status": "Listed"}], "sme": []}), today=TODAY)
    assert res.ok and s.calls == [] and res.replace == {}
