# Dashboard survey — what to learn from, what to borrow, what to fork (18 Sep 2026)

Three parallel surveys: commercial Indian IPO/trading products, Indian-market GitHub repos, and
best-in-class open-source terminals worldwide. Star counts and prices are as seen on 18 Sep 2026.
Written in the Cowork session on 18 Sep 2026 against the repo as of commit `3621afe` (live loop landed).
It is input to the roadmap in `CLAUDE.md` (A–F), not a replacement for it. Nothing here is investment advice.

## The one-paragraph verdict

There is no well-maintained open-source Indian IPO dashboard to fork; every one is 0–4 stars and
one author. The commercial products are each excellent at one thing and none of them merges the
three things that matter to us — the subsidiary pipeline, the parent-holding record-date countdown,
and the shareholder-quota outcome — which is exactly the gap ipo-desk fills. The good code to
borrow lives in adjacent repos (FII/DII boards, P&L ledgers, options terminals) and in a handful of
global terminal projects. Recommendation: keep hand-building the site layer, lift specific components and patterns from
the repos in §2 and §3, and decide the front-end stack question in §5 with Hari before any rewrite.

## 1. Commercial products — the feature bar to clear

| product | price | what it does best | steal |
|---|---|---|---|
| [Chittorgarh](https://www.chittorgarh.com/ipo/ipo_dashboard.asp) | free | best free **shareholder-quota report** ([link](https://www.chittorgarh.com/report/ipo-with-shareholder-quota/164/upcoming/)): parent, shares reserved, % of issue, quota-category subscription; basis-of-allotment viewer; broker review-consensus grid | quota outcome columns; allotment-ratio table; review-consensus matrix |
| [InvestorGain](https://www.investorgain.com/ipo-dashboard/mainline/) | free | GMP + subscription (bNII/sNII split, Employee, Shareholder) + post-listing performance on one row; **GMP performance tracker** (GMP said X, listing gave Y) | one-row-per-IPO density; GMP calibration table |
| [IPO Watch](https://ipowatch.in/) | free | GMP marquee; [upcoming IPOs with shareholder quota](https://ipowatch.in/upcoming-ipo-with-shareholders-quota/) (27 rows incl. DRHP stage) | earliest-stage pipeline list (candidate list only) |
| [IPO Central](https://ipocentral.in/upcoming-ipos-with-shareholders-quota/) | free | quota list with the practical rules (hold by RHP/record date, T+1/T+2 buffer, quota sometimes added only in RHP) | eligibility rules as a card per row |
| [Ipoji](https://www.ipoji.com/) | free / Pro | status chips phrased as user actions (Apply / Allotment out / Unblock funds); push per event | action-verb statuses for the Today queue |
| [Ipowala](https://ipowala.in/ipo-anchor-investor-list/) | free | anchor list with direct BSE PDF links | deep links to exchange PDFs |
| [Groww](https://groww.in/ipo) / Zerodha Kite / Angel One / Upstox / Kotak Neo | free with account | apply flows; Kite exposes **Individual / Existing shareholder / Employee** category; Kotak publishes per-IPO quota-eligibility explainers | jargon-free timeline stepper; category at apply time; eligibility explainer |
| [Screener](https://www.screener.in/ipo/) | free / ₹4,999 yr | "Recent IPOs", "Below IPO price" standing views; densest tables in India; phrase alerts on filings | standing filters; table density; phrase alert on "reservation for eligible shareholders" |
| [Trendlyne](https://trendlyne.com/ipo/dashboard/) | free / ₹310–2,000 mo | DVM traffic-light score on newly listed names; screener rewind | traffic-light score for recent listings |
| [Tickertape](https://www.tickertape.in/) | ₹249 mo | Market Mood Index dial; scorecard chips | "IPO market mood" dial from aggregate GMP + subscription |
| [PRIME Database](https://primedatabase.com/pub_demo.asp) | institutional, price on enrolment | the only structured **anchor-investor names, QIB sub-category breakdown, city-wise bids**, league tables | the concept of an anchor-quality tag; not reachable for us |
| Moneycontrol Pro | ₹899 mo | subscription-by-category bars with day tabs | day tabs |
| Sensibull / Dhan / Kite / TradingView | free–₹1,300 mo | keyboard-first terminals: hotkeys, sticky order pane, ⌘K search | command palette + sticky action pane |

**Who shows shareholder quota:** Chittorgarh and InvestorGain (structured, outcome), IPO Watch and
IPO Central (pipeline stage), Kite and Kotak (apply-time category and eligibility). Nobody free
merges pipeline + record-date countdown + quota outcome. That is our screen.

### Top 10 to steal, ranked

1. Parent-holding eligibility countdown (IPO Central + Kite) — Pipeline: parent ticker, "buy by" date (record/RHP date minus settlement), held/not-held flag.
2. Shareholder-quota outcome columns (Chittorgarh) — Pipeline + Research: quota % of issue, quota-category subscription, allotment ratio, per past IPO.
3. Day-wise subscription heatmap by category (InvestorGain) — Today: QIB/bNII/sNII/RII/Emp/SH × Day 1–3, coloured by multiple.
4. GMP calibration tracker (InvestorGain) — Research: GMP-implied vs actual listing gain, so GMP is trusted exactly as much as it deserves.
5. Action-verb status chips (Ipoji/Groww) — Today: "Buy parent by", "Apply by 5pm", "Check allotment".
6. Allotment-odds card (Chittorgarh basis-of-allotment) — Today: given category subscription, odds per lot count; client-side arithmetic.
7. Review-consensus matrix + scorecard chips (Chittorgarh + Tickertape) — Board: Valuation / Anchor quality / Promoter / Use of funds / Red flags.
8. Anchor-book quality tag (PRIME concept, Ipowala PDFs) — Research: parse the BSE anchor PDF once, show top-5 anchors, MF share, lock-in dates.
9. "Below IPO price" / "uptrending" standing views (Screener) — Market/Book.
10. Command palette + screen hotkeys (Dhan/Kite/TradingView) — everywhere.

## 2. Indian-market GitHub repos — honest ranking

No safe fork exists. Read these; copy patterns, not projects.

| repo | ★ / licence | why it matters to us |
|---|---|---|
| [MrChartist/fii-dii-data](https://github.com/MrChartist/fii-dii-data) | 40 / MIT, pushed this week | **our Market screen nearly verbatim**: single-file vanilla JS, FII/DII table + 45-day heatmap + flow-strength meter, Chart.js, PWA, `data/history.json` snapshots swappable for our feed; html2canvas "share as image" |
| [Shubhamnpk/yonepse](https://github.com/Shubhamnpk/yonepse) (NEPSE) | 2–4 / MIT, 850+ commits | the only repo running **our exact pipeline** (Actions cron → sharded JSON → GitHub Pages) with an IPO tab; take the shard scheme and page shell, not the CSS |
| [marketcalls/openalgo](https://github.com/marketcalls/openalgo) `frontend/` | 2.6k / AGPL | production-grade shadcn + TanStack tables for orders/positions/trade book — the Book screen bar; copy patterns, not files |
| [udaysrinu/sharecase](https://github.com/udaysrinu/sharecase) | 0 / MIT | **Book/P&L logic**: parses Zerodha Console tradebook CSV into FIFO-matched P&L, equity curve, concentration, "never sold" counterfactual — all client-side |
| [Parikshit985/india-ipo-tracker](https://github.com/Parikshit985/india-ipo-tracker) | 1 / MIT | most complete **IPO data model** seen (ipos, gmp_history, subscription time-series, sentiment, sector views) — mirror as JSON |
| [pushpankar-kiran/india-ipo-dashboard](https://github.com/pushpankar-kiran/india-ipo-dashboard) | 0 / MIT | **benchmark-adjusted post-listing return checkpoints** (listing, D5, D10, 1M, 6M, 1Y vs Nifty) — best Research idea found; curated 2021–26 seed |
| [dinoopm/kite-dashboard](https://github.com/dinoopm/kite-dashboard) | 1 / none | screen inventory close to ours; **ASM/GSM surveillance badges** on holdings |
| [samrendr/nse-institutional-flow](https://github.com/samrendr/nse-institutional-flow) | 0 / none | dual scheduler (Actions + local launchd) because NSE geo-blocks runners — the ops lesson we already hit |
| [rajeevayathu/gandiva-dashboard](https://github.com/rajeevayathu/gandiva-dashboard) | 2 / none | **"new since last scan" diff view** — reusable for the Today queue |
| [sarthak2443/IPO-Radar-Bharat](https://github.com/sarthak2443/IPO-Radar-Bharat) | 1 / MIT | provenance envelope `{source, updatedAt, availability}` on every metric |
| [vishesh0604/IPO-Tracker](https://github.com/vishesh0604/IPO-Tracker) | 0 / none, 560 commits | latest.json + history.json split, scraper that survived site changes |
| [hedaprateek/ipo-tracker](https://github.com/hedaprateek/ipo-tracker) | small / — | zero-build "Today" tab with per-category application cost + allotment odds; three-tier data fallback |
| [vinodscode/ipo-exchange-scrape](https://github.com/vinodscode/ipo-exchange-scrape) | small / — | Actions → `data/ipos.json` → Pages; keeps last-good data on scrape failure (our rule 2) |
| [anshuthopsee/nse-oi-visualizer](https://github.com/anshuthopsee/nse-oi-visualizer) | 36 / none | D3 grouped bars; web-worker scheduled refresh; stale a year |
| [AdroitAnandAI/RRG-Sector-Rotation-India](https://github.com/AdroitAnandAI/RRG-Sector-Rotation-India) | 32 / none | relative-rotation graph as a Market widget |
| [Utsav173/ipo-gmp-pro](https://github.com/Utsav173/ipo-gmp-pro) | 1 / MIT | clean Radix + Tailwind GMP table and stat cards; desktop/mobile split |
| [marketcalls/openalgo-heatmap](https://github.com/marketcalls/openalgo-heatmap) | 4 / MIT | zero-dep squarified treemap core — Pipeline/Market tile map sized by issue, coloured by GMP% |

Skipped: API-only repos with stars (maanavshah/stock-market-india 1k, hi-imcodeman 290,
kite-mcp-server 317), archived ones, and the scrapers already mined in `docs/mined/`.

## 3. Global open-source terminals — the UI bar

| repo | ★ / licence | borrow |
|---|---|---|
| [OpenTerminal](https://github.com/ErTasselli/OpenTerminal) | 1.1k / MIT | ⌘K palette + ⌥1–9 add-widget keys; draggable panels persisted to localStorage; **stale-while-revalidate fallback chain** per source. The single most relevant repo. |
| [gloomberb](https://github.com/gloom-sh/gloomberb) | 903 / MIT | **two-mode command line** (Ctrl+P commands, backtick ticker search) — the Bloomberg `<GO>` split; vim keys; every command emits JSON |
| [Lightweight Charts](https://github.com/tradingview/lightweight-charts) | 17k / Apache | 45 KB; price lines + markers for issue price / GMP / listing on one chart |
| [uPlot](https://github.com/leeoniya/uPlot) | 10k / MIT | sparklines in table cells (GMP trend, subscription build-up) at near-zero cost |
| [cmdk](https://github.com/pacocoursey/cmdk) | 13k / MIT | the palette; use a verb grammar (`go pipeline`, `open <ipo>`), take kbar's `actions[]` model |
| [TanStack Table](https://github.com/TanStack/table) | 28k / MIT | headless; column defs as data; sort/filter/group state serialised to the URL hash as saved views |
| [Perspective (FINOS)](https://github.com/finos/perspective) | 11k / Apache | datagrid look (±colouring, dense rows); view config as JSON. Too heavy as the app shell |
| [Actual Budget](https://github.com/actualbudget/actual) | 27k / MIT | keyboard-editable ledger grid for the applications ledger |
| [Wealthfolio](https://github.com/afadil/wealthfolio) | 9k / AGPL | CSV import-mapping UI (broker statement → Book); nicest-looking personal-finance repo |
| [Ghostfolio](https://github.com/ghostfolio/ghostfolio) | 9k / AGPL | Holdings → Activities → Performance IA; not a density reference |
| [Tremor](https://github.com/tremorlabs/tremor) / [shadcn/ui](https://github.com/shadcn-ui/ui) | Apache / MIT | KPI card with delta badge + inline sparkline; Table/Command/Dialog/Tabs primitives — restyle, never inherit the SaaS-white theme |
| [niusann/fical](https://github.com/niusann/fical) | small | publish an `.ics` feed next to the JSON so Today lands in a calendar |
| OpenBB (73k), FinceptTerminal (31k), Maybe (archived), Grafana/Superset/Streamlit | — | almost nothing borrowable for a static web UI; star counts mislead here |

## 4. Patterns to adopt (attributed)

1. Two-mode command line: commands on one key, entity search on another (gloomberb).
2. Verb-first palette with a visible breadcrumb path (cmdk + OpenBB CLI prompt).
3. Screen hotkeys `1–6`, panel hotkeys, persisted layout (OpenTerminal).
4. View state — columns, sort, filter, grouping — as JSON in the URL hash, savable as named views (Perspective, TanStack).
5. Sparkline column + delta badge in every dense table (uPlot, Tremor, AG Grid finance demo).
6. Annotated price chart: issue-price line, GMP band, listing marker (Lightweight Charts).
7. Squarified treemap sized by issue size, coloured by GMP% (openalgo-heatmap core).
8. Stale-while-revalidate + last-good data, with a visible generated-at badge (OpenTerminal, vinodscode). Already our rule; make it visible.
9. Keyboard-editable ledger for applications and allotments (Actual).
10. Today = decision-cost view: per-category cost, lots, odds, deadline countdown, before any chart (hedaprateek); export `.ics` (fical).
11. "New since last run" diff on the Today queue (gandiva).
12. Provenance envelope per metric: `{source, asOf, availability}` (IPO-Radar-Bharat) — our `integrity.checks` already carries this per module; surface it per cell on hover.

### Anti-patterns seen

SaaS-white card grids with 24 px padding (density collapses; a terminal wants 28–32 px rows and
12–13 px numerals); chart-first pages when the decision lives in a table; one fuzzy palette where
verbs and entities collide; server-required fallbacks hidden inside "static" apps; multi-MB engines
for under 2,000 rows; animated, rounded, gradient charts; silent staleness with no timestamp;
choosing by star count.

## 5. Front-end stack — a proposal, not a decision (needs Hari's "go", rule 2)

The site today is `inner.html` + `app.js` (772 lines, vanilla, string-built HTML) + `boot.js` with the
per-screen JSON split and hash-based refresh already done. That is working and live, and the roadmap
says "cut each screen to what matters today" before anything else. So the question is not "rewrite
now" but "what do we rewrite into when the screens have been cut". Two honest options:

**Option 1 — stay vanilla, modularise.** ES modules per screen, a `format.js`, a `store.js` for
localStorage, `site/build.py` concatenates. Zero new dependencies, no toolchain on the Mac (no
Homebrew; `uv` only), Claude Code can keep shipping one-file fixes. Cost: table state (sort, filter,
group, saved views) and the command palette get hand-written; six screens of hand-written table code
is how `app.js` reached 108 KB in the db era.

**Option 2 — Vite + React 19 + TypeScript, hash-routed, Tailwind v4 + shadcn primitives, cmdk,
TanStack Table, Zustand, Lightweight Charts v5 for price series, uPlot for sparklines.** The stack
OpenTerminal proved for this aesthetic; all MIT/Apache and static-safe; the libraries Claude Code
writes most reliably. Cost: a Node toolchain on the Mac and in `deploy.yml`, and a real rewrite of
every screen (screenshot before/after; localStorage keys `ipo-interest`, `ipo-holdings`,
`ipo-investors` and the `lot`/`priceHistory`/application bookkeeping keyed by row `name` must
survive byte-for-byte).

My recommendation is Option 2, but only after roadmap items A and B have settled what each screen
shows — rewriting screens whose content is still being cut wastes the rewrite. Until then, Option 1
discipline for every change to `app.js`: no new string-built tables; new screens get their own file.

Rejected either way: Perspective or AG Grid as the shell (weight, licence); Svelte (fewer
copy-paste primitives for Claude Code); ECharts except for a calendar heatmap.

## 6. Mapping onto the roadmap (A–F in CLAUDE.md)

| roadmap item | what this survey adds |
|---|---|
| A. Decision-first Board | Chittorgarh's review-consensus grid and Tickertape scorecard chips as the row-expand; InvestorGain's one-row density (GMP + sub + performance) as the bar; Ipoji's action-verb status chips for the Today cap-of-three |
| B. Signal scoreboard | InvestorGain's GMP performance tracker (report 377) is the exact precedent — "GMP said X, listing gave Y" per issue; pushpankar-kiran's benchmark-adjusted checkpoints (D5 / D10 / 1M / 6M / 1Y vs Nifty) for the horizon columns |
| C. Capital timeline + Book | hedaprateek's Today tab (per-category cost + odds before any chart); sharecase's client-side FIFO from Zerodha tradebook CSV; Actual's keyboard-editable ledger; Wealthfolio's CSV import-mapping UI; fical's `.ics` export of the calendar |
| D. Quota eligibility planner | IPO Central's rules (hold by RHP/record date, T+1/T+2 buffer, quota sometimes added only in RHP) as the card text; Chittorgarh report 164 columns (quota %, quota-category subscription, allotment ratio) as the outcome history; Kite's apply-time category as the reminder of what the user must select |
| E. Provenance + source health | IPO-Radar-Bharat's `{source, asOf, availability}` per cell; OpenTerminal's stale-while-revalidate badge (the live strip already does the visible half) |
| F. Alerts / digest | Screener's phrase alerts on filings ("reservation for eligible shareholders") as an alert rule; MrChartist's html2canvas "share as image" for the digest card |
| Later: charts, live prices | Lightweight Charts price lines/markers (issue price, GMP band, listing print, pre-open IEP); uPlot sparklines in cells; openalgo-heatmap's treemap core for a Market tile map |

Things the survey found that are NOT on the roadmap and probably should be, in priority order:
1. **Two-mode command line** (gloomberb): commands on one key, IPO search on another; `1–6` for screens. The
   palette exists (`openCmd`); the split and the hotkeys do not.
2. **Saved views** — sort/filter/group state in the URL hash, nameable (Perspective/TanStack). Cheap in
   either stack; lets Hari keep "SME only, closing this week" as a link.
3. **"New since last run" diff** on Today (gandiva) — the live loop makes this natural: what changed since
   the last five-minute tick.
4. **Below-issue-price standing view** (Screener) over recent listings, in Market.

## 7. Repos to read before touching a screen

MrChartist/fii-dii-data (Market), udaysrinu/sharecase (Book), openalgo `frontend/` (tables), OpenTerminal
(keyboard + panels), gloomberb (command line). Everything else in §2–3 is a single idea each.
