# SETUP — accounts for a small group of friends (per-reader saved dashboards)

Everything here is done once, in the Cloudflare dashboard and GitHub settings. No secret is pasted into chat or into
a file in this repo: the one value that lands in the repo (the D1 database id) is an identifier.

What it gives: every signed-in reader gets their own Book, application log, held parents, stars, done / snoozed
items, tasks, followed investors and theme, kept under their **verified Access email** (the Worker reads the email
from the signed `Cf-Access-Jwt-Assertion` token it already checks on every request — never from the browser).
Readers cannot see each other's data; the shared market data (Board, Pipeline, Market, Research, Score) is the same
for everyone.

## 1. The database (D1, free tier)

1. dash.cloudflare.com → **Storage & Databases → D1 SQL Database → Create** → name `ipo-desk-accounts` → Create.
2. Copy the **Database ID** shown on its page.
3. In `ops/site-worker/wrangler.toml`, uncomment the `[[d1_databases]]` block and paste the id into `database_id`.
   Commit and push. The Worker creates the one table (`schema.sql`) the first time a reader opens the page; nothing
   to run in the console. (If you prefer to see it: D1 → the database → Console → paste `schema.sql` → Execute.)
4. **Deploy token permission.** The GitHub secret `CLOUDFLARE_API_TOKEN` was made from the *Edit Cloudflare Workers*
   template. Binding a D1 database at deploy may need one more permission on that token: My Profile → API Tokens →
   the token → Edit → add **Account · D1 · Edit** → Save. If the deploy's wrangler step fails with an authorisation
   message about D1, this is why.

Free tier: 5 GB, 5 million rows read and 100,000 rows written a day. Fifty readers saving a few dozen things a day
use well under one percent of that.

## 1b. "Wrong number?" reports and the ntfy ping (optional)

The same database holds `reports` (schema.sql): what a reader flagged under an IPO, with the value that was on screen
and the run it came from. Nothing to create. To be pinged on your phone, add the GitHub secret `NTFY_TOPIC` (the topic
you subscribe to in the ntfy app — the collector's alerts use the same secret); `deploy.yml` hands it to the Worker on
the next deploy. Without it, reports are only listed on /admin. Mark one handled in the D1 console:
`UPDATE reports SET status='done' WHERE id=…`.

## 2. Access: who gets in

The Access application in front of the Worker (Zero Trust → Access → Applications → the `ipo-desk-site` app) decides
who can sign in. Today its policy is *Include → Everyone* (anyone with the link who completes the email code). For an
allow-list of up to 50 friends:

1. Policies → the Allow policy → Include → change the selector to **Emails** → add each address (one per line).
   Remove the *Everyone* rule.
2. Save. A reader not on the list sees Access's own "not authorised" page; nothing of the site is served.
3. Session duration (Overview → Session Duration): 1 month is fine for this audience.

The Worker needs nothing new here: it already verifies the token against `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`
with the application's AUD tag (repo variables `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD`, passed by `deploy.yml`).

## 3. Check it

- Open https://ipodesk.dev/ signed in. The header shows a pill: **Saved** once your first change lands; click it for
  the account menu (your email, Export my data, Reset my data, Sign out).
- https://ipodesk.dev/api/state answers your parts as JSON; from a browser with no Access session it answers 401.
- A second address (a friend, or your own second email) starts with an empty Book and never sees yours.
- `/admin` → the Visitors card lists who has signed in.

## What the Worker does on `/api/*` (for the record)

| Route | Does |
|---|---|
| `GET /api/state` | all of this reader's parts: `{email, parts: {holdings, interest, apps, tasks-done, tasks-custom, investors, theme}, updated}` |
| `PUT /api/state/<part>` | replaces that one part with the JSON body (64 KB cap; unknown part → 400) |
| `DELETE /api/state` | removes every part for this reader ("Reset my data") |
| `GET /api/whoami` | the verified email |

Any request without a valid Access token is refused with 401 before routing (the whole Worker is fail-closed). With no
D1 binding, `/api/*` answers 503 and the page says "Not saved · accounts not set up" while keeping a local copy.

## Local testing on this Mac (no Node, no wrangler)

`scripts/preview.py` serves `_site` on 8765 with an in-memory `/api` that takes the email from a dev cookie:
open `http://localhost:8765/dev/as/alice@example.com`, then `/dev/as/bob@example.com` in another browser profile.
The Worker's own token check and reader isolation are tested in `ops/site-worker/test/` — a browser harness page
(`http://localhost:8765/__worker/harness.html`, signs real RS256 tokens with WebCrypto) and the same cases under
`node --test`, which `ci.yml` runs on every push and pull request.
