"""Headless render check: serve the repo root, open index.html, prove the boot sequence.

  python3 tests/render_check.py          # exit 0 when the page renders live data with no errors

Not a pytest test (needs Chromium); CI can run it as a separate step later.
"""
from __future__ import annotations

import http.server
import json
import pathlib
import socketserver
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8765


def serve():
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(ROOT), **k)
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    from playwright.sync_api import sync_playwright
    httpd = serve()
    errors, logs = [], []
    latest = json.loads((ROOT / "data" / "latest.json").read_text(encoding="utf8"))
    want_label = latest["meta"]["label"]
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                                   args=["--no-sandbox"])
            pg = b.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            # block the CDN so we also prove the page survives without chart.js
            pg.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
            time.sleep(1.5)
            tape = pg.inner_text("#tape") if pg.query_selector("#tape") else ""
            note = pg.inner_text("#dbnote") if pg.query_selector("#dbnote") else ""
            n_el = pg.evaluate("document.querySelectorAll('*').length")
            has_ipo = pg.evaluate("!!window.__ipo")
            as_of = pg.evaluate("window.__ipo && window.__ipo.asOf")
            rows = pg.evaluate("document.querySelectorAll('table tr').length")
            b.close()
    finally:
        httpd.shutdown()

    print(f"elements {n_el}  table rows {rows}  __ipo {has_ipo}  asOf {as_of}")
    print(f"tape: {tape[:120]!r}")
    print(f"note: {note[:160]!r}")
    ok = True
    if errors:
        ok = False
        print("PAGE ERRORS:", *errors, sep="\n  ")
    if not has_ipo:
        ok = False
        print("FAIL: window.__ipo not initialised")
    if as_of != latest["meta"]["asOf"]:
        ok = False
        print(f"FAIL: page asOf {as_of!r} != latest.json asOf {latest['meta']['asOf']!r} — live upgrade did not happen")
    if note and "Could not load" in note:
        ok = False
        print("FAIL: page shows the load-failure banner")
    if n_el < 500:
        ok = False
        print("FAIL: page looks empty")
    for l in logs[:10]:
        print("console", l)
    print("RENDER:", "PASS" if ok else "FAIL", f"— live data from {want_label}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
