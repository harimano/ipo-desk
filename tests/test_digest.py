"""The weekly digest over a fixture week: Mon 26 Oct – Sun 1 Nov 2026, snapshots in tmp_path."""
import datetime as dt
import json

import pytest

from collector.digest import MAX_LINES, build, load_week, main, message

MON = dt.date(2026, 10, 26)
NOW = dt.datetime(2026, 11, 1, 18, 30, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
BAND = lambda n, pos, lo, hi, med: {"n": n, "pos": pos, "lo": lo, "hi": hi, "med": med, "p10": -5, "p90": 20}
EVIDENCE = {
    "minN": 30,
    "edges": {"total": [0, 2, 10, 50, None], "gmp": [None, 0.01, 10, 30, None]},
    "segments": {
        "main": {"window": {"rule": "last 12 months"}, "bands": {"gmp": {"window": [BAND(27, 14.8, 5.9, 32.5, -3.6), BAND(47, 61.7, 47.4, 74.2, 2.5),
                                              BAND(32, 90.6, 75.8, 96.8, 16.7), BAND(25, 100.0, 86.7, 100.0, 39.6)]},
                           "total": {"all": [BAND(52, 36.5, 24.8, 50.1, 0.0), BAND(101, 56.4, 46.7, 65.7, 1.4),
                                             BAND(98, 69.4, 59.7, 77.6, 7.7), BAND(157, 95.5, 91.1, 97.8, 33.1)]}}},
        "sme": {"window": {"rule": "last 12 months"}, "bands": {"gmp": {"window": [BAND(107, 37.4, 28.8, 46.8, 0.0), BAND(63, 46.0, 34.3, 58.2, 0.0),
                                             BAND(29, 89.7, 73.6, 96.4, 19.2), BAND(37, 100.0, 90.6, 100.0, 74.2)]},
                          "total": {"all": [BAND(172, 43.6, 36.4, 51.1, 0.0), BAND(224, 58.0, 51.5, 64.3, 1.9),
                                            BAND(159, 71.7, 64.2, 78.1, 6.8), BAND(434, 90.1, 86.9, 92.6, 50.0)]}}},
    },
}
JIO = {"name": "Reliance Jio", "parent": "Reliance Industries", "ticker": "RELIANCE", "bucket": "approved",
       "stage": "SEBI approved", "quota": True, "recordDate": None, "lapse": "2027-08-28"}


def doc(as_of, **kw):
    d = {"meta": {"asOf": as_of}, "mainboard": [], "sme": [], "quota": [], "expected": [], "quotaLeads": [],
         "listedPerf": [], "calendar": {"events": []}, "integrity": {"checks": []}, "evidence": EVIDENCE}
    d.update(kw)
    return d


def first_doc():
    return doc("2026-10-25T22:20:00+05:30", quota=[JIO], expected=[{"name": "Encube Ethicals", "stage": "DRHP filed"}])


def last_doc():
    return doc(
        "2026-11-01T18:13:00+05:30",
        listedPerf=[
            {"name": "Jio Platforms", "igId": "2306", "date": "2026-10-28", "sme": False, "issue": 1119.0, "gmp": 250.0,
             "listing": 1358.0, "close1": 1417.5, "gmpEve": 248.0, "gmpEveAsOf": "2026-10-27T21:02:00+05:30"},
            {"name": "Shellz India", "igId": "2228", "date": "2026-10-30", "sme": True, "issue": 179.0, "gmp": 7.0,
             "listing": 179.0, "close1": 170.05},                                   # no gmpEve: the listing-morning figure
            {"name": "Tonbo Imaging India", "igId": "2369", "date": "2026-10-23", "sme": False, "issue": 700.0, "gmp": 452.0,
             "listing": 1160.0, "close1": 1133.8},                                  # last week: not in the digest
        ],
        mainboard=[{"name": "BLS Polymers", "status": "Closed", "close": "2026-10-29", "listing": "2026-11-03",
                    "gmpPct": 42.0, "sub": {"total": 241.22}},
                   {"name": "Bombay Coated and Special Steels", "status": "Open", "close": "2026-11-02", "listing": "2026-11-05",
                    "gmpPct": 10.98, "sub": {"total": 2.67}}],
        sme=[{"name": "Wiscon Industries", "status": "Open", "close": "2026-11-02", "listing": "2026-11-05", "gmpPct": 0.0,
              "sub": {"total": 1.27}}],
        calendar={"events": [
            {"date": "2026-11-02", "kind": "open", "name": "Vedant Poly Fabs", "sme": True, "src": "record"},
            {"date": "2026-11-02", "kind": "close", "name": "Bombay Coated and Special Steels", "sme": False, "src": "record"},
            {"date": "2026-11-02", "kind": "refund", "name": "BLS Polymers", "sme": False, "src": "record"},
            {"date": "2026-11-03", "kind": "listing", "name": "BLS Polymers", "sme": False, "src": "record"},
            {"date": "2026-11-03", "kind": "lockin30", "name": "Vans Electroengineerings", "sme": True, "src": "anchors", "amountCr": 4.75},
            {"date": "2026-11-05", "kind": "lockin30", "name": "Nityas Gems & Jewellery", "sme": False, "src": "anchors", "amountCr": 12.0},
            {"date": "2026-11-05", "kind": "lockin30", "name": "Eventions", "sme": True, "src": "anchors"},
            {"date": "2026-11-06", "kind": "record", "name": "Reliance Jio", "parent": "Reliance Industries", "src": "quota"},
            {"date": "2026-11-09", "kind": "open", "name": "Too Far Away", "sme": False, "src": "record"},
        ]},
        quota=[dict(JIO, stage="RHP filed", recordDate="2026-11-06"),
               {"name": "Hero FinCorp", "parent": "Hero MotoCorp", "ticker": "HEROMOTOCO", "bucket": "drhp", "stage": "DRHP filed"}],
        expected=[{"name": "Encube Ethicals", "stage": "DRHP filed",
                   "lastFiling": {"register": "DRHP", "date": "2026-10-28", "title": "Encube Ethicals Limited - DRHP"}},
                  {"name": "GAMP Services", "stage": "DRHP filed 21 Oct 2026"}],
        quotaLeads=[{"parentName": "Bigbloc Construction Limited", "kind": "ipo", "date": "2026-10-26"},
                    {"parentName": "Prestige Estates Projects Limited", "kind": "withdrawn", "date": "2026-09-25"}],
        integrity={"checks": [
            {"area": "offers", "status": "blocked", "note": "kept previous — HTTP 403", "lastOk": None},
            {"area": "gmp", "status": "ok", "note": "fine", "lastOk": "2026-11-01T18:13:00+05:30"},
            {"area": "flows", "status": "ok", "note": "fine", "lastOk": "2026-10-28T18:13:00+05:30"},
            {"area": "run", "status": "ok", "note": "107s"}]},
    )


@pytest.fixture
def week(tmp_path):
    hist = tmp_path / "history"
    hist.mkdir()
    (hist / "2026-10-25.json").write_text(json.dumps(first_doc()), encoding="utf8")
    for d in ("2026-10-26", "2026-10-27", "2026-10-29", "2026-10-30", "2026-10-31"):      # Wednesday 28 Oct missed
        (hist / f"{d}.json").write_text(json.dumps(doc(f"{d}T18:13:00+05:30")), encoding="utf8")
    (tmp_path / "latest.json").write_text(json.dumps(last_doc()), encoding="utf8")
    return tmp_path


def lines_of(**kw):
    first, last = first_doc(), last_doc()
    return [ln.text for ln in build(first, last, MON, snapshots=[MON + dt.timedelta(days=i) for i in (0, 1, 3, 4, 5)], now=NOW, **kw)]


def test_listings_scored_one_line_each_never_pooled():
    t = lines_of()
    assert "LISTED THIS WEEK" in t
    assert "Jio Platforms · GMP said +22% · opened +21%, closed +27%" in t
    assert "Shellz India (SME) · GMP said +4% (listing morning) · opened +0%, closed -5%" in t
    assert not [x for x in t if x.startswith("Tonbo")]


def test_calendar_one_line_a_day_opens_closes_listings_only():
    t = lines_of()
    i = t.index("NEXT WEEK")
    assert t[i + 1] == "Mon 2 · 1 SME opens · Bombay Coated and Special Steels closes"
    assert t[i + 2] == "Tue 3 · BLS Polymers lists"
    assert t[i + 3] == "PIPELINE" or t[i + 3].startswith("OPEN NOW"), "lock-ins, refunds and record dates stay on the planner"
    assert not [x for x in t if "Too Far Away" in x or "Nityas" in x or "Vans" in x]


def test_open_now_mainboard_by_name_sme_counted():
    t = lines_of()
    i = t.index("OPEN NOW")
    assert t[i + 1:i + 4] == ["BLS Polymers · closed, lists 3 Nov · book 241x · GMP +42%",
                              "Bombay Coated and Special Steels · closes 2 Nov · book 2.7x · GMP +11%",
                              "1 SME on the board, 1 with no GMP quote"]


def test_record_states_each_band_once_with_n_and_interval():
    t = lines_of()
    i = t.index("WHAT THE RECORD SAYS · mainboard, last 12 months")
    assert t[i + 1:i + 3] == ["GMP 10–30%: 91% listed up (76–97%, 32 cases), median +17%",      # Jio, Bombay Coated
                              "GMP over 30%: 100% listed up (87–100%, 25 cases, thin), median +40%"]   # BLS
    assert t[i + 3] != "GMP 0–10%: 62% listed up (47–74%, 47 cases), median +2%", "Shellz is SME: never pooled"
    j = t.index("WHAT THE RECORD SAYS · SME, last 12 months")
    assert t[j + 1] == "GMP 0–10%: 46% listed up (34–58%, 63 cases), median +0%"
    assert t.count("GMP 10–30%: 91% listed up (76–97%, 32 cases), median +17%") == 1


def test_record_uses_the_book_band_when_there_is_no_gmp_quote():
    last = last_doc()
    last["mainboard"] = [{"name": "Quiet Issue", "status": "Open", "close": "2026-11-02", "gmpPct": 0.0, "sub": {"total": 1.5}}]
    last["listedPerf"] = []
    t = [ln.text for ln in build(first_doc(), last, MON, now=NOW)]
    assert "Quiet Issue · closes 2 Nov · book 1.5x · no GMP quote" in t
    assert "WHAT THE RECORD SAYS · mainboard, last 12 months (book bands: all years)" in t
    assert "book under 2x: 36% listed up (25–50%, 52 cases), median +0%" in t


def test_pipeline_moves_are_the_diff_of_first_and_last():
    t = lines_of()
    i = t.index("PIPELINE")
    assert t[i + 1:i + 6] == [
        "Reliance Jio (Reliance Industries) · SEBI approved → RHP filed",
        "Reliance Jio (Reliance Industries) · record date 6 Nov",
        "New: Hero FinCorp (Hero MotoCorp) · DRHP filed",
        "Encube Ethicals · DRHP 28 Oct",
        "+2 more on the desk",                      # GAMP Services and the Bigbloc NSE lead: the cap is five lines
    ]
    from collector.digest import pipeline
    full = [ln.text for ln in pipeline(first_doc(), last_doc(), MON, MON + dt.timedelta(days=6))]
    assert full[4:] == ["New: GAMP Services · DRHP filed 21 Oct 2026",
                        "NSE lead 26 Oct: Bigbloc Construction · ipo"]
    assert not [ln for ln in pipeline({}, last_doc(), MON, MON) if ln.text.startswith("New")], "no baseline, no 'new' spam"


def test_health_is_two_lines_for_hari_only():
    t = lines_of()
    i = t.index("DESK HEALTH")
    assert t[i + 1] == "Snapshots 5 of 7 days · offers feed blocked (HTTP 403) · flows stale 4 days"
    assert t[i + 2] == "Wrong number? reports: on /admin (D1 is the Worker's; the collector cannot count them)"
    assert not [x for x in lines_of(personal=False) if "HEALTH" in x or "/admin" in x]


def test_message_three_ways_under_the_cap():
    lines = build(first_doc(), last_doc(), MON, now=NOW)
    m = message(lines)
    assert len(m.text.splitlines()) < MAX_LINES
    assert m.text.startswith("IPO desk · 26 Oct – 1 Nov\n\nLISTED THIS WEEK\n")
    assert m.click == "https://ipodesk.dev/#today"
    assert "[Jio Platforms](https://ipodesk.dev/#sheet/Jio%20Platforms) · GMP said +22%" in m.markdown
    assert "**NEXT WEEK**" in m.markdown and "\n\n" in m.markdown
    assert "[Bombay Coated and Special Steels](https://ipodesk.dev/#board/Bombay%20Coated%20and%20Special%20Steels) closes" in m.markdown
    assert '<a href="https://ipodesk.dev/#board/BLS%20Polymers">BLS Polymers</a> · closed' in m.html
    assert "<b>OPEN NOW</b>" in m.html and "&amp;" not in m.text and "→" in m.html


def test_load_week_picks_the_previous_sunday_and_latest(week):
    first, last, snaps = load_week(week, MON)
    assert first["meta"]["asOf"].startswith("2026-10-25") and last["meta"]["asOf"].startswith("2026-11-01")
    assert [d.day for d in snaps] == [26, 27, 29, 30, 31]
    first, last, snaps = load_week(week, dt.date(2026, 10, 19))      # a past week: its Sunday snapshot is `last`,
    assert first["meta"] == last["meta"] and [d.day for d in snaps] == [25]   # and with no Sunday-before, `first` too
    first, last, snaps = load_week(week, dt.date(2026, 10, 12))      # nothing on file: no diff, latest.json
    assert first is last and snaps == []


def test_cli_dry_run_prints_and_sends_nothing(week, capsys, monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert main(["--data", str(week), "--week", "2026-10-26", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Jio Platforms · GMP said +22%" in out and out.rstrip().endswith("dry run — nothing sent (pass --send)")
    assert main(["--data", str(week), "--week", "2026-10-27"]) == 2
