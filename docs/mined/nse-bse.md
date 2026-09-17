# `nse` (NseIndiaApi) and `bse` (BseIndiaApi) — code-mining notes

Source: /home/claude/ref/NseIndiaApi and /home/claude/ref/BseIndiaApi (local clones). Both by Benny Thadikaran, both GPLv3.

| | nse | bse |
|---|---|---|
| pyproject version | 4.0.1 | 3.3.1 |
| last commit | 2026-08-31 21:11 +0530 "Bump to version v4.0.1" | 2026-08-19 19:36 +0530 "Bump to version 3.3.1" |
| licence | GPLv3 (LICENSE + classifier) | GPLv3 (LICENSE + classifier) |
| hard deps | `httpx==0.28.1`, `mthrottle>=0.0.1` | `requests>=2.31`, `mthrottle>=0.0.1` |
| extras | `nse[server]` = `httpx[http2]==0.28.1`; `nse[local]` = plain httpx | none |
| python | >=3.8 | >=3.8 |
| import | `from nse import NSE` (src/nse/__init__.py) | `from bse import BSE, SymbolParser` (src/bse/__init__.py) |

---

## NSE package

### 1. Session / cookie layer

Files: `src/nse/NSE.py` (class), `src/nse/transport.py` (httpx transport, default), `src/nse/request_transport.py` (requests transport, opt-in).

**Constructor** — `NSE(download_folder, server=False, timeout=15, use_requests_library=False)` (NSE.py:51-80).
- `download_folder` is mandatory; it is where the cookie file AND downloaded reports land. Created if missing (NSE.py:91-102).
- **Headers** (NSE.py:59-67): UA `Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0`; `Accept: */*`; `Accept-Language: en-US,en;q=0.5`; `Accept-Encoding: gzip, deflate` (no `br`); `Referer: https://www.nseindia.com/get-quotes/equity?symbol=HDFCBANK`. No Origin, no sec-fetch-* headers.
- **What `server=True` does** (transport.py:28): exactly one thing — `httpx.Client(http2=server)`. So `server=True` means HTTP/2 over httpx (needs the `h2` package, i.e. `nse[server]`); `server=False` is still httpx but HTTP/1.1. **README is stale**: it says `server=False` uses `requests` — that was true in v1.x; in 4.0.1 `requests` is only used if `use_requests_library=True` (NSE.py:71-76), and `requests` is NOT a declared dependency, so that path needs a manual `pip install requests`.
- **Cookie bootstrap** (transport.py:30-53): on construction it looks for `<download_folder>/nse_cookies_httpx.json` (`nse_cookies_requests.json` for the requests transport). If absent, or if any cookie `is_expired()`, it GETs `https://www.nseindia.com/option-chain` (transport.py:36) and persists `dict(r.cookies)` to the JSON file. The bootstrap happens **inside `__init__`**, so a 403 at bootstrap raises during `NSE(...)` itself. `exit()` / `__exit__` closes the client and **deletes the cookie file** (transport.py:55-57), so cookie reuse across runs only works if you skip `exit()`. In GitHub Actions each run is a fresh box anyway.
- No cookie refresh on a mid-session 401/403; only the expiry check at construction.
- **Throttle** (transport.py:8-14): module-level `mthrottle.Throttle({"default": {"rps": 3}}, 10)`, `th.check()` before every request/download. Semantics (mthrottle 0.0.2): every 3rd call sleeps until the next whole-second boundary since the throttle was created. The `10` is `maxPenaltyCount` for `penalize()`, which the nse package never calls. So: ~3 req/s cap, no 429 handling.
- **Retry logic: none.** Zero retries anywhere.
- **Exceptions** (transport.py:66-83):
  - `httpx.ReadTimeout` -> `TimeoutError("The request timed out.")`. Only ReadTimeout is caught; `httpx.ConnectTimeout`, `httpx.ConnectError`, `httpx.PoolTimeout` propagate raw.
  - `httpx.RemoteProtocolError` -> calls `self.exit()` (deletes cookie file) then `ConnectionError("The connection to the remote server was unexpectedly closed.")`.
  - Any non-2xx (403, 421, 429, 5xx) -> `ConnectionError(f"{url} {status}: {reason}")`. The status code is only in the message string, not an attribute; parse it with a regex if you need to branch on 403 vs 5xx.
  - `.json()` decode errors (NSE returning an HTML block page with 200) propagate as `json.JSONDecodeError`.
- **`download()`** (transport.py:85-103): streams to `<folder>/<last path segment>`. Only check is `Content-Type` contains `text/html` -> `RuntimeError("NSE file is unavailable or not yet updated.")`. It does **not** check the status code, and does not catch timeouts, so a 404 with a non-HTML body writes a junk file and raw `httpx.ReadTimeout` can surface. The callers then `_unzip` (NSE.py:105-125) which raises `zipfile.BadZipFile` on junk.

### 2/3. Method signatures, return shapes, URLs

All JSON endpoints are under `base_url = "https://www.nseindia.com/api"` (NSE.py:47); archives under `archive_url = "https://nsearchives.nseindia.com"` (NSE.py:49).

| Method (NSE.py line) | Signature | URL | Returns |
|---|---|---|---|
| `listCurrentIPO` (963) | `() -> List[Dict]` | `GET /api/ipo-current-issue` | list of `{symbol, companyName, series, issueStartDate "26-Mar-2024", issueEndDate, status "Active", issueSize (str), issuePrice "Rs.200 to Rs.210", srNo, category "Total", noOfSharesOffered (str), noOfsharesBid (str, may be "6.77E7"), noOfTime (str)}`. Empty list when no live issue. |
| `listUpcomingIPO` (973) | `() -> List[Dict]` | `GET /api/all-upcoming-issues?category=ipo` | list of `{symbol, companyName, series, issueStartDate, issueEndDate, status, issueSize, issuePrice, sr_no (int)}` |
| `listPastIPO` (985) | `(from_date: datetime=None, to_date: datetime=None) -> List[Dict]`; defaults to_date=now, from_date=to_date-90d; ValueError if reversed | `GET /api/public-past-issues?from_date=DD-MM-YYYY&to_date=DD-MM-YYYY` | list of `{symbol, companyName, ipoStartDate "22-MAR-2024", ipoEndDate, priceRange, listingDate ("-" if not listed), securityType "SME"/"EQ", issuePrice, company}` |
| `bulkdeals` (1483) | `(option_type: Literal["block_deals","bulk_deals","short_selling"], fromdate: datetime, todate: datetime) -> List[Dict]`; both dates required; ValueError if reversed or >365 days; **RuntimeError if `data` empty** (e.g. no deals that day) | `GET /api/historicalOR/bulk-block-short-deals?optionType=..&from=DD-MM-YYYY&to=DD-MM-YYYY` | returns `resp["data"]`: list of `{BD_DT_DATE "31-Oct-2023", BD_DT_ORDER, BD_SYMBOL, BD_SCRIP_NAME, BD_CLIENT_NAME, BD_BUY_SELL "BUY"/"SELL", BD_QTY_TRD (int), BD_TP_WATP (float), BD_REMARKS}` |
| `blockDeals` (1097) | `() -> Dict` | `GET /api/block-deal` | live intraday block deals: `{timestamp, data: [...] (empty list if none), totalTradedValue, totalTradedVolume, "Session 1"/"Session 2": {advances,declines,unchanged}, marketStatus: {...}}` |
| `announcements` (489) | `(index: Literal["equities","sme","debt","mf","invitsreits"]="equities", symbol: str=None, fno=False, from_date: datetime=None, to_date: datetime=None) -> List[Dict]`; date range only applied if BOTH given; no range -> today | `GET /api/corporate-announcements?index=equities[&symbol=X][&fo_sec=True][&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY]` | list of `{symbol, desc, dt "18102023221142", attchmntFile (full https://nsearchives.nseindia.com/corporate/....pdf), sm_name, sm_isin, an_dt "18-Oct-2023 22:11:42", sort_date "2023-10-18 22:11:42", seq_id, smIndustry, orgid, attchmntText, bflag, old_new, csvName, exchdisstime, difference}` |
| `actions` (438) | corporate actions | `GET /api/corporates-corporateActions` | list |
| `boardMeetings` (544) | | `GET /api/corporate-board-meetings` | list |
| `equityBhavcopy` (213) | `(date: datetime, folder=None) -> Path` | date < 2024-07-08: `nsearchives/content/historical/EQUITIES/{YYYY}/{MON}/cm{DDMONYYYY}bhav.csv.zip`; else `nsearchives/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip` | Path to unzipped CSV. Raises RuntimeError (html body), FileNotFoundError, BadZipFile |
| `deliveryBhavcopy` (255) | `(date, folder=None) -> Path` | `nsearchives/products/content/sec_bhavdata_full_{DDMMYYYY}.csv` | Path |
| `indicesBhavcopy` (284) | | `nsearchives/content/indices/ind_close_all_{DDMMYYYY}.csv` | Path |
| `fnoBhavcopy` (312) | | `nsearchives/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip` | Path |
| `priceband_report` (342) | | `nsearchives/content/equities/sec_list_{..}.csv` | Path |
| `pr_bhavcopy` (372) | | `nsearchives/archives/equities/bhavcopy/pr/PR{..}.zip` | Path |
| `cm_mii_security_report` (406) | | `nsearchives/content/cm/NSE_CM_security_{..}.csv.gz` | Path |
| `download_document` (1545) | `(url: str, folder=None, extract_files: List[str]=None) -> Path` — **generic archive fetch**, any URL, auto-unzips `.zip` | whatever you pass (e.g. `https://nsearchives.nseindia.com/content/equities/bulk.csv`) | Path |
| `fetch_daily_reports_file_metadata` (1939) | `(segment)` | `GET /api/daily-reports?key=..` | dict |

**FII/DII: confirmed absent.** `grep -i "fii\|dii"` over src/nse/NSE.py returns nothing. No method hits `/api/fiidiiTradeReact` or the archives FII/DII CSVs. You'd need `download_document()` with a hand-built URL, or a raw request via `nse._transport.request(url)` (private, but it's just `request(url, params=None)` and reuses the cookie jar).

Also present but not asked: `listSme` (`/api/live-analysis-emerge`), `circulars` (`/api/circulars`), `financial_results`, `shareholding`, `quote`, `optionChain`, historical data via `/api/historicalOR/*`.

### 4. Cloud/datacenter caveats (as documented)

- README.md:15 and docs/source/index.rst:13: 3 rps throttle "allows making large number of requests without ... getting blocked"; advises downloading reports after-market hours, adding 0.5-1 s extra sleep, caching files.
- README.md:23: "v1.2.0 NSE package now works in server environments like AWS. See PR #10" — the mechanism is HTTP/2 via httpx (the theory being NSE's WAF fingerprints HTTP/1.1 python clients). README.md:33-44 and docs/source/usage.rst:21-32: "To install on server like AWS or other cloud services: `pip install nse[server]`... Make sure to set server parameter to True."
- No mention of GitHub Actions, Azure/MS IP ranges, 403/421 handling, or proxies anywhere in README/docs/code comments. tests/test_nse_h2*.py exercise `server=True` live; tests/Dockerfile only tests `status()` in a slim python 3.8 container.
- Implicit caveats from the code: (a) cookie bootstrap is in the constructor, so blocks surface as `ConnectionError` from `NSE(...)`; (b) there is no retry or backoff; (c) `download()` ignores status codes; (d) `Accept-Encoding` lacks `br`, and the UA is a 2023 Firefox 118 string — both are fingerprint-able.

---

## BSE package

### 6. Session setup

File: `src/bse/BSE.py`. Constructor `BSE(download_folder)` (BSE.py:67-83) — `download_folder` is a required positional (docs' `BSE()` example without args is wrong).
- Plain `requests.Session()`. **No cookie bootstrap at all** — no priming GET; the constructor makes no network call.
- Headers (BSE.py:69-80): UA `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3`; `Accept: application/json, text/plain, */*`; `Accept-Language: en-US,en;q=0.5`; `Origin: https://www.bseindia.com/`; `Referer: https://www.bseindia.com/`; `Connection: keep-alive`. (Origin with trailing slash is technically malformed but api.bseindia.com accepts it.)
- Throttle (BSE.py:15-24): `Throttle({"lookup": {"rps": 15}, "default": {"rps": 8}}, 15)`; `th.check()` before each API call, `th.check("lookup")` for the smart-search endpoint.
- `__req` (BSE.py:144-153): timeout 10 s; `requests.ReadTimeout` -> `TimeoutError("Request timed out")`; non-ok -> `ConnectionError(f"{status}: {reason}")`. No retry. `requests.ConnectionError` propagates raw.
- `__download` (BSE.py:107-142): 404 -> `RuntimeError("Report is unavailable or not yet updated.")`; other non-ok -> RuntimeError; cleans up partial file.
- `exit()` / context manager just closes the session (BSE.py:85-96).

### 7. Methods, signatures, URLs

`api_url = "https://api.bseindia.com/BseIndiaAPI/api"` (BSE.py:38); `base_url = "https://www.bseindia.com/"`.

| Method (line) | Signature | URL | Returns |
|---|---|---|---|
| `announcements` (240) | `(page_no=1, from_date: datetime=None, to_date: datetime=None, segment: Literal["equity","debt","mf_etf"]="equity", scripcode: str=None, category: str="-1", subcategory: str="-1") -> Dict[str, List[dict]]`; dates default to now; ValueError if reversed or subcategory without category | `GET /AnnSubCategoryGetData/w?pageno=1&strCat=-1&subcategory=-1&strPrevDate=YYYYMMDD&strToDate=YYYYMMDD&strSearch=P&strscrip=500325&strType=C` (`strType` C/D/M for equity/debt/mf_etf) | `{"Table": [ {NEWSID, SCRIP_CD (int), XML_NAME, NEWSSUB, DT_TM "2023-10-20T23:44:22.95", NEWS_DT, CRITICALNEWS, ANNOUNCEMENT_TYPE, QUARTER_ID, FILESTATUS, ATTACHMENTNAME "<uuid>.pdf", MORE, HEADLINE, CATEGORYNAME, OLD, RN, PDFFLAG, NSURL, SLONGNAME, AGENDA_ID, TotalPageCnt, News_submission_dt, DissemDT, TimeDiff, Fld_Attachsize, SUBCATNAME, AUDIO_VIDEO_FILE} ], "Table1": [{"ROWCNT": int}]}`. Paginated; loop `page_no` until `len(collected) >= Table1[0].ROWCNT` (src/examples/get_all_announcements.py). `ATTACHMENTNAME` is a bare filename — the package does not build the attachment URL (BSE's convention is `https://www.bseindia.com/xml-data/corpfiling/AttachLive/<ATTACHMENTNAME>`; not in this code). Category constants: `bse.constants.CATEGORY` (constants.py:4). |
| `quote` (768) | `(scripcode) -> Dict[str, float]` | `GET /getScripHeaderData/w?scripcode=..` | `{PrevClose, Open, High, Low, LTP}` floats only (from `resp["Header"]`; the rest of Header is discarded) |
| `quoteWeeklyHL` (799) | `(scripcode) -> dict` | `GET /HighLow/w` | 52-week/monthly HL |
| `equityMetaInfo` (1015) | `(scripcode) -> dict` | `GET /ComHeadernew/w` | company header |
| `actions` (334) | corporate actions by scripcode/segment | `GET /DefaultData/w` | list |
| `resultCalendar` (419) | | `GET /Corpforthresults/w` | |
| `listSecurities` (831) | `(industry="", scripcode="", group="A", segment="Equity", status="Active") -> List[dict]` | `GET /ListofScripData/w` | list of `{SCRIP_CD, Scrip_Name, Status, GROUP, FACE_VALUE, ISIN_NUMBER, INDUSTRY, scrip_id (=symbol), Segment, NSURL, Issuer_Name, Mktcap}` — this is the bulk scrip-code <-> symbol table |
| `bhavcopyReport` (181) | `(date, folder=None) -> Path` | `https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{YYYYMMDD}_F_0000.CSV` | Path |
| `deliveryReport` (207) | | www.bseindia.com download | Path |
| gainers/losers/advanceDecline/near52WeekHighLow/circulars/resultsSnapshot/index history | see BSE.py:470-1274 | `/getDataAdvance_New/w`, `/MktRGainerLoserData/w`, `/advanceDecline/w`, `/MktHighLowData/w`, `/TabResults_PAR/w`, `/IndexArchDailyAll/w`, `/ProduceCSVForDate/w` | |

**Bulk deals: absent.** No method and no `BulkDeal`/`/BulkDeals/w` string anywhere in src/bse. **IPO / public issue: absent.** No method touches BSE's IPO pages (`/PublicIssue/`, `ipo` etc.). Both need hand-rolled requests; `bse.session` is a public attribute with the right headers, so `bse.session.get(f"{bse.api_url}/…")` is the least-friction route.

### 8. Scrip code <-> symbol mapping

Three routes, all in BSE.py:
- `lookup(text) -> Optional[dict]` (894): free-text search of company name / symbol / ISIN / code via `GET /PeerSmartSearch/w?Type=SS&text=..` (returns an HTML fragment, parsed by `SymbolParser`, BSE.py:1330-1371) -> `{company_name, symbol, isin, bse_code}` or `None`. Throttled at 15 rps under the "lookup" key.
- `getScripName(scripcode) -> str` (916): regex over the same HTML; `500180 -> "HDFCBANK"`; ValueError if not found.
- `getScripCode(scripname) -> str` (942): reverse; `"HDFCBANK" -> "500180"`; ValueError if not found.
- Bulk: `listSecurities(group="A"/"B"/…)` gives `SCRIP_CD` + `scrip_id` (symbol) + `ISIN_NUMBER` per row; iterate over `valid_groups` (BSE.py:40-65) for the full universe. The best cross-exchange join key is ISIN (NSE `announcements` gives `sm_isin`; NSE `listCurrentIPO` does not give ISIN).

### 9. Version / date / licence

bse 3.3.1, last commit 2026-08-19 (+0530), GPLv3. README/docs caveats: docs/source/index.rst:13 only says requests are throttled "without ... getting blocked". No cloud/server notes at all.

---

## Gotchas summary for a GitHub Actions collector

1. `pip install "nse[server]" bse` pins `httpx==0.28.1` (exact pin). bse pulls `requests`. Both pull `mthrottle`.
2. `NSE(...)` does a network GET in the constructor; wrap construction itself in try/except.
3. NSE errors are plain `ConnectionError` / `TimeoutError` with the status code only in the message; `httpx.ConnectError`/`ConnectTimeout` are NOT translated. Catch `(ConnectionError, TimeoutError, httpx.HTTPError, json.JSONDecodeError)`.
4. No retries in either library; add your own (with a fresh `NSE()` instance, since a RemoteProtocolError deletes the cookie file and a fresh instance re-bootstraps).
5. `nse.bulkdeals()` raises `RuntimeError` on "no deals", which is a normal outcome on quiet days — treat it as empty.
6. Never call `nse.exit()` if you want the cookie file to persist across steps in the same job.
7. BSE `announcements()` is paginated; `Table1[0].ROWCNT` is the total. Both date params default to "now", i.e. today.
8. BSE `quote()` throws away everything except 5 float fields; use `equityMetaInfo` or `bse.session.get` on `/getScripHeaderData/w` for the full header.
9. Neither package has FII/DII (nse) or bulk deals / IPO (bse).
10. Licence: both GPLv3 — fine for a collector script you run, but linking them into a distributed product has copyleft implications.

---

## Usage sketch

```python
import json, httpx
from datetime import datetime
from pathlib import Path
from nse import NSE          # src/nse/__init__.py -> nse.NSE.NSE
from bse import BSE          # src/bse/__init__.py -> bse.BSE.BSE

WORK = Path("./data"); WORK.mkdir(exist_ok=True)
NET_ERRS = (ConnectionError, TimeoutError, httpx.HTTPError, json.JSONDecodeError, RuntimeError)

try:
    nse = NSE(download_folder=WORK, server=True, timeout=20)   # HTTP/2 httpx; cookie GET happens here
    current_ipos = nse.listCurrentIPO()                          # -> list[dict], [] when none open
    bulk_csv = nse.download_document("https://nsearchives.nseindia.com/content/equities/bulk.csv")  # -> Path
except NET_ERRS as e:        # 403/421 arrive as ConnectionError("<url> 403: Forbidden")
    print("NSE failed:", repr(e)); current_ipos, bulk_csv = [], None
# do NOT call nse.exit() if you want data/nse_cookies_httpx.json kept for a later step

try:
    with BSE(download_folder=WORK) as bse:                       # no cookie priming; plain requests
        today = datetime.now()
        page = bse.announcements(scripcode="500325", from_date=today, to_date=today)
        ril_anns = page["Table"]                                  # ROWCNT = page["Table1"][0]["ROWCNT"]; loop page_no if > len
except (ConnectionError, TimeoutError, ValueError) as e:
    print("BSE failed:", repr(e)); ril_anns = []
```
