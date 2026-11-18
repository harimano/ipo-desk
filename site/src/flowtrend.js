// Money flow, the longer view (Market > Flows). Everything here is a field the collector wrote in `flows.trend`
// (collector/modules/flows.py): `own` = our daily NSE rows summed by month (the only DII history there is), `nsdl` = the
// depository's final FPI equity figures by month and financial year, plus FPI money into primary issues this month, and
// `facts`. Two different series, labelled apart, never merged; the page adds nothing up.
let ftView = "d";
const ftMon = (ym, o) => new Date(ym + "-01T00:00:00").toLocaleDateString("en-IN", { month: o || "long" });
$("#ftView").addEventListener("click", e => { const b = e.target.closest("button[data-ft]"); if (b) { ftView = b.dataset.ft; renderMarket(); } });

function ftChart(c) {
  const F = DATA.flows || {}, N = (F.trend || {}).nsdl;
  if (!N) ftView = "d";
  $("#ftView").style.display = N ? "" : "none";      // `.filters` is display:flex, which beats the hidden attribute
  $$("#ftView button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.ft === ftView)));
  const tip = { callbacks: { label: x => `${x.dataset.label}: ${sgn(Math.round(x.raw))} Cr` } }, legend = { position: "bottom", labels: { color: c.text, boxWidth: 10 } };
  if (ftView === "d") {
    const H = (F.history || []).slice(-20); let run = 0; const cum = H.map(r => (run += (r[1] || 0) + (r[2] || 0)));
    return new Chart($("#flowsChart2"), { data: { labels: H.map(r => fmtD(r[0])), datasets: [
        { type: "line", label: "Cumulative FII + DII", data: cum, borderColor: c.lav, backgroundColor: c.lav + "22", fill: true, borderWidth: 2, pointRadius: 0, tension: .25, yAxisID: "y1", order: 0 },
        { type: "bar", label: "FII net", data: H.map(r => r[1]), backgroundColor: H.map(r => r[1] >= 0 ? c.up : c.down), borderRadius: 3, maxBarThickness: 16, order: 1 },
        { type: "bar", label: "DII net", data: H.map(r => r[2]), backgroundColor: c.acc + "aa", borderRadius: 3, maxBarThickness: 16, order: 1 }] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, plugins: { legend, tooltip: tip },
        scales: { x: { type: "category", ticks: { color: c.text, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } }, y: { type: "linear", title: { display: true, text: "₹ Cr a day", color: c.text }, ticks: { color: c.text }, grid: { color: c.grid } }, y1: { type: "linear", position: "right", title: { display: true, text: "cumulative ₹ Cr", color: c.text }, ticks: { color: c.text }, grid: { display: false } } } } });
  }
  const byM = ftView === "m", rows = (byM ? N.months : N.years) || [], last = rows.length - 1;
  const labels = rows.map((r, i) => (byM ? ftMon(r[0], "short") : r[0].slice(2)) + (i === last ? "*" : ""));
  return new Chart($("#flowsChart2"), { type: "bar", data: { labels, datasets: [
      { label: `FPI equity, net by ${byM ? "month, " + N.year : "financial year"} · NSDL final · * to ${fmtD(N.asOf)}`, data: rows.map(r => r[1]), backgroundColor: rows.map(r => r[1] >= 0 ? c.up : c.down), borderRadius: 3, maxBarThickness: 26 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: c.text, boxWidth: 0 } }, tooltip: tip },
      scales: { x: { type: "category", ticks: { color: c.text, maxRotation: 0, autoSkip: true }, grid: { display: false } }, y: { type: "linear", title: { display: true, text: "₹ Cr", color: c.text }, ticks: { color: c.text }, grid: { color: c.grid } } } } });
}

function renderFtTotals() {
  const T = (DATA.flows || {}).trend || {}, own = T.own || [], N = T.nsdl, box = $("#ftBox");
  const cur = own[own.length - 1], was = own[own.length - 2];
  box.hidden = !cur && !N; if (box.hidden) return;
  const tile = (l, v, d1) => `<div class="kpi card"><div class="lbl">${l}</div><div class="v mono ${cls(v)}">${sgn(Math.round(v))} Cr</div><div class="d">${d1}</div></div>`;
  const before = k => was ? `<br>${ftMon(was.m)}${was === own[0] && +was.from.slice(8) > 5 ? " from " + fmtD(was.from) : ""}: ${sgn(Math.round(was[k]))} Cr` : "";
  const side = (k, up1) => `bought on ${cur[up1]} of ${cur.n} sessions · to ${fmtD(cur.to)}${before(k)}`;
  const P = N && N.primary, t = [];
  if (cur) t.push(tile(`FII · ${ftMon(cur.m)} so far`, cur.fii, side("fii", "fiiUp")), tile(`DII · ${ftMon(cur.m)} so far`, cur.dii, side("dii", "diiUp")));
  if (N) t.push(tile(`FPI equity · ${N.year} so far`, N.ytd, `NSDL final figures · to ${fmtD(N.asOf)}<br>cash and primary market together`));
  if (P) t.push(tile(`FPI into primary issues · ${ftMon(P.month)}`, P.net, `${P.days} reporting days · NSDL${P.top ? `<br>${sgn(Math.round(P.top.net))} Cr of it reported ${fmtD(P.top.date)}` : ""}`));
  $("#ftTotals").innerHTML = t.join("");
  $("#ftFacts").innerHTML = (T.facts || []).map(f => `<span>${esc(f)}</span>`).join("");
  $("#ftNote").textContent = `Two series, side by side, never added together: NSE's provisional cash figures (FII and DII, a row a session${own[0] ? ", on file since " + fmtDY(own[0].from) : ""}) and NSDL's final FPI figures${N ? " (months of " + N.year + ", financial years since " + N.since + ")" : " (none on file yet)"}. No source publishes DII by month or year.`;
}
