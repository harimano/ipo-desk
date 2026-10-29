"""scripts/restore_d1.py against a local stand-in for Cloudflare's D1 query endpoint backed by a real sqlite3 file.

Limitation, stated: the stand-in speaks the endpoint's shape (POST .../d1/database/<id>/query, {sql} in, {success,
result:[{success, meta}]} out) and runs the SQL in SQLite, which is what D1 is — but it is not D1. The first real
restore goes into a scratch database Hari creates; this proves the splitter, the plan, the batching and the refusals.
"""
from __future__ import annotations

import http.server
import json
import pathlib
import sqlite3
import sys
import threading
from typing import ClassVar

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import restore_d1

DUMP = """PRAGMA defer_foreign_keys=TRUE;
CREATE TABLE user_state (email TEXT NOT NULL, part TEXT NOT NULL, body TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY (email, part));
INSERT INTO "user_state" VALUES('alice@example.com','holdings','["Reliance Industries"]','2026-10-29T10:00:00Z');
INSERT INTO "user_state" VALUES('bob@example.com','interest','["Lenskart; Solutions"]','2026-10-29T11:00:00Z');
CREATE TABLE reports (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, email TEXT NOT NULL, issue TEXT NOT NULL, ig_id TEXT, field TEXT NOT NULL, shown TEXT, note TEXT, page TEXT, data_as_of TEXT, status TEXT NOT NULL DEFAULT 'open');
INSERT INTO "reports" VALUES(1,'2026-10-29T12:00:00Z','bob@example.com','Lenskart Solutions','2305','gmp','73','IG shows 65;
it''s lower on the second line','today','2026-10-29T15:08:47+05:30','open');
CREATE TABLE daily_active (day TEXT NOT NULL, email_hash TEXT NOT NULL, PRIMARY KEY (day, email_hash));
INSERT INTO "daily_active" VALUES('2026-10-29','ab12');
DELETE FROM sqlite_sequence;
INSERT INTO "sqlite_sequence" VALUES('reports',1);
"""


def test_splitter_respects_quotes():
    st = restore_d1.split_statements(DUMP)
    assert len(st) == 10
    assert st[5].startswith("INSERT INTO \"reports\"") and "it''s lower" in st[5] and "second line" in st[5]
    assert restore_d1.split_statements("-- a comment;\nSELECT 1; SELECT 'a;b' -- trailing\n;") == ["SELECT 1", "SELECT 'a;b'"]


def test_plan_idempotent_create_and_replace():
    st = restore_d1.plan(restore_d1.split_statements(DUMP), replace=False)
    assert sum(s.startswith("CREATE TABLE IF NOT EXISTS") for s in st) == 3 and not any(s.startswith("DROP") for s in st)
    st = restore_d1.plan(restore_d1.split_statements(DUMP), replace=True)
    assert st[:3] == ['DROP TABLE IF EXISTS "user_state"', 'DROP TABLE IF EXISTS "reports"', 'DROP TABLE IF EXISTS "daily_active"']


class _D1Stub(http.server.BaseHTTPRequestHandler):
    db_path: str = ""
    calls: ClassVar[list] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).calls.append((self.path, self.headers.get("Authorization")))
        if not self.path.endswith("/query") or self.headers.get("Authorization") != "Bearer tok-test":
            return self._send(403, {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]})
        con = sqlite3.connect(type(self).db_path)
        try:
            before = con.total_changes
            con.executescript(body["sql"])
            con.commit()
            out = {"success": True, "result": [{"success": True, "results": [], "meta": {"rows_written": con.total_changes - before}}], "errors": []}
        except sqlite3.Error as e:
            out = {"success": False, "result": [], "errors": [{"code": 7500, "message": str(e)}]}
        finally:
            con.close()
        self._send(200, out)

    def _send(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)


@pytest.fixture
def stub(tmp_path):
    _D1Stub.db_path = str(tmp_path / "scratch.sqlite"); _D1Stub.calls = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _D1Stub)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/client/v4", _D1Stub.db_path
    srv.shutdown()


def test_restore_into_scratch(stub, tmp_path, monkeypatch, capsys):
    api, db = stub
    dump = tmp_path / "2026-10-30.sql"; dump.write_text(DUMP, encoding="utf8")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-test\n"); monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct1")
    assert restore_d1.main([str(dump), "--database-id", "scratch-1", "--api", api]) == 0
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM user_state").fetchone()[0] == 2
    assert con.execute("SELECT note FROM reports").fetchone()[0] == "IG shows 65;\nit's lower on the second line"
    assert con.execute("SELECT body FROM user_state WHERE email='bob@example.com'").fetchone()[0] == '["Lenskart; Solutions"]'
    assert _D1Stub.calls[0][0] == "/client/v4/accounts/acct1/d1/database/scratch-1/query"
    # a second run without --replace hits the primary keys; with --replace it lands clean
    assert restore_d1.main([str(dump), "--database-id", "scratch-1", "--api", api]) == 1
    assert "stopped" in capsys.readouterr().err
    assert restore_d1.main([str(dump), "--database-id", "scratch-1", "--api", api, "--replace"]) == 0
    assert con.execute("SELECT COUNT(*) FROM user_state").fetchone()[0] == 2


def test_refusals(tmp_path, monkeypatch, capsys):
    dump = tmp_path / "x.sql"; dump.write_text(DUMP, encoding="utf8")
    live = restore_d1.live_database_id()
    assert live, "wrangler.toml names the live database"
    assert restore_d1.main([str(dump), "--database-id", live, "--dry-run"]) == 2
    assert "LIVE" in capsys.readouterr().err
    assert restore_d1.main([str(dump), "--database-id", live, "--dry-run", "--i-mean-the-live-database"]) == 0
    assert "dry run: nothing sent" in capsys.readouterr().out
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert restore_d1.main([str(dump), "--database-id", "scratch-1"]) == 2
    (tmp_path / "notadump.sql").write_text("SELECT 1;", encoding="utf8")
    assert restore_d1.main([str(tmp_path / "notadump.sql"), "--database-id", "scratch-1", "--dry-run"]) == 2
