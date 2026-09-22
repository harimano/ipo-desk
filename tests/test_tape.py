"""tape — one close a day for every listing of this year, from NSE's EOD bhavcopy. Fixture: the real file of 21 Sep 2026, trimmed."""
import datetime as dt
import io
import pathlib
import zipfile
from zoneinfo import ZoneInfo

from collector import assemble, layout, schema
from collector.errors import SourceBlocked, SourceDown
from collector.modules import tape
from collector.result import Result

FX = pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/nsearchives"
IST = ZoneInfo("Asia/Kolkata")
CSV = (FX / "bhavcopy-2026-09-21.csv").read_text()


def zipped(csv_text: str, name="BhavCopy_NSE_CM_0_0_0_20260921_F_0000.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, csv_text)
    return buf.getvalue()


class S:
    """Serves the 21 Sep file for any date in `have`; 404 for other dates; 403 when blocked."""
    def __init__(self, have=("20260921",), blocked=False):
        self.have, self.blocked, self.calls = set(have), blocked, []

    def get_bytes(self, url, *, source, headers=None, expect_pdf=False):
        self.calls.append(url)
        if self.blocked:
            raise SourceBlocked(source, "HTTP 403", url, 403)
        ymd = url.split("_F_0000")[0][-8:]
        if ymd in self.have:
            return zipped(CSV.replace("2026-09-21", f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"))
        raise SourceDown(source, "HTTP 404", url, 404)


def doc():
    return {"mainboard": [{"name": "Glass Wall Systems", "symbol": "GLASSWALL", "status": "Listed", "listing": "2026-09-16"},
                          {"name": "Not Yet", "symbol": "NOTYET", "status": "Closed", "listing": "2026-09-25"}],
            "sme": [{"name": "Vinod Texworld", "symbol": "VINOD", "status": "Listed", "listing": "2026-09-17"}],
            "listedPerf": [{"name": "Sunshine Pictures", "date": "2026-08-25", "sme": False}, {"name": "Some BSE SME", "date": "2026-09-10", "sme": True},
                           {"name": "Old One", "date": "2025-11-01", "sme": False}],
            "investors": {"listingSymbols": {"Sunshine Pictures": {"symbol": "SUNSHINE", "triedOn": "2026-09-22"}, "Some BSE SME": {"symbol": None, "triedOn": "2026-09-22"},
                                             "Old One": {"symbol": "OLDONE", "triedOn": "2026-09-22"}}},
            "priceHistory": {"Glass Wall Systems": [["2026-09-16", 194.0], ["2026-09-21", 301.29]]}}


def run(s, prev=None, when=dt.datetime(2026, 9, 22, 14, 0, tzinfo=IST)):
    return tape.run(s, prev or {}, Result(module="tape", doc=doc()), now=when)


def test_names_are_this_years_listings_with_a_symbol():
    n = tape.this_years_names(doc(), dt.date(2026, 9, 22))
    assert n == {"Glass Wall Systems": "GLASSWALL", "Vinod Texworld": "VINOD", "Sunshine Pictures": "SUNSHINE"}, "no BSE-only, no unlisted, no last year"


def test_todays_file_is_only_tried_after_six_thirty():
    early = dt.datetime(2026, 9, 22, 14, 0, tzinfo=IST)
    late = dt.datetime(2026, 9, 22, 18, 45, tzinfo=IST)
    assert tape.weekdays_back(dt.date(2026, 9, 22), 7, early)[:3] == ["2026-09-21", "2026-09-18", "2026-09-17"], "weekend skipped, today not yet"
    assert tape.weekdays_back(dt.date(2026, 9, 22), 7, late)[0] == "2026-09-22"


def test_one_file_fills_every_listing_and_never_a_date_twice():
    s = S()
    res = run(s)
    assert res.ok and res.source == "nsearchives"
    assert len(s.calls) == tape.FETCH_PER_RUN, "newest first, six missing weekdays tried"
    assert tape.KEEP_DATES > tape.LOOKBACK_DAYS, "a date read once must stay remembered for the whole lookback"
    ph = res.merge["priceHistory"]
    assert ph["Vinod Texworld"] == [["2026-09-21", 80.65]] and ph["Sunshine Pictures"] == [["2026-09-21", 430.1]]
    assert ph["Glass Wall Systems"] == [["2026-09-16", 194.0], ["2026-09-21", 301.29]], "21 Sep already on file: kept, not duplicated"
    t = res.replace["tape"]
    assert t["dates"] == ["2026-09-21"] and t["names"]["Vinod Texworld"] == "VINOD" and t["n"] == 3
    assert "2026-09-18" in t["noFile"] and "2026-09-22" not in t["noFile"], "a past 404 is a holiday; today's is 'not yet'"
    data = schema.empty_data(); data["priceHistory"] = {"Other": [["2026-09-01", 1.0]]}
    assemble.apply(data, res); layout.check_groups()
    assert data["priceHistory"]["Other"] == [["2026-09-01", 1.0]] and data["priceHistory"]["Vinod Texworld"], "merge touches only the names it priced"


def test_steady_state_costs_one_call_and_remembers_holidays():
    prev = {"tape": {"dates": ["2026-09-21"], "noFile": ["2026-09-18", "2026-09-17", "2026-09-16", "2026-09-15", "2026-09-14", "2026-09-11", "2026-09-10", "2026-09-09"] +
                     [d for d in tape.weekdays_back(dt.date(2026, 9, 8), tape.LOOKBACK_DAYS, dt.datetime(2026, 9, 8, 20, 0, tzinfo=IST))], "names": {}}}
    s = S(have=("20260922",))
    res = run(s, prev, when=dt.datetime(2026, 9, 22, 18, 45, tzinfo=IST))
    assert res.ok and len(s.calls) == 1 and s.calls[0].endswith("20260922_F_0000.csv.zip")
    assert res.replace["tape"]["dates"][-1] == "2026-09-22"


def test_a_403_fails_the_module_and_nothing_is_written():
    res = run(S(blocked=True))
    assert not res.ok and res.error["kind"] == "blocked" and not res.replace and not res.merge


def test_no_symbols_is_a_failure_not_an_empty_success():
    res = tape.run(S(), {}, Result(module="tape", doc={"mainboard": [], "sme": [], "listedPerf": []}), now=dt.datetime(2026, 9, 22, 14, 0, tzinfo=IST))
    assert not res.ok
