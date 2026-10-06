# CLAUDE.md — read this first

India IPO desk for one retail investor (Hari). A deterministic collector on GitHub Actions writes one JSON document; a
static vanilla-JS page renders it; Claude is never in the daily path. Live at https://harimano.github.io/ipo-desk/ from
https://github.com/harimano/ipo-desk (public). This file is the working brief — kept short on purpose, because every
session pays for it. The long story (why each thing is the way it is, every lesson with its date) is
`docs/project/HISTORY-2026-09.md`; read the part you need when you touch that area.

Other docs: `README.md` architecture + the seven enforced rules · `docs/MODULE-CONTRACT.md` how a module is written ·
`docs/DATA-SCHEMA.md` the document's shape · `docs/mined/` endpoint and response notes (check before guessing a field) ·
`docs/AI-AND-PREDICTION.md` what the evidence base supports (the AI layer in §3 is NOT started) · `docs/DASHBOARD-SURVEY.md`.

## Where things live

- `main` — code, fixtures, `data/aliases.json`, research sheets. Never collector output.
- `data` branch (orphan) — `latest.json` + `history/`, written ONLY by `ipo-desk-bot` in `collect.yml`. `live` branch —
  one amended commit of `live.json` from the five-minute market-hours loop (`collector/live.py`: mainboard from NSE
  `/api/ipo-detail`; every SME from Narada, at most every 10 min an issue; NSE's list total, then InvestorGain 566, as
  fallbacks; every book tagged `src`; never an all-zero book; exits on an NSE trading holiday; GMP from IG 331). `scripts/pull_data.sh` copies `data` into `./data`.
- `_site/` — built by `site/build.py`, never committed. `collector/layout.py` splits the document into
  `meta / board / pipeline / investors / research / history` parts; `boot.js` fetches `meta.json`, then only changed parts.
- Schedule: full runs 06:43 and 18:13 IST; intraday (subscription + gmp + open issues' records) :07/:37 on weekdays;
  `live.yml` 08:55 and 12:55. GitHub's cron is best-effort, so a Cloudflare Worker (`ops/trigger-worker/`) dispatches them.
  A workflow's push does not trigger other workflows: `collect.yml` dispatches `deploy.yml`; a page-only change needs
  `gh workflow run deploy.yml`.
- Hari's Mac: no Homebrew, no Node. `uv` and `gh` in `~/.local/bin`; `.venv/bin/python -m collector`, `.venv/bin/pytest`.
  Preview: `.claude/launch.json` server `site` serves `_site` on 8765.

## Rules (the ones that have bitten)

1. **The pipeline fetches structured data and renders it. It never reads documents** (PDF / OCR / zip). If a figure exists
   only in a document, leave the field empty and say so; that is research-layer work (`data/research/`). Parsing an HTML
   table an API returns is fine. The page follows the same rule: it renders fields, it never parses sentences.
2. **Statistics are the collector's** (`evidence`), never the page's. Mainboard and SME are NEVER pooled. Every rate carries
   n and a Wilson 95% interval; a thin band widens, it is never hidden. The page's own arithmetic is limited to an open
   issue's EV (its inputs move with `live.json`) and the Scoreboard's by-year explorer, which follows the same n + Wilson rule.
3. **Evidence and both sides, never a verdict** — no "apply" / "skip", no invented scores. Allotment odds are a LOWER BOUND
   ("at least 1 in N"): lots per application is unpublished. Since 2 Oct 2026 the REAL odds by count sit BESIDE it ("about 1
   in N": Narada's applications received ÷ slots, slots from the RHP's Max Allottees where the record has them) — never
   instead of it, hidden when the two disagree; EV stays on the lower bound.
4. Never edit `latest.json` by hand, never commit it on `main`, never push to `data`. `scripts/validate.py` is the gate.
5. A parser that gets an empty or unexpected response raises `SourceChanged` — never `[]` as success. Retries are for
   network faults only; **never retry a 403**.
6. Row `name`s are keys the viewer's browser depends on: match, never rename. `collector/names.py` is the one matcher
   (`Matcher.match` can return an alias target that is not in the list searched — always `.get`); fix spellings in
   `data/aliases.json`. A row is matched by `igId`, else by name AND opening date.
7. Secrets (Angel One, `NTFY_TOPIC`, Cloudflare `GITHUB_TOKEN`) are entered by Hari, never pasted in chat or written to a
   file. The Book (applications, holdings, P&L) never goes in the repo. No paid services. No React / Node.
8. localStorage keys must survive: `ipo-interest`, `ipo-holdings`, `ipo-apps`, `ipo-tasks-done`, `ipo-tasks-custom`,
   `ipo-investors`, `ipo-theme`, `ipo-tab`, `ipo-research-sel`, `ipo-seen`.
9. **Dependencies are a run-time risk, not a footnote** (6 Oct 2026: selectolax 1.0 dropped `selectolax.parser`; every
   collect run failed at import for a morning — the gate refused to write, the board went stale). HTML parsing is the
   lexbor backend only (`from selectolax.lexbor import LexborHTMLParser as HTMLParser`). A declared package must be
   imported somewhere or carry the reason beside it (`logzero`, `websocket-client`: SmartApi needs them and does not
   declare them); `nse` / `bse` were surveyed, never used, and are gone.

## How to build here

- Survey the source first (the site's own network calls); one complete API beats five partial ones.
- State the design and get a "go" before anything larger than one file. Small fixes: just do them.
- When a bug is a pattern, grep every call site and fix them all in one change.
- Run it live early into a throwaway copy (`cp -R data /tmp/x && python -m collector --data /tmp/x/data --only <m> -v`),
  then `scripts/validate.py <new> --prev data/latest.json`; record the REAL response as the fixture (saved fixtures
  `ipo-detail-2305` / `2119` are trimmed to 120 chars a field — `ipo-detail-2057-JINDAL-full.json` is the whole one).
- **Before shipping any page change**: no console errors on all seven tabs; loop over EVERY option in `#rsel` calling
  `onchange` (one JS call, ~50 sheets — three different crashes were caught only this way, one reached production);
  check phone width. Test the listing-day card with `window.__ipo.live({preopen:[…]})`.
- Say what was verified (`git log`, `gh run list`, the live URL) and what was not. Side findings go on a list.
- Cost: one fresh session per task; Sonnet for page work, Fable for collector / design work.
- **A stale page is a failed run until proven otherwise**: `gh run list` first. A scheduled "success" may be an intraday
  no-op; read the Install / import lines of the latest failure before touching code.
- `ruff check .` must pass (309 tests too). CI runs ruff LAST in `collect.yml` — it fails the run, never the data. The
  standard lives in `[tool.ruff.lint]`: BLE001 is off on purpose (module-boundary catches record, log or re-wrap).

## The collector

`MODULES` order IS the fallback logic (a later patch wins):
`calendar, gmp, details, subscription, listings, history, tape, anchorbook, evidence, players, parents, filings, offers, flows, deals, news, logos`.
Ownership is enforced by `schema.OWNERS` / `ROW_PATCHERS`; a failed module changes nothing. `Result.doc` is today's
document as assembled so far; `prev` is yesterday's.

- **InvestorGain's private JSON API is the backbone** (`webnodejs.investorgain.com/cloud/v2`; v1 vanished in July 2026 — if
  it goes, NSE / BSE modules carry the board). `ipo/list-read` = the calendar (ids, SME included); `ipo-detail-read/<id>` =
  one ~280-field record per listing → row fields, `anchors[]`, `facts`, and `records{igId}` (the Research sheet: financials,
  peers, objects, reservation with max allottees, GMP by day, the book by day — HTML tables parsed AS tables). Reports:
  331 GMP · 566 this year's category books · 377 listing performance since 2022 (`history` → `listedPerf`, `comps`) ·
  607 allotment planner · 554 event calendar · 551 all anchor investors · 561 one investor's IPOs (id is the LAST path
  segment; the free feed returns only the latest FIVE — a members' limit, do not work around it).
- `evidence` (no network): per segment — trailing window named on screen (12 months, else last 100), all-years secondary;
  total-subscription bands primary, QIB / retail labelled with their years (2026 only); GMP fit (a, b, q10/q90) — PROVISIONAL
  because report 377's GMP is stamped on listing morning: `details` writes `gmpEve`, `history` freezes it, and at 30 rows a
  segment both fits are published side by side, never switched silently; EV per retail application by retail-book band;
  `hold` (day-1 close vs the open, by how it opened); `warnings[]`, rendered on the page. The fit excludes GMP = 0.
- `players`: the 40 largest anchors by money + 30 by count, each one's latest five, turned round into `books{igId}` for
  unlisted issues. Enough for "who is in today's books"; NOT enough for a per-investor track record, so none is shown.
  `frozen{igId}` = each issue's line-up the day it lists (never rewritten; `covered[]` makes "no book" a real zero);
  `evidence.segments[x].anchors` bands those against the outcome — accruing since 22 Sep 2026, thin and said so.
- `deals`: NSE's daily bulk + block files, two cuts — tracked names (`investors.bulkDeals`, 45 days; ~2 hits a month) and
  EVERY deal in one of this year's listings (`investors.listingDeals`, 60 days, `sme` on each row). Symbols come from board
  rows, else NSE's equity lists via `names.Matcher`, cached in `investors.listingSymbols`; a fuzzy hit listed before this
  year is rejected. BSE's own bulk + block APIs (`sources/bse_deals.py`, found in the site's network calls) add the BSE
  SME board by scrip code (`listedPerf.bseCode` from report 377's Symbol column; rows carry `exchange`). Most rows are
  prop desks round-tripping on day one; the page's sold│bought bar is what makes that visible.
- `tape`: one NSE bhavcopy per trading day (nsearchives zip, SME series included) → a close a day in `priceHistory` for EVERY
  listing of this year with a symbol (board `symbol`, else deals' `listingSymbols`); backfills 6 days a run, then 1 call a day;
  `tape.noFile` remembers holidays; today's file only after 18:30 IST. A second leg reads BSE's bhavcopy for listings with a
  BSE code and no NSE symbol (`tape.bse`), so the BSE SME board has a price path too. `evidence.lockins` freezes the 5-day move after each
  30-day anchor unlock from that path (`segments[x].lockin`, n + Wilson, since 22 Sep 2026).
- `anchorbook` (80 records a run, newest first, ~10 days to backfill 1,300): every IPO's anchor allocation table from the IG
  record → `anchorBooks` (own lazy part `books.json`, NOT fetched at boot; `complete` marks feed-truncated books).
  `evidence` turns it into `trackRecords` (same part): per investor, per segment, listed-up share + Wilson, median gain,
  day-one close, 5/30-day moves from the tape, lead-anchor subset; `minRows` on screen. Rule 3 applies: rates with
  intervals, sorted by n — no score, no verdict. Same key: `dealRows` / `deals` = the tape's names (net buyer / net seller
  per client × stock × day) and the stock's 5- / 20-day move after, frozen once the 20-day move exists — accrues from 22 Sep 2026.
- `parents` prices sheet parents AND every live quota row's `ticker` into `investors.prices[parent]` (the quota planner).
- `filings` (quota radar) also discovers parents it does not know: NSE's market-wide `/api/corporate-announcements` (one call a
  board, 4 days, ~3,900 rows; works from the runners, BSE's does not) → `quotaLeads[]` (a listed company on a subsidiary's offer,
  60 days). A lead from a watched parent moves its quota row (source `nse_ann`; a withdrawal only flags). A lead naming an `expected`
  row, or an `auto` row whose first word is a listed group's (≤15 share it; stoplist), gets `quotaCandidate` — a flag, never a quota;
  promotion is still a person reading the DRHP. NSE's summary is sometimes just "General Updates" (JSW Cement, 25 Sep 2026): partial
  recall by construction, never fixed by reading the PDF.
- `listings` borrows a symbol from `investors.listingSymbols` (matched, since that cache uses the listing report's spelling)
  and does not report a row `tape.bse` prices as "cannot price". `validate.py` caps the COMPACT document (6 MB, warns at 80%).
- `subscription` asks mainboard NSE → Narada, SME Narada → NSE (NSE's SME answer has no shares offered: zeros), then BSE,
  chittorgarh (dead). **Narada** (`sources/narada.py`, trynarada.com, reachable from runners) is the only fresh book for
  BSE-only SMEs and gives application counts (`apps`; mainboard books stay NSE's but take Narada's counts). Narada's
  SLOT counts can be wrong on mainboard (Nityas: 7,178 vs the RHP's 25,123), so `max_allottees` from the record wins
  (`reservedSrc`). It publishes no timestamp: books and counts carry our fetch time. A small third-party site: be polite.
- `logos` (full runs): InvestorGain's record names each issue's logo file (`row.logo`, via `details`); the PNG (~100 KB, from
  chittorgarh.net/images/ipo/) is fetched ONCE, shrunk to a 96x48 WebP (~1.3 KB) and written to `logos/<igId>.webp` beside
  latest.json — the first module that writes files (`Result.files`, only under `schema.FILE_OWNERS[module]`, only when
  ok). `logos{igId: {src, at, missing?}}` (board part) lists what exists, so the page never asks for a missing image.
  `collect.yml` commits `logos/` to the data branch after the gate; `deploy.yml` and `build.py` publish it. Needs Pillow.
- `subscription` never replaces a positive book with an all-zero one (exchanges answer zeros after close). A GMP of "0"
  with no trade behind it is "no quote". `validate.py`'s loss check ignores rows due to retire (listing + 1 day). It also exempts `players.covered` / `players.names` (keyed by unlisted
  issue: they shrink when issues list; `players.frozen` is the gate and only grows — 13 listings over 5–6 Oct read as "40% loss").
- Known gaps: `api.bseindia.com` answers 403 to GitHub's runners (offers, bse_ann, and the BSE deals leg — all "blocked", a
  note; they work from Hari's Mac); `www.bseindia.com/download` (the BSE bhavcopy) is fine. NSE gives FII / DII one day at a time (8–16 Sep missing; no backfill source surveyed); Tata Motors' quota
  ticker is stale; `details` caps at 25 record calls a run; ipopremium 403s (leave it); chittorgarh fallback is dead;
  Angel One has no secrets; `investors.moves / holdings / portfolios`, `flows.monthly / rotation`, quota prose are db-era
  carry-forward that nothing refreshes (the page shows the sweep's snapshot in a closed, dated archive).

## The page (`site/src/`)

`app.js` is the db-era monolith (closure `window.__ipoInit`; nothing inside is a global — inspect charts with
`Chart.getChart(id)`). New screens go in their own file, pulled in by `/* @include name.js */`:
`research.js` (fetched sheet, "issues like this one") · `players.js` (Anchors on the board: one line per current issue, line-up behind a `who` expander, past-books line from the anchors band) · `quota.js` (quota
planner, Pipeline tab) · `quotaradar.js` (Possible quotas under the planner: `expected[].quotaCandidate`, strong vs
group-name, and the `quotaLeads` list folded; a `quota?` mark on Market's pipeline chips) · `hold.js` (hold-or-sell meter: Today, Board row, Scoreboard) · `deals.js` (Market > Superinvestors: one tracker card per listing with deals — price vs issue, round-trip / net buyer / net seller counts per client×stock, sold│bought bar, rows folded under; Money that stayed; Repeat clients; `Mine` = held or starred; counts only) ·
`lockin.js` (Anchor lock-ins: 30 / 90-day expiries from `anchors[]` in a −10/+45 day window, next 14 days open, rest folded, free-to-sell amount, price vs issue, sales on the tape since; `trackerQueueItems()` puts lock-ins, the day's deals, followed names, and a strong-record anchor in an unlisted book (5+ IPOs, 70%+ listed up — the filter is printed on the card) on the Today queue) ·
`records.js` (Anchor track records + today's books read against them; fetches the lazy `data/books.json` on demand via `DATA.lazy.books.hash`; `recKey` mirrors `anchorbook.investor_key`) ·
`logo()` in app.js (board, SME screener, sheet headers; white chip in dark mode) · `names.js` (Your names: the followed investors matched by normalised substring against anchor books, anchor letters and both deal files; `follows()`, `+` buttons via `[data-follow]`) · `scoreboard.js` (Open calls, GMP
calibration with the collector's fit, hit-rate by month, band explorer). Shared evidence helpers in `app.js`: `EVD`, `SEG`,
`EDG`, `bandOf`, `edgeLbl`, `evBand`, `evCls` (coloured by the INTERVAL), `evOf(b, seg, cat)` — `cat` = retail / shareholder /
employee; the reserved-category EV beside the retail one is Hari's real edge. Chart.js needs explicit `type:"linear"` scales
when dataset types are mixed. Market has a sticky section bar built from `.sec-h h2` + `[data-nav]`.

## Next

Hari to do: set the `NTFY_TOPIC` secret (alerts are built and in dry-run). Then: login + Book sync on Cloudflare free tier (Access + Worker + KV,
encrypted in the browser; state the design, get a go) → capital planner and calendar (reports 554 / 607) → provenance on
hover, source-health strip → alerts with deep links, weekly digest → the AI layer, last.
