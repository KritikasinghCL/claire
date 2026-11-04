#!/usr/bin/env python3
"""Gate step3/dashboard_data.json against the brief. Exit 0 only if every check holds.

Run from the repository root:  python3 tools/validate_step3.py

This does NOT trust the builder's own self-check: it re-reads the emitted artefact
and asserts the contract the commander specified — 12 sections, 13 KPIs with
Target/Actual/Variance/Status, the reconciliation panel, the ContextFlow model name
and run timestamp, warning banners, and a reason behind every UNCOMPUTABLE.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "step3", "dashboard_data.json")

SECTIONS = [
    "kpi_scorecard", "demand_forecast", "inventory_health", "over_understock",
    "nm_sm", "shutdown_maintenance", "pr_recommendations", "mrp_rop",
    "duplicate_sku", "plan_vs_actual", "data_sources", "raia",
]

KPI_CODES = [
    "GROSS_INVENTORY_REDUCTION", "NMI", "SMI", "OBSOLETE_REDUCTION",
    "QTY_ACCURACY", "INVENTORY_FORECAST_ACCURACY", "NM_SM_F1",
    "VITAL_AVAILABILITY", "ROP_COVERAGE", "DUPLICATE_SKU",
    "PR_DATE_ADHERENCE", "PR_COUNT_YOY", "NOM_DAYS",
]

# Each section must carry the blocks the brief names for it.
REQUIRED_BLOCKS = {
    "kpi_scorecard": ["cards", "kpi_table", "baseline", "red_against_baseline"],
    "demand_forecast": ["cards", "horizons", "history", "holdout", "seasonality",
                        "accuracy", "model_selection", "by_driver",
                        "material_level_forecast", "lead_time_variability",
                        "planned_and_projected_requirements", "last12_vs_next12",
                        "deviation_band"],
    "inventory_health": ["cards", "stock_by_movement_class", "positions", "mtd_ytd"],
    "over_understock": ["cards", "by_status", "stockout_risk", "detail_top_understock"],
    "nm_sm": ["cards", "by_class", "transitions_90d", "watchlist", "sap_agreement"],
    "shutdown_maintenance": ["cards", "calendar", "requirements", "pr_mix", "equipment"],
    "pr_recommendations": ["cards", "value_by_week", "recommendations_table", "exceptions"],
    "mrp_rop": ["cards", "mrp_type_split", "rop_vs_master", "parameters"],
    "duplicate_sku": ["cards", "clusters", "pairs", "releasable_by_plant"],
    "plan_vs_actual": ["cards", "fy_selector", "monthly", "by_fy", "variance_table"],
    "data_sources": ["cards", "tables_used", "provenance", "movement_class_rules",
                     "business_rules", "sap_mapping"],
    "raia": ["engine", "contextflow_model", "raw_vs_curated", "reconciliation",
             "accuracy", "limitations", "uncomputable_items", "assumptions",
             "data_quality", "forecast", "top_risks", "actions"],
}

FAIL = []
OK = [0]


def check(cond, msg):
    OK[0] += 1
    if not cond:
        FAIL.append(msg)


def main():
    if not os.path.exists(ART):
        print("FAIL: %s does not exist. Run python3 step3/builder/build.py first." % ART)
        return 1
    with open(ART, "r", encoding="utf-8") as fh:
        d = json.load(fh)

    # --- meta -------------------------------------------------------------
    m = d.get("meta", {})
    cf = m.get("contextflow", {})
    check(cf.get("model_name"), "meta.contextflow.model_name is empty")
    check(cf.get("experiment_id"), "meta.contextflow.experiment_id is empty")
    check(cf.get("run_timestamp_utc"), "meta.contextflow.run_timestamp_utc is empty")
    check(m.get("as_of_date") == "2025-12-31", "as_of_date is not 2025-12-31")
    check(m.get("measure", {}).get("default") == "QTY", "default measure is not QTY")
    check(m.get("fiscal_year") == "Apr-Mar", "fiscal year is not Apr-Mar")
    check(sorted(m.get("scope", {}).get("material_type_in", [])) == ["ZSPN", "ZSPR"],
          "scope is not ZSPR/ZSPN")
    check(len(m.get("badges", [])) >= 5, "fewer than 5 badges")

    # --- filters ----------------------------------------------------------
    f = d.get("filters", {})
    for key in ("plant", "category", "material_group", "material_type", "criticality",
                "movement_class", "shutdown", "date_range", "horizon", "measure", "cascade"):
        check(f.get(key), "filters.%s is missing or empty" % key)
    check(f.get("horizon") == [3, 6, 9, 12], "horizons are not 3/6/9/12")
    check(f.get("cascade") == ["plant", "material_type", "material_group", "material"],
          "cascade is not plant -> material_type -> material_group -> material")

    # --- sections ---------------------------------------------------------
    S = d.get("sections", {})
    check(len(S) == 12, "expected 12 sections, found %d" % len(S))
    for sid in SECTIONS:
        s = S.get(sid)
        check(bool(s), "section missing: %s" % sid)
        if not s:
            continue
        check(s.get("id") == sid, "section %s has id %r" % (sid, s.get("id")))
        check(bool(s.get("title")), "section %s has no title" % sid)
        check(len(s.get("description", "")) > 20, "section %s has no real description" % sid)
        for blk in REQUIRED_BLOCKS[sid]:
            check(blk in s, "section %s is missing block %s" % (sid, blk))

    # --- KPIs -------------------------------------------------------------
    K = d.get("kpis", [])
    check(len(K) == 13, "expected 13 KPIs, found %d" % len(K))
    codes = [k.get("code") for k in K]
    for want in KPI_CODES:
        check(want in codes, "KPI missing: %s" % want)
    for k in K:
        for fld in ("target", "actual", "variance", "status"):
            check(fld in k, "KPI %s missing field %s" % (k.get("code"), fld))
        check(k.get("status") in ("GREEN", "AMBER", "RED", "INFO", "UNCOMPUTABLE"),
              "KPI %s has status %r" % (k.get("code"), k.get("status")))
        check(bool(k.get("basis")), "KPI %s has no basis" % k.get("code"))
        if k.get("actual") is None:
            check(bool(k.get("uncomputable_reason")),
                  "KPI %s is null with no uncomputable_reason" % k.get("code"))
            check(k.get("status") == "UNCOMPUTABLE",
                  "KPI %s is null but not UNCOMPUTABLE" % k.get("code"))

    # --- reconciliation ---------------------------------------------------
    R = d.get("reconciliation", {})
    check(len(R.get("items", [])) >= 6, "reconciliation panel has fewer than 6 items")
    for it in R.get("items", []):
        for fld in ("item", "curated", "raw", "status"):
            check(fld in it, "reconciliation item %s missing %s" % (it.get("id"), fld))
        check("diff" in it, "reconciliation item %s missing diff" % it.get("id"))
        check("diff_pct" in it, "reconciliation item %s missing diff_pct" % it.get("id"))

    # --- warnings ---------------------------------------------------------
    W = d.get("warnings", [])
    check(len(W) >= 5, "fewer than 5 warning banners")
    for w in W:
        check(w.get("severity") in ("critical", "warn", "info"),
              "warning %s has severity %r" % (w.get("code"), w.get("severity")))
        check(bool(w.get("message")), "warning %s has no message" % w.get("code"))

    # --- no UNCOMPUTABLE anywhere without a reason ------------------------
    def walk(o, path):
        if isinstance(o, dict):
            if o.get("status") == "UNCOMPUTABLE":
                check(bool(o.get("reason") or o.get("uncomputable_reason")),
                      "UNCOMPUTABLE with no reason at %s" % path)
            for k, v in o.items():
                walk(v, path + "." + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, "%s[%d]" % (path, i))
    walk(d, "$")

    # --- nothing hand-filled: the engine totals must agree with step 1 ----
    T = d.get("dimensions", {}).get("totals", {})
    check(T.get("lines") == 34717, "scope line count is not 34,717 (got %r)" % T.get("lines"))
    check(T.get("overstock_lines", 0) + T.get("understock_lines", 0) <= T.get("lines", 0),
          "overstock + understock lines exceed the scope")

    print("checks run: %d" % OK[0])
    if FAIL:
        print("FAILED %d:" % len(FAIL))
        for x in FAIL:
            print("  - " + x)
        return 1
    print("OK — dashboard_data.json satisfies the step-3 contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
