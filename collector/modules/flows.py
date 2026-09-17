"""flows — owns `flows`: FII/FPI and DII cash-market provisional figures from NSE
`/api/fiidiiTradeReact` (the only source; there is no second one, so a blocked NSE means the section is
kept from prev and marked stale — the note says so).

Response shape (a list of two rows):
  [{"category": "DII **", "buyValue": "12,345.67", "sellValue": "11,000.00", "netValue": "1,345.67",
    "date": "16-Sep-2026"},
   {"category": "FII/FPI *", ...}]

Writes flows.latest = {date, fiiNetCr, diiNetCr, previousDay, source, fiiBuyCr, fiiSellCr, diiBuyCr,
diiSellCr} and appends [date, fii, dii] to flows.history when that date is not already there.
`monthly`, `rotation`, `note` are carried from prev (Claude-owned commentary).
"""
from __future__ import annotations

import copy
import logging

from ..errors import SourceChanged
from ..http import Session
from ..result import Result, try_chain
from ..sources.nsearchives import parse_date

log = logging.getLogger("collector.flows")

PATH = "/api/fiidiiTradeReact"
NO_SECOND_SOURCE = "flows: NSE fiidiiTradeReact is the only source; no fallback exists"


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_fiidii(data) -> dict:
    """-> {date, fii: {buy, sell, net}, dii: {buy, sell, net}}. Raises SourceChanged on any gap."""
    if isinstance(data, dict):
        data = data.get("data") or data.get("fiidii") or list(data.values())
    if not isinstance(data, list) or not data:
        raise SourceChanged("nse", "fiidii: expected a non-empty list", PATH)
    out: dict = {"date": None, "fii": None, "dii": None}
    for row in data:
        if not isinstance(row, dict):
            continue
        cat = str(row.get("category") or "").upper()
        key = "fii" if ("FII" in cat or "FPI" in cat) else ("dii" if "DII" in cat else None)
        if key is None:
            continue
        vals = {"buy": _num(row.get("buyValue")), "sell": _num(row.get("sellValue")), "net": _num(row.get("netValue"))}
        if vals["net"] is None and vals["buy"] is not None and vals["sell"] is not None:
            vals["net"] = round(vals["buy"] - vals["sell"], 2)
        if vals["net"] is None:
            raise SourceChanged("nse", f"fiidii: {key} row has no usable netValue", PATH)
        out[key] = vals
        out["date"] = out["date"] or parse_date(str(row.get("date") or ""))
    if not out["fii"] or not out["dii"]:
        raise SourceChanged("nse", "fiidii: missing FII or DII row", PATH)
    if not out["date"]:
        raise SourceChanged("nse", "fiidii: no parseable date", PATH)
    return out


def _from_nse(session: Session, prev: dict, res: Result) -> str | None:
    data = session.nse_json(PATH, source="nse")
    parsed = parse_fiidii(data)
    prev_flows = copy.deepcopy(prev.get("flows") or {})
    prev_latest = prev_flows.get("latest") or {}
    date, fii, dii = parsed["date"], parsed["fii"], parsed["dii"]

    previous_day = prev_latest.get("previousDay")
    if prev_latest.get("date") and prev_latest.get("date") != date:
        previous_day = {"date": prev_latest.get("date"), "fiiNetCr": prev_latest.get("fiiNetCr"),
                        "diiNetCr": prev_latest.get("diiNetCr")}
    latest = {
        "date": date, "fiiNetCr": fii["net"], "diiNetCr": dii["net"], "previousDay": previous_day,
        "source": "NSE provisional (fiidiiTradeReact)",
        "fiiBuyCr": fii["buy"], "fiiSellCr": fii["sell"], "diiBuyCr": dii["buy"], "diiSellCr": dii["sell"],
    }
    history = [h for h in (prev_flows.get("history") or []) if isinstance(h, list) and h]
    if not any(str(h[0])[:10] == date for h in history):
        history.append([date, fii["net"], dii["net"]])
        history.sort(key=lambda h: str(h[0]))
        res.notes.append(f"appended {date}")
    else:
        res.notes.append(f"{date} already in history")
    res.replace["flows"] = {
        "latest": latest,
        "history": history,
        "monthly": prev_flows.get("monthly") or [],
        "rotation": prev_flows.get("rotation") or {"fiiSelling": [], "diiBuying": []},
        "note": prev_flows.get("note"),
    }
    res.notes.append(f"FII {fii['net']:+,.0f} / DII {dii['net']:+,.0f} Cr")
    return date


def run(session: Session, prev: dict, res: Result) -> Result:
    out = try_chain(res, [("nse", lambda: _from_nse(session, prev, res))])
    if not out.ok:
        out.notes.append(NO_SECOND_SOURCE)
    return out
