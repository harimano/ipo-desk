"""Turn module Results into one DATA document, safely.

The rules the assembler enforces, so no module has to remember them:
  1. Start from the previous latest.json. A module that fails leaves its section exactly as it was,
     stamped stale in integrity. Nothing is ever blanked because a website was down.
  2. A module may only write keys it owns (schema.OWNERS / ROW_PATCHERS / MERGE_PATCHERS).
     Anything else is a bug and the run aborts — that is how "one owner per key" is a property of
     the code rather than a sentence in a prompt.
  3. Row patches merge by name into existing rows. Stars, applications and lot bookkeeping in the
     viewer's localStorage key off row names, so names are never rewritten here.
  4. The research layer (data/research/, data/quota-reviews/, data/investors.json) is read in and
     overlaid. The collector never writes there.
  5. meta.unresolved is MERGED: still-open items carried, module contributions appended, nothing
     dropped wholesale. The validator's delta check would refuse a wholesale rewrite anyway.
  6. Caps are applied every run (schema.CAPS) so nothing grows without bound.
  7. If every module failed, the assembler refuses to produce a document at all (exit 2), so the
     workflow commits nothing and the previous data stays live.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import pathlib
import re
from zoneinfo import ZoneInfo

from . import schema
from .result import Result

log = logging.getLogger("collector.assemble")
IST = ZoneInfo("Asia/Kolkata")


class OwnershipError(RuntimeError):
    pass


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST).replace(microsecond=0)


def label_ist(t: dt.datetime) -> str:
    return t.strftime("%-d %b %Y, %H:%M IST")


# ---------------------------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------------------------
def load_previous(path: pathlib.Path) -> dict:
    if not path.exists():
        log.warning("no previous %s — starting from an empty document", path)
        return schema.empty_data()
    data = json.loads(path.read_text(encoding="utf8"))
    for k in schema.TOP_LEVEL:
        data.setdefault(k, schema.empty_data()[k])
    return data


def slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:60]


def load_research_layer(data: dict, root: pathlib.Path) -> list[str]:
    """Overlay Claude-owned files. Returns notes for integrity."""
    notes = []
    research = root / "research"
    if research.exists():
        cur: dict = {}
        files = sorted(research.glob("*.json"))
        bodies = []
        for f in files:
            try:
                b = json.loads(f.read_text(encoding="utf8"))
            except json.JSONDecodeError as e:
                notes.append(f"research/{f.name}: does not parse ({e}) — skipped")
                continue
            bodies.append(b)
        bodies.sort(key=lambda b: (b.get("order") if b.get("order") is not None else 1e9))
        for b in bodies:
            name = b.get("name")
            if not name:
                continue
            body = {k: v for k, v in b.items() if k not in ("name", "order")}
            kind = b.get("kind", "current")          # "current" (issue sheet) or "sheet" (quota parent)
            target = "sheets" if kind == "sheet" else "current"
            data[target][name] = {**data[target].get(name, {}), **body}
        notes.append(f"research: {len(bodies)} files overlaid")
    reviews = root / "quota-reviews"
    if reviews.exists():
        by_name = {r.get("name"): r for r in data.get("quota", []) if isinstance(r, dict)}
        n = 0
        for f in sorted(reviews.glob("*.json")):
            try:
                rv = json.loads(f.read_text(encoding="utf8"))
            except json.JSONDecodeError:
                continue
            row = by_name.get(rv.get("name"))
            if not row:
                continue
            for k in ("quota", "quotaPct", "confidence"):
                if k in rv:
                    row[k] = rv[k]
            if rv.get("source"):
                row.setdefault("sources", [])
                if rv["source"] not in row["sources"]:
                    row["sources"].append(rv["source"])
            n += 1
        notes.append(f"quota-reviews: {n} rows updated")
    inv = root / "investors.json"
    if inv.exists():
        try:
            body = json.loads(inv.read_text(encoding="utf8"))
            keep_deals = data["investors"].get("bulkDeals", [])
            data["investors"] = {**data["investors"], **body.get("investors", body)}
            # the collector's deals module owns bulkDeals; the sweep's copy is a fallback only
            if keep_deals:
                data["investors"]["bulkDeals"] = keep_deals
            notes.append("investors.json overlaid (sweep-owned)")
        except json.JSONDecodeError as e:
            notes.append(f"investors.json does not parse ({e}) — kept previous")
    return notes


# ---------------------------------------------------------------------------------------------
# applying results
# ---------------------------------------------------------------------------------------------
def _rows_by_name(rows: list) -> dict[str, dict]:
    return {r.get(schema.ROW_KEY): r for r in rows if isinstance(r, dict) and r.get(schema.ROW_KEY)}


def apply(data: dict, res: Result) -> None:
    m = res.module
    for key in res.replace:
        if schema.OWNERS.get(key) != m:
            raise OwnershipError(f"module {m!r} tried to replace {key!r}, owned by {schema.OWNERS.get(key)!r}")
    for key in res.rows:
        if key not in schema.ROW_PATCHERS.get(m, set()) and schema.OWNERS.get(key) != m:
            raise OwnershipError(f"module {m!r} tried to patch rows of {key!r}")
    for key in res.merge:
        if key not in schema.MERGE_PATCHERS.get(m, set()) and schema.OWNERS.get(key) != m:
            raise OwnershipError(f"module {m!r} tried to merge into {key!r}")
    if not res.ok:
        return
    for key, value in res.replace.items():
        data[key] = value
    for key, patches in res.rows.items():
        by_name = _rows_by_name(data.get(key, []))
        missing = []
        for name, fields in patches.items():
            row = by_name.get(name)
            if row is None:
                missing.append(name)
                continue
            row.update(fields)
        if missing:
            res.notes.append(f"{key}: {len(missing)} patched names not on the board: {', '.join(missing[:5])}")
    for key, sub in res.merge.items():
        target = data.setdefault(key, {})
        if key == "sheets":
            for sheet, fields in sub.items():
                target.setdefault(sheet, {}).update(fields)
        else:
            target.update(sub)


# ---------------------------------------------------------------------------------------------
# caps + meta + integrity
# ---------------------------------------------------------------------------------------------
def _cutoff(days: int) -> str:
    return (now_ist().date() - dt.timedelta(days=days)).isoformat()


def enforce_caps(data: dict) -> None:
    c = schema.CAPS
    data["meta"]["newFindings"] = (data["meta"].get("newFindings") or [])[: c["meta.newFindings"]]
    inv = data.get("investors") or {}
    cut = _cutoff(c["investors.bulkDeals.days"])
    inv["bulkDeals"] = [d for d in inv.get("bulkDeals", []) if (d.get("date") or "9999") >= cut]
    cut = _cutoff(c["investors.moves.days"])
    inv["moves"] = [d for d in inv.get("moves", []) if (d.get("disclosedDate") or "9999") >= cut]
    cut = _cutoff(c["priceHistory.days"])
    ph = data.get("priceHistory") or {}
    for name, series in list(ph.items()):
        ph[name] = [p for p in series if isinstance(p, list) and p and str(p[0]) >= cut]
        if not ph[name]:
            del ph[name]
    fl = data.get("flows") or {}
    fl["history"] = (fl.get("history") or [])[-c["flows.history.rows"]:]
    data["news"] = (data.get("news") or [])[: c["news.rows"]]
    cut = _cutoff(c["recent.days"])
    data["recent"] = [r for r in data.get("recent", []) if (r.get("listingDate") or "9999") >= cut]


def merge_unresolved(prev: list[str], results: list) -> list[str]:
    """`meta.unresolved` is the list of things a human should look at *now*, not a log.

    Every note is tagged "[module] ...". A module that succeeded this run has just restated everything
    that is still true, so its earlier notes are replaced. A module that failed or did not run keeps its
    earlier notes — it had no chance to withdraw them. Untagged notes are from the db era, when Claude
    wrote this list by hand; no code path can ever resolve them, so they are not carried."""
    ran_ok = {r.module for r in results if r.ok}
    out: list[str] = []
    for u in prev:
        m = re.match(r"\[([a-z_]+)\] ", u) if isinstance(u, str) else None
        if m and m.group(1) not in ran_ok and u not in out:
            out.append(u)
    for r in results:
        for u in r.unresolved:
            tagged = f"[{r.module}] {u}"
            if tagged not in out:
                out.append(tagged)
    return out


def stamp(data: dict, results: list[Result], t: dt.datetime, research_notes: list[str], total_calls: int,
          elapsed: float) -> None:
    checks = []
    for r in results:
        status = "ok" if r.ok else ("blocked" if (r.error or {}).get("kind") == "blocked" else "stale")
        tried = ", ".join(f"{t.get('source')}:{'ok' if t.get('ok') else t.get('kind')}" for t in r.tried) or "—"
        note = "; ".join(r.notes) if r.notes else ""
        if not r.ok and r.error:
            note = (note + "; " if note else "") + f"kept previous — {r.error.get('detail')}"
        checks.append({"area": r.module, "method": tried, "status": status, "asOf": r.asOf,
                       "elapsed": r.elapsed, "calls": r.calls, "note": note})
    checks.append({"area": "research layer", "method": "data/research, quota-reviews, investors.json",
                   "status": "ok", "note": "; ".join(research_notes) or "none present"})
    checks.append({"area": "run", "method": "collector", "status": "ok",
                   "note": f"{elapsed:.0f}s, {total_calls} calls, {sum(1 for r in results if r.ok)}/{len(results)} modules ok"})
    data["integrity"] = {"asOf": t.isoformat(), "checks": checks,
                         "discrepancies": data.get("integrity", {}).get("discrepancies", [])[-30:]}
    data["meta"]["asOf"] = t.isoformat()
    data["meta"]["label"] = label_ist(t)


# ---------------------------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------------------------
def write(data: dict, root: pathlib.Path, t: dt.datetime) -> tuple[pathlib.Path, pathlib.Path]:
    latest = root / "latest.json"
    hist = root / "history" / f"{t.date().isoformat()}.json"
    hist.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False)
    tmp = latest.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf8")
    tmp.replace(latest)
    hist.write_text(text, encoding="utf8")
    return latest, hist


def prune_history(root: pathlib.Path, keep_days: int = 45) -> list[str]:
    """Keep every day for keep_days, Sundays forever. Mirrors the retention rule from the db era."""
    removed = []
    cut = now_ist().date() - dt.timedelta(days=keep_days)
    for f in sorted((root / "history").glob("*.json")):
        try:
            d = dt.date.fromisoformat(f.stem)
        except ValueError:
            continue
        if d < cut and d.weekday() != 6:
            f.unlink()
            removed.append(f.name)
    return removed


def snapshot_for_fallback(data: dict) -> dict:
    return {k: copy.deepcopy(data[k]) for k in schema.FALLBACK_KEYS if k in data}
