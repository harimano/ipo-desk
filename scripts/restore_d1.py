"""Restore a nightly dump (backup.yml → R2 ipo-desk-backups/nightly/<date>.sql) into a D1 database — by id, never the
live one by default.

  export CLOUDFLARE_API_TOKEN=…      # typed in the shell (a token with D1 · Edit); never pasted in chat, never in a file
  export CLOUDFLARE_ACCOUNT_ID=…
  .venv/bin/python scripts/restore_d1.py 2026-10-30.sql --database-id <scratch id> --dry-run    # what would run
  .venv/bin/python scripts/restore_d1.py 2026-10-30.sql --database-id <scratch id>              # into an empty scratch
  .venv/bin/python scripts/restore_d1.py 2026-10-30.sql --database-id <id> --replace            # drop the dump's tables first

The dump is what `wrangler d1 export` writes: CREATE TABLE and INSERT statements, one per line, string literals in
single quotes (a reader's note may carry a newline or a semicolon inside them — the splitter knows quotes). It is sent
in batches to Cloudflare's D1 query endpoint, POST /accounts/{account}/d1/database/{id}/query, with the plain token
(developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/). No Node, no wrangler: Hari's Mac
has neither. Get the file from the dashboard (R2 → ipo-desk-backups → nightly/ → Download).

The id in ops/site-worker/wrangler.toml is the LIVE database: the script refuses it unless --i-mean-the-live-database
is given as well. CREATE TABLE becomes CREATE TABLE IF NOT EXISTS, so a restore into a database that has the tables
adds rows (and fails on duplicate keys) unless --replace drops those tables first. D1 Time Travel (7 days on the Free
plan, `wrangler d1 time-travel restore`, in place) is the first resort for a bad write; this is the copy from outside.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
WRANGLER_TOML = ROOT / "ops" / "site-worker" / "wrangler.toml"
API = "https://api.cloudflare.com/client/v4"
BATCH = 40                       # statements per request; a dump line is well under D1's 100 KB statement cap


def split_statements(text: str) -> list[str]:
    """Split SQL on `;` outside single-quoted strings ('' is an escaped quote inside one); drop `--` comments and blanks."""
    out, cur, i, n, inq = [], [], 0, len(text), False
    while i < n:
        c = text[i]
        if inq:
            cur.append(c)
            if c == "'":
                if i + 1 < n and text[i + 1] == "'":
                    cur.append("'"); i += 1
                else:
                    inq = False
        elif c == "'":
            inq = True; cur.append(c)
        elif c == "-" and text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif c == ";":
            s = "".join(cur).strip()
            if s:
                out.append(s)
            cur = []
        else:
            cur.append(c)
        i += 1
    s = "".join(cur).strip()
    if s:
        out.append(s)
    return out


_CREATE = re.compile(r'^CREATE TABLE\s+(IF NOT EXISTS\s+)?("?)([A-Za-z_][A-Za-z0-9_]*)\2', re.IGNORECASE)


def table_of(stmt: str) -> str | None:
    m = _CREATE.match(stmt)
    return m.group(3) if m else None


def plan(statements: list[str], replace: bool) -> list[str]:
    """The statements as they will be sent: CREATE TABLE made idempotent; with --replace, each table dropped first."""
    tables = [t for t in (table_of(s) for s in statements) if t]
    out = [f'DROP TABLE IF EXISTS "{t}"' for t in tables] if replace else []
    for s in statements:
        t = table_of(s)
        if t and not re.match(r"^CREATE TABLE\s+IF NOT EXISTS", s, re.IGNORECASE):
            s = re.sub(r"^CREATE TABLE\s+", "CREATE TABLE IF NOT EXISTS ", s, count=1, flags=re.IGNORECASE)
        out.append(s)
    return out


def live_database_id() -> str | None:
    try:
        m = re.search(r'^database_id\s*=\s*"([^"]+)"', WRANGLER_TOML.read_text(encoding="utf8"), re.MULTILINE)
    except OSError:
        return None
    return m.group(1) if m else None


def query(api: str, account: str, token: str, db: str, sql: str) -> dict:
    req = urllib.request.Request(f"{api}/accounts/{account}/d1/database/{db}/query", method="POST",
                                 data=json.dumps({"sql": sql}).encode(),
                                 headers={"Authorization": f"Bearer {token.strip()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"success": False, "errors": [{"code": e.code, "message": str(e)}]}
    if not body.get("success"):
        raise RuntimeError("D1 answered: " + json.dumps(body.get("errors") or body)[:600])
    return body


def restore(statements: list[str], *, api: str, account: str, token: str, db: str, log=print) -> int:
    sent = 0
    for i in range(0, len(statements), BATCH):
        chunk = statements[i:i + BATCH]
        body = query(api, account, token, db, ";\n".join(chunk) + ";")
        results = body.get("result") or []
        bad = [r for r in results if r.get("success") is False]
        if bad:
            raise RuntimeError(f"statement batch {i // BATCH + 1} failed: {json.dumps(bad[0])[:400]}")
        sent += len(chunk)
        written = sum((r.get("meta") or {}).get("rows_written", 0) for r in results)
        log(f"  batch {i // BATCH + 1}: {len(chunk)} statements, {written} rows written")
    return sent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dump", help="the nightly .sql file (downloaded from the bucket)")
    ap.add_argument("--database-id", required=True, help="the D1 database to restore INTO (a scratch one, normally)")
    ap.add_argument("--replace", action="store_true", help="DROP the dump's tables in the target first")
    ap.add_argument("--dry-run", action="store_true", help="print the statement plan, send nothing")
    ap.add_argument("--i-mean-the-live-database", action="store_true", help="allow the id in ops/site-worker/wrangler.toml")
    ap.add_argument("--api", default=API, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    text = pathlib.Path(a.dump).read_text(encoding="utf8")
    statements = plan(split_statements(text), a.replace)
    tables = [t for t in (table_of(s) for s in statements) if t]
    inserts = sum(1 for s in statements if s.upper().startswith("INSERT"))
    print(f"{a.dump}: {len(statements)} statements — tables {', '.join(tables) or '(none)'}; {inserts} INSERTs"
          + ("; --replace drops them first" if a.replace else ""))
    if not tables:
        print("refusing: no CREATE TABLE in the file — not a dump", file=sys.stderr)
        return 2
    live = live_database_id()
    if live and a.database_id == live and not a.i_mean_the_live_database:
        print(f"refusing: {a.database_id} is the LIVE database in {WRANGLER_TOML.relative_to(ROOT)}; add --i-mean-the-live-database "
              "(and think about D1 Time Travel first)", file=sys.stderr)
        return 2
    if a.dry_run:
        for s in statements:
            print("  " + (s if len(s) < 140 else s[:137] + "…"))
        print("dry run: nothing sent")
        return 0
    token, account = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip(), os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not account:
        print("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set in the environment (typed in the shell, never in a file)", file=sys.stderr)
        return 2
    try:
        n = restore(statements, api=a.api, account=account, token=token, db=a.database_id)
    except RuntimeError as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1
    print(f"restored {n} statements into {a.database_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
