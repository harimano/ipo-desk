"""Telegram + ntfy senders, called by collector.alerts at the end of a collect run.

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
        except Exception as e:
            log.warning("telegram send failed: %s", e)
            ok = False
    if ok:
        log.info("telegram: sent %d message(s)", len(messages))
    return ok


MAX_ACTIONS = 3            # ntfy shows at most three action buttons


def actions_header(actions) -> str:
    """ntfy's `Actions` header: up to three `view` buttons, `label, url` pairs joined by `;` (docs.ntfy.sh/publish/#action-buttons).
    A label may not contain `,` or `;`; it is kept short because the buttons share one row on the phone."""
    out = []
    for label, url in list(actions or [])[:MAX_ACTIONS]:
        lbl = str(label).replace(",", " ").replace(";", " ").strip()[:24]
        if lbl and url:
            out.append(f"view, {lbl}, {url}")
    return "; ".join(out)


def send_ntfy(text: str, click: str | None = None, markdown: bool = False, actions=None) -> bool:
    """`click`: the URL the notification opens on tap (ntfy's `Click` header, one per message, every platform).
    `actions`: up to three (label, url) buttons under the notification (`Actions` header; Android, iOS and web).
    `markdown`: the body is Markdown (`Markdown: yes`) — rendered in ntfy's web and Android apps ONLY; on an iPhone the
    body shows the raw brackets, so Hari's desk (29 Oct 2026: iPhone) sends plain text with Click and action buttons.
    docs.ntfy.sh/publish/#click-action, #action-buttons and #markdown-formatting."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        log.info("ntfy: NTFY_TOPIC unset — skipping")
        return False
    if httpx is None:
        log.warning("ntfy: httpx not installed — skipping")
        return False
    base = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")
    headers = {"Title": TITLE, "Tags": "chart_with_upwards_trend"}
    if click:
        headers["Click"] = click
    if markdown:
        headers["Markdown"] = "yes"
    if actions and (h := actions_header(actions)):
        headers["Actions"] = h
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
    except Exception as e:
        log.warning("ntfy send failed: %s", e)
        return False


def send(text: str, *, html: str | None = None, markdown: str | None = None, click: str | None = None,
         actions=None) -> dict[str, bool]:
    """Send to every configured channel. `text` is the plain message; `html` (Telegram, already escaped, <a href> allowed)
    is the same lines with links. ntfy gets the plain text, `click` as its tap URL and `actions` as buttons — or the
    `markdown` body when one is given (Android / web readers only; not for an iPhone). No-op with a log line when no
    channel is configured."""
    cfg = configured()
    if not any(cfg.values()):
        log.info("notify: no channel configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID, NTFY_TOPIC) — not sending")
        return {"telegram": False, "ntfy": False}
    return {
        "telegram": send_telegram(chunk(html if html is not None else _esc(text))) if cfg["telegram"] else False,
        "ntfy": (send_ntfy(markdown, click=click, markdown=True, actions=actions) if markdown is not None
                 else send_ntfy(text, click=click, actions=actions)) if cfg["ntfy"] else False,
    }
