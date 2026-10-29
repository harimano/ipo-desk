/* ================= ACCOUNT — each reader's own saved dashboard, kept under their Access email =================
   Loaded before app.js (site/build.py). app.js's `store` reads and writes through `window.__ipoAccount`, so every
   user action (star, held, application, done / snooze, task, follow, theme) is one part that this file:
     1. keeps in memory and in a localStorage cache namespaced by email (`ipo-u:<email>:<part>`) — instant on reload,
        and nothing of one reader is ever read under another's address on a shared device;
     2. pushes to the Worker (`PUT /api/state/<part>`, ops/site-worker/worker.js) a moment after the change, with a
        quiet retry at 2, 4, 8 … 60 s; the header pill says Saved / Saving / Not saved.
   `GET /api/state` on load is the truth across devices: it replaces the cache except for parts changed in this tab
   that have not landed yet. The Worker knows the reader from the verified token; this file never sends an email.
   Per-device prefs (tab, research sheet, "since you last looked") stay in the namespaced cache and are not synced.
   Legacy: the un-namespaced `ipo-*` keys of the one-person era are offered for a one-time import, then renamed
   `ipo-legacy-*` and never read again. */
window.__ipoAccount = (function () {
"use strict";
const PARTS = ["holdings", "interest", "apps", "tasks-done", "tasks-custom", "investors", "theme", "budget"];
const LOCAL = ["tab", "research-sel", "seen", "intro"];
const API = "/api/state", NS = "ipo-u:";
const lsGet = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
const lsSet = (k, v) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* storage blocked: memory only */ } };
const parse = v => { try { return JSON.parse(v); } catch (e) { return v; } };

let email = lsGet(NS + "who") || null;        // the last address that signed in on this device: its cache can paint before the API answers
let parts = {}, dirty = new Set(), timer = null, backoff = 2000, loadWait = 5000;
let status = "loading", ready = false, lastErr = null;
const listeners = { status: [], change: [], legacy: [] };
const cacheKey = p => NS + (email || "?") + ":" + p;
function loadCache() { parts = {}; if (!email) return; PARTS.forEach(p => { const v = lsGet(cacheKey(p)); if (v != null) parts[p] = parse(v); }); }
loadCache();
function emit(ev, a, b) { listeners[ev].forEach(f => { try { f(a, b); } catch (e) { console.error(e); } }); }
function setStatus(s) { status = s; emit("status", status, email); }

// ---- the store app.js sees --------------------------------------------------------------------------------------
const partOf = key => String(key).replace(/^ipo-/, "");
function get(key, def) {
  const p = partOf(key);
  if (LOCAL.includes(p)) { const v = lsGet(cacheKey(p)); return v == null ? def : parse(v); }
  return p in parts ? parts[p] : def;
}
function set(key, v) {
  const p = partOf(key);
  if (LOCAL.includes(p)) { lsSet(cacheKey(p), JSON.stringify(v)); return; }
  if (!PARTS.includes(p)) return;
  parts[p] = v; lsSet(cacheKey(p), JSON.stringify(v));
  dirty.add(p); schedule(600);
}

// ---- push: one PUT per dirty part, coalesced; retry with backoff; never blocks the page --------------------------
function schedule(ms) { clearTimeout(timer); timer = setTimeout(flush, ms); }
async function flush(keepalive) {
  clearTimeout(timer); timer = null;
  if (!dirty.size) return;
  setStatus("saving");
  for (const p of [...dirty]) {
    try {
      const r = await fetch(API + "/" + p, { method: "PUT", headers: { "Content-Type": "application/json" }, credentials: "same-origin", keepalive: !!keepalive,
        body: JSON.stringify(parts[p] === undefined ? null : parts[p]) });
      if (!r.ok) throw Object.assign(new Error("HTTP " + r.status), { status: r.status });
      dirty.delete(p); lastErr = null;
    } catch (e) { lastErr = e; break; }
  }
  if (dirty.size) {
    setStatus(lastErr && lastErr.status === 503 ? "unavailable" : lastErr && lastErr.status === 401 ? "signed-out" : "retrying");
    timer = setTimeout(flush, backoff); backoff = Math.min(backoff * 2, 60000);
  } else { backoff = 2000; setStatus("saved"); }
}
addEventListener("online", () => { if (dirty.size) schedule(0); });
addEventListener("pagehide", () => { if (dirty.size) flush(true); });
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && dirty.size && !timer) schedule(0); });

// ---- load: the account's parts from the Worker; the cache (and this tab's unsaved changes) win only until it answers
async function load() {
  try {
    const r = await fetch(API, { cache: "no-store", credentials: "same-origin" });
    if (r.status === 401) { setStatus("signed-out"); return; }
    if (r.status === 503) { ready = true; setStatus("unavailable"); emit("change"); return; }
    if (!r.ok) throw new Error("HTTP " + r.status);
    const body = await r.json();
    const who = String(body.email || "").toLowerCase();
    if (!who) throw new Error("no email");
    if (who !== email) { email = who; lsSet(NS + "who", who); loadCache(); }
    const sp = body.parts || {};
    PARTS.forEach(p => { if (dirty.has(p)) return; if (p in sp) { parts[p] = sp[p]; lsSet(cacheKey(p), JSON.stringify(sp[p])); } else { delete parts[p]; lsSet(cacheKey(p), null); } });
    ready = true; loadWait = 5000;
    setStatus(dirty.size ? "retrying" : "saved");
    if (dirty.size) schedule(0);
    emit("change");
    if (!Object.keys(sp).length && !dirty.size) { const l = legacy(); if (Object.keys(l).length) emit("legacy", l); }
  } catch (e) {
    console.warn("account load failed", e);
    setStatus("offline"); emit("change");
    setTimeout(load, loadWait); loadWait = Math.min(loadWait * 2, 120000);
  }
}

// ---- legacy keys: the one-person era kept everything un-namespaced in this browser -----------------------------
const LEGACY = PARTS.map(p => "ipo-" + p);
function legacy() {
  const out = {};
  LEGACY.forEach(k => { const v = lsGet(k); if (v != null && !["[]", "{}", "null", '""', ""].includes(v.trim())) out[k.slice(4)] = parse(v); });
  if (out.investors && typeof out.investors === "object" && !(out.investors.add || []).length && !(out.investors.remove || []).length) delete out.investors;
  return out;
}
function retireLegacy() { [...LEGACY, "ipo-tab", "ipo-research-sel", "ipo-seen"].forEach(k => { const v = lsGet(k); if (v != null) { lsSet("ipo-legacy-" + k.slice(4), v); lsSet(k, null); } }); }
function importLegacy() { const l = legacy(); Object.keys(l).forEach(p => set("ipo-" + p, l[p])); retireLegacy(); emit("change"); return Object.keys(l).length; }
function legacySummary(l) {
  const n = v => Array.isArray(v) ? v.length : v && typeof v === "object" ? Object.keys(v).filter(k => v[k]).length : v ? 1 : 0;
  const bits = [];
  if (l.interest) bits.push(n(l.interest) + " starred");
  if (l.holdings) bits.push(n(l.holdings) + " held parent" + (n(l.holdings) === 1 ? "" : "s"));
  if (l.apps) bits.push(n(l.apps) + " application" + (n(l.apps) === 1 ? "" : "s"));
  if (l["tasks-done"]) bits.push(n(l["tasks-done"]) + " done or snoozed");
  if (l["tasks-custom"]) bits.push(n(l["tasks-custom"]) + " task" + (n(l["tasks-custom"]) === 1 ? "" : "s"));
  if (l.investors) bits.push("followed investors");
  if (l.theme) bits.push("the theme");
  return bits.join(", ");
}

// ---- export / import / reset -------------------------------------------------------------------------------------
const exportDoc = () => ({ app: "ipo-desk", version: 2, email, exportedAt: new Date().toISOString(), origin: location.origin, parts: Object.assign({}, parts) });
function download() {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(exportDoc(), null, 1)], { type: "application/json" }));
  a.download = `ipo-desk-${(email || "me").replace(/[^a-z0-9.@_-]/gi, "_")}-${new Date().toISOString().slice(0, 10)}.json`;
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
// Accepts this format (version 2: parts) and the old browser backup (version 1: raw ipo-* keys). Returns a message.
function importDoc(text) {
  let doc; try { doc = JSON.parse(text); } catch (e) { return "That is not a backup: not JSON"; }
  if (!doc || doc.app !== "ipo-desk") return "That is not an ipo-desk backup";
  let got = {};
  if (doc.parts && typeof doc.parts === "object") PARTS.forEach(p => { if (p in doc.parts) got[p] = doc.parts[p]; });
  else if (doc.keys && typeof doc.keys === "object") Object.keys(doc.keys).forEach(k => { const p = partOf(k); if (PARTS.includes(p) && typeof doc.keys[k] === "string") got[p] = parse(doc.keys[k]); });
  const names = Object.keys(got);
  if (!names.length) return "That backup holds nothing this page keeps";
  if (!confirm(`Restore ${names.length} item(s) from the backup of ${String(doc.exportedAt || "").slice(0, 10) || "an unknown date"}?\n\nThis replaces the stars, holdings, applications and tasks in your account.`)) return null;
  names.forEach(p => set("ipo-" + p, got[p]));
  emit("change");
  return `Restored ${names.length} item(s)`;
}
async function reset() {
  if (!confirm("Reset my data?\n\nThis removes your stars, held parents, applications, done / snoozed items, tasks and followed investors from your account on every device. The shared market data is not affected.")) return false;
  if (!confirm("Last check — there is no undo. Export my data first if in doubt.\n\nReset now?")) return false;
  clearTimeout(timer); timer = null; dirty.clear();
  PARTS.forEach(p => { delete parts[p]; lsSet(cacheKey(p), null); });
  emit("change");
  try {
    const r = await fetch(API, { method: "DELETE", credentials: "same-origin" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    setStatus("saved");
  } catch (e) { console.warn("reset did not reach the server", e); setStatus("retrying"); }
  return true;
}

// ---- the header pill and the account menu ------------------------------------------------------------------------
const TEXT = { loading: "Loading…", saved: "Saved", saving: "Saving…", retrying: "Not saved · retrying", unavailable: "Not saved · accounts not set up",
  offline: "Offline · local copy", "signed-out": "Signed out" };
function paint() {
  const pill = document.getElementById("acct"); if (!pill) return;
  pill.dataset.state = status; pill.querySelector(".st").textContent = TEXT[status] || status;
  pill.title = email ? `${email} — ${TEXT[status] || status}` : TEXT[status] || status;
  const who = document.getElementById("acctWho"); if (who) who.textContent = email || "not signed in";
  const bw = document.getElementById("bkWho"); if (bw) bw.textContent = email ? `Signed in as ${email}. Saved to your account; the same on every device you sign in on.` : "Not signed in — changes stay in this browser only.";
}
listeners.status.push(paint);
function wire() {
  const pill = document.getElementById("acct"), menu = document.getElementById("acctMenu");
  if (!pill || !menu) return;
  const close = () => { menu.hidden = true; pill.setAttribute("aria-expanded", "false"); };
  pill.onclick = () => { menu.hidden = !menu.hidden; pill.setAttribute("aria-expanded", String(!menu.hidden)); if (!menu.hidden) paint(); };
  document.addEventListener("click", e => { if (!menu.hidden && !e.target.closest("#acctMenu,#acct")) close(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  document.addEventListener("click", e => {                    // the menu, and the same buttons on the Book's account card
    const b = e.target.closest("button[data-acct]"); if (!b) return; close();
    const act = b.dataset.acct;
    if (act === "export") download();
    else if (act === "reset") reset();
    else if (act === "restore") { const f = document.getElementById("bkFile"); if (f) f.click(); }
    else if (act === "signout") { lsSet(NS + "who", null); location.href = "/logout"; }   // the next person on this device starts with no cached identity
  });
  const bf = document.getElementById("bkFile");
  if (bf) bf.onchange = e => { const f = e.target.files[0]; if (f) f.text().then(t => { const m = importDoc(t); if (m && window.__ipoToast) window.__ipoToast(m); }); e.target.value = ""; };
  paint();
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire); else wire();

// the one-time import banner, at the top of <main>
listeners.legacy.push(l => {
  const main = document.querySelector("main"); if (!main || document.getElementById("acctNote")) return;
  const el = document.createElement("div"); el.id = "acctNote"; el.className = "acct-note";
  el.innerHTML = `<span>This browser has <b>${legacySummary(l)}</b> saved from before accounts. Import them into <b>${email}</b>? They then follow you to every device.</span>
    <span class="acts"><button class="btn sm primary" data-leg="import">Import my existing data</button><button class="btn sm" data-leg="skip">Start empty</button></span>`;
  main.insertBefore(el, main.firstChild);
  el.addEventListener("click", e => { const b = e.target.closest("button[data-leg]"); if (!b) return;
    if (b.dataset.leg === "import") { const n = importLegacy(); if (window.__ipoToast) window.__ipoToast(`Imported ${n} item(s) into your account`); }
    else { if (!confirm("Start empty? The old data stays in this browser under ipo-legacy-* keys but is not read again.")) return; retireLegacy(); }
    el.remove(); });
});

load();
return { get, set, load, flush, on(ev, fn) { if (!listeners[ev]) return; listeners[ev].push(fn); if (ev === "status") fn(status, email); if (ev === "change" && ready) fn(); },
  get email() { return email; }, get status() { return status; }, get ready() { return ready; }, exportDoc, importDoc, reset, download, PARTS };
})();
