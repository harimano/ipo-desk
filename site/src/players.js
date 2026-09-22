/* ================= ANCHORS ON THE BOARD — one line per current issue =================
   Included into app.js (`@include players.js`); shares $, esc, cr, fmtD, days, anchorFor, SEG, EDG, bandOf, edgeLbl, evShort,
   follows. `players` is written by collector/modules/players.py: the N largest anchors' latest five IPOs, turned round
   into books for unlisted issues, and `frozen{igId}` — each issue's line-up the day it listed. `evidence.segments[x].anchors`
   bands those frozen line-ups against the listing outcome (n + Wilson; accruing since Sep 2026, thin and said so).
   No per-investor track record: the feed does not give enough history for one, so none is shown. */
function anchorEvidence(b, large) {
  const seg = SEG(!!b.sme), A = seg && seg.anchors; if (!A || !A.n || large == null) return "";     // nothing frozen yet: the note says so once
  const ed = EDG("anchors"), i = bandOf(large, ed); if (i < 0) return "";
  const s = A.rows[i], lbl = edgeLbl(ed, i, "");
  return `<span class="dt" title="${b.sme ? "SME" : "Mainboard"} listings since ${fmtD(A.since)} whose line-up was frozen the day they listed: ${A.n} on file">past ${b.sme ? "SME" : "mainboard"} books with ${esc(lbl)} large anchors: ${evShort(s)}</span>`;
}
function playerCards(curIss) {
  const P = DATA.players || {}, B = P.books || {}, covered = new Set(P.covered || []);
  const named = new Set(), rows = curIss.slice().sort((x, y) => (x.open || "").localeCompare(y.open || ""));
  const later = [];
  const html = rows.map(b => {
    // `covered` names the issues looked up (from 22 Sep 2026); an older document looked up every unlisted issue
    const id = b.igId != null ? String(b.igId) : null, L = id && B[id] ? B[id] : null, looked = !!L || (id && (P.covered ? covered.has(id) : true));
    if (L) named.add(b.name);
    const A1 = anchorFor(b.name), size = A1 && A1.amountCr ? `${cr(A1.amountCr)}${A1.issueSizeCr ? ` · ${Math.round(A1.amountCr / A1.issueSizeCr * 100)}% of the issue` : ""}` : "";
    const lock = A1 && A1.lockIn30 ? `lock-in ends ${fmtD(A1.lockIn30)} / ${fmtD(A1.lockIn90)}` : "";
    const mine = L ? L.filter(x => follows(x.name)) : [];
    // an Upcoming issue's anchor book is allotted the day before it opens: until then there is no book to be in
    const notYet = !L && b.status === "Upcoming" && !(A1 && A1.amountCr) && !(A1 && A1.date && days(A1.date) < 0);
    const large = L ? L.length : looked && !notYet ? 0 : null;
    if (notYet) { later.push(`<span class="chip-i" data-row data-name="${esc(b.name)}">${esc(b.name)}${A1 && A1.date ? `<small class="dim"> bid ${days(A1.date) === 0 ? "today" : fmtD(A1.date)}</small>` : ""}</span>`); return ""; }
    const who = L ? `<details class="who"><summary>${L.length} of the ${P.tracked} largest anchors are in · who</summary><div class="chips" style="margin-top:6px">${L.map(x => `<span class="${follows(x.name) ? "ok" : ""}">${esc(x.name)}<small class="dim"> ${x.ipos} IPOs</small><button class="fbtn" data-follow="${esc(x.name)}" title="${follows(x.name) ? "Following" : "Follow this name"}">${follows(x.name) ? "✓" : "+"}</button></span>`).join("")}</div></details>`
      : notYet ? `<span class="dt">anchor book not published yet${A1 && A1.date ? ` · bid ${days(A1.date) === 0 ? "today" : fmtD(A1.date)}` : ""}</span>`
      : looked ? `<span class="dt">none of the ${P.tracked} largest anchors in this book</span>` : `<span class="dt">line-up not read yet</span>`;
    return `<div class="arow" data-row data-name="${esc(b.name)}"><div class="an"><b>${esc(b.name)}</b> <span class="pill ${b.status.toLowerCase()}">${esc(b.status)}</span>${b.sme ? ` <span class="pill plan" style="height:17px;font-size:10.5px">SME</span>` : ""}<div class="dt">${[size, lock].filter(Boolean).join(" · ") || (notYet ? "" : "no anchor book on file")}</div></div>
      <div class="aw">${who}${mine.length ? `<div class="dt" style="color:var(--up)">your names: ${mine.map(x => esc(x.name)).join(" · ")}</div>` : ""}${anchorEvidence(b, large)}</div></div>`; }).join("")
    + (later.length ? `<div class="arow" style="grid-template-columns:1fr"><div class="dt" style="margin-bottom:4px">Anchor books still to be published · ${later.length} issue${later.length > 1 ? "s" : ""}</div><div class="wl">${later.join("")}</div></div>` : "");
  return { html, named };
}
const playersNote = () => { const P = DATA.players || {}, A = (SEG(false) || {}).anchors; return P.tracked ? `Names come from the ${P.tracked} largest of ${(P.of || 0).toLocaleString("en-IN")} anchor investors on file (their latest ${P.latestPerInvestor} IPOs each; ${P.asOf ? "read " + fmtD(P.asOf) : ""}). A book with none of them is a book the big funds skipped. Each line-up is frozen the day the issue lists${A && A.n ? `; ${A.n} mainboard line-ups on file since ${fmtD(A.since)}` : "; the record starts now, so the past-books line reads thin for a while"}.` : "Anchor names are not on file yet."; };
