/* ================= PLAYERS — which of the largest anchor investors are in today's books =================
   Included into app.js (`@include players.js`); shares esc, cr, fmtD, anchorFor, inr0. `players` is written by
   collector/modules/players.py: the N largest anchors' latest five IPOs, turned round into books for unlisted issues.
   Coverage is always stated ("18 of the 53 largest"): a book with no names is not an empty book, it is one the big
   funds are not in — which is itself worth knowing the evening before an issue opens. No track record: the feed does
   not give enough history for one, so none is shown. */
function playerCards(curIss) {
  const P = DATA.players || {}, B = P.books || {}; if (!P.tracked) return { html: "", named: new Set() };
  const named = new Set(), rows = curIss.filter(b => b.igId != null && B[String(b.igId)]);
  const html = rows.map(b => { named.add(b.name); const L = B[String(b.igId)], A1 = anchorFor(b.name), mx = Math.max(1, ...L.map(x => x.investedCr || 0));
    return `<div class="card acard pcard" style="display:block;grid-column:1/-1" data-row data-name="${esc(b.name)}"><div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap"><div class="nm">${esc(b.name)}</div><span class="pill ${b.status.toLowerCase()}">${b.status}</span>
      <span class="dt">${A1 && A1.amountCr ? `anchor book ${cr(A1.amountCr)}${A1.issueSizeCr ? " · " + Math.round(A1.amountCr / A1.issueSizeCr * 100) + "% of the issue" : ""}${A1.lockIn30 ? " · lock-in ends " + fmtD(A1.lockIn30) + " / " + fmtD(A1.lockIn90) : ""}` : ""}</span></div>
      <div class="dt" style="margin:6px 0 8px"><b style="color:var(--ink)">${L.length} of the ${P.tracked} largest anchor investors</b> are in this book · bar = what each has put into IPO anchor books over time</div>
      <div class="hbars pgrid">${L.slice(0, 12).map(x => `<div class="hb"><div class="n" title="${esc(x.name)}">${esc(x.name)}<small>${x.ipos} IPOs · average cheque ${x.ticketCr != null ? cr(x.ticketCr) : "—"}</small></div><div class="bar"><i class="lav grow" style="left:0;width:${Math.max(2, (x.investedCr || 0) / mx * 100).toFixed(1)}%"></i></div><div class="v num">${x.investedCr != null ? cr(x.investedCr) : "—"}</div></div>`).join("")}</div>
      ${L.length > 12 ? `<div class="dt" style="margin-top:6px">and ${L.length - 12} more: ${L.slice(12).map(x => esc(x.name)).join(" · ")}</div>` : ""}</div>`; }).join("");
  return { html, named };
}
const playersNote = () => { const P = DATA.players || {}; return P.tracked ? `Names come from the ${P.tracked} largest of ${(P.of || 0).toLocaleString("en-IN")} anchor investors on file (their latest ${P.latestPerInvestor || 5} IPOs each), read ${fmtD(P.asOf)}. A book with no name here is one the biggest funds are not in — small SME books are usually taken by local funds.` : ""; };
