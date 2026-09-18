/* ================= QUOTA PLANNER — what it costs to be eligible, and by when =================
   Included into app.js (`@include quota.js`); shares live, Q, held, toggleHold, inr, inr0, fmtD, days, rel, esc, cls.
   The shareholder category is this desk's real edge (its book runs at a fraction of retail's), and the whole cost of
   entry is ONE share of the parent, held in the demat on the record date. Every figure here is fetched: the parent's
   price is `investors.prices[parent]` (collector/modules/parents.py prices every live quota row's ticker), stage /
   record date / lapse come from `quota`. "Held" is the viewer's own mark (localStorage `ipo-holdings`), never sent anywhere. */
function renderQuotaPlanner() {
  const el = $("#quotaPlan"); if (!el) return;
  const PX = (DATA.investors || {}).prices || {}, stageRank = { approved: 0, drhp: 1, awaited: 2 };
  const rows = live.filter(q => q.quota !== false).map(q => { const p = PX[q.parent] || {}, rd = q.recordDate ? days(q.recordDate) : null; return { q, px: p.value, pxAsOf: p.asOf, rd, lapse: q.lapse ? days(q.lapse) : null, has: held(q.parent) }; })
    .sort((a, b) => (a.rd == null) - (b.rd == null) || (a.rd || 0) - (b.rd || 0) || stageRank[a.q.bucket] - stageRank[b.q.bucket] || (a.q.rank || 0) - (b.q.rank || 0));
  const parents = {}; rows.forEach(r => { (parents[r.q.parent] = parents[r.q.parent] || { px: r.px, has: r.has, n: 0 }).n++; });
  const P = Object.values(parents), open = P.filter(p => !p.has), cost = open.reduce((s, p) => s + (p.px || 0), 0), unpriced = open.filter(p => !p.px).length;
  const kpi = (l, v, d2) => `<div class="card kpi"><div class="lbl">${l}</div><div class="v mono">${v}</div><div class="d">${d2}</div></div>`;
  const near = rows.filter(r => !r.has && (r.q.bucket === "approved" || r.rd != null));
  const when = r => r.rd != null ? (r.rd < 0 ? `<span class="dim">record date passed ${fmtD(r.q.recordDate)}</span>` : `<b class="${r.rd <= 7 ? "down" : "amb"}">record date ${fmtD(r.q.recordDate)}</b><div class="dt">buy by ${fmtD(new Date(d(r.q.recordDate).getTime() - 2 * DAY).toISOString().slice(0, 10))} · shares settle T+1</div>`)
    : r.q.bucket === "approved" ? `<span class="amb">not announced</span><div class="dt">comes with the RHP, often with a few days' notice</div>` : `<span class="dim">not yet</span><div class="dt">${r.q.bucket === "drhp" ? "DRHP filed — approval comes first" : "no DRHP yet"}</div>`;
  el.innerHTML = `<div class="kpis">${kpi("Parents covered", `${P.length - open.length} of ${P.length}`, `${rows.length} pipeline IPOs hang off them`)}
      ${kpi("To cover the rest", inr0(cost), `one share each of ${open.length} parent${open.length === 1 ? "" : "s"}${unpriced ? ` · ${unpriced} without a price` : ""}`)}
      ${kpi("Approved, parent not held", String(near.length), near.length ? esc(near.slice(0, 3).map(r => r.q.parent).join(", ")) + (near.length > 3 ? "…" : "") : "nothing urgent")}</div>
    <div class="card tw" style="margin-top:12px"><table><thead><tr><th>IPO</th><th>Parent to hold</th><th class="r">One share costs</th><th>Stage</th><th>Record date</th><th>Approval lapses</th><th class="r">Held?</th></tr></thead><tbody>${rows.map(r => `<tr data-row data-name="${esc(r.q.name)}">
      <td><div class="nm"><button data-sheet="${esc(r.q.name)}">${esc(r.q.name)}</button></div><div class="dt">${r.q.sizeCr ? "₹" + Number(r.q.sizeCr).toLocaleString("en-IN") + " Cr" : "size not known"}${r.q.quotaPct ? " · " + r.q.quotaPct + "% reserved for shareholders" : r.q.quota === true ? " · shareholder quota confirmed" : " · quota not confirmed yet"}</div></td>
      <td>${esc(r.q.parent)}<div class="dt">${esc(r.q.ticker || "")}</div></td>
      <td class="r num">${r.px ? inr(r.px) : `<span class="dim">no price</span>`}<div class="dt">${r.pxAsOf ? fmtD(r.pxAsOf) : ""}</div></td>
      <td><span class="pill ${r.q.bucket === "approved" ? "ok" : r.q.bucket === "drhp" ? "soon" : "plan"}">${esc(r.q.stage || r.q.bucket)}</span>${r.q.expectedWindow ? `<div class="dt" style="max-width:260px">${esc(r.q.expectedWindow)}</div>` : ""}</td>
      <td>${when(r)}</td>
      <td>${r.lapse == null ? `<span class="dim">—</span>` : `<span class="${r.lapse <= 30 ? "down" : ""}">${fmtD(r.q.lapse)}</span><div class="dt">${rel(r.lapse)}</div>`}</td>
      <td class="r"><button class="btn sm${r.has ? " primary" : ""}" data-hold="${esc(r.q.parent)}">${r.has ? "Held ✓" : "Mark held"}</button></td></tr>`).join("") || `<tr><td colspan="7" class="empty">No quota IPOs in the pipeline.</td></tr>`}</tbody></table></div>
    <div class="dt" style="margin-top:8px">The share must be in the demat on the record date, so it has to be bought at least two trading days before. The price of one share is the whole cost of entry; its own price risk is yours and is not netted anywhere on this desk. "Held" is your mark, kept in this browser only.</div>`;
}
document.addEventListener("click", e => { const b = e.target.closest("#quotaPlan button"); if (!b) return;
  if (b.dataset.hold != null) { toggleHold(b.dataset.hold); renderAll(); } else if (b.dataset.sheet != null) { sheets[b.dataset.sheet] ? openSheet(b.dataset.sheet) : openPipe(b.dataset.sheet); } });
