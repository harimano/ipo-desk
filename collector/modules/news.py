"""news — owns `news`: primary-market headlines from RSS (sources/rss.py), merged with prev deduped by
url, newest first, capped at 25 rows ({title, url, date} only).
"""
from __future__ import annotations

import logging

from ..http import Session
from ..result import Result, try_chain
from ..schema import CAPS
from ..sources import rss

log = logging.getLogger("collector.news")

CAP = CAPS.get("news.rows", 25)


def merge_news(prev_news: list[dict], fresh: list[dict], cap: int = CAP) -> list[dict]:
    by_url: dict[str, dict] = {}
    for item in list(fresh) + list(prev_news or []):
        if not isinstance(item, dict) or not item.get("url") or not item.get("title"):
            continue
        url = item["url"].strip()
        if url in by_url:
            continue
        by_url[url] = {"title": item["title"], "url": url, "date": item.get("date")}
    out = sorted(by_url.values(), key=lambda i: i.get("date") or "", reverse=True)
    return out[:cap]


def _from_rss(session: Session, prev: dict, res: Result) -> str | None:
    items, notes = rss.fetch(session)
    res.notes.extend(notes)
    merged = merge_news(prev.get("news") or [], items)
    res.replace["news"] = merged
    res.notes.append(f"{len(items)} fresh, {len(merged)} kept")
    return items[0].get("date") if items else None


def run(session: Session, prev: dict, res: Result) -> Result:
    return try_chain(res, [("rss", lambda: _from_rss(session, prev, res))])
