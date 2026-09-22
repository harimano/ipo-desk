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
  // measured: what the price did over the first five trading days after a 30-day lock opened, per segment, from the
  // collector's frozen record (evidence.lockins) — n and the interval come with it; nothing on file reads as nothing
  const ev = $("#lockinEv"); if (ev) { const line = k => { const L = (SEG(k === "sme") || {}).lockin; if (!L || !L.n) return `${k === "sme" ? "SME" : "Mainboard"}: no 30-day unlock with five days of price path on file yet`;
      return `${k === "sme" ? "SME" : "Mainboard"}: after ${L.n} unlock${L.n === 1 ? "" : "s"} since ${fmtD(L.since)}, the price was up ${L.days} days later in ${Math.round(L.pos)}% of cases (95% range ${Math.round(L.lo)}–${Math.round(L.hi)}%) · median ${pct(L.med, true)} · 10th–90th ${pct(L.p10, true)} to ${pct(L.p90, true)}`; };
    ev.innerHTML = `<b>Measured, not assumed:</b> ${line("main")} · ${line("sme")}. The record started 22 Sep 2026 and only grows.`; }
}

/* ---- the trackers on the Today queue: only for listings Hari holds or starred, and for names he follows ---- */
function trackerQueueItems() {
  const P = [], mineOf = n => held(n) ? "you hold" : S.interest.has(n) ? "starred" : null;
  const perf = new Map((DATA.listedPerf || []).map(p => [p.name, p])), deals = (DATA.investors || {}).listingDeals || [];
  (DATA.anchors || []).forEach(a => { const m = mineOf(a.name); if (!m) return;
    [["lockIn30", "half", 0.5], ["lockIn90", "the rest", 0.5]].forEach(([k, lbl, share]) => { const d = a[k]; if (!d) return; const n = days(d); if (n < -3 || n > 7) return;
      const free = a.amountCr != null ? cr(a.amountCr * share) : "an unknown amount", sold = deals.filter(r => r.stock === a.name && r.side === "SELL" && r.date >= d), soldCr = sold.reduce((s, r) => s + (r.valueCr || 0), 0), p = perf.get(a.name) || {};
      P.push({ id: `lock:${a.name}:${k}`, pri: n <= 0 ? 1 : 2, tag: [n <= 0 ? "now" : "soon", n === 0 ? "Lock-in opens today" : n < 0 ? `Lock-in opened ${rel(n)}` : `Lock-in opens ${rel(n)}`], lbl: `Anchor lock-in · ${m}`,
        ttl: `${a.name} — ${lbl} of the anchor book (${free}) ${n <= 0 ? "is" : "becomes"} free to sell`, b: { name: a.name },
        desc: `${a.amountCr ? `Anchor book ${cr(a.amountCr)}${a.issueSizeCr ? `, ${Math.round(a.amountCr / a.issueSizeCr * 100)}% of the issue` : ""}. ` : ""}${p.ltp && p.issue ? `Now ${inr(p.ltp)}, ${pct((p.ltp - p.issue) / p.issue * 100, true)} vs issue. ` : ""}${n <= 0 ? (sold.length ? `On the tape since: <b class="down">${cr(soldCr)}</b> sold in ${sold.length} bulk/block deal${sold.length === 1 ? "" : "s"}.` : "No bulk or block sale on NSE since it opened.") : "Whether anyone sells is the tape's to tell — the Superinvestors tab counts it from that day."}`,
        acts: [["done", "Seen"], ["snooze", "Snooze"]] }); }); });
  const latest = deals.reduce((m, r) => r.date > m ? r.date : m, "");
  if (latest && days(latest) >= -3) {
    const byStock = {};
    deals.filter(r => r.date === latest).forEach(r => { (byStock[r.stock] = byStock[r.stock] || []).push(r); });
    Object.entries(byStock).forEach(([stock, rows]) => { const m = mineOf(stock); if (!m) return;
      const pairs = ldPairs(rows), stayed = pairs.filter(x => x.beh === "net buyer").reduce((s, x) => s + x.net, 0), left = pairs.filter(x => x.beh === "net seller").reduce((s, x) => s - x.net, 0);
      P.push({ id: `tape:${stock}:${latest}`, pri: 3, tag: ["soon", `Deals ${days(latest) === 0 ? "today" : fmtD(latest)}`], lbl: `On the tape · ${m}`, b: { name: stock },
        ttl: `${stock} — ${rows.length} bulk/block deal${rows.length === 1 ? "" : "s"} by ${new Set(rows.map(r => r.client)).size} name${new Set(rows.map(r => r.client)).size === 1 ? "" : "s"}`,
        desc: `${pairs.filter(x => x.beh === "round-trip").length} round-trip · ${pairs.filter(x => x.beh === "net buyer").length} net buyer · ${pairs.filter(x => x.beh === "net seller").length} net seller. ${stayed >= 0.5 ? `<b class="up">${cr(stayed)} stayed</b>` : "Nothing stayed"}${left >= 0.5 ? ` · <b class="down">${cr(left)} left</b>` : ""}. Names and rows are on the Superinvestors tab.`,
        acts: [["done", "Seen"], ["snooze", "Snooze"]] }); });
    const mine = deals.filter(r => r.date === latest && follows(r.client));
    if (mine.length) { const names = [...new Set(mine.map(r => r.client))];
      P.push({ id: `names:${latest}`, pri: 3, tag: ["ok", `Your names ${days(latest) === 0 ? "today" : fmtD(latest)}`], lbl: "Followed investors",
        ttl: `${names.length === 1 ? names[0] : names.length + " names you follow"} on the tape in ${[...new Set(mine.map(r => r.stock))].join(", ")}`,
        desc: ldPairs(mine).map(x => `${esc(x.client)}: ${x.beh} in ${esc(x.stock)} (${cr(x.cb)} bought / ${cr(x.cs)} sold)`).join(" · "), acts: [["done", "Seen"]] }); }
  }
  return P;
}
