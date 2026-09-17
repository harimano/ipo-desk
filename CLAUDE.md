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
completes 9/9 modules from GitHub Actions runners (16/17 sources reachable there; only ipopremium
403s), so the cron stays on Actions. `collect.yml` runs 06:45 and 18:15 IST.

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
`anchors`, `offers`, `expected`, `flows.monthly/rotation` are still carried forward (BUILD-PLAN Tier 2).

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
