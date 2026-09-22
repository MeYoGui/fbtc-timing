# BTC model-fixes decision — per pre-registered rule

Date: 2026-07-02
Experiment: `data/experiments/bitcoin_model_fixes.json`
Pre-registered rules: Task 7 of `docs/superpowers/plans/2026-07-01-btc-model-fixes-experiment.md`

---

## 1. Comparison table (from `bitcoin_model_fixes_report.md`)

| run | edge@5% | edge@10% | precision@10% | IC | scored days (OOS) |
|---|---|---|---|---|---|
| stage1_fixed_labels | -0.2911 | -0.2268 | 1.0 | 0.249 | 3870 |
| stage1c_causal_z | -0.1623 | -0.2244 | 1.0 | 0.2491 | 3870 |
| stage2_continuous | -0.3739 | -0.1774 | 1.0 | 0.2966 | 3870 |
| stage2_family | -0.3874 | -0.8783 | 0.7623 | 0.2506 | 3870 |
| stage2_continuous_family | -0.237 | -0.5924 | 0.8605 | 0.2251 | 3870 |

Coverage metrics use 10% of eligible days — edge@10% uses days with a valid 548-day forward return (381 of 3813), precision@10% uses all scored days (387 of 3870) — with the same day-count across ternary and continuous variants for fair comparison.

---

## 2. Rule-by-rule verdict

### Rule 1 — Correctness fixes adopted unconditionally

**ADOPTED.**

`stage1_fixed_labels` and `stage1c_causal_z` fix two bugs: the forward-looking label leak and the look-ahead z-score. These are not optimizations subject to performance gating — they are correctness repairs. `stage1c_causal_z` (leak-fixed labels + causal z-score) becomes the honest baseline for all downstream comparisons, regardless of metric direction. Its edge@10% is -0.2244 and IC is 0.2491, both slightly changed from the leaky `stage1_fixed_labels` (-0.2268, 0.249). The difference is negligible; the point is irrelevant — correctness fixes are not voted in by OOS numbers.

### Rule 2 — `continuous` scoring

**Pre-registered gate (vs `stage1c_causal_z`):**
1. edge@10% ≥ baseline: `stage2_continuous` = **-0.1774** vs baseline = **-0.2244** → -0.1774 ≥ -0.2244 → **PASS**
2. IC drop < 0.02: IC goes from 0.2491 → 0.2966, a rise of +0.0475 (not a drop) → **PASS**
3. precision@10% drop < 0.05: precision stays at 1.0 → 0.0 drop → **PASS**

**Result: `continuous` passes all three gates.**

Note: this verdict is recorded for the record. Rule 5 (kill criterion, below) fires and overrides adoption decisions.

### Rule 3 — `family_weights`

**Pre-registered gate (vs `stage1c_causal_z`):**
1. edge@10% ≥ baseline: `stage2_family` = **-0.8783** vs baseline = **-0.2244** → **FAIL**

The first gate fails. No further gates are checked. `family_weights` is rejected.

**Combined run condition:** rule 3 also requires that if both `continuous` and `family_weights` pass individually, then `stage2_continuous_family` must also be ≥ baseline on edge@10%. Since `family_weights` failed individually, this condition is moot. For the record: `stage2_continuous_family` edge@10% = -0.5924, which is also worse than baseline (-0.2244), confirming that the combination does not rescue the family weights variant.

**Result: `family_weights` REJECTED. `stage2_continuous_family` not adopted.**

Note: these verdicts are recorded for the record. Rule 5 overrides.

### Rule 4 — Robustness check

**Applies to `stage2_continuous` (the only candidate that passed rules 2–3 before the kill criterion).**

Per-cycle edge@10% for `stage2_continuous`:

| Cycle (halving date) | coverage days | edge@10% |
|---|---|---|
| 2012-11-28 | 72 | -1.5433 |
| 2016-07-09 | 140 | -1.0912 |
| 2020-05-11 | 143 | +1.2486 |
| 2024-04-19 | 24 | +0.0489 |

Edge@10% > 0 in two cycles (2020 and 2024). The rule requires > 0 in at least 2 halving cycles with scored OOS days. **PASS.**

For reference, the honest baseline `stage1c_causal_z` per-cycle:

| Cycle | edge@10% |
|---|---|
| 2012-11-28 | -2.0896 |
| 2016-07-09 | -0.9063 |
| 2020-05-11 | +0.9064 |
| 2024-04-19 | +0.0025 |

Also positive in the same two cycles. The 2024 cycle has only 24 scored OOS days; the positive edge there is economically tiny and statistically meaningless given sample size. The baseline's 2024 value (+0.0025 on 24 days) clears zero by an even thinner margin and carries the same statistical-meaninglessness caveat.

**Result: robustness check PASSES for `stage2_continuous`. Recorded for the record — rule 5 overrides.**

### Rule 5 — Kill criterion

**The rule:** if `stage1c_causal_z` AND every stage2 run have edge@10% ≤ 0, conclude "no demonstrated timing edge once leaks are removed."

Checking:

| run | edge@10% | ≤ 0? |
|---|---|---|
| stage1c_causal_z | -0.2244 | YES |
| stage2_continuous | -0.1774 | YES |
| stage2_family | -0.8783 | YES |
| stage2_continuous_family | -0.5924 | YES |

All four values in scope are negative. **Kill criterion FIRES.**

**Conclusion (verbatim per pre-registered rule): no demonstrated timing edge once leaks are removed.**

### Rule interactions

Rule 5 fires. Rules 2–4 verdicts are recorded above for the record and for intellectual completeness, but they do **not** override the kill criterion. The adoption outcomes from rules 2–4 are void. Phase B scope is determined by rule 5 alone.

---

## 3. Z-threshold diagnostic

From `zscore_threshold_diagnostics` in the JSON:

| method | pct_below_invest(-0.5) | pct_above_avoid(1.5) |
|---|---|---|
| full_history | 0.0172 (1.72%) | 0.0115 (1.15%) |
| expanding | 0.0007 (0.07%) | 0.0000 (0.00%) |

The calibrated thresholds (-0.5 for invest, +1.5 for avoid) sit at materially different percentiles under expanding vs full-history z-scores: under full history, 1.72% of days fall below -0.5; under the causally correct expanding window, only 0.07% do — roughly a 25-fold difference. This means the thresholds are severely miscalibrated for expanding z: the current -0.5 / +1.5 cuts will almost never trigger an invest signal and never trigger an avoid signal under causal scoring, making the existing threshold values unusable as-is. Phase B will need threshold recalibration against the expanding z distribution before any dashboard signal can function as intended.

---

## 4. Positive IC observation

IC (Spearman rank correlation between composite score and 548-day forward return) is approximately 0.25–0.30 across all runs:

- stage1_fixed_labels: 0.2490
- stage1c_causal_z: 0.2491
- stage2_continuous: 0.2966
- stage2_family: 0.2506
- stage2_continuous_family: 0.2251

This is a real observation and deserves honest description. The composite score has genuine rank correlation with forward 548-day returns across the full OOS period: days when the composite is higher tend to be followed by higher forward returns overall. This is what the IC measures.

What IC does not imply: that the top-decile days (the 10% of days the model would flag as "best entry points") outperform buy-and-hold. They do not — every run shows edge@10% < 0. The model correctly rank-orders days in the middle of the distribution better than random, but its highest-confidence "invest" signals are concentrated in periods that happen to be followed by lower-than-average returns. A positive IC combined with a negative top-decile edge is a coherent combination: it means the rank correlation is driven by the model correctly identifying poor periods (low scores → low returns) more than it correctly identifies exceptional entry points.

This combination implies the composite has descriptive value as a cycle-phase indicator but does not support timing entries on its highest-conviction signals. It would be misleading to present it as a timing tool.

---

## 5. Recommended Phase B scope

Rule 5 fires. The rule's mandated scope for Phase B is:

1. **Ship the correctness fixes.** Port the leak-fixed label logic and causal z-score to `compute_all_signals`, `score.py`, and `validate_composite.py`. Run data regeneration.
2. **Reframe the dashboard as descriptive, not predictive.** Remove or relabel any language implying the composite identifies superior entry points. Signal bands (BUY / AVOID etc.) are retained as descriptive cycle-phase labels only, not timing recommendations.
3. **Do NOT add new signals to chase a positive edge@10% number.** Adding signals now would be chasing a metric on a burned OOS series. If future work explores new signals, it requires a fresh plan with a genuinely held-out evaluation window.

Additionally, threshold recalibration (per the z-threshold diagnostic in section 3) is required before any signal threshold can be used in production, even in a descriptive context. The current -0.5/+1.5 thresholds are calibrated to full-history z and will produce near-zero trigger rates under causal expanding z.

Phase B does not include: ETH's `eth_btc_ratio_z` look-ahead fix (separate issue, separate plan), locked-formula test updates beyond what the correctness port requires, or any new model development.
