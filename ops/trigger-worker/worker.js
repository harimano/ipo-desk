// A dependable clock for ipo-desk. GitHub's own cron is best-effort (18 Sep 2026: 2 of ~16 runs started, one 4.5 h
// late), so this Cloudflare Worker fires on Cloudflare's cron and asks GitHub to run collect.yml.
//
// Secrets / vars (set in the Cloudflare dashboard, never in this file):
//   GITHUB_TOKEN  fine-grained PAT, this repo only, permission "Actions: Read and write"
//   REPO          e.g. "harimano/ipo-desk"
//
// Cron triggers (UTC), set on the Worker:
//   13 1 * * *          06:43 IST  full
//   43 12 * * *         18:13 IST  full
//   7,37 4-11 * * 1-5   09:37-17:07 IST weekdays  intraday
//   7 12 * * 1-5        17:37 IST  intraday
const FULL = new Set(["13 1 * * *", "43 12 * * *"]);

async function dispatch(env, mode) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}/actions/workflows/collect.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: "application/vnd.github+json",
               "User-Agent": "ipo-desk-trigger", "X-GitHub-Api-Version": "2022-11-28" },
    body: JSON.stringify({ ref: "main", inputs: { mode } }),
  });
  if (!r.ok) throw new Error(`GitHub answered ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return `dispatched ${mode}`;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env, FULL.has(event.cron) ? "full" : "intraday"));
  },
  // Opening the Worker's URL shows that it is alive; it never triggers a run (that is what the schedule is for).
  async fetch() {
    return new Response("ipo-desk trigger: alive. Runs are started by the cron schedule only.\n");
  },
};
