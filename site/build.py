"""Build the whole publishable site into _site/ — what Pages serves and what a local preview serves.

  python site/build.py             # reads site/src/{inner.html,account.js,app.js,boot.js} and data/
                                   # writes _site/index.html, _site/data/{meta,board,...}.json (collector/layout.py),
                                   #        _site/data/latest.json, _site/data/research/, _site/data/quota-reviews/, _site/data/logos/

The page is: chart.js tag + inner markup + <script>FALLBACK + account.js + app.js + boot.js</script>.
FALLBACK is the small snapshot (meta, mainboard, sme, quota, lot) taken from data/latest.json at
build time, so the page is never blank even if the fetch fails. CI rebuilds the page after every
collector run, so the snapshot is at most one run old.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector import layout

SITE = ROOT / "_site"
SRC = ROOT / "site" / "src"
FALLBACK_KEYS = ["meta", "mainboard", "sme", "quota", "lot"]

CHARTJS = ('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.js" '
           'integrity="sha384-iU8HYtnGQ8Cy4zl7gbNMOhsDTTKX02BTXptVP/vqAWIaTfM7isw76iyZCsjL2eVi" '
           'crossorigin="anonymous"></script>\n')

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>India IPO Command Center</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📈</text></svg>">
<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<meta name="theme-color" content="#2f6fed">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="IPO Desk">
"""
# Home-screen install (site/src/install.js): the manifest is fetched WITH the Access cookie (crossorigin=use-credentials),
# or the gated Worker would answer the login redirect and the browser would call the page uninstallable.


def main() -> int:
    inner = (SRC / "inner.html").read_text(encoding="utf8")
    app = (SRC / "app.js").read_text(encoding="utf8")
    # new screens live in their own files; `/* @include name.js */` inside app.js pulls one into its scope
    app = re.sub(r"/\* @include ([\w.-]+) \*/", lambda m: (SRC / m.group(1)).read_text(encoding="utf8"), app)
    account = (SRC / "account.js").read_text(encoding="utf8")   # the reader's account: runs before app.js so its store is ready
    boot = (SRC / "boot.js").read_text(encoding="utf8")
    latest_path = ROOT / "data" / "latest.json"
    if not latest_path.exists():
        print("data/latest.json missing — build the fallback from site/src/fallback.json", file=sys.stderr)
        fb = json.loads((SRC / "fallback.json").read_text(encoding="utf8"))
    else:
        data = json.loads(latest_path.read_text(encoding="utf8"))
        fb = {k: data[k] for k in FALLBACK_KEYS if k in data}
        for k in ("mainboard", "sme"):                       # the snapshot only has to paint the board; facts arrive with the fetch
            fb[k] = [{f: v for f, v in r.items() if f != "facts"} for r in fb.get(k) or []]
        missing = [k for k in FALLBACK_KEYS if k not in fb]
        if missing:
            raise SystemExit(f"fallback keys missing from latest.json: {missing}")

    inner = inner.replace("<!--INNER-START-->", "", 1)
    fb_js = "const FALLBACK = " + json.dumps(fb, ensure_ascii=False, separators=(",", ":")) + ";\n"
    script = "<script>\n" + fb_js + account + app + boot + "</script>\n"
    html = HEAD + CHARTJS + "</head>\n<body>\n" + inner + script + "</body>\n</html>\n"
    SITE.mkdir(exist_ok=True)
    out = SITE / "index.html"
    out.write_text(html, encoding="utf8")
    kb = lambda n: f"{n / 1024:.1f} KB"
    print(f"fallback {kb(len(fb_js))}  render {kb(len(app) + len(boot))}  -> {out.relative_to(ROOT)} {kb(out.stat().st_size)}")

    shutil.copy(SRC / "manifest.webmanifest", SITE / "manifest.webmanifest")
    icons = SITE / "icons"
    if icons.exists():
        shutil.rmtree(icons)
    shutil.copytree(SRC / "icons", icons)
    data_out = SITE / "data"
    if data_out.exists():
        shutil.rmtree(data_out)
    data_out.mkdir()
    if latest_path.exists():
        parts = layout.split(data)
        if layout.join(parts) != data:
            raise SystemExit("layout split/join did not round-trip — refusing to publish")
        for name, body in parts.items():
            (data_out / name).write_bytes(body)
        shutil.copy(latest_path, data_out / "latest.json")     # the whole document, for people and for old tabs
        print("layout   " + ", ".join(f"{n} {kb(len(b))}" for n, b in parts.items()))
    for d in ("research", "quota-reviews", "logos"):
        if (ROOT / "data" / d).is_dir():
            shutil.copytree(ROOT / "data" / d, data_out / d)
    build_admin(data if latest_path.exists() else None)
    return 0


def build_admin(data: dict | None) -> None:
    """/admin: the ops page (site/admin/), served to ADMIN_EMAIL only by the Worker, and its audit.json
    (scripts/audit.py) from the same document the page was built from. A missing document still builds the page."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit", ROOT / "scripts" / "audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    adm = SRC.parent / "admin"
    html = (adm / "admin.html").read_text(encoding="utf8")
    html = html.replace("/* @include admin.js */", (adm / "admin.js").read_text(encoding="utf8"), 1)
    out = SITE / "admin"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf8")
    if data is None:
        return
    logos = ROOT / "data" / "logos"
    rep = audit.build(data, audit.previous(data, ROOT / "data" / "history"), logos if logos.is_dir() else None)
    (out / "audit.json").write_text(json.dumps(rep, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    print(f"admin    verdict {rep['verdict']['level']} · {len(rep['verdict']['items'])} item(s) · {len(rep['audit'])} audit finding(s)")


if __name__ == "__main__":
    sys.exit(main())
