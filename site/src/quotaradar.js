/* ================= POSSIBLE QUOTAS — pipeline names a listed company may own =================
   Included into app.js (`@include quotaradar.js`); shares DATA, esc, fmtD, days.
   Two fields from collector/modules/filings.py, rendered as they are (rule 1: fields, never sentences parsed here):
     expected[].quotaCandidate — via "announcement" (a listed company's NSE announcement about a subsidiary's offer
       names the row: strong) or via "name" (an auto row's first word is a listed group's: weak, false positives expected);
     quotaLeads[] — every such announcement in the last 60 days, matched to a row or not.
   A flag, never a quota (rule 3): a name reaches the quota planner only after someone reads the DRHP's reservation clause. */
const QR_KIND = { drhp: "DRHP filed", udrhp: "UDRHP filed", rhp: "RHP filed", observation: "SEBI observations", withdrawn: "withdrawn", ipo: "IPO mentioned" };
const qrSyms = (ps, max = 4) => { ps = ps || []; return esc(ps.slice(0, max).map(p => p.symbol).join(", ")) + (ps.length > max ? ` <span class="dim">+${ps.length - max} more</span>` : ""); };
const qrLink = (u, t) => u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>` : "";
function renderQuotaRadar() {
  const el = $("#quotaRadar"); if (!el) return;
  const C = (DATA.expected || []).filter(e => e && e.quotaCandidate), L = DATA.quotaLeads || [];
  const strong = c => c.quotaCandidate.via === "announcement";
  const filed = e => (e.lastFiling || {}).date || "";
  C.sort((a, b) => strong(b) - strong(a) || filed(b).localeCompare(filed(a)) || a.name.localeCompare(b.name));
  const why = e => { const c = e.quotaCandidate;
    return strong(e)
      ? `<span class="pill soon">parent announced</span><div class="dt" style="max-width:360px" title="${esc(c.text || "")}">${esc((c.text || "").slice(0, 120))}${(c.text || "").length > 120 ? "…" : ""}</div><div class="dt">${c.date ? fmtD(c.date) : ""}${c.url ? " · " + qrLink(c.url, "the filing") : ""}</div>`
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
  el.innerHTML = `<div class="card tw"><table><thead><tr><th>Pipeline name</th><th>Why it is flagged</th><th>Possible parent</th><th>Last SEBI filing</th></tr></thead><tbody>${rows ||
      `<tr><td colspan="4" class="empty">No pipeline name is flagged. A flag appears when a listed company announces a subsidiary's offer, or a DRHP filer shares a listed group's name.</td></tr>`}</tbody></table></div>
    <div class="dt" style="margin-top:8px">${C.length ? `${nS} flagged by the parent's own announcement, ${C.length - nS} by group name only. ` : ""}Not a confirmed reservation: a name moves to the quota planner only after someone reads the DRHP's shareholder-reservation clause. A group-name match can be a coincidence.</div>
    ${L.length ? `<details class="qrd"><summary>${L.length} announcement${L.length === 1 ? "" : "s"} by listed companies about a subsidiary's offer · last 60 days</summary>
      <div class="card tw" style="margin-top:6px"><table><thead><tr><th>Date</th><th>Listed company</th><th>What</th><th>Announcement</th></tr></thead><tbody>${leads}</tbody></table></div>
      <div class="dt" style="margin-top:6px">From NSE's market-wide announcements, both boards. NSE sometimes summarises a filing as just "General Updates"; those are missed here, never read from the PDF.</div></details>` : ""}`;
}
