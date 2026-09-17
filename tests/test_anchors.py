import datetime as dt
import io
import pathlib
import zipfile

import pytest

from collector.errors import SourceChanged, SourceDown
from collector.modules import anchors
from collector.pdf import anchor as letter
from collector.result import Result

ROOT = pathlib.Path(__file__).resolve().parent.parent
SONA = (ROOT / "data/fixtures/anchor/SONA-letter-text.txt").read_text()
TODAY = dt.date(2026, 9, 17)


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


class FakeSession:
    def __init__(self, by_symbol):
        self.by, self.calls = by_symbol, []

    def get_bytes(self, url, *, source=None, **kw):
        sym = url.rsplit("ANCHOR_", 1)[1].split(".")[0]
        self.calls.append(sym)
        v = self.by.get(sym)
        if isinstance(v, Exception):
            raise v
        return v


def _zip(pdf_bytes=b"%PDF-fake"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ANCHOR_X/letter.pdf", pdf_bytes)
    return buf.getvalue()


def prev():
    return {"mainboard": [{"name": "Sonaselection India", "symbol": "SONA", "open": "2026-09-17", "type": "Mainboard", "issueSizeCr": 99.1},
                          {"name": "Later Co", "symbol": "LATER", "open": "2026-09-18", "type": "Mainboard"},
                          {"name": "Old Co", "symbol": "OLD", "open": "2026-08-01", "type": "Mainboard"},
                          {"name": "Done Co", "symbol": "DONE", "open": "2026-09-16", "type": "Mainboard"}],
            "sme": [],
            "anchors": [{"name": "Sonaselection India", "anchor": "hand-written", "investors": []},
                        {"name": "Done Co", "source": "nse-anchor-letter", "investors": [{"name": "x"}]},
                        {"name": "Deepa Jewellers", "anchor": "hand-written, long listed", "investors": [{"name": "y"}]}]}


def test_module_reads_once_replaces_handwriting_and_waits_quietly(monkeypatch):
    monkeypatch.setattr(letter, "extract_text", lambda pdf, **kw: (SONA, "text"))
    s = FakeSession({"SONA": _zip(), "LATER": SourceDown("nsearchives", "HTTP 404", "u", 404)})
    res = anchors.run(s, prev(), Result(module="anchors"), today=TODAY)
    assert res.ok and sorted(s.calls) == ["LATER", "SONA"], "Old Co is outside the window, Done Co already has its letter"
    rows = {r["name"]: r for r in res.replace["anchors"]}
    sona = rows["Sonaselection India"]
    assert sona["source"] == "nse-anchor-letter" and sona["count"] == 3 and sona["amountCr"] == 42.47
    assert sona["topTierShare"] == 0 and sona["issueSizeCr"] == 99.1 and sona["sources"][0].endswith("ANCHOR_SONA.zip")
    assert abs(sum(i["pct"] for i in sona["investors"]) - 100) < 0.05
    assert rows["Deepa Jewellers"]["anchor"].startswith("hand-written") and rows["Done Co"]["investors"] == [{"name": "x"}]
    assert any("not published yet" in n for n in res.notes) and not res.unresolved


def test_module_fails_only_when_every_letter_it_tried_failed(monkeypatch):
    def scan(pdf, **kw):
        raise SourceChanged("anchor-letter", "letter is a scan and tesseract is not installed")
    monkeypatch.setattr(letter, "extract_text", scan)
    res = anchors.run(FakeSession({"SONA": _zip(), "LATER": _zip()}), prev(), Result(module="anchors"), today=TODAY)
    assert not res.ok and res.replace == {} and res.unresolved
    nothing = {"mainboard": [], "sme": [], "anchors": []}
    assert anchors.run(FakeSession({}), nothing, Result(module="anchors"), today=TODAY).ok
