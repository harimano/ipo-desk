/* ================= LINKS: the hash is an address =================
   Alerts (collector/alerts.py `link()`) land a reader here; the command bar's Jump writes the same hash, so the address bar is
   a copyable link to what is on screen. Honoured on load and on hashchange, nothing else changes.
     #today|pipe|board|market|research|book|score   the tab
     #board/<name>    Board, the row scrolled into view with its ▾ detail open (the filter widens when the row is hidden)
     #pipe/<name>     Pipeline, that row's detail      #sheet/<name>   the research sheet
   Names are encodeURIComponent'd and matched exactly against row names (rule 6: names are keys). An unknown hash is ignored;
   a name not on the board today leaves the tab selected and says so. The hash wins over the remembered tab for that load only:
   `show()` skips writing `tab` while a hash is being followed (`hashNav`).
   Boot order: the page first renders the built-in snapshot (boot.js), so on load only the tab is selected; the name is landed
   by `landPending()` once `update()` has put the first full document on screen (snapshot names and statuses are stale). */
const TABS = ["today", "pipe", "board", "market", "research", "book", "score"];
const hashFor = (kind, name) => "#" + kind + (name ? "/" + encodeURIComponent(name) : "");
function setHash(h) { if (h && location.hash !== h) history.replaceState(null, "", h); }   // replaceState: no history entry, no hashchange
function parseHash(h) {
  const m = /^#([a-z]+)(?:\/(.*))?$/.exec(h || ""); if (!m || !(TABS.includes(m[1]) || m[1] === "sheet")) return null;
  let name = null; if (m[2] != null) { try { name = decodeURIComponent(m[2]); } catch (e) { return null; } }
  return { kind: m[1], name: name && name.trim() ? name.trim() : null };
}
const missing = () => toast("not on the board today");
const LAND_MS = 20000;
let landed = null;                       // {name, until}: the row a link landed on — re-opened when the board is redrawn soon after
const linkedRow = name => $(`#board tr[data-row][data-name="${CSS.escape(name)}"]`);
function openRow(tr) {
  const bx = tr.nextElementSibling; if (bx && bx.classList.contains("bx")) bx.hidden = false;
  const R = rows(); R.forEach(r => r.classList.toggle("cur", r === tr)); cursor = R.indexOf(tr);
}
function landOnBoard(name) {
  const inSme = sme.some(b => b.name === name), inMain = board.some(b => b.name === name);
  if (!inSme && !inMain) { missing(); return; }
  if (!linkedRow(name)) { bfilter = inSme ? "sme" : "all"; renderBoard(); }            // hidden by the filter: widen it, never rename
  const tr = linkedRow(name); if (!tr) { missing(); return; }
  landed = { name, until: Date.now() + LAND_MS };
  openRow(tr);
  setTimeout(() => tr.scrollIntoView({ block: "center", behavior: "smooth" }), 60);   // after show()'s scrollTo(0,0)
}
/* renderBoard() rebuilds its rows (the account answering, live.json, a refresh) and would close the landed detail
   seconds after the reader arrived; for LAND_MS after a landing the row is re-opened, without scrolling again. */
function keepLanding() {
  if (!landed) return;
  if (Date.now() > landed.until) { landed = null; return; }
  const tr = linkedRow(landed.name); if (tr) openRow(tr);
}
let hashPending = false;
function followHash(h, tabOnly) {
  const p = parseHash(h); if (!p) return false;
  hashNav = true;
  try {
    if (tabOnly) { hashPending = !!p.name; show(p.kind === "sheet" ? "research" : p.kind); }
    else if (p.kind === "sheet") { if (p.name && (sheets[p.name] || current[p.name] || (findIssue(p.name) || {}).facts)) openSheet(p.name); else { show("research"); if (p.name) missing(); } }
    else if (p.kind === "pipe" && p.name) { show("pipe"); if (Q.find(q => q.name === p.name)) openPipe(p.name); else missing(); }
    else if (p.kind === "board" && p.name) { show("board"); landOnBoard(p.name); }
    else show(p.kind);
  } finally { hashNav = false; }
  return true;
}
function landPending() { if (!hashPending) return; hashPending = false; followHash(location.hash); }
window.addEventListener("hashchange", () => { hashPending = false; try { followHash(location.hash); } catch (err) { console.error(err); } });
