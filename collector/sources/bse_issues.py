"""BSE public-issue sources — the cloud-safe fallback for the calendar and for subscription.

Three things live here:
  public_issues_json(session)   modern Angular API  api.bseindia.com/BseIndiaAPI/api/GetPublicIssue_par_updated/w
                                params flag=1&status=&exchange=&ir_flag=IPO (the IPOFetch shape, endpoints.md B3).
                                Returns {Table: [{IPO_NO, Scrip_cd, Scrip_Name, LONG_NAME, IR_flag, Start_Dt, End_Dt,
                                Price_Band, Face_Val, Status, eXCHANGE_PLATFORM ...}]}.
  public_issues_html(session)   legacy table  beta.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p
                                (www. serves 0 rows since the 2026 site migration; beta. still renders it).
                                Row parser: direct th/td children only (the page nests its real table inside layout
                                rows), >= 8 cells, fixed columns: 0 Security Name, 1 Platform, 2 Start, 3 End,
                                4 Offer Price, 6 Type of Issue (must be IPO), 7 Issue Status. IPONo from any
                                DisplayIPO link in the row.
  cumulative_demand(session, ipo_no)  beta.bseindia.com/markets/publicIssues/CummDemandSchedule.aspx?ID=<n>&status=L
                                category label in the first two cells, multiple in the last numeric cell.
                                Returned in the same [{category, noOfTime}] shape as NSE bidDetails so the
                                subscription classifier is shared.

Both HTML parsers use selectolax. Same internal row shape as nse_ipo.normalise_list_row, plus bseIpoNo/bseScripCode.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from ..errors import SourceChanged
from ..http import BSE_BETA
from .nse_ipo import first, iso_date, number, price_band

try:  # selectolax is a declared dependency; guard so the module imports (and tests can skip) without it
    from selectolax.parser import HTMLParser
except ImportError:  # pragma: no cover
    HTMLParser = None

SRC = "bse"
LEGACY_LIST_URL = BSE_BETA + "/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p"
DEMAND_URL = BSE_BETA + "/markets/publicIssues/CummDemandSchedule.aspx"
JSON_PATH = "/GetPublicIssue_par_updated/w"
JSON_PARAMS = {"flag": "1", "status": "", "exchange": "", "ir_flag": "IPO"}
HEADER_WORDS = {"security name", "security", "issuer", "company", "company name", "scrip"}


def _need_parser():
    if HTMLParser is None:
        raise SourceChanged(SRC, "selectolax not installed; cannot parse BSE HTML")


def _cell_text(node) -> str:
    return re.sub(r"\s+", " ", node.text(deep=True, separator=" ", strip=True)).strip()


def _direct_cells(tr) -> list:
    """th/td that are DIRECT children of the row — the legacy page nests the real table inside layout
    rows and a recursive walk collapses the whole page into one giant row."""
    return [c for c in tr.iter() if c.tag in ("td", "th")]


def _ipo_no_from_row(tr) -> str | None:
    for a in tr.css("a"):
        for raw in (a.attributes.get("href"), a.attributes.get("onclick")):
            n = _ipo_no_from_text(raw)
            if n:
                return n
    return _ipo_no_from_text(tr.html)


def _ipo_no_from_text(raw) -> str | None:
    if not raw:
        return None
    m = re.search(r"IPONo=(\d+)", str(raw), re.I)
    if m:
        return m.group(1)
    m = re.search(r"CummDemandSchedule\.aspx\?ID=(\d+)", str(raw), re.I)
    if m:
        return m.group(1)
    return None


def _board(platform: str) -> str:
    return "SME" if "SME" in (platform or "").upper() else "Mainboard"


# ---------------------------------------------------------------------------------------------
# calendar: legacy HTML table
# ---------------------------------------------------------------------------------------------
def parse_public_issues_html(html: str, *, url: str = LEGACY_LIST_URL) -> list[dict]:
    _need_parser()
    tree = HTMLParser(html or "")
    rows: list[dict] = []
    seen = set()
    for tr in tree.css("tr"):
        cells_nodes = _direct_cells(tr)
        if len(cells_nodes) < 8:
            continue
        cells = [_cell_text(c) for c in cells_nodes]
        name = cells[0]
        if not name or name.lower() in HEADER_WORDS:
            continue
        if cells[6].strip().upper() != "IPO":
            continue
        open_, close = iso_date(cells[2]), iso_date(cells[3])
        if not open_ or not close:
            continue
        lo, hi = price_band(cells[4])
        key = (name.lower(), open_, close)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "name": re.sub(r"\s+", " ", name).strip(), "symbol": None, "series": None,
            "board": _board(cells[1]), "open": open_, "close": close, "listing": None, "allotment": None,
            "bandLow": lo, "bandHigh": hi, "lotSize": None, "issueSizeCr": None, "statusHint": cells[7], "withdrawn": "withdraw" in cells[7].lower(),
            "totalSub": None, "bseIpoNo": _ipo_no_from_row(tr), "bseScripCode": None,
            "source": "BSE public issues (legacy table)",
        })
    if not rows:
        raise SourceChanged(SRC, "legacy public-issues table: 0 IPO rows", url)
    return rows


def public_issues_html(session) -> list[dict]:
    html = session.get_text(LEGACY_LIST_URL, source=SRC, headers={"Referer": BSE_BETA + "/"})
    return parse_public_issues_html(html, url=LEGACY_LIST_URL)


# ---------------------------------------------------------------------------------------------
# calendar: modern JSON API
# ---------------------------------------------------------------------------------------------
def parse_public_issues_json(data, *, url: str = JSON_PATH) -> list[dict]:
    table = data.get("Table") if isinstance(data, dict) else data
    if not isinstance(table, list) or not table:
        raise SourceChanged(SRC, "GetPublicIssue_par_updated: no Table rows", url)
    rows = []
    for r in table:
        if not isinstance(r, dict):
            continue
        flag = str(first(r, "IR_flag", "IR_FLAG", "ir_flag", default="") or "").upper()
        if flag and flag != "IPO":
            continue
        name = first(r, "LONG_NAME", "Scrip_Name", "short_name", "SCRIP_NAME")
        if not name:
            continue
        open_ = iso_date(first(r, "Start_Dt", "START_DT", "StartDate"))
        close = iso_date(first(r, "End_Dt", "END_DT", "EndDate"))
        if not open_ and not close:
            continue
        lo, hi = price_band(first(r, "Price_Band", "PRICE_BAND"))
        platform = str(first(r, "eXCHANGE_PLATFORM", "EXCHANGE_PLATFORM", "Platform", default="") or "")
        ipo_no = first(r, "IPO_NO", "IPONO", "IPONo")
        rows.append({
            "name": re.sub(r"\s+", " ", str(name)).strip(), "symbol": None, "series": None,
            "board": _board(platform), "open": open_, "close": close, "listing": None, "allotment": None,
            "bandLow": lo, "bandHigh": hi, "lotSize": None, "issueSizeCr": None,
            "statusHint": str(first(r, "Status", "STATUS", default="") or ""),
            "withdrawn": "withdraw" in str(first(r, "Status", default="") or "").lower(), "totalSub": None,
            "bseIpoNo": str(int(number(ipo_no))) if number(ipo_no) is not None else None,
            "bseScripCode": str(first(r, "Scrip_cd", "SCRIP_CD", default="") or "") or None,
            "source": "BSE public issues (api)",
        })
    if not rows:
        raise SourceChanged(SRC, f"GetPublicIssue_par_updated: {len(table)} rows, none an IPO with a name and dates "
                                 f"(keys: {sorted(table[0].keys())[:10] if isinstance(table[0], dict) else '?'})", url)
    return rows


def public_issues_json(session) -> list[dict]:
    data = session.bse_json(JSON_PATH, JSON_PARAMS, source=SRC)
    return parse_public_issues_json(data, url=JSON_PATH)


# ---------------------------------------------------------------------------------------------
# subscription: cumulative demand schedule
# ---------------------------------------------------------------------------------------------
def parse_cumulative_demand(html: str, *, url: str = DEMAND_URL) -> list[dict]:
    """Return [{category, noOfTime}] from the legacy demand table. Category text = first two cells
    (Sr.No + label, or label + offered); multiple = last numeric cell of the row."""
    _need_parser()
    tree = HTMLParser(html or "")
    out = []
    for tr in tree.css("tr"):
        cells = [_cell_text(c) for c in tr.css("th, td")]
        cells = [c for c in cells if c != ""]
        if len(cells) < 2:
            continue
        label = " ".join(cells[:2])
        if not re.search(r"[A-Za-z]", label):
            continue
        low = label.lower()
        if "no. of shares" in low and "category" in low:      # header row
            continue
        value = None
        for c in reversed(cells):
            n = number(c)
            if n is not None:
                value = n
                break
        if value is None or value < 0:
            continue
        out.append({"category": label, "noOfTime": value})
    if not out:
        raise SourceChanged(SRC, "cumulative demand table: no category rows (empty page?)", url)
    return out


def cumulative_demand(session, ipo_no: str) -> list[dict]:
    url = f"{DEMAND_URL}?ID={ipo_no}&status=L"
    html = session.get_text(url, source=SRC, headers={"Referer": BSE_BETA + "/"})
    return parse_cumulative_demand(html, url=url)


def ipo_no_from_url(url: str) -> str | None:
    q = {k.lower(): v for k, v in parse_qs(urlparse(url).query).items()}
    for k in ("ipono", "id"):
        if q.get(k):
            digits = re.sub(r"\D", "", q[k][0])
            if digits:
                return digits
    return None
