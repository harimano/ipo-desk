#!/usr/bin/env python3
"""Survey what BSE serves to an honestly identified client on the network this runs on. Status, bytes, content type
and a short body snippet only.

Run by .github/workflows/probe-bse.yml (workflow_dispatch) from a GitHub runner — where the collector runs — after
5 Nov 2026 showed api.bseindia.com answering 403 to GitHub AND to Cloudflare's Worker egress, while the bhavcopy
download answers 200. Two questions: (1) does the API answer an identified client at all; (2) which non-API
surfaces answer (legacy beta pages, report downloads, RSS, the attachment store), so a leg can be rebuilt on one.
The client says who it is (User-Agent names the repo), sends no browser disguise, primes no cookies, uses no proxy.
If BSE says no to an identified client, that is BSE's answer and the desk states it as a limit.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys

import httpx

HEADERS = {"User-Agent": "ipo-desk/1.0 (+https://github.com/harimano/ipo-desk)", "Accept": "*/*"}
API_HEADERS = {**HEADERS, "Origin": "https://www.bseindia.com", "Referer": "https://www.bseindia.com/"}   # what the collector sends today
API = "https://api.bseindia.com/BseIndiaAPI/api"
yday = (dt.date.today() - dt.timedelta(days=1)).strftime("%Y%m%d")

API_CALLS = [
    ("api bulk deals", f"{API}/BulkDeal_Beta/w"),
    ("api block deals", f"{API}/BlockDeal_Beta/w"),
    ("api public issues", f"{API}/GetPublicIssue_par_updated/w"),
    ("api announcements", f"{API}/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate={yday}&strScrip=&strSearch=P&strToDate={yday}&strType=C&subcategory=-1"),
]
SURFACES = [
    ("control: bhavcopy download", f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{yday}_F_0000.CSV"),
    ("www homepage", "https://www.bseindia.com/"),
    ("beta: public issues (legacy aspx, bse_issues.py)", "https://beta.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p"),
    ("beta: cumulative demand (legacy aspx)", "https://beta.bseindia.com/markets/publicIssues/CummDemandSchedule.aspx"),
    ("www: bulk deals page", "https://www.bseindia.com/markets/equity/EQReports/bulk_deals.aspx"),
    ("www: block deals page", "https://www.bseindia.com/markets/equity/EQReports/block_deals.aspx"),
    ("www: bulk+block deals page", "https://www.bseindia.com/markets/equity/EQReports/BulknBlockDeals.aspx"),
    ("www: notices RSS", "https://www.bseindia.com/data/xml/notices.xml"),
    ("www: announcements page", "https://www.bseindia.com/corporates/ann.html"),
    ("www: corp filing attachment store (dir)", "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"),
    ("www: IPO page", "https://www.bseindia.com/markets/PublicIssues/IPODisplay.aspx"),
    # batch 2 (5 Nov, after the first run): the www pages are one 16.9 KB app shell that calls the blocked API from the
    # browser, so the question is whether BSE's LEGACY (beta.) pages and feeds still carry deals and announcements server-side.
    ("beta: bulk deals (legacy aspx)", "https://beta.bseindia.com/markets/equity/EQReports/bulk_deals.aspx"),
    ("beta: block deals (legacy aspx)", "https://beta.bseindia.com/markets/equity/EQReports/block_deals.aspx"),
    ("beta: bulk+block deals (legacy aspx)", "https://beta.bseindia.com/markets/equity/EQReports/BulknBlockDeals.aspx"),
    ("beta: announcements (legacy aspx)", "https://beta.bseindia.com/corporates/ann.aspx"),
    ("beta: announcements (legacy, alt)", "https://beta.bseindia.com/corporates/ann.html"),
    ("beta: homepage", "https://beta.bseindia.com/"),
    ("www: announcements RSS?", "https://www.bseindia.com/data/xml/announcements.xml"),
    ("www: corp announcements RSS?", "https://www.bseindia.com/corporates/annrss.aspx"),
    ("www: RSS index?", "https://www.bseindia.com/rss.html"),
    ("www: bulk deals download?", f"https://www.bseindia.com/download/BulkDeals/bulk_{yday}.csv"),
    ("www: markets/equity download index?", "https://www.bseindia.com/download/"),
    ("www: sitemap", "https://www.bseindia.com/sitemap.xml"),
    ("www: robots.txt", "https://www.bseindia.com/robots.txt"),
    ("beta: robots.txt", "https://beta.bseindia.com/robots.txt"),
    ("api: robots.txt", "https://api.bseindia.com/robots.txt"),
]


SAVE = {   # bodies worth keeping as fixtures for the rebuild (uploaded by the workflow as an artifact; never committed here)
    "beta: public issues (legacy aspx, bse_issues.py)": "beta-public-issues.html",
    "beta: bulk deals (legacy aspx)": "beta-bulk-deals.html",
    "beta: block deals (legacy aspx)": "beta-block-deals.html",
    "beta: bulk+block deals (legacy aspx)": "beta-bulk-block-deals.html",
    "beta: announcements (legacy, alt)": "beta-announcements.html",
    "www: announcements RSS?": "www-announcements-rss.xml",
    "www: notices RSS": "www-notices-rss.xml",
    "www: sitemap": "www-sitemap.xml",
}
OUT = pathlib.Path("probe-out")


def show(label: str, r: httpx.Response | Exception) -> None:
    if isinstance(r, Exception):
        print(f"{label:52s} ERROR {type(r).__name__}: {r}"); return
    body = r.content or b""
    snip = body[:160].decode("utf8", "replace").replace("\n", " ").replace("\r", " ")
    srv = r.headers.get("server", ""); ct = r.headers.get("content-type", "")
    if label in SAVE and r.status_code == 200:
        OUT.mkdir(exist_ok=True); (OUT / SAVE[label]).write_bytes(body)
    print(f"{label:52s} {r.status_code} {len(body):>8d} B  {ct[:28]:28s} server={srv[:14]:14s} | {snip}")


def get(client: httpx.Client, url: str, headers: dict) -> httpx.Response | Exception:
    try:
        return client.get(url, headers=headers, timeout=30)
    except Exception as e:
        return e


def main() -> int:
    print(f"probe_bse {dt.datetime.now(dt.UTC).isoformat()}  python {sys.version.split()[0]}  httpx {httpx.__version__}")
    print("\n== 1. The API, as the collector calls it, from an identified client")
    with httpx.Client(http2=True, follow_redirects=True) as c:
        for label, url in API_CALLS:
            show(label, get(c, url, API_HEADERS))
    print("\n== 2. Non-API surfaces")
    with httpx.Client(http2=True, follow_redirects=True) as c:
        for label, url in SURFACES:
            show(label, get(c, url, HEADERS))
    print("\n== 3. The legacy issues page's form: does it answer the non-IPO types (OFS, buyback, rights) to a plain POST?")
    issues_form(ISSUES_URL)
    return 0


ISSUES_URL = "https://beta.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p"
FORM_TYPES = [("0", "all"), ("OFS", "ofs"), ("BuyBack", "buyback"), ("RI", "rights"), ("IPO", "ipo")]


def issues_form(url: str) -> None:
    """A classic ASP.NET page: GET it for __VIEWSTATE / __EVENTVALIDATION, then POST the same form back with the
    dropdowns set, exactly as the page's own Submit button does. Status, bytes, row and type counts; bodies saved."""
    with httpx.Client(http2=True, follow_redirects=True) as c:
        page = get(c, url, HEADERS)
        if isinstance(page, Exception) or page.status_code != 200:
            show("form: GET", page); return
        html = page.text
        hidden = dict(re.findall(r'<input type="hidden" name="([^"]+)"[^>]*value="([^"]*)"', html))
        print(f"{'form: hidden fields':52s} {sorted(hidden)}")
        for status_code, status_label in (("L", "live"), ("F", "forthcoming")):
            for value, label in FORM_TYPES:
                data = {**hidden, "ctl00$ContentPlaceHolder1$ddlExchPlatform": "0", "ctl00$ContentPlaceHolder1$ddlIssueType": value,
                        "ctl00$ContentPlaceHolder1$rblIssueStatus": status_code, "ctl00$ContentPlaceHolder1$ScripName": "",
                        "ctl00$ContentPlaceHolder1$txtFromDate": "", "ctl00$ContentPlaceHolder1$txtIssuetype": "",
                        "ctl00$ContentPlaceHolder1$btnSubmit": "Submit"}
                try:
                    r = c.post(url, data=data, headers={**HEADERS, "Referer": url, "Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
                except Exception as e:
                    print(f"{'form: ' + status_label + ' / ' + label:52s} ERROR {type(e).__name__}: {e}"); continue
                body = r.text
                rows = len(re.findall(r"<tr", body)); types = sorted(set(re.findall(r"<td[^>]*>\s*(IPO|FPO|OFS|BuyBack|Buyback[^<]*|RI|Right[^<]*|OTB|DPI|CMN|IPP|InvITs|REITS)\s*<", body)))
                print(f"{'form: ' + status_label + ' / ' + label:52s} {r.status_code} {len(r.content):>8d} B  tr={rows:<4d} types={types}")
                if r.status_code == 200:
                    OUT.mkdir(exist_ok=True); (OUT / f"beta-issues-form-{status_label}-{label}.html").write_text(body, encoding="utf8")


if __name__ == "__main__":
    sys.exit(main())
