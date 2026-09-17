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
work it top to bottom.

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
