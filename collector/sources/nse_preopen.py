"""NSE's special pre-open session for a security listing today: 9:00-9:45 IST, the exchange computes an indicative
equilibrium price from real orders before the first trade at 10:00. `/api/special-preopen-listing` (seen live
18 Sep 2026: Veegaland IEP 154.00 = +10.0% — where it then listed; the grey market had implied +6%).

An empty `data` list is the normal answer on a day nothing lists, so it is NOT an error here; a body without the
`data` key is."""
from __future__ import annotations

import re

from ..errors import SourceChanged

SRC = "nse"
PATH = "/api/special-preopen-listing"


def _f(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse(data) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise SourceChanged(SRC, f"special-preopen-listing: no data list ({type(data).__name__})", PATH)
    stamp = None
    m = re.match(r"(\d{1,2})-([A-Za-z]{3})-(\d{4}) (\d{2}):(\d{2})", str(data.get("timestamp") or ""))
    if m:
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(m.group(2).lower()) + 1
        stamp = f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}T{m.group(4)}:{m.group(5)}:00+05:30"
    out = []
    for r in data["data"]:
        if not isinstance(r, dict) or not r.get("symbol") or _f(r.get("iep")) is None:
            continue
        out.append({"symbol": str(r["symbol"]).upper(), "iep": _f(r.get("iep")), "pct": _f(r.get("perChange")),
                    "base": _f(r.get("prevClose")), "qty": _f(r.get("ieq")), "status": str(r.get("status") or ""), "asOf": stamp})
    return out


def fetch(session) -> list[dict]:
    return parse(session.nse_json(PATH, None, source=SRC))
