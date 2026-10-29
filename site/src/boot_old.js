/* ================= BOOT — data lives in the artifact db, not in this file ================= */
(function () {
"use strict";
const DASH = ["meta", "board", "market", "integrity", "investors", "anchors", "quota"];
const COLLECTIONS = ["current", "sheets"];
const USE_TIMEOUT = 12000;      // claude.use() resolves null after 10s when nobody answers
const REFETCH_THROTTLE = 60000; // don't re-read on every tab switch

let db = null, busy = false, lastFetch = 0, unsubscribe = null;

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

/* ---------- documents -> the single DATA object the render code expects ---------- */
/* Snapshot bodies are frozen and platform-owned, and a document that has not changed is the
   SAME object across deliveries. Never let DATA alias one: clone on the way in, so the render
   code can treat DATA as ordinary mutable data. */
const clone = o => (typeof structuredClone === "function" ? structuredClone(o) : JSON.parse(JSON.stringify(o)));

function assemble(dashBodies, collections) {
  const DATA = {};
  for (const body of dashBodies) Object.assign(DATA, clone(body));
  for (const name of COLLECTIONS) {
    DATA[name] = {};
    const bodies = (collections[name] || []).slice()
      .sort((x, y) => (x.order == null ? 1e9 : x.order) - (y.order == null ? 1e9 : y.order));
    for (const body of bodies) {
      const b = clone(body), key = b.name;
      delete b.name; delete b.order;          // bookkeeping, not part of the sheet
      if (key) DATA[name][key] = b;
    }
  }
  return DATA;
}

async function readAll(conn) {
  const snaps = await Promise.all(DASH.map(id => conn.doc("dash/" + id).get()));
  const missing = snaps.filter(s => !s.exists).map((s, i) => s.id || DASH[i]);
  if (missing.length) throw new Error("missing document(s): " + missing.join(", "));
  const collections = {};
  for (const name of COLLECTIONS) {
    const snap = await conn.collection(name).get();
    collections[name] = snap.docs.map(d => d.data()).filter(Boolean);
  }
  return assemble(snaps.map(s => s.data()), collections);
}

const label = D => (D && D.meta && D.meta.label) || "an earlier date";

/* ---------- refresh: re-read the store and swap the data in place ---------- */
async function refresh(reason) {
  if (!db || busy) return false;
  if (reason === "visible" && Date.now() - lastFetch < REFETCH_THROTTLE) return false;
  busy = true;
  if (reason !== "boot") setPill("Refreshing…", "busy");
  try {
    const DATA = await readAll(db);
    lastFetch = Date.now();
    if (!window.__ipo) { window.__ipo = __ipoInit(DATA); strip("", ""); setPill(null); return true; }
    if (window.__ipo.update(DATA)) {
      strip("", "");
      setPill(reason === "boot" ? null : "Updated " + (DATA.meta && DATA.meta.label ? DATA.meta.label : ""), "done");
      return true;
    }
    setPill("Update failed — still showing the previous data", "done");
    return false;
  } catch (err) {
    console.error("db read failed", err);
    const why = (err && (err.code || err.message)) || "unknown";
    if (reason === "boot") strip("disc", "Could not load live data (" + why +
        ") — showing the cached snapshot from <b>" + label(FALLBACK) + "</b>.");
    else setPill("Refresh failed (" + why + ")", "done");
    return false;
  } finally { busy = false; }
}

/* ---------- 1. render the cached snapshot at once: never blank, never a spinner ---------- */
try {
  window.__ipo = __ipoInit(FALLBACK);
  strip("disc", "Showing cached data from <b>" + label(FALLBACK) + "</b> — checking for a live update…");
} catch (err) { console.error("fallback render failed", err); }

/* ---------- 2. upgrade to live data, then keep it fresh ---------- */
(async function () {
  try {
    if (window.claude && typeof window.claude.use === "function") {
      db = await Promise.race([window.claude.use("db"),
                               new Promise(r => setTimeout(() => r(null), USE_TIMEOUT))]);
    }
  } catch (err) { console.error("claude.use(db) threw", err); }

  if (!db) {
    strip("disc", "Live data is unavailable in this view — showing the cached snapshot from <b>"
                  + label(FALLBACK) + "</b>.");
    return;
  }
  await refresh("boot");

  // tapping the timestamp in the header refreshes (delegated: the tape is re-rendered constantly)
  const tape = document.getElementById("tape");
  if (tape) tape.addEventListener("click", e => { if (e.target.closest(".asof")) refresh("tap"); });

  // coming back to the tab picks up anything written while you were away
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh("visible");
  });

  // watch only the small meta document: when a run writes a new asOf, offer the update
  try {
    unsubscribe = db.doc("dash/meta").onSnapshot(
      snap => {
        if (!snap.exists || busy) return;
        const body = snap.data() || {}, next = body.meta && body.meta.asOf;
        if (next && window.__ipo && next !== window.__ipo.asOf) setPill("New data — tap to load", "new");
      },
      e => console.error("meta subscription ended", e && e.code)
    );
  } catch (err) { console.error("could not subscribe to meta", err); }
})();
})();
