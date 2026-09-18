/* ================= SCOREBOARD — how much to trust each signal, from the desk's own history =================
   Included into app.js by site/build.py (`@include scoreboard.js`), so it shares app.js's helpers: $, esc, pct, cls,
   inr, fmtD, bandOf, median, QIB_EDGES, GMP_EDGES, edgeLbl. Everything here is computed from fields the collector
   wrote (listedPerf, comps: modules/history.py). Facts with their sample sizes; never a verdict. */
let sbScope = "main", sbYear = "all", sbBelow = false, sbSort = ["date", -1];
function sbRows() {
  const by = {}; (DATA.comps || []).forEach(c => by[c.igId || c.name] = c);
  return (DATA.listedPerf || []).filter(p => p.issue && p.listing && (sbScope === "sme") === !!p.sme && (sbYear === "all" || String(p.date || "").slice(0, 4) === sbYear)).map(p => {
    const c = by[p.igId || p.name] || {}, g = p.gmpImplied ? 100 * (p.gmpImplied - p.issue) / p.issue : null, open = 100 * (p.listing - p.issue) / p.issue;
    return { name: p.name, date: p.date, g, open, close: p.close1 ? 100 * (p.close1 - p.issue) / p.issue : null, now: p.ltp ? 100 * (p.ltp - p.issue) / p.issue : null,
      err: g != null ? open - g : null, total: c.total, qib: c.qib, retail: c.retail };
  });
}
function renderScore() {
  const R = sbRows(), el = $("#score"); if (!el) return;
  const years = [...new Set((DATA.listedPerf || []).map(p => String(p.date || "").slice(0, 4)).filter(Boolean))].sort().reverse();
  const G = R.filter(r => r.g != null), hit = G.filter(r => (r.g > 0) === (r.open > 0)).length, near = G.filter(r => Math.abs(r.err) <= 10).length;
  const H = R.filter(r => r.close != null), held = H.filter(r => r.close > r.open).length, below = R.filter(r => r.now != null && r.now < 0).length, N = R.filter(r => r.now != null).length;
  const p100 = (a, b) => b ? Math.round(100 * a / b) + "%" : "—";
  const kpi = (l, v, d) => `<div class="card kpi"><div class="lbl">${l}</div><div class="v mono">${v}</div><div class="d">${d}</div></div>`;
  const bandTbl = (title, key, edges, unit, rows) => { const out = edges.slice(0, -1).map((_, i) => { const x = rows.filter(r => typeof r[key] === "number" && bandOf(r[key], edges) === i); if (!x.length) return "";
      const o = x.map(r => r.open), c = x.filter(r => r.close != null).map(r => r.close);
      return `<tr><td>${edgeLbl(edges, i, unit)}</td><td class="r num">${x.length}</td><td class="r num">${p100(o.filter(v => v > 0).length, o.length)}</td><td class="r num ${cls(median(o))}">${pct(median(o), true)}</td><td class="r num ${cls(median(c))}">${c.length ? pct(median(c), true) : "—"}</td></tr>`; }).join("");
    return `<div class="card"><div class="ch">${title}</div><div class="tw"><table><thead><tr><th>Band</th><th class="r">Issues</th><th class="r">Listed positive</th><th class="r">Median at open</th><th class="r">Median at day-1 close</th></tr></thead><tbody>${out || `<tr><td colspan="5" class="empty">No cases in this selection.</td></tr>`}</tbody></table></div></div>`; };
  const big = H.filter(r => r.open >= 30), bigHeld = big.filter(r => r.close > r.open).length, flat = H.filter(r => r.open > 0 && r.open < 10), flatHeld = flat.filter(r => r.close > r.open).length;
  const cols = [["name", "IPO"], ["date", "Listed"], ["g", "GMP implied"], ["open", "Listing"], ["err", "GMP error"], ["close", "Day-1 close"], ["now", "Now"], ["total", "Book"]];
  const list = (sbBelow ? R.filter(r => r.now != null && r.now < 0) : R).slice().sort((a, b) => { const k = sbSort[0], x = a[k], y = b[k]; return (x == null) - (y == null) || (x > y ? 1 : x < y ? -1 : 0) * sbSort[1]; });
  el.innerHTML = `<div class="sec-h" style="margin-top:0"><h2>Scoreboard</h2><span class="sub">what each signal said, and what then happened · ${R.length} listings in this selection · analysis, not advice</span>
      <div class="filters right" id="sbf"><button data-sc="main" aria-pressed="${sbScope === "main"}">Mainboard</button><button data-sc="sme" aria-pressed="${sbScope === "sme"}">SME</button>
      <button data-y="all" aria-pressed="${sbYear === "all"}">All years</button>${years.map(y => `<button data-y="${y}" aria-pressed="${sbYear === y}">${y}</button>`).join("")}</div></div>
    <div class="kpis">${kpi("GMP called the direction", p100(hit, G.length), `${hit} of ${G.length} · within 10 points of the listing: ${p100(near, G.length)}`)}
      ${kpi("GMP error, median", G.length ? pct(median(G.map(r => r.err)), true) : "—", "listing gain minus what the grey market implied")}
      ${kpi("Held to the close beat the open", p100(held, H.length), `${held} of ${H.length} · after a +30% open: ${p100(bigHeld, big.length)} of ${big.length} · after a 0–10% open: ${p100(flatHeld, flat.length)} of ${flat.length}`)}
      ${kpi("Below issue price now", p100(below, N), `${below} of ${N} listings`)}</div>
    <div class="sec grid g2">${bandTbl("Grey-market premium → listing", "g", GMP_EDGES, "%", R)}${bandTbl("Total subscription → listing", "total", QIB_EDGES, "x", R)}</div>
    <div class="sec grid g2">${bandTbl("QIB subscription → listing <span class='sub'>category books are on file from 2026</span>", "qib", QIB_EDGES, "x", R)}${bandTbl("Retail subscription → listing <span class='sub'>from 2026</span>", "retail", QIB_EDGES, "x", R)}</div>
    <div class="sec card"><div class="ch">Every listing <span class="sub">${list.length} shown · click a column to sort</span><span class="right"><button class="btn sm${sbBelow ? " primary" : ""}" id="sbBelow">Below issue price${sbBelow ? " ✓" : ""}</button></span></div>
      <div class="tw" style="max-height:520px;overflow:auto"><table id="sbt"><thead><tr>${cols.map(([k, l], i) => `<th class="${i > 1 ? "r" : ""}" data-k="${k}" style="cursor:pointer">${l}${sbSort[0] === k ? (sbSort[1] > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
      <tbody>${list.slice(0, 400).map(r => `<tr><td class="nm">${esc(r.name)}</td><td class="dt">${fmtD(r.date)} ${String(r.date || "").slice(2, 4)}</td><td class="r num">${r.g != null ? pct(r.g, true) : "—"}</td><td class="r num ${cls(r.open)}">${pct(r.open, true)}</td><td class="r num ${r.err == null ? "dim" : Math.abs(r.err) <= 10 ? "" : "amb"}">${r.err != null ? pct(r.err, true) : "—"}</td><td class="r num ${cls(r.close)}">${r.close != null ? pct(r.close, true) : "—"}</td><td class="r num ${cls(r.now)}">${r.now != null ? pct(r.now, true) : "—"}</td><td class="r num">${r.total != null ? r.total + "x" : "—"}</td></tr>`).join("")}</tbody></table></div></div>`;
}
document.addEventListener("click", e => { if (!e.target.closest("#score")) return;
  const b = e.target.closest("#sbf button"), th = e.target.closest("#sbt th[data-k]");
  if (b) { if (b.dataset.sc) sbScope = b.dataset.sc; if (b.dataset.y) sbYear = b.dataset.y; renderScore(); }
  else if (th) { sbSort = [th.dataset.k, sbSort[0] === th.dataset.k ? -sbSort[1] : -1]; renderScore(); }
  else if (e.target.closest("#sbBelow")) { sbBelow = !sbBelow; renderScore(); } });
