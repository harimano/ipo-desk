"""The contract every module returns. Modules never touch DATA directly; they hand back a Result and
the assembler applies it. That is what keeps a module failure local.

A module MUST:
  * raise (or return ok=False) when it fetched nothing usable — an empty list is not success;
  * say which source actually answered (primary or which fallback), so integrity can show it;
  * stamp asOf with the data's own date where the source gives one, else the run time.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .errors import SourceError


@dataclass
class Result:
    module: str
    ok: bool = False
    source: str | None = None            # e.g. "nse", "bse", "ipowatch" — the one that won
    asOf: str | None = None              # ISO date or datetime the data is as-of
    elapsed: float = 0.0
    calls: int = 0
    error: dict | None = None            # SourceError.record() of the last failure, if not ok
    tried: list[dict] = field(default_factory=list)   # every source attempted, with outcome
    replace: dict = field(default_factory=dict)       # top-level key -> new value (owned keys only)
    rows: dict = field(default_factory=dict)          # key -> {row name -> {field: value}}
    merge: dict = field(default_factory=dict)         # key -> {subkey: value} shallow merge
    notes: list[str] = field(default_factory=list)    # human-readable, goes to integrity.checks note
    unresolved: list[str] = field(default_factory=list)  # items for meta.unresolved (merged, never replaced)

    def fail(self, err: SourceError | Exception, source: str | None = None) -> "Result":
        self.ok = False
        rec = err.record() if isinstance(err, SourceError) else {"kind": "error", "detail": f"{type(err).__name__}: {err}"}
        if source:
            rec["source"] = source
        self.error = rec
        self.tried.append({**rec, "ok": False})
        return self

    def won(self, source: str, asOf: str | None = None) -> "Result":
        self.ok, self.source, self.asOf = True, source, asOf or self.asOf
        self.tried.append({"source": source, "ok": True})
        return self


class Timer:
    def __init__(self):
        self.t0 = time.monotonic()

    def __call__(self) -> float:
        return round(time.monotonic() - self.t0, 2)


def try_chain(result: Result, attempts: list[tuple[str, callable]]) -> Result:
    """Run (source_name, fn) pairs in order; the first that returns without raising wins.
    fn() must raise a SourceError on anything short of usable data, and return the asOf string
    (or None) on success — it should have populated result.replace/rows/merge itself."""
    last: Exception | None = None
    for name, fn in attempts:
        try:
            as_of = fn()
            return result.won(name, as_of)
        except SourceError as e:
            result.tried.append({**e.record(), "ok": False})
            last = e
        except Exception as e:  # a parser bug is a SourceChanged in disguise; record, keep going
            result.tried.append({"kind": "changed", "source": name, "detail": f"{type(e).__name__}: {e}", "ok": False})
            last = e
    return result.fail(last or RuntimeError("no sources attempted"))
