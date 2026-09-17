#!/usr/bin/env python3
"""Gate for the IPO dashboard data. Exits non-zero -> the caller must NOT write.

17 Sep 2026: --prev pointing at a path with no documents under it silently skipped the
delta check and printed PASS. It now fails loudly. See Phase 6 run 1 in the procedure doc."""
import json, sys, argparse, datetime as dt, pathlib

DASH_DOCS   = ["meta", "board", "market", "integrity", "investors", "anchors", "quota"]
STATUSES    = {"Open", "Upcoming", "Closed", "Listed"}
BUCKETS     = {"approved", "awaited", "done", "drhp", "dropped"}
ISO_FIELDS  = {"close","date","disclosedDate","listDate","listedDate","listing",
               "listingDate","open","recordDate","stageDate"}
FREE_TEXT   = {"dates", "when"}
MAX_DOC_BYTES = 262_144
WARN_DOC_BYTES = 200_000
MAX_ITEM_LOSS = 0.30

errors, warnings = [], []
def err(m): errors.append(m)
def warn(m): warnings.append(m)

def iso(s):
    try: dt.date.fromisoformat(s); return True
    except Exception: return False

def walk_dates(o, where):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in FREE_TEXT: continue
            if k in ISO_FIELDS and isinstance(v, str) and v.strip():
                if not iso(v): err(f"{where}: {k}={v!r} is not YYYY-MM-DD")
            else: walk_dates(v, where)
    elif isinstance(o, list):
        for x in o: walk_dates(x, where)

MIN_CENSUS = 8

def census(o, path="", acc=None):
    acc = {} if acc is None else acc
    if isinstance(o, dict):
        acc[path or "/"] = len(o)
        for k, v in o.items(): census(v, f"{path}/{k}", acc)
    elif isinstance(o, list):
        acc[path or "/"] = len(o)
        for i, v in enumerate(o):
            if isinstance(v, (dict, list)): census(v, f"{path}[]", acc)
    return acc

def load(p):
    try: return json.loads(p.read_text(encoding="utf8"))
    except Exception as e: err(f"{p.name}: does not parse — {e}"); return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docs"); ap.add_argument("--prev"); ap.add_argument("--max-age-hours", type=float, default=168)
    a = ap.parse_args()
    root = pathlib.Path(a.docs)
    docs = {}
    for name in DASH_DOCS:
        p = root / "dash" / f"{name}.json"
        if not p.exists(): err(f"missing document dash/{name}"); continue
        d = load(p)
        if d is not None:
            docs[name] = d
            sz = p.stat().st_size
            if sz > MAX_DOC_BYTES: err(f"dash/{name}: {sz:,} B exceeds the {MAX_DOC_BYTES:,} B document limit")
            elif sz > WARN_DOC_BYTES: warn(f"dash/{name}: {sz:,} B is approaching the {MAX_DOC_BYTES:,} B limit")
    for coll, minimum in (("current", 1), ("sheets", 1)):
        files = list((root / coll).glob("*.json")) if (root / coll).exists() else []
        if len(files) < minimum: err(f"collection {coll}/ has {len(files)} documents, expected >= {minimum}")
        for p in files:
            d = load(p)
            if d is not None and not d.get("name"): err(f"{coll}/{p.stem}: missing 'name'")
            if d is not None and d.get("order") is None: err(f"{coll}/{p.stem}: missing 'order' (sheet ordering)")
            if p.stat().st_size > MAX_DOC_BYTES: err(f"{coll}/{p.stem}: exceeds the {MAX_DOC_BYTES:,} B document limit")
    if errors: return report()
    meta = docs["meta"].get("meta", {})
    for k in ("asOf", "label"):
        if not meta.get(k): err(f"meta.{k} is missing or empty")
    board = docs["board"]
    for k in ("mainboard", "sme"):
        if not isinstance(board.get(k), list) or not board[k]:
            err(f"board.{k} is missing or empty")
    for k in ("mainboard", "sme"):
        for r in board.get(k, []):
            s = r.get("status")
            if s not in STATUSES: err(f"board.{k} '{r.get('name','?')}': status {s!r} not in {sorted(STATUSES)}")
    for r in docs["quota"].get("quota", []):
        b = r.get("bucket")
        if b not in BUCKETS: err(f"quota '{r.get('name','?')}': bucket {b!r} not in {sorted(BUCKETS)}")
    for name, d in docs.items(): walk_dates(d, f"dash/{name}")
    if meta.get("asOf"):
        try:
            ts = dt.datetime.fromisoformat(meta["asOf"])
            now = dt.datetime.now(ts.tzinfo)
            age = (now - ts).total_seconds() / 3600
            if age < -0.5: err(f"meta.asOf {meta['asOf']} is in the future")
            elif age > a.max_age_hours: err(f"meta.asOf is {age:.1f}h old, limit {a.max_age_hours}h")
        except Exception as e: err(f"meta.asOf {meta['asOf']!r} does not parse — {e}")
    if a.prev:
        prev = pathlib.Path(a.prev)
        matched = 0
        for name in DASH_DOCS:
            pp = prev / "dash" / f"{name}.json"
            if not pp.exists() or name not in docs: continue
            matched += 1
            old_c, new_c = census(json.loads(pp.read_text())), census(docs[name])
            for path, old in old_c.items():
                if old < MIN_CENSUS: continue
                new = new_c.get(path, 0)
                if (old - new) / old > MAX_ITEM_LOSS:
                    err(f"dash/{name}{path}: {old} -> {new} items "
                        f"({100*(old-new)/old:.0f}% loss, limit {100*MAX_ITEM_LOSS:.0f}%)")
        # A --prev that resolves to nothing used to skip the delta check in silence.
        # That is the single most dangerous state this script can be in: it prints
        # PASS while checking nothing. Fail loudly instead.
        if matched == 0:
            err(f"--prev {a.prev!r} matched no documents — expected {a.prev}/dash/<name>.json. "
                f"The delta check DID NOT RUN. Fix the path; do not write unchecked data.")
        elif matched < len(DASH_DOCS):
            warn(f"--prev matched only {matched} of {len(DASH_DOCS)} dash documents — "
                 f"the delta check covered part of the data only")
    return report()

def report():
    for w in warnings: print(f"WARN  {w}")
    if errors:
        print(f"\nFAIL — {len(errors)} error(s); do not write:")
        for e in errors[:25]: print(f"  · {e}")
        if len(errors) > 25: print(f"  · ... and {len(errors)-25} more")
        return 1
    print("PASS — data is safe to write")
    return 0

sys.exit(main())
