# Third-party code

## chirag127/oriz-ipo (MIT)

Source: https://github.com/chirag127/oriz-ipo — commit `42d7f7b97eb03fbcb0f6a8ca4986f6336ee0c028` (2026-09-08).

Copied, in places adapted, into this repository:

| Here | From |
|---|---|
| `collector/sources/_parse.py` — `parse_money`, `parse_pct`, `upper_band`, `clean` (verbatim); `compute_gmp_pct` (adapted to dict rows) | `src/ipo_watch/util.py`, `src/ipo_watch/sources/base.py` |
| `collector/sources/ipowatch.py` — table walk and header-substring `col()` helper | `src/ipo_watch/sources/ipowatch.py` |
| `collector/sources/ipopremium.py` — table walk | `src/ipo_watch/sources/ipopremium.py` |
| `collector/modules/gmp.py` — failover loop shape ("first source with a usable GMP row wins") | `src/ipo_watch/sources/chain.py` |
| `collector/notify.py` — `_esc`, `send_telegram`, `send_ntfy`, message chunking | `src/ipo_watch/notify/channels.py` |
| `data/fixtures/ipowatch/board.html` | `tests/fixtures/ipowatch.html` |

The Playwright-based sources (InvestorGain page scrape, Chittorgarh) were **not** copied.

### License

```
MIT License

Copyright (c) 2026 Chirag Singhal

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
