
/* ================= BOOT — data lives in data/*.json next to this page ================= */
(function () {
"use strict";
const DATA_DIR = "data/";
const REFETCH_THROTTLE = 60000;   // don't re-read on every tab switch
const FETCH_TIMEOUT = 15000;

let busy = false, lastFetch = 0, lastAsOf = null, onSnapshot = true;

/* ---------- chrome: the banner strip and the refresh pill ---------- */
function strip(cls, html) {
  const main = document.querySelector("main");
  let el = document.getElementById("dbnote");
  if (!html) { if (el) el.remove(); return; }
  if (!el) { el = document.createElement("div"); el.id = "dbnote"; main.insertBefore(el, main.firstChild); }
  el.className = cls; el.style.cssText = "margin-bottom:16px"; el.innerHTML = html;
}
const pill = document.createElement("button");
pill.id = "refreshPill"; pill.hidden = true;
pill.addEventListener("click", () => refresh("pill"));
document.body.appendChild(pill);
let pillTimer = null;
function setPill(text, kind) {
  clearTimeout(pillTimer);
  if (!text) { pill.hidden = true; return; }
  pill.textContent = text;
  pill.className = kind || "";
  pill.hidden = false;
  if (kind === "done") pillTimer = setTimeout(() => { pill.hidden = true; }, 2600);
}
const label = D => (D && D.meta && D.meta.label) || "an earlier date";

/* ---------- fetch with a hard timeout: the page must never wait forever ---------- */
async function getJson(url, opts) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), FETCH_TIMEOUT);
  try {
    const r = await fetch(url, Object.assign({ signal: ctl.signal }, opts));
    if (!r.ok) { const e = new Error("HTTP " + r.status); e.status = r.status; throw e; }
    return await r.json();
  } finally { clearTimeout(t); }
}

/* The document is published in parts (collector/layout.py): meta.json names each part and its hash.
   A part is fetched as <name>.json?h=<hash>, so the browser cache answers for everything that did not
   change; `parts` does the same across refreshes in this tab. A visit costs what moved, not 430 KB. */
const parts = {};                 // name -> { hash, body }
async function fetchSplit() {
  const head = await getJson(DATA_DIR + "meta.json?t=" + Date.now(), { cache: "no-store" });
  if (!head || !head.meta || !head.meta.asOf || !head.files) throw new Error("malformed meta.json");
  const names = Object.keys(head.files);
  await Promise.all(names.map(async name => {
    const hash = head.files[name].hash;
    if (parts[name] && parts[name].hash === hash) return;
    parts[name] = { hash, body: await getJson(DATA_DIR + name + ".json?h=" + hash) };
  }));
  const D = { meta: head.meta, integrity: head.integrity };
  names.forEach(name => Object.assign(D, parts[name].body));
  return D;
}
async function fetchData() {
  try { return await fetchSplit(); }
  catch (err) {
    if (err.status !== 404) throw err;          // only a site published before the split lacks meta.json
    const D = await getJson(DATA_DIR + "latest.json?t=" + Date.now(), { cache: "no-store" });
    if (!D || !D.meta || !D.meta.asOf) throw new Error("malformed document");
    return D;
  }
}

/* ---------- staleness: say so, per run, when the collector last landed ---------- */
function staleness(D) {
  const asOf = D.meta && D.meta.asOf ? new Date(D.meta.asOf) : null;
  if (!asOf || isNaN(asOf)) return null;
  const hours = (Date.now() - asOf.getTime()) / 36e5;
  if (hours < 30) return null;
  return "Last collector run was <b>" + label(D) + "</b> — " + Math.round(hours) + " hours ago. " +
         "Figures may be stale; the integrity panel on Market shows which sections were kept from a previous run.";
}

/* ---------- refresh: re-read the file and swap the data in place ---------- */
async function refresh(reason) {
  if (busy) return false;
  if (reason === "visible" && Date.now() - lastFetch < REFETCH_THROTTLE) return false;
  busy = true;
  if (reason !== "boot" && reason !== "poll" && reason !== "watch") setPill("Refreshing…", "busy");
  try {
    const DATA = await fetchData();
    lastFetch = Date.now();
    // the built-in snapshot holds only a few sections: the first full document always replaces it,
    // even when it carries the same asOf (it does after every deploy)
    const changed = onSnapshot || DATA.meta.asOf !== lastAsOf;
    lastAsOf = DATA.meta.asOf;
    if (!window.__ipo) { window.__ipo = __ipoInit(DATA); onSnapshot = false; strip("", ""); setPill(null); }
    else if (changed) {
      if (!window.__ipo.update(DATA)) { setPill("Update failed — still showing the previous data", "done"); return false; }
      onSnapshot = false;
      liveSeen = null; setTimeout(() => pollLive(true), 0);      // a new document replaced the rows: lay the live file over it again
      setPill(reason === "boot" ? null : "Updated " + label(DATA), "done");
    } else if (reason !== "poll" && reason !== "watch") setPill(reason === "boot" ? null : "Already current", "done");
    const s = staleness(DATA);
    strip(s ? "disc" : "", s || "");
    return true;
  } catch (err) {
    console.error("data fetch failed", err);
    const why = (err && err.message) || "unknown";
    if (reason === "boot") strip("disc", "Could not load the data files (" + why +
        ") — showing the snapshot built into this page from <b>" + label(FALLBACK) + "</b>.");
    else setPill("Refresh failed (" + why + ")", "done");
    return false;
  } finally { busy = false; }
}

/* ---------- after "Run": a collect + deploy takes two to three minutes; look every 30 s for 8 ---------- */
let watch = null;
function watchForRun() {
  if (watch) return;
  const from = lastAsOf, until = Date.now() + 8 * 60000;
  setPill("Waiting for the new run…", "busy");
  watch = setInterval(async () => {
    if (document.visibilityState === "visible") await refresh("watch");
    const landed = lastAsOf !== from;
    if (landed || Date.now() > until) {
      clearInterval(watch); watch = null;
      if (!landed) setPill("No new run yet — tap the data stamp to check again", "done");
    } else setPill("Waiting for the new run…", "busy");
  }, 30000);
}

/* ---------- live.json: the five-minute loop's file, on the `live` branch. GitHub's API serves it fresh (raw.github…
   caches for five minutes, so it is only the fallback). 60 unauthenticated calls an hour per visitor: one a minute
   is inside that, and only in market hours with the tab in view. ---------- */
const LIVE_API = "https://api.github.com/repos/harimano/ipo-desk/contents/live.json?ref=live";
const LIVE_RAW = "https://raw.githubusercontent.com/harimano/ipo-desk/live/live.json";
let liveSeen = null;
function marketHours() { const n = new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000), m = n.getHours() * 60 + n.getMinutes(); return n.getDay() % 6 !== 0 && m >= 8 * 60 + 50 && m <= 17 * 60 + 40; }
async function pollLive(force) {
  if (!window.__ipo || !window.__ipo.live || document.visibilityState !== "visible" || !(force || marketHours())) return;
  let L = null;
  try { L = await getJson(LIVE_API, { headers: { Accept: "application/vnd.github.raw+json" }, cache: "no-store" }); }
  catch (e) { try { L = await getJson(LIVE_RAW + "?t=" + Date.now(), { cache: "no-store" }); } catch (e2) { return; } }
  if (!L || !L.asOf || L.asOf === liveSeen) return;
  if ((Date.now() - new Date(L.asOf)) > 6 * 3600000) return;          // yesterday's file says nothing about today
  liveSeen = L.asOf; window.__ipo.live(L);
}

/* ---------- 1. render the built-in snapshot at once: never blank, never a spinner ---------- */
try {
  window.__ipo = __ipoInit(FALLBACK);
  lastAsOf = FALLBACK.meta && FALLBACK.meta.asOf;
  strip("disc", "Showing the snapshot built into this page from <b>" + label(FALLBACK) + "</b> — loading the latest…");
} catch (err) { console.error("fallback render failed", err); }

/* ---------- 2. upgrade to the latest file, then keep it fresh ---------- */
(async function () {
  await refresh("boot");
  pollLive(true); setInterval(pollLive, 60000);
  const tape = document.getElementById("tape");
  if (tape) tape.addEventListener("click", e => {
    if (e.target.closest(".asof")) refresh("tap");
    if (e.target.closest(".runnow")) watchForRun();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh("visible");
  });
  // a light poll while the tab is open: meta.json is ~4 KB and parts are fetched only when their hash moved, so every
  // two minutes costs next to nothing and a new run shows up on its own (quietly: no pill unless something changed)
  setInterval(() => { if (document.visibilityState === "visible") refresh("poll"); }, 120000);
})();
})();
