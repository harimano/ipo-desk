#!/usr/bin/env python3
"""deploy.yml: fold GitHub's run list and the live branch's last commit into _site/admin/runs.json for /admin.

  python3 scripts/runs_snapshot.py <runs.json from gh api> <live commit json> <out>

Why a snapshot: the browser's own call to api.github.com is unauthenticated, 60 an hour per address, and shared with
the page's live polling — on 29 Oct 2026 the admin page opened with three "?" tiles because that hour's calls were
gone. The Actions token has no such limit; every collect deploys, so this is at most one run old.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys


def main(argv: list[str]) -> int:
    runs_p, live_p, out_p = (pathlib.Path(a) for a in argv[1:4])
    try:
        runs = json.loads(runs_p.read_text(encoding="utf8") or "[]")
    except Exception as e:
        print(f"runs: unreadable ({e}); writing an empty list", file=sys.stderr)
        runs = []
    live = None
    try:
        c = json.loads(live_p.read_text(encoding="utf8") or "null")
        if c:
            m = re.search(r"live: (\S+)", c.get("msg") or "")
            live = {"at": c.get("at"), "asOf": m.group(1) if m else c.get("at")}     # live.py's message carries live.json's asOf
    except Exception as e:
        print(f"live: unreadable ({e})", file=sys.stderr)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps({"at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "runs": runs if isinstance(runs, list) else [],
                                 "live": live}, separators=(",", ":")), encoding="utf8")
    print(f"runs.json: {len(runs)} runs, live {live and live['asOf']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
