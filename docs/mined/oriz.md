# Mining notes: chirag127/oriz-ipo (MIT)

Repo: `/home/claude/ref/oriz-ipo` — Python 3.11+, package `src/ipo_watch/` (~1,100 LOC incl. LLM/YouTube extras), tests in `tests/`.
Last commit: **2026-09-08 07:30:59 +0000** `42d7f7b` "data: IPO GMP scrape 2026-09-08 07:30Z" — the repo has **exactly one commit** (squashed history; `git rev-list --count HEAD` = 1). Code comments say sources were "VERIFIED 2026-08-04"; committed data runs 2026-08-04 → 2026-09-08 (33 daily snapshots) and **every snapshot's `source` is `ipowatch`** — the fallbacks were never exercised in the committed history.

Dependencies (`pyproject.toml:6-15`): `httpx>=0.28`, `selectolax>=0.3.25`, `yt-dlp`, `g4f`; optional `browser = ["playwright>=1.50"]`, `dev = ["pytest"]`.

---

## 1. GMP failover chain

**File:** `src/ipo_watch/sources/chain.py`

Order (`build_chain()`, lines 27-36):

| # | Source class | `name` | URL | Transport |
|---|---|---|---|---|
| 1 | `IpoWatch` (`sources/ipowatch.py`) | `ipowatch` | `https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/` | httpx + selectolax |
| 2 | `IpoPremium` (`sources/ipopremium.py`) | `ipopremium` | `https://ipopremium.in/` | httpx + selectolax |
| 3 | `InvestorGain` (`sources/investorgain.py`) — subclass of `PlaywrightTable` | `investorgain` | `https://www.investorgain.com/report/live-ipo-gmp/331/` | Playwright (Chromium) |
| 4 | `PlaywrightTable("chittorgarh", ...)` (`sources/playwright_source.py`) | `chittorgarh` | `https://www.chittorgarh.com/report/ipo-grey-market-premium-latest-ipo-gmp/74/` | Playwright (Chromium) |

Dropped per comment `chain.py:10`: `niftytrader.in/ipo-grey-market-premium`, `ipocentral.in` (404 on probe 2026-08-04).

### "Good" vs fall-through — `scrape_first_available()` `chain.py:39-54`
- Iterates chain; calls `src.fetch()`. Any exception → log warning, append to `errors`, continue.
- Acceptance test line 46-48: `good = [i for i in ipos if i.name and i.gmp_pct is not None]`; if `good` is empty → `ValueError` → falls through. **Winner-takes-all**: the first source with ≥1 row carrying a GMP% returns `(src.name, ipos)` (the full list, not just `good`). There is NO merging across sources and NO cross-source name matching in the GMP chain.
- All fail → `RuntimeError("all IPO GMP sources failed:\n  ...")` (line 54).
- Caveat: `gmp_pct == 0.0` counts as "good" (e.g. IPOWatch's `₹- (0.00%)` placeholder rows parse to 0.0), so a page of all-placeholder rows would still "win".

### Parser: IPOWatch — `sources/ipowatch.py:25-70`
- Header (verified 2026-08-04, line 4-5): `IPO Name | IPO GMP* | Trend | Price Band | Est. Listing | Date | Type | Status | Last Updated`.
- **Key quirk (line 7-9):** GMP **%** is inside the `Est. Listing` cell, e.g. `₹1,116 (28.13%)`; `IPO GMP*` cell is absolute rupees `₹245`. `Price Band` cell holds only the upper price (`₹871`).
- Header row is `<tr><td><strong>…` (NOT `<th>`) — parser uses `rows[0].css("th,td")` (line 32), so it copes.
- Algorithm: for each `table` → `tr` rows; header = lowercased cleaned text of row0 cells; table accepted if any header contains `"ipo"` AND any contains `"gmp"` (line 33). Builds `idx = {header_text: col_index}`; helper `col(cells, *keys)` returns the first cell whose header *contains* a key (substring, first-match-in-header-order) (lines 37-42).
- Row: `cells = row.css("td")`; skip if <2 cells or empty name; `name = cells[0].text()` (a link `<a href="https://ipowatch.in/<slug>-ipo/">` — the href is NOT captured, but would be a useful per-IPO detail URL).
- Field mapping (lines 51-63): `gmp = parse_money(col("gmp"))`; `gmp_pct = parse_pct(col("est. listing","est listing","listing"))`; `price_band = col("price")`; `est_listing` raw; `open_date = col("date")` (matches `"date"` before `"last updated"` because of header order); `ipo_type = col("type")` (`<mark>Mainboard</mark>` / SME); `status = col("status")` (`Upcoming|Open|Closed|Listed`). Then `compute_gmp_pct(ipo)` (`sources/base.py:16-24`) fills % from `gmp / upper_band(price_band) * 100` only if % missing.
- Stops after the first table that produced rows (line 66-67); raises `ValueError("ipowatch: no GMP table rows parsed")` if none.
- **Drift observed:** in `data/latest.json` (2026-09-08) every row has `ipo_type == ""` while the 2026-08-04 fixture has `Mainboard` in the Type column — IPOWatch appears to have changed/emptied that column, so the pipeline's SME filter is silently inert now. Verify before relying on it. Date column now has values like `18-22 Sept (T)`.

### Parser: IPOPremium — `sources/ipopremium.py:24-67`
- Header (line 4-5): `Company Name | Type | GMP (₹) | Open | Close | Price Band (₹) | Listing Date`. GMP absolute `249`; band `829–871` (en-dash). Name carries `(Mainboard)`/`(SME)` suffix.
- Table accepted if a header contains `"gmp"` AND one contains `"company"` or `"name"` (line 32-33). Same `idx`/`col` scheme.
- Mapping (51-60): `gmp = parse_money(col("gmp"))`; `price_band = col("price band","band","price")`; `open_date = col("open")`; `close_date = col("close")`; `listing_date = col("listing")`; `ipo_type = col("type")`. `gmp_pct` always computed via `compute_gmp_pct` (GMP / upper band).

### Parser: InvestorGain + Chittorgarh (generic) — `sources/playwright_source.py:20-84`
- Launch Chromium headless with `--no-sandbox --disable-gpu --disable-dev-shm-usage` (27-30); page UA `Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0` (31); `page.goto(url, wait_until="networkidle", timeout=45000)` (33); then best-effort `page.wait_for_selector("table tr td", timeout=8000)` (36).
- Table accepted if header contains `"gmp"` or `"premium"` AND `"ipo"` or `"name"` (46-47). Rows via `query_selector_all("td")` and `inner_text()`.
- Mapping (65-75): `gmp_cell = col("gmp","premium")` → both `parse_money` and `parse_pct` from the same cell (InvestorGain's GMP cell reads like `₹45 (12.5%)`); `price_band = col("price","band")`; `est_listing = col("est","listing")`; `ipo_type = col("type")`; `status = col("status")`. Then `compute_gmp_pct`.
- No site-specific selectors for either JS site — purely header-keyword heuristics. No fixture exists for them; neither is verified in committed data.

### Name normalisation across sites
Only used in the **subscription enrichment** step, not the GMP chain. `sources/subscription.py:26-29`:
```
_norm(name): lower → remove whole words ltd|limited|ipo|mainboard|sme|nse|bse|eq → strip all non [a-z0-9]
```
Matching (`subscription.py:103-110`): exact `_norm` key lookup, else loose fallback `key in k or k in key` (substring either direction) over the subscription table's rows.

---

## 2. JSON endpoints?
**None.** Every source is HTML-table scraping (`grep` for `json|api/|cloud/v2|.php` in `src/` finds only Telegram/NVIDIA payloads and yt-dlp `--dump-json`). InvestorGain is fetched as the rendered HTML report page (`/report/live-ipo-gmp/331/`, and `/report/ipo-subscription-live/333/` for subscription), not its XHR backend. If we want the InvestorGain JSON endpoint we must discover it ourselves (this repo gives no URL or response fields).

---

## 3. Playwright vs plain HTTP — and why
- Plain httpx: IPOWatch, IPOPremium — server-rendered (`chain.py:4-5`, `ipowatch.py:3`, `ipopremium.py:3`).
- Playwright: InvestorGain GMP (`investorgain.py:3-4`: plain HTTP returns an empty table "No data available" — rows are JS-rendered), Chittorgarh GMP (`chain.py:8`: "per-IPO GMP, JS"), and InvestorGain subscription report (`subscription.py:3-5`: "separate, JS-rendered pages").
- Playwright is optional: `PlaywrightTable.fetch` raises `RuntimeError("playwright not available")` on ImportError (`playwright_source.py:21-24`) which the chain tolerates. Subscription step retries `chromium.launch` 3× with 2 s sleep (`subscription.py:52-58`) and returns `[]` on any failure.
- CI installs it: `python -m playwright install chromium --with-deps` (`scrape.yml:50-51`), caches `~/.cache/ms-playwright` (35-43).

---

## 4. HTTP session setup — `src/ipo_watch/util.py:14-40`
- UA (line 14-17): `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36`.
- Headers (30-34): `Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8`, `Accept-Language: en-US,en;q=0.9`.
- `httpx.Client(headers=..., timeout=25.0, follow_redirects=True)`; one `client.get(url)`; `raise_for_status()`; return `r.text`. **No retries, no backoff, no proxy, no caching, no HTTP/2, one client per call.** Retry is implicit only via the chain's failover.
- Notifier calls use bare `httpx.post(..., timeout=20)` (`notify/channels.py:110-119`, `140-146`).

---

## 5. Alert plumbing — `src/ipo_watch/notify/channels.py` + `src/ipo_watch/pipeline.py`

**Message building**
- Telegram: `format_messages(picks, source)` (76-98) → list of HTML chunks. Header `📈 <b>N open mainboard IPOs · GMP &gt; 5%</b> (via <source>)`, one `_ipo_block()` per pick (47-73): `"{rank}. Name | GMP: ₹245 (28.1%) | Size: … | Band: … | Subscribed 6.03x overall (QIB …, NII …, Retail …) | Type | Status | List | Est | Src | <a href=…>Analysis</a>"`, footer link. HTML-escape helper `_esc` (25-26). Chunked at `SAFE_CHUNK = 3800` chars (22, 89-97) to respect Telegram's 4096 limit. Empty picks → "No open mainboard IPO is above the 5% GMP threshold right now."
- ntfy: `_fmt_ntfy(picks, source)` (155-186) plain-text equivalent, one line per pick.

**Sending**
- `send_telegram(messages)` (101-126): env `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; POST `https://api.telegram.org/bot{token}/sendMessage` JSON `{chat_id, text, parse_mode:"HTML", disable_web_page_preview:true}`, timeout 20; no-op (returns False) when env unset. Each chunk sent sequentially, no sleep between chunks.
- `send_ntfy(text)` (129-152): env `NTFY_TOPIC`, `NTFY_BASE_URL` (default `https://ntfy.sh`), optional basic auth `NTFY_USER`/`NTFY_PASSWORD`; POST `{base}/{topic}` with body = UTF-8 text, headers `Title: IPO GMP watch`, `Tags: chart_with_upwards_trend`.
- `notify_all(picks, source)` (189-194) → `{"telegram": bool, "ntfy": bool}`.
- Workflow-level failure alert: `scrape.yml:84-94` curls Telegram with run URL on `if: failure()`.

**Dedup / state**
- State = the previous `data/latest.json` (committed to git by the workflow). `load_previous()` (`pipeline.py:42-57`) reads only `picks[].name` and `gmp_pct` back.
- Change signature `_change_key(picks)` (`pipeline.py:37-39`): `sorted([[name, round(gmp_pct,1)], ...])`. `changed = prev is None or _change_key(prev.picks) != _change_key(picks)` (139). Notify only if `changed` (146-150). So it re-alerts the **whole pick list** whenever any pick's GMP% moves by ≥0.1 pt or the set changes; it does NOT track per-IPO "already notified" (despite AGENTS.md:53 saying "notify on NEW items only").
- **Rate limiting: none** beyond the change gate and the daily cron. No per-IPO cooldown, no Telegram 429 handling.

---

## 6. Data model — `src/ipo_watch/models.py`
`Ipo` dataclass (27-65), slots:
`name:str; gmp:float|None (₹); gmp_pct:float|None (% of upper band — ranking key); price_band:str; lot_size:str (never populated); open_date, close_date, listing_date, est_listing:str; ipo_type:str ("Mainboard"|"SME"…); status:str ("Upcoming|Open|Closed|Listed"); source:str; kostak, subject_to:str (never populated); issue_size:str ("₹1,200 Cr"); sub_total, sub_qib, sub_nii, sub_retail: float|None (times); review_score:float; videos:list[ReviewVideo]; summary, comment_analysis:str; slug:str`. Properties `is_open` (`"open" in status.lower()`), `is_sme` (`"sme" in ipo_type.lower()`). `to_dict()` via `asdict`.

`Snapshot` (68-85): `generated_at` (UTC ISO seconds), `source`, `threshold_pct=5.0`, `all_ipos`, `picks`; `to_dict()` adds `count_all`, `count_picks`.

**GMP history model:** there is no per-IPO time series. History = one full `Snapshot` JSON per day, `data/history/YYYY-MM-DD.json` + `data/latest.json` (`pipeline.py:67-74`; day key = `generated_at[:10]`, so multiple runs per day overwrite). Consumers (`web/src/lib/data.ts`) read those files. Ranking: `rank()` `pipeline.py:23-34` = `gmp_pct > 5.0 and is_open and not is_sme`, sorted by `(gmp_pct, review_score)` desc.

---

## 7. Scheduling — `.github/workflows/scrape.yml`
- `on.schedule: cron '30 2 * * *'` (02:30 UTC = 08:00 IST, once daily; comment says user asked for morning-only), plus `workflow_dispatch` and `repository_dispatch: types [tick]` (7-12).
- `permissions: contents: write`; `concurrency: group ipo-scrape, cancel-in-progress: false`; `timeout-minutes: 25`.
- Steps: checkout (depth 1) → setup-python 3.12 with pip cache → cache `~/.cache/yt-dlp` + `~/.cache/ms-playwright` → `pip install -e ".[browser,dev]"` → `playwright install chromium --with-deps` → `pytest -q` → `python -m ipo_watch --data data --content web/src/content/ipo --iterations 3 --interval 60 -v` (self-loop 3× 60 s inside one run, `__main__.py:36-52`) → commit `data` + `web/src/content/ipo` as `github-actions[bot]` with `git pull --rebase --autostash origin main || true; git push` (71-82) → Telegram alert on failure (84-94) → no-op "heartbeat" step (96-103).
- Secrets used: `NVIDIA_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, NTFY_TOPIC, NTFY_BASE_URL, NTFY_USER, NTFY_PASSWORD`.
- `ci.yml`: pytest on push/PR + `npm run build` for the Astro site.

---

## 8. Tests — `tests/`
- `test_util.py` (39 lines): `parse_money` (`₹245`, `1,116`, `₹- (Ni)`→None, `0`→0.0), `parse_pct` (`₹1,116 (28.13%)`→28.13, `₹- (0.00%)`→0.0), `upper_band` (`829–871`, `₹151–159`, `100 to 108`), `slugify`, `clean`.
- `test_ipowatch_parser.py` (72 lines): offline parse of the fixture — asserts ≥5 rows, all named, ≥3 with GMP%, % in [-50, 500]. NOTE: it **re-implements** the parse loop (`_parse_fixture`, 16-54) instead of calling `IpoWatch.fetch()` (because fetch does its own network GET — no injection point). 
- `test_pipeline.py` (80): `rank()` threshold (`5.0` not included), open-only, SME excluded, sort/tiebreak, `_change_key`, `write_blog_posts`.
- `test_notify_llm.py` (108): message formatting, chunking ≤4096, ntfy plain text, notifiers no-op without env, LLM template fallback.
- `test_gha_workflows.py` (152): lints the YAMLs (cron present, concurrency, playwright install, tests-before-scrape, no hard-coded tokens, timeout set).
- **Fixture:** `tests/fixtures/ipowatch.html` — 17.8 KB, captured 2026-08-04, a bare `<html><body><table>` (no page chrome), 19 `<tr>` (1 header + 18 IPOs incl. Dhoot Transmission ₹245 / `₹1,116 (28.13%)`, Molbio `₹0` placeholder, `<mark>Mainboard</mark>`, `<mark>Upcoming</mark>`, links to `https://ipowatch.in/<slug>-ipo/`). **Directly reusable** to unit-test an IPOWatch parser offline. No fixtures for IPOPremium, InvestorGain, Chittorgarh or the subscription page.

---

## 9. Last commit
`42d7f7b97eb03fbcb0f6a8ca4986f6336ee0c028` — 2026-09-08 07:30:59 +0000 — "data: IPO GMP scrape 2026-09-08 07:30Z" (bot commit; single-commit repo, so code age is unknowable beyond the "VERIFIED 2026-08-04" comments).

---

## What to vendor (MIT — copy verbatim) vs rewrite

### Copy verbatim
1. `src/ipo_watch/util.py` lines 43-82: `_NUM`, `parse_money`, `parse_pct`, `upper_band`, `slugify`, `clean` — small, tested, handle `₹`, commas, en-dash bands, `(28.13%)`. Also copy `tests/test_util.py` with them.
2. `src/ipo_watch/sources/base.py:16-24` `compute_gmp_pct` (GMP → % via upper band).
3. `src/ipo_watch/sources/ipowatch.py` — the whole `IpoWatch.fetch` table-walk (lines 28-67) including the header-substring `col()` helper and the "Est. Listing holds the %" mapping. Split into `parse_ipowatch(html) -> list[Ipo]` + a thin fetcher so it's testable; the parse body is unchanged.
4. `src/ipo_watch/sources/ipopremium.py:27-64` — same pattern, same reason.
5. `tests/fixtures/ipowatch.html` + the assertions in `tests/test_ipowatch_parser.py:57-72` (point them at the vendored `parse_ipowatch`).
6. `src/ipo_watch/sources/subscription.py:26-37` `_norm` and `_to_times` — name normaliser and "12.45x" parser; plus the exact/substring match loop 103-110 if we cross-match names.
7. `src/ipo_watch/notify/channels.py`: `_esc` (25), `send_telegram` (101-126), `send_ntfy` (129-152), and the 3800-char chunker loop (87-97). `_ipo_block`/`_fmt_ntfy` are fine as starting templates but carry `ipo.oriz.in` links (`SITE`, line 21) — strip.
8. `src/ipo_watch/sources/chain.py:39-54` `scrape_first_available` — the try/except failover loop and the `name and gmp_pct is not None` acceptance test (tighten: exclude `gmp_pct == 0.0` placeholder rows, see §1 caveat).
9. Workflow skeleton `.github/workflows/scrape.yml` lines 14-51 and 71-94 (permissions, concurrency, caches, playwright install, commit-with-rebase, Telegram-on-failure).

### Rewrite / do not copy
- `playwright_source.py` / `investorgain.py` / Chittorgarh: only a generic header-keyword heuristic, never exercised in committed data, no fixtures. Rewrite with real selectors after fetching the pages (InvestorGain likely has an XHR/JSON endpoint — this repo does not know it; discover and prefer it over Playwright).
- `util.fetch_html`: keep the UA/headers, but add retries with backoff (e.g. 3 attempts, 429/5xx aware), a shared `httpx.Client`, and optional `If-Modified-Since`. Nothing here to vendor beyond the header dict.
- Dedup/state: `_change_key` is whole-list compare; rewrite as per-IPO state (`{norm_name: {last_gmp_pct, last_alerted_at}}`) with per-IPO delta thresholds and cooldown, persisted in a committed JSON.
- History: rewrite as an append-only per-IPO GMP series (`{norm_name: [{ts, gmp, gmp_pct, source}]}`) rather than daily full-snapshot files that overwrite on same-day reruns.
- `models.py`: fine as a base; drop `videos/summary/comment_analysis/review_score`, add `detail_url` (IPOWatch `<a href>`), `norm_name`, `scraped_at`, `lot_size` (never filled here).
- Skip entirely: `llm/summary.py` (NVIDIA NIM + g4f), `reviews/youtube.py` (yt-dlp), `web/` Astro site, blog-post writer (`pipeline.py:77-105`).
