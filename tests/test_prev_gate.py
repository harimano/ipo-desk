import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("prev_gate", pathlib.Path(__file__).resolve().parent.parent / "scripts/prev_gate.py")
pg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pg)

SHA = "12a3cfa"
LOG = ("2026-10-16T13:54:38.1Z \x1b[31mWARN  something minor\x1b[0m\n"
       "2026-10-16T13:54:38.4Z FAIL — 1 error(s); do not write:\n"
       "2026-10-16T13:54:38.4Z   · latest/recent[]/sources: 64 -> 34 items (47% loss, limit 30%)\n"
       "2026-10-16T13:54:38.5Z ##[error]Process completed with exit code 1.\n")


def run(id_, conclusion, sha=SHA, status="completed"):
    return {"databaseId": id_, "status": status, "conclusion": conclusion, "headSha": sha,
            "createdAt": "2026-10-16T13:53:37Z", "url": f"https://x/{id_}"}


def jobs(gate="failure", collect="success"):
    return [{"id": 7, "steps": [{"name": "Collect", "conclusion": collect},
                                {"name": "Gate — the validator must pass or nothing is committed", "conclusion": gate}]}]


def test_a_repeated_gate_refusal_on_the_same_commit_skips_with_the_message():
    runs = [run(2, None, status="in_progress"), run(1, "failure")]
    w = pg.decide(runs, 2, SHA, lambda r: jobs(), lambda j: LOG)
    assert w.startswith("gate refused at 2026-10-16 13:53 UTC (https://x/1): FAIL — 1 error(s); do not write: "
                        "· latest/recent[]/sources: 64 -> 34 items (47% loss, limit 30%)")
    assert "intraday skipped until the next full run or a push to main" in w


def test_a_push_to_main_or_a_green_previous_run_means_go():
    assert pg.decide([run(2, None, status="in_progress"), run(1, "failure", sha="fix")], 2, SHA, jobs, lambda j: LOG) is None
    assert pg.decide([run(1, "success")], 2, SHA, jobs, lambda j: LOG) is None
    assert pg.decide([], 2, SHA, jobs, lambda j: LOG) is None


def test_a_failure_anywhere_but_the_gate_is_retried_as_usual():
    calls = []
    w = pg.decide([run(1, "failure")], 2, SHA, lambda r: jobs(gate="skipped", collect="failure"), lambda j: calls.append(j))
    assert w is None and not calls, "a network fault in Collect is retried at the next slot; no log is fetched"


def test_the_message_survives_a_log_without_the_fail_line():
    assert pg.gate_message("2026-10-16T13:54:38.5Z ##[error]Process completed with exit code 1.\n") == "message not found in the job log"
