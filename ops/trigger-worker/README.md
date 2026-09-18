# The trigger Worker — a clock that actually fires

GitHub's scheduler started 2 of ~16 runs on 18 Sep 2026. This Worker runs on Cloudflare's cron (free plan) and calls
GitHub's `workflow_dispatch` for `collect.yml`. The collector still runs on GitHub; only the alarm clock moves.
`collect.yml`'s own crons stay as a fallback; the `collect` concurrency group means a double trigger just queues.

## Setup (about 10 minutes, all in the browser)

1. **GitHub token** — github.com → Settings → Developer settings → Fine-grained tokens → Generate new token.
   Repository access: *Only select repositories* → `ipo-desk`. Permissions → Repository → **Actions: Read and write**.
   Nothing else. Copy the token (starts `github_pat_`).
2. **Cloudflare** — dash.cloudflare.com → Workers & Pages → Create → *Import a repository* → pick `ipo-desk`.
   On the last screen: project name `ipo-desk` (must equal `name` in wrangler.toml); deploy command `npx wrangler deploy`; open **Advanced
   settings** and set **Root directory** to `ops/trigger-worker`; UNTICK *Builds for non-production branches* (the
   `data` branch gets a commit every run and must not trigger builds); leave *Cloudflare Access* off. Deploy.
   `wrangler.toml` in this folder supplies the code, the four cron triggers and `REPO`.
3. **Settings → Variables and Secrets** → add a **Secret** named `GITHUB_TOKEN` with the token. (Nothing else.)
4. Settings → Triggers should already list the four cron schedules from `wrangler.toml`.
5. Check: the Worker's *Logs* tab after the next trigger time, and the repo's Actions tab — a `collect` run whose
   event is `workflow_dispatch` should appear within a minute of the scheduled time.

The token can start workflows in this one repo and nothing else. Revoke it on GitHub to switch the Worker off.
