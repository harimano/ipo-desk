# The gated site — Cloudflare Access in front of a Worker that serves `_site/`

GitHub Pages is public: anyone with the URL gets the page and every JSON under `data/`. This Worker serves the
same `_site/` build, but only to people who have signed in through **Cloudflare Access** (free up to 50 users):
they type their email, get a 6-digit code by mail, and are in for the session length you set. There is no
password anywhere, and no login code of ours to maintain — `worker.js` only verifies Access's signed token on
every request, so a removed or misconfigured Access application fails CLOSED (401 / 503), never open.

`deploy.yml`'s `cloudflare` job builds `_site` and runs `wrangler deploy` from this folder on every push to main and
after every collect. (While it was being set up it sat behind a repo variable `SITE_WORKER` so Pages kept serving;
that variable and the Pages job are gone.)

## Setup (about 20 minutes, all in the browser; nothing is pasted into chat or a file)

1. **Cloudflare API token** — dash.cloudflare.com → profile (top right) → My Profile → API Tokens → Create Token →
   template **Edit Cloudflare Workers** → keep it to this one account → Continue → Create. Copy it.
   **Account ID** — Workers & Pages → Overview: it is in the right-hand column.
2. **GitHub** — repo → Settings → Secrets and variables → Actions:
   - Secrets: `CLOUDFLARE_API_TOKEN` (the token), `CLOUDFLARE_ACCOUNT_ID`.
   Then Actions → deploy → Run workflow. The `cloudflare` job creates the Worker `ipo-desk-site`. Its URL
   (`https://ipo-desk-site.<your-subdomain>.workers.dev`) answers **503 "gate is not configured"** — correct: the
   Worker exists but will not serve until Access is in front and the two variables below are set.
3. **Zero Trust team** — dash → Zero Trust (left menu). First time it asks for a team name: that gives you
   `<team>.cloudflareaccess.com`, the **team domain** (later visible at Zero Trust → Settings → Custom Pages).
   Pick the Free plan.
4. **Put Access in front of the Worker** — Workers & Pages → `ipo-desk-site` → Settings → Domains & Routes →
   the `workers.dev` row → **Enable Cloudflare Access**. That creates an Access application for the Worker's
   address, with a policy that allows only your Cloudflare email. Then Zero Trust → Access → Applications →
   open it:
   - Policies → the policy: Action *Allow*, Include → **Everyone** (Hari's choice, 28 Oct 2026: the link is sent, the
     reader signs in with their own email and code, no list kept by hand — so a forwarded link also gets in; the
     sign-ins are listed by email under Zero Trust → Logs → Access, and an *Exclude → Emails* rule blocks one).
     The allowlist variant is Include → *Emails* with the addresses.
   - Overview / settings: **Session duration** — 1 month is fine for a family dashboard; **Application Audience
     (AUD) Tag** — copy it (it is an identifier, not a secret).
   - Authentication: *One-time PIN* is on by default; leave it as the only method.
5. **GitHub variables** — `ACCESS_TEAM_DOMAIN` = `<team>.cloudflareaccess.com` (no `https://`),
   `ACCESS_AUD` = the AUD tag. Run the deploy workflow again. (Both must exist from the first deploy on — wrangler
   refuses an empty var — so they start as the placeholder `pending`, which the Worker treats as "sign-in required".)
   `ACCESS_ADMIN_EMAIL` = the one address that may open `/admin` (the ops page, `site/admin/`; its README is the
   header of `scripts/audit.py`). Unset or `pending`, `/admin` is a 404 for everyone; any other signed-in email
   gets a 403. Set it with `gh variable set ACCESS_ADMIN_EMAIL --body <email>`.
7. **Visitors** — `/admin` lists everyone who has signed in, from two sources. Cloudflare's Access log (every email
   code completed or failed at the gate since it went up) is read by the Worker with a token that can only read
   Access audit logs: Cloudflare → My Profile → API Tokens → Create Token → Custom → permission *Account · Access:
   Audit Logs · Read*, your account → copy → GitHub secret `CF_ACCESS_LOGS_TOKEN`. The deploy uploads it (and the
   existing `CLOUDFLARE_ACCOUNT_ID`) to the Worker as secrets; without it the card says so and shows the ledger alone.
   The ledger is a KV record per signed-in email (first, last, page loads, country; a load counts at most once every
   ten minutes): namespace `ipo-desk-visits`, created once in the dashboard, id in `wrangler.toml`.

## Where this landed (28 Oct 2026)

- The Worker behind Access is the ONLY door to the page: GitHub Pages is switched off (repo Settings → Pages, and the
  `publish` job is gone from `deploy.yml`). The link to send is **`https://ipodesk.dev/`** (a custom domain on the Worker: Worker → Domains → Add Domain;
  the registrar is Cloudflare, ~$12 a year, WHOIS redacted). `ipo-desk-site.ipodesk.workers.dev` still answers — the
  account's workers.dev subdomain was renamed to `ipodesk` so no name is in it.
- The repo stays PUBLIC, by choice. The readers are a handful of friends; hiding the code would protect against a copier
  who does not exist, and a private repo loses GitHub's free Actions minutes (the market-hours live loop alone is
  ~240 min a day against a 2,000-a-month allowance). If that ever changes, the design is written down in
  HISTORY-2026-10 (28 Oct): whole repo private, the live loop ported to a Cloudflare Worker on cron with KV, collect +
  deploy staying on GitHub within the free minutes — after a reachability survey of NSE / InvestorGain from
  Cloudflare's addresses, which nobody has done.
- Consequences of public: `data/latest.json` and the history are readable on github.com's `data` branch, so are the
  research sheets on main and the Actions logs. Fine for this audience; the gate is about strangers and the page.
- `collect.yml` and the trigger Worker are untouched: data still lands on the `data` branch and `collect.yml` still
  dispatches `deploy.yml`, which now builds and deploys the Worker on every run.

## Per-reader state: `/api/state` (29 Oct 2026)

The token's email is also the key of each reader's own saved dashboard: `GET /api/state`, `PUT /api/state/<part>`,
`DELETE /api/state`, one D1 row per (email, part) — `SETUP.md` has the database step, the Access allow-list and the
local test route; `test/` has the cases (`node --test` in `ci.yml`, or `/__worker/test/harness.html` on the preview).
Nothing in a request names the reader: the Worker takes the email from the token it verified, only ever lower-cased.
