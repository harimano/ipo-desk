# Rules carried over from the db-era daily briefing skill (v4, 7 Sep 2026)

The old scheduled-Claude skill is retired, but three parts of it still define product behaviour:
the alert rules (stage two), the key-stability rules (enforced by the collector now), and the source
notes for the research layer. Extracted here so the repo is self-contained.

## Alert rules (stage two — wire into `collector/notify.py` at the end of a run)

Send a message only when one of these is true; otherwise stay silent:

- a `quota[]` row changed stage (DRHP filed / SEBI approved / RHP filed / record date announced /
  withdrawn) — name the parent stock and ticker;
- a record date or RHP date is within 30 days for any row with `quota !== false`;
- a SEBI approval `lapse` date is within 14 days;
- a new subsidiary-of-listed-parent IPO appeared;
- a mainboard IPO opens, closes tomorrow, or lists (stars/applications live in the viewer's
  localStorage — `ipo-interest`, `ipo-holdings`, `ipo-investors` — which the collector cannot see, so
  alert on pipeline rules regardless);
- a tracked superinvestor appears in an anchor book of an open/upcoming issue, or in a bulk deal on a
  stock that listed this year.

Message shape Hari asked for: ≤ 6 lines, leading with the action (which parent, which record date).
Missed-run detection: if the previous `meta.asOf` is more than 36 hours old, prefix "⚠ Refresh gap".

## Key-stability rules (now code, in `schema.py` / the assembler)

- `quota[].name` (subsidiary) and `quota[].parent` (parent short name, e.g. "Reliance Industries",
  "Coal India", "Hero MotoCorp", "Edelweiss Financial Services", "SIS Limited", "Prestige Estates",
  "SBI", "IEX", "NLC India") drive saved toggles — never rename.
- Board `name`s are keys for stars, applications, `lot`, `priceHistory` — keep spelling stable day to
  day ("ESDS Software", not "ESDS Software Solution"). Sources are matched by normalised name; the
  board's spelling wins.
- Never drop a section; carry the previous value forward if not refreshed (the assembler does this and
  marks it `stale`).
- Structured data only: ISO dates, numbers, short factual strings, `null` for unknown. No run
  commentary in any field.
- Never guess a quota stage: each stage must be backed by a dated URL in `sources[]`; otherwise keep the
  previous stage and list the name in `meta.unresolved`.

## Research-layer sources (for Claude writing `data/research/` and `data/quota-reviews/`)

- Quota pipeline: read the "reservation for eligible shareholders" clause in the DRHP/RHP PDF from
  sebi.gov.in or nsearchives — that is how `quota`, `quotaPct` and the eligibility wording get
  confidence "high". `python -m collector.pdf.clause <pdf>` extracts the candidate text.
  ipowatch.in/upcoming-ipo-with-shareholders-quota/ is a candidate list only, never a source of truth.
- Current-issue sheets: ipowatch per-IPO page + Dilip Davda review + DRHP/RHP. Sheet shape is in
  `docs/DATA-SCHEMA.md` (`current{}` and `sheets{}`).
- Anchors: allocation letters the evening before opening (ipoji, chittorgarh, BS, Moneycontrol, BRLM
  PDF) — capture every investor with category and %; the page computes an anchor-quality score from
  `investors[]`, so never leave it empty once the letter is public.
- Offers (rights/buyback/OFS/NCD): ipowatch.in/rights-issue-calendar/, /share-buyback-offers/,
  /offer-for-sale-ofs/ — drop entries whose windows have closed.

## Trendlyne MCP (Monday sweep only — `data/investors.json`)

- `search_entities(query)` → NSE code; one new name per call; cache codes.
- `get_ownership_deals_insider_sast(code, "sast" | "bulblockdeal" | "shareholding")`.
- `get_parameter_values_multi_stock(query)` — ONE stock per call with explicit NSE code and metric
  names; multi-name queries return fuzzy matches.
- `get_overview_news_corp_events(code, "events" | "news")`; `get_document_search_results(query)`.
- Never for a stock that listed today (returns unrelated companies instead of erroring). Always check
  the returned symbol. Never write Trendlyne's proprietary scores (DVM, fair price) into data fields
  other than `sheets{}.street`, with attribution.
- Budget: a sweep should stay under ~150 calls.

## Standing rule for anything Hari reads

Analysis only, both sides shown, never a recommendation to apply or not apply.
