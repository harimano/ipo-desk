"""The stale-cache tripwire (collector/http.py `_note_cache`): a CDN HIT older than STALE_CACHE_S is said in the log."""
import logging

import httpx

from collector.http import CACHE_BUST_HOSTS, STALE_CACHE_S, Session, cache_age


def _client(headers: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": 1}, headers=headers)))


def _get(client, caplog):
    with caplog.at_level(logging.WARNING, logger="collector.http"):
        return Session()._request(client, "GET", "https://example.test/x", source="example")


def test_stale_hit_is_warned(caplog):
    r = _get(_client({"cf-cache-status": "HIT", "age": str(STALE_CACHE_S + 1)}), caplog)
    assert r.status_code == 200
    assert cache_age(r) == STALE_CACHE_S + 1
    assert any("served from the CDN's cache" in m and "example" in m for m in caplog.messages)


def test_fresh_hit_and_misses_are_quiet(caplog):
    for h in ({"cf-cache-status": "HIT", "age": "30"}, {"cf-cache-status": "MISS"}, {"cf-cache-status": "EXPIRED", "age": "9999"}, {},
              {"cf-cache-status": "HIT", "age": "884820", "content-type": "image/png"}):      # a logo PNG held for days: a CDN doing its job
        _get(_client(h), caplog)
    assert not caplog.messages
    assert cache_age(httpx.Response(200, headers={"cf-cache-status": "EXPIRED", "age": "9999"})) is None
    assert cache_age(httpx.Response(200, headers={"cf-cache-status": "HIT", "age": "x"})) is None


def test_investorgain_calls_carry_a_cache_buster():
    seen = []
    client = httpx.Client(transport=httpx.MockTransport(lambda req: (seen.append(str(req.url)), httpx.Response(200, json={"ok": 1}))[1]))
    s = Session()
    s._request(client, "GET", "https://webnodejs.investorgain.com/cloud/v2/ipo/list-read", source="investorgain")
    s._request(client, "GET", "https://webnodejs.investorgain.com/cloud/v2/report/data-read/331/1/11/2026/2026-27/0/all", source="investorgain", params={"search": ""})
    s._request(client, "GET", "https://example.test/plain", source="example")
    assert "webnodejs.investorgain.com" in CACHE_BUST_HOSTS
    assert all("v=" in u for u in seen[:2]) and "search=" in seen[1]
    assert "v=" not in seen[2]
