import copy
import datetime as dt

from collector.assemble import IST, stamp_notes

T = dt.datetime(2026, 10, 30, 6, 43, tzinfo=IST)


def test_notes_as_of_moves_only_when_the_notes_change():
    prev = {"meta": {"marketNotes": ["9 Sep refresh"], "newFindings": [], "quotaSourceNote": None}}
    data = copy.deepcopy(prev)
    stamp_notes(data, prev, T)
    assert "notesAsOf" not in data["meta"]                       # never recorded: the page reads it as old
    prev["meta"]["notesAsOf"] = "2026-10-01T06:43:00+05:30"
    data = copy.deepcopy(prev)
    stamp_notes(data, prev, T)
    assert data["meta"]["notesAsOf"] == "2026-10-01T06:43:00+05:30"   # unchanged notes keep their stamp
    data["meta"]["marketNotes"] = ["9 Sep refresh", "a new note"]
    stamp_notes(data, prev, T)
    assert data["meta"]["notesAsOf"] == T.isoformat()
    data = copy.deepcopy(prev)
    data["meta"]["quotaSourceNote"] = "re-verified"
    stamp_notes(data, prev, T)
    assert data["meta"]["notesAsOf"] == T.isoformat()
