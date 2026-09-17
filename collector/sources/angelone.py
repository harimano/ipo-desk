"""Angel One SmartAPI (smartapi-python) — free price source for NSE symbols.

Login = client code + PIN + TOTP (pyotp from the enrolment secret). Data endpoints need no static IP.
Historical candles are rate-limited to ~3 req/s, so calls are paced. The instrument master is a public
JSON (no login) that lists new symbols on listing morning; it is fetched once per run and cached.

Configuration comes ONLY from the environment:
  ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET
If any is missing, every entry point raises SourceDown("angelone", "not configured") before importing
the SDK, so a module chain falls straight through to the next source. Credentials are never logged.

Every SDK call goes through `_call`, which turns SDK exceptions and `status: false` envelopes into
SourceDown / SourceBlocked / SourceChanged.

Note: `import SmartApi` performs a network GET (api.ipify.org) at import time inside the SDK's class
body. That is why the import is lazy and only happens once we know we are configured.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
from zoneinfo import ZoneInfo

from ..errors import SourceBlocked, SourceChanged, SourceDown

log = logging.getLogger("collector.sources.angelone")

SOURCE = "angelone"
IST = ZoneInfo("Asia/Kolkata")
INSTRUMENT_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
ENV_VARS = ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET")
CANDLE_PACE = 0.35          # seconds between candle calls (~3 req/s cap)
LTP_BATCH = 50              # getMarketData accepts up to 50 tokens per exchange per call
_SERIES_PREF = ("-EQ", "-SM", "-ST", "-BE", "-BZ")
_BLOCK_WORDS = ("invalid token", "access denied", "rate", "limit", "exceed", "unauthori", "forbidden", "login")

# run-scoped caches (one process = one run)
_api = None
_master: dict[str, dict] | None = None
_last_call = 0.0


def reset() -> None:
    """Forget the cached session and instrument master (tests, or a forced re-login)."""
    global _api, _master, _last_call
    _api, _master, _last_call = None, None, 0.0


# ---------------------------------------------------------------------------------------------
# configuration / login
# ---------------------------------------------------------------------------------------------
def configured() -> bool:
    return all(os.environ.get(k) for k in ENV_VARS)


def _env() -> dict[str, str]:
    missing = [k for k in ENV_VARS if not os.environ.get(k)]
    if missing:
        raise SourceDown(SOURCE, "not configured")           # never name which var: keep logs credential-free
    return {k: os.environ[k] for k in ENV_VARS}


def _connect(api_key: str):
    """Build the SDK client. Split out so tests can swap in a fake without importing the SDK."""
    try:
        from SmartApi.smartConnect import SmartConnect      # lazy: import has side effects
    except Exception as e:  # ImportError or anything the SDK does at import time
        raise SourceDown(SOURCE, f"smartapi-python unavailable: {type(e).__name__}")
    return SmartConnect(api_key=api_key)


def _call(what: str, fn, *args, **kwargs) -> dict:
    """Run one SDK call; return its envelope dict. Every failure becomes a SourceError."""
    try:
        out = fn(*args, **kwargs)
    except SourceDown:
        raise
    except Exception as e:
        msg = str(e).lower()
        if any(w in msg for w in ("429", "too many", "rate")):
            raise SourceBlocked(SOURCE, f"{what}: {type(e).__name__}")
        raise SourceDown(SOURCE, f"{what}: {type(e).__name__}: {str(e)[:120]}")
    if not isinstance(out, dict):
        raise SourceChanged(SOURCE, f"{what}: non-dict response {type(out).__name__}")
    if out.get("status") is False or (out.get("status") is None and out.get("data") is None):
        msg = str(out.get("message") or out.get("errorcode") or "status false")
        if any(w in msg.lower() for w in _BLOCK_WORDS):
            raise SourceBlocked(SOURCE, f"{what}: {msg[:120]}")
        raise SourceDown(SOURCE, f"{what}: {msg[:120]}")
    return out


def login():
    """Return a logged-in SDK client (cached for the run). Raises SourceDown when not configured."""
    global _api
    if _api is not None:
        return _api
    env = _env()
    try:
        import pyotp
    except ImportError:
        raise SourceDown(SOURCE, "pyotp unavailable")
    api = _connect(env["ANGEL_API_KEY"])
    try:
        totp = pyotp.TOTP(env["ANGEL_TOTP_SECRET"]).now()
    except Exception as e:
        raise SourceDown(SOURCE, f"totp: {type(e).__name__}")
    _call("login", api.generateSession, env["ANGEL_CLIENT_CODE"], env["ANGEL_PIN"], totp)
    log.info("angelone: session established")
    _api = api
    return api


# ---------------------------------------------------------------------------------------------
# instrument master
# ---------------------------------------------------------------------------------------------
def _fetch_master(session):
    if session is not None:
        return session.get_json(INSTRUMENT_MASTER_URL, source=SOURCE)
    import httpx  # no Session given (script use): a plain bounded GET
    try:
        r = httpx.get(INSTRUMENT_MASTER_URL, timeout=60, follow_redirects=True)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise SourceDown(SOURCE, f"instrument master: {type(e).__name__}")


def instrument_master(session=None) -> dict[str, dict]:
    """symbol -> {"token", "symbol" (trading symbol e.g. RELIANCE-EQ), "series"} for exchange NSE.
    Fetched once per run and cached. Prefers the EQ series when a symbol lists under several."""
    global _master
    if _master is not None:
        return _master
    _env()                                                    # not configured -> fall through early
    raw = _fetch_master(session)
    if not isinstance(raw, list) or not raw:
        raise SourceChanged(SOURCE, "instrument master: expected a non-empty list", INSTRUMENT_MASTER_URL)
    out: dict[str, dict] = {}
    for row in raw:
        if not isinstance(row, dict) or row.get("exch_seg") != "NSE":
            continue
        sym, tok, name = row.get("symbol") or "", str(row.get("token") or ""), row.get("name") or ""
        suffix = next((s for s in _SERIES_PREF if sym.endswith(s)), None)
        if suffix is None or not tok or not name:
            continue
        rank = _SERIES_PREF.index(suffix)
        cur = out.get(name)
        if cur is None or rank < cur["_rank"]:
            out[name] = {"token": tok, "symbol": sym, "series": suffix[1:], "_rank": rank}
    if not out:
        raise SourceChanged(SOURCE, "instrument master: no NSE equity rows (shape changed?)", INSTRUMENT_MASTER_URL)
    for v in out.values():
        v.pop("_rank", None)
    _master = out
    log.info("angelone: instrument master %d NSE symbols", len(out))
    return out


def token_for(symbol: str, session=None) -> str | None:
    return (instrument_master(session).get(symbol.upper().removesuffix(".NS")) or {}).get("token")


# ---------------------------------------------------------------------------------------------
# prices
# ---------------------------------------------------------------------------------------------
def _pace():
    global _last_call
    wait = CANDLE_PACE - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def ltp(symbols: list[str], session=None) -> dict[str, float]:
    """Last traded price per symbol via getMarketData(mode=LTP). Unknown symbols are skipped."""
    master = instrument_master(session)
    api = login()
    wanted = {}
    for s in symbols:
        key = s.upper().removesuffix(".NS")
        rec = master.get(key)
        if rec:
            wanted[rec["token"]] = key
    if not wanted:
        raise SourceChanged(SOURCE, "ltp: none of the requested symbols are in the instrument master")
    out: dict[str, float] = {}
    tokens = list(wanted)
    for i in range(0, len(tokens), LTP_BATCH):
        _pace()
        env = _call("getMarketData", api.getMarketData, "LTP", {"NSE": tokens[i:i + LTP_BATCH]})
        fetched = ((env.get("data") or {}).get("fetched")) or []
        for row in fetched:
            tok = str(row.get("symbolToken") or "")
            price = row.get("ltp")
            if tok in wanted and isinstance(price, (int, float)) and price > 0:
                out[wanted[tok]] = float(price)
    if not out:
        raise SourceChanged(SOURCE, "ltp: response had no usable rows")
    return out


def daily_candles(symbol: str, days: int, session=None) -> list[list]:
    """[[date ISO, open, high, low, close, volume], ...] oldest first via getCandleData ONE_DAY."""
    key = symbol.upper().removesuffix(".NS")
    tok = token_for(key, session)
    if not tok:
        raise SourceChanged(SOURCE, f"candles: {key} not in instrument master")
    api = login()
    today = dt.datetime.now(IST).date()
    start = today - dt.timedelta(days=max(1, int(days)))
    params = {"exchange": "NSE", "symboltoken": tok, "interval": "ONE_DAY",
              "fromdate": f"{start.isoformat()} 09:15", "todate": f"{today.isoformat()} 15:30"}
    _pace()
    env = _call("getCandleData", api.getCandleData, params)
    data = env.get("data")
    if not isinstance(data, list):
        raise SourceChanged(SOURCE, f"candles: {key} data is {type(data).__name__}, not list")
    out = []
    for c in data:
        if not isinstance(c, (list, tuple)) or len(c) < 5:
            continue
        try:
            out.append([str(c[0])[:10], float(c[1]), float(c[2]), float(c[3]), float(c[4]),
                        float(c[5]) if len(c) > 5 and c[5] is not None else None])
        except (TypeError, ValueError):
            continue
    return out
