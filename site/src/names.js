/* ================= YOUR NAMES — the investors Hari follows, wherever they appear =================
   Included into app.js (`@include names.js`); shares $, $$, esc, cr, fmtD, norm2, store, toast, watchNames, anchorFor,
   allIssues. The list is the tracked-names list (`investors.watchlist` from the sweep plus `ipo-investors` in this
   browser). Every name is matched, by normalised substring, against what the collector wrote today: the books of the
   largest anchors (players), the anchor letters on file (anchors[].investors), deals in this year's listings
   (investors.listingDeals, by client) and the tracked-name bulk deals (investors.bulkDeals, by investor). Counts and
   facts only — where a name is, not what to make of it. */
const followKey = s => norm2(String(s || "").replace(/\(.*?\)/g, "").replace(/\b(private|pvt|limited|ltd|llp|inc|co|plc|the)\b\.?/gi, ""));
function follows(name) { const c = followKey(name); if (c.length < 4) return false; return watchNames().some(w => { const k = followKey(w); return k.length >= 4 && (c.includes(k) || k.includes(c)); }); }
function toggleFollow(name) {
  const lst = store.get("ipo-investors", { add: [], remove: [] }) || { add: [], remove: [] }, I = DATA.investors || {};
  const hit = watchNames().find(w => { const k = followKey(w), c = followKey(name); return k.length >= 4 && c.length >= 4 && (c.includes(k) || k.includes(c)); });
  if (hit) { lst.add = (lst.add || []).filter(x => x !== hit); if ((I.watchlist || []).includes(hit)) lst.remove = [...new Set([...(lst.remove || []), hit])]; toast(`${hit} unfollowed`); }
  else { const v = String(name).trim(); lst.add = [...new Set([...(lst.add || []), v])]; lst.remove = (lst.remove || []).filter(x => x !== v); toast(`Following ${v}`); }
  store.set("ipo-investors", lst); renderMarket();
}
function renderYourNames() {
  const host = $("#yourNames"); if (!host) return;
  const I = DATA.investors || {}, P = DATA.players || {}, B = P.books || {}, names = P.names || {}, WL = watchNames();
  const cur = new Map(allIssues().filter(b => b.status !== "Listed").map(b => [b.name, b]));
  const cards = WL.map(w => {
    const k = followKey(w), is = s => { const c = followKey(s); return k.length >= 4 && c.length >= 4 && (c.includes(k) || k.includes(c)); };
    const books = Object.entries(B).filter(([id, L]) => L.some(x => is(x.name))).map(([id]) => names[id]).filter(Boolean);
    const letters = (DATA.anchors || []).filter(a => (a.investors || []).some(x => is(x.name))).map(a => { const x = a.investors.find(x => is(x.name)); return { name: a.name, amountCr: x.amountCr, pct: x.pct, live: cur.has(a.name) }; });
    const deals = (I.listingDeals || []).filter(d => is(d.client)), bulk = (I.bulkDeals || []).filter(d => is(d.investor) || is(d.vehicle));
    const b = deals.filter(d => d.side === "BUY").reduce((s, d) => s + (d.valueCr || 0), 0), s = deals.filter(d => d.side === "SELL").reduce((s, d) => s + (d.valueCr || 0), 0);
    const stocks = [...new Set(deals.map(d => d.stock))];
    const lines = [];
    if (books.length) lines.push(`<div><b>in ${books.length} current book${books.length > 1 ? "s" : ""}</b> as one of the largest anchors: ${books.map(esc).join(" · ")}</div>`);
    if (letters.length) lines.push(`<div><b>on ${letters.length} anchor letter${letters.length > 1 ? "s" : ""}</b>: ${letters.map(l => `${esc(l.name)}${l.amountCr ? ` ${cr(l.amountCr)}` : ""}${l.pct ? ` (${l.pct}% of the book)` : ""}${l.live ? "" : " · listed"}`).join(" · ")}</div>`);
    if (deals.length) lines.push(`<div><b>${deals.length} deal${deals.length > 1 ? "s" : ""} in this year's listings</b> (60 days): bought ${cr(b)} · sold ${cr(s)} · ${stocks.slice(0, 5).map(esc).join(", ")}${stocks.length > 5 ? ` +${stocks.length - 5}` : ""}</div>`);
    if (bulk.length) lines.push(`<div><b>${bulk.length} bulk / block deal${bulk.length > 1 ? "s" : ""}</b> (45 days): ${bulk.slice(0, 4).map(d => `${d.side === "BUY" ? "bought" : "sold"} ${esc(d.stock)}${d.valueCr ? ` ${cr(d.valueCr)}` : ""} ${fmtD(d.date)}`).join(" · ")}</div>`);
    const local = !(I.watchlist || []).includes(w);
    return `<div class="yn${lines.length ? "" : " quiet"}"><div class="ynh"><b>${esc(w)}</b>${local ? `<span class="pill plan" style="height:17px;font-size:10.5px" title="added in this browser">mine</span>` : ""}<button class="fbtn" data-follow="${esc(w)}" title="Unfollow">✕</button></div>${lines.join("") || `<div class="dt">not in any current anchor book, anchor letter or deal file today</div>`}</div>`;
  });
  host.innerHTML = cards.join("") || `<div class="dt">No names yet. Press + beside any anchor in a book below, or beside a client in the deals table, and it appears here with everything the collector sees it doing.</div>`;
}
{ const m = $("#s-market"); if (m) m.addEventListener("click", e => { const f = e.target.closest("[data-follow]"); if (f) { e.preventDefault(); e.stopPropagation(); toggleFollow(f.dataset.follow); } }); }
