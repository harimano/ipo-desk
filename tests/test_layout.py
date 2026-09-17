import json
import pathlib

import pytest

from collector import layout
from collector.schema import empty_data

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_every_schema_key_is_published_exactly_once():
    layout.check_groups()


def test_split_round_trips_and_hashes_track_content():
    doc = empty_data()
    doc["mainboard"] = [{"name": "Hero Motors", "gmp": 5.5}]
    doc["meta"]["asOf"] = "2026-09-17T18:15:00+05:30"
    parts = layout.split(doc)
    assert set(parts) == {"meta.json"} | {f"{g}.json" for g in layout.GROUPS}
    assert layout.join(parts) == doc
    files = json.loads(parts["meta.json"])["files"]

    doc2 = json.loads(json.dumps(doc))
    doc2["mainboard"][0]["gmp"] = 7
    files2 = json.loads(layout.split(doc2)["meta.json"])["files"]
    assert files2["board"]["hash"] != files["board"]["hash"]
    assert all(files2[g]["hash"] == files[g]["hash"] for g in layout.GROUPS if g != "board")


def test_unknown_top_level_key_is_refused_not_dropped():
    doc = empty_data()
    doc["surprise"] = 1
    with pytest.raises(ValueError):
        layout.split(doc)


def test_seed_document_round_trips():
    p = ROOT / "data" / "latest.json"
    if not p.exists():
        pytest.skip("no local data/latest.json")
    doc = json.loads(p.read_text(encoding="utf8"))
    assert layout.join(layout.split(doc)) == doc
