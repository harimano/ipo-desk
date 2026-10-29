"""The size cap is on what the page fetches at boot: the on-demand books part has its own, so a backfill of 1,300
anchor books (the only part that grows without bound) never stops the gate writing the board."""
import importlib.util
import pathlib

from collector import layout

spec = importlib.util.spec_from_file_location("validate", pathlib.Path(__file__).resolve().parent.parent / "scripts/validate.py")
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


def test_lazy_keys_mirror_the_layouts_lazy_groups():
    lazy_keys = {k for g in layout.LAZY for k in layout.GROUPS[g]}
    assert set(validate.LAZY_KEYS) == lazy_keys


def test_on_demand_parts_do_not_count_against_the_boot_cap():
    big = "x" * (7 * 1024 * 1024)
    boot, lazy = validate.published_bytes({"meta": {"asOf": "2026-10-29"}, "mainboard": [], "anchorBooks": {"books": big}, "trackRecords": {}})
    assert boot < 1024
    assert lazy > 7 * 1024 * 1024
    assert lazy < validate.MAX_LAZY_BYTES


def test_a_runaway_board_still_counts():
    big = "x" * (7 * 1024 * 1024)
    boot, lazy = validate.published_bytes({"meta": {}, "mainboard": [{"name": big}]})
    assert boot > validate.MAX_DOC_BYTES
    assert lazy == 0
