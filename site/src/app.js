
/* ================= RENDER CODE (never edited by the refresh task) ================= */
window.__ipoInit = function (DATA) {
"use strict";
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => [...(el || document).querySelectorAll(s)];
const esc = s => s == null ? "" : String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const DAY = 86400000;
let asOf = new Date(DATA.meta.asOf);
let today = new Date(asOf.getFullYear(), asOf.getMonth(), asOf.getDate());
const iso = dt => dt.toISOString().slice(0, 10);
const d = s => s ? new Date(String(s).slice(0, 10) + "T00:00:00") : null;   // date part only: values may be ISO datetimes
const fmtT = s => { const m = /T(\d{2}:\d{2})/.exec(String(s || "")); return m ? ", " + m[1] : ""; };
const days = s => { const x = d(s); return x ? Math.round((x - today) / DAY) : null; };
const fmtD = s => { const x = d(s); return x ? x.toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "—"; };
const fmtDY = s => { const x = d(s); return x ? x.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—"; };
const inr = n => n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const inr0 = n => n == null ? "—" : "₹" + Math.round(Number(n)).toLocaleString("en-IN");
const cr = n => n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 }) + " Cr";
const pct = (n, sign) => n == null ? "—" : ((sign && n > 0) ? "+" : "") + Number(n).toFixed(1) + "%";
const xx = n => n == null ? "—" : Number(n).toFixed(2) + "x";
const cls = n => n == null ? "dim" : n > 0 ? "up" : n < 0 ? "down" : "";
// ---- freshness: how old is a number, when is the next run, what moved since this browser last looked ----------
const ago = s => { if (!s) return ""; const x = new Date(s); if (isNaN(x)) return ""; const m = Math.max(0, Math.round((Date.now() - x) / 60000));
  return m < 1 ? "just now" : m < 60 ? m + " min ago" : m < 1440 ? Math.round(m / 60) + " h ago" : x.toLocaleDateString("en-IN", { day: "numeric", month: "short" }); };
const hasTime = s => /T\d{2}:\d{2}/.test(String(s || ""));
const RUNS_IST = [[6, 43, 0]].concat([9, 10, 11, 12, 13, 14, 15, 16, 17].flatMap(h => [[h, 7, 1], [h, 37, 1]])).concat([[18, 13, 0]]).filter(r => !(r[0] === 9 && r[1] === 7));   // [h, m, weekdaysOnly]
function nextRun() {                                        // the collector's timetable, in IST whatever the viewer's zone
  const ist = new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
  for (let add = 0; add < 4; add++) { const dte = new Date(ist.getFullYear(), ist.getMonth(), ist.getDate() + add), wk = dte.getDay() % 6 !== 0;
    for (const [h, m, wd] of RUNS_IST) { if (wd && !wk) continue; const at = new Date(dte.getFullYear(), dte.getMonth(), dte.getDate(), h, m);
      if (at > ist) return (add === 0 ? "" : add === 1 ? "tomorrow " : at.toLocaleDateString("en-IN", { weekday: "short" }) + " ") + String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0"); } }
  return ""; }
const seenOf = D => { const o = {}; [...(D.mainboard || []), ...(D.sme || [])].forEach(b => { o[b.name] = { g: b.gmp == null ? null : b.gmp, s: b.sub && b.sub.total != null ? b.sub.total : null }; }); return o; };
let LIVE = null;                                            // {asOf, preopen[], timeline{}} from the five-minute loop
let CHG = {};                                               // name -> {g:[was, now], s:[was, now]} for this session
let NEWN = [];
function noteChanges(was, D) { const now = seenOf(D); if (Object.keys(was).length) Object.keys(now).forEach(n => { if (!was[n] && !NEWN.includes(n)) NEWN.push(n); }); Object.keys(now).forEach(n => { const a = was[n]; if (!a) return; const c = CHG[n] || {};
  if (a.g != null && now[n].g != null && a.g !== now[n].g) c.g = [a.g, now[n].g]; if (a.s != null && now[n].s != null && a.s !== now[n].s) c.s = [a.s, now[n].s];
  if (c.g || c.s) CHG[n] = c; }); }
const delta = (pair, fmt) => pair ? `<div class="dt chgd ${pair[1] > pair[0] ? "up" : "down"}">${pair[1] > pair[0] ? "▲" : "▼"} from ${fmt(pair[0])}</div>` : "";
const oldTag = (iso, days) => { const x = iso ? new Date(iso) : null; return x && !isNaN(x) && (Date.now() - x) / 864e5 > days ? ` <span class="oldtag" title="not refreshed by the collector since then">as of ${fmtD(iso)}</span>` : ""; };
const rel = n => n == null ? "" : n === 0 ? "today" : n === 1 ? "tomorrow" : n === -1 ? "yesterday" : n > 0 ? `in ${n} days` : `${-n} days ago`;
const sgn = n => n == null ? "—" : (n >= 0 ? "+" : "−") + inr0(Math.abs(n));

/* ---------- storage (keys fixed) ---------- */
const store = {
  get(k, def) { try { const v = localStorage.getItem(k); if (v == null) return def; try { return JSON.parse(v); } catch (e) { return v; } } catch (e) { return def; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
};
// Legacy shapes from the 8-tab build: holdings/interest/tasks-done were {name:true} objects, theme/tab raw strings, apps had {sellPrice}, tasks had {title, pr}.
const asList = v => Array.isArray(v) ? v : (v && typeof v === "object") ? Object.keys(v).filter(k => v[k]) : (typeof v === "string" && v) ? [v] : [];
const legacyApps = v => asList(v).filter(a => a && typeof a === "object").map(a => ({ name: a.name, cat: a.cat || "Retail", lots: +a.lots || 1, price: +a.price || 0, status: a.status || "Applied", sold: a.sold != null ? a.sold : (a.sellPrice != null ? a.sellPrice : null), added: a.added || null }));
const legacyTasks = v => asList(v).filter(t => t && typeof t === "object").map(t => ({ id: String(t.id || ("c:" + Date.now())), text: t.text || t.title || "", added: t.added || null }));
// ipo-holdings entries: "Parent short name" or {parent, qty, price, date}
const S = {
  holdings: asList(store.get("ipo-holdings", [])),
  interest: new Set(asList(store.get("ipo-interest", []))),
  apps: legacyApps(store.get("ipo-apps", [])),
  done: new Set(asList(store.get("ipo-tasks-done", [])).map(String)),   // "id" = done, "id@YYYY-MM-DD" = snoozed until
  tasksCustom: legacyTasks(store.get("ipo-tasks-custom", [])),
};
const holdName = h => typeof h === "string" ? h : h.parent;
const held = p => S.holdings.some(h => holdName(h) === p);
const heldNames = () => [...new Set(S.holdings.map(holdName))];
const toggleHold = p => { if (held(p)) S.holdings = S.holdings.filter(h => holdName(h) !== p); else S.holdings.push(p); save(); };
const isDone = id => S.done.has(id) || [...S.done].some(k => k.startsWith(id + "@") && k.slice(id.length + 1) > iso(today));
const save = () => { store.set("ipo-holdings", S.holdings); store.set("ipo-interest", [...S.interest]); store.set("ipo-apps", S.apps); store.set("ipo-tasks-done", [...S.done]); store.set("ipo-tasks-custom", S.tasksCustom); };

/* ---------- theme: system → light → dark ---------- */
const root = document.documentElement;
const applyTheme = t => { if (t) root.setAttribute("data-theme", t); else root.removeAttribute("data-theme"); $$("#themeSeg button").forEach(b => b.setAttribute("aria-checked", String((b.dataset.themeSet || null) === (t || null)))); };
{ const t0 = store.get("ipo-theme", null); applyTheme(t0 === "dark" || t0 === "light" ? t0 : null); }
const setTheme = t => { applyTheme(t); store.set("ipo-theme", t); drawCharts(); if (!$("#s-market").hidden) renderMarket(); if (!$("#s-book").hidden) drawPosCharts(); };
$("#themeSeg").addEventListener("click", e => { const b = e.target.closest("button[data-theme-set]"); if (b) setTheme(b.dataset.themeSet || null); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (!store.get("ipo-theme", null)) drawCharts(); });
const isDark = () => (root.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";

/* ---------- derived ---------- */
let Q = DATA.quota || [];
let live = Q.filter(q => ["approved", "drhp", "awaited"].includes(q.bucket)).sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
let board = DATA.mainboard || [], sme = DATA.sme || [];
let sheets = DATA.sheets || {}, current = DATA.current || {};
const allIssues = () => board.concat(sme);
const findIssue = n => allIssues().find(b => b.name === n);
let stale = (Date.now() - asOf) > 36 * 3600000;
function recompute() {
  asOf = new Date(DATA.meta.asOf);
  today = new Date(asOf.getFullYear(), asOf.getMonth(), asOf.getDate());
  Q = DATA.quota || [];
  live = Q.filter(q => ["approved", "drhp", "awaited"].includes(q.bucket)).sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
  board = DATA.mainboard || []; sme = DATA.sme || [];
  sheets = DATA.sheets || {}; current = DATA.current || {};
  stale = (Date.now() - asOf) > 36 * 3600000;
}
const covClass = q => q.quota === false ? "noq" : q.bucket === "approved" && q.lapse && days(q.lapse) >= 0 && days(q.lapse) <= 45 && !held(q.parent) ? "risk" : held(q.parent) ? "cov" : q.bucket === "awaited" ? "noq" : "unc";
const lotCost = b => b.lotSize && b.bandHigh ? b.lotSize * b.bandHigh : null;
const expGain = b => b.lotSize && b.gmp != null ? b.lotSize * b.gmp : null;
// a LOWER BOUND: lots bid / lots offered overstates the number of applications (many bid more than one lot); nobody publishes the count
const odds = v => v == null ? "—" : v <= 1 ? "full allotment likely" : "at least 1 in " + (v < 10 ? v.toFixed(1) : Math.round(v));
const quotaPill = q => q.quota === true ? `<span class="pill yes">quota ✓${q.quotaPct ? " " + q.quotaPct + "%" : ""}</span>` : q.quota === false ? `<span class="pill no">no quota</span>` : `<span class="pill unk">quota ?</span>`;
const toast = m => { const t = $("#toast"); t.textContent = m; t.hidden = false; clearTimeout(toast.h); toast.h = setTimeout(() => t.hidden = true, 1800); };

/* ---------- screens ---------- */
let screen = "today";
function show(id) {
  screen = id; $$("#nav button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.s === id)));
  $$(".screen").forEach(p => p.hidden = p.id !== "s-" + id);
  store.set("ipo-tab", id); cursor = -1; if (id === "board") drawCharts(); if (id === "market") renderMarket(); if (id === "book") drawPosCharts(); if (id === "score") renderScore(); window.scrollTo(0, 0);
}
$("#nav").addEventListener("click", e => { const b = e.target.closest("button[data-s]"); if (b) show(b.dataset.s); });

/* ================= QUEUE (the action plan) ================= */
function buildQueue() {
  const P = [];
  live.forEach(q => {
    const cov = held(q.parent);
    if (q.recordDate && days(q.recordDate) >= -1) P.push({ id: "rec:" + q.name, pri: 0, tag: ["now", days(q.recordDate) <= 0 ? "Record date today" : "Record date " + rel(days(q.recordDate))], lbl: "Quota cover", ttl: `${cov ? "Confirm" : "Buy and settle"} ${q.parent} before ${fmtD(q.recordDate)}`, desc: `${q.name} record date. Shares must be in demat on the record date — buy at least 2 trading days ahead.`, big: q.ticker, bigCls: "down", acts: [["hold", cov ? "Held ✓" : "Mark held"], ["sheet", "Sheet"]], q });
    const lapsing = q.bucket === "approved" && q.lapse && days(q.lapse) >= 0 && days(q.lapse) <= 45;
    if ((q.bucket === "approved" || q.bucket === "drhp") && q.quota !== false && !cov) {
      const now = q.bucket === "approved" && q.quota === true;
      P.push({ id: "buy:" + q.parent, pri: now ? 1 : 2, tag: [now ? "now" : "soon", now ? "Buy now" : lapsing ? "Lapses " + rel(days(q.lapse)) : "Soon"], lbl: "Quota cover", ttl: `Buy 1 share of ${q.parentFull || q.parent}`, desc: `Covers <b>${esc(q.name)}</b>${q.sizeCr ? " (" + cr(q.sizeCr) + ")" : ""} — ${esc(q.stage)}${q.stageDate ? " (" + fmtDY(q.stageDate) + ")" : ""}. ${q.quota === true ? "Shareholder quota confirmed." : "Quota not yet confirmed; one share is cheap insurance."}${lapsing ? ` Approval lapses ${fmtD(q.lapse)} — if an RHP lands first, the record date follows within days.` : ""}${q.name === "Reliance Jio" ? " Record date arrives with the RHP, so this can't wait for the announcement." : ""}`, big: q.ticker, acts: [["hold", "Mark held"], ["snooze", "Later"], ["sheet", "Sheet"]], q });
    }
    else if (lapsing)
      P.push({ id: "lapse:" + q.name, pri: 3, tag: ["soon", rel(days(q.lapse))], lbl: "Approval cliff", ttl: `${q.name} — approval lapses ${fmtD(q.lapse)}`, desc: `If an RHP is filed before then, expect a record date within days. Parent: ${esc(q.parent)}${q.ticker ? " (" + q.ticker + ")" : ""}${cov ? " — already held." : "."}`, big: fmtD(q.lapse), bigCls: "amb", acts: cov ? [["done", "Noted"]] : [["hold", "Mark held"], ["done", "Ignore"]], q });
  });
  Q.filter(q => q.isNew && q.bucket !== "dropped").forEach(q => P.push({ id: "new:" + q.name, pri: 4, tag: ["ok", "New filing"], lbl: "Pipeline", ttl: `${q.name} — ${q.stage}`, desc: `${esc(q.parent)}${q.stageDate ? " · " + fmtDY(q.stageDate) : ""}. ${esc(q.detail || "")}`, big: q.ticker, acts: [["star", "Star"], ["done", "Seen"]], q }));
  board.forEach(b => {
    const star = S.interest.has(b.name), g = expGain(b), c = lotCost(b);
    const money = c ? `1 lot = ${b.lotSize} sh = <b>${inr0(c)}</b>${g != null ? ` · GMP ${inr(b.gmp)} (${pct(b.gmpPct, true)}) → about <b class="${cls(g)}">${sgn(g)} per lot</b>` : ""}` : "lot size TBA";
    const sub = b.sub && b.sub.total != null ? ` Book ${xx(b.sub.total)}${b.sub.retail != null ? ", retail " + xx(b.sub.retail) + " (" + odds(b.sub.retail) + ")" : ""}.` : "";
    if (b.status === "Open") P.push({ id: "apply:" + b.name, pri: days(b.close) <= 1 ? 1 : 2, tag: [days(b.close) <= 1 ? "now" : "soon", days(b.close) === 0 ? "Closes today" : "Closes " + rel(days(b.close))], lbl: "Mainboard" + (star ? " · starred" : ""), ttl: `${b.name} — apply or pass`, desc: `Band ${inr(b.bandLow)}–${inr(b.bandHigh)} · ${money}.${sub}`, big: fmtD(b.close), bigCls: days(b.close) <= 1 ? "down" : "", acts: [["app", "Log application"], ["done", "Pass"], ["sheet", "Sheet"]], b });
    else if (b.status === "Upcoming" && (star || (b.gmpPct || 0) >= 15)) P.push({ id: "prep:" + b.name, pri: 5, tag: ["plan", "Opens " + rel(days(b.open))], lbl: "Mainboard" + (star ? " · starred" : " · strong GMP"), ttl: `${b.name} opens ${fmtD(b.open)}`, desc: `${b.bandHigh ? "Band " + inr(b.bandLow) + "–" + inr(b.bandHigh) + " · " : "Band TBA · "}${money}. Keep funds ready in UPI/ASBA.`, big: fmtD(b.open), acts: [["star", star ? "Starred ★" : "Star"], ["done", "Skip"], ["sheet", "Sheet"]], b });
    else if (b.status === "Closed" && (star || S.apps.some(a => a.name === b.name))) P.push({ id: "allot:" + b.name, pri: 4, tag: ["ok", "Lists " + rel(days(b.listing))], lbl: "Allotment", ttl: `Check ${b.name} allotment`, desc: `Lists ${fmtDY(b.listing)}${g != null ? ` · expected ${sgn(g)} per lot at GMP ${inr(b.gmp)}` : ""}.`, big: fmtD(b.listing), acts: [["done", "Checked"]], b });
  });
  S.apps.filter(a => a.status === "Allotted — holding").forEach(a => { const b = findIssue(a.name); if (b && b.status === "Listed") P.push({ id: "exit:" + a.name, pri: 3, tag: ["soon", "Listed"], lbl: "Position", ttl: `Decide on ${a.name}`, desc: `Listed ${fmtD(b.listing)} at ${inr(b.listingPrice)} vs your ${inr(a.price)}.`, big: pct(b.listingGainPct, true), bigCls: cls(b.listingGainPct), acts: [["done", "Decided"]] }); });
  return P.sort((a, b) => a.pri - b.pri);
}
function renderToday() {
  const all = buildQueue(), P = all.filter(p => !isDone(p.id));
  const urgent = P.filter(p => p.tag[0] === "now").length;
  $("#todayTitle").textContent = today.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
  $("#todaySum").textContent = P.length ? `${P.length} thing${P.length > 1 ? "s" : ""} to do${urgent ? ` · ${urgent} now` : ""}` : "Nothing needs a decision — the queue is clear.";
  const acts = p => p.acts.map(([k, l], j) => `<button class="btn sm${j === 0 ? " primary" : ""}" data-act="${k}">${esc(l)}${k === "hold" ? " <kbd>h</kbd>" : k === "done" ? " <kbd>d</kbd>" : k === "snooze" ? " <kbd>s</kbd>" : k === "star" ? " <kbd>*</kbd>" : ""}</button>`).join("");
  const nm = p => p.q ? p.q.name : p.b ? p.b.name : "";
  const urgentAll = P.filter(p => p.pri <= 2), top = urgentAll.slice(0, 3), later = [...urgentAll.slice(3), ...P.filter(p => p.pri > 2)];
  const pre = ((LIVE || {}).preopen || []).map(p => { const b = findIssue(p.name) || {}, imp = b.gmpPct;
    const holdLine = holdBlock(/SME/i.test(b.type || ""), p.pct, p.status === "Close" ? "at the opening price" : "at the indicative price");
    return `<div class="card q lead" data-row data-name="${esc(p.name)}"><div class="l"><div class="tags"><span class="pill now">Lists today</span><span class="lbl">NSE pre-open${p.status === "Close" ? " · final" : " · indicative"}</span></div>
      <div class="ttl">${esc(p.name)} — ${p.status === "Close" ? "opens at" : "indicating"} ${inr(p.iep)} (${pct(p.pct, true)})</div>
      <div class="desc">Issue price ${inr(p.base)}${imp != null ? ` · the grey market had implied ${pct(imp, true)}` : ""}${p.qty ? ` · ${Math.round(p.qty / 1e5) / 10} M shares matched` : ""} · ${p.asOf ? "as of " + p.asOf.slice(11, 16) + " IST" : ""}. Trading starts 10:00.</div>${holdLine}</div>
      <div class="r"><div class="big mono ${cls(p.pct)}">${pct(p.pct, true)}</div></div></div>`; }).join("");
  const moves = Object.entries(CHG).flatMap(([n, c]) => [c.s ? `${esc(n)} book ${c.s[0]}x → <b>${c.s[1]}x</b>` : null, c.g ? `${esc(n)} GMP ${inr(c.g[0])} → <b class="${c.g[1] > c.g[0] ? "up" : "down"}">${inr(c.g[1])}</b>` : null]).filter(Boolean);
  const since = moves.length || NEWN.length ? `<div class="card" style="padding:10px 16px;margin-bottom:12px"><span class="lbl">Since you last looked</span> &nbsp;<span style="font-size:13px">${[...moves.slice(0, 6), NEWN.length ? "new on the board: " + NEWN.slice(0, 6).map(esc).join(", ") + (NEWN.length > 6 ? ` +${NEWN.length - 6}` : "") : null].filter(Boolean).join(" · ")}${moves.length > 6 ? ` · +${moves.length - 6} more` : ""}</span></div>` : "";
  $("#queue").innerHTML = since + pre + (top.length ? top.map((p, i) => `<div class="card q${i === 0 ? " lead" : ""}" data-row data-id="${esc(p.id)}" data-name="${esc(nm(p))}">
    <div class="l"><div class="tags"><span class="pill ${p.tag[0]}">${esc(p.tag[1])}</span><span class="lbl">${esc(p.lbl)}</span></div><div class="ttl">${esc(p.ttl)}</div><div class="desc">${p.desc}</div></div>
    <div class="r"><div class="big mono ${p.bigCls || ""}">${esc(p.big || "")}</div><div class="acts">${acts(p)}</div></div></div>`).join("") : `<div class="card empty">Nothing urgent. ${later.length ? "The rest is below." : "Snoozed and done items are in Book."}</div>`)
    + (later.length ? `<div class="card"><div class="ch">Everything else <span class="sub">${later.length} item${later.length > 1 ? "s" : ""}</span></div>${later.map(p => `<div class="q" data-row data-id="${esc(p.id)}" data-name="${esc(nm(p))}" style="padding:10px 18px;border-top:1px solid var(--line)"><div class="l"><div class="tags"><span class="pill ${p.tag[0]}">${esc(p.tag[1])}</span><span class="lbl">${esc(p.lbl)}</span><span style="font-weight:700">${esc(p.ttl)}</span></div><div class="desc" style="font-size:12.5px">${p.desc}</div></div><div class="r"><div class="acts">${acts(p)}</div></div></div>`).join("")}</div>` : "");
  $("#c-today").textContent = urgent || "";

  // KPIs
  const actionable = live.filter(q => q.bucket !== "awaited" && q.quota !== false), covered = actionable.filter(q => held(q.parent)).length;
  const open = board.filter(b => b.status === "Open"), best = open.slice().sort((a, b) => (b.gmpPct || 0) - (a.gmpPct || 0))[0];
  const listing = board.filter(b => b.listing && days(b.listing) >= 0 && days(b.listing) <= 7);
  const F = DATA.flows && DATA.flows.latest;
  $("#kpis").innerHTML = [
    ["Coverage", `${covered}<span class="dim">/${actionable.length}</span>`, "actionable names with the parent held", covered === actionable.length ? "up" : ""],
    ["Open IPOs", open.length, best ? `best GMP: ${best.name} ${pct(best.gmpPct, true)}` : "none open", ""],
    ["Mainboard listings this week", listing.length, listing[0] ? `${listing[0].name} on ${fmtD(listing[0].listing)}` : "—", ""],
    ["Flows " + (F ? fmtD(F.date) : ""), F ? sgn((F.fiiNetCr || 0) + (F.diiNetCr || 0)) + " Cr" : "—", F ? `FII ${sgn(F.fiiNetCr)} · DII ${sgn(F.diiNetCr)}` : "no data", F ? cls((F.fiiNetCr || 0) + (F.diiNetCr || 0)) : ""],
  ].map(([l, v, dd, c]) => `<div class="card kpi"><div class="lbl">${l}</div><div class="v mono ${c}">${v}</div><div class="d">${esc(dd)}</div></div>`).join("");

  // mini lanes
  const lane = (title, rows, max) => `<div class="lane"><div class="lbl">${title} · ${rows.length}</div>${rows.slice(0, max).map(q => `<button class="chip ${covClass(q)}" data-jump="${esc(q.name)}">${esc(q.name)}${S.interest.has(q.name) ? '<span class="mk">★</span>' : ""}<small>${esc(q.ticker || q.parent)}${q.sizeCr ? " · " + cr(q.sizeCr) : ""}${q.lapse && q.bucket === "approved" && days(q.lapse) <= 45 ? " · lapses " + fmtD(q.lapse) : q.quota === true ? " · quota ✓" : q.quota == null ? " · quota ?" : ""}</small></button>`).join("")}${rows.length > max ? `<button class="chip noq" data-jump="" style="color:var(--ink-3)">+ ${rows.length - max} more<small>${esc(rows.slice(max).map(q => q.name).join(", ").slice(0, 60))}…</small></button>` : ""}</div>`;
  $("#miniLanes").innerHTML = lane("Approved", live.filter(q => q.bucket === "approved"), 5) + lane("DRHP filed", live.filter(q => q.bucket === "drhp"), 5) + lane("Awaited", live.filter(q => q.bucket === "awaited"), 2);

  // calendar
  const ev = [];
  allIssues().forEach(b => { if (b.status === "Open" && b.close) ev.push({ d: b.close, w: b.name, s: "closes", c: days(b.close) <= 1 ? "now" : "" }); if (b.status === "Upcoming" && b.open) ev.push({ d: b.open, w: b.name, s: "opens", c: "" }); if (b.status === "Closed" && b.listing) ev.push({ d: b.listing, w: b.name, s: "lists", c: "" }); });
  live.forEach(q => { if (q.recordDate) ev.push({ d: q.recordDate, w: q.name, s: "record date", c: "now" }); if (q.bucket === "approved" && q.lapse && days(q.lapse) <= 30) ev.push({ d: q.lapse, w: q.name, s: "approval lapses", c: "warn" }); });
  const byDay = {}; ev.filter(e => days(e.d) >= 0 && days(e.d) <= 30).forEach(e => (byDay[e.d] = byDay[e.d] || []).push(e));
  const daysArr = Object.keys(byDay).sort().slice(0, 7);
  $("#cal").innerHTML = daysArr.map(k => { const es = byDay[k]; const c = es.some(e => e.c === "now") ? "now" : es.some(e => e.c === "warn") ? "warn" : ""; const groups = {}; es.forEach(e => (groups[e.s] = groups[e.s] || []).push(e.w)); return `<div class="day ${c}"><div class="d mono ${c === "now" ? "down" : c === "warn" ? "amb" : ""}">${fmtD(k)}</div>${Object.entries(groups).map(([s, ws]) => `<div class="w">${esc(ws.length > 2 ? ws.slice(0, 2).join(", ") + " +" + (ws.length - 2) : ws.join(", "))}<small>${s}</small></div>`).join("")}</div>`; }).join("") +
    (live.some(q => q.name === "Reliance Jio" && !q.recordDate) ? `<div class="day est"><div class="d mono dim">?</div><div class="w dim">Jio record date<small>arrives with the RHP</small></div></div>` : "");
}
function queueAct(id, act, name) {
  const q = Q.find(z => z.name === name), b = findIssue(name);
  if (act === "done") { S.done.add(id); save(); toast("Done"); }
  else if (act === "snooze") { S.done.add(id + "@" + iso(new Date(today.getTime() + 3 * DAY))); save(); toast("Snoozed 3 days"); }
  else if (act === "hold" && q) { toggleHold(q.parent); toast(held(q.parent) ? `Holding ${q.parent}` : `Removed ${q.parent}`); }
  else if (act === "star") { const n = name; S.interest.has(n) ? S.interest.delete(n) : S.interest.add(n); save(); toast(S.interest.has(n) ? "Starred" : "Unstarred"); }
  else if (act === "app" && b) { show("book"); $("#apName").value = b.name; $("#apPrice").value = b.bandHigh || ""; bounds(); $("#apLots").focus(); return; }
  else if (act === "sheet") { openSheet(name); return; }
  const el = $(`[data-id="${CSS.escape(id)}"]`); if (el && (act === "done" || act === "snooze")) { el.classList.add("gone"); setTimeout(renderAll, 200); } else renderAll();
}
$("#queue").addEventListener("click", e => { const b = e.target.closest("button[data-act]"); if (!b) return; const card = b.closest("[data-id]"); queueAct(card.dataset.id, b.dataset.act, card.dataset.name); });
$("#miniLanes").addEventListener("click", e => { const c = e.target.closest("[data-jump]"); if (!c) return; if (c.dataset.jump) { show("pipe"); openPipe(c.dataset.jump); } else show("pipe"); });

/* ================= PIPELINE ================= */
let pipeSel = null;
function renderPipe() {
  const L = [["awaited", "DRHP awaited", live.filter(q => q.bucket === "awaited")], ["drhp", "DRHP filed", live.filter(q => q.bucket === "drhp")], ["approved", "SEBI approved", live.filter(q => q.bucket === "approved")],
    ["rhp", "RHP · record date", live.filter(q => q.recordDate)], ["done", "Listed 2026", Q.filter(q => q.bucket === "done").sort((a, b) => (b.listingDate || "").localeCompare(a.listingDate || ""))]];
  $("#lanes").innerHTML = L.map(([k, t, rows]) => `<div class="pipe-lane"><div class="lh"><h2 style="font-size:13px">${t}</h2><span class="n mono">${rows.length}</span></div><div class="body">${rows.length ? rows.map(q => `<button class="chip ${q.bucket === "done" ? "cov" : covClass(q)}${pipeSel === q.name ? " cur" : ""}" data-row data-name="${esc(q.name)}">${esc(q.name)}${S.interest.has(q.name) ? '<span class="mk">★</span>' : ""}<small>${esc(q.ticker || q.parent)}${q.bucket === "done" ? ` · ${pct(q.listingGainPct, true)} · quota ${q.quotaPct != null ? q.quotaPct + "%" : "?"}` : q.sizeCr ? " · " + cr(q.sizeCr) : ""}${q.recordDate ? " · record " + fmtD(q.recordDate) : q.bucket === "approved" && q.lapse && days(q.lapse) <= 45 ? " · lapses " + fmtD(q.lapse) : q.stageDate && q.bucket !== "done" ? " · " + fmtD(q.stageDate) : ""}${held(q.parent) && q.bucket !== "done" ? " · held ✓" : ""}</small></button>`).join("") : `<div class="dim" style="font-size:12px;padding:6px 2px">${k === "rhp" ? "No record dates announced. Jio's arrives with its RHP." : "—"}</div>`}</div></div>`).join("");
  renderQuotaPlanner();
  $("#c-pipe").textContent = live.filter(q => (q.bucket === "approved" || q.bucket === "drhp") && q.quota !== false && !held(q.parent)).length || "";
  const q = Q.find(z => z.name === pipeSel);
  $("#pipeDetailWrap").hidden = !q;
  if (q) $("#pipeDetail").innerHTML = `<div><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><h2 style="font-size:18px">${esc(q.name)}</h2>${quotaPill(q)}${q.isNew ? '<span class="pill ok">new</span>' : ""}<span class="pill plan">${esc(q.stage)}</span><span class="dim" style="font-size:12px">confidence ${esc(q.confidence || "—")}</span></div>
      <p class="prose" style="margin-top:8px">${esc(q.detail || "No detail captured yet.")}</p>
      <dl class="kv"><dt>Parent</dt><dd>${esc(q.parentFull || q.parent)} <span class="mono dim">${esc(q.ticker || "")}</span></dd><dt>Stage date</dt><dd>${fmtDY(q.stageDate)}</dd><dt>Issue size</dt><dd>${q.sizeCr ? cr(q.sizeCr) : "TBA"}</dd><dt>Record date</dt><dd>${q.recordDate ? `<b class="down">${fmtDY(q.recordDate)}</b>` : "not announced"}</dd>${q.lapse ? `<dt>Approval lapses</dt><dd class="${days(q.lapse) <= 45 ? "amb" : ""}">${fmtDY(q.lapse)}</dd>` : ""}${q.sources && q.sources.length ? `<dt>Sources</dt><dd class="docs">${q.sources.map(u => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\//, "").slice(0, 50))}</a>`).join("")}</dd>` : ""}</dl></div>
    <div style="display:flex;flex-direction:column;gap:8px;align-items:flex-end"><div style="display:flex;gap:6px"><button class="tg star${S.interest.has(q.name) ? " on" : ""}" data-star="${esc(q.name)}" title="Interested">★</button><button class="tg hold${held(q.parent) ? " on" : ""}" data-hold="${esc(q.parent)}" title="Holding the parent">✓</button></div>${sheets[q.name] ? `<button class="btn sm" data-sheet="${esc(q.name)}">Open sheet <kbd>⏎</kbd></button>` : ""}<button class="btn sm" data-close-detail>Close <kbd>esc</kbd></button></div>`;
  // done + dropped
  $("#done").innerHTML = `<thead><tr><th>Subsidiary</th><th>Parent</th><th>Record date</th><th>Listed</th><th class="r">Quota</th><th class="r">Listing gain</th></tr></thead><tbody>` + Q.filter(q => q.bucket === "done").sort((a, b) => (b.listingDate || "").localeCompare(a.listingDate || "")).map(q => `<tr><td class="nm">${esc(q.name)}</td><td>${esc(q.parent)}</td><td>${fmtDY(q.recordDate)}</td><td>${fmtDY(q.listingDate)}</td><td class="r num">${q.quotaPct != null ? q.quotaPct + "%" : "—"}</td><td class="r num ${cls(q.listingGainPct)}">${pct(q.listingGainPct, true)}</td></tr>`).join("") + "</tbody>";
  $("#dropped").innerHTML = `<thead><tr><th>Subsidiary</th><th>Parent</th><th>Why</th><th>Quota</th></tr></thead><tbody>` + Q.filter(q => q.bucket === "dropped").map(q => `<tr><td class="nm">${esc(q.name)}</td><td>${esc(q.parent)}</td><td class="dim">${esc(q.stage)}${q.stageDate ? " · " + fmtDY(q.stageDate) : ""}${q.detail ? " — " + esc(q.detail) : ""}</td><td>${quotaPill(q)}</td></tr>`).join("") + "</tbody>";
}
function openPipe(name) { pipeSel = name; renderPipe(); const el = $("#pipeDetailWrap"); if (el && !el.hidden) el.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
$("#lanes").addEventListener("click", e => { const c = e.target.closest("[data-name]"); if (c) openPipe(pipeSel === c.dataset.name ? null : c.dataset.name); });
$("#pipeDetail").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.star != null) { S.interest.has(b.dataset.star) ? S.interest.delete(b.dataset.star) : S.interest.add(b.dataset.star); save(); renderAll(); }
  else if (b.dataset.hold != null) { toggleHold(b.dataset.hold); renderAll(); }
  else if (b.dataset.sheet != null) openSheet(b.dataset.sheet);
  else if (b.hasAttribute("data-close-detail")) { pipeSel = null; renderPipe(); }
});

/* ================= BOARD ================= */
let bfilter = "now", bsort = null;
const subBar = (l, v) => { const w = v == null ? 0 : Math.min(100, Math.log10(1 + v) / Math.log10(301) * 100); return `<div class="sb"><span class="l">${l}</span><span class="bar"><i class="${v == null ? "" : v < 1 ? "lo" : v >= 10 ? "hi" : ""}" style="width:${w}%"></i></span><span class="n num">${xx(v)}</span></div>`; };
// ---- evidence: computed once per run by collector/modules/evidence.py; the page quotes it and does no statistics. The one sum
// made here is an open issue's expected value, because its inputs (retail book, GMP) move every five minutes with the live overlay. ----
const EVD = () => DATA.evidence || {}, SEG = isSme => (EVD().segments || {})[isSme ? "sme" : "main"] || null;
const EDG = k => ((EVD().edges || {})[k] || []).map((x, i) => x == null ? (i ? Infinity : -Infinity) : x);
const edgeLbl = (e, i, u) => e[i] === -Infinity ? "zero or below" : (e[i] === 0 && u === "x") ? `under ${e[i + 1]}${u}` : e[i + 1] === Infinity ? `over ${e[i]}${u}` : `${e[i]}–${e[i + 1]}${u}`;
const bandOf = (v, e) => { for (let i = 0; i < e.length - 1; i++) if (v >= e[i] && v < e[i + 1]) return i; return -1; };
const median = a => { const s = a.slice().sort((x, y) => x - y), m = s.length >> 1; return s.length ? (s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2) : null; };
const winLbl = W => W ? `${W.rule}, ${fmtD(W.from)} ${String(W.from).slice(2, 4)} – ${fmtD(W.to)} ${String(W.to).slice(2, 4)}` : "";
// the gain GMP implies, corrected by the segment's fit, with the 10th–90th percentile of how far past listings landed from it
const gmpRange = (seg, gmpPct) => { const f = seg && seg.fit && (seg.fit.eve || seg.fit.r377); if (!f || !gmpPct) return null;          /* the fit leaves out GMP = 0 (mostly "no quote"), so it says nothing about one */ const c = f.a + f.b * gmpPct; return { c, lo: c + f.q10, hi: c + f.q90, n: f.n, prov: !!seg.fit.provisional }; };
// expected value of one application, as % of the money ASBA blocks: (at least 1/retail book) x gain - what the money earns elsewhere meanwhile
// `cat` picks whose book sets the chance of allotment: "retail" (default), "shareholder" or "employee". A reserved category is
// usually far less crowded than retail, and a PAN may apply in it AND in retail — the two EVs side by side are the point.
function evOf(b, seg, cat) {
  const r = (b.sub || {})[cat || "retail"], G = gmpRange(seg, b.gmpPct); if (r == null || !G || b.status === "Listed" || b.status === "Upcoming") return null;
  const p = Math.min(1, 1 / Math.max(r, 1e-9)), from = b.status === "Open" ? today : d(b.close), to = d(b.refund) || (d(b.allotment) ? new Date(d(b.allotment).getTime() + DAY) : null);
  const blocked = Math.max(1, from && to ? Math.round((to - from) / DAY) : 5), cost = 100 * (EVD().rfAnnual || 0) * blocked / 365;
  return { p, blocked, cost, ev: p * G.c - cost, lo: p * G.lo - cost, hi: p * G.hi - cost, prov: G.prov };
}
const spark = pts => { if (!pts || pts.length < 3) return ""; const v = pts.map(p => p[1]), lo = Math.min(...v), hi = Math.max(...v), W = 150, H = 22;
  const xy = v.map((y, i) => `${(i / (v.length - 1) * W).toFixed(1)},${(H - 2 - (hi > lo ? (y - lo) / (hi - lo) : .5) * (H - 4)).toFixed(1)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="total subscription through today"><polyline points="${xy}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg><div class="dt">today ${pts[0][0]} → ${pts[pts.length - 1][0]} · ${v[0]}x → ${v[v.length - 1]}x</div>`; };
// coloured by the INTERVAL, not the point: green only when even the low end of the 95% range is a clear majority
const evCls = s => !s || !s.n ? "na" : s.lo >= 60 ? "hi" : s.hi <= 50 ? "lo" : "mid";
const evTxt = s => !s || !s.n ? "no past cases in this band" : `${Math.round(s.pos)}% of ${s.n} listed positive (95% range ${Math.round(s.lo)}–${Math.round(s.hi)}%) · median ${pct(s.med, true)}${s.n < (EVD().minN || 30) ? " · thin" : ""}`;
const evShort = s => !s || !s.n ? "no past cases" : `${Math.round(s.pos)}% of ${s.n} up <span title="95% range: with ${s.n} cases the true rate could be anywhere in here">(${Math.round(s.lo)}–${Math.round(s.hi)}%)</span> · median ${pct(s.med, true)}${s.n < (EVD().minN || 30) ? " · thin" : ""}`;
const evLong = s => !s || !s.n ? "no past cases" : `${evTxt(s)} · 1 in 10 did worse than ${pct(s.p10, true)}, 1 in 10 better than ${pct(s.p90, true)}`;
const istNow = () => new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);

function boardRow(b) {
  const isSme = /SME/i.test(b.type), g = expGain(b), c = lotCost(b), seg = SEG(isSme), B = seg ? seg.bands : null, segLbl = isSme ? "SME" : "mainboard", W = seg ? winLbl(seg.window) : "";
  const lastDay = b.status === "Open" && days(b.close) === 0, late = istNow().getHours() >= 14;
  const when = b.status === "Upcoming" ? `Opens ${fmtD(b.open)}${b.close ? "–" + fmtD(b.close) : ""}`
    : b.status === "Open" ? (lastDay ? `<b class="down">Closes today, 5 pm</b><div class="dt">${late ? "the book is close to final" : "QIBs bid late — the picture firms after 2 pm"}</div>` : `Closes ${fmtD(b.close)} · ${rel(days(b.close))}<div class="dt">QIBs bid on the last afternoon — early QIB figures say little</div>`)
    : b.status === "Closed" ? `Allotment ${fmtD(b.allotment)}<div class="dt">lists ${fmtD(b.listing)} · ${rel(days(b.listing))}</div>` : `Listed ${fmtD(b.listing)}`;
  const band = b.bandLow != null && b.bandHigh != null && b.bandLow !== b.bandHigh ? `${inr(b.bandLow)}–${inr(b.bandHigh)}` : b.bandHigh != null ? inr(b.bandHigh) : "TBA";
  const S0 = b.sub || {}, early = b.status === "Open" && !(lastDay && late);
  const pick = (key, v, where) => evBand(seg, key, v, where);
  const T = pick("total", S0.total, "window"), TA = pick("total", S0.total, "all"), QB = !isSme ? pick("qib", S0.qib, "rows") : null, GB = pick("gmp", b.gmpPct, "window"), GA = pick("gmp", b.gmpPct, "all");
  const catYears = B ? (B.qib.years || []).join(", ") : "";
  const bookCell = S0.total == null ? `<span class="dim">${b.status === "Upcoming" ? "not open" : "—"}</span>`
    : early ? `<span class="num dim">${S0.total}x</span><div class="dt">total so far — too early to read</div>`
    : `<span class="ev ${evCls(T && T.s)} num" title="Final total book ${T ? T.lbl : ""} · ${segLbl}, ${W}: ${evLong(T && T.s)}">${S0.total}x</span><div class="dt">${evShort(T && T.s)}</div>${QB ? `<div class="dt">QIB ${S0.qib}x, ${catYears} only: ${evShort(QB.s)}</div>` : ""}`;
  const R = b.status !== "Listed" ? gmpRange(seg, b.gmpPct) : null;
  const gmpCell = b.status === "Listed" ? `<span class="${cls(b.listingGainPct)}">${inr(b.listingPrice)} · ${pct(b.listingGainPct, true)}</span><div class="dt">listing</div>`
    : b.gmp != null ? `<span class="ev ${evCls(GB && GB.s)} num" title="GMP ${GB ? GB.lbl : ""} · ${segLbl}, ${W}: ${evLong(GB && GB.s)}">${pct(b.gmpPct, true)}</span> <span class="dim">${inr(b.gmp)}</span> ${b.gmpTrend === "up" ? "▲" : b.gmpTrend === "down" ? "▼" : ""}${delta((CHG[b.name] || {}).g, inr)}<div class="dt">${evShort(GB && GB.s)}${hasTime(b.gmpAsOf) ? " · " + ago(b.gmpAsOf) : ""}</div>${R ? `<div class="dt" title="From ${R.n} ${segLbl} listings: where 8 in 10 landed around what their GMP implied.${R.prov ? " Provisional: fitted on the source's listing-morning GMP; the desk's own evening-before record is still too short to confirm it." : ""}">8 in 10 like this listed ${pct(R.lo, true)} to ${pct(R.hi, true)}${R.prov ? ' <span class="oldtag">provisional</span>' : ""}</div>` : ""}`
    : `<span class="dim">no quote</span>`;
  const gainCell = b.status === "Listed" || g == null ? `<span class="dim">—</span>` : `<span class="num ${cls(g)}">${sgn(g)}</span><div class="dt">per lot, if allotted${c ? " · " + inr0(c) + " blocked" : ""}</div>`;
  const E1 = evOf(b, seg);
  const evCell = b.status === "Listed" ? `<span class="dim">—</span>` : !E1 ? `<span class="dim">—</span><div class="dt">${S0.retail == null ? "once the retail book opens" : "needs a GMP quote"}</div>`
    : `<span class="num ${early ? "dim" : cls(E1.ev)}" title="Chance of allotment (at least ${Math.round(E1.p * 1000) / 10}%) × the gain GMP implies, less ${E1.cost.toFixed(2)}% for money blocked ${E1.blocked} days at ${Math.round((EVD().rfAnnual || 0) * 100)}% a year. Range uses where 8 in 10 past listings landed. The chance is a LOWER BOUND: retail applicants bid more than one lot on average, so there are fewer applications than lots bid — nobody publishes the count.">${pct(E1.ev, true)}</span>${c ? ` <span class="dim">≈ ${sgn(Math.round(E1.ev * c / 100))}</span>` : ""}<div class="dt">of money blocked · ${pct(E1.lo, true)} to ${pct(E1.hi, true)}</div><div class="dt">retail · ${odds(S0.retail)}${early ? " <b>at the book so far</b> — retail fills on the last day, and this falls as it does" : ""}</div>`;
  // reserved categories, when the issue has them: same gain, a different (usually much shorter) queue
  const reserved = b.status === "Listed" ? "" : [["shareholder", "Shareholder category"], ["employee", "Employee category"]].map(([k, l]) => { const E2 = evOf(b, seg, k); if (!E2) return "";
    return `<div class="dt" style="margin-top:4px;padding-top:4px;border-top:1px dashed var(--line-2)" title="${l}: the book is ${S0[k]}x, so the chance of allotment is at least ${Math.round(E2.p * 1000) / 10}%. One PAN may apply here and in retail. ${k === "shareholder" ? "Needs the parent's shares in the demat on the record date; the cost and price risk of holding them is not in this figure." : ""}"><b class="${cls(E2.ev)}">${pct(E2.ev, true)}</b> ${l.toLowerCase()} · ${odds(S0[k])}${E1 && E1.ev > 0 && E2.ev > E1.ev ? ` · <b>${(E2.ev / E1.ev).toFixed(E2.ev / E1.ev >= 10 ? 0 : 1)}×</b> the retail EV` : ""}</div>`; }).join("");
  const A1 = anchorFor(b.name), K = (b.facts || {}).kpis || {};
  const more = kvs([["Band · lot", `${band} · ${b.lotSize ? b.lotSize + " shares" : "lot TBA"}`], ["Funds per lot", c ? inr0(c) : null], ["Issue size", b.issueSizeCr ? cr(b.issueSizeCr) + (b.freshCr != null || b.ofsCr != null ? ` <span class="dt">fresh ${b.freshCr != null ? cr(b.freshCr) : "—"} · OFS ${b.ofsCr != null ? cr(b.ofsCr) : "—"}</span>` : "") : null],
    ["Dates", [b.open && "opens " + fmtD(b.open), b.close && "closes " + fmtD(b.close), b.allotment && "allotment " + fmtD(b.allotment), b.listing && "lists " + fmtD(b.listing)].filter(Boolean).join(" · ")],
    ["Anchor book", A1 && A1.amountCr ? `${cr(A1.amountCr)}${A1.issueSizeCr ? " · " + Math.round(A1.amountCr / A1.issueSizeCr * 100) + "% of issue" : ""}${A1.lockIn30 ? " · lock-in ends " + fmtD(A1.lockIn30) + " / " + fmtD(A1.lockIn90) : ""}` : null],
    ["Valuation", K.pe != null ? `P/E ${K.pe}x → ${K.pePost != null ? K.pePost + "x" : "—"} post issue${K.mcapCr != null ? " · mcap " + cr(K.mcapCr) : ""}${K.roe != null ? " · ROE " + K.roe + "%" : ""}` : null],
    ["Total book, all years", TA && TA.s && TA.s.n && !early ? `${TA.lbl} · ${evLong(TA.s)} <span class="dt">${segLbl}, every listing since 2022 — an average of different markets</span>` : null],
    ["GMP, all years", GA && GA.s && GA.s.n ? `${GA.lbl} · ${evLong(GA.s)}` : null],
    ["Window", seg ? `${seg.window.n} ${segLbl} listings · ${W}` : null],
    ["On listing day", (b.status === "Closed" || b.status === "Open") && R ? holdBlock(isSme, R.c, `if it opens where GMP implies, ${pct(R.c, true)}`) : null],
    ["GMP estimate", R && b.bandHigh != null ? `lists near ${inr(b.bandHigh * (1 + R.c / 100))}; 8 in 10 comparable listings landed between ${inr(b.bandHigh * (1 + R.lo / 100))} and ${inr(b.bandHigh * (1 + R.hi / 100))}${R.prov ? " (provisional)" : ""}` : null]]);
  return `<tr class="${CHG[b.name] ? "moved" : ""}" data-row data-name="${esc(b.name)}"><td><button class="tg star${S.interest.has(b.name) ? " on" : ""}" data-star="${esc(b.name)}">★</button></td>
    <td><div class="nm"><button data-open="${esc(b.name)}">${esc(b.name)}</button></div><div class="dt">${esc(b.type)}${b.issueSizeCr ? " · " + cr(b.issueSizeCr) : ""}${b.shareholderQuota && b.shareholderQuota.parent ? ` · <span class="up">quota via ${esc(b.shareholderQuota.parent)}</span>` : ""}</div></td>
    <td><span class="pill ${b.status.toLowerCase()}">${b.status}</span><div style="margin-top:3px;font-size:12.5px">${when}</div></td>
    <td class="r">${bookCell}</td><td class="r">${gmpCell}</td><td class="r">${gainCell}</td><td class="r">${evCell}${reserved}</td>
    <td style="min-width:170px">${S0.total != null && !isSme ? subBar("QIB", S0.qib) + subBar("NII", S0.nii) + subBar("Retail", S0.retail) + subBar("Total", S0.total) + `<div class="dt">${S0.asOf ? (hasTime(S0.asOf) ? ago(S0.asOf) : "as of " + fmtD(S0.asOf)) : ""}</div>` + delta((CHG[b.name] || {}).s, v => v + "x") + spark(((LIVE || {}).timeline || {})[b.name]) : S0.total != null ? subBar("Total", S0.total) + spark(((LIVE || {}).timeline || {})[b.name]) : `<span class="dim">${b.status === "Upcoming" ? "not open" : "—"}</span>`}</td>
    <td class="r"><button class="tg" data-more title="details">▾</button></td></tr>
    <tr class="bx" hidden><td></td><td colspan="8">${more}</td></tr>`;
}
function renderBoard() {
  const order = { Open: 0, Closed: 1, Upcoming: 2, Listed: 3 };
  const srt = (a, b) => order[a.status] - order[b.status] || ((a.close || a.open || a.listing || "") > (b.close || b.open || b.listing || "") ? 1 : -1);
  const soon = b => b.status === "Open" || (b.status === "Upcoming" && days(b.open) <= 3) || (b.status === "Closed" && days(b.listing) != null && days(b.listing) <= 3) || (b.status === "Listed" && days(b.listing) === 0);
  let rows = bfilter === "sme" ? sme.slice() : bfilter === "all" ? board.slice() : bfilter === "now" ? board.filter(soon) : board.filter(b => b.status === bfilter);
  rows.sort(srt);
  if (bsort) { const val = b => bsort === "ev" ? (evOf(b, SEG(/SME/i.test(b.type))) || {}).ev : expGain(b); rows.sort((x, y) => { const a = val(x), c = val(y); return (a == null) - (c == null) || c - a; }); }
  $$("#bfilters button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.f === bfilter)));
  const W0 = SEG(false), sortTh = (k, l, t) => `<th class="r" data-bsort="${k}" style="cursor:pointer" title="${t} Click to sort.">${l}${bsort === k ? " ▼" : ""}</th>`;
  $("#board").innerHTML = `<thead><tr><th></th><th>IPO</th><th>When</th><th class="r" title="Final total subscription, against how issues in the same band listed — same segment, ${W0 ? winLbl(W0.window) : ""}">Book · track record</th><th class="r" title="Grey-market premium, against how issues in the same band listed, and where 8 in 10 landed around it">GMP · track record</th>${sortTh("gain", "If allotted", "GMP × lot size: what one lot gains if the grey market is right.")}${sortTh("ev", "EV per application", "Chance of allotment × gain, less the cost of blocked money — as % of the money blocked. The hottest books have the biggest pop and often the worst expected value.")}<th>Book</th><th></th></tr></thead><tbody>${rows.map(boardRow).join("") || `<tr><td colspan="9" class="empty">Nothing here.</td></tr>`}</tbody>`;
  const EW = (EVD().warnings || []), ew = $("#evWarn"); if (ew) { ew.hidden = !EW.length; ew.innerHTML = `<summary>Track records are for the same segment over ${W0 ? winLbl(W0.window) : "the trailing window"} · ${EW.length} caveat${EW.length === 1 ? "" : "s"} on the evidence</summary><ul class="notes">${EW.map(w => `<li>${esc(w.text)}</li>`).join("")}</ul>`; }
  $("#c-board").textContent = board.filter(b => b.status === "Open").length || "";
  const R = (DATA.recent || []).slice().sort((a, b) => (b.listingDate || "").localeCompare(a.listingDate || ""));
  $("#recent").innerHTML = `<thead><tr><th>IPO</th><th>Listed</th><th class="r">Issue</th><th class="r">Listing</th><th class="r">Gain</th><th class="r">Day-1 close</th></tr></thead><tbody>` + R.map(r => `<tr><td class="nm">${esc(r.name)}</td><td>${fmtD(r.listingDate)}</td><td class="r num">${inr(r.issuePrice)}</td><td class="r num">${inr(r.listingPrice)}</td><td class="r num ${cls(r.gainPct)}">${pct(r.gainPct, true)}</td><td class="r num ${cls(r.closeDay1GainPct)}">${r.closeDay1 != null ? inr(r.closeDay1) + " · " + pct(r.closeDay1GainPct, true) : "—"}</td></tr>`).join("") + "</tbody>";
  const O = DATA.offers || {}; $("#offersAsOf").textContent = O.asOf ? "as of " + fmtDY(O.asOf) : "";
  const card = (title, rows, fn) => `<div class="card"><div class="ch">${title}<span class="sub">${rows.length}</span></div>${rows.length ? `<div class="tw"><table><tbody>${rows.map((o, i) => fn(o, i)).join("")}</tbody></table></div>` : `<div class="empty">None open.</div>`}</div>`;
  const lnk = o => o.url ? `<a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.name)}</a>` : esc(o.name);
  const det = (o, i, kind) => o.detail ? `<tr class="od" id="od-${kind}-${i}" hidden><td colspan="3"><dl class="kv">${Object.entries(o.detail).filter(([k, v]) => v).map(([k, v]) => `<dt>${esc({ why: "Why", math: "The maths", apply: "How to apply", flag: "Flag", note: "Note" }[k] || k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl></td></tr>` : "";
  const st = o => ({ position: ["ok", "can position"], "open-holders": ["soon", "holders only"], live: ["ok", "live"], upcoming: ["plan", "opens soon"], tba: ["plan", "dates TBA"], closed: ["plan", "closed"] }[o.status] || null);
  const stp = o => { const s = st(o); return s ? `<span class="pill ${s[0]}">${s[1]}</span> ` : ""; };
  $("#offers").innerHTML = card("Rights issues", O.rights || [], (o, i) => `<tr data-od="od-r-${i}" style="cursor:pointer"><td><div class="nm">${lnk(o)} ${o.detail ? '<span class="dim">▾</span>' : ""}</div><div class="dt">${stp(o)}${esc(o.deal || "")}</div></td><td class="num">${o.price != null ? inr(o.price) : ""}${o.terp ? `<div class="dt">TERP ${inr(o.terp)}${o.cmp ? " · CMP " + inr(o.cmp) : ""}</div>` : ""}</td><td class="dt" style="white-space:nowrap">${o.record ? "record " + fmtD(o.record) + "<br>" : ""}${o.open || o.close ? `${fmtD(o.open)}–${fmtD(o.close)}` : "dates TBA"}</td></tr>` + det(o, i, "r")) +
    card("Buybacks", O.buybacks || [], (o, i) => `<tr data-od="od-b-${i}" style="cursor:pointer"><td><div class="nm">${lnk(o)} ${o.detail ? '<span class="dim">▾</span>' : ""}</div><div class="dt">${stp(o)}${esc(o.type || "")}${o.note ? " · " + esc(o.note) : ""}</div></td><td class="num">${o.price != null ? inr(o.price) : ""}</td><td class="dt" style="white-space:nowrap">${o.record && o.record !== "—" ? "record " + fmtD(o.record) + "<br>" : ""}${o.open || o.close ? `${fmtD(o.open)}–${fmtD(o.close)}` : ""}</td></tr>` + det(o, i, "b")) +
    card("OFS", O.ofs || [], o => `<tr><td><div class="nm">${lnk(o)}</div><div class="dt">${esc(o.note || "")}</div></td></tr>`) +
    card("NCDs", O.ncd || [], o => `<tr><td><div class="nm">${lnk(o)}</div><div class="dt">${esc(o.read || "")}</div></td><td class="num">${esc(o.rate || "")}<div class="dt">${esc(o.rating || "")}</div></td></tr>`);
  renderPlanner();
}
$("#offers").addEventListener("click", e => { if (e.target.closest("a")) return; const r = e.target.closest("tr[data-od]"); if (!r) return; const d = document.getElementById(r.dataset.od); if (d) d.hidden = !d.hidden; });
$("#board").addEventListener("click", e => { if (e.target.closest("[data-star],[data-open],a")) return; const r = e.target.closest("tr[data-row]"); if (r && r.nextElementSibling && r.nextElementSibling.classList.contains("bx")) r.nextElementSibling.hidden = !r.nextElementSibling.hidden; });
$("#board").addEventListener("click", e => { const th = e.target.closest("th[data-bsort]"); if (th) { bsort = bsort === th.dataset.bsort ? null : th.dataset.bsort; renderBoard(); } });
$("#bfilters").addEventListener("click", e => { const b = e.target.closest("button[data-f]"); if (b) { bfilter = b.dataset.f; renderBoard(); } });
$("#board").addEventListener("click", e => { const s = e.target.closest("[data-star]"); if (s) { S.interest.has(s.dataset.star) ? S.interest.delete(s.dataset.star) : S.interest.add(s.dataset.star); save(); renderAll(); return; } const o = e.target.closest("[data-open]"); if (o) openSheet(o.dataset.open); });

/* ---------- ₹2L quota planner ---------- */
const CAT = { Retail: [1, 13, 200000], Shareholder: [1, null, 200000], "S-HNI": [14, 67, 1000000], "B-HNI": [68, null, null], Employee: [1, null, 500000] };
let plan = { name: null, price: null, lot: null };
function renderPlanner() {
  const opts = live.filter(q => q.bucket !== "awaited" && q.quota !== false).map(q => ({ n: q.name, p: q.parent, kind: "q" })).concat(board.filter(b => b.status !== "Listed").map(b => ({ n: b.name, kind: "b" })));
  if (!plan.name && opts[0]) plan.name = opts[0].n;
  const q = Q.find(z => z.name === plan.name), b = findIssue(plan.name);
  const price = plan.price != null ? plan.price : b && b.bandHigh != null ? b.bandHigh : null, lot = plan.lot != null ? plan.lot : b && b.lotSize ? b.lotSize : null;
  const lotAmt = price && lot ? price * lot : null;
  const maxL = cap => lotAmt ? Math.floor(cap / lotAmt) : null;
  $("#planner").innerHTML = `<div class="form"><div><label class="lbl">IPO</label><select id="plName">${opts.map(o => `<option value="${esc(o.n)}"${o.n === plan.name ? " selected" : ""}>${esc(o.n)}${o.p ? " (" + esc(o.p) + ")" : ""}</option>`).join("")}</select></div><div><label class="lbl">Price ₹ (top of band)</label><input type="number" id="plPrice" value="${price != null ? price : ""}" placeholder="TBA — enter a guess"></div><div><label class="lbl">Lot size</label><input type="number" id="plLot" value="${lot != null ? lot : ""}" placeholder="TBA"></div></div>
    ${lotAmt ? `<div class="out"><div class="o"><div class="v mono">${inr0(lotAmt)}</div><div class="l">funds per lot (${lot} sh)</div></div><div class="o"><div class="v mono">${maxL(200000)} lots</div><div class="l">max in Shareholder (₹2 lakh cap) = ${inr0(maxL(200000) * lotAmt)}</div></div><div class="o"><div class="v mono">${Math.min(13, maxL(200000))} lots</div><div class="l">max in Retail (≤ ₹2 lakh, 13 lots)</div></div><div class="o"><div class="v mono">${inr0(14 * lotAmt)}+</div><div class="l">S-HNI minimum (14 lots)</div></div></div>
    <p class="dim" style="font-size:12px;margin-top:10px">${q ? `Hold ≥1 ${esc(q.parent)} share on the record date to use the Shareholder category <b>and</b> Retail/HNI in parallel — two shots at allotment, one PAN. ` : ""}Funds blocked in both categories if you apply in both.</p>` : `<div class="empty">Enter a price and lot size to plan.${q ? " " + esc(q.name) + "'s band comes with the RHP." : ""}</div>`}`;
  $("#plName").onchange = e => { plan = { name: e.target.value, price: null, lot: null }; renderPlanner(); };
  $("#plPrice").oninput = e => { plan.price = +e.target.value || null; renderPlanner(); $("#plPrice").focus(); };
  $("#plLot").oninput = e => { plan.lot = +e.target.value || null; renderPlanner(); $("#plLot").focus(); };
}

/* ---------- charts ---------- */
let charts = {};
const tok = n => getComputedStyle(root).getPropertyValue(n).trim();
function drawCharts() {
  if (typeof Chart === "undefined" || $("#s-board").hidden) return;
  Object.values(charts).forEach(c => c.destroy()); charts = {};
  const grid = tok("--chart-grid"), text = tok("--chart-text"), up = tok("--up"), down = tok("--down"), acc = tok("--accent");
  const base = { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: text, boxWidth: 10 } } }, scales: { x: { ticks: { color: text }, grid: { color: grid } }, y: { ticks: { color: text }, grid: { color: grid } } } };
  const F = DATA.flows || {}, H = (F.history || []).slice(-20);
  $("#flowsSub").textContent = F.latest ? `latest ${fmtD(F.latest.date)}` : "";
  charts.f = new Chart($("#flowsChart"), { type: "bar", data: { labels: H.map(r => fmtD(r[0])), datasets: [{ label: "FII net ₹Cr", data: H.map(r => r[1]), backgroundColor: H.map(r => r[1] >= 0 ? up : down), borderRadius: 3, maxBarThickness: 18 }, { label: "DII net ₹Cr", data: H.map(r => r[2]), backgroundColor: acc + "99", borderRadius: 3, maxBarThickness: 18 }] }, options: base });
  const R = (DATA.recent || []).filter(r => r.listingPrice != null).slice(0, 12).reverse();
  charts.r = new Chart($("#recentChart"), { type: "bar", data: { labels: R.map(r => r.name.length > 16 ? r.name.slice(0, 15) + "…" : r.name), datasets: [{ label: "Issue ₹", data: R.map(r => r.issuePrice), backgroundColor: grid, borderRadius: 3, maxBarThickness: 16 }, { label: "Listing ₹", data: R.map(r => r.listingPrice), backgroundColor: R.map(r => r.gainPct >= 0 ? up : down), borderRadius: 3, maxBarThickness: 16 }] },
    options: { ...base, plugins: { ...base.plugins, tooltip: { callbacks: { afterBody: it => "Gain " + pct(R[it[0].dataIndex].gainPct, true) } } }, scales: { x: { ticks: { color: text, autoSkip: false, maxRotation: 45, minRotation: 30, font: { size: 10 } }, grid: { display: false } }, y: { ticks: { color: text }, grid: { color: grid } } } } });
}

/* ================= RESEARCH ================= */
function renderResearchSelect() {
  const sel = $("#rsel"), opts = [];
  const pipeNames = live.map(q => q.name).filter(n => sheets[n]);
  if (pipeNames.length) opts.push(`<optgroup label="Quota pipeline">${pipeNames.map(n => `<option value="q:${esc(n)}">${esc(n)} — ${esc(Q.find(z => z.name === n).parent)}</option>`).join("")}</optgroup>`);
  const curNames = [...new Set([...Object.keys(current), ...allIssues().filter(b => (b.facts && b.status !== "Listed") || recordOf(b)).map(b => b.name)])];
  if (curNames.length) opts.push(`<optgroup label="Issues on the board">${curNames.map(n => `<option value="c:${esc(n)}">${esc(n)}${findIssue(n) ? " · " + findIssue(n).status : ""}</option>`).join("")}</optgroup>`);
  sel.innerHTML = opts.join("");
  const saved = store.get("ipo-research-sel", null);
  if (saved && [...sel.options].some(o => o.value === saved)) sel.value = saved;
  renderSheet();
}
$("#rsel").onchange = () => { store.set("ipo-research-sel", $("#rsel").value); renderSheet(); };
function openSheet(name) { const sel = $("#rsel"); const v = sheets[name] ? "q:" + name : (current[name] || (findIssue(name) || {}).facts) ? "c:" + name : null; if (!v) { toast("No sheet for " + name + " yet"); return; } sel.value = v; store.set("ipo-research-sel", v); show("research"); renderSheet(); }
const li = a => (a && a.length) ? `<ul class="plain">${a.map(s => `<li>${esc(s)}</li>`).join("")}</ul>` : `<div class="dim">—</div>`;
const kvs = pairs => `<dl class="kv">${pairs.filter(p => p[1] != null && p[1] !== "").map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
function renderSheet() {
  const v = $("#rsel").value || "", kind = v.slice(0, 1), name = v.slice(2), el = $("#sheet");
  if (!name) { el.innerHTML = `<div class="card empty">No sheets available.</div>`; return; }
  if (kind === "q") {
    const s = sheets[name], q = Q.find(z => z.name === name) || {}, t = s.timeline || {}, is = s.issue || {}, val = s.valuation || {};
    el.innerHTML = `<div class="sheet"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><h3>${esc(name)}</h3>${quotaPill(q)}<button class="tg star${S.interest.has(name) ? " on" : ""}" data-star="${esc(name)}">★</button><button class="tg hold${held(q.parent) ? " on" : ""}" data-hold="${esc(q.parent)}">✓</button></div><div class="meta">${esc(s.parent)} · <span class="mono">${esc(s.parentTicker || "")}</span>${s.parentPrice && s.parentPrice.value ? ` · parent ${inr(s.parentPrice.value)} (${fmtD(s.parentPrice.asOf)})` : ""} · ${esc(s.status || q.stage || "")}</div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="ch">Timeline</div><div class="cb">${kvs([["DRHP", fmtDY(t.drhp)], ["SEBI approval", fmtDY(t.sebiApproval)], ["RHP", t.rhp ? fmtDY(t.rhp) : "awaited"], ["Expected window", esc(t.expectedWindow) || "—"], ["Record date", t.recordDate ? `<b class="down">${fmtDY(t.recordDate)}</b>` : "not announced"], ["Approval lapses", q.lapse ? fmtDY(q.lapse) : null]])}</div></div>
        <div class="card"><div class="ch">Issue structure</div><div class="cb">${kvs([["Total", is.totalCr != null ? cr(is.totalCr) : "TBA"], ["Fresh / OFS", is.freshCr != null || is.ofsCr != null ? `${cr(is.freshCr)} / ${cr(is.ofsCr)}` : null], ["Sellers", is.sellers && is.sellers.length ? esc(is.sellers.join(", ")) : null], ["Shareholder quota", is.shareholderQuota ? esc(is.shareholderQuota) : `<span class="dim">unverified</span>`], ["Employee quota", esc(is.employeeQuota)], ["Allocation", esc(is.allocation)], ["Objects", esc(is.objects)], ["Lead managers", esc(is.leadManagers)]])}</div></div>
        <div class="card"><div class="ch">Parent logistics</div><div class="cb prose">${esc(s.logistics) || "<span class='dim'>—</span>"}</div></div>
        <div class="card"><div class="ch">Business &amp; metrics</div><div class="cb prose">${esc(s.business) || "<span class='dim'>Not yet researched — the daily task fills this in once the row is approved or DRHP-filed.</span>"}${s.metrics && s.metrics.length ? "<div style='margin-top:8px'>" + kvs(s.metrics.map(m => [m[0], esc(m[1])])) + "</div>" : ""}</div></div>
      </div>
      <div class="sec grid g2">
        <div class="card"><div class="ch">Financials</div>${s.financials && s.financials.length ? `<div class="tw"><table><thead><tr><th>FY</th><th class="r">Revenue</th><th class="r">PAT</th><th class="r">Margin</th><th class="r">RoNW</th><th>Note</th></tr></thead><tbody>${s.financials.map(f => `<tr><td>${esc(f.fy)}</td><td class="r num">${f.revenue != null ? cr(f.revenue) : "—"}</td><td class="r num ${cls(f.pat)}">${f.pat != null ? cr(f.pat) : "—"}</td><td class="r num">${f.margin != null ? f.margin + "%" : "—"}</td><td class="r num">${f.ronw != null ? f.ronw + "%" : "—"}</td><td class="dt">${esc(f.note || "")}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">No financials captured yet.</div>`}</div>
        <div class="card"><div class="ch">Valuation</div><div class="cb">${kvs([["Implied mcap", val.impliedMcapCr != null ? cr(val.impliedMcapCr) + (val.impliedMcapNote ? ` <span class="dt">${esc(val.impliedMcapNote)}</span>` : "") : null], ["Implied P/E", val.impliedPE != null ? val.impliedPE + "x" + (val.impliedPENote ? ` <span class="dt">${esc(val.impliedPENote)}</span>` : "") : null], ["Implied P/B", val.impliedPB != null ? val.impliedPB + "x" : null]])}${val.peers && val.peers.length ? `<div class="chart-wrap" style="height:160px;margin-top:8px"><canvas id="peerChart"></canvas></div>` : `<div class="dim" style="margin-top:6px">Peer multiples not yet captured.</div>`}</div></div>
      </div>
      ${((s.bull || []).length || (s.bear || []).length) ? "" : `<div class="sec dt">No written analysis for this issue yet — everything above is fetched, not an opinion.</div>`}
    <div class="sec grid g2"${((s.bull || []).length || (s.bear || []).length) ? "" : " hidden"}><div class="card"><div class="ch up">For</div><div class="cb">${li(s.bull)}</div></div><div class="card"><div class="ch down">Against</div><div class="cb">${li(s.bear)}</div></div></div>
      <div class="sec grid g2"><div class="card"><div class="ch">Flags</div><div class="cb">${s.flags && s.flags.length ? s.flags.map(f => `<div class="flag">${esc(f)}</div>`).join("") : "<span class='dim'>—</span>"}</div></div><div class="card"><div class="ch">Street view</div><div class="cb">${s.street && s.street.length ? `<table><tbody>${s.street.map(v => `<tr><td class="nm">${esc(v.who)}</td><td class="dt">${fmtD(v.date)}</td><td>${esc(v.view)}</td></tr>`).join("")}</tbody></table>` : "<span class='dim'>No broker views captured yet.</span>"}</div></div></div>
      <div class="sec docs">${(s.sources || []).map(u => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\//, "").slice(0, 60))}</a>`).join("") || "<span class='dim' style='font-size:12px'>Source links are attached on the next refresh.</span>"}</div></div>`;
    if (val.peers && val.peers.length && typeof Chart !== "undefined") { if (charts.p) charts.p.destroy(); charts.p = new Chart($("#peerChart"), { type: "bar", data: { labels: val.peers.map(p => p[0]), datasets: [{ label: val.peers[0][2] || "multiple", data: val.peers.map(p => p[1]), backgroundColor: tok("--accent") + "99", borderRadius: 3 }] }, options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: tok("--chart-text") }, grid: { color: tok("--chart-grid") } }, y: { ticks: { color: tok("--chart-text") }, grid: { display: false } } } } }); }
    return;
  }
  const c = current[name] || {}, r = c.research || {}, rec = c.recs || {}, sh = c.sheet || {}, b = findIssue(name), fin = r.financials && r.financials.rows ? r.financials.rows : [];
  const g = b ? expGain(b) : null, lc = b ? lotCost(b) : null;
  // fetched facts (the collector's per-IPO record) stand in wherever no written research exists
  const F = (b && b.facts) || {}, K = F.kpis || {}, D = F.docs || {}, pc = v => v != null ? v + "%" : null, x = v => v != null ? v + "x" : null;
  const A0 = b ? anchorFor(b.name) : null;
  const RC = recordOf(b);
  const factsKv = !b ? null : [["Issue size", b.issueSizeCr != null ? cr(b.issueSizeCr) : null], ["Fresh / OFS", b.freshCr != null || b.ofsCr != null ? `${b.freshCr != null ? cr(b.freshCr) : "—"} / ${b.ofsCr != null ? cr(b.ofsCr) : "—"}` : null],
    ["Price band", b.bandHigh ? `${inr(b.bandLow || b.bandHigh)} – ${inr(b.bandHigh)}` : null], ["Lot", b.lotSize ? b.lotSize + " shares" : null],
    ["Allotment · listing", b.allotment || b.listing ? `${fmtD(b.allotment)} · ${fmtD(b.listing)}` : null], ["Sector", esc(F.sector)],
    ["Anchor book", A0 && A0.amountCr ? `${cr(A0.amountCr)}${A0.lockIn30 ? ` · lock-in ends ${fmtD(A0.lockIn30)} / ${fmtD(A0.lockIn90)}` : ""}` : null],
    ["Promoter holding", K.promoterPre != null ? `${K.promoterPre}% → ${K.promoterPost != null ? K.promoterPost + "%" : "—"}` : null],
    ["Lead managers", F.leadManagers ? esc(F.leadManagers.join(", ")) : null], ["Registrar", esc(F.registrar)],
    ["Broker views", F.recs && F.recs.length ? F.recs.map(r => `${esc(r.who)}: <b>${esc(r.view || "—")}</b>`).join(" · ") : null],
    ["Documents", Object.keys(D).length ? Object.entries(D).map(([k, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc({ drhp: "DRHP", rhp: "RHP", prospectus: "Prospectus", anchorLetter: "Anchor letter", allotment: "Allotment status" }[k] || k)}</a>`).join(" · ") : null]];
  const factsVal = Object.keys(K).length ? [["P/E pre → post issue", K.pe != null ? `${K.pe}x → ${K.pePost != null ? K.pePost + "x" : "—"}` : null], ["Market cap", K.mcapCr != null ? cr(K.mcapCr) : null], ["ROE · ROCE", K.roe != null || K.roce != null ? `${pc(K.roe) || "—"} · ${pc(K.roce) || "—"}` : null], ["RoNW", pc(K.ronw)], ["Debt / equity", K.debtEquity != null ? String(K.debtEquity) : null], ["PAT · EBITDA margin", K.patMargin != null || K.ebitdaMargin != null ? `${pc(K.patMargin) || "—"} · ${pc(K.ebitdaMargin) || "—"}` : null], ["Price / book", x(K.pb)], ["EPS pre → post", K.eps != null ? `${inr(K.eps)} → ${K.epsPost != null ? inr(K.epsPost) : "—"}` : null], ["As of", K.asOf ? fmtDY(K.asOf) : null]] : null;
  el.innerHTML = `<div class="sheet"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><h3>${esc(name)}</h3>${b ? `<span class="pill ${b.status.toLowerCase()}">${b.status}</span>` : ""}<button class="tg star${S.interest.has(name) ? " on" : ""}" data-star="${esc(name)}">★</button></div><div class="meta">${b ? `${esc(b.type)} · ${fmtD(b.open)}–${fmtD(b.close)} · lists ${fmtD(b.listing)} · band ${b.bandLow != null ? inr(b.bandLow) + "–" : ""}${inr(b.bandHigh)} · GMP ${b.gmp != null ? inr(b.gmp) + " (" + pct(b.gmpPct, true) + ")" : "—"}` : esc(r.status || "")}</div>
    ${b && lc ? `<div class="kpis" style="margin-top:14px"><div class="card kpi"><div class="lbl">Funds per lot</div><div class="v mono">${inr0(lc)}</div><div class="d">${b.lotSize} shares at ${inr(b.bandHigh)}</div></div><div class="card kpi"><div class="lbl">Expected gain / lot</div><div class="v mono ${cls(g)}">${sgn(g)}</div><div class="d">at GMP ${inr(b.gmp)}; grey market, not a promise</div></div><div class="card kpi"><div class="lbl">Retail odds</div><div class="v mono">${b.sub && b.sub.retail != null ? odds(b.sub.retail) : "—"}</div><div class="d">${b.sub && b.sub.retail != null ? "retail book " + xx(b.sub.retail) : "book not open"}</div></div><div class="card kpi"><div class="lbl">Retail max</div><div class="v mono">${Math.min(13, Math.floor(200000 / lc))} lots</div><div class="d">${inr0(Math.min(13, Math.floor(200000 / lc)) * lc)} · S-HNI from ${inr0(14 * lc)}</div></div>${(() => { const A9 = anchorFor(name), n9 = b.igId != null ? (((DATA.players || {}).books || {})[String(b.igId)] || []).length : 0; return !A9 || !A9.amountCr ? "" : `<div class="card kpi"><div class="lbl">Anchor book</div><div class="v mono">${cr(A9.amountCr)}</div><div class="d">${A9.issueSizeCr ? Math.round(A9.amountCr / A9.issueSizeCr * 100) + "% of the issue · " : ""}${(DATA.players || {}).tracked ? n9 + " of the " + DATA.players.tracked + " largest anchors in it" : ""}</div></div>`; })()}</div>` : ""}
    ${rec.consensus ? `<div class="card" style="margin-top:14px;padding:12px 18px;border-color:var(--amber)"><span class="lbl amb">Consensus</span> &nbsp;${esc(rec.consensus)}</div>` : ""}
    <div class="grid g2" style="margin-top:14px">
      <div class="card"><div class="ch">Issue sheet${!sh.kv && factsKv ? ` <span class="sub">fetched${F.asOf ? " · " + fmtD(F.asOf) : ""}</span>` : ""}</div><div class="cb">${sh.kv ? kvs(sh.kv.filter(p => !/^⚠/.test(p[0])).map(p => [p[0], esc(p[1])])) : factsKv ? kvs(factsKv) : "<span class='dim'>—</span>"}</div></div>
      <div class="card"><div class="ch">Demand ${r.demand && r.demand.asOf ? `<span class="sub">${esc(r.demand.asOf)}</span>` : ""}</div><div class="cb">${r.demand && Array.isArray(r.demand.sub) && r.demand.sub.length && r.demand.sub.every(Array.isArray) && !(b && b.sub && b.sub.total != null) ? r.demand.sub.map(s => subBar(String(s[0]).replace(" (HNI)", ""), s[1])).join("") : b && b.sub && b.sub.total != null ? [["QIB", b.sub.qib], ["NII", b.sub.nii], ["Retail", b.sub.retail], ["Employee", b.sub.employee], ["Shareholder", b.sub.shareholder], ["Total", b.sub.total]].filter(s => s[1] != null).map(s => subBar(s[0], s[1])).join("") + `<div class="dt">${b.sub.asOf ? "as of " + fmtD(b.sub.asOf) + fmtT(b.sub.asOf) : ""}</div>` : "<span class='dim'>Not open yet.</span>"}${r.demand && r.demand.anchor ? `<div class="prose" style="margin-top:8px"><b>Anchor:</b> ${esc(r.demand.anchor)}</div>` : ""}${r.demand && r.demand.read ? `<div class="prose" style="margin-top:8px">${esc(r.demand.read)}</div>` : ""}</div></div>
    </div><div class="sec grid g2">
      <div class="card"><div class="ch">Financials${!fin.length && RC && RC.financials ? ` <span class="sub">${esc(RC.financials.title || "₹ Cr")}</span>` : ""}</div>${!fin.length && RC && RC.financials ? recTbl(RC.financials) : ""}${fin.length ? `<div class="tw"><table><thead><tr><th>FY</th><th class="r">Revenue ₹Cr</th><th class="r">PAT ₹Cr</th></tr></thead><tbody>${fin.map(f => `<tr><td>${esc(f[0])}</td><td class="r num">${f[1] != null ? f[1] : "—"}</td><td class="r num ${cls(f[2])}">${f[2] != null ? f[2] : "—"}</td></tr>`).join("")}</tbody></table></div>` : ""}${r.financials && r.financials.read ? `<div class="cb prose">${esc(r.financials.read)}</div>` : ""}</div>
      <div class="card"><div class="ch">Valuation</div><div class="cb">${r.valuation && r.valuation.own ? kvs([["P/E", r.valuation.own.pe != null ? r.valuation.own.pe + "x" : null], ["RoNW", r.valuation.own.ronw != null ? r.valuation.own.ronw + "%" : null], ["EPS", r.valuation.own.eps != null ? inr(r.valuation.own.eps) : null]]) : factsVal ? kvs(factsVal) : ""}${r.valuation && r.valuation.peers && r.valuation.peers.length ? `<table style="margin-top:6px"><tbody>${r.valuation.peers.map(p => `<tr><td>${esc(p[0])}</td><td class="r num">${esc(p[1])}${typeof p[1] === "number" ? "x" : ""}</td></tr>`).join("")}</tbody></table>` : ""}${!(r.valuation && r.valuation.peers && r.valuation.peers.length) && RC && RC.peers ? `<div class="dt" style="margin:10px 0 4px">Listed peers${RC.peers.asOf ? " · as on " + fmtDY(RC.peers.asOf) : ""}</div>${recTbl(RC.peers)}` : ""}${r.valuation && r.valuation.read ? `<div class="prose" style="margin-top:8px">${esc(r.valuation.read)}</div>` : ""}</div></div>
    </div>
    ${recordCards(b)}
    ${comparablesCard(b)}
    ${rec.claude && ((rec.claude.bull || []).length || (rec.claude.bear || []).length) ? "" : `<div class="sec dt">No written analysis for this issue yet — everything above is fetched, not an opinion.</div>`}
    <div class="sec grid g2"${rec.claude && ((rec.claude.bull || []).length || (rec.claude.bear || []).length) ? "" : " hidden"}><div class="card"><div class="ch up">For</div><div class="cb">${li(rec.claude && rec.claude.bull)}</div></div><div class="card"><div class="ch down">Against</div><div class="cb">${li(rec.claude && rec.claude.bear)}</div></div></div>
    ${(() => { const flags = (r.governance && r.governance.flags) || [], ex = rec.experts && rec.experts.length ? rec.experts.map(e => [e[0], e[1], e[2]]) : (F.recs || []).map(v => [v.who, v.view || "—", v.date ? fmtD(v.date) : "", v.url]);
      if (!flags.length && !ex.length) return "";
      const tally = {}; ex.forEach(e => { const k = /subscribe|apply|buy|positive/i.test(e[1]) ? "positive" : /avoid|sell|negative/i.test(e[1]) ? "negative" : /neutral|may apply|long term|risk/i.test(e[1]) ? "neutral / conditional" : "other"; tally[k] = (tally[k] || 0) + 1; });
      return `<div class="sec grid g2">${flags.length ? `<div class="card"><div class="ch">Governance flags</div><div class="cb">${flags.map(f => `<div class="flag">${esc(Array.isArray(f) ? f[1] : f)}</div>`).join("")}</div></div>` : ""}
        ${ex.length ? `<div class="card"><div class="ch">Street view <span class="sub">${ex.length} broker view${ex.length === 1 ? "" : "s"}${rec.experts && rec.experts.length ? "" : " · fetched"} · ${Object.entries(tally).map(([k, n]) => n + " " + k).join(" · ")}</span></div><div class="cb"><table><tbody>${ex.map(e => `<tr><td class="nm">${e[3] && /^https?:/.test(e[3]) ? `<a href="${esc(e[3])}" target="_blank" rel="noopener">${esc(e[0])}</a>` : esc(e[0])}</td><td>${esc(e[1])}<div class="dt">${esc(e[2] || "")}</div></td></tr>`).join("")}</tbody></table></div></div>` : ""}</div>`; })()}
    ${r.company && r.company.about ? `<div class="sec card"><div class="ch">Company</div><div class="cb prose">${esc(r.company.about)}${r.company.facts ? "<div style='margin-top:8px'>" + kvs(r.company.facts.map(f => [f[0], esc(f[1])])) + "</div>" : ""}</div></div>` : ""}
    ${r.allotment ? `<div class="sec card"><div class="ch">Allotment</div><div class="cb prose">${esc(r.allotment)}</div></div>` : ""}
    ${rec.claude && rec.claude.take ? `<div class="sec card"><div class="ch">Synthesis</div><div class="cb prose">${esc(rec.claude.take)}</div></div>` : ""}
    <div class="sec docs">${(r.docs || sh.docs || []).map(dd => `<a href="${esc(dd[1])}" target="_blank" rel="noopener">${esc(dd[0])}</a>`).join("")}</div></div>`;
}
$("#sheet").addEventListener("click", e => { const s = e.target.closest("[data-star]"); if (s) { S.interest.has(s.dataset.star) ? S.interest.delete(s.dataset.star) : S.interest.add(s.dataset.star); save(); renderAll(); } const h = e.target.closest("[data-hold]"); if (h) { toggleHold(h.dataset.hold); renderAll(); } });

/* ================= BOOK ================= */
function markPrice(name) { const ph = (DATA.priceHistory || {})[name]; if (ph && ph.length) return ph[ph.length - 1][1]; const b = findIssue(name); return b ? b.listingPrice : null; }
function parentPrice(p) { const s = Object.values(sheets).find(s => s.parent === p && s.parentPrice && s.parentPrice.value); return s ? s.parentPrice.value : null; }
function renderBook() {
  // holdings
  const pm = {}; Q.forEach(q => (pm[q.parent] = pm[q.parent] || []).push(q));
  $("#parentNames").innerHTML = Object.keys(pm).sort().map(p => `<option value="${esc(p)}">`).join("");
  let hCost = 0, hVal = 0, hKnown = true;
  const hrows = S.holdings.map((h, i) => { const p = holdName(h), o = typeof h === "object" ? h : {}, subs = (pm[p] || []).filter(q => !["done", "dropped"].includes(q.bucket)), mp = parentPrice(p), cost = o.qty && o.price ? o.qty * o.price : null, val = o.qty && mp ? o.qty * mp : null; if (cost) hCost += cost; if (val) hVal += val; else if (cost) hKnown = false;
    return `<tr data-row data-name="${esc(p)}"><td><div class="nm">${esc(p)}</div><div class="dt">${subs.length ? subs.map(q => `${esc(q.name)} · ${esc(q.stage)}`).join("<br>") : "no live subsidiary IPO"}</div></td><td class="num">${o.qty ? o.qty + " sh" : "✓"}</td><td class="r num">${o.price ? inr(o.price) : "—"}</td><td class="r num">${mp ? inr(mp) : "—"}</td><td class="r num ${cls(val != null && cost != null ? val - cost : null)}">${val != null && cost != null ? sgn(val - cost) : "—"}</td><td><button class="x" data-delhold="${i}">✕</button></td></tr>`; });
  $("#holdings").innerHTML = `<thead><tr><th>Parent</th><th>Qty</th><th class="r">Bought</th><th class="r">Last</th><th class="r">P&amp;L</th><th></th></tr></thead><tbody>${hrows.join("") || `<tr><td colspan="6" class="empty">Tick ✓ on a pipeline name, or log qty and price here.</td></tr>`}</tbody>`;
  // apps
  $("#ipoNames").innerHTML = allIssues().map(b => `<option value="${esc(b.name)}">`).join("");
  let aCost = 0, aPnl = 0;
  const arows = S.apps.map((a, i) => { const b = findIssue(a.name) || {}, lot = (DATA.lot || {})[a.name] || {}, shares = a.lots * (lot.shares || b.lotSize || 0), cost = shares * a.price, mark = a.status === "Sold" ? a.sold : markPrice(a.name), pnl = ["Not allotted", "Applied"].includes(a.status) ? null : (mark != null && shares ? (mark - a.price) * shares : null); if (a.status === "Applied") aCost += cost; if (pnl != null) aPnl += pnl;
    return `<tr data-row data-name="${esc(a.name)}"><td><div class="nm">${esc(a.name)}</div><div class="dt">${esc(a.cat)}</div></td><td class="num">${a.lots} lot${a.lots > 1 ? "s" : ""}${shares ? `<div class="dt">${shares} sh</div>` : ""}</td><td class="r num">${inr(a.price)}<div class="dt">${shares ? inr0(cost) : ""}</div></td><td>${esc(a.status)}</td><td class="r num">${mark != null ? inr(mark) : "—"}</td><td class="r num ${cls(pnl)}">${pnl != null ? sgn(pnl) : "—"}</td><td><button class="x" data-delapp="${i}">✕</button></td></tr>`; });
  $("#apps").innerHTML = `<thead><tr><th>IPO</th><th>Qty</th><th class="r">Price · cost</th><th>Status</th><th class="r">Mark</th><th class="r">P&amp;L</th><th></th></tr></thead><tbody>${arows.join("") || `<tr><td colspan="7" class="empty">No applications logged.</td></tr>`}</tbody>`;
  $("#totals").innerHTML = `<div><div class="v mono ${cls(aPnl)}">${S.apps.length ? sgn(aPnl) : "—"}</div><div class="l">IPO P&amp;L (allotted + sold)</div></div><div><div class="v mono">${inr0(aCost)}</div><div class="l">funds blocked in open applications</div></div><div><div class="v mono ${cls(hVal - hCost)}">${hCost ? (hKnown ? sgn(hVal - hCost) : "—") : "—"}</div><div class="l">parent shares P&amp;L${hCost && !hKnown ? " (no parent price in data yet)" : ""}</div></div><div><div class="v mono">${heldNames().length}</div><div class="l">parents held · ${live.filter(q => held(q.parent) && q.bucket !== "awaited").length} live names covered</div></div>`;
  // done/snoozed + tasks
  const all = buildQueue(); const dn = all.filter(p => isDone(p.id));
  $("#doneList").innerHTML = dn.length ? dn.map(p => { const sn = [...S.done].find(k => k.startsWith(p.id + "@")); return `<div class="task done"><input type="checkbox" checked data-undo="${esc(p.id)}"><div class="t">${esc(p.ttl)}<small>${sn ? "snoozed until " + fmtD(sn.split("@")[1]) : "done"}</small></div><span></span></div>`; }).join("") : `<div class="empty">Nothing done or snoozed.</div>`;
  $("#tasks").innerHTML = S.tasksCustom.length ? S.tasksCustom.map(t => `<div class="task${S.done.has(t.id) ? " done" : ""}"><input type="checkbox" data-id="${esc(t.id)}" ${S.done.has(t.id) ? "checked" : ""}><div class="t">${esc(t.text)}<small>added ${fmtD(t.added)}</small></div><button class="x" data-del="${esc(t.id)}">✕</button></div>`).join("") : `<div class="empty">No custom tasks.</div>`;
  $("#c-book").textContent = S.tasksCustom.filter(t => !S.done.has(t.id)).length || "";
}
function bounds() {
  const n = $("#apName").value, cat = $("#apCat").value, b = findIssue(n), c = CAT[cat];
  if (!b || !c) { $("#apBounds").textContent = ""; return; }
  const lc = lotCost(b); if (!lc) { $("#apBounds").textContent = "Lot size or band not yet known for this IPO."; return; }
  const maxLots = c[2] ? Math.min(c[1] || 999, Math.floor(c[2] / lc)) : c[1];
  $("#apBounds").textContent = `${cat}: ${c[0]} lot = ${inr0(c[0] * lc)} minimum${maxLots ? `; up to ${maxLots} lots = ${inr0(maxLots * lc)}` : ""}${cat === "Shareholder" ? " (₹2 lakh cap; one application per PAN per category)" : ""}.`;
  if (!$("#apPrice").value && b.bandHigh) $("#apPrice").value = b.bandHigh;
}
["#apName", "#apCat"].forEach(s => $(s).addEventListener("input", bounds));
$("#apAdd").onclick = () => { const n = $("#apName").value.trim(); if (!n) return; S.apps.push({ name: n, cat: $("#apCat").value, lots: +$("#apLots").value || 1, price: +$("#apPrice").value || 0, status: $("#apStatus").value, sold: +$("#apSold").value || null, added: iso(today) }); save(); $("#apName").value = ""; $("#apPrice").value = ""; $("#apSold").value = ""; toast("Application logged"); renderAll(); };
$("#hAdd").onclick = () => { const p = $("#hName").value.trim(); if (!p) return; S.holdings = S.holdings.filter(h => holdName(h) !== p); S.holdings.push({ parent: p, qty: +$("#hQty").value || 1, price: +$("#hPrice").value || null, date: iso(today) }); save(); $("#hName").value = ""; $("#hPrice").value = ""; toast("Holding logged"); renderAll(); };
$("#taskAdd").onclick = () => { const t = $("#taskIn").value.trim(); if (!t) return; S.tasksCustom.push({ id: "c:" + Date.now(), text: t, added: iso(today) }); $("#taskIn").value = ""; save(); renderBook(); };
$("#taskIn").addEventListener("keydown", e => { if (e.key === "Enter") $("#taskAdd").click(); });
$("#s-book").addEventListener("change", e => { const cb = e.target.closest("input[type=checkbox]"); if (!cb) return; if (cb.dataset.undo) { S.done.delete(cb.dataset.undo); [...S.done].filter(k => k.startsWith(cb.dataset.undo + "@")).forEach(k => S.done.delete(k)); } else if (cb.dataset.id) { cb.checked ? S.done.add(cb.dataset.id) : S.done.delete(cb.dataset.id); } save(); renderAll(); });
$("#s-book").addEventListener("click", e => { const t = e.target.closest("button"); if (!t) return; if (t.dataset.del) { S.tasksCustom = S.tasksCustom.filter(x => x.id !== t.dataset.del); } else if (t.dataset.delapp != null) S.apps.splice(+t.dataset.delapp, 1); else if (t.dataset.delhold != null) S.holdings.splice(+t.dataset.delhold, 1); else return; save(); renderAll(); });


/* ================= MARKET ================= */
// a band's outcome, looked up from the collector's own evidence (never a page-side score): {i, s: {n,pos,lo,hi,med,p10,p90}, lbl}
const evBand = (seg, key, v, where) => { if (!seg || v == null) return null; const ed = EDG(key), i = bandOf(v, ed); return i >= 0 ? { i, s: seg.bands[key][where][i], lbl: edgeLbl(ed, i, key === "gmp" ? "%" : "x") } : null; };
const norm2 = s => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
const sameName = (x, y) => { const a = norm2((x || "").replace(/\(.*?\)/g, "").split(" ").slice(0, 2).join(" ")), b = norm2((y || "").replace(/\(.*?\)/g, "").split(" ").slice(0, 2).join(" ")); return a && b && (a.startsWith(b) || b.startsWith(a)); };
const anchorFor = name => (DATA.anchors || []).find(a => sameName(a.name, name));
const watchNames = () => { const I = DATA.investors || {}, l = store.get("ipo-investors", { add: [], remove: [] }) || {}; return [...new Set([...(I.watchlist || (I.portfolios || []).map(p => p.name)), ...(l.add || [])])].filter(n => !(l.remove || []).includes(n)); };
// Flow context, computed from the rows the collector fetched (NSE's daily FII / DII cash figures): sums over windows, how
// often each side bought, how much of FII selling DIIs absorbed, and how mainboard listings did on FII-buy vs FII-sell days.
// Counting on fetched rows with n shown. It replaced db-era monthly / rotation prose last written by hand in August.
function flowContext(hist) {
  const H = hist.filter(r => r && r[0] && r[1] != null && r[2] != null); if (H.length < 3) return `<div class="empty">Not enough sessions on file yet.</div>`;
  const sum = (rows, i) => rows.reduce((a, r) => a + (r[i] || 0), 0), wins = [5, 10, 20].filter(n => H.length >= n).map(n => [n, H.slice(-n)]), S20 = H.slice(-20);
  // 1. the session strip: one cell a day, colour = bought / sold, strength = size; a dashed gap where days are missing on file
  const mx = Math.max(1, ...S20.map(r => Math.max(Math.abs(r[1]), Math.abs(r[2]))));
  const cellRow = (i, lbl) => `<div class="fs-row"><span class="fs-l">${lbl}</span>${S20.map((r, k) => { const gap = k && (d(r[0]) - d(S20[k - 1][0])) / DAY > 5; return `${gap ? '<i class="fs-gap" title="sessions missing on file"></i>' : ""}<i class="fs-c ${r[i] >= 0 ? "up" : "down"}" style="--o:${(0.25 + 0.75 * Math.abs(r[i]) / mx).toFixed(2)};animation-delay:${k * 25}ms" title="${fmtD(r[0])}: ${lbl} ${sgn(Math.round(r[i]))} Cr"></i>`; }).join("")}</div>`;
  let streak = 1; for (let i = H.length - 2; i >= 0 && (H[i][1] > 0) === (H[H.length - 1][1] > 0); i--) streak++;
  const strip = `<div class="lbl" style="margin-bottom:6px">Last ${S20.length} sessions on file · ${fmtD(S20[0][0])} → ${fmtD(S20[S20.length - 1][0])}</div><div class="fstrip">${cellRow(1, "FII")}${cellRow(2, "DII")}</div>
    <div class="dt" style="margin-top:6px">green bought · red sold · stronger colour = bigger day. FIIs have been net ${H[H.length - 1][1] > 0 ? "buyers" : "sellers"} for <b>${streak}</b> session${streak === 1 ? "" : "s"} running.</div>`;
  // 2. tug of war: what each pool did over 5 / 10 / 20 sessions, pulling left (sold) or right (bought) from the centre line
  const wmx = Math.max(1, ...wins.map(([, rows]) => Math.max(Math.abs(sum(rows, 1)), Math.abs(sum(rows, 2)))));
  const pull = (v, c) => `<div class="tug-bar"><i class="${c} ${v >= 0 ? "pos" : "neg"}" style="width:${Math.max(1, Math.abs(v) / wmx * 50).toFixed(1)}%"></i></div>`;
  const tug = `<div class="lbl" style="margin:16px 0 6px">Who pulled harder · ₹ Cr, sold ← → bought</div><div class="tug">${wins.map(([n, rows]) => { const f = sum(rows, 1), dd = sum(rows, 2); return `<div class="tug-row"><div class="tug-l">last ${n}<small>${rows.filter(r => r[1] > 0).length} of ${n} days FIIs bought</small></div><div class="tug-bars">${pull(f, f >= 0 ? "up" : "down")}${pull(dd, "acc")}</div><div class="tug-v num"><span class="${cls(f)}">FII ${sgn(Math.round(f))}</span><span class="acc">DII ${sgn(Math.round(dd))}</span></div></div>`; }).join("")}</div>`;
  const W = (wins[wins.length - 1] || [H.length, H])[1], f = sum(W, 1), dd = sum(W, 2);
  const absorb = f < 0 && dd > 0 ? `<div class="dt" style="margin-top:6px">Over ${W.length} sessions domestic funds bought <b>${dd / -f >= 2 ? (dd / -f).toFixed(1) + "×" : Math.round(100 * dd / -f) + "% of"}</b> what FIIs sold.</div>` : "";
  // 3. did it matter for listings? mainboard listing gains on FII-buy days vs FII-sell days, with n
  const onDay = {}; H.forEach(r => onDay[r[0]] = r[1]);
  const L0 = (DATA.listedPerf || []).filter(p => !p.sme && p.issue && p.listing != null && onDay[p.date] != null).map(p => ({ buy: onDay[p.date] > 0, ret: 100 * (p.listing - p.issue) / p.issue }));
  const sides = [["FII-buying days", true], ["FII-selling days", false]].map(([l, b1]) => { const x = L0.filter(v => v.buy === b1).map(v => v.ret); return { l, n: x.length, m: x.length ? median(x) : null }; }), lmx = Math.max(1, ...sides.map(x => Math.abs(x.m || 0)));
  const lst = L0.length ? `<div class="lbl" style="margin:16px 0 6px">Mainboard listings on those days · median gain</div><div class="hbars">${sides.map(x => `<div class="hb"><div class="n">${x.l}<small>${x.n} listing${x.n === 1 ? "" : "s"}</small></div><div class="bar"><i class="${(x.m || 0) >= 0 ? "up" : "down"} grow" style="left:0;width:${x.m == null ? 0 : Math.max(2, Math.abs(x.m) / lmx * 100)}%"></i></div><div class="v num ${cls(x.m)}">${x.m == null ? "—" : pct(x.m, true)}</div></div>`).join("")}</div><div class="dt" style="margin-top:6px">A small sample — a pattern to watch, not a rule.</div>` : "";
  return strip + tug + absorb + lst;
}
let mcharts = {}, smeSort = { k: "status", dir: 1 }, mktCompScope = "main";
const binCls = s => ({ hi: "up", lo: "down", mid: "mid", na: "mid" }[evCls(s)]);
$("#compScope").addEventListener("click", e => { const b = e.target.closest("button[data-sc]"); if (b) { mktCompScope = b.dataset.sc; renderMarket(); } });
$("#smeScreen").addEventListener("click", e => { const o = e.target.closest("[data-open]"); if (o) { openSheet(o.dataset.open); return; } const th = e.target.closest("th[data-sort]"); if (!th) return; smeSort = smeSort.k === th.dataset.sort ? { k: th.dataset.sort, dir: -smeSort.dir } : { k: th.dataset.sort, dir: 1 }; renderMarket(); });
function renderMarket() {
  const grid = tok("--chart-grid"), text = tok("--chart-text"), up = tok("--up"), down = tok("--down"), acc = tok("--accent"), lav = tok("--lav");
  // temperature
  const LP = (DATA.listedPerf || []).filter(r => r.issue && r.listing != null);
  const gain = r => (r.listing - r.issue) / r.issue * 100, pred = r => r.gmpImplied != null ? (r.gmpImplied - r.issue) / r.issue * 100 : null;
  const avg = xs => xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : 0;
  const last10 = LP.slice(0, 10).map(gain), prev10 = LP.slice(10, 20).map(gain), last20 = LP.slice(0, 20);
  const a10 = avg(last10), p10 = avg(prev10), trend = a10 - p10, hit = last20.length ? Math.round(last20.filter(r => gain(r) > 0).length / last20.length * 100) : 0;
  const errs = last20.filter(r => pred(r) != null).map(r => Math.abs(gain(r) - pred(r))), gmpErr = avg(errs);
  const best = last20.slice().sort((x, y) => gain(y) - gain(x))[0], worst = last20.slice().sort((x, y) => gain(x) - gain(y))[0];
  $("#mtKpis").innerHTML = [["Avg gain · last 10 listings", pct(a10, true), `${LP.length ? fmtD(null) && "" : ""}mainboard, by listing date`, cls(a10)], ["vs prior 10", (trend > 3 ? "warming ▲" : trend < -3 ? "cooling ▼" : "steady →"), `prior 10 averaged ${pct(p10, true)}`, trend > 3 ? "up" : trend < -3 ? "down" : ""], ["Hit rate · last 20", hit + "%", "listed above issue price", hit >= 60 ? "up" : hit >= 40 ? "amb" : "down"], ["GMP miss · avg", "±" + gmpErr.toFixed(1) + "pp", "grey market vs actual listing", gmpErr <= 6 ? "up" : gmpErr <= 10 ? "amb" : "down"]]
    .map(([l, v, dd, c]) => `<div class="card kpi"><div class="lbl">${l}</div><div class="v mono ${c}">${v}</div><div class="d">${esc(dd)}</div></div>`).join("");
  $("#mtRead").innerHTML = `The IPO market is <b>${trend > 3 ? "warming" : trend < -3 ? "cooling" : "steady"}</b>: the last 10 listings averaged ${pct(a10, true)} against ${pct(p10, true)} for the 10 before, and ${hit}% of the last 20 listed above issue. GMP has missed the actual pop by ±${gmpErr.toFixed(1)} points on average — ${gmpErr <= 6 ? "a usable guide" : gmpErr <= 10 ? "directionally right, size it down" : "not to be trusted for sizing"}. Best of the last 20: <b>${best ? esc(best.name) : "—"}</b> ${best ? pct(gain(best), true) : ""}; worst: <b>${worst ? esc(worst.name) : "—"}</b> ${worst ? pct(gain(worst), true) : ""}.`;
  Object.values(mcharts).forEach(c => c.destroy()); mcharts = {};
  if (typeof Chart !== "undefined") {
    const seq = LP.slice(0, 24).reverse(), sg = seq.map(gain), roll = sg.map((_, i) => +avg(sg.slice(Math.max(0, i - 4), i + 1)).toFixed(1));
    mcharts.mt = new Chart($("#mtChart"), { data: { labels: seq.map(r => r.name.length > 14 ? r.name.slice(0, 13) + "…" : r.name), datasets: [{ type: "bar", label: "Listing gain %", data: sg.map(v => +v.toFixed(1)), backgroundColor: sg.map(v => v >= 0 ? up : down), borderRadius: 3, maxBarThickness: 22, order: 2 }, { type: "line", label: "5-listing trend", data: roll, borderColor: acc, borderWidth: 2.5, borderDash: [6, 3], pointRadius: 0, tension: .3, order: 1 }] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, plugins: { legend: { position: "bottom", labels: { color: text, boxWidth: 10 } }, tooltip: { callbacks: { afterBody: it => { const r = seq[it[0].dataIndex], pg = pred(r); return pg != null ? "GMP had implied " + pct(pg, true) : "no GMP tracked"; } } } }, scales: { x: { ticks: { color: text, autoSkip: false, maxRotation: 45, minRotation: 30, font: { size: 10 } }, grid: { display: false } }, y: { ticks: { color: text, callback: v => v + "%" }, grid: { color: grid } } } } });
    // comparables — mainboard and SME are NEVER pooled (71% of the base is SME: a pooled bin describes neither); the bins are
    // the collector's own evidence.bands.total (n, Wilson interval, median), not an average taken here on the page.
    $$("#compScope button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.sc === mktCompScope)));
    const isSme = mktCompScope === "sme", segLbl = isSme ? "SME" : "mainboard";
    const C = (DATA.comps || []).filter(c => !!c.sme === isSme && typeof c.total === "number" && c.ret != null);
    const liveP = allIssues().filter(r => /SME/i.test(r.type) === isSme && r.status === "Open" && r.sub && r.sub.total > 0 && r.gmpPct != null).map(r => ({ x: r.sub.total, y: r.gmpPct, name: r.name }));
    mcharts.c = new Chart($("#compChart"), { type: "scatter", data: { datasets: [{ label: `Listed ${segLbl} issues`, data: C.map(c => ({ x: c.total, y: c.ret, name: c.name })), backgroundColor: C.map(c => c.ret >= 0 ? up + "aa" : down + "aa"), pointRadius: 5, pointHoverRadius: 8 }, { label: "Open now (GMP-implied)", data: liveP, backgroundColor: acc, pointStyle: "rectRot", pointRadius: 9, pointHoverRadius: 12 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: text, boxWidth: 10 } }, tooltip: { callbacks: { title: it => it[0].raw.name, label: c => `Total ${c.raw.x}x → ${c.datasetIndex ? "GMP-implied " : "listed "}${pct(c.raw.y, true)}` } } }, scales: { x: { type: "logarithmic", title: { display: true, text: "Total subscription (x, log)", color: text }, ticks: { color: text }, grid: { color: grid } }, y: { title: { display: true, text: "Listing-day return", color: text }, ticks: { color: text, callback: v => v + "%" }, grid: { color: grid } } } } });
    const cseg = SEG(isSme), ed = EDG("total"), tb = cseg ? cseg.bands.total.all : null;
    $("#compBins").innerHTML = (tb ? tb.map((s, i) => `<div class="bin ${binCls(s)}" title="${evLong(s)}"><div class="v mono">${s.n ? pct(s.med, true) : "—"}</div><div class="l">${edgeLbl(ed, i, "x")} · ${s.n ? s.n + " issues" : "none"}</div></div>`).join("") : `<div class="dim">Evidence not yet computed.</div>`)
      + `<div class="dim" style="grid-column:1/-1;font-size:12px">${segLbl}, all years · median listing gain by total subscription. ${liveP.length ? "Diamonds are today's open " + segLbl + " books at their GMP-implied return — one far above the cloud for its book is froth." : "No open " + segLbl + " book yet."}</div>`;
    // flows
    const Fh = DATA.flows || {}, H = (Fh.history || []).slice(-20); let run = 0; const cum = H.map(r => (run += (r[1] || 0) + (r[2] || 0)));
    mcharts.f = new Chart($("#flowsChart2"), { data: { labels: H.map(r => fmtD(r[0])), datasets: [
        { type: "line", label: "Cumulative FII + DII", data: cum, borderColor: lav, backgroundColor: lav + "22", fill: true, borderWidth: 2, pointRadius: 0, tension: .25, yAxisID: "y1", order: 0 },
        { type: "bar", label: "FII net", data: H.map(r => r[1]), backgroundColor: H.map(r => r[1] >= 0 ? up : down), borderRadius: 3, maxBarThickness: 16, order: 1 },
        { type: "bar", label: "DII net", data: H.map(r => r[2]), backgroundColor: acc + "aa", borderRadius: 3, maxBarThickness: 16, order: 1 }] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, plugins: { legend: { position: "bottom", labels: { color: text, boxWidth: 10 } }, tooltip: { callbacks: { label: c => `${c.dataset.label}: ${sgn(Math.round(c.raw))} Cr` } } },
        scales: { x: { type: "category", ticks: { color: text, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } }, y: { type: "linear", title: { display: true, text: "₹ Cr a day", color: text }, ticks: { color: text }, grid: { color: grid } }, y1: { type: "linear", position: "right", title: { display: true, text: "cumulative ₹ Cr", color: text }, ticks: { color: text }, grid: { display: false } } } } });
  } else { $("#compBins").innerHTML = ""; }
  // anchor x-ray — fetched fields only: book sizes from `anchors` (details), the largest anchor investors from `players`
  const hbar = (rows, max, fmt, col) => rows.map(r => `<div class="hb"><div class="n" title="${esc(r.n)}">${esc(r.n)}${r.s ? `<small>${esc(r.s)}</small>` : ""}</div><div class="bar"><i class="${col ? col(r) : ""}" style="width:${Math.max(2, r.v / max * 100)}%"></i></div><div class="v num">${fmt(r.v)}</div></div>`).join("");
  const ab = (DATA.anchors || []).filter(x => x.amountCr).map(x => ({ n: x.name, v: x.amountCr, s: [x.issueSizeCr ? Math.round(x.amountCr / x.issueSizeCr * 100) + "% of issue" : "", x.lockIn30 ? "lock-in ends " + fmtD(x.lockIn30) : ""].filter(Boolean).join(" · ") })).sort((x, y) => y.v - x.v).slice(0, 12);
  $("#anchorBars").innerHTML = ab.length ? hbar(ab, ab[0].v, v => cr(v)) : `<div class="dim" style="font-size:12.5px">No anchor books on file.</div>`;
  const lg = ((DATA.players || {}).league || []).filter(x => x.investedCr).map(x => ({ n: x.name, v: x.investedCr, s: `${x.ipos} IPOs · average cheque ${x.ticketCr != null ? cr(x.ticketCr) : "—"}` })).sort((x, y) => y.v - x.v).slice(0, 15);
  $("#anchorFreq").innerHTML = lg.length ? hbar(lg, lg[0].v, v => cr(v), () => "lav") : `<div class="dim" style="font-size:12.5px">The anchor-investor list has not been read yet.</div>`;
  // SME screener — sortable table. Track record and EV are the collector's own evidence.segments.sme bands, never a
  // page-side score: this used to combine QIB depth, demand ratio and GMP level into one invented 0-100 "Score" and an
  // "institution-backed / mixed signals / retail froth" verdict, which is exactly what the standing rule forbids
  // (evidence and both sides, never a verdict). Rebuilt 19 Sep 2026 to match the Board's own evidence cells.
  const order = { Open: 0, Closed: 1, Listed: 2, Upcoming: 3 };          // rows with a book first; unopened issues last
  const sbar = (v, k) => `<div class="tb"><div class="bar"><i class="${k}" style="width:${v == null ? 0 : Math.min(100, Math.log10(1 + v) / Math.log10(301) * 100)}%"></i></div><span class="num">${xx(v)}</span></div>`;
  const cols = [["name", "Issue"], ["status", "Status"], ["gmpPct", "GMP", 1], ["qib", "QIB", 1], ["retail", "Retail", 1], ["total", "Total", 1], ["track", "Track record", 1], ["ev", "EV / app", 1], ["listing", "Listing / est.", 1]];
  const smeSeg = SEG(true);
  const val = (r, k) => { if (k === "status") return order[r.status]; if (k === "track") { const T = evBand(smeSeg, "total", (r.sub || {}).total, "all"); return T && T.s.n ? T.s.pos : -1; } if (k === "ev") { const E = evOf(r, smeSeg); return E ? E.ev : -999; } if (["qib", "retail", "total"].includes(k)) return (r.sub || {})[k]; if (k === "listing") return r.listingGainPct != null ? r.listingGainPct : r.gmpPct; if (k === "name") return r.name; return r[k]; };
  const S2 = sme.slice().sort((x, y) => { const a = val(x, smeSort.k), b = val(y, smeSort.k); const d = a == null && b == null ? 0 : a == null ? 1 : b == null ? -1 : typeof a === "string" ? a.localeCompare(b) * smeSort.dir : (smeSort.k === "status" ? (a - b) : (b - a)) * smeSort.dir; return d || order[x.status] - order[y.status] || ((y.sub || {}).total || 0) - ((x.sub || {}).total || 0); });
  const colTip = { track: "Median listing gain of past SME issues at this book's total-subscription band, all years (evidence.segments.sme).", ev: "Chance of allotment × the gain GMP implies, less the cost of blocked money — see the Board for the full method." };
  $("#smeScreen").innerHTML = `<thead><tr>${cols.map(([k, l, r]) => `<th class="${r ? "r" : ""} srt${smeSort.k === k ? " on" : ""}" data-sort="${k}" title="${colTip[k] || ""}">${l}${smeSort.k === k ? (smeSort.dir === 1 ? " ▾" : " ▴") : ""}</th>`).join("")}</tr></thead><tbody>${S2.length ? S2.map(r => {
    const s = r.sub || {}, G = evBand(smeSeg, "gmp", r.gmpPct, "window"), T = evBand(smeSeg, "total", s.total, "all"), E = evOf(r, smeSeg);
    // QIB conviction, graded — not scored: how past SME issues at this same QIB-subscription level actually listed.
    // This is the one grade this screener keeps, because a fluff SME book usually shows up here first; it is real
    // n + a Wilson interval from evidence.segments.sme.bands.qib, not a blend of QIB/demand/GMP invented on the page.
    const Q = evBand(smeSeg, "qib", s.qib, "rows"), qYears = (smeSeg && smeSeg.bands.qib.years || []).join(", ");
    const lc = lotCost(r), head = `<td><div class="nm"><button data-open="${esc(r.name)}">${esc(r.name)}</button></div><div class="dt">${esc(r.type)}${r.issueSizeCr ? " · " + cr(r.issueSizeCr) : ""}</div></td>`;
    // before the book opens there is no QIB / retail / total / track record / EV to show: say what IS known in one cell
    if (r.status === "Upcoming" && s.total == null) return `<tr data-row data-name="${esc(r.name)}">${head}<td><span class="pill upcoming">Upcoming</span><div class="dt">opens ${fmtD(r.open)} · ${rel(days(r.open))}</div></td>
      <td class="r num">${r.gmpPct ? (G ? `<span class="ev ${evCls(G.s)}" title="GMP ${G.lbl}: ${evLong(G.s)}">${pct(r.gmpPct, true)}</span>` : pct(r.gmpPct, true)) : `<span class="dim">no quote yet</span>`}</td>
      <td colspan="5"><div class="prebook">${[r.bandHigh != null ? `<span><b>${r.bandLow != null && r.bandLow !== r.bandHigh ? inr(r.bandLow) + "–" : ""}${inr(r.bandHigh)}</b> band</span>` : "", r.lotSize ? `<span><b>${r.lotSize}</b> shares a lot</span>` : "", lc ? `<span><b>${inr0(lc * 2)}</b> minimum application (2 lots)</span>` : "", r.close ? `<span>closes <b>${fmtD(r.close)}</b></span>` : "", r.listing ? `<span>lists <b>${fmtD(r.listing)}</b></span>` : ""].filter(Boolean).join("") || "details awaited"}</div></td>
      <td class="r num">${r.gmpPct ? `<span class="dim">est.</span> ${pct(r.gmpPct, true)}` : `<span class="dim">—</span>`}</td></tr>`;
    return `<tr data-row data-name="${esc(r.name)}"><td><div class="nm"><button data-open="${esc(r.name)}">${esc(r.name)}</button></div><div class="dt">${esc(r.type)}${r.issueSizeCr ? " · " + cr(r.issueSizeCr) : ""}</div></td>
    <td><span class="pill ${r.status.toLowerCase()}">${r.status}</span><div class="dt">${r.status === "Upcoming" ? "opens " + fmtD(r.open) : r.status === "Open" ? "closes " + fmtD(r.close) : "lists " + fmtD(r.listing)}</div></td>
    <td class="r num">${G ? `<span class="ev ${evCls(G.s)}" title="GMP ${G.lbl}: ${evLong(G.s)}">${pct(r.gmpPct, true)}</span>` : pct(r.gmpPct, true)}</td>
    <td class="r">${sbar(s.qib, "qb")}${Q && Q.s.n ? `<div class="dt"><span class="ev ${evCls(Q.s)}" title="QIB ${Q.lbl}, ${qYears} books only: ${evLong(Q.s)}">${Math.round(Q.s.pos)}% listed positive</span></div>` : s.qib != null ? `<div class="dt dim">too few QIB cases in this band</div>` : ""}</td>
    <td class="r">${sbar(s.retail, "rt")}</td><td class="r">${sbar(s.total, "")}</td>
    <td class="r">${T && T.s.n ? `<span class="ev ${evCls(T.s)}" title="Total book ${T.lbl}, all years: ${evLong(T.s)}">${Math.round(T.s.pos)}%</span>` : `<span class="dim">—</span>`}</td>
    <td class="r">${E ? `<span class="num ${cls(E.ev)}" title="${colTip.ev} Range ${pct(E.lo, true)} to ${pct(E.hi, true)}.">${pct(E.ev, true)}</span>` : `<span class="dim">${r.status === "Listed" ? "listed" : s.retail == null ? "book not open" : "no GMP quote"}</span>`}</td>
    <td class="r num ${cls(r.listingGainPct != null ? r.listingGainPct : null)}">${r.listingPrice != null ? inr(r.listingPrice) + " · " + pct(r.listingGainPct, true) : r.gmpPct != null ? `<span class="dim">est.</span> ${pct(r.gmpPct, true)}` : "—"}</td></tr>`;
  }).join("") : `<tr><td colspan="9" class="empty">No SME issues on the board.</td></tr>`}</tbody>`;
  // flow kpis + context
  const F = DATA.flows || {}, L = F.latest;
  $("#flowsSub2").textContent = L ? `latest ${fmtD(L.date)}${L.source ? " · " + L.source : ""}` : "";
  const P0 = (L && L.previousDay) || {}, gross = (b1, s1) => b1 != null && s1 != null ? `bought ${inr0(b1)} · sold ${inr0(s1)} Cr` : "";
  $("#flowKpis").innerHTML = L ? [["FII net", L.fiiNetCr, P0.fiiNetCr, gross(L.fiiBuyCr, L.fiiSellCr)], ["DII net", L.diiNetCr, P0.diiNetCr, gross(L.diiBuyCr, L.diiSellCr)], ["Combined", (L.fiiNetCr || 0) + (L.diiNetCr || 0), P0.fiiNetCr != null ? (P0.fiiNetCr || 0) + (P0.diiNetCr || 0) : null, "the two biggest pools together"]]
    .map(([l, v, was, d2]) => `<div class="kpi card"><div class="lbl">${l} · ${fmtD(L.date)}</div><div class="v mono ${cls(v)}">${sgn(Math.round(v))} Cr</div><div class="d">${was != null ? `previous session ${sgn(Math.round(was))} Cr` : ""}${d2 ? `<br>${d2}` : ""}</div></div>`).join("") : "";
  $("#flowCtx").innerHTML = flowContext(F.history || []);
  $("#flowNoteWrap").hidden = true;                     // `flows.note` is db-era prose nobody refreshes; the card's header names the live source
  // ===== smart money: anchor cards =====
  const curIss = allIssues().filter(b => b.status === "Open" || b.status === "Upcoming" || (b.status === "Closed" && days(b.listing) >= 0));
  const WL = watchNames();
  const PL = playerCards(curIss); { const pn = $("#playersNote"); if (pn) pn.textContent = playersNote(); }
  const pending = curIss.filter(b => !PL.named.has(b.name));
  $("#anchorCards").innerHTML = (PL.html + (pending.length ? `<div class="card acard pend" style="grid-column:1/-1;display:block"><div class="lbl" style="margin-bottom:6px">None of the largest anchors seen in these books · size and lock-in dates</div><div class="chips" style="margin-top:0">${pending.map(b => { const A1 = anchorFor(b.name), f = A1 ? [A1.amountCr ? cr(A1.amountCr) : null, A1.amountCr && A1.issueSizeCr ? Math.round(A1.amountCr / A1.issueSizeCr * 100) + "% of issue" : null, A1.lockIn30 ? "lock-in ends " + fmtD(A1.lockIn30) + " / " + fmtD(A1.lockIn90) : null].filter(Boolean).join(" · ") : ""; return `<span class="chip-i" data-row data-name="${esc(b.name)}"><b>${esc(b.name)}</b>${f ? " " + f : " · no anchor book on file"}</span>`; }).join("")}</div></div>` : "")) || `<div class="empty">No current issues.</div>`;
  // ===== superinvestors ===== (bulk deals are live; the rest is the retired sweep's snapshot and sits in a closed archive)
  { const sn = $("#invSnap"); if (sn) sn.textContent = (DATA.investors || {}).asOf ? "of " + fmtDY(DATA.investors.asOf) : ""; }
  const I = DATA.investors || {}, worthOf = s => { const m = /([\d,.]+)\s*(Cr|crore)/i.exec(s || ""); return m ? parseFloat(m[1].replace(/,/g, "")) : null; };
  const isBuy = t => /fresh|add|buy|bought|raised|bulk buy/i.test(t) && !/exit|trim|sold/i.test(t), isSell = t => /exit|trim|sold|sell|cut|reduced|below/i.test(t);
  const dir = t => { const m = /([\d.]+)\s*%?\s*(?:→|->|to)\s*([\d.]+)/.exec(t); if (m) return +m[2] > +m[1] ? "up" : "down"; return isBuy(t) ? "up" : isSell(t) ? "down" : ""; };
  const kind = m => isBuy(m.action) ? "up" : isSell(m.action) ? "down" : "lav";
  const actLbl = t => /fresh/i.test(t) ? "fresh" : /bulk/i.test(t) ? "bulk buy" : /add/i.test(t) ? "add" : /trim/i.test(t) ? "trim" : /exit/i.test(t) ? "exit" : t.toLowerCase();
  const ret = m => m.priceAtDisclosure && m.priceNow ? (m.priceNow - m.priceAtDisclosure) / m.priceAtDisclosure * 100 : null;
  const invOf = s => WL.find(w => norm2(s).startsWith(norm2(w.split(" (")[0]))) || s.split(" (")[0];
  // the collector prices these stocks every run (investors.prices); the sweep's own quote is only a fallback
  const livePx = m => { const p = (I.prices || {})[m.stock]; return p && p.value != null && String(p.asOf || "") >= String(m.priceAsOf || "") ? { priceNow: p.value, priceAsOf: p.asOf } : {}; };
  const moves = (I.moves || []).map(m => { const x = { ...m, ...livePx(m) }; return { ...x, inv: invOf(m.investor), r: ret(x), k: kind(m) }; });
  const deals = (I.bulkDeals || []).map(d => ({ ...d, inv: invOf(d.investor) }));
  const lst = store.get("ipo-investors", { add: [], remove: [] }) || { add: [], remove: [] };
  $("#watchlist").innerHTML = WL.map(w => `<span class="chip-i${(I.watchlist || []).includes(w) ? "" : " local"}" title="${(I.watchlist || []).includes(w) ? "tracked by the daily sweep" : "added here — ask Claude to add to the sweep"}">${esc(w)}<button data-rm="${esc(w)}" title="Remove">✕</button></span>`).join("") + `<input type="text" id="wlIn" placeholder="Add an investor…"><button class="btn sm" id="wlAdd">Add</button>`;
  $("#wlAdd").onclick = () => { const v = $("#wlIn").value.trim(); if (!v) return; lst.add = [...new Set([...(lst.add || []), v])]; lst.remove = (lst.remove || []).filter(x => x !== v); store.set("ipo-investors", lst); toast(`${v} added — tell Claude to include them in the morning sweep`); renderMarket(); };
  $("#wlIn").onkeydown = e => { if (e.key === "Enter") $("#wlAdd").click(); };
  $$("#watchlist [data-rm]").forEach(b => b.onclick = () => { const v = b.dataset.rm; lst.add = (lst.add || []).filter(x => x !== v); if ((I.watchlist || []).includes(v)) lst.remove = [...new Set([...(lst.remove || []), v])]; store.set("ipo-investors", lst); renderMarket(); });
  const wmax = Math.max(1, ...(I.portfolios || []).map(p => worthOf(p.worth) || 0));
  $("#portfolios").innerHTML = WL.map(w => { const p = (I.portfolios || []).find(x => x.name === w) || { name: w }; const mm = moves.filter(m => m.inv === w), buys = mm.filter(m => m.k === "up" && m.r != null), sells = mm.filter(m => m.k === "down" && m.r != null); const avgB = buys.length ? avg(buys.map(m => m.r)) : null, hit = buys.length ? Math.round(buys.filter(m => m.r > 0).length / buys.length * 100) : null, avoided = sells.length ? -avg(sells.map(m => m.r)) : null; const dd = deals.filter(d => d.inv === w); const wv = worthOf(p.worth);
    return `<div class="p"><b>${esc(p.name)}</b> <span class="dim mono" style="font-size:11.5px">${p.worth ? esc(p.worth) : ""}${p.stocks ? " · " + p.stocks + " stocks" : ""}</span>${wv ? `<div class="wb"><i style="width:${wv / wmax * 100}%"></i></div>` : ""}<div class="s">${esc(p.style || "Not yet in the sweep — no filings pulled.")}</div>
      <div class="tr"><div><div class="v mono ${cls(avgB)}">${avgB == null ? "—" : pct(avgB, true)}</div><div class="l">avg since buys (${buys.length})</div></div><div><div class="v mono ${hit == null ? "dim" : hit >= 60 ? "up" : hit >= 40 ? "amb" : "down"}">${hit == null ? "—" : hit + "%"}</div><div class="l">buys up so far</div></div><div><div class="v mono ${cls(avoided)}">${avoided == null ? "—" : pct(avoided, true)}</div><div class="l">avoided on exits (${sells.length})</div></div></div>
      ${mm.length ? `<div class="rc">${mm.map(m => `<span class="${m.k === "lav" ? "" : m.k}" title="${esc(m.detail || "")}${m.priceAtDisclosure ? " · " + inr(m.priceAtDisclosure) + " → " + inr(m.priceNow) : ""}">${esc(m.stock.length > 22 ? m.stock.slice(0, 21) + "…" : m.stock)} ${esc(actLbl(m.action))}${m.r != null ? `<b class="num">${pct(m.r, true)}</b>` : ""}</span>`).join("")}</div>` : ""}
      ${dd.length ? `<div class="bd">${dd.map(d => `<b>${d.side}</b> ${esc(d.stock)} ${d.valueCr ? cr(d.valueCr) : ""} · ${fmtD(d.date)}`).join(" · ")}</div>` : ""}
      ${p.read ? `<div class="rd r">${esc(p.read)}</div><button class="tgl" data-pf="${esc(w)}">Read the quarter ▾</button>` : ""}</div>`; }).join("") || `<div class="empty">No investors tracked.</div>`;
  $$("#portfolios .tgl").forEach(b => b.onclick = () => { const p = b.closest(".p"); p.classList.toggle("open"); b.textContent = p.classList.contains("open") ? "Hide ▴" : "Read the quarter ▾"; });
  // bulk deals + insiders
  $("#bulkDeals").innerHTML = `<thead><tr><th>Date</th><th>Investor</th><th>Stock</th><th>Side</th><th class="r">Qty</th><th class="r">Price</th><th class="r">Value</th></tr></thead><tbody>${deals.slice().sort((x, y) => (y.date || "").localeCompare(x.date || "")).map(d => `<tr><td class="dt" style="white-space:nowrap">${fmtD(d.date)}</td><td class="nm">${esc(d.inv)}<div class="dt">${esc((d.vehicle || "").slice(0, 40))}</div></td><td>${d.source ? `<a href="${esc(d.source)}" target="_blank" rel="noopener">${esc(d.stock)}</a>` : esc(d.stock)}</td><td><span class="pill ${d.side === "BUY" ? "ok" : "now"}">${esc(d.side)}</span></td><td class="r num">${d.qty ? d.qty.toLocaleString("en-IN") : "—"}</td><td class="r num">${d.price ? inr(d.price) : "—"}</td><td class="r num">${d.valueCr ? cr(d.valueCr) : "—"}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">No bulk or block deals by tracked names in the window.</td></tr>`}</tbody>`;
  renderListingDeals();
  $("#insiders").innerHTML = `<thead><tr><th>Parent</th><th>Who</th><th>Action</th><th class="r">Value</th><th>Note</th></tr></thead><tbody>${(I.insiders || []).slice().sort((x, y) => (y.date || "").localeCompare(x.date || "")).map(x => `<tr><td class="nm">${esc(x.parent)}<div class="dt">${fmtD(x.date)}</div></td><td class="dt">${esc(x.who)}<div>${esc(x.role || "")}</div></td><td><span class="pill ${x.side === "BUY" ? "ok" : x.side === "SELL" || x.side === "OFS" ? "now" : "soon"}">${esc(x.side)}</span></td><td class="r num" style="white-space:nowrap">${x.valueCr ? cr(x.valueCr) : "—"}</td><td class="dt" title="${esc(x.note || "")}">${esc((x.note || "").replace(/^OUTSIDE 60-day window \(context only\)\.\s*/i, "").slice(0, 150))}${(x.note || "").length > 150 ? "…" : ""}${/OUTSIDE 60-day/i.test(x.note || "") ? ` <span class="pill plan" style="height:17px;font-size:10.5px">context</span>` : ""}${x.source ? ` <a href="${esc(x.source)}" target="_blank" rel="noopener">↗</a>` : ""}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">No insider or promoter actions found in the quota parents.</td></tr>`}</tbody>`;
  // overlap + sector tilt
  const HD = (I.holdings || []).map(h => ({ ...h, inv: invOf(h.investor) })).filter(h => WL.includes(h.inv));
  const byStock = {}; HD.forEach(h => (byStock[h.stock] = byStock[h.stock] || []).push(h));
  const ov = Object.entries(byStock).filter(([, hs]) => new Set(hs.map(h => h.inv)).size >= 2).sort((x, y) => y[1].length - x[1].length);
  $("#overlap").innerHTML = ov.length ? `<div class="ov">${ov.map(([s, hs]) => `<div class="o"><div class="n">${esc(s)}<div class="dt">${esc(hs[0].sector || "")}${hs[0].listedDate ? " · listed " + fmtD(hs[0].listedDate) : ""}</div></div><div class="hs">${[...new Map(hs.map(h => [h.inv, h])).values()].map(h => `<span>${esc(h.inv.split(" ")[0])} ${h.pct != null ? h.pct + "%" : ""}</span>`).join("")}</div></div>`).join("")}</div>` : `<div class="dim" style="font-size:12.5px">No stock is held above 1% by two tracked names in the captured holdings (${HD.length} positions). Overlap appears as the sweep fills more portfolios.</div>`;
  const GROUPS = ["Financials", "Industrials", "Pharma / Health", "Consumer", "Chemicals", "Tech / IT", "Infra / Construction", "Energy / Power", "Other"];
  const tilt = WL.map(w => { const hs = HD.filter(h => h.inv === w); const c = {}; hs.forEach(h => c[h.sectorGroup || "Other"] = (c[h.sectorGroup || "Other"] || 0) + 1); return { w, n: hs.length, c }; }).filter(t => t.n);
  $("#sectorTilt").innerHTML = tilt.length ? tilt.map(t => `<div class="hb"><div class="n">${esc(t.w)}<small>${t.n} holdings</small></div><div class="bar">${GROUPS.map((g, gi) => t.c[g] ? `<i class="s${gi}" style="width:${t.c[g] / t.n * 100}%" title="${g}: ${t.c[g]}"></i>` : "").join("")}</div><div class="v num">${Object.entries(t.c).sort((x, y) => y[1] - x[1])[0][0].split(" ")[0]}</div></div>`).join("") + `<div class="slegend">${GROUPS.map((g, gi) => `<span><i class="s${gi}" style="display:inline-block"></i>${g}</span>`).join("")}</div>` : `<div class="dim">No holdings captured.</div>`;
  // smart money in recent listings
  const RL = (I.recentListings || []).filter(r => WL.some(w => norm2(r.investor || "").includes(norm2(w.split(" ")[0]))) || /pre-IPO|post-listing/i.test(r.how || "") || /singularity|rare|abakkus|kedia|kacholia|khanna|kela|agrawal|jhunjhunwala/i.test(r.investor || ""));
  $("#smartRecent").innerHTML = `<thead><tr><th>Stock</th><th>Listed</th><th>Investor</th><th>How</th><th class="r">Stake</th></tr></thead><tbody>${RL.slice().sort((x, y) => (y.listedDate || "").localeCompare(x.listedDate || "")).map(r => `<tr><td class="nm">${r.source ? `<a href="${esc(r.source)}" target="_blank" rel="noopener">${esc(r.stock)}</a>` : esc(r.stock)}${r.note ? `<div class="dt" title="${esc(r.note)}">${esc(r.note.slice(0, 70))}${r.note.length > 70 ? "…" : ""}</div>` : ""}</td><td class="dt">${fmtD(r.listedDate)}</td><td>${esc(r.investor)}</td><td><span class="pill ${r.how === "anchor" ? "ok" : r.how === "pre-IPO" ? "plan" : "soon"}">${esc(r.how || "")}</span></td><td class="r num">${r.pct != null ? r.pct + "%" : "—"}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">No tracked names found inside 2026 listings yet.</td></tr>`}</tbody>`;
  $("#moves").innerHTML = `<thead><tr><th>Investor</th><th>Stock</th><th>Action</th><th class="r">Since</th><th>Detail</th></tr></thead><tbody>${moves.map(m => `<tr><td class="nm">${esc(m.inv)}</td><td>${esc(m.stock)}<div class="dt">${esc(m.when || "")}</div></td><td><span class="pill ${m.k === "up" ? "ok" : m.k === "down" ? "now" : "plan"}">${esc(m.action)}</span></td><td class="r num ${cls(m.r)}">${m.r == null ? "—" : pct(m.r, true)}${m.priceNow && m.priceAtDisclosure ? `<div class="dt" style="white-space:nowrap">${inr(m.priceAtDisclosure)} → ${inr(m.priceNow)}</div>` : m.priceNow ? `<div class="dt">now ${inr(m.priceNow)}</div>` : ""}</td><td class="dt">${esc(m.detail || "")}</td></tr>`).join("") || `<tr><td class="empty" colspan="5">No moves captured.</td></tr>`}</tbody>`;
  $("#invNotes").innerHTML = (I.notes || []).map(esc).join("<br>"); $("#invNotesWrap").hidden = !(I.notes || []).length;
  // expected pipeline — sized bars + TBA chips
  const E = DATA.expected || [], Es = E.filter(e => e.sizeCr).sort((x, y) => y.sizeCr - x.sizeCr), Et = E.filter(e => !e.sizeCr);
  $("#expWrap").style.height = Math.max(120, 30 * Es.length + 40) + "px";
  // an earlier render with no sized names (the built-in snapshot has none) replaced the canvas with a message
  if (Es.length && !$("#expChart")) $("#expWrap").innerHTML = `<canvas id="expChart"></canvas>`;
  if (typeof Chart !== "undefined" && Es.length) mcharts.e = new Chart($("#expChart"), { type: "bar", data: { labels: Es.map(e => { const n = e.name.split(" (")[0]; return n.length > 22 ? n.slice(0, 21) + "…" : n; }), datasets: [{ label: "Expected size ₹Cr", data: Es.map(e => e.sizeCr), backgroundColor: Es.map(e => /sept|sep 2026|this month/i.test(e.window || "") ? acc : lav), borderRadius: 4, maxBarThickness: 18 }] }, options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => Es[it[0].dataIndex].name, label: c => cr(c.raw), afterLabel: c => { const e = Es[c.dataIndex]; return [e.window ? "Window: " + e.window : "", e.stage || "", e.note || ""].filter(Boolean).join("\n"); } } } }, scales: { x: { ticks: { color: text, callback: v => "₹" + (v >= 1000 ? (v / 1000).toFixed(0) + "k" : v) + " Cr" }, grid: { color: grid } }, y: { ticks: { color: text, font: { size: 11 } }, grid: { display: false } } } } });
  else $("#expWrap").innerHTML = `<div class="empty">No sized names captured.</div>`;
  $("#expTba").innerHTML = `<span class="acc" style="cursor:default"><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:var(--accent)"></i> September window</span><span class="plan" style="cursor:default"><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:var(--lav)"></i> later / TBD</span>` + Et.map(e => `<span title="${esc([e.window, e.stage, e.note].filter(Boolean).join(" · "))}">${esc(e.name)} <b class="dim">${esc(e.sizeText || "size TBA")}</b></span>`).join("");
  // news — date badges
  $("#news").innerHTML = `<div class="newsl">${(DATA.news || []).map(n => `<a href="${esc(n.url || "#")}" target="_blank" rel="noopener"><span class="db">${n.date ? fmtD(n.date) : "—"}</span>${esc(n.title)}</a>`).join("") || `<div class="empty">No headlines captured.</div>`}</div>`;
  // integrity — status bar + chips
  const G = DATA.integrity || {}; $("#intAsOf").textContent = G.asOf ? "checked " + fmtDY(G.asOf) : "";
  const ck = G.checks || [], nOk = ck.filter(c => c.status === "ok").length, nW = ck.filter(c => c.status === "warn").length, nS = ck.length - nOk - nW;
  $("#intBar").innerHTML = ck.length ? [["ok", nOk], ["warn", nW], ["single", nS]].filter(([, n]) => n).map(([k, n]) => `<i class="${k}" style="flex:${n}" title="${n} ${k}"></i>`).join("") : "";
  $("#intChips").innerHTML = ck.map(c => `<span class="${c.status === "ok" ? "ok" : c.status === "warn" ? "bad" : "warn"}" title="${esc(c.note || "")}">${c.status === "ok" ? "✓" : c.status === "warn" ? "!" : "○"} ${esc(c.area)}</span>`).join("") + (ck.length ? `<span style="background:transparent;color:var(--ink-3)">${nOk} cross-checked · ${nW} flagged · ${nS} single-source</span>` : "");
  $("#intDisc").innerHTML = (G.discrepancies || []).length ? `<div class="lbl" style="margin-bottom:2px">Where sources disagree</div><div class="discs">${G.discrepancies.map(x => `<div class="disc">${esc(x)}</div>`).join("")}</div>` : "";
  $("#integrity").innerHTML = `<thead><tr><th>Area</th><th>Method</th><th>Status</th><th>Finding</th></tr></thead><tbody>${ck.map(c => `<tr><td class="nm">${esc(c.area)}</td><td class="dt">${esc(c.method || "")}</td><td><span class="pill ${c.status === "ok" ? "ok" : c.status === "warn" ? "now" : "soon"}">${esc(c.status === "ok" ? "cross-checked" : c.status === "warn" ? "flagged" : "single source")}</span></td><td class="dt">${esc(c.note || "")}</td></tr>`).join("")}</tbody>`;
  $("#c-market").textContent = (G.discrepancies || []).length || "";
}
/* ---------- position charts (Book) ---------- */
let pcharts = [];
function drawPosCharts() {
  pcharts.forEach(c => c.destroy()); pcharts = [];
  const held = S.apps.filter(a => a.status === "Allotted — holding"); const el = $("#posCharts");
  if (!held.length) { el.innerHTML = `<div class="card empty" style="grid-column:1/-1">Charts appear here for allotted holdings, drawn from the daily price points.</div>`; return; }
  el.innerHTML = held.map((a, i) => { const ph = (DATA.priceHistory || {})[a.name] || []; return `<div class="card"><div class="ch">${esc(a.name)}<span class="sub">${ph.length} point${ph.length === 1 ? "" : "s"} · bought ${inr(a.price)}</span></div><div class="cb">${ph.length > 1 ? `<div class="chart-wrap" style="height:160px"><canvas id="pc${i}"></canvas></div>` : `<div class="dim" style="font-size:12.5px">${ph.length ? "One price point so far (" + inr(ph[0][1]) + " on " + fmtD(ph[0][0]) + ") — the line draws itself from tomorrow." : "No price points yet."}</div>`}</div></div>`; }).join("");
  if (typeof Chart === "undefined") return;
  held.forEach((a, i) => { const ph = (DATA.priceHistory || {})[a.name] || []; if (ph.length < 2) return; pcharts.push(new Chart($("#pc" + i), { type: "line", data: { labels: ph.map(p => fmtD(p[0])), datasets: [{ label: "Price", data: ph.map(p => p[1]), borderColor: tok("--accent"), backgroundColor: tok("--accent") + "22", fill: true, tension: .3, pointRadius: 3 }, { label: "Your cost", data: ph.map(() => a.price), borderColor: tok("--ink-3"), borderDash: [4, 4], pointRadius: 0 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: tok("--chart-text") }, grid: { display: false } }, y: { ticks: { color: tok("--chart-text") }, grid: { color: tok("--chart-grid") } } } } })); });
}

/* ================= TAPE ================= */
function renderTape() {
  const t = [];
  board.filter(b => b.status === "Open").forEach(b => t.push(`<span class="t"><b>${esc(b.name.split(" ")[0].toUpperCase())}</b><span class="${cls(b.gmpPct)} num">${pct(b.gmpPct, true)}</span><span class="dim">closes ${fmtD(b.close)}</span></span>`));
  board.filter(b => b.status === "Closed").slice(0, 2).forEach(b => t.push(`<span class="t"><b>${esc(b.name.split(" ")[0].toUpperCase())}</b><span class="${cls(b.gmpPct)} num">${pct(b.gmpPct, true)}</span><span class="dim">lists ${fmtD(b.listing)}</span></span>`));
  const F = DATA.flows && DATA.flows.latest; if (F) t.push(`<span class="t"><b>FII</b><span class="${cls(F.fiiNetCr)} num">${sgn(F.fiiNetCr)}</span><b>DII</b><span class="${cls(F.diiNetCr)} num">${sgn(F.diiNetCr)}</span><span class="dim">${fmtD(F.date)}</span></span>`);
  const rec = live.filter(q => q.recordDate).sort((a, b) => a.recordDate.localeCompare(b.recordDate))[0];
  t.push(rec ? `<span class="t"><b>NEXT RECORD DATE</b><span class="down">${esc(rec.name)} · ${fmtD(rec.recordDate)}</span></span>` : `<span class="t"><b>NEXT RECORD DATE</b><span class="amb">Jio — with its RHP</span></span>`);
  $("#tape").innerHTML = t.join("") + `<span class="asof${stale ? " stale" : ""}" title="Collector run of ${esc(DATA.meta.label)} — tap to check now"><i class="livedot"></i><span id="liveTxt"></span></span><a class="runnow" href="https://github.com/harimano/ipo-desk/actions/workflows/collect.yml" target="_blank" rel="noopener" title="Open the collector on GitHub and press Run workflow. This page then watches for the new data for a few minutes.">Run ↗</a>`;
}

/* ================= COMMAND BAR ================= */
const cmdEl = $("#cmd"), cmdIn = $("#cmdIn"), cmdList = $("#cmdList"); let cmdSel = 0, cmdItems = [];
function catalog() {
  const items = [];
  live.forEach(q => items.push({ k: sheets[q.name] ? "SHEET" : "PIPE", t: q.name, h: `${q.parent} · ${q.stage}${sheets[q.name] ? " · ⏎ sheet" : ""}`, run: () => { if (sheets[q.name]) openSheet(q.name); else { show("pipe"); openPipe(q.name); } }, keys: [q.name, q.parent, q.ticker || ""] }));
  live.filter(q => sheets[q.name]).forEach(q => items.push({ k: "PIPE", t: q.name + " on the map", h: q.parent, run: () => { show("pipe"); openPipe(q.name); }, keys: [q.name, q.parent] }));
  allIssues().forEach(b => items.push({ k: b.type.includes("SME") ? "SME" : "IPO", t: b.name, h: `${b.status}${b.gmpPct != null ? " · GMP " + pct(b.gmpPct, true) : ""}`, run: () => openSheet(b.name), keys: [b.name] }));
  [["today", "Today"], ["pipe", "Pipeline"], ["board", "Board"], ["market", "Market"], ["research", "Research"], ["book", "Book"]].forEach(([s, l]) => items.push({ k: "GO", t: l, h: "screen", run: () => show(s), keys: [l, s] }));
  [["light", "Light theme"], ["dark", "Dark theme"], [null, "Auto theme (follow system)"]].forEach(([v, l]) => items.push({ k: "SET", t: l, h: "", run: () => setTheme(v), keys: [l, l.split(" ")[0], v === "dark" ? "night" : ""] }));
  return items;
}
const norm = s => s.toLowerCase().replace(/[^a-z0-9 ]/g, "");
function parseCmd(raw) {
  const s = raw.trim(); if (!s) return null; const parts = s.split(/\s+/), verb = parts[0].toUpperCase(), rest = parts.slice(1).join(" ");
  const findQ = n => live.find(q => norm(q.name).startsWith(norm(n)) || norm(q.parent).startsWith(norm(n)) || (q.ticker || "").toLowerCase() === n.toLowerCase());
  const findB = n => allIssues().find(b => norm(b.name).startsWith(norm(n)));
  if (verb === "HOLD" && rest) { const q = findQ(rest); const p = q ? q.parent : rest; return { k: "HOLD", t: `${held(p) ? "Remove" : "Mark held"}: ${p}`, h: q ? "covers " + q.name : "parent short name", run: () => { toggleHold(p); toast(held(p) ? "Holding " + p : "Removed " + p); renderAll(); } }; }
  if ((verb === "STAR" || verb === "*") && rest) { const q = findQ(rest) || findB(rest); if (!q) return null; return { k: "STAR", t: `${S.interest.has(q.name) ? "Unstar" : "Star"}: ${q.name}`, h: "", run: () => { S.interest.has(q.name) ? S.interest.delete(q.name) : S.interest.add(q.name); save(); renderAll(); } }; }
  if (verb === "APP" && rest) { const m = rest.match(/^(.+?)(?:\s+(\d+))?(?:\s+(retail|shareholder|s-?hni|b-?hni|employee))?$/i); const b = m && findB(m[1]); if (!b) return null; const lots = +(m[2] || 1), cat = m[3] ? m[3].replace(/hni/i, "HNI").replace(/^s/i, "S-").replace(/^b/i, "B-").replace(/^(retail|shareholder|employee)$/i, x => x[0].toUpperCase() + x.slice(1).toLowerCase()).replace("S-S-", "S-").replace("B-B-", "B-") : "Retail"; const lc = lotCost(b); return { k: "APP", t: `Log ${lots} lot${lots > 1 ? "s" : ""} of ${b.name} · ${cat}`, h: lc ? inr0(lots * lc) + " at " + inr(b.bandHigh) : "band TBA", run: () => { S.apps.push({ name: b.name, cat, lots, price: b.bandHigh || 0, status: "Applied", sold: null, added: iso(today) }); save(); toast("Application logged"); renderAll(); show("book"); } }; }
  if (verb === "DONE" && rest) { const p = buildQueue().find(p => norm(p.ttl).includes(norm(rest))); if (!p) return null; return { k: "DONE", t: "Done: " + p.ttl, h: "", run: () => { S.done.add(p.id); save(); renderAll(); } }; }
  return null;
}
function openCmd(prefill) { cmdEl.hidden = false; cmdIn.value = prefill || ""; cmdIn.focus(); cmdFilter(); }
function closeCmd() { cmdEl.hidden = true; cmdIn.value = ""; }
function cmdFilter() {
  const q = cmdIn.value.trim(), n = norm(q); const parsed = parseCmd(q); const all = catalog();
  let list = !n ? all.filter(i => i.k !== "SET").slice(0, 12) : all.filter(i => i.keys.some(k => norm(k).includes(n))).sort((a, b) => (norm(a.t).startsWith(n) ? 0 : 1) - (norm(b.t).startsWith(n) ? 0 : 1)).slice(0, 12);
  cmdItems = parsed ? [parsed, ...list] : list; cmdSel = 0;
  cmdList.innerHTML = cmdItems.length ? cmdItems.map((i, ix) => `<div class="cmd-it${ix === 0 ? " sel" : ""}" data-ix="${ix}"><span class="k">${i.k}</span><span>${esc(i.t)}</span><span class="h">${esc(i.h || "")}</span></div>`).join("") : `<div class="cmd-it"><span class="k"></span><span class="dim">No match. Try a name, HOLD RELIANCE, STAR DEEPA, APP DEEPA 2 RETAIL, BOARD.</span><span></span></div>`;
}
cmdIn.addEventListener("input", cmdFilter);
cmdIn.addEventListener("keydown", e => {
  if (e.key === "Escape") { closeCmd(); e.preventDefault(); }
  else if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); cmdSel = (cmdSel + (e.key === "ArrowDown" ? 1 : -1) + cmdItems.length) % Math.max(1, cmdItems.length); $$(".cmd-it", cmdList).forEach((el, i) => el.classList.toggle("sel", i === cmdSel)); }
  else if (e.key === "Enter") { e.preventDefault(); const it = cmdItems[cmdSel]; if (it) { closeCmd(); it.run(); } }
});
cmdList.addEventListener("click", e => { const el = e.target.closest("[data-ix]"); if (el) { const it = cmdItems[+el.dataset.ix]; closeCmd(); it && it.run(); } });
cmdEl.addEventListener("click", e => { if (e.target === cmdEl) closeCmd(); });
$("#cmdOpen").onclick = () => openCmd();

/* ================= KEYBOARD ================= */
let cursor = -1;
const rows = () => $$(`#s-${screen} [data-row]`);
function setCursor(i) { const R = rows(); if (!R.length) return; cursor = (i + R.length) % R.length; R.forEach((r, j) => r.classList.toggle("cur", j === cursor)); R[cursor].scrollIntoView({ block: "nearest" }); }
document.addEventListener("keydown", e => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (!cmdEl.hidden) return;
  if (tag === "input" || tag === "select" || tag === "textarea") { if (e.key === "Escape") e.target.blur(); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (k === "/") { e.preventDefault(); openCmd(); return; }
  if (/^[1-7]$/.test(k)) { show(["today", "pipe", "board", "market", "research", "book", "score"][+k - 1]); return; }
  if (k === "j" || k === "ArrowDown") { e.preventDefault(); setCursor(cursor + 1); return; }
  if (k === "k" || k === "ArrowUp") { e.preventDefault(); setCursor(cursor - 1); return; }
  if (k === "Escape") { if (screen === "pipe" && pipeSel) { pipeSel = null; renderPipe(); } cursor = -1; rows().forEach(r => r.classList.remove("cur")); return; }
  if (k === "?") { toast("/ command · 1–6 screens · j/k move · ⏎ open · * star · h held · d done · s snooze · t theme"); return; }
  if (k === "t") { setTheme(isDark() ? "light" : "dark"); return; }
  const R = rows(), row = R[cursor]; if (!row) { if (k === "Enter" || k === "*" || k === "h" || k === "d" || k === "s") setCursor(0); return; }
  const name = row.dataset.name, id = row.dataset.id, q = Q.find(z => z.name === name);
  if (k === "Enter") { if (screen === "today") { if (q && sheets[q.name]) openSheet(q.name); else if (q) { show("pipe"); openPipe(q.name); } else if (name) openSheet(name); } else if (screen === "pipe") openPipe(name); else if (name) openSheet(name); }
  else if (k === "*") { if (!name) return; S.interest.has(name) ? S.interest.delete(name) : S.interest.add(name); save(); toast(S.interest.has(name) ? "Starred " + name : "Unstarred " + name); const c = cursor; renderAll(); setCursor(c); }
  else if (k === "h") { const p = q ? q.parent : Q.find(z => z.parent === name) ? name : null; if (!p) return; toggleHold(p); toast(held(p) ? "Holding " + p : "Removed " + p); const c = cursor; renderAll(); setCursor(c); }
  else if (k === "d" && id) { queueAct(id, "done", name); }
  else if (k === "s" && id) { queueAct(id, "snooze", name); }
});

/* ================= BOOT ================= */
/* ---------- Market: a sticky section bar. Sections are found, not listed: every .sec-h heading and top-level card title in the
   screen becomes a button, so a section added later shows up by itself. ---------- */
(function marketNav() {
  const nav = $("#mktNav"), scr = $("#s-market"); if (!nav || !scr) return;
  const heads = [...scr.querySelectorAll(".sec-h h2, [data-nav]")].filter(h => (h.dataset.nav || h.textContent).trim());
  const label = h => (h.dataset.nav || h.textContent).trim().replace(/^Market /, "").replace(/ on the board$/, "").replace(/^Data /, "");
  nav.innerHTML = heads.map((h, i) => `<button data-i="${i}">${esc(label(h).replace(/^./, c => c.toUpperCase()))}</button>`).join("");
  const hdrH = () => ($(".hdr") || {}).offsetHeight || 58, fit = () => { nav.style.top = hdrH() + "px"; };
  fit(); window.addEventListener("resize", fit); if (window.ResizeObserver && $(".hdr")) new ResizeObserver(fit).observe($(".hdr"));   // the header wraps on a phone
  const top = () => hdrH() + nav.offsetHeight + 10;
  nav.addEventListener("click", e => { const b = e.target.closest("button[data-i]"); if (!b) return; const y = heads[+b.dataset.i].getBoundingClientRect().top + window.scrollY - top(); window.scrollTo({ top: y, behavior: "smooth" }); });
  let tick = false; window.addEventListener("scroll", () => { if (tick || scr.hidden) return; tick = true; requestAnimationFrame(() => { tick = false; fit();
    let cur = 0; heads.forEach((h, i) => { if (h.getBoundingClientRect().top - top() <= 48) cur = i; });
    [...nav.children].forEach((b, i) => b.setAttribute("aria-current", String(i === cur))); const on = nav.children[cur]; if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest", inline: "nearest" }); }); }, { passive: true });
})();
/* @include hold.js */
/* @include quota.js */
/* @include players.js */
/* @include deals.js */
/* @include research.js */
/* @include scoreboard.js */
function renderAll() { renderTape(); renderToday(); renderPipe(); renderBoard(); renderBook(); if (screen === "score") renderScore(); }
$("#foot").innerHTML = `${esc(DATA.meta.quotaSourceNote || "")}${DATA.meta.marketNotes && DATA.meta.marketNotes.length ? "<br>" + DATA.meta.marketNotes.map(esc).join("<br>") : ""}${DATA.meta.unresolved && DATA.meta.unresolved.length ? `<br>Unverified this cycle: ${esc(DATA.meta.unresolved.join(", "))}.` : ""}<br>Aggregated public data and analytical synthesis with both sides shown — not investment advice. Nothing here places orders. Press <b>?</b> for keys.`;
noteChanges(store.get("ipo-seen", {}) || {}, DATA);
try { renderAll(); renderResearchSelect(); liveText(); oldTags(); } catch (err) { document.querySelector("main").insertAdjacentHTML("afterbegin", `<div class="card" style="padding:14px 18px;border-color:var(--down);margin-bottom:16px"><b class="down">The page hit an error while rendering.</b> <span class="dim">${esc(err && err.message)}</span></div>`); console.error(err); }
// ---- backup / restore: every "ipo-*" key, raw, so legacy shapes round-trip untouched -------------
const backupKeys = () => { const out = {}; try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.startsWith("ipo-")) out[k] = localStorage.getItem(k); } } catch (e) {} return out; };
const backupDoc = () => ({ app: "ipo-desk", version: 1, exportedAt: new Date().toISOString(), origin: location.origin, keys: backupKeys() });
function restoreFrom(text) {
  let doc; try { doc = JSON.parse(text); } catch (e) { toast("That is not a backup: not JSON"); return; }
  const keys = doc && doc.app === "ipo-desk" && doc.keys && typeof doc.keys === "object" ? doc.keys : null;
  const names = keys ? Object.keys(keys).filter(k => k.startsWith("ipo-") && typeof keys[k] === "string") : [];
  if (!names.length) { toast("That is not an ipo-desk backup"); return; }
  if (!confirm(`Restore ${names.length} item(s) from the backup of ${String(doc.exportedAt || "").slice(0, 10) || "unknown date"}?\n\nThis replaces the stars, holdings, applications and tasks in this browser.`)) return;
  try { names.forEach(k => localStorage.setItem(k, keys[k])); } catch (e) { toast("Could not write to this browser's storage"); return; }
  location.reload();
}
{ const n = Object.keys(backupKeys()).length; $("#bkNote").textContent = n ? "" : "nothing saved in this browser yet — restore a backup from your old dashboard"; }
$("#bkSave").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(backupDoc(), null, 1)], { type: "application/json" })); a.download = `ipo-desk-backup-${iso(new Date())}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); toast("Backup saved"); };
$("#bkLoad").onclick = () => $("#bkFile").click();
$("#bkFile").onchange = e => { const f = e.target.files[0]; if (f) f.text().then(restoreFrom); e.target.value = ""; };
$("#bkPaste").onclick = () => { const t = prompt("Paste the backup text here"); if (t) restoreFrom(t); };

function oldTags() { const I = DATA.investors || {}, qd = (DATA.quota || []).map(q => q.stageDate).filter(Boolean).sort().pop();
  if ($("#invOld")) $("#invOld").innerHTML = oldTag(I.asOf, 7) ? oldTag(I.asOf, 7).replace("as of", "holdings and moves as of") + ' <span class="dt">prices live</span>' : "";
  if ($("#pipeOld")) $("#pipeOld").innerHTML = qd ? `<span class="dt" style="margin-left:8px">stages tracked every run · last stage change ${fmtD(qd)} · descriptions are hand-written notes</span>` : ""; }
function liveText() { const el = $("#liveTxt"); if (!el) return; const mins = (Date.now() - new Date(DATA.meta.asOf)) / 60000, nx = nextRun();
  const lv = LIVE && LIVE.asOf && (Date.now() - new Date(LIVE.asOf)) < 20 * 60000;
  el.textContent = (mins > 36 * 60 ? "Stale · " : "Live · ") + (lv ? "book " + ago(LIVE.asOf) + " · full run " + ago(DATA.meta.asOf) : "updated " + ago(DATA.meta.asOf)) + (nx ? " · next " + nx + " IST" : ""); el.parentElement.classList.toggle("stale", mins > 36 * 60); }
setInterval(liveText, 30000);
const savedTab = store.get("ipo-tab", "today"); show(["today", "pipe", "board", "market", "research", "book", "score"].includes(savedTab) ? savedTab : "today");

/* Swap in freshly fetched data without reloading the page or touching local state
   (starred names, held parents, applications and tasks all live in localStorage). */
return {
  update(next) {
    if (!next || !next.meta) return false;
    noteChanges(seenOf(DATA), next);
    DATA = next;
    store.set("ipo-seen", seenOf(DATA));
    recompute();
    try {
      renderAll(); renderResearchSelect(); liveText(); oldTags();
      if (screen === "market") renderMarket();
      if (screen === "board") drawCharts();
      if (screen === "book") drawPosCharts();
    } catch (err) { console.error(err); return false; }
    return true;
  },
  // live.json (the five-minute loop) laid over the document: only values newer than the ones on the row are taken
  live(L) {
    if (!L || !L.rows) return false;
    const was = seenOf(DATA); let moved = false;
    [...(DATA.mainboard || []), ...(DATA.sme || [])].forEach(b => { const v = L.rows[b.name]; if (!v) return;
      if (v.sub && String(v.sub.asOf || "") > String((b.sub || {}).asOf || "")) { b.sub = { ...(b.sub || {}), ...v.sub }; moved = true; }
      if (v.gmp != null && String(v.gmpAsOf || "") > String(b.gmpAsOf || "") && v.gmp !== b.gmp) { b.gmpTrend = b.gmp == null ? "flat" : v.gmp > b.gmp ? "up" : v.gmp < b.gmp ? "down" : "flat"; b.gmp = v.gmp; b.gmpPct = v.gmpPct != null ? v.gmpPct : b.bandHigh ? Math.round(v.gmp / b.bandHigh * 1e4) / 100 : b.gmpPct; b.gmpAsOf = v.gmpAsOf; moved = true; } });
    const hadPre = JSON.stringify((LIVE || {}).preopen || []); LIVE = { asOf: L.asOf, preopen: L.preopen || [], timeline: L.timeline || {} };
    if (!moved && hadPre === JSON.stringify(LIVE.preopen)) { liveText(); return true; }
    noteChanges(was, DATA); store.set("ipo-seen", seenOf(DATA));
    try { renderAll(); liveText(); } catch (err) { console.error(err); return false; }
    return true;
  },
  get asOf() { return DATA.meta.asOf; }
};
};

