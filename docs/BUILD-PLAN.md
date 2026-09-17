# Build plan for Claude Code — what to fix, what to rebuild, what to add

An honest list, written by the session that built this repo. Everything is ordered by "what makes
the site live and trustworthy soonest". Do not start a tier until the one above it is done; a
beautiful page over a collector that has never completed a run is the mistake the db era made.

## Tier 0 — make it real (the first two or three sessions)

**Every parser is unverified.** All nine modules were written from notes on other people's repos,
never from a live response. Expect most of them to be wrong in small ways (a field renamed, a
date format, a nested key). The fix loop for each module is the same: run it with `-v`, read the
raw response in the log, correct the parser, capture the real response into `data/fixtures/` and
update the test. Build a small helper first so this loop is fast:

- `scripts/record_fixture.py <source> <name>` — call a source through the collector's `Session`
  and save the raw body to `data/fixtures/<source>/<name>.<json|html|csv>`, redacting nothing but
  noting the date. Tests then run against real bodies, and a source that changes shape is caught
  by re-recording and diffing. This single tool is worth more than any other item on this page.

**Reachability decides where the cron lives.** If `reachability.yml` shows NSE JSON blocked from
GitHub runners but working from the Mac, do not try to outwit Akamai. Options in order: rely on the
BSE fallbacks for a week and see what the board looks like; move the cron to a Cloudflare Worker
(different egress pool, free tier is enough); a ₹300–400/month Indian VPS running the same
`collect.yml` steps via cron. Never the Mac — it sleeps.

**BSE scrip codes.** Seven of the eight in `collector/sources/parents.json` are marked `# verify`.
A wrong code silently polls the wrong company's filings, which defeats the quota radar entirely.

**Angel One.** `sources/angelone.py` has never logged in. The instrument master is a ~100 MB JSON
downloaded on every run; cache it by date in the workflow (actions/cache keyed on the date) or
fetch it once and filter. Check the TOTP flow works from a runner before trusting listing prices.

## Tier 1 — things I built adequately that Claude Code should rebuild properly

**The repo will bloat.** `collect.yml` commits `data/latest.json` (430 KB), `data/history/<date>.json`
(another 430 KB) and a rebuilt `index.html` (200 KB, with the whole snapshot embedded as FALLBACK)
twice a day to `main`. That is ~2 MB of history a day, on the branch humans work on. Better:
commit collector output to a `data` branch (or an orphan branch) and have `deploy.yml` assemble the
Pages artifact from `main` (site) + `data` (documents); or keep `latest.json` in git but publish
`history/` as a GitHub Release asset per month. Also stop rebuilding `index.html` in the collector:
build it in the deploy job and never commit it. The FALLBACK snapshot can shrink to `meta` +
`mainboard` + `sme` + `quota` — the page only needs enough to paint before the fetch returns.

**The document is one 430 KB blob.** The page fetches everything on every load and every hourly
refresh. Split the collector's output into per-screen files (`data/board.json`, `data/pipeline.json`,
`data/market.json`, `data/research.json`, `data/book.json`) plus a tiny `data/meta.json` with
`asOf` and a hash per file; `boot.js` fetches `meta.json`, then only files whose hash changed.
`listedPerf` and `comps` (history, 400 rows each) belong in a separate file that loads on demand.
`docs/DATA-SCHEMA.md` stays the logical schema; this is only the physical layout. Keep
`validate.py` running on the assembled whole.

**`site/src/app.js` is 108 KB of db-era render code in one file.** It works and it renders six
screens, but it was grown across many sessions by a model writing into a single `<script>` block:
global state, string-built HTML, `innerHTML` everywhere, no modules, no tests beyond a headless
smoke check. Rebuild it as ES modules (one per screen, a shared `format.js`, a `store.js` for
localStorage) with a tiny bundler-free build (concatenate in `site/build.py`, or move to Vite if
you prefer). Non-negotiable while doing so: the localStorage keys `ipo-interest`, `ipo-holdings`,
`ipo-investors`, and the `lot`/`priceHistory`/application bookkeeping keyed by row `name`, must
survive unchanged — Hari's stars and applications live there. Screenshot every screen before and
after and compare. Chart.js comes from a CDN; vendor it or replace with inline SVG charts so the
page has zero external dependencies.

**`filings` classifies by headline keyword.** "DRHP", "draft red herring", "initial public offer",
"subsidiary" in a Reg-30 headline sets `needsReview`. That is the right first filter but it will
both miss (a headline that says "Intimation under Regulation 30" with the substance in the PDF) and
false-positive (a parent announcing someone else's IPO). Rebuild as: headline filter → download the
attachment → `collector/pdf/clause.py` on the first three pages → classify on the extracted text.
Still deterministic, still no AI in the path.

**`collector/pdf/clause.py` is a regex.** It finds "Eligible Shareholder(s)" and returns the
surrounding paragraphs. Good enough to hand to Claude for a reading; not good enough to set
`quotaPct` on its own. Improve with the bookmark walk from ipo-radar (`docs/mined/ipo-radar.md`):
jump to "The Offer" / "Offer Structure" / Definitions, then regex within those sections only.

**Name matching is `normalise()` + exact.** Sources spell issuers differently ("ESDS Software
Solution Ltd" vs "ESDS Software"). `rapidfuzz` is already a dependency; use `token_set_ratio ≥ 90`
as the second pass, log every fuzzy match, and refuse below threshold rather than creating a new
row. Never let a fuzzy match rename an existing row.

**`validate.py` delta check is per-collection count.** Add per-row invariants that catch the
subtle failures: an Open issue with `sub.total` lower than yesterday; a Listed row with no
`listingPrice`; a `quota` row whose `stageDate` moved backwards; `gmp` for a name not on the board.

## Tier 2 — data the collector does not collect yet (sections currently carried forward)

| section | today | what to build |
|---|---|---|
| `anchors[]` | carried from the db era, never refreshed | the evening before an issue opens, fetch the anchor allocation from the BSE/NSE announcement (PDF) or ipowala/investorgain 551; parse investor name, category, amount. The page's anchor-quality score depends on `investors[]` being filled |
| `offers` (rights / buyback / OFS / NCD) | carried | ipowatch calendars (`docs/mined/endpoints.md`); BSE corporate-actions API for record dates. Drop closed windows |
| `expected[]` | carried | SEBI `smid=10/11` diff already feeds `filings`; the same diff for non-subsidiary names (size ≥ ₹1,000 cr) populates `expected` |
| SME board | `calendar` handles `isBse`/Emerge flags but SME subscription and GMP were never checked | verify NSE Emerge + BSE SME endpoints; ipowatch SME pages as fallback |
| `flows.monthly`, `flows.rotation` | carried | NSDL fortnightly sector data; month-end roll-up from `flows.history` is pure arithmetic |
| `investors.moves[].priceNow` | never refreshed | `parents` already prices eight tickers via yfinance; extend to every stock in `moves[]` and `holdings[]` |

## Tier 3 — the AI layer, done properly

Today Claude contributes only when Hari asks in a chat. Make it routine without putting it back in
the blocking path:

- **`research.yml`** — a workflow triggered after a successful collect that diffs the board, finds
  names with no `data/research/<slug>.json`, and runs `claude -p` (Claude Code headless, with an
  `ANTHROPIC_API_KEY` secret) with a prompt that reads the ipowatch page and the RHP and writes the
  sheet. It opens a pull request, never commits to `main`; `deploy.yml` validates it like any
  other change. If it fails, the board renders "not yet researched" and nothing else is affected.
- **`quota-review.yml`** — same shape, triggered when `filings` sets `needsReview`: download the
  PDF, run `clause.py`, hand the extract to `claude -p`, write `data/quota-reviews/<slug>.json`,
  open a PR. Hari merges after a glance.
- **The Monday sweep** — Trendlyne is a claude.ai MCP connector, so this stays in Cowork for now.
  If Claude Code can reach the same MCP (it can be configured as an MCP server), move it to a
  `sweep.yml` on the same PR pattern and retire the last Cowork task.

## Tier 4 — stage two as Hari defined it

1. **Alerts.** `collector/notify.py` has Telegram and ntfy senders (from oriz-ipo, MIT). Evaluate
   the rules in `docs/project/legacy-briefing-rules.md` against previous vs new document at the end
   of a run; send one message, ≤ 6 lines, action first. Secrets `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID` or `NTFY_TOPIC`. Add a `--dry-run` that prints what it would send.
2. **Login.** Cloudflare Access in front of the Pages site (free for up to 50 users, email OTP)
   keeps the site static and needs no code. Do this before sharing the URL with family.
3. **In-page AI.** A Cloudflare Worker holding the API key, exposing one endpoint the page calls
   with the current row and a question; the Worker fetches the research sheet and answers. Scope
   it to "explain this row", not free chat.
4. **The Book screen** (holdings, applications, P&L) lives in localStorage on one browser. If Hari
   wants it across devices, that is the first thing that needs a backend — a Worker + KV keyed by
   the Access identity is enough. Not before login.

## Things not to do

- Do not add a database. A JSON file in git, validated in CI, with 45 days of restore points, is
  the whole point.
- Do not put Claude back between a source and `latest.json`. The three AI workflows above write to
  their own directories through pull requests.
- Do not rename row `name`s, ever, for any reason — write a `data/aliases.json` if a source needs a
  different spelling.
- Do not retry a 403. Do not scrape chittorgarh or Trendlyne HTML from a runner; both block it and
  flag the IP.
