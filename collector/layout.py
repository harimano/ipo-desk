"""Physical layout of the published document.

`docs/DATA-SCHEMA.md` is the logical schema and `data/latest.json` stays the one validated document.
This module only decides how that document is cut into files for the page, so a visit costs what
changed rather than the whole 430 KB:

    data/meta.json       meta + integrity + files{name: {hash, bytes, keys}}   — always fetched, never cached
    data/<name>.json     one file per group below, fetched as <name>.json?h=<hash> so the browser's HTTP
                         cache serves every file whose hash did not move

Groups follow how often sections change, not which screen shows them: `board` moves every run,
`research` only when Claude writes a sheet, `history` only when something lists.

    python -m collector.layout data/latest.json _site/data
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

from .schema import TOP_LEVEL

META_KEYS = ("meta", "integrity")
GROUPS: dict[str, tuple[str, ...]] = {
    "board":     ("mainboard", "sme", "recent", "lot", "priceHistory", "tape", "news", "flows"),
    "pipeline":  ("quota", "expected", "offers", "anchors", "players"),
    "investors": ("investors",),
    "research":  ("current", "sheets", "records"),
    "history":   ("listedPerf", "comps", "evidence"),
    "books":     ("anchorBooks", "trackRecords"),            # every IPO's anchor allocation since 2022: large, changes only when a book is added
}
# Parts the page does not need at boot: written like the others, listed under meta.lazy (hash, bytes) instead of
# meta.files, so boot.js leaves them alone and a screen fetches one on demand. The books part will be a few MB.
LAZY = {"books"}


def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf8")


def check_groups() -> None:
    """Every top-level key is published exactly once. A key added to the schema and forgotten here would
    silently vanish from the page, so this is an error, not a default."""
    placed = list(META_KEYS) + [k for keys in GROUPS.values() for k in keys]
    dupes = sorted({k for k in placed if placed.count(k) > 1})
    missing = sorted(set(TOP_LEVEL) - set(placed))
    unknown = sorted(set(placed) - set(TOP_LEVEL))
    if dupes or missing or unknown:
        raise ValueError(f"layout groups out of step with schema.TOP_LEVEL: "
                         f"duplicated={dupes} missing={missing} unknown={unknown}")


def split(doc: dict) -> dict[str, bytes]:
    """The document -> {filename: bytes}. Keys outside the schema are refused rather than dropped."""
    check_groups()
    extra = sorted(set(doc) - set(TOP_LEVEL))
    if extra:
        raise ValueError(f"document has top-level keys the layout does not publish: {extra}")
    out: dict[str, bytes] = {}
    files: dict[str, dict] = {}
    lazy: dict[str, dict] = {}
    for name, keys in GROUPS.items():
        body = _dump({k: doc[k] for k in keys if k in doc})
        out[f"{name}.json"] = body
        (lazy if name in LAZY else files)[name] = {"hash": hashlib.sha256(body).hexdigest()[:16], "bytes": len(body), "keys": list(keys)}
    head = {k: doc[k] for k in META_KEYS if k in doc}
    head["files"] = files
    head["lazy"] = lazy
    out["meta.json"] = _dump(head)
    return out


def join(parts: dict[str, bytes]) -> dict:
    """Inverse of split(): what the page reassembles. Used by the tests to prove nothing is lost."""
    head = json.loads(parts["meta.json"])
    files = {**head.pop("files"), **head.pop("lazy", {})}
    doc = dict(head)
    for name in files:
        doc.update(json.loads(parts[f"{name}.json"]))
    return doc


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 64
    src, out_dir = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    doc = json.loads(src.read_text(encoding="utf8"))
    parts = split(doc)
    if join(parts) != doc:
        raise SystemExit("split/join did not round-trip — refusing to publish")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, body in parts.items():
        (out_dir / name).write_bytes(body)
    sizes = ", ".join(f"{n} {len(b) / 1024:.0f} KB" for n, b in parts.items())
    print(f"layout: {sizes}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
