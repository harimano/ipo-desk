"""SEBI public-issues filing registers (DRHP = smid 10, RHP = smid 11).

Primary (from ipo-radar.md B6 / automation/update.py): POST
  https://www.sebi.gov.in/sebiweb/ajax/home/getnewslistinfo.jsp
  nextValue=<page>&next=n&search=&fromDate=&toDate=&fromYear=&toYear=&deptId=&sid=3&ssid=15&smid=<smid>
  &ssidhidden=15&intmid=-1&sText=Filings
  Referer https://www.sebi.gov.in/sebiweb/home/HomeAction.do
Fallback (from ipo-tracker.md 1c): GET
  https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=<smid>
Both answer the same table: <tr><td>Mon DD, YYYY</td><td><a href="https://www.sebi.gov.in/filings/public-issues/...html"
title="...">...</a></td></tr>.

Detail page → PDF: the full document is `https://www.sebi.gov.in/sebi_data/attachdocs/<mon-yyyy>/<epoch>.pdf`;
the abridged prospectus is `.../sebi_data/commondocs/<mon-yyyy>/<Name> - AP_p.pdf`. Prefer the former.
The detail page may wrap the PDF in the viewer `https://www.sebi.gov.in/web/?file=<encoded pdf url>`.
"""
from __future__ import annotations

import datetime as dt
import html as htmlmod
import re
import urllib.parse

from ..errors import SourceChanged
from ..http import SEBI, Session

AJAX = SEBI + "/sebiweb/ajax/home/getnewslistinfo.jsp"
LISTING = SEBI + "/sebiweb/home/HomeAction.do"
REFERER = SEBI + "/sebiweb/home/HomeAction.do"
SMID = {"DRHP": 10, "RHP": 11}

_DATE_RE = re.compile(r"([A-Z][a-z]{2})\.?\s+(\d{1,2}),?\s+(\d{4})")
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_ANCHOR_RE = re.compile(r"<a\b([^>]*)href=[\'\"]([^\'\"]*/filings/[^\'\"]+)[\'\"]([^>]*)>(.*?)</a>", re.S | re.I)
_TITLE_ATTR_RE = re.compile(r"title=[\'\"]([^\'\"]+)[\'\"]", re.I)
_TAG_RE = re.compile(r"<[^>]+>")

# classification, most specific first
_ADDENDUM_RE = re.compile(r"addendum|corrigendum|erratum", re.I)
_DRHP_RE = re.compile(r"draft\s+red\s+herring|\bU?DRHP\b|draft\s+prospectus|draft\s+offer\s+document", re.I)
_RHP_RE = re.compile(r"red\s+herring|\bRHP\b", re.I)
_PROSPECTUS_RE = re.compile(r"prospectus|offer\s+document", re.I)

_PDF_FULL_RE = re.compile(r"(https?://[^\'\"\s<>]*?/sebi_data/attachdocs/[^\'\"\s<>]+?\.pdf)", re.I)
_PDF_VIEWER_RE = re.compile(r"[?&]file=([^&\'\"\s<>]+\.pdf)", re.I)
_PDF_ANY_RE = re.compile(r"href=[\'\"]([^\'\"]+\.pdf)[\'\"]", re.I)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(_TAG_RE.sub(" ", s))).strip()


def _iso(mon: str, day: str, year: str) -> str | None:
    try:
        return dt.datetime.strptime(f"{mon} {day} {year}", "%b %d %Y").date().isoformat()
    except ValueError:
        return None


def classify(title: str) -> str | None:
    """DRHP / RHP / Addendum / Prospectus, or None when the title is none of those."""
    if not title:
        return None
    if _ADDENDUM_RE.search(title):
        return "Addendum"
    if _DRHP_RE.search(title):
        return "DRHP"
    if _RHP_RE.search(title):
        return "RHP"
    if _PROSPECTUS_RE.search(title):
        return "Prospectus"
    return None


def parse_listing(html: str, *, source: str = "sebi", url: str | None = None) -> list[dict]:
    """Rows {title, date, detailUrl, kind}. Raises SourceChanged when no filing rows are present."""
    rows: list[dict] = []
    seen: set[str] = set()
    for m in _ROW_RE.finditer(html or ""):
        tr = m.group(1)
        a = _ANCHOR_RE.search(tr)
        if not a:
            continue
        href = htmlmod.unescape(a.group(2)).strip()
        detail = urllib.parse.urljoin(SEBI + "/", href)
        attrs = a.group(1) + a.group(3)
        t = _TITLE_ATTR_RE.search(attrs)
        title = _clean(t.group(1)) if t else _clean(a.group(4))
        d = _DATE_RE.search(_clean(tr[: a.start()]) or _clean(tr))
        date = _iso(*d.groups()) if d else None
        if not title or detail in seen:
            continue
        seen.add(detail)
        rows.append({"title": title, "date": date, "detailUrl": detail, "kind": classify(title)})
    if not rows:
        raise SourceChanged(source, "no filing rows found in listing", url)
    return rows


def _post_body(smid: int, page: int) -> dict:
    return {
        "nextValue": str(page - 1), "next": "n",     # zero-based: nextValue=1 is the SECOND page (seen live 17 Sep 2026) "search": "", "fromDate": "", "toDate": "",
        "fromYear": "", "toYear": "", "deptId": "", "sid": "3", "ssid": "15", "smid": str(smid),
        "ssidhidden": "15", "intmid": "-1", "sText": "Filings",
    }


_ISSUER_RE = re.compile(r"\s*[-\u2013\u2014:]+\s*(?:the\s+)?(?:second\s+|third\s+)?(?:draft|abridged|addendum|corrigendum|erratum|"
                        r"u?drhp|rhp|red\s+herring|prospectus|offer\s+document|public\s+announcement).*$", re.I)


def issuer(title: str) -> str:
    """'Torrent Gas Limited - Draft Abridged Prospectus' -> 'Torrent Gas Limited'."""
    return _ISSUER_RE.sub("", _clean(title)).strip(" -\u2013\u2014.")


def _tag(rows: list[dict], register: str) -> list[dict]:
    """The register is the evidence: real titles say 'Draft Abridged Prospectus', not 'DRHP', so what a row
    means comes from which list SEBI put it on (seen live 17 Sep 2026), not from its wording."""
    for r in rows:
        r["register"] = register
        r["issuer"] = issuer(r["title"])
    return rows


def fetch_listing(session: Session, kind: str = "DRHP", page: int = 1, *, source: str = "sebi") -> list[dict]:
    """Page `page` of the DRHP or RHP register. POST ajax first, GET listing page as fallback."""
    smid = SMID[kind]
    headers = {"Referer": REFERER, "X-Requested-With": "XMLHttpRequest",
               "Content-Type": "application/x-www-form-urlencoded"}
    try:
        html = session.post_text(AJAX, _post_body(smid, page), source=source, headers=headers)
        return _tag(parse_listing(html, source=source, url=AJAX), kind)
    except SourceChanged as first:
        params = {"doListing": "yes", "sid": "3", "ssid": "15", "smid": str(smid)}
        if page > 1:
            params["page"] = str(page)
        html = session.get_text(LISTING, source=source, params=params, headers={"Referer": REFERER})
        try:
            return _tag(parse_listing(html, source=source, url=LISTING), kind)
        except SourceChanged as second:
            raise SourceChanged(source, f"ajax: {first.detail}; listing: {second.detail}", LISTING)


def pick_pdf(detail_html: str, base: str = SEBI + "/") -> str | None:
    """Best PDF link on a filing detail page: full attachdocs first, then viewer ?file=, then any .pdf
    that is not the abridged commondocs/*_p.pdf. Returns None when nothing usable."""
    if not detail_html:
        return None
    text = htmlmod.unescape(detail_html)
    m = _PDF_FULL_RE.search(text)
    if m:
        return m.group(1)
    candidates: list[str] = []
    for m in _PDF_VIEWER_RE.finditer(text):
        candidates.append(urllib.parse.unquote(m.group(1)))
    for m in _PDF_ANY_RE.finditer(text):
        candidates.append(m.group(1))
    candidates = [urllib.parse.urljoin(base, c) for c in candidates]
    full = [c for c in candidates if "/attachdocs/" in c]
    if full:
        return full[0]
    non_abridged = [c for c in candidates if not _is_abridged(c)]
    if non_abridged:
        return non_abridged[0]
    return candidates[0] if candidates else None


def _is_abridged(u: str) -> bool:
    lu = u.lower()
    return "/commondocs/" in lu or lu.endswith("_p.pdf") or "abridged" in lu


def resolve_pdf(session: Session, detail_url: str, *, source: str = "sebi") -> str | None:
    html = session.get_text(detail_url, source=source, headers={"Referer": SEBI + "/"})
    return pick_pdf(html, detail_url)
