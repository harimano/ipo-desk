"""Yahoo Finance via yfinance — fallback price source. `.NS` tickers work but Yahoo 429s cloud IPs
readily, so: batches of 8, `group_by="ticker"`, exponential backoff on YFRateLimitError, and a
SourceBlocked once the backoff is exhausted. yfinance is imported lazily so the collector runs (and
tests pass) without it installed.
"""
from __future__ import annotations

import logging
import math
import time

from ..errors import SourceBlocked, SourceChanged, SourceDown

log = logging.getLogger("collector.sources.yahoo")

SOURCE = "yahoo"
BATCH = 8
BACKOFF = (3.0, 8.0, 20.0)


def _download(tickers: list[str], days: int):
    """Thin wrapper around yf.download so tests can swap it. Returns a pandas DataFrame."""
    try:
        import yfinance as yf
    except ImportError:
        raise SourceDown(SOURCE, "yfinance unavailable")
    period = f"{max(2, int(days))}d"
    return yf.download(tickers, period=period, interval="1d", group_by="ticker", auto_adjust=False,
                       progress=False, threads=False, timeout=30)


def _rate_limit_error():
    try:
        from yfinance.exceptions import YFRateLimitError
        return YFRateLimitError
    except Exception:  # older yfinance or not installed
        return ()


def _is_nan(v) -> bool:
    try:
        return v is None or (isinstance(v, float) and math.isnan(v)) or bool(v != v)
    except Exception:
        return True


def _frame_for(df, ticker: str, ntickers: int):
    """Slice one ticker's OHLC out of a group_by='ticker' frame; handles the single-ticker flat case."""
    cols = df.columns
    if getattr(cols, "nlevels", 1) > 1:
        if ticker in cols.get_level_values(0):
            return df[ticker]
        return None
    return df if ntickers == 1 else None


def _rows(sub) -> list[list]:
    out = []
    if sub is None or "Close" not in sub.columns:
        return out
    opens = sub["Open"] if "Open" in sub.columns else None
    for idx, close in sub["Close"].items():
        if _is_nan(close):
            continue
        o = None if opens is None or _is_nan(opens.loc[idx]) else round(float(opens.loc[idx]), 2)
        date = str(getattr(idx, "date", lambda: idx)())[:10]
        out.append([date, o, round(float(close), 2)])
    return out


def daily_bars(tickers_ns: list[str], days: int) -> dict[str, list[list]]:
    """{symbol (without .NS): [[date, open, close], ...] oldest first}. Raises SourceChanged when a
    whole batch comes back all-NaN (Yahoo answered with junk), SourceBlocked when rate limited."""
    tickers = [t if t.upper().endswith(".NS") else f"{t.upper()}.NS" for t in tickers_ns if t]
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        raise SourceChanged(SOURCE, "no tickers requested")
    RL = _rate_limit_error()
    out: dict[str, list[list]] = {}
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        df = None
        for attempt, sleep in enumerate((0.0,) + BACKOFF):
            if sleep:
                log.warning("yahoo: rate limited; backing off %.0fs (attempt %d)", sleep, attempt + 1)
                time.sleep(sleep)
            try:
                df = _download(batch, days)
                break
            except RL:
                continue
            except SourceDown:
                raise
            except Exception as e:
                raise SourceDown(SOURCE, f"download: {type(e).__name__}: {str(e)[:120]}")
        if df is None:
            raise SourceBlocked(SOURCE, "rate limited after backoff", status=429)
        if df is None or len(df) == 0:
            raise SourceChanged(SOURCE, f"empty frame for batch {batch[:3]}")
        got_any = False
        for t in batch:
            rows = _rows(_frame_for(df, t, len(batch)))
            if rows:
                got_any = True
                out[t.removesuffix(".NS")] = rows
        if not got_any:
            raise SourceChanged(SOURCE, f"all-NaN batch {batch[:3]}")
        if i + BATCH < len(tickers):
            time.sleep(1.0)
    return out


def daily_closes(tickers_ns: list[str], days: int) -> dict[str, list[list]]:
    """{symbol: [[date, close], ...]} — the documented entry point; bars minus the open."""
    return {sym: [[d, c] for d, _o, c in rows] for sym, rows in daily_bars(tickers_ns, days).items()}
