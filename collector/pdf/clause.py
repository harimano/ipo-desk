"""Find the shareholder-reservation clause in a DRHP/RHP.

    python -m collector.pdf.clause file.pdf          # prints the JSON result

Approach (learned from ipo-radar's section_extractor, written fresh): one PyMuPDF pass, page by
page, regex for the clause; chapters located from `doc.get_toc()` bookmarks with a rapidfuzz
token_set_ratio >= 82 against chapter synonyms, falling back to a heading scan of page tops.

Result:
  {found: bool, pages: [1-indexed page numbers with a hit], definition: str|None,
   excerpt: str|None, parent_mentioned: str|None, pageCount: int, scanned: int, capped: bool,
   chapters: {key: [start, end]}}

Hard caps: at most 600 pages are read; pages with fewer than 40 characters of text are skipped.
"""
from __future__ import annotations

import json
import re
import sys

try:  # optional at import time so the collector still starts if the wheel is missing
    import pymupdf as fitz  # PyMuPDF >= 1.24 name; `fitz` is the deprecated alias
except ImportError:  # pragma: no cover
    try:
        import fitz
    except ImportError:
        fitz = None
try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None

MAX_PAGES = 600
MIN_CHARS = 40
FUZZY_THRESHOLD = 82
EXCERPT_CHARS = 600

CLAUSE_RE = re.compile(
    r"eligible\s+shareholders?|shareholders?\s+reservation\s+portion|reservation\s+for\s+eligible\s+shareholders?",
    re.I)
DEFN_RE = re.compile(
    r"[\"“”']?\s*Eligible\s+Shareholders?(?:\s*\(s\))?\s*[\"“”']?\s*[:\-–]?\s*"
    r"(?:means|shall\s+mean|refers?\s+to|shall\s+refer\s+to)\b",
    re.I)
PARENT_RE = re.compile(
    r"(?:equity\s+)?shareholders?\s+of\s+(?:our\s+)?(?:promoters?,?\s+)?(?:the\s+)?"
    r"([A-Z][A-Za-z0-9&.,'\- ]{2,80}?(?:Limited|Ltd\.?))",
    re.S)

# Chapters worth knowing about, in typical order. Synonyms feed the fuzzy bookmark match; the
# heading regex is for the page-top scan when a PDF has no bookmarks.
CHAPTERS: list[dict] = [
    {"key": "definitions", "synonyms": ["definitions and abbreviations", "definitions"],
     "heading": r"DEFINITIONS(?: AND ABBREVIATIONS)?"},
    {"key": "offer_summary", "synonyms": ["offer document summary", "summary of the offer document"],
     "heading": r"(?:OFFER DOCUMENT SUMMARY|SUMMARY OF THE OFFER DOCUMENT)"},
    {"key": "the_offer", "synonyms": ["the offer", "the issue", "summary of the offer"],
     "heading": r"(?:THE OFFER|THE ISSUE)"},
    {"key": "terms_of_offer", "synonyms": ["terms of the offer", "terms of the issue"],
     "heading": r"TERMS OF THE (?:OFFER|ISSUE)"},
    {"key": "offer_structure", "synonyms": ["offer structure", "issue structure"],
     "heading": r"(?:OFFER|ISSUE) STRUCTURE"},
    {"key": "offer_procedure", "synonyms": ["offer procedure", "issue procedure"],
     "heading": r"(?:OFFER|ISSUE) PROCEDURE"},
]
OFFER_CHAPTERS = ("offer_structure", "the_offer", "offer_summary", "terms_of_offer")


def _normalize(title: str) -> str:
    t = re.sub(r"section\s+[ivxlc]+\s*[-–:.]?\s*", "", (title or "").strip().lower())
    return re.sub(r"[^a-z ]+", " ", t).strip()


def _match_chapter(title: str) -> tuple[str, float] | None:
    norm = _normalize(title)
    if not norm:
        return None
    best: tuple[str, float] | None = None
    best_gap = 99
    for spec in CHAPTERS:
        for syn in spec["synonyms"]:
            if fuzz is not None:
                score = float(fuzz.token_set_ratio(norm, syn))
            else:  # crude fallback: exact-or-substring
                score = 100.0 if norm == syn or syn in norm else 0.0
            # token_set_ratio scores a subset as 100 ("the offer" vs "summary of the offer document"),
            # so ties go to the synonym whose length is closest to the title's
            gap = abs(len(syn.split()) - len(norm.split()))
            if score >= FUZZY_THRESHOLD and (best is None or score > best[1] or (score == best[1] and gap < best_gap)):
                best, best_gap = (spec["key"], score), gap
    return best


def _chapters_from_toc(toc: list, page_count: int) -> dict[str, int]:
    found: dict[str, tuple[int, float]] = {}
    for entry in toc or []:
        try:
            level, title, page = entry[0], entry[1], int(entry[2])
        except (TypeError, ValueError, IndexError):
            continue
        if level > 2 or page < 1 or page > page_count:
            continue
        m = _match_chapter(title)
        if m and (m[0] not in found or m[1] > found[m[0]][1]):
            found[m[0]] = (page, m[1])
    return {k: v[0] for k, v in found.items()}


def _chapters_from_headings(pages: dict[int, str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for spec in CHAPTERS:
        pat = re.compile(rf"^\s*(?:SECTION\s+[IVXLC]+\s*[-–:.]?\s*)?{spec['heading']}\s*$", re.M)
        for n in sorted(pages):
            head = "\n".join(pages[n].splitlines()[:12])
            if pat.search(head):
                found[spec["key"]] = n
                break
    return found


def _spans(starts: dict[str, int], page_count: int) -> dict[str, list[int]]:
    """Each chapter runs from its start page to the page before the next chapter start."""
    if not starts:
        return {}
    order = sorted(starts.items(), key=lambda kv: kv[1])
    spans: dict[str, list[int]] = {}
    for i, (key, start) in enumerate(order):
        end = order[i + 1][1] - 1 if i + 1 < len(order) else page_count
        spans[key] = [start, max(start, end)]
    return spans


def _in(spans: dict[str, list[int]], keys, page: int) -> bool:
    return any(k in spans and spans[k][0] <= page <= spans[k][1] for k in keys)


def _window(text: str, pos: int, width: int = EXCERPT_CHARS) -> str:
    lo = max(0, pos - width // 3)
    hi = min(len(text), lo + width)
    return re.sub(r"[ \t]+", " ", text[lo:hi]).strip()


def _definition(text: str) -> str | None:
    m = DEFN_RE.search(text)
    if not m:
        return None
    tail = text[m.start():m.start() + 900]
    # stop at a blank line or at the next definition-looking line ("Something means ...")
    cut = re.search(r"\n\s*\n|\n(?=[\"“]?[A-Z][A-Za-z ()/\-]{2,60}[\"”]?\s+(?:means|shall mean)\b)", tail[20:])
    if cut:
        tail = tail[: 20 + cut.start()]
    return re.sub(r"\s+", " ", tail).strip(" \"“”'")


def _parent(*texts: str | None) -> str | None:
    for t in texts:
        if not t:
            continue
        m = PARENT_RE.search(t)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" ,")
    return None


def find_reservation_clause(pdf_bytes: bytes, *, max_pages: int = MAX_PAGES) -> dict:
    if fitz is None:
        raise RuntimeError("PyMuPDF (pymupdf) is not installed")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page_count = doc.page_count
        limit = min(page_count, max_pages)
        pages: dict[int, str] = {}
        hits: list[tuple[int, int]] = []          # (page, offset)
        for i in range(limit):
            text = doc[i].get_text("text") or ""
            if len(text.strip()) < MIN_CHARS:
                continue
            n = i + 1
            pages[n] = text
            m = CLAUSE_RE.search(text)
            if m:
                hits.append((n, m.start()))
        try:
            toc = doc.get_toc(simple=True)
        except Exception:  # a broken outline is not a reason to give up
            toc = []
        starts = _chapters_from_toc(toc, page_count)
        if not starts:
            starts = _chapters_from_headings(pages)
        spans = _spans(starts, page_count)
    finally:
        doc.close()

    definition = None
    for n in sorted(pages):
        if "definitions" in spans and not _in(spans, ("definitions",), n):
            continue
        d = _definition(pages[n])
        if d:
            definition = d
            break
    if definition is None and "definitions" in spans:   # bookmarks lied; scan everything once
        for n in sorted(pages):
            d = _definition(pages[n])
            if d:
                definition = d
                break

    excerpt = None
    excerpt_page = None
    for n, off in hits:
        if _in(spans, OFFER_CHAPTERS, n):
            excerpt, excerpt_page = _window(pages[n], off), n
            break
    if excerpt is None and hits:
        n, off = hits[0]
        excerpt, excerpt_page = _window(pages[n], off), n

    return {
        "found": bool(hits),
        "pages": [n for n, _ in hits],
        "definition": definition,
        "excerpt": excerpt,
        "excerptPage": excerpt_page,
        "parent_mentioned": _parent(definition, excerpt),
        "pageCount": page_count,
        "scanned": limit,
        "capped": page_count > max_pages,
        "chapters": spans,
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m collector.pdf.clause file.pdf", file=sys.stderr)
        return 2
    with open(argv[0], "rb") as f:
        data = f.read()
    if not data.startswith(b"%PDF"):
        print(f"{argv[0]}: not a PDF (no %PDF magic)", file=sys.stderr)
        return 1
    out = find_reservation_clause(data)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["found"] else 1


if __name__ == "__main__":
    sys.exit(main())
