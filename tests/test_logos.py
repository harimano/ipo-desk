"""logos module: one thumbnail per issue, written only under logos/. Fixture: a real logo (Vishal Nirmiti, 1 Oct 2026)."""
from __future__ import annotations

import datetime as dt
import io
import pathlib

import pytest

from collector import assemble, layout, schema
from collector.errors import SourceChanged, SourceDown
from collector.modules import logos
from collector.result import Result

PNG = (pathlib.Path(__file__).resolve().parent.parent / "data/fixtures/logos/sample.png").read_bytes()
TODAY = dt.datetime.now(logos.IST).date()


class S:
    def __init__(self, answers: dict):
        self.answers, self.calls = answers, []

    def get_bytes(self, url, *, source, headers=None, expect_pdf=False):
        name = url.rsplit("/", 1)[1]
        self.calls.append(name)
        v = self.answers.get(name, SourceDown(source, "HTTP 404", url, 404))
        if isinstance(v, Exception):
            raise v
        return v


def _doc():
    return {"mainboard": [{"name": "Vishal Nirmiti", "igId": "1602", "logo": "vnl.png", "open": "2026-09-30"}],
            "sme": [{"name": "Black Opal", "igId": "2370", "logo": "bo.png", "open": "2026-09-29"},
                    {"name": "No Logo", "igId": "9", "open": "2026-09-29"}],
            "recent": [{"name": "Gone", "igId": "7", "logo": "gone.png", "listingDate": "2026-09-01"}]}


def _run(session, prev=None, doc=None):
    res = Result(module="logos", doc=doc or _doc())
    return logos.run(session, prev or {"logos": {}}, res)


def test_thumbnail_is_a_small_2_to_1_webp():
    from PIL import Image
    out = logos.thumbnail(PNG)
    im = Image.open(io.BytesIO(out))
    assert im.format == "WEBP" and im.size == logos.SIZE and len(out) < 4096
    with pytest.raises(SourceChanged):
        logos.thumbnail(b"<html>not found</html>")


def test_fetches_each_logo_once_newest_first_and_marks_missing_ones():
    s = S({"vnl.png": PNG, "bo.png": PNG, "gone.png": b"<html>"})
    res = _run(s)
    assert res.ok and s.calls == ["vnl.png", "bo.png", "gone.png"], "newest first; a row with no logo is not asked"
    assert set(res.files) == {"logos/1602.webp", "logos/2370.webp"}
    assert res.replace["logos"]["1602"] == {"src": "vnl.png", "at": TODAY.isoformat()}
    assert res.replace["logos"]["7"]["missing"] is True
    again = S({"vnl.png": PNG, "bo.png": PNG, "gone.png": PNG})
    res2 = _run(again, prev={"logos": res.replace["logos"]})
    assert again.calls == [] and res2.ok and not res2.files, "made once; a missing one waits RETRY_DAYS"


def test_a_changed_logo_file_is_fetched_again():
    s = S({"vnl2.png": PNG})
    doc = _doc()
    doc["mainboard"][0]["logo"] = "vnl2.png"
    res = _run(s, prev={"logos": {"1602": {"src": "vnl.png", "at": "2026-09-30"}, "2370": {"src": "bo.png", "at": "2026-09-30"},
                                  "7": {"src": "gone.png", "at": TODAY.isoformat(), "missing": True}}}, doc=doc)
    assert s.calls == ["vnl2.png"] and "logos/1602.webp" in res.files


def test_only_network_errors_fail_the_module():
    s = S({"vnl.png": SourceDown("logos", "timeout"), "bo.png": SourceDown("logos", "timeout"),
           "gone.png": SourceDown("logos", "timeout")})
    res = _run(s)
    assert not res.ok and not res.files


def test_files_are_written_only_under_the_module_s_own_directory(tmp_path):
    ok = Result(module="logos", ok=True, files={"logos/1.webp": b"x"})
    assert assemble.write_files([ok], tmp_path) == 1 and (tmp_path / "logos/1.webp").read_bytes() == b"x"
    failed = Result(module="logos", ok=False, files={"logos/2.webp": b"x"})
    assert assemble.write_files([failed], tmp_path) == 0, "a failed module writes nothing"
    for bad in ("latest.json", "logos/../latest.json", "history/x.json"):
        with pytest.raises(assemble.OwnershipError):
            assemble.write_files([Result(module="logos", ok=True, files={bad: b"x"})], tmp_path)
    with pytest.raises(assemble.OwnershipError):
        assemble.write_files([Result(module="gmp", ok=True, files={"logos/3.webp": b"x"})], tmp_path)


def test_schema_and_layout_publish_the_logo_index():
    assert schema.OWNERS["logos"] == "logos" and schema.empty_data()["logos"] == {}
    assert "logos" in layout.GROUPS["board"]
    layout.check_groups()
