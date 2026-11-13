"""gmp — row patcher for `mainboard` / `sme`: sets gmp, gmpPct, gmpTrend on every board row it can match.

Chain: investorgain (JSON) -> ipowatch (JSON). The FIGURE is winner-takes-all like oriz-ipo's `scrape_first_available`
(ipopremium, the third, was dropped on 5 Nov 2026: it answered 403 from every network the desk runs on), with one
addition: if the winner matched fewer than half of the board's Open/Upcoming rows, the next source fills the names still
unmatched (a board name is only ever filled once, by the earliest source that had it). `gmpSrc` names the figure's source.

Since 13 Nov 2026 EVERY source is fetched every run, and the ones that did not supply a row's figure stand beside it as
the WITNESS: `gmpWitness = {src, gmp, gmpPct, agree}` — `agree` true when the two quotes are within WITNESS_TOL of the
issue price (the board's bandHigh), false beyond it, None when the figure's source had no quote and the other did. The
page prints "ipowatch says ₹32" only when agree is not true; a figure with no second quote carries gmpWitness None (a
stale witness is cleared, never left). Two grey-market sites largely relay the same dealers, so agreement is weak evidence
the figure is right — what the witness catches is a feed that stopped, a CDN serving yesterday, a parser on the wrong row.
InvestorGain stays the figure because the GMP fit in `evidence` is calibrated on its history.

Name matching: both sides are normalised (lowercase; drop "limited/ltd/ipo/mainboard/sme/nse/bse"
as whole words; drop brackets and punctuation; collapse spaces) and looked up against the board's
existing names — the board's spelling wins, GMP-site spellings never reach the board.

  * GMP rows for IPOs not on our board  -> res.notes (never added to the board)
  * board rows absent from every source -> keep their previous gmp (no patch); Open ones -> res.unresolved
  * gmpTrend = up/down/flat vs the row's previous gmp in `prev`; flat when there is no previous value
"""
from __future__ import annotations

import logging
import pathlib
import re

from ..errors import SourceError
from ..http import Session
from ..names import load_aliases
from ..result import Result
from ..sources import investorgain, ipowatch

log = logging.getLogger("collector.gmp")
ALIASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"

BOARDS = ("mainboard", "sme")
ACTIVE = {"Open", "Upcoming"}
WITNESS_TOL = 0.02          # two sites within 2% of the issue price agree (Crystal Crop at ₹272: about ₹5); `app.js` mirrors it
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


def witness(row: dict, figure: dict | None, others: list[dict]) -> dict | None:
    """The second site's quote beside the figure, or None when no other source quoted this board name."""
    if not others:
        return None
    q = others[0]
    w = {"src": q.get("source"), "gmp": q["gmp"], "gmpPct": q.get("gmpPct"), "agree": None}
    if figure is not None:
        band = row.get("bandHigh") or figure.get("bandHigh") or q.get("bandHigh")
        try:
            gap = abs(float(q["gmp"]) - float(figure["gmp"]))
            w["agree"] = gap <= WITNESS_TOL * float(band) if band else gap == 0
        except (TypeError, ValueError):
            w["agree"] = None
    return w


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
    ]


def run(session: Session, prev: dict, res: Result, attempts: list[tuple[str, callable]] | None = None) -> Result:
    rows = _board_rows(prev)
    board_index: dict[str, str] = {}
    for _, row in rows:
        board_index.setdefault(normalise(row["name"]), row["name"])
    active = [row["name"] for _, row in rows if row.get("status") in ACTIVE]
    board_names = {row["name"] for _, row in rows}
    aliases = load_aliases(ALIASES_DIR)

    matched: dict[str, dict] = {}          # board name -> the figure's source row
    quotes: dict[str, dict[str, dict]] = {}   # source -> board name -> that source's row (every source, for the witness)
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
        mine = quotes.setdefault(name, {})
        for r in good:
            alias = aliases.get(r["name"])                 # data/aliases.json: the human override, e.g. "NSE"
            bname = alias if alias in board_names else match_name(r["name"], board_index)
            if bname is None:
                off_board.append(f"{r['name']} (₹{r['gmp']:g}, {name})")
            else:
                mine.setdefault(bname, r)
        # the figure: the first source fills every name it has; a later one only while the figure covers under half of
        # the active rows (the availability fallback). Every source is still fetched, for the witness.
        covered = sum(1 for n in active if n in matched)
        added = 0
        if not winners or not active or covered * 2 < len(active):
            for bname, r in mine.items():
                if bname not in matched:
                    matched[bname] = r
                    added += 1
            winners.append(name)
            if winners[:-1]:
                log.info("gmp: the figure covered %d/%d active rows — %s fills the rest", covered, len(active), name)
        res.tried.append({"source": name, "ok": True, "matched": added})
        if name == "investorgain":
            as_of = as_of or investorgain.as_of(src_rows)

    if not winners:
        # every attempt is already in res.tried; record the last failure without appending it twice
        err = last or RuntimeError("no GMP source attempted")
        res.ok = False
        res.error = err.record() if isinstance(err, SourceError) else {"kind": "error", "detail": f"{type(err).__name__}: {err}"}
        return res

    patches: dict[str, dict[str, dict]] = {}
    tally = {"agree": 0, "differ": 0, "alone": 0}
    for key, row in rows:
        src = matched.get(row["name"])
        others = [q[row["name"]] for q in quotes.values() if row["name"] in q and q[row["name"]] is not src]
        w = witness(row, src, others)
        if w:
            tally["agree" if w["agree"] else "alone" if w["agree"] is None else "differ"] += 1
        if src is None:
            if row.get("status") == "Open":
                res.unresolved.append(f"gmp: no grey-market print found for open issue {row['name']}")
            if w or row.get("gmpWitness"):                 # a second site's quote on a row with no figure; or a stale one to clear
                patches.setdefault(key, {})[row["name"]] = {"gmpWitness": w}
            continue
        pct = src.get("gmpPct")
        if pct is None and src.get("gmp") is not None and row.get("bandHigh"):
            try:
                pct = round(float(src["gmp"]) / float(row["bandHigh"]) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                pct = None
        patch = {"gmp": src["gmp"], "gmpPct": pct, "gmpTrend": trend(src["gmp"], row.get("gmp")),
                 "gmpSrc": src.get("source"), "gmpWitness": w}
        # The feed also quotes the whole issue at the upper band. NSE's list cannot: its share count is net of
        # the anchor portion, so calendar's figure runs ~30% short on every mainboard issue (Hero Motors: 744 Cr
        # there, 1,000 Cr here). Where the feed has it, that is the issue size.
        if src.get("issueSizeCr"):
            patch["issueSizeCr"] = src["issueSizeCr"]
        patches.setdefault(key, {})[row["name"]] = patch
    res.rows = {k: v for k, v in patches.items() if v}

    res.ok, res.source, res.asOf = True, "+".join(winners), as_of
    n = sum(len(v) for v in res.rows.values())
    res.notes.append(f"gmp: {n} board rows patched via {res.source}; {len(active)} active, "
                     f"{sum(1 for a in active if a in matched)} of them matched")
    if len(quotes) > 1 or any(tally.values()):
        res.notes.append(f"gmp: second site — {tally['agree']} agree (within {WITNESS_TOL:.0%} of the issue price), "
                         f"{tally['differ']} differ, {tally['alone']} quoted by one site only")
    if off_board:
        seen = sorted(set(off_board))
        res.notes.append(f"gmp: {len(seen)} GMP-site names not on the board: " + "; ".join(seen[:8])
                         + (" …" if len(seen) > 8 else ""))
    return res
