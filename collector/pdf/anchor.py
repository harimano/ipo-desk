"""Anchor allocation letters — the PDF an issuer files with the exchanges the evening before it opens.
NSE serves it at nsearchives .../content/ipo/ANCHOR_<SYMBOL>.zip (linked from ipo-detail as "Anchor
Allocation Report"; seen live 17 Sep 2026).

Seen in the wild: small issuers file real text; large ones file a scan (NSE's own letter: 14 pages, no
text layer). So text comes from the text layer when there is one and from OCR (Tesseract through
PyMuPDF) when there is not. Either way the text is only a candidate. A row is believed when its own
arithmetic closes — shares x price = amount — and the letter is believed when the rows add up to the
anchor portion. OCR that misreads a digit fails that test and the row is dropped; a letter that loses
too much is refused (SourceChanged), so nothing half-read reaches the page.

    python -m collector.pdf.anchor letter.pdf [--ocr]
"""
from __future__ import annotations

import io
import re
import sys
import zipfile

from ..errors import SourceChanged

SRC = "anchor-letter"
ROW_TOLERANCE_RS = 1.0       # shares x price must equal the amount to the rupee: these are exact integers
MIN_PARTIAL = 0.50           # below this even a summary row is not published
MIN_COVERAGE = 0.90          # believed rows must carry this much of the letter's stated total (or of 100%)

# The dependable part of every row, in text and in OCR alike, is its numeric tail:
#     shares  pct%  price  amount          (cells may be split by "|", the price may end "/-", digits may
# carry OCR punctuation slips such as 4,99,99.488.00). The name is whatever lies between two tails.
_INT = r"\d[\d,.]*\d"
_TAIL = re.compile(
    rf"(?<![\d,.])(?P<shares>{_INT})[\s|]*(?P<pct>\d{{1,3}}(?:[.,]\d{{1,4}})?)\s*%[\s|]*(?:Rs\.?|₹|INR)?\s*"
    rf"(?P<price>{_INT}|\d)\s*(?:/-)?[\s|]*(?:Rs\.?|₹|INR)?\s*(?P<amount>{_INT})(?:\s*/-)?")
_SERIAL = re.compile(r"(?:^|[\s|\[(])(\d{1,3})\s*[.\])]?\s*\|")            # "| 9. |", "10. |", "106]"
_SERIAL_LINE = re.compile(r"(?:^|\s)(\d{1,3})[.)]\s+(?=[A-Za-z])")
_HEADER_END = re.compile(r".*(?:\(\s*(?:in\s+)?(?:Rs\.?|₹|INR|%|z)\s*\)|\bper\s+Equity\s+Share\)?|\bEquity\s+Shares?\)?|\bPortion\b|"
                         r"\ballocated\b|\bAllocation\b|\bAmount\b|\bPrice\b|\bInvestor\b|\bmanner\s*:)", re.I | re.S)
# "Out of the 37,793,739 Equity Shares allocated to the Anchor Investors, 13,977,524 Equity Shares (i.e., 36.98% ...)
#  were allocated to 29 domestic mutual funds ..." — the issuer's own statement of who took the book. The tables
# that follow these sentences repeat rows of the main table, so the main table ends where the first one starts.
_STATED = re.compile(r"out\s+of\s+the\b.{0,120}?\(\s*i\.?\s*e\.?,?\s*(?P<pct>\d{1,3}(?:\.\d{1,2})?)\s*%.{0,90}?allocated\s+to\s+"
                     r"(?P<n>\d{1,3})\s+(?P<who>[A-Za-z /&-]{4,70}?)(?:,|\s+which|\s+details|\s+through|\.)", re.I)
_PRICE = re.compile(r"allocation\s+price\s+of\s*(?:Rs\.?|₹|INR|%|z|Z)?\s*([\d,]+(?:\.\d+)?)", re.I)
_TOTAL = re.compile(r"(?:allocation\s+of|out\s+of\s+the(?:\s+total\s+allocation\s+of)?)\s+([\d,]{5,})\s+Equity\s+Shares", re.I)
_DATE = re.compile(r"(?:Date[d:]*\s*)?((?:January|February|March|April|May|June|July|August|September|October|November|"
                   r"December)\s+\d{1,2},?\s+\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|"
                   r"August|September|October|November|December),?\s+\d{4})", re.I)
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}

_CATS = (("MF", r"mutual fund|\bmf\b|\bamc\b|asset management|flexi ?cap|small ?cap|mid ?cap|large ?cap|multi ?cap|"
                r"elss|tax saver|hybrid fund|balanced advantage|opportunities fund|\bscheme\b"),
         ("Insurance", r"insurance|\blife\b|assurance|\blic\b|general ins"),
         ("Pension/Sovereign", r"pension|provident|superannuation|sovereign|government of|monetary authority|"
                               r"investment authority|\bgic\b|temasek|norges|retirement"),
         ("FPI", r"\bplc\b|\bllc\b|\bl\.?p\.?\b|\bpte\b|mauritius|singapore|luxembourg|cayman|\bsicav\b|\bvcc\b|"
                 r"\bodi\b|global|international|emerging markets|\binc\b|limited partnership"),
         ("AIF", r"\baif\b|alternative investment|\btrust\b|\bfund\b"))


def _n(s: str) -> float:
    """Indian or Western grouping, with OCR's comma/full-stop confusion: a final group of one or two digits
    after a separator is the paise; every other separator is just grouping."""
    s = str(s).strip()
    m = re.fullmatch(r"(.*\d)[.,](\d{1,2})", s)
    whole, frac = (m.group(1), m.group(2)) if m else (s, "")
    digits = re.sub(r"\D", "", whole)
    return float(f"{digits}.{frac}") if frac else float(digits)


def _clean_name(s: str) -> str:
    s = re.sub(r"[|\[\]{}_~;=]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—:,.'\"")
    s = re.sub(r"^(?:Sr\.?\s*No\.?|No\.?)\s*", "", s, flags=re.I)
    s = re.sub(r"^\d{1,3}[.,)]?\s+(?=[A-Za-z])", "", s)                      # the row's own serial number
    s = re.sub(r"(?<=[A-Za-z])\s+\d{1,2}\s+(?=[A-Z])", " ", s)               # a serial OCR dropped inside a wrapped name
    return s.strip(" -–—:,.'\"")


def category(name: str) -> str:
    low = name.lower()
    for cat, pat in _CATS:
        if re.search(pat, low):
            return cat
    return "Other"


def _iso(text: str) -> str | None:
    m = _DATE.search(text)
    if not m:
        return None
    parts = re.findall(r"[A-Za-z]+|\d+", re.sub(r"(st|nd|rd|th)\b", "", m.group(1)))
    day = next((int(p) for p in parts if p.isdigit() and len(p) <= 2), None)
    year = next((int(p) for p in parts if p.isdigit() and len(p) == 4), None)
    mon = next((_MONTHS[p.lower()] for p in parts if p.lower() in _MONTHS), None)
    return f"{year:04d}-{mon:02d}-{day:02d}" if day and year and mon else None


def parse_text(text: str) -> dict:
    """-> {date, price, totalShares, amountCr, investors[{name, cat, shares, amountCr, pct}], dropped}."""
    flat = re.sub(r"\s+", " ", text or "")
    if len(flat) < 200:
        raise SourceChanged(SRC, f"letter has almost no text ({len(flat)} chars) — scanned, and OCR unavailable?")
    pm, tm = _PRICE.search(flat), _TOTAL.search(flat)
    stated_price = _n(pm.group(1)) if pm else None
    stated_total = _n(tm.group(1)) if tm else None

    stated = {}
    for s in _STATED.finditer(flat):
        who = s["who"].lower()
        key = "mf" if "mutual" in who else "insurancePension" if re.search(r"insur|pension", who) else None
        if key and key not in stated:
            stated[key] = {"pct": float(s["pct"]), "count": int(s["n"])}
    first_summary = _STATED.search(flat)
    main_end = first_summary.start() if first_summary else len(flat)
    tails = list(_TAIL.finditer(flat))
    flat_for_rows = flat
    rows, dropped, seen = [], 0, set()
    prev_end = 0
    for m in tails:
        between, prev_end = flat_for_rows[prev_end:m.start()], m.end()
        try:
            shares, price, amount = _n(m["shares"]), _n(m["price"]), _n(m["amount"])
            pct = float(m["pct"].replace(",", "."))
        except ValueError:
            dropped += 1
            continue
        # which words belong to this row? After a serial marker they are this row's; before it they are the
        # tail end of the previous row's name, which wrapped under its numbers.
        cut = None
        for s in list(_SERIAL.finditer(between)) + list(_SERIAL_LINE.finditer(between)):
            cut = s if cut is None or s.start() > cut.start() else cut
        carry, own = (between[:cut.start()], between[cut.end():]) if cut else ("", between)
        if rows and carry.strip() and rows[-1].get("_open"):
            rows[-1]["name"] = _clean_name(rows[-1]["name"] + " " + carry)[:160]
        hdr = _HEADER_END.match(own)
        name = _clean_name(own[hdr.end():] if hdr else own)[-160:]
        ok = (shares > 0 and price > 0 and abs(shares * price - amount) <= ROW_TOLERANCE_RS and 0 < pct <= 100
              and (not stated_price or abs(price - stated_price) <= 0.01 * stated_price))
        if re.fullmatch(r"(?:grand\s+)?total.*", name, re.I) or (stated_total and shares == stated_total):
            continue                                        # the letter's own total line
        if not ok or len(name) < 3:
            dropped += 1
            continue
        key = (name, shares, m.start() < main_end)
        if key in seen:                                     # the same table printed again for the MF break-up
            continue
        seen.add(key)
        rows.append({"name": name, "shares": int(shares), "amountCr": round(amount / 1e7, 2), "pct": round(pct, 2),
                     "_open": True, "_main": m.start() < main_end})
    if not rows:
        raise SourceChanged(SRC, f"no allocation row passed the arithmetic check ({dropped} candidates rejected)")

    # The break-up tables after the summary sentences repeat rows of the main table. A row OCR garbled in the
    # main table is often legible in its repeat, so per share-count the book holds max(main, repeats) rows:
    # repeats are a subset of the main table, never an addition to it.
    main_rows = [r for r in rows if r["_main"]]
    later: dict[int, list[dict]] = {}
    for r in rows:
        if not r["_main"]:
            later.setdefault(r["shares"], []).append(r)
    have: dict[int, int] = {}
    for r in main_rows:
        have[r["shares"]] = have.get(r["shares"], 0) + 1
    recovered = 0
    for v, rs in later.items():
        for r in rs[have.get(v, 0):]:
            main_rows.append(r)
            recovered += 1
    rows = main_rows
    got_shares, got_pct = sum(r["shares"] for r in rows), sum(r["pct"] for r in rows)
    coverage = got_shares / stated_total if stated_total else got_pct / 100
    partial = False
    if not (MIN_COVERAGE <= coverage <= 1.02):
        # A long scan rarely reads clean line by line. The letter still says, in prose, how big the book is and
        # how much of it mutual funds and insurers took. With those three facts on record the verified rows can be
        # published as what they are — part of the list — under totals that are the issuer's, not ours.
        if coverage > 1.02 or coverage < MIN_PARTIAL or not (stated_total and stated_price and stated):
            raise SourceChanged(SRC, f"believed rows cover {coverage:.0%} of the anchor portion "
                                     f"({len(rows)} rows kept, {dropped} rejected) — refusing a partial book")
        partial = True
    for r in rows:
        r.pop("_open", None)
        r.pop("_main", None)
        r["cat"] = category(r["name"])
    price = stated_price or _n(tails[0]["price"])
    # the book's size is the issuer's statement whenever the letter makes one; our row sum is the fallback
    amount = stated_total * stated_price / 1e7 if stated_total and stated_price else sum(r["amountCr"] for r in rows)
    return {"date": _iso(flat), "price": price, "totalShares": int(stated_total or got_shares),
            "amountCr": round(amount, 2), "partial": partial, "coverage": round(coverage, 4), "stated": stated, "recovered": recovered,
            "investors": rows, "dropped": dropped}


# ---------------------------------------------------------------------------------------------
def pdf_from_zip(blob: bytes) -> bytes:
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise SourceChanged(SRC, f"anchor report is not a zip: {e}")
    pdfs = sorted((i for i in z.infolist() if i.filename.lower().endswith(".pdf")), key=lambda i: -i.file_size)
    if not pdfs:
        raise SourceChanged(SRC, f"anchor zip holds no PDF: {[i.filename for i in z.infolist()][:4]}")
    return z.read(pdfs[0])


def ocr_available() -> bool:
    import shutil
    return shutil.which("tesseract") is not None


def extract_text(pdf: bytes, *, max_pages: int = 20) -> tuple[str, str]:
    """-> (text, how) where how is 'text' or 'ocr'."""
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    pages = list(doc)[:max_pages]
    text = "\n".join(p.get_text() for p in pages)
    if len(re.sub(r"\s+", "", text)) >= 400:
        return text, "text"
    if not ocr_available():
        raise SourceChanged(SRC, f"letter is a scan ({len(pages)} pages, no text layer) and tesseract is not installed")
    out = []
    for p in pages:
        tp = p.get_textpage_ocr(dpi=300, full=True, language="eng")
        out.append(p.get_text(textpage=tp))
    return "\n".join(out), "ocr"


def parse_pdf(pdf: bytes) -> dict:
    text, how = extract_text(pdf)
    book = parse_text(text)
    book["read"] = how
    return book


if __name__ == "__main__":
    import json
    import pathlib
    print(json.dumps(parse_pdf(pathlib.Path(sys.argv[1]).read_bytes()), indent=1, ensure_ascii=False))
