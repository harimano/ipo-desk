# The gated site — Cloudflare Access in front of a Worker that serves `_site/`

GitHub Pages is public: anyone with the URL gets the page and every JSON under `data/`. This Worker serves the
same `_site/` build, but only to people who have signed in through **Cloudflare Access** (free up to 50 users):
they type their email, get a 6-digit code by mail, and are in for the session length you set. There is no
password anywhere, and no login code of ours to maintain — `worker.js` only verifies Access's signed token on
every request, so a removed or misconfigured Access application fails CLOSED (401 / 503), never open.

`deploy.yml`'s `cloudflare` job builds `_site` exactly like the Pages job and runs `wrangler deploy` from this
folder. It is off until the repo variable `SITE_WORKER` is `on`, so Pages keeps serving while you set this up,
and both run side by side until you switch.

## Setup (about 20 minutes, all in the browser; nothing is pasted into chat or a file)

1. **Cloudflare API token** — dash.cloudflare.com → profile (top right) → My Profile → API Tokens → Create Token →
   template **Edit Cloudflare Workers** → keep it to this one account → Continue → Create. Copy it.
   **Account ID** — Workers & Pages → Overview: it is in the right-hand column.
2. **GitHub** — repo → Settings → Secrets and variables → Actions:
   - Secrets: `CLOUDFLARE_API_TOKEN` (the token), `CLOUDFLARE_ACCOUNT_ID`.
   - Variables: `SITE_WORKER` = `on`.
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
   - Policies → edit the one policy: Action *Allow*, Include → *Emails* → your address, your dad's, your
     friend's. Save. (Remove an address here to lock someone out; they are gone at their next request.)
   - Overview / settings: **Session duration** — 1 month is fine for a family dashboard; **Application Audience
     (AUD) Tag** — copy it (it is an identifier, not a secret).
   - Authentication: *One-time PIN* is on by default; leave it as the only method.
5. **GitHub variables** — `ACCESS_TEAM_DOMAIN` = `<team>.cloudflareaccess.com` (no `https://`),
   `ACCESS_AUD` = the AUD tag. Run the deploy workflow again.
6. **Check** — open the Worker URL in a private window: Access's page asks for an email; an address not on the
   list is refused; yours gets a code and then the dashboard. `/whoami` prints the signed-in email; `/logout` signs
   out. Open it on your phone too.

## Switching over (when you are ready; nothing below is done by the deploy)

- Send the new URL to your dad and friend; the Pages URL keeps working until the next step.
- **Make the repo private** (Settings → General → Danger Zone → Change visibility). This is the step that
  actually hides the data: as long as the repo is public, `data/latest.json` is readable on github.com whatever
  the Worker does. Pages stops on a private repo of a free account, which is what we want.
- In `deploy.yml`, delete the `publish` job and the `pages: write` / `id-token: write` permissions; drop
  `if: vars.SITE_WORKER == 'on'` from the `cloudflare` job. Update the live URL in `CLAUDE.md` and `README.md`.
- `collect.yml` and the trigger Worker are untouched: data still lands on the `data` branch and `collect.yml`
  still dispatches `deploy.yml`.

## What the Worker does not do

It never reads the token's email for anything but `/whoami` — no per-person content yet. A later Book sync
(encrypted in the browser, stored per email in KV) builds on exactly this identity header.
