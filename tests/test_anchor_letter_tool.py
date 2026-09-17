import pathlib

import pytest

from collector.errors import SourceChanged
from collector.pdf import anchor as letter        # a bench tool for the research layer; no workflow calls it

ROOT = pathlib.Path(__file__).resolve().parent.parent
SONA = (ROOT / "data/fixtures/anchor/SONA-letter-text.txt").read_text()


def test_real_letter_text_every_row_adds_up():
    book = letter.parse_text(SONA)
    assert book["date"] == "2026-09-16" and book["price"] == 99 and book["totalShares"] == 4290000
    assert [(i["name"], i["shares"], i["amountCr"]) for i in book["investors"]] == [
        ("ASTORNE CAPITAL VCC - ARVEN", 2296350, 22.73), ("INDIA MAX INVESTMENT FUND LIMITED", 996900, 9.87),
        ("LORDS MULTIGROWTH FUND", 996750, 9.87)]
    assert book["dropped"] == 0 and abs(sum(i["pct"] for i in book["investors"]) - 100) < 0.01


def test_a_misread_digit_is_dropped_and_a_partial_book_is_refused():
    one_bad = SONA.replace("9,96,750", "9,98,750")            # OCR-style slip: shares x price no longer equals the amount
    with pytest.raises(SourceChanged) as e:
        letter.parse_text(one_bad)                            # 77% coverage: refuse rather than publish a partial book
    assert "refusing a partial book" in str(e.value)
    with pytest.raises(SourceChanged):
        letter.parse_text("x" * 50)
    with pytest.raises(SourceChanged):
        letter.parse_text("Dear Sir, " * 60)


def test_categories():
    c = letter.category
    assert c("SBI Mutual Fund - SBI Small Cap Fund") == "MF" and c("ICICI Prudential Life Insurance Company") == "Insurance"
    assert c("Government of Singapore") == "Pension/Sovereign" and c("Nomura Singapore Limited ODI") == "FPI"
    assert c("WhiteOak Capital Equity Fund") == "AIF" and c("Motilal Oswal Finvest Ltd") == "Other"


def test_real_scanned_letters_ocr_text():
    """OCR text of two real scans (Tesseract on a GitHub runner, 17 Sep 2026)."""
    hero = letter.parse_text((ROOT / "data/fixtures/anchor/HEROMOTORS-letter-ocr.txt").read_text())
    assert hero["partial"] is False and hero["coverage"] >= 0.90 and hero["price"] == 84 and hero["totalShares"] == 35714284
    assert hero["stated"] == {"mf": {"pct": 81.66, "count": 7}, "insurancePension": {"pct": 6.67, "count": 2}}
    assert all(abs(i["shares"] * 84 - i["amountCr"] * 1e7) < 1e5 for i in hero["investors"])

    nse = letter.parse_text((ROOT / "data/fixtures/anchor/NSE-letter-ocr.txt").read_text())
    assert nse["partial"] is True and 0.5 <= nse["coverage"] < 0.9
    assert nse["amountCr"] == round(37793739 * 1785 / 1e7, 2), "a partial book carries the issuer's total, not our sum"
    assert nse["stated"]["mf"] == {"pct": 36.98, "count": 29} and nse["stated"]["insurancePension"]["pct"] == 16.04
