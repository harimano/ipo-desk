/* ================= SCOREBOARD — how much to trust each signal, from the desk's own history =================
   Included into app.js by site/build.py (`@include scoreboard.js`), so it shares app.js's helpers: $, esc, pct, cls,
   inr, fmtD, bandOf, median, EDG, SEG, EVD, winLbl, edgeLbl. The headline cards (warnings, expected value, the GMP fit)
   are `evidence`, computed by collector/modules/evidence.py. The band tables below them are an EXPLORER over the rows of
   listedPerf / comps for whatever year the viewer picks, so they are counted here — with n and a Wilson 95% range on
   every line, the same rule the collector follows. Facts with their sample sizes; never a verdict. */
const wilsonJs = (k, n) => { if (!n) return null; const z = 1.96, p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return [Math.round(100 * Math.max(0, c - h)), Math.round(100 * Math.min(1, c + h))]; };
function evidenceCards() {
  const E = EVD(), seg = SEG(sbScope === "sme"); if (!seg) return "";
  const lbl = sbScope === "sme" ? "SME" : "mainboard", Wn = (E.warnings || []).filter(w => new RegExp("-" + lbl, "i").test(w.code));
  const warn = Wn.length ? `<div class="sec card"><div class="ch">Read these first <span class="sub">what the evidence base cannot yet support · written by the collector's audit every run</span></div><ul class="notes">${Wn.map(w => `<li>${esc(w.text)}</li>`).join("")}</ul></div>` : "";
  const ed = EDG("retail"), ev = seg.ev.rows.map((r, i) => !r.n ? "" : `<tr><td>${edgeLbl(ed, i, "x")}</td><td class="r num">${r.n}${r.n < (E.minN || 30) ? ' <span class="dim">thin</span>' : ""}</td><td class="r num">${Math.round(r.pos)}% <span class="dim">${Math.round(r.lo)}–${Math.round(r.hi)}</span></td><td class="r num ${cls(r.med)}">${pct(r.med, true)}</td><td class="r num">${r.oddsMed}%</td><td class="r num ${cls(r.evMed)}"><b>${pct(r.evMed, true)}</b></td><td class="r num dim">${pct(r.evP10, true)} to ${pct(r.evP90, true)}</td><td class="r num dim">${pct(r.evMean, true)}</td></tr>`).join("");
  const f = seg.fit || {}, fitRow = (l, x) => x ? `<tr><td>${l}</td><td class="r num">${x.n}</td><td class="r num">${x.a >= 0 ? "+" : "−"}${Math.abs(x.a)} + ${x.b} × GMP</td><td class="r num">${x.r2}</td><td class="r num">${x.sd} pp</td><td class="r num">${pct(x.q10, true)} to ${pct(x.q90, true)}</td></tr>` : "";
  return warn + `<div class="sec"><div class="card"><div class="ch">Expected value of one retail application <span class="sub">${lbl} · ${(seg.ev.years || []).join(", ")} only · % of the money blocked, net of ${Math.round((E.rfAnnual || 0) * 100)}% a year for ${seg.ev.blockDays} days</span></div>
      <div class="tw"><table><thead><tr><th>Retail book</th><th class="r">Issues</th><th class="r">Listed positive <span class="dim">95% range</span></th><th class="r">Median pop</th><th class="r" title="1 ÷ retail subscription. A lower bound: applicants bid more than one lot on average, so applications are fewer than lots bid.">Chance, at least</th><th class="r">Median EV</th><th class="r">8 in 10 between</th><th class="r">Mean</th></tr></thead><tbody>${ev}</tbody></table></div>
      <div class="dt" style="padding:8px 12px">The most crowded books pop the most and pay the least per application: the chance falls faster than the gain rises.</div></div></div>
    <div class="sec"><div class="card"><div class="ch">How far listings land from their GMP <span class="sub">${lbl} · ${winLbl(seg.window)}${f.provisional ? ' · <span class="oldtag">provisional</span>' : ""}</span></div>
      <div class="tw"><table><thead><tr><th>GMP taken from</th><th class="r">Listings</th><th class="r">Listing gain ≈</th><th class="r">R²</th><th class="r">Typical miss</th><th class="r">8 in 10 within</th></tr></thead><tbody>${fitRow("Source's listing-morning figure (report 377)", f.r377)}${fitRow("Desk's own evening-before record", f.eve)}${fitRow("Report 377, same listings as the desk's", f.r377OnSameRows)}</tbody></table></div>
      <div class="dt" style="padding:8px 12px">${f.eve ? "Both fits are shown side by side; if they disagree, the evening-before one is the honest one." : `The desk's own evening-before GMP is on file for ${f.eveRows || 0} of the ${E.minN || 30} listings needed before a second fit is shown beside this one.`}</div></div></div>`;
}
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
      return `<tr><td>${edgeLbl(edges, i, unit)}</td><td class="r num">${x.length}</td><td class="r num">${p100(o.filter(v => v > 0).length, o.length)} <span class="dim">${wilsonJs(o.filter(v => v > 0).length, o.length).join("–")}</span></td><td class="r num ${cls(median(o))}">${pct(median(o), true)}</td><td class="r num ${cls(median(c))}">${c.length ? pct(median(c), true) : "—"}</td></tr>`; }).join("");
    return `<div class="card"><div class="ch">${title}</div><div class="tw"><table><thead><tr><th>Band</th><th class="r">Issues</th><th class="r">Listed positive <span class="dim">95% range</span></th><th class="r">Median at open</th><th class="r">Median at day-1 close</th></tr></thead><tbody>${out || `<tr><td colspan="5" class="empty">No cases in this selection.</td></tr>`}</tbody></table></div></div>`; };
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
    ${evidenceCards()}
    <div class="sec grid g2">${bandTbl("Grey-market premium → listing", "g", EDG("gmp"), "%", R)}${bandTbl("Total subscription → listing", "total", EDG("total"), "x", R)}</div>
    <div class="sec grid g2">${bandTbl("QIB subscription → listing <span class='sub'>category books are on file from 2026</span>", "qib", EDG("qib"), "x", R)}${bandTbl("Retail subscription → listing <span class='sub'>from 2026</span>", "retail", EDG("retail"), "x", R)}</div>
    <div class="sec card"><div class="ch">Every listing <span class="sub">${list.length} shown · click a column to sort</span><span class="right"><button class="btn sm${sbBelow ? " primary" : ""}" id="sbBelow">Below issue price${sbBelow ? " ✓" : ""}</button></span></div>
      <div class="tw" style="max-height:520px;overflow:auto"><table id="sbt"><thead><tr>${cols.map(([k, l], i) => `<th class="${i > 1 ? "r" : ""}" data-k="${k}" style="cursor:pointer">${l}${sbSort[0] === k ? (sbSort[1] > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
      <tbody>${list.slice(0, 400).map(r => `<tr><td class="nm">${esc(r.name)}</td><td class="dt">${fmtD(r.date)} ${String(r.date || "").slice(2, 4)}</td><td class="r num">${r.g != null ? pct(r.g, true) : "—"}</td><td class="r num ${cls(r.open)}">${pct(r.open, true)}</td><td class="r num ${r.err == null ? "dim" : Math.abs(r.err) <= 10 ? "" : "amb"}">${r.err != null ? pct(r.err, true) : "—"}</td><td class="r num ${cls(r.close)}">${r.close != null ? pct(r.close, true) : "—"}</td><td class="r num ${cls(r.now)}">${r.now != null ? pct(r.now, true) : "—"}</td><td class="r num">${r.total != null ? r.total + "x" : "—"}</td></tr>`).join("")}</tbody></table></div></div>`;
}
document.addEventListener("click", e => { if (!e.target.closest("#score")) return;
  const b = e.target.closest("#sbf button"), th = e.target.closest("#sbt th[data-k]");
  if (b) { if (b.dataset.sc) sbScope = b.dataset.sc; if (b.dataset.y) sbYear = b.dataset.y; renderScore(); }
  else if (th) { sbSort = [th.dataset.k, sbSort[0] === th.dataset.k ? -sbSort[1] : -1]; renderScore(); }
  else if (e.target.closest("#sbBelow")) { sbBelow = !sbBelow; renderScore(); } });
