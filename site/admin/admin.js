/* ================= ADMIN — /admin, served to ADMIN_EMAIL only (ops/site-worker/worker.js) =================
   Reads: audit.json (scripts/audit.py, written by site/build.py from the same document the page shows),
   runs.json (deploy.yml's snapshot of GitHub's run list, taken with the Actions token), data/meta.json (the
   document's asOf), raw live.json from the live branch, GitHub's public API (only to freshen the run list — the
   repo is public, 60 calls an hour per address, never the only source), /admin/me.json and /admin/visitors.json
   (the Worker's own view of the gate and its ledger). Everything here is "time since" and rendering; the facts
   come from the audit and the Worker. Every list is a table: one line per record, columns aligned.                */
(function () {
"use strict";
const $ = (s, r) => (r || document).querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const REPO = "harimano/ipo-desk", API = "https://api.github.com/repos/" + REPO;
const IST = 330;
const nowIST = () => new Date(Date.now() + (IST + new Date().getTimezoneOffset()) * 60000);   // wall clock in IST
const pad = n => String(n).padStart(2, "0");
const hhmm = d => pad(d.getHours()) + ":" + pad(d.getMinutes());
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const toIST = iso => { const d = new Date(iso); return isNaN(d) ? null : new Date(d.getTime() + (IST + d.getTimezoneOffset()) * 60000); };
const fmtIST = iso => { const d = toIST(iso); return d ? `${d.getDate()} ${MON[d.getMonth()]} ${hhmm(d)}` : "—"; };
const dayIST = iso => { const d = toIST(iso); return d ? `${d.getDate()} ${MON[d.getMonth()]}` : "—"; };
const ago = iso => {
  const t = new Date(iso).getTime(); if (isNaN(t)) return "";
  const m = Math.round((Date.now() - t) / 60000);
  return m < 1 ? "just now" : m < 60 ? m + " min ago" : m < 48 * 60 ? Math.round(m / 60 * 10) / 10 + " h ago" : Math.round(m / 1440) + " d ago";
};
const minsAgo = iso => (Date.now() - new Date(iso).getTime()) / 60000;
const pill = (lvl, txt) => `<span class="pill ${lvl}">${esc(txt)}</span>`;
const LVL = { ok: "ok", warn: "warn", bad: "bad", known: "known" };
const tile = (id, val, lvl, sub) => { const t = $(id); t.className = "tile " + (lvl || ""); $(".val", t).textContent = val; $(".dt", t).innerHTML = sub || ""; $(".dt", t).title = $(".dt", t).textContent; };
const td = (html, cls, title) => `<td${cls ? ` class="${cls}"` : ""}${title ? ` title="${esc(title)}"` : ""}>${html}</td>`;
const table = (heads, rows) => rows.length ? `<table class="t"><thead><tr>${heads.map(h => `<th${h.endsWith("|n") ? ' class="n"' : h.endsWith("|fit") ? ' class="fit"' : ""}>${esc(h.split("|")[0])}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>` : "";
const empty = txt => `<div class="empty">${txt}</div>`;
const note = txt => `<div class="note">${txt}</div>`;

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
  } finally { clearTimeout(tm); }
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
  if (!open) return ["ok", "market closed · runs 08:55–17:40 IST on weekdays"];
  const age = minsAgo(asOf);
  return age > 20 ? ["bad", "the five-minute loop has not written for " + Math.round(age) + " min"] : age > 9 ? ["warn", "loop late"] : ["ok", "writing every five minutes"];
}

/* ---------- the verdict line: the audit's items first; runs, the live loop and the smoke test add theirs ---------- */
const ORDER = { bad: 0, warn: 1, ok: 2 };
function setTitle() {
  const n = $("#vList").children.length, l = $("#verdict").className;
  $("#vTitle").textContent = l === "ok" ? "Nothing needs you." : l === "bad" ? (n > 1 ? `${n} things need a look.` : "One thing needs a look.") : (n > 1 ? `${n} things are worth a look.` : "One thing is worth a look.");
}
function addVerdict(level, text, where) {
  const vb = $("#verdict");
  if (ORDER[level] < (ORDER[vb.className] ?? 9)) vb.className = level;
  $("#vList").insertAdjacentHTML("beforeend", `<li>${pill(level, level)} ${esc(text)} <a href="#${esc(where)}" class="mu">→ ${esc(where)}</a></li>`);
  setTitle();
}

/* ---------- the audit (scripts/audit.py): verdict, modules, diff, audit ---------- */
function renderAudit(a) {
  const v = a.verdict || { level: "ok", items: [] };
  $("#verdict").className = v.level;
  $("#vList").innerHTML = v.items.map(i => `<li>${pill(i.level, i.level)} ${esc(i.text)} <a href="#${esc(i.where)}" class="mu">→ ${esc(i.where)}</a></li>`).join("");
  setTitle();
  const b = a.doc.boards || {}, cnt = s => Object.entries(b[s] || {}).map(([k, n]) => `${n} ${k.toLowerCase()}`).join(", ");
  $("#vSub").textContent = `Document ${a.doc.label || a.doc.asOf} · mainboard ${cnt("mainboard") || "empty"} · SME ${cnt("sme") || "empty"} · ${(a.doc.bytesCompact / 1048576).toFixed(2)} MB of ${(a.doc.capBytes / 1048576).toFixed(0)} MB cap · audit built ${fmtIST(a.generated)} IST`;

  // modules: one line each
  const mods = a.modules || [];
  $("#modules").innerHTML = mods.length ? table(["module", "source", "when|fit", "note", "|fit"], mods.map(m => {
    const when = m.asOf ? (m.asOf.length > 10 ? ago(m.asOf) : dayIST(m.asOf)) : (m.asOfRaw ? esc(m.asOfRaw) : "");
    const txt = m.level === "known" ? "known gap" : m.level === "warn" ? "fallback" : m.status;
    return `<tr>${td(esc(m.area), "k")}${td(esc(m.method) + (m.carried ? ' <span class="mu">· carried</span>' : ""), "", m.method)}${td(esc(when), "fit mu", m.asOfRaw || "")}${td(esc(m.note || m.known || ""), "mu", (m.note || "") + (m.known ? "\n" + m.known : ""))}${td(pill(LVL[m.level] || "nt", txt), "fit")}</tr>`;
  })) : empty("No integrity checks in the document.");

  // diff: what | detail | change
  const d = a.diff || {};
  $("#diffSub").textContent = d.prevAsOf ? `previous: ${fmtIST(d.prevAsOf)} IST` : "no earlier document to compare";
  const rows = [];
  for (const [bd, x] of Object.entries(d.boards || {})) {
    const bits = [];
    if (x.added.length) bits.push(`+${x.added.length} new: ${x.added.join(", ")}`);
    if (x.retired.length) bits.push(`−${x.retired.length} retired on schedule: ${x.retired.join(", ")}`);
    if (x.vanished.length) bits.push(`−${x.vanished.length} LEFT EARLY: ${x.vanished.join(", ")}`);
    rows.push(`<tr>${td(esc(bd), "k fit")}${td(esc(bits.join(" · ") || "no rows in or out"), bits.length ? "" : "mu", bits.join("\n"))}${td(pill(x.vanished.length ? "bad" : "nt", `${x.prev} → ${x.now}`), "fit")}</tr>`);
  }
  for (const s of d.statusMoves || []) rows.push(`<tr>${td("status", "k fit")}${td(esc(s.name), "", s.name)}${td(`<span class="mu">${esc(s.from)} →</span> ${esc(s.to)}`, "fit")}</tr>`);
  for (const s of d.sourceSwitches || []) rows.push(`<tr>${td("source", "k fit")}${td(`${esc(s.area)}: <span class="mu">${esc(s.from)} →</span> ${esc(s.to)}`, "", `${s.from} → ${s.to}`)}${td(pill("warn", "switched"), "fit")}</tr>`);
  const w = d.warnings || {};
  for (const c of w.added || []) rows.push(`<tr>${td("warning", "k fit")}${td(esc(c))}${td(pill("nt", "new"), "fit")}</tr>`);
  for (const c of w.removed || []) rows.push(`<tr>${td("warning", "k fit")}${td(esc(c))}${td(pill("nt", "gone"), "fit")}</tr>`);
  for (const [k, [p, n]] of Object.entries(d.counts || {})) if (p !== n) rows.push(`<tr>${td("count", "k fit")}${td(esc(k))}${td(`<span class="mu">${p} →</span> ${n}`, "fit n")}</tr>`);
  $("#diff").innerHTML = rows.length ? table(["what|fit", "detail", "change|fit"], rows) : empty("Nothing moved.");

  // audit: check | rows | n
  const au = a.audit || [], extra = [];
  const arow = (k, items, p, lvl) => `<tr>${td(esc(k), "k fit")}${td(esc(items.join(", ")), "", items.join("\n"))}${td(pill(lvl, p), "fit")}</tr>`;
  const main_ = au.map(f => arow(f.check, f.rows, f.rows.length, f.level));
  if ((a.unresolved || []).length) extra.push(arow("unresolved", a.unresolved, a.unresolved.length, "warn"));
  if ((a.warnings || []).length) extra.push(arow("evidence warnings", a.warnings.map(x => x.code), a.warnings.length, "nt"));
  if ((a.awaiting || []).length) extra.push(arow("awaiting data", a.awaiting, a.awaiting.length, "nt"));
  if ((a.discrepancies || []).length) extra.push(arow("discrepancies", a.discrepancies.slice(-8).map(x => typeof x === "string" ? x : JSON.stringify(x)), a.discrepancies.length, "nt"));
  $("#audit").innerHTML = (main_.length ? "" : note(`${pill("ok", "clean")} every board row passes the soft checks`))
    + table(["check|fit", "rows", "|fit"], main_.concat(extra.map((r, i) => i === 0 ? r.replace("<tr>", '<tr class="sep">') : r)));
}

/* ---------- runs: deploy.yml's snapshot first, GitHub's own list when it answers ---------- */
function runRow(r, prev) {
  const started = r.run_started_at || r.created_at, secs = Math.round((new Date(r.updated_at) - new Date(started)) / 1000);
  const how = r.event === "schedule" ? "cron" : r.event === "workflow_dispatch" ? "dispatched" : r.event;
  const lvl = r.status !== "completed" ? "nt" : r.conclusion === "success" ? "ok" : r.conclusion === "cancelled" ? "nt" : "bad";
  const txt = r.status !== "completed" ? r.status.replace("_", " ") : r.conclusion;
  const d = toIST(started), day = dayIST(started), newDay = prev && dayIST(prev.run_started_at || prev.created_at) !== day;
  return `<tr${newDay ? ' class="sep"' : ""}>${td(`${!prev || newDay ? day + " " : ""}${hhmm(d)}`, "k fit")}${td(`<a href="${esc(r.html_url)}" target="_blank" rel="noopener">${esc(r.name)}</a>`, "fit")}${td(esc(r.display_title === r.name ? "" : r.display_title || ""), "mu", r.display_title)}${td(esc(how), "fit mu")}${td(secs + "s", "fit n mu")}${td(pill(lvl, txt), "fit")}</tr>`;
}
function paintRuns(runs, source) {
  $("#runsSrc").textContent = source;
  $("#runs").innerHTML = runs.length ? table(["when|fit", "workflow|fit", "commit", "how|fit", "took|n", "|fit"], runs.map((r, i) => runRow(r, runs[i - 1]))) : empty("No runs.");
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
let SNAP = null;
async function snapshot() { if (SNAP === null) { try { SNAP = await getJson("runs.json?t=" + Date.now(), { cache: "no-store" }); } catch (e) { SNAP = false; } } return SNAP; }
async function renderRuns() {
  const snap = await snapshot();
  if (snap && snap.runs) paintRuns(snap.runs, `as of the last deploy, ${ago(snap.at)} · asking GitHub for newer…`);
  try {
    const live = (await getJson(API + "/actions/runs?per_page=40")).workflow_runs || [];
    paintRuns(live, "live from GitHub Actions, newest first"); judgeRuns(live);
  } catch (e) {
    if (snap && snap.runs) { judgeRuns(snap.runs); $("#runsSrc").textContent = `as of the last deploy, ${ago(snap.at)} · GitHub itself did not answer (${e.message})`; }
    else { $("#runs").innerHTML = empty(`No runs.json (a local build) and GitHub did not answer (${esc(e.message)}).`); tile("#tRun", "?", "warn", "no run data"); tile("#tDeploy", "?", "warn", ""); }
  }
}
const LIVE_RAW = "https://raw.githubusercontent.com/harimano/ipo-desk/live/live.json";
async function renderLive() {
  let asOf = null, from = "";
  try { asOf = (await getJson(LIVE_RAW)).asOf; }
  catch (e) { const snap = await snapshot(); if (snap && snap.live) { asOf = snap.live.asOf; from = " · from the last deploy's snapshot"; } }
  if (!asOf) { tile("#tLive", "?", "warn", "could not read live.json"); return; }
  const [lvl, why] = liveExpectation(asOf);
  tile("#tLive", hhmm(toIST(asOf)), lvl, `${ago(asOf)} · ${esc(why)}${from}`);
  if (lvl === "bad") addVerdict("bad", why, "runs");
}

/* ---------- security: what this browser is actually served ---------- */
async function renderSecurity() {
  const rows = [];
  const srow = (k, v, p, title) => `<tr>${td(esc(k), "k fit")}${td(v, "", title || "")}${td(p, "fit")}</tr>`;
  let me = null;
  try { me = await getJson("/admin/me.json", { cache: "no-store" }); } catch (e) { me = { error: e.message }; }
  const local = location.hostname === "localhost" || location.hostname.startsWith("127.");
  if (me && !me.error) {
    $("#who").textContent = me.email || "";
    rows.push(srow("gate", `Access on ${esc(me.team || "?")} · JWT re-verified by the Worker on every request`, pill("ok", "on"), me.team));
    rows.push(srow("/admin", me.adminEmailSet ? "served only to ADMIN_EMAIL; everyone else gets 403" : "ADMIN_EMAIL is not set — /admin answers 404 to everyone", pill(me.adminEmailSet ? "ok" : "bad", me.adminEmailSet ? "gated" : "unset")));
  } else {
    rows.push(srow("gate", `no gate answered (${esc(me.error)}) — ${local ? "a local preview" : "the Worker is not in front"}`, pill(local ? "nt" : "bad", local ? "local" : "open?")));
  }
  try {
    const r = await fetch("/", { method: "HEAD", cache: "no-store" });
    const want = { "x-robots-tag": "noindex", "referrer-policy": "no-referrer", "x-content-type-options": "nosniff" };
    const got = Object.entries(want).map(([h, v]) => [h, (r.headers.get(h) || "").includes(v)]);
    rows.push(srow("headers on /", got.map(([h, ok]) => `${ok ? "✓" : "✗"} ${esc(h)}`).join(" · "), pill(got.every(([, ok]) => ok) ? "ok" : local ? "nt" : "warn", `${got.filter(([, ok]) => ok).length}/${got.length}`), "set by the Worker; a local preview has none"));
  } catch (e) { rows.push(srow("headers on /", esc(e.message), pill("warn", "?"))); }
  rows.push(srow("repo", "public by choice · the document lives on the data branch · the Book never leaves the browser · secrets are GitHub secrets", pill("nt", "note"), "ops/site-worker/README.md says why"));
  $("#sec").innerHTML = table(["what|fit", "detail", "|fit"], rows);
  return me && !me.error ? me : null;
}

/* ---------- visitors: Cloudflare's Access log + the Worker's KV ledger (/admin/visitors.json) ---------- */
const dayKey = iso => { const d = toIST(iso); return d ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` : ""; };
async function renderVisitors(me) {
  const box = $("#visitors");
  let v;
  try { v = await getJson("/admin/visitors.json", { cache: "no-store" }); }
  catch (e) { box.innerHTML = empty(`No ledger answered (${esc(e.message)}) — a local preview, or the Worker is not in front.`); tile("#tVis", "?", "", "no ledger"); return; }
  const list = v.visitors || [], today = dayKey(new Date().toISOString()), week = Date.now() - 7 * 86400000;
  const mine = (me && me.email || "").toLowerCase();
  const todayN = list.filter(x => dayKey(x.last) === today).length, weekN = list.filter(x => Date.parse(x.last) > week).length;
  $("#visSum").textContent = list.length ? `${list.length} people · ${todayN} today · ${weekN} this week` : "";
  tile("#tVis", String(list.length), list.length ? "ok" : "", list.length ? `${todayN} today · ${weekN} this week` : "nobody yet");
  const srcs = [];
  if (v.accessLog && !v.accessLog.error) srcs.push(`sign-ins: Cloudflare's Access log, ${v.accessLog.records} records since the gate went up`); else srcs.push(`<b>no sign-in history</b>: ${esc(v.accessLog && v.accessLog.error || "?")}`);
  srcs.push(v.ledger ? "loads: the Worker's ledger since 29 Oct 2026, one per person per ten minutes" : "<b>no ledger</b>: the VISITS KV binding is missing");
  if (!list.length) { box.innerHTML = empty("Nobody recorded yet.") + note(srcs.join(" · ")); return; }
  box.innerHTML = table(["who", "first|fit", "last|fit", "sign-ins|n", "loads|n", "|fit"], list.map(x => {
    const flags = [x.country, x.failed ? `${x.failed} failed` : "", x.admin && x.email !== mine ? "tried /admin" : ""].filter(Boolean).join(" · ");
    return `<tr>${td(x.email === mine ? "<b>you</b>" : esc(x.email), "who", x.email)}${td(dayIST(x.first), "fit mu")}${td(`${fmtIST(x.last)} <span class="mu">${ago(x.last)}</span>`, "fit")}${td(String(x.signins), "n")}${td(String(x.loads), "n")}${td(flags ? pill(x.failed ? "warn" : "nt", flags) : "", "fit")}</tr>`;
  })) + note(srcs.join(" · "));
}

/* ---------- "Wrong number?" reports: what readers flagged (Worker /admin/reports.json ← D1 reports) ---------- */
async function renderReports() {
  const box = $("#reports");
  let v;
  try { v = await getJson("/admin/reports.json", { cache: "no-store" }); }
  catch (e) { box.innerHTML = empty(`No reports answered (${esc(e.message)}) — a local preview without one, or no D1 binding.`); return; }
  const list = v.reports || [], open = list.filter(r => r.status === "open");
  $("#repSum").textContent = list.length ? `${open.length} open · ${list.length} in all` : "nothing flagged yet";
  if (!list.length) { box.innerHTML = empty("No reader has flagged a number." + (v.error ? " " + esc(v.error) : "")); return; }
  box.innerHTML = table(["when|fit", "who", "IPO", "number", "shown|fit", "note"], list.slice(0, 60).map(r =>
    `<tr>${td(`${fmtIST(r.at)} <span class="mu">${ago(r.at)}</span>`, "fit")}${td(esc(r.email), "who", r.email)}${td(esc(r.issue), "", r.ig_id ? "IG " + r.ig_id : "")}${td(esc(r.field))}${td(esc(r.shown || ""), "fit mu", r.data_as_of ? "data as of " + r.data_as_of : "")}${td(esc(r.note || ""), "", r.note || "")}</tr>`))
    + note("A report never changes a number. Mark one done in the D1 console: UPDATE reports SET status='done' WHERE id=…");
}

/* ---------- the smoke test: the page in a hidden same-origin frame, every tab, every sheet ---------- */
const TAP = `<script>window.__smoke={errors:[]};addEventListener("error",e=>__smoke.errors.push(String(e.message||e)));addEventListener("unhandledrejection",e=>__smoke.errors.push("rejection: "+String(e.reason&&e.reason.message||e.reason)));const _ce=console.error.bind(console);console.error=(...a)=>{__smoke.errors.push(a.map(String).join(" "));_ce(...a)};<\/script>`;
async function smoke() {
  const btn = $("#smoke"), out = $("#smokeOut"), fr = $("#frame"); btn.disabled = true; out.innerHTML = empty("Loading the page…"); tile("#tPage", "…", "", "running");
  const t0 = performance.now(), rows = [];
  const srow = (k, v, p) => `<tr>${td(esc(k), "k fit")}${td(v, "w")}${td(p, "fit")}</tr>`;
  try {
    const html = await (await fetch("/", { cache: "no-store" })).text();
    fr.hidden = false;
    await new Promise((res, rej) => { fr.onload = res; fr.onerror = rej; fr.srcdoc = html.replace(/<head>/i, `<head><base href="${location.origin}/">` + TAP); setTimeout(res, 15000); });
    const w = fr.contentWindow, d = fr.contentDocument;
    const until = async (f, ms) => { const t = Date.now(); while (!f() && Date.now() - t < ms) await new Promise(r => setTimeout(r, 100)); return f(); };
    const live = await until(() => w.__ipo && d.querySelectorAll("#rsel option").length > 0, 12000);
    rows.push(srow("boot", live ? "page booted, data fetched" : "the page did not finish booting in 12 s", pill(live ? "ok" : "bad", live ? "ok" : "slow")));
    const tabs = [...d.querySelectorAll("#nav button[data-s]")];
    for (const b of tabs) { b.click(); await new Promise(r => setTimeout(r, 60)); }
    const sel = d.querySelector("#rsel"), opts = sel ? [...sel.options] : [];
    for (const o of opts) { sel.value = o.value; if (typeof sel.onchange === "function") sel.onchange(); else sel.dispatchEvent(new w.Event("change")); }
    let liveOk = true;
    try { if (w.__ipo && w.__ipo.live) w.__ipo.live({ asOf: new Date().toISOString(), rows: {} }); } catch (e) { liveOk = false; w.__smoke.errors.push("live(): " + e.message); }
    const errs = (w.__smoke && w.__smoke.errors) || [];
    rows.push(srow("tabs", `${tabs.length} opened`, pill(tabs.length === 7 ? "ok" : "warn", tabs.length)));
    rows.push(srow("sheets", `${opts.length} Research sheets rendered`, pill(opts.length ? "ok" : "warn", opts.length)));
    rows.push(srow("live()", liveOk ? "overlay called" : "threw", pill(liveOk ? "ok" : "bad", liveOk ? "ok" : "error")));
    const meta = await getJson("/data/meta.json?t=" + Date.now(), { cache: "no-store" });
    const files = Object.entries(meta.files || {});
    const heads = await Promise.all(files.map(([n, f]) => fetch(`/data/${n}.json?h=${f.hash}`, { method: "HEAD" }).then(r => [n, r.ok])));
    const badParts = heads.filter(([, ok]) => !ok);
    rows.push(srow("data parts", `${files.length} answer${badParts.length ? ", MISSING: " + badParts.map(x => x[0]).join(", ") : ""}`, pill(badParts.length ? "bad" : "ok", files.length - badParts.length + "/" + files.length)));
    rows.push(srow("chart.js", w.Chart ? "loaded " + esc(w.Chart.version) : "not loaded", pill(w.Chart ? "ok" : "bad", w.Chart ? "ok" : "missing")));
    rows.push(srow("console", errs.length ? errs.slice(0, 20).map(esc).join("<br>") : "no errors", pill(errs.length ? "bad" : "ok", errs.length)));
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    const lvl = errs.length || badParts.length || !live ? "bad" : "ok";
    out.innerHTML = table(["check|fit", "result", "|fit"], rows) + note(`${secs} s · ${new Date().toLocaleTimeString()}`);
    tile("#tPage", lvl === "ok" ? "clean" : `${errs.length || "!"} errors`, lvl, `${tabs.length} tabs · ${opts.length} sheets · ${secs} s`);
    if (lvl !== "ok") addVerdict("bad", `the page smoke test found ${errs.length} console error${errs.length === 1 ? "" : "s"}${badParts.length ? " and missing data parts" : ""}`, "smokeOut");
  } catch (e) {
    out.innerHTML = table(["check|fit", "result", "|fit"], [srow("result", esc(e.message), pill("bad", "failed"))]); tile("#tPage", "failed", "bad", esc(e.message));
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
  try { renderAudit(await getJson("audit.json?t=" + Date.now(), { cache: "no-store" })); }
  catch (e) { $("#vTitle").textContent = "No audit.json"; $("#vSub").textContent = "site/build.py writes admin/audit.json from scripts/audit.py — " + e.message; $("#verdict").className = "bad"; }
  await Promise.all([renderRuns(), renderLive(), renderSecurity().then(renderVisitors), renderReports()]);
}
$("#reload").addEventListener("click", () => location.reload());
$("#smoke").addEventListener("click", smoke);
try { const th = localStorage.getItem("ipo-theme"); if (th === "dark" || th === "light") document.documentElement.dataset.theme = th; } catch (e) { /* storage blocked */ }
main();
})();
