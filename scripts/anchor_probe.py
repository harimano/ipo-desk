#!/usr/bin/env python3
"""Read anchor letters for the given NSE symbols and print what the parser believes. Writes nothing.
    python scripts/anchor_probe.py NSE HEROMOTORS SONA
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from collector.errors import SourceError  # noqa: E402
from collector.http import Session  # noqa: E402
from collector.modules.anchors import url_for  # noqa: E402
from collector.pdf import anchor as letter  # noqa: E402


def main(symbols: list[str]) -> int:
    s = Session()
    print("tesseract:", "yes" if letter.ocr_available() else "NO")
    for sym in symbols:
        print(f"\n=== {sym}")
        try:
            pdf = letter.pdf_from_zip(s.get_bytes(url_for(sym), source="nsearchives"))
            text, how = letter.extract_text(pdf)
            flat = re.sub(r"\s+", " ", text)
            pathlib.Path("anchor-text").mkdir(exist_ok=True)
            pathlib.Path(f"anchor-text/{sym}-{how}.txt").write_text(text, encoding="utf8")
            print(f"read by {how}: {len(flat)} chars, {len(letter._ROW.findall(flat))} row candidates")
            book = letter.parse_text(text)
            print(f"BELIEVED {len(book['investors'])} rows, ₹{book['amountCr']} Cr, price {book['price']}, "
                  f"date {book['date']}, dropped {book['dropped']}")
            for i in book["investors"][:60]:
                print(f"   {i['pct']:6.2f}%  ₹{i['amountCr']:9.2f} Cr  {i['cat']:18} {i['name'][:70]}")
        except SourceError as e:
            print("REFUSED:", e.detail)
            if "flat" in locals():
                i = flat.lower().find("sr")
                print("   text sample:", flat[max(i, 0):max(i, 0) + 900])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["NSE", "HEROMOTORS", "SONA"]))
