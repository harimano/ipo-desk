"""Shared HTTP layer.

Design rules, each of which comes from a failure someone else already had:
  * NSE (www.nseindia.com) sits behind Akamai and 403s the homepage from datacenter IPs. The list
    endpoints still answer if you (a) prime cookies against the issue-information page instead of
    the homepage, (b) do NOT raise when the prime itself fails, (c) send a Chrome UA and a Referer,
    and (d) retry the first call once on 401/403. Lifted from Vasuki8/IPO-Tracker
    scripts/enrich_nse_issue_information.py:216-238 and update_data.py:456.
  * Retries are for network faults only (connect, timeout, reset). A 403 is an answer, not a
    fault: retrying it hammers the WAF and gets the runner IP flagged. So blocks fail fast.
  * BSE's api.bseindia.com needs Origin/Referer and nothing else. beta.bseindia.com still serves
    the legacy public-issue tables that www. no longer does.
  * Every call has a hard timeout. Nothing in this collector may hang: the whole point of moving
    off scheduled Claude tasks was that a hung call cannot be interrupted.
  * Bounded bodies: 40 MiB cap on downloads, %PDF magic check on PDFs.
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field

import httpx

from .errors import SourceBlocked, SourceChanged, SourceDown

log = logging.getLogger("collector.http")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/152.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json,text/html,application/xhtml+xml,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
NSE = "https://www.nseindia.com"
NSE_ARCHIVES = "https://nsearchives.nseindia.com"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
BSE_WEB = "https://www.bseindia.com"
BSE_BETA = "https://beta.bseindia.com"
SEBI = "https://www.sebi.gov.in"

BLOCK_STATUSES = {401, 403, 421, 429, 503}
MAX_BODY = 40 * 1024 * 1024
RETRY_SLEEPS = (0.5, 1.0, 2.0)
NETWORK_FAULTS = (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError,
                  httpx.ReadError, httpx.WriteError, httpx.PoolTimeout, httpx.ProxyError)


@dataclass
class Session:
    """One httpx client per host family, so NSE cookies never leak into BSE calls and vice versa."""
    timeout_api: float = 25.0
    timeout_html: float = 30.0
    timeout_prime: float = 20.0
    throttle: float = 0.3
    _nse: httpx.Client | None = field(default=None, repr=False)
    _plain: httpx.Client | None = field(default=None, repr=False)
    _nse_primed: bool = False
    _nse_prime_failed: bool = False
    _last: dict[str, float] = field(default_factory=dict)
    calls: int = 0

    # ---------- clients ----------
    def nse(self) -> httpx.Client:
        if self._nse is None:
            self._nse = httpx.Client(http2=True, headers={**BASE_HEADERS, "Referer": NSE + "/"},
                                     timeout=self.timeout_api, follow_redirects=True)
        return self._nse

    def plain(self) -> httpx.Client:
        if self._plain is None:
            self._plain = httpx.Client(http2=True, headers=BASE_HEADERS, timeout=self.timeout_html,
                                       follow_redirects=True)
        return self._plain

    def close(self):
        for c in (self._nse, self._plain):
            if c is not None:
                c.close()

    # ---------- politeness ----------
    def _pace(self, host: str):
        last = self._last.get(host, 0.0)
        wait = self.throttle - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.1))
        self._last[host] = time.monotonic()

    # ---------- core request with fault-only retries ----------
    def _request(self, client: httpx.Client, method: str, url: str, *, source: str,
                 headers: dict | None = None, params: dict | None = None, data: dict | None = None,
                 timeout: float | None = None, allow_statuses: frozenset[int] = frozenset()) -> httpx.Response:
        host = httpx.URL(url).host
        last_exc: Exception | None = None
        for attempt, sleep in enumerate((0.0,) + RETRY_SLEEPS):
            if sleep:
                time.sleep(sleep)
            self._pace(host)
            self.calls += 1
            try:
                r = client.request(method, url, headers=headers, params=params, data=data, timeout=timeout)
            except NETWORK_FAULTS as e:
                last_exc = e
                log.warning("%s: %s on %s (attempt %d)", source, type(e).__name__, url, attempt + 1)
                continue
            if r.status_code in BLOCK_STATUSES and r.status_code not in allow_statuses:
                raise SourceBlocked(source, f"HTTP {r.status_code}", url, r.status_code)
            if r.status_code >= 400 and r.status_code not in allow_statuses:
                raise SourceDown(source, f"HTTP {r.status_code}", url, r.status_code)
            if len(r.content) > MAX_BODY:
                raise SourceChanged(source, f"body {len(r.content)} B exceeds cap", url)
            return r
        raise SourceDown(source, f"{type(last_exc).__name__}: {last_exc}", url)

    # ---------- NSE ----------
    def nse_prime(self, source: str = "nse") -> bool:
        """Prime cookies via the issue-information page, NOT the homepage (which 403s from cloud).
        Never raises: a failed prime is recorded and the caller proceeds — the list endpoints often
        answer anyway."""
        if self._nse_primed or self._nse_prime_failed:
            return self._nse_primed
        url = NSE + "/market-data/issue-information"
        try:
            r = self._request(self.nse(), "GET", url, source=source,
                              params={"series": "EQ", "symbol": "RELIANCE", "type": "Past"},
                              timeout=self.timeout_prime, allow_statuses=frozenset({401, 403}))
            self._nse_primed = r.status_code < 400
            if not self._nse_primed:
                log.warning("nse prime answered %s; continuing unprimed", r.status_code)
                self._nse_prime_failed = True
        except SourceDown as e:
            log.warning("nse prime failed (%s); continuing unprimed", e.detail)
            self._nse_prime_failed = True
        return self._nse_primed

    def nse_json(self, path: str, params: dict | None = None, *, source: str = "nse",
                 referer: str | None = None):
        """GET an NSE JSON endpoint. Retries once on 401/403 after re-priming — that single retry is
        the documented fix; a second one is hammering."""
        self.nse_prime(source)
        url = NSE + path
        headers = {"Referer": referer or (NSE + "/market-data/all-upcoming-issues-ipo")}
        r = None
        for attempt in (1, 2):
            try:
                r = self._request(self.nse(), "GET", url, source=source, headers=headers, params=params)
                break
            except SourceBlocked as e:
                if attempt == 1 and e.status in (401, 403):
                    log.warning("%s: %s on first call; re-priming once", source, e.status)
                    self._nse_primed = False
                    self._nse_prime_failed = False
                    self.nse_prime(source)
                    continue
                raise
        return _json_or_raise(r, source)

    # ---------- BSE ----------
    def bse_json(self, path: str, params: dict | None = None, *, source: str = "bse"):
        headers = {"Origin": BSE_WEB, "Referer": BSE_WEB + "/", "X-Requested-With": "XMLHttpRequest"}
        r = self._request(self.plain(), "GET", BSE_API + path, source=source, headers=headers, params=params)
        return _json_or_raise(r, source)

    # ---------- generic ----------
    def get_text(self, url: str, *, source: str, headers: dict | None = None, params: dict | None = None) -> str:
        r = self._request(self.plain(), "GET", url, source=source, headers=headers, params=params,
                          timeout=self.timeout_html)
        return r.text

    def get_json(self, url: str, *, source: str, headers: dict | None = None, params: dict | None = None):
        r = self._request(self.plain(), "GET", url, source=source, headers=headers, params=params)
        return _json_or_raise(r, source)

    def post_text(self, url: str, data: dict, *, source: str, headers: dict | None = None) -> str:
        r = self._request(self.plain(), "POST", url, source=source, headers=headers, data=data,
                          timeout=self.timeout_html)
        return r.text

    def get_bytes(self, url: str, *, source: str, headers: dict | None = None, expect_pdf: bool = False) -> bytes:
        r = self._request(self.plain(), "GET", url, source=source, headers=headers, timeout=self.timeout_html * 2)
        if expect_pdf and not r.content.startswith(b"%PDF"):
            raise SourceChanged(source, "not a PDF (no %PDF magic)", url)
        return r.content


def _json_or_raise(r: httpx.Response, source: str):
    try:
        data = r.json()
    except (json.JSONDecodeError, ValueError):
        head = r.text[:120].replace("\n", " ")
        raise SourceChanged(source, f"non-JSON body: {head!r}", str(r.url))
    if data in (None, "", [], {}):
        raise SourceChanged(source, "empty JSON body", str(r.url))
    return data
