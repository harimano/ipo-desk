
/* ================= BOOT — data lives in data/latest.json next to this page ================= */
(function () {
"use strict";
const DATA_URL = "data/latest.json";
const REFETCH_THROTTLE = 60000;   // don't re-read on every tab switch
const FETCH_TIMEOUT = 15000;

let busy = false, lastFetch = 0, lastAsOf = null;

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
async function fetchData() {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), FETCH_TIMEOUT);
  try {
    const r = await fetch(DATA_URL + "?t=" + Date.now(), { cache: "no-store", signal: ctl.signal });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const D = await r.json();
    if (!D || !D.meta || !D.meta.asOf) throw new Error("malformed document");
    return D;
  } finally { clearTimeout(t); }
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
  if (reason !== "boot") setPill("Refreshing…", "busy");
  try {
    const DATA = await fetchData();
    lastFetch = Date.now();
    const changed = DATA.meta.asOf !== lastAsOf;
    lastAsOf = DATA.meta.asOf;
    if (!window.__ipo) { window.__ipo = __ipoInit(DATA); strip("", ""); setPill(null); }
    else if (changed) {
      if (!window.__ipo.update(DATA)) { setPill("Update failed — still showing the previous data", "done"); return false; }
      setPill(reason === "boot" ? null : "Updated " + label(DATA), "done");
    } else setPill(reason === "boot" ? null : "Already current", "done");
    const s = staleness(DATA);
    strip(s ? "disc" : "", s || "");
    return true;
  } catch (err) {
    console.error("data fetch failed", err);
    const why = (err && err.message) || "unknown";
    if (reason === "boot") strip("disc", "Could not load data/latest.json (" + why +
        ") — showing the snapshot built into this page from <b>" + label(FALLBACK) + "</b>.");
    else setPill("Refresh failed (" + why + ")", "done");
    return false;
  } finally { busy = false; }
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
  const tape = document.getElementById("tape");
  if (tape) tape.addEventListener("click", e => { if (e.target.closest(".asof")) refresh("tap"); });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh("visible");
  });
  // a light poll while the tab is open: the collector lands twice a day, so once an hour is plenty
  setInterval(() => { if (document.visibilityState === "visible") refresh("poll"); }, 3600000);
})();
})();
