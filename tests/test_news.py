"""Offline tests for collector.modules.news and sources/rss."""
from __future__ import annotations

import copy

import pytest

from _support import FakeSession, blocked, fixture

from collector import assemble
from collector.errors import SourceChanged
from collector.modules import news
from collector.result import Result
from collector.sources import rss

XML = fixture("rss", "markets.xml")
HTML = fixture("rss", "blocked.html")


def all_feeds(body):
    return {url: body for _, url in rss.FEEDS}


def test_parse_feed_and_keyword_filter():
    items = rss.parse_feed(XML, "x")
    assert len(items) == 6                                 # raw, includes the duplicate
    kept = [i for i in items if rss._matches(i)]
    titles = [i["title"] for i in kept]
    assert any("subscribed 42 times" in t for t in titles)
    assert any("SEBI clears DRHP" in t for t in titles)
    assert any("SME listing" in t for t in titles)
    assert not any("Sensex" in t or "Rupee" in t for t in titles)
    assert kept[0]["date"].startswith("2026-09-16T14:05:00+05:30")


def test_parse_feed_changed_shape():
    with pytest.raises(SourceChanged):
        rss.parse_feed(HTML, "x")
    with pytest.raises(SourceChanged):
        rss.parse_feed("", "x")


def test_fetch_dedupes_and_orders_newest_first():
    items, notes = rss.fetch(FakeSession(text=all_feeds(XML)))
    urls = [i["url"] for i in items]
    assert len(urls) == len(set(urls)) == 3
    dates = [i["date"] for i in items]
    assert dates == sorted(dates, reverse=True)
    assert len(notes) == len(rss.FEEDS)


def test_fetch_one_feed_enough_when_others_blocked():
    text = {rss.FEEDS[0][1]: XML, rss.FEEDS[1][1]: blocked("rss"), rss.FEEDS[2][1]: HTML}
    items, notes = rss.fetch(FakeSession(text=text))
    assert len(items) == 3
    assert any("blocked" in n for n in notes) and any("changed" in n for n in notes)


def test_fetch_all_blocked_raises():
    from collector.errors import SourceBlocked
    with pytest.raises(SourceBlocked):
        rss.fetch(FakeSession(text={url: blocked("rss") for _, url in rss.FEEDS}))


def test_module_merges_with_prev_dedupes_by_url_and_caps():
    prev = {"news": [
        {"title": "SEBI clears DRHP of three companies for public issues (older copy)",
         "url": "https://example-news.test/markets/sebi-clears-drhp", "date": "2026-09-15T19:20:00+05:30"},
        {"title": "Old IPO story", "url": "https://example-news.test/old", "date": "2026-09-01T09:00:00+05:30"},
    ] + [{"title": f"filler {i}", "url": f"https://example-news.test/f{i}", "date": f"2026-08-{i:02d}T09:00:00+05:30"}
         for i in range(1, 30)]}
    snapshot = copy.deepcopy(prev)
    res = news.run(FakeSession(text=all_feeds(XML)), prev, Result(module="news"))
    assert res.ok and res.source == "rss"
    out = res.replace["news"]
    assert len(out) == 25
    urls = [i["url"] for i in out]
    assert len(set(urls)) == 25
    assert urls[0] == "https://example-news.test/markets/newlist-ipo-subscribed-42x"
    assert urls.count("https://example-news.test/markets/sebi-clears-drhp") == 1
    assert set(out[0]) == {"title", "url", "date"}
    assert "https://example-news.test/old" in urls
    assert prev == snapshot
    assemble.apply(copy.deepcopy(prev), res)


def test_module_fails_cleanly_when_feeds_down():
    prev = {"news": [{"title": "kept", "url": "u", "date": "2026-09-01"}]}
    res = news.run(FakeSession(), prev, Result(module="news"))
    assert not res.ok
    data = copy.deepcopy(prev)
    assemble.apply(data, res)
    assert data == prev
