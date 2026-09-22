"""BSE deal files and end-of-day prices — fixtures are the real answers of 22 Sep 2026, trimmed."""
import datetime as dt
import json
import pathlib

import pytest

from collector.errors import SourceChanged, SourceDown
from collector.sources import bse_deals

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/bse"


def test_bulk_and_block_deals_parse_to_the_common_deal_shape():
    rows = bse_deals.parse_deals(json.loads((FX / "bulk-deals-2026-09-22.json").read_text()), "bulk")
    adon = [r for r in rows if r["symbol"] == "544809"]
    assert len(adon) == 3 and adon[0]["date"] == "2026-09-22" and adon[0]["side"] in ("BUY", "SELL") and adon[0]["qty"] and adon[0]["price"]
    assert {"date", "symbol", "security", "client", "side", "qty", "price"} == set(rows[0])
    block = bse_deals.parse_deals(json.loads((FX / "block-deals-2026-09-22.json").read_text()), "block")
    assert block and all(r["side"] in ("BUY", "SELL") for r in block)
    assert bse_deals.parse_deals({"Table": []}, "bulk") == [], "an empty Table is a quiet day"
    with pytest.raises(SourceChanged):
        bse_deals.parse_deals({"Table": [{"x": 1}]}, "bulk")
    with pytest.raises(SourceChanged):
        bse_deals.parse_deals("<html>", "bulk")


def test_bse_bhavcopy_is_keyed_by_scrip_code_and_html_means_no_file():
    text = (FX / "bhavcopy-2026-09-22.csv").read_text()
    day = bse_deals.parse_bhavcopy(text, "u", dt.date(2026, 9, 22))
    assert day["544931"]["close"] == 323.95 and day["544931"]["series"] == "MT" and day["544931"]["symbol"] == "VAMAWOVEN"
    assert day["500209"]["symbol"] == "INFY"
    with pytest.raises(SourceDown) as e:
        bse_deals.parse_bhavcopy("<!DOCTYPE html><html>", "u", dt.date(2026, 9, 19))
    assert e.value.status == 404


def test_report_377_carries_the_bse_code():
    from collector.sources import investorgain as ig
    rows = ig.parse_performance_report(json.loads((FX.parent / "investorgain/report-377-gmp-performance-2026-09-22.json").read_text()))
    assert next(r for r in rows if r["name"] == "Vama Wovenfab")["bseCode"] == "544931"
