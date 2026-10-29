/* ---------- the trust strip and provenance (included into app.js) ----------
   Part 1 — under each screen's "data as of" stamp: the feeds that screen depends on, each with a dot (fresh / late / failed),
   the source that answered and the time of its last good answer. Every fact is a field of DATA.integrity.checks; "late" is
   the collector's own `dueBy` (collector/assemble.py due_by) — the page holds no threshold. A check with no `dueBy` (a
   document written before the field existed) gets a grey dot and no verdict. Folded to one line, a toggle opens the list.
   Part 2 — provenance: `pv(base, ...lines)` writes a title "base ⏎ source · fetched HH:MM IST" and marks it data-prov, so the
   same text shows on hover (title) and on tap (the popover below; touch screens do not show titles). */
const SRC_LBL = { investorgain: "InvestorGain", nse: "NSE", bse: "BSE", narada: "Narada", nsearchives: "NSE archives", chittorgarh: "Chittorgarh", angelone: "Angel One",
  yahoo: "Yahoo", sebi: "SEBI", nse_ann: "NSE announcements", bse_ann: "BSE announcements", rss: "news feeds", computed: "computed from the document", trendlyne: "Trendlyne" };
const srcName = k => SRC_LBL[String(k).split("-")[0]] || String(k);
// feeds each screen depends on: [integrity area, label]
const FEEDS = {
  today: [["calendar", "Calendar"], ["gmp", "GMP"], ["subscription", "Books"], ["flows", "FII / DII"], ["filings", "Quota radar"]],
  pipe: [["filings", "Quota radar"], ["parents", "Parent prices"], ["offers", "Offers"], ["calendar", "Calendar"]],
  board: [["calendar", "Calendar"], ["details", "IPO records"], ["gmp", "GMP"], ["subscription", "Books"], ["listings", "Listing prices"], ["history", "Listing history"]],
  market: [["flows", "FII / DII"], ["deals", "Bulk / block deals"], ["tape", "Price tape"], ["players", "Anchor investors"], ["anchorbook", "Anchor books"], ["news", "News"]],
  research: [["details", "IPO records"], ["history", "Listing history"], ["parents", "Parent prices"]],
  score: [["evidence", "Evidence"], ["history", "Listing history"], ["tape", "Price tape"], ["gmp", "GMP"]],
  book: [["parents", "Parent prices"], ["listings", "Listing prices"]],
};
const checkOf = area => ((DATA.integrity || {}).checks || []).find(c => c.area === area);
// "angelone:down, yahoo:ok" -> answered by Yahoo, Angel One down. "narada+nse:ok" -> Narada + NSE.
function answeredBy(c) {
  const ok = [], down = [];
  String(c.method || "").split(",").forEach(t => { const m = /^\s*([\w+.-]+):(\w+)\s*$/.exec(t); if (!m) return; (m[2] === "ok" ? ok : down).push(...m[1].split("+")); });
  return { ok: [...new Set(ok.map(srcName))], down: [...new Set(down.map(srcName))] };
}
const feedAt = c => c.lastOk || (c.carried ? c.asOf : (DATA.integrity || {}).asOf || c.asOf);
const feedWhen = c => { const t = feedAt(c);
  return hasTime(t) ? istClock(t) : /^\d{4}-\d{2}-\d{2}$/.test(String(t || "")) ? fmtD(t) : ""; };
function feedState(c) {
  const a = answeredBy(c), when = feedWhen(c), ts = new Date(feedAt(c)).getTime() || 0;
  if (c.status !== "ok") return { ts, cls: "fail", word: c.status === "blocked" ? "blocked" : "failed", src: c.status === "blocked" ? "blocked" : "no answer", when, note: when ? "kept previous from " + when : "kept previous", a };
  const late = c.dueBy && Date.now() > new Date(c.dueBy);
  return { ts, cls: !c.dueBy ? "none" : late ? "late" : "fresh", word: !c.dueBy ? "" : late ? "late" : "fresh", src: a.ok.join(" + ") || "—", when,
    note: [a.down.length ? a.down.join(", ") + " down — fallback used" : "", late ? "was due by " + istClock(c.dueBy) : ""].filter(Boolean).join(" · "), a };
}
let trustOpen = false;
function trustStrip(id) {
  const rows = (FEEDS[id] || []).map(([area, label]) => { const c = checkOf(area); return c ? { label, s: feedState(c) } : null; }).filter(Boolean);
  if ((id === "today" || id === "board") && LIVE && LIVE.asOf) {   // the five-minute book: live.json carries no due time, so no verdict
    const srcs = [...new Set(allIssues().filter(b => b.status === "Open").map(b => (b.sub || {}).src).filter(Boolean).map(srcName))];
    rows.push({ label: "Live book (5 min)", s: { cls: "none", word: "", src: srcs.join(" + ") || "—", when: istClock(LIVE.asOf), note: "", a: {} } }); }
  if (!rows.length) return "";
  const groups = {};                                          // folded line: one chip per source + state
  rows.forEach(r => { const k = r.s.cls + "|" + r.s.src; const g = groups[k] = groups[k] || { s: r.s, n: 0 }; g.n++; if (r.s.ts && (!g.s.ts || r.s.ts < g.s.ts)) g.s = r.s; });   /* the oldest time in the group */
  const worst = ["fail", "late", "none", "fresh"].find(k => rows.some(r => r.s.cls === k));
  return `<details class="src" data-trust ${trustOpen ? "open" : ""}><summary aria-label="Where this screen's data comes from">${Object.values(groups).map(g => `<span><i class="d ${g.s.cls}"></i>${esc(g.s.src)}${g.s.when ? " " + esc(g.s.when) : ""}</span>`).join("")}<span class="more">${rows.length} feed${rows.length > 1 ? "s" : ""}${worst === "fail" || worst === "late" ? " · check" : ""} <i class="chev">▾</i></span></summary>
    <div class="list">${rows.map(r => `<div class="row"><i class="d ${r.s.cls}"></i><b>${esc(r.label)}</b><span class="n">${esc(r.s.src)}${r.s.cls === "fail" ? "" : r.s.when ? " · last good " + esc(r.s.when) : ""}${r.s.note ? " · " + esc(r.s.note) : ""}</span><span class="w">${r.s.word}</span></div>`).join("")}</div></details>`;
}
function renderTrust() { $$("section.screen").forEach(sec => { const id = sec.id.replace(/^s-/, ""), html = trustStrip(id); let el = sec.querySelector(":scope > .srcwrap");
  if (!html) { if (el) el.remove(); return; }
  if (!el) { el = document.createElement("div"); el.className = "srcwrap"; const st = sec.querySelector(":scope > .stamp"); sec.insertBefore(el, st ? st.nextSibling : sec.firstChild); }
  el.innerHTML = html; }); }
document.addEventListener("toggle", e => { if (e.target.matches && e.target.matches("details[data-trust]")) { trustOpen = e.target.open; $$("details[data-trust]").forEach(d => { if (d.open !== trustOpen) d.open = trustOpen; }); } }, true);

/* ---- provenance: "source · fetched HH:MM IST" ---- */
const fetchedAt = t => !t ? "" : hasTime(t) ? " · fetched " + istClock(t) : " · " + fmtD(t);
const provLine = (src, t, extra) => src + fetchedAt(t) + (extra ? " · " + extra : "");
const chkAt = area => { const c = checkOf(area); return c ? c.lastOk || (c.carried ? c.asOf : (DATA.integrity || {}).asOf) : null; };
const PROV = {
  gmp: b => provLine("GMP: InvestorGain report 331", b.gmpAsOf, "the quote's own date is not published"),
  book: b => { const s = b.sub || {}, src = s.src === "investorgain" ? "InvestorGain report 566" : s.src ? srcName(s.src) : "exchange feed";
    return provLine("Book: " + src, s.asOf) + (s.catAsOf && s.catAsOf !== s.asOf && hasTime(s.catAsOf) ? ` · QIB / NII / retail split from ${istClock(s.catAsOf)}` : ""); },
  apps: b => provLine("Applications: Narada", (b.apps || {}).asOf || (b.sub || {}).asOf),
  odds: b => "Odds: the retail book above (a lower bound) and, where shown, Narada's application count",
  ev: (b, seg) => `EV inputs: the retail book, the GMP above, ${seg ? `${/SME/i.test(b.type) ? "SME" : "mainboard"} evidence window ${winLbl(seg.window)}` : "the evidence window"}${(DATA.evidence || {}).asOf ? ", evidence computed " + fmtD(DATA.evidence.asOf) : ""}`,
  record: b => provLine("InvestorGain issue record" + (b.igId ? " " + b.igId : ""), chkAt("details")),
  listing: b => provLine("Listing price: InvestorGain report 377", chkAt("history")),
};
// a title that carries its sources; `lines` are the PROV texts to append
const pv = (base, ...lines) => `title="${esc([base, ...lines.filter(Boolean)].filter(Boolean).join("\n"))}" data-prov`;

/* ---- the tap popover: touch screens never show a title ---- */
(function () {
  let pop = null;
  const close = () => { if (pop) { pop.remove(); pop = null; } };
  document.addEventListener("click", e => {
    const t = e.target.closest && e.target.closest("[data-prov]");
    if (!t) { if (!(pop && pop.contains(e.target))) close(); return; }
    if (!matchMedia("(hover: none)").matches) return;
    const text = t.getAttribute("title") || t.dataset.provText; if (!text) return;
    t.dataset.provText = text; t.removeAttribute("title");     // else the browser's own tooltip shows beside ours
    const again = pop && pop.dataset.for === text; close(); if (again) return;
    const [head, ...rest] = text.split("\n");
    pop = document.createElement("div"); pop.className = "provpop"; pop.setAttribute("role", "tooltip"); pop.dataset.for = text;
    pop.innerHTML = `<b>${esc(head)}</b>${rest.map(l => `<div>${esc(l)}</div>`).join("")}`;
    document.body.appendChild(pop);
    const r = t.getBoundingClientRect(), w = Math.min(300, innerWidth - 24);
    pop.style.width = w + "px"; pop.style.left = Math.max(12, Math.min(innerWidth - w - 12, r.left)) + "px";
    const below = r.bottom + 8 + pop.offsetHeight < innerHeight; pop.style.top = (below ? r.bottom + 8 : Math.max(8, r.top - 8 - pop.offsetHeight)) + "px";
  }, true);
  window.addEventListener("scroll", close, { passive: true });
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
})();
