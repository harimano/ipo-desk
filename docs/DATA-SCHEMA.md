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
anchors[]: {name, anchor, date, amountCr, issueSizeCr, count, topTierShare, investors[{name, cat, amountCr, pct}], sources[], note}
flows: {latest{date, fiiNetCr, diiNetCr, previousDay, source}, history[[date, fii, dii], ...] (<= 40 rows, append),
        monthly[[label, fiiNetCr, sentence]] (last 3), rotation{fiiSelling[[sector, evidence]], diiBuying[[sector, evidence]]}, note}
investors: {asOf, watchlist[], portfolios[], moves[], holdings[], bulkDeals[{date, investor, vehicle, stock, side BUY|SELL, qty, price, valueCr, exchange, source}], insiders[], recentListings[], anchorActivity[], notes[]}
expected[]: {name, window, stage, sizeCr, sizeText, note, parent, sources[]}
news[]: {title, url, date}
integrity: {asOf, checks[{area, method, status, note, asOf?, elapsed?, calls?}], discrepancies[]}
current{name}: per-IPO research for open/upcoming mainboard names {research, recs, sheet}   - Claude-owned (data/research/)
lot{name}: {shares, price, listDate}; priceHistory{name}: [[date, price]]
offers: {asOf, rights[], buybacks[], ofs[], ncd[]}

Status transitions by date: Upcoming -> Open (open <= today <= close) -> Closed (close < today < listing) -> Listed (listing <= today).
