// The Worker's gate and its /api/state, exercised without Cloudflare: real RS256 tokens signed here with WebCrypto,
// the certs URL answered by a stubbed fetch, D1 replaced by an in-memory table. Runs the same in Node (api.test.mjs,
// ci.yml) and in a browser (harness.html via scripts/preview.py), because Hari's Mac has no Node.
//
// What must hold: no token / bad signature / wrong audience / expired -> 401 and not a byte served; each reader's
// parts live under their verified email only; an unknown part is 400, an oversize one 413; DELETE empties one reader;
// no D1 binding -> 503, the page is still served.
// Daily active: a page load writes one (day, hash) row — never the email — only with DAU_SALT; /admin/retention.json
// turns the rows into 8 weeks of counts and is served to the admin alone.
import worker, { verify, handleApi, emailHash, retentionWeeks } from "../worker.js";

const TEAM = "example.cloudflareaccess.com", AUD = "aud-for-tests";
const enc = s => btoa(String.fromCharCode(...new TextEncoder().encode(s))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const encBytes = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function signer() {
  const kp = await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
  const jwk = await crypto.subtle.exportKey("jwk", kp.publicKey);
  const kid = "test-key-1";
  Object.assign(jwk, { kid, use: "sig", alg: "RS256" });
  const sign = async (claims, opts = {}) => {
    const now = Math.floor(Date.now() / 1000);
    const body = Object.assign({ iss: `https://${TEAM}`, aud: [AUD], iat: now, exp: now + 3600 }, claims);
    const h = enc(JSON.stringify({ alg: "RS256", kid: opts.kid || kid, typ: "JWT" })), p = enc(JSON.stringify(body));
    const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", opts.key || kp.privateKey, new TextEncoder().encode(`${h}.${p}`));
    return `${h}.${p}.${encBytes(sig)}`;
  };
  return { jwk, sign, kp };
}

// D1 in memory: the four statements worker.js uses, matched by their first word and parameters
function fakeD1() {
  const rows = new Map();                       // "email\0part" -> {email, part, body, updated}
  const reports = [];
  const daily = new Map();                      // "day|hash" -> {day, email_hash}
  let writes = 0;                               // INSERTs that reached the table (D1 bills rows written)
  const stmt = sql => ({ bind: (...a) => ({
    run: async () => {
      if (/^CREATE TABLE/i.test(sql)) return { success: true };
      if (/^DELETE/i.test(sql)) { for (const k of [...rows.keys()]) if (k.startsWith(a[0] + "\0")) rows.delete(k); return { success: true }; }
      if (/INTO daily_active/i.test(sql)) { const k = a[0] + "|" + a[1]; if (!daily.has(k)) { daily.set(k, { day: a[0], email_hash: a[1] }); writes++; } return { success: true }; }
      if (/INTO reports/i.test(sql)) { reports.push({ id: reports.length + 1, at: a[0], email: a[1], issue: a[2], ig_id: a[3], field: a[4], shown: a[5], note: a[6], page: a[7], data_as_of: a[8], status: "open" }); return { success: true }; }
      if (/^INSERT/i.test(sql)) { rows.set(a[0] + "\0" + a[1], { email: a[0], part: a[1], body: a[2], updated: a[3] }); return { success: true }; }
      throw new Error("unexpected sql: " + sql);
    },
    all: async () => { if (!/^SELECT/i.test(sql)) throw new Error("unexpected sql: " + sql);
      if (/COUNT\(\*\) AS n FROM reports/i.test(sql)) return { results: [{ n: reports.filter(r => r.email === a[0] && r.at > a[1]).length }] };
      if (/FROM reports/i.test(sql)) return { results: reports.slice().reverse().slice(0, a[0]) };
      if (/FROM daily_active/i.test(sql)) return { results: [...daily.values()].filter(r => r.day >= a[0]) };
      return { results: [...rows.values()].filter(r => r.email === a[0]) }; },
  }), run: async () => { if (/^CREATE TABLE/i.test(sql)) return { success: true }; throw new Error("bind first: " + sql); } });
  return { prepare: stmt, _rows: rows, _reports: reports, _daily: daily, get _writes() { return writes; } };
}

export async function runCases() {
  const out = [], ok = (cond, msg) => out.push({ ok: !!cond, msg });
  const s = await signer();
  const realFetch = globalThis.fetch;
  const pings = [];
  globalThis.fetch = async (url, init) => {
    if (String(url) === `https://${TEAM}/cdn-cgi/access/certs`) return new Response(JSON.stringify({ keys: [s.jwk] }), { headers: { "Content-Type": "application/json" } });
    if (String(url).startsWith("https://ntfy.sh/")) { pings.push({ url: String(url), title: init && init.headers && init.headers.Title }); return new Response("{}", { status: 200 }); }
    throw new Error("unexpected fetch " + url);
  };
  try {
    const DB = fakeD1();
    const env = { TEAM_DOMAIN: TEAM, POLICY_AUD: AUD, DB, ASSETS: { fetch: async () => new Response("<html>page</html>", { headers: { "Content-Type": "text/html" } }) } };
    const ctx = { waitUntil() {} };
    const call = (path, init = {}, token) => {
      const headers = new Headers(init.headers || {});
      if (token) headers.set("Cf-Access-Jwt-Assertion", token);
      return worker.fetch(new Request("https://ipodesk.dev" + path, Object.assign({}, init, { headers })), env, ctx);
    };
    const alice = await s.sign({ email: "Alice@Example.com" }), bob = await s.sign({ email: "bob@example.com" });

    // the gate
    let r = await call("/api/state");
    ok(r.status === 401, `no token -> 401 (got ${r.status})`);
    r = await call("/");
    ok(r.status === 401 && !(await r.text()).includes("<html>"), "no token -> the page is not served either");
    r = await call("/api/state", {}, await s.sign({ email: "x@example.com", aud: ["someone-else"] }));
    ok(r.status === 401, "wrong audience -> 401");
    r = await call("/api/state", {}, await s.sign({ email: "x@example.com", exp: Math.floor(Date.now() / 1000) - 10 }));
    ok(r.status === 401, "expired -> 401");
    r = await call("/api/state", {}, await s.sign({ email: "x@example.com", iss: "https://evil.example" }));
    ok(r.status === 401, "wrong issuer -> 401");
    const other = await signer();
    r = await call("/api/state", {}, await s.sign({ email: "x@example.com" }, { key: other.kp.privateKey }));
    ok(r.status === 401, "signed by another key -> 401");
    r = await call("/api/state", {}, alice.slice(0, -4) + "AAAA");
    ok(r.status === 401, "tampered signature -> 401");
    r = await call("/api/state", {}, "not.a.jwt");
    ok(r.status === 401, "garbage token -> 401");
    ok((await verify(alice, env)).email === "Alice@Example.com", "verify() returns the claims of a good token");

    // two readers, separate
    r = await call("/api/state", {}, alice);
    let b = await r.json();
    ok(r.status === 200 && b.email === "alice@example.com" && Object.keys(b.parts).length === 0, "alice starts empty, email lower-cased");
    r = await call("/api/state/holdings", { method: "PUT", body: JSON.stringify(["Reliance Industries"]) }, alice);
    ok(r.status === 200 && (await r.json()).ok, "alice PUT holdings -> 200");
    r = await call("/api/state/interest", { method: "PUT", body: JSON.stringify(["Wiscon Industries"]) }, alice);
    ok(r.status === 200, "alice PUT interest -> 200");
    r = await call("/api/state", {}, alice); b = await r.json();
    ok(b.parts.holdings[0] === "Reliance Industries" && b.parts.interest[0] === "Wiscon Industries" && b.updated.holdings, "alice GET shows both parts with updated times");
    r = await call("/api/state", {}, bob); b = await r.json();
    ok(b.email === "bob@example.com" && Object.keys(b.parts).length === 0, "bob sees nothing of alice's");
    r = await call("/api/state/holdings", { method: "PUT", body: JSON.stringify(["Hero MotoCorp"]) }, bob);
    r = await call("/api/state", {}, bob); b = await r.json();
    ok(b.parts.holdings[0] === "Hero MotoCorp" && !b.parts.interest, "bob's own holdings only");
    r = await call("/api/state", {}, alice); b = await r.json();
    ok(b.parts.holdings[0] === "Reliance Industries", "alice's holdings untouched by bob's PUT");
    r = await call("/api/state/holdings", { method: "PUT", body: JSON.stringify([]) }, alice);
    r = await call("/api/state", {}, alice); b = await r.json();
    ok(Array.isArray(b.parts.holdings) && b.parts.holdings.length === 0, "a PUT replaces the whole part (empty list stays an empty list)");
    ok(DB._rows.size === 3, `three rows in the table (got ${DB._rows.size})`);

    // the edges
    r = await call("/api/state/nonsense", { method: "PUT", body: "[]" }, alice);
    ok(r.status === 400, "unknown part -> 400");
    r = await call("/api/state/apps", { method: "PUT", body: "{not json" }, alice);
    ok(r.status === 400, "not JSON -> 400");
    r = await call("/api/state/apps", { method: "PUT", body: JSON.stringify("x".repeat(70 * 1024)) }, alice);
    ok(r.status === 413, "oversize part -> 413");
    r = await call("/api/state", { method: "POST", body: "{}" }, alice);
    ok(r.status === 405, "POST /api/state -> 405");
    r = await call("/api/other", {}, alice);
    ok(r.status === 404, "unknown API route -> 404");
    r = await call("/api/whoami", {}, bob);
    ok((await r.json()).email === "bob@example.com", "/api/whoami is the verified email");
    r = await call("/api/state", { method: "DELETE" }, alice);
    ok(r.status === 200, "alice DELETE -> 200");
    r = await call("/api/state", {}, alice); b = await r.json();
    ok(Object.keys(b.parts).length === 0, "alice is empty after reset");
    r = await call("/api/state", {}, bob); b = await r.json();
    ok(b.parts.holdings[0] === "Hero MotoCorp", "bob survives alice's reset");
    r = await call("/", {}, bob);
    ok(r.status === 200 && (await r.text()).includes("<html>"), "the page is served to a signed-in reader");
    ok(r.headers.get("X-Robots-Tag") === "noindex, nofollow", "noindex header on the page");

    // "Wrong number?": stored under the verified email, never the body's; capped; the admin list is gated
    r = await call("/api/report", { method: "POST", body: JSON.stringify({ issue: "Lenskart Solutions", igId: "2305", field: "gmp", shown: "73", note: "IG shows 65", email: "mallory@example.com", dataAsOf: "2026-10-29T15:08:47+05:30" }) }, bob);
    ok(r.status === 200 && (await r.json()).ok, `a report -> 200 (got ${r.status})`);
    ok(DB._reports.length === 1 && DB._reports[0].email === "bob@example.com" && DB._reports[0].issue === "Lenskart Solutions" && DB._reports[0].field === "gmp", "the report carries the token's email, not the body's");
    r = await worker.fetch(new Request("https://ipodesk.dev/api/report", { method: "POST", body: JSON.stringify({ issue: "Ajwa Projects — SME", field: "gmp" }), headers: { "Cf-Access-Jwt-Assertion": bob } }), Object.assign({}, env, { NTFY_TOPIC: "ipodesk-test\n" }), ctx);
    b = await r.json();
    ok(r.status === 200 && b.ping === 200 && pings.length === 1 && pings[0].url === "https://ntfy.sh/ipodesk-test" && !/[^\x20-\x7e]/.test(pings[0].title), `with NTFY_TOPIC the ping goes to the trimmed topic with an ASCII title (got ${JSON.stringify(pings[0])}, ping ${b.ping})`);
    r = await call("/api/report", { method: "POST", body: JSON.stringify({ note: "no issue named" }) }, bob);
    ok(r.status === 400, "a report without issue and field -> 400");
    r = await call("/api/report", { method: "POST", body: "{nope" }, bob);
    ok(r.status === 400, "a report that is not JSON -> 400");
    r = await call("/api/report", {}, bob);
    ok(r.status === 405, "GET /api/report -> 405");
    for (let i = 0; i < 18; i++) await call("/api/report", { method: "POST", body: JSON.stringify({ issue: "X", field: "other" }) }, bob);
    r = await call("/api/report", { method: "POST", body: JSON.stringify({ issue: "X", field: "other" }) }, bob);
    ok(r.status === 429 && DB._reports.length === 20, `the 21st report in a day -> 429 (got ${r.status}, ${DB._reports.length} stored)`);
    r = await call("/admin/reports.json", {}, bob);
    ok(r.status === 404, "reports.json with no ADMIN_EMAIL -> 404 (fail closed)");
    r = await worker.fetch(new Request("https://ipodesk.dev/admin/reports.json", { headers: { "Cf-Access-Jwt-Assertion": bob } }), Object.assign({}, env, { ADMIN_EMAIL: "alice@example.com" }), ctx);
    ok(r.status === 403, "reports.json as a non-admin -> 403");
    r = await worker.fetch(new Request("https://ipodesk.dev/admin/reports.json", { headers: { "Cf-Access-Jwt-Assertion": alice } }), Object.assign({}, env, { ADMIN_EMAIL: "alice@example.com" }), ctx);
    b = await r.json();
    ok(r.status === 200 && b.reports.length === 20 && b.reports[0].issue === "X" && b.reports[19].note === "IG shows 65", "the admin lists the reports, newest first");

    // daily active: one row per reader per day, hashed, only with a salt; the admin's retention.json
    const page = (token, e) => worker.fetch(new Request("https://ipodesk.dev/", { headers: { "Cf-Access-Jwt-Assertion": token, Accept: "text/html" } }), e || env, ctx);
    const settle = () => new Promise(r => setTimeout(r, 20));
    await page(alice); await settle();
    ok(DB._daily.size === 0, "a page load with no DAU_SALT writes no daily row");
    const salted = Object.assign({}, env, { DAU_SALT: " pepper\n", ADMIN_EMAIL: "alice@example.com" });
    await page(alice, salted); await page(alice, salted); await page(bob, salted); await settle();
    const h = await emailHash("Alice@Example.com", "pepper");
    ok(DB._daily.size === 2 && DB._writes === 2, `two readers, three loads -> two daily rows, two writes (got ${DB._daily.size}, ${DB._writes})`);
    ok([...DB._daily.values()].every(r => r.email_hash === h || r.email_hash !== "bob@example.com") && [...DB._daily.values()].some(r => r.email_hash === h), "the row holds the salted hash (salt trimmed), never the email");
    ok(/^\d{4}-\d{2}-\d{2}$/.test([...DB._daily.values()][0].day), "the day is YYYY-MM-DD");
    await worker.fetch(new Request("https://ipodesk.dev/data/meta.json", { headers: { "Cf-Access-Jwt-Assertion": bob, Accept: "application/json" } }), salted, ctx); await settle();
    ok(DB._writes === 2, "a data fetch is not a page load: no write");
    r = await worker.fetch(new Request("https://ipodesk.dev/admin/retention.json", { headers: { "Cf-Access-Jwt-Assertion": bob } }), salted, ctx);
    ok(r.status === 403, "retention.json as a non-admin -> 403");
    r = await worker.fetch(new Request("https://ipodesk.dev/admin/retention.json", { headers: { "Cf-Access-Jwt-Assertion": alice } }), salted, ctx);
    b = await r.json();
    ok(r.status === 200 && b.salted && b.weeks.length === 8 && b.weeks[7].active === 2 && b.weeks[7].new === 2 && b.rows === 2, `retention.json: 8 weeks, this week 2 active 2 new (got ${JSON.stringify(b.weeks && b.weeks[7])})`);
    ok(!JSON.stringify(b).includes("example.com"), "retention.json names nobody");
    // the week arithmetic on its own: Mon 2026-10-26 IST; week 1 starts 2026-09-07
    const now = Date.parse("2026-10-29T10:00:00+05:30");
    const rowsW = [{ day: "2026-09-08", email_hash: "A" }, { day: "2026-09-09", email_hash: "A" }, { day: "2026-09-10", email_hash: "B" }, { day: "2026-10-27", email_hash: "A" }, { day: "2026-10-27", email_hash: "C" }, { day: "2026-08-01", email_hash: "Z" }];
    const w = retentionWeeks(rowsW, now);
    ok(w.weeks[0].start === "2026-09-07" && w.weeks[7].start === "2026-10-26" && w.daysIntoWeek === 4 && w.firstWeekReaders === 2, `weeks run 7 Sep … 26 Oct, 4 days in, 2 in week 1 (got ${w.weeks[0].start} … ${w.weeks[7].start}, ${w.daysIntoWeek}, ${w.firstWeekReaders})`);
    ok(w.weeks[0].active === 2 && w.weeks[0].new === 2 && w.weeks[0].ofFirst === 2 && w.weeks[7].active === 2 && w.weeks[7].new === 1 && w.weeks[7].ofFirst === 1 && w.weeks[3].active === 0, "week 1: 2 active 2 new; this week: A back (of week 1's: 1), C new; a row before the window is ignored");
    r = await worker.fetch(new Request("https://ipodesk.dev/admin/me.json", { headers: { "Cf-Access-Jwt-Assertion": alice } }), Object.assign({}, salted, { BACKUP_BUCKET: "ipo-desk-backups" }), ctx);
    b = await r.json();
    ok(b.dauSalt === true && b.accounts === true && b.backupBucket === "ipo-desk-backups", "me.json reports the salt, the binding and the backup bucket");

    // no binding: fail closed on the API, the page still serves
    const env2 = Object.assign({}, env, { DB: undefined });
    r = await worker.fetch(new Request("https://ipodesk.dev/api/state", { headers: { "Cf-Access-Jwt-Assertion": alice } }), env2, ctx);
    ok(r.status === 503, "no D1 binding -> 503");
    r = await worker.fetch(new Request("https://ipodesk.dev/", { headers: { "Cf-Access-Jwt-Assertion": alice } }), env2, ctx);
    ok(r.status === 200, "no D1 binding -> the page is still served");
    // handleApi with a token that has no email claim
    r = await handleApi(new Request("https://ipodesk.dev/api/state"), env, {}, new URL("https://ipodesk.dev/api/state"));
    ok(r.status === 401, "no email claim -> 401");
  } finally { globalThis.fetch = realFetch; }
  return { passed: out.filter(o => o.ok).length, failed: out.filter(o => !o.ok), all: out };
}
