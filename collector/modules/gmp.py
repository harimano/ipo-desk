"""gmp — row patcher for `mainboard` / `sme`: sets gmp, gmpPct, gmpTrend on every board row it can match.

Chain: investorgain (JSON) -> ipowatch (HTML) -> ipopremium (HTML). Winner-takes-all like oriz-ipo's
`scrape_first_available`, with one addition: if the winner matched fewer than half of the board's
Open/Upcoming rows, the next source is tried for the names still unmatched and merged in (a board name
is only ever filled once, by the earliest source that had it).

Name matching: both sides are normalised (lowercase; drop "limited/ltd/ipo/mainboard/sme/nse/bse"
as whole words; drop brackets and punctuation; collapse spaces) and looked up against the board's
existing names — the board's spelling wins, GMP-site spellings never reach the board.

  * GMP rows for IPOs not on our board  -> res.notes (never added to the board)
  * board rows absent from every source -> keep their previous gmp (no patch); Open ones -> res.unresolved
  * gmpTrend = up/down/flat vs the row's previous gmp in `prev`; flat when there is no previous value
"""
from __future__ import annotations

import logging
import re

from ..errors import SourceError
from ..http import Session
from ..result import Result
from ..sources import investorgain, ipopremium, ipowatch

log = logging.getLogger("collector.gmp")

BOARDS = ("mainboard", "sme")
ACTIVE = {"Open", "Upcoming"}
_DROP_WORDS = re.compile(r"\b(limited|ltd|ipo|mainboard|mainline|sme|nse|bse)\b")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def normalise(name: str) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = s.replace("(", " ").replace(")", " ")
    s = _DROP_WORDS.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def match_name(name: str, board_index: dict[str, str]) -> str | None:
    """Return the board's own spelling for a GMP-site name, or None. Exact normalised match first;
    then a containment match only when it is unambiguous."""
    key = normalise(name)
    if not key:
        return None
    if key in board_index:
        return board_index[key]
    if len(key) < 6:
        return None
    cands = [v for k, v in board_index.items() if len(k) >= 6 and (key in k or k in key)]
    return cands[0] if len(cands) == 1 else None


def trend(new, old) -> str:
    if new is None or old is None:
        return "flat"
    try:
        new, old = float(new), float(old)
    except (TypeError, ValueError):
        return "flat"
    return "up" if new > old else "down" if new < old else "flat"


def _board_rows(prev: dict) -> list[tuple[str, dict]]:
    out = []
    for key in BOARDS:
        for row in prev.get(key) or []:
            if isinstance(row, dict) and row.get("name"):
                out.append((key, row))
    return out


def _attempts(session: Session) -> list[tuple[str, callable]]:
    return [
        ("investorgain", lambda: investorgain.fetch(session)),
        ("ipowatch", lambda: ipowatch.fetch(session)),
        ("ipopremium", lambda: ipopremium.fetch(session)),
    ]


def run(session: Session, prev: dict, res: Result, attempts: list[tuple[str, callable]] | None = None) -> Result:
    rows = _board_rows(prev)
    board_index: dict[str, str] = {}
    for _, row in rows:
        board_index.setdefault(normalise(row["name"]), row["name"])
    active = [row["name"] for _, row in rows if row.get("status") in ACTIVE]

    matched: dict[str, dict] = {}          # board name -> source row
    winners: list[str] = []
    as_of: str | None = None
    last: Exception | None = None
    off_board: list[str] = []

    for name, fn in (attempts or _attempts(session)):
        try:
            src_rows = fn()
        except SourceError as e:
            res.tried.append({**e.record(), "ok": False})
            last = e
            continue
        except Exception as e:  # a parser bug is a SourceChanged in disguise
            res.tried.append({"kind": "changed", "source": name, "detail": f"{type(e).__name__}: {e}", "ok": False})
            last = e
            continue
        good = [r for r in src_rows if r.get("name") and r.get("gmp") is not None]
        if not good:
            res.tried.append({"kind": "changed", "source": name,
                              "detail": f"parsed {len(src_rows)} rows, none had a GMP", "ok": False})
            last = RuntimeError(f"{name}: parsed {len(src_rows)} rows, none had a GMP")
            continue
        added = 0
        for r in good:
            bname = match_name(r["name"], board_index)
            if bname is None:
                off_board.append(f"{r['name']} (₹{r['gmp']:g}, {name})")
            elif bname not in matched:
                matched[bname] = r
                added += 1
        winners.append(name)
        res.tried.append({"source": name, "ok": True, "matched": added})
        if name == "investorgain":
            as_of = as_of or investorgain.as_of(src_rows)
        covered = sum(1 for n in active if n in matched)
        if not active or covered * 2 >= len(active):
            break
        log.info("gmp: %s covered %d/%d active rows — trying the next source for the rest", name, covered, len(active))

    if not winners:
        # every attempt is already in res.tried; record the last failure without appending it twice
        err = last or RuntimeError("no GMP source attempted")
        res.ok = False
        res.error = err.record() if isinstance(err, SourceError) else {"kind": "error", "detail": f"{type(err).__name__}: {err}"}
        return res

    patches: dict[str, dict[str, dict]] = {}
    for key, row in rows:
        src = matched.get(row["name"])
        if src is None:
            if row.get("status") == "Open":
                res.unresolved.append(f"gmp: no grey-market print found for open issue {row['name']}")
            continue
        pct = src.get("gmpPct")
        if pct is None and src.get("gmp") is not None and row.get("bandHigh"):
            try:
                pct = round(float(src["gmp"]) / float(row["bandHigh"]) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                pct = None
        patches.setdefault(key, {})[row["name"]] = {
            "gmp": src["gmp"],
            "gmpPct": pct,
            "gmpTrend": trend(src["gmp"], row.get("gmp")),
        }
    res.rows = {k: v for k, v in patches.items() if v}

    res.ok, res.source, res.asOf = True, "+".join(winners), as_of
    n = sum(len(v) for v in res.rows.values())
    res.notes.append(f"gmp: {n} board rows patched via {res.source}; {len(active)} active, "
                     f"{sum(1 for a in active if a in matched)} of them matched")
    if off_board:
        seen = sorted(set(off_board))
        res.notes.append(f"gmp: {len(seen)} GMP-site names not on the board: " + "; ".join(seen[:8])
                         + (" …" if len(seen) > 8 else ""))
    return res
