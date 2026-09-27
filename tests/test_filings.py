"""filings module: BSE announcements + SEBI registers -> quota row patches. Offline, fixture-driven."""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from collector import assemble, schema
from collector.errors import SourceChanged, SourceDown
from collector.modules import filings
from collector.result import Result
from collector.sources import bse_ann, sebi

FIX = pathlib.Path(__file__).resolve().parent.parent / "data" / "fixtures"
TODAY = dt.date(2026, 9, 17)


def _bse(name: str):
    return json.loads((FIX / "bse_ann" / name).read_text(encoding="utf8"))


def _sebi(name: str) -> str:
    return (FIX / "sebi" / name).read_text(encoding="utf8")


class FakeSession:
    """Same method names as collector.http.Session; answers from fixtures keyed by scrip / register."""

    def __init__(self, bse: dict | None = None, sebi_post: dict | None = None, sebi_get: dict | None = None,
                 detail: str | None = None, bse_exc: Exception | None = None,
                 nse: dict | None = None, equity_csv: str | None = None):
        self.bse = bse or {}
        self.sebi_post = sebi_post or {}
        self.sebi_get = sebi_get or {}
        self.detail = detail
        self.bse_exc = bse_exc
        self.nse = nse or {}               # index -> payload | Exception; absent -> down
        self.equity_csv = equity_csv
        self.calls: list[tuple] = []

    def bse_json(self, path, params=None, *, source="bse"):
        self.calls.append(("bse", path, dict(params or {})))
        if self.bse_exc:
            raise self.bse_exc
        key = (str(params["strscrip"]), int(params.get("pageno", 1)))
        if key in self.bse:
            return self.bse[key]
        if (str(params["strscrip"]), None) in self.bse:
            return self.bse[(str(params["strscrip"]), None)]
        return _bse("empty.json")

    def post_text(self, url, data, *, source, headers=None):
        self.calls.append(("post", url, dict(data)))
        smid = data.get("smid")
        if smid in self.sebi_post:
            v = self.sebi_post[smid]
            if isinstance(v, Exception):
                raise v
            return v
        raise SourceDown(source, "ajax unavailable", url)

    def get_text(self, url, *, source, headers=None, params=None):
        self.calls.append(("get", url, dict(params or {})))
        if url.endswith("EQUITY_L.csv"):
            if self.equity_csv is None:
                raise SourceDown(source, "no equity list", url)
            return self.equity_csv
        if url.endswith("SME_EQUITY_L.csv"):
            raise SourceDown(source, "no SME list", url)
        if "/filings/" in url:
            if self.detail is None:
                raise SourceDown(source, "no detail", url)
            return self.detail
        smid = (params or {}).get("smid")
        if smid in self.sebi_get:
            return self.sebi_get[smid]
        raise SourceDown(source, "listing unavailable", url)

    def nse_json(self, path, params=None, *, source="nse", referer=None):
        self.calls.append(("nse", path, dict(params or {})))
        v = self.nse.get((params or {}).get("index"))
        if v is None:
            raise SourceDown(source, "nse down", path)
        if isinstance(v, Exception):
            raise v
        return v

    # unused by this module, present so the fake has the full surface

    def get_json(self, *a, **k):
        raise AssertionError("unexpected get_json")

    def get_bytes(self, *a, **k):
        raise AssertionError("unexpected get_bytes")


def _prev() -> dict:
    d = schema.empty_data()
    d["quota"] = [
        {"name": "Jio Platforms", "parent": "Reliance", "parentFull": "Reliance Industries Limited", "ticker": "RELIANCE",
         "bucket": "awaited", "stage": "DRHP awaited", "rank": 3, "stageDate": "2026-06-01", "detail": "",
         "sizeCr": None, "quota": None, "quotaPct": None, "recordDate": None, "listingDate": None,
         "confidence": "medium", "sources": ["https://example.test/jio"], "isNew": False},
        {"name": "Hero FinCorp", "parent": "Hero MotoCorp", "parentFull": "Hero MotoCorp Limited", "ticker": "HEROMOTOCO",
         "bucket": "drhp", "stage": "DRHP filed", "rank": 2, "stageDate": "2026-08-01", "detail": "",
         "quota": True, "quotaPct": 10, "confidence": "high", "sources": [], "isNew": False},
        {"name": "Coal India Subsidiary", "parent": "Coal India", "parentFull": "Coal India Limited", "ticker": "COALINDIA",
         "bucket": "awaited", "stage": "Board approval", "rank": 4, "stageDate": "2026-05-20", "detail": "",
         "quota": None, "quotaPct": None, "confidence": "low", "sources": [], "isNew": False},
        {"name": "Nuvama Legacy", "parent": "Edelweiss", "parentFull": "Edelweiss Financial Services Limited",
         "ticker": "EDELWEISS", "bucket": "approved", "stage": "Listed", "rank": 1, "stageDate": "2026-01-02",
         "listingDate": "2026-01-05", "quota": True, "quotaPct": 5, "confidence": "high", "sources": [], "isNew": False},
    ]
    return d


def _run(session, prev=None, today=TODAY, monkeypatch=None):
    prev = prev or _prev()
    if monkeypatch is not None:
        monkeypatch.setattr(filings, "_today", lambda: today)
    res = Result(module="filings")
    return filings.run(session, prev, res), prev


# ------------------------------------------------------------------------------------------
# headline classification
# ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("headline,stage,bucket", [
    ("Intimation of filing of Draft Red Herring Prospectus by Jio Platforms Limited, a subsidiary", "DRHP filed", "drhp"),
    ("Filing of DRHP with SEBI by subsidiary", "DRHP filed", "drhp"),
    ("Receipt of SEBI observation letter on the DRHP of Hero FinCorp Limited", "SEBI observations received", "approved"),
    ("Filing of Red Herring Prospectus by Hero FinCorp Limited", "RHP filed", "approved"),
    ("Hero FinCorp Limited - RHP", "RHP filed", "approved"),
    ("Filing of Updated Draft Red Herring Prospectus (UDRHP-I)", "UDRHP filed", "drhp"),
])
def test_headline_classification(headline, stage, bucket):
    c = filings.classify_headline(headline)
    assert c and c["stage"] == stage and c["bucket"] == bucket


def test_headline_generic_ipo_mention_flags_only():
    c = filings.classify_headline("Update on proposed initial public offer of subsidiary")
    assert c and c["kind"] == "generic" and c["stage"] is None


@pytest.mark.parametrize("headline", [
    "Announcement under Regulation 30 (LODR)-Newspaper Publication",
    "Board Meeting Intimation",
    "Outcome of Board Meeting - Dividend",
])
def test_headline_no_match(headline):
    assert filings.classify_headline(headline) is None
    assert not filings.HEADLINE_RE.search(headline)


def test_fixture_has_one_match_and_one_miss():
    rows, cnt = bse_ann.parse_page(_bse("reliance_500325.json"))
    assert cnt == 2 and len(rows) == 2
    hits = [r for r in rows if filings.HEADLINE_RE.search(r["headline"])]
    assert len(hits) == 1 and "Draft Red Herring" in hits[0]["headline"]
    assert hits[0]["url"] == "https://www.bseindia.com/xml-data/corpfiling/AttachLive/9d1f2c3a-1111-4a5b-9c1d-aaaa00000001.pdf"
    assert hits[0]["date"] == "2026-09-16"
    assert hits[0]["category"] == "Company Update"


# ------------------------------------------------------------------------------------------
# bse_ann source
# ------------------------------------------------------------------------------------------
def test_bse_changed_shape_raises():
    with pytest.raises(SourceChanged):
        bse_ann.parse_page(_bse("changed.json"))


def test_bse_pagination_follows_rowcnt():
    s = FakeSession(bse={("500182", 1): _bse("paged_p1.json"), ("500182", 2): _bse("paged_p2.json")})
    rows = bse_ann.fetch(s, "500182", TODAY - dt.timedelta(days=3), TODAY)
    assert [r["newsId"] for r in rows] == ["p1-0001", "p2-0001"]
    pages = [c[2]["pageno"] for c in s.calls if c[0] == "bse"]
    assert pages == [1, 2]
    p = s.calls[0][2]
    assert p["strCat"] == "-1" and p["strSearch"] == "P" and p["strType"] == "C"
    assert p["strPrevDate"] == "20260914" and p["strToDate"] == "20260917"


def test_bse_empty_window_is_not_an_error():
    rows, cnt = bse_ann.parse_page(_bse("empty.json"))
    assert rows == [] and cnt == 0


# ------------------------------------------------------------------------------------------
# sebi source
# ------------------------------------------------------------------------------------------
def test_sebi_listing_parse_and_classify():
    rows = sebi.parse_listing(_sebi("drhp_page1.html"))
    assert [r["kind"] for r in rows] == ["DRHP", "DRHP", "Addendum", None]
    assert rows[0]["date"] == "2026-09-16"
    assert rows[0]["detailUrl"].startswith("https://www.sebi.gov.in/filings/public-issues/")
    assert rows[0]["title"] == "Jio Platforms Limited - DRHP"
    rhp = sebi.parse_listing(_sebi("rhp_page1.html"))
    assert [r["kind"] for r in rhp] == ["RHP", "RHP"]


def test_sebi_changed_shape_raises():
    with pytest.raises(SourceChanged):
        sebi.parse_listing(_sebi("changed.html"))


def test_sebi_falls_back_to_get_listing():
    s = FakeSession(sebi_post={"10": _sebi("changed.html")}, sebi_get={"10": _sebi("drhp_page1.html")})
    rows = sebi.fetch_listing(s, "DRHP")
    assert len(rows) == 4
    kinds = [c[0] for c in s.calls]
    assert kinds == ["post", "get"]
    assert s.calls[0][2]["sid"] == "3" and s.calls[0][2]["ssid"] == "15" and s.calls[0][2]["smid"] == "10"
    assert s.calls[1][2] == {"doListing": "yes", "sid": "3", "ssid": "15", "smid": "10"}


def test_sebi_resolve_pdf_prefers_full_document():
    s = FakeSession(detail=_sebi("detail.html"))
    assert sebi.resolve_pdf(s, "https://www.sebi.gov.in/filings/public-issues/sep-2026/x_1.html") == \
        "https://www.sebi.gov.in/sebi_data/attachdocs/sep-2026/1789012955772.pdf"
    # abridged only: still returns something, but the abridged one
    assert "commondocs" in sebi.pick_pdf(_sebi("detail_abridged_only.html"))
    assert sebi.pick_pdf("<html>no links</html>") is None


# ------------------------------------------------------------------------------------------
# module: transitions
# ------------------------------------------------------------------------------------------
def test_bse_drhp_announcement_advances_row(monkeypatch):
    s = FakeSession(bse={("500325", None): _bse("reliance_500325.json")},
                    sebi_post={"10": SourceDown("sebi", "down"), "11": SourceDown("sebi", "down")})
    res, prev = _run(s, monkeypatch=monkeypatch)
    assert res.ok and res.source == "bse_ann"
    p = res.rows["quota"]["Jio Platforms"]
    assert p["stage"] == "DRHP filed" and p["bucket"] == "drhp" and p["stageDate"] == "2026-09-16"
    assert p["isNew"] is True
    nr = p["needsReview"]
    assert nr["source"] == "bse_ann" and nr["url"].endswith("aaaa00000001.pdf")
    assert "Draft Red Herring" in nr["headline"] and nr["date"] == "2026-09-16"
    assert any(t["source"] == "sebi" and not t["ok"] for t in res.tried)
    assert any(n.startswith("bse_ann:") for n in res.notes)


def test_sebi_rhp_listing_advances_row_parent_did_not_announce(monkeypatch):
    s = FakeSession(sebi_post={"10": _sebi("drhp_page1.html"), "11": _sebi("rhp_page1.html")},
                    bse_exc=SourceDown("bse_ann", "api down"))
    res, prev = _run(s, monkeypatch=monkeypatch)
    assert res.ok and res.source == "sebi"
    p = res.rows["quota"]["Hero FinCorp"]
    assert p["stage"] == "RHP filed" and p["bucket"] == "approved" and p["stageDate"] == "2026-09-15"
    assert p["needsReview"]["source"] == "sebi" and "hero-fincorp" in p["needsReview"]["url"]
    # Jio's DRHP in the SEBI register also caught it
    assert res.rows["quota"]["Jio Platforms"]["bucket"] == "drhp"
    assert any(n.startswith("sebi:") for n in res.notes)


def test_both_sources_answer_records_both(monkeypatch):
    s = FakeSession(bse={("500325", None): _bse("reliance_500325.json")},
                    sebi_post={"10": _sebi("drhp_page1.html"), "11": _sebi("rhp_page1.html")})
    res, _ = _run(s, monkeypatch=monkeypatch)
    assert res.ok and res.source == "bse_ann+sebi"
    assert [t["source"] for t in res.tried if t["ok"]] == ["bse_ann", "sebi"]


def test_row_with_no_news_keeps_stage(monkeypatch):
    s = FakeSession(bse={("500325", None): _bse("reliance_500325.json")},
                    sebi_post={"10": _sebi("drhp_page1.html"), "11": _sebi("rhp_page1.html")})
    res, prev = _run(s, monkeypatch=monkeypatch)
    assert "Coal India Subsidiary" not in res.rows["quota"]
    data = json.loads(json.dumps(prev))
    assemble.apply(data, res)
    coal = next(r for r in data["quota"] if r["name"] == "Coal India Subsidiary")
    assert coal["stage"] == "Board approval" and coal["bucket"] == "awaited" and coal["stageDate"] == "2026-05-20"
    assert any("kept previous stage" in n for n in res.notes)


def test_stage_never_regresses(monkeypatch):
    prev = _prev()
    jio = prev["quota"][0]
    jio["bucket"], jio["stage"] = "approved", "RHP filed"
    s = FakeSession(bse={("500325", None): _bse("reliance_500325.json")},
                    sebi_post={"10": SourceDown("sebi", "down"), "11": SourceDown("sebi", "down")})
    res, _ = _run(s, prev=prev, monkeypatch=monkeypatch)
    p = res.rows["quota"]["Jio Platforms"]
    assert "stage" not in p and "bucket" not in p
    assert p["needsReview"]["source"] == "bse_ann"


def test_same_evidence_not_reflagged(monkeypatch):
    prev = _prev()
    jio = prev["quota"][0]
    jio.update({"bucket": "drhp", "stage": "DRHP filed", "stageDate": "2026-09-16",
                "needsReview": {"source": "bse_ann", "date": "2026-09-16", "headline": "x",
                                "url": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/9d1f2c3a-1111-4a5b-9c1d-aaaa00000001.pdf"}})
    s = FakeSession(bse={("500325", None): _bse("reliance_500325.json")},
                    sebi_post={"10": SourceDown("sebi", "down"), "11": SourceDown("sebi", "down")})
    res, _ = _run(s, prev=prev, monkeypatch=monkeypatch)
    assert "Jio Platforms" not in res.rows["quota"]


def test_past_listing_date_moves_to_done(monkeypatch):
    s = FakeSession(sebi_post={"10": _sebi("drhp_page1.html"), "11": _sebi("rhp_page1.html")})
    res, _ = _run(s, monkeypatch=monkeypatch)
    p = res.rows["quota"]["Nuvama Legacy"]
    assert p["bucket"] == "done" and p["stageDate"] == "2026-01-05"


def test_both_sources_fail_is_not_ok(monkeypatch):
    s = FakeSession(bse_exc=SourceDown("bse_ann", "api down"),
                    sebi_post={"10": SourceDown("sebi", "down"), "11": SourceDown("sebi", "down")})
    res, prev = _run(s, monkeypatch=monkeypatch)
    assert not res.ok and res.error
    assert len([t for t in res.tried if not t["ok"]]) == 3
    data = json.loads(json.dumps(prev))
    assemble.apply(data, res)          # not ok -> nothing applied, no ownership error
    assert data["quota"] == prev["quota"]


# ------------------------------------------------------------------------------------------
# ownership: never quota / quotaPct / confidence / sources
# ------------------------------------------------------------------------------------------
def test_module_never_writes_quota_fields(monkeypatch):
    s = FakeSession(bse={("500325", None): _bse("reliance_500325.json"), ("500182", 1): _bse("paged_p1.json"),
                         ("500182", 2): _bse("paged_p2.json")},
                    sebi_post={"10": _sebi("drhp_page1.html"), "11": _sebi("rhp_page1.html")})
    res, prev = _run(s, monkeypatch=monkeypatch)
    assert res.rows and set(res.rows) == {"quota"} and set(res.replace) <= {"expected", "quotaLeads"} and not res.merge
    for name, fields in res.rows["quota"].items():
        assert set(fields) <= filings.ALLOWED_FIELDS, (name, fields)
        assert not (set(fields) & filings.FORBIDDEN_FIELDS)
    data = json.loads(json.dumps(prev))
    assemble.apply(data, res)
    for before, after in zip(prev["quota"], data["quota"]):
        for k in ("quota", "quotaPct", "confidence", "sources", "name"):
            assert before.get(k) == after.get(k)
    hero = next(r for r in data["quota"] if r["name"] == "Hero FinCorp")
    assert hero["quotaPct"] == 10 and hero["quota"] is True
    assert hero["bucket"] == "approved"


def test_schema_registers_filings_as_quota_patcher():
    assert schema.OWNERS["quota"] == "filings"
    assert schema.ROW_PATCHERS["filings"] == {"quota"}


def test_parents_json_has_eight_known_parents():
    parents = filings.load_parents()
    assert {"RELIANCE", "COALINDIA", "HEROMOTOCO", "EDELWEISS", "IEX", "PRESTIGE", "SIS", "NLCINDIA"} <= set(parents)
    assert parents["RELIANCE"]["scrip"] == "500325"
    assert all(p["scrip"].isdigit() for p in parents.values())


def test_sebi_first_page_is_next_value_zero():
    """Live, 17 Sep 2026: nextValue=1 answered with rows from 22 Aug back; nextValue=0 with today's."""
    from collector.sources import sebi
    assert sebi._post_body(10, 1)["nextValue"] == "0"
    assert sebi._post_body(11, 2)["nextValue"] == "1"


# ------------------------------------------------------------------------------------------
# expected[] from the SEBI registers
# ------------------------------------------------------------------------------------------
def _f(register, title, date, kind=None):
    from collector.sources import sebi
    return {"register": register, "title": title, "date": date, "kind": kind or sebi.classify(title),
            "issuer": sebi.issuer(title), "detailUrl": "https://www.sebi.gov.in/filings/x/" + title[:12].replace(" ", "-")}


def test_build_expected_adds_facts_never_rewrites_handwriting():
    import datetime as dt
    prev = {"mainboard": [{"name": "Hero Motors"}], "sme": [], "recent": [], "quota": [{"name": "Mahanadi Coalfields"}],
            "expected": [{"name": "Hero Motors", "sizeCr": 1200, "note": "launched"},
                         {"name": "Zetwerk", "sizeCr": None, "note": "hand note", "stage": "UDRHP filed", "sources": ["u1"]},
                         {"name": "Torrent Gas", "sizeCr": 5000, "note": "big one", "stage": "DRHP filed", "sources": []}]}
    rows = [_f("DRHP", "Zetwerk Manufacturing Businesses Limited - Draft abridged prospectus", "2026-08-14"),
            _f("DRHP", "IBERIA PHARMACEUTICALS INDIA LIMITED- Draft Abridged Prospectus", "2026-09-17"),
            _f("DRHP", "Sterlite Electric Limited – Second Addendum to DRHP", "2026-09-16"),
            _f("DRHP", "Mahanadi Coalfields Ltd. - Draft Abridged Prospectus", "2026-09-04"),
            _f("RHP", "Torrent Gas Limited - Abridged Prospectus", "2026-09-15"),
            _f("RHP", "SS RETAIL LIMITED - Abridged Prospectus", "2026-09-09")]
    out, stats = filings.build_expected(prev, rows, dt.date(2026, 9, 17))
    by = {r["name"]: r for r in out}
    assert "Hero Motors" not in by and stats["launched"] == 1
    assert by["Zetwerk"]["note"] == "hand note" and by["Zetwerk"]["stage"] == "UDRHP filed"
    assert by["Zetwerk"]["lastFiling"]["date"] == "2026-08-14" and by["Zetwerk"]["sources"][-1] == "u1"
    assert by["Torrent Gas"]["stage"] == "RHP filed 15 Sep 2026" and by["Torrent Gas"]["sizeCr"] == 5000
    ib = by["Iberia Pharmaceuticals India"]
    assert ib["auto"] is True and ib["stage"] == "DRHP filed 17 Sep 2026" and ib["sizeCr"] is None and ib["note"] is None
    assert set(by) == {"Zetwerk", "Torrent Gas", "Iberia Pharmaceuticals India"}, "no addendum-only, quota, or RHP-register names"
    again, stats2 = filings.build_expected({**prev, "expected": out}, rows, dt.date(2026, 9, 18))
    assert [r["name"] for r in again] == [r["name"] for r in out] and stats2["new"] == 0 and stats2["rhp"] == 0


# ------------------------------------------------------------------------------------------
# discovery: NSE's market-wide announcements + group names -> quotaCandidate / quotaLeads
# ------------------------------------------------------------------------------------------
from collector.sources import nse_ann, nse_symbols  # noqa: E402

NSE_FIX = FIX / "nse"


def _ann():
    return json.loads((NSE_FIX / "corporate-announcements.json").read_text(encoding="utf8"))


def _equity():
    return (FIX / "nsearchives" / "EQUITY_L-sample.csv").read_text(encoding="utf8")


def test_nse_ann_parse_and_changed_shape():
    rows = nse_ann.parse(_ann())
    assert len(rows) == 13 and all(r["symbol"] and r["date"] for r in rows)
    kp = next(r for r in rows if r["symbol"] == "KPIL")
    assert kp["date"] == "2026-09-25" and kp["url"].startswith("https://nsearchives")
    with pytest.raises(SourceChanged):
        nse_ann.parse({"data": []})
    with pytest.raises(SourceChanged):
        nse_ann.parse([{"foo": 1}])


@pytest.mark.parametrize("text,kind", [
    ("Disclosure under Regulation 30 of SEBI LODR, 2015 Filing of DRHP of Mahanadi Coalfields Limited (MCL), "
     "a wholly owned Subsidiary of CIL.", "drhp"),
    ("Prestige Estates Projects Limited has informed the Exchange about the withdrawal of DRHP by Subsidiary", "withdrawn"),
    ("Kalpataru Projects International Limited has informed the Exchange about Initial public offering of equity "
     "shares of Linjemontage i Grastorp AB, a first level step down material subsidiary", "ipo"),
    ("Arkade Developers Limited has informed the Exchange regarding a press release on marking a milestone of 2 years "
     "of IPO and growth journey.", None),
    ("Statement of deviation in utilisation of IPO proceeds of the subsidiary", None),
    ("JSW Cement Limited has informed the Exchange about General Updates", None),
    ("Filing of Red Herring Prospectus by Hero FinCorp Limited, a subsidiary", "rhp"),
])
def test_classify_lead(text, kind):
    assert filings.classify_lead(text) == kind


def test_discover_finds_leads_and_moves_watched_parent(monkeypatch):
    prev = _prev()
    prev["expected"] = [{"name": "Iberia Pharmaceuticals India", "auto": True, "stage": "DRHP filed 17 Sep 2026",
                         "lastFiling": {"date": "2026-09-17"}}]
    s = FakeSession(bse_exc=SourceDown("bse_ann", "HTTP 403"),
                    sebi_post={"10": SourceDown("sebi", "down"), "11": SourceDown("sebi", "down")},
                    nse={"equities": _ann(), "sme": SourceChanged("nse_ann", "empty JSON body")}, equity_csv=_equity())
    res, _ = _run(s, prev=prev, today=dt.date(2026, 9, 26), monkeypatch=monkeypatch)
    assert res.ok and res.source == "nse_ann"
    leads = res.replace["quotaLeads"]
    assert {(x["parentSymbol"], x["kind"]) for x in leads} == {("PRESTIGE", "withdrawn"), ("KPIL", "ipo"), ("COALINDIA", "drhp")}
    assert any(n.startswith("discover: 13 announcements scanned, 3 ") for n in res.notes)
    # Coal India is a watched parent: its quota row moves, from an NSE announcement
    p = res.rows["quota"]["Coal India Subsidiary"]
    assert p["bucket"] == "drhp" and p["needsReview"]["source"] == "nse_ann" and p["stageDate"] == "2026-09-02"
    assert next(x for x in leads if x["parentSymbol"] == "COALINDIA")["watched"] is True
    # the window asked for is the last four days
    assert [c for c in s.calls if c[0] == "nse"][0][2]["from_date"] == "22-09-2026"


def test_lead_attaches_to_expected_row_not_to_the_announcer_itself():
    expected = [{"name": "Mahanadi Coalfields", "auto": True},
                {"name": "Coal India", "note": "hand row"},             # the announcer: never its own candidate
                {"name": "Linjemontage", "auto": True}]
    leads = [{"parentSymbol": "COALINDIA", "parentName": "Coal India Limited", "kind": "drhp", "date": "2026-09-02",
              "text": "Filing of DRHP of Mahanadi Coalfields Limited (MCL), a wholly owned Subsidiary of Coal India", "url": "u"},
             {"parentSymbol": "PRESTIGE", "parentName": "Prestige Estates Projects Limited", "kind": "withdrawn",
              "date": "2026-09-25", "text": "withdrawal of DRHP by Linjemontage subsidiary", "url": "w"}]
    stats = filings.attach_candidates(expected, leads, [])
    by = {r["name"]: r for r in expected}
    c = by["Mahanadi Coalfields"]["quotaCandidate"]
    assert c["via"] == "announcement" and c["parents"] == [{"symbol": "COALINDIA", "name": "Coal India Limited"}]
    assert c["url"] == "u" and c["kind"] == "drhp"
    assert "quotaCandidate" not in by["Coal India"] and by["Coal India"]["note"] == "hand row"
    assert "quotaCandidate" not in by["Linjemontage"], "a withdrawal is a lead, never a candidate"
    assert leads[0]["matched"] == "Mahanadi Coalfields" and stats["announcement"] == 1


def test_name_flag_on_auto_rows_only():
    companies = nse_symbols.parse(_equity())
    expected = [{"name": "Torrent Gas", "auto": True}, {"name": "Hero Fincorp", "auto": True},
                {"name": "JSW One Platforms", "auto": True}, {"name": "India Shelter Housing", "auto": True},
                {"name": "India Exposition Mart", "auto": True}, {"name": "M P Steel (India)", "auto": True},
                {"name": "Sembcorp Green Infra", "auto": True}, {"name": "Torrent Hand", "note": "hand"},
                {"name": "Fractal Analytics", "auto": True}]
    stats = filings.attach_candidates(expected, [], companies)
    by = {r["name"]: r.get("quotaCandidate") for r in expected}
    assert {p["symbol"] for p in by["Torrent Gas"]["parents"]} == {"TORNTPOWER", "TORNTPHARM"}
    assert by["Torrent Gas"]["via"] == "name"
    assert "HEROMOTOCO" in {p["symbol"] for p in by["Hero Fincorp"]["parents"]}
    assert "JSWCEMENT" in {p["symbol"] for p in by["JSW One Platforms"]["parents"]}
    assert by["India Shelter Housing"] is None and by["India Exposition Mart"] is None, "generic first word"
    assert by["M P Steel (India)"] is None and by["Sembcorp Green Infra"] is None
    assert by["Torrent Hand"] is None, "hand rows are not name-flagged"
    assert by["Fractal Analytics"] is None, "a listed company is not its own parent"
    assert stats["name"] == 3


def test_name_never_downgrades_announcement_and_missing_list_keeps_flags():
    ann = {"via": "announcement", "parents": [{"symbol": "COALINDIA"}], "url": "u"}
    name = {"via": "name", "parents": [{"symbol": "TORNTPOWER"}]}
    expected = [{"name": "Torrent Gas", "auto": True, "quotaCandidate": dict(ann)},
                {"name": "Torrent Other", "auto": True, "quotaCandidate": dict(name)}]
    filings.attach_candidates(expected, [], nse_symbols.parse(_equity()))
    assert expected[0]["quotaCandidate"] == ann
    expected[1]["quotaCandidate"] = {"via": "name", "parents": [{"symbol": "OLD"}]}
    filings.attach_candidates(expected, [], None)
    assert expected[1]["quotaCandidate"]["parents"] == [{"symbol": "OLD"}]


def test_merge_leads_dedupes_and_ages_out():
    today = dt.date(2026, 9, 26)
    old = {"parentSymbol": "X", "seqId": "1", "date": "2026-07-01", "text": "t", "kind": "drhp"}
    kept = {"parentSymbol": "Y", "seqId": "2", "date": "2026-09-20", "text": "t", "kind": "drhp", "matched": "Row"}
    again = {"parentSymbol": "Y", "seqId": "2", "date": "2026-09-20", "text": "t", "kind": "drhp"}
    out = filings.merge_leads([old, kept], [again], today)
    assert [x["seqId"] for x in out] == ["2"] and out[0]["matched"] == "Row"


def test_nse_down_carries_leads_and_still_flags_names(monkeypatch):
    prev = _prev()
    prev["quotaLeads"] = [{"parentSymbol": "KPIL", "seqId": "9", "date": "2026-09-25", "text": "x", "kind": "ipo"}]
    prev["expected"] = [{"name": "Torrent Gas", "auto": True}]
    s = FakeSession(sebi_post={"10": _sebi("drhp_page1.html"), "11": _sebi("rhp_page1.html")}, equity_csv=_equity())
    res, _ = _run(s, prev=prev, monkeypatch=monkeypatch)
    assert res.ok and "quotaLeads" not in res.replace, "no answer -> yesterday's leads stay by not replacing"
    tg = next(r for r in res.replace["expected"] if r["name"] == "Torrent Gas")
    assert tg["quotaCandidate"]["via"] == "name"
    assert any(t["source"] == "nse_ann" and not t["ok"] for t in res.tried)


def test_schema_and_layout_publish_quota_leads():
    from collector import layout
    assert schema.OWNERS["quotaLeads"] == "filings" and "quotaLeads" in schema.TOP_LEVEL
    assert schema.empty_data()["quotaLeads"] == []
    assert "quotaLeads" in layout.GROUPS["pipeline"]
    layout.check_groups()
