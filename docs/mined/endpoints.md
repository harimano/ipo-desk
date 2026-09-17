# Endpoint catalogue — mined from ipowatch-co and IPOFetch (local files only)

Mined 2026-09-17 from:
- `/home/claude/ref/ipowatch-co` — `ipo_portal/`, `scripts/`, `docs/`, `HANDOFF.md`, `README.md`
- `/home/claude/ref/IPOFetch` — `scraper/`, `README.md`

Shorthand for the "serves" column: CAL = IPO calendar/status, SUB = subscription, GMP, LIST = listing/current price,
ANCH = anchor list, DOCS = DRHP/RHP/prospectus, OFS/RTS = OFS & rights, FIIDII, BULK = bulk/block, NEWS, PARENT = parent/peer price.
Things neither repo has: **FII/DII, bulk/block deals, bhavcopy, security master, corporate announcements, an NSE basis-of-allotment API, a
structured anchor-allocation API, news** (grep of both repos: only `BasisAllot_ID` in BSE `ipo_documents`, `Anchor_Details` in BSE issue
detail (usually empty), and RHP-PDF anchor extraction in `ipo_portal/orchestrator/rhp_enrich.py:7`).

---

## 1. Session / header conventions (shared by everything below)

| Source | Session bootstrap | Headers | Ref |
|---|---|---|---|
| NSE | GET `https://www.nseindia.com/market-data/all-upcoming-issues-ipo` once per session with `Referer: https://www.nseindia.com/` to seed Akamai cookies; then reuse `requests.Session` | UA `Mozilla/5.0 (X11; Linux x86_64) ... Chrome/124.0`, `Accept: application/json,text/plain,*/*`, `Accept-Language: en-US,en;q=0.9`, per-endpoint `Referer` (page that hosts that API) | `ipo_portal/http.py:11-45`, `ipo_portal/sources.py:10-14,126-135`; IPOFetch `scraper/nse.py:14-38` |
| BSE | none — no cookies | `Referer: https://www.bseindia.com/publicissue` (ipowatch) or `https://www.bseindia.com/` (IPOFetch); UA; `Accept: application/json` | `sources.py:15,81`, `backfill_detail.py:36-52`; IPOFetch `scraper/bse.py:1-24` |
| InvestorGain | none | UA, `Accept: application/json`, `Referer: https://www.investorgain.com/report/live-ipo-gmp/331/ipo/`, `Origin: https://www.investorgain.com` | IPOFetch `scraper/gmp.py:22-48` |
| Moneycontrol | none | `Origin: https://www.moneycontrol.com`, `Referer: https://www.moneycontrol.com/ipo/listed-ipos/` | `moneycontrol.py:568-577` |
| Trendlyne | none | `Referer: https://trendlyne.com/ipo/dashboard/`, `X-Requested-With: XMLHttpRequest` | `trendlyne.py:632-640` |
| CapitalMarket | ASP.NET `__VIEWSTATE` postback paging (GET page 1, then POST hidden fields + `__EVENTTARGET`) | `Accept: text/html`, Referer = table page | `capitalmarket.py:17-21,52-75,111-142` |
| PRIME | none; public demo pages only (paywalled data) | `Referer: https://primedatabase.com/default.asp` | `prime.py:260-261,300-315` |
| SEBI | none | UA; throttle 0.6 s | `sebi.py:43-79` |
| Tijori (b2b) | none; plain GET, no auth in code | `Accept: application/json`, custom UA | `tijori.py:13-36` |
| IndiaDataHub | API key `INDIA_DATAHUB_API_KEY` as query param | — | `datahub.py:6-22` |
| Yahoo | none | custom UA | `yahoo_v2.py:31,124-131,209-213` |
| Kite | full Zerodha login (api key/secret/TOTP); local only, never in CI | — | `kite.py:27-28`, `kite_auth.py:45-46`, `docs/KITE.md:28` |

Retry policy (ipowatch): 2 retries, exponential backoff 1s·2^n, retry only on timeout/conn-error/408/425/429; other 4xx raise immediately (`http.py:55-71`).
IPOFetch: 3 tries, `2**(attempt+1)` s backoff, 401/403 raised as HTTPError, 0.6 s gap after every request (`scraper/common.py:13-15,47-66`).

---

## 2. Endpoint table

All NSE URLs are `GET https://www.nseindia.com` + path; all BSE URLs are `GET https://api.bseindia.com/BseIndiaAPI/api` + path (JSON) unless noted.
Column "Ref" = `ipo_portal/sources.py` line unless another file is given. Field names are from `docs/schema/raw_catalog/<source>/<endpoint>.json`.

### 2a. NSE — list feeds (static)

| # | Endpoint (name in repo) | URL | Referer | Returns (key fields) | Serves | Ref / notes |
|---|---|---|---|---|---|---|
| N1 | `ipo_current_issue` | `/api/ipo-current-issue` | `/market-data/all-upcoming-issues-ipo` | list: `companyName, symbol, series (EQ/SME), status, issueStartDate, issueEndDate, noOfSharesOffered, noOfsharesBid, noOfTime, isBse` (numbers as strings) | CAL, SUB (headline) | `sources.py:40`; SOURCES.md cadence 15 min / tol 2 h; seed for all NSE nested endpoints. Note `docs/AUDIT_FINDINGS.md:36` — returned 0 rows on 2026-05-26 while BSE had 19 |
| N2 | `ipo_upcoming` | `/api/all-upcoming-issues?category=ipo` | same | list (often empty): forthcoming mainboard + SME | CAL | `sources.py:41`; catalog observed 0 rows |
| N3 | `ipo_public_past_issues` | `/api/public-past-issues` (IPOFetch adds `?from_date=DD-MM-YYYY&to_date=DD-MM-YYYY`) | same | list: `company, companyName, symbol, securityType, priceRange, issuePrice, ipoStartDate, ipoEndDate, listingDate, htmSym, linkRemovalDate`; company may carry "-Issue Withdrawn" suffix | CAL (history), LIST (issue price) | `sources.py:42`; IPOFetch `scraper/nse.py:59-72`; 380 KB+ payload |
| N4 | `ipo_past_security_type` | `/api/ipo-past-security-type` | same | list of `security_type` buckets (N0/DEBT etc.) | CAL helper | `sources.py:43,65-70` |
| N5 | `rights_forthcoming` | `/api/all-upcoming-issues?category=forthcomingIssues` | same | `company, symbol, series, rightStartDate, rightEndDate, qty, bidQty, nse_bse_cumu, status` | RTS | `sources.py:55` |
| N6 | `rights_active` / `rights_past` | `/api/liveWatchRights-issues?index=activeIssues` / `?index=pastIssues` | same | `company, symbol, rightStartDate, rightEndDate, bidQty, nse_bse_cumu, nse_cumu_timestamp, status` | RTS (+ rights subscription) | `sources.py:56-57`; `AUDIT_FINDINGS.md:40` — demand fields often null in rights feed |
| N7 | `ofs_active_grouped` | `/api/live-ofs-active-issues` | `/market-data/public-issues-offer-for-sale-ofs` | `company, symbol, series, floorPrice, cutOffPrice, issueSize, ltp, noOfTimes, totalSubscription, offerDate, status` | OFS | `sources.py:51` |
| N8 | `ofs_active_retail/general/total_retail` | `/api/live-ofs-active-issues-ss?index=RS` / `IS` / `totalForRetail` | same | `{data, timestamp}`; total_retail: `companyName, symbolRG, totalIssue, totalNOT, totalRG` | OFS | `sources.py:44-46` |
| N9 | `ofs_forthcoming` | `/api/live-ofs-forthcoming-issues` | same | usually empty | OFS | `sources.py:47` |
| N10 | `ofs_past` (+`?index=GENERAL`, `?index=RETAIL`) | `/api/live-ofs-past-issues` | same | `companyName, symbol, category, floorPrice, allocatePrice(General/Retail), noOfshareOffered, cumlativeQty*, allocatedQty*, noOfTimes, methodology, offerDate` | OFS | `sources.py:48-50` |
| N11 | `tender_active/forthcoming/past` | `/api/liveTenderActive-issues`, `/api/liveTenderForthcoming-issues`, `/api/liveTenderPast-issues` | `/market-data/public-issues-tender` | buyback tender books: `company, symbol, category, noOfSharesOffered, noOfsharesBid, noOfTime, cumDmatQty, cumPhyQty, cumConf*, allocatedPrice, band, offerDate, offerEndDate` | (buybacks — outside our needs) | `sources.py:52-54` |
| N12 | `ipp_forthcoming/active/past` | `/api/all-upcoming-issues?category=ipp`, `/api/liveIppActive-issues`, `/api/liveIppPast-issues` | IPO referer | `company, symbol, ippStartDate, ippEndDate, issueSize, ieqQty` | — | `sources.py:58-60` |
| N13 | `invits_current/past`, `reits_current/past` | `/api/invits-current-issues`, `/api/invits-past-issues`, `/api/reits-current-issues`, `/api/reits-past-issues` | IPO referer | same shape as N3 | CAL (REIT/InvIT) | `sources.py:61-64` |
| N14 | `offer_documents_equity` / `offer_documents_sme` | `/api/corporates/offerdocs?index=equities` / `?index=sme` | `/companies-listing/corporate-filings-offer-documents` | list: `company, symbol, isin, pan_no (may be masked XXXXX0000X), drhp, drhpAttach, drhpDate, drhpStatus, drhpSubDate, rhp, rhpAttach, rhpDate, fp, fpAttach, fpDate, adv, advAttach, advDate, issue_open_date, issue_close_date, ipo_abridged_prospectus_xbrl_link, ipo_inprincipal_xbrl_link, ipo_inlisting_xbrl_link, iapAvLink, icAvLink` | DOCS (DRHP/RHP/final prospectus PDFs), CAL (filing stage) | `sources.py:71-72`; 1–1.4 MB payloads; cadence 6 h |
| N15 | `offer_documents_*_companylist` | `/api/corporates/offerdocs/equity/companylist`, `/api/corporates/offerdocs/sme/companylist` | same | `company, isin, symbol` / `company_name` | DOCS helper (symbol↔ISIN map for filers) | `sources.py:73-74` |
| N16 | `public_issue_advertisements` | `/api/public-issue-advertisement?` | `/companies-listing/corporate-public-issue-advertisements` | `issuerName, panNo, boardType, issueType, draftDate, advertisementType, attFilename, record10..record90` | DOCS (price-band ads, statutory ads) | `sources.py:75`; yields PANs for N19/N20 |
| N17 | `public_issue_company_list` | `/api/ipo-issue-company-list` | same | `issuerName` list | helper | `sources.py:76` |
| N18 | (in NSE bundle, NOT fetched) `zczp_*`, `lwf*`, `noncompbid-issue`, `ncbgsec-pastissues`, `mfss-*`, `all-upcoming-issues?category=forthcoming|invits|reits|tender|gsec` | see list | — | ZCZP fields: `companyName, symbol, series, securityType, issueSize, issueStartDate, issueEndDate, status` | — | `docs/NSE_BSE_PRIMARY_MARKET_COVERAGE_AUDIT.md:118-140`; removed deliberately per `sources.py:65-70` (G-Sec/MF, not public issues) |

### 2b. NSE — per-issue (nested, discovered from N1 symbols and N14/N16 PANs)

| # | Endpoint | URL pattern | Referer | Returns | Serves | Ref / notes |
|---|---|---|---|---|---|---|
| N19 | `issue_detail_<sym>_<series>` | `/api/ipo-detail?symbol={SYMBOL}&series={EQ|SME}` | `/market-data/issue-information?series={series}&symbol={symbol}&type=Active` | object: `companyName`; `issueInfo.dataList[]` (key/value: price band, lot, face value, dates, BRLM, registrar, RHP link — some values contain HTML anchors); `activeCat.dataList[] {category, noOfShareOffered, noOfSharesBid, noOfTotalMeant, srNo}` + `activeCat.updateTime` (literal "null" when absent); `bidDetails[] {category, noOfshareBid, noofapplication}`; `demandDataNSE[]/demandDataBSE[] {price, cumQty, timestamp}`; `demandGraph{noOfTimesIssueSubscribed, totalBidRecieved, totalBidAtCutOff, totalIssueSize, graphData[]}`; `demandGraphALL` | SUB (category-wise, both exchanges), CAL detail, DOCS (rhp url) | `sources.py:169`; parser `normalize_v2/parsers/nse_bid_summary.py`; `docs/PIPELINE_STATUS.md:141` — this single call carries the whole NSE subscription picture |
| N20 | `bid_details_<sym>_<series>` | `/api/ipo-bid-details?symbol={SYMBOL}&series={series}` | same | list `{srNo, category, noOfshareBid, noofapplication, updateTime}` | SUB (application counts) | `sources.py:170` |
| N21 | `consolidated_bid_details_<sym>` | `/api/ipo-active-category?symbol={SYMBOL}` | same | `{heading, symbol, updateTime, dataList[] {category, noOfShareOffered, noOfSharesBid, noOfTotalMeant}}` | SUB (NSE+BSE consolidated times) | `sources.py:171`; used for hourly trajectories |
| N22 | `demand_data_nse_<sym>` / `demand_data_all_<sym>` | `/api/ipo-chart-demand?symbol={SYMBOL}&exchange=NSE` / `&exchange=ALL` | same | list `{company, symbol, price, cumQty, timestamp}` (price-wise cumulative demand) | SUB (price-level demand curve) | `sources.py:172-173` |
| N23 | `offer_document_detail_<pan>` | `/api/offer-documents?pan_no={PAN}` | offer-docs referer | object: `isin, industry, face_Value, estimated_Total_Issue_Amount, mode_Of_Issue, eligibility_Of_The_Issue, listing_Sought_At, name_Of_LM_BRLM, name_Of_Other_LM_BRLM, name_Of_Market_Maker, name_Of_Other_RTA, name_Of_Promoter, corporate_Identity_Number, date_Of_Submission, ...` | DOCS + issue metadata (industry, BRLM, promoter) | `sources.py:198`; only fetched for PANs of current symbols or advertised issues (`sources.py:190-195`) |
| N24 | `offer_abridged_<TYPE>_<pan>` | `/api/offer-documents-abridged-prospectus?pan_no={PAN}&type={GENERAL|OFFER_PUBLIC|PRICE_BAND|BRLM|REGISTRAR|ISSUER_COMP|OBJ_ISSUE|SHP}` | same | per type; GENERAL: `nameOfTheIssuerCompany, cinofTheIssuerCompany, dateOfIncorporation, nameOfPromoterOrPromotersOfTheCompany, urlofRHP, websiteOfTheCompany, ...`; SHP = shareholding pattern; BRLM list; OBJ_ISSUE = objects | DOCS (structured abridged prospectus), ANCH-adjacent (promoter/SHP, not anchors) | `sources.py:16-25,200-208`; `HANDOFF.md:163` — "mostly empty in current SME records but real for mainboard" |

### 2c. BSE — list feeds

| # | Endpoint | URL | Returns | Serves | Ref / notes |
|---|---|---|---|---|---|
| B1 | `public_issue` | `GetPublicIssue/w` | `{Table[] {IPO_NO, Scrip_cd, Scrip_Name, LONG_NAME, IR_flag (IPO/FPO/OTB/DPI/CMN/...), IR_FLAG_FULL, Start_Dt, End_Dt, Price_Band (string), Face_Val, Status, FLAG, Is_retailertype, Cum_Shares_BuyBack}}` | CAL (all public-issue types) | `sources.py:85`; `IR_flag`→issue_type mapping in `PIPELINE_STATUS.md:142` |
| B2 | `public_issue_details` | `GetPublicIssue_par/w` | as B1 plus `eXCHANGE_PLATFORM, short_name, RN` (23 rows observed) | CAL; seed for all BSE nested endpoints (IPO_NO, Scrip_cd) | `sources.py:86,257-280`; `refresh.py:478` uses this + N1 as the two seeds for the active-subscription mode |
| B3 | (IPOFetch variant) `GetPublicIssue_par_updated/w?flag=1&status=&exchange=&ir_flag=IPO` | GET, `Referer: https://www.bseindia.com/` | `{Table[]}` same family; `flag=1` = live/recent/forthcoming, both mainboard and SME; narrow near-term window only | CAL | IPOFetch `scraper/bse.py:1-33`, `README.md:41` |
| B4 | `ipo_years` | `IPOYear/w` | `{sr, year}` | helper | `sources.py:87` |
| B5 | `ipo_tracker_current_year` | `IPOTrackerN/w?Fromdt=YYYY0101&Todt=YYYYMMDD` | aggregates: `TotalIPO, NoOfIpo, NoOfSMEIpo, IPOWithPositiveListingDayGains, IPOWithListingDayLosses, ...` | LIST (year stats) | `sources.py:88` |
| B6 | `ipo_documents` | `Pubissues_IPODRHP_par_ng/w` | list: `scrip_cd, Scrip_Name, Stk_Name, Stk_Exchange (1/2), Status, DRHP_ID, DRHP_Doc, Red_Herring_Prospectus, Prospectus, BasisAllot_ID, Open_ID, Prior_Id, T_3_ID, T_5_ID, T5Stage_Document, Audiovisual_DRHP/RHP, updated_date` | DOCS; **basis-of-allotment document id** (`BasisAllot_ID`) — the only BoA reference in either repo | `sources.py:89`; 520 KB+; catalog note: status codes undocumented |
| B7 | `ipo_performance_mainboard_<year>` / `_sme_<year>` | `MoreCompanyN/w?Fromdt={YYYY}&company=&flag=1&type=2` (flag=2 for SME) | list: `CompanyName, Company_Short_Name, IssuePrice, ListedOn, ListingDayClose, ListingDayGain, CurrentPrice, GainLoss, IMAGE (URL contains BSE security id), Time` | LIST (listing price, listing-day gain, CMP) | `sources.py:102-104`; one call per year 2017→now; catalog warning: `Time` was a stale year-end snapshot |
| B8 | `ofs_date_list` | `Mkt_CurrDeri_dropDownDate_OFS_beta/w` | `{DT_TM}` date dropdown | OFS (date-keyed detail not implemented) | `sources.py:90`; SOURCES.md "dropdown-dependent" |
| B9 | `rights_issue_documents` | `Pubissues_FurtherIssuesummary_RI_isd_ng/w` | `Company_Name, scripcode, InPrincipleStatus, InPrinciple_date, ListingStatus, Listing_stage_date, Recordid` | RTS (documents) | `sources.py:95` |
| B10 | `qip_documents` | `Pubissues_FurtherIssuesummary_QIP_isd_ng/w` | same shape as B9 | — | `sources.py:96` |
| B11 | `buyback_tender_documents`, `buyback_open_market_documents`, `takeover_documents`, `voluntary_delisting_documents` | `Mkt_Pubissues_FIS_BuybackTenderoffer_isd_ng/w`, `Pubissues_FIS_Buyback_Openmkt_isd_ng/w`, `Mkt_Pubissues_FIS_Takeover_isd_ng/w`, `Pubissues_FIS_VoluntaryDelisting_isd_ng/w` | `Fld_CompanyId/COMPANY_CODE, Company_Name, PreStatus/PostStatus, predoc/postdoc, preDoc/PostDoc, PreendDate/PostendDate` | — | `sources.py:91-94` |
| B12 | `invit_placement_documents`, `invit_reit_documents` | `Pubissues_get_InvitPlacement_ng/w`, `Pubissues_INVSTSandREITS_File_ng/w` | `COMPANY, Draft_FILE, Red_Herring_FILE, Prospectus_FILE` + dates | DOCS (REIT/InvIT) | `sources.py:97-98` |
| B13 | `bond_issue_documents`, `bond_issuance_years` | `Pubissues_BondIssues_DRHP_ng/w`, `Pubissues_Bond_Issuances_Fin_Year_ng/w` | `Scrip_Name, scrip_cd, DRHP_Date, Red_Herring_Prospectus, Prospectus, Open_Date` | — (NCDs) | `sources.py:99-100` |
| B14 | `sgb_live_issues` | `Pubissues_SGBIssues_Live_ng/w` | `IM_ID, IM_IPO_NAME, IM_IPO_SYMBOL, IM_OPEN_DATE, IM_CLOSE_DATE, IM_FLOOR_PRICE, Status` | — | `docs/schema/raw_catalog/index.json:279`; parser `normalize.py:778` (v1 only; not in `sources.py`) |

### 2d. BSE — per-issue (nested, keyed by `IPO_NO` and `Scrip_cd` from B2)

| # | Endpoint | URL pattern | Referer | Returns | Serves | Ref / notes |
|---|---|---|---|---|---|---|
| B15 | `issue_detail_<ipo_no>` | `GetMkt_ISSUE_BBS_IPO/w?IPO_NO={N}` | `https://www.bseindia.com/markets/publicIssues/DisplayIPO?id={N}` | `{IPONO_0[] master: IPO_NO, Issue_Period, Price_Band, Face_Value, Market_Lot, Minimum_Bid_Quantity, Issue_Size_No_of_shares, Book_Running_Lead_Manager, Co_Book_Running_Lead_Manager, Registrar, Anchor_Details (usually ""), Prospectus_GID, Price_Band_Advertisement, Public_Notices, Corrigendum, Addendum, Eligible_Banks, Cut_off_time_for_UPI_Mandate_Confirmation, DY1..DY6, Security_Type...; IPONO_1 dynamic cols; IPONO_2/IPONO_3 price-level demand {Price, Quantity} at two timestamps}`; names `^`-delimited | CAL detail (lot, band, BRLM, registrar), SUB (price-wise bid book), ANCH (flag only) | `sources.py:276`; parser `normalize_v2/parsers/bse_issue_detail.py:1-12,93-94`; `HANDOFF.md:160-161` calls IPONO_2 "the most distinctive datapoint"; works for **historical** IPO_NOs too (`backfill_detail.py:1-19`, sweep 1→7800) |
| B16 | `bid_details_<ipo_no>` | `Pubissues_GetBkbldgCatdem_ng/w?IPO_NO={N}` | same | `{Table[] {SRNo, Scripname, Maxdt, col2..col5}}` category rows (BSE-only book) | SUB (BSE book by category) | `sources.py:277`; parser `bse_bid_summary.py` |
| B17 | `consolidated_bid_details_<ipo_no>` | `Pubissues_GetBkbldgCatdem_PAR_ng/w?IPO_NO={N}` | same | as B16 plus `col8` (NSE+BSE cumulative) | SUB (consolidated) | `sources.py:278` |
| B18 | `consolidated_bid_details_new_<ipo_no>` | `Pubissues_GetBkbldgCatdem_PAR_bbnew_ng/w?IPO_NO={N}` | same | new-format consolidated book (the one v2 trajectories key on) | SUB (consolidated, preferred) | `sources.py:279`; `trajectory_v2.py:46` |
| B19 | `demand_schedule_<ipo_no>` | `Pubissues_BSEDemandSchedule_otb_ng/w?Scripcode={S}&IPO_NO={N}` | same | `{Table[] {SRNo, Scripname, Maxdt, col2, col4}}` cumulative demand by category | SUB (trajectory) | `sources.py:284` |
| B20 | `demand_graph_bse_<ipo_no>` / `_consolidated_` | `https://www.bseindia.com/BseGraph/charts/BarChart_IPO?Scripcode={S}&ir_flag={IPO|FPO|CMN}&CType=B` (`C` for consolidated) | same | HTML (not JSON) | SUB (visual only) | `sources.py:285-286`; "intentionally exempted" from parsing (`COVERAGE_AUDIT.md:87-90`) |

### 2e. GMP / aggregators / enrichment

| # | Source, endpoint | URL pattern | Method / auth | Returns | Serves | Ref / notes |
|---|---|---|---|---|---|---|
| G1 | InvestorGain cloud v2 (IPOFetch) | `https://webnodejs.investorgain.com/cloud/v2/report/data-read/331/{page}/{month}/{year}/{fy}/0/{category}` + `?search=` — page=1, month/year = today (UTC), `fy` = `YYYY-YY` Indian FY (e.g. `2026-27`), category=`all`; report id 331 = "live IPO GMP" | GET, no auth; Referer/Origin investorgain.com | `{reportTableData[] {Name (HTML `<a>` fragment), GMP (HTML: `&#8377;<b>45</b> (12%)` or `--`), Sub, "Price (₹)", "IPO Size", Lot, "Updated-On", ~ipo_status1 (U/O/C), ~IPO_Category, ~Srt_Open, ~Srt_Close, ~Str_Listing, ~urlrewrite_folder_name}}` | GMP, SUB (headline), CAL (earliest — tracks from rumour/DRHP stage) | IPOFetch `scraper/gmp.py:22-27,54-105`, `README.md:42`. **No v1-retirement note anywhere in IPOFetch** — only that the page is Next.js client-rendered so HTML is empty and the JSON endpoint is undocumented and "can change without notice". ~15–20 rows per run have no NSE/BSE match (`README.md:76-80`) |
| M1 | Moneycontrol listed IPOs | `https://api.moneycontrol.com/mcapi/v1/ipo/get-listed-ipo?start={N}&limit=20` | GET, no auth; Origin/Referer moneycontrol | `{success, data.listedIpo[] {sc_id, company_code, company_name, ipo_type, issue_price, issue_size, dt_open, dt_close, listing_date, listing_gain, last_price, change, perChange, todays_gain, total_subs, url}}` | LIST (listing gain, CMP), SUB (total_subs, historical), CAL (history) | `moneycontrol.py:508-577`; paginate until short page (E.PAG.003 says stop on two consecutive short pages); 0.1 s sleep |
| T1 | Trendlyne upcoming | `https://trendlyne.com/ipo/api/upcoming/` | GET, XHR headers | list `{ipo_id, company_name, company_slug_name, drhp_filing_date, ipo_drhp_document, ipo_rhp_document, rhp_external_document, issue_size, pre_ipo_placement_in_cr, price_range_min/max, bid_open_date, bid_close_date}` (dates/bands mostly null — filing-stage only) | DOCS (DRHP links), CAL (filed pipeline) | `trendlyne.py:600-640` |
| T2 | Trendlyne year screener | `https://trendlyne.com/ipo/api/screener-v2/year/{YYYY}/` (2018→now) | GET | year stats + per-IPO rows: `total, profit, loss, avg_gain, max_gain, min_gain, insights[]...` | LIST (listing gains history) | `trendlyne.py:610-613`; enrichment tier only (E.SRC.003: must not mask exchange data) |
| C1 | CapitalMarket IPO/SME historic table | `https://www.capitalmarket.com/markets/IPOs/ipo-historic-table`, `.../sme-historic-table` | GET page 1, then POST ASP.NET postback (`__VIEWSTATE`, `__EVENTTARGET=<pager target>`); no auth | HTML `tbody tr` rows: mainboard 13 cols = listing_date, company (+`/IPO-Synopsis/<id>` link), issue_size, subscription_qib/nii/retail/total, offer_price, list_price, listing_gain_percent, cmp_bse, cmp_nse, current_gain_percent; SME 11 cols (lot_size, offer_price, listing_open/close, ...) | SUB (historical category-wise), LIST | `capitalmarket.py:17-21,192-243`; E.PAG.001 viewstate drift |
| P1 | PRIME Database demo pages | `https://primedatabase.com/{pub_demo,sme_ipo_demo,rig_demo,qual_demo,ipp_demo,invit_demo,too_demo,deli_demo,buy_demo,blockdeal_demo,...}.asp` | GET, no auth — but **only coverage tables (Year / Amount / No. of issues)**; row-level data paywalled | `{fiscal_year, amount_rs_cr, count}` per year | none for us (aggregate counts only) | `prime.py:277-297`; SOURCES.md "Used as coverage map, not row-level join" |
| S1 | SEBI public-issues filings | `https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=10` → detail `/filings/public-issues/<mon-year>/<slug>_<id>.html` → PDF `/sebi_data/attachdocs/<mon-year>/<n>.pdf` | GET HTML, 25 rows/page, ~2127 rows | `{filing_date, company_name, detail_url, document_url, document_type (DRHP/UDRHP/corrigendum/abridged)}` | DOCS (earliest DRHP signal, weeks before exchanges) | `sebi.py:1-46`; `AUDIT_FINDINGS.md:49` — SEBI DNS failed once; treat stale-if-fail |
| Y1 | Yahoo chart | `https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL.NS|.BO}?period1&period2&interval=1d&events=history&includeAdjustedClose=true` | GET, no auth | OHLC candles from listing date | LIST (listing close, CMP), PARENT (any listed symbol) | `yahoo_v2.py:31,124-131`; 18 h disk cache |
| K1 | Zerodha Kite Connect | `https://api.kite.trade/session/token`, instruments, historical, LTP | full broker login; local-only | instrument master, listing candles, LTP | LIST, PARENT | `kite.py:27-28`, `kite_v2.py`; never runs in CI (`docs/KITE.md`) |
| TJ1 | Tijori B2B kite-screener IPO feed | `https://b2b.tijorifinance.com/b2b/v1/in/api/kite-screener/ipo/` | GET, no auth header in code (may be IP/partner-gated) | list `{compname, isin, keystats{symbol, financials.yearly_results}, revenue_mix, peers, shareholding}` | PARENT/peers, financials | `tijori.py:13-36`; `docs/TIJORI_IPO_FEED_REQUEST.md` |
| D1 | IndiaDataHub Economic Monitor | `https://feeds.indiadatahub.com/...` series `CMEQCRN*11M`, `CMEQCRV*11M` | API key | SEBI monthly capital-raising counts / ₹ Cr | none (macro stats) | `datahub.py:22-47` |

---

## 3. NSE cookie bootstrap and cloud blocking — what the code says

- **ipowatch-co**: `HttpClient.warm_nse()` (`http.py:40-45`) GETs the upcoming-issues HTML page with `Referer: https://www.nseindia.com/`; `fetch_endpoints` calls it once before the first NSE endpoint in a batch (`sources.py:126-135`; same in `orchestrator/refresh.py:498-504`). Browser UA + Accept-Language set on the session (`http.py:32-38`). There is **no comment about Akamai/cloud IP blocking in ipowatch-co code**; `SOURCES.md:22-24,62-63` says warm-up is required, NSE returns 429 on burst, and recommends 1 req / 500 ms with exponential backoff on 429. BSE: 1 req / 500 ms, backoff on 429/503 (`SOURCES.md:114-115`). Non-retryable 4xx (401/403) raise immediately (`http.py:65-66`).
- **Failure handling** is stale-if-fail: on any exception the previous raw snapshot is kept and an event is appended to `data/reports/source_fetch_events.jsonl` (`refresh.py:493-518`, `storage.py:160-170`, `REFRESH_CYCLE.md:127-130`); the manifest gets `degraded`, `stale_sources[]`, `source_freshness` (`REFRESH_CYCLE.md:120-126`). `EDGE_CASES.md:341-349` lists "GitHub Actions runner outages, NSE rate limiting" as the known triggers.
- **IPOFetch** is explicit (`scraper/nse.py:1-6`, `README.md:40,84-88`): "NSE blocks naive requests (Akamai)"; and "**NSE occasionally blocks datacenter IPs, including GitHub Actions runners, even with a correct cookie warm-up.** If the scheduled workflow starts failing with 401/403 from NSE specifically, that's the likely cause — BSE and GMP scraping are unaffected." Every source is wrapped so one failure degrades rather than kills the run (`merge.py`; `README.md:89-94`). Workflow runs every 2 h on `ubuntu-latest` (`.github/workflows/scrape.yml:5`).
- Practical implication for our collector: run NSE from a residential/Indian IP or accept BSE + InvestorGain as the cloud-safe core; BSE needs only a Referer.

## 4. Point-in-time snapshot design (ipowatch-co)

- Every fetch is written as `data/raw/<source>/<endpoint>/<YYYYMMDDTHHMMSSZ>.json` with an envelope `{meta:{source,endpoint,url,fetched_at,status_code,elapsed_ms,body_sha256}, body}` (`storage.py:130-157`). `write_json` is **hash-gated**: byte-identical content is not rewritten (`storage.py:109-127`), so unchanged endpoints don't accrue files. `data/raw/` is gitignored (`HANDOFF.md:32`); only derived outputs are committed.
- Consumers read only the **latest** file per endpoint dir (`storage.py:173-191`). History is compacted into **trajectories**: per-issue hourly subscription observations extracted from the bid-book snapshots, deduped by `(source, observed_at)`, merged monotonically, and **frozen 7 days after close** so old curves never churn (`trajectory.py:14,256-262,360`; `trajectory_v2.py:1-45`; `REFRESH_CYCLE.md:72-77`). Provenance is `sources[].snapshot_at` on each record (`REFRESH_CYCLE.md:62-70`). No explicit pruning of raw dirs exists; growth is bounded by hash-gating plus timestamps only changing when bodies change. Historical BSE per-issue detail was backfilled once by sweeping `IPO_NO` 1→7800 (`backfill_detail.py`, `PIPELINE_STATUS.md:158-160`) giving ~20k endpoint dirs.

## 5. "Sources that broke / block" — explicit notes found

| Note | Where |
|---|---|
| NSE blocks datacenter/GitHub Actions IPs (401/403) even with warm-up | IPOFetch `README.md:84-88` |
| NSE Akamai blocks cold API calls; warm-up + Referer required | IPOFetch `scraper/nse.py:1-6`; `SOURCES.md:22-24` |
| NSE 429 on burst; BSE throttles bursts (429/503) | `SOURCES.md:62-63,114-115` |
| NSE `ipo_current_issue` returned 0 rows while 19 issues were live on BSE (2026-05-26) | `docs/AUDIT_FINDINGS.md:36-37` |
| SEBI DNS resolution failure; needs stale-if-fail | `docs/AUDIT_FINDINGS.md:49` |
| Latest full refresh recorded 331 "blocking drift events" (upstream schema drift) | `docs/AUDIT_FINDINGS.md:51`, `data/reports/upstream_drift.jsonl` |
| 14 parser-failed and 301 unsupported endpoints; aggregator feeds may be "retired or modelled as comparison-only" | `NSE_BSE_PRIMARY_MARKET_COVERAGE_AUDIT.md:31-34`, `V3_REBUILD_REPORT.md:74` |
| InvestorGain / NSE / BSE all undocumented, "can change field names, move, or start requiring new headers/auth at any time" | IPOFetch `README.md:7-9,89-94` |
| BSE demand-graph HTML deliberately not parsed | `COVERAGE_AUDIT.md:87-90` |
| Capitalmarket `__VIEWSTATE` paging drifts between fetches | `EDGE_CASES.md:363-367` |
| Trendlyne values can mask primary data (enrichment must not overwrite) | `EDGE_CASES.md:258-262` |
| G-Sec/NCB/LWF/MFSS NSE feeds intentionally dropped | `sources.py:65-70` |
| HANDOFF.md has **no** broken-sources list; it names all sources as working and lists "Sector / industry breakdown … would need new scraping from CapMkt or PRIME" as a gap | `HANDOFF.md:82-88,171` |

---

## 6. Ranked: 10 most valuable endpoints for our collector

1. **NSE `/api/ipo-detail?symbol=&series=`** (N19) — one call = category-wise NSE+BSE subscription, price-level demand, lot/band/BRLM/registrar/RHP link. Reliability: needs cookie warm-up + Referer; blocked from datacenter IPs per IPOFetch; `updateTime` may be literal "null".
2. **BSE `GetPublicIssue_par/w`** (B2, or IPOFetch's `GetPublicIssue_par_updated/w?flag=1&ir_flag=IPO`) — calendar seed with `IPO_NO`/`Scrip_cd` for every issue type. Reliability: Referer only, no cookies, cloud-safe; most robust calendar source in both repos.
3. **BSE `Pubissues_GetBkbldgCatdem_PAR_bbnew_ng/w?IPO_NO=`** (B18) — consolidated NSE+BSE category book, cloud-safe, also serves historical IPO_NOs. Reliability: high; columns are unlabeled `col2..col8` so header-row detection is needed (`trajectory.py:53-58`).
4. **InvestorGain `cloud/v2/report/data-read/331/1/{m}/{y}/{fy}/0/all`** (G1) — the only GMP source; also gives status, sub, size, dates for pre-official IPOs. Reliability: undocumented, HTML-in-JSON fields, but no blocking reported.
5. **NSE `/api/ipo-current-issue`** (N1) — live headline subscription + symbol seed. Reliability: same NSE caveats; observed empty once when BSE showed 19 live issues, so never treat as sole calendar.
6. **BSE `GetMkt_ISSUE_BBS_IPO/w?IPO_NO=`** (B15) — lot, band, BRLM, registrar, price-level bid book (IPONO_2), `Anchor_Details` flag; works historically. Reliability: high; strings everywhere, `^`-delimited names.
7. **BSE `MoreCompanyN/w?Fromdt=YYYY&flag=1|2&type=2`** (B7) — listing price/day-1 gain/CMP for every mainboard+SME IPO per year. Reliability: high, but `CurrentPrice` can be a stale year-end snapshot.
8. **NSE `/api/corporates/offerdocs?index=equities|sme`** (N14) + **BSE `Pubissues_IPODRHP_par_ng/w`** (B6) — DRHP/RHP/prospectus PDFs; B6 additionally has `BasisAllot_ID`. Reliability: NSE 1 MB+ payload behind cookie wall; BSE cloud-safe.
9. **Moneycontrol `mcapi/v1/ipo/get-listed-ipo?start=&limit=20`** (M1) — historical listing gain, CMP and `total_subs` in one paginated JSON, no auth. Reliability: good; pagination stop-condition quirk (E.PAG.003).
10. **NSE `/api/ipo-chart-demand?symbol=&exchange=ALL`** (N22) and **BSE `Pubissues_BSEDemandSchedule_otb_ng/w`** (B19) — price-wise cumulative demand curves for the subscription window. Reliability: NSE caveats / BSE cloud-safe; only populated while the issue is open.

Runners-up: NSE `/api/public-past-issues` (N3, full history incl. issue price and listing date, 380 KB), NSE `/api/offer-documents-abridged-prospectus?pan_no=&type=` (N24, structured promoter/BRLM/objects/SHP — mainboard only), SEBI filings listing (S1, earliest DRHP signal), NSE rights/OFS live feeds (N6–N8).
