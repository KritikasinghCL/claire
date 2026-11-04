# S-8 verification — does `dashboard_data.json` cover the 12 sections and the 13 KPIs?

**Verdict: PASS on coverage. 0 blocking gaps, 0 real content gaps, 4 cosmetic label advisories.**
**But three CRITICAL warnings inside the artefact mean the dashboard it feeds cannot yet meet the goal's SUCCESS criterion.** Those are S-3/S-7 defects, not S-8 defects — recorded here so they are not lost between tickets.

Reviewer: Maya (Scrum Master). Artefact under test: `step3/dashboard_data.json`.
Gates: `tools/verify_dashboard_coverage.py` (structure) and `tools/verify_dashboard_depth.py` (content).
Both are committed on this branch and re-runnable; this report quotes their actual output.

---

## 1. Section coverage — 12 / 12 present, none hollow

| Section | Cards | Content blocks | Data rows | UNCOMPUTABLE |
|---|---:|---:|---:|---:|
| kpi_scorecard | 6 | 7 | 73 | 1 |
| demand_forecast | 5 | 13 | 96 | 12 |
| inventory_health | 4 | 8 | 58 | 0 |
| over_understock | 4 | 8 | 59 | 0 |
| nm_sm | 5 | 6 | 66 | 0 |
| shutdown_maintenance | 4 | 6 | 76 | 2 |
| pr_recommendations | 5 | 8 | 80 | 0 |
| mrp_rop | 6 | 7 | 54 | 3 |
| duplicate_sku | 4 | 5 | 60 | 1 |
| plan_vs_actual | 4 | 7 | 67 | 1 |
| data_sources | 6 | 10 | 17 | 0 |
| raia | 0 (by design) | 14 | 71 | 0 |

**Hollow-block scan: `none — every container carries content`.** No key is present with an empty list or dict behind it. That was the failure mode most worth testing for: a structural gate that passes on keys alone would not have caught it.

## 2. The 13 KPIs — all present, all with target / actual / variance / status / basis

| Code | Target | Actual | Variance | Status |
|---|---:|---:|---:|---|
| GROSS_INVENTORY_REDUCTION | 10.0 | 29.1318 | +19.1318 | GREEN |
| NMI | 10.0 | −1.398 | −11.398 | RED |
| SMI | 20.0 | −90.3924 | −110.3924 | RED |
| OBSOLETE_REDUCTION | 5.0 | 90.2447 | +85.2447 | GREEN |
| QTY_ACCURACY | 90.0 | 52.2482 | −37.7518 | RED |
| INVENTORY_FORECAST_ACCURACY | 90.0 | — | — | **UNCOMPUTABLE** |
| NM_SM_F1 | 0.9 | 0.510731 | −0.3893 | RED |
| VITAL_AVAILABILITY | 95.0 | 88.7485 | −6.2515 | AMBER |
| ROP_COVERAGE | 100.0 | 100.0 | 0.0 | GREEN |
| DUPLICATE_SKU | 0.0 | 1125 | +1125 | INFO |
| PR_DATE_ADHERENCE | 95.0 | 97.7579 | +2.7579 | GREEN |
| PR_COUNT_YOY | 10.0 | 34.9219 | +24.9219 | RED |
| NOM_DAYS | 90.0 | 121.66 | +31.66 | RED |

Status mix: **4 GREEN · 1 AMBER · 6 RED · 1 UNCOMPUTABLE · 1 INFO.**

No KPI carries a null actual without a reason, and none carries a null actual with a non-UNCOMPUTABLE status. Every KPI has a `basis`. The single UNCOMPUTABLE is honestly labelled:

> `INVENTORY_FORECAST_ACCURACY`: No inventory-position forecast exists. ContextFlow experiment `6ae894a219423a530ab79f69` forecasts consumption quantity (target `actual_qty`), not inventory position.

That is the correct call. Fabricating an inventory-position accuracy from a consumption model would have been the wrong answer, and it was not done.

### One KPI to read with care

`PR_COUNT_YOY` shows **actual 34.9219 against target 10.0 with variance +24.9219 and status RED**. Positive variance with a RED status looks self-contradictory at a glance. The target is a *reduction* of ≥10% in PR count year-on-year; the actual is a 34.9% *increase*. The status is right and the variance sign follows the raw arithmetic. **Recommend the builder add an explicit `direction` field** so the dashboard tile does not render a green arrow on a red KPI. Advisory, not blocking.

## 3. The four card-label advisories — all cosmetic, adjudicated on payload

The coverage gate flagged four brief-named card terms it could not find in a label. The depth gate printed each full card payload. All four are wording, not absence:

| Advisory | Finding |
|---|---|
| `over_understock` / "no-demand" | Card exists as **"No demand"** = 2,782 SKU lines, ₹348,339,940.04, with its definition. Hyphen vs space. |
| `nm_sm` / "at-risk" | Card exists as **"NM + SM at risk"** = 13,329 SKU lines, 380,674.446 base UoM. |
| `pr_recommendations` / "value" | PR value is present as `value_inr` on **every** PR card (₹4,744,629,655.45 recommended; ₹3,681,308,830.15 raise-immediately) — carried as a field rather than its own tile. |
| `mrp_rop` / "adjusted" | Expressed as the **Increase (21,673) / Decrease (5,244)** recommended pair = 26,917 adjusted lines. |

**No card the brief names is missing.** The gate's own string match was too literal; the evidence says the content is there.

## 4. RAIA — 12 / 12 sub-items, all non-empty

`engine` (5 keys) · `contextflow_model` (10) · `raw_vs_curated` (2) · `reconciliation` (5) · `accuracy` (7) · `limitations` (5 items) · `uncomputable_items` (9 items) · `assumptions` (5) · `data_quality` (7) · `forecast` (4) · `top_risks` (7) · `actions` (6 items).

## 5. Cross-section agreement — 7 / 7 MATCH

Where a number appears in two places it agrees to the digit: vital availability 88.7485, NM/SM F1 0.510731, NOM days 121.66, stock 852,059.19, NOM lines 15,990, PR lines 14,631, and understock lines == PR lines 14,631. No section tells a different story from another.

## 6. Reconciliation — 8 items, 3 MATCH exactly, differences disclosed not hidden

| Item | Curated | RAW | Diff | Status |
|---|---:|---:|---:|---|
| Gross inventory QTY | 852,059.1 | 852,059.1 | 0 (0.0%) | MATCH |
| Gross inventory VALUE INR | 5,125,222,947 | 5,125,222,947 | 0 (0.0%) | MATCH |
| Inventory line count | 34,717 | 34,717 | 0 (0.0%) | MATCH |
| Movement line counts | — | 261: 1,317,733 · 262: 75,513 · total 1,531,775 | — | RAW_ONLY |
| Movement-class counts | NM 2,934 / OBS 3,864 | NM 4,133 / OBS 2,665 | 1,199 lines (3.45%) | DIFFERENCE |
| Reorder point (recompute) | 602,102.3 | 624,047.7 | −21,945.4 (−3.64%) | DIFFERENCE |
| ROP total (engine vs curated table) | 120,099.152 | 818,303.519 | +698,204.367 (581%) | DIFFERENCE — different populations |
| Movement class (engine rule vs curated) | — | — | 1,199 lines (3.45%) | DIFFERENCE |

The brief says never hide a difference. It does not: all three differences carry a stated cause.

## 7. Provenance

`ExtraTreesMSE` · experiment `6ae894a219423a530ab79f69` · run `2026-11-04T20:03:06Z` · as-of `2025-12-31` · **default measure `QTY`** as the brief requires.

## 8. 17 warning banners — three are CRITICAL and block the goal's SUCCESS criterion

These are **not** S-8 defects. The artefact carries them correctly and visibly. They are S-3/S-7 defects that S-8 inherited:

1. **`FORECAST_ARTEFACT_MISSING`** — `step2_forecast.json` does not exist.
2. **`FORECAST_CANNOT_EXTRAPOLATE`** — a predict for 2099-06 returns exactly 2026-06's value (1397.11669921875). Forward horizons replay history rather than project it.
3. **`FORECAST_NOT_MATERIAL_GRAIN`** — `MATERIAL_ID` is not a model feature; MAT-000001 and MAT-005999 return byte-identical predictions.

**Consequence, stated plainly:** all four forecast cards (3/6/9/12-month) are UNCOMPUTABLE, and `demand_forecast` carries 12 UNCOMPUTABLE items — the most of any section. The goal's SUCCESS criterion is *"drill Plant → Material Type → Material Group → Material and see historical + forecast quantity"*. The historical half is sound and reconciles exactly. **The forecast half cannot be served at material grain from this experiment.** That turns on the commander's descope-or-re-run decision already raised on S-3.

Nine further warnings disclose real data limits rather than failures: no MRP-type column anywhere in VEDANTA_POC (42 tables / 377 columns scanned), `BUSINESS_PLAN_VS_ACTUAL` value-only with no quantity columns, and every one of the 36 shutdown events `COMPLETED` with no forward-dated event — which is why "Projected shutdowns" is UNCOMPUTABLE rather than invented.

---

## Verdict and recommendation

| Question | Answer |
|---|---|
| 12 sections present and populated? | **Yes** — 0 hollow containers |
| 13 KPIs with target/actual/variance/status/basis? | **Yes** — 13/13 |
| Any fabricated number? | **No** — gaps labelled UNCOMPUTABLE with a reason |
| Reconciliation differences hidden? | **No** — 8 items, 3 differences each with a cause |
| Real content gap? | **None** — 4 advisories all cosmetic |
| Ready to call Done? | **Not yet** — see below |

**S-8's own scope passes.** I am not moving it to Done: that needs the team lead's explicit go-ahead, and two things should land first —

1. **`direction` on each KPI** so `PR_COUNT_YOY` and the other lower-is-better KPIs do not render a green arrow on a RED status. Small, and the dashboard reads wrong without it.
2. **The S-3 forecast decision.** Until the material grain is either re-run with `MATERIAL_ID` as a feature or formally descoped and labelled an allocation, the forecast half of the SUCCESS criterion is unreachable and four cards stay UNCOMPUTABLE.

## Re-running these gates

```bash
python3 tools/verify_dashboard_coverage.py   # structure; exit 0 = PASS -> verify_out/coverage.txt
python3 tools/verify_dashboard_depth.py      # content;   exit 0 = no real gaps -> verify_out/depth.txt
```

Both exit 2 with a clear message if `step3/dashboard_data.json` is absent, so they are safe to wire into CI ahead of the artefact landing. **Note the standing CI gap flagged on step 1: the repository still reports "no checks configured", so nothing gates these automatically yet.**
