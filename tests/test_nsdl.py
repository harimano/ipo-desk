"""Offline tests for collector.sources.nsdl against NSDL's real replies of 18 Nov 2026 (whole pages, untrimmed)."""
from __future__ import annotations

import pytest
from _support import fixture

from collector.errors import SourceChanged
from collector.sources import nsdl

YEARS = fixture("nsdl", "yearwise-fy-2026-11-18.html")
MONTHS = fixture("nsdl", "yearwise-cy-2026-11-18.html")
DAYS = fixture("nsdl", "monthly-2026-11-18.html")


def test_parse_years_reads_equity_by_financial_year():
    out = nsdl.parse_years(YEARS)
    years = dict(out["years"])
    assert out["asOf"] == "2026-11-18"
    assert out["years"][0][0] == "1992-93" and out["years"][-1] == ["2026-27", -57796.0]
    assert years["2020-21"] == 274032.0 and years["2025-26"] == -180832.0
    assert len(out["years"]) == 35 and [y for y, _ in out["years"]] == sorted(years)


def test_parse_months_reads_the_calendar_year_and_checks_it_against_the_total():
    out = nsdl.parse_months(MONTHS)
    assert out["year"] == 2026 and out["asOf"] == "2026-11-18" and out["total"] == -188916.0
    assert out["months"][0] == ["2026-01", -35962.0] and out["months"][-1] == ["2026-11", 106229.0]
    assert len(out["months"]) == 11 and sum(v for _, v in out["months"]) == out["total"]


def test_parse_months_refuses_months_that_do_not_add_up():
    with pytest.raises(SourceChanged, match="sum to"):
        nsdl.parse_months(MONTHS.replace(">106229<", ">6229<"))


def test_parse_days_pairs_the_exchange_row_with_the_primary_market_row():
    days = nsdl.parse_days(DAYS)
    by = {d["date"]: d for d in days}
    assert len(days) == 12 and days[0]["date"] == "2026-11-02" and days[-1]["date"] == "2026-11-18"
    assert by["2026-11-18"] == {"date": "2026-11-18", "buy": 21092.53, "sell": 15177.67, "net": 5914.86, "primary": 5350.82}
    assert by["2026-11-05"]["primary"] == -30.78          # printed as (30.78)
    assert round(sum(d["primary"] for d in days), 2) == 5863.52


@pytest.mark.parametrize("parse", [nsdl.parse_years, nsdl.parse_months, nsdl.parse_days])
@pytest.mark.parametrize("bad", ["", "<html><body>Service unavailable</body></html>",
                                 "<table><tr><td>Equity</td><td>Debt</td></tr></table>"])
def test_an_empty_or_reshaped_page_is_source_changed(parse, bad):
    with pytest.raises(SourceChanged):
        parse(bad)


def test_num_reads_commas_and_brackets():
    assert nsdl._num("5,350.82") == 5350.82 and nsdl._num("(371.45)") == -371.45 and nsdl._num("-35962") == -35962.0
    assert nsdl._num("Rs.93.5703") is None and nsdl._num("") is None
