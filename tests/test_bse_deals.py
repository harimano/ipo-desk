"""BSE deal pages and end-of-day prices — fixtures are real answers (deal pages 4 Nov 2026, bhavcopy 22 Sep 2026)."""
import datetime as dt
import json
import pathlib

import pytest

from collector.errors import SourceChanged, SourceDown
from collector.sources import bse_deals

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/bse"


def test_bulk_and_block_deals_parse_to_the_common_deal_shape():
    """The legacy beta pages of 4 Nov 2026 (fetched 5 Nov from a GitHub runner, scripts/probe_bse.py)."""
    rows = bse_deals.parse_deals((FX / "bulk_deals-2026-11-04.html").read_text(encoding="utf8"), "bulk")
    assert len(rows) == 43 and {"date", "symbol", "security", "client", "side", "qty", "price"} == set(rows[0])
    assert rows[0] == {"date": "2026-11-04", "symbol": "538812", "security": "AANCHALISP", "client": "SAHASTRAA ADVISORS PRIVATE LIMITED",
                       "side": "SELL", "qty": 32486.0, "price": 55.76}
    wiscon = [r for r in rows if r["symbol"] == "545010"]                                  # Wiscon Industries, listed 28 Oct 2026
    assert wiscon and all(r["security"] == "WISCON" for r in wiscon)
    assert {"client": "AMITSG VENTURES FUND", "side": "SELL", "qty": 217200.0, "price": 204.01} == {k: wiscon[-1][k] for k in ("client", "side", "qty", "price")}
    block = bse_deals.parse_deals((FX / "block_deals-2026-11-04.html").read_text(encoding="utf8"), "block")
    assert [(r["symbol"], r["side"], r["price"]) for r in block] == [("513349", "BUY", 140.75), ("513349", "SELL", 140.75)]
    quiet = "<html><table><tr><th>Deal Date</th><th>Security Code</th><th>Security Name</th><th>Client Name</th><th>Deal Type *</th><th>Quantity</th><th>Price **</th></tr></table></html>"
    assert bse_deals.parse_deals(quiet, "bulk") == [], "the header with no rows is a quiet day"
    with pytest.raises(SourceChanged):
        bse_deals.parse_deals("<html><body><table><tr><td>Something else</td></tr></table></body></html>", "bulk")
    with pytest.raises(SourceChanged):
        bse_deals.parse_deals("", "bulk")


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
