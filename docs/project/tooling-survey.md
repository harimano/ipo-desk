# Tooling survey for the standalone architecture — 17 Sep 2026

**Decision context.** Two manual fires of the db-backed daily task hung on 17 Sep without writing. The
diagnosis is architectural: Claude sits in the critical path for scraping that needs no judgement. The
replacement is a deterministic collector on cloud cron writing `data/latest.json`, a static site reading
it, and Claude as an on-demand contributor to `data/research/` and `data/quota-reviews/` only. Hari's
decisions 17 Sep: cloud, not Mac; public URL first, login later; alerts in stage two.

This document is the result of four parallel web surveys (libraries, open-source IPO scrapers, price
APIs, SEBI/NSE filing sources). Sources are linked inline. Treat every "works from cloud" claim as
"worked for someone recently" — the first collector run from GitHub Actions is the real test.

---

## 1. The structural finding: NSE blocks datacenter IPs, BSE does not

Everything else in the design follows from this.

`nseindia.com` sits behind Akamai and blocks or times out connections from AWS, GCP, Azure and
GitHub Actions runners ([NseIndiaApi #9](https://github.com/BennyThadikaran/NseIndiaApi/issues/9),
[#14](https://github.com/BennyThadikaran/NseIndiaApi/issues/14) — `421 Misdirected Request` on the
cookie bootstrap by Oct 2025; [#27](https://github.com/BennyThadikaran/NseIndiaApi/issues/27),
[#28](https://github.com/BennyThadikaran/NseIndiaApi/issues/28) — a May 2026 change broke endpoints
again). Real GitHub-Actions projects corroborate it: [AmfiBeas PR #228](https://github.com/techmuns/AmfiBeas/pull/228)
gets a bare 403 and falls back to a headless browser on the runner;
[nse-swing-scanner](https://github.com/amitashwinibhagat/nse-swing-scanner) reports the historical API
needs a JS-computed `_abck` cookie, yet its corporate-actions and surveillance calls work twice daily
from Actions. The picture: **lightweight JSON endpoints often work from cloud with browser headers and a
cookie-bootstrap GET; heavier endpoints and archives are hit-or-miss and change without notice.** One
survey fetched `/api/fiidiiTradeReact`, `/api/ipo-current-issue` and `/api/all-upcoming-issues?category=ipo`
from a non-Indian cloud fetcher with no cookies and got JSON — so the endpoints are not strictly gated
today; whether a given runner IP is flagged varies.

`api.bseindia.com` is far more tolerant of cloud IPs ([BseIndiaApi](https://github.com/BennyThadikaran/BseIndiaApi)),
and the same Regulation 30 intimation is filed on both exchanges. **BSE is therefore the primary exchange
feed for filings and announcements; NSE is secondary, with hard-fail.**

`nsearchives.nseindia.com` (the static CDN) served `content/equities/bulk.csv` and `block.csv` from cloud
without cookies in the survey (bulk had 16-SEP-2026 rows). Daily bhavcopy CSVs there are reported as
Akamai-blocked from Actions. Treat archives as "usually works, must fail loudly".

`sebi.gov.in` appears not to block cloud: [ipo-radar](https://github.com/rohanbeingsocial/ipo-radar) pulls
SEBI RHPs from GitHub Actions daily. Use a browser-like UA.

**Residual risk and its mitigations, in order:** design every NSE call to raise on 403/421/empty JSON and
never write stale data; substitute BSE wherever the same data exists there; and only if it bites, move the
cron to Cloudflare Workers (different egress pool) or a ₹300–400/month Indian VPS. Not the Mac.

---

## 2. Source-by-source: what to use, primary → fallback

| need | primary | fallback | notes |
|---|---|---|---|
| IPO calendar, band, dates, status | NSE `/api/ipo-current-issue`, `/api/all-upcoming-issues?category=ipo` via the `nse` package | BSE `api.bseindia.com/BseIndiaAPI/api/GetPublicIssue_par_updated` via `bse`; ipowatch calendar HTML | NSE JSON carries `noOfTime` (subscription multiple) and `isBse` (SME flag) |
| Subscription figures | same NSE JSON (`noOfTime`) | BSE cumulative-demand endpoint; chittorgarh report 21 HTML | chittorgarh's DRHP report is JS-loaded, but its subscription report is plain HTML |
| GMP | InvestorGain v2 JSON `webnodejs.investorgain.com/cloud/v2/report/data-read/331/` | oriz-ipo's failover chain: IPOWatch → IPOPremium → InvestorGain → Chittorgarh | **InvestorGain v1 was retired July 2026** (`{"msg":"API not found"}`) — treat v2 as fragile, keep the HTML chain live |
| Listing-day open/close | Angel One SmartAPI (symbol appears in instrument master on listing morning) | NSE daily bhavcopy after ~18:00; yfinance lags 0–2 days for new tickers | see §4 — this is the one need that forces a broker account |
| Parent prices (8 tickers), daily | yfinance `.NS`, batched, backoff, latest version (curl_cffi) | Angel One; `nse` bhavcopy | yfinance 429s from cloud are common ([#2422](https://github.com/ranaroussi/yfinance/issues/2422), [#2567](https://github.com/ranaroussi/yfinance/issues/2567)); fine for 10–20 tickers with retries |
| FII/DII provisional | NSE `/api/fiidiiTradeReact` | `nsepythonserver.nse_fiidii()`; skip-with-flag | **no broker or vendor API exposes this** — NSE-only, cloud-risk accepted |
| Bulk/block deals with client names | nsearchives `bulk.csv`, `block.csv` | `nse.bulkdeals()`, `nse.blockDeals()`; BSE via `bse` | NSE-only data; nsearchives is the softer path |
| Parent filings (the quota signal) | **BSE announcements API** polled daily per parent scrip code | NSE `/api/corporate-announcements?symbol=…` | see §5 |
| DRHP/RHP list | SEBI listing page 1, `smid=10` (DRHP) / `smid=11` (RHP), diffed daily | — | JS pagination, 25 rows/page newest-first, page 1 is enough |
| SEBI observations | SEBI processing-status listing `ssid=14&smid=8` | — | least machine-friendly: embedded external sheet; classify by diffing DRHP→RHP listings instead |
| Anchor lists | NSE/BSE allocation PDFs via announcement records; [ipowala](https://ipowala.in/ipo-anchor-investor-list/), [investorgain 551](https://www.investorgain.com/report/anchor-investor-list-by-number-of-ipos/551/) | chittorgarh anchor tab (HTML) | no dedicated repo exists; Vasuki8 and ipowatch-co are the closest bases |
| News | RSS: Business Standard markets, ET markets, Moneycontrol IPO | — | trivial |
| Superinvestor holdings | **stays Claude** — Trendlyne MCP (no public REST API; Pro ₹299/mo, 400 calls/day) | BSE quarterly shareholding-pattern PDFs, parsed | weekly, judgement-heavy: the one need that legitimately stays in the AI layer |

---

## 3. Libraries: use, avoid

**Use.** [`nse`](https://pypi.org/project/nse/) by BennyThadikaran — 4.0.1 released 31 Aug 2026, GPLv3,
`pip install nse[server]` for httpx/HTTP2, 3 req/s throttle, methods `listCurrentIPO`, `listUpcomingIPO`,
`listPastIPO`, `bulkdeals`, `blockDeals`, announcements, nsearchives bhavcopies
([API docs](https://bennythadikaran.github.io/NseIndiaApi/api.html)). No FII/DII method. Its sibling
[`bse`](https://github.com/BennyThadikaran/BseIndiaApi) hits `api.bseindia.com` with plain requests:
announcements, bulk deals, IPO info. These two are the cookie/header layer; do not reimplement it.
[`nsepythonserver`](https://pypi.org/project/nsepythonserver/) (2.97, May 2025) has `nse_fiidii()`.
[`jugaad-data`](https://github.com/jugaad-py/jugaad-data) is alive (Aug 2026 commits, BSE announcements
added) but has no IPO or FII/DII coverage and open bugs on FNO bhavcopy and holidays.

**Avoid.** `nsepy` (dead, README says unmaintained, last release 2020). `nsetools` (quotes only).
`bsedata` (0.6.0 Mar 2024, author says not for production).

**PDF.** PyMuPDF (`fitz`) is ~10× faster than pdfplumber on a 400-page DRHP. `page.get_text()` per page,
regex `eligible shareholders?|shareholders? reservation portion|Reservation for Eligible Shareholders`,
then read bookmarks to jump to "The Offer" / "Offer Structure" and the Definitions table where
"Eligible Shareholder(s)" names the parent and the record-date wording. Seconds per prospectus, no browser.

---

## 4. Prices: the one dependency that needs an account

No free, cloud-friendly, listing-day-capable price source exists without a broker account.

**Angel One SmartAPI** is the pick: free including historical candles
([Angel One](https://www.angelone.in/knowledge-center/smartapi/detailed-introduction-to-smartapi)); login
is client code + PIN + TOTP, and TOTP is scriptable with `pyotp` from the enrolment secret, so daily
headless login works ([smartapi-python](https://github.com/angel-one/smartapi-python)); static IP is
mandatory only for order/GTT endpoints, "not mandatory for APIs other than Orders & GTT"
([forum](https://smartapi.angelone.in/smartapi/forum/topic/5352/static-ip-based-api-keys-now-live-old-flow-still-supported-temporarily));
the April 2026 SEBI changes concern order placement only. Historical endpoint throttles at ~3 req/s. New
symbols appear in the instrument master on listing morning, which is what makes listing-day OHLC possible.
Cost: opening a free Angel One demat (KYC) — Hari's SBI Securities account has no API. Hari has an
Angel One account.

**Alternatives, rejected for this use.** Upstox: free but daily OAuth browser login, not headless.
Dhan: data API ₹499/mo. Zerodha Kite: ₹500/mo data plus daily browser redirect. Groww: ₹499/mo.
EODHD: NSE on $19.99/mo, no BSE, free tier US-only. Alpha Vantage: 25 req/day, BSE suffix only.
Twelve Data / FMP: India only on $149–229/mo tiers. GOOGLEFINANCE: 20-min delay, Sheets-only, no API.

**Fallback:** yfinance `.NS` with small batches and backoff for the eight parents; nsearchives bhavcopy
as ground truth after 18:00.

---

## 5. The quota signal: how a script hears "a listed parent's subsidiary filed"

The earliest machine-readable signal is the **parent's own Regulation 30 intimation** — "board approved
IPO of subsidiary", "subsidiary has filed DRHP" — from the BSE announcements API, polled daily for a
watchlist of parent scrip codes:

```
https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w
  ?pageno=1&strCat=-1&subcategory=-1&strPrevDate=YYYYMMDD&strToDate=YYYYMMDD
  &strSearch=P&strscrip=<code>&strType=C
  (headers Origin/Referer: https://www.bseindia.com/)
```
Attachments are `https://www.bseindia.com/xml-data/corpfiling/AttachLive/<guid>.pdf`. NSE's equivalent,
`/api/corporate-announcements?index=equities&symbol=RELIANCE&from_date=…`, returns `symbol, desc,
attchmntFile, attchmntText, an_dt` with `attchmntFile` pointing at nsearchives — secondary, cloud-risk.
Filter `desc`/`attchmntText` for "draft red herring prospectus", "DRHP", "initial public offer",
"subsidiary".

Confirm and classify (DRHP → observations → RHP) by diffing page 1 of SEBI's `smid=10` and `smid=11`
listings daily. Row links are `/filings/public-issues/<mon-yyyy>/<slug>-drhp_<id>.html`; that page carries
the abridged PDF at `/sebi_data/commondocs/<mon-yyyy>/<name>_p.pdf` and the full DRHP at
`/sebi_data/attachdocs/<mon-yyyy>/<epoch>.pdf`. The title says "DRHP"/"RHP"/"Addendum" — a regex on the
title is the classifier.

Then the clause: download the `attachdocs` full DRHP (fallback nsearchives `Registration_<ts>_<name>.pdf`
from the announcement), PyMuPDF page-by-page, regex-hit "Eligible Shareholder", capture the Definitions
entry plus the Offer-structure paragraph around the first hit. Nothing purpose-built exists;
[ipo-radar](https://github.com/rohanbeingsocial/ipo-radar) parses RHPs by chapter but has no reservation
logic.

---

## 6. Repos worth borrowing from

Almost every repo found has 0–1 stars and most carry no licence. **Copy endpoint knowledge and parsing
patterns; vendor code only from the MIT ones.** Detailed mined notes are in `docs/mined/`.

- [Vasuki8/IPO-Tracker](https://github.com/Vasuki8/IPO-Tracker) — Python, ~690 commits, hourly Actions.
  NSE JSON + BSE fallback + SEBI discovery + **abridged DRHP/RHP/prospectus PDF parsing** (issue
  composition, financials, shareholding; parser versioning, SHA-256). Timestamped subscription history.
  No licence. The most complete pipeline found — the skeleton to study first.
- [chirag127/oriz-ipo](https://github.com/chirag127/oriz-ipo) — Python 3.11, **MIT**, 164 commits, hourly in
  production. GMP failover chain IPOWatch → IPOPremium → InvestorGain → Chittorgarh via selectolax +
  Playwright; Telegram/ntfy alerts. The GMP module and the alert plumbing, vendorable.
- [rohanbeingsocial/ipo-radar](https://github.com/rohanbeingsocial/ipo-radar) — Python, daily Actions.
  PyMuPDF bookmarks + pdfplumber tables (+OCR) extracting 27 SEBI chapters, restated financials, price band,
  peers, risks; pushes a 20-year Chittorgarh dataset to Kaggle weekly. The PDF layer.
- [bebhuvan/ipowatch-co](https://github.com/bebhuvan/ipowatch-co) — Python/Astro, 185 commits, hourly.
  ~30 NSE endpoints + BSE, enriched from CapitalMarket, PRIME, Trendlyne, Moneycontrol; IPO/OFS/rights/REIT;
  point-in-time snapshots. No licence. Endpoint reference.
- [harshitag456/ipo-tracker](https://github.com/harshitag456/ipo-tracker) — Node, 312 commits; notes NSE
  blocks datacenter IPs. [steptechnovision/trendalert-data](https://github.com/steptechnovision/trendalert-data)
  — Node, 887 commits, 20-min cadence; documents the InvestorGain v1 retirement.
- [awesome-et/IPOFetch](https://github.com/awesome-et/IPOFetch) — tiny, but documents the exact NSE, BSE
  and InvestorGain v2 endpoints in one place.

**Datasets for backfill and calibration:** Kaggle [IPO Data India 2010–2026](https://www.kaggle.com/datasets/karanammithul/ipo-data-india-2010-2025),
[Indian IPO Listing Gain 2010–2025](https://www.kaggle.com/datasets/skworld/indian-ipo-dataset),
[IPO Watch debuts/GMPs](https://www.kaggle.com/datasets/nikhilraj7700/ipo-watch-debuts-gmps-trajectories);
HF [scholarly360/indian_ipo_prospectus_data](https://huggingface.co/datasets/scholarly360/indian_ipo_prospectus_data),
[gtfintechlab/ipo-tables](https://huggingface.co/datasets/gtfintechlab/ipo-tables). The ipo-radar dataset
already seeds `listedPerf[]` and `comps[]` (see `data/seed/`).

---

## 7. Collector module map (stage 1)

Each module is independent, writes its own section with its own `asOf` and `{ok, error}`, and raises
rather than writing stale data. `validate.py` runs in CI before any commit lands.

| module | writes | primary → fallback |
|---|---|---|
| `calendar` | `mainboard[]`, `sme[]`, `lot{}` | `nse.listCurrentIPO/listUpcomingIPO` → `bse` public issues → ipowatch HTML |
| `subscription` | `mainboard[].sub`, `sme[].sub` | NSE `noOfTime` → BSE cumulative demand → chittorgarh HTML |
| `gmp` | `gmp`, `gmpPct`, `gmpTrend` | InvestorGain v2 JSON → oriz chain |
| `listings` | `recent[]`, `listedPerf[]`, `comps[]`, `priceHistory{}` | Angel One → nsearchives bhavcopy → yfinance |
| `parents` | `sheets{}.parentPrice` | yfinance batched → Angel One |
| `filings` | `quota[]` stage/bucket/stageDate, `needsReview` flags | BSE announcements per parent → SEBI page-1 diff → NSE announcements |
| `flows` | `flows.latest`, `flows.history` | NSE fiidii → nsepythonserver → skip-with-flag |
| `deals` | `investors.bulkDeals` | nsearchives CSVs → `nse.bulkdeals` |
| `news` | `news[]` | RSS |
| `integrity` | `integrity.checks[]` | one row per module: source used, status, elapsed |

**Stays in the AI layer (Claude, non-blocking, own directories):** `data/research/<slug>.json` (the
current-issue sheets), `data/quota-reviews/<slug>.json` (the reservation clause, read by Claude from the
PDF the `filings` module flagged), `data/investors.json` (Monday sweep via Trendlyne MCP). Claude commits
these to the repo; CI validates them exactly as it validates the collector, and a Claude commit that
touches `latest.json` fails the build.

**Day-one test, before anything else:** `.github/workflows/reachability.yml` hits each primary endpoint
from a runner and reports status codes. That single run decides whether the cron lives on Actions or
moves to Workers.
