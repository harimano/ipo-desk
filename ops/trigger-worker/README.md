# The trigger Worker — a clock that actually fires

GitHub's scheduler started 2 of ~16 runs on 18 Sep 2026. This Worker runs on Cloudflare's cron (free plan) and calls
GitHub's `workflow_dispatch` for `collect.yml`. The collector still runs on GitHub; only the alarm clock moves.
`collect.yml`'s own crons stay as a fallback; the `collect` concurrency group means a double trigger just queues.

## Setup (about 10 minutes, all in the browser)

1. **GitHub token** — github.com → Settings → Developer settings → Fine-grained tokens → Generate new token.
   Repository access: *Only select repositories* → `ipo-desk`. Permissions → Repository → **Actions: Read and write**.
   Nothing else. Copy the token (starts `github_pat_`).
2. **Cloudflare** — dash.cloudflare.com (free account) → Workers & Pages → Create → Worker → name it
   `ipo-desk-trigger` → Deploy → Edit code → paste `worker.js` from this folder → Deploy.
3. **Settings → Variables and Secrets**: add secret `GITHUB_TOKEN` (the token) and text variable `REPO` =
   `harimano/ipo-desk`.
4. **Settings → Triggers → Cron Triggers**: add the four schedules listed at the top of `worker.js`.
5. Check: the Worker's *Logs* tab after the next trigger time, and the repo's Actions tab — a `collect` run whose
   event is `workflow_dispatch` should appear within a minute of the scheduled time.

The token can start workflows in this one repo and nothing else. Revoke it on GitHub to switch the Worker off.
