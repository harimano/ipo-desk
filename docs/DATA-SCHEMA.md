# DATA schema (keep exactly; extra keys are ignored by the page)

meta: {asOf ISO+05:30, label "2 Sep 2026, 18:17 IST", quotaSourceNote, unresolved[], awaitingData[], newFindings[], marketNotes[]}
quota[]: {name, parent, parentFull, ticker, bucket: approved|drhp|awaited|done|dropped, stage (short label), rank (0-6),
          stageDate, detail (<= 2 sentences, factual), sizeCr, quota: true|false|null, quotaPct, recordDate, listingDate,
          listingGainPct, lapse, expectedWindow, confidence: high|medium|low, sources[<=4], isNew}
sheets{name}: {parent, parentTicker, parentPrice{value, asOf}, status, timeline{drhp, sebiApproval, rhp, expectedWindow, recordDate},
          issue{totalCr, freshCr, ofsCr, sellers[], shareholderQuota, employeeQuota, allocation, objects, leadManagers},
          business, metrics[[label,value]], financials[{fy, revenue, pat, margin, ronw, networth, note}],
          valuation{impliedMcapCr, impliedMcapNote, impliedPE, impliedPENote, impliedPB, peers[[name, multiple, "PE"|"PB"]]},
          bull[], bear[], flags[], street[{who, date, view}], logistics, sources[]}
mainboard[] / sme[]: {name, slug, type "Mainboard"|"NSE SME"|"BSE SME", status, open, close, allotment, listing, bandLow, bandHigh, lotSize,
          issueSizeCr, freshCr, ofsCr, gmp, gmpPct, gmpTrend up|down|flat, sub{qib, nii, retail, employee?, shareholder?, total, asOf},
          shareholderQuota{offered, parent, recordDate}|null, listingPrice, listingGainPct, currentPrice, sources[]}
          - a Listed row stays on the board only on its listing day, then moves to recent[].
recent[]: {name, type, listingDate, issuePrice, listingPrice, gainPct, closeDay1, closeDay1GainPct, sources[]}  - last ~4 weeks
listedPerf[]: {name, issue, gmpImplied, listing}  - rolling ~40 mainboard listings, newest first. Prepend each new listing.
comps[]: {name, qib, ret}  - listed issues: final QIB subscription vs listing-day return %. Append each listing that had a QIB print.
evidence: {asOf, rfAnnual, minN, edges{total,qib,retail,gmp}, segments{main,sme}, warnings[{code,text}]}  - owned by the `evidence` module; the page quotes it.
  segment: {n, window{rule,from,to,n}, byYear, bands{total{window,all}, gmp{window,all}, qib{rows,years}, retail{rows,years}}, ev{rows,years,blockDays}, fit{r377, eve, r377OnSameRows?, provisional, eveRows}}
  band: {n, pos, lo, hi, med, p10, p90} (pos/lo/hi in %, Wilson 95%); ev row adds {oddsMed, evMed, evP10, evP90, evMean}; fit: {n, a, b, r2, sd, q10, q90}. A null edge is an open end.
listedPerf[] rows may carry gmpEve, gmpEveAsOf: the desk's own last GMP stamped before listing day, frozen once.
anchors[]: {name, anchor, date, amountCr, issueSizeCr, count, topTierShare, investors[{name, cat, amountCr, pct}], sources[], note}
flows: {latest{date, fiiNetCr, diiNetCr, previousDay, source}, history[[date, fii, dii], ...] (<= 40 rows, append),
        monthly[[label, fiiNetCr, sentence]] (last 3), rotation{fiiSelling[[sector, evidence]], diiBuying[[sector, evidence]]}, note}
investors: {asOf, watchlist[], portfolios[], moves[], holdings[], bulkDeals[{date, investor, vehicle, stock, side BUY|SELL, qty, price, valueCr, exchange, source}], insiders[], recentListings[], anchorActivity[], notes[]}
  - `listingDeals[]` (owned by `deals`, 60 days, newest first): every NSE bulk/block deal whose stock listed this year, whoever the client —
    {date, symbol, stock (the board / listedPerf name), client, side BUY|SELL, qty, price, valueCr, exchange, kind bulk|block, sme,
    listedOn, daysSinceListing, issuePrice, vsIssuePct}. `sme` on every row: never pooled. Deduped on date+symbol+client+side+qty.
  - `listingSymbols{name: {symbol|null, triedOn}}` (owned by `deals`): this year's listings' NSE symbols, remembered so NSE's equity
    lists are fetched only for new names; null = no NSE symbol (BSE-only), retried weekly while the listing is under 90 days old.
expected[]: {name, window, stage, sizeCr, sizeText, note, parent, sources[]}
news[]: {title, url, date}
integrity: {asOf, checks[{area, method, status, note, asOf?, elapsed?, calls?}], discrepancies[]}
current{name}: per-IPO research for open/upcoming mainboard names {research, recs, sheet}   - Claude-owned (data/research/)
lot{name}: {shares, price, listDate}; priceHistory{name}: [[date, price]]
offers: {asOf, rights[], buybacks[], ofs[], ncd[]}

Status transitions by date: Upcoming -> Open (open <= today <= close) -> Closed (close < today < listing) -> Listed (listing <= today).
records: {igId: {name, fetchedAt, about[], desc[], promoters?, objects?, financials?, peers?, reservation?, kpiPeriods[], holding{}, gmpHistory[], bidding[], company{}}}
  - owned by `details`, published in the `research` part. A table is {head[], rows[][]} of cell text (+ title/asOf), parsed from the HTML table
    the per-IPO record carries; gmpHistory: {date, gmp, est, pct, kostakSauda}; bidding: {asOf, qib, nii, bnii, snii, retail, employee?, total, bidCr, retailBidCr}.
    Kept while the row is on the board; a row with no record on file is fetched at once. Board rows also carry `refund` (the unblock day).
players: {asOf, tracked, of, latestPerInvestor, books{igId: [{id, name, ipos, investedCr, ticketCr}]}, names{igId: row name}, league[]}
  - owned by `players`; which of the largest anchor investors (InvestorGain 551 / 561) are in the books of unlisted issues on the board.
    `covered[]` = the igIds looked up this run; `frozen{igId: {name, sme, listedOn, large, of, names[], frozenOn}}` = each issue's line-up
    the day it listed, never rewritten (accruing since 22 Sep 2026). `evidence.segments[x].anchors` = {rows[4] by `large` band
    (edges 0,1,3,6), n, since, of} — listing outcomes of frozen line-ups, with Wilson; thin for months and shown as such.
  evidence segment also carries hold{window[], all[]}: {n, held, lo, hi, med, p10, p90} per `edges.open` band (day-1 close vs the open).

tape: {asOf, dates[], noFile[], names{name: symbol}, n} — owned by `tape`: which trading days' NSE bhavcopies have been read (last 90),
  which weekdays had no file (holidays), and which listings of this year were priced from them. `tape` merge-patches `priceHistory`
  with one [date, close] a trading day for EVERY listing of this year with an NSE symbol (listings prices only the board).
evidence.lockins: {rows[{name, sme, date, base, after, ret}], days} — the price move over the first 5 trading days after an anchor's
  30-day lock opened, frozen once written (outlives the 90-day price cap); `segments[x].lockin` = summarise(rows of that segment)
  + since + days. Started 22 Sep 2026.

anchorBooks: {asOf, n, books{igId: {name, sme, listedOn, bidDate, price, totalShares, pctQib, locked30, locked90, complete, rows[{name, key,
  shares, amtCr, pctAlloc, pctIssue}], fetchedOn}}, none{igId: triedOn}} — owned by `anchorbook`, its own part (`books.json`): every IPO's
  anchor allocation since 2022 from InvestorGain's record (HTML table parsed as a table), frozen once fetched. `complete` = the rows
  account for the whole book (some records carry only the first two names). `key` = investor name normalised (`anchorbook.investor_key`).
