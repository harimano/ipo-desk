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


def test_book_crossing_speaks_once_per_mark_and_only_the_highest():
    row = dict(HERO, close="2026-09-21")
    at = lambda hhmm, total: doc(f"2026-09-17T{hhmm}:00+05:30", mainboard=[dict(row, sub={"total": total})])
    subs = lambda a, b: [x.line for x in evaluate(a, b) if x.key.startswith("sub:")]
    assert subs(at("10:00", 0.4), at("10:30", 0.9)) == []
    assert subs(at("10:30", 0.9), at("11:00", 1.2)) == ["Hero Motors book crossed 1x — now 1.2x, closes 21 Sep"]
    assert subs(at("11:00", 1.2), at("11:30", 3.0)) == []
    assert subs(at("11:30", 3.0), at("12:00", 61)) == ["Hero Motors book crossed 50x — now 61x, closes 21 Sep"]
    assert subs(at("12:00", 61), at("12:30", 45)) == [], "a dip below a mark already announced stays quiet"


def test_anchor_lock_in_speaks_once_the_day_before_for_mainboard_names():
    a = [{"name": "Hero Motors", "lockIn30": "2026-10-21", "lockIn90": "2026-12-20", "amountCr": 300.0},
         {"name": "Some SME", "lockIn30": "2026-10-21"}]
    rec = [{"name": "Hero Motors", "type": "Mainboard"}, {"name": "Some SME", "type": "NSE SME"}]
    at = lambda day: doc(f"2026-10-{day}T06:45:00+05:30", anchors=a, recent=rec)
    assert evaluate(at(18), at(19)) == []
    assert [x.line for x in evaluate(at(19), at(20))] == ["Hero Motors: lock-in on half the anchor book ends tomorrow (₹300 Cr book)"]
    assert evaluate(at(20), at(21)) == [], "said once: the day itself does not repeat it"
    assert [x.line for x in evaluate(at(18), at(21))] == ["Hero Motors: lock-in on half the anchor book ends today (₹300 Cr book)"]


def test_a_strong_record_anchor_in_an_unlisted_book_speaks_once_with_its_n_and_range():
    rec = {"key": "EDELWEISS RECENTLY LISTED IPO FUND", "name": "EDELWEISS RECENTLY LISTED IPO FUND", "n": 11,
           "main": {"n": 11, "pos": 81.8, "lo": 52.3, "hi": 94.9, "med": 19.4}, "sme": None}
    weak = {"key": "SMALL FUND", "name": "SMALL FUND", "n": 3, "main": {"n": 3, "pos": 100.0, "lo": 43.8, "hi": 100.0, "med": 5.0}, "sme": None}
    kw = {"mainboard": [{"name": "NSE", "igId": "2305", "status": "Closed", "open": "2026-09-17", "close": "2026-09-21", "listing": "2026-09-24"},
                         {"name": "Old Co", "igId": "1", "status": "Listed", "listing": "2026-09-10"}],
              "anchors": [{"name": "NSE", "investors": [{"name": "Edelweiss Recently Listed IPO Fund"}, {"name": "Small Fund"}]},
                       {"name": "Old Co", "investors": [{"name": "Edelweiss Recently Listed IPO Fund"}]}],
              "players": {"books": {"2305": [{"name": "SMALL FUND"}]}},
              "trackRecords": {"rows": [rec, weak]}}
    prev = doc("2026-09-21T18:15:00+05:30", **{**kw, "trackRecords": {"rows": []}})
    new = doc("2026-09-22T06:45:00+05:30", **kw)
    out = evaluate(prev, new)
    lines = [a.line for a in out if a.key.startswith("rec:")]
    assert lines == ["EDELWEISS RECENTLY LISTED IPO FUND is in the NSE book — 11 mainboard IPOs anchored, 82% listed up (52–95%), median +19.4%"], "3 IPOs is not a record; a listed issue is not a book"
    again = doc("2026-09-22T18:15:00+05:30", **kw)
    assert not [a for a in evaluate(new, again) if a.key.startswith("rec:")], "spoken once"


# ---- links: every line lands the reader on the right card (collector.alerts.link ↔ site/src/links.js) ----
from collector import notify
from collector.alerts import Alert, link, message


def test_every_alert_carries_a_deep_link_to_its_card():
    prev = doc("2026-09-15T06:45:00+05:30", quota=[JIO])
    new = doc("2026-09-17T06:45:00+05:30",
              mainboard=[dict(HERO, name="M&K Sons")],
              quota=[dict(JIO, stage="RHP filed", recordDate="2026-10-10")],
              investors={"bulkDeals": [{"date": "2026-09-17", "investor": "Ashish Kacholia", "stock": "Rentomojo", "side": "BUY"}]})
    by = {a.key.split(":")[0]: a.url for a in evaluate(prev, new)}
    assert by["close"] == "https://ipodesk.dev/#board/M%26K%20Sons", "encoded with quote(): & and space survive the hash"
    assert by["record"] == by["stage"] == "https://ipodesk.dev/#pipe/Reliance%20Jio"
    assert by["deal"] == "https://ipodesk.dev/#market"
    assert all(a.url for a in evaluate(prev, new)), "no line without a landing place"
    assert link("today") == "https://ipodesk.dev/#today"


def test_message_puts_the_first_link_on_click_and_one_link_per_line():
    rows = [dict(HERO, name=f"Issue {i}") for i in range(9)]
    prev = doc("2026-09-17T06:45:00+05:30")
    new = doc("2026-09-17T18:15:00+05:30", mainboard=rows)
    alerts = evaluate(prev, new)
    m = message(alerts, prev, new)
    assert m.text == compose(alerts, prev, new)
    assert m.click == alerts[0].url == "https://ipodesk.dev/#board/Issue%200"
    md, html = m.markdown.split("\n\n"), m.html.split("\n")
    assert len(md) == len(html) == 6 and md[-1] == "[+4 more on the desk](https://ipodesk.dev/#today)"
    assert md[0].startswith("[Issue 0 closes tomorrow (₹84, book 3.36x, GMP +6.") and md[0].endswith(")](https://ipodesk.dev/#board/Issue%200)")
    assert html[0].startswith('<a href="https://ipodesk.dev/#board/Issue%200">Issue 0 closes tomorrow') and html[-1].endswith("+4 more on the desk</a>")
    assert message([], prev, new) is None


def test_markdown_and_html_escape_what_the_line_contains():
    a = [Alert("k", 1, "A <b> & [x]_y*z", "https://ipodesk.dev/#board/A%20%3Cb%3E")]
    m = message(a, {}, {"meta": {"asOf": "2026-09-17T18:15:00+05:30"}})
    assert m.markdown == "[A <b> & \\[x\\]\\_y\\*z](https://ipodesk.dev/#board/A%20%3Cb%3E)"
    assert m.html == '<a href="https://ipodesk.dev/#board/A%20%3Cb%3E">A &lt;b&gt; &amp; [x]_y*z</a>'


def test_notify_sends_click_and_markdown_headers_and_the_html_body(monkeypatch):
    calls = []

    class R:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(notify.httpx, "post", lambda url, **kw: calls.append((url, kw)) or R())
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    out = notify.send("plain <x>", html='<a href="https://ipodesk.dev/#today">plain &lt;x&gt;</a>', markdown="[plain <x>](https://ipodesk.dev/#today)",
                      click="https://ipodesk.dev/#today")
    assert out == {"telegram": True, "ntfy": True}
    tg = next(kw for url, kw in calls if "telegram" in url)
    assert tg["json"]["text"] == '<a href="https://ipodesk.dev/#today">plain &lt;x&gt;</a>' and tg["json"]["parse_mode"] == "HTML"
    nt = next(kw for url, kw in calls if url.endswith("/t"))
    assert nt["headers"]["Click"] == "https://ipodesk.dev/#today" and nt["headers"]["Markdown"] == "yes"
    assert nt["content"] == b"[plain <x>](https://ipodesk.dev/#today)"
    calls.clear()
    notify.send("plain <x>")                         # the old shape still works: escaped text, no Click, no Markdown
    assert next(kw for url, kw in calls if "telegram" in url)["json"]["text"] == "plain &lt;x&gt;"
    assert "Click" not in next(kw for url, kw in calls if url.endswith("/t"))["headers"]
