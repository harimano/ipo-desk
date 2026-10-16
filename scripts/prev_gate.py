#!/usr/bin/env python3
"""Did the previous collect run refuse at the gate on this same commit? Then an intraday run has nothing new to say.

16 Oct 2026: one gate refusal (recent[]/sources ageing out in a lump) was repeated by every 30-minute intraday slot,
~20 identical failure mails in a day. The refusal is the signal and must stay red in `gh run list`; its copies are
noise. So the Mode step of collect.yml asks this script, on intraday runs only, before paying for the install:

    python3 scripts/prev_gate.py --run-id <this run> --sha <this commit>     # prints a "::warning::" and exits 3 to skip

Exit 0 = go (no refusal to repeat, or the API could not be read: a flaky API never silences a run). Exit 3 = the last
completed collect run failed at the Gate step on the same main commit: the refusal is printed as a workflow warning
(the run page shows it, the job summary carries it) and the caller skips. Full runs never ask: they retry, and fail
loudly, twice a day; a push to main (a fix) changes the sha and the next intraday run goes too.

Three `gh` calls: run list, the failed run's jobs, that job's log (for the validator's FAIL lines). Runs on the
runner's own python3 and gh, no install.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

GATE_STEP = "Gate"            # the step's name starts with this (collect.yml)
SKIP = 3
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_STAMP = re.compile(r"^\S+Z ")  # the log's per-line timestamp


def previous_run(runs: list[dict], this_id: int) -> dict | None:
    """The newest completed run that is not this one. None when there is none."""
    for r in runs:
        if int(r.get("databaseId") or 0) == this_id:
            continue
        if r.get("status") == "completed":
            return r
    return None


def gate_job(jobs: list[dict]) -> dict | None:
    """The job whose Gate step failed, else None (a run that failed anywhere else is retried as usual)."""
    for j in jobs:
        for s in j.get("steps") or []:
            if str(s.get("name", "")).startswith(GATE_STEP) and s.get("conclusion") == "failure":
                return j
    return None


def gate_message(log: str) -> str:
    """The validator's verdict from the job log: the FAIL line and its bullets, timestamps and colour stripped."""
    lines = [_STAMP.sub("", _ANSI.sub("", ln)).rstrip() for ln in log.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln.startswith("FAIL"):
            out = [ln]
        elif out and ln.startswith("  · "):
            out.append(ln.strip())
        elif out:
            break
    return " ".join(out) if out else "message not found in the job log"


def decide(runs: list[dict], this_id: int, sha: str, jobs_of, log_of) -> str | None:
    """The warning to print when this run should skip, else None. `jobs_of(run)` and `log_of(job)` do the fetching."""
    prev = previous_run(runs, this_id)
    if not prev or prev.get("conclusion") != "failure":
        return None
    if prev.get("headSha") != sha:
        return None                      # main moved since: maybe a fix, so run
    job = gate_job(jobs_of(prev))
    if job is None:
        return None
    msg = gate_message(log_of(job))
    when = str(prev.get("createdAt", ""))[:16].replace("T", " ") + " UTC"
    return (f"gate refused at {when} ({prev.get('url', '')}): {msg} — intraday skipped until the next full run "
            f"or a push to main")


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, timeout=60).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", type=int, required=True, help="this run's id (github.run_id)")
    ap.add_argument("--sha", required=True, help="this run's commit (github.sha)")
    ap.add_argument("--repo", required=True, help="owner/name (github.repository)")
    ap.add_argument("--workflow", default="collect.yml")
    a = ap.parse_args(argv)
    try:
        runs = json.loads(_gh("run", "list", "--repo", a.repo, "--workflow", a.workflow, "--limit", "5", "--json",
                              "databaseId,status,conclusion,headSha,createdAt,url"))

        def jobs_of(run: dict) -> list[dict]:
            return json.loads(_gh("api", f"repos/{a.repo}/actions/runs/{run['databaseId']}/jobs"))["jobs"]

        def log_of(job: dict) -> str:
            return _gh("api", "--allow-escape-sequences", f"repos/{a.repo}/actions/jobs/{job['id']}/logs")

        warning = decide(runs, a.run_id, a.sha, jobs_of, log_of)
    except (subprocess.SubprocessError, OSError, ValueError, KeyError) as e:   # could not read: go, never silence
        print(f"prev_gate: could not read the previous run ({e!r}); running")
        return 0
    if warning is None:
        print("prev_gate: no gate refusal to repeat")
        return 0
    print(f"::warning::{warning}")
    return SKIP


if __name__ == "__main__":
    sys.exit(main())
