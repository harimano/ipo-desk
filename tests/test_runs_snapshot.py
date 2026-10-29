"""scripts/runs_snapshot.py — the deploy's run list for /admin."""
import importlib.util
import json
import pathlib

spec = importlib.util.spec_from_file_location("runs_snapshot", pathlib.Path(__file__).resolve().parent.parent / "scripts/runs_snapshot.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def test_folds_runs_and_the_live_commit_and_reads_live_json_asof_from_the_message(tmp_path):
    (tmp_path / "runs.json").write_text(json.dumps([{"id": 1, "name": "collect", "conclusion": "success"}]))
    (tmp_path / "live.json").write_text(json.dumps({"at": "2026-10-29T09:31:37Z", "msg": "live: 2026-10-29T15:01:35+05:30"}))
    out = tmp_path / "out" / "runs.json"
    assert rs.main(["x", str(tmp_path / "runs.json"), str(tmp_path / "live.json"), str(out)]) == 0
    body = json.loads(out.read_text())
    assert body["runs"][0]["name"] == "collect"
    assert body["live"] == {"at": "2026-10-29T09:31:37Z", "asOf": "2026-10-29T15:01:35+05:30"}
    assert body["at"].endswith("+00:00")


def test_garbage_in_gives_an_empty_snapshot_not_a_failed_deploy(tmp_path):
    (tmp_path / "runs.json").write_text("not json")
    (tmp_path / "live.json").write_text("")
    out = tmp_path / "runs.json.out"
    assert rs.main(["x", str(tmp_path / "runs.json"), str(tmp_path / "live.json"), str(out)]) == 0
    assert json.loads(out.read_text()) == {"at": json.loads(out.read_text())["at"], "runs": [], "live": None}
