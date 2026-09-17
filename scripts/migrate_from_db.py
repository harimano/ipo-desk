#!/usr/bin/env python3
"""One-time migration from the artifact-db era.

  python3 scripts/migrate_from_db.py <dir with dash/ current/ sheets/> [--seed]

Reassembles the 24 documents into data/latest.json (the inverse of split.py, same as boot.js's
assemble()), moves current/ and sheets/ into data/research/ as Claude-owned files, and with --seed
merges data/seed/{listedPerf,comps}.json (ipo-radar's 2005-2026 dataset) into the history sections.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DASH = ["meta", "board", "market", "integrity", "investors", "anchors", "quota"]


def slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:60]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = pathlib.Path(sys.argv[1])
    seed = "--seed" in sys.argv
    data: dict = {}
    for d in DASH:
        data.update(json.loads((src / "dash" / f"{d}.json").read_text(encoding="utf8")))

    research = ROOT / "data" / "research"
    research.mkdir(parents=True, exist_ok=True)
    moved = 0
    for coll, kind in (("current", "current"), ("sheets", "sheet")):
        data[coll] = {}
        bodies = [json.loads(f.read_text(encoding="utf8")) for f in sorted((src / coll).glob("*.json"))]
        bodies.sort(key=lambda b: (b.get("order") if b.get("order") is not None else 1e9))
        for b in bodies:
            name = b["name"]
            body = {k: v for k, v in b.items() if k not in ("name", "order")}
            data[coll][name] = body
            out = research / f"{slug(name)}.json"
            out.write_text(json.dumps({"name": name, "kind": kind, "order": b.get("order"), **body},
                                      ensure_ascii=False, indent=1), encoding="utf8")
            moved += 1
    print(f"research: {moved} files written to data/research/")

    # the sweep's document becomes its own file, so ownership is visible in the tree
    inv = ROOT / "data" / "investors.json"
    inv.write_text(json.dumps({"investors": data["investors"]}, ensure_ascii=False, indent=1), encoding="utf8")
    print("investors.json written (Monday-sweep-owned)")

    if seed:
        for key in ("listedPerf", "comps"):
            f = ROOT / "data" / "seed" / f"{key}.json"
            if not f.exists():
                continue
            rows = json.loads(f.read_text(encoding="utf8"))
            have = {r.get("name") for r in data.get(key, [])}
            added = [r for r in rows if r.get("name") not in have]
            data[key] = list(data.get(key, [])) + added
            print(f"seed: {key} +{len(added)} rows (now {len(data[key])})")

    data.setdefault("meta", {}).setdefault("unresolved", [])
    data["meta"]["unresolved"] = [u for u in data["meta"]["unresolved"] if "db migration" not in u.lower()]
    data["meta"]["marketNotes"] = (data["meta"].get("marketNotes") or [])[:5]

    out = ROOT / "data" / "latest.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf8")
    print(f"latest.json: {out.stat().st_size // 1024} KB, keys: {len(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
