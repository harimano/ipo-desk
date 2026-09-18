# CLAUDE.md — read this first

This repo is the India IPO Command Center rebuilt as a standalone site: a deterministic collector
on GitHub Actions writes `data/latest.json`; a static page reads it; Claude contributes research
into its own directories and is never in the daily path. `README.md` has the architecture and the
seven rules the code enforces. `docs/MODULE-CONTRACT.md` is how a module is written.
`docs/DATA-SCHEMA.md` is the document shape. Do not change the schema — the page renders it.
`docs/mined/` holds the notes taken from the reference repos (endpoints, response shapes, parser
patterns) — check there before guessing at a field name. `docs/project/tooling-survey.md` is why each
source was chosen; `docs/project/legacy-briefing-rules.md` has the stage-two alert rules.
`docs/BUILD-PLAN.md` is the tiered list of what to fix, what to rebuild better, and what to add —
work it top to bottom. `docs/DASHBOARD-SURVEY.md` (18 Sep) surveys the commercial products, Indian repos and
global terminals to learn from, maps them onto roadmap A–F, and holds the open front-end stack question (§5).
`docs/AI-AND-PREDICTION.md` (19 Sep) audits the evidence base, says what is and is not predictable from it,
and stages the AI layer; `tools/evidence_check.py` reproduces its numbers and can run as a CI guard.

## State of play (updated 17 Sep 2026)

Live at https://harimano.github.io/ipo-desk/ from https://github.com/harimano/ipo-desk. The collector
completes 10/10 modules from GitHub Actions runners (16/17 sources reachable there; only ipopremium
403s), so the cron stays on Actions. `collect.yml` runs full at 06:45 and 18:15 IST, and a light
intraday pass (subscription + gmp, only while an issue is open) every 30 min 10:00-17:30 IST on weekdays;
intraday commits amend one rolling commit a day on the data branch. `collector/alerts.py` runs after the
commit (dry run until `NTFY_TOPIC` or `TELEGRAM_*` secrets exist).

**Where things live**
- `main` — code, research sheets, `data/aliases.json`, fixtures. Never collector output.
- `data` branch (orphan) — `latest.json` + `history/`, written only by `ipo-desk-bot` in `collect.yml`.
  `scripts/pull_data.sh` copies it into `./data` for local work (both paths are gitignored on main).
- `_site/` — built by `site/build.py`, never committed: `index.html`, the document split into
  `data/{meta,board,pipeline,investors,research,history}.json` by `collector/layout.py`, plus research.
  `boot.js` fetches `meta.json`, then only the parts whose hash changed.
- A push made by a workflow does not trigger other workflows, so `collect.yml` dispatches `deploy.yml`.

**Local setup on Hari's Mac**: no Homebrew. `uv` and `gh` are in `~/.local/bin`; the venv is `.venv/`
(`.venv/bin/python -m collector`, `.venv/bin/pytest`). Playwright is not installed — check pages in a
browser against `python3 -m http.server --directory _site` instead of `tests/render_check.py`.

**Working loop for a parser fix**: `scripts/pull_data.sh`; run the module into a throwaway copy
(`cp -R data /tmp/x && python -m collector --data /tmp/x/data --only <module> -v`); read the real body;
fix; save the body under `data/fixtures/` and add a test; `scripts/validate.py <new> --prev data/latest.json`.
After a fresh `prev` with no symbols, `subscription` and `listings` need a second pass: they read the
symbols `calendar` wrote on the previous run.

**Verified against live responses**: NSE lists + ipo-detail, BSE public issues, BSE category demand
(`Pubissues_BBS_CumultveCatdem_ng/w`), BSE announcements, SEBI lists, InvestorGain v2, ipowatch, NSE
FII/DII, nsearchives CSVs, Yahoo, RSS, all eight scrip codes in `parents.json`.
**Known broken or unproven**: the chittorgarh subscription fallback (site moved to Next.js; parser finds
no table); ipopremium (403, leave it); Angel One (no secrets set yet — Hari adds them himself);
the investor lists inside `anchors` rows, the sweep-owned parts of `investors` (moves, holdings, portfolios — the retired Monday sweep), `flows.monthly/rotation`
and the descriptive text of `quota` rows are still carried forward from the db era (BUILD-PLAN Tier 2/3).
Live since 17 Sep: `offers` (BSE list), `expected` (SEBI registers, built inside `filings`), `investors.prices`
(the `parents` module), sheet `parentPrice`, and everything `details` fetches (see below).

**The pipeline fetches data and renders it. It does not read documents.** Hari's rule, 18 Sep 2026, after an
attempt to OCR anchor-allocation letters inside a run: an important figure must come from a structured source
(exchange or aggregator JSON), not from parsing a PDF/zip each run. Look for the JSON first — open the site's own
page in a browser and read its network calls (that found BSE's demand endpoint and InvestorGain's reports 480 /
333 / 399 / 400). If a figure exists only in a document, say so and leave the field empty; turning documents
into data is research-layer work (`data/research/`, by pull request), never a collector module.
`collector/pdf/anchor.py` and `collector/pdf/clause.py` are bench tools for that layer; no workflow calls them.
The page follows the same rule: it renders fields the collector wrote and should not parse sentences (the anchor
bars used to regex "₹X Cr from N investors — a, b, c" out of prose).

**The backbone is one complete record per listing (`collector/modules/details.py`, since 18 Sep 2026).**
InvestorGain's backend — `GET …/cloud/v2/ipo/list-read` for ids, `GET …/cloud/v2/ipo/ipo-detail-read/<id>` for ~280
fields — fills every placeholder a listing has: ISIN / codes / sector; allotment and listing dates; band, lot, size
split into fresh and OFS; anchor shares x allocation price = anchor book, bid date, both lock-in expiries
(`details` owns `anchors[]`); GMP with its own timestamp; subscription by category; listing price; `facts` (P/E,
market cap, ROE, ROCE, margins, promoter holding, broker views, documents, lead managers, registrar), which the
Research screen renders for any listing nobody has written up. A row is matched to its record once, by name AND
opening date, and carries `igId` from then on. MODULE ORDER IS THE FALLBACK LOGIC: `details` runs after `gmp`
(fresher quote wins) and before `subscription` / `listings` (the exchanges' live book and the traded listing price
overwrite its copies when they answer; its copies stand when they do not). It is a private, undocumented API whose
v1 vanished in July 2026 — if it goes, `details` fails, rows keep what they had, and the NSE/BSE modules carry the
board. `anchorInvestorData` is always empty: who took a book exists only as a PDF letter, which no run reads.
THE CALENDAR IS THE SAME SOURCE: `calendar`'s chain is investorgain -> nse -> bse. InvestorGain's `list-read` is the
board (every upcoming / open / closed-not-yet-listed issue on both exchanges, SME included, days before NSE or BSE
list it, each with a stable id); NSE + BSE lists only enrich it with symbol, series and BSE issue number (what
`subscription` needs to ask them for the live book). The list forgets an issue the moment it lists, so rows it has
dropped are carried from the previous board until the normal expiry. A row is matched by id, else by name AND opening
date (a lookalike name with other dates is another issue). `Result.doc` gives a module today's board as assembled so
far, so a listing born in this run gets its record and its subscription in the same run (`details` and
`subscription` read it; `prev` remains yesterday's document, used for trends and carry-forward).
Two traps met on the way: `Matcher.match` returns an alias target even when that row is not in the list being
searched (always `.get`, never index); and the exchanges answer all zeros for a closed issue, so `subscription`
never replaces a positive book with a zero one. A GMP of "0" with no sauda rate behind it is "no quote".
Hari, 18 Sep: the companies on the board are sample material for getting the METHOD right — do not spend effort
curating or preserving individual legacy rows; make every future listing fill itself.

**Lessons from first contact — check these first when a module says "ok" but the page looks old**
- An "ok" module can be reading the wrong thing: SEBI's `nextValue` is zero-based (page=1 was page two, a month
  old), and real SEBI titles never say "DRHP" (the register a row is on is its meaning).
- Anything overlaid after the modules (`data/research`, `data/investors.json`) silently undoes a module's write to
  the same key. Give the collector its own key (`investors.prices`) or let the newer `asOf` win (`parentPrice`).
- A number can be precisely wrong: NSE's list gives an issue's share count net of the anchor portion, so
  `issueSizeCr` ran ~30% short on every mainboard issue until the InvestorGain feed's figure replaced it. NSE's
  SME issue pages label fields differently ("Price Range", "Lot Size"), which left SME rows without band or lot.
- A private name matcher is a private bug: `gmp` normalised the name "NSE" to nothing, so the year's biggest
  IPO never got a fresh GMP. `data/aliases.json` is honoured by `gmp`, `calendar`, `offers`, `filings`, `anchors`.
- A workflow's push does not trigger other workflows; the page's built-in snapshot shares an `asOf` with the first
  fetch after every deploy. Both looked like "it works" until someone opened the Research tab.

## How to build here (agreed with Hari, 18 Sep 2026)

1. Survey sources before writing a parser: read the site's JS for its endpoints, watch its network calls. One
   complete API beats five partial ones; a document is never the pipeline's source.
2. State the design and get a "go" before anything larger than one file. Small fixes: just do them.
3. When a bug is a pattern, grep every call site and fix them all in the same change.
4. Side findings go on a list for the end of the task, unless they corrupt what is shipping now.
5. Run it live early: `python -m collector --data /tmp/x/data` then `scripts/validate.py`; record the real response
   as the fixture. Hand-made fixtures hid every real bug this repo had.
6. Say what was verified (`git log`, `gh run list`), and say so when something was not.
7. NEXT, in order: make freshness visible on the page (ages, change flashes, live strip, grey out old text) ->
   cut each screen to what matters today -> remove or automate the db-era sections -> measure InvestorGain-vs-NSE
   subscription lag and drop the slow NSE calls if it is minutes.

## Product roadmap (agreed with Hari, 18 Sep 2026) — a decision desk, not a data page

Hari applies for himself only for now (father's and mother's accounts later: model accounts as a field, default "Me").
A. Decision-first Board: QIB and GMP shown against their own track record (from `comps` / `listedPerf`: QIB >100x ->
   97% listed positive, <5x -> 43%), probability-weighted gain (gain x allotment odds) instead of the headline gain,
   a decision clock (QIBs bid late: the picture firms after 2 pm on the last day), details behind a row expand.
   Today capped at three actions. Standing rule: evidence and both sides, never "apply" / "skip".
B. Signal scoreboard: snapshot each issue's signals at close, log the outcome at listing, keep the hit-rate.
C. Capital timeline (ASBA blocks per day across overlapping issues) and full application lifecycle in the Book
   (applied -> allotment -> listing -> sold/held, P&L per account). Needs login + a small store for cross-device.
D. Quota eligibility planner (cost to qualify, last buy date, held or not).  E. Provenance on hover + source-health
   strip.  F. More alerts, weekly digest.  Later: embedded charts, live prices (NSE quote API).
Survey of the reference dashboards, 18 Sep 2026 (live sites + roadmaps): ipo-radar = RHP-PDF score vs listing scatter,
per-IPO report pages, 6/12/24-month horizons, but its live figures are wrong or blank; IPO-Tracker = 1,370-IPO archive,
filters, CSV, compare, calendar, per-cell provenance, but most cells read "Under review"; oriz = one stale GMP row.
None has: a working live book, evidence-calibrated signals, odds-weighted gain, capital planning, or the pre-open.
Verified sources for what comes next (all JSON, all probed live):
  - InvestorGain report 377 (220 IPOs of 2026 incl. SME: sub, GMP at close, est. price, listing open, day close, LTP),
    566 (235 IPOs: QIB / sHNI / bHNI / NII / RII / total, P/E), 421, 486 (LTP) -> this year's evidence, SME included,
    and a scoreboard with back-history on day one; 607 (retail size, RETAIL ALLOTTEES, allot date, FUND REUSE) and
    554 (calendar by day: open / close / BOA / UNBLOCK / listing) -> capital planner; per-IPO `peer-comparison-read`,
    `ipoRecommendationData` (broker tally), `ipo-allotment-read` (registrar link).
  - NSE `/api/special-preopen-listing`: listing-day 9:00-9:45 indicative price + order book (Veegaland: IEP 154 = +10%,
    where it listed; GMP had said +6%). NSE `quote-equity` 403s — do not use; Yahoo covers prices.
ipo-radar and IPO-Tracker state NO LICENCE: take ideas, never code or data. The seed that came from ipo-radar's dataset
was deleted on 19 Sep 2026: `history` (collector/modules/history.py) now builds `listedPerf` and `comps` from InvestorGain
report 377 (2022 onward, 1,323 listings, SME included) and 566 (this year's category books; older years keep only the
total, so QIB evidence starts with 2026 and grows).
**Statistics are the collector's, not the page's (`collector/modules/evidence.py`, owns `evidence`, since 19 Sep 2026).**
Runs after `history`, no network. Per segment (mainboard and SME are NEVER pooled): a trailing window named on screen
(last 12 months, else last 100 listings) with all-years as the secondary figure; total-subscription bands primary, QIB /
retail bands labelled with the years they cover; every band carries n, a Wilson 95% interval, median and p10-p90 — a thin
band widens, it is never hidden; a GMP fit (a, b, residual q10/q90) the page turns into "8 in 10 listed between"; expected
value per retail application by retail-book band (chance x gain - cost of blocked money, median and spread); and
`evidence.warnings[]`, which the Board and Scoreboard render. The chance of allotment is a LOWER BOUND (1 / retail book;
true chance = k / book, k = lots per application >= 1, which no feed publishes) and the page says "at least 1 in N".
The GMP fit is PROVISIONAL: report 377's GMP is stamped on listing morning. `details` writes the last pre-listing-day quote
to the row as `gmpEve`; `history` freezes it into `listedPerf`; at 30 rows in a segment `evidence` publishes both fits
side by side — never switch silently. The page's only arithmetic is an open issue's EV (its inputs move with live.json).
The Scoreboard's band tables are an explorer over rows by year, counted in the page with the same n + Wilson rule.
Build order after A: A2 five-minute market-hours loop + live.json + pre-open watcher -> B history import, evidence for
SME and "this year", scoreboard, sell-at-open-vs-hold -> C calendar + capital planner + compare + per-IPO URLs ->
E provenance, conflict flags, source health -> D quota planner -> F alerts with deep links, digest, broker tally, peers.
Data worth adding: subscription timeline per run, BSE retail application counts (true allotment odds), listing-day
open/high/close, price around anchor lock-in expiry.

**The sheet behind every listing (`records{igId}`, owned by `details`, in the `research` part, since 19 Sep 2026).** The per-IPO
record carries its tables as HTML fragments inside the JSON; `investorgain.build_sheet` parses them AS TABLES ({head, rows}) —
financials, peers, issue objects, reservation (with max allottees per category) — plus typed rows for GMP by day, the book
by day, ratios for two periods, holding, company. A fragment with a <table> and no rows raises SourceChanged; a field the
record lacks is left out. `site/src/research.js` renders it under any written sheet. The saved 2305 / 2119 fixtures were
trimmed to 120 chars per field — `ipo-detail-2057-JINDAL-full.json` is the untrimmed one to test tables against.
Also on `research.js`: "Issues like this one" (a live sheet's total-subscription band, `EDG`/`bandOf`/`SEG`, matched within the
same segment only — no match until the book opens; never a listedPerf/comps join done again on the page). And "For"/"Against"
on the fetched-facts sheet is hidden (with a one-line note) when nobody has written analysis, matching the quota-sheet path.
The Market tab's "Comparables" widget (mainboard/SME toggle, `mktCompScope`) also stopped pooling the two segments and now
reads its bins straight from `evidence.segments[x].bands.total.all` instead of averaging raw `comps` rows on the page.
The SME screener's "Score" (0-100, an invented blend of QIB depth/demand ratio/GMP level) and "Verdict" pill
("institution-backed"/"mixed signals"/"retail froth") were the one place on the page still handing out a verdict —
removed 19 Sep 2026. Its Track record and EV/app columns now read `evidence.segments.sme` the same way the Board does
(`evBand`, shared with `boardRow`'s `pick`); GMP is coloured by its own evidence band instead of an arbitrary >50% "froth" cut.
Hari asked to keep an institutional-conviction grade (a fluff SME book shows up here first) but grounded, not invented:
the QIB cell now carries `evidence.segments.sme.bands.qib` under the bar — n, Wilson interval, labelled 2026-only.
Scoreboard (`scoreboard.js`) gained three pieces, 19 Sep 2026: "Open calls" (live, not history — Open/Closed board rows
with today's evidence-band read and EV, so a viewer can check back after listing day); a GMP calibration scatter
(implied vs realised, coloured by whether GMP called the direction, diagonal = perfect calibration — needed an explicit
`type: "linear"` on both scales, since Chart.js defaults to category axes once a chart mixes dataset types without one);
and hit-rate by month (a page-side explorer over `listedPerf`, segment-only, n + Wilson per month, same as the band tables).
Market tab, 19 Sep 2026 (Hari: "I need a professional dashboard"): the FII/DII chart carries a cumulative line and KPIs with
the previous session and gross buy/sell; "Flow context" is now `flowContext()` — window sums, FII buy-day counts, DII
absorption, mainboard listings on FII-buy vs FII-sell days, and the gaps in the sessions on file — computed from
`flows.history`; the db-era `flows.monthly` / `rotation` / `note` prose is no longer rendered (still carried in the document).
The SME screener sorts rows with a book first and gives an unopened issue ONE cell of what is known (band, lot, minimum
application, dates) instead of six dashes. The GMP calibration chart draws the collector's fit and its 8-in-10 band, fades
listings older than the window, and marks open issues on the fit. `gmpRange` / EV return nothing for a GMP of 0: the fit
excludes zeros. Known gap: NSE gives one day of FII/DII at a time, so days the collector did not run (8-16 Sep) stay missing
until a history source is surveyed.
Reserved categories (19 Sep 2026): `evOf(b, seg, cat)` takes "retail" / "shareholder" / "employee"; the Board's EV cell adds a
line per reserved category the issue has a book for (same fitted gain, that category's own queue, "N× the retail EV"). This is
Hari's real edge — a shareholder book runs at 2-5x when retail runs at 50x+. Not in the figure: the cost and price risk of
holding the parent. No history yet: report 566 carries no shareholder column, so there is no evidence band for it.
Anchor investors ARE structured, partly: InvestorGain report 551 lists 2,842 anchors (IPO count, total invested, average
ticket); 561 with the investor id as the LAST path segment (`…/561/1/<m>/<y>/<fy>/0/<id>`) lists that investor's IPOs with our
igIds — but the feed is capped at the 5 most recent (totalRecords says 150, page 2 repeats page 1): a members' limit, not to
be worked around. Enough for "which top anchors are in today's open books"; not enough for a per-investor track record.
`collector/modules/players.py` (owns `players`, pipeline part, full runs only, ~55 calls / 20 s) does exactly that: the 40
largest anchors by money + 30 by count, each one's latest five turned round into `books{igId: [investor…]}` for unlisted
issues; `site/src/players.js` renders them in "Smart money on the board" with coverage stated ("18 of the 53 largest").
A 403 stops it at once. The line above that says anchor names exist only as a PDF letter is true of the per-IPO record, not of 561.
Quota planner (roadmap D, 19 Sep 2026): `site/src/quota.js` on the Pipeline tab — per live quota IPO: the parent to hold, what ONE
share costs, stage, record date ("buy by" = record date - 2 days) and approval lapse, soonest first; KPIs for parents covered
and the rupees to cover the rest. `parents.quota_parents()` prices every live quota row's `ticker` in the same batch into
`investors.prices[parent]` (20 of 21 priced; Tata Motors' ticker changed with the demerger). "Held" is localStorage `ipo-holdings`.
Page files: `site/src/app.js` is the db-era monolith; NEW screens go in their own file and are pulled into app.js's scope
by `/* @include name.js */` (site/build.py). First one: `scoreboard.js` (tab 7, "Score": GMP calibration, band tables,
sell-at-open vs hold-to-close, below-issue-price filter, sortable list — all computed from `listedPerf` + `comps`).
No React / Node: decided 19 Sep 2026 (stay vanilla, modularise as we touch things).

## Rules for working here

- Never edit `latest.json` by hand, never commit it or `data/history/` on `main`, and never push to the
  `data` branch yourself. The deploy guard fails if main tracks them or if the data branch's last
  commit is not by `ipo-desk-bot`. `scripts/validate.py` is the gate; do not bypass it.
- Research goes in `data/research/<slug>.json` with `name` matching the board row exactly and
  `kind: "current"` (issue sheet) or `"sheet"` (quota parent). Clause readings go in
  `data/quota-reviews/`. The sweep writes `data/investors.json`. Nothing else.
- A parser that gets an empty or unexpected response raises `SourceChanged`. It never returns
  `[]` as success. Keep that property when fixing parsers.
- Retries are for network faults only. Never retry a 403 — it flags the IP.
- Trendlyne (the MCP) is a snapshot database with a fuzzy matcher: never use it for a stock that
  listed today, never more than one NSE code per call, always check the returned symbol matches.
- Row `name`s are keys the viewer's browser depends on. Match to existing names; never rename.
  `collector/names.py` is the one matcher; when a source's spelling defeats it, add a line to
  `data/aliases.json` rather than loosening the matcher.
- `meta.unresolved` is rebuilt every run from `[module]`-tagged notes. Do not append to it by hand.

## Stage two, not yet

Alerts (`collector/notify.py` has Telegram/ntfy senders from oriz-ipo, unwired): evaluate the
rules in the old SKILL doc — record date within 30 days, IPO opens/closes tomorrow, quota stage
change — at the end of a run and send. Then a login (Cloudflare Access), then in-page AI via a
Worker holding the API key.
