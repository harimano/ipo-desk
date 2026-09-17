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
MIN_COVERAGE = 0.90          # believed rows must carry this much of the letter's stated total (or of 100%)

_NUM = r"\d[\d,]*"
_ROW = re.compile(
    rf"(?<![\d,.])(?P<sr>\d{{1,3}})[.)]?\s+(?P<name>[A-Za-z][^%]{{2,220}}?)\s+(?P<shares>{_NUM})\s+"
    rf"(?P<pct>\d{{1,3}}(?:\.\d{{1,4}})?)\s*%\s+(?:Rs\.?\s*|₹\s*)?(?P<price>\d[\d,]*(?:\.\d+)?)\s*(?:/-)?\s+"
    rf"(?:Rs\.?\s*|₹\s*)?(?P<amount>{_NUM}(?:\.\d+)?)")
_PRICE = re.compile(r"allocation\s+price\s+of\s+(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d+)?)", re.I)
_TOTAL = re.compile(r"allocation\s+of\s+([\d,]{4,})\s+Equity\s+Shares", re.I)
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
    return float(str(s).replace(",", ""))


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
    rows, dropped = [], 0
    for m in _ROW.finditer(flat):
        shares, price, amount, pct = _n(m["shares"]), _n(m["price"]), _n(m["amount"]), float(m["pct"])
        name = re.sub(r"\s+", " ", m["name"]).strip(" -–|:;,.")
        ok = shares > 0 and price > 0 and abs(shares * price - amount) <= ROW_TOLERANCE_RS
        if stated_price and abs(price - stated_price) > 0.01 * stated_price:
            ok = False
        if not ok or len(name) < 3 or pct > 100:
            dropped += 1
            continue
        rows.append({"name": name, "cat": category(name), "shares": int(shares),
                     "amountCr": round(amount / 1e7, 2), "pct": round(pct, 2)})
    if not rows:
        raise SourceChanged(SRC, f"no allocation row passed the arithmetic check ({dropped} candidates rejected)")
    got_shares, got_pct = sum(r["shares"] for r in rows), sum(r["pct"] for r in rows)
    coverage = got_shares / stated_total if stated_total else got_pct / 100
    if not (MIN_COVERAGE <= coverage <= 1.02):
        raise SourceChanged(SRC, f"believed rows cover {coverage:.0%} of the anchor portion "
                                 f"({len(rows)} rows kept, {dropped} rejected) — refusing a partial book")
    price = stated_price or _n(_ROW.search(flat)["price"])
    return {"date": _iso(flat), "price": price, "totalShares": int(stated_total or got_shares),
            "amountCr": round(sum(r["amountCr"] for r in rows), 2), "investors": rows, "dropped": dropped}


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
