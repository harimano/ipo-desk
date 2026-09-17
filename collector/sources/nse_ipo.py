"""NSE public-issue endpoints, normalised.

Endpoints (all GET https://www.nseindia.com + path, via Session.nse_json):
  /api/ipo-current-issue                       live issues (Active/Forthcoming)
  /api/all-upcoming-issues?category=ipo        forthcoming issues (often legitimately empty)
  /api/public-past-issues?from_date&to_date    listed/withdrawn issues in a window (mixes in NCD/debt rows)
  /api/ipo-detail?symbol=&series=              bidDetails (category -> noOfTime) + issueInfo.dataList (lot, size)

NSE renames list fields between the three list endpoints (companyName/company, issueStartDate/
ipoStartDate, series/securityType, issuePrice/priceRange ...). Everything below folds those into one
internal row:

  {name, symbol, series, board ("Mainboard"|"SME"), open, close, listing, allotment,
   bandLow, bandHigh, lotSize, issueSizeCr, statusHint, totalSub, source}

Dates are ISO YYYY-MM-DD or None. Anything that cannot be normalised into at least a name plus one
date is dropped; a list that yields zero rows raises SourceChanged.
"""
from __future__ import annotations

import datetime as dt
import re

from ..errors import SourceChanged
from ..http import NSE

SRC = "nse"
DEBT_WORDS = re.compile(r"\b(NCD|DEBT|BONDS?|DEBENTURES?|NON[- ]CONVERTIBLE)\b", re.I)
DEBT_SYMBOL = re.compile(r"^\d{3,4}[A-Z][A-Z0-9]{1,14}\d{2}$")
DATE_FORMATS = ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y",
                "%b %d, %Y", "%B %d, %Y", "%d-%b-%y", "%d/%b/%Y", "%Y%m%d")
NULLS = (None, "", "-", "--", "NA", "N/A", "null", "None")

# ---------------------------------------------------------------------------------------------
# small parsers shared with the BSE wrapper
# ---------------------------------------------------------------------------------------------
def first(d: dict, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v not in NULLS:
            return v
    return default


def iso_date(v) -> str | None:
    """Accept every date spelling NSE and BSE have used; return YYYY-MM-DD or None."""
    if v in NULLS:
        return None
    if isinstance(v, (dt.date, dt.datetime)):
        return v.date().isoformat() if isinstance(v, dt.datetime) else v.isoformat()
    s = str(v).strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        s = s[:10]
    s = re.sub(r"\s+", " ", s)
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})[-/ ]([A-Za-z]{3,9})[-/ ](\d{4})", s)
    if m:
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return dt.datetime.strptime(" ".join(m.groups()), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def number(v) -> float | None:
    """'6.77E7', '1,234.5', 'Rs. 210', '210 x' -> float; None when nothing numeric is there."""
    if v in NULLS:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("₹", " ").replace("Rs.", " ").replace("Rs", " ")
    m = re.search(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def price_band(text) -> tuple[float | None, float | None]:
    """'Rs.200 to Rs.210' / '200-210' / '₹ 95 - 100 per share' / '210' -> (low, high)."""
    if text in NULLS:
        return None, None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(text).replace(",", ""))]
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], nums[0]
    lo, hi = nums[0], nums[1]
    return (min(lo, hi), max(lo, hi))


def _unwrap(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "records", "result", "Table"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def is_debt(row: dict) -> bool:
    text = " ".join(str(row.get(k) or "") for k in ("securityType", "series", "companyName", "company", "symbol"))
    sym = str(row.get("symbol") or "")
    return bool(DEBT_WORDS.search(text)) or bool(DEBT_SYMBOL.match(sym)) or \
        str(row.get("securityType") or "").upper() in {"DEBT", "NCD"}


def _issue_size_cr(row: dict, band_high: float | None) -> float | None:
    for k in ("issueSizeCr", "issueSizeInCr", "issueSizeRsCr", "totalIssueSizeCr", "issueSizeCrore"):
        n = number(row.get(k))
        if n is not None:
            return round(n, 2)
    raw = number(first(row, "issueSize", "totalIssueSize"))
    if raw is None:
        return None
    if raw >= 100_000:                       # shares, not crore
        if band_high:
            return round(raw * band_high / 1e7, 2)
        return None
    return round(raw, 2)


def normalise_list_row(row: dict, endpoint: str) -> dict | None:
    """Fold NSE's drifting names into the internal row. Returns None for rows we cannot identify."""
    if not isinstance(row, dict):
        return None
    name = first(row, "companyName", "company", "issuerName", "name")
    if not name:
        return None
    name = re.sub(r"\s+", " ", str(name)).strip()
    withdrawn = bool(re.search(r"issue withdrawn", name, re.I))
    name = re.sub(r"\s*-\s*issue withdrawn.*$", "", name, flags=re.I)
    symbol = first(row, "symbol", "nseSymbol", "securitySymbol", "smSymbol")
    series = str(first(row, "series", "securityType", default="") or "").upper()
    blob = " ".join(str(v) for v in row.values() if isinstance(v, str)).upper()
    board = "SME" if (series == "SME" or "SME" in blob or "EMERGE" in blob) else "Mainboard"
    open_ = iso_date(first(row, "issueStartDate", "openDate", "issueOpenDate", "biddingStartDate",
                           "ipoStartDate", "startDate"))
    close = iso_date(first(row, "issueEndDate", "closeDate", "issueCloseDate", "biddingEndDate",
                           "ipoEndDate", "endDate"))
    listing = iso_date(first(row, "listingDate", "dateOfListing"))
    allotment = iso_date(first(row, "allotmentDate", "basisOfAllotmentDate"))
    lo = number(first(row, "minPrice", "priceMin", "lowerPrice", "floorPrice", "priceBandMin"))
    hi = number(first(row, "maxPrice", "priceMax", "upperPrice", "capPrice", "priceBandMax"))
    if lo is None or hi is None:
        lo2, hi2 = price_band(first(row, "issuePrice", "priceBand", "priceRange"))
        lo, hi = (lo if lo is not None else lo2), (hi if hi is not None else hi2)
    lot = number(first(row, "lotSize", "marketLot", "minimumBidQuantity", "minBidQuantity", "bidLot"))
    total = number(first(row, "noOfTime", "subscription", "timesSubscribed"))
    if not (open_ or close or listing):
        return None
    return {
        "name": name, "symbol": (str(symbol).strip() if symbol else None), "series": series or None,
        "board": board, "open": open_, "close": close, "listing": listing, "allotment": allotment,
        "bandLow": lo, "bandHigh": hi, "lotSize": int(lot) if lot else None,
        "issueSizeCr": _issue_size_cr(row, hi),
        "statusHint": str(first(row, "status", "issueStatus", default="") or ""),
        "withdrawn": withdrawn, "totalSub": total, "source": f"NSE {endpoint}",
    }


def _rows(data, endpoint: str, *, url: str) -> list[dict]:
    raw = _unwrap(data)
    if not raw:
        raise SourceChanged(SRC, f"{endpoint}: empty list", url)
    out = []
    for x in raw:
        if not isinstance(x, dict) or is_debt(x):
            continue
        r = normalise_list_row(x, endpoint)
        if r:
            out.append(r)
    if not out:
        raise SourceChanged(SRC, f"{endpoint}: {len(raw)} rows but none had a name and a date "
                                 f"(keys: {sorted(raw[0].keys())[:8] if isinstance(raw[0], dict) else type(raw[0])})", url)
    return out


# ---------------------------------------------------------------------------------------------
# endpoint wrappers
# ---------------------------------------------------------------------------------------------
REFERER_IPO = NSE + "/market-data/all-upcoming-issues-ipo"


def current_issues(session) -> list[dict]:
    path = "/api/ipo-current-issue"
    data = session.nse_json(path, source=SRC, referer=REFERER_IPO)
    return _rows(data, "ipo-current-issue", url=NSE + path)


def upcoming_issues(session) -> list[dict]:
    path = "/api/all-upcoming-issues"
    data = session.nse_json(path, {"category": "ipo"}, source=SRC, referer=REFERER_IPO)
    return _rows(data, "all-upcoming-issues", url=NSE + path)


def past_issues(session, from_date: dt.date, to_date: dt.date) -> list[dict]:
    if from_date > to_date:
        raise ValueError("from_date after to_date")
    path = "/api/public-past-issues"
    params = {"from_date": from_date.strftime("%d-%m-%Y"), "to_date": to_date.strftime("%d-%m-%Y")}
    data = session.nse_json(path, params, source=SRC, referer=REFERER_IPO)
    return _rows(data, "public-past-issues", url=NSE + path)


def ipo_detail(session, symbol: str, series: str = "EQ") -> dict:
    """/api/ipo-detail for one issue. Returns
       {symbol, series, name, bidDetails: [{category, noOfTime, sharesOffered?, sharesBid?}],
        dataList: [{title, value}], updateTime}
    SME issues are sometimes filed under series EQ and sometimes SME; the caller passes what the
    list gave and we try the other one if the first answers without bidDetails."""
    path = "/api/ipo-detail"
    referer = NSE + f"/market-data/issue-information?series={series}&symbol={symbol}&type=Active"
    tried = []
    for ser in _series_order(series):
        data = session.nse_json(path, {"symbol": symbol, "series": ser}, source=SRC, referer=referer)
        if not isinstance(data, dict):
            tried.append(ser)
            continue
        bids = _bid_rows(data)
        info = data.get("issueInfo")
        has_info = isinstance(info, dict) and isinstance(info.get("dataList"), list) and bool(info["dataList"])
        if bids or has_info:            # an upcoming issue has issueInfo (lot, band) but no bids yet
            return _detail(data, symbol, ser, bids)
        tried.append(ser)
    raise SourceChanged(SRC, f"ipo-detail {symbol}: neither bidDetails nor issueInfo for series {tried}", NSE + path)


def _series_order(series: str) -> tuple[str, ...]:
    s = (series or "EQ").upper()
    return ("SME", "EQ") if s == "SME" else ("EQ", "SME")


def _bid_rows(data: dict) -> list[dict]:
    """bidDetails is the documented list; activeCat.dataList carries shares offered/bid per category
    (needed to combine NII sub-buckets correctly). Prefer the richer one when both agree on shape."""
    out = []
    active = data.get("activeCat")
    rows = active.get("dataList") if isinstance(active, dict) else None
    if isinstance(rows, list) and rows:
        for r in rows:
            if not isinstance(r, dict):
                continue
            cat = first(r, "category", "categoryName", "investorCategory", "bidCategory")
            times = number(first(r, "noOfTotalMeant", "noOfTime", "subscription", "timesSubscribed"))
            offered = number(first(r, "noOfShareOffered", "noOfSharesOffered", "sharesOffered"))
            bid = number(first(r, "noOfSharesBid", "noOfshareBid", "sharesBid"))
            if times is None and offered and bid is not None:
                times = bid / offered
            if cat and times is not None:
                out.append({"category": str(cat), "noOfTime": times, "sharesOffered": offered, "sharesBid": bid})
    if out:
        return out
    rows = data.get("bidDetails")
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            cat = first(r, "category", "categoryName", "investorCategory", "bidCategory")
            code = first(r, "categoryCode", "code", "caCode")
            times = number(first(r, "noOfTime", "subscription", "timesSubscribed", "subscriptionTimes"))
            offered = number(first(r, "noOfShareOffered", "noOfSharesOffered", "sharesOffered"))
            bid = number(first(r, "noOfSharesBid", "noOfshareBid", "sharesBid"))
            if times is None and offered and bid is not None:
                times = bid / offered
            if cat and times is not None:
                label = f"{cat} {code}" if code else str(cat)
                out.append({"category": label, "noOfTime": times, "sharesOffered": offered, "sharesBid": bid})
    return out


def _detail(data: dict, symbol: str, series: str, bids: list[dict]) -> dict:
    info = data.get("issueInfo")
    data_list = info.get("dataList") if isinstance(info, dict) else None
    if not isinstance(data_list, list):
        data_list = []
    meta = data.get("metaInfo") if isinstance(data.get("metaInfo"), dict) else {}
    name = first(data, "companyName") or first(meta, "companyName")
    upd = None
    active = data.get("activeCat")
    if isinstance(active, dict):
        upd = first(active, "updateTime")
    upd = upd or first(data, "updateTime")
    if upd in NULLS or str(upd).strip().lower() == "null":
        upd = None
    root_total = number(first(data, "noOfTime", "subscription", "timesSubscribed", "totalSubscription"))
    if root_total is None:
        dg = data.get("demandGraph")
        if isinstance(dg, dict):
            root_total = number(first(dg, "noOfTimesIssueSubscribed"))
    return {"symbol": symbol, "series": series, "name": name, "bidDetails": bids,
            "dataList": [d for d in data_list if isinstance(d, dict)], "updateTime": upd,
            "rootTotal": root_total}


def detail_lot(detail: dict) -> dict:
    """Pull lot / minimum order / issue size / band out of issueInfo.dataList {title, value} rows."""
    out: dict = {"lotSize": None, "issueSizeCr": None, "bandLow": None, "bandHigh": None}
    for row in detail.get("dataList", []):
        title = str(first(row, "title", "label", "key", default="") or "").lower()
        value = first(row, "value", "val")
        if value in NULLS:
            continue
        txt = re.sub(r"<[^>]+>", " ", str(value))
        if "bid lot" in title or "minimum order" in title or "market lot" in title or "lot size" in title:   # SME pages say "Lot Size"
            n = number(txt)
            if n and out["lotSize"] is None:
                out["lotSize"] = int(n)
        elif "issue size" in title and out["issueSizeCr"] is None:
            out["issueSizeCr"] = _size_text_to_cr(txt)
        elif "price band" in title or "issue price" in title or "price range" in title:                      # SME pages say "Price Range"
            lo, hi = price_band(txt)
            if hi and out["bandHigh"] is None:
                out["bandLow"], out["bandHigh"] = lo, hi
    return out


_ANCHOR_SHARES = re.compile(r"anchor\s+(?:investors?\s+)?(?:reservation\s+)?(?:portion|allocation)\s*(?:of\s+)?"
                            r"(?:up\s*to\s+)?([\d,]{4,})\s*(?:equity\s+)?shares", re.I)


def detail_anchor_shares(detail: dict) -> int | None:
    """The anchor portion in shares, as ipo-detail's "Issue Size" states it. Seen live (17 Sep 2026):
    "Anchor Portion of 37,793,739 Equity Shares", "Anchor reservation portion of 3,57,14,284 equity shares",
    "Anchor allocation 10,70,000 Equity Shares". None when the issue has no anchor portion or says nothing."""
    for row in detail.get("dataList", []):
        if "issue size" not in str(first(row, "title", "label", "key", default="") or "").lower():
            continue
        m = _ANCHOR_SHARES.search(re.sub(r"<[^>]+>", " ", str(first(row, "value", "val") or "")))
        if m:
            n = number(m.group(1))
            return int(n) if n else None
    return None


def _size_text_to_cr(txt: str) -> float | None:
    """'Rs. 1,200.00 crore' / '₹ 450 Cr' / 'up to 20,00,000 equity shares aggregating to 42.5 crores'."""
    t = txt.replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(crore|crores|cr\b)", t, re.I)
    if m:
        return round(float(m.group(1)), 2)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac)", t, re.I)
    if m:
        return round(float(m.group(1)) / 100, 2)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(million|mn)\b", t, re.I)
    if m:
        return round(float(m.group(1)) / 10, 2)
    return None
