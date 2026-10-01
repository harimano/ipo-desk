"""Offline tests for the subscription row-patcher: category classifier, NII sub-bucket combining,
NSE ipo-detail -> BSE cumulative demand -> chittorgarh fallback, and the never-all-null rule."""
from __future__ import annotations

import copy
import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector import assemble  # noqa: E402
from collector.errors import SourceBlocked, SourceChanged, SourceDown  # noqa: E402
from collector.modules import subscription  # noqa: E402
from collector.result import Result  # noqa: E402
from collector.sources import bse_issues  # noqa: E402

from test_calendar import TODAY, FakeSession, load, nse_ok, prev_board, text  # noqa: E402

needs_selectolax = pytest.mark.skipif(bse_issues.HTMLParser is None, reason="selectolax not installed")
CHIT_KEY = "chittorgarh.com/report/ipo-subscription-status"


def run(session, prev, today=TODAY) -> Result:
    return subscription.run(session, prev, Result(module="subscription"), today=today)


def bse_html() -> dict:
    return {"CummDemandSchedule.aspx?ID=7973": text("bse", "CummDemandSchedule-7973.html"),
            "CummDemandSchedule.aspx?ID=7980": text("bse", "CummDemandSchedule-7980.html")}


# ---------------------------------------------------------------------------------------------
# classifier
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label,expected", [
    ("Qualified Institutional Buyers(QIBs)", ("qib", None)),
    ("QIB", ("qib", None)),
    ("Non Institutional Investors", ("nii", None)),
    ("NII", ("nii", None)),
    ("Non-Institutional Buyers (NIB)", ("nii", None)),
    ("HNI", ("nii", None)),
    ("Non Institutional Investors - bids above Rs.10 lakh (bNII)", ("nii", "big")),
    ("Non Institutional Investors - Bid amount upto Rs.10 lakh", ("nii", "small")),
    ("bNII (x)", ("nii", "big")),
    ("sNII (x)", ("nii", "small")),
    ("Retail Individual Investors(RIIs)", ("retail", None)),
    ("Individual Investors", ("retail", None)),
    ("Retail (x)", ("retail", None)),
    ("Employee Reservation", ("employee", None)),
    ("Employees", ("employee", None)),
    ("Shareholders", ("shareholder", None)),
    ("Total", ("total", None)),
    ("Total (x)", ("total", None)),
    ("Foreign Institutional Investors(FIIs)", (None, None)),
    ("Close Date", (None, None)),
    ("", (None, None)),
])
def test_classify(label, expected):
    assert subscription.classify(label) == expected


def test_combine_aggregate_nii_wins_over_sub_buckets():
    d = load("nse", "ipo-detail-SONASEL.json")
    from collector.sources import nse_ipo
    detail = nse_ipo.ipo_detail(FakeSession(nse={"detail:SONASEL": d}), "SONASEL", "EQ")
    sub = subscription.combine(detail["bidDetails"])
    assert sub == {"qib": 3.91, "nii": 4.16, "retail": 0.8, "total": 2.39, "employee": 0.45}


def test_combine_nii_sub_buckets_summed_on_shares_not_double_counted():
    """Only bNII/sNII rows: nii = (bid_b + bid_s) / (offered_b + offered_s), counted exactly once."""
    rows = [
        {"category": "Qualified Institutional Buyers", "noOfTime": 0.65, "sharesOffered": 1140000, "sharesBid": 741000},
        {"category": "Non Institutional Investors - bNII (above 10 lakh)", "noOfTime": 2.10, "sharesOffered": 570000, "sharesBid": 1197000},
        {"category": "Non Institutional Investors - sNII (upto 10 lakh)", "noOfTime": 1.50, "sharesOffered": 285000, "sharesBid": 427500},
        {"category": "Individual Investors", "noOfTime": 1.20, "sharesOffered": 2850000, "sharesBid": 3420000},
        {"category": "Total", "noOfTime": 1.19},
    ]
    sub = subscription.combine(rows)
    assert sub["nii"] == round((1197000 + 427500) / (570000 + 285000), 2) == 1.9
    assert sub["nii"] != 2.10 + 1.50, "sub-buckets are not naively added"
    assert sub["qib"] == 0.65 and sub["retail"] == 1.2 and sub["total"] == 1.19


def test_combine_nii_sub_buckets_multiples_only_uses_reservation_weights():
    rows = [{"category": "bNII", "noOfTime": 3.0}, {"category": "sNII", "noOfTime": 1.5}, {"category": "Total", "noOfTime": 2.0}]
    sub = subscription.combine(rows)
    assert sub["nii"] == round(3.0 * 2 / 3 + 1.5 * 1 / 3, 2) == 2.5


def test_combine_all_null_is_not_a_value():
    assert not subscription.has_values(subscription.combine([{"category": "Foreign Institutional", "noOfTime": 1}]))
    assert not subscription.has_values(None)
    assert not subscription.has_values({"qib": None, "nii": None, "retail": None, "total": None, "asOf": "x"})


# ---------------------------------------------------------------------------------------------
# chittorgarh table
# ---------------------------------------------------------------------------------------------
@needs_selectolax
def test_chittorgarh_table_parsed_by_header():
    table = subscription.parse_chittorgarh(text("chittorgarh", "report-21.html"))
    assert set(table) == {"Sona Selection India", "Vidya Wires"}, "'IPO' / 'SME IPO' suffixes stripped"
    sona = table["Sona Selection India"]
    assert sona["qib"] == 3.91 and sona["nii"] == 4.16 and sona["retail"] == 0.8 and sona["total"] == 2.39
    assert sona["employee"] == 0.45
    assert "Tejas Cargo Logistics" not in table, "a row with only '--' has no values and is dropped"


@needs_selectolax
def test_chittorgarh_changed_shape_raises():
    with pytest.raises(SourceChanged):
        subscription.parse_chittorgarh("<html><body><table><tr><th>Name</th><th>Price</th></tr><tr><td>X</td><td>1</td></tr></table></body></html>")


# ---------------------------------------------------------------------------------------------
# module
# ---------------------------------------------------------------------------------------------
def test_candidates_open_and_recently_closed_only():
    prev = prev_board()
    names = [r["name"] for r in subscription.candidates(prev, TODAY)]
    assert names == ["Sona Selection India", "Vidya Wires Limited"]
    # Anlon closed 10 Sep (7 days ago) and listed: excluded. The day after the close still counts (the final print);
    # from then on the book is final and the per-IPO record carries it, so the exchanges are not asked again
    assert "Anlon Healthcare Limited" in [r["name"] for r in subscription.candidates(prev, dt.date(2026, 9, 11))]
    assert "Anlon Healthcare Limited" not in [r["name"] for r in subscription.candidates(prev, dt.date(2026, 9, 12))]


def test_happy_path_nse():
    prev = prev_board()
    before = copy.deepcopy(prev)
    s = FakeSession(nse=nse_ok())
    res = run(s, prev)
    assert res.ok and res.source == "nse", res.error
    assert prev == before
    assert set(res.rows) == {"mainboard", "sme"}
    sona = res.rows["mainboard"]["Sona Selection India"]["sub"]
    assert sona == {"qib": 3.91, "nii": 4.16, "retail": 0.8, "total": 2.39, "employee": 0.45,
                    "asOf": "2026-09-17T15:02:00+05:30", "src": "nse"}
    vidya = res.rows["sme"]["Vidya Wires Limited"]["sub"]
    assert vidya["nii"] == 1.9 and vidya["retail"] == 1.2 and vidya["qib"] == 0.65 and vidya["total"] == 1.19
    assert vidya["asOf"].startswith("20") and "T" in vidya["asOf"]
    assert not any("bse" in c or "chittorgarh" in c for c in s.calls), "primary answered; no fallback calls"
    assert res.notes[0].startswith("2/2 rows patched via nse")


def test_happy_path_applies_to_board_by_name():
    prev = prev_board()
    data = copy.deepcopy(prev)
    res = run(FakeSession(nse=nse_ok()), prev)
    assemble.apply(data, res)
    sona = next(r for r in data["mainboard"] if r["name"] == "Sona Selection India")
    assert sona["sub"]["qib"] == 3.91 and sona["gmp"] == 18, "only sub is patched; the rest of the row is untouched"
    assert [r["name"] for r in data["mainboard"]] == [r["name"] for r in prev["mainboard"]]


@needs_selectolax
def test_nse_blocked_bse_wins():
    prev = prev_board()
    s = FakeSession(nse={"detail:*": SourceBlocked("nse", "HTTP 403", "x", 403)}, html=bse_html())
    res = run(s, prev)
    assert res.ok and res.source == "bse"
    sona = res.rows["mainboard"]["Sona Selection India"]["sub"]
    assert sona["qib"] == 3.91 and sona["nii"] == 4.16 and sona["retail"] == 0.8 and sona["total"] == 2.39
    assert sona["employee"] == 0.45
    vidya = res.rows["sme"]["Vidya Wires Limited"]["sub"]
    assert vidya["nii"] == 1.9, "BSE sub-buckets combined on shares, not double-counted"
    assert sum(1 for c in s.calls if "ipo-detail" in c) == 1, "one 403 stops further NSE calls this run"
    assert "nse blocked" in "; ".join(res.notes)


@needs_selectolax
def test_nse_and_bse_fail_chittorgarh_last_resort():
    prev = prev_board()
    s = FakeSession(nse={"detail:*": SourceDown("nse", "timeout", "x")},
                    html={"CummDemandSchedule.aspx": text("bse", "CummDemandSchedule-empty.html"),
                          CHIT_KEY: text("chittorgarh", "report-21.html")})
    res = run(s, prev)
    assert res.ok and res.source == "chittorgarh"
    assert res.rows["mainboard"]["Sona Selection India"]["sub"]["total"] == 2.39
    assert res.rows["sme"]["Vidya Wires Limited"]["sub"]["nii"] == 1.9
    assert sum(1 for c in s.calls if CHIT_KEY in c) == 1, "chittorgarh fetched once per run"


def test_all_sources_fail_leaves_previous_sub_untouched():
    prev = prev_board()
    data = copy.deepcopy(prev)
    s = FakeSession(nse={"detail:*": SourceBlocked("nse", "HTTP 403", "x", 403)},
                    html={"CummDemandSchedule.aspx": SourceDown("bse", "timeout"), CHIT_KEY: SourceDown("chittorgarh", "timeout")})
    res = run(s, prev)
    assert not res.ok and res.error and not res.rows
    assemble.apply(data, res)
    assert data == prev
    assert data["mainboard"][0]["sub"]["qib"] == 1.2


def test_no_candidates_is_ok_with_note():
    prev = prev_board()
    res = run(FakeSession(), prev, today=dt.date(2026, 10, 30))
    assert res.ok and res.source == "none" and not res.rows
    assert "no open" in res.notes[0]


def test_never_writes_all_null_sub():
    prev = prev_board()
    nulls = {"companyName": "Sona", "issueInfo": {"dataList": [{"title": "Bid Lot", "value": "150"}]},
             "bidDetails": [{"category": "Foreign Institutional Investors", "noOfTime": "1.0"}]}
    s = FakeSession(nse={"detail:*": nulls}, html={CHIT_KEY: SourceDown("chittorgarh", "timeout"),
                                                  "CummDemandSchedule.aspx": SourceDown("bse", "timeout")})
    res = run(s, prev)
    assert not res.ok and not res.rows


def test_partial_success_patches_what_answered_and_flags_the_rest():
    prev = prev_board()
    n = nse_ok()
    n["detail:VIDYAWIRE"] = SourceDown("nse", "timeout", "x")
    s = FakeSession(nse=n, html={CHIT_KEY: SourceDown("chittorgarh", "timeout"), "CummDemandSchedule.aspx": SourceDown("bse", "timeout")})
    res = run(s, prev)
    assert res.ok and "Sona Selection India" in res.rows["mainboard"] and "sme" not in res.rows
    assert res.unresolved and "Vidya Wires Limited" in res.unresolved[0]


def test_row_patcher_only_touches_sub_key():
    res = run(FakeSession(nse=nse_ok()), prev_board())
    for key, patches in res.rows.items():
        for name, fields in patches.items():
            assert set(fields) == {"sub"}
    assert not res.replace and not res.merge


def test_bse_category_demand_json_live_shape():
    """The endpoint bseindia.com's demand page calls, recorded 17 Sep 2026 (NSE's own IPO, day 1)."""
    import json
    import pathlib
    from collector.sources import bse_issues
    from collector.modules.subscription import combine
    live = json.loads((pathlib.Path(__file__).parent.parent / "data/fixtures/live-2026-09-17/bse_CatDem-7977.json").read_text())
    sub = combine(bse_issues.parse_category_demand(live))
    assert sub["qib"] == 0.19 and sub["nii"] == 0.72          # aggregate rows win; 2.1 / 2.2 are not added on top
    assert sub["retail"] is not None and sub["total"] is not None
    with pytest.raises(SourceChanged):
        bse_issues.parse_category_demand({"Table": []})
    with pytest.raises(SourceChanged):
        bse_issues.parse_category_demand({"Table": [{"unexpected": 1}]})


def test_a_blank_exchange_page_never_zeroes_a_book_we_already_have():
    """Live, 18 Sep 2026: after a BSE SME issue closed, BSE answered with zeros and they overwrote 11.87x."""
    import copy
    import json
    import pathlib
    live = json.loads((pathlib.Path(__file__).parent.parent / "data/fixtures/live-2026-09-17/bse_CatDem-7977.json").read_text())
    blank = copy.deepcopy(live)
    for r in blank["Table"][1:]:
        r["col4"], r["col5"] = "0", "0.0000"

    class S:
        def bse_json(self, path, params=None, *, source="bse"):
            return blank

    row = {"name": "Shakti Polytarp", "type": "BSE SME", "status": "Closed", "open": "2026-09-15", "close": "2026-09-17",
           "bseIpoNo": "7967", "sub": {"qib": 49.22, "nii": 5.43, "retail": 4.12, "total": 11.87}}
    res = subscription.run(S(), {"mainboard": [], "sme": [row]}, Result(module="subscription"), today=dt.date(2026, 9, 18))
    assert "Shakti Polytarp" not in (res.rows.get("sme") or {})
    fresh = dict(row, sub=None)
    res = subscription.run(S(), {"mainboard": [], "sme": [fresh]}, Result(module="subscription"), today=dt.date(2026, 9, 18))
    assert (res.rows.get("sme") or {}).get("Shakti Polytarp", {}).get("sub", {}).get("total") == 0.0, "with nothing on file, the exchange's zero stands"


# ---------------------------------------------------------------------------------------------
# Narada: the book for what NSE does not carry (BSE-only SMEs), share- and application-wise
# ---------------------------------------------------------------------------------------------
NARADA = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/narada"


def _narada(sym):
    return (NARADA / f"subscription-{sym}.html").read_text(encoding="utf8")


@needs_selectolax
def test_narada_parses_both_tables_and_nests_sub_rows():
    from collector.sources import narada
    p = narada.parse(_narada("BLACKOPAL"))
    assert narada.book(p) == {"qib": 59.7, "nii": 124.82, "bnii": 145.83, "snii": 82.81, "retail": 60.15, "total": 73.88}
    assert narada.applications(p)["retail"] == {"reserved": 775, "received": 46619}
    fii = next(r for r in p["shares"] if r["label"] == "FII")
    assert fii["parent"] == "qib" and fii["times"] is None, "a sub-row has amounts, no multiple"
    small = narada.parse(_narada("SOLLFEGE"))
    assert narada.book(small) == {"other": 2.22, "retail": 1.59, "total": 1.91}, \
        "a small SME's QIB has no reservation: no multiple invented (InvestorGain printed 1819000x)"
    with pytest.raises(SourceChanged):
        narada.parse("<html><body><p>Page not found</p></body></html>")


@needs_selectolax
def test_nse_zeros_fall_through_to_narada_with_application_counts():
    """1 Oct 2026: NSE's ipo-detail answers zeros for SMEs it does not carry; the zeros must not stop the chain."""
    prev = prev_board()
    vidya = prev["sme"][0]
    vidya["symbol"], vidya["bseIpoNo"] = "BLACKOPAL", None
    zero = {"bidDetails": [{"category": "Total", "noOfTime": "0.00", "noOfSharesOffered": "0.0", "noOfsharesBid": "0.0"}]}
    s = FakeSession(nse={**nse_ok(), "detail:BLACKOPAL": zero},
                    html={"trynarada.com/ipos/BLACKOPAL/subscription/": _narada("BLACKOPAL")})
    res = run(s, prev)
    assert res.ok and "narada" in res.source
    patch = res.rows["sme"]["Vidya Wires Limited"]
    assert patch["sub"]["total"] == 73.88 and patch["sub"]["src"] == "narada"
    assert patch["apps"]["retail"] == {"reserved": 775, "received": 46619}
