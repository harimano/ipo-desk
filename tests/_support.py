"""Shared offline helpers for the price/flows/deals/news module tests."""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.errors import SourceBlocked, SourceDown  # noqa: E402

FIX = ROOT / "data" / "fixtures"


def fixture(*parts) -> str:
    return FIX.joinpath(*parts).read_text(encoding="utf8")


def fixture_json(*parts):
    return json.loads(fixture(*parts))


class FakeSession:
    """Same method names as collector.http.Session; answers from tables keyed by URL/path substring.
    A value that is an Exception is raised instead."""

    def __init__(self, text=None, json_=None, nse=None, bytes_=None):
        self.text, self.json_, self.nse, self.bytes_ = text or {}, json_ or {}, nse or {}, bytes_ or {}
        self.calls: list[str] = []
        self.calls_count = 0

    def _lookup(self, table, url, source):
        for key, val in table.items():
            if key in url:
                if isinstance(val, Exception):
                    raise val
                return val
        raise SourceDown(source, "no fixture for URL", url)

    def get_text(self, url, *, source, headers=None, params=None):
        self.calls.append(url)
        return self._lookup(self.text, url, source)

    def get_json(self, url, *, source, headers=None, params=None):
        self.calls.append(url)
        return self._lookup(self.json_, url, source)

    def get_bytes(self, url, *, source, headers=None, expect_pdf=False):
        self.calls.append(url)
        return self._lookup(self.bytes_, url, source)

    def post_text(self, url, data, *, source, headers=None):
        self.calls.append(url)
        return self._lookup(self.text, url, source)

    def nse_json(self, path, params=None, *, source="nse", referer=None):
        self.calls.append(path)
        return self._lookup(self.nse, path, source)

    def bse_json(self, path, params=None, *, source="bse"):
        self.calls.append(path)
        return self._lookup(self.json_, path, source)


def blocked(source="nse"):
    return SourceBlocked(source, "HTTP 403", None, 403)


def yahoo_frame(bars: dict, tickers: list[str]):
    """Build the DataFrame yf.download(group_by='ticker') returns, from the yahoo/bars.json fixture."""
    import pandas as pd
    frames = {}
    for t in tickers:
        spec = bars.get(t)
        if not spec:
            continue
        idx = pd.to_datetime(spec["dates"])
        frames[t] = pd.DataFrame({"Open": spec["open"], "Close": spec["close"]}, index=idx)
    if not frames:
        idx = pd.to_datetime(bars[next(iter(bars))]["dates"])
        return pd.DataFrame({(t, "Close"): [float("nan")] * len(idx) for t in tickers}, index=idx)
    return pd.concat(frames, axis=1)          # columns: (ticker, field)


def nan_frame(tickers: list[str], n: int = 3):
    import pandas as pd
    idx = pd.date_range("2026-09-14", periods=n)
    cols = {}
    for t in tickers:
        cols[(t, "Open")] = [float("nan")] * n
        cols[(t, "Close")] = [float("nan")] * n
    return pd.DataFrame(cols, index=idx)


class FakeSmartConnect:
    """Stands in for SmartApi.smartConnect.SmartConnect. Records calls; answers from fixtures."""

    def __init__(self, api_key=None, candles=None, ltp=None, login_ok=True, raise_on=None):
        self.api_key = api_key
        self.candles = candles if candles is not None else fixture_json("angelone", "candles.json")
        self.ltp_resp = ltp if ltp is not None else fixture_json("angelone", "ltp.json")
        self.login_ok = login_ok
        self.raise_on = raise_on or set()
        self.calls: list[tuple] = []

    def generateSession(self, clientCode, password, totp):
        self.calls.append(("login", clientCode))
        if "login" in self.raise_on:
            raise RuntimeError("Couldn't parse the JSON response received from the server: 502")
        if not self.login_ok:
            return {"status": False, "message": "Invalid totp", "errorcode": "AB1050", "data": None}
        return {"status": True, "data": {"jwtToken": "x", "refreshToken": "y", "feedToken": "z", "clientcode": clientCode}}

    def getCandleData(self, params):
        self.calls.append(("candles", params["symboltoken"]))
        if "candles" in self.raise_on:
            raise RuntimeError("Access denied because of exceeding access rate")
        if isinstance(self.candles, dict) and "status" in self.candles:
            return self.candles
        return {"status": True, "data": self.candles.get(params["symboltoken"], [])}

    def getMarketData(self, mode, exchangeTokens):
        self.calls.append(("ltp", tuple(exchangeTokens.get("NSE", []))))
        if "ltp" in self.raise_on:
            raise RuntimeError("Couldn't parse the JSON response received from the server: 502")
        return self.ltp_resp
