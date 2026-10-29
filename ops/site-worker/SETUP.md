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

## 1c. The nightly backup (R2, free tier) and the daily-active salt

**Backup.** `.github/workflows/backup.yml` runs at 02:51 IST: `wrangler d1 export` of `ipo-desk-accounts` → one file a
night, `nightly/<date>.sql`, in the R2 bucket named in `wrangler.toml` (`BACKUP_BUCKET`, beside the D1 id); files dated
31–37 days back are deleted, so 30 stay. It is a GitHub job, not a Worker cron, because the Workers Free plan allows
5 cron triggers an account (developers.cloudflare.com/workers/platform/limits/) and the trigger Worker holds all five.
It uses the deploy token: no new secret.

1. dash.cloudflare.com → **R2 Object Storage → Create bucket** → name `ipo-desk-backups` → location *Automatic*
   (or the APAC hint, like the D1) → Create. Nothing else: no public access, no custom domain, no API token.
2. (Optional belt) the bucket → Settings → **Object lifecycle rules → Add rule** → prefix `nightly/` → *Delete
   uploaded objects* after 35 days. The workflow prunes anyway; the rule covers a month of missed runs.
3. Actions → **backup** → Run workflow. Then the bucket → Objects → `nightly/` shows today's file (~tens of KB).
   If the run's export step fails with an authorisation message, the token is missing **Account · D1 · Edit** (§1 step 4);
   if the put step does, **Account · Workers R2 Storage · Edit**: add it under My Profile → API Tokens → the token → Edit.

Free tier (developers.cloudflare.com/r2/pricing/): 10 GB stored, 1 million class-A operations (puts, deletes, lists)
and 10 million class-B a month, egress free. Thirty files under a megabyte and eight operations a night are nothing.
`/admin` → Security → *backup* says where the files go; whether last night's is there is the bucket's own listing.

**Restore.** First resort for a bad write is D1's own **Time Travel** — every minute of the last 7 days on the Free
plan, in place, `wrangler d1 time-travel restore ipo-desk-accounts --timestamp=…` (developers.cloudflare.com/d1/reference/time-travel/;
needs Node, so from a GitHub Actions shell or any machine with npx). The dumps are the copy that lives OUTSIDE the
database, for the day the database itself is gone or more than a week has passed:

1. The bucket → `nightly/` → the file → Download.
2. D1 → Create → a scratch database (any name) → copy its id.
3. In a shell (the token from My Profile → API Tokens, with D1 · Edit; typed, never in a file):
   ```
   export CLOUDFLARE_API_TOKEN=…  CLOUDFLARE_ACCOUNT_ID=…
   .venv/bin/python scripts/restore_d1.py ~/Downloads/2026-10-30.sql --database-id <scratch id> --dry-run
   .venv/bin/python scripts/restore_d1.py ~/Downloads/2026-10-30.sql --database-id <scratch id>
   ```
   D1 → the scratch database → Console → `SELECT email, part, length(body) FROM user_state` shows the rows back.
4. To put it in front of readers, either point `wrangler.toml`'s `database_id` at the restored database and push
   (the clean way: the old one stays as it was), or restore into the live id with `--replace --i-mean-the-live-database`
   (drops the three tables first, then loads the dump; readers' changes since the dump are gone).
   The script refuses the live id without that flag. Tested against a SQLite stand-in for the D1 endpoint
   (`tests/test_restore_d1.py`), not against D1 itself — the first real run goes into a scratch database.

**Daily-active salt.** `/admin` → *Readers by week* counts readers from a D1 row per reader per IST day that holds
only `SHA-256(salt + email)`. Add the GitHub secret `DAU_SALT` (any long random string — `openssl rand -hex 24` —
never pasted anywhere else; losing it only breaks the link between past and future rows), then run deploy. Without
it nothing is written and the card says so.

## 2. Access: who gets in

**Decision, 29 Oct 2026: the policy stays *Include → Everyone*.** The link is the key; the email code identifies each
reader and the Worker keys their saved state to that verified address. The allow-list steps below are kept only in case
that ever changes.

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

## 4. Rolling back the Worker

Every `wrangler deploy` (each deploy.yml run) publishes a new version; the last 100 can be put back as they were
(developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/). Bindings (KV, D1, the vars)
are not touched by a rollback — so a version that needs a binding the current one does not have will still fail; code
that reads a table the newer version created is fine, the data stays.

- **Dashboard:** Workers & Pages → `ipo-desk-site` → **Deployments** → the version to go back to → ⋯ → **Rollback**
  → confirm. Live within seconds. The deploy that caused it is still on `main`: the next collect's deploy will put it
  back, so revert the commit (or fix forward) before the next run (full runs 06:43 and 18:13 IST; intraday half-hourly).
- **Shell with Node** (GitHub Actions or any machine with npx; this Mac has none):
  `cd ops/site-worker && npx wrangler@4.154.0 rollback` — pick from the list, or `rollback <version id>`.
- **Without either:** `git revert <sha>` on main and push; deploy.yml redeploys in ~3 minutes. This is the one that
  also fixes the source.

Secrets (`CF_ACCESS_LOGS_TOKEN`, `NTFY_TOPIC`, `DAU_SALT`) belong to the Worker, not to a version: they survive a
rollback. The page's data (`_site`) is part of the version: rolling back also puts back that deploy's document.

## 5. Removing one reader's data on request

A reader can do it themself: account menu → **Reset my data** (`DELETE /api/state`: every part under their email).
What that leaves, and the admin's path for all of it — D1 → `ipo-desk-accounts` → Console, with the address as
Access shows it (lower-case):

```sql
DELETE FROM user_state WHERE email = 'name@example.com';    -- their saved dashboard (what Reset does)
DELETE FROM reports    WHERE email = 'name@example.com';    -- their "Wrong number?" flags
SELECT COUNT(*) FROM user_state WHERE email = 'name@example.com';   -- 0
```

- `daily_active` holds no email, only `SHA-256(DAU_SALT + "\n" + email)`: a day count that no one can tie back
  without the salt, and the D1 console cannot compute the hash. Leave it; it is a count, not their data.
- The visitors ledger: Workers & Pages → KV → `ipo-desk-visits` → key `v:name@example.com` → delete. Cloudflare's own
  Access log (sign-ins) is Cloudflare's, kept by its retention, not ours.
- The nightly dumps hold the `user_state` and `reports` rows for up to 30 more days (the bucket → `nightly/`): delete
  those files too if the request is "everything, now", or tell them the date it ages out.
- To stop them signing in again: Zero Trust → Access → Applications → the app → the policy → **Exclude → Emails** →
  their address (the policy stays *Everyone* for the rest).

## What the Worker does on `/api/*` (for the record)

| Route | Does |
|---|---|
| `GET /api/state` | all of this reader's parts: `{email, parts: {holdings, interest, apps, tasks-done, tasks-custom, investors, theme}, updated}` |
| `PUT /api/state/<part>` | replaces that one part with the JSON body (64 KB cap; unknown part → 400) |
| `DELETE /api/state` | removes every part for this reader ("Reset my data") |
| `GET /api/whoami` | the verified email |
| `GET /admin/retention.json` | admin only: 8 weeks of daily-active counts (no email) |

Any request without a valid Access token is refused with 401 before routing (the whole Worker is fail-closed). With no
D1 binding, `/api/*` answers 503 and the page says "Not saved · accounts not set up" while keeping a local copy.

## Local testing on this Mac (no Node, no wrangler)

`scripts/preview.py` serves `_site` on 8765 with an in-memory `/api` that takes the email from a dev cookie:
open `http://localhost:8765/dev/as/alice@example.com`, then `/dev/as/bob@example.com` in another browser profile.
The Worker's own token check and reader isolation are tested in `ops/site-worker/test/` — a browser harness page
(`http://localhost:8765/__worker/harness.html`, signs real RS256 tokens with WebCrypto) and the same cases under
`node --test`, which `ci.yml` runs on every push and pull request.
