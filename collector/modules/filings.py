"""filings — the quota radar. Row patcher for `quota`: stage, bucket, stageDate, recordDate,
listingDate, isNew, needsReview ONLY. It never writes quota / quotaPct / confidence / sources:
those come from data/quota-reviews/ (a human reading of the reservation clause) via the assembler.

What it does each run:
  (a) builds the parent watchlist from prev["quota"] rows (ticker + parentFull) joined to the BSE
      scrip-code map in collector/sources/parents.json;
  (b) polls BSE corporate announcements for each parent over the last 3 days and, for a headline
      matching HEADLINE_RE, advances the row (DRHP filed -> bucket drhp; observation letter -> approved;
      RHP -> approved, stage "RHP filed") and sets needsReview {source, url, headline, date};
  (c) diffs page 1 of SEBI's DRHP and RHP registers against prev to catch filings the parent did
      not announce, matching subsidiary names to quota row names after normalisation;
  (d) moves rows whose listingDate is now past to bucket done.

Both bse_ann and sebi are attempted every run; the module is ok if EITHER answered, and res.notes
records which. A row nothing mentioned keeps its previous stage (no patch). Stages never regress:
a DRHP headline for a row already approved only flags needsReview.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import re
from zoneinfo import ZoneInfo

from ..errors import SourceChanged, SourceError
from ..http import Session
from ..result import Result
from ..sources import bse_ann, sebi

log = logging.getLogger("collector.filings")
IST = ZoneInfo("Asia/Kolkata")
PARENTS_FILE = pathlib.Path(__file__).resolve().parent.parent / "sources" / "parents.json"

LOOKBACK_DAYS = 3
NEW_FOR_DAYS = 14
ALLOWED_FIELDS = {"stage", "bucket", "stageDate", "recordDate", "listingDate", "isNew", "needsReview"}
FORBIDDEN_FIELDS = {"quota", "quotaPct", "confidence", "sources"}

HEADLINE_RE = re.compile(
    r"draft red herring|DRHP|red herring|RHP|initial public offer|IPO of .*subsidiary|observation letter", re.I)
_OBS_RE = re.compile(r"observation\s+letter|final\s+observations?", re.I)
_DRHP_RE = re.compile(r"draft\s+red\s+herring|\bU?DRHP\b", re.I)
_RHP_RE = re.compile(r"red\s+herring|\bRHP\b", re.I)
_UPDATED_DRHP_RE = re.compile(r"updated\s+draft|\bUDRHP\b|addendum|corrigendum", re.I)

# bucket rank: a transition may only move a row forward
RANK = {"dropped": -1, "awaited": 0, "drhp": 1, "approved": 2, "done": 3}
_DROP_WORDS = re.compile(
    r"\b(limited|ltd|ipo|drhp|rhp|red|herring|prospectus|draft|dated|private|pvt|updated|udrhp|"
    r"filed|filing|the|of|by|and|for|with|its|intimation|subsidiary)\b")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def normalise(name: str) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = _PUNCT.sub(" ", s)
    s = _DROP_WORDS.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def classify_headline(headline: str) -> dict | None:
    """Map a BSE/SEBI headline to a stage transition.
    Returns {"stage", "bucket", "kind"} or None when the headline is not about a filing.
    kind "generic" (IPO mentioned, no document named) carries stage/bucket None: flag only."""
    if not headline or not HEADLINE_RE.search(headline):
        return None
    if _OBS_RE.search(headline):
        return {"stage": "SEBI observations received", "bucket": "approved", "kind": "observation"}
    if _DRHP_RE.search(headline):
        if _UPDATED_DRHP_RE.search(headline):
            return {"stage": "UDRHP filed", "bucket": "drhp", "kind": "udrhp"}
        return {"stage": "DRHP filed", "bucket": "drhp", "kind": "drhp"}
    if _RHP_RE.search(headline):
        return {"stage": "RHP filed", "bucket": "approved", "kind": "rhp"}
    return {"stage": None, "bucket": None, "kind": "generic"}


def load_parents(path: pathlib.Path = PARENTS_FILE) -> dict[str, dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("parents.json unreadable (%s); BSE polling has no scrip codes", e)
        return {}
    return {k.upper(): v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict) and v.get("scrip")}


def watchlist(prev: dict, parents: dict[str, dict]) -> dict[str, dict]:
    """ticker -> {scrip, name, rows: [quota rows]}. Rows with a ticker we have no scrip for are
    still listed (scrip None) so SEBI matching covers them."""
    out: dict[str, dict] = {}
    for row in prev.get("quota") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        t = (row.get("ticker") or "").upper().strip()
        if not t:
            continue
        p = parents.get(t, {})
        entry = out.setdefault(t, {"scrip": p.get("scrip"), "name": row.get("parentFull") or p.get("name"), "rows": []})
        entry["rows"].append(row)
    return out


def _today() -> dt.date:
    return dt.datetime.now(IST).date()


def _transition(row: dict, cls: dict, evidence: dict, patches: dict, today: dt.date) -> bool:
    """Apply a classified filing to a row. Returns True when stage/bucket actually changed."""
    name = row["name"]
    prev_review = row.get("needsReview") or {}
    if evidence.get("url") and prev_review.get("url") == evidence.get("url"):
        return False                       # seen on an earlier run; do not re-stamp or re-flag
    patch = patches.setdefault(name, {})
    if patch.get("needsReview") and (patch["needsReview"].get("date") or "") > (evidence.get("date") or ""):
        return False                       # a newer filing already flagged this row in this run
    patch["needsReview"] = evidence
    if cls.get("kind") == "generic" or not cls.get("bucket"):
        return False
    cur_bucket = patch.get("bucket") or row.get("bucket") or "awaited"
    cur_rank = RANK.get(cur_bucket, 0)
    new_rank = RANK.get(cls["bucket"], 0)
    if cur_bucket == "done":
        return False
    if new_rank < cur_rank:
        return False                       # never regress; needsReview already set
    if new_rank == cur_rank and (patch.get("stage") or row.get("stage")) == cls["stage"]:
        return False                       # same stage already
    patch["stage"] = cls["stage"]
    patch["bucket"] = cls["bucket"]
    patch["stageDate"] = evidence.get("date") or today.isoformat()
    patch["isNew"] = True
    return True


# ---------------------------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------------------------
def _from_bse(session: Session, wl: dict[str, dict], patches: dict, res: Result, today: dt.date) -> str | None:
    polled, answered, hits, errors = 0, 0, 0, []
    since = today - dt.timedelta(days=LOOKBACK_DAYS)
    for ticker, p in wl.items():
        if not p.get("scrip"):
            continue
        polled += 1
        try:
            rows = bse_ann.fetch(session, p["scrip"], since, today, source="bse_ann")
        except SourceError as e:
            errors.append(f"{ticker}: {e.detail}")
            continue
        answered += 1
        rows = [r for r in rows if HEADLINE_RE.search(r["headline"]) or HEADLINE_RE.search(r.get("subject") or "")]
        rows.sort(key=lambda r: (r.get("date") or ""), reverse=True)
        for ann in rows:
            cls = classify_headline(ann["headline"]) or classify_headline(ann.get("subject") or "")
            if not cls:
                continue
            evidence = {"source": "bse_ann", "url": ann.get("url"), "headline": ann["headline"], "date": ann.get("date")}
            targets = _rows_for_announcement(p["rows"], ann["headline"])
            for row in targets:
                if _transition(row, cls, evidence, patches, today):
                    hits += 1
    if polled == 0:
        raise SourceChanged("bse_ann", "no parent has a BSE scrip code; nothing to poll")
    if answered == 0:
        raise SourceChanged("bse_ann", "no parent answered: " + "; ".join(errors[:3]))
    note = f"bse_ann: {answered}/{polled} parents answered, {hits} stage changes"
    if errors:
        note += f", {len(errors)} errors"
    res.notes.append(note)
    return today.isoformat()


def _rows_for_announcement(rows: list[dict], headline: str) -> list[dict]:
    """A parent's announcement names the subsidiary when it can; match on that, else every row of the
    parent gets the flag (one parent usually has one live candidate)."""
    h = normalise(headline)
    named = [r for r in rows if normalise(r["name"]) and normalise(r["name"]) in h]
    return named or rows


def _from_sebi(session: Session, wl: dict[str, dict], prev: dict, patches: dict, res: Result,
               today: dt.date) -> str | None:
    index: list[tuple[str, dict]] = []
    for p in wl.values():
        for row in p["rows"]:
            key = normalise(row["name"])
            if len(key) >= 4:
                index.append((key, row))
    kinds_ok, matched, listed = [], 0, 0
    errors = []
    for kind in ("DRHP", "RHP"):
        try:
            rows = sebi.fetch_listing(session, kind, 1, source="sebi")
        except SourceError as e:
            errors.append(f"{kind}: {e.detail}")
            continue
        kinds_ok.append(kind)
        listed += len(rows)
        for f in rows:
            if f.get("kind") not in ("DRHP", "RHP"):
                continue        # addenda / prospectus registers do not move a stage
            t = normalise(f["title"])
            for key, row in index:
                if key not in t:
                    continue
                cls = classify_headline(f["title"]) or {"stage": f"{f['kind']} filed",
                                                        "bucket": "drhp" if f["kind"] == "DRHP" else "approved",
                                                        "kind": f["kind"].lower()}
                evidence = {"source": "sebi", "url": f["detailUrl"], "headline": f["title"], "date": f.get("date")}
                if _transition(row, cls, evidence, patches, today):
                    matched += 1
    if not kinds_ok:
        raise SourceChanged("sebi", "; ".join(errors) or "no register answered")
    res.notes.append(f"sebi: {'+'.join(kinds_ok)} page 1 ({listed} rows), {matched} stage changes")
    if errors:
        res.notes.append("sebi partial: " + "; ".join(errors))
    return today.isoformat()


def _expire(prev: dict, patches: dict, today: dt.date) -> int:
    moved = 0
    for row in prev.get("quota") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        ld = row.get("listingDate")
        if ld and isinstance(ld, str) and ld[:10] < today.isoformat() and row.get("bucket") != "done":
            p = patches.setdefault(row["name"], {})
            p["bucket"] = "done"
            p["stage"] = "Listed"
            p["stageDate"] = ld[:10]
            moved += 1
        # isNew decays after NEW_FOR_DAYS
        if row.get("isNew") and row.get("stageDate") and row["name"] not in patches:
            try:
                age = (today - dt.date.fromisoformat(row["stageDate"][:10])).days
            except ValueError:
                age = 0
            if age > NEW_FOR_DAYS:
                patches[row["name"]] = {"isNew": False}
    return moved


# ---------------------------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------------------------
def run(session: Session, prev: dict, res: Result) -> Result:
    today = _today()
    parents = load_parents()
    wl = watchlist(prev, parents)
    patches: dict[str, dict] = {}
    if not wl:
        res.notes.append("quota: no rows with a ticker in prev; nothing to watch")
    wins: list[str] = []
    last: Exception | None = None
    for name, fn in (("bse_ann", lambda: _from_bse(session, wl, patches, res, today)),
                     ("sebi", lambda: _from_sebi(session, wl, prev, patches, res, today))):
        try:
            fn()
            res.tried.append({"source": name, "ok": True})
            wins.append(name)
        except SourceError as e:
            res.tried.append({**e.record(), "ok": False})
            last = e
        except Exception as e:  # parser bug == SourceChanged in disguise
            res.tried.append({"kind": "changed", "source": name, "detail": f"{type(e).__name__}: {e}", "ok": False})
            last = e
    moved = _expire(prev, patches, today)
    if moved:
        res.notes.append(f"{moved} rows past listingDate moved to done")

    # belt and braces: the assembler enforces ownership, but a forbidden field here is our bug
    for name, fields in patches.items():
        bad = set(fields) - ALLOWED_FIELDS
        if bad:
            raise RuntimeError(f"filings tried to write {sorted(bad)} on {name!r}")
    res.rows["quota"] = patches
    kept = sum(1 for r in prev.get("quota") or [] if isinstance(r, dict) and r.get("name") not in patches)
    res.notes.append(f"{len(patches)} rows patched, {kept} kept previous stage")
    if wins:
        res.ok, res.source, res.asOf = True, "+".join(wins), today.isoformat()
        return res
    err = last or RuntimeError("no sources attempted")
    res.ok = False
    res.error = err.record() if isinstance(err, SourceError) else {"kind": "error", "detail": f"{type(err).__name__}: {err}"}
    return res
