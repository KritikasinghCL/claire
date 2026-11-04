# HZL Stores & Spares — Inventory Control Center (POC)

Interactive inventory dashboard over the synthetic `HZL_DEMO` dataset in **SAP HANA Cloud**, schema `VEDANTA_POC`, with forecasting supplied exclusively by the **ContextFlow MCP**.

Nothing in this repository fabricates a number. Every figure traces to a query in `step1/sql/`, and anything that cannot be computed is labelled `UNCOMPUTABLE` with its reason rather than estimated.

## Scope

| | |
|---|---|
| Material types | `ZSPR`, `ZSPN` |
| Filter | `IS_BACKCAST_PERIOD = 'N'` |
| Period | 2024-01-01 → 2025-12-31 |
| As-of | 2025-12-31 |
| Fiscal year | Apr–Mar |
| Default measure | **QTY in base UoM** (SKU = material-plant line count). INR only when the Qty/Value toggle is set to Value. |
| Demand | Net issues = MovType **261 − 262**, by Material × Plant × Month |

## Pipeline

| Step | Output | State |
|---|---|---|
| **1 · Profile & reconcile** | `step1/step1_data.json`, `step1/reconciliation.md` | ✅ done |
| 2 · Lead time, ROP, classification | — | pending |
| 3 · ContextFlow forecast (3/6/9/12 mo, 6-mo holdout) | — | pending |
| 4 · `dashboard.html` + `dashboard_data.json` + `.xlsx` + `.pptx` | — | pending |

## Step 1 — what it established

- **6,000** materials in scope across **6 physical plants** and **12 material groups**; **34,717** material-plant SKU lines; **34,713** of them moved in the period.
- Net demand **3,088,369.25** base-UoM units over 24 months (261: 1,317,733 lines / 3,167,766.25; 262: 75,513 lines / 79,397.00).
- Gross inventory reconciles **exactly** between CURATED and RAW — 852,059.1 base UoM, ₹5,125,222,947 — per plant, to the rupee.
- **Two real differences**, both carried forward as dashboard warnings rather than smoothed over: movement-class counts (1,199 lines, 3.45%) and reorder point (−3.64% aggregate, only 47.1% of lines within ±20%).
- **One UNCOMPUTABLE**: lead time `MAX(planned, actual) + median PR→PO` — actual lead time and PR→PO latency need the PR/PO/GR facts, and PR and PO each exist as a base and a `_V2` table whose precedence is unresolved.

Full detail, with CURATED / RAW / Diff / % for every check: **[`step1/reconciliation.md`](step1/reconciliation.md)**.

## Traps in this schema — read before writing a query

1. `FACT_MATERIAL_MOVEMENT` is **4 date-ordered partitions**. `PART_001` alone covers 2023-01-12 → 2024-07-19 and silently drops 17 of the 24 in-scope months. Always `UNION ALL` all four.
2. `FACT_INVENTORY_SNAPSHOT` is **3 partitions**; `PART_001` ends 2024-03-31 and does not contain the 2025-12-31 snapshot.
3. Every RAW `DIM_*`/`FACT_*` column is **`NVARCHAR`**, including `QUANTITY`, `CLOSING_QTY` and `UNIT_COST_INR`. Cast with `TO_DECIMAL(col,18,3)` before arithmetic. Only CURATED tables carry real `DECIMAL`/`DATE`.
4. `PLANT_ID = 'ALL_PLANTS'` is a **rollup**, not a plant. Summing all seven `PLANT_ID` values double-counts gross inventory to ₹10.25 bn.
5. `IS_BACKCAST_PERIOD = 'Y'` rows exist **only** in movement `PART_001` (132,526 rows, all pre-2024).
6. **`TOP` is reserved in HANA** and cannot be used as a CTE alias — it returns a bare syntax error.
7. `DATA_DICTIONARY` holds **14 rows** across 42 tables; it is a sample, not the schema. Resolve columns from `SYS.TABLE_COLUMNS`.

## Layout

```
step1/
  step1_data.json                          profile + reconciliation + warnings + aggregates
  reconciliation.md                        CURATED / RAW / Diff / % tables
  sql/
    step1_demand_material_plant_month.sql  canonical Material x Plant x Month net-demand grain
    step1_reconciliation.sql               reconciliation queries R1-R4, verbatim
  aggregates/
    plant_month.json                       net demand by plant x month
    type_group_month.json                  net demand by material type x group x month
    criticality_month.json                 net demand by VITAL/ESSENTIAL/DESIRABLE x month
    top_material_plant_series.json         top 30 material x plant series for forecast smoke-testing
```

## Running the queries

HANA access is read-only through the connected SAP HANA integration — `hana_list_tables` to discover, `hana_query` to run. The `.sql` files are the exact statements behind every figure here; paste one in and it reproduces the number. Aggregate `GROUP BY` only: no row-level extract is ever pulled out of HANA.

## Conventions

- **Never alter a value — flag it.** A disagreement between CURATED and RAW is published with both figures and the root cause; it is never reconciled by overwriting one side.
- **Sparse months are gaps, not zeros.** A missing month in a series means no 261/262 movement occurred. Do not impute.
- **Forecasts come from ContextFlow only.** No hand-rolled forecast, ever.
