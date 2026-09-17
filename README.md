# ipo-desk

The India IPO Command Center as a standalone site. A deterministic collector runs on GitHub
Actions twice a day and writes `data/latest.json`; a static page reads it. Claude contributes
research on demand into its own directories and is never in the path between the data and the
screen.

```
                collector (GitHub Actions, 06:45 + 18:15 IST)
  NSE ─┐          │  read previous latest.json
  BSE ─┤          │  run 9 modules, each primary → fallback, each fails alone
 SEBI ─┼──────────┤  validate.py — the gate; red = nothing committed
  GMP ─┤          │  write data/latest.json + data/history/<date>.json
 …   ─┘          │  rebuild index.html with a fresh fallback snapshot
                  ▼
        git commit as ipo-desk-bot ──▶ deploy.yml ──▶ GitHub Pages
                                        │
   Claude ──▶ data/research/ ───────────┤  guard: latest.json may only change
   Claude ──▶ data/quota-reviews/ ──────┤  under the bot's name
   sweep  ──▶ data/investors.json ──────┘
```

## What is where

| path | what | who writes it |
|---|---|---|
| `data/latest.json` | the whole DATA document the page renders | the collector, only |
| `data/history/YYYY-MM-DD.json` | daily restore points (45 days, Sundays forever) | the collector |
| `data/research/<slug>.json` | per-IPO research sheets (`kind: current`) and quota-parent sheets (`kind: sheet`) | Claude, on request |
| `data/quota-reviews/<slug>.json` | what a DRHP's shareholder-reservation clause says: `quota`, `quotaPct`, `confidence`, `source` | Claude, after reading a flagged PDF |
| `data/investors.json` | superinvestor holdings, moves, portfolios | the Monday sweep (Claude + Trendlyne) |
| `data/seed/` | ipo-radar's 2005–2026 dataset, reshaped; merged once at migration | — |
| `index.html` | the page, rebuilt every run | `site/build.py` |
| `site/src/` | `inner.html`, `app.js` (render), `boot.js` (fetch + refresh) | humans |
| `collector/` | the collector | humans |

## Running it

```
pip install -e ".[dev]"
python -m collector                      # full run against ./data
python -m collector --only gmp,calendar  # some modules
python -m collector --dry-run            # assemble, print integrity, write nothing
python scripts/validate.py data/latest.json --prev <previous> --max-age-hours 2
python site/build.py                     # -> index.html
pytest                                   # 170 offline tests against fixtures
python tests/render_check.py             # headless: boots, fetches, upgrades, no errors
python scripts/reachability.py           # which sources answer THIS machine
```

Secrets the collector reads (set as repository secrets; every one optional — a missing one just
means that source fails cleanly): `ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_PIN`,
`ANGEL_TOTP_SECRET`. Stage two adds `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` or `NTFY_TOPIC`.

## The rules the code enforces

These are properties of the code, not instructions in a prompt. That distinction is the whole
reason this repo exists.

1. **A module owns its keys.** `schema.OWNERS`, `ROW_PATCHERS`, `MERGE_PATCHERS`. The assembler
   aborts the run (exit 3) on a violation.
2. **A failed module changes nothing.** Its section is carried from the previous file and marked
   `stale` or `blocked` in `integrity.checks`, with the reason. An empty answer is a failure, not
   a success — parsers raise `SourceChanged` on zero rows.
3. **Nothing is written unless `validate.py` exits 0** — in CI as a step between collect and
   commit. The delta check refuses a >30% loss in any collection, and a `--prev` that resolves to
   nothing is an error, never a silent skip.
4. **If every module fails, nothing is written** (exit 2). The previous file stays live.
5. **Nothing hangs.** Every call has a timeout; retries are for network faults only, never for
   a 403; the whole run has a SIGALRM budget. A blocked source fails in seconds.
6. **Row names are stable.** Stars, applications and lot bookkeeping in the viewer's browser key
   off `name`. Sources are matched to existing names by normalisation; the board's spelling wins.
7. **`latest.json` is the bot's alone.** `deploy.yml` fails a push that changes it under any
   other author.

## Sources, primary → fallback

| need | chain | notes |
|---|---|---|
| calendar | NSE `/api/ipo-current-issue`, `all-upcoming-issues` → BSE `GetPublicIssue_par_updated` → BSE legacy table (beta host) | NSE primed via the issue-information page, not the homepage, which 403s from cloud |
| subscription | NSE `ipo-detail` bidDetails → BSE `CummDemandSchedule` → chittorgarh report 21 | NII sub-buckets summed once, never double-counted |
| GMP | InvestorGain v2 JSON → IPOWatch → IPOPremium (HTML, parsers from oriz-ipo, MIT) | v1 retired July 2026; v2 treated as fragile |
| listing prices | Angel One SmartAPI → yfinance `.NS` | Angel One has new symbols on listing morning; yfinance lags 0–2 days |
| parent prices | yfinance → Angel One | eight parents, one batch |
| filings (the quota radar) | BSE announcements per parent scrip + SEBI DRHP/RHP page-1 diff | Reg 30 intimations; classify by headline; flag `needsReview` for Claude |
| FII/DII | NSE `fiidiiTradeReact` | no second source exists; fails cleanly |
| bulk/block deals | nsearchives CSVs | watchlist + vehicle substring match |
| news | RSS | keyword-filtered |

`docs/tooling-survey.md` in the project has the evidence behind each choice.

## The AI layer

Claude writes three things, each to its own directory, each committed through git so CI
validates it like any other change:

- A **research sheet** when a new name appears on the board — `data/research/<slug>.json`,
  `kind: "current"`, `name` matching the board row exactly.
- A **clause reading** when `filings` sets `needsReview` on a quota row — run
  `python -m collector.pdf.clause <pdf>` to get the candidate text, read it, write
  `data/quota-reviews/<slug>.json` with `quota`, `quotaPct`, `confidence`, `source`.
- The **Monday sweep** — `data/investors.json`.

None of it is in the daily path. A missing sheet renders as "not yet researched."

## Provenance

Built 17 Sep 2026 from the db-era Command Center after two scheduled Claude runs hung without
writing. Patterns and endpoints learned from Vasuki8/IPO-Tracker, bebhuvan/ipowatch-co,
awesome-et/IPOFetch, rohanbeingsocial/ipo-radar and BennyThadikaran's `nse`/`bse`; GMP parsers and
notify senders vendored from chirag127/oriz-ipo (MIT, see `THIRD_PARTY.md`).
