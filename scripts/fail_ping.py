"""One ntfy line when a collect run fails, so a red run reaches the phone and not only GitHub's mail.

  python scripts/fail_ping.py            # prints the line; posts it when NTFY_TOPIC is set
  python scripts/fail_ping.py --dry-run  # prints the line, never posts (NTFY_TOPIC is not read)

Reads from the environment: STEPS (the workflow's `toJSON(steps)`), RUN_URL, RUN_ID, MODE, DRILL ("true" fakes a
refusal at the Gate and says DRILL), NTFY_TOPIC (trimmed; silent when unset). The topic is never printed.
A gate refusal also prints a ::warning:: so the run page carries it. Stdlib only: it runs when pip install failed.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

TITLES = {
    "mode": "mode check", "install": "Install", "layover": "lay the live document over ./data",
    "collect": "Collect", "gate": "Gate (validator refused to write)", "site": "Build the site",
    "commit": "Commit to the data branch", "publish": "Publish (dispatch deploy)",
}


def failing(steps: dict) -> str | None:
    for sid, s in steps.items():
        if (s or {}).get("outcome") == "failure":
            return sid
    return None


def build(env) -> tuple[str, str | None]:
    drill = env.get("DRILL", "").lower() == "true"
    steps = {"gate": {"outcome": "failure"}} if drill else json.loads(env.get("STEPS") or "{}")
    sid = failing(steps)
    what = TITLES.get(sid, sid) if sid else "a step before the collector (checkout / setup / runner)"
    run = env.get("RUN_URL") or f"run {env.get('RUN_ID', '?')}"
    line = f"{'DRILL: ' if drill else ''}collect ({env.get('MODE') or '?'}) FAILED at: {what}. {run}"
    warn = (f"::warning::the Gate refused to write — {run}" if sid == "gate" else None)
    return line, warn


def post(line: str, topic: str) -> int:
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=line.encode("utf-8"), method="POST",
                                 headers={"Title": "IPO desk - collect failed", "Priority": "high", "Tags": "warning"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except Exception as e:
        print(f"ntfy post failed: {type(e).__name__}", file=sys.stderr)
        return 0


def main(argv: list[str]) -> int:
    line, warn = build(os.environ)
    print(line)
    if warn:
        print(warn)
    if "--dry-run" in argv:
        return 0
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("NTFY_TOPIC unset - not sending")
        return 0
    raw = os.environ.get("NTFY_TOPIC", "")
    print(f"ntfy: topic is {len(topic)} characters ({len(raw) - len(topic)} of whitespace trimmed)")   # length only: compare it with the phone's subscription
    print(f"ntfy: status {post(line, topic)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
