# Prediction and the AI layer — what is worth building, in what order

Written in the Cowork session, 18–19 Sep 2026, against the repo at `c414f7a` (Scoreboard screen landed)
and the evidence base as it stood that evening: **1,323 listings, 2022–2026, 944 SME and 379 mainboard**.
Every figure below was computed from `data/latest.json` by `tools/evidence_check.py`, which ships with
this document — run it rather than trusting the numbers here, because the base grows every week.

Analysis and evidence only. Nothing here is a recommendation to apply to, or skip, any issue.

---

## 0. The finding that matters before any model

`tools/evidence_check.py` on the live document, 18 Sep:

```
rows 1323   years 2022-2026   SME 944 (71%)   mainboard 379
category books (QIB/NII/retail): 195 rows, years [2026]
```

Three problems with the statistics the Board and Scoreboard quote today, in order of how much they
mislead:

**a) Pooling SME with mainboard inverts the answer in the middle bands.**

```
qib band   pooled            mainboard         SME
5-25x      n=36   56%  +1.2  n=13  77%  +7.0   n=23  43%  -3.1
<5x        n=70   37%  +0.0  n=26  23%  -3.6   n=44  45%  +0.0
```

71% of the base is SME, so a pooled band mostly describes SME issues. In the 5–25× QIB band a
mainboard reader is shown 56% when their own segment says 77%; in the <5× band they are shown 37%
when their segment says 23%. The fix is not a better model — it is splitting the band and printing
`n`. Where a segment has under ~30 rows, the honest display is the count, not a percentage.

**b) Every QIB band rests on 195 rows from a single year.** Report 566 carries category books for
the current year only, so QIB evidence starts at 2026 and grows. A "QIB >100× → 93% listed positive"
line is a 2026 statement wearing the clothes of a general law. Until the books go back further, band
by **total subscription** (n=1,323, every year) and keep QIB as a secondary, explicitly-2026 cut.

**c) The regime moved, twice.**

```
2024  all n=340  85% med +31.4      2025  all n=377  63% med +3.4      2026  all n=220  60% med +3.3
```

A base rate computed "since 2022" averages a market where five issues in six listed up with one where
three in five do, and a median pop of +31% with one of +3%. Anything the page states as a base rate
should be a trailing window — last 12 months, or last 100 listings in that segment — with the window
named on screen. This alone changes more of what the desk tells you than any model would.

---

## 1. What is actually predictable — and the honest answer is "less than it looks"

Regressing realised listing return on GMP-implied return (`gmpImplied` is exactly `issue + gmp`, so
this is a pure GMP calibration):

```
             n      realised = a + b x implied      R2     resid sd    80% band
all        1323     -0.06 + 1.00 x implied         0.70    24.9pp     -21 to +20pp
mainboard   379     -1.23 + 0.99 x implied         0.77    13.7pp     -12 to +12pp
SME         944     +0.55 + 1.00 x implied         0.69    28.1pp     -25 to +26pp
```

**Slope 1.00, intercept ≈ 0. GMP is already unbiased.** That is the single most important result in
this document, and it is a negative one: a machine-learning model cannot improve the *point estimate*
much, because the free number on the screen is already centred. The published literature agrees that
demand and GMP are the only reliable signals and that everything else is weak — the best serious
attempt (418 mainboard + 681 SME, walk-forward) reached AUC 0.90 on mainboard *direction* and only
0.69 on SME, with prospectus text and LLM features adding essentially nothing
([arXiv 2412.16174](https://arxiv.org/html/2412.16174v1)). Indian studies report subscription r≈0.62
and GMP r≈0.50 against listing gain in hot years ([JAAFR 2025](https://www.rjwave.org/jaafr/papers/JAAFR2604803.pdf)),
and at least one peer-reviewed paper finds GMP *not* significant at all
([IJRCM 2025](https://indianjournalofcomputerscience.com/index.php/ijrcm/article/view/175891)).
Treat every published r as an upper bound from a hot sample.

So the value is not in a better number. It is in three things GMP does not give you:

**The width.** GMP says +25%; the desk should say "centred +25%, but eight times in ten this lands
between +13% and +37%" for a mainboard issue, and between −1% and +51% for an SME one. The residual
spread is the product. It is one line of arithmetic, not a model.

**The odds.** A pop you have a 2% chance of receiving is not a 25% return. Retail allotment in an
oversubscribed issue is a lottery for exactly one lot, so `P(allotment) ≈ max_allottees /
applications`, and applying for more lots does not change it
([Chittorgarh](https://www.chittorgarh.com/book-chapter/ipo-allotment/25/)). Before the basis of
allotment is published, `RII applications ≈ RII shares bid / lot size` is near-exact. Expected value
per application, with ASBA capital blocked five to seven days under T+3:

```
EV = p_alloc x lot_value x E[return]  -  lot_value x r_f x days_blocked/365  -  p_alloc x costs
```

For a 50×-oversubscribed mainboard issue with a +15% centre, that is roughly ₹45 gross against ₹15 of
forgone interest on a ₹15,000 lot. **The odds dominate the pop.** No part of this needs machine
learning; it needs the applications count, which report 607 carries (retail allottees, allotment date,
fund reuse) and the registrar's basis-of-allotment confirms afterwards.

**The regime.** Whether this is a 2024 market or a 2025 one is a trailing-window statistic, and it
moves the base rate by 25 points. It belongs on the page as a stated condition, not inside a model.

The one thing GMP genuinely cannot do is SME: residual sd 28pp against mainboard's 14pp, and the
literature puts GMP/listing agreement at 80% for mainboard versus 21% for SME. The correct product
decision is to show SME bands wider and say why, not to model harder.

### The look-ahead risk that could void all of it

R² of 0.70–0.77 is better than the literature, which is a reason for suspicion, not celebration.
Report 377's "last GMP" is dated by its source. **If that GMP is stamped on or after listing day, the
calibration above is fitted on a number that already knew the answer.** The test is in
`evidence_check.py` and needs doing before anything is published: for listings since this desk went
live, compare the GMP the collector itself recorded the evening before listing
(`data/history/<date>.json`) with report 377's figure for the same `igId`. Equal-and-late means
look-ahead. Until that is settled, every R² here is an upper bound.

---

## 2. Build order for the numbers

**Stage 1 — arithmetic, no model, no new dependency.** Everything in §0 and §1 above:
segment-split bands with `n`, a trailing window with the window named, the calibration interval from
a rolling fit, allotment odds from bid shares ÷ lot size, and EV per application including blocked
capital. This is `collector/modules/evidence.py` writing an `evidence` key — a deterministic module
like any other, owned in `schema.OWNERS`, validated by `validate.py`, no pickled model in the repo.
It is also where `tools/evidence_check.py` graduates from a bench tool into a CI guard: fail the run
if a band the page will print has fewer than 30 rows behind it.

**Stage 2 — a calibrated model, once the look-ahead question is settled.** Scope: direction
(`opens above issue`) as a probability, and a p10/p50/p90 band on the return. `scikit-learn`
`LogisticRegression` on standardised, log-transformed subscription plus GMP and a regime feature,
wrapped in `CalibratedClassifierCV`; `statsmodels.QuantReg` at τ = 0.1/0.5/0.9 for the band;
[MAPIE](https://mapie.readthedocs.io/) for conformalised intervals with honest coverage. All CPU,
seconds in Actions, all already-common dependencies. Features that will survive: log QIB, log NII,
log retail, GMP, log issue size, SME flag, regime temperature. Features that will not, at this
sample size: registrar, lead manager, sector beyond three buckets, ROE/ROCE/margins, promoter
holding, anchor investor count. The literature is consistent that fundamentals are insignificant
once demand is controlled for, and that anchor participation and IPO grading show no effect
([Global Business Review 2024](https://ideas.repec.org/a/sae/globus/v25y2024i4p1074-1095.html)).

**Validation, or it does not ship.** Walk-forward only — rolling six-month test windows, never a
random split. Three baselines to beat: the base rate, GMP sign alone, and rolling-α/β GMP. If the
model does not beat the third on out-of-sample Brier score by more than the fold-to-fold noise, it
has learned nothing beyond the free number on the screen, and the honest thing is to ship the
arithmetic and say so. Score with Brier and log loss for direction, pinball loss and realised
coverage for the bands, and publish a calibration curve per segment per year. Pre-register the
feature list; a dozen features against several targets is a hundred silent hypotheses.

**Stage 3 — only if stage 2 earns it.** Partial pooling across SME and mainboard (`bambi`/PyMC
hierarchical, or ridge shrunk toward the pooled fit, which is a tenth of the work); gradient boosting
as a *challenger* only, depth ≤ 3, and only if it beats the linear model on walk-forward log loss.
1,300 rows with three structural breaks — the April 2022 NII split, T+3 in December 2023, the
March/July 2025 SME rules — is not a boosting problem.

**What not to attempt at this size**: the magnitude of day-1 *close* return beyond the GMP baseline
(expect MAE near the standard deviation); intraday open→close drift; anchor, registrar or
lead-manager "quality" effects; fundamentals as listing-day predictors; SME magnitude models trained
across the 2025 rule change; and anything involving deep learning or prospectus NLP as a signal.

**Beyond listing day, one real effect.** SEBI's study of 242 mainboard IPOs (Apr-22 to Oct-25) finds
that where more than 10% of anchor holdings are sold in the T+29–T+33 window, mean price impact is
about −3.5% and median −6%; the 90-day unlock shows essentially nothing. Smaller issues see much
heavier anchor exit ([Business Standard](https://www.business-standard.com/markets/news/smaller-ipos-see-sharper-anchor-investor-exits-after-lock-in-periods-sebi-126081301818_1.html)).
Exit intensity is only observable after the fact, so ex ante this is a "small issue + high FPI share
of the anchor book + big listing pop → elevated chance of a soft week" flag on the calendar, not a
trade. The desk already collects both anchor lock-in dates from `details`.

---

## 3. The AI layer — three shapes, none of them in the data path

The rule that produced this repo stands: the pipeline fetches structured data and renders it. Every
AI feature below is one of three shapes, and none can write `data/`.

**Shape A — offline generator, output lands as a pull request.** A workflow runs Claude Code headless
with read-only tools and a JSON schema, and the result becomes a draft PR. GitHub's own Agentic
Workflows technical preview formalises exactly this: the agent job holds a read-only token and emits
structured "create a PR with these files" requests that a separate permissioned job applies, with a
fallback to an issue when protected paths are touched
([safe-outputs](https://github.github.com/gh-aw/reference/safe-outputs/)). `claude-code-action@v1`
defaults the same way — it pushes a branch and links the PR page rather than opening it
([security](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md)). Use
`claude --bare -p` with `--allowedTools "Read"`, `--json-schema`, `--max-turns`, and assert on the
returned JSON so a silent failure fails the job. `--output-format json` returns `total_cost_usd`;
log it and fail above a cap.

**Shape B — read-only in-page helper behind a proxy.** A Cloudflare Worker holding the key. The page
sends `{igId, question_id}` — never free text — and the Worker loads that issue's JSON server-side,
picks one of a fixed set of prompt templates, and returns schema-constrained output. With no free-text
input there is no chat surface to abuse, and responses cache on `(igId, question_id, data_hash)`.
AI Gateway gives rate limiting, caching and, since June 2026, **spend limits** per model with
block-or-downgrade behaviour ([blog](https://blog.cloudflare.com/ai-gateway-spend-limits/)); add
Turnstile in front. At Haiku pricing this is cents per issue.

**Shape C — one-off extraction, reviewed, committed as a file.** The prospectus and anchor-letter work
that the run-time rule correctly forbids. A `workflow_dispatch` tool locates sections by their SEBI
ICDR headings, sends only those 40–80 pages to a vision model with a per-section schema, validates
(totals reconcile, holdings sum ≤ 100%, every field carries a page citation), and opens a draft PR
with the citations beside the values. A 400-page DRHP is roughly $1.4 on Haiku, under $3 on Sonnet;
an anchor letter is under a cent. Expect ~95% field accuracy on born-digital filings and worse on
scanned SME ones. `collector/pdf/clause.py` and `anchor.py` are already the bench tools for this.

**The division of labour between the model and the language.** Numbers come from the calibrated
model or the arithmetic; the LLM writes prose into slots and is forbidden to emit a digit. The
template holds `"Centred {p50}%, eight times in ten between {p10} and {p90}. {narrative}"`, the model
returns `{narrative, cited_fields[]}`, and a regex for `\d` on the narrative is the cheapest effective
guard there is. Every factual field in a schema should be a `{value, source_field}` pair whose pointer
is verified in code against the input; reject the whole output on a mismatch, and give the schema an
`unanswerable` slot so "not in the data" is an available answer. Render numbers first and hydrate
prose asynchronously, so the page degrades to "explanation unavailable" rather than to a blank.

**Build order.** A weekly research-brief PR job first, because it proves the loop with nothing at
risk. Then the prospectus extractor on `workflow_dispatch`, which is where AI actually earns its place
on this desk — turning the reservation clause and the offer structure into fields is the one job that
is genuinely hard for a parser and genuinely easy for a model. Then the in-page "explain this row".
RAG last and probably never: 300 research sheets is ~300k tokens, per-issue questions need no
retrieval at all, and cross-issue questions are filters over structured fields, not embeddings.

**Injection is the live risk**, and it arrives through scraped news and filing text, not through the
user. Keep untrusted text in a delimited block, give that call no tools, constrain the output to a
schema, require citations, verify in code, and keep a human on the PR. Log model id, prompt hash,
input data hash, tokens, cost and reviewer to an append-only file in the PR, so any sentence on the
site can be reproduced or repudiated.

---

## 4. Data the desk does not collect yet, ranked by what it unlocks

1. **Applications by category** (report 607: retail allottees, allotment date, fund reuse; the
   registrar's basis of allotment afterwards) — without it there are no allotment odds, and without
   odds there is no expected value. This is the highest-value missing field on the desk.
2. **Subscription timeline per run** — the desk already fetches the book every 30 minutes while an
   issue is open, but does not keep the series. Storing it gives the day-2-to-final relationship and
   makes the decision clock evidence-based instead of a rule of thumb.
3. **Category books for past years** — QIB evidence is 2026-only. If report 566 cannot be fetched for
   closed years, the bands stay on total subscription and say so.
4. **Listing-day open/high/close** rather than only the open — the desk currently calibrates against
   the open; sell-at-open versus hold-to-close is a question the Book screen will ask.
5. **Anchor exit observations** around the 30-day unlock, from bulk-deal and shareholding data the
   `deals` module already touches.

---

## 5. Where this contradicts the roadmap, and where it agrees

Agrees with A (decision-first Board), B (signal scoreboard), C (capital timeline) and E (provenance) —
those are exactly right, and C is more important than it looks, because expected value is where the
desk's real edge lives.

Contradicts one thing: the roadmap's framing of B as "keep the hit-rate" understates it. A hit-rate
without a segment split, a sample size and a stated window is the kind of number that reads as
authority and is not. The Scoreboard's first job is to make its own thinness visible.

Adds one item not on the roadmap: **the look-ahead check in §1** should happen before B is built on
report 377, because if it fails, the evidence base needs rebuilding from the desk's own recorded GMP
and every band changes.
