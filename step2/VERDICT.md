# Step 2 — verification verdict: **BLOCKED**

Verified by Maya (Scrum Master) on 2026-11-04 against the ContextFlow MCP and SAP HANA
`VEDANTA_POC` directly. Machine-checkable evidence: `step2/contextflow_evidence.json`,
enforced by `tools/verify_step2_contextflow.py` (50 checks, exit 0).

## 0. The deliverable does not exist

`step2_forecast.json` is **ABSENT** — not in the workspace (`find / -name 'step2_forecast*'`
returned nothing), not on the remote (GitHub 404 on `step2/step2_forecast.json`), not in
`git ls-files`. S-3 is genuinely in progress. What exists is the forecast **input** design:
`step2/sql/step2_cohort_history.sql` and `step2/tools/fetch_notes.md`.

So this verification is against the deployed ContextFlow experiments themselves.

## 1. What is sound

| Check | Verdict | Evidence |
|---|---|---|
| Engine is ContextFlow | ✅ | AutoML `enabled: true`, engine `onprem`, 2 CPUs |
| Task is **regression**, not classification | ✅ | `problemType: regression` on dataset *and* endpoint; `probabilities: null`, `decisionThreshold: null` on a live predict; diagnostics are `kind: regression` |
| Target is a **quantity** | ✅ | `targetColumn: actual_qty`; live predict returned continuous `1290.153…`; holdout actuals include `0` and `-1` |
| Model chosen by ContextFlow, not by us | ✅ | `bestCandidateId` returned by the engine and matches `endpoint.candidateId`; no `champion` call made |
| Endpoint live | ✅ | POST predict → 200 with numeric predictions, 2026-11-04T18:10:21Z |
| **Forecast input grain** | ✅ | re-derived against HANA — see §3 |

## 2. Model, evaluation, accuracy — verbatim

**Experiment `6ae894a219423a530ab79f69`** · job `contextflow-184ddfa1979f4ae2a294` · 11 candidates · 484.2s

| Rank | Model | RMSE | MAE | R² |
|---:|---|---:|---:|---:|
| **1** | **ExtraTreesMSE** | **172.503385** | 52.051765 | 0.716757 |
| 2 | WeightedEnsemble_L2 | 174.086569 | 44.088502 | 0.711535 |
| 3 | NeuralNetTorch | 178.123274 | 43.592121 | 0.698002 |
| 4 | RandomForestMSE | 181.142213 | 49.053176 | 0.687678 |
| 5 | XGBoost | 191.337482 | 52.373099 | 0.651532 |
| … | … | … | … | … |
| 11 | KNeighborsUnif | 341.540746 | 133.451528 | −0.110320 |

> **Why it ranked #1 (engine's own basis):** candidates were ranked on holdout
> `root_mean_squared_error`, the declared `primaryMetric`. ExtraTreesMSE scored the lowest
> of 11. Margin over second place: **1.583184 RMSE = 0.91%** — thin.

Top features: `MOVEMENT_CLASS` 170.34 · `MATERIAL_GROUP` 154.39 · `month` 117.89 · `SHUTDOWN_FLAG` 81.97.

## 3. HANA re-verification of the forecast input — all PASS

Every quantitative claim in the step-2 SQL header re-run independently:

| Claim | HANA returned | |
|---|---|---|
| `SUM(Q)` = step-1 net demand | `3,088,369.252` | ✅ exact |
| 2,027 cohorts | `2027` | ✅ exact |
| 30,861 cohort-month rows | `30861` | ✅ exact |
| 24 months | `24` | ✅ |
| `ALL_PLANTS` excluded | `0` rows | ✅ |
| 34,717 SKU lines → 2,027 cohorts | confirmed from a *second* table | ✅ |
| CATEGORY_MAP 12 pairs / 5 categories | all 12 match verbatim | ✅ |

Also for step 3: **154** zero-demand and **242** negative-demand cohort-months (real 262
reversals — do not clip without saying so).

## 4. Six blocking defects

**D1 — the holdout is not the brief's holdout.** `splitStrategy: deterministic_random_holdout`,
`holdoutFraction: 0.2`, 1,200 of 6,000 rows. That is a **random** 20% split over a time series:
2025-12 rows can train while 2024-03 rows test. The reported accuracy is optimistic and is
**not forecast accuracy**. The correct split is 2025-07..2025-12 = **5,283 of 30,861 rows
(17.12%), 937,113.778 base UoM**.

**D2 — the published accuracy belongs to the runner-up.** The diagnostics block reports
`rmse 174.086569 / r2 0.711535` — those are **WeightedEnsemble_L2's** numbers (rank 2), not
ExtraTreesMSE's (`172.503385 / 0.716757`). **WAPE 0.477518 is the runner-up's WAPE.** Quoting it
as "the ContextFlow model's accuracy" is wrong.

**D3 — `MATERIAL_ID` is not a feature.** Proven, not asserted: two predict rows identical except
`MATERIAL_ID` `MAT-000001` vs `MAT-005999` both returned **`1290.1533203125`** — byte-identical.
The model is blind to material. **The SUCCESS criterion "drill … → Material and see forecast
quantity" cannot be met.** A material-level number would be the cohort number repeated and must
be labelled an *allocation*, not a forecast.

**D4 — the model cannot extrapolate.** Same cohort, month varied:

| 2024-06 | 2025-12 | 2026-06 | 2030-06 | **2099-06** |
|---:|---:|---:|---:|---:|
| 786.42 | 1268.20 | 1397.12 | 1443.40 | **1397.12** |

2099-06 returns **exactly** 2026-06's value. A tree ensemble flattens onto the nearest learned
leaf. Forward months are a **seasonal replay of 2024-25, not a projection** — a 12-month-ahead
number carries no more information than a 1-month-ahead one.

**D5 — two live endpoints, 35% apart.** Experiment `6ae8a3b619423a530ab79f89` is *also*
`in_service` on the same asset: RMSE 232.885196, WAPE 0.598288, R² 0.483766. The dashboard must
pin an experiment id or it can silently serve the weaker model.

**D6 — Qty Accuracy fails its target.** `1 − WAPE = 1 − 0.477518 = ` **52.2%** against a **>90%**
target → **RED**. And that is the *optimistic* random-split figure.

Also: **MAPE is UNCOMPUTABLE.** Every leaderboard candidate reports
`mean_absolute_percentage_error` of order 1e15–5e16 (ExtraTreesMSE: 1.85e15) because the target
contains zeros — HANA confirms 154 zero-demand cohort-months. Report WAPE; label MAPE with this
reason.

## 5. Not evidenced

- **Horizons 3/6/9/12** — no horizon parameter exists on either experiment. This is a tabular
  regressor over a `month` feature, not a horizon-aware forecaster.
- **`forecastEvaluation` / `predictBatch`** — the brief names these. The AutoML surface exposes
  `predict` (≤1000 rows), `diagnostics`, `model_card`, `pipeline`. No `forecastEvaluation` or
  `predictBatch` action is registered. Horizons must be produced by calling `predict` once per
  forward month, and the dashboard must say that is what it did.

## 6. Resolution

Re-run with a **time-ordered holdout on 2025-07..2025-12**, and either add `MATERIAL_ID` as a
feature or **formally descope the material grain and label it**. Until then, no forecast number
reaches the dashboard without the warning banner the brief requires.

## 7. Reproduce this

```
$ python3 tools/verify_step2_contextflow.py
OK — 50 checks passed.          # exit 0
```

The validator re-derives the arithmetic rather than reading it, and enforces each defect as a
test — mutating the evidence to hide D2, D3 or D6 makes it fail with 5 named checks.
