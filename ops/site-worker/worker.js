// The gated dashboard. Cloudflare Access (email one-time PIN, an allowlist of addresses) sits in front of this
// Worker; this file re-checks Access's signed JWT on EVERY request before serving a byte of _site/, so a
// misconfigured or removed Access application fails closed, never open. No code here ever sees a password:
// Access does the login, we only verify its signature.
//
// Vars (deploy.yml passes them from repo variables; never secrets, never in wrangler.toml):
//   TEAM_DOMAIN  "<team>.cloudflareaccess.com"  — Zero Trust → Settings → Custom Pages → Team domain
//   POLICY_AUD   the Access application's Audience (AUD) tag — Zero Trust → Access → Applications → the app
//   ADMIN_EMAIL  the one address that may open /admin (repo variable ACCESS_ADMIN_EMAIL); unset = /admin does not exist
// Bindings (wrangler.toml): VISITS, a KV namespace — the visitors ledger behind /admin (optional: absent, nothing is kept);
//   DB, a D1 database — each reader's own saved dashboard behind /api/state (see SETUP.md; absent, /api answers 503 and the
//   page keeps a local copy and says "not saved").
// Secrets (uploaded by deploy.yml from GitHub secrets of the same name, when they exist):
//   CF_ACCESS_LOGS_TOKEN  an API token with only Account · Access: Audit Logs · Read — the sign-in history for /admin
//   CF_ACCOUNT_ID         the account the token reads (from the existing GitHub secret CLOUDFLARE_ACCOUNT_ID)
//   NTFY_TOPIC            (optional) the ntfy.sh topic a reader's "Wrong number?" report is pushed to — the same secret
//                         the collector's alerts use; absent, reports are only listed on /admin
//
// Access puts the JWT in the Cf-Access-Jwt-Assertion header (and a CF_Authorization cookie). It is RS256-signed
// by keys published at https://<team>.cloudflareaccess.com/cdn-cgi/access/certs; those are cached an hour.

const CERTS_TTL_MS = 60 * 60 * 1000;
let certs = { at: 0, keys: {} };            // kid -> CryptoKey; module-level, so it survives across requests in one isolate

async function keyFor(kid, env) {
  if (!certs.keys[kid] || Date.now() - certs.at > CERTS_TTL_MS) {
    const r = await fetch(`https://${env.TEAM_DOMAIN}/cdn-cgi/access/certs`);
    if (!r.ok) throw new Error(`certs answered ${r.status}`);
    const body = await r.json();
    const keys = {};
    for (const k of body.keys || []) {
      keys[k.kid] = await crypto.subtle.importKey("jwk", k, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    }
    certs = { at: Date.now(), keys };
  }
  const key = certs.keys[kid];
  if (!key) throw new Error("unknown signing key");
  return key;
}

function b64url(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(s + "=".repeat((4 - (s.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
const decodeJson = part => JSON.parse(new TextDecoder().decode(b64url(part)));

// Returns the verified claims (email among them) or throws.
export async function verify(token, env) {
  if (!token) throw new Error("no token");
  const [h, p, s] = token.split(".");
  if (!h || !p || !s) throw new Error("malformed token");
  const header = decodeJson(h);
  if (header.alg !== "RS256") throw new Error(`alg ${header.alg}`);
  const key = await keyFor(header.kid, env);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64url(s), new TextEncoder().encode(`${h}.${p}`));
  if (!ok) throw new Error("bad signature");
  const claims = decodeJson(p);
  const now = Math.floor(Date.now() / 1000);
  if (typeof claims.exp !== "number" || claims.exp < now) throw new Error("expired");
  if (typeof claims.nbf === "number" && claims.nbf > now + 60) throw new Error("not yet valid");
  if (claims.iss !== `https://${env.TEAM_DOMAIN}`) throw new Error("wrong issuer");
  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!aud.includes(env.POLICY_AUD)) throw new Error("wrong audience");
  return claims;
}

export function tokenFrom(request) {
  const h = request.headers.get("Cf-Access-Jwt-Assertion");
  if (h) return h;
  const m = /(?:^|;\s*)CF_Authorization=([^;]+)/.exec(request.headers.get("Cookie") || "");
  return m ? m[1] : "";
}

const text = (body, status, extra) =>
  new Response(body + "\n", { status, headers: Object.assign({ "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" }, extra || {}) });

// ---- the visitors ledger (KV binding VISITS; wrangler.toml) ----------------------------------------------------
// One small record per signed-in email: first seen, last seen, page loads, last country. Written only on a page load
// (not on data fetches) and at most once every WRITE_GAP_MS per person, so a day of friends is a few dozen writes
// against KV's free 1,000. No binding -> nothing is written and /admin/visitors.json says so. Emails are what Access
// already showed us; nothing else about a reader is kept.
const WRITE_GAP_MS = 10 * 60 * 1000;
const recent = new Map();                    // email -> last write, per isolate; saves a KV read on the hot path

async function noteVisit(request, env, claims, url) {
  if (!env.VISITS || !claims.email) return;
  const accept = request.headers.get("Accept") || "";
  const pageLoad = request.method === "GET" && (url.pathname === "/" || url.pathname.endsWith(".html") || url.pathname === "/admin" || url.pathname === "/admin/") && accept.includes("text/html");
  if (!pageLoad) return;
  const email = claims.email.toLowerCase(), now = Date.now();
  if (now - (recent.get(email) || 0) < WRITE_GAP_MS) return;
  recent.set(email, now);
  const key = "v:" + email;
  const cur = (await env.VISITS.get(key, "json")) || { first: new Date(now).toISOString(), n: 0 };
  if (cur.last && now - Date.parse(cur.last) < WRITE_GAP_MS) return;
  cur.last = new Date(now).toISOString();
  cur.n = (cur.n || 0) + 1;
  cur.country = (request.cf && request.cf.country) || cur.country || null;
  cur.admin = url.pathname.startsWith("/admin") ? true : !!cur.admin;
  await env.VISITS.put(key, JSON.stringify(cur));
}

async function ledger(env) {
  const out = {};
  if (!env.VISITS) return out;
  let cursor, n = 0;
  do {
    const page = await env.VISITS.list({ prefix: "v:", cursor, limit: 200 });
    for (const k of page.keys) {
      const v = await env.VISITS.get(k.name, "json");
      if (v) { out[k.name.slice(2)] = v; n++; }
    }
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor && n < 1000);
  return out;
}

// Cloudflare's own Access log — every sign-in attempt at the gate since it went up, read with a token that can ONLY
// read Access audit logs (Worker secrets CF_ACCESS_LOGS_TOKEN + CF_ACCOUNT_ID, uploaded by deploy.yml when the GitHub
// secrets exist; absent, the card says so). Cached a minute per isolate so a page reload is not an API call.
let accessCache = { at: 0, body: null };
async function accessLog(env) {
  if (!env.CF_ACCESS_LOGS_TOKEN || !env.CF_ACCOUNT_ID) return { error: "no Access-log token: add the GitHub secret CF_ACCESS_LOGS_TOKEN (Account · Access: Audit Logs · Read), then run deploy" };
  if (Date.now() - accessCache.at < 60 * 1000 && accessCache.body) return accessCache.body;
  const r = await fetch(`https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/access/logs/access_requests?limit=1000&direction=desc`,
    { headers: { Authorization: `Bearer ${env.CF_ACCESS_LOGS_TOKEN}` } });
  if (!r.ok) return { error: `Cloudflare answered ${r.status} to the Access-log call (is the token Access: Audit Logs: Read on this account?)` };
  const body = await r.json();
  if (!body.success) return { error: "Access-log call failed: " + JSON.stringify((body.errors || []).slice(0, 2)) };
  const by = {};
  for (const e of body.result || []) {
    const email = (e.user_email || "").toLowerCase();
    if (!email) continue;
    const at = e.created_at, ok = e.allowed !== false;
    const v = by[email] || (by[email] = { first: at, last: at, signins: 0, failed: 0, country: e.country || null, lastIp: null });
    if (at < v.first) v.first = at;
    if (at > v.last) { v.last = at; v.country = e.country || v.country; }
    if (ok) v.signins++; else v.failed++;
  }
  const out = { by, n: (body.result || []).length };
  accessCache = { at: Date.now(), body: out };
  return out;
}

// One row per email, from both: the Access log (sign-ins, since the gate went up) and the ledger (page loads, since
// 29 Oct 2026). Either source may be missing; the row says which it has.
async function visitors(env) {
  const [led, acc] = await Promise.all([ledger(env), accessLog(env)]);
  const rows = {};
  for (const [email, v] of Object.entries(led)) rows[email] = { email, first: v.first, last: v.last, loads: v.n || 0, signins: 0, failed: 0, country: v.country || null, admin: !!v.admin };
  for (const [email, a] of Object.entries(acc.by || {})) {
    const r = rows[email] || (rows[email] = { email, first: a.first, last: a.last, loads: 0, signins: 0, failed: 0, country: null, admin: false });
    if (a.first < r.first) r.first = a.first;
    if (a.last > r.last) r.last = a.last;
    r.signins = a.signins; r.failed = a.failed; r.country = r.country || a.country;
  }
  const out = Object.values(rows).sort((x, y) => (y.last || "").localeCompare(x.last || ""));
  return { at: new Date().toISOString(), visitors: out, ledger: !!env.VISITS, accessLog: acc.error ? { error: acc.error } : { records: acc.n } };
}

// ---- per-reader state: /api/state (D1 binding DB; schema.sql) --------------------------------------------------
// One row per (email, part). The email is the VERIFIED Access claim — never anything the client sends. A part is a
// whole JSON value (a list of a few dozen names at most) replaced on each PUT: idempotent, so a retry can never
// double-apply, and last writer wins per part. Nothing about one reader is ever readable under another's email.
const PARTS = ["holdings", "interest", "apps", "tasks-done", "tasks-custom", "investors", "theme", "budget"];
const PART_MAX_BYTES = 64 * 1024;
let schemaReady = null;                      // per isolate: the CREATE TABLE IF NOT EXISTS statements run once
const SCHEMA = [
  "CREATE TABLE IF NOT EXISTS user_state (email TEXT NOT NULL, part TEXT NOT NULL, body TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY (email, part))",
  "CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, email TEXT NOT NULL, issue TEXT NOT NULL, ig_id TEXT, field TEXT NOT NULL, shown TEXT, note TEXT, page TEXT, data_as_of TEXT, status TEXT NOT NULL DEFAULT 'open')",
];
function ensureSchema(db) {
  if (!schemaReady) schemaReady = SCHEMA.reduce((p, sql) => p.then(() => db.prepare(sql).run()), Promise.resolve()).catch(e => { schemaReady = null; throw e; });
  return schemaReady;
}
// "Wrong number?" (site/src/report.js): a reader flags a figure. Stored under the VERIFIED email, capped per reader per
// day, pushed to NTFY_TOPIC when set. A report never changes a number; it is a note to a person.
const REPORT_MAX_PER_DAY = 20, clip = (v, n) => v == null ? null : String(v).slice(0, n);
async function storeReport(request, env, email, ctx) {
  let body; try { body = await request.json(); } catch (e) { return json({ error: "body is not JSON" }, 400); }
  if (!body || typeof body !== "object" || !body.issue || !body.field) return json({ error: "issue and field are required" }, 400);
  const since = new Date(Date.now() - 86400000).toISOString();
  const { results } = await env.DB.prepare("SELECT COUNT(*) AS n FROM reports WHERE email = ?1 AND at > ?2").bind(email, since).all();
  if (((results || [])[0] || {}).n >= REPORT_MAX_PER_DAY) return json({ error: "that is plenty for one day — thank you; Hari has them" }, 429);
  const at = new Date().toISOString();
  const row = [at, email, clip(body.issue, 120), clip(body.igId, 20), clip(body.field, 40), clip(body.shown, 80), clip(body.note, 500), clip(body.page, 80), clip(body.dataAsOf, 40)];
  await env.DB.prepare("INSERT INTO reports (at, email, issue, ig_id, field, shown, note, page, data_as_of) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)").bind(...row).run();
  if (env.NTFY_TOPIC) {
    const ping = fetch(`https://ntfy.sh/${encodeURIComponent(env.NTFY_TOPIC)}`, { method: "POST", headers: { Title: `Wrong number? ${row[2]} - ${row[4]}`, Tags: "mag", Click: "https://ipodesk.dev/admin" },
      body: `${row[2]} · ${row[4]}${row[5] ? ` (shown ${row[5]})` : ""}${row[6] ? `\n${row[6]}` : ""}\nfrom ${email} · data as of ${row[8] || "?"}` }).catch(() => {});
    if (ctx && ctx.waitUntil) ctx.waitUntil(ping); else await ping;
  }
  return json({ ok: true, at });
}
export async function listReports(env, limit) {
  await ensureSchema(env.DB);
  const { results } = await env.DB.prepare("SELECT id, at, email, issue, ig_id, field, shown, note, page, data_as_of, status FROM reports ORDER BY id DESC LIMIT ?1").bind(limit || 200).all();
  return { reports: results || [] };
}
export async function handleApi(request, env, claims, url, ctx) {
  const email = (claims.email || "").toLowerCase();
  if (!email) return json({ error: "no email in the sign-in token" }, 401);
  if (!env.DB) return json({ error: "accounts are not configured on this deployment (no D1 binding — ops/site-worker/SETUP.md)" }, 503);
  await ensureSchema(env.DB);
  const path = url.pathname.replace(/\/+$/, "");
  if (path === "/api/state" && request.method === "GET") {
    const { results } = await env.DB.prepare("SELECT part, body, updated FROM user_state WHERE email = ?1").bind(email).all();
    const parts = {}, updated = {};
    for (const r of results || []) { try { parts[r.part] = JSON.parse(r.body); updated[r.part] = r.updated; } catch (e) { /* a corrupt row is skipped, never fatal */ } }
    return json({ email, parts, updated });
  }
  if (path === "/api/state" && request.method === "DELETE") {
    await env.DB.prepare("DELETE FROM user_state WHERE email = ?1").bind(email).run();
    return json({ ok: true, email, parts: {}, updated: {} });
  }
  const m = /^\/api\/state\/([a-z-]+)$/.exec(path);
  if (m && request.method === "PUT") {
    const part = m[1];
    if (!PARTS.includes(part)) return json({ error: `unknown part '${part}'` }, 400);
    const body = await request.text();
    if (body.length > PART_MAX_BYTES) return json({ error: `part too large (${body.length} bytes; limit ${PART_MAX_BYTES})` }, 413);
    let value;
    try { value = JSON.parse(body); } catch (e) { return json({ error: "body is not JSON" }, 400); }
    if (value === undefined) return json({ error: "body is not JSON" }, 400);
    const updated = new Date().toISOString();
    await env.DB.prepare("INSERT INTO user_state (email, part, body, updated) VALUES (?1, ?2, ?3, ?4) ON CONFLICT (email, part) DO UPDATE SET body = excluded.body, updated = excluded.updated")
      .bind(email, part, JSON.stringify(value), updated).run();
    return json({ ok: true, part, updated });
  }
  if (path === "/api/whoami" && request.method === "GET") return json({ email });
  if (path === "/api/report" && request.method === "POST") return storeReport(request, env, email, ctx);
  return json({ error: "no such API route" }, path.startsWith("/api/state") || path === "/api/report" ? 405 : 404);
}

const json = (body, status) => new Response(JSON.stringify(body), { status: status || 200, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

export default {
  async fetch(request, env, ctx) {
    if (!env.TEAM_DOMAIN || !env.POLICY_AUD) {
      return text("ipo-desk: the gate is not configured (TEAM_DOMAIN / POLICY_AUD), so nothing is served.", 503);
    }
    let claims;
    try {
      claims = await verify(tokenFrom(request), env);
    } catch (e) {
      // With Access in front a visitor never gets here unauthenticated; this answers only when Access is missing
      // or the token is stale. Say so plainly, never serve.
      return text(`ipo-desk: sign-in required (${e.message}). Open the page again to sign in.`, 401);
    }
    const url = new URL(request.url);
    if (url.pathname === "/logout") return Response.redirect(`https://${env.TEAM_DOMAIN}/cdn-cgi/access/logout`, 302);
    if (url.pathname === "/whoami") return text(claims.email || "(no email claim)", 200);
    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      try { return await handleApi(request, env, claims, url, ctx); }
      catch (e) { return json({ error: "state store failed: " + (e && e.message) }, 500); }
    }

    // /admin is Hari's ops page (site/admin/): served only when the signed-in email is ADMIN_EMAIL (a repo variable,
    // passed like the two above). Unset -> 404 for everyone, the fail-closed default; anyone else -> 403, no byte of it.
    if (url.pathname === "/admin" || url.pathname.startsWith("/admin/")) {
      const admin = (env.ADMIN_EMAIL || "").trim().toLowerCase();
      if (!admin || admin === "pending") return text("not found", 404);
      if ((claims.email || "").toLowerCase() !== admin) return text("ipo-desk: this page is for the admin only.", 403);
      if (url.pathname === "/admin/me.json") return json({ email: claims.email, team: env.TEAM_DOMAIN, adminEmailSet: true, visitors: !!env.VISITS });
      if (url.pathname === "/admin/visitors.json") return json(await visitors(env));
      if (url.pathname === "/admin/reports.json") { if (!env.DB) return json({ error: "no D1 binding", reports: [] }, 503); try { return json(await listReports(env, 200)); } catch (e) { return json({ error: "reports failed: " + (e && e.message), reports: [] }, 500); } }
    }

    ctx.waitUntil(noteVisit(request, env, claims, url).catch(() => {}));   // never in the way of the page, never fatal
    const res = await env.ASSETS.fetch(request);
    const headers = new Headers(res.headers);
    headers.set("X-Robots-Tag", "noindex, nofollow");       // a gated page is not for search engines
    headers.set("Referrer-Policy", "no-referrer");
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  },
};
