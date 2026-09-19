/* ================= HOLD OR SELL AT THE OPEN — the collector's record, drawn =================
   Included into app.js (`@include hold.js`); shares SEG, EDG, EVD, bandOf, edgeLbl, winLbl, pct, cls, esc. Every number is
   evidence.segments[x].hold (collector/modules/evidence.py): listings banded by how they OPENED, the share whose day-1 close
   beat the open with its Wilson range, and the open-to-close move (median, p10-p90) in points of issue price.
   One drawing, three places: the listing-day card on Today, the Board's expanded row (against where GMP says it will open),
   and the Scoreboard panel. A rate is drawn against the 50% line with its 95% range as a whisker — a whisker that crosses
   the line is a coin flip, and the drawing should make that obvious before anyone reads a number. */
const holdBand = (isSme, openPct, where) => { const s = SEG(isSme); if (!s || !s.hold || openPct == null) return null; const i = bandOf(openPct, EDG("open")); return i < 0 ? null : { i, b: s.hold[where || "window"][i], seg: s }; };
const holdRead = b => !b || !b.n ? "" : b.lo > 50 ? "holding usually paid" : b.hi < 50 ? "selling at the open usually paid" : "a coin flip";
function holdMeter(b) {                     // 0..100% track, 50% line, Wilson whisker, dot at the rate
  if (!b || !b.n) return `<span class="dim">no past cases</span>`;
  const c = b.lo > 50 ? "up" : b.hi < 50 ? "down" : "mid";
  return `<div class="hm" title="${Math.round(b.held)}% of ${b.n} · 95% range ${Math.round(b.lo)}–${Math.round(b.hi)}%"><i class="hm-mid"></i><i class="hm-w ${c}" style="left:${b.lo}%;width:${Math.max(1, b.hi - b.lo)}%"></i><i class="hm-d ${c}" style="left:${b.held}%"></i></div>`;
}
function holdMove(b, max) {                 // open -> close move: p10..p90 bar around zero, tick at the median
  if (!b || !b.n) return "";
  const m = max || Math.max(5, Math.abs(b.p10), Math.abs(b.p90)), x = v => 50 + Math.max(-50, Math.min(50, v / m * 50));
  return `<div class="hm mv" title="open to close: median ${pct(b.med, true)}, 8 in 10 between ${pct(b.p10, true)} and ${pct(b.p90, true)} (points of issue price)"><i class="hm-mid"></i><i class="hm-w ${b.med > 0 ? "up" : b.med < 0 ? "down" : "mid"}" style="left:${x(b.p10)}%;width:${Math.max(1, x(b.p90) - x(b.p10))}%"></i><i class="hm-t" style="left:${x(b.med)}%"></i></div>`;
}
// the compact block used on Today and in the Board's expanded row
function holdBlock(isSme, openPct, how) {
  const H = holdBand(isSme, openPct); if (!H || !H.b.n) return "";
  const b = H.b, lbl = edgeLbl(EDG("open"), H.i, "%"), thin = b.n < (EVD().minN || 30);
  return `<div class="holdb"><div class="holdb-h"><b>Hold or sell at the open?</b> <span class="dim">${how} · ${b.n} ${isSme ? "SME" : "mainboard"} listings that opened ${lbl} · ${winLbl(H.seg.window)}${thin ? " · thin sample" : ""}</span></div>
    <div class="holdb-r"><span class="holdb-l">Close beat the open</span>${holdMeter(b)}<span class="num"><b>${Math.round(b.held)}%</b> <span class="dim">${Math.round(b.lo)}–${Math.round(b.hi)}</span></span></div>
    <div class="holdb-r"><span class="holdb-l">Open → close move</span>${holdMove(b)}<span class="num"><b class="${cls(b.med)}">${pct(b.med, true)}</b> <span class="dim">${pct(b.p10, true)} to ${pct(b.p90, true)}</span></span></div>
    <div class="dt">History says: <b>${holdRead(b)}</b>${b.lo <= 50 && b.hi >= 50 ? " — the 95% range straddles 50%, so the open tells you little about the rest of the day" : ""}.</div></div>`;
}
// the Scoreboard panel: every band, this window and all years, for the segment in view
function holdPanel(isSme) {
  const s = SEG(isSme); if (!s || !s.hold) return "";
  const ed = EDG("open"), mx = Math.max(5, ...s.hold.window.concat(s.hold.all).filter(b => b.n).flatMap(b => [Math.abs(b.p10), Math.abs(b.p90)]));
  const row = (b, i, tag) => !b.n ? "" : `<tr><td>${tag ? `<span class="dim">${tag}</span>` : `<b>${edgeLbl(ed, i, "%").replace("zero or below", "below issue price")}</b>`}</td><td class="r num">${b.n}${b.n < (EVD().minN || 30) ? ' <span class="dim">thin</span>' : ""}</td><td style="min-width:180px">${holdMeter(b)}</td><td class="r num"><b>${Math.round(b.held)}%</b> <span class="dim">${Math.round(b.lo)}–${Math.round(b.hi)}</span></td><td style="min-width:180px">${holdMove(b, mx)}</td><td class="r num ${cls(b.med)}">${pct(b.med, true)}</td><td class="dim">${tag ? "" : holdRead(b)}</td></tr>`;
  return `<div class="sec card"><div class="ch">Hold or sell at the open? <span class="sub">${isSme ? "SME" : "mainboard"} · by how the stock opened · ${winLbl(s.window)}, with all years under each</span></div>
    <div class="tw"><table><thead><tr><th>Opened</th><th class="r">Listings</th><th>Close beat the open <span class="dim">· line = 50%, bar = 95% range</span></th><th class="r">Rate</th><th>Open → close move <span class="dim">· 8 in 10, tick = median</span></th><th class="r">Median</th><th>History says</th></tr></thead>
    <tbody>${s.hold.window.map((b, i) => row(b, i) + row(s.hold.all[i], i, "all years")).join("")}</tbody></table></div>
    <div class="dt" style="padding:8px 12px">Moves are in points of the issue price. A bar that crosses the 50% line is a coin flip whatever its centre says. This is what happened between the open and the close on day one — nothing about day two.</div></div>`;
}
