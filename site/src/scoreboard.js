/* ================= SCOREBOARD — how much to trust each signal, from the desk's own history =================
   Included into app.js by site/build.py (`@include scoreboard.js`), so it shares app.js's helpers: $, esc, pct, cls,
   inr, fmtD, bandOf, median, EDG, SEG, EVD, winLbl, edgeLbl, evBand, evCls, evLong, evOf, board, sme, tok, Chart. The
   headline cards (warnings, expected value, the GMP fit) are `evidence`, computed by collector/modules/evidence.py.
   The band tables, the calibration scatter and hit-rate-by-month are an EXPLORER over the rows of listedPerf / comps
   for whatever year and segment the viewer picks, so they are counted here — with n and a Wilson 95% range on every
   line, the same rule the collector follows. "Open calls" is the live half: not history, but today's own signals on
   issues not yet listed, so a viewer can come back after listing day and see whether they held up. Facts with their
   sample sizes; never a verdict. */
const wilsonJs = (k, n) => { if (!n) return null; const z = 1.96, p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return [Math.round(100 * Math.max(0, c - h)), Math.round(100 * Math.min(1, c + h))]; };
function openCalls() {
  const isSme = sbScope === "sme", seg = SEG(isSme), rows = (isSme ? sme : board).filter(b => b.status === "Open" || b.status === "Closed")
    .sort((a, b) => (a.close || a.listing || "").localeCompare(b.close || b.listing || ""));
  const body = rows.map(b => {
    const s = b.sub || {}, T = evBand(seg, "total", s.total, "all"), G = evBand(seg, "gmp", b.gmpPct, "window"), E = evOf(b, seg);
    return `<tr data-row data-name="${esc(b.name)}"><td class="nm">${esc(b.name)}</td><td><span class="pill ${b.status.toLowerCase()}">${b.status}</span><div class="dt">${b.status === "Open" ? "closes " + fmtD(b.close) : "lists " + fmtD(b.listing)}</div></td>
      <td class="r num">${b.gmpPct != null ? pct(b.gmpPct, true) : "—"}</td>
      <td class="r">${T && T.s.n ? `<span class="ev ${evCls(T.s)}" title="Total book ${T.lbl}, all years: ${evLong(T.s)}">${Math.round(T.s.pos)}%</span>` : `<span class="dim">${s.total != null ? s.total + "x" : "—"}</span>`}</td>
      <td class="r">${G && G.s.n ? `<span class="ev ${evCls(G.s)}" title="GMP ${G.lbl}: ${evLong(G.s)}">${Math.round(G.s.pos)}%</span>` : `<span class="dim">—</span>`}</td>
      <td class="r num ${E ? cls(E.ev) : ""}">${E ? pct(E.ev, true) : "—"}</td></tr>`;
  }).join("");
  return `<div class="sec card"><div class="ch">Open calls <span class="sub">${isSme ? "SME" : "mainboard"} · what today's signals say for issues not yet listed — come back after listing day</span></div>
    <div class="tw"><table><thead><tr><th>Issue</th><th>Status</th><th class="r">GMP</th><th class="r" title="How past issues at this book's total-subscription band listed">Book track record</th><th class="r" title="How past issues at this GMP level listed">GMP track record</th><th class="r">EV / app</th></tr></thead>
    <tbody>${body || `<tr><td colspan="6" class="empty">Nothing open right now.</td></tr>`}</tbody></table></div></div>`;
}
// GMP calibration. What it has to convey at a glance: (1) where listings actually land for a given GMP — the collector's own
// fitted line and its 8-in-10 band (evidence.segments[x].fit), not just a y = x ideal; (2) whether the recent market behaves
// like the old one — the trailing window in full colour, older listings faded; (3) where today's open issues sit on it.
function calibScatter(R) {
  Object.values(scharts).forEach(c => c.destroy()); scharts = {};
  const el = $("#sbCalib"); if (!el || typeof Chart === "undefined") return;
  const grid = tok("--chart-grid"), text = tok("--chart-text"), up = tok("--up"), down = tok("--down"), acc = tok("--accent"), lav = tok("--lav");
  const isSme = sbScope === "sme", seg = SEG(isSme), f = seg && seg.fit && (seg.fit.eve || seg.fit.r377), from = seg && seg.window ? seg.window.from : null;
  const G = R.filter(r => r.g != null && r.open != null && r.g !== 0); if (!G.length) return;
  const q = (arr, p) => { const v = arr.slice().sort((x, y) => x - y); return v[Math.min(v.length - 1, Math.max(0, Math.round(p * (v.length - 1))))]; };
  const x0 = Math.min(-10, q(G.map(r => r.g), .01)), x1 = Math.max(40, q(G.map(r => r.g), .99)), y0 = Math.min(-20, q(G.map(r => r.open), .01)), y1 = Math.max(40, q(G.map(r => r.open), .99));
  const pt = r => ({ x: r.g, y: r.open, name: r.name, date: r.date, total: r.total }), recent = r => !from || (r.date || "") >= from, hit = r => (r.g > 0) === (r.open > 0);
  const line = (k, label, color, dash, w) => ({ type: "line", label, data: [x0, x1].map(x => ({ x, y: f.a + f.b * x + k })), borderColor: color, borderDash: dash, borderWidth: w, pointRadius: 0, order: 1 });
  const live = (isSme ? sme : board).filter(b => (b.status === "Open" || b.status === "Closed") && b.gmpPct != null && b.gmpPct !== 0 && f).map(b => ({ x: b.gmpPct, y: f.a + f.b * b.gmpPct, name: b.name, live: true, lo: f.a + f.b * b.gmpPct + f.q10, hi: f.a + f.b * b.gmpPct + f.q90 }));
  const sets = [{ type: "line", label: "If GMP were exact", data: [{ x: x0, y: x0 }, { x: x1, y: x1 }], borderColor: text + "66", borderDash: [4, 4], borderWidth: 1, pointRadius: 0, order: 2 }];
  if (f) sets.push(line(0, "Where listings actually landed (fit)", acc, [], 2), line(f.q90, "8 in 10 landed inside", acc + "77", [6, 4], 1.2), Object.assign(line(f.q10, "", acc + "77", [6, 4], 1.2), { label: "_lower" }));
  sets.push({ type: "scatter", label: "Older listings", data: G.filter(r => !recent(r)).map(pt), backgroundColor: text + "40", pointRadius: 3, pointHoverRadius: 6, order: 5 },
    { type: "scatter", label: "Last 12 months · GMP right on direction", data: G.filter(r => recent(r) && hit(r)).map(pt), backgroundColor: up + "cc", pointRadius: 4.5, pointHoverRadius: 8, order: 4 },
    { type: "scatter", label: "Last 12 months · GMP wrong on direction", data: G.filter(r => recent(r) && !hit(r)).map(pt), backgroundColor: down + "dd", pointRadius: 4.5, pointHoverRadius: 8, order: 3 });
  if (live.length) sets.push({ type: "scatter", label: "Open now, at the fit", data: live, backgroundColor: lav, borderColor: tok("--surface"), borderWidth: 1.5, pointStyle: "rectRot", pointRadius: 9, pointHoverRadius: 12, order: 0 });
  scharts.calib = new Chart(el, { data: { datasets: sets }, options: { responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: "bottom", labels: { color: text, boxWidth: 8, padding: 8, font: { size: 11 }, filter: i => !/^_/.test(i.text) } },
      tooltip: { filter: c => c.dataset.type === "scatter", callbacks: { title: it => it[0] ? it[0].raw.name || "" : "", label: c => c.raw.live ? [`GMP implies ${pct(c.raw.x, true)}`, `listings like this landed near ${pct(c.raw.y, true)}`, `8 in 10 between ${pct(c.raw.lo, true)} and ${pct(c.raw.hi, true)}`] : [`GMP implied ${pct(c.raw.x, true)} → listed ${pct(c.raw.y, true)}`, `${c.raw.date ? fmtD(c.raw.date) + " " + String(c.raw.date).slice(0, 4) : ""}${c.raw.total != null ? " · book " + c.raw.total + "x" : ""}`] } } },
    scales: { x: { type: "linear", min: Math.floor(x0 / 10) * 10, max: Math.ceil(x1 / 10) * 10, title: { display: true, text: "What GMP implied", color: text }, ticks: { color: text, callback: v => v + "%" }, grid: { color: grid } },
              y: { type: "linear", min: Math.floor(y0 / 10) * 10, max: Math.ceil(y1 / 10) * 10, title: { display: true, text: "What the listing did", color: text }, ticks: { color: text, callback: v => v + "%" }, grid: { color: grid } } } } });
  const note = $("#sbCalibNote"); if (note) note.innerHTML = f ? `Fit over ${f.n} ${isSme ? "SME" : "mainboard"} listings: a listing lands near <b>${f.a >= 0 ? "+" : "−"}${Math.abs(f.a)} + ${f.b} × GMP</b>, typically within <b>${f.sd} points</b>${seg.fit.provisional ? ' <span class="oldtag">provisional</span>' : ""}. The 1% most extreme listings are off the chart; issues with no GMP quote are left out.` : "";
}
function hitRateByMonth() {
  const isSme = sbScope === "sme", months = {};
  (DATA.listedPerf || []).filter(p => !!p.sme === isSme && p.issue && p.listing != null).forEach(p => {
    const m = String(p.date || "").slice(0, 7); if (!m) return;
    const g = p.gmpImplied ? 100 * (p.gmpImplied - p.issue) / p.issue : null, open = 100 * (p.listing - p.issue) / p.issue;
    (months[m] = months[m] || []).push({ g, open });
  });
  const keys = Object.keys(months).sort().reverse().slice(0, 18);
  const rows = keys.map(m => {
    const xs = months[m], n = xs.length, G = xs.filter(x => x.g != null), hit = G.filter(x => (x.g > 0) === (x.open > 0)).length,
      pos = xs.filter(x => x.open > 0).length, wi = wilsonJs(pos, n) || [null, null];
    return `<tr><td>${m}</td><td class="r num">${n}</td><td class="r num">${G.length ? Math.round(100 * hit / G.length) + "% of " + G.length : "—"}</td>
      <td class="r num">${Math.round(100 * pos / n)}% <span class="dim">${wi[0]}–${wi[1]}</span></td><td class="r num ${cls(median(xs.map(x => x.open)))}">${pct(median(xs.map(x => x.open)), true)}</td></tr>`;
  }).join("");
  return `<div class="card"><div class="ch">Hit rate by month <span class="sub">${isSme ? "SME" : "mainboard"} · last ${keys.length || 0} months with a listing</span></div>
    <div class="tw" style="max-height:500px;overflow:auto"><table><thead><tr><th>Month</th><th class="r">Issues</th><th class="r" title="GMP and the listing had the same sign">GMP called it</th><th class="r">Listed positive <span class="dim">95%</span></th><th class="r">Median gain</th></tr></thead>
    <tbody>${rows || `<tr><td colspan="5" class="empty">Not enough listings yet.</td></tr>`}</tbody></table></div></div>`;
}
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
let sbScope = "main", sbYear = "all", sbBelow = false, sbSort = ["date", -1], scharts = {};
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
    ${openCalls()}
    <div class="kpis">${kpi("GMP called the direction", p100(hit, G.length), `${hit} of ${G.length} · within 10 points of the listing: ${p100(near, G.length)}`)}
      ${kpi("GMP error, median", G.length ? pct(median(G.map(r => r.err)), true) : "—", "listing gain minus what the grey market implied")}
      ${kpi("Held to the close beat the open", p100(held, H.length), `${held} of ${H.length} · after a +30% open: ${p100(bigHeld, big.length)} of ${big.length} · after a 0–10% open: ${p100(flatHeld, flat.length)} of ${flat.length}`)}
      ${kpi("Below issue price now", p100(below, N), `${below} of ${N} listings`)}</div>
    ${evidenceCards()}
    <div class="sec grid g2"><div class="card"><div class="ch">GMP calibration <span class="sub">${sbScope === "sme" ? "SME" : "mainboard"} · ${sbYear === "all" ? "all years" : sbYear} · solid line = where listings actually landed, dashed = 8 in 10</span></div><div class="cb"><div class="chart-wrap" style="height:420px"><canvas id="sbCalib"></canvas></div><div class="dt" id="sbCalibNote" style="margin-top:8px"></div></div></div>${hitRateByMonth()}</div>
    ${holdPanel(sbScope === "sme")}
    <div class="sec grid g2">${bandTbl("Grey-market premium → listing", "g", EDG("gmp"), "%", R)}${bandTbl("Total subscription → listing", "total", EDG("total"), "x", R)}</div>
    <div class="sec grid g2">${bandTbl("QIB subscription → listing <span class='sub'>category books are on file from 2026</span>", "qib", EDG("qib"), "x", R)}${bandTbl("Retail subscription → listing <span class='sub'>from 2026</span>", "retail", EDG("retail"), "x", R)}</div>
    <div class="sec card"><div class="ch">Every listing <span class="sub">${list.length} shown · click a column to sort</span><span class="right"><button class="btn sm${sbBelow ? " primary" : ""}" id="sbBelow">Below issue price${sbBelow ? " ✓" : ""}</button></span></div>
      <div class="tw" style="max-height:520px;overflow:auto"><table id="sbt"><thead><tr>${cols.map(([k, l], i) => `<th class="${i > 1 ? "r" : ""}" data-k="${k}" style="cursor:pointer">${l}${sbSort[0] === k ? (sbSort[1] > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
      <tbody>${list.slice(0, 400).map(r => `<tr><td class="nm">${esc(r.name)}</td><td class="dt">${fmtD(r.date)} ${String(r.date || "").slice(2, 4)}</td><td class="r num">${r.g != null ? pct(r.g, true) : "—"}</td><td class="r num ${cls(r.open)}">${pct(r.open, true)}</td><td class="r num ${r.err == null ? "dim" : Math.abs(r.err) <= 10 ? "" : "amb"}">${r.err != null ? pct(r.err, true) : "—"}</td><td class="r num ${cls(r.close)}">${r.close != null ? pct(r.close, true) : "—"}</td><td class="r num ${cls(r.now)}">${r.now != null ? pct(r.now, true) : "—"}</td><td class="r num">${r.total != null ? r.total + "x" : "—"}</td></tr>`).join("")}</tbody></table></div></div>`;
  calibScatter(R);
}
document.addEventListener("click", e => { if (!e.target.closest("#score")) return;
  const b = e.target.closest("#sbf button"), th = e.target.closest("#sbt th[data-k]");
  if (b) { if (b.dataset.sc) sbScope = b.dataset.sc; if (b.dataset.y) sbYear = b.dataset.y; renderScore(); }
  else if (th) { sbSort = [th.dataset.k, sbSort[0] === th.dataset.k ? -sbSort[1] : -1]; renderScore(); }
  else if (e.target.closest("#sbBelow")) { sbBelow = !sbBelow; renderScore(); } });
