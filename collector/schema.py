"""The DATA shape the site renders, and who owns what.

Eighteen top-level keys. This is the same shape the Command Center has rendered since the db era
(split.py's GROUPS + PER_ITEM), so the render code needs no changes.

Ownership is by directory, not by promise:
  data/latest.json          — the collector, and only the collector
  data/research/<slug>.json — Claude (current-issue research sheets). Read in, never written.
  data/quota-reviews/…      — Claude (reservation-clause readings). Read in, never written.
  data/investors.json       — the Monday sweep (Claude + Trendlyne). Read in, never written.
CI refuses a commit that touches latest.json from anyone but the collector bot.
"""
from __future__ import annotations

TOP_LEVEL = [
    "meta", "mainboard", "sme", "recent", "expected", "offers", "lot",
    "comps", "listedPerf", "evidence", "priceHistory", "flows", "news",
    "integrity", "investors", "anchors", "quota", "current", "sheets", "records", "players", "tape", "anchorBooks", "trackRecords",
]

STATUSES = {"Open", "Upcoming", "Closed", "Listed"}
BUCKETS = {"approved", "awaited", "done", "drhp", "dropped"}
SUB_CATEGORIES = ("qib", "nii", "retail", "employee", "shareholder", "total")

# Which module is the writer of which key. A module that patches a key it does not own is a bug
# the assembler rejects.
OWNERS: dict[str, str] = {
    "mainboard": "calendar", "sme": "calendar", "lot": "calendar", "expected": "filings",
    "recent": "listings", "listedPerf": "history", "comps": "history", "evidence": "evidence", "priceHistory": "listings",
    "flows": "flows", "news": "news", "quota": "filings", "integrity": "integrity", "meta": "integrity",
    # carried forward from the previous latest.json, refreshed by other layers:
    "offers": "offers", "anchors": "details", "records": "details", "players": "players", "tape": "tape", "anchorBooks": "anchorbook", "trackRecords": "evidence", "investors": "carry", "current": "research", "sheets": "research",
}
# Modules that patch FIELDS INTO rows another module produced (by row name).
ROW_PATCHERS: dict[str, set[str]] = {
    "subscription": {"mainboard", "sme"},
    "gmp": {"mainboard", "sme"},
    "details": {"mainboard", "sme"},     # the per-IPO record: every field it has, on every listing
    "listings": {"mainboard", "sme"},
    "filings": {"quota"},
}
# Modules that shallow-merge INTO a dict another layer owns.
MERGE_PATCHERS: dict[str, set[str]] = {
    "parents": {"sheets", "investors"},     # sheets: only parentPrice; investors: only `prices`
    "deals": {"investors"},    # only bulkDeals, listingDeals, listingSymbols
    "tape": {"priceHistory"},  # one series per listing it prices from the bhavcopy (names listings does not price)
}

# Row keys are stable identifiers the site's localStorage (stars, applications) depends on.
ROW_KEY = "name"

# Caps enforced every run (invariant 7 from the rebuild doc).
CAPS = {
    "meta.newFindings": 10,
    "investors.bulkDeals.days": 45,
    "investors.listingDeals.days": 60,
    "investors.moves.days": 90,
    "priceHistory.days": 90,
    "flows.history.rows": 40,
    "news.rows": 25,
    "recent.days": 28,
}

# The fallback snapshot embedded in the page: enough for Today, Pipeline and the Board skeleton.
FALLBACK_KEYS = ["meta", "mainboard", "sme", "quota", "lot"]


def empty_data() -> dict:
    d: dict = {k: None for k in TOP_LEVEL}
    for k in ("mainboard", "sme", "recent", "expected", "comps", "listedPerf", "news", "anchors", "quota"):
        d[k] = []
    for k in ("lot", "priceHistory", "current", "sheets", "records"):
        d[k] = {}
    d["meta"] = {"asOf": None, "label": None, "unresolved": [], "awaitingData": [], "newFindings": [],
                 "marketNotes": [], "quotaSourceNote": None}
    d["players"] = {"asOf": None, "tracked": 0, "books": {}, "names": {}, "league": []}
    d["tape"] = {"asOf": None, "dates": [], "noFile": [], "names": {}}
    d["anchorBooks"] = {"asOf": None, "n": 0, "books": {}, "none": {}}
    d["trackRecords"] = {"asOf": None, "booksOn": 0, "withOutcome": 0, "investors": 0, "rows": []}
    d["evidence"] = {"asOf": None, "segments": {}, "warnings": []}
    d["offers"] = {"asOf": None, "rights": [], "buybacks": [], "ofs": [], "ncd": []}
    d["flows"] = {"latest": None, "history": [], "monthly": [], "rotation": {"fiiSelling": [], "diiBuying": []}, "note": None}
    d["investors"] = {"asOf": None, "watchlist": [], "portfolios": [], "moves": [], "holdings": [],
                      "bulkDeals": [], "listingDeals": [], "listingSymbols": {}, "insiders": [], "recentListings": [],
                      "anchorActivity": [], "notes": []}
    d["integrity"] = {"asOf": None, "checks": [], "discrepancies": []}
    return d
