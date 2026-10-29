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

The account's workers.dev subdomain was renamed from Hari's name to `ipodesk` (one-time, from Workers & Pages → Overview →
Subdomain → Edit): the gated page is https://ipo-desk-site.ipodesk.workers.dev/ and the old name stops resolving at once.
Access followed the Worker (same AUD, same policy); the new name took about five minutes to answer. The trigger Worker
moved too, which changes nothing — it is called by cron, never by URL.

Decision, same evening: the gate is enough. Readers are a handful of friends, so the repo stays public and GitHub Pages
is switched off (the `publish` job and `pages` permissions removed from `deploy.yml`, Pages disabled in repo settings,
`SITE_WORKER` deleted — the `cloudflare` job now runs unconditionally). Considered and parked: whole-repo private
costs the free Actions minutes (live loop ~240 min/day vs 2,000/month); the fix would be the live loop as a Cloudflare
Worker on cron + KV, taking over the trigger's fifth cron slot, preceded by a reachability survey of NSE/IG from
Cloudflare's egress. Hosting on the Mac was rejected: it must run unattended. Cloudflare costs start at 50 Zero Trust
users a month ($7 a seat beyond) and 100k Worker requests a day (errors, not charges, beyond that).

ipodesk.dev, same evening: bought through Cloudflare Registrar ($8.20 the first year, renews $12.20; WHOIS redacted) —
the one paid line item, written into rule 7. Attached as the Worker's custom domain (Worker → Domains → Add Domain,
root, production); the certificate took about a minute and the Worker-level Access policy covers the new hostname (302
to the team login for ipodesk.dev, same AUD). The page's "Run ↗" link to the collector on GitHub is gone: it carried
Hari's GitHub handle and the repo to every reader, and the terminal / Actions tab do the same job. Checked: .in is not
sold by Cloudflare; .ai is $160 for two years then $80.

### 29 Oct — /admin, the ops page

Now that friends read ipodesk.dev, Hari wanted one place that says whether the site is up to standard — data fresh and
right, nothing broken on the page, the gate on — without opening Actions logs. `ipodesk.dev/admin` (`site/admin/`,
built by `site/build.py` into `_site/admin/`) is served by the Worker only to `ADMIN_EMAIL` (repo variable
`ACCESS_ADMIN_EMAIL`; unset = 404, anyone else = 403). It opens on one verdict line ("Nothing needs you" / "N things
need a look", each item linking to its card), five tiles (document written, live loop, last collect, last deploy,
smoke test), then Runs, Freshness by module, Since the previous document, Data audit, the smoke test, Security, links.

The facts come from `scripts/audit.py`, run by every build from the same document the page shows, into
`admin/audit.json`: per-module level (ok / fallback / known gap / bad), the diff against the newest earlier
`data/history` file (rows in and out — a Listed row leaving on schedule is "retired", anything else "left early" —
status moves, source switches, evidence warnings that came or went, counts), and soft anomalies the gate does not
refuse (Open past its close, Upcoming past its open, Listed with no price, an empty book on day two, dates out of
order, a logo named but absent). The browser adds only time-since: the document's age against collect.yml's crons,
the live branch's last commit against market hours, and GitHub's public runs API (the repo is public, no token, 60
calls an hour per address — a visit costs about four; the page says when the limit resets). The run list tells cron
from dispatch, so a trigger Worker that stopped dispatching shows up. The smoke test is CLAUDE.md's pre-ship check as a
button: the page loaded in a hidden same-origin frame with an error tap injected ahead of its scripts, all seven tabs
clicked, every `#rsel` option fired, `__ipo.live()` called, every data part HEAD-checked; 34 sheets in 1.1 s locally.

Found while building it: an intraday run replaced `integrity.checks` with the three modules it ran, so the full run's
statuses (tape, anchorbook, offers blocked) vanished from the document at 09:37 every day. `assemble.stamp` now carries
forward the checks of modules that did not run, marked `carried` with their own asOf. Also seen: every run carries
GitHub's notice that `ubuntu-latest` moves to Ubuntu 26 from 19 Oct 2026 — the runner should be pinned before an image
change breaks an install (not done in this change). Deploy copies `data/history` into the build for the diff.
Not built: the gate's own verdict beside latest.json (validate.py still speaks only in the Actions log) and a visitor
log in KV — both listed as phase 2.

Same afternoon, first live look: three "?" tiles. The page's own calls to api.github.com are unauthenticated — 60 an hour
per address, and the survey from Hari's network had spent them. So the deploy now snapshots the run list and the live
branch's last commit with the Actions token (`scripts/runs_snapshot.py` → `admin/runs.json`, at most one run old since
every collect deploys), the live loop is read from raw live.json (no call limit, cached five minutes), and the browser's
GitHub call only freshens the list when it can. The headline tiles never depend on a rate-limited call again.

Later: Hari asked to see all users. Cloudflare's Access log has every sign-in (Zero Trust → Logs → Access); the
page now has a Visitors card too — the Worker keeps a KV ledger (`VISITS` binding, one record per email: first, last,
loads, country; written only on a page load, at most once every ten minutes a person, in `ctx.waitUntil` so it never
delays a response) and `/admin/visitors.json` lists it. The binding is optional and off until Hari creates the
namespace and uncomments the block in `wrangler.toml`; absent, the card explains the setup. This is the KV the
login + Book sync work will reuse.
A deploy step that found or created the namespace with the deploy token was pushed, then taken out at Hari's ask:
he created `ipo-desk-visits` in the dashboard himself and the id sits in `wrangler.toml`, plain to read. Lesson for the
desk: an explicit id in a committed file beats deploy-time magic he cannot see.

"It's not showing the people that already visited" — of course: the ledger began that minute. The Worker now also reads
Cloudflare's Access log (`/accounts/<id>/access/logs/access_requests`, last 1,000 records, cached a minute) with a token
that can only read Access audit logs — GitHub secret `CF_ACCESS_LOGS_TOKEN`, uploaded to the Worker by `deploy.yml`
with `wrangler secret put` only when it exists, so a missing secret is a note on the card, never a failed deploy — and
merges it with the ledger: one row per email, sign-ins and failed attempts from Access, page loads from KV.

Hari: "the runs need to scroll, too long a page — a dashboard, each card to see it all". The page is now a grid
(four columns at 1,500 px, one on a phone), every card scrolling inside itself at 28% of the screen height, the
verdict and tiles above: one screen, no page scroll on a 900 px display.

That grid was "by far the worst design, so unusable": four narrow columns, every line wrapping. Redone as tables —
one line per run, module, change and visitor, columns aligned, ellipsis with the full text on hover — in two wide
rows (Runs | Freshness; diff | audit | Visitors) and a short third (smoke test, security, links), six tiles above
with a Readers count. Shown as a screenshot and approved before the push. Lesson: a dashboard is tables, not cards
of prose; and show the picture first.

The push of that layout carried two commits from another session working on the `friends-ready` branch in the same
checkout (a per-reader saved dashboard on D1, unfinished: its ci step failed) and deployed them. Rolled back at
Hari's word: main re-pointed at the layout commit alone, the other work left on its branch. Two sessions in one
working copy are two writers on the same files; the second should have had its own worktree.

Brand pass on /admin, at Hari's ask: the page's own palette and pieces (the blue mark and top bar, pills, --el
shadow, radius 14), a verdict banner tinted by state, tiles with a state stripe, colour-dotted card headers, chip
links, row hover. Light and dark screenshots approved before the push. Pushed from a separate worktree off
origin/main — the shared checkout sits on another session's branch.

## 29 Oct 2026 — friends-ready: accounts (branch `friends-ready`)

The desk opens to a small group. Each reader's state (stars, held parents, applications, done / snoozed, tasks, followed
investors, theme) moved from this browser's un-namespaced `ipo-*` keys to an account: `site/src/account.js` keeps the
parts, caches them per email (`ipo-u:<email>:<part>`), PUTs each changed part to the Worker after 600 ms with a retry at
2 → 60 s, and paints a Saved / Saving / Not saved pill in the header with the account menu (email, export, restore,
reset, sign out) behind it. The Worker (`ops/site-worker/worker.js` `handleApi`) keys everything by the email of the
Access token it already verified; D1 table `user_state(email, part, body, updated)`; the binding is a commented block in
`wrangler.toml` until Hari creates the database (`SETUP.md`), and without it `/api` answers 503 while the page keeps a
local copy and says so. Chosen over KV: KV's free tier is 1,000 writes a day shared with the visitors ledger and reads
can lag a minute across edges; D1 is consistent and allows 100,000 row writes a day.

Decisions: a PUT replaces a whole part (lists of tens of names; idempotent, retry-safe, last writer wins per part) rather
than PATCHing records. Tab, research sheet and "since you last looked" stay per device. The theme syncs (the only
setting). On sign-out the cached identity is forgotten so the next person on a shared device never paints from it.
Legacy keys are offered once for import, then renamed `ipo-legacy-*` and never read again.

Also: the footer is built from `meta` + `integrity` (last run, sources, unverified count); the 15 hand-written
`marketNotes` / `newFindings` / `quotaSourceNote` the collector carries forward sit folded in a "notes archive" (the
collector was not touched — the brief said so). Every screen has a "data as of HH:MM IST" stamp with a "feed N late"
pill when the document is older than the timetable allows (75 min on a weekday 09–18 IST, else 14.5 h). The privacy
sweep of `_site` found no PAN / demat / phone / personal positions; the author's first name in three code comments is
gone. `boot_old.js` and the always-hidden flows "Source note" are gone. The header overflowed below 1340 px once the
pill was in it: the command bar's hint hides under 1400 px and the tabs wrap under 1180 px. A pre-existing phone bug:
the queue card's one-column rule sat before the base `.q` rules and lost, so titles wrapped one word a line.

Testing without Node (none on the Mac): `scripts/preview.py` serves `_site` with an in-memory `/api` keyed by a dev
cookie (`/dev/as/<email>`); `ops/site-worker/test/cases.mjs` signs real RS256 tokens with WebCrypto against a stubbed
certs URL and an in-memory D1 — 32 cases, run in the browser (`harness.html`) and by `node --test` in `ci.yml`.
That grid was "by far the worst design, so unusable": four narrow columns, every line wrapping. Redone as tables —
one line per run, module, change and visitor, columns aligned, ellipsis with the full text on hover — in two wide
rows (Runs | Freshness; diff | audit | Visitors) and a short third (smoke test, security, links), six tiles above
with a Readers count. Shown as a screenshot and approved before the push. Lesson: a dashboard is tables, not cards
of prose; and show the picture first.

## 29 Oct 2026 — launch polish (branch `launch-polish`, on top of friends-ready)

Three things a friend needs on day one, mocked first and approved as pictures. **How to read this desk** (`intro.js`):
seven steps, one idea each, a static picture of the real element and a "where" line — Today, GMP, odds and EV, the
book, quota, "five sources, one desk" (Hari: "we are a data aggregator, show the perks"), evidence never a verdict.
It opens once per device (flag `intro`, in the account's local cache so a shared device does not hide it from the next
person) and again from the account menu or the footer. Hari asked for a flow in a few steps, not the six-term sheet
first mocked, and parked hover explainers until the platform is done. **Wrong number?** (`report.js`): a line under
every Today card and Board detail opens a three-field form in place; `POST /api/report` stores it in D1 `reports`
under the verified email (20 a reader a day), pings `NTFY_TOPIC` when the Worker has it, and `/admin` lists them. A
report never changes a figure. **Add to home screen** (`install.js`): a web manifest and PNG icons drawn once with
Pillow (`site/src/icons/`), linked with `crossorigin="use-credentials"` so the manifest fetch carries the Access cookie.
No service worker (the plan wanted no offline copy), so Chrome offers Install only from its own menu and never fires
`beforeinstallprompt` (developer.chrome.com/blog/update-install-criteria); the card shows the device's own steps instead
of a button that cannot work. Verified in the preview: no console error on seven tabs and 34 sheets, phone width with
no horizontal scroll, the Worker harness, the admin card.

### 29 Oct, evening — merged and live

PRs 3 (accounts), 4 (launch polish) and 5 (trust strip, built in its own session on Sonnet from a brief) were merged
into main in order with merge commits, each retargeted to main after the one below it landed. Hari created the D1
database in the dashboard (APAC) and gave the id in chat; it sits in `wrangler.toml` in plain sight, the deploy
accepted it without a token change, and Hari confirmed the Saved pill green on ipodesk.dev. The Access policy is
still Everyone and `NTFY_TOPIC` is still unset.

### 29 Oct, late — the planner lands, and a deploy that refused its own new key

PR 6 (capital planner and calendar: the `planner` module's `calendar` part and `planner.js` on Today, built in its own
session from a brief, mockup approved by Hari) and PR 7 (`iso()` built the date in UTC, so after 05:30 IST "today" was
still yesterday; now local getters) merged into main after a readiness check. The deploy then failed at its own gate:
`validate.py` now lists `calendar` as required, and the document on the data branch was the old collector's, without it.
`deploy.yml` validates that document before publishing, so it refused and the live site stayed on the previous deploy.
One dispatched `collect.yml` run wrote the part and dispatched the deploy; both green. Lesson: **a change that adds a
required top-level key must be followed by a collect run before any deploy** (a push to main triggers deploy first,
and it validates yesterday's data). Either dispatch collect right after the merge, or make the key required only once
`--prev` has it.

### 29 Oct, night — Access stays Everyone; the ntfy ping, and the newline that ate it

Hari decided the Access policy stays *Everyone* with a one-month policy session: the link is the key. He set the
`NTFY_TOPIC` secret (the first topic name was printed into the chat by accident and treated as burned; a second was made
in his terminal and never pasted). The deploy handed the secret to the Worker, a "Wrong number?" report said Sent, and no
ping came. A curl straight to the topic from the Mac arrived, so ntfy and the phone were fine and the Worker was the
broken link: it put `env.NTFY_TOPIC` into the URL untrimmed, so a trailing newline from the paste became `%0A` and the
ping went to a topic nobody reads; the collector's `notify.py` had always stripped. The Worker now trims, keeps the
Title header to ASCII (fetch throws on a non-Latin-1 header value) and returns the ping's HTTP status, with a case in
the harness (42). Re-tested live: the ping arrived. Lesson: **a value read from a secret is `.trim()`ed at the point
of use, in every runtime, not only the Python one.**

## 30 Oct 2026 — Phase 4 ops: the backup, the restore, readers by week (branch `vibrant-boyd`)

- **The backup is a GitHub job, not a Worker cron.** The survey's one decisive fact: the Workers Free plan allows
  five cron triggers per ACCOUNT (developers.cloudflare.com/workers/platform/limits/), and the trigger Worker has held all
  five since 18 Sep (a sixth failed that deploy). So `backup.yml` runs at 02:51 IST on GitHub's cron — best-effort,
  which a nightly copy tolerates — with `wrangler d1 export --remote` and `wrangler r2 object put` on the existing deploy
  token: no new secret, nothing in the Worker's request path. One `nightly/<IST date>.sql` a night in R2
  `ipo-desk-backups`; the keys dated 31–37 days back are deleted, so a missed night never leaks a file. The bucket's
  name sits in `wrangler.toml` as a `[vars]` entry beside the D1 id — the Worker never touches the bucket (no binding),
  but `/admin` and the workflow read the name from the one place. R2 free: 10 GB, 1 M class-A ops a month.
- **Restore is Python over the D1 REST query endpoint** (`scripts/restore_d1.py`): no Node on the Mac. Quote-aware
  statement splitter (a reader's note may carry `;` or a newline), batches of 40, `CREATE TABLE` made `IF NOT EXISTS`,
  `--replace` drops the dump's tables first, and the id in `wrangler.toml` is refused without
  `--i-mean-the-live-database`. Tested against a SQLite-backed stand-in of the endpoint (`tests/test_restore_d1.py`);
  a real run into a scratch D1 is still to do. D1's own Time Travel (7 days on Free, in place) is written down as the
  first resort — the dump is the copy outside the database.
- **Daily active readers**: `daily_active(day, email_hash)`, one `INSERT OR IGNORE` per reader per IST day on a page
  load, behind a per-isolate set — one D1 write a day a reader against the free 100,000. The hash is
  `SHA-256(DAU_SALT + "\n" + email)`, the salt a Worker secret `deploy.yml` hands over when the GitHub secret exists
  (the `NTFY_TOPIC` pattern, trimmed at use); no salt, no row, and the card says so. `/admin/retention.json` → the
  *Readers by week* card: eight Monday-start IST weeks, active / new / of-week-1's, counts only. The bottom rows of
  `/admin` widened (Wrong numbers c4→c6; smoke, security, links c4 each) so the rows stay full — the only layout change.
- `SETUP.md` gained §1c (bucket clicks, the restore walk-through, the salt), §4 (rollback: the Deployments page or
  `wrangler rollback`, 100 versions, bindings untouched, secrets survive) and §5 (removing one reader: the two
  `DELETE`s, the KV key, the dumps' 30-day tail, the Access exclude rule). `scripts/preview.py` now emulates
  `/admin/retention.json` and `/admin/me.json`, so the card renders on the preview.
- Verified: 53 Worker cases green in the browser harness; ruff and pytest green. Not verified until Hari acts: the
  bucket exists, the first backup file is in it, `DAU_SALT` is set and the card fills.

### 29 Oct, late night — Phase 4 live: the first backup is in the bucket

PR 8 (nightly D1 backup to R2 as a GitHub Action, since the account's five free Worker crons are all the trigger
Worker's; restore script; salted daily-active rows; the "Readers by week" card on /admin) merged and deployed. Hari set
`DAU_SALT` from his terminal in one command (generated and sent to GitHub, never printed), created the bucket
`ipo-desk-backups` (APAC), and the first backup run failed at the export with Cloudflare's "Authentication error
[code: 10000]": the deploy token, from the Edit Workers template, could bind D1 but not export it. He added
**Account · D1 · Edit** to the token (R2 Edit was already in the template, which is why the picker greyed it); the
re-run exported 4 rows and put `nightly/2026-10-29.sql` in the bucket, and the prune step's deletes of non-existent
older keys were harmless. Lesson, now in SETUP.md: **the deploy token needs D1 · Edit before the first backup**; a
new resource is the token's permission as much as the dashboard's click.
