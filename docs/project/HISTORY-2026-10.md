# History — October 2026

The dated lessons, continued from `HISTORY-2026-09.md` (which holds the state of play, the roadmap and the rules
agreed in September). Newest section last. `CLAUDE.md` is the short working brief; this is the long story.

## 1 Oct 2026 — whole-system check

- Scheduling after the 27 Sep Worker fix: the Worker starts both live halves on time (03:25 / 07:25 UTC, `workflow_dispatch`)
  and intraday runs only on weekdays. But GitHub's fallback live cron still fired ~5 h late (~15:28 IST) and, with
  `cancel-in-progress`, killed the Worker's afternoon loop at the close. Now only a `workflow_dispatch` cancels; a scheduled
  start queues behind the running loop.
- Every module ok in the 06:43 full run except `offers` (BSE 403, known). One deploy failed on a Pages HTTP 500 (transient).
- Size: `latest.json` grew ~250 KB a day while `anchorbook` backfilled (3.5 MB 24 Sep → 4.9 MB; backfill done, 1,328 of
  ~1,352). The file is written indent=1; the published parts are compact (3.3 MB). `validate.py` now caps the compact size.
- Live loop vs NSE: report 566's stamps were 10:17–10:22 at 12:01 IST while NSE's board run said 11:10; NSE's
  `/api/ipo-current-issue` had fresher totals and an issue 566 lacked. InvestorGain also publishes absurd QIB multiples on
  SMEs with a near-empty QIB portion (Sollfege "1819000x") — it is their number, not a parse error. The page only lays a
  live value over a newer one, so the stale feed never overwrote NSE's.
- `listings`: 10 of 11 "no NSE symbol — cannot price" warnings were BSE-only rows the tape prices daily (noise, now
  suppressed via `tape.bse.names`); the 11th, board "ESDS Software", had no symbol while deals had resolved "ESDS Software
  Solution" → ESDS — `listings` now borrows it. Five board rows have a second series under the listing report's spelling.

- Test trap (22 Sep 2026): tests' FakeSession matches URL substrings — "EQUITY_L.csv" also matches the SME list URL; use full paths.
- Live loop moved to NSE first (Hari's call, 1 Oct). Survey: NSE's per-issue `/api/ipo-detail` gives mainboard a category
  split ~10 min old, but for SMEs it carries shares bid and no shares offered (no multiples) — the one-call
  `/api/ipo-current-issue` has their totals; for BSE-only SMEs NSE answers ZEROS, and BSE's own category-demand API (the
  one its page calls, `Pubissues_BBS_CumultveCatdem_ng`) shows "No Records Found" mid-issue — BSE does not publish it, so
  no route to BSE helps. InvestorGain 566 stays for those 11 issues only. First cut wrote NSE's zeros: caught by a live
  tick before shipping — the page would have blanked every SME book. Rule: an all-zero book is never written.
- Narada (trynarada.com, found via an unrelated public repo, sanketicfai/ipo-desk) — 1 Oct evening. Its `/ipos/<symbol>/
  subscription/` fragment (the site's own htmx swap) holds two tables: share-wise and application-wise, sub-rows marked by
  an indent span. For BSE-only SMEs it is the only fresh book (Black Opal closing day 73.88x vs IG 2.22x; Vans 628.78x vs
  93x). Board run: SMEs ask Narada first — NSE's ~4.5 s per-issue call returned zeros for every SME and cost 60 s a run
  (78 s → 16 s). Live: SMEs from Narada at most every 10 min an issue. Applications received per quota stored as `apps`.
- Logos (Hari liked them on sanketicfai's page, which hotlinks Narada's CDN). Option chosen: thumbnails we make and publish.
  InvestorGain's record already names the file (`logo_url`), served from chittorgarh.net/images/ipo/ at ~100 KB a PNG —
  too heavy to hotlink. `logos` fetches each once, 96x48 WebP (~1.3 KB; a square shrank the wordmarks to strips), 25 a
  run. First module to write files: `Result.files`, guarded to `logos/` and written only when the module succeeded.
- 2 Oct: real allotment odds by count shown beside the lower bound (Hari's call). First cut showed Nityas Gems "about 1 in
  3.8" beside "at least 1 in 1.3" — impossible (applications cannot outnumber lots bid). Cause: Narada's retail SLOT count
  for that mainboard issue was a 10% quota (7,178); the RHP's Max Allottees in the IG record says 25,123 (35%). Slots now
  come from the RHP where present; for SMEs Narada's slots check out (Black Opal 9,30,000 / 1,200 = 775) and the ratio
  equals the retail multiple (each SME individual applies for exactly the minimum). The page hides real odds that are
  worse than the book allows, rather than show a contradiction.

## 6 Oct 2026 — the morning the collector would not import

- Every collect run from ~04:30 UTC failed in 30 s: `ImportError: Modest backend is deprecated since selectolax 1.0`. The
  pin was `selectolax>=0.3.21` with no ceiling; 1.0 shipped and removed `selectolax.parser`, which all six HTML sources
  import. The collector did the right thing (every module failed → "refusing to write; previous latest.json stays live"),
  so the page simply sat on the 06:43 document. Not obvious from the run list: the 07:30 UTC scheduled run showed
  "success" because it was an intraday no-op. Lesson: when the page is stale, read the latest failure's import lines first.
- Fix in three commits, each proven on the runner: pin `<1` (back in business in 20 min) → migrate to lexbor (the test
  suite run with `selectolax.parser.HTMLParser` monkey-swapped for `LexborHTMLParser` before import, plus a Modest-vs-
  lexbor probe over the fragment shapes we parse: byte-identical) → lift the ceiling. venv now on 1.0.0, like the runners.
- The first good run was then refused by the gate: `players/covered: 30 -> 18 (40% loss)`. Thirteen issues had listed over
  5–6 Oct while runs were failing; `covered` is simply the unlisted set and every dropped id had moved into `frozen`
  (27 → 40). Exempted like `/players/books/<id>` already was; `frozen` stays gated and only grows, which is the real check.
- Ruff: 114 findings across collector/scripts, more in tests (ruff 0.16.8 from the dev extra resolves a broad rule set;
  nothing ran it in CI). Cleaned to zero over the whole tree. Decisions worth keeping: BLE001 off in `[tool.ruff.lint]`
  with the reason (all 20 sites record to `tried`, log, or re-wrap — a parser bug is a SourceChanged in disguise); five
  B023 closures bind their loop variable as a default (each only ran inside its own iteration); `v != v` stays as the
  numpy-NaN test; `NAME_STOP` stays prose. ruff now runs as the LAST step of `collect.yml` with `if: always()` — a lint
  slip turns the run red but the document is already committed and published. Code hygiene never leaves the board stale.
- Dependencies: `nse[server]` warned on every install (5.0.0 dropped the extra). Survey: neither `nse` nor `bse` is
  imported anywhere — `docs/mined/nse-bse.md` was the study of the libraries, the collector uses its own `http.py`. Both
  dropped (with mthrottle, an exact httpx pin, GPLv3). Tried to drop the three "smartapi extras" too: `python-dateutil`
  is declared by the SDK and went; `logzero` and `websocket-client` are imported by `SmartApi/__init__` and
  `smartConnect` at import time and NOT declared by the SDK — without them `_connect` degrades silently to SourceDown.
  Proven by removing each in the venv. They stay, with the reason beside them in pyproject.
- Docs: today's lessons went into CLAUDE.md (rule 9: dependencies are a run-time risk; two "how to build" bullets: a stale
  page is a failed run until proven otherwise, ruff must pass and runs last in CI; the covered/names exemption on the
  validate line). The history is now split by month: `HISTORY-2026-09.md` keeps September (state of play, roadmap, rules)
  under its own title instead of the brief's heading it had carried since the rebuild; this file starts at 1 Oct.
- `live.yml` got the same trailing ruff step (dev extra installed for it). Proving it is a day-structure question: a running
  loop keeps the workflow file it started with, so the step only exists on a job started after the push; a dispatch is the
  documented "new start replaces the running one" (one tick's gap). Started 15:41 IST; the Lint step runs when the loop
  ends at 17:20. A short `until` would have proved it faster but would have left the afternoon without a loop — never
  cut into market hours to verify a lint step.

## 16 Oct 2026 — four days of red runs, one day of a stale board

- Hari: "non-stop error emails and the whole desk isn't functioning". `gh run list` first: every `collect` and `live` run
  since 12 Oct red. Two causes, found in that order, both proven locally before any change.
- The emails (12 Oct on): the trailing Lint step. `ruff>=0.6` resolves to 0.17.1 on the runners (0.16.8 here) and 0.17
  reports RUF100 for a `noqa: DTZ007` when DTZ is not enabled — four of them. The step is last on purpose, so the data kept
  flowing for three days while every run mailed a failure; the design held (`cd37660`, 15 Oct 17:23 UTC, was a normal
  commit under a red run). Comments removed; venv on 0.17.1 like the runners.
- The stale board (16 Oct): the gate. `recent[]/sources: 64 -> 34 items (47% loss)`. `recent` is capped at 28 days
  (`schema.CAPS`); on the 16th the nine 17 Sep listings aged out together, carrying 30 of the list's 64 source tags (the
  September rows had 3–7 news links each, October's one). The rows were a 30% loss — exactly the limit, allowed — their
  summed sources 47%, refused. Same class as 19 Sep (board rows retiring) and 22 Sep (records leaving with them):
  `retire_due` now drops recent rows past the window from `prev`; a row vanishing early still counts. Reproduced with an
  intraday run into a scratch copy against the data branch, test added (310), full run dispatched: gate PASS, data
  `293660a`, deploy, live `asOf 16 Oct 21:33 IST`. Lesson for the gate: a summed nested list under a capped list ages out
  in lumps — whenever a cap is added to a list the validator compares, `retire_due` needs the matching cutoff.
- Then Hari: "I don't want 100 failure emails". The lint step's placement was the amplifier: it ran in every scheduled
  data run (~25 a day), so one ruff release was four days of mail. Code checks now live in `ci.yml` (ruff + pytest — the
  tests had never run in CI) on pushes to main: one red run per slip, seen once. `collect.yml` and `live.yml` no longer
  lint; their only failures are the board's. ruff pinned `==0.17.1`. Proven: ci.yml green on the first push (309 passed,
  1 skipped), an intraday collect dispatched on the edited workflow. What still mails: a real gate refusal repeats every
  intraday slot until fixed — that is the signal, but 20 copies of it a day is the next thing to tame.
- Tamed the same evening. Surveyed first: the Gate step fails with the validator's `FAIL — … · …` lines on stdout and
  nothing else records them; the Mode step runs before the install and already decides `go`; the Alerts step runs only
  after a commit, so it can never carry a refusal, and NTFY is unset anyway. So the refusal travels through the Actions
  API: `scripts/prev_gate.py` (runner python3 + gh, three calls, GITHUB_TOKEN) reads the last completed collect run; if
  it failed at the step named Gate on this same main commit, it pulls the FAIL lines from that job's log and prints them
  as one `::warning::` (run annotation + job summary), exit 3, and the Mode step sets `go=0`. Only exit 3 skips — an API
  error or a crash runs as usual, so a flaky API never silences the board; a failure in any other step (a network fault
  in Collect) is retried at the next slot as before. Full runs never ask, so the refusal is seen once per slot that
  matters: the failed run stays red, 06:43 and 18:13 retry and fail loudly, and a push to main (a fix) changes the sha
  and the next intraday goes too. Proven: both paths live from the Mac against the real runs (the 13:53 refusal reproduced
  verbatim), four tests (314), ruff, and one intraday dispatch on the edited workflow.

## 28 Oct 2026 — the gate, built and parked

Hari's dad and a friend now read the dashboard, and the Pages URL is public, so the first step of the roadmap's
"login" item was built: `ops/site-worker/` — a Worker serving `_site` (Workers static assets, `run_worker_first`) that
verifies Cloudflare Access's RS256 JWT (team certs cached an hour; `exp`, `iss`, `aud` checked) on every request and
fails closed without it. Access itself does the login (email one-time PIN, an allowlist of three addresses, free
plan); no password, no code of ours. `deploy.yml` gained a `cloudflare` job gated on the repo variable `SITE_WORKER`,
so Pages keeps serving until the switch; the README in the folder has the clicks and the switch-over list. The step
that actually hides the data is making the repo private — the Worker alone leaves `data/latest.json` readable on
github.com. Not pushed on the day it was written: the current readers were on the page. Not yet run anywhere (no
Node on the Mac; the first deploy is the Actions job).

Set up the same evening (28 Oct): secrets + variables on GitHub; Zero Trust Free activated (team `super-pond-6304`,
auto-named; a card is required even at $0); Access put in front of the Worker from its own **Access** tab ("Protect this
Worker behind Access", scope All traffic) with a reusable policy `ipo-desk readers` (Emails allowlist, 1-month session)
made under Zero Trust → Access controls → Policies — the two pre-configured policies the dialog offers are "Cloudflare
account" and "Email domain", neither an allowlist. A new Zero Trust org has only the Cloudflare login: **One-time PIN
had to be added** under Integrations → Identity providers before the login page offered "Send login code". Two deploy
lessons: wrangler-action's default wrangler 3 rejects `run_worker_first` (pinned 4.154.0), and it refuses an empty
`--var`, so the Access variables are `pending` until the real values exist. Unauthenticated: the Worker URL 302s to
the team login page. Pages still serves the public copy; the switch-over waits on the readers' emails being added.

Later that evening Hari chose self-service over an allowlist: the policy rule is Everyone. Access still makes each
reader sign in with an email code and remembers them a month; the link is the key. Verified signed in: the page loads
the live parts behind the gate, no console errors, `/whoami` prints the email.
