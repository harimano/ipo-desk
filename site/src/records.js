/* ================= ANCHOR TRACK RECORDS — who anchored what, and what it did =================
   Included into app.js (`@include records.js`); shares $, $$, esc, cr, pct, cls, fmtD, follows, allIssues, anchorFor.
   The record is the collector's (evidence.track_records -> trackRecords, in the lazy books.json part that boot does
   not fetch): per investor, per segment, the share of anchored IPOs that listed up with its Wilson interval, the median
   gain, the day-one close, the 5- and 30-day moves where the price path exists, and the same over the IPOs where the
   investor was a lead anchor. This file fetches that part on demand, draws it, and looks up the anchors of today's
   books in it. Mainboard and SME never share a number. No score, no verdict: n and the interval travel with every rate. */
let recScope = "main", recMinN = 3, recBooks = null, recHash = null, recLoading = null;
const recKey = s => { let x = String(s || "").toUpperCase(); if (x.includes("A/C")) x = x.split("A/C")[1]; x = x.replace(/\(.*?\)/g, " ").replace(/[^A-Z0-9 ]+/g, " ").replace(/\b(PRIVATE|PVT|LIMITED|LTD|LLP|CO|INC|PLC|THE|TRUSTEE|TRUSTEES|COMPANY)\b/g, " "); return x.replace(/\s+/g, " ").trim(); };
{ const f = $("#recFilters"); if (f) f.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; if (b.dataset.recSc) recScope = b.dataset.recSc; else if (b.dataset.recN) recMinN = +b.dataset.recN; renderRecords(); }); }

async function loadBooks() {
  const lazy = (DATA.lazy || {}).books; if (!lazy) return null;
  if (recBooks && recHash === lazy.hash) return recBooks;
  if (recLoading) return recLoading;
  recLoading = fetch("data/books.json?h=" + lazy.hash).then(r => { if (!r.ok) throw new Error("books.json " + r.status); return r.json(); })
    .then(b => { recBooks = b; recHash = lazy.hash; recLoading = null; return b; }).catch(e => { recLoading = null; console.warn(e); return null; });
  return recLoading;
}

function renderRecords() {
  const host = $("#recTable"); if (!host) return;
  $$("#recFilters button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.recSc ? b.dataset.recSc === recScope : +b.dataset.recN === recMinN)));
  const lazy = (DATA.lazy || {}).books;
  if (!lazy) { host.innerHTML = `<tbody><tr><td class="empty">The record is not published yet — it appears with the next full run.</td></tr></tbody>`; return; }
  if (!recBooks || recHash !== lazy.hash) { host.innerHTML = `<tbody><tr><td class="empty">Loading the record (${Math.round(lazy.bytes / 1024)} KB, fetched only on this card)…</td></tr></tbody>`; loadBooks().then(b => { if (b) renderRecords(); else host.innerHTML = `<tbody><tr><td class="empty">Could not load books.json.</td></tr></tbody>`; }); return; }
  const T = recBooks.trackRecords || {}, A = recBooks.anchorBooks || {}, isSme = recScope === "sme", segLbl = isSme ? "SME" : "mainboard";
  const rows = (T.rows || []).map(r => ({ ...r, s: r[recScope] })).filter(r => r.s && r.s.n >= recMinN).sort((x, y) => y.s.n - x.s.n || (y.s.pos || 0) - (x.s.pos || 0));
  const range = s => s && s.n ? `<span title="95% range: with ${s.n} cases the true rate could be anywhere in here">${Math.round(s.lo)}–${Math.round(s.hi)}%</span>` : "";
  const med = s => s && s.n ? `<span class="num ${cls(s.med)}">${pct(s.med, true)}</span><small class="dim"> (${s.n})</small>` : `<span class="dim">—</span>`;
  const fb = name => `<button class="fbtn" data-follow="${esc(name)}" title="${follows(name) ? "Following" : "Follow this name"}">${follows(name) ? "✓" : "+"}</button>`;
  const sub = $("#recSub"); if (sub) sub.textContent = `${T.withOutcome || 0} of ${T.booksOn || 0} anchor books on file have a listing outcome · ${(T.investors || 0).toLocaleString("en-IN")} investors seen · ${rows.length} with ${recMinN}+ ${segLbl} IPOs · ${A.n != null ? `${A.n} of ~1,300 books collected so far` : ""}`;
  host.innerHTML = `<thead><tr><th>Investor</th><th class="r">Anchored</th><th class="r">Listed up</th><th class="r">Median pop</th><th class="r">Day-1 close</th><th class="r">+5 days</th><th class="r">+30 days</th><th class="r">As lead anchor</th><th class="r">Placed</th></tr></thead><tbody>${rows.slice(0, 40).map(r => `<tr>
    <td class="nm${follows(r.name) ? " up" : ""}" title="${esc(r.name)}">${esc(r.name.length > 34 ? r.name.slice(0, 33) + "…" : r.name)} ${fb(r.name)}<div class="dt">${r.ipos.filter(i => !!i.sme === isSme).slice(0, 3).map(i => `${esc(i.name)} <span class="num ${cls(i.ret)}">${pct(i.ret, true)}</span>`).join(" · ")}</div></td>
    <td class="r num">${r.s.n}</td>
    <td class="r num"><b class="${r.s.pos >= 60 ? "up" : r.s.pos < 40 ? "down" : ""}">${Math.round(r.s.pos)}%</b><div class="dt">${range(r.s)}</div></td>
    <td class="r num ${cls(r.s.med)}">${pct(r.s.med, true)}<div class="dt">10–90: ${pct(r.s.p10, true)} to ${pct(r.s.p90, true)}</div></td>
    <td class="r">${med(r.s.close1)}</td><td class="r">${med(r.s.d5)}</td><td class="r">${med(r.s.d30)}</td>
    <td class="r">${r.s.lead && r.s.lead.n ? `<span class="num">${Math.round(r.s.lead.pos)}%</span><small class="dim"> of ${r.s.lead.n}</small>` : `<span class="dim">—</span>`}</td>
    <td class="r num">${cr(r.cr)}</td></tr>`).join("") || `<tr><td colspan="9" class="empty">No investor has ${recMinN} or more ${segLbl} IPOs with an outcome on file yet — the backfill adds about 40 books a run.</td></tr>`}</tbody>`;
  const more = $("#recMore"); if (more) more.textContent = rows.length > 40 ? `Showing 40 of ${rows.length}. Raise the minimum to narrow.` : "";
  // today's books, read against the record: the names on the anchor letter (anchors[].investors) or among the largest
  // anchors (players.books), each looked up by normalised key
  const byKey = new Map((T.rows || []).map(r => [r.key, r]));
  const P = DATA.players || {}, B = P.books || {};
  const cur = allIssues().filter(b => b.status !== "Listed");
  const items = cur.map(b => { const A1 = anchorFor(b.name), names = new Set([...(A1 && A1.investors || []).map(x => x.name), ...((b.igId != null && B[String(b.igId)]) || []).map(x => x.name)]);
    if (!names.size) return null;
    const hits = [...names].map(n => ({ n, r: byKey.get(recKey(n)) })).map(h => ({ ...h, s: h.r && h.r[b.sme ? "sme" : "main"] })).filter(h => h.s && h.s.n >= 2).sort((x, y) => y.s.n - x.s.n);
    return { b, names: names.size, hits }; }).filter(Boolean).sort((x, y) => y.hits.length - x.hits.length || y.names - x.names);
  const O = $("#recToday"); if (O) O.innerHTML = items.length ? items.map(it => `<div class="arow"><div class="an"><b data-row data-name="${esc(it.b.name)}">${esc(it.b.name)}</b> <span class="pill ${it.b.status.toLowerCase()}">${esc(it.b.status)}</span>${it.b.sme ? ` <span class="pill plan" style="height:17px;font-size:10.5px">SME</span>` : ""}<div class="dt">${it.names} anchor name${it.names === 1 ? "" : "s"} known · ${it.hits.length} with a ${it.b.sme ? "SME" : "mainboard"} record of 2+ IPOs</div></div>
      <div class="aw">${it.hits.length ? it.hits.slice(0, 6).map(h => `<span class="dt"><b style="color:var(--ink)">${esc(h.r.name.length > 36 ? h.r.name.slice(0, 35) + "…" : h.r.name)}</b> · ${h.s.n} anchored · listed up <b class="${h.s.pos >= 60 ? "up" : h.s.pos < 40 ? "down" : ""}">${Math.round(h.s.pos)}%</b> <small class="dim">(${Math.round(h.s.lo)}–${Math.round(h.s.hi)})</small> · median ${pct(h.s.med, true)}</span>`).join("") + (it.hits.length > 6 ? `<span class="dt">and ${it.hits.length - 6} more</span>` : "") : `<span class="dt">none of these names has two ${it.b.sme ? "SME" : "mainboard"} IPOs with an outcome on file yet</span>`}</div></div>`).join("")
    : `<div class="dt">No current issue has anchor names on file.</div>`;
}
