/* ================= WRONG NUMBER? — a reader flags a figure, Hari sees it =================
   One link under an IPO's figures (a Today card, the Board row's detail). It opens a three-field form in place:
   which number, what it should be, send. POST /api/report → the Worker stores it in D1 (`reports`, schema.sql) under
   the VERIFIED email and pings NTFY_TOPIC when that secret exists; /admin lists them. The number on screen does not
   change: a report is a note to a person, never an edit (rule 1 — the pipeline fetches, nobody types figures in). */
function reportFields(b) {
  const S0 = b.sub || {};
  return [b.gmp != null ? ["gmp", `GMP (${inr(b.gmp)}${b.gmpPct != null ? ", " + pct(b.gmpPct, true) : ""})`, `${b.gmp}`] : null,
    S0.total != null ? ["book", `Book total (${S0.total}x)`, `${S0.total}x`] : null,
    S0.retail != null ? ["retail", `Retail book (${S0.retail}x)`, `${S0.retail}x`] : null,
    S0.qib != null ? ["qib", `QIB book (${S0.qib}x)`, `${S0.qib}x`] : null,
    ["band", `Band / lot (${b.bandLow != null ? inr(b.bandLow) + "–" : ""}${b.bandHigh != null ? inr(b.bandHigh) : "TBA"}${b.lotSize ? ", " + b.lotSize + " shares" : ""})`, `${b.bandLow || ""}-${b.bandHigh || ""} x${b.lotSize || ""}`],
    ["dates", `Dates (${[b.open && fmtD(b.open), b.close && fmtD(b.close), b.listing && fmtD(b.listing)].filter(Boolean).join(" · ") || "—"})`, [b.open, b.close, b.allotment, b.listing].filter(Boolean).join("/")],
    ["odds", "Odds / applications", ""], ["status", `Status (${b.status})`, b.status], ["other", "Something else", ""]].filter(Boolean);
}
const reportLink = (b, where) => b && b.name ? `<div class="wn" data-wn-for="${esc(b.name)}" data-wn-where="${where}">Data as of ${istClock(DATA.meta.asOf)} · <a href="#" data-wn>Wrong number?</a></div>` : "";
function reportForm(host) {
  const b = findIssue(host.dataset.wnFor); if (!b) return;
  const F = reportFields(b);
  host.innerHTML = `<form class="wform" data-wn-form><select name="field" aria-label="Which number">${F.map(f => `<option value="${esc(f[0])}" data-shown="${esc(f[2])}">${esc(f[1])}</option>`).join("")}</select>
    <input name="note" maxlength="500" placeholder="What should it be, and where did you see it? (optional)" aria-label="Note">
    <button class="btn primary sm" type="submit">Send</button><button class="btn sm" type="button" data-wn-cancel>Cancel</button>
    <div class="meta">Sent with the IPO, the number as shown, the run it came from and your email. Hari sees it on /admin and gets a ping. The figure here stays until the next run or the source is fixed.</div></form>`;
  host.querySelector("input").focus();
}
async function reportSend(host, form) {
  const b = findIssue(host.dataset.wnFor); if (!b) return;
  const sel = form.field, opt = sel.options[sel.selectedIndex];
  const btn = form.querySelector("button[type=submit]"); btn.disabled = true; btn.textContent = "Sending…";
  const body = { issue: b.name, igId: b.igId != null ? String(b.igId) : null, field: sel.value, shown: opt ? opt.dataset.shown || "" : "", note: form.note.value.trim(), where: host.dataset.wnWhere || "", dataAsOf: DATA.meta.asOf || null, page: location.pathname };
  try {
    const r = await fetch("/api/report", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify(body) });
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || ("HTTP " + r.status)); }
    host.innerHTML = `<div class="sent">✓ Sent. Thanks — the number stays until the next run or Hari fixes the source.</div>`;
  } catch (e) {
    btn.disabled = false; btn.textContent = "Send";
    toast(/503|not configured/i.test(e.message) ? "Not sent: reports need the accounts database" : "Not sent: " + e.message);
  }
}
document.addEventListener("click", e => {
  const a = e.target.closest("a[data-wn]"); if (a) { e.preventDefault(); reportForm(a.closest("[data-wn-for]")); return; }
  const c = e.target.closest("[data-wn-cancel]"); if (c) { const h = c.closest("[data-wn-for]"); const b = findIssue(h.dataset.wnFor); h.outerHTML = reportLink(b, h.dataset.wnWhere); }
});
document.addEventListener("submit", e => { const f = e.target.closest("form[data-wn-form]"); if (!f) return; e.preventDefault(); reportSend(f.closest("[data-wn-for]"), f); });
