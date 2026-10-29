/* ================= THE WEEK AND THE CAPITAL PLANNER — "with this much money free, which issues, which category, what does
   the evidence say" (planner.js) =================
   Included into app.js (`@include planner.js`); shares $, esc, inr0, pct, fmtD, days, rel, cls, sgn, odds, appOdds, evOf, SEG,
   evBand, evShort, evCls, store, S, findIssue, reportLink, pv, PROV. Reads DATA.calendar (collector/modules/planner.py): the
   events of the week and, per issue, what one application blocks per category, the day the money is back and how long it
   is away. Nothing here is computed from lots and prices — the collector wrote every rupee; the page adds the reader's ticks.
   The one sum made here is the EV per application (evOf, the sanctioned exception) and the total of what the reader ticked.
   Rows sit in order of close and nothing says apply or skip: odds, EV and the evidence band sit beside each, with n and the
   95% range. The reader's budget and ticks are the synced account part `budget` = {free, picks["igId:cat"]}. */
const WEEK_DAYS = 7;
const WK_KIND = { open: ["opens", "open"], close: ["closes", "close"], allotment: ["allotment", "allot"], refund: ["₹ back", "back"], listing: ["lists", "list"],
  lockin30: ["lock-in opens · half", "lock"], lockin90: ["lock-in opens · rest", "lock"], record: ["record date", "rec"] };
const CAT_ORDER = ["retail", "employee", "shareholder", "snii", "bnii"], CAT_NAME = { retail: "retail", employee: "employee", shareholder: "shareholder", snii: "sNII", bnii: "bNII" };
function normBudget(b) { return b && typeof b === "object" ? { free: b.free == null || b.free === "" || isNaN(Number(b.free)) ? null : Number(b.free), picks: Array.isArray(b.picks) ? b.picks.map(String) : [] } : { free: null, picks: [] }; }
const saveBudget = () => store.set("ipo-budget", S.budget);
const CAL = () => DATA.calendar || {};
const inLakh = n => n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });

function renderWeek() {
  const host = $("#week"); if (!host) return;
  const ev = (CAL().events || []).filter(e => { const n = days(e.date); return n != null && n >= 0 && n <= WEEK_DAYS; });
  const cols = [];
  for (let i = 0; i <= WEEK_DAYS; i++) { const d0 = new Date(today.getTime() + i * DAY); const es = ev.filter(e => days(e.date) === i);   // by offset: iso() speaks UTC, today is local midnight
    const groups = {}; es.forEach(e => (groups[e.kind] = groups[e.kind] || []).push(e));
    const chip = (kind, list) => { const [lbl, c] = WK_KIND[kind] || [kind, ""], sme = list.every(e => e.sme), n = list.length;
      if (kind.startsWith("lockin")) return `<div class="ev ${c}">${n} anchor lock-in${n > 1 ? "s" : ""} <small>${esc(list.slice(0, 3).map(e => e.name).join(", "))}${n > 3 ? " +" + (n - 3) : ""} · ${lbl.split(" · ")[1]} the book</small></div>`;
      const names = list.slice(0, 3).map(e => esc(e.name)).join(", ") + (n > 3 ? ` +${n - 3}` : "");
      return `<div class="ev ${c}" data-row data-name="${esc(list[0].name)}">${names}<small>${lbl}${kind === "close" && i === 0 ? " · 5 pm" : ""}${kind === "record" && list[0].parent ? " · hold " + esc(list[0].parent) : ""}${sme ? " · SME" : list.some(e => e.sme) ? ` · ${list.filter(e => e.sme).length} SME` : ""}</small></div>`; };
    cols.push(`<div class="wd${i === 0 ? " today" : es.length ? "" : " off"}"><div class="d${es.length ? "" : " dim"}">${d0.toLocaleDateString("en-IN", { weekday: "short", day: "numeric" })}${i === 0 ? "<small>today</small>" : d0.getDate() === 1 ? "<small>" + d0.toLocaleDateString("en-IN", { month: "short" }) + "</small>" : ""}</div>${Object.keys(WK_KIND).filter(k => groups[k]).map(k => chip(k, groups[k])).join("") || `<div class="dt" style="margin-top:6px">—</div>`}</div>`); }
  host.innerHTML = cols.join("");
  const leg = $("#weekLeg"); if (leg) leg.innerHTML = [["accent", "opens"], ["down", "closes"], ["lav", "allotment"], ["up", "₹ back (ASBA unblock)"], ["mint", "lists"], ["amber", "anchor lock-in opens"], ["peach", "quota record date"]].map(([c, l]) => `<span><i style="background:var(--${c})"></i>${l}</span>`).join("")
    + `<span style="margin-left:auto">${(CAL().conflicts || []).length ? `<b class="amb">${CAL().conflicts.length} date${CAL().conflicts.length > 1 ? "s" : ""} where the record and report 554 disagree</b> — the record's day is shown` : "the record and InvestorGain's event calendar agree on every date"}</span>`;
  const sub = $("#weekSub"); if (sub) sub.innerHTML = `today + ${WEEK_DAYS} days · ${ev.length} event${ev.length === 1 ? "" : "s"} · <span ${pv("", provLine("Calendar: the issue records, anchors, quota record dates and InvestorGain report 554", chkAt("planner")))}>collector's calendar</span>`;
}

function plannerRows() {
  const issues = CAL().issues || {};
  return Object.entries(issues).map(([id, it]) => ({ id, it, b: findIssue(it.name) || allIssues().find(b => String(b.igId) === id) || {} }))
    .filter(x => x.it.status === "Open" || (x.it.status === "Upcoming" && days(x.it.open) != null && days(x.it.open) <= WEEK_DAYS))
    .sort((x, y) => String(x.it.close || "").localeCompare(String(y.it.close || "")) || x.it.name.localeCompare(y.it.name));
}

function renderPlanner() {
  const host = $("#planner"); if (!host) return;
  const rows = plannerRows(), B = S.budget || normBudget(null), picked = new Set(B.picks);
  const issues = CAL().issues || {};
  const seg = sme => SEG(sme);
  const tr = ({ id, it, b }) => {
    const sme = !!it.sme, sg = seg(sme), S0 = b.sub || {}, n = days(it.close), lastDay = n === 0, early = it.status === "Open" && !(lastDay && istNow().getHours() >= 14);
    const when = it.status !== "Open" ? `<span class="pill plan">opens ${fmtD(it.open)}</span><div class="dt">closes ${fmtD(it.close)}</div>` : lastDay ? `<span class="pill now">today · 5 pm</span><div class="dt">${fmtD(it.close)}</div>` : `<span class="pill ${n <= 1 ? "now" : n <= 3 ? "soon" : "plan"}">${rel(n)}</span><div class="dt">${fmtD(it.close)}</div>`;
    const blocks = it.blocks || {};
    const cats = CAT_ORDER.filter(k => blocks[k]);
    const catRows = cats.length ? cats.map(k => { const v = blocks[k], key = id + ":" + k; return `<div class="cat"><label><input type="checkbox" data-pick="${esc(key)}"${picked.has(key) ? " checked" : ""}><span class="k">${CAT_NAME[k]}</span></label><span class="num">${inLakh(v.amount)}</span><span class="dt">${v.lots} lot${v.lots === 1 ? "" : "s"}${v.discount ? ` · ₹${v.discount} off` : ""}</span></div>`; }).join("")
      : `<span class="dim">terms not on the record yet</span>`;
    const reuse = (it.fundReuse || []).map(i => issues[i]).filter(Boolean);
    const back = it.releaseDate ? `<b>${fmtD(it.releaseDate)}</b><div class="dt">${it.blockedDays != null ? `${it.blockedDays} day${it.blockedDays === 1 ? "" : "s"} from close` : ""}${it.releaseSrc === "allotment+1" ? " · day after allotment" : ""}${it.listing ? ` · lists ${fmtD(it.listing)}` : ""}</div>${reuse.length ? `<div class="dt up">${esc(reuse.map(r => r.name).join(" and "))} money is back ${fmtD(reuse[0].releaseDate)} — in time (report 607)</div>` : ""}` : `<span class="dim">—</span>`;
    const oddsCell = S0.retail == null ? `<span class="dim">book not open</span>${it.retailSlots ? `<div class="dt">${it.retailSlots.toLocaleString("en-IN")} retail allottees at most</div>` : ""}`
      : `<div>retail <b>${S0.retail}x</b> → ${odds(S0.retail)}</div><div class="dt">${appOdds(b, "retail", "")}${early ? `${appOdds(b, "retail", "") ? " · " : ""}book so far — retail fills on the last day` : ""}</div>` + ["employee", "shareholder", "snii", "bnii"].filter(k => S0[k] != null && blocks[k]).map(k => `<div class="dt">${CAT_NAME[k]} ${S0[k]}x → ${odds(S0[k])}${appOdds(b, k)}</div>`).join("");
    const E1 = evOf(b, sg), evCell = !E1 ? `<span class="dim">—</span><div class="dt">${it.status !== "Open" || S0.retail == null ? "once the retail book opens" : "needs a GMP quote"}</div>`
      : `<div><b class="${early ? "dim" : cls(E1.ev)}" ${pv(`Chance of allotment (at least ${Math.round(E1.p * 1000) / 10}%) × the gain GMP implies, less ${E1.cost.toFixed(2)}% for money blocked ${E1.blocked} days at ${Math.round((EVD().rfAnnual || 0) * 100)}% a year. The chance is a LOWER BOUND.`, PROV.ev(b, sg), PROV.gmp(b), PROV.book(b))}>${pct(E1.ev, true)}</b>${blocks.retail ? ` <span class="dim">≈ ${sgn(Math.round(E1.ev * blocks.retail.amount / 100))}</span>` : ""}</div><div class="dt">of money blocked · ${pct(E1.lo, true)} to ${pct(E1.hi, true)}${E1.prov ? " · provisional" : ""}</div>`
        + ["employee", "shareholder"].filter(k => blocks[k]).map(k => { const E2 = evOf(b, sg, k); return E2 ? `<div class="dt"><b class="${cls(E2.ev)}">${pct(E2.ev, true)}</b> ${k} · ${odds(S0[k])}${E1.ev > 0 && E2.ev > E1.ev ? ` · <b>${(E2.ev / E1.ev).toFixed(E2.ev / E1.ev >= 10 ? 0 : 1)}×</b> retail` : ""}</div>` : `<div class="dt">${k} category — its book is not published yet</div>`; }).join("");
    const T = S0.total != null ? evBand(sg, "total", S0.total, "window") : null, G = b.gmpPct ? evBand(sg, "gmp", b.gmpPct, "window") : null, segLbl = sme ? "SME" : "mainboard", W = sg ? sg.window : null;
    const evid = (T ? `<span class="ev-b ${evCls(T.s)}">${T.s && T.s.n ? `${Math.round(T.s.pos)}% of ${T.s.n} listed up` : "no past cases"}</span><div class="dt">total book ${T.lbl}${early ? " <b>so far</b>" : ""} · ${T.s && T.s.n ? `95% range ${Math.round(T.s.lo)}–${Math.round(T.s.hi)}% · median ${pct(T.s.med, true)}` : "none in this band"}</div>` : `<span class="ev-b na">no book yet</span>`)
      + (G ? `<div class="dt">GMP ${G.lbl}: ${evShort(G.s)}</div>` : "") + (W ? `<div class="dt">${segLbl}, ${W.rule} (${W.n})</div>` : `<div class="dt">no ${segLbl} evidence on file</div>`);
    return `<tr data-row data-name="${esc(it.name)}"><td data-l="Issue"><div class="nm">${esc(it.name)}<span class="seg ${sme ? "s" : "m"}">${sme ? "SME" : "Main"}</span></div><div class="dt">${b.bandHigh ? inr(b.bandHigh) : "band TBA"}${b.lotSize ? ` · ${b.lotSize} sh a lot` : ""}${b.gmp != null ? ` · GMP ${inr(b.gmp)} (${pct(b.gmpPct, true)})` : " · no GMP quote"}${cats.includes("employee") ? " · <b>employee</b> category" : ""}${cats.includes("shareholder") ? " · <b>shareholder</b> category" : ""}</div>${reportLink(b.name ? b : { name: it.name }, "planner")}</td>
      <td data-l="Closes">${when}</td><td data-l="One application blocks">${catRows}</td><td data-l="Money back">${back}</td><td data-l="Allotment odds">${oddsCell}</td><td data-l="EV per application">${evCell}</td><td data-l="Evidence · total book">${evid}</td></tr>`;
  };
  // totals: what the reader ticked, against the budget; the money-back schedule; the longest block
  const ticked = B.picks.map(p => { const [id, k] = p.split(":"), it = issues[id]; return it && it.blocks && it.blocks[k] ? { id, k, it, amt: it.blocks[k].amount } : null; }).filter(Boolean);
  const sum = ticked.reduce((s, t) => s + t.amt, 0), free = B.free != null ? B.free - sum : null;
  const byDay = {}; ticked.forEach(t => { const d0 = t.it.releaseDate || "?"; byDay[d0] = (byDay[d0] || 0) + t.amt; });
  const longest = ticked.reduce((m, t) => t.it.blockedDays != null && t.it.blockedDays > (m ? m.it.blockedDays : -1) ? t : m, null);
  const totals = `<div class="tot">
    <div class="kpi"><div class="lbl">Ticked</div><div class="v mono">${inLakh(sum)}</div><div class="d">${ticked.length} application${ticked.length === 1 ? "" : "s"}${B.free != null ? ` · of ${inLakh(B.free)} free` : " · type the money free above to compare"}</div>${B.free ? `<div class="bar"><i style="width:${Math.min(100, Math.round(100 * sum / B.free))}%;background:var(--${sum > B.free ? "down" : "accent"})"></i></div>` : ""}</div>
    <div class="kpi"><div class="lbl">${free != null && free < 0 ? "Over by" : "Still free"}</div><div class="v mono ${free == null ? "dim" : free < 0 ? "down" : "up"}">${free == null ? "—" : inLakh(Math.abs(free))}</div><div class="d">${free == null ? "no budget typed" : free < 0 ? "more ticked than is free" : `room for ${rows.filter(r => r.it.blocks && r.it.blocks.retail && !picked.has(r.id + ":retail") && r.it.blocks.retail.amount <= free).length} more retail lot${rows.length === 1 ? "" : "s"} this week`}</div></div>
    <div class="kpi"><div class="lbl">Money back</div><div class="v mono" style="font-size:15px">${Object.keys(byDay).sort().map(d0 => `${inLakh(byDay[d0])} · ${d0 === "?" ? "date TBA" : fmtD(d0)}`).join("<br>") || "—"}</div><div class="d">${ticked.length ? `all home by ${fmtD(Object.keys(byDay).filter(k => k !== "?").sort().pop())}` : "tick an application"}</div></div>
    <div class="kpi"><div class="lbl">Longest block</div><div class="v mono">${longest ? `${longest.it.blockedDays} day${longest.it.blockedDays === 1 ? "" : "s"}` : "—"}</div><div class="d">${longest ? `${esc(longest.it.name)} · close to unblock` : ""}</div></div></div>`;
  host.innerHTML = `<div class="pl-in"><span class="lbl">Money free this week</span> <span class="mono" style="font-size:15px">₹ <input class="mono" id="budgetFree" inputmode="numeric" placeholder="1,50,000" value="${B.free != null ? Number(B.free).toLocaleString("en-IN") : ""}" style="width:130px;font-size:15px;font-weight:700"></span> <span class="dt">saved to your account · tick what you will apply for; the sheet adds it up</span></div>
    ${rows.length ? `<div class="tw" style="margin-top:12px"><table class="pl-t"><thead><tr><th>Issue</th><th>Closes</th><th>One application blocks</th><th>Money back</th><th>Allotment odds</th><th>EV per application</th><th>Evidence · total book</th></tr></thead><tbody>${rows.map(tr).join("")}</tbody></table></div>` : `<div class="empty" style="margin-top:12px">No issue is open or opens in the next ${WEEK_DAYS} days.</div>`}
    ${totals}
    <div class="dt" style="margin-top:12px">Odds are a <b>lower bound</b> (lots bid ÷ lots offered); "about 1 in N" is Narada's application count ÷ the RHP's allottee slots, beside it, never instead. EV = that chance × the gain GMP implies (the collector's fit), less the money's time at ${Math.round((EVD().rfAnnual || 0) * 100)}% a year; the range is where 8 in 10 past listings landed. Evidence bands are the collector's, mainboard and SME never pooled, n and the 95% interval always printed. Rows are in order of close — nothing here says apply or skip. Amounts are the record's, at the cap price.</div>`;
  const inp = $("#budgetFree");
  inp.addEventListener("change", () => { const v = Number(String(inp.value).replace(/[^\d.]/g, "")); S.budget.free = inp.value.trim() === "" || isNaN(v) ? null : v; saveBudget(); renderPlanner(); });
  $$("#planner [data-pick]").forEach(c => c.addEventListener("change", () => { const k = c.dataset.pick; S.budget.picks = c.checked ? [...new Set([...S.budget.picks, k])] : S.budget.picks.filter(x => x !== k); saveBudget(); renderPlanner(); }));
}
