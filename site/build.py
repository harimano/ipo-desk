"""Build the whole publishable site into _site/ — what Pages serves and what a local preview serves.

  python site/build.py             # reads site/src/{inner.html,app.js,boot.js} and data/
                                   # writes _site/index.html, _site/data/{meta,board,...}.json (collector/layout.py),
                                   #        _site/data/latest.json, _site/data/research/, _site/data/quota-reviews/

The page is: chart.js tag + inner markup + <script>FALLBACK + app.js + boot.js</script>.
FALLBACK is the small snapshot (meta, mainboard, sme, quota, lot) taken from data/latest.json at
build time, so the page is never blank even if the fetch fails. CI rebuilds the page after every
collector run, so the snapshot is at most one run old.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector import layout  # noqa: E402

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
"""


def main() -> int:
    inner = (SRC / "inner.html").read_text(encoding="utf8")
    app = (SRC / "app.js").read_text(encoding="utf8")
    boot = (SRC / "boot.js").read_text(encoding="utf8")
    latest_path = ROOT / "data" / "latest.json"
    if not latest_path.exists():
        print("data/latest.json missing — build the fallback from site/src/fallback.json", file=sys.stderr)
        fb = json.loads((SRC / "fallback.json").read_text(encoding="utf8"))
    else:
        data = json.loads(latest_path.read_text(encoding="utf8"))
        fb = {k: data[k] for k in FALLBACK_KEYS if k in data}
        missing = [k for k in FALLBACK_KEYS if k not in fb]
        if missing:
            raise SystemExit(f"fallback keys missing from latest.json: {missing}")

    inner = inner.replace("<!--INNER-START-->", "", 1)
    fb_js = "const FALLBACK = " + json.dumps(fb, ensure_ascii=False, separators=(",", ":")) + ";\n"
    script = "<script>\n" + fb_js + app + boot + "</script>\n"
    html = HEAD + CHARTJS + "</head>\n<body>\n" + inner + script + "</body>\n</html>\n"
    SITE.mkdir(exist_ok=True)
    out = SITE / "index.html"
    out.write_text(html, encoding="utf8")
    kb = lambda n: f"{n / 1024:.1f} KB"  # noqa: E731
    print(f"fallback {kb(len(fb_js))}  render {kb(len(app) + len(boot))}  -> {out.relative_to(ROOT)} {kb(out.stat().st_size)}")

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
    for d in ("research", "quota-reviews"):
        if (ROOT / "data" / d).is_dir():
            shutil.copytree(ROOT / "data" / d, data_out / d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
