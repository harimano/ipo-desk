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
]


def show(label: str, r: httpx.Response | Exception) -> None:
    if isinstance(r, Exception):
        print(f"{label:52s} ERROR {type(r).__name__}: {r}"); return
    body = r.content or b""
    snip = body[:160].decode("utf8", "replace").replace("\n", " ").replace("\r", " ")
    srv = r.headers.get("server", ""); ct = r.headers.get("content-type", "")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
