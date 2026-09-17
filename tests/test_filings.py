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
                 detail: str | None = None, bse_exc: Exception | None = None):
        self.bse = bse or {}
        self.sebi_post = sebi_post or {}
        self.sebi_get = sebi_get or {}
        self.detail = detail
        self.bse_exc = bse_exc
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
        if "/filings/" in url:
            if self.detail is None:
                raise SourceDown(source, "no detail", url)
            return self.detail
        smid = (params or {}).get("smid")
        if smid in self.sebi_get:
            return self.sebi_get[smid]
        raise SourceDown(source, "listing unavailable", url)

    # unused by this module, present so the fake has the full surface
    def nse_json(self, *a, **k):
        raise AssertionError("filings must not call NSE")

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
    assert len([t for t in res.tried if not t["ok"]]) == 2
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
    assert res.rows and set(res.rows) == {"quota"} and not res.replace and not res.merge
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
