"""IPOWatch — https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/

Server-rendered HTML (no JS). Header verified 2026-08-04 by oriz-ipo:
  ['IPO Name', 'IPO GMP*', 'Trend', 'Price Band', 'Est. Listing', 'Date', 'Type', 'Status', 'Last Updated']

KEY QUIRK: the GMP **percentage** lives in the 'Est. Listing' column (e.g. '₹1,116 (28.13%)'), NOT in
'IPO GMP*' ('₹245' = absolute rupees). The header row is `<tr><td><strong>…` rather than `<th>`, so the
walk reads `th,td`. 'Price Band' holds only the upper price ('₹871').

Table walk copied from chirag127/oriz-ipo `src/ipo_watch/sources/ipowatch.py` (MIT, THIRD_PARTY.md),
adapted to take the page text instead of fetching itself.
"""
from __future__ import annotations

from selectolax.parser import HTMLParser

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
        if not (any("ipo" in h for h in header) and any("gmp" in h for h in header)):
            continue
        idx = {h: i for i, h in enumerate(header)}

        def col(cells, *keys):
            for k in keys:
                for h, i in idx.items():
                    if k in h and i < len(cells):
                        return clean(cells[i].text())
            return ""

        for row in rows[1:]:
            cells = row.css("td")
            if len(cells) < 2:
                continue
            name = clean(cells[0].text())
            if not name:
                continue
            gmp_cell = col(cells, "gmp")                                    # '₹245' absolute
            est_cell = col(cells, "est. listing", "est listing", "listing")  # '₹1,116 (28.13%)'
            gmp = parse_money(gmp_cell)
            gmp_pct = parse_pct(est_cell)
            # '₹0' + '₹- (0.00%)' is IPOWatch's placeholder for "no grey market yet", not a zero premium.
            if parse_money(est_cell.split("(")[0]) is None:
                gmp, gmp_pct = None, None
            r = {
                "name": name,
                "gmp": gmp,
                "gmpPct": gmp_pct,
                "bandHigh": parse_money(col(cells, "price")),
                "open": None, "close": None, "listing": None,
                "dateText": col(cells, "date"),
                "type": col(cells, "type"),
                "status": col(cells, "status"),
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
