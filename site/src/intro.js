/* ================= HOW TO READ THIS DESK — seven steps, one idea each =================
   Opens once for a new reader (the per-device flag `ipo-intro`, kept in the account's local cache so a shared device
   does not show it to the next person as "seen"), then from the account menu, the footer link, or the `?` key.
   The pictures are static replicas of the real elements — never live data, so a step is never blank on a quiet day.
   The words follow rule 3: evidence and both sides, never a verdict. */
const INTRO_STEPS = [
  { t: "Each morning, Today tells you what needs doing.",
    p: "Open IPOs closing soon, a record date to catch, an allotment to check. Newest and most urgent first. The rest is folded below.",
    pic: `<div class="iq"><div><span class="pill now">Closes today</span><div class="ttl">Lenskart Solutions — apply or pass</div><div class="desc">Band ₹382–402 · one lot ₹14,874 · book 12.4x</div></div><div><div class="big down">31 Oct</div><div class="acts"><span class="btn sm primary">Log application</span><span class="btn sm">Pass</span></div></div></div>`,
    w: `Where: the <b>Today</b> tab, key <b>1</b>. Press <b>Pass</b> and a card leaves the list; <b>Log application</b> puts it in your Book.` },
  { t: "GMP is the market's guess at the listing pop.",
    p: "The grey market trades an IPO's shares before they list. The premium it pays over the issue price is the GMP: a guess at the first-day gain, not a promise. The desk shows the guess, then how that kind of guess did before.",
    pic: `<div class="ikv"><div><div class="k">GMP today</div><div class="v"><span class="ev hi num">+18.2%</span> <span class="dim">₹73</span></div></div><div><div class="k">How this band listed</div><div class="v num">71% of 38 up</div><div class="dt">95% range 55–83% · median +12%</div></div></div><div class="dt" style="margin-top:8px">8 in 10 like this listed between +4% and +31%</div>`,
    w: `Where: <b>GMP · track record</b> on the <b>Board</b>, key <b>3</b>. The same cell on SME issues is read against SME history only; the two are never mixed.` },
  { t: "Your odds, and what one application is worth.",
    p: "When the retail queue is 6x full, at most 1 in 6 get shares. The desk shows that worst case, then weighs it against the gain GMP implies. The result is the EV: what one ticket is worth, as a % of the money it blocks.",
    pic: `<div class="ikv"><div><div class="k">Retail book</div><div class="v num">6.2x</div></div><div><div class="k">Odds</div><div class="v">at least 1 in 6</div></div><div><div class="k">EV per application</div><div class="v up num">+2.9%</div></div></div><div class="irange"><i></i><b></b></div><div class="dt" style="margin-top:6px">past issues like this landed between −1.1% and +6.4%</div>`,
    w: `Where: the <b>EV</b> column on the <b>Board</b>. Green when the whole past range is above zero. The hottest IPOs often have the worst EV: everyone applies, almost nobody gets shares.` },
  { t: "The book: three queues, and how crowded each one is.",
    p: "Institutions (QIB), the wealthy (NII) and everyone else (retail) bid in separate queues with separate shares set aside. “12x” means the shares on offer were bid for twelve times over. The QIB line matters most and fills last, on the closing afternoon.",
    pic: `<div class="isb"><span class="l">QIB</span><span class="bar"><i style="width:84%"></i></span><span class="n num">48.1x</span></div><div class="isb"><span class="l">NII</span><span class="bar"><i style="width:66%"></i></span><span class="n num">22.4x</span></div><div class="isb"><span class="l">Retail</span><span class="bar"><i style="width:40%"></i></span><span class="n num">6.2x</span></div><div class="isb"><span class="l">Total</span><span class="bar"><i style="width:55%"></i></span><span class="n num">12.4x</span></div>`,
    w: `Where: the <b>Book</b> column on the <b>Board</b>, refreshed every half hour on market days. Early figures say little: the desk marks a book “too early to read” until the last afternoon.` },
  { t: "Quota: own one share of the parent, get a second queue.",
    p: "When a listed company floats a subsidiary, it often reserves part of the IPO for its own shareholders. One share of the parent in your demat on the record date is the ticket. That queue is usually far shorter than retail.",
    pic: `<div class="ipipe"><span class="chip"><b>Reliance Industries</b>parent · ₹1,420</span><span class="arrow">→</span><span class="chip"><b>Reliance Jio</b>DRHP filed</span><span class="pill yes">quota ✓</span><span class="pill ok">held ✓</span></div>`,
    w: `Where: the <b>Pipeline</b> tab, key <b>2</b>: every subsidiary IPO in the works, which parents have a quota, and the record dates. <b>Mark held</b> and the desk tells you when a record date needs you.` },
  { t: "Five sources, one desk. Nothing to look up elsewhere.",
    p: "Every number is pulled from the exchanges and the IPO sites twice an hour and read side by side, so you never open six tabs to check one IPO.",
    pic: `<div class="isrc"><span>NSE</span><span>BSE</span><span>InvestorGain</span><span>Narada</span><span>NSE archives</span></div><div class="iperks"><div><b>Research sheet</b> per IPO: financials, peers, objects, the book day by day, GMP day by day</div><div><b>Who is in the book</b>: every anchor investor, with how their past picks listed</div><div><b>After listing</b>: the price path, bulk and block deals, lock-in expiries, FII / DII flows</div><div><b>Every listing since 2022</b> as the yardstick each live number is read against</div></div>`,
    w: `Where: <b>Market</b> (key <b>4</b>) for the temperature, anchors, superinvestors and flows; <b>Research</b> (key <b>5</b>) for one IPO in full. Every screen says <b>data as of</b> at the top.` },
  { t: "Evidence, never a verdict.",
    p: "Every rate on the desk says how many past cases it rests on and how wide the honest range is. <b>The desk never says apply or skip.</b> It shows you what happened before, both sides, and you decide.",
    pic: `<div class="iex"><b>71% of 38 listed up (55–83%)</b> means: of 38 past IPOs with this kind of GMP, 71% opened above the issue price, and with only 38 cases the true rate could be anywhere from 55% to 83%.<br><b>Thin</b> means too few cases to lean on.</div>`,
    w: `Numbers refresh every 30 minutes on market days. If one looks wrong, <b>Wrong number?</b> under the IPO sends it to Hari. Keys: <b>/</b> command bar · <b>1–7</b> screens · <b>?</b> this walkthrough.` },
];
let introAt = -1;
function introOpen(i) {
  const ov = $("#intro"); if (!ov) return;
  introAt = Math.max(0, Math.min(INTRO_STEPS.length - 1, i == null ? 0 : i));
  const s = INTRO_STEPS[introAt], n = INTRO_STEPS.length, last = introAt === n - 1;
  ov.querySelector(".walk").innerHTML = `<div class="top"><div class="dots" aria-hidden="true">${INTRO_STEPS.map((_, k) => `<i class="${k < introAt ? "done" : k === introAt ? "on" : ""}"></i>`).join("")}</div><button class="skip" data-intro="close">${last ? "Close" : "Skip"}</button></div>
    <div class="body"><div class="n">Step ${introAt + 1} of ${n}</div><h2>${s.t}</h2><p>${s.p}</p><div class="pic">${s.pic}</div><div class="where">${s.w}</div></div>
    <div class="foot">${introAt ? `<button class="back" data-intro="back">Back</button>` : ""}<button class="btn primary next" data-intro="${last ? "done" : "next"}">${last ? "Start reading" : "Next"}</button></div>`;
  ov.hidden = false; document.body.classList.add("intro-open");
  ov.querySelector(".next").focus({ preventScroll: true });
}
function introClose() { const ov = $("#intro"); if (!ov || ov.hidden) return; ov.hidden = true; document.body.classList.remove("intro-open"); store.set("ipo-intro", { seen: iso(today) }); }
$("#intro").addEventListener("click", e => {
  const b = e.target.closest("[data-intro]");
  if (!b) { if (e.target === e.currentTarget) introClose(); return; }
  const k = b.dataset.intro;
  if (k === "next") introOpen(introAt + 1); else if (k === "back") introOpen(introAt - 1); else introClose();
});
document.addEventListener("keydown", e => {
  if ($("#intro").hidden) return;
  if (e.key === "Escape") { introClose(); e.preventDefault(); }
  else if (e.key === "ArrowRight" || e.key === "Enter") { if (introAt < INTRO_STEPS.length - 1) introOpen(introAt + 1); else introClose(); e.preventDefault(); }
  else if (e.key === "ArrowLeft") { if (introAt > 0) introOpen(introAt - 1); e.preventDefault(); }
}, true);   // capture: ahead of the page's own 1–7 / j / k keys while the walkthrough is up
document.addEventListener("click", e => { const b = e.target.closest("[data-intro-open]"); if (!b) return; const m = $("#acctMenu"); if (m) m.hidden = true; introOpen(0); });
// first visit: once the account has answered (so a returning reader's cache is in) or straight away without one
(function introFirst() { const go = () => { if (!store.get("ipo-intro", null) && $("#intro").hidden && !document.getElementById("acctNote")) introOpen(0); };
  if (ACC) ACC.on("change", () => setTimeout(go, 400)); else setTimeout(go, 400); })();
