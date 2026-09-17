"""Reservation-clause finder against PDFs generated in the test (PyMuPDF)."""
from __future__ import annotations

import json

import pytest

fitz = pytest.importorskip("pymupdf")

from collector.pdf import clause  # noqa: E402

DEFINITIONS = (
    "DEFINITIONS AND ABBREVIATIONS\n\n"
    "Term Description\n"
    "\"Allotment\" means the allotment of Equity Shares pursuant to the Offer.\n"
    "\"Eligible Shareholders\" means individuals and HUFs who are the public equity shareholders of\n"
    "Reliance Industries Limited, our Promoter, as on the date of the Red Herring Prospectus, excluding\n"
    "persons not eligible under applicable laws.\n"
    "\"Escrow Account\" means the account opened with the Escrow Collection Bank.\n"
)
OFFER = (
    "THE OFFER\n\n"
    "The following table summarises the Offer:\n"
    "Offer of Equity Shares up to 100,000,000 Equity Shares aggregating up to Rs 10,000 million\n"
    "of which:\n"
    "Shareholders Reservation Portion up to 5,000,000 Equity Shares aggregating up to Rs 500 million\n"
    "Net Offer 95,000,000 Equity Shares\n"
    "The Shareholders Reservation Portion shall not exceed 10% of the Offer. Eligible Shareholders bidding in the\n"
    "Shareholders Reservation Portion can also bid in the Net Offer.\n"
)
COVER = "JIO PLATFORMS LIMITED\nDRAFT RED HERRING PROSPECTUS\nDated September 16, 2026\nPlease read Section 26 of the Companies Act.\n"
PLAIN_OFFER = (
    "THE OFFER\n\nOffer of Equity Shares up to 100,000,000 Equity Shares.\nQIB Portion not less than 75% of the Net Offer.\n"
    "Retail Portion not more than 10% of the Net Offer.\nEmployee Reservation Portion up to 200,000 Equity Shares.\n"
)


def _pdf(pages: list[str], toc: list | None = None, filler: int = 0) -> bytes:
    doc = fitz.open()
    for t in pages:
        p = doc.new_page()
        p.insert_text((50, 72), t, fontsize=9)
    for i in range(filler):
        p = doc.new_page()
        p.insert_text((50, 72), f"Filler page {i}. Nothing of interest here, just risk factors prose.", fontsize=9)
    if toc:
        doc.set_toc(toc)
    out = doc.tobytes()
    doc.close()
    return out


def test_clause_found_with_bookmarks():
    pdf = _pdf([COVER, DEFINITIONS, OFFER], toc=[[1, "Cover", 1], [1, "Definitions and Abbreviations", 2],
                                                 [1, "Section II - The Offer", 3]])
    r = clause.find_reservation_clause(pdf)
    assert r["found"] is True
    assert r["pages"] == [2, 3]
    assert r["definition"] and r["definition"].startswith("Eligible Shareholders")
    assert "Reliance Industries Limited" in r["definition"]
    assert "Escrow" not in r["definition"]
    assert r["parent_mentioned"] == "Reliance Industries Limited"
    assert r["excerpt"] and "Shareholders Reservation Portion" in r["excerpt"]
    assert r["excerptPage"] == 3
    assert r["chapters"]["definitions"] == [2, 2] and r["chapters"]["the_offer"] == [3, 3]
    assert r["pageCount"] == 3 and r["scanned"] == 3 and r["capped"] is False


def test_clause_found_without_bookmarks_uses_heading_scan():
    pdf = _pdf([COVER, DEFINITIONS, OFFER])
    r = clause.find_reservation_clause(pdf)
    assert r["found"] and r["excerptPage"] == 3
    assert "the_offer" in r["chapters"] and "definitions" in r["chapters"]


def test_clause_not_found():
    pdf = _pdf([COVER, "DEFINITIONS AND ABBREVIATIONS\n\n\"Allotment\" means the allotment of Equity Shares.\n", PLAIN_OFFER])
    r = clause.find_reservation_clause(pdf)
    assert r == {**r, "found": False, "pages": [], "definition": None, "excerpt": None, "parent_mentioned": None}


def test_page_cap_stops_at_600():
    # clause sits on page 603 -> beyond the cap -> not found, capped flagged
    pdf = _pdf([COVER], filler=601)
    doc = fitz.open(stream=pdf, filetype="pdf")
    p = doc.new_page()
    p.insert_text((50, 72), OFFER, fontsize=9)
    pdf = doc.tobytes()
    doc.close()
    r = clause.find_reservation_clause(pdf)
    assert r["pageCount"] == 603 and r["scanned"] == 600 and r["capped"] is True
    assert r["found"] is False
    # same document with a higher cap finds it, proving the cap was the reason
    r2 = clause.find_reservation_clause(pdf, max_pages=700)
    assert r2["found"] and r2["pages"] == [603]


def test_short_pages_are_skipped():
    pdf = _pdf(["Eligible Shareholders", COVER, OFFER])   # page 1 is under 40 chars -> ignored
    r = clause.find_reservation_clause(pdf)
    assert r["pages"] == [3]


def test_main_prints_json(tmp_path, capsys):
    f = tmp_path / "x.pdf"
    f.write_bytes(_pdf([COVER, DEFINITIONS, OFFER]))
    assert clause.main([str(f)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["found"] is True and out["pages"] == [2, 3]
    g = tmp_path / "notpdf.pdf"
    g.write_bytes(b"hello")
    assert clause.main([str(g)]) == 1
