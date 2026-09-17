# Code-mining notes: IPO-Tracker (local clone at /home/claude/ref/IPO-Tracker)

Repo facts: ~39.6k lines of Python across `scripts/` (there is NO `ipo/` Python package;
`ipo/<slug>/index.html` are 1,365 generated company pages). Deps (pyproject.toml):
`requests`, `beautifulsoup4`, `pypdf`, `fonttools`; Python 3.12; `uv sync --frozen`.
Poppler `pdftotext` is installed on the runner for PDF text extraction.
The single canonical output is `data/ipos.json` (`{"meta": {...}, "ipos": [...]}`),
1,365 records, schema v5 (`docs/SCHEMA.md`).

Core file to read first: `scripts/update_data.py` (907 lines, all NSE/SEBI/BSE clients +
record normalisation). Live subscription: `scripts/track_subscriptions.py` +
`scripts/priority_subscriptions.py` + `scripts/run_priority_subscriptions_v3.py`.
Orchestrator: `scripts/run_pipeline.py`. Workflow: `.github/workflows/refresh.yml`.

Important operational reality visible in the committed data (`data/ipos.json` meta,
2026-09-17): on the GitHub runner, NSE `/api/ipo-current-issue` and
`/api/all-upcoming-issues` **worked** (`sourceHealth["NSE-live"] = {"ok": true, "records": 14}`),
but `/api/ipo-detail` (subscription) **failed on every open issue with
`403 Client Error: Forbidden for url: https://www.nseindia.com/`** — i.e. the *homepage
cookie prime* is what 403s, and `track_subscriptions.NSESubscriptionClient._prime` calls
`raise_for_status()` on it, so the whole NSE branch aborts. `update_data.NSEClient.get`
does NOT raise on the prime (line 456), which is why the list endpoints still work. The
proven alternative bootstrap is in `scripts/enrich_nse_issue_information.py:224-234`
(prime via `/market-data/issue-information?series=..&symbol=..&type=Past`, retry once on 401/403).

---------------------------------------------------------------------------------------

## 1. External endpoints, grouped by source

### 1a. NSE (www.nseindia.com) — JSON API

Common headers (`scripts/update_data.py:44-51`):
```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36
Accept: application/json,text/html,application/xhtml+xml,text/plain,*/*
Accept-Language: en-US,en;q=0.9
```
Bootstrap: `requests.Session()`; first call `GET https://www.nseindia.com` (timeout 20)
to set cookies, **without** raise_for_status (`update_data.py:454-457`). Then API calls with
timeout 25, `raise_for_status()`, `.json()`; list payload unwrapped from top-level list or
`data`/`records`/`result` keys (`update_data.py:458-466`).

| Endpoint | Params | Where | Notes |
|---|---|---|---|
| `GET /api/ipo-current-issue` | none | `update_data.py:468-469` | list of open issues |
| `GET /api/all-upcoming-issues` | `category=ipo` | `update_data.py:471-472` | upcoming issues |
| `GET /api/public-past-issues` | `from_date=DD-MM-YYYY&to_date=DD-MM-YYYY` | `update_data.py:474-481`; iterated in 90-day windows `history_ranges()` `update_data.py:737-742`, `time.sleep(0.2)` between windows `:794` | contains debt/NCD rows — filtered by `scripts/p4_history_guard.py` (patterns NCD/DEBT/BONDS/DEBENTURES/NON-CONVERTIBLE; `securityType`/`series` fields; debt-like symbol regex `^\d{3,4}[A-Z][A-Z0-9]{1,14}\d{2}$` at `:65`) |
| `GET /api/ipo-detail` | `symbol=SYM&series=EQ|SME` | `track_subscriptions.py:238-262`; extra header `Referer: https://www.nseindia.com/market-data/issue-information` (`:249`) | SME: tries series EQ then SME; accepts payload when `bidDetails` is a list |
| same `/api/ipo-detail` (lot / issue size) | same | `enrich_nse_issue_information.py:35-56, 216-238` | reads `issueInfo.dataList[]` `{title, value}` rows: `"Bid Lot"`, `"Minimum Order Quantity"`, `"Issue Size"` (narrative text, parsed to crore by `enrich_nse_issue_terms.py:84-113`, units regex `:37-41`); identity via `metaInfo.symbol`, `metaInfo.isDebtSec`, `companyName`/`metaInfo.companyName` (`:98-118`) |
| `GET /api/corporates/offerdocs` | `index=sme` and `index=equities` | `collect_nse_offer_filings.py:27-28, 182-215`; header `Referer: https://www.nseindia.com/companies-listing/corporate-filings-offer-documents`; plain `requests.get` (no session), timeout (10,25), 8 MiB cap, 45 s budget | Register rows read: `company`, `symbol`, `isin`, `issue_open_date`, `issue_close_date`, `fpAttach`/`fpDate` (final prospectus PDF), `rhpAttach`/`rhpDate`, `ipo_inlisting_xbrl_link` (`:65-69, 160-165, 239`) |
| final-listing XBRL (`nsearchives.nseindia.com/...xml`) | — | `collect_nse_offer_filings.py:76-93`; namespace `https://www.sebi.gov.in/xbrl/2022-03-31/in-capmkt` | tags: `MarketLot` (unitRef `shares`), `FinalIssuePrice` (unitRef `INRPerShare`), `DateOfIssueOpen`, `DateOfIssueClose`, `DateOfListing`, `ScripID`, `ISIN` (`:80-93, 99-113, 128-146`) |
| `GET /api/quote-equity` | `symbol=SYM` | `performance_tracking.py:48, 35-70` | reads `info.symbol`, `priceInfo.lastPrice`, `priceInfo.open`, `metadata.lastUpdateTime`. **Probe returned 403 on runner** (`docs/RELIABILITY_REVIEW.md:22`) |
| `https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv` | — | `collect_price_history.py:170` | daily bhavcopy (listing-day open/close) |
| `https://nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv` | — | `collect_price_history.py:171` | NIFTY 50 close for benchmark |
| `https://www.nseindia.com/static/regulations/segment-wise-historical-reports-capital-primary-market` | — | `enrich_nse_primary_market_reports.py:41, 226-240` | HTML index of monthly `primary_market*.xlsx`; column `Issue_Price` read at `:167` |

NSE list-record field names actually read (`update_data.py:289-350` + aliases in
`run_update.py:130-151`):
- company: `companyName`, `company`, `issuerName`, `name`
- symbol: `symbol`, `nseSymbol`, `securitySymbol`, alias `smSymbol`
- open: `issueStartDate`, `openDate`, `issueOpenDate`, `biddingStartDate`, aliases `ipoStartDate`, `startDate`
- close: `issueEndDate`, `closeDate`, `issueCloseDate`, `biddingEndDate`, aliases `ipoEndDate`, `endDate`
- listing: `listingDate`, `dateOfListing`; allotment: `allotmentDate`, `basisOfAllotmentDate`
- band: `minPrice`/`priceMin`/`lowerPrice`/`floorPrice`/`priceBandMin`, `maxPrice`/`priceMax`/`upperPrice`/`capPrice`/`priceBandMax`, else text `issuePrice`/`priceBand`/`priceRange` (`:169-183`)
- lot: `lotSize`, `marketLot`, `minimumBidQuantity`, `minBidQuantity`, aliases `bidLot`
- size: `issueSizeCr`/`issueSizeInCr`/`issueSizeRsCr`/`totalIssueSizeCr`/`issueSizeCrore`; raw `issueSize`/`totalIssueSize` is **shares** when >= 100,000 else crore (`:186-225`)
- shares: `noOfSharesOffered`, `sharesOffered`, `numberOfSharesOffered`, `totalSharesOffered`; `noOfsharesBid`, `sharesBid`
- subscription in list rows: `qib`, `nii`/`hni`, `retail`/`rii`, total `noOfTime`/`subscription`/`timesSubscribed` (`:279-286`)
- board: "SME" if the string `"SME"` or `"EMERGE"` appears anywhere in the row (`:305`) — crude but works
- status hint: `status`, `issueStatus`
- Date formats accepted (`:105-129`): `%d-%b-%Y`, `%d-%B-%Y`, `%d/%m/%Y`, `%d-%m-%Y`, `%Y-%m-%d`, `%d %b %Y`, `%d %B %Y`, `%b %d, %Y`, `%B %d, %Y`

`/api/ipo-detail` subscription payload (`track_subscriptions.py:103-138`, fixture
`tests/test_subscription_tracking.py:18-23`): `bidDetails: [{category, noOfTime}, ...]`;
category keys tried: `category`/`categoryName`/`investorCategory`/`bidCategory` +
`categoryCode`/`code`/`caCode`; value keys: `noOfTime`/`subscription`/`timesSubscribed`/
`subscriptionTimes`; root-level `noOfTime` used as total fallback. Category classifier
`_classify_category` (`:56-100`): "total"→total; "qualified institutional"/"qib"→qib;
"retail"/"rii"→retail; "individual investor" (NSE's new SME label)→retail; "non institutional"/
"nii"/"nib"→nii **unless** it is a sub-bucket ("bid amount", "above/below", "10 lakh", "2 lakh",
"snii/bnii", "small/big nii") — sub-buckets are deliberately dropped.

Other NSE API paths discovered from NSE's own JS bundle but not used (`docs/NSE_ISSUE_INFO_PROBE.txt:31-38`):
`/api/ipo-active-category?symbol=`, `/api/ipo-bid-details?symbol=`, `/api/ipo-chart-demand?symbol=`,
`/api/ipo-detail-rights?symbol=`, `/api/download-drhp-file?drhpFileURL=`. Probe also shows
`HOME status=403` while the issue-information HTML page returned 200 (`:1-2`).

### 1b. BSE (www.bseindia.com / beta.bseindia.com / www.bsesme.com) — HTML scraping

Session headers = the NSE HEADERS + `Referer: https://www.bseindia.com/` (`update_data.py:533-537`).
Timeout 30. No cookie prime needed.

| URL | Where | What is parsed |
|---|---|---|
| `https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p` then fallback `https://beta.bseindia.com/...same` | `update_data.py:38-42, 618-632`; `run_update_v2.py:157-180` aggregates all hosts | current/forthcoming public issues table. Parser `run_update.py:184-249`: `tr.find_all(["th","td"], recursive=False)` (recursive=False is essential, comment `:190-192`), needs >= 8 cells; fixed columns `cells[0]`=Security Name, `[1]`=Platform (contains "SME"), `[2]`=Start Date, `[3]`=End Date, `[4]`=Offer Price, `[6]`=Type of Issue (must be `IPO`), `[7]`=Issue Status |
| `https://www.bsesme.com/PublicIssues/PublicIssues.aspx?id=2` | `run_update_v2.py:27, 42-154` (header-name based parser, fails closed) | SME current issues; headers matched by alias (`Security Name`, `Start Date`, `End Date`, `Offer Price`, `Lot Size`, `Type of Issue`, `Issue Status`, `Listing Date`). **Timed out from the runner on 2026-09-17** (`meta.subscriptionHealth.pageHealth`) |
| `https://www.bsesme.com/PublicIssues/SMEIPODRHP.aspx` | `critical_backfill.py:48` | SME DRHP document list |
| `.../PublicIssues/IPOIssues_new.aspx?id=2&Type=P` (both hosts) | `enrich_exchange_details.py:38`, `backfill_bse_history.py:35-38` | historical archive; ASP.NET WebForms postback needed (`history_form_payload` `:48-80`: copies hidden inputs, sets `ddlIssueType` select). **Returned 403 / "did not contain its ASP.NET form" on runner** (`sourceHealth["BSE-history-detail"]`, `RELIABILITY_REVIEW.md:22`) |
| `DisplayIPO.aspx?...&IPONo=NNN` (links found in the list page rows) | `track_subscriptions.py:287-303`, `enrich_exchange_details.py:62-160` | label/value table: `Symbol`, `Issue Period`, `Price Band`/`Issue Price`/`Offer Price`, `Market Lot`, `Minimum Bid Quantity`, `Issue Size – No. of Shares`, `Book Running Lead Manager(s)`, `Registrar`, plus official `/downloads/ipo/*.pdf` "Prospectus & GID" links |
| `CummDemandSchedule.aspx?ID=<IPONo>&status=L` (constructed from IPONo, `track_subscriptions.py:306-321`) or discovered as a real link on the list row / DisplayIPO page (`priority_subscriptions.py:123-157`); tried on both `www.` and `beta.` hosts (`:110-120`) | subscription fallback | table rows: category text in first two cells, multiple = last numeric cell (`track_subscriptions.py:141-164`); same classifier as NSE. Observed live URLs in data: `https://beta.bseindia.com/markets/publicIssues/CummDemandSchedule.aspx?ID=7973&status=L` (works) and `...?ID=7967&status=H` (returned an empty page for some SME issues → "BSE's 2026 public-site migration currently returns an empty legacy cumulative-demand table for several live SME IPOs", `run_priority_subscriptions_v3.py:11-14`) |
| `https://www.bseindia.com/downloads/ipo/*.pdf` | `run_offer_documents.py:43-45, 100-121` | official BSE prospectus PDFs; download needs the session bootstrapped via `https://www.bseindia.com/` and the IPO list page with `Referer` set to the list page |
| Probed only, never wired (`.github/workflows/probe-p4-bse-modern.yml:100-116`, `probe-phase45a-bse-isd.yml:44-70`) | — | modern Angular API guesses `https://api.bseindia.com/BseIndiaAPI/api/IPO_HomePageDetail/w`, `.../IssueSummary/w`, `.../IPOProcessStatus/w`, `.../PublicIssue/w` with `Origin: https://www.bseindia.com` + `Referer: https://www.bseindia.com/markets/PublicIssues/Issuesummary.aspx`; param shapes tried `?id=<scrip>&IPONo=<n>` etc. No result recorded in repo |

### 1c. SEBI (www.sebi.gov.in) — HTML scraping, no bootstrap, plain session with the same HEADERS

| URL | Where | Parsed |
|---|---|---|
| `https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&sid=3&smid=0&ssid=0` + `&page=N` (N=1..`--sebi-pages`, default 6, pipeline uses 4), `time.sleep(0.15)` between pages | `update_data.py:31-35, 489-530` | every `a[href]` whose text contains DRHP/RHP/PROSPECTUS/RED HERRING; type inferred UDRHP > DRHP > RHP > PROSPECTUS; company = title with the doc-type suffix stripped; `filedDate` = first parseable date in the parent element's text; dedupe on `(url,type)` |
| `https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&smid=11&ssid=15` (RHP register) and `...smid=12&ssid=15` (Prospectus register) | `enrich_sebi_priority_registers.py:44-46, 78-116` | `table tbody tr` rows; anchor `a[href*="/filings/public-issues/"]`; `td[0]` = filed date (`%b %d, %Y`); skips ADDENDUM/CORRIGENDUM/PUBLIC ANNOUNCEMENT/ADVERTISEMENT |
| `https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=<company name>` | `enrich_sebi_priority_registers_v2.py:39, 170` | per-issuer GET search; same row parser (`:57-79`) |
| `https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&smid=78&ssid=15` + `&page=N` | `backfill_recent_sebi_other_docs_lot_sizes.py:39-42, 104` | "Other Documents" register (price band / bid lot ads) |
| Filing landing page `https://www.sebi.gov.in/filings/public-issues/<mon-yyyy>/<slug>_<id>.html` | `enrich_sebi_document_links.py:86-192` | direct PDFs: anchors ending `.pdf` on a sebi.gov.in host, OR the viewer `https://www.sebi.gov.in/web/?file=<encoded pdf url>` (`file` query param unquoted, `:86-101`); regex fallbacks over the raw HTML (`:170-175`). Abridged Prospectus detected by title "ABRIDGED PROSPECTUS" or filename `*AP_p.pdf` (`:121-128`). Real examples in data: full RHP `https://www.sebi.gov.in/sebi_data/attachdocs/sep-2026/1789012955772.pdf`; abridged `https://www.sebi.gov.in/sebi_data/commondocs/sep-2026/Sonaselection%20India%20Limited%20%20-%20AP_p.pdf` |

### 1d. Aggregators (explicitly "secondary", used only after NSE and BSE fail)

`scripts/run_priority_subscriptions_v3.py:43-48, 362-401`; each client is a plain
`requests.Session` with HEADERS + a site Referer, timeout 30, table parsed only when
all category column headers are present by name (fails closed, `:88-167`):
- `https://www.ipopremium.in/view/subscription` (Referer `https://www.ipopremium.in/`) — card layout; heading ends with `(BSE SME)|(NSE SME)|(Mainboard)`; a `Last updated on DD-Mon-YYYY HH:MM:SS` line gives `observedAt` (`:198-210`); rows `Category | Offered | Applied | Times` with labels QIBs/HNIs/Retail/Individual/Total (`:213-298`). **This was the only source that worked for 3 SME issues on 2026-09-17.**
- `https://groww.in/ipo/subscription` (Referer `https://groww.in/ipo`) — headers `Company`, `QIB`, `NII`/`NII/HNI`, `Retail`/`RII`, `Total` (`:170-179`). Returned "no parseable table rows" on 2026-09-17 (JS-rendered).
- `https://ipodhamaka.in/subscription/` (Referer `https://ipodhamaka.in/`) — headers `IPO`/`Company`, `QIB (X)`, `NII (X)`, `Retail (X)`, `Total (X)`; sHNI/bHNI columns ignored (`:182-195`).
- Company-name matching to the secondary row: exact canonical key, then containment, then `SequenceMatcher >= 0.72` (`:301-321`).

### 1e. Issuer / registrar hosted PDFs
`scripts/issuer_offer_registry.py` — hand-verified dict of issuer-website / registrar
(`ipostatus.integratedregistry.in`) Final Prospectus URLs with exact host pinning;
`scripts/enrich_issuer_offer_docs.py:54-74` similar. Useful pattern (registry as data),
not reusable content.

---------------------------------------------------------------------------------------

## 2. HTTP layer

- Library: `requests` only. No HTTP/2, no `httpx`, no `curl_cffi`, no browser. Probe
  workflows use `curl --http1.1` explicitly (`probe-p4-bse-modern.yml:21, 44`).
- Session build: `requests.Session(); s.headers.update(HEADERS)` (`update_data.py:448-452`).
  UA is a fixed desktop-Chrome string (`:44-51`). BSE adds `Referer: https://www.bseindia.com/`.
- No `urllib3.Retry`/HTTPAdapter anywhere. Retries are ad-hoc:
  - NSE `ipo-detail`: refetch the issue-information page and retry the API **once** on 401/403
    (`enrich_nse_issue_information.py:229-233`); a 401/403/429 marks the client `blocked_error`
    and the loop stops early (`backfill_recent_nse_lot_sizes.py:264-268, 313-316`).
  - NSE subscription prime: cache the first prime exception and re-raise for every later symbol
    instead of hammering the WAF (`track_subscriptions.py:225-236`).
  - PDF download: 3 attempts, total 180 s budget, exponential sleep `min(0.5*2**(n-1), 2.0)`,
    only on connection/timeout/chunked/invalid-PDF errors (`run_offer_documents.py:39-42, 190-206`);
    legacy: 3 attempts with linear `retry_delay*attempt` (`legacy_offer_parser.py:833-843`).
  - bhavcopy: break loop on 401/403/429 (`collect_price_history.py:193-196`).
- Timeouts: 20 s prime, 25 s NSE API, 30 s SEBI/BSE HTML, `(15,30)` streamed PDFs,
  `(10,25)` NSE feeds, `(5,10)` BSE bootstrap.
- Throttling: `time.sleep(0.2)` between NSE history windows, `0.15` between SEBI pages,
  `0.08-0.15` between NSE ipo-detail calls (`enrich_nse_issue_information.py:246`).
- Cloud-IP handling = **fallback chains, not evasion**: NSE → BSE cumulative demand →
  ipopremium → groww → ipodhamaka (`run_priority_subscriptions_v3.py:4-14, 457-519`), with
  the source name and `kind: "secondary-market-data"` recorded on the record (`:404-408`).
  Pipeline classifies a stage as `source_blocked` if its log matches
  `403|Forbidden|ConnectTimeout|ConnectionError|source_blocked|"failed": N` (`run_pipeline.py:83-84`).
- Bounded downloads: streamed `iter_content(131072)`, 40 MiB PDF cap, `%PDF` magic check,
  pypdf page-tree validation before caching, atomic temp-file rename into
  `.cache/offer-documents/<sha256(url)>.pdf` (`run_offer_documents.py:73-165`).
- Whole-dataset safety: if no source fetched anything, the existing JSON is preserved and
  exit code 2 (`update_data.py:848-852`); each pipeline stage restores the previous bytes if
  the stage leaves invalid JSON (`run_pipeline.py:69-82`).

---------------------------------------------------------------------------------------

## 3. Data model (`data/ipos.json`)

Top level: `{"meta": {...}, "ipos": [record, ...]}`; records sorted by
`openDate || listingDate || lifecycle.stageDate` desc (`update_data.py:873-883`).
`meta` (`:884-896`): `schemaVersion`, `generatedAt` (IST ISO), `timezone: "Asia/Kolkata"`,
`sources`, `recordCount`, `historyStart`, `sourceHealth{<source>: {ok, records, error…}}`,
`errors[]`, plus `subscriptionHealth`, `pipelineStages{script: {status, exitCode,
durationSeconds, checkedAt, diagnostics}}`, `publication{runId, collectorCommit, status,
pendingConflictCount}`.

Record core (`update_data.py:311-350`; example `docs/SCHEMA.md:5-68`):
```
id                 slug of symbol-or-company (+ "-withdrawn-<date>" suffix, record_integrity.py:13-19)
matchKey           canonical_company(company): upper, "&"→AND, strip LIMITED/LTD/PVT/... and doc-type words, non-alnum removed (update_data.py:62-75)
symbol, company, board ("Mainboard"|"SME"), exchange ("NSE"|"NSE Emerge"|"BSE"|"BSE SME")
status             "upcoming"|"open"|"closed"|"listed"  (derive_status, :249-267, from dates vs today-IST, then text hint)
openDate, closeDate, allotmentDate, listingDate     ISO YYYY-MM-DD or null
priceBand          {"min": float, "max": float} | null
lotSize            int | null   (+ marketLot, minimumBidQuantity, minInvestment, faceValue when known)
issueSizeCr, freshIssueCr, ofsCr   float crore | null
sharesOffered, sharesBid           int | null
subscription       {"qib","nii","retail","total"} floats (multiples) | null
listing            {"issuePrice", "listPrice", "gainPct", "issuePriceEvidence"{...}, "sourceUrl", "asOf", "basis"} | null
lifecycle          {"stage": "drhp|udrhp|rhp|prospectus|exchange", "stageDate", "candidate": bool}
documents[]        {"type": "DRHP|UDRHP|RHP|PROSPECTUS|ABRIDGED|ADDENDUM", "title", "url", "filedDate", "source": "SEBI|NSE|BSE", "sourcePage"}
sources[]          {"name", "kind": "exchange|regulator|secondary-market-data", "url", "asOf"}   (source = sources[0], legacy)
observations       {"NSE": {openDate, closeDate, priceBand, lotSize, issueSizeCr, staticOfferTerms{}}, "BSE": {...}, "SEBI": {stage, filedDate, documentCount}}
validation         {"status": "verified|single-source|conflict", "checkedAt", "checks": [{field, nse, bse, match}], "independentSources": []}
```
Merge rules: NSE values win and are re-normalised each run (`merge_non_null`, `:364-369`);
BSE is fill-only for the protected fields company/openDate/closeDate/listingDate/priceBand/
lotSize/issueSizeCr (`attach_bse`, `:702-727`); conflicts flagged in `validation.checks`
(`field_equal` tolerances: band ±0.01, size ±max(0.05, 0.5%), `:394-409`). Fuzzy record
matching: `SequenceMatcher` on matchKey with threshold 0.88 (`best_match`, `:382-391`).

Subscription (`track_subscriptions.py:436-467`):
```
subscription          {qib, nii, retail, total}  (partial updates keep old non-null keys)
subscriptionAsOf      == subscriptionCollectedAt   IST ISO seconds
subscriptionObservedAt  source's own timestamp or null
subscriptionTimeBasis "source-observation" | "collection-only"
subscriptionSource    "NSE subscription detail" | "BSE cumulative demand" | "<aggregator> subscription (secondary)"
subscriptionHistory[] {capturedAt, observedAt, source, sourceUrl, qib, nii, retail, total}
```
History append rule (`append_snapshot`, `:178-187`): sort by `capturedAt`; append only if any
of the four values changed vs the last row (`_same_values`, `:167-175`, tolerance 1e-9) or
`--force-snapshot`; cap `MAX_HISTORY = 500`. Live example: `data/ipos.json` record `sona`
has 3 snapshots on one day from BSE cumulative demand.

Offer-document fields (Phase 3, `README.md:109-122`; example record `sona`):
`issueComposition{freshShares, ofsShares, freshIssueCr?, ofsCr}`, `leadManagers[]`,
`registrar`, `promoters[]`, `objectsOfIssue[{purpose, amountCr}]`, `financials{unit:"₹ crore",
periods[{period:"FY2026", revenueCr, totalIncomeCr, ebitdaCr, patCr, netWorthCr, ronwPct, roePct,
eps, dilutedEps}]}`, `shareholding{promoters[{name, preIssueShares, preIssuePct}],
promoterPreIssuePct}`, `offerDocumentExtraction{status, parserVersion, documentUrl,
documentType, documentTitle, source, sha256, pagesRead, pageCount, extractedFields[],
extractedAt, conflicts[], sourcePolicy}`, `staticFieldProvenance{<field>: {source, sourceUrl,
documentType, sha256, parserVersion, checkedAt, field, value, evidence{page, heading, rows…}}}`,
`dataCorrections[{field, before, after, reason, parserVersion, sourceUrl, sha256, correctedAt}]`.

Atomic field groups used when merging concurrent runs (`publish_transaction.py:20-35`):
`documentFields`, `subscriptionSnapshot` (subscription, subscriptionSource, subscriptionSourceUrl,
subscriptionAsOf, subscriptionCollectedAt, subscriptionObservedAt, subscriptionTimeBasis,
subscriptionDegraded), `priceSnapshot` (listing, performance, listingDate, listingDateEvidence),
`lotTerms` (lotSize, marketLot, minimumBidQuantity, lotSizeEvidence).

---------------------------------------------------------------------------------------

## 4. PDF layer

- Libraries: `pypdf` (`PdfReader`, container/page-tree validation, decrypt("")) + Poppler
  `pdftotext -layout -fixed 3 -enc UTF-8 -f 1 -l N - -` via subprocess, stdin→stdout, 120 s
  timeout, page cap 520; output split on form-feed and prefixed `[PAGE n]`
  (`offer_parser.py:372-388`). Raises if `pdftotext` is missing. The original v1 used
  `pypdf.page.extract_text()` on the first 30 pages (`enrich_offer_docs.py:481-495`) —
  abandoned because column alignment was lost.
- Locating the document (`legacy_offer_parser.py:806-830` `choose_document`): from
  `record.documents`, skip ADDENDUM/CORRIGENDUM; prefer SEBI-hosted `.pdf`; rank by
  `(abridged, type rank PROSPECTUS=4>RHP=3>UDRHP=2>DRHP=1, filedDate, title length)` — i.e.
  **Abridged Prospectus first** because it is 8-20 pages and repeats the key disclosures
  (`enrich_offer_docs.py:4-7`, `README.md:71`). Current policy (`final_prospectus_policy.py`,
  `run_offer_documents.py:1-10, 57-59`) only lets a *final* PROSPECTUS populate canonical
  static fields; RHP/DRHP are history. Discovery of the PDF URL itself is via the SEBI
  landing page (`enrich_sebi_document_links.extract_pdf_links`) or NSE `fpAttach`.
- Identity gate before trusting a PDF: canonical company name must appear in the first
  25,000 chars, or the cover page issuer must not contradict (`run_offer_documents.py:209-220`,
  `final_prospectus_identity.py`). Real failure in data: `"Final Prospectus cover issuer
  'KABRA JEWLS LIMITED' contradicts expected issuer 'Kabra Jewels Limited'"`.
- What it extracts and how (all regex over the layout text):
  - Lead managers / registrar: heading regexes `_ROLE`, `_REGISTRAR` (`offer_parser.py:44-45`)
    + entity validators `valid_manager`/`valid_registrar` (`:55-60`).
  - Financials: only rows under a recognised heading (`_HEADING` `:34`) with a period header
    (`_YEAR` `:35`), metric regexes `_METRICS` (`:23-33`), unit detection `_UNIT` (`:37`) with
    factors million=0.1, lakh=0.01, thousand=0.0001 → crore (`:63-68`).
  - Promoters: "OUR PROMOTERS" heading list (`final_prospectus_parser.py:105-131, 272-318`).
  - Bid lot: `_LOT_PATTERNS` (`:64-92`); price band / floor-cap (`:37-63`); fixed offer
    price (`:24-36`, `extract_final_issue_price` `:400`).
  - Issue composition (fresh/OFS shares & amounts, cross-checked against total)
    `extract_final_issue_composition` (`:655-805`); objects of issue table
    `p4_offer_parser.extract_objects` with unit + page evidence; pre-issue promoter
    shareholding (`:349-398`).
  - Only the first 20 pages / 100k chars are used for promoters/objects/shareholding/lot/band
    (`offer_parser.py:361`).
- Versioning & hashing: `PARSER_VERSION` chain: `enrich_offer_docs`=1 → `legacy_offer_parser`=14
  → `offer_parser`=22 → `final_prospectus_parser`=22+9=31 (`final_prospectus_parser.py:21`).
  Each record stores `offerDocumentExtraction.parserVersion` + `sha256` of the PDF bytes
  (`run_offer_documents.py:237-252`); re-parse is skipped when both match and no newer
  document exists (`README.md:71`). Cache key = sha256(url) (`:167`). Test fixtures of
  pdftotext output live in `tests/fixtures/{financials,issue_composition,objects_of_issue}/`.

---------------------------------------------------------------------------------------

## 5. SEBI discovery of new filings

1. Every core run: `SEBIClient.fetch_recent_filings(max_pages=4)` on the "all public issues"
   listing (`update_data.py:489-530`), i.e. `HomeAction.do?doListingAll=yes&sid=3&smid=0&ssid=0&page=N`.
   Results are attached to existing NSE/BSE records by canonical name (fuzzy 0.88) or create a
   new **candidate** record with `lifecycle.candidate: true`, `status: "upcoming"`, no dates
   (`attach_sebi`, `:635-699`). Latest doc type sets `lifecycle.stage` (rank drhp<udrhp<rhp<prospectus).
2. Filing landing page → direct PDF resolution (`enrich_sebi_document_links.py`, bounded by
   `--limit`, attempt stamp `sebiDocumentLinkResolution` for rotation).
3. For records still missing a final prospectus: the dedicated RHP (`smid=11`) / Prospectus
   (`smid=12`) registers first page, then per-company GET search `?doListingAll=yes&search=<name>`
   (`enrich_sebi_priority_registers_v2.py:155-186`); match = exact canonical key, else
   `SequenceMatcher >= 0.93`, and filedDate within 60 days of openDate (`enrich_sebi_priority_registers.py:118-140`).
4. NSE's own offer-docs register (`/api/corporates/offerdocs?index=sme|equities`) provides
   `fpAttach`/`rhpAttach` PDFs on nsearchives (`collect_nse_offer_filings.py:155-178`), windowed:
   RHP filed within 60 days before open, Prospectus within 30 days after close.
5. SEBI "Other Documents" (`smid=78`) for price-band / bid-lot advertisements (lot backfill).

---------------------------------------------------------------------------------------

## 6. GitHub Actions workflow (`.github/workflows/refresh.yml`)

- Triggers (`:3-18`): `workflow_dispatch` with `mode` choice; `push` to main on `scripts/**`,
  the workflow, `data/verified_corrections.json`, `uv.lock`; four crons:
  `17 * * * *` (hourly → mode `core`), `0,30 4-12 * * 1-5` (twice-hourly on weekdays 04:00-12:59
  UTC = 09:30-18:29 IST → `subscriptions`), `43 13 * * *` (daily → `maintenance`),
  `31 */6 * * *` (→ `filings`). Mode resolved from `github.event.schedule` string (`:40-64`).
- Concurrency: push runs cancel superseded pushes; scheduled runs are independent (`:27-29`).
- Job `collect` (`permissions: contents: read`, 75 min, `:32-117`): checkout →
  `astral-sh/setup-uv` → `uv python install 3.12` → `uv sync --frozen` → conditional
  `apt-get install poppler-utils` (not for `subscriptions`) → **run full unittest suite first**
  → save `data/ipos.json` as `base.json` + `git rev-parse HEAD` → `run_pipeline.py --mode $MODE`
  (60-min internal budget, later stages `deferred`) → optional repair scripts → copy result
  as `proposed.json` → `upload-artifact` (14-day retention).
- Job `publish` (`needs: collect`, only on `main`, `permissions: contents: write, pages: write`,
  serialized `concurrency: group: ipo-publication, cancel-in-progress: false`, `:119-178`):
  download artifact → loop 3 attempts { `git fetch && git reset --hard origin/main`;
  `publish_transaction.py --base base.json --proposed proposed.json --run-id --source-commit-file`
  (three-way merge vs current main, refuses if collector commit != current main, conflicts go
  to `data/pending_updates.json`); re-run validation/derived builders; `git add data/ ipo/
  docs/DATA_QUALITY.md`; exit 0 if nothing staged; commit as `ipo-tracker-bot`
  (`41898282+github-actions[bot]@users.noreply.github.com`) `'data: publish validated IPO
  collection'`; `git push origin HEAD:main` } → `gh api --method POST repos/$REPO/pages/builds`.
- No `continue-on-error` in refresh.yml; failure isolation is inside `run_pipeline.step()`
  (subprocess per script, timeout, outcome recorded in `meta.pipelineStages`). Probe workflows
  use `continue-on-error: true` on curl steps (`probe-p4-bse-modern.yml:102`).
- Other workflows: `validate.yml` (tests + JS syntax on PR/push), `source-review.yml`
  (read-only parser preview, uploads artifact), several `probe-*.yml` diagnostics.
- `.gitignore` excludes `.cache/` (PDF cache is not committed; it is rebuilt per run) and,
  oddly, lists the data JSON basenames — but `data/*.json` are force-tracked and committed.

---------------------------------------------------------------------------------------

## 7. Documented blocks, broken endpoints, fallbacks

- NSE Akamai WAF: homepage `https://www.nseindia.com/` returns 403 from GitHub runners
  (`docs/NSE_ISSUE_INFO_PROBE.txt:1`; live error strings in `meta.subscriptionHealth.errors`).
  `/api/ipo-current-issue` and `/api/all-upcoming-issues` still succeed when the prime error is
  ignored. `/api/ipo-detail` succeeded historically when primed via the issue-information page
  (`enrich_nse_issue_information.py:224-226` comment) but the subscription client still primes
  via homepage and therefore fell back to BSE on 2026-09-17 (`nseRecords: 0, bseFallbackRecords: 5`).
- NSE `/api/quote-equity` returned 403 on the runner (`docs/RELIABILITY_REVIEW.md:22`).
- BSE: `www.bseindia.com` IPOIssues_new page returns **0 rows** (new Angular site), `beta.bseindia.com`
  still serves the legacy table (`meta.sourceHealth["BSE"].indexHealth`; pipeline log
  `"BSE current source https://www.bseindia.com/...: 0 IPO rows"`, `"beta...: 10 IPO rows"`).
  Historical archive (`id=2`) returned 403 on both hosts (`RELIABILITY_REVIEW.md:22`).
  Cumulative demand `status=H` pages come back empty for some SME issues (`run_priority_subscriptions_v3.py:11-14`).
- `www.bsesme.com` connect-timeout from the runner (`meta.subscriptionHealth.pageHealth`).
- Groww subscription page parsed to zero rows (JS-rendered) on 2026-09-17; ipopremium worked.
- `README.md:105-107`: endpoints are "public website data endpoints rather than a guaranteed
  commercial API"; `README.md:158`: GMP deliberately excluded (only as future "unofficial" source).
- NSE list field names drift between live/upcoming/past (`run_update.py:124-151`), and
  `/public-past-issues` mixes in NCD/debt issues (`p4_history_guard.py:1-12`).

---------------------------------------------------------------------------------------

## 8. Licence and history

- **No licence file** (`LICENSE*`/`COPYING*` absent; README/pyproject do not mention one).
  Treat as all-rights-reserved; reuse patterns/endpoint knowledge, do not copy code verbatim.
- Git history is a **single squashed commit**: `31a1e79a` 2026-09-17 13:35:04 +0000
  "data: publish validated IPO collection" (bot). Docs reference 14 Sep 2026 work
  (`docs/RELIABILITY_REVIEW.md:1`). Data generated 2026-09-17T19:05 IST.

---------------------------------------------------------------------------------------

## What to copy (concrete, with paths)

1. **NSE client + record normaliser** — `scripts/update_data.py:44-51` (headers), `:448-481`
   (session, prime-without-raise, 3 list endpoints, 90-day past-issue windows), `:78-183`
   (`first`, `number`, `iso_date` formats, `price_band`), `:186-225` (shares-vs-crore
   disambiguation), `:249-267` (`derive_status`), `:289-350` (record shape) plus the alias table
   `scripts/run_update.py:130-151` and the debt filter `scripts/p4_history_guard.py:20-30, 65, 99`.
   Change one thing: prime via `/market-data/issue-information?series=EQ&symbol=X&type=Past`
   with `Referer: https://www.nseindia.com/` and retry once on 401/403
   (`scripts/enrich_nse_issue_information.py:216-238`) instead of the homepage.

2. **Subscription capture with timestamped history** — `scripts/track_subscriptions.py:36-37`
   (keys, 500 cap), `:56-138` (category classifier + `bidDetails` parser incl. NII sub-bucket
   rejection and SME "Individual Investor"), `:167-187` (change-only `append_snapshot`),
   `:436-467` (`apply_subscription` field set). Also lift `issueInfo.dataList` lot parsing
   (`enrich_nse_issue_information.py:60-93`) and the `Issue Size` narrative → fresh/OFS crore
   parser (`enrich_nse_issue_terms.py:37-113`) since they come from the same `/api/ipo-detail` call.

3. **BSE fallback for live subscription** — list page on `beta.bseindia.com` (not `www`), row
   parser `scripts/run_update.py:184-249` (recursive=False, fixed columns, `Type of Issue == IPO`),
   `DisplayIPO.aspx?IPONo=` → `CummDemandSchedule.aspx?ID=<IPONo>&status=L` construction
   (`track_subscriptions.py:265-321`), host alternation `priority_subscriptions.py:110-120`,
   demand table parser `track_subscriptions.py:141-164`. Then the ipopremium card parser
   (`run_priority_subscriptions_v3.py:198-298`) as last resort, labelled secondary.

4. **SEBI discovery + PDF link resolution** — listing scrape `update_data.py:484-530`
   (`doListingAll=yes&sid=3&smid=0&ssid=0&page=N`), register/search row parser
   `enrich_sebi_priority_registers.py:78-116` and `_v2.py:57-79, 170`, landing page →
   direct PDF via `/web/?file=` unquoting and `AP_p.pdf` abridged detection
   (`enrich_sebi_document_links.py:86-192`), and `canonical_company` (`update_data.py:62-75`)
   for name matching across all three sources.

5. **Bounded PDF fetch + pdftotext extraction + provenance** — `run_offer_documents.py:39-42,
   73-206` (stream, 40 MiB cap, `%PDF` magic, pypdf validation, atomic cache by sha256(url),
   3 attempts / 180 s), `offer_parser.py:372-388` (`pdftotext -layout -fixed 3`, `[PAGE n]`
   markers), heading/metric/unit regexes `offer_parser.py:23-45, 63-68`, and the
   `offerDocumentExtraction{parserVersion, sha256, pagesRead, pageCount, extractedFields}`
   stamp (`run_offer_documents.py:237-252`) so re-parsing is skipped when version+hash match.

6. (Workflow) Copy the shape of `refresh.yml`: mode-from-cron-string resolution (`:40-64`),
   tests before collection, `poppler-utils` install only when parsing, collect job with
   read-only token → artifact → separate serialized publish job that `git reset --hard
   origin/main`, merges, commits as the bot and retries push 3 times (`:142-174`).
