"""python -m collector [--only calendar,gmp] [--dry-run] [--data DIR] [--max-seconds 600]

Exit codes: 0 wrote latest.json · 2 every module failed, nothing written · 3 ownership violation.
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import pathlib
import signal
import sys
import time

from . import assemble
from .http import Session
from .result import Result

# Order is the fallback logic: a later module's patch wins. `details` (the fullest record) runs after `gmp` so its
# fresher quote overwrites the cached report, and before `subscription` / `listings` so the exchanges' live book and
# the traded listing price overwrite its copies when they answer — and its copies stand when they do not.
MODULES = ["calendar", "gmp", "details", "subscription", "listings", "history", "evidence", "players", "parents", "filings", "offers", "flows", "deals", "news"]
log = logging.getLogger("collector")


class Budget:
    """A whole-run wall-clock budget. SIGALRM is the one thing that can interrupt a stuck call."""
    def __init__(self, seconds: int):
        self.seconds = seconds

    def __enter__(self):
        signal.signal(signal.SIGALRM, self._fire)
        signal.alarm(self.seconds)
        return self

    def __exit__(self, *a):
        signal.alarm(0)

    @staticmethod
    def _fire(signum, frame):
        raise TimeoutError("run budget exceeded")


def run_module(name: str, session: Session, prev: dict, budget_left: float, doc: dict | None = None) -> Result:
    res = Result(module=name, doc=json.loads(json.dumps(doc)) if doc is not None else None)
    t0 = time.monotonic()
    calls0 = session.calls
    try:
        mod = importlib.import_module(f"collector.modules.{name}")
        res = mod.run(session, prev, res)
    except TimeoutError:
        raise
    except Exception as e:  # a module crash is a stale section, not a dead run
        log.exception("module %s crashed", name)
        res.fail(e)
    res.elapsed = round(time.monotonic() - t0, 2)
    res.calls = session.calls - calls0
    log.info("%-13s %s  %s  %.1fs  %d calls  %s", name, "ok   " if res.ok else "FAIL ", res.source or "-",
             res.elapsed, res.calls, (res.error or {}).get("detail", "") if not res.ok else "")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated module names")
    ap.add_argument("--data", default="data", help="data directory (default ./data)")
    ap.add_argument("--dry-run", action="store_true", help="assemble but do not write")
    ap.add_argument("--max-seconds", type=int, default=600)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s", datefmt="%H:%M:%S")

    root = pathlib.Path(a.data)
    prev = assemble.load_previous(root / "latest.json")
    data = json.loads(json.dumps(prev))                    # deep copy: modules see prev, we mutate data
    session = Session()
    t_start = time.monotonic()
    names = [m.strip() for m in a.only.split(",")] if a.only else MODULES
    results: list[Result] = []

    try:
        with Budget(a.max_seconds):
            for name in names:
                res = run_module(name, session, prev, a.max_seconds - (time.monotonic() - t_start), doc=data)
                try:
                    assemble.apply(data, res)
                except assemble.OwnershipError as e:
                    log.error("OWNERSHIP: %s", e)
                    return 3
                results.append(res)
    except TimeoutError:
        log.error("run budget of %ds exceeded after %d modules; assembling what we have", a.max_seconds, len(results))
    finally:
        session.close()

    ok_count = sum(1 for r in results if r.ok)
    if ok_count == 0:
        log.error("every module failed — refusing to write; previous latest.json stays live")
        for r in results:
            log.error("  %s: %s", r.module, (r.error or {}).get("detail"))
        return 2

    research_notes = assemble.load_research_layer(data, root)
    t = assemble.now_ist()
    data["meta"]["unresolved"] = assemble.merge_unresolved(prev["meta"].get("unresolved", []), results)
    assemble.enforce_caps(data)
    assemble.stamp(data, results, t, research_notes, session.calls, time.monotonic() - t_start)

    if a.dry_run:
        print(json.dumps(data["integrity"], indent=1, ensure_ascii=False))
        return 0
    latest, hist = assemble.write(data, root, t)
    removed = assemble.prune_history(root)
    log.info("wrote %s (%d KB) and %s; pruned %d old snapshots", latest, latest.stat().st_size // 1024, hist.name, len(removed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
