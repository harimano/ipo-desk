"""subscription — patches `sub` into rows of `mainboard` / `sme` (ROW_PATCHERS, never owns the lists).

For every board row that is Open, or Closed within the last 3 days, fetch category-wise subscription:
  nse   /api/ipo-detail?symbol=&series=        (needs the row's `symbol`; the calendar stores it)
  bse   CummDemandSchedule.aspx?ID=<IPONo>     (needs the row's `bseIpoNo`)
  chittorgarh  report 21 live-bidding table    (matched by name; fetched once per run, last resort)
and write  sub: {qib, nii, retail, employee?, shareholder?, total, asOf}.

Category classifier (lifted from the IPO-Tracker track_subscriptions notes, with one change): NII
sub-buckets (bNII/sNII, "above/below 10 lakh", "bid amount ...") are NOT dropped — they are combined
into `nii` when no aggregate NII row exists. Combining is done on shares (sum bid / sum offered) when
the source gives them, else by the SEBI 1/3 (small) : 2/3 (big) reservation weights. A sub-bucket is
never counted on top of an aggregate NII row.

Never writes a `sub` whose qib/nii/retail/total are all null.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from zoneinfo import ZoneInfo

from ..errors import SourceBlocked, SourceChanged, SourceError
from ..http import Session
from ..result import Result
from ..sources import bse_issues, nse_ipo
from .calendar import derive_status, match_name, norm_name

try:
    from selectolax.parser import HTMLParser
except ImportError:  # pragma: no cover
    HTMLParser = None

log = logging.getLogger("collector.subscription")
IST = ZoneInfo("Asia/Kolkata")
MODULE = "subscription"
CLOSED_GRACE_DAYS = 1              # the evening after the close carries the final print; after that the per-IPO record has it
#                                    (was 3: a dozen 4-5 s NSE calls per run for books that no longer move)
CHITTORGARH_URL = "https://www.chittorgarh.com/report/ipo-subscription-status-live-bidding-data-bse-nse/21/"
CATEGORIES = ("qib", "nii", "retail", "employee", "shareholder", "total")
SUB_BUCKET_MARKERS = ("bid amount", "above", "below", "more than", "less than", "upto", "up to", "10 lakh",
                      "10 lac", "2 lakh", "2 lac", "snii", "bnii", "shni", "bhni", "small nii", "big nii",
                      "small hni", "big hni", "s hni", "b hni", "s nii", "b nii", "nii1", "nii2", "nii 1", "nii 2")
BIG_MARKERS = ("above", "more than", "bnii", "bhni", "big", "b nii", "b hni", "nii2", "nii 2", "greater")
SMALL_MARKERS = ("below", "less than", "upto", "up to", "snii", "shni", "small", "s nii", "s hni", "nii1", "nii 1")


# ---------------------------------------------------------------------------------------------
# classifier
# ---------------------------------------------------------------------------------------------
def classify(text: str) -> tuple[str | None, str | None]:
    """-> (category, bucket). bucket is None for an aggregate row, "big"/"small" for an NII sub-bucket."""
    t = " ".join(str(text or "").lower().replace("-", " ").replace("_", " ").replace("/", " ").split())
    t = re.sub(r"\([^)]*\)", lambda m: " " + m.group(0)[1:-1] + " ", t)
    t = " ".join(t.split())
    words = set(re.findall(r"[a-z0-9]+", t))
    if not words:
        return None, None
    if "total" in words or t in {"overall", "grand total", "cumulative"}:
        return "total", None
    if "employee" in words or "employees" in words or "emp" in words:
        return "employee", None
    if "shareholder" in words or "shareholders" in words or "policyholder" in words or "policyholders" in words:
        return "shareholder", None
    if "qualified institutional" in t or "qib" in words or "qibs" in words or "institutional buyers" in t:
        if "non" not in words:
            return "qib", None
    if "retail" in t or "rii" in words or "riis" in words or "rib" in words:
        return "retail", None
    if ("individual investor" in t or "individual investors" in t) and "non" not in words:
        return "retail", None                      # NSE's SME label for the retail bucket
    if ("non institutional" in t or "non institution" in t or "nii" in words or "niis" in words
            or "nib" in words or "hni" in words or "hnis" in words or "non ins" in t):
        if any(m in t for m in SUB_BUCKET_MARKERS):
            if any(m in t for m in BIG_MARKERS):
                return "nii", "big"
            if any(m in t for m in SMALL_MARKERS):
                return "nii", "small"
            return "nii", "unknown"
        return "nii", None
    if t.startswith("bnii") or t.startswith("snii") or t.startswith("bhni") or t.startswith("shni"):
        return "nii", ("big" if t[0] == "b" else "small")
    return None, None


def combine(rows: list[dict]) -> dict:
    """[{category, noOfTime, sharesOffered?, sharesBid?}] -> {qib, nii, retail, employee?, shareholder?, total}.
    Aggregate rows win. NII sub-buckets are combined only when no aggregate NII row is present."""
    agg: dict[str, float] = {}
    subs: list[tuple[str, dict]] = []
    for r in rows:
        cat, bucket = classify(r.get("category", ""))
        if not cat:
            continue
        val = nse_ipo.number(r.get("noOfTime"))
        if val is None or val < 0:
            continue
        if bucket:
            subs.append((bucket, {**r, "noOfTime": val}))
        elif cat not in agg:
            agg[cat] = val
    if "nii" not in agg and subs:
        nii = _combine_nii(subs)
        if nii is not None:
            agg["nii"] = nii
    out: dict = {k: agg.get(k) for k in ("qib", "nii", "retail", "total")}
    for k in ("employee", "shareholder"):
        if k in agg:
            out[k] = agg[k]
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in out.items()}


def _combine_nii(subs: list[tuple[str, dict]]) -> float | None:
    offered = sum(nse_ipo.number(r.get("sharesOffered")) or 0 for _, r in subs)
    bid = [nse_ipo.number(r.get("sharesBid")) for _, r in subs]
    if offered > 0 and all(b is not None for b in bid):
        return sum(bid) / offered
    # multiples only: weight by the SEBI reservation split (1/3 small, 2/3 big)
    weights = {"big": 2 / 3, "small": 1 / 3}
    known = [(weights[b], r["noOfTime"]) for b, r in subs if b in weights]
    if len(known) == 2 and {b for b, _ in subs} == {"big", "small"}:
        return sum(w * v for w, v in known)
    vals = [r["noOfTime"] for _, r in subs]
    return sum(vals) / len(vals) if vals else None


def has_values(sub: dict | None) -> bool:
    return bool(sub) and any(sub.get(k) is not None for k in ("qib", "nii", "retail", "total"))


# ---------------------------------------------------------------------------------------------
# chittorgarh report 21 (HTML table, matched by name)
# ---------------------------------------------------------------------------------------------
def parse_chittorgarh(html: str, *, url: str = CHITTORGARH_URL) -> dict[str, dict]:
    """-> {company name: {qib, nii, retail, employee?, shareholder?, total}} from the live-bidding table.
    Columns are found by header text, so column order does not matter; sNII/bNII headers are
    sub-buckets and are combined only when there is no NII column."""
    if HTMLParser is None:
        raise SourceChanged("chittorgarh", "selectolax not installed", url)
    tree = HTMLParser(html or "")
    out: dict[str, dict] = {}
    for table in tree.css("table"):
        header_cells = None
        for tr in table.css("tr"):
            cells = [re.sub(r"\s+", " ", c.text(deep=True, separator=" ", strip=True)).strip() for c in tr.css("th, td")]
            if not cells:
                continue
            if header_cells is None:
                if any(re.search(r"\bqib", c, re.I) for c in cells) and any(re.search(r"total", c, re.I) for c in cells):
                    header_cells = [classify(c) for c in cells]
                continue
            name = cells[0]
            if not name or len(cells) != len(header_cells):
                continue
            rows = []
            for i, (cat, bucket) in enumerate(header_cells):
                if not cat or i == 0:
                    continue
                label = {"big": "bNII", "small": "sNII"}.get(bucket, cat) if cat == "nii" else cat
                rows.append({"category": label, "noOfTime": cells[i]})
            sub = combine(rows)
            if has_values(sub):
                out[re.sub(r"\s+(ipo|sme ipo)$", "", name, flags=re.I).strip()] = sub
    if not out:
        raise SourceChanged("chittorgarh", "report 21: no subscription table with QIB/Total headers", url)
    return out


# ---------------------------------------------------------------------------------------------
# per-row fetch
# ---------------------------------------------------------------------------------------------
def candidates(prev: dict, today: dt.date) -> list[dict]:
    cut = (today - dt.timedelta(days=CLOSED_GRACE_DAYS)).isoformat()
    out = []
    for key in ("mainboard", "sme"):
        for r in prev.get(key) or []:
            if not isinstance(r, dict) or not r.get("name"):
                continue
            st = derive_status(r.get("open"), r.get("close"), r.get("listing"), today)
            if st == "Open" or (st == "Closed" and (r.get("close") or "0000") >= cut):
                out.append(r)
    return out


def _now_iso() -> str:
    return dt.datetime.now(IST).replace(microsecond=0).isoformat()


class _Chittorgarh:
    """Fetched at most once per run, and only when a row needs it."""
    def __init__(self, session: Session):
        self.session, self.table, self.err = session, None, None

    def get(self) -> dict[str, dict]:
        if self.table is None and self.err is None:
            try:
                html = self.session.get_text(CHITTORGARH_URL, source="chittorgarh",
                                             headers={"Referer": "https://www.chittorgarh.com/"})
                self.table = parse_chittorgarh(html)
            except SourceError as e:
                self.err = e
        if self.err:
            raise self.err
        return self.table

    def lookup(self, name: str) -> dict | None:
        table = self.get()
        hit = match_name(name, list(table.keys()))
        if hit is None:
            n = norm_name(name)
            for k in table:
                kn = norm_name(k)
                if n and kn and (n in kn or kn in n):
                    hit = k
                    break
        return table.get(hit) if hit else None


def fetch_row(session: Session, row: dict, chit: _Chittorgarh, nse_blocked: list[bool]) -> tuple[str, dict]:
    """-> (source, sub). Raises SourceError when every source failed."""
    errs: list[str] = []
    if row.get("symbol") and not nse_blocked[0]:
        try:
            d = nse_ipo.ipo_detail(session, row["symbol"], row.get("series") or "EQ")
            sub = combine(d["bidDetails"])
            if not has_values(sub) and d.get("rootTotal") is not None:
                sub["total"] = d["rootTotal"]
            if has_values(sub):
                sub["asOf"] = _as_of(d.get("updateTime"))
                return "nse", sub
            errs.append("nse: bidDetails classified to nothing")
        except SourceBlocked as e:
            nse_blocked[0] = True             # one block is enough; do not hammer for every row
            errs.append(f"nse: {e.detail}")
        except SourceError as e:
            errs.append(f"nse: {e.detail}")
    if row.get("bseIpoNo"):
        try:
            rows = bse_issues.cumulative_demand(session, str(row["bseIpoNo"]))
            sub = combine(rows)
            if has_values(sub):
                sub["asOf"] = _now_iso()
                return "bse", sub
            errs.append("bse: demand rows classified to nothing")
        except SourceError as e:
            errs.append(f"bse: {e.detail}")
    try:
        sub = chit.lookup(row["name"])
        if sub and has_values(sub):
            sub = dict(sub)
            sub["asOf"] = _now_iso()
            return "chittorgarh", sub
        errs.append("chittorgarh: name not in table")
    except SourceError as e:
        errs.append(f"chittorgarh: {e.detail}")
    raise SourceChanged("subscription", f"{row['name']}: " + "; ".join(errs))


def _as_of(update_time) -> str:
    iso = nse_ipo.iso_date(update_time)
    if iso and update_time:
        m = re.search(r"(\d{1,2}):(\d{2})", str(update_time))
        if m:
            return f"{iso}T{int(m.group(1)):02d}:{m.group(2)}:00+05:30"
        return iso
    return _now_iso()


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = today or dt.datetime.now(IST).date()
    rows = candidates(res.doc or prev, t)                  # today's board: a row calendar made this run has its symbol already
    if not rows:
        res.notes.append("no open or recently closed issues on the board")
        return res.won("none", _now_iso())
    chit = _Chittorgarh(session)
    nse_blocked = [False]
    patches: dict[str, dict[str, dict]] = {"mainboard": {}, "sme": {}}
    won: set[str] = set()
    last: SourceError | None = None
    failed = []
    for row in rows:
        if not row.get("symbol") and not row.get("bseIpoNo"):
            continue                                   # no handle to ask an exchange with; the per-IPO record covers it
        try:
            src, sub = fetch_row(session, row, chit, nse_blocked)
        except SourceError as e:
            last = e
            failed.append(row["name"])
            log.info("subscription %s", e.detail)
            continue
        if not has_values(sub):
            continue
        # An exchange's page goes blank once an issue has closed (BSE SME, seen live 18 Sep 2026: all zeros where the
        # book had been 11.87x). This module runs last so that the exchanges win — but never with nothing.
        if not (sub.get("total") or 0) > 0 and ((row.get("sub") or {}).get("total") or 0) > 0:
            continue
        for k in ("employee", "shareholder"):     # keep an optional category from earlier today if this source lacks it
            old = (row.get("sub") or {}).get(k)
            if k not in sub and old is not None:
                sub[k] = old
        key = "sme" if str(row.get("type", "")).endswith("SME") else "mainboard"
        patches[key][row["name"]] = {"sub": sub}
        won.add(src)
    n = sum(len(v) for v in patches.values())
    if n == 0:
        res.tried.append({"kind": "changed", "source": "nse/bse/chittorgarh", "ok": False,
                          "detail": f"0 of {len(rows)} rows fetched"})
        return res.fail(last or SourceChanged("subscription", "no source answered"))
    res.rows = {k: v for k, v in patches.items() if v}
    res.notes.append(f"{n}/{len(rows)} rows patched via {', '.join(sorted(won))}")
    if failed:
        res.notes.append(f"no subscription for: {', '.join(failed[:5])}")
        res.unresolved.append(f"subscription missing for {', '.join(failed[:5])} — check NSE/BSE ids on the row")
    if nse_blocked[0]:
        res.notes.append("nse blocked; used fallbacks")
    return res.won("+".join(sorted(won)), _now_iso())
