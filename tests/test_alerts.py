import copy

from collector.alerts import compose, evaluate


def doc(as_of, **kw):
    d = {"meta": {"asOf": as_of}, "mainboard": [], "sme": [], "quota": [], "anchors": [], "investors": {}}
    d.update(kw)
    return d


HERO = {"name": "Hero Motors", "status": "Open", "open": "2026-09-16", "close": "2026-09-18",
        "bandHigh": 84, "gmpPct": 6.55, "sub": {"total": 3.36}}
JIO = {"name": "Reliance Jio", "parent": "Reliance Industries", "ticker": "RELIANCE", "bucket": "approved",
       "stage": "SEBI approved", "quota": True, "recordDate": None, "lapse": None}


def test_silent_when_nothing_became_true():
    d = doc("2026-09-17T18:15:00+05:30", mainboard=[HERO], quota=[JIO])
    assert evaluate(d, copy.deepcopy(d)) == []
    assert compose([], d, d) is None


def test_same_day_second_run_does_not_repeat_but_next_day_speaks_again():
    morning = doc("2026-09-17T06:45:00+05:30", mainboard=[HERO])
    evening = doc("2026-09-17T18:15:00+05:30", mainboard=[HERO])
    next_day = doc("2026-09-18T06:45:00+05:30", mainboard=[HERO])
    assert evaluate(morning, evening) == []
    lines = [a.line for a in evaluate(evening, next_day)]
    assert lines == ["Hero Motors closes today (₹84, book 3.36x, GMP +6.5%)"] or lines == ["Hero Motors closes today (₹84, book 3.36x, GMP +6.6%)"]


def test_record_date_leads_names_the_parent_and_refires_only_at_milestones():
    q = dict(JIO, recordDate="2026-10-10")
    far = doc("2026-09-09T06:45:00+05:30", quota=[q])          # 31 days: outside the window
    d30 = doc("2026-09-10T06:45:00+05:30", quota=[q], mainboard=[dict(HERO, close="2026-09-11")])
    d29 = doc("2026-09-11T06:45:00+05:30", quota=[q])
    d14 = doc("2026-09-26T06:45:00+05:30", quota=[q])
    first = evaluate(far, d30)
    assert first[0].line == "Hold Reliance Industries (RELIANCE) before 10 Oct — Reliance Jio record date in 30 days"
    assert not [a for a in evaluate(d30, d29) if a.key.startswith("record:")]
    assert [a for a in evaluate(d29, d14) if a.key.startswith("record:")]
    assert evaluate(far, doc("2026-09-10T06:45:00+05:30", quota=[dict(q, quota=False)])) == []


def test_stage_change_new_row_and_lapse():
    prev = doc("2026-09-17T06:45:00+05:30", quota=[JIO])
    new = doc("2026-09-17T18:15:00+05:30", quota=[
        dict(JIO, stage="RHP filed", lapse="2026-09-27"),
        {"name": "Hero FinCorp", "parent": "Hero MotoCorp", "ticker": "HEROMOTOCO", "bucket": "drhp", "stage": "DRHP filed"}])
    lines = [a.line for a in evaluate(prev, new)]
    assert "Reliance Jio (Reliance Industries (RELIANCE)): SEBI approval lapses 27 Sep, in 10 days" in lines
    assert "New quota IPO: Hero FinCorp — Hero MotoCorp (HEROMOTOCO): now DRHP filed" in lines
    assert "Reliance Jio — Reliance Industries (RELIANCE): now RHP filed" in lines
    assert evaluate({}, new) == [a for a in evaluate({}, new) if not a.key.startswith("stage:")], "no baseline, no stage spam"


def test_six_lines_and_refresh_gap():
    rows = [dict(HERO, name=f"Issue {i}") for i in range(9)]
    prev = doc("2026-09-15T06:45:00+05:30")
    new = doc("2026-09-17T06:45:00+05:30", mainboard=rows)
    text = compose(evaluate(prev, new), prev, new)
    assert len(text.splitlines()) == 6 and text.splitlines()[-1] == "+4 more on the desk"
    assert text.startswith("⚠ Refresh gap (48h) · ")


def test_tracked_investor_bulk_deal_is_new_once():
    deal = {"date": "2026-09-17", "investor": "Ashish Kacholia", "stock": "Rentomojo", "side": "BUY", "valueCr": 12.4}
    prev = doc("2026-09-17T06:45:00+05:30")
    new = doc("2026-09-17T18:15:00+05:30", investors={"bulkDeals": [deal]})
    assert [a.line for a in evaluate(prev, new)] == ["Ashish Kacholia bought Rentomojo ₹12.4 Cr (2026-09-17)"]
    assert evaluate(new, new) == []
