/* ================= ADD TO HOME SCREEN =================
   The page ships a web manifest and icons (site/src/manifest.webmanifest, icons/; build.py copies them, the HEAD links
   them with crossorigin=use-credentials so the manifest fetch carries the Access cookie). No service worker, so
   nothing is cached offline beyond the per-reader state (the plan asked for none): Chrome then offers "Install app"
   from its own menu but never fires beforeinstallprompt (developer.chrome.com/blog/update-install-criteria), and
   Safari has no prompt at all — so this card shows the device's own steps rather than a button that cannot work. */
const installStandalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
function installSteps() {
  const ua = navigator.userAgent, ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1), android = /Android/.test(ua), safari = /Safari/.test(ua) && !/Chrome|CriOS|FxiOS|EdgiOS/.test(ua);
  if (installStandalone()) return { t: "Already on your home screen", s: ["You are reading this from the installed desk. Open it from the icon any time; it signs in with the same email code."] };
  if (ios) return { t: safari ? "Add to home screen (iPhone, Safari)" : "Add to home screen (iPhone)", s: safari ? ["Tap <b>Share</b> at the bottom of Safari (the square with an arrow).", "Scroll and choose <b>Add to Home Screen</b>.", "Tap <b>Add</b>. The desk opens full-screen, signed in."] : ["Open this page in <b>Safari</b> (Chrome on iPhone cannot add it).", "Tap <b>Share</b>, then <b>Add to Home Screen</b>, then <b>Add</b>."] };
  if (android) return { t: "Add to home screen (Android)", s: ["Tap the <b>⋮</b> menu at the top right of Chrome.", "Choose <b>Add to Home screen</b> (or <b>Install app</b>).", "Tap <b>Add</b>. The desk opens full-screen, signed in."] };
  return { t: "Install on this computer", s: ["Chrome and Edge: click the <b>install</b> icon at the right end of the address bar, or <b>⋮ → Cast, save and share → Install page as app</b>.", "Safari on a Mac: <b>File → Add to Dock</b>.", "On your phone, open ipodesk.dev and use <b>Add to Home Screen</b> from the browser's share or menu."] };
}
function installOpen() {
  const ov = $("#install"); if (!ov) return;
  const I = installSteps();
  ov.querySelector(".walk").innerHTML = `<div class="top"><div class="n">Home screen</div><button class="skip" data-install="close">Close</button></div>
    <div class="body"><div class="ihome"><div class="ic"><img src="/icons/icon-192.png" width="58" height="58" alt=""></div><div class="nm">IPO Desk</div></div><h2>${I.t}</h2><ol class="isteps">${I.s.map(x => `<li>${x}</li>`).join("")}</ol>
    <div class="where">No offline copy is kept: the desk needs the network, and stays signed in for the length of your Access session.</div></div>
    <div class="foot"><button class="btn primary next" data-install="close">Done</button></div>`;
  ov.hidden = false; document.body.classList.add("intro-open");
}
function installClose() { const ov = $("#install"); if (!ov || ov.hidden) return; ov.hidden = true; document.body.classList.remove("intro-open"); }
$("#install").addEventListener("click", e => { if (e.target.closest("[data-install]") || e.target === e.currentTarget) installClose(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#install").hidden) installClose(); });
document.addEventListener("click", e => { const b = e.target.closest("[data-install-open]"); if (!b) return; const m = $("#acctMenu"); if (m) m.hidden = true; installOpen(); });
if (installStandalone()) $$("[data-install-open]").forEach(b => b.hidden = true);
