# Module contract

Read `collector/http.py`, `collector/result.py`, `collector/schema.py`, `collector/assemble.py` first. They are short and they are the law.

A module is `collector/modules/<name>.py` exposing:

```python
from collector.http import Session
from collector.result import Result, try_chain
from collector.errors import SourceBlocked, SourceDown, SourceChanged

def run(session: Session, prev: dict, res: Result) -> Result:
    ...
    return try_chain(res, [("nse", lambda: _from_nse(session, prev, res)),
                           ("bse", lambda: _from_bse(session, prev, res)),
                           ("ipowatch", lambda: _from_ipowatch(session, prev, res))])
```

Each `_from_x` function:
- fetches via the `session` methods only (`nse_json`, `bse_json`, `get_text`, `get_json`, `post_text`, `get_bytes`) — never its own client;
- parses; **raises `SourceChanged`** if the result is empty, has zero rows, or lacks the fields it needs — an empty list is not success;
- writes its output into `res.replace` / `res.rows` / `res.merge` (only the keys its module owns — see `schema.OWNERS`, `ROW_PATCHERS`, `MERGE_PATCHERS`; the assembler aborts the run on a violation);
- returns the data's own as-of string (ISO date or datetime) or `None`.

`prev` is the previous `latest.json` — read it for carry-forward decisions (e.g. keep a row's `listingPrice` if today's source lacks it) but never mutate it.

Row keys: `name` is the stable identifier the viewer's localStorage keys off. Reuse the exact spelling already on the board (`prev["mainboard"]`) when the same issue appears under a variant name; add a helper that matches on a normalised form (lowercase, strip "limited/ltd/ipo", collapse spaces) and returns the existing name.

`res.notes` — short human-readable facts for the integrity panel ("14 issues, 3 open"). `res.unresolved` — items a human should look at, appended to `meta.unresolved`.

Fixtures and tests: put recorded or hand-made sample responses in `data/fixtures/<source>/…` and write `tests/test_<module>.py` that runs the parser against them with a fake session (a tiny class exposing the same method names returning fixture contents). Tests must pass offline with `pytest`. Every parser needs at least one "changed shape" test proving it raises `SourceChanged` rather than returning junk.

Field names must match the existing DATA schema (see `docs/DATA-SCHEMA.md`, copied from the db-era SKILL doc). Do not invent new field names when an existing one fits.
