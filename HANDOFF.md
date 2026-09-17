# Handoff — paste this as the first message in Claude Code

> Read CLAUDE.md, README.md, docs/MODULE-CONTRACT.md and docs/DATA-SCHEMA.md before touching anything.
>
> This repo was built in a sandbox with no network to any Indian market site. The architecture is
> proven; every parser was written blind from the notes in docs/mined/. Your job in this session is
> to make the collector complete one real run, then get it running on GitHub Actions. Work through
> the "First session, in order" list in CLAUDE.md, one step at a time, and stop and show me the
> output between steps rather than pushing ahead.
>
> Ground rules that are not negotiable: never edit data/latest.json by hand; never retry a 403;
> never bypass scripts/validate.py; a parser that gets an empty response raises SourceChanged, it
> does not return []; row names are keys and never get renamed; Angel One credentials go in GitHub
> repository secrets only, never in a file, never in a log. The GitHub push token I give you is for
> the push only — do not write it anywhere.
>
> Start with step 1: confirm `pip install -e ".[dev]"` and `pytest` are green on this Mac, then
> `python scripts/reachability.py` and show me the table before we push.

## What you (Hari) need to have ready

- GitHub: an empty public repo named `ipo-desk` under your account, and a fine-grained personal
  access token with **Contents: read/write** and **Workflows: read/write** on that repo only. Revoke
  it after the first push; later pushes use your normal git credentials.
- Angel One SmartAPI: from smartapi.angelone.in create an app to get the **API key**; you also need
  your **client code**, **PIN**, and the **TOTP enrolment secret** (the long string shown when you
  enable TOTP in the SmartAPI portal — not a 6-digit code). These go into the repo's Settings →
  Secrets as `ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_PIN`, `ANGEL_TOTP_SECRET`. The collector
  runs fine without them; only listing-day prices fall back to yfinance.
- Python 3.11+ on the Mac. `gh` CLI is convenient but optional.
- Repo Settings → Pages → Source: **GitHub Actions** (do this after the first successful push, before
  the first scheduled run).

## What is in the box

| path | what |
|---|---|
| `CLAUDE.md` | the session brief: verified vs guessed, ordered first steps, rules, stage two |
| `README.md` | architecture, the seven enforced rules, source chains |
| `docs/MODULE-CONTRACT.md`, `docs/DATA-SCHEMA.md` | how a module is written; the document shape the page renders |
| `docs/mined/` | the notes taken from the seven reference repos — the evidence behind every endpoint and parser |
| `docs/project/tooling-survey.md` | why each source and library was chosen, with links |
| `docs/project/legacy-briefing-rules.md` | alert rules for stage two, key-stability rules, Trendlyne rules |
| `collector/` | the collector: 9 modules, http layer, assembler, validator hooks |
| `site/` | `inner.html`, `app.js`, `boot.js`, `build.py` → `index.html` |
| `scripts/` | `validate.py` (the gate), `reachability.py`, `migrate_from_db.py`, `seed_history.py` |
| `tests/` | 170 offline tests; `render_check.py` headless page check |
| `data/latest.json` | migrated from the db era, validator-clean, plus ipo-radar history seed |
| `data/research/` (17), `data/investors.json`, `data/seed/`, `data/fixtures/` | Claude-owned research, sweep output, seed, test fixtures |
| `.github/workflows/` | `reachability.yml`, `collect.yml` (cron), `deploy.yml` (guard + Pages) |

## What was retired on the Cowork side (17 Sep 2026)

- Daily and Monday-sweep scheduled tasks: disabled, not deleted.
- The NSE-IPO Monday one-off task: deleted.
- The db-era dashboard artifact and the 🧪 test artifact still exist; retire them once ipo-desk is
  live and you have looked at both side by side.
