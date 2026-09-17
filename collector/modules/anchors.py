"""anchors — owns `anchors[]`: who took the anchor book of each issue, read from the issuer's own letter.

Source: NSE's "Anchor Allocation Report" (nsearchives .../content/ipo/ANCHOR_<SYMBOL>.zip), parsed by
collector/pdf/anchor.py, which believes a row only when shares x price = amount and a letter only when the
rows add up. There is no second source: the alternatives are blogs retyping the same letter.

  * a letter is read once. A row carrying `source: "nse-anchor-letter"` is never fetched again;
  * hand-written rows from the db era stay until a letter for the same issue replaces them;
  * a letter that is not there yet (404 the day before it is filed), is a scan on a machine without
    Tesseract, or does not add up, changes nothing and is noted — the module still succeeds if it had
    nothing to do. It fails only when every letter it tried to read failed.
"""
from __future__ import annotations

import datetime as dt
import logging
import pathlib
from zoneinfo import ZoneInfo

from ..errors import SourceChanged, SourceError
from ..http import NSE_ARCHIVES, Session
from ..names import Matcher, load_aliases
from ..pdf import anchor as letter
from ..result import Result

log = logging.getLogger("collector.anchors")
IST = ZoneInfo("Asia/Kolkata")
ALIASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"
SOURCE_TAG = "nse-anchor-letter"
MAX_LETTERS_PER_RUN = 6
WINDOW_BEFORE_OPEN, WINDOW_AFTER_OPEN = 2, 10          # days around `open` in which a letter is looked for
TOP_TIER = ("MF", "Insurance", "Pension/Sovereign")


def url_for(symbol: str) -> str:
    return f"{NSE_ARCHIVES}/content/ipo/ANCHOR_{symbol}.zip"


def targets(prev: dict, today: dt.date) -> list[dict]:
    done = {a.get("name") for a in prev.get("anchors") or [] if isinstance(a, dict) and a.get("source") == SOURCE_TAG}
    out = []
    for key in ("mainboard", "sme"):
        for r in prev.get(key) or []:
            if not isinstance(r, dict) or not r.get("symbol") or r.get("name") in done:
                continue
            try:
                opens = dt.date.fromisoformat(str(r.get("open"))[:10])
            except ValueError:
                continue
            if -WINDOW_BEFORE_OPEN <= (today - opens).days <= WINDOW_AFTER_OPEN:
                out.append(r)
    out.sort(key=lambda r: (r.get("type") != "Mainboard", r.get("open") or ""))
    return out[:MAX_LETTERS_PER_RUN]


def build_row(board_row: dict, book: dict, url: str) -> dict:
    inv = sorted(book["investors"], key=lambda i: -i["amountCr"])
    total = book["amountCr"] or sum(i["amountCr"] for i in inv)
    for i in inv:
        i["pct"] = round(100 * i["amountCr"] / total, 2) if total else i["pct"]
    top = round(sum(i["pct"] for i in inv if i["cat"] in TOP_TIER), 2)
    names = ", ".join(i["name"].title() if i["name"].isupper() else i["name"] for i in inv[:9])
    return {"name": board_row["name"], "date": book.get("date"), "amountCr": total,
            "issueSizeCr": board_row.get("issueSizeCr"), "count": len(inv), "topTierShare": top,
            "anchor": f"₹{total:,.2f} Cr from {len(inv)} allocations on {book.get('date') or '—'} — {names}",
            "investors": [{"name": i["name"], "cat": i["cat"], "amountCr": i["amountCr"], "pct": i["pct"]} for i in inv],
            "price": book.get("price"), "sources": [url], "source": SOURCE_TAG,
            "note": f"Read from the issuer's allocation letter ({book.get('read')}); every row checked: shares × price = amount."
                    + (f" {book['dropped']} unreadable line(s) left out." if book.get("dropped") else "")}


def run(session: Session, prev: dict, res: Result, today: dt.date | None = None) -> Result:
    t = today or dt.datetime.now(IST).date()
    todo = targets(prev, t)
    if not todo:
        res.notes.append("no issue near its opening day without a letter on file")
        return res.won("none", t.isoformat())
    rows = [dict(a) for a in prev.get("anchors") or [] if isinstance(a, dict) and a.get("name")]
    read, waiting, failed = [], [], []
    last: SourceError | None = None
    for b in todo:
        url = url_for(b["symbol"])
        try:
            book = letter.parse_pdf(letter.pdf_from_zip(session.get_bytes(url, source="nsearchives")))
        except SourceError as e:
            (waiting if e.kind == "down" else failed).append(f"{b['name']}: {e.detail}")
            last = e if e.kind != "down" else last
            log.info("anchor letter %s: %s", b["symbol"], e.detail)
            continue
        new = build_row(b, book, url)
        hit = Matcher(rows, load_aliases(ALIASES_DIR)).match(b["name"])
        rows = [r for r in rows if r["name"] != hit] + [new]      # a letter replaces a hand-written row for the same issue
        read.append(f"{b['name']} ({new['count']} allocations, ₹{new['amountCr']:,.0f} Cr, {book['read']})")
    if read:
        rows.sort(key=lambda r: r.get("date") or "", reverse=True)
        res.replace["anchors"] = rows
        res.notes.append("read: " + "; ".join(read))
    if waiting:
        res.notes.append(f"{len(waiting)} letter(s) not published yet")
    if failed:
        res.notes.append("could not read: " + "; ".join(failed)[:400])
        res.unresolved.append("anchor letters that could not be read: " + "; ".join(f.split(":")[0] for f in failed))
    if failed and not read:
        return res.fail(last or SourceChanged("anchors", "no letter could be read"))
    return res.won("nse-anchor-letters", t.isoformat())
