"""Telegram + ntfy senders. Stage two — nothing calls this yet.

Both read config from env and no-op (with a log line) when unconfigured:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID       -> Telegram Bot API sendMessage (HTML parse mode)
  NTFY_TOPIC [, NTFY_BASE_URL, NTFY_USER, NTFY_PASSWORD]  -> POST {base}/{topic}

`_esc`, the 3800-char chunker, `send_telegram` and `send_ntfy` are copied from chirag127/oriz-ipo
`src/ipo_watch/notify/channels.py` (MIT, see THIRD_PARTY.md), minus its ipo.oriz.in links and
Ipo-model formatting. `send(text)` is the one entry point: plain text in, both channels out.
"""
from __future__ import annotations

import logging
import os

try:
    import httpx
except ImportError:  # pragma: no cover - httpx is a hard dependency of the collector, but keep import-safe
    httpx = None

log = logging.getLogger("collector.notify")

SAFE_CHUNK = 3800          # Telegram's hard limit is 4096 chars per message
TITLE = "IPO desk"


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def configured() -> dict[str, bool]:
    return {
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
                         and os.environ.get("TELEGRAM_CHAT_ID", "").strip()),
        "ntfy": bool(os.environ.get("NTFY_TOPIC", "").strip()),
    }


def chunk(text: str, limit: int = SAFE_CHUNK) -> list[str]:
    """Split on blank lines so no chunk exceeds Telegram's limit (oriz chunker, generalised to text)."""
    blocks = [b for b in text.split("\n\n")]
    messages: list[str] = []
    current = ""
    for b in blocks:
        piece = b + "\n\n"
        if len(current) + len(piece) > limit and current:
            messages.append(current.rstrip())
            current = ""
        while len(piece) > limit:            # one oversized block: hard-cut it
            messages.append(piece[:limit].rstrip())
            piece = piece[limit:]
        current += piece
    if current.strip():
        messages.append(current.rstrip())
    return messages or [""]


def send_telegram(messages: list[str]) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.info("telegram: TELEGRAM_BOT_TOKEN/CHAT_ID unset — skipping")
        return False
    if httpx is None:
        log.warning("telegram: httpx not installed — skipping")
        return False
    ok = True
    for msg in messages:
        try:
            r = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            log.warning("telegram send failed: %s", e)
            ok = False
    if ok:
        log.info("telegram: sent %d message(s)", len(messages))
    return ok


def send_ntfy(text: str) -> bool:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        log.info("ntfy: NTFY_TOPIC unset — skipping")
        return False
    if httpx is None:
        log.warning("ntfy: httpx not installed — skipping")
        return False
    base = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")
    headers = {"Title": TITLE, "Tags": "chart_with_upwards_trend"}
    user = os.environ.get("NTFY_USER", "").strip()
    pw = os.environ.get("NTFY_PASSWORD", "").strip()
    auth = (user, pw) if user and pw else None
    try:
        r = httpx.post(
            f"{base}/{topic}",
            content=text.encode("utf-8"),
            headers=headers,
            auth=auth,
            timeout=20,
        )
        r.raise_for_status()
        log.info("ntfy: sent to %s/%s", base, topic)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("ntfy send failed: %s", e)
        return False


def send(text: str) -> dict[str, bool]:
    """Send plain text to every configured channel. No-op with a log line when none is configured."""
    cfg = configured()
    if not any(cfg.values()):
        log.info("notify: no channel configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID, NTFY_TOPIC) — not sending")
        return {"telegram": False, "ntfy": False}
    return {
        "telegram": send_telegram(chunk(_esc(text))) if cfg["telegram"] else False,
        "ntfy": send_ntfy(text) if cfg["ntfy"] else False,
    }
