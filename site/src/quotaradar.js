/* ================= POSSIBLE QUOTAS — pipeline names a listed company may own =================
   Included into app.js (`@include quotaradar.js`); shares DATA, esc, fmtD, days.
   Two fields from collector/modules/filings.py, rendered as they are (rule 1: fields, never sentences parsed here):
     expected[].quotaCandidate — via "announcement" (a listed company's NSE announcement about a subsidiary's offer
       names the row: strong) or via "name" (an auto row's first word is a listed group's: weak, false positives expected);
       (an announcement candidate the SEBI registers also put there carries `register`, the row's filing: shown beside, never merged);
     quotaLeads[] — every such announcement in the last 60 days, matched to a row or not;
     quotaFound[] — every IPO ON THE BOARD whose InvestorGain record (or bidding book) shows a shareholder reservation, matched to a
       quota row (`quotaRow`) or not: the first section, so a reservation the hand-written quota list missed is seen the day the
       record lands (Jio Platforms listed 28 Oct 2026 while the table said "awaited"). Both witnesses are printed, never merged.
   A flag, never a quota (rule 3): a name reaches the quota planner only after someone reads the DRHP's reservation clause. */
const QR_KIND = { drhp: "DRHP filed", udrhp: "UDRHP filed", rhp: "RHP filed", observation: "SEBI observations", withdrawn: "withdrawn", ipo: "IPO mentioned" };
const qrSyms = (ps, max = 4) => { ps = ps || []; return esc(ps.slice(0, max).map(p => p.symbol).join(", ")) + (ps.length > max ? ` <span class="dim">+${ps.length - max} more</span>` : ""); };
const qrLink = (u, t) => u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>` : "";
const qfShares = n => n == null ? "—" : Number(n).toLocaleString("en-IN") + " shares";
const qfRecord = w => w === true ? "reservation" : w === false ? "no reservation" : "—";              // the InvestorGain record
const qfBook = w => w === true ? "shareholder line" : w === false ? "no shareholder line" : "not open yet";   // the bidding book
const QF_ORDER = { Open: 0, Closed: 1, Upcoming: 2, Listed: 3 };
const QF_MAX_ROWS = 6;                                                                      // more than this scrolls inside the card
function renderQuotaFound() {
  const st = x => { const b = findIssue(x.name); return b && b.status in QF_ORDER ? QF_ORDER[b.status] : 4; };
  const F = (DATA.quotaFound || []).slice().sort((a, b) => st(a) - st(b) || (b.open || "").localeCompare(a.open || "") || a.name.localeCompare(b.name));
  if (!F.length) return "";
  const onList = F.filter(x => x.quotaRow).length;
  const parent = x => x.parentSymbol ? `<span class="mono" style="font-size:12px">${esc(x.parentSymbol)}</span>${x.parent ? `<div class="dt">${esc(x.parent)}</div>` : ""}`
    : x.parent ? esc(x.parent) : x.parentId != null ? `<span class="dim">parent id ${esc(String(x.parentId))}</span><div class="dt">name not on the record</div>` : `<span class="dim">—</span>`;
  const reserved = x => `${x.offered != null ? `<span class="num">${qfShares(x.offered)}</span>` : `<span class="dim">size not on the record</span>`}<div class="dt">${[x.bidLimit != null ? "bid limit " + inr0(x.bidLimit) : "", x.discount != null ? "discount " + inr(x.discount) + (x.discountPct != null ? " (" + x.discountPct + "%)" : "") : ""].filter(Boolean).join(" · ")}</div>`;
  const w = x => { const W = x.witness || {}, dis = W.record === false && W.book === true;
    return `<span class="${dis ? "amb" : ""}" style="white-space:nowrap">record: ${qfRecord(W.record)} · book: ${qfBook(W.book)}</span>${dis ? `<div class="dt" style="max-width:260px">the record shows no reservation, the bidding book has a shareholder line — both kept</div>` : ""}`; };
  const rows = F.map(x => { const b = findIssue(x.name), dates = [x.open ? "opens " + fmtD(x.open) : "", x.listing ? "lists " + fmtD(x.listing) : ""].filter(Boolean).join(" · ");
    return `<tr><td><div class="nm">${b ? logo(b) : ""}${b ? `<a href="${hashFor("board", x.name)}" title="open the Board row">${esc(x.name)}</a>` : esc(x.name)}</div><div class="dt">${x.board === "sme" ? "SME" : "Mainboard"}${dates ? " · " + dates : ""}</div></td>
      <td>${parent(x)}</td><td>${reserved(x)}</td>
      <td>${x.quotaRow ? `<span class="pill ok">on the quota list</span><div class="dt"><a href="${hashFor("pipe", x.quotaRow)}">${esc(x.quotaRow)}</a></div>` : `<span class="pill unk">not on the quota list</span>`}</td>
      <td class="dt">${w(x)}</td></tr>`; }).join("");
  return `<div class="card" style="margin-bottom:12px"><div class="ch">On the board with a shareholder reservation <span class="sub">${F.length} issue${F.length === 1 ? "" : "s"} · ${onList} on the quota list · ${F.length - onList} not</span></div>
    <div class="tw${F.length > QF_MAX_ROWS ? " scroll" : ""}"><table><thead><tr><th>IPO</th><th>Parent</th><th>Reserved for shareholders</th><th>Quota list</th><th>Seen in</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="dt" style="padding:8px 18px 10px">From each issue's InvestorGain record and its bidding book, every run · "not on the quota list" = the hand-written table has no row for it.</div></div>`;
}
function renderQuotaRadar() {
  const el = $("#quotaRadar"); if (!el) return;
  const C = (DATA.expected || []).filter(e => e && e.quotaCandidate), L = DATA.quotaLeads || [];
  const strong = c => c.quotaCandidate.via === "announcement";
  const filed = e => (e.lastFiling || {}).date || "";
  C.sort((a, b) => strong(b) - strong(a) || filed(b).localeCompare(filed(a)) || a.name.localeCompare(b.name));
  const why = e => { const c = e.quotaCandidate;
    return strong(e)
      ? `<span class="pill soon">parent announced</span><div class="dt" style="max-width:360px" title="${esc(c.text || "")}">${esc((c.text || "").slice(0, 120))}${(c.text || "").length > 120 ? "…" : ""}</div><div class="dt">${c.date ? fmtD(c.date) : ""}${c.url ? " · " + qrLink(c.url, "the filing") : ""}</div>${c.register ? `<div class="dt">SEBI register: ${esc(c.register.register || "")}${c.register.date ? " " + fmtD(c.register.date) : ""}${c.register.url ? " · " + qrLink(c.register.url, "SEBI") : ""} — two documents, both linked, neither read</div>` : ""}`
      : `<span class="pill plan">same group name</span><div class="dt">first word matches ${(c.parents || []).length} listed compan${(c.parents || []).length === 1 ? "y" : "ies"} — may be a coincidence</div>`; };
  const rows = C.map(e => `<tr><td class="nm">${esc(e.name)}<div class="dt">${esc(e.stage || "")}</div></td><td>${why(e)}</td>
      <td><span class="mono" style="font-size:12px">${qrSyms(e.quotaCandidate.parents)}</span>${strong(e) && e.quotaCandidate.parents && e.quotaCandidate.parents[0] && e.quotaCandidate.parents[0].name ? `<div class="dt">${esc(e.quotaCandidate.parents[0].name)}</div>` : ""}</td>
      <td class="dt" style="white-space:nowrap">${e.lastFiling ? `${fmtD(e.lastFiling.date)} ${esc(e.lastFiling.register || "")}${e.lastFiling.url ? "<br>" + qrLink(e.lastFiling.url, "SEBI") : ""}` : "—"}</td></tr>`).join("");
  const lk = x => x.kind === "withdrawn" ? "now" : x.kind === "ipo" ? "plan" : "soon";
  const leads = L.map(x => `<tr><td class="dt" style="white-space:nowrap">${x.date ? fmtD(x.date) : "—"}</td>
      <td class="nm">${esc(x.parentSymbol)}${x.sme ? ' <span class="dim">SME</span>' : ""}<div class="dt">${esc(x.parentName || "")}</div></td>
      <td><span class="pill ${lk(x)}">${esc(QR_KIND[x.kind] || x.kind)}</span>${x.watched ? '<div class="dt">on the quota list</div>' : ""}${x.matched ? `<div class="dt">→ ${esc(x.matched)}</div>` : ""}</td>
      <td class="dt" style="max-width:420px" title="${esc(x.text || "")}">${esc((x.text || "").slice(0, 160))}${(x.text || "").length > 160 ? "…" : ""}${x.url ? " · " + qrLink(x.url, "filing") : ""}</td></tr>`).join("");
  const nS = C.filter(strong).length;
  el.innerHTML = renderQuotaFound() + `<div class="card tw"><table><thead><tr><th>Pipeline name</th><th>Why it is flagged</th><th>Possible parent</th><th>Last SEBI filing</th></tr></thead><tbody>${rows ||
      `<tr><td colspan="4" class="empty">No pipeline name is flagged. A flag appears when a listed company announces a subsidiary's offer, or a DRHP filer shares a listed group's name.</td></tr>`}</tbody></table></div>
    <div class="dt" style="margin-top:8px">${C.length ? `${nS} flagged by the parent's own announcement, ${C.length - nS} by group name only. ` : ""}Not a confirmed reservation: a name moves to the quota planner only after someone reads the DRHP's shareholder-reservation clause. A group-name match can be a coincidence.</div>
    ${L.length ? `<details class="qrd"><summary>${L.length} announcement${L.length === 1 ? "" : "s"} by listed companies about a subsidiary's offer · last 60 days</summary>
      <div class="card tw" style="margin-top:6px"><table><thead><tr><th>Date</th><th>Listed company</th><th>What</th><th>Announcement</th></tr></thead><tbody>${leads}</tbody></table></div>
      <div class="dt" style="margin-top:6px">From NSE's market-wide announcements, both boards. NSE sometimes summarises a filing as just "General Updates"; those are missed here, never read from the PDF.</div></details>` : ""}`;
}
