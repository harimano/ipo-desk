"""IPOWatch — the GMP page's own JSON feed.

    https://ipowatch.in/server/api/ipo/GetIpoGMPHistory

Found 13 Nov 2026 by reading the site's Next.js bundles: the page (`/ipo-grey-market-premium-latest-ipo-gmp/`) lost its
`<table>` when the site moved to Next.js that month — the "Gmp History" block renders this call client-side, with a
Mainline / SME filter over the SAME list (`Type`: 'Mainboard', 'NSE Emerge', 'BSE SME'), so mainboard and SME GMP live in
one response; the old `/sme-ipo-grey-market-premium/` page is a 404 and the sitemap has no SME GMP page. The HTML parser
that read the table (header shapes of Aug and early Nov 2026) is gone with the table.

Response (real, `data/fixtures/ipowatch/gmp-history-2026-11-13.json`):
  {"status": 1, "message": "IPO GMP Data Retrieved Successfully", "result": [
     {"id": 1149, "ipoName": "Crystal Crop Protection", "ipo_slug": "...", "ipoGmp": "₹45", "trendIcon": "fa-arrow-up",
      "trendColor": "#28A745", "priceBand": "₹259 - ₹272", "estListing": "₹317 (16.54%)", "IPODate": "18 Nov - 20 Nov",
      "Type": "Mainboard", "Status": "Upcoming", "LastUpdated": "13 Nov, 12:12"}], "jwtToken": null, "totalCount": 0}

KEY QUIRK, unchanged from the table it fed: the GMP **percentage** lives in `estListing` ('₹317 (16.54%)'), `ipoGmp` is
absolute rupees. "No grey market yet" is '₹0' with a '(0.00%)' estimate — a placeholder, never a zero premium: the row's
gmp is None (the module writes "no quote", not 0). Only the status in `status` and the list in `result` are trusted: an
answer without them raises SourceChanged, never [].

The server sends `cache-control: public, max-age=300, s-maxage=600` and its own `x-cache` — a ten-minute cache the site
declares, respected (the host is NOT in `http.CACHE_BUST_HOSTS`; the module runs half an hour apart).
"""
from __future__ import annotations

from ..errors import SourceChanged
from ._parse import clean, compute_gmp_pct, parse_money, parse_pct, upper_band

SOURCE = "ipowatch"
URL = "https://ipowatch.in/server/api/ipo/GetIpoGMPHistory"
PAGE = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"       # what the feed renders, for the notes


def parse_gmp_history(data) -> list[dict]:
    if not isinstance(data, dict):
        raise SourceChanged(SOURCE, f"expected a JSON object, got {type(data).__name__}", URL)
    if data.get("status") != 1:
        raise SourceChanged(SOURCE, f"status {data.get('status')!r}: {str(data.get('message') or '')[:80]}", URL)
    rows = data.get("result")
    if not isinstance(rows, list) or not rows:
        raise SourceChanged(SOURCE, "result missing or empty", URL)
    out: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        name = clean(raw.get("ipoName"))
        if not name:
            continue
        gmp_text, est_text = clean(raw.get("ipoGmp")), clean(raw.get("estListing"))
        gmp = parse_money(gmp_text)
        gmp_pct = parse_pct(est_text)
        if gmp == 0 and not gmp_pct:                         # '₹0' + '(0.00%)': no grey market yet, not a zero premium
            gmp, gmp_pct = None, None
        r = {
            "name": name,
            "gmp": gmp,
            "gmpPct": gmp_pct if gmp is not None else None,
            "bandHigh": upper_band(clean(raw.get("priceBand"))),
            "open": None, "close": None, "listing": None,
            "dateText": clean(raw.get("IPODate")),
            "type": clean(raw.get("Type")),
            "status": clean(raw.get("Status")),
            "updated": clean(raw.get("LastUpdated")),
            "iwId": str(raw.get("id") or "") or None,
            "source": SOURCE,
        }
        compute_gmp_pct(r)
        out.append(r)
    if not out:
        raise SourceChanged(SOURCE, f"{len(rows)} rows but none had an ipoName — field names changed?", URL)
    return out


def fetch(session) -> list[dict]:
    return parse_gmp_history(session.get_json(URL, source=SOURCE, headers={"Referer": PAGE}))
