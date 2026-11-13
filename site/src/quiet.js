/* ---------- the quiet desk: the first card on Today when no issue is open and nothing lists this week (13 Nov 2026) ----------
   13 Nov 2026: the post-Diwali lull left one upcoming row on the board and a blank "Next 30 days"; the desk read as down.
   This card says what the document says: the next board row by opening date (its logo, dates, band, lot, size), the last
   listing from `listedPerf`, the SME count, the calendar check's source and time, and the collector's next slot (nextRun(), the
   gate's own rule). Every figure is a field; nothing is parsed, nothing is a verdict. Ids and functions carry the `quiet` prefix. */
function quietNext() { const up = allIssues().filter(b => b.status === "Upcoming").sort((a, b) => (a.open || "9999").localeCompare(b.open || "9999")); return up[0] || null; }
function quietShow() { const all = allIssues(); return !all.some(b => b.status === "Open") && !all.some(b => b.listing && days(b.listing) >= 0 && days(b.listing) <= 7); }
function renderQuiet() {
  const host = $("#quiet-host"); if (!host) return;
  if (!quietShow()) { host.innerHTML = ""; return; }
  const b = quietNext(), c = checkOf("calendar"), src = c ? answeredBy(c).ok.join(" + ") : "", when = c ? feedWhen(c) : "";
  const last = (DATA.listedPerf || []).slice().sort((x, y) => (y.date || "").localeCompare(x.date || ""))[0];   // every listing since 2022, both segments (`recent` is the mainboard tracker)
  const smeUp = sme.filter(x => x.status === "Upcoming").length, dOpen = b && b.open ? days(b.open) : null;
  const facts = b ? [b.type || "Mainboard", b.open ? `${fmtD(b.open)}${b.close ? "–" + fmtD(b.close) : ""}` : "dates awaited",
    b.bandLow && b.bandHigh ? `₹${Number(b.bandLow)}–${Number(b.bandHigh)}` : null, b.lotSize ? `lot ${b.lotSize}` : null,
    b.issueSizeCr ? cr(b.issueSizeCr) : null, b.listing ? `lists ${fmtD(b.listing)}` : null].filter(Boolean) : [];
  const big = b && b.open ? `<div class="big mono">${fmtD(b.open)}</div><div class="d2">${dOpen === 0 ? "opens today" : dOpen === 1 ? "opens tomorrow" : `opens in ${dOpen} days`} · ${d(b.open).toLocaleDateString("en-IN", { weekday: "short" })}</div>`
    : `<div class="big mono dim">TBA</div><div class="d2">opening date</div>`;
  host.innerHTML = `<div class="card q lead quiet" id="quiet-card">
    <div class="l">
      <div class="tags"><span class="pill upcoming">No open issue</span><span class="lbl">Primary market · ${esc(fmtD(iso(today)))}</span><a class="go" href="#" data-quiet-go="board">Board ›</a></div>
      ${b ? `<div class="ttl">${logo(b)}${esc(b.name)} <small>next issue</small></div><div class="desc">${facts.map(esc).join(" · ")}</div>`
        : `<div class="ttl">Nothing on the calendar <small>next issue</small></div><div class="desc">No dated issue on the board.</div>`}
      <dl class="kv">
        <dt>Last listing</dt><dd>${last ? `${esc(last.name)}${last.sme ? " · SME" : ""} · ${fmtD(last.date)}` : "—"}</dd>
        <dt>SME</dt><dd>${smeUp ? `${smeUp} upcoming` : "None on the calendar"}</dd>
        <dt>Calendar</dt><dd>${src ? esc(src) : "—"}${when ? " · " + esc(when) : ""}</dd>
      </dl>
    </div>
    <div class="r">${big}</div>
    <div class="foot">Next collector run ${esc(nextRun() || "—")} IST · intraday runs resume ${b && b.open ? fmtD(b.open) : "with the next open issue"}</div>
  </div>`;
}
$("#quiet-host").addEventListener("click", e => { const a = e.target.closest("[data-quiet-go]"); if (!a) return; e.preventDefault(); show(a.dataset.quietGo); });
