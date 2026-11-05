"""IPOWatch — https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/

Server-rendered HTML (no JS). Header verified 2026-08-04 by oriz-ipo:
  ['IPO Name', 'IPO GMP*', 'Trend', 'Price Band', 'Est. Listing', 'Date', 'Type', 'Status', 'Last Updated']
Since Nov 2026 (`board-2026-11.html`, caught by the gmp "changed" note on /admin):
  ['Company', 'GMP*', 'Trend', 'Price Band', 'Est. Gain', 'Date'] — the name is an <a>, the status a <span> under it
  in the same cell, no Type column, and "no grey market yet" is '₹0' with Est. Gain = the band ('₹105 (0.00%)').
Both shapes parse; a third raises SourceChanged.

KEY QUIRK: the GMP **percentage** lives in the 'Est. Listing' column (e.g. '₹1,116 (28.13%)'), NOT in
'IPO GMP*' ('₹245' = absolute rupees). The header row is `<tr><td><strong>…` rather than `<th>`, so the
walk reads `th,td`. 'Price Band' holds only the upper price ('₹871').

Table walk copied from chirag127/oriz-ipo `src/ipo_watch/sources/ipowatch.py` (MIT, THIRD_PARTY.md),
adapted to take the page text instead of fetching itself.
"""
from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..errors import SourceChanged
from ._parse import clean, compute_gmp_pct, parse_money, parse_pct

SOURCE = "ipowatch"
URL = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"


def parse_ipowatch(html: str) -> list[dict]:
    tree = HTMLParser(html or "")
    out: list[dict] = []
    for table in tree.css("table"):
        rows = table.css("tr")
        if len(rows) < 2:
            continue
        header = [clean(c.text()).lower() for c in rows[0].css("th,td")]
        if not (any("ipo" in h or "company" in h for h in header) and any("gmp" in h for h in header)):
            continue
        idx = {h: i for i, h in enumerate(header)}

        def col(cells, *keys, idx=idx):
            for k in keys:
                for h, i in idx.items():
                    if k in h and i < len(cells):
                        return clean(cells[i].text())
            return ""

        for row in rows[1:]:
            cells = row.css("td")
            if len(cells) < 2:
                continue
            link = cells[0].css_first("a")
            name = clean(link.text()) if link else clean(cells[0].text())
            if not name:
                continue
            badge = cells[0].css_first("span")                              # Nov 2026: 'Open' / 'Closed' under the name
            status = col(cells, "status") or (clean(badge.text()) if badge else "")
            gmp_cell = col(cells, "gmp")                                    # '₹245' absolute
            est_cell = col(cells, "est. listing", "est listing", "est. gain", "listing", "gain")  # '₹1,116 (28.13%)'
            gmp = parse_money(gmp_cell)
            gmp_pct = parse_pct(est_cell)
            # "No grey market yet" is a placeholder, not a zero premium: '₹0' + '₹- (0.00%)' (Aug 2026 shape) or
            # '₹0' + '₹105 (0.00%)' (Nov 2026). The collector would otherwise patch a real 0 onto the board.
            if parse_money(est_cell.split("(")[0]) is None or (gmp == 0 and not gmp_pct):
                gmp, gmp_pct = None, None
            r = {
                "name": name,
                "gmp": gmp,
                "gmpPct": gmp_pct,
                "bandHigh": parse_money(col(cells, "price")),
                "open": None, "close": None, "listing": None,
                "dateText": col(cells, "date"),
                "type": col(cells, "type"),
                "status": status,
                "source": SOURCE,
            }
            compute_gmp_pct(r)
            out.append(r)
        if out:
            break
    if not out:
        raise SourceChanged(SOURCE, "no GMP table rows parsed", URL)
    return out


def fetch(session) -> list[dict]:
    return parse_ipowatch(session.get_text(URL, source=SOURCE))
