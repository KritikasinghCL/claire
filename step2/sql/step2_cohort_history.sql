-- STEP 2 — ContextFlow forecast input grain.
--
-- WHY THIS GRAIN: the deployed ContextFlow endpoint's own featureColumns are
--   [month, PLANT_ID, CATEGORY, MATERIAL_GROUP, MATERIAL_TYPE, CRITICALITY,
--    MOVEMENT_CLASS, SHUTDOWN_MATERIAL_FLAG]
-- read back from AutoMlController endpoint. MATERIAL_ID is NOT a feature, so the
-- finest unit the model can actually distinguish is the 7-way cohort below.
-- Forecasting per Material x Plant would feed the model 34,713 rows that are
-- identical in every feature it reads -> one repeated number dressed up as
-- 34,713 distinct forecasts. We forecast the cohort and record the limitation.
--
-- VERIFIED EMPIRICALLY 2026-11-04 (Maya, Scrum Master): two predict rows
-- identical except MATERIAL_ID 'MAT-000001' vs 'MAT-005999' both returned
-- 1290.1533203125 — byte-identical. The model is provably blind to material.
-- This is no longer an inference from featureColumns; it is a measurement.
-- See step2/contextflow_evidence.json and step2/VERDICT.md defect D3.
--
-- Measure: NET_DEMAND = 261 qty - 262 qty, base UoM (NOT INR).
-- Scope:   MATERIAL_TYPE IN ('ZSPR','ZSPN'), IS_BACKCAST_PERIOD='N',
--          2024-01-01..2025-12-31, as-of 2025-12-31, PLANT_ID <> 'ALL_PLANTS'.
--
-- TRAPS honoured (see README): all 4 movement partitions UNION ALL'd;
-- every RAW column is NVARCHAR so quantities are TO_DECIMAL(...,18,3) cast;
-- ALL_PLANTS is a rollup and is excluded via the MATERIAL_PLANT_CLASSIFICATION join.
--
-- RE-VERIFIED AGAINST HANA 2026-11-04 — every figure below was re-run, not trusted:
--   SUM(Q)             = 3,088,369.252  == step1 net_demand_qty_total (exact match)
--   cohorts            = 2,027          (exact)
--   cohort-month rows  = 30,861         (exact)
--   distinct months    = 24
--   ALL_PLANTS rows    = 0              (the rollup is correctly excluded)
-- Cross-check from a second table: MATERIAL_PLANT_CLASSIFICATION's 34,717
-- in-scope material-plant lines collapse to exactly 2,027 distinct cohorts.
--
-- FOR STEP 3 — two facts the forecast must not silently swallow:
--   154 cohort-months have ZERO net demand      -> MAPE is uncomputable (div/0)
--   242 cohort-months have NEGATIVE net demand  -> real 262 reversals exceeding
--       261 issues. Do NOT clip these to zero without saying so in the output.
--
-- The series is packed one row per cohort ("YYYY-MM:qty;...") so the whole grain
-- transfers in a few paged calls; aggregate GROUP BY only, no row-level extract.

WITH MM AS (
  SELECT MATERIAL_ID,PLANT_ID,MOVEMENT_TYPE,QUANTITY,POSTING_DATE,IS_BACKCAST_PERIOD
    FROM VEDANTA_POC.FACT_MATERIAL_MOVEMENT_PART_001
  UNION ALL
  SELECT MATERIAL_ID,PLANT_ID,MOVEMENT_TYPE,QUANTITY,POSTING_DATE,IS_BACKCAST_PERIOD
    FROM VEDANTA_POC.FACT_MATERIAL_MOVEMENT_PART_002
  UNION ALL
  SELECT MATERIAL_ID,PLANT_ID,MOVEMENT_TYPE,QUANTITY,POSTING_DATE,IS_BACKCAST_PERIOD
    FROM VEDANTA_POC.FACT_MATERIAL_MOVEMENT_PART_003
  UNION ALL
  SELECT MATERIAL_ID,PLANT_ID,MOVEMENT_TYPE,QUANTITY,POSTING_DATE,IS_BACKCAST_PERIOD
    FROM VEDANTA_POC.FACT_MATERIAL_MOVEMENT_PART_004
),
B AS (
  SELECT C.PLANT_ID                                  AS P,
         COALESCE(CM.BUSINESS_CATEGORY,'UNMAPPED')   AS CAT,
         D.MATERIAL_GROUP                            AS MG,
         D.MATERIAL_TYPE                             AS MT,
         D.CRITICALITY                               AS CR,
         C.MOVEMENT_CLASS                            AS MVC,
         C.SHUTDOWN_MATERIAL_FLAG_PLANT              AS SD,
         LEFT(M.POSTING_DATE,7)                      AS MN,
         SUM(CASE WHEN M.MOVEMENT_TYPE='261'
                  THEN  TO_DECIMAL(M.QUANTITY,18,3)
                  ELSE -TO_DECIMAL(M.QUANTITY,18,3) END) AS Q
    FROM MM M
    JOIN VEDANTA_POC.DIM_MATERIAL D
      ON D.MATERIAL_ID = M.MATERIAL_ID
    JOIN VEDANTA_POC.MATERIAL_PLANT_CLASSIFICATION C
      ON C.MATERIAL_ID = M.MATERIAL_ID AND C.PLANT_ID = M.PLANT_ID
    LEFT JOIN VEDANTA_POC.CATEGORY_MAP CM
      ON CM.MATERIAL_GROUP = D.MATERIAL_GROUP
   WHERE D.MATERIAL_TYPE IN ('ZSPR','ZSPN')
     AND M.IS_BACKCAST_PERIOD = 'N'
     AND M.MOVEMENT_TYPE IN ('261','262')
     AND M.POSTING_DATE BETWEEN '2024-01-01' AND '2025-12-31'
   GROUP BY C.PLANT_ID, COALESCE(CM.BUSINESS_CATEGORY,'UNMAPPED'), D.MATERIAL_GROUP,
            D.MATERIAL_TYPE, D.CRITICALITY, C.MOVEMENT_CLASS,
            C.SHUTDOWN_MATERIAL_FLAG_PLANT, LEFT(M.POSTING_DATE,7)
)
SELECT P, CAT, MG, MT, CR, MVC, SD,
       STRING_AGG(MN || ':' || TO_VARCHAR(ROUND(Q,2)), ';' ORDER BY MN) AS SERIES
  FROM B
 GROUP BY P, CAT, MG, MT, CR, MVC, SD
 ORDER BY P, CAT, MG, MT, CR, MVC, SD;
