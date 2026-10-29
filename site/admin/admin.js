/* ================= ADMIN — /admin, served to ADMIN_EMAIL only (ops/site-worker/worker.js) =================
   Reads: audit.json (scripts/audit.py, written by site/build.py from the same document the page shows),
   data/meta.json (the document's asOf), GitHub's public API (runs; the live branch's last commit — the repo is
   public, no token, 60 calls an hour per IP, a visit costs about four), /admin/me.json (the Worker's own view
   of the gate). Everything here is "time since" and rendering; the facts come from the audit.                     */
(function () {
"use strict";
const $ = (s, r) => (r || document).querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const REPO = "harimano/ipo-desk", API = "https://api.github.com/repos/" + REPO;
const IST = 330;
const nowIST = () => new Date(Date.now() + (IST + new Date().getTimezoneOffset()) * 60000);   // wall clock in IST
const pad = n => String(n).padStart(2, "0");
const hhmm = d => pad(d.getHours()) + ":" + pad(d.getMinutes());
const toIST = iso => { const d = new Date(iso); return isNaN(d) ? null : new Date(d.getTime() + (IST + d.getTimezoneOffset()) * 60000); };
const fmtIST = iso => { const d = toIST(iso); return d ? d.getDate() + " " + ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getMonth()] + " " + hhmm(d) : "—"; };
const ago = iso => {
  const t = new Date(iso).getTime(); if (isNaN(t)) return "";
  const m = Math.round((Date.now() - t) / 60000);
  return m < 1 ? "just now" : m < 60 ? m + " min ago" : m < 48 * 60 ? Math.round(m / 60 * 10) / 10 + " h ago" : Math.round(m / 1440) + " d ago";
};
const minsAgo = iso => (Date.now() - new Date(iso).getTime()) / 60000;
const pill = (lvl, txt) => `<span class="pill ${lvl}">${esc(txt)}</span>`;
const row = (k, v, p, sub) => `<div class="row"><span class="k">${esc(k)}</span><span class="v">${v}${sub ? `<small>${sub}</small>` : ""}</span>${p || ""}</div>`;
const LVL = { ok: "ok", warn: "warn", bad: "bad", known: "known" };
const tile = (id, val, lvl, sub) => { const t = $(id); t.className = "tile " + (lvl || ""); $(".val", t).textContent = val; $(".dt", t).innerHTML = sub || ""; };

async function getJson(url, opts) {
  const ctl = new AbortController(); const tm = setTimeout(() => ctl.abort(), 15000);
  try {
    const r = await fetch(url, Object.assign({ signal: ctl.signal }, opts || {}));
    if (!r.ok) {
      const reset = r.headers.get("x-ratelimit-reset"), left = r.headers.get("x-ratelimit-remaining");
      if (r.status === 403 && left === "0" && reset) throw new Error("GitHub's hourly limit for this address is used up; it resets at " + hhmm(toIST(new Date(reset * 1000).toISOString())) + " IST");
      throw new Error("HTTP " + r.status);
    }
    return await r.json();
  }
  finally { clearTimeout(tm); }
}

/* ---------- what "fresh" means, from collect.yml / live.yml's crons (IST) ---------- */
function docExpectation(asOf) {
  const n = nowIST(), wd = n.getDay() % 6 !== 0, m = n.getHours() * 60 + n.getMinutes(), age = minsAgo(asOf);
  const intraday = wd && m >= 9 * 60 + 50 && m <= 17 * 60 + 50;           // 09:37 … 17:37 every 30 min, plus a run's own minutes
  if (intraday) return age > 75 ? ["bad", "an intraday run is overdue (every 30 min on weekdays)"] : age > 45 ? ["warn", "the last intraday run is late"] : ["ok", "intraday runs every 30 min"];
  return age > 14 * 60 ? ["bad", "no full run since " + fmtIST(asOf) + " (06:43 and 18:13 IST)"] : ["ok", "full runs 06:43 and 18:13 IST"];
}
function liveExpectation(asOf) {
  const n = nowIST(), wd = n.getDay() % 6 !== 0, m = n.getHours() * 60 + n.getMinutes();
  const open = wd && m >= 9 * 60 && m <= 17 * 60 + 40;
  if (!open) return ["ok", "market closed · the loop runs 08:55–17:40 IST on weekdays"];
  const age = minsAgo(asOf);
  return age > 20 ? ["bad", "the five-minute loop has not written for " + Math.round(age) + " min"] : age > 9 ? ["warn", "loop late"] : ["ok", "writing every five minutes"];
}

/* ---------- the audit (scripts/audit.py) ---------- */
let AUDIT = null;
function renderAudit(a) {
  const v = a.verdict || { level: "ok", items: [] };
  const vb = $("#verdict"); vb.className = v.level;
  $("#vTitle").textContent = v.level === "ok" ? "Nothing needs you." : v.level === "bad" ? `${v.items.length} thing${v.items.length > 1 ? "s" : ""} need a look.` : `${v.items.length} thing${v.items.length > 1 ? "s are" : " is"} worth a look.`;
  $("#vList").innerHTML = v.items.map(i => `<li>${pill(i.level, i.level)} ${esc(i.text)} <a href="#${esc(i.where)}" class="mu">→ ${esc(i.where)}</a></li>`).join("");
  const b = a.doc.boards || {}, cnt = s => Object.entries(b[s] || {}).map(([k, n]) => `${n} ${k.toLowerCase()}`).join(", ");
  $("#vSub").textContent = `Document ${a.doc.label || a.doc.asOf} · mainboard ${cnt("mainboard") || "empty"} · SME ${cnt("sme") || "empty"} · ${(a.doc.bytesCompact / 1048576).toFixed(2)} MB of ${(a.doc.capBytes / 1048576).toFixed(0)} MB cap · audit built ${fmtIST(a.generated)} IST`;

  // modules
  const mods = a.modules || [];
  $("#modules").innerHTML = mods.length ? mods.map(m => {
    const when = m.asOf ? `${fmtIST(m.asOf)}${m.asOf.length > 10 ? " · " + ago(m.asOf) : ""}` : (m.asOfRaw ? "stamped " + esc(m.asOfRaw) : "");
    const txt = m.level === "known" ? "known gap" : m.level === "warn" ? "fallback" : m.status;
    const note = m.note.length > 150 ? `<span title="${esc(m.note)}">${esc(m.note.slice(0, 150))}…</span>` : esc(m.note);
    return row(m.area, `${esc(m.method)}${m.carried ? " <span class='mu'>· carried from an earlier run</span>" : ""}`, pill(LVL[m.level] || "nt", txt),
      esc(when) + (when && note ? " · " : "") + note + (m.known ? `<br>${esc(m.known)}` : ""));
  }).join("") : `<div class="empty">No integrity checks in the document.</div>`;

  // diff
  const d = a.diff || {};
  $("#diffSub").textContent = d.prevAsOf ? `previous: ${fmtIST(d.prevAsOf)} IST (data/history)` : "no earlier document to compare";
  const parts = [];
  for (const [bd, x] of Object.entries(d.boards || {})) {
    const bits = [];
    if (x.added.length) bits.push(`+${x.added.length} new: ${esc(x.added.join(", "))}`);
    if (x.retired.length) bits.push(`−${x.retired.length} retired on schedule: ${esc(x.retired.join(", "))}`);
    if (x.vanished.length) bits.push(`<b>−${x.vanished.length} left early: ${esc(x.vanished.join(", "))}</b>`);
    parts.push(row(bd, bits.join("<br>") || "<span class='mu'>no rows in or out</span>", pill(x.vanished.length ? "bad" : "nt", `${x.prev} → ${x.now}`)));
  }
  if ((d.statusMoves || []).length) parts.push(row("status", d.statusMoves.map(s => `${esc(s.name)} <span class='mu'>${esc(s.from)} →</span> ${esc(s.to)}`).join("<br>"), pill("nt", d.statusMoves.length + " moved")));
  if ((d.sourceSwitches || []).length) parts.push(row("sources", d.sourceSwitches.map(s => `${esc(s.area)}: <span class='mu'>${esc(s.from)} →</span> ${esc(s.to)}`).join("<br>"), pill("warn", "switched")));
  const w = d.warnings || {};
  if ((w.added || []).length || (w.removed || []).length) parts.push(row("warnings", `${w.added.length ? "+ " + esc(w.added.join(", ")) : ""}${w.added.length && w.removed.length ? "<br>" : ""}${w.removed.length ? "− " + esc(w.removed.join(", ")) : ""}`, pill("nt", "changed")));
  const moved = Object.entries(d.counts || {}).filter(([, [p, n]]) => p !== n);
  if (moved.length) parts.push(row("counts", moved.map(([k, [p, n]]) => `${esc(k)} <span class='mu'>${p} →</span> ${n}`).join(" · "), ""));
  $("#diff").innerHTML = parts.join("") || `<div class="empty">Nothing moved.</div>`;

  // audit
  const au = a.audit || [], extra = [];
  if ((a.warnings || []).length) extra.push(row("evidence warnings", a.warnings.map(x => `<b>${esc(x.code)}</b> ${esc(x.text)}`).join("<br>"), pill("nt", a.warnings.length), "shown on the page's Scoreboard too"));
  if ((a.unresolved || []).length) extra.push(row("unresolved", a.unresolved.map(esc).join("<br>"), pill("warn", a.unresolved.length), "meta.unresolved — what a module could not settle"));
  if ((a.awaiting || []).length) extra.push(row("awaiting data", esc(a.awaiting.join(", ")), pill("nt", a.awaiting.length), "expected issues with no record yet"));
  if ((a.discrepancies || []).length) extra.push(row("discrepancies", a.discrepancies.slice(-8).map(x => esc(typeof x === "string" ? x : JSON.stringify(x))).join("<br>"), pill("nt", a.discrepancies.length), "integrity.discrepancies — where two sources disagreed"));
  $("#audit").innerHTML = (au.length ? au.map(f => row(f.check, f.rows.map(esc).join("<br>"), pill(f.level, f.rows.length))).join("")
    : `<div class="row"><span class="k">rows</span><span class="v">Every board row passes the soft checks.</span>${pill("ok", "clean")}</div>`)
    + (extra.length ? `<details><summary>Also in the document (${extra.length})</summary>${extra.join("")}</details>` : "");
}

/* ---------- GitHub: runs and the live branch ---------- */
function runRow(r) {
  const started = r.run_started_at || r.created_at, secs = Math.round((new Date(r.updated_at) - new Date(started)) / 1000);
  const how = r.event === "schedule" ? "cron (the fallback clock)" : r.event === "workflow_dispatch" ? "dispatched" : r.event;
  const lvl = r.status !== "completed" ? "nt" : r.conclusion === "success" ? "ok" : r.conclusion === "cancelled" ? "nt" : "bad";
  const txt = r.status !== "completed" ? r.status.replace("_", " ") : r.conclusion;
  return row(`${hhmm(toIST(started))} ${r.name}`, `<a href="${esc(r.html_url)}" target="_blank" rel="noopener">${esc(r.display_title || r.name)}</a> <span class="mu">· ${esc(how)} · ${secs}s${r.run_attempt > 1 ? " · attempt " + r.run_attempt : ""}</span>`, pill(lvl, txt));
}
function paintRuns(runs, source) {
  const byDay = {};
  for (const r of runs) { const d = toIST(r.run_started_at || r.created_at); const k = `${d.getDate()} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getMonth()]}`; (byDay[k] = byDay[k] || []).push(r); }
  $("#runs").innerHTML = `<div class="dt" id="runsSrc" style="padding:4px 0 6px">${source}</div>`
    + (Object.entries(byDay).map(([day, rs], i) => (i === 0 ? rs.map(runRow).join("") : `<details><summary>${esc(day)} · ${rs.length} runs${rs.some(r => r.conclusion && r.conclusion !== "success" && r.conclusion !== "cancelled") ? " · " + pill("bad", "a failure") : ""}</summary>${rs.map(runRow).join("")}</details>`)).join("") || `<div class="empty">No runs.</div>`);
  const last = name => runs.find(r => r.name === name && r.status === "completed");
  const c = last("collect"), dp = last("deploy");
  tile("#tRun", c ? hhmm(toIST(c.run_started_at)) : "—", c ? (c.conclusion === "success" ? "ok" : "bad") : "", c ? `${esc(c.conclusion)} · ${ago(c.run_started_at)} · ${c.event === "schedule" ? "cron" : "dispatched"}` : "");
  tile("#tDeploy", dp ? hhmm(toIST(dp.run_started_at)) : "—", dp ? (dp.conclusion === "success" ? "ok" : "bad") : "", dp ? `${esc(dp.conclusion)} · ${ago(dp.run_started_at)}` : "");
}
function judgeRuns(runs) {
  const failed = runs.filter(r => r.status === "completed" && !["success", "cancelled", "skipped"].includes(r.conclusion));
  if (failed.length) addVerdict("bad", `${failed.length} run${failed.length > 1 ? "s" : ""} failed in the last ${runs.length} (${failed.map(r => r.name).join(", ")})`, "runs");
  const crons = runs.filter(r => r.name === "collect" && r.event === "schedule").length, disp = runs.filter(r => r.name === "collect" && r.event === "workflow_dispatch").length;
  if (crons > disp) addVerdict("warn", `the trigger Worker dispatched only ${disp} of the last ${crons + disp} collects — GitHub's cron carried the rest`, "runs");
}
/* The run list has TWO sources. runs.json is written by deploy.yml with the Actions token (no call limit) and is as
   fresh as the last deploy — every collect deploys, so at most one run old. GitHub's public API, called from here, is
   fresher but limited to 60 calls an hour per address, shared with the page's own live polling: it freshens the list
   when it can and is never the only source. */
let SNAP = null;
async function snapshot() { if (SNAP === null) { try { SNAP = await getJson("runs.json?t=" + Date.now(), { cache: "no-store" }); } catch (e) { SNAP = false; } } return SNAP; }
async function renderRuns() {
  const snap = await snapshot();
  if (snap && snap.runs) paintRuns(snap.runs, `as of the last deploy, ${ago(snap.at)} · asking GitHub for newer…`);
  try {
    const live = (await getJson(API + "/actions/runs?per_page=40")).workflow_runs || [];
    paintRuns(live, "live from GitHub"); judgeRuns(live);
  } catch (e) {
    if (snap && snap.runs) { judgeRuns(snap.runs); $("#runsSrc").textContent = `as of the last deploy, ${ago(snap.at)} · GitHub itself did not answer (${e.message})`; }
    else { $("#runs").innerHTML = `<div class="empty">No runs.json (a local build) and GitHub did not answer (${esc(e.message)}).</div>`; tile("#tRun", "?", "warn", "no run data"); tile("#tDeploy", "?", "warn", ""); }
  }
}
/* The live loop: live.json's own asOf, read raw from the live branch (cached up to five minutes, no call limit); the
   deploy's snapshot of the branch's last commit is the fallback. */
const LIVE_RAW = "https://raw.githubusercontent.com/harimano/ipo-desk/live/live.json";
async function renderLive() {
  let asOf = null, note = "";
  try { asOf = (await getJson(LIVE_RAW)).asOf; }
  catch (e) { const snap = await snapshot(); if (snap && snap.live) { asOf = snap.live.asOf; note = " · from the last deploy's snapshot"; } }
  if (!asOf) { tile("#tLive", "?", "warn", "could not read live.json"); return; }
  const [lvl, why] = liveExpectation(asOf);
  tile("#tLive", hhmm(toIST(asOf)), lvl, `${ago(asOf)} · ${esc(why)}${note}`);
  if (lvl === "bad") addVerdict("bad", why, "runs");
}

/* ---------- the verdict can grow after the audit: runs and the live loop are read here, not by audit.py ---------- */
const ORDER = { bad: 0, warn: 1, ok: 2 };
function addVerdict(level, text, where) {
  const vb = $("#verdict"), cur = vb.className;
  if (ORDER[level] < (ORDER[cur] ?? 9)) { vb.className = level; }
  $("#vList").insertAdjacentHTML("beforeend", `<li>${pill(level, level)} ${esc(text)} <a href="#${esc(where)}" class="mu">→ ${esc(where)}</a></li>`);
  const n = $("#vList").children.length, l = vb.className;
  $("#vTitle").textContent = l === "ok" ? "Nothing needs you." : l === "bad" ? `${n} thing${n > 1 ? "s" : ""} need a look.` : `${n} thing${n > 1 ? "s are" : " is"} worth a look.`;
}

/* ---------- security: what this browser is actually served ---------- */
async function renderSecurity() {
  const out = [];
  let me = null;
  try { me = await getJson("/admin/me.json", { cache: "no-store" }); } catch (e) { me = { error: e.message }; }
  if (me && !me.error) {
    $("#who").textContent = me.email || "";
    out.push(row("access", `team ${esc(me.team || "?")} · you are ${esc(me.email || "?")} · JWT re-verified by the Worker on every request`, pill("ok", "on")));
    out.push(row("/admin", me.adminEmailSet ? "served only to ADMIN_EMAIL; everyone else gets 403" : "<b>ADMIN_EMAIL is not set — /admin answers 404 to everyone, including you</b>", pill(me.adminEmailSet ? "ok" : "bad", me.adminEmailSet ? "gated" : "unset")));
  } else {
    out.push(row("access", `no gate answered (${esc(me.error)}) — a local preview, or the Worker is not in front`, pill(location.hostname === "localhost" || location.hostname === "127.0.0.1" ? "nt" : "bad", location.hostname.startsWith("127.") || location.hostname === "localhost" ? "local" : "open?")));
  }
  try {
    const r = await fetch("/", { method: "HEAD", cache: "no-store" });
    const want = { "x-robots-tag": "noindex", "referrer-policy": "no-referrer", "x-content-type-options": "nosniff" };
    const got = Object.entries(want).map(([h, v]) => [h, (r.headers.get(h) || "").includes(v)]);
    out.push(row("headers on /", got.map(([h, ok]) => `${ok ? "✓" : "✗"} ${esc(h)}`).join(" · "), pill(got.every(([, ok]) => ok) ? "ok" : "warn", `${got.filter(([, ok]) => ok).length}/${got.length}`), "set by the Worker; a local preview has none of them"));
  } catch (e) { out.push(row("headers on /", esc(e.message), pill("warn", "?"))); }
  out.push(row("repo", "public by choice (ops/site-worker/README.md) · the document is on the data branch, the Book never leaves the browser · secrets are GitHub secrets, never in the repo", pill("nt", "note")));
  $("#sec").innerHTML = out.join("");
  return me && !me.error ? me : null;
}

/* ---------- visitors: the Worker's KV ledger (/admin/visitors.json) ---------- */
const dayKey = iso => { const d = toIST(iso); return d ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` : ""; };
async function renderVisitors(me) {
  const box = $("#visitors");
  let v;
  try { v = await getJson("/admin/visitors.json", { cache: "no-store" }); }
  catch (e) { box.innerHTML = `<div class="empty">No ledger answered (${esc(e.message)}) — a local preview, or the Worker is not in front.</div>`; return; }
  if (v.error) { box.innerHTML = row("setup", `${esc(v.error)}<small>Workers &amp; Pages → KV → Create a namespace → paste its id into the [[kv_namespaces]] block of ops/site-worker/wrangler.toml → push. Until then nothing is recorded.</small>`, pill("warn", "KV not set up")); $("#visSum").textContent = ""; return; }
  const list = v.visitors || [], today = dayKey(new Date().toISOString()), week = Date.now() - 7 * 86400000;
  const mine = (me && me.email || "").toLowerCase();
  const todayN = list.filter(x => dayKey(x.last) === today).length, weekN = list.filter(x => Date.parse(x.last) > week).length;
  $("#visSum").textContent = list.length ? `${list.length} people · ${todayN} today · ${weekN} this week` : "";
  if (!list.length) { box.innerHTML = `<div class="empty">Nobody recorded yet. The ledger starts with the first page load after the binding went live.</div>`; return; }
  box.innerHTML = `<div class="row" style="border-top:0"><span class="k mu">who</span><span class="v mu">first seen · last seen</span><span class="mu">loads</span></div>`
    + list.map(x => row(x.email === mine ? "you" : x.email, `${fmtIST(x.first)} · <b>${fmtIST(x.last)}</b> <span class="mu">${ago(x.last)}${x.country ? " · " + esc(x.country) : ""}${x.admin && x.email !== mine ? " · opened /admin" : ""}</span>`,
        pill(dayKey(x.last) === today ? "ok" : "nt", x.n))).join("")
    + `<div class="dt" style="padding-top:8px">A load is one page open per person, counted at most once every ten minutes. Someone who got the link and never finished the email code is not here; Cloudflare's Access log has every attempt.</div>`;
}

/* ---------- the smoke test: the page in a hidden same-origin frame, every tab, every sheet ---------- */
const TAP = `<script>window.__smoke={errors:[]};addEventListener("error",e=>__smoke.errors.push(String(e.message||e)));addEventListener("unhandledrejection",e=>__smoke.errors.push("rejection: "+String(e.reason&&e.reason.message||e.reason)));const _ce=console.error.bind(console);console.error=(...a)=>{__smoke.errors.push(a.map(String).join(" "));_ce(...a)};<\/script>`;
async function smoke() {
  const btn = $("#smoke"), out = $("#smokeOut"), fr = $("#frame"); btn.disabled = true; out.innerHTML = `<div class="empty">Loading the page…</div>`; tile("#tPage", "…", "", "running");
  const t0 = performance.now(), steps = [];
  try {
    const html = await (await fetch("/", { cache: "no-store" })).text();
    fr.hidden = false;
    await new Promise((res, rej) => { fr.onload = res; fr.onerror = rej; fr.srcdoc = html.replace(/<head>/i, `<head><base href="${location.origin}/">` + TAP); setTimeout(res, 15000); });
    const w = fr.contentWindow, d = fr.contentDocument;
    const until = async (f, ms) => { const t = Date.now(); while (!f() && Date.now() - t < ms) await new Promise(r => setTimeout(r, 100)); return f(); };
    const live = await until(() => w.__ipo && d.querySelectorAll("#rsel option").length > 0, 12000);
    steps.push(live ? "page booted, data fetched" : "the page did not finish booting in 12 s");
    const tabs = [...d.querySelectorAll("#nav button[data-s]")];
    for (const b of tabs) { b.click(); await new Promise(r => setTimeout(r, 60)); }
    steps.push(`${tabs.length} tabs opened`);
    const sel = d.querySelector("#rsel"), opts = sel ? [...sel.options] : [];
    for (const o of opts) { sel.value = o.value; if (typeof sel.onchange === "function") sel.onchange(); else sel.dispatchEvent(new w.Event("change")); }
    steps.push(`${opts.length} Research sheets rendered`);
    try { if (w.__ipo && w.__ipo.live) { w.__ipo.live({ asOf: new Date().toISOString(), rows: {} }); steps.push("live overlay called"); } } catch (e) { w.__smoke.errors.push("live(): " + e.message); }
    const errs = (w.__smoke && w.__smoke.errors) || [];
    const meta = await getJson("/data/meta.json?t=" + Date.now(), { cache: "no-store" });
    const files = Object.entries(meta.files || {});
    const heads = await Promise.all(files.map(([n, f]) => fetch(`/data/${n}.json?h=${f.hash}`, { method: "HEAD" }).then(r => [n, r.ok, r.headers.get("content-length")])));
    const badParts = heads.filter(([, ok]) => !ok);
    steps.push(`${files.length} data parts answer${badParts.length ? ", MISSING: " + badParts.map(x => x[0]).join(", ") : ""}`);
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    const lvl = errs.length || badParts.length || !live ? "bad" : "ok";
    out.innerHTML = row("result", steps.map(esc).join(" · "), pill(lvl, lvl === "ok" ? "clean" : "errors"), `${secs} s · ${new Date().toLocaleTimeString()}`)
      + (errs.length ? row("console errors", errs.slice(0, 20).map(esc).join("<br>"), pill("bad", errs.length)) : "")
      + row("chart.js", (w.Chart ? "loaded " + esc(w.Chart.version) : "<b>not loaded</b>"), pill(w.Chart ? "ok" : "bad", w.Chart ? "ok" : "missing"), "pinned with an integrity hash in site/build.py");
    tile("#tPage", lvl === "ok" ? "clean" : `${errs.length || "!"} errors`, lvl, `${tabs.length} tabs · ${opts.length} sheets · ${secs} s`);
    if (lvl !== "ok") addVerdict("bad", `the page smoke test found ${errs.length} console error${errs.length === 1 ? "" : "s"}${badParts.length ? " and missing data parts" : ""}`, "smokeOut");
  } catch (e) {
    out.innerHTML = row("result", esc(e.message), pill("bad", "failed")); tile("#tPage", "failed", "bad", esc(e.message));
  } finally { btn.disabled = false; fr.srcdoc = ""; fr.hidden = true; }
}

/* ---------- boot ---------- */
async function main() {
  $("#clock").textContent = hhmm(nowIST()) + " IST";
  try {
    const meta = await getJson("/data/meta.json?t=" + Date.now(), { cache: "no-store" });
    const [lvl, why] = docExpectation(meta.meta.asOf);
    tile("#tDoc", hhmm(toIST(meta.meta.asOf)), lvl, `${ago(meta.meta.asOf)} · ${esc(why)}`);
    if (lvl !== "ok") addVerdict(lvl, "the document is stale: " + why, "runs");
  } catch (e) { tile("#tDoc", "?", "bad", "meta.json did not load: " + esc(e.message)); addVerdict("bad", "the page's own data did not load", "runs"); }
  try { AUDIT = await getJson("audit.json?t=" + Date.now(), { cache: "no-store" }); renderAudit(AUDIT); }
  catch (e) { $("#vTitle").textContent = "No audit.json"; $("#vSub").textContent = "site/build.py writes admin/audit.json from scripts/audit.py — " + e.message; $("#verdict").className = "bad"; }
  await Promise.all([renderRuns(), renderLive(), renderSecurity().then(renderVisitors)]);
}
$("#reload").addEventListener("click", () => location.reload());
$("#smoke").addEventListener("click", smoke);
try { const th = localStorage.getItem("ipo-theme"); if (th === "dark" || th === "light") document.documentElement.dataset.theme = th; } catch (e) { /* storage blocked */ }
main();
})();
