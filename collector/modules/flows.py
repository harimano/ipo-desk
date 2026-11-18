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

`flows.trend` (18 Nov 2026) is the longer view, all of it counted here (rule 2):
  own     one entry a calendar month from OUR daily rows — {m, fii, dii, n, fiiUp, diiUp, from, to}. `history` is capped
          at 40 rows, so a month is recomputed only while its rows are still there and never shrinks; the first month
          (Sep 2026, from the 18th) is partial and `from` says so. This is the only DII history that exists.
  nsdl    NSDL's final FPI equity figures (`sources/nsdl.py`): `years` (financial, since 1992-93), `months` (this
          calendar year), `ytd`, and `primary` — FPI money into primary issues this month, by reporting day.
          A second leg: when NSDL refuses or changes, the last figures are kept with their own `asOf` and the note says so.
  facts   short lines read off those numbers (rank of the month in the year, first buying month since …).
NSE's provisional cash figure and NSDL's final one are different series: side by side, never merged.
"""
from __future__ import annotations

import copy
import datetime as dt
import logging

from ..errors import SourceChanged, SourceError
from ..http import Session
from ..result import Result, try_chain
from ..sources import nsdl
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
        "source": "NSE provisional",      # shown on the page: a label a reader can use, not the endpoint's name
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
        "trend": trend(session, prev_flows.get("trend") or {}, history, res),
    }
    res.notes.append(f"FII {fii['net']:+,.0f} / DII {dii['net']:+,.0f} Cr")
    return date


def own_months(history: list, kept: list) -> list[dict]:
    """One entry a month from the daily rows; an entry on file is replaced only by one counted from at least as many rows."""
    by: dict[str, dict] = {str(e.get("m")): e for e in kept if isinstance(e, dict) and e.get("m")}
    fresh: dict[str, dict] = {}
    for row in history:
        day, fii, dii = str(row[0])[:10], row[1] or 0, row[2] or 0
        e = fresh.setdefault(day[:7], {"m": day[:7], "fii": 0.0, "dii": 0.0, "n": 0, "fiiUp": 0, "diiUp": 0, "from": day, "to": day})
        e["fii"] += fii
        e["dii"] += dii
        e["n"] += 1
        e["fiiUp"] += fii > 0
        e["diiUp"] += dii > 0
        e["from"], e["to"] = min(e["from"], day), max(e["to"], day)
    for m, e in fresh.items():
        if e["n"] >= (by.get(m) or {}).get("n", 0):
            by[m] = {**e, "fii": round(e["fii"], 2), "dii": round(e["dii"], 2)}
    return [by[m] for m in sorted(by)]


def _mon(ym: str) -> str:
    return dt.date(int(ym[:4]), int(ym[5:7]), 1).strftime("%B")


def nsdl_view(got: dict, now: str) -> dict:
    """The three parsed pages -> the block the page renders. The last year and the last month are in progress."""
    months, days = got["months"], got["days"]
    prim = [d for d in days if d.get("primary") is not None]
    top = max(prim, key=lambda d: abs(d["primary"]), default=None)
    return {
        "asOf": months.get("asOf") or got["years"].get("asOf") or days[-1]["date"], "checkedAt": now,
        "years": got["years"]["years"][-12:], "since": got["years"]["years"][0][0],
        "year": months["year"], "months": months["months"], "ytd": months["total"],
        "primary": {"month": days[-1]["date"][:7], "net": round(sum(d["primary"] for d in prim), 2), "days": len(prim),
                    "top": {"date": top["date"], "net": top["primary"]} if top else None},
        "days": [[d["date"], d["net"], d["primary"]] for d in days],
    }


def facts(view: dict) -> list[str]:
    """Plain readings of NSDL's months: no forecast, no adjective the numbers do not carry."""
    out, months = [], view.get("months") or []
    if len(months) >= 3:
        (cur_m, cur), vals = months[-1], [v for _, v in months]
        if cur > 0 and cur == max(vals):
            out.append(f"Biggest FPI buying month of {view['year']} so far")
        elif cur < 0 and cur == min(vals):
            out.append(f"Heaviest FPI selling month of {view['year']} so far")
        prior = months[:-1]
        if cur > 0 and prior[-1][1] < 0:
            last = next((m for m, v in reversed(prior) if v > 0), None)
            out.append(f"First net-buying month since {_mon(last)}" if last else f"First net-buying month of {view['year']}")
        elif cur < 0 and prior[-1][1] > 0:
            last = next((m for m, v in reversed(prior) if v < 0), None)
            out.append(f"First net-selling month since {_mon(last)}" if last else f"First net-selling month of {view['year']}")
        del cur_m
    years = view.get("years") or []
    if years:
        fy, v = years[-1]
        out.append(f"Financial year {fy} so far: {'−' if v < 0 else '+'}₹{abs(v):,.0f} Cr")
    return out


def trend(session: Session, kept: dict, history: list, res: Result) -> dict:
    out = {"own": own_months(history, kept.get("own") or []), "nsdl": kept.get("nsdl"), "facts": kept.get("facts") or []}
    try:
        got = nsdl.fetch(session)
    except Exception as e:      # the second leg never fails the module: NSE's figure stands, NSDL's last figures are kept
        res.tried.append({**(e.record() if isinstance(e, SourceError) else {"kind": "changed", "source": "nsdl", "detail": f"{type(e).__name__}: {e}"}), "ok": False})
        res.notes.append(f"nsdl: no fresh figures ({type(e).__name__}); kept those of {(kept.get('nsdl') or {}).get('asOf') or 'no earlier run'}")
        return out
    out["nsdl"] = nsdl_view(got, dt.datetime.now(dt.UTC).isoformat(timespec="seconds"))
    out["facts"] = facts(out["nsdl"])
    res.notes.append(f"nsdl to {out['nsdl']['asOf']}: {len(out['nsdl']['months'])} months, {len(out['nsdl']['years'])} years")
    return out


def run(session: Session, prev: dict, res: Result) -> Result:
    out = try_chain(res, [("nse", lambda: _from_nse(session, prev, res))])
    if not out.ok:
        out.notes.append(NO_SECOND_SOURCE)
    return out
