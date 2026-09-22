/* ================= DEALS — every bulk / block deal in this year's listings, as trackers =================
   Included into app.js (`@include deals.js`); shares $, $$, esc, cr, inr, fmtD, pct, cls, days, held, S, follows.
   `investors.listingDeals` is written by collector/modules/deals.py: every deal in NSE's daily bulk + block files whose
   stock listed this year, whoever the client is, 60 days, `sme` on every row. The page groups and counts; it never scores
   or advises. Mainboard and SME are never pooled in a number: the segment filter picks one, "All" only lists side by side.

   Three views of the same rows:
   1. one tracker per stock — price now vs issue, deals and names, how many round-tripped vs stayed, the two-sided bar
      (sold ← centre → bought), the latest day's names, and every row folded under it;
   2. money that stayed — client × stock pairs that are net long after their deals (a fact, not a recommendation);
   3. repeat clients — names in two or more deals, with what they did in each stock.
   Behaviour of a client in a stock, from quantities: round-trip = bought and sold within 20% of each other; net buyer /
   net seller otherwise. Counts only. */
let ldScope = "all", ldMine = false;
const LD_ROUNDTRIP = 0.8;
const ldSigned = v => Math.abs(v) < 0.5 ? "net 0" : (v > 0 ? "+" : "−") + cr(Math.abs(v));
const ldBehaviour = p => { const lo = Math.min(p.qb, p.qs), hi = Math.max(p.qb, p.qs); return hi && lo / hi >= LD_ROUNDTRIP ? "round-trip" : p.qb > p.qs ? "net buyer" : "net seller"; };
const ldBehCls = b => b === "net buyer" ? "ok" : b === "net seller" ? "now" : "plan";
{ const f = $("#ldFilters"); if (f) f.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.ldSc) ldScope = b.dataset.ldSc; else if (b.dataset.ldMine) ldMine = !ldMine; renderListingDeals(); }); }

function ldPairs(rows) {
  // client × stock: quantities and crore each way, dates, behaviour
  const P = {};
  rows.forEach(r => { const k = r.client + "\u0000" + r.stock, p = P[k] = P[k] || { client: r.client, stock: r.stock, sme: r.sme, qb: 0, qs: 0, cb: 0, cs: 0, n: 0, first: r.date, last: r.date };
    if (r.side === "BUY") { p.qb += r.qty || 0; p.cb += r.valueCr || 0; } else { p.qs += r.qty || 0; p.cs += r.valueCr || 0; }
    p.n++; if (r.date < p.first) p.first = r.date; if (r.date > p.last) p.last = r.date; });
  return Object.values(P).map(p => ({ ...p, net: p.cb - p.cs, beh: ldBehaviour(p) }));
}

/* price path since listing, from priceHistory (tape: one close a trading day for every listing this year). Marks: deal days
   (green = net bought that day, red = net sold, grey = round-trip), and the anchor lock-in dates. Drawing, not arithmetic. */
function ldSpark(name, rows, A1) {
  const ph = ((DATA.priceHistory || {})[name] || []).filter(p => Array.isArray(p) && p[1] != null).sort((x, y) => String(x[0]).localeCompare(String(y[0])));
  if (ph.length < 2) return "";
  const W = 320, H = 44, pad = 3, xs = ph.map(p => new Date(p[0]).getTime()), ys = ph.map(p => p[1]);
  const x0 = xs[0], x1 = xs[xs.length - 1] || x0 + 1, lo = Math.min(...ys), hi = Math.max(...ys);
  const X = t => pad + (W - 2 * pad) * (x1 === x0 ? 1 : (t - x0) / (x1 - x0)), Y = v => H - pad - (H - 2 * pad) * (hi === lo ? 0.5 : (v - lo) / (hi - lo));
  const path = ph.map((p, i) => `${i ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join("");
  const byDay = {}; rows.forEach(r => { byDay[r.date] = (byDay[r.date] || 0) + (r.side === "BUY" ? 1 : -1) * (r.valueCr || 0); });
  const marks = Object.entries(byDay).map(([d, net]) => { const t = new Date(d).getTime(); if (t < x0 || t > x1) return ""; const i = ph.findIndex(p => String(p[0]) >= d), y = i >= 0 ? Y(ys[i]) : H / 2;
    return `<circle cx="${X(t).toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="var(--${Math.abs(net) < 0.5 ? "ink-3" : net > 0 ? "up" : "down"})"><title>${fmtD(d)}: ${ldSigned(net)}</title></circle>`; }).join("");
  const locks = A1 ? [["lockIn30", "30-day lock-in opens"], ["lockIn90", "90-day lock-in opens"]].map(([k, l]) => { const d = A1[k]; if (!d) return ""; const t = new Date(d).getTime(); if (t < x0 || t > x1) return "";
    return `<line x1="${X(t).toFixed(1)}" x2="${X(t).toFixed(1)}" y1="0" y2="${H}" stroke="var(--amber)" stroke-dasharray="2 2"><title>${l} ${fmtD(d)}</title></line>`; }).join("") : "";
  return `<svg class="ldspark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="price since listing"><path d="${path}" fill="none" stroke="var(--accent)" stroke-width="1.5"/>${locks}${marks}</svg><div class="dt" style="display:flex;justify-content:space-between"><span>${fmtD(ph[0][0])} ${inr(ys[0])}</span><span>${ph.length} closes</span><span>${fmtD(ph[ph.length - 1][0])} ${inr(ys[ys.length - 1])}</span></div>`;
}

const lastClose = name => { const ph = (DATA.priceHistory || {})[name] || []; const last = ph.filter(x => Array.isArray(x) && x[1] != null).sort((a, b) => String(a[0]).localeCompare(String(b[0]))).pop(); return last ? last[1] : null; };   // the tape's latest close when the report has no LTP yet (a listing on its first day)

function renderListingDeals() {
  const host = $("#ldStocks"); if (!host) return;
  const I = DATA.investors || {}, all = I.listingDeals;
  $$("#ldFilters button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.ldSc ? b.dataset.ldSc === ldScope : ldMine)));
  const segOk = r => ldScope === "all" || (ldScope === "sme") === !!r.sme;
  const mine = n => held(n) || S.interest.has(n);
  const rows = (all || []).filter(segOk).filter(r => !ldMine || mine(r.stock));
  const latest = rows.reduce((m, r) => r.date > m ? r.date : m, "");
  const perf = new Map((DATA.listedPerf || []).map(p => [p.name, p]));
  const segPill = sme => `<span class="pill ${sme ? "plan" : "soon"}" style="height:17px;font-size:10.5px">${sme ? "SME" : "Main"}</span>`;
  const fb = name => `<button class="fbtn" data-follow="${esc(name)}" title="${follows(name) ? "Following" : "Follow this name"}">${follows(name) ? "✓" : "+"}</button>`;
  const short = s => (s || "").replace(/\b(PRIVATE|PVT\.?|LIMITED|LTD\.?|LLP)\b/g, "").replace(/\s+/g, " ").trim();
  // ---- 1. stock trackers
  const byStock = {};
  rows.forEach(r => { const s = byStock[r.stock] = byStock[r.stock] || { stock: r.stock, sme: r.sme, listedOn: r.listedOn, issue: r.issuePrice, rows: [] }; s.rows.push(r); });
  const stocks = Object.values(byStock).map(s => { const pairs = ldPairs(s.rows), b = s.rows.filter(r => r.side === "BUY").reduce((a, r) => a + (r.valueCr || 0), 0), sl = s.rows.filter(r => r.side === "SELL").reduce((a, r) => a + (r.valueCr || 0), 0);
    const last = s.rows.reduce((m, r) => r.date > m ? r.date : m, ""), p = perf.get(s.stock) || {};
    return { ...s, pairs, b, s: sl, net: b - sl, last, n: s.rows.length, names: new Set(s.rows.map(r => r.client)).size,
      rt: pairs.filter(x => x.beh === "round-trip").length, nb: pairs.filter(x => x.beh === "net buyer"), ns: pairs.filter(x => x.beh === "net seller").length,
      stayed: pairs.filter(x => x.beh === "net buyer").reduce((a, x) => a + x.net, 0), ltp: p.ltp || lastClose(s.stock), open: p.listing, mine: mine(s.stock) }; })
    .sort((x, y) => y.last.localeCompare(x.last) || y.n - x.n);
  const mx = Math.max(1, ...stocks.map(s => Math.max(s.b, s.s)));
  const empty = all == null ? "The collector has not written this yet — it fills on the next full run."
    : all.length === 0 ? "No bulk or block deal in this year's NSE listings in the last 60 days."
    : ldMine ? "None of your held or starred listings has a deal in the window." : "Nothing under this filter.";
  host.innerHTML = stocks.map(s => { const vs = s.ltp && s.issue ? (s.ltp - s.issue) / s.issue * 100 : null, op = s.open && s.issue ? (s.open - s.issue) / s.issue * 100 : null;
    const day = s.rows.filter(r => r.date === s.last), dayPairs = ldPairs(day).sort((x, y) => (y.cb + y.cs) - (x.cb + x.cs));
    return `<div class="ldc${s.mine ? " mine" : ""}">
      <div class="ldh"><b data-row data-name="${esc(s.stock)}">${esc(s.stock)}</b>${segPill(s.sme)}${s.mine ? `<span class="pill ok" style="height:17px;font-size:10.5px">${held(s.stock) ? "you hold" : "starred"}</span>` : ""}<span class="dt" style="margin-left:auto">listed ${fmtD(s.listedOn)}${s.listedOn ? ` · day ${-days(s.listedOn)}` : ""}</span></div>
      <div class="ldp">${s.ltp ? `<b class="num">${inr(s.ltp)}</b> now` : "no price on file"}${vs != null ? ` · <span class="num ${cls(vs)}">${pct(vs, true)}</span> vs issue ${inr(s.issue)}` : s.issue ? ` · issue ${inr(s.issue)}` : ""}${op != null ? ` · opened <span class="num ${cls(op)}">${pct(op, true)}</span>` : ""}</div>
      <div class="dt">${s.n} deals · ${s.names} names · <span title="bought and sold within 20% of each other">${s.rt} round-trip</span> · <span class="up">${s.nb.length} net buyer${s.nb.length === 1 ? "" : "s"}</span> · <span class="down">${s.ns} net seller${s.ns === 1 ? "" : "s"}</span></div>
      ${ldSpark(s.stock, s.rows, anchorFor(s.stock))}
      <div class="hb two"><div class="n" style="font-weight:500;color:var(--ink-3)" title="sold to the left of centre, bought to the right">sold│bought</div><div class="bar" title="sold ${cr(s.s)} · bought ${cr(s.b)}"><i class="s down" style="width:${s.s / mx * 50}%"></i><i class="b up" style="width:${s.b / mx * 50}%"></i></div><div class="v num ${cls(Math.abs(s.net) < 0.5 ? 0 : s.net)}">${ldSigned(s.net)}</div></div>
      <div class="dt">${s.stayed >= 0.5 ? `<b class="up">${cr(s.stayed)} stayed</b> with ${s.nb.length} name${s.nb.length === 1 ? "" : "s"}: ${s.nb.sort((x, y) => y.net - x.net).slice(0, 3).map(x => `${esc(short(x.client))}${fb(x.client)}`).join(", ")}${s.nb.length > 3 ? ` +${s.nb.length - 3}` : ""}` : "nothing stayed — every name that bought also sold"}</div>
      <div class="dt">${s.last === latest ? `<span class="pill now" style="height:17px;font-size:10.5px">new</span> ` : ""}latest ${fmtD(s.last)}: ${dayPairs.slice(0, 3).map(x => `${esc(short(x.client))} <span class="pill ${ldBehCls(x.beh)}" style="height:16px;font-size:10px">${x.beh}</span> ${cr(x.cb + x.cs)}`).join(" · ")}${dayPairs.length > 3 ? ` · +${dayPairs.length - 3} more` : ""}</div>
      ${(() => { const D = {}; s.rows.forEach(r => { D[r.date] = (D[r.date] || 0) + (r.side === "BUY" ? 1 : -1) * (r.valueCr || 0); }); const ds = Object.keys(D).sort(); return ds.length > 1 ? `<div class="dt">by day: ${ds.map(d => `${fmtD(d)} <span class="num ${cls(Math.abs(D[d]) < 0.5 ? 0 : D[d])}">${ldSigned(D[d])}</span>`).join(" · ")}</div>` : ""; })()}
      <details class="ldd"><summary>all ${s.n} deals ▾</summary><div class="tw"><table><thead><tr><th>Date</th><th>Client</th><th>Side</th><th class="r">Qty</th><th class="r">Price</th><th class="r">vs issue</th><th class="r">Value</th></tr></thead><tbody>${s.rows.map(r => `<tr><td class="dt" style="white-space:nowrap">${fmtD(r.date)}</td><td class="dt${follows(r.client) ? " up" : ""}" title="${esc(r.client)}">${esc(short(r.client).slice(0, 30))} ${fb(r.client)}</td><td><span class="pill ${r.side === "BUY" ? "ok" : "now"}">${esc(r.side)}</span></td><td class="r num">${r.qty ? Number(r.qty).toLocaleString("en-IN") : "—"}</td><td class="r num">${r.price ? inr(r.price) : "—"}</td><td class="r num ${cls(r.vsIssuePct)}">${r.vsIssuePct == null ? "—" : pct(r.vsIssuePct, true)}</td><td class="r num">${r.valueCr != null ? cr(r.valueCr) : "—"}</td></tr>`).join("")}</tbody></table></div></details>
    </div>`; }).join("") || `<div class="empty">${empty}</div>`;
  const sub = $("#ldSub"); if (sub) sub.textContent = `${stocks.length} stock${stocks.length === 1 ? "" : "s"} · ${rows.length} deal${rows.length === 1 ? "" : "s"} · last 60 days${latest ? ` · latest ${fmtD(latest)}` : ""}`;
  const bse = rows.filter(r => r.exchange === "BSE").length;
  const note = $("#ldNote"); if (note) note.textContent = all && all.length ? `NSE's and BSE's bulk and block files${bse ? ` (${bse} of these deals are BSE's)` : ""}; a listing that trades on both may show a deal on each. Round-trip = a name bought and sold within 20% of the same quantity, usually the same day. "Stayed" adds up what net buyers are still long after their deals — a fact about the tape, not about the stock.` : "";
  // ---- 2. money that stayed
  const pairs = ldPairs(rows), stayed = pairs.filter(p => p.beh === "net buyer" && p.net >= 0.5).sort((x, y) => y.net - x.net).slice(0, 20);
  const H = $("#ldHolders"); if (H) H.innerHTML = `<thead><tr><th>Name</th><th>Stock</th><th class="r">Net long</th><th class="r">Bought / sold</th><th>Last</th></tr></thead><tbody>${stayed.map(p => `<tr><td class="nm${follows(p.client) ? " up" : ""}" title="${esc(p.client)}">${esc(short(p.client).slice(0, 28))} ${fb(p.client)}</td><td class="dt" data-row data-name="${esc(p.stock)}">${esc(p.stock)} ${segPill(p.sme)}</td><td class="r num up">${cr(p.net)}</td><td class="r num dt">${cr(p.cb)} / ${cr(p.cs)}</td><td class="dt" style="white-space:nowrap">${fmtD(p.last)}${p.last === latest ? ` <span class="pill now" style="height:16px;font-size:10px">new</span>` : ""}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">No name is net long after its deals under this filter.</td></tr>`}</tbody>`;
  // ---- 3. repeat clients, with behaviour
  const byClient = {};
  pairs.forEach(p => { const c = byClient[p.client] = byClient[p.client] || { client: p.client, n: 0, stocks: 0, b: 0, s: 0, rt: 0, nb: 0, ns: 0 };
    c.n += p.n; c.stocks++; c.b += p.cb; c.s += p.cs; if (p.beh === "round-trip") c.rt++; else if (p.beh === "net buyer") c.nb++; else c.ns++; });
  const rep = Object.values(byClient).filter(c => c.n >= 2).sort((x, y) => y.n - x.n || (y.b + y.s) - (x.b + x.s)).slice(0, 15);
  // the record behind a name: what stocks did 20 trading days after this desk was a net buyer (evidence.deal_records, in
  // the lazy books part — loaded on demand, the table re-renders once it is here)
  const DR = recBooks && recBooks.trackRecords ? new Map((recBooks.trackRecords.deals || []).map(r => [r.key, r])) : null;
  if (!DR && (DATA.lazy || {}).books) loadBooks().then(b => { if (b) renderListingDeals(); });
  const record = c => { if (!DR) return `<span class="dim">…</span>`; const r = DR.get(recKey(c)); if (!r) return `<span class="dim">no position on record</span>`;
    const seg = ldScope === "sme" ? r.sme : r.main, bits = [];
    for (const [k, lbl] of [["buys", "after buys"], ["sells", "after sells"]]) { const x = seg && seg[k]; if (!x) continue; const m = x.d20 && x.d20.n ? x.d20 : x.d5 && x.d5.n ? x.d5 : null; const h = x.d20 && x.d20.n ? "+20d" : "+5d";
      bits.push(m ? `${lbl}: <b class="${m.pos >= 60 ? "up" : m.pos < 40 ? "down" : ""}">${Math.round(m.pos)}%</b> up ${h} <small class="dim">(${m.n}, ${Math.round(m.lo)}–${Math.round(m.hi)})</small> · median ${pct(m.med, true)}` : `${lbl}: ${x.n} on file, path not there yet`); }
    return bits.join("<br>") || `<span class="dim">no ${ldScope === "sme" ? "SME" : "mainboard"} position on record</span>`; };
  const C = $("#ldClients"); if (C) C.innerHTML = `<thead><tr><th>Client</th><th class="r">Deals</th><th class="r">Stocks</th><th>Behaviour</th><th class="r">Net</th><th>Record</th></tr></thead><tbody>${rep.map(c => `<tr><td class="nm${follows(c.client) ? " up" : ""}" title="${esc(c.client)}">${esc(short(c.client).slice(0, 28))} ${fb(c.client)}</td><td class="r num">${c.n}</td><td class="r num">${c.stocks}</td><td class="dt" style="white-space:nowrap">${[c.rt ? `${c.rt} round-trip` : "", c.nb ? `<span class="up">${c.nb} net buy</span>` : "", c.ns ? `<span class="down">${c.ns} net sell</span>` : ""].filter(Boolean).join(" · ")}</td><td class="r num ${cls(Math.abs(c.b - c.s) < 0.5 ? 0 : c.b - c.s)}">${ldSigned(c.b - c.s)}</td><td class="dt">${record(c.client)}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">No name appears twice under this filter.</td></tr>`}</tbody>`;
}
