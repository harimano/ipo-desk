#!/usr/bin/env python3
"""Day-one test: can THIS runner reach each primary source, through the collector's own HTTP layer?

Prints a table and writes reachability.json. Exit 0 always — the point is the report, not a gate.
Run it from GitHub Actions first (workflow: reachability). The answer decides whether the cron
lives on Actions or moves to Cloudflare Workers.
"""
from __future__ import annotations

import json
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from collector.http import Session, NSE, NSE_ARCHIVES, BSE_API, BSE_BETA, SEBI  # noqa: E402
from collector.errors import SourceError  # noqa: E402

PROBES = [
    # name, kind, target, params
    ("nse.prime",            "nse_prime", None, None),
    ("nse.ipo-current",      "nse_json",  "/api/ipo-current-issue", None),
    ("nse.upcoming",         "nse_json",  "/api/all-upcoming-issues", {"category": "ipo"}),
    ("nse.ipo-detail",       "nse_json",  "/api/ipo-detail", {"symbol": "RELIANCE", "series": "EQ"}),
    ("nse.fiidii",           "nse_json",  "/api/fiidiiTradeReact", None),
    ("nse.announcements",    "nse_json",  "/api/corporate-announcements", {"index": "equities", "symbol": "RELIANCE"}),
    ("nsearchives.bulk.csv", "get_text",  NSE_ARCHIVES + "/content/equities/bulk.csv", None),
    ("nsearchives.block.csv","get_text",  NSE_ARCHIVES + "/content/equities/block.csv", None),
    ("bse.announcements",    "bse_json",  "/AnnSubCategoryGetData/w",
        {"pageno": 1, "strCat": -1, "subcategory": -1, "strPrevDate": time.strftime("%Y%m%d"),
         "strToDate": time.strftime("%Y%m%d"), "strSearch": "P", "strscrip": "500325", "strType": "C"}),
    ("bse.beta.public-issues","get_text", BSE_BETA + "/markets/PublicIssues/IPOIssues_new.aspx", {"id": 1, "Type": "p"}),
    ("sebi.drhp-list",       "get_text",  SEBI + "/sebiweb/home/HomeAction.do",
        {"doListing": "yes", "sid": 3, "ssid": 15, "smid": 10}),
    ("investorgain.gmp-v2",  "get_json",  "https://webnodejs.investorgain.com/cloud/v2/report/data-read/331/1/9/2026/2026-27/0/all", None),
    ("ipowatch.gmp",         "get_text",  "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/", None),
    ("ipopremium.gmp",       "get_text",  "https://ipopremium.in/", None),
    ("chittorgarh.sub",      "get_text",  "https://www.chittorgarh.com/report/ipo-subscription-status-live-bidding-data-bse-nse/21/", None),
    ("yahoo.chart",          "get_json",  "https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS", {"range": "5d", "interval": "1d"}),
    ("rss.bs-markets",       "get_text",  "https://www.business-standard.com/rss/markets-106.rss", None),
]


def main() -> int:
    s = Session()
    rows = []
    for name, kind, target, params in PROBES:
        t0 = time.monotonic()
        status, detail, size = "ok", "", 0
        try:
            if kind == "nse_prime":
                ok = s.nse_prime()
                status, detail = ("ok" if ok else "unprimed"), "cookie prime via issue-information"
            elif kind == "nse_json":
                data = s.nse_json(target, params, source=name)
                size = len(json.dumps(data))
                detail = f"json {type(data).__name__}, {len(data) if hasattr(data, '__len__') else '?'} top-level"
            elif kind == "bse_json":
                data = s.bse_json(target, params, source=name)
                size = len(json.dumps(data))
                detail = f"json keys {list(data)[:4] if isinstance(data, dict) else 'list'}"
            elif kind == "get_json":
                data = s.get_json(target, source=name, params=params)
                size = len(json.dumps(data))
                detail = "json"
            else:
                text = s.get_text(target, source=name, params=params)
                size = len(text)
                low = text[:4000].lower()
                if "access denied" in low or "captcha" in low or "cloudflare" in low and "challenge" in low:
                    status, detail = "soft-block", "page served but looks like a bot wall"
                else:
                    detail = "html" if "<html" in low else "text"
        except SourceError as e:
            status, detail = e.kind, f"{e.detail}"
        except Exception as e:
            status, detail = "error", f"{type(e).__name__}: {e}"
        rows.append({"probe": name, "status": status, "ms": int((time.monotonic() - t0) * 1000), "bytes": size, "detail": detail})
        print(f"{status:<10} {rows[-1]['ms']:>6}ms {size:>9}B  {name:<26} {detail}")
    s.close()
    out = pathlib.Path("reachability.json")
    out.write_text(json.dumps({"runner": "github-actions", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "calls": s.calls, "rows": rows}, indent=1))
    ok = sum(1 for r in rows if r["status"] == "ok")
    blocked = [r["probe"] for r in rows if r["status"] in ("blocked", "soft-block")]
    print(f"\n{ok}/{len(rows)} reachable · blocked: {', '.join(blocked) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
