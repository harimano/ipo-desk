"""The live loop — a small file, refreshed every few minutes through the market day.

    python -m collector.live --board data/latest.json --out _live/live.json --until 17:20 --interval 300 [--publish _live]

`collect` writes the whole validated document a few times a day. This writes only what moves minute to minute, for
the issues on that document's board, into `live.json` on the `live` branch (one commit, amended and force-pushed, so
the branch never grows). The page lays it over the document it already has.

  subscription   InvestorGain report 566: every issue's book in ONE call, with the site's own bid timestamp
  gmp            InvestorGain report 331: one call
  pre-open       NSE special pre-open session, 09:00-10:05 IST: the indicative listing price of anything listing today
  timeline       each issue's book through the day, [HH:MM, total, qib, retail] — the late QIB surge, visible

Three calls per tick. Rows are matched by `igId`, never by name. A source that fails costs that tick its part and
nothing else: the previous values stay in the file, stamped with their own times. Nothing here touches `latest.json`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import pathlib
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from .errors import SourceError
from .http import Session
from .sources import investorgain, nse_preopen

log = logging.getLogger("collector.live")
IST = ZoneInfo("Asia/Kolkata")
PREOPEN_FROM, PREOPEN_TO = dt.time(8, 55), dt.time(10, 5)
TIMELINE_MAX = 120


def board_index(doc: dict, today: dt.date) -> tuple[dict, dict]:
    """igId -> row and symbol -> row, for issues that can still move: open, closing/closed today, or listing today."""
    by_ig, by_sym = {}, {}
    t = today.isoformat()
    for key in ("mainboard", "sme"):
        for r in doc.get(key) or []:
            if not isinstance(r, dict) or not r.get("name"):
                continue
            opens, close, listing = r.get("open") or "9999", r.get("close") or "0000", r.get("listing")
            if r.get("igId") and opens <= t <= close:
                by_ig[str(r["igId"])] = r
            if r.get("symbol") and listing == t:
                by_sym[str(r["symbol"]).upper()] = r
    return by_ig, by_sym


def tick(session: Session, doc: dict, prev: dict, now: dt.datetime) -> dict:
    """One refresh. `prev` is the last live.json (or {}); returns the next one."""
    by_ig, by_sym = board_index(doc, now.date())
    out = {"asOf": now.replace(microsecond=0).isoformat(), "rows": dict(prev.get("rows") or {}), "preopen": list(prev.get("preopen") or []),
           "timeline": dict(prev.get("timeline") or {}), "sources": {}}
    if (prev.get("asOf") or "")[:10] != now.date().isoformat():            # a new day starts clean
        out["rows"], out["preopen"], out["timeline"] = {}, [], {}
    hhmm = now.strftime("%H:%M")

    try:
        for s in investorgain.fetch_subscription_report(session, now.date()):
            row = by_ig.get(s["igId"])
            if not row:
                continue
            cur = out["rows"].setdefault(row["name"], {})
            cur["sub"] = {k: v for k, v in s.items() if k != "igId" and v is not None}
            line = out["timeline"].setdefault(row["name"], [])
            if not line or line[-1][1:] != [s["total"], s["qib"], s["retail"]]:
                line.append([hhmm, s["total"], s["qib"], s["retail"]])
                del line[:-TIMELINE_MAX]
        out["sources"]["subscription"] = "ok"
    except SourceError as e:
        out["sources"]["subscription"] = f"{e.kind}: {e.detail}"[:120]

    try:
        for g in investorgain.fetch(session, now.date()):
            row = by_ig.get(str(g.get("igId")))
            if row and g.get("gmp") is not None:
                cur = out["rows"].setdefault(row["name"], {})
                cur["gmp"], cur["gmpPct"], cur["gmpAsOf"] = g["gmp"], g.get("gmpPct"), out["asOf"]
        out["sources"]["gmp"] = "ok"
    except SourceError as e:
        out["sources"]["gmp"] = f"{e.kind}: {e.detail}"[:120]

    if by_sym and PREOPEN_FROM <= now.time() <= PREOPEN_TO:
        try:
            seen = [{"name": by_sym[p["symbol"]]["name"], **p} for p in nse_preopen.fetch(session) if p["symbol"] in by_sym]
            if seen:
                out["preopen"] = seen
            out["sources"]["preopen"] = "ok"
        except SourceError as e:
            out["sources"]["preopen"] = f"{e.kind}: {e.detail}"[:120]
    return out


def publish(repo_dir: pathlib.Path, stamp: str) -> None:
    """One commit on the `live` branch, replaced every time: the branch never grows."""
    def git(*a):
        return subprocess.run(["git", "-C", str(repo_dir), *a], check=True, capture_output=True, text=True).stdout
    git("add", "live.json")
    if not git("status", "--porcelain").strip():
        return
    git("-c", "user.name=ipo-desk-bot", "-c", "user.email=ipo-desk-bot@users.noreply.github.com", "commit", "--amend", "-m", f"live: {stamp}")
    git("push", "--force", "origin", "HEAD:live")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--board", required=True, help="the collector's latest.json (board rows with igId / symbol)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--until", default=None, help="HH:MM IST; omit for a single tick")
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--publish", default=None, help="a checkout of the live branch to commit and force-push from")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s", datefmt="%H:%M:%S")
    out_p, session = pathlib.Path(a.out), Session()
    prev = json.loads(out_p.read_text()) if out_p.exists() and out_p.stat().st_size > 2 else {}
    while True:
        now = dt.datetime.now(IST)
        doc = json.loads(pathlib.Path(a.board).read_text())
        nxt = tick(session, doc, prev, now)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(nxt, ensure_ascii=False, separators=(",", ":")))
        log.info("tick: %d rows, %d pre-open, sources %s", len(nxt["rows"]), len(nxt["preopen"]), nxt["sources"])
        if a.publish:
            try:
                publish(pathlib.Path(a.publish), nxt["asOf"])
            except subprocess.CalledProcessError as e:
                log.warning("publish failed: %s", (e.stderr or "")[-200:])
        prev = nxt
        if not a.until or now.strftime("%H:%M") >= a.until:
            return 0
        time.sleep(max(30, a.interval - (dt.datetime.now(IST) - now).total_seconds()))


if __name__ == "__main__":
    sys.exit(main())
