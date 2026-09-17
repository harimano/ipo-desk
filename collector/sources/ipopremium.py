"""IPOPremium — https://ipopremium.in/

Server-rendered HTML. Header verified 2026-08-04 by oriz-ipo:
  ['Company Name', 'Type', 'GMP (₹)', 'Open', 'Close', 'Price Band (₹)', 'Listing Date']

GMP is absolute rupees ('249'); price band is 'low–high' ('829–871', en-dash). The % is computed from
GMP / upper band. Names carry '(Mainboard)' / '(SME)' suffixes — the normaliser in modules/gmp strips them.

Table walk copied from chirag127/oriz-ipo `src/ipo_watch/sources/ipopremium.py` (MIT, THIRD_PARTY.md),
adapted to take the page text instead of fetching itself.
"""
from __future__ import annotations

from selectolax.parser import HTMLParser

from ..errors import SourceChanged
from ._parse import clean, compute_gmp_pct, parse_money, upper_band

SOURCE = "ipopremium"
URL = "https://ipopremium.in/"


def parse_ipopremium(html: str) -> list[dict]:
    tree = HTMLParser(html or "")
    out: list[dict] = []
    for table in tree.css("table"):
        rows = table.css("tr")
        if len(rows) < 2:
            continue
        header = [clean(c.text()).lower() for c in rows[0].css("th,td")]
        if not (any("gmp" in h for h in header)
                and any(("company" in h or "name" in h) for h in header)):
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
            r = {
                "name": name,
                "gmp": parse_money(col(cells, "gmp")),
                "gmpPct": None,
                "bandHigh": upper_band(col(cells, "price band", "band", "price")),
                "open": col(cells, "open") or None,
                "close": col(cells, "close") or None,
                "listing": col(cells, "listing") or None,
                "type": col(cells, "type"),
                "status": "",
                "source": SOURCE,
            }
            compute_gmp_pct(r)   # % from GMP / upper band
            out.append(r)
        if out:
            break
    if not out:
        raise SourceChanged(SOURCE, "no GMP table rows parsed", URL)
    return out


def fetch(session) -> list[dict]:
    return parse_ipopremium(session.get_text(URL, source=SOURCE))
