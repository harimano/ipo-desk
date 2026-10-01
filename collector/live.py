"""The live loop — a small file, refreshed every few minutes through the market day.

    python -m collector.live --board data/latest.json --out _live/live.json --until 17:20 --interval 300 [--publish _live]

`collect` writes the whole validated document a few times a day. This writes only what moves minute to minute, for
the issues on that document's board, into `live.json` on the `live` branch (one commit, amended and force-pushed, so
the branch never grows). The page lays it over the document it already has.

  subscription   NSE first, every figure carrying its own source (`src`) and timestamp:
                   mainboard   NSE /api/ipo-detail, one call an issue — category-wise, NSE's update time
                   NSE SME     NSE /api/ipo-current-issue, ONE call — the total only (NSE's per-issue SME answer has
                               shares bid but no shares offered, so no multiples)
                   BSE-only    InvestorGain report 566, one call — the only live feed: BSE's own category demand
                               answers "No Records Found" mid-issue for SMEs (surveyed 1 Oct 2026). ~1-2 h behind.
                 Until 1 Oct 2026 everything came from 566, whose stamps ran 1-2 h behind NSE's.
  gmp            InvestorGain report 331: one call (the grey market is off-exchange; NSE has no GMP)
  pre-open       NSE special pre-open session, 09:00-10:05 IST: the indicative listing price of anything listing today
  timeline       each issue's book through the day, [HH:MM, total, qib, retail] — the late QIB surge, visible

A tick is one NSE call per open mainboard issue plus four. An all-zero book is never written: NSE answers zeros for an
issue it does not carry, and the page would lay them over a real book. An NSE block (401/403 after the session's one
re-prime) ends that tick's NSE pass — never retried. A source that fails costs that tick its part and nothing else: the
previous values stay in the file, stamped with their own times. Nothing here touches `latest.json`.
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

from .errors import SourceBlocked, SourceError
from .http import Session
from .modules.subscription import _as_of, combine, has_values
from .sources import investorgain, nse_ipo, nse_preopen

log = logging.getLogger("collector.live")
IST = ZoneInfo("Asia/Kolkata")
PREOPEN_FROM, PREOPEN_TO = dt.time(8, 55), dt.time(10, 5)
TIMELINE_MAX = 120


def board_index(doc: dict, today: dt.date) -> tuple[dict, dict, list]:
    """igId -> row and symbol -> row, for issues that can still move: open, closing/closed today, or listing today; and
    the open rows (a copy tagged with its board), for the subscription pass."""
    by_ig, by_sym, open_rows = {}, {}, []
    t = today.isoformat()
    for key in ("mainboard", "sme"):
        for r in doc.get(key) or []:
            if not isinstance(r, dict) or not r.get("name"):
                continue
            opens, close, listing = r.get("open") or "9999", r.get("close") or "0000", r.get("listing")
            if r.get("igId") and opens <= t <= close:
                by_ig[str(r["igId"])] = r
            if opens <= t <= close and (r.get("symbol") or r.get("igId")):
                open_rows.append({**r, "_board": key})
            if r.get("symbol") and listing == t:
                by_sym[str(r["symbol"]).upper()] = r
    return by_ig, by_sym, open_rows


def nse_sub(session: Session, row: dict) -> dict | None:
    """One mainboard issue's book from NSE, as the `subscription` module reads it; None when there is no real book."""
    d = nse_ipo.ipo_detail(session, row["symbol"], row.get("series") or "EQ")
    sub = combine(d["bidDetails"])
    if not has_values(sub) and d.get("rootTotal") is not None:
        sub["total"] = d["rootTotal"]
    if not real_book(sub):
        return None
    sub["asOf"] = _as_of(d.get("updateTime"))
    return {k: v for k, v in sub.items() if v is not None}


def real_book(sub: dict | None) -> bool:
    """Some category, or the total, above zero — zeros are what a source says when it has nothing."""
    return bool(sub) and any((sub.get(k) or 0) > 0 for k in ("qib", "nii", "retail", "total"))


def tick(session: Session, doc: dict, prev: dict, now: dt.datetime) -> dict:
    """One refresh. `prev` is the last live.json (or {}); returns the next one."""
    by_ig, by_sym, open_rows = board_index(doc, now.date())
    out = {"asOf": now.replace(microsecond=0).isoformat(), "rows": dict(prev.get("rows") or {}), "preopen": list(prev.get("preopen") or []),
           "timeline": dict(prev.get("timeline") or {}), "sources": {}}
    if (prev.get("asOf") or "")[:10] != now.date().isoformat():            # a new day starts clean
        out["rows"], out["preopen"], out["timeline"] = {}, [], {}
    hhmm = now.strftime("%H:%M")

    def put(row: dict, sub: dict, src: str):
        sub = {**{k: v for k, v in sub.items() if v is not None}, "src": src}
        out["rows"].setdefault(row["name"], {})["sub"] = sub
        point = [sub.get("total"), sub.get("qib"), sub.get("retail")]
        line = out["timeline"].setdefault(row["name"], [])
        if not line or line[-1][1:] != point:
            line.append([hhmm, *point])
            del line[:-TIMELINE_MAX]

    status, covered = [], set()
    if open_rows:
        # 1. NSE's list: which open issues NSE carries, and each one's total, in one call
        nse_list, blocked = {}, False
        try:
            nse_list = {str(r["symbol"]).upper(): r for r in nse_ipo.current_issues(session) if r.get("symbol")}
        except SourceBlocked as e:
            blocked = True
            status.append(f"nse {e.kind}")
        except SourceError as e:
            status.append(f"nse list {e.kind}")
        stamp = now.replace(second=0, microsecond=0).isoformat()
        n_main, n_sme = 0, 0
        for row in open_rows:
            listed = nse_list.get(str(row.get("symbol") or "").upper())
            if not listed or blocked:
                continue
            covered.add(row["name"])
            if row.get("_board") == "mainboard":
                # 2. mainboard: NSE's category split, one call each
                try:
                    s = nse_sub(session, row)
                except SourceBlocked as e:
                    blocked = True
                    status.append(f"nse {e.kind}")
                    continue
                except SourceError:
                    s = None
                if s:
                    put(row, s, "nse")
                    n_main += 1
                    continue
            total = listed.get("totalSub")
            if total is not None and total > 0:
                put(row, {"total": round(float(total), 2), "asOf": stamp}, "nse")
                n_sme += 1
        status.append(f"nse {n_main} split + {n_sme} total")
        # 3. what NSE does not carry: InvestorGain's report, matched by igId, never by name
        rest = {str(r["igId"]): r for r in open_rows if r["name"] not in covered and r.get("igId")}
        if rest:
            try:
                n_ig = 0
                for s in investorgain.fetch_subscription_report(session, now.date()):
                    row = rest.get(s["igId"])
                    if row and real_book(s):
                        put(row, {k: v for k, v in s.items() if k != "igId"}, "investorgain")
                        n_ig += 1
                status.append(f"investorgain {n_ig}/{len(rest)}")
            except SourceError as e:
                status.append(f"investorgain {e.kind}")
    out["sources"]["subscription"] = "; ".join(status)[:120] if status else "ok"

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


def trading_holiday(session: Session, day: dt.date) -> str | None:
    """NSE's equity-segment holiday for `day` (its description), else None. Fails open: a list that will not load
    never costs a trading day."""
    try:
        data = session.nse_json("/api/holiday-master", {"type": "trading"}, source="nse_holidays")
    except SourceError as e:
        log.warning("holiday list unavailable (%s); running anyway", e.kind)
        return None
    want = day.strftime("%d-%b-%Y").lower()
    for h in (data.get("CM") if isinstance(data, dict) else None) or []:
        if isinstance(h, dict) and str(h.get("tradingDate") or "").lower() == want:
            return str(h.get("description") or "holiday")
    return None


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
    if a.until:                                     # a loop on a market holiday would poll a closed market all day
        why = trading_holiday(session, dt.datetime.now(IST).date())
        if why:
            log.info("NSE trading holiday (%s): no loop today", why)
            return 0
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
