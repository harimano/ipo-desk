"""BSE corporate announcements — the exchange's own RSS feed, read once a run and filtered by scrip code.

  GET https://www.bseindia.com/data/xml/announcements.xml
      <rss><channel><lastBuildDate>…</lastBuildDate><item><title>Company Ltd (500325)</title><link>…AttachLive/<guid>.pdf</link>
      <scripcode>500325</scripcode><description>the headline</description><pubDate>05-Nov-2026 14:59:15</pubDate></item>…
  Every announcement BSE disseminated TODAY (midnight to the fetch), all companies, ~7,700 items / 2.6 MB on a results
  day. No category, no news id; the attachment link is the public one. Rows keep the shape the API gave, so filings
  reads them unchanged: {headline, subject, date, url, category, subcategory, scrip, company, newsId}.

Until 5 Nov 2026 this was api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w, one call per watched parent over a
date window. That host answers 403 "Access Denied" to GitHub's runners and to Cloudflare alike (scripts/probe_bse.py);
the feed answers an identified client. The feed is one day deep: a day the collector does not run is a day of
announcements never seen — the full runs (06:43 and 18:13 IST) plus the intraday ones make that a holiday-only risk,
and `filings` already treats a missed announcement as partial recall, never fixed by reading PDFs.

An empty feed is a legitimate answer (a holiday morning), so the parser raises SourceChanged only on a malformed
document, never on zero items.
"""
from __future__ import annotations

import datetime as dt
import re
from xml.etree import ElementTree as ET

from ..errors import SourceChanged
from ..http import BSE_WEB, Session

FEED_URL = BSE_WEB + "/data/xml/announcements.xml"
ATTACH_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
_MON = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def attachment_url(name: str | None) -> str | None:
    if not name or not isinstance(name, str):
        return None
    name = name.strip()
    if not name:
        return None
    if name.lower().startswith("http"):
        return name
    return ATTACH_BASE + name


def _iso_date(text: str | None) -> str | None:
    """'05-Nov-2026 14:59:15' (the feed's pubDate) or an RFC-822 date -> 'YYYY-MM-DD'."""
    m = re.search(r"(\d{1,2})[-\s]([A-Za-z]{3})[-\s](\d{4})", text or "")
    if not m or m.group(2).lower() not in _MON:
        return None
    try:
        return dt.date(int(m.group(3)), _MON[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return None


def _text(item: ET.Element, tag: str) -> str:
    return (item.findtext(tag) or "").strip()


def parse_feed(xml: str | bytes, *, source: str = "bse_ann", url: str = FEED_URL) -> list[dict]:
    try:
        root = ET.fromstring(xml.encode("utf8") if isinstance(xml, str) else xml)
    except ET.ParseError as e:
        raise SourceChanged(source, f"announcements feed is not XML: {e}", url)
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise SourceChanged(source, f"announcements feed: <{root.tag}> is not an <rss><channel>", url)
    rows = []
    for item in channel.findall("item"):
        headline, scrip, title = _text(item, "description"), _text(item, "scripcode"), _text(item, "title")
        if not headline and not scrip:
            raise SourceChanged(source, "announcement item without description and scripcode", url)
        company = re.sub(r"\s*\(\d+\)\s*$", "", title).strip() or None
        rows.append({"headline": headline, "subject": None, "date": _iso_date(_text(item, "pubDate")), "url": attachment_url(_text(item, "link")),
                     "category": None, "subcategory": None, "scrip": scrip or None, "company": company, "newsId": None})
    return rows


def fetch_feed(session: Session, *, source: str = "bse_ann") -> list[dict]:
    """Today's announcements, all companies, newest first as BSE serves them."""
    return parse_feed(session.get_text(FEED_URL, source=source, headers={"Referer": BSE_WEB + "/"}), source=source)


def for_scrip(rows: list[dict], scrip: str, from_date: dt.date, to_date: dt.date) -> list[dict]:
    """The feed's rows for one scrip code inside [from_date, to_date] (undated rows kept: the feed is today's)."""
    lo, hi = from_date.isoformat(), to_date.isoformat()
    return [r for r in rows if r.get("scrip") == str(scrip) and (r.get("date") is None or lo <= r["date"] <= hi)]
