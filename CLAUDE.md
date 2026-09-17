# CLAUDE.md — read this first

This repo is the India IPO Command Center rebuilt as a standalone site: a deterministic collector
on GitHub Actions writes `data/latest.json`; a static page reads it; Claude contributes research
into its own directories and is never in the daily path. `README.md` has the architecture and the
seven rules the code enforces. `docs/MODULE-CONTRACT.md` is how a module is written.
`docs/DATA-SCHEMA.md` is the document shape. Do not change the schema — the page renders it.
`docs/mined/` holds the notes taken from the reference repos (endpoints, response shapes, parser
patterns) — check there before guessing at a field name. `docs/project/tooling-survey.md` is why each
source was chosen; `docs/project/legacy-briefing-rules.md` has the stage-two alert rules.

## Where this was built, and what that means

Built 17 Sep 2026 in a cloud sandbox with **no network access to any market site**. Everything
below was written from mined notes on seven reference repos, not from live responses. The 170
tests run against hand-made fixtures. The collector has never completed a successful run. That is
the first job.

**Verified:** the architecture (assembler ownership, fail-loud, carry-forward, exit 2 on total
failure) — proven by running the collector with every source blocked. The site boots, fetches and
upgrades — proven headless. The migrated `data/latest.json` passes the validator.

**Guessed, must be checked against a real response before trusting:**
- `collector/sources/nse_ipo.py` — NSE list field aliases; `ipo-detail` `bidDetails` shape.
- `collector/sources/bse_issues.py` — `GetPublicIssue_par_updated/w` param spellings and the
  date/platform value formats (`flag=1&status=&exchange=&ir_flag=IPO` came from a note).
- `collector/sources/parents.json` — BSE scrip codes: only RELIANCE 500325 is confirmed; the
  other seven are marked `# verify`. Wrong codes silently poll the wrong company.
- `collector/sources/rss.py` — ET and Moneycontrol feed URLs are from memory.
- `collector/sources/investorgain.py` — the v2 URL and `reportTableData` field; v1 died in
  July 2026 with `{"msg":"API not found"}`, v2 may follow.
- The chittorgarh subscription-report parser (report 21) — column positions.
- Board rows migrated from the db era have no `symbol` field; `listings` cannot price them until
  `calendar` has run once and set it. Expected on the first run.

## First session, in order

1. `gh repo create ipo-desk --public --source . --push` (or push to the repo Hari made). This
   triggers `.github/workflows/reachability.yml`. Read its output: it says which sources answer a
   GitHub runner. If NSE JSON is blocked there, the cron moves to Cloudflare Workers — but check
   from the Mac first, because a residential IP is a different answer.
2. `python scripts/reachability.py` from the Mac. Then `python -m collector --only calendar -v`
   and read the actual NSE JSON in the logs. Fix `nse_ipo.py` field names against it. Repeat per
   module: `subscription`, `gmp`, `filings`, `flows`, `deals`, `news`, `parents`, `listings`.
   Every fix that changes a parser gets a fixture updated from the real response and a test.
3. Verify the seven BSE scrip codes in `parents.json` (BSE's `PeerSmartSearch/w` or the `bse`
   package's `getScripCode`). Remove the `# verify` markers only when confirmed.
4. A full `python -m collector`, then `python scripts/validate.py data/latest.json --prev <the
   committed one> --max-age-hours 2`, then `python site/build.py`, then `python
   tests/render_check.py`. Commit only when all four are green.
5. Repo settings: Pages → Source → GitHub Actions. Secrets: `ANGEL_API_KEY`,
   `ANGEL_CLIENT_CODE`, `ANGEL_PIN`, `ANGEL_TOTP_SECRET` (Hari has the account; SmartAPI portal
   issues the key; the TOTP secret is the enrolment string, not a code).
6. Let `collect.yml` run on its schedule. Three clean scheduled runs before calling stage one done.
   Watch `integrity.checks` in the committed `latest.json` — `stale`/`blocked` rows say which
   source needs attention.

## Rules for working here

- Never edit `data/latest.json` by hand and never commit one that `validate.py` rejects. The
  deploy guard fails any commit to it not authored by `ipo-desk-bot`.
- Research goes in `data/research/<slug>.json` with `name` matching the board row exactly and
  `kind: "current"` (issue sheet) or `"sheet"` (quota parent). Clause readings go in
  `data/quota-reviews/`. The sweep writes `data/investors.json`. Nothing else.
- A parser that gets an empty or unexpected response raises `SourceChanged`. It never returns
  `[]` as success. Keep that property when fixing parsers.
- Retries are for network faults only. Never retry a 403 — it flags the IP.
- Trendlyne (the MCP) is a snapshot database with a fuzzy matcher: never use it for a stock that
  listed today, never more than one NSE code per call, always check the returned symbol matches.
- Row `name`s are keys the viewer's browser depends on. Match to existing names; never rename.

## Stage two, not yet

Alerts (`collector/notify.py` has Telegram/ntfy senders from oriz-ipo, unwired): evaluate the
rules in the old SKILL doc — record date within 30 days, IPO opens/closes tomorrow, quota stage
change — at the end of a run and send. Then a login (Cloudflare Access), then in-page AI via a
Worker holding the API key.
