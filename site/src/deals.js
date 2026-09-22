/* ================= DEALS — every bulk / block deal in this year's listings =================
   Included into app.js (`@include deals.js`); shares $, $$, esc, cr, inr, fmtD, pct, cls. `investors.listingDeals` is
   written by collector/modules/deals.py: every deal in NSE's daily bulk + block files whose stock listed this year, whoever
   the client is, 60 days, `sme` on every row. The page filters, groups and counts; it never scores or advises. Mainboard
   and SME are never pooled in a number: the segment filter picks one, and "All" only lists rows side by side. */
let ldScope = "all", ldSide = "all";
const LD_NET_DAYS = 30, LD_ROWS = 80;
const ldSigned = v => Math.abs(v) < 0.5 ? "net 0" : (v > 0 ? "+" : "−") + cr(Math.abs(v));
{ const f = $("#ldFilters"); if (f) f.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.ldSc) ldScope = b.dataset.ldSc; else if (b.dataset.ldSide) ldSide = b.dataset.ldSide; renderListingDeals(); }); }

function renderListingDeals() {
  const T = $("#ldTable"); if (!T) return;
  const I = DATA.investors || {}, all = I.listingDeals;
  $$("#ldFilters button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.ldSc ? b.dataset.ldSc === ldScope : b.dataset.ldSide === ldSide)));
  const segOk = r => ldScope === "all" || (ldScope === "sme") === !!r.sme;
  const scoped = (all || []).filter(segOk), rows = scoped.filter(r => ldSide === "all" || r.side === ldSide);
  const segPill = r => `<span class="pill ${r.sme ? "plan" : "soon"}" style="height:17px;font-size:10.5px">${r.sme ? "SME" : "Main"}</span>`;
  const empty = all == null ? "The collector has not written this yet — it fills on the next full run."
    : all.length === 0 ? "No bulk or block deal in this year's NSE listings in the last 60 days."
    : "Nothing under this filter.";
  T.innerHTML = `<thead><tr><th>Date</th><th>Stock</th><th>Client</th><th>Side</th><th class="r">Qty</th><th class="r">Price</th><th class="r">vs issue</th><th class="r">Value</th></tr></thead><tbody>${rows.slice(0, LD_ROWS).map(r => `<tr>
    <td class="dt" style="white-space:nowrap">${fmtD(r.date)}</td>
    <td class="nm" data-row data-name="${esc(r.stock)}">${esc(r.stock)}<div class="dt">${segPill(r)} ${r.daysSinceListing != null ? `day ${r.daysSinceListing} after listing` : ""}${r.kind === "block" ? " · block" : ""}</div></td>
    <td class="dt${follows(r.client) ? " up" : ""}" title="${esc(r.client)}">${esc((r.client || "").slice(0, 34))}${(r.client || "").length > 34 ? "…" : ""} <button class="fbtn" data-follow="${esc(r.client)}" title="${follows(r.client) ? "Following" : "Follow this name"}">${follows(r.client) ? "✓" : "+"}</button></td>
    <td><span class="pill ${r.side === "BUY" ? "ok" : "now"}">${esc(r.side)}</span></td>
    <td class="r num">${r.qty ? Number(r.qty).toLocaleString("en-IN") : "—"}</td>
    <td class="r num">${r.price ? inr(r.price) : "—"}</td>
    <td class="r num ${cls(r.vsIssuePct)}">${r.vsIssuePct == null ? "—" : pct(r.vsIssuePct, true)}${r.issuePrice ? `<div class="dt">issue ${inr(r.issuePrice)}</div>` : ""}</td>
    <td class="r num">${r.valueCr != null ? cr(r.valueCr) : "—"}</td></tr>`).join("") || `<tr><td colspan="8" class="empty">${empty}</td></tr>`}</tbody>`;
  const noSym = Object.values(I.listingSymbols || {}).filter(v => v && !v.symbol).length;
  const sub = $("#ldSub"); if (sub) sub.textContent = `${rows.length} deal${rows.length === 1 ? "" : "s"}${rows.length > LD_ROWS ? ` · showing the newest ${LD_ROWS}` : ""} · last 60 days`;
  const note = $("#ldNote"); if (note) note.textContent = all && all.length ? `NSE's files only: ${noSym ? `${noSym} of this year's listings trade only on BSE and cannot appear here. ` : ""}A desk that buys and sells the same day is on both sides; the net bar shows what stayed.` : "";
  // net by stock, last 30 days — bought minus sold, in crore, under the segment filter (both sides always)
  const cutoff = new Date(Date.now() - LD_NET_DAYS * 864e5).toISOString().slice(0, 10);
  const byStock = {};
  scoped.filter(r => (r.date || "") >= cutoff).forEach(r => { const s = byStock[r.stock] = byStock[r.stock] || { stock: r.stock, sme: r.sme, b: 0, s: 0, n: 0, clients: new Set() };
    if (r.valueCr) { if (r.side === "BUY") s.b += r.valueCr; else s.s += r.valueCr; } s.n++; s.clients.add(r.client); });
  const net = Object.values(byStock).map(s => ({ ...s, net: s.b - s.s })).sort((x, y) => Math.abs(y.net) - Math.abs(x.net));
  const mx = Math.max(1, ...net.map(s => Math.max(s.b, s.s)));
  // sold grows left from the centre, bought grows right: a desk that round-trips shows as two equal arms and a net near zero
  const N = $("#ldNet"); if (N) N.innerHTML = net.length ? net.map(s => `<div class="hb two"><div class="n wrap" title="bought ${cr(s.b)} · sold ${cr(s.s)}">${esc(s.stock)}<small>${s.n} deals · ${s.clients.size} names</small></div><div class="bar"><i class="s down" style="width:${s.s / mx * 50}%"></i><i class="b up" style="width:${s.b / mx * 50}%"></i></div><div class="v num ${cls(Math.abs(s.net) < 0.5 ? 0 : s.net)}" title="bought ${cr(s.b)} · sold ${cr(s.s)}">${ldSigned(s.net)}</div></div>`).join("")
      + `<div class="dt" style="margin-top:4px"><i style="display:inline-block;width:10px;height:8px;border-radius:2px;background:var(--down);vertical-align:middle"></i> sold ← centre → bought <i style="display:inline-block;width:10px;height:8px;border-radius:2px;background:var(--up);vertical-align:middle"></i> · largest arm ${cr(mx)}</div>`
    : `<div class="dim" style="font-size:12.5px">No deal in the last ${LD_NET_DAYS} days.</div>`;
  // repeat clients — counts only
  const byClient = {};
  rows.forEach(r => { const c = byClient[r.client] = byClient[r.client] || { client: r.client, n: 0, stocks: new Set(), b: 0, s: 0 };
    c.n++; c.stocks.add(r.stock); if (r.valueCr) { if (r.side === "BUY") c.b += r.valueCr; else c.s += r.valueCr; } });
  const rep = Object.values(byClient).filter(c => c.n >= 2).sort((x, y) => y.n - x.n || (y.b + y.s) - (x.b + x.s)).slice(0, 15);
  const C = $("#ldClients"); if (C) C.innerHTML = `<thead><tr><th>Client</th><th class="r">Deals</th><th class="r">Stocks</th><th class="r">Bought</th><th class="r">Sold</th><th class="r">Net</th></tr></thead><tbody>${rep.map(c => `<tr><td class="nm${follows(c.client) ? " up" : ""}" title="${esc(c.client)}">${esc((c.client || "").slice(0, 32))}${(c.client || "").length > 32 ? "…" : ""} <button class="fbtn" data-follow="${esc(c.client)}" title="${follows(c.client) ? "Following" : "Follow this name"}">${follows(c.client) ? "✓" : "+"}</button></td><td class="r num">${c.n}</td><td class="r num">${c.stocks.size}</td><td class="r num">${cr(c.b)}</td><td class="r num">${cr(c.s)}</td><td class="r num ${cls(Math.abs(c.b - c.s) < 0.5 ? 0 : c.b - c.s)}">${ldSigned(c.b - c.s)}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">No name appears twice under this filter.</td></tr>`}</tbody>`;
}
