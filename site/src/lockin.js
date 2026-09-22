/* ================= ANCHOR LOCK-INS — when anchor shares in this year's listings become free to sell =================
   Included into app.js (`@include lockin.js`); shares $, esc, cr, inr, fmtD, days, rel, pct, cls, held, S. Reads
   anchors[] (details: book size, bid date, both expiries; rows stay 150 days), listedPerf (price now vs issue) and
   investors.listingDeals (what was sold in that stock since the lock opened). Half of an anchor's allotment is locked
   for 30 days from allotment, the rest for 90 — a rule, so the dates are facts; whether anyone sells is the tape's to
   tell, and the deals column reports it. No verdict. */
const LI_BACK = 10, LI_AHEAD = 45, LI_NEAR = 14;     // rows inside LI_NEAR days show at once; the rest fold
function renderLockins() {
  const host = $("#lockins"); if (!host) return;
  const perf = new Map((DATA.listedPerf || []).map(p => [p.name, p])), seg = new Map(allIssues().map(b => [b.name, !!b.sme]));
  const deals = (DATA.investors || {}).listingDeals || [];
  const rows = [];
  (DATA.anchors || []).forEach(a => { const p = perf.get(a.name) || {}, sme = seg.has(a.name) ? seg.get(a.name) : !!p.sme;
    [["lockIn30", 0.5, "half"], ["lockIn90", 0.5, "rest"]].forEach(([k, share, lbl]) => { const d = a[k]; if (!d) return; const n = days(d); if (n < -LI_BACK || n > LI_AHEAD) return;
      const sold = deals.filter(r => r.stock === a.name && r.side === "SELL" && r.date >= d), soldCr = sold.reduce((s, r) => s + (r.valueCr || 0), 0);
      rows.push({ name: a.name, sme, date: d, n, lbl, free: a.amountCr != null ? a.amountCr * share : null, book: a.amountCr, pctIssue: a.amountCr && a.issueSizeCr ? a.amountCr / a.issueSizeCr * 100 : null,
        ltp: p.ltp, issue: p.issue, vs: p.ltp && p.issue ? (p.ltp - p.issue) / p.issue * 100 : null, sold: sold.length, soldCr, names: new Set(sold.map(r => r.client)).size, mine: held(a.name) || S.interest.has(a.name) }); }); });
  rows.sort((x, y) => x.date.localeCompare(y.date) || (y.free || 0) - (x.free || 0));
  const segPill = sme => `<span class="pill ${sme ? "plan" : "soon"}" style="height:17px;font-size:10.5px">${sme ? "SME" : "Main"}</span>`;
  const when = r => r.n === 0 ? `<span class="pill now">today</span>` : r.n < 0 ? `<span class="dt">${fmtD(r.date)} · ${rel(r.n)}</span>` : r.n <= 7 ? `<span class="pill soon">${fmtD(r.date)} · ${rel(r.n)}</span>` : `<span class="dt">${fmtD(r.date)} · ${rel(r.n)}</span>`;
  const near = rows.filter(r => r.n <= LI_NEAR || r.mine), far = rows.filter(r => !(r.n <= LI_NEAR || r.mine));
  const tr = r => `<tr${r.mine ? ` style="box-shadow:inset 3px 0 0 var(--up)"` : ""}>
    <td class="nm" data-row data-name="${esc(r.name)}">${esc(r.name)} ${segPill(r.sme)}${r.mine ? ` <span class="pill ok" style="height:17px;font-size:10.5px">${held(r.name) ? "you hold" : "starred"}</span>` : ""}</td>
    <td style="white-space:nowrap">${when(r)}<div class="dt">${r.lbl === "half" ? "half · 30 days" : "the rest · 90 days"}</div></td>
    <td class="r num">${r.free != null ? cr(r.free) : "—"}</td>
    <td class="r num dt">${r.book != null ? cr(r.book) : "—"}${r.pctIssue ? `<div>${Math.round(r.pctIssue)}% of issue</div>` : ""}</td>
    <td class="r num ${cls(r.vs)}">${r.vs == null ? "—" : pct(r.vs, true)}${r.ltp ? `<div class="dt">${inr(r.ltp)}</div>` : ""}</td>
    <td class="dt">${r.n > 0 ? "not yet open" : r.sold ? `<b class="down">${cr(r.soldCr)}</b> in ${r.sold} deal${r.sold === 1 ? "" : "s"} by ${r.names} name${r.names === 1 ? "" : "s"}` : "no bulk or block sale on NSE"}</td></tr>`;
  const head = `<thead><tr><th>Stock</th><th>Unlocks</th><th class="r">Free to sell</th><th class="r">Anchor book</th><th class="r">Now vs issue</th><th>Sold since, on the tape</th></tr></thead>`;
  host.innerHTML = `${head}<tbody>${near.map(tr).join("") || `<tr><td colspan="6" class="empty">No anchor lock-in opens in the next ${LI_NEAR} days.</td></tr>`}</tbody>`;
  const more = $("#lockinMore"); if (more) { more.hidden = !far.length; more.innerHTML = far.length ? `<summary>${far.length} more between ${fmtD(far[0].date)} and ${fmtD(far[far.length - 1].date)} ▾</summary><div class="tw"><table>${head}<tbody>${far.map(tr).join("")}</tbody></table></div>` : ""; }
  const sub = $("#lockinSub"); if (sub) sub.textContent = `${rows.filter(r => r.n >= 0).length} opening in the next ${LI_AHEAD} days · ${rows.filter(r => r.n < 0).length} opened in the last ${LI_BACK}`;
}
