"""Local preview of the gated site WITHOUT Cloudflare: serves _site/ and emulates the Worker's /api/state in memory.

  .venv/bin/python scripts/preview.py            # http://localhost:8765  (what .claude/launch.json's `site` runs)
  .venv/bin/python scripts/preview.py 8766

The real Worker (ops/site-worker/worker.js) knows the reader from the Access token it verifies. Here there is no
Access, so the "signed-in" email is a plain dev cookie: open /dev/as/alice@example.com, then /dev/as/bob@example.com
in another browser profile, and each gets a separate in-memory account. Nothing here is deployed, and nothing
persists past the process: this is for driving the page by hand and from the smoke tests.

Also serves ops/site-worker/ under /__worker/ so the browser test harness (test/harness.html) can import worker.js,
and /admin/retention.json + /admin/me.json in the Worker's shape, so /admin's cards render here (a page load by a
dev email counts as that day's active reader, as the Worker's daily_active row does).
"""
from __future__ import annotations

import http.server
import json
import pathlib
import sys
import threading
import urllib.parse
from http.cookies import SimpleCookie

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "_site"
WORKER = ROOT / "ops" / "site-worker"
PARTS = {"holdings", "interest", "apps", "tasks-done", "tasks-custom", "investors", "theme", "budget"}
PART_MAX = 64 * 1024

STORE: dict[str, dict[str, tuple[str, str]]] = {}      # email -> part -> (body, updated)
REPORTS: list[dict] = []                               # "Wrong number?" reports, newest last
DAILY: set[tuple[str, str]] = set()                    # (IST day, dev email): the Worker's daily_active, for /admin's card
LOCK = threading.Lock()


def now() -> str:
    import datetime
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def ist_day(offset_days: int = 0) -> str:
    import datetime
    return (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=5, minutes=30, days=offset_days)).date().isoformat()


def retention() -> dict:
    """The shape of the Worker's /admin/retention.json (worker.js retentionWeeks), from the loads this process saw."""
    import datetime
    today = datetime.date.fromisoformat(ist_day())
    monday = today - datetime.timedelta(days=today.weekday())
    starts = [(monday - datetime.timedelta(weeks=7 - i)).isoformat() for i in range(8)]
    week_of = lambda d: max((i for i, st in enumerate(starts) if d >= st), default=-1)
    with LOCK:
        rows = sorted(DAILY)
    active: list[set[str]] = [set() for _ in starts]
    first: dict[str, str] = {}
    for day, who in rows:
        w = week_of(day)
        if w < 0:
            continue
        active[w].add(who)
        first[who] = min(first.get(who, day), day)
    weeks = [{"start": st, "active": len(active[i]), "new": sum(week_of(first[h]) == i for h in active[i]),
              "ofFirst": len(active[i] & active[0])} for i, st in enumerate(starts)]
    return {"at": now(), "salted": True, "rows": len(rows), "from": starts[0], "today": today.isoformat(),
            "daysIntoWeek": today.weekday() + 1, "firstWeekReaders": len(active[0]), "weeks": weeks}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(SITE), **kw)

    def log_message(self, fmt, *args):   # one quiet line per request
        sys.stderr.write(f"{self.command} {self.path}\n")

    # ---- helpers ----
    def email(self) -> str | None:
        c = SimpleCookie(self.headers.get("Cookie", ""))
        v = c.get("dev_email")
        return v.value.lower() if v and v.value else None

    def send_json(self, body, status=200):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def serve_worker_file(self, rel: str):
        p = (WORKER / rel).resolve()
        if not str(p).startswith(str(WORKER)) or not p.is_file():
            self.send_error(404)
            return
        data = p.read_bytes()
        ctype = "text/javascript" if p.suffix in (".js", ".mjs") else "text/html" if p.suffix == ".html" else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- routes ----
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        if path.startswith("/dev/as/"):
            who = urllib.parse.unquote(path[len("/dev/as/"):]).strip().lower()
            self.send_response(302)
            self.send_header("Set-Cookie", f"dev_email={who}; Path=/; SameSite=Lax")
            self.send_header("Location", "/")
            self.end_headers()
            return
        if path == "/dev/signout":
            self.send_response(302)
            self.send_header("Set-Cookie", "dev_email=; Path=/; Max-Age=0")
            self.send_header("Location", "/")
            self.end_headers()
            return
        if path.startswith("/__worker/"):
            return self.serve_worker_file(path[len("/__worker/"):])
        if path == "/logout":
            return self.do_GET_redirect("/dev/signout")
        if path == "/whoami":
            e = self.email()
            raw = ((e or "(no email claim)") + "\n").encode()
            self.send_response(200 if e else 401)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if path == "/admin/reports.json":
            return self.send_json({"reports": list(reversed(REPORTS))})
        if path == "/admin/retention.json":
            return self.send_json(retention())
        if path == "/admin/me.json":
            return self.send_json({"email": self.email(), "team": "preview", "adminEmailSet": True, "visitors": False, "accounts": True, "dauSalt": True, "backupBucket": "ipo-desk-backups"})
        if path in ("/", "/index.html", "/admin", "/admin/") and self.email() and "text/html" in (self.headers.get("Accept") or ""):
            with LOCK:
                DAILY.add((ist_day(), self.email()))
        if path.startswith("/api"):
            return self.api("GET", path.rstrip("/") or "/api", b"")
        return super().do_GET()

    def do_GET_redirect(self, to):
        self.send_response(302)
        self.send_header("Location", to)
        self.end_headers()

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        return self.api("PUT", urllib.parse.urlsplit(self.path).path.rstrip("/"), body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        return self.api("POST", urllib.parse.urlsplit(self.path).path.rstrip("/"), body)

    def do_DELETE(self):
        return self.api("DELETE", urllib.parse.urlsplit(self.path).path.rstrip("/"), b"")

    def api(self, method: str, path: str, body: bytes):
        if not path.startswith("/api"):
            return self.send_error(405)
        email = self.email()
        if not email:
            return self.send_json({"error": "sign-in required (dev: open /dev/as/<email>)"}, 401)
        with LOCK:
            acct = STORE.setdefault(email, {})
            if path == "/api/state" and method == "GET":
                parts = {p: json.loads(b) for p, (b, _) in acct.items()}
                return self.send_json({"email": email, "parts": parts, "updated": {p: u for p, (_, u) in acct.items()}})
            if path == "/api/state" and method == "DELETE":
                acct.clear()
                return self.send_json({"ok": True, "email": email, "parts": {}, "updated": {}})
            if path == "/api/whoami" and method == "GET":
                return self.send_json({"email": email})
            if path == "/api/report" and method == "POST":
                try:
                    rep = json.loads(body or b"x")
                except ValueError:
                    return self.send_json({"error": "body is not JSON"}, 400)
                if not isinstance(rep, dict) or not rep.get("issue") or not rep.get("field"):
                    return self.send_json({"error": "issue and field are required"}, 400)
                row = {"id": len(REPORTS) + 1, "at": now(), "email": email, "status": "open"}
                row.update({k: rep.get(k) for k in ("issue", "field", "shown", "note", "page")})
                row["ig_id"], row["data_as_of"] = rep.get("igId"), rep.get("dataAsOf")
                REPORTS.append(row)
                sys.stderr.write(f"report: {email} {row['issue']} {row['field']} {row.get('note') or ''}\n")
                return self.send_json({"ok": True, "at": row["at"]})
            if path.startswith("/api/state/") and method == "PUT":
                part = path[len("/api/state/"):]
                if part not in PARTS:
                    return self.send_json({"error": f"unknown part '{part}'"}, 400)
                if len(body) > PART_MAX:
                    return self.send_json({"error": "part too large"}, 413)
                try:
                    json.loads(body or b"x")
                except ValueError:
                    return self.send_json({"error": "body is not JSON"}, 400)
                u = now()
                acct[part] = (body.decode("utf8"), u)
                return self.send_json({"ok": True, "part": part, "updated": u})
        return self.send_json({"error": "no such API route"}, 405 if path.startswith("/api/state") or path == "/api/report" else 404)


def main() -> int:
    import os
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8765))   # the preview launcher may hand out another port
    if not SITE.is_dir():
        print("_site/ missing — run site/build.py first", file=sys.stderr)
        return 1
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"preview: http://localhost:{port}/  (sign in: /dev/as/you@example.com · harness: /__worker/test/harness.html)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
