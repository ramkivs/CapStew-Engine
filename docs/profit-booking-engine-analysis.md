# Profit-Booking Decision Engine — Spec Review, Findings & Implementation Plan

**Reviewed by:** Arena.ai Agent Mode
**Date:** 2026-08-22
**Status:** Analysis deliverable (v1.0 of the review, not the engine itself)
**Scope:** Read of Spec v1.0 §1–§10 + Appendices, validated against the three real data exports and current India tax law.

---

## 0. Executive summary

The spec is **fundamentally sound and unusually disciplined for a personal-investing tool** — it correctly refuses to be a single-metric trigger, correctly puts position-sizing and tax timing at high weight, correctly separates hard gates from a weighted composite, and correctly treats "not enough data" as a first-class output rather than a silent fallback. The two-stage architecture, the per-lot tax realization (resolved via the trade ledger), and the averaging-into-losses behavioral flag are all strong design decisions.

The review below does **not** re-litigate what the spec already decided. It adds three things:

1. **~15 new findings/gaps the spec does not list** — the most consequential being: (a) the Stage 1 tax-defer gate is too binary and will systematically under-sell stretched positions; (b) `confidence` appears in the output schema but is never defined anywhere; (c) the whole current book is <12 months old, so XIRR is a meaningless artifact and the tax gate is inert for ~5 months; (d) the backtest will be universe-biased because only *open* positions exist in the data.
2. **A concrete architecture blueprint** — modules, schemas, and executable pseudocode for the four hardest pieces (per-lot FIFO tax engine, trim sizing, re-rating decomposition, averaging-down detector), so "build it" is a mechanical step, not a design step.
3. **A phased implementation plan** and a **policy-decision checklist** (the ~10 parameters only Ramki can set, each with a recommended default).

**Bottom-line verdict:** the three files are sufficient to ship a **shadow-mode v1** that covers Stage 1 + most of Stage 2 + portfolio layer + behavioral flags, *provided* the ~10 policy parameters are pinned down and the two "Gap" items in the spec's own Section 7 minimum-set (own-historical valuation median, score-at-entry) are run with explicit proxies for the first few months while snapshot archiving closes them. The highest-value next action is **not more analysis — it's starting to archive the fundamentals snapshot on a schedule**, because every day without an archive permanently burns the ability to compute "score at entry vs now" retroactively.

---

## 1. What the spec gets right (worth preserving)

These are design choices that should be locked in, not reopened:

| # | Design choice | Why it's correct |
|---|---|---|
| 1 | **Two-stage: hard gates → weighted composite** | Prevents a "55/100 sell?" dither from delaying a governance exit, and prevents a mechanical trim from overriding a thesis break. Correct ordering. |
| 2 | **Position sizing at 25% weight, co-equal with valuation** | The only category where booking is right *even when the stock is fine*. Most P&L tools skip it entirely. |
| 3 | **ACCUMULATE as a tag, not a competing decision** | Keeps the decision set mutually exclusive (5 decisions would collapse into "buy/sell/hold" confusion). Clean. |
| 4 | **Tax timing as a hard gate, not a score input** | Tax is a sequencing constraint, not a thesis input. Making it a gate (with override) is right. |
| 5 | **Per-lot resolution via the trade ledger (8.2/9.1)** | Indian CGT is per-lot FIFO. Running the engine on a blended Avg Buy Price would have silently misfired the tax gate. This was the single most important structural catch in the spec. |
| 6 | **Averaging-into-losses as a caution flag, not a gate** | Correctly refuses to criminalize disciplined accumulation while still surfacing the pattern. |
| 7 | **"Margin of safety consumed" as the mirror of the buy-side MOS** | Cleanest possible framing of "the thesis played out" — it reuses existing infrastructure instead of inventing a new concept. |
| 8 | **Cross-engine divergence surfaced, not averaged away** | Divergence *is* information. Silently blending it would destroy the exact signal they've already gotten value from (the negative-PE/PB bug). |
| 9 | **Weights as configurable parameters per bucket** | Correct; a microcap momentum name and a large-cap compounder should not share one weight profile. |
| 10 | **Alert vs auto-decision separation** | Stage 1 = auto-flag, Stage 2 = advisory. (See §5.9 — I'd promote this from "enhancement" to "design principle of v1".) |

---

## 2. Findings — deeper observations not in the spec

### 2.1 Tax: the Stage 1 defer-gate is too binary and will systematically under-sell

The spec's Stage 1 says: *days-to-LTCG < 30 and no thesis break → HOLD (defer booking until LTCG)*.

The math problem: the tax saving from waiting is only **7.5 percentage points** (20% STCG → 12.5% LTCG), and it's not even a full 7.5pp in most cases because the ₹1.25L exemption means small LTCG is *free* while STCG has no exemption at all. Against that, the cost of waiting is **price risk on a position you already believe is stretched**. A single −3% day wipes out ~40% of the tax saving; a −7.5% drawdown over the wait wipes it out entirely. For a microcap (their book clearly includes these — Ashoka Buildcon, SALASAR, Credo), 7.5% can be *one day*.

**Recommendation:** keep the defer-gate, but make it two-tier:
- **Tier 1 (hard):** thesis break → EXIT regardless of tax (spec already has this — correct).
- **Tier 2 (expected-value, not binary):** if days-to-LTCG < 30 but the position is *valuation-stretched*, do not auto-HOLD. Compute `expected_drawdown_risk = daily_vol × sqrt(days_to_ltcg)` and if `tax_saved_pct < expected_drawdown_risk`, override the defer and surface a "tax-vs-drawdown conflict" warning with the numbers. Only genuinely *unstretched* positions should get the pure tax-defer HOLD.

This is a refinement of the spec, not a disagreement — the spec's own Section D says the gate should default to HOLD "unless a stop-loss/thesis-break condition overrides," but it omits the *valuation-extreme* override, which is empirically the more common case where waiting 30 days is wrong.

### 2.2 `confidence` is in the output schema but never defined

§4.3 outputs `"confidence": 68` with zero definition of how it's computed. For a system whose whole value is "tell me *how sure* this recommendation is," this is the biggest hole in the spec. See §8 for a concrete confidence model.

### 2.3 The entire current book is short-term; XIRR is an artifact

From the sample data, as of **2026-08-22**:
- Oldest lot in evidence: Bank of Baroda, 09-02-2026 → **~194 days**. Still < 365.
- Most other names: 80–95 days held.
- **Conclusion: 100% of the book is STCG today.** The Stage 1 LTCG-defer gate will be inert for ~5–6 more months for the oldest lots and ~9+ months for the rest.

Three consequences:
1. **XIRR is meaningless at these horizons.** A 73% gain over 81 days annualizes to **1344%** (Kalyan Jewellers row) and a 20% gain over 87 days to **126%**. These are mathematical artifacts, not signals. Any rule that reads XIRR (the spec's "decompose XIRR" in §3A, the "post-tax XIRR" in §3D) will be garbage until holdings pass ~1 year. **The engine should suppress XIRR below 365 days** and use simple % return (or money-weighted return) instead, with a `return_metric` field that flips over at the 1-year mark.
2. The tax module's near-term job is **not** "don't churn to LTCG" — it's "the whole book is at 20% STCG, so sequence any trims to the oldest lots and prefer trimming names closest to their LTCG date; consider whether *not* trimming until LTCG is worth the carry for each stretched name."
3. The "decompose total return into re-rating vs earnings" idea only becomes valid once there's a 12-month baseline. For now it must run on a *lower-fidelity proxy* (gain % vs PE premium vs EPS growth since entry) and be labelled as such.

### 2.4 Data staleness is unhandled; the sample export is ~1 week old

Portfolio rows say "Holding Period (Days)" of 80–87 for names whose First Date is 2026-05-19/26, but the calendar says those are ~88–95 days. The export is **stale by ~7 days**. The spec's dedup discipline (same-day duplicate checks) exists, but there's no **staleness check**. Recommendation: every input snapshot carries an explicit `as_of_date`; the engine flags any input whose `as_of_date` is >N days behind the run date (N=3 for price/valuation files, N=7 for the ledger, since buys don't change), and the decision output always stamps `data_as_of` so a recommendation is never silently based on week-old prices.

### 2.5 FIFO ordering: the operative tax unit is the *oldest unsold lot*, not the blend

§9.1 correctly resolves per-lot granularity, but the implementation implication is sharper than the spec states: when Stage 2 recommends a partial trim, FIFO matches the sale to the **oldest lots first**. So:
- `days_to_ltcg` for the *oldest unsold lot* is the number that matters for a trim, not the blended holding period.
- If the oldest lots are already LTCG-eligible (they will be, next year) and gains are within the ₹1.25L headroom, a trim is nearly tax-free. If the oldest lots are STCG, the same trim costs 20%.
- The trim-sizing module (§4.2) must therefore be **lot-aware**, not quantity-aware: it should say *"sell 120 shares = lots #1–#4 (the oldest four), realizing ₹X STCG / ₹Y LTCG,"* not just "sell 120 shares." The spec gestures at this in 9.1's FIFO bullet; this makes it a hard requirement of the sizing module's output.

### 2.6 Reconciliation actually validates on the sample — a good sign, but automate it

Worked example from the data: AGI Greenpac — ledger shows 1 @ 588.30 + 1 @ 591.00 = ₹1,179.30 invested, avg 589.65, which **exactly matches** the portfolio file (Avg Buy Price 589.65, Invested 1179.3). This proves the ledger and portfolio files are the same source-of-truth lineage. The engine should automate exactly this check for all names: `sum(lot qty × buy price) == Invested` and `sum(lot qty) == Qty Held`, flagging any mismatch as a hard data-quality error (same discipline as their existing duplicate-file dedup, applied to cost basis). Note: this only works while the ledger is *buys-only*; once sells exist, the check becomes `qty_held == Σbuys − Σsells` with FIFO-matched cost basis, which is a bigger reconciliation job (see §5.7).

### 2.7 The backtest will be universe-biased (survivorship/look-ahead)

Enhancement #1 (backtest) is correctly ranked highest-value, but there's a fatal subtlety the spec misses: **all three files contain only *open* positions.** A backtest that replays decisions against "what happened next" can only see names the portfolio still holds — it can never see the names that were *sold* (and would have been the engine's exits). The historical full-holdings archive (including sold positions and their sell dates/prices) does not exist. Therefore:
- Any backtest today is conditioned on survivorship and will **overstate HOLD quality** (losers that got sold and kept falling are invisible).
- The fix is the same one as §2.4: **start archiving now** (full holdings + sold ledger going forward), accept that a clean backtest is ~12 months away, and in the interim run the backtest only as a *sanity check on rule mechanics*, not as weight calibration.

### 2.8 Several "thresholds" that Stage 1 depends on are undefined

Stage 1 fires on: "quality score drops below your floor, e.g. >2 notches," "promoter pledge spikes," "position > absolute max % cap," "days-to-LTCG < your threshold." Four thresholds, none defined. "Notch" has no operational meaning — is it a 10-point drop on a 0–100 composite? A tier change (A→C)? Without pinned values, Stage 1 is unimplementable. §7 provides concrete defaults.

### 2.9 Missing-data renormalization will silently distort weights

§8.3 says partial-data names "fall back to a partial-data Stage 2 score (position-sizing and tax-timing only)." But if the 25%-weight valuation category is absent and you just *drop* it, the remaining categories silently re-weight themselves (position-sizing 25% → effectively 45%) without anyone noticing. Two rules are needed:
1. **Renormalize** remaining weights to sum to 100%, and **report** the reduced coverage.
2. **Penalize confidence** by the weight of the missing categories (see §8). Otherwise a data-poor name can look *more* confident than a data-rich one because its score is driven by fewer, cleaner inputs.

### 2.10 The "return decomposition" needs a formula, and a sub-1yr caveat

§3A's "decompose XIRR into re-rating vs earnings" is the single strongest signal in the spec, but it's stated as an idea. Concrete version (geometric identity):

```
(1 + price_return) = (1 + eps_growth) × (1 + pe_change)   [approx, + dividend yield additively]
share_from_re_rating = ln(PE_now / PE_entry) / ln(Price_now / Price_entry)
```

Operationally, with the files on hand, the proxy is: `gain_%` vs `EPS growth over holding period` vs `PE premium vs sub-sector` — if `gain_% ≫ EPS growth`, the residual is re-rating. **Caveat:** over <1yr, all of these are noisy; the decomposition should only be *asserted* (as a driver, not a whisper) after ~12 months, and labelled "low-confidence" before that. And note the spec's "80%+ from multiple expansion = strongest signal" threshold should be a **sliding penalty** (e.g., >65% = strong, >80% = critical) rather than a single cliff, since 79% vs 81% should not flip a decision.

### 2.11 India tax mechanics the spec can exploit further (confirmed current)

Verified against Budget 2026 (unchanged) and current rules:
- **LTCG 12.5% above ₹1.25L/yr, STCG 20%, 12-month holding** — confirmed unchanged for FY 2026-27. ✓ (spec is correct)
- **No wash-sale rule in India.** A sell-and-rebuy to reset cost basis is legal (GAAR applies only to sham transactions without economic substance). This means the engine can recommend **annual tax-gain harvesting** (book up to ₹1.25L of LTCG each FY, rebuy immediately, reset cost basis) as a *standing policy*, not just as an ad-hoc trim trigger — a materially stronger use of the ₹1.25L headroom than the spec's "if under headroom, be more aggressive on trims."
- **Set-off rules** (missing from the spec's §5 tax tracker): **STCL offsets STCG *and* LTCG; LTCL offsets only LTCG; unabsorbed losses carry forward 8 years (S.74).** This changes the loss-harvesting companion module's logic: short-term losers are the *most* valuable losses to harvest (they offset the 20% STCG bucket), and since the whole book is short-term today, the loss-harvesting module is actually *actionable now* even though the gain-harvesting side isn't (nothing is LTCG yet).
- **Budget 2026 change worth a watch item:** share-buyback proceeds are now taxed as capital gains in the shareholder's hands. If any holding announces a buyback, the post-tax expectation changes — add as a `watch_flags` source.

### 2.12 Liquidity/executability of the trim is absent from the whole spec

A "trim 50%" recommendation on a microcap with thin volume is not executable without moving the price against yourself. The engine should output, for every trim, `max_executable_qty_today = participation_cap × 20d_avg_daily_volume` (default participation cap ~10–20% of ADV) and cap the suggested trim at it, splitting the rest into a staged sequence. This is a small addition with outsized practical value for a book that demonstrably includes microcaps. (Source for ADV: not in the three files — see gap G-12; but can default to "trim ≤ X% of current qty per session" until price history arrives.)

### 2.13 Transaction costs are missing from sizing and opportunity-cost math

STT (0.1% each side) + brokerage + impact cost ≈ **0.3–0.5% round trip** for liquid names, **0.5–1.5%+** for microcaps. The §4.2 trim formula and the §E opportunity-cost comparison both need this deducted. A 0.5% round trip on a "free up cash" trim that then sits idle is a pure loss. At minimum, the trim output should carry `est_transaction_cost` and the opportunity-cost test should be `post-tax net-of-cost expected return (holding) vs post-tax net-of-cost expected return (alternative)`.

### 2.14 Factor/theme clustering is a better concentration measure than sector alone

§C uses "sum of allocation % across correlated holdings" as the concentration test, which is right but underspecified: sector is a weak proxy for correlation. E.g., a PSU bank, a private bank, and an NBFC share a *rate/credit* factor far more than their different sector labels suggest; a defence name and a PSU capital-goods name share a *capex* factor. Recommendation: define a small **theme/factor tag set** (rate-sensitive financials, PSU/defence, capex/infra, consumption, pharma, IT, microcap-momentum, etc.), tag every holding once, and compute concentration on **theme sum**, with sector as a secondary check. This is a one-time manual tag pass that dramatically improves the §C signal.

### 2.15 The "opportunity cost" category needs a default hurdle to be computable now

§E requires a scored watchlist, which doesn't exist (gap E-1). Without it, the 10%-weight category is dead. Fix: use a **standing default hurdle** — post-tax expected return of the best available *passive* alternative (Nifty index fund ≈ 10–12% pre-tax long-term expectation, or a liquid/overnight fund ≈ 6.3–6.5% pre-tax as the "wait" rate). The category then computes immediately: *is this holding's forward expected return (from the scoring engine's implied fair value/MOS) above the default hurdle after tax and cost?* When a real watchlist score exists for a specific alternative, it replaces the default. This turns §E from "blocked" to "ready with a coarse proxy," consistent with the spec's own phased philosophy.

---

## 3. Analysis — the scoring architecture under stress

This section tests the architecture against realistic scenarios to expose where it will behave oddly.

### 3.1 Scenario walkthroughs

| Scenario | What the engine does (per spec) | Problem / verdict |
|---|---|---|
| **Kalyan Jewellers: +73% in 81 days** | Stage 1: no gate fires (no pledge, allocation 1.52%, no thesis break). Stage 2: valuation stretch high (likely), position sizing neutral, tax timing *penalizes* exit (81 days → STCG 20%). Composite likely lands in PARTIAL territory but tax drags it down. | **Correct-ish outcome, wrong reason.** A +73%-in-11-weeks position is the single strongest "book something" case in the book, yet the 15% tax weight actively *suppresses* the signal because it's short-term. The engine should distinguish "tax drag on the *decision*" from "tax drag on the *trim size*": the decision to trim a 73%-gainer should not be softened by STCG; the *timing/sizing* should. This is a concrete reason the tax category needs careful sub-scoring (see §3.2). |
| **HDFC Bank: −4.3%, 87 days, blue chip** | No booking signal (it's a loss). But note: it's a *loss* position in a blue chip with a 36-lot build over ~2 months — the averaging-into-losses flag (§9.2) should fire here if lots are sequentially lower. | The behavioral flag is the *only* signal that fires for HDFC Bank, and it fires correctly — this name is the textbook "chasing the average down" pattern (36 lots in ~9 weeks on a name that's still underwater). Good validation that §9.2 matters for their actual book. |
| **Ashoka Buildcon: 16 lots, all red** | Same as above but worse: 16 declining lots over 3 months, every lot negative. | This is a *thesis re-underwrite trigger*, not just a caution flag. The spec caps this at "caution flag"; recommend: when the flag fires **and** the name is in loss **and** lot count ≥ threshold, escalate to "blocked from further adds without written re-underwrite" (a soft-gate, not a hard one). The spec itself says "confirm thesis before adding further" — operationalize it as a required checkpoint in the review workflow. |
| **Bajaj Finance: +20%, 87 days** | Similar to Kalyan but milder; 25 lots. | Likely HOLD or HOLD-watch. Correct. The engine should *not* book a 20%-gainer in a quality NBFC at 87 days — validating that the spec's non-single-metric stance works. |
| **A name 20 days from LTCG, +35%, PE 40 vs own-median 22** | Stage 1 defer-gate → HOLD (no thesis break). | **The §2.1 failure mode.** +35% with a 40/22 PE stretch, deferred 20 days purely for 7.5pp tax, could give back the entire gain and more. Needs the valuation-extreme override. |

### 3.2 The tax category (15% weight) is doing two jobs at once — split them

Looking at the scenarios, the tax input is trying to be both (a) a **timing/sequencing** signal (wait 30 days → LTCG) and (b) a **decision** signal (short-term gains make exits expensive). These should be different mechanics:
- **(a) Timing/sequencing** → belongs in Stage 1 gates and the trim-scheduling logic, *not* in the 0–100 composite. It changes *when* and *how much*, not *whether*.
- **(b) Decision economics** → the composite should only carry *post-tax economics* (e.g., post-tax XIRR vs hurdle), not a blunt "days to LTCG" penalty that mechanically suppresses every exit signal on a short-term book (which, today, is the entire book — meaning 15% of the score is currently a flat tax against *all* booking signals).

**Concrete fix:** move "days to LTCG" out of the Stage 2 tax sub-score entirely. Keep in Stage 2 only: (i) realized-gains headroom usage, (ii) post-tax-vs-hurdle comparison. Let the Stage 1 gate handle deferral. This prevents the tax weight from being a permanent anti-booking bias during the first year of every position.

### 3.3 The band boundaries are hard cliffs with no hysteresis

55 → HOLD-watch; 56 → PARTIAL. A stock scoring 55.6 and 55.4 on consecutive days flips. Fixes: (a) report the composite to 1 decimal with a **distance-to-boundary** field; (b) require a composite to sit in a new band for N consecutive runs before the decision changes (hysteresis), with N=2 for soft bands and N=1 for Stage 1 gates; (c) fold boundary-proximity into the confidence score (§8).

### 3.4 ACCUMULATE has no trigger rule

The spec says ACCUMULATE is a tag on a HOLD candidate that's under-allocated relative to conviction, but never defines the trigger. Recommended rule (all must hold, no order dependency):

```
ACCUMULATE tag iff:
  composite_score ≤ 30 (i.e., decision == HOLD)
  AND conviction_score ≥ high_threshold (from Quality/Growth engines)
  AND current_allocation < target_band_low
  AND valuation_not_stretched (PE/PB premium ≤ ~0, or MOS still positive)
  AND no Stage 1 gate fired
```

It should also *never* fire while the averaging-into-losses flag is active on that name (don't add to a loser the engine already flagged as reactive).

---

## 4. Consolidated gap register

Legend — **Owner:** Ramki-policy = a decision, not data; Data = new export/source needed; Build = code/schema work. **Severity:** 🔴 blocker for that feature; 🟠 major; 🟡 minor. **(new)** = not in the spec's own gap list.

| ID | Category | Gap | Owner | Severity | Closure path |
|---|---|---|---|---|---|
| G-01 | C | Target allocation band per stock/bucket | Ramki-policy | 🔴 | Spec §8.4 — defaults in §7 below |
| G-02 | C | Max single-stock % cap (Stage 1 gate) | Ramki-policy | 🔴 | Default 10% absolute, 8/6/4% by bucket |
| G-03 | D | Realized gains booked this FY (headroom) | Data | 🔴 | Sold-transactions export; until then, engine reports headroom = ₹1.25L "assumed unbooked" with a caveat |
| G-04 | A | Own 5-yr PE/PB historical median | Data | 🟠 | Screener.in export, or **start archiving** and build own series; proxy = peer-relative premium until then |
| G-05 | B | Quality/composite score at entry vs now (time series) | Data | 🔴 | **Start periodic archiving of the screener now** — irrecoverable otherwise |
| G-06 | E | Watchlist scores for opportunity cost | Data | 🟠 | Default hurdle proxy (§2.15) until watchlist scoring exists |
| G-07 | F | 50D SMA, relative strength vs Nifty/sector | Data | 🟡 | Price-history pull per holding + index |
| G-08 | B2 | Cross-engine agreement (Engine2/Filter/Arena) | Build | 🟡 | Feed their outputs; until then, engine reports "single-engine" confidence penalty |
| G-09 | — | **Confidence score definition** | Build | 🔴 | **(new)** §8 |
| G-10 | — | **Tax-defer gate over-binary (valuation-extreme override)** | Build | 🔴 | **(new)** §2.1 |
| G-11 | — | **Backtest universe bias (no sold-position history)** | Data | 🔴 | **(new)** Start full-book + sold archive; backtest stays "mechanics check" for ~12 months |
| G-12 | — | **ADV / liquidity for trim executability** | Data | 🟠 | **(new)** Price-history pull; interim cap = % of qty per session |
| G-13 | — | **Transaction-cost assumptions (STT/brokerage/impact)** | Ramki-policy | 🟡 | **(new)** Config values, defaults in §7 |
| G-14 | — | **Theme/factor tag set for concentration** | Ramki-policy | 🟡 | **(new)** One-time manual tag pass (§2.14) |
| G-15 | — | **Input staleness check + as_of dates** | Build | 🟡 | **(new)** §2.4 |
| G-16 | — | **Negative/zero/nil fundamentals sentinels** | Build | 🟠 | **(new)** PE<0, PEG undefined, negative growth — the negative-PE bug they already caught must be systematic: every ratio gets a validity mask |
| G-17 | — | **Dividend yield as a holding-offset** | Data | 🟡 | **(new)** Minor; add later |
| G-18 | — | **Buyback taxation watch (Budget 2026 change)** | Build | 🟡 | **(new)** Flag names with buyback announcements |
| G-19 | — | **Threshold definitions: quality floor, pledge spike, "notch"** | Ramki-policy | 🔴 | **(new)** §7 defaults |

---

## 5. Design decisions to lock before build (with recommended defaults)

These are the "don't leave implicit" items from §8.2 plus the parameters the spec names but never values. Each has a recommended default so Ramki can sign off in one pass.

| # | Decision | Recommended default | Notes |
|---|---|---|---|
| D-01 | Bucket definitions | Large-cap ≥ ₹20k Cr mcap; Mid ₹5k–20k; Small ₹500–5k; Micro < ₹500 Cr | Aligns with screener's Market Cap field |
| D-02 | Target allocation band | Large 4–8%, Mid 2–5%, Small/Micro 1–3% | Band = "soft range"; hard cap below is absolute |
| D-03 | Absolute max single-stock cap (Stage 1) | 10% (any bucket) | >10% → PARTIAL trim to cap, regardless of view |
| D-04 | Rebalance trigger | position > 1.5× target *mid-point* → trim to band top | Spec's own 1.5x rule |
| D-05 | Quality floor (thesis break) | composite quality < 40/100, **or** drop ≥ 20 points vs entry | "2 notches" ≈ 20 points on 0–100 |
| D-06 | Promoter pledge spike | pledged % > 10%, or ≥ +5pp in one quarter | Hard gate EXIT |
| D-07 | LTCG defer window | 30 days, but with valuation-extreme override (§2.1) | Tier-2 EV check |
| D-08 | Band boundaries | 0–30 HOLD, 31–55 HOLD-watch, 56–75 PARTIAL, 76–100 FULL | Keep spec's values; add hysteresis |
| D-09 | Category weights (default profile) | 25/25/20/15/10/5 (sizing/valuation/quality/tax/opp-cost/technical) | Per-bucket profiles tunable; microcap: sizing↑ valuation↓ technical↑ |
| D-10 | Re-rating share thresholds | >65% strong signal, >80% critical (sliding, not cliff) | §2.10 |
| D-11 | Min meaningful position size | no trim that leaves < 0.5% allocation or < ₹5,000 value | Avoid dust positions |
| D-12 | Participation cap per session | min(10% of 20d ADV, 25% of qty) per session | Staged exit otherwise |
| D-13 | Transaction-cost assumption | 0.35% round trip liquid; 1.0% microcap | Config, revisable |
| D-14 | Default opportunity-cost hurdle | Nifty index 11% pre-tax long-term; liquid fund 6.4% for "wait" | §2.15 |
| D-15 | Review cadence | HOLD+high-conf +90d; HOLD+low-conf +30d; PARTIAL/FULL +7d (verify); Stage-1 fire +1d | §8.6 |

---

## 6. Implementation plan (phased)

### Phase 0 — Policy lock + snapshot archiving starts immediately (0.5 day)
- Ramki signs off D-01…D-15 (adjusting defaults).
- **Start the snapshot archiver today** (even a cron job that copies the fundamentals screener into a dated folder). This is the one action that cannot be retrofitted later and unblocks G-05/G-04 over time.
- Deliverable: `policy.yaml` (versioned) + first archived snapshot.

### Phase 1 — Ingest, reconcile, lots engine (the foundation) (~3–5 days)
- Parsers for the 3 files with **strict date handling** (the files mix `YYYY-MM-DD` and `DD-MM-YYYY` — must disambiguate explicitly, e.g. reject/flag ambiguous dates).
- Symbol normalization table: map full-company names → NSE ticker (Arihant Capital, Canara Robeco AMC, IIFL Capital etc.) — fuzzy match + manual confirmation; names that can't be matched get the partial-data path.
- **Cost-basis reconciliation**: `Σ(lot qty × price) == Invested`, `Σ(lot qty) == Qty Held` per name → hard error on mismatch (validates the AGI Greenpac-style exact match).
- **Per-lot tax engine**: for every lot compute `days_held`, `days_to_ltcg`, `ltcg_eligible`, `lot_gain`, `lot_gain_pct`; FIFO-ordered.
- **Validity masks** for all fundamentals (PE<0, PEG undefined, growth nil) — kills the negative-PE bug class systematically.
- Deliverable: `lots.csv` (per-lot, FIFO-ordered, with tax fields), reconciliation report, data-quality flags (incl. staleness).

### Phase 2 — Stage 1 gates + Stage 2 composite + output schema (~3–5 days)
- Hard gates wired to D-03/D-05/D-06/D-07 (with the §2.1 Tier-2 EV override).
- Category sub-scores 0–100 for A/B/B2/C/D/E/F with the **missing-data renormalization + confidence penalty** (§2.9).
- Weighted composite per bucket profile; band mapping with hysteresis; ACCUMULATE tag (§3.4); confidence model (§8); review cadence (§8.6).
- Output: the §4.3 JSON, **plus** `confidence_breakdown`, `data_completeness`, `tax_status_per_lot`, `fifo_lots_to_sell`, `est_transaction_cost`, `next_review_date`.
- Deliverable: `decisions.json` per holding, log-append only.

### Phase 3 — Trim sizing, behavioral flags, portfolio layer (~2–3 days)
- §4.2 lot-aware trim sizing (max of band-correcting qty vs headroom qty, capped by min-position and participation cap), with per-lot FIFO selection and per-lot tax breakdown.
- Averaging-into-losses detector (§9.2) with the "soft-gate: block adds without re-underwrite" escalation (§3.1).
- Portfolio layer (§5 of spec): rank candidates, theme-concentration rebalance check, tax-year tracker (with S.74 set-off rules from §2.11), redeployment-correlation check.
- Deliverable: portfolio-level report + per-holding execution notes.

### Phase 4 — Shadow-mode backtest + tuning (ongoing, starts after Phase 2)
- Log every decision with input hash; once archive + sold-ledger accumulate (~12 months), run the forward-return replay.
- Weight/boundary tuning via the backtest, not vibes. Until then the engine runs **advisory, never auto-executed** (promote Enhancement #4 to a hard rule).

### Phase 5 — Enhancements (prioritized as the spec lists them)
1. Backtest harness (blocked on data per §2.7, but scaffold now) · 2. Post-tax XIRR field · 3. What-if sensitivity slider · 4. Alert/auto separation (already a principle) · 5. Review cadence (already in Phase 2) · 6. Divergence dashboard.

**Sequencing rationale:** Phase 1 de-risks everything (if the data doesn't reconcile, nothing downstream is trustworthy). Phase 2 is where all the *decisions* live; Phase 3 is mostly arithmetic on Phase 1's lots. Phase 4 is where the spec stops being "sounds sensible" and becomes "tuned to this portfolio."

---

## 7. Appendix A — v1 minimum input set, with the spec's own caveat resolved

The spec's §7 says the top-5 highest-leverage inputs are: (1) allocation vs band, (2) PE/PB vs own median, (3) quality score vs entry, (4) days-to-LTCG, (5) pledge/governance. Cross-checked against the readiness scorecard (§10 of the spec):

| # | Input | Actually ready? | v1 approach |
|---|---|---|---|
| 1 | Allocation vs band | ✅ (data) — but **band is policy** | Lock D-02/D-03 first |
| 2 | PE/PB vs own median | ❌ Gap | **Proxy:** peer-relative premium (ready) + PE level vs 200D SMA; label as proxy |
| 3 | Quality score vs entry | ❌ Gap | **Proxy:** current quality *level* only; start archiving so the *trend* self-heals |
| 4 | Days to LTCG | ✅ per lot | Full fidelity via Phase 1 |
| 5 | Pledge/governance | ✅ | Wire D-06 |

So v1 can ship **with 3 of 5 inputs at full fidelity and 2 at proxy fidelity**, explicitly labelled, with the archive running so the proxies degrade gracefully into the real thing. This is a materially better position than the spec's own Section 7 implies, and it's the honest framing to carry into the build.

---

## 8. Appendix B — concrete mechanics (formulas & pseudocode)

### 8.1 Per-lot tax engine (Phase 1 core)

```
LTCG_PERIOD_DAYS = 365
LTCG_RATE = 0.125 ; STCG_RATE = 0.20
EXEMPTION = 125000

for lot in ledger_lots (grouped by instrument, sorted by trade_date ASC):
    lot.days_held      = (as_of - lot.trade_date).days
    lot.days_to_ltcg   = max(0, 365 - lot.days_held)
    lot.ltcg_eligible  = lot.days_held > 365          # strict: >12 months
    lot.gain           = (ltp - lot.buy_price) * lot.qty
    lot.gain_pct       = (ltp / lot.buy_price - 1) * 100
```

### 8.2 Lot-aware partial-trim sizing (Phase 3, §4.2 + §2.5 + §2.12)

```
# qty to restore allocation to band top
over_alloc_qty = (alloc_pct - target_band_high)/100 * portfolio_value / ltp
# qty whose oldest-lot gain exhausts remaining LTCG headroom
headroom_qty   = remaining_ltcg_exemption / (ltp - oldest_unsold_lot.buy_price)
trim_qty       = max(over_alloc_qty, headroom_qty)          # §4.2
trim_qty       = min(trim_qty, qty_held - min_position_qty) # avoid dust
trim_qty       = min(trim_qty, participation_cap)           # liquidity cap

# FIFO lot selection + per-lot tax
sell = []; qty_left = trim_qty
for lot in lots_order_asc:
    take = min(lot.qty, qty_left)
    sell.append(lot, take,
                tax = take*max(0,lot.gain/lot.qty) *
                      (LTCG_RATE if lot.ltcg_eligible and (exemption_left>0...) else STCG_RATE))
    qty_left -= take
```

### 8.3 Re-rating decomposition (valid ≥ 1yr; proxy below)

```
price_ret = close_now / avg_buy - 1
eps_growth_over_period = forward_eps_growth (from screener)
pe_now = pe_ratio ; pe_entry = pe_ratio / (1 + price_ret) * (1 + eps_growth_over_period)
re_rating_share = ln(pe_now / pe_entry) / ln(1 + price_ret)   # 0..1
# <1yr fallback: label low-confidence; use gain% vs PE premium vs sub-sector
```

### 8.4 Averaging-into-losses detector (Phase 3, §9.2)

```
buys = lots sorted by date
declining_run = 0 ; run_gaps = []
for i in 1..len(buys):
    if buys[i].buy_price <= buys[i-1].buy_price:   # flat or down
        declining_run += 1 ; run_gaps.append(buys[i].date - buys[i-1].date)
    else: declining_run = 0
flag if declining_run >= 3 and net_pnl(holdings) < 0:
    severity = "warn"                      # surface for review
    if declining_run >= 8 or avg(run_gaps) < 30 days:
        severity = "block-adds"            # require written re-underwrite
```

### 8.5 Confidence model (Phase 2 — closes §2.2)

```
confidence = 100
- missing_weight_penalty   # sum of weights of categories with no data (e.g. 25 if valuation missing)
- divergence_penalty       # k * stdev(category_sub_scores) + engine disagreement term
- boundary_penalty         # d if composite within d points of a band edge (0..5)
- proxy_penalty            # e.g. 10 if valuation/quality running on proxies (G-04/G-05)
confidence = clamp(confidence, 20, 95)
```

`confidence_breakdown` is emitted alongside, so a "68" always decomposes into *why*.

### 8.6 Review cadence (Phase 2, Enhancement #5 + D-15)

```
if stage1_gate_fired:                next_review = +1 day
elif decision in {PARTIAL, FULL}:    next_review = +7 days   # verify execution
elif decision == HOLD and conf >= 70: next_review = +90 days
elif decision == HOLD:               next_review = +30 days
if averaging_flag: next_review = min(next_review, +14 days)
```

### 8.7 Proposed tables (append-only where it matters)

| Table | Purpose | Notes |
|---|---|---|
| `lots` | Per-fill FIFO lots + tax fields | Rebuilt each ingest; immutable |
| `positions` | Rolled-up per instrument | Derived from `lots` |
| `fundamentals_snapshot` | Screener export **with `as_of_date`** | **Archive every run** — closes G-05 |
| `decisions` | Append-only: input hash + outputs + conf | Enables backtest + audit |
| `policy` | Versioned weights/bands/thresholds | D-01…D-15 |
| `sold` (future) | Sell transactions | Closes G-03, G-11 |
| `watchlist` (future) | Scored non-held names | Closes G-06 |
| `themes` | Manual theme tags | G-14 |

---

## 9. One-line answers to the open questions in the spec

| Spec question | Answer |
|---|---|
| Per-lot vs per-stock granularity (§8.2) | **Resolved by the ledger — per-lot compute, stock-level recommend, `mixed_ltcg` flag when lots straddle 365 days** (spec already reached this; confirmed) |
| Names missing from screener (§8.3) | Partial-data path with renormalized weights + confidence penalty + a one-off fundamentals pull for those specific names |
| What is "confidence"? (§4.3) | Defined in §8.5 |
| When does ACCUMULATE fire? (§3.4) | Defined in §3.4 |
| Tax gate over-binary? (§2.1) | Two-tier EV override — §2.1 |

---

## 10. What I'd build next (if you want it)

The highest-leverage next step is **Phase 1 + a runnable shadow-mode engine** (Python, CLI or single HTML dashboard), because it (a) proves the reconciliation on your real data, (b) produces the per-lot tax engine that everything else needs, and (c) starts emitting decisions into an append-only log so the backtest clock starts now. Phases 2–3 are then mostly wiring.

If you'd like, I can build the **Phase 1 pipeline + a sample decision output** against synthetic rows matching your file formats (so nothing depends on your real exports), which you can then point at the real CSVs. Just say the word — and if you have preferred values for D-01…D-15 (or want me to use the defaults), tell me before I start.

---

*Sources verified this review:* Budget 2026 left equity LTCG 12.5% (above ₹1.25L), STCG 20%, and the 12-month holding period unchanged [1](https://www.bajajfinserv.in/investments/understanding-long-term-capital-gains-tax); India has no wash-sale rule, so sell-and-rebuy gain/loss harvesting is legal subject only to GAAR [2](https://www.incorpx.io/blog/tax-loss-harvesting-india-strategy-investors).
