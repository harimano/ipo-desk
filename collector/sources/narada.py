"""Narada (trynarada.com) — one issue's subscription book, share-wise AND application-wise.

  GET https://trynarada.com/ipos/<SYMBOL>/subscription/
      the HTML fragment the site's own ↻ button swaps in (hx-get); <SYMBOL> is the exchange symbol the board row carries
      (NSE's, or BSE's for a BSE-only SME). Two tables, read AS tables (rule 1):
        shares        Quota | Shares offered (₹ Cr) | Shares applied (₹ Cr) | Times subscribed
        applications  Quota | Applications reserved | Applications received | Times subscribed
      Sub-rows (FII / DFI / MF / Other under QIB; bNII / sNII under NII; QIB / NII under a small SME's "Other") carry an
      indent marker span; the label is the cell's first text, the long name sits in a tooltip.

Why it is here (surveyed 1 Oct 2026): for BSE-only SMEs NSE has nothing and BSE's own category demand answers "No
Records Found" mid-issue; InvestorGain's report ran hours behind (Black Opal on its closing day: Narada 73.88x, IG 2.22x).
Narada says "exchange-consolidated NSE + BSE bids" and publishes NO timestamp ("Last updated: just now" is the browser's
fetch time), so a book from here is stamped with the time WE fetched it. Reachable from GitHub's runners (1 Oct 2026).
"""
from __future__ import annotations

import re

from ..errors import SourceChanged

try:
    from selectolax.lexbor import LexborHTMLParser as HTMLParser
except ImportError:  # pragma: no cover
    HTMLParser = None

SRC = "narada"
BASE = "https://trynarada.com"
KEYS = {"qib": "qib", "nii": "nii", "bnii": "bnii", "snii": "snii", "ind": "retail", "rii": "retail", "individual": "retail",
        "individuals": "retail", "retail": "retail", "emp": "employee", "employee": "employee", "employees": "employee",
        "sha": "shareholder", "shareholder": "shareholder", "shareholders": "shareholder", "other": "other",
        "others": "other", "fii": "fii", "dfi": "dfi", "mf": "mf", "total": "total", "policyholder": "policyholder",
        "policyholders": "policyholder"}
_NUM = re.compile(r"-?[\d,]*\.?\d+")


def url_for(symbol: str) -> str:
    return f"{BASE}/ipos/{symbol.strip().upper()}/subscription/"


def _num(text: str) -> float | None:
    m = _NUM.search((text or "").replace("−", "-"))
    return float(m.group(0).replace(",", "")) if m and text.strip() not in ("-", "–", "") else None


def _rows(table) -> list[dict]:
    out, parent = [], None
    for tr in table.css("tbody tr"):
        tds = tr.css("td")
        if len(tds) < 4:
            continue
        label = next((t.strip() for t in tds[0].text(deep=True, separator="\n").split("\n") if t.strip()), "")
        sub = tds[0].css_first("span.rounded-bl-sm") is not None
        row = {"label": label, "key": KEYS.get(label.lower(), label.lower()), "a": _num(tds[1].text()),
               "b": _num(tds[2].text()), "times": _num(tds[3].text()), "parent": parent if sub else None}
        if not sub:
            parent = row["key"]
        out.append(row)
    return out


def parse(html: str, *, url: str = "") -> dict:
    """-> {"shares": [rows], "apps": [rows]}, rows = {label, key, a, b, times, parent}: for shares a/b are ₹ Cr offered /
    applied, for apps the applications reserved / received. Raises SourceChanged when the shares table is not there."""
    if HTMLParser is None:  # pragma: no cover
        raise SourceChanged(SRC, "selectolax not installed", url)
    out: dict[str, list] = {}
    for t in HTMLParser(html or "").css("table"):
        head = "".join(th.text(strip=True) for th in t.css("thead th")).lower().replace(" ", "")   # "Applications<br>reserved"
        kind = "shares" if "sharesoffered" in head else "apps" if "applicationsreserved" in head else None
        if kind and kind not in out:
            out[kind] = _rows(t)
    if not out.get("shares"):
        raise SourceChanged(SRC, "no 'Shares offered' table in the subscription fragment", url)
    if not any(r["key"] == "total" for r in out["shares"]):
        raise SourceChanged(SRC, "shares table has no Total row", url)
    return {"shares": out["shares"], "apps": out.get("apps") or []}


def book(parsed: dict) -> dict:
    """The board's `sub` shape from the shares table: top-level quotas, plus bNII / sNII under NII. A quota with no
    multiple (a small SME's QIB with no reservation) is left out rather than invented."""
    sub = {}
    for r in parsed["shares"]:
        if r["times"] is None:
            continue
        if r["parent"] is None or (r["parent"] == "nii" and r["key"] in ("bnii", "snii")):
            sub.setdefault(r["key"], r["times"])
    return sub


def applications(parsed: dict) -> dict:
    """{quota: {reserved, received}} from the applications table (top-level quotas, plus bNII / sNII). Counts only."""
    out = {}
    for r in parsed["apps"]:
        if (r["parent"] is None or (r["parent"] == "nii" and r["key"] in ("bnii", "snii"))) and (r["a"] is not None or r["b"] is not None):
            out.setdefault(r["key"], {"reserved": int(r["a"]) if r["a"] is not None else None,
                                      "received": int(r["b"]) if r["b"] is not None else None})
    return out


def fetch(session, symbol: str) -> dict:
    url = url_for(symbol)
    return parse(session.get_text(url, source=SRC), url=url)
