# Step 1 — RAW vs CURATED reconciliation

**Schema** `VEDANTA_POC` (SAP HANA, read-only) · **As-of** 2025-12-31 · **Scope** `MATERIAL_TYPE IN ('ZSPR','ZSPN')`, `IS_BACKCAST_PERIOD='N'`, Jan-2024 → Dec-2025 · **FY** Apr–Mar
**Default measure** QTY in base UoM. INR appears only where the row says so.

> Nothing is hidden and no value in HANA was altered. Two of the six checks differ; both are explained and carried forward as dashboard warnings.

## Summary

| Item | CURATED | RAW | Diff | Diff % | Status |
|---|---:|---:|---:|---:|---|
| R1 · Gross inventory QTY (base UoM, 6 plants) | 852,059.1 | 852,059.1 | 0.0 | 0.00% | ✅ MATCH |
| R1b · Gross inventory VALUE (INR) | 5,125,222,947 | 5,125,222,947 | 0 | 0.00% | ✅ MATCH |
| R1c · Inventory lines (material × plant SKUs) | 34,717 | 34,717 | 0 | 0.00% | ✅ MATCH |
| R2 · Movement lines in scope | — | 1,531,775 | — | — | ⚪ RAW ONLY |
| R3 · Movement-class counts | see below | see below | 1,199 lines | 3.45% | ⚠️ DIFFERENCE |
| R4 · Reorder point (ROP) total qty | 602,102.3 | 624,047.7 | −21,945.4 | −3.64% | ⚠️ DIFFERENCE |
| Lead time = MAX(planned, actual) + median PR→PO | — | — | — | — | 🚫 UNCOMPUTABLE |

## R1 · Gross inventory by plant — exact match

| Plant | CURATED qty | RAW qty | Diff | Diff % | Lines |
|---|---:|---:|---:|---:|---:|
| HZL_DEMO_01 | 147,723.0 | 147,723.0 | 0.0 | 0.00% | 5,960 |
| HZL_DEMO_02 | 139,630.5 | 139,630.5 | 0.0 | 0.00% | 5,965 |
| HZL_DEMO_03 | 125,535.3 | 125,535.3 | 0.0 | 0.00% | 5,533 |
| HZL_DEMO_04 | 144,996.4 | 144,996.4 | 0.0 | 0.00% | 5,737 |
| HZL_DEMO_05 | 172,972.1 | 172,972.1 | 0.0 | 0.00% | 5,893 |
| HZL_DEMO_06 | 121,201.8 | 121,201.8 | 0.0 | 0.00% | 5,629 |
| **Total** | **852,059.1** | **852,059.1** | **0.0** | **0.00%** | **34,717** |

CURATED `INVENTORY_CLASSIFICATION`, CURATED `INVENTORY_KPI_MONTHLY.GROSS_INVENTORY_VALUE_INR` @ 2025-12 and the RAW snapshot × unit-cost recomputation all agree to the rupee, per plant.

> ⚠️ `INVENTORY_KPI_MONTHLY` carries a seventh `PLANT_ID = 'ALL_PLANTS'` row of ₹5,125,222,947 — a **rollup equal to the six plants**, not a plant. Summing all seven double-counts to ₹10.25 bn. Every plant filter must exclude it.

## R2 · Movement lines in scope (RAW baseline — no curated counterpart)

| MovType | Meaning | Lines | Qty |
|---|---|---:|---:|
| 261 | Issue to order — **demand** | 1,317,733 | 3,167,766.25 |
| 262 | Issue reversal — **demand offset** | 75,513 | 79,397.00 |
| 101 | Goods receipt vs PO | 130,567 | 2,661,219.97 |
| 102 | GR reversal | 4,534 | 13,905.34 |
| 702 | Physical-inventory loss | 1,822 | 3,469.33 |
| 701 | Physical-inventory gain | 1,606 | 3,227.39 |

**Net demand (261 − 262) = 3,088,369.25** base-UoM units across 24 months and 34,713 material-plant pairs.

## R3 · Movement-class counts — 1,199 lines differ (3.45%)

| Movement class | CURATED | RAW (brief's rule) | Diff | Diff % |
|---|---:|---:|---:|---:|
| ACTIVE (≤90d) | 18,723 | 18,723 | 0 | 0.00% |
| SLOW_MOVING (≤180d) | 9,196 | 9,196 | 0 | 0.00% |
| NON_MOVING (≤365d) | 2,934 | 4,133 | −1,199 | −29.01% |
| OBSOLETE (>365d) | 3,864 | 2,665 | +1,199 | +44.99% |

**Root cause.** 1,195 lines are flagged `OBSOLETE` in the curated table while their *own* `DAYS_SINCE_LAST_CONSUMPTION` sits in the 181–365 bucket — which is `NON_MOVING` under the brief. The curated ageing itself is not in dispute: it matches the RAW last-261 date on **1,195 of 1,195** of those lines. Only the NM→OBS cut-point differs; the curated rule breaks below 365 days. A further **4** lines have no 261 movement ever and are flagged `OBSOLETE`, where the brief makes never-issued `NON_MOVING`. 1,195 + 4 = 1,199.

**Impact.** ACTIVE and SLOW_MOVING are untouched, so **SMI is safe**; **NMI and the Obsolete KPI move materially** with the rule chosen.
**Resolution.** The dashboard computes NM/SM/OBS from the brief's rule (RAW) and shows the CURATED figure beside it with this warning. Neither is changed in HANA.

## R4 · Reorder point — −3.64% in aggregate, far wider line by line

| Measure | CURATED | RAW | Diff | Diff % |
|---|---:|---:|---:|---:|
| ROP total qty | 602,102.3 | 624,047.7 | −21,945.4 | −3.64% |
| Trailing-12m demand | 2,091,095.4 | 1,770,896.3 (net 261−262) | −320,199.1 | −15.31% |
| Trailing-12m demand | 2,091,095.4 | 1,815,618.3 (issues-only 261) | −275,477.1 | −13.17% |
| Lines within ±20% ROP tolerance | 16,340 of 34,717 (47.1%) | | | |

**Root cause — two drivers.**
1. **Lead time.** RAW here uses `PLANNED_DELIVERY_DAYS` only. The brief's rule is `MAX(planned, actual) + median PR→PO`, so this RAW ROP is a **lower bound** and will rise in step 2.
2. **Demand basis.** Curated `TRAILING_12M_DEMAND_QTY` matches **issues-only (261)** on 25,925 of 34,717 lines but **net (261−262)** on only 18,927 — it behaves like a gross-issues measure, not the brief's net definition. Neither matches exactly, so a third adjustment (a different 12-month window, or backcast rows included) is also present.

**Resolution.** Dashboard ROP is recomputed from RAW once actual lead time and median PR→PO land; the ±20% ROP flag is driven off that. Curated ROP is retained as the SAP-master comparison column.

## 🚫 UNCOMPUTABLE in step 1

| Item | Reason |
|---|---|
| Lead time = MAX(planned, actual) + median PR→PO | Only `DIM_MATERIAL.PLANNED_DELIVERY_DAYS` is resolved. Actual lead time needs `FACT_GOODS_RECEIPT ⋈ FACT_PURCHASE_ORDER`; median PR→PO needs `FACT_PURCHASE_REQUISITION ⋈ FACT_PURCHASE_ORDER` — and PR and PO each exist as a base **and** a `_V2` table whose precedence is not yet established. Deferred to step 2 rather than guessed. Every ROP figure above is therefore a planned-lead-time lower bound. |

## Schema traps the next step must respect

1. **`FACT_MATERIAL_MOVEMENT` is 4 date-ordered partitions** (500k/500k/500k/164,301). `PART_001` alone covers 2023-01-12 → 2024-07-19 — querying it alone silently drops **17 of the 24 in-scope months**. Always `UNION ALL` all four.
2. **`FACT_INVENTORY_SNAPSHOT` is 3 partitions.** `PART_001` ends 2024-03-31; the 2025-12-31 snapshot is not in it.
3. **Every RAW `DIM_*`/`FACT_*` column is `NVARCHAR`** — including `QUANTITY`, `CLOSING_QTY`, `UNIT_COST_INR`. Cast with `TO_DECIMAL(col,18,3)` before arithmetic. Only the CURATED tables carry real `DECIMAL`/`DATE`.
4. **`IS_BACKCAST_PERIOD='Y'` lives only in movement `PART_001`** (132,526 rows, all pre-2024).
5. **`TOP` is reserved in HANA** and cannot be a CTE alias — it returns a bare syntax error.
6. **`DATA_DICTIONARY` has only 14 rows** across 42 tables; it is a sample, not the schema. Resolve columns from `SYS.TABLE_COLUMNS`.

## Other data-quality findings

| Severity | Finding |
|---|---|
| ⚠️ | `ALL_PLANTS` rollup row in `DIM_PLANT` and `INVENTORY_KPI_MONTHLY` — exclude from plant sums. |
| ℹ️ | 4 of 34,717 classified material-plant pairs have **no 261 movement ever** → never-issued → `NON_MOVING` per the brief. |
| ℹ️ | Material group **LUBRICANTS** has months with no 261/262 movement at all; its series carries **nulls, not zeros**. Forecasting must handle the gap explicitly and not impute. |
| ℹ️ | Sparse months in the material-level series are **true gaps**, not zeros — see the `note` field in `step1/aggregates/top_material_plant_series.json`. |

## Files

| Path | What it is |
|---|---|
| `step1/step1_data.json` | The step-1 deliverable: profile, scope, schema traps, demand definition, reconciliation, warnings, uncomputable items, aggregate index |
| `step1/sql/step1_demand_material_plant_month.sql` | Canonical Material × Plant × Month net-demand grain (GROUP BY only) |
| `step1/sql/step1_reconciliation.sql` | The four reconciliation queries R1–R4, verbatim |
| `step1/aggregates/plant_month.json` | Net demand by plant × month, with 261 / 262 / active-SKU counts |
| `step1/aggregates/type_group_month.json` | Net demand by material type × material group × month |
| `step1/aggregates/criticality_month.json` | Net demand by VITAL/ESSENTIAL/DESIRABLE × month, with service-level targets |
| `step1/aggregates/top_material_plant_series.json` | Top 30 material × plant series for forecast smoke-testing and drilldown seeding |
