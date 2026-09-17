"""Primary-market headlines from a few RSS feeds, parsed with feedparser.

Feed URLs (verify with scripts/reachability.py; only the Business Standard one is in the probe list):
  Business Standard markets   https://www.business-standard.com/rss/markets-106.rss    (in the probe)
  Economic Times markets      https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms
  Moneycontrol IPO news       https://www.moneycontrol.com/rss/iponews.xml
The ET and Moneycontrol URLs are the long-standing public feed ids; if either 404s or moves, the feed is
skipped with a note — one working feed is enough for the news module.

Items are filtered to primary-market keywords, deduped by URL, newest first.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import time
from zoneinfo import ZoneInfo

from ..errors import SourceChanged, SourceDown, SourceError

log = logging.getLogger("collector.sources.rss")

SOURCE = "rss"
IST = ZoneInfo("Asia/Kolkata")
FEEDS = [
    ("business-standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("economic-times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("moneycontrol-ipo", "https://www.moneycontrol.com/rss/iponews.xml"),
]
KEYWORDS = re.compile(
    r"\b(ipo|ipos|sebi|listing|listed|lists|debut|drhp|rhp|gmp|grey market|gray market|anchor|"
    r"public issue|public offer|fpo|ofs|offer for sale|subscription|subscribed|allotment|sme)\b",
    re.I,
)


def _when(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return dt.datetime.fromtimestamp(time.mktime(t), tz=dt.timezone.utc).astimezone(IST).isoformat()
            except (OverflowError, ValueError):
                continue
    for key in ("published", "updated"):
        if entry.get(key):
            return str(entry[key])
    return None


def parse_feed(text: str, url: str) -> list[dict]:
    """feedparser over one feed body -> [{title, url, date}] (unfiltered). Raises SourceChanged on junk."""
    try:
        import feedparser
    except ImportError:
        raise SourceDown(SOURCE, "feedparser unavailable")
    if not (text or "").strip():
        raise SourceChanged(SOURCE, "empty body", url)
    parsed = feedparser.parse(text)
    entries = parsed.get("entries") or []
    if not entries:
        head = (text or "")[:80].replace("\n", " ")
        raise SourceChanged(SOURCE, f"no entries parsed: {head!r}", url)
    out = []
    for e in entries:
        link = (e.get("link") or "").strip()
        title = re.sub(r"\s+", " ", (e.get("title") or "")).strip()
        if not link or not title:
            continue
        out.append({"title": title, "url": link, "date": _when(e)})
    return out


def _matches(item: dict) -> bool:
    return bool(KEYWORDS.search(item["title"]))


def fetch(session, feeds: list[tuple[str, str]] | None = None) -> tuple[list[dict], list[str]]:
    """Fetch every feed; return (items filtered/deduped/newest-first, notes). Raises when NO feed
    yielded anything — one working feed is success."""
    notes: list[str] = []
    items: dict[str, dict] = {}
    errors: list[SourceError] = []
    for name, url in (feeds or FEEDS):
        try:
            text = session.get_text(url, source=SOURCE)
            got = parse_feed(text, url)
        except SourceError as e:
            notes.append(f"{name}: {e.kind} — {e.detail[:60]}")
            errors.append(e)
            continue
        kept = 0
        for it in got:
            if _matches(it) and it["url"] not in items:
                items[it["url"]] = it
                kept += 1
        notes.append(f"{name}: {kept}/{len(got)} primary-market items")
    if not items:
        if errors and len(errors) == len(feeds or FEEDS):
            raise errors[-1]
        raise SourceChanged(SOURCE, "feeds answered but no primary-market items matched")
    ordered = sorted(items.values(), key=lambda i: i.get("date") or "", reverse=True)
    return ordered, notes
