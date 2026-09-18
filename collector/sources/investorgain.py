"""InvestorGain live-IPO-GMP report (id 331) via its cloud JSON backend — the JSON-first GMP source.

  https://webnodejs.investorgain.com/cloud/v2/report/data-read/331/{page}/{month}/{year}/{fy}/0/all

page = 1, month/year = today, fy = Indian financial year "YYYY-YY" (April–March, e.g. "2026-27"),
category = all. No auth; the site wants its own Referer/Origin. The report page itself is Next.js
client-rendered, so plain HTML is empty — hence the XHR endpoint (found via IPOFetch scraper/gmp.py).

Response: {"reportTableData": [ {Name: '<a href="…">Kanohar Electricals Ltd IPO</a>',
           GMP: '&#8377;<b>45</b> (12.5%)' | '--', Sub, "Price (₹)", "IPO Size", Lot, "Updated-On",
           "~ipo_status1": U|O|C, "~IPO_Category", "~Srt_Open", "~Srt_Close", "~Str_Listing", …} ]}
Fields are undocumented and carry HTML fragments — tags are stripped with selectolax.

The v1 endpoint retired in July 2026 by answering {"msg": "API not found"}; v2 may follow, so that body
(or zero rows) raises SourceChanged rather than returning an empty list.
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from selectolax.parser import HTMLParser

from ..errors import SourceChanged
from ._parse import clean, compute_gmp_pct, parse_money, parse_pct, upper_band

SOURCE = "investorgain"
BASE = "https://webnodejs.investorgain.com/cloud/v2/report/data-read/331"
PAGE_URL = "https://www.investorgain.com/report/live-ipo-gmp/331/ipo/"
HEADERS = {"Accept": "application/json", "Referer": PAGE_URL, "Origin": "https://www.investorgain.com"}
IST = ZoneInfo("Asia/Kolkata")

STATUS = {"U": "Upcoming", "O": "Open", "C": "Closed", "L": "Listed"}
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def fiscal_year(d: dt.date) -> str:
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def url_for(d: dt.date, page: int = 1) -> str:
    return f"{BASE}/{page}/{d.month}/{d.year}/{fiscal_year(d)}/0/all"


def strip_tags(fragment) -> str:
    if fragment is None:
        return ""
    if not isinstance(fragment, str):
        return clean(str(fragment))
    return clean(HTMLParser(fragment).text(separator=" "))


def _name(fragment) -> str:
    """Prefer the link text — the cell may carry badges/spans beside the <a>."""
    if isinstance(fragment, str) and "<a" in fragment:
        a = HTMLParser(fragment).css_first("a")
        if a is not None and clean(a.text()):
            return clean(a.text())
    return strip_tags(fragment)


def _date(value) -> str | None:
    """'2026-09-15' / '15-Sep-2026' / '15 Sep 2026' -> ISO date; else the cleaned text or None."""
    s = strip_tags(value)
    if not s or s in ("--", "-"):
        return None
    if _ISO.match(s):
        return s[:10]
    m = re.match(r"^(\d{1,2})[ -]([A-Za-z]{3})[A-Za-z]*[ ,-]+(\d{4})", s)
    if m and m.group(2).lower() in _MONTHS:
        try:
            return dt.date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
        except ValueError:
            return s
    return s


def _pick(row: dict, *keys):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    lower = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, ""):
            return v
    return None


def parse_investorgain(data) -> list[dict]:
    if not isinstance(data, dict):
        raise SourceChanged(SOURCE, f"expected a JSON object, got {type(data).__name__}", BASE)
    if data.get("msg") == "API not found" or (not data.get("reportTableData") and "msg" in data):
        raise SourceChanged(SOURCE, f"endpoint answered {data.get('msg')!r} — v2 retired?", BASE)
    rows = data.get("reportTableData")
    if not isinstance(rows, list) or not rows:
        raise SourceChanged(SOURCE, "reportTableData missing or empty", BASE)
    out: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        name = _name(_pick(raw, "Name", "IPO", "~IPO_Name"))
        if not name:
            continue
        gmp_text = strip_tags(_pick(raw, "GMP", "GMP(₹)", "GMP (₹)"))
        gmp = parse_money(gmp_text.split("(")[0]) if gmp_text and gmp_text not in ("--", "-") else None
        price_text = strip_tags(_pick(raw, "Price (₹)", "Price", "Price (Rs)", "~Price"))
        st = strip_tags(_pick(raw, "~ipo_status1", "Status"))
        r = {
            "name": name,
            "gmp": gmp,
            "gmpPct": parse_pct(gmp_text) if gmp is not None else None,
            "bandHigh": upper_band(price_text),
            "open": _date(_pick(raw, "~Srt_Open", "Open", "~Open")),
            "close": _date(_pick(raw, "~Srt_Close", "Close", "~Close")),
            "listing": _date(_pick(raw, "~Str_Listing", "~Srt_Listing", "Listing", "~Listing")),
            "type": strip_tags(_pick(raw, "~IPO_Category", "Type")),
            "status": STATUS.get(st.upper(), st) if st else "",
            "updated": strip_tags(_pick(raw, "Updated-On", "~Updated_On", "Updated")),
            # the whole issue at the upper band, as the market quotes it. NSE's list cannot give this: its
            # share count is net of the anchor portion (Hero Motors: 744 Cr there, 1,000 Cr here).
            "issueSizeCr": parse_money(strip_tags(_pick(raw, "IPO Size", "Issue Size"))),
            "igId": str(_pick(raw, "~id") or "") or None,
            "source": SOURCE,
        }
        compute_gmp_pct(r)
        out.append(r)
    if not out:
        raise SourceChanged(SOURCE, f"{len(rows)} rows but none had a name — field names changed?", BASE)
    return out


# ---------------------------------------------------------------------------------------------
# The per-IPO record — the fullest source there is for an Indian IPO (found 18 Sep 2026 by reading the site's
# own bundles): one call returns ~280 fields. `list-read` gives the ids of every current and upcoming issue.
#
#   GET /cloud/v2/ipo/list-read                 {ipoList: [{id, company_short_name, issue_open_dt, ipo_status, …}]}
#   GET /cloud/v2/ipo/ipo-detail-read/<id>      {ipoData: [{…282 fields…}], biddingData: {ipoBiddingData: [day rows]},
#                                                gmpData: [newest first], ipoRecommendationData, ipoLeadManagersList,
#                                                registrarInfo, anchorInvestorData (always empty: lists are PDF-only)}
#
# Private and undocumented, like report 331 (whose v1 was retired without notice in July 2026): every shape
# surprise raises SourceChanged, and the NSE/BSE modules remain the fallback for everything they can supply.
# ---------------------------------------------------------------------------------------------
_API = "https://webnodejs.investorgain.com/cloud/v2/ipo"
IPO_LIST_URL = _API + "/list-read"
IPO_DETAIL_URL = _API + "/ipo-detail-read/{id}"
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _num(v) -> float | None:
    """'10557402000.00' / '5,011,424' / '&#8377;1055.74 Cr' / '23 shares (1 lot)' -> the first number; else None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = _NUMBER.search(strip_tags(v).replace("&#8377;", " "))
    try:
        return float(m.group().replace(",", "")) if m else None
    except ValueError:
        return None


def _day(v) -> str | None:
    """'2026-09-11T00:00:00.000Z' / '2026-09-08' / '16th Sep 2026' / '16-Sep-2026' / '16-09-2026' -> ISO date."""
    s = strip_tags(v)
    if not s:
        return None
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", s)
    if m:
        s = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    iso = _date(re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", s))
    return iso if iso and _ISO.match(iso) else None


def _stamp(v) -> str | None:
    """'10th Sep 2026 18:56' / '16-Sep-2026 9:33' -> '2026-09-10T18:56:00+05:30' (the site speaks IST)."""
    s = strip_tags(v)
    day = _day(re.sub(r"\s+\d{1,2}:\d{2}.*$", "", s))
    if not day:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", s)
    return f"{day}T{int(m.group(1)):02d}:{m.group(2)}:00+05:30" if m else day


def parse_ipo_list(data) -> list[dict]:
    rows = data.get("ipoList") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise SourceChanged(SOURCE, f"list-read: ipoList missing or empty (msg={data.get('msg') if isinstance(data, dict) else None!r})", IPO_LIST_URL)
    out = [{"igId": str(r["id"]), "name": clean(str(r["company_short_name"])), "open": _day(r.get("issue_open_dt")),
            "close": _day(r.get("issue_end_dt")), "status": strip_tags(r.get("ipo_status")),
            "category": strip_tags(r.get("issue_category") or r.get("ipo_category")), "listingAt": strip_tags(r.get("ipo_listing_at"))}
           for r in rows if isinstance(r, dict) and r.get("id") and r.get("company_short_name")]
    if not out:
        raise SourceChanged(SOURCE, f"list-read: {len(rows)} rows, none with id and company_short_name", IPO_LIST_URL)
    return out


def fetch_ipo_list(session) -> list[dict]:
    return parse_ipo_list(session.get_json(IPO_LIST_URL, source=SOURCE, headers=HEADERS))


def _drop_empty(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def normalise_detail(raw) -> dict:
    """The record, flat and typed. Only fields the desk uses; prose (objects, company text) is left behind."""
    url = IPO_DETAIL_URL
    ipo = (raw.get("ipoData") or [None])[0] if isinstance(raw, dict) else None
    if not isinstance(ipo, dict) or not ipo.get("id") or "issue_open_dt_json" not in ipo:
        raise SourceChanged(SOURCE, f"ipo-detail-read: no ipoData record (msg={raw.get('msg') if isinstance(raw, dict) else None!r})", url)
    g = ipo.get
    band_hi = _num(g("issue_price_upper")) or _num(g("max_price_to_display"))
    final = _num(g("issue_price_final")) or _num(g("allotment_price"))
    anchor_shares = int(_num(g("shares_offered_anchor_investor")) or 0)
    total_amt = _num(g("issue_size_in_amt"))

    bids = (raw.get("biddingData") or {}).get("ipoBiddingData") if isinstance(raw.get("biddingData"), dict) else None
    sub = None
    if isinstance(bids, list) and bids and isinstance(bids[-1], dict):
        b = bids[-1]
        sub = {"qib": _num(b.get("qib")), "nii": _num(b.get("nii")), "retail": _num(b.get("rii")), "total": _num(b.get("total")),
               "asOf": _stamp(b.get("bid_date"))}
        for ours, theirs in (("employee", "emp"), ("shareholder", "shareholder")):
            if (_num(b.get(f"{theirs}_offered")) or 0) > 0:
                sub[ours] = _num(b.get(theirs))
        if sub["total"] is None:
            sub = None

    gmp = None
    quotes = [q for q in (raw.get("gmpData") or []) if isinstance(q, dict)]
    if quotes:
        q = next((x for x in quotes if str(x.get("gmp_active_record_flag")) == "1"), quotes[0])
        # "0" with no trade behind it (no subject-to-sauda rate, no estimated profit) is the site saying "no quote",
        # not a premium of zero — seen live on issues days away from opening
        unquoted = (_num(q.get("gmp")) or 0) == 0 and _num(q.get("subject_to_sauda")) is None and _num(q.get("est_profit")) is None
        if _num(q.get("gmp")) is not None and not unquoted:
            gmp = {"value": _num(q.get("gmp")), "pct": _num(q.get("gmp_percent_calc")),
                   "estListing": _num(q.get("estimated_listing_price")), "asOf": _stamp(q.get("last_updated"))}

    late = "_2" if g("kpi_as_of_date_2") else ""               # two reporting periods: take the later one
    kpis = _drop_empty({"asOf": _day(g("kpi_as_of_date" + late)), "roe": _num(g("kpi_roe" + late)), "roce": _num(g("kpi_roce" + late)),
                        "debtEquity": _num(g("kpi_debt_equity" + late)), "ronw": _num(g("kpi_ronw" + late)),
                        "patMargin": _num(g("kpi_pat_margin" + late)), "ebitdaMargin": _num(g("kpi_ebitda" + late)),
                        "pb": _num(g("price_to_book_value" + late)), "eps": _num(g("kpi_eps")), "epsPost": _num(g("kpi_eps_post")),
                        "pe": _num(g("pe_ratio")), "pePost": _num(g("post_pe_ratio")), "mcapCr": _num(g("market_cap")),
                        "promoterPre": _num(g("promoter_shareholding_pre_issue")), "promoterPost": _num(g("promoter_shareholding_post_issue"))})
    recs = [_drop_empty({"who": strip_tags(r.get("reviewer_name")), "view": strip_tags(r.get("recommendation")),
                         "url": strip_tags(r.get("reviewer_link")), "date": _day(r.get("create_date"))})
            for r in (raw.get("ipoRecommendationData") or []) if isinstance(r, dict) and r.get("reviewer_name")][:12]
    registrar = next((strip_tags(r.get("registrar_name")) for r in (raw.get("registrarInfo") or []) if isinstance(r, dict)), None)

    return {
        "igId": str(g("id")), "name": clean(str(g("company_short_name") or "")), "companyName": strip_tags(g("company_name")),
        "category": strip_tags(g("issue_category")), "listingAt": strip_tags(g("ipo_listing_at")),
        "symbol": strip_tags(g("nse_symbol") or g("nse_script_symbol")) or None,
        "bseCode": strip_tags(g("bse_script_code") or g("bse_cd")) or None, "isin": strip_tags(g("isin")) or None,
        "sector": strip_tags(g("company_sector")) or None, "faceValue": _num(g("face_value")),
        "open": _day(g("issue_open_dt_json")), "close": _day(g("issue_end_dt_json")), "allotment": _day(g("timetable_boa_dt")),
        "refund": _day(g("timetable_refunds_dt")), "credit": _day(g("timetable_share_credit_dt")),
        "listing": _day(g("ipo_listing_date")) or _day(g("timetable_listing_dt")),
        "anchorBidDate": _day(g("timetable_anchor_bid_dt")), "lockIn30": _day(g("timetable_anchor_lockin_end_dt_1")),
        "lockIn90": _day(g("timetable_anchor_lockin_end_dt_2")),
        "bandLow": _num(g("issue_price_lower")), "bandHigh": band_hi, "priceFinal": final,
        "lotSize": int(_num(g("market_lot_size")) or 0) or None, "minAmount": _num(g("min_order_amount")),
        "issueSizeCr": round(total_amt / 1e7, 2) if total_amt else _num(g("issue_size")),
        "freshCr": round((_num(g("issue_size_fresh_in_amt")) or 0) / 1e7, 2) or None,
        "ofsCr": round((_num(g("issue_size_ofs_in_amt")) or 0) / 1e7, 2) or None,
        "anchorShares": anchor_shares,
        "anchorCr": round(anchor_shares * (final or band_hi) / 1e7, 2) if anchor_shares and (final or band_hi) else None,
        "sub": sub, "gmp": gmp, "listingPrice": _num(g("listing_price")),
        "facts": _drop_empty({"sector": strip_tags(g("company_sector")), "isin": strip_tags(g("isin")), "listingAt": strip_tags(g("ipo_listing_at")),
                              "kpis": kpis, "recs": recs, "registrar": registrar,
                              "leadManagers": [strip_tags(m.get("comp_name")) for m in (raw.get("ipoLeadManagersList") or [])
                                               if isinstance(m, dict) and m.get("comp_name")][:8],
                              "docs": _drop_empty({"drhp": strip_tags(g("prospectus_drhp")), "rhp": strip_tags(g("prospectus_rhp")),
                                                   "prospectus": strip_tags(g("final_prospectus")),
                                                   "anchorLetter": strip_tags(g("anchor_investor_url")),
                                                   "allotment": strip_tags(g("ipo_allotment_url"))})}),
        "updated": _stamp(g("last_updated")),
    }


def fetch_detail(session, ig_id: str) -> dict:
    return normalise_detail(session.get_json(IPO_DETAIL_URL.format(id=ig_id), source=SOURCE, headers=HEADERS))


# ---------------------------------------------------------------------------------------------
# report 566 — live subscription for every issue of the year in ONE call, with the site's own bid timestamp.
# The five-minute live loop reads this instead of one slow exchange call per issue.
# ---------------------------------------------------------------------------------------------
SUBSCRIPTION_REPORT = 566


def parse_subscription_report(data, today: dt.date) -> list[dict]:
    rows = data.get("reportTableData") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise SourceChanged(SOURCE, f"report 566: reportTableData missing or empty (msg={data.get('msg') if isinstance(data, dict) else None!r})", "report 566")
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("~id") or _num(r.get("Total")) is None:
            continue
        stamp = _stamp(f"{strip_tags(r.get('BID Date'))[:-5].strip()} {today.year} {strip_tags(r.get('BID Date'))[-5:]}")   # '18th Sep 17:57' has no year
        if stamp and stamp[:10] > (today + dt.timedelta(days=2)).isoformat():
            stamp = str(today.year - 1) + stamp[4:]                                  # a December bid read in January
        out.append({"igId": str(r["~id"]), "qib": _num(r.get("QIB")), "snii": _num(r.get("SHNI")), "bnii": _num(r.get("BHNI")),
                    "nii": _num(r.get("NII")), "retail": _num(r.get("RII")), "total": _num(r.get("Total")), "asOf": stamp})
    if not out:
        raise SourceChanged(SOURCE, f"report 566: {len(rows)} rows, none with an id and a total (keys: {sorted(rows[0])[:8]})", "report 566")
    return out


def fetch_subscription_report(session, today: dt.date | None = None) -> list[dict]:
    d = today or dt.datetime.now(IST).date()
    url = f"https://webnodejs.investorgain.com/cloud/v2/report/data-read/{SUBSCRIPTION_REPORT}/1/{d.month}/{d.year}/{fiscal_year(d)}/0/all"
    return parse_subscription_report(session.get_json(url, source=SOURCE, headers=HEADERS), d)


def as_of(rows: list[dict]) -> str | None:
    """Latest 'Updated-On' stamp across rows, as an ISO date when parseable."""
    stamps = [r.get("updated") for r in rows if r.get("updated")]
    if not stamps:
        return None
    iso = [d for d in (_date(s) for s in stamps) if d and _ISO.match(d)]
    return max(iso) if iso else max(stamps)


def fetch(session, today: dt.date | None = None) -> list[dict]:
    d = today or dt.datetime.now(IST).date()
    data = session.get_json(url_for(d), source=SOURCE, headers=HEADERS)
    return parse_investorgain(data)
