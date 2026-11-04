"""Assemble dashboard_data.json: 12 sections, 13 KPIs, reconciliation and warnings.

Run:  python3 step3/builder/build.py [output_path]
Default output: step3/dashboard_data.json

The build FAILS LOUDLY rather than emitting a partial file: every section must be
present, the KPI table must carry exactly 13 rows, and anything that cannot be
computed must say so with a reason. Nothing is fabricated or hand-filled.
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import rules          # noqa: E402
import engine         # noqa: E402
import kpis           # noqa: E402
import sections       # noqa: E402
from facts import load_all, ROOT  # noqa: E402

SECTION_BUILDERS = [
    "kpi_scorecard", "demand_forecast", "inventory_health", "over_understock",
    "nm_sm", "shutdown_maintenance", "pr_recommendations", "mrp_rop",
    "duplicate_sku", "plan_vs_actual", "data_sources", "raia",
]


def collect_warnings(F, kpi_rows):
    """Warning banners for the dashboard. Each one is raised by a fact, not by taste."""
    W = []
    ev = F["step2"]
    exp = ev.get("experiment_A_authoritative", {})

    if F.get("step2_missing"):
        W.append({"severity": "critical", "code": "FORECAST_ARTEFACT_MISSING",
                  "section": "demand_forecast", "message": F["step2_missing"]})

    W.append({"severity": "critical", "code": "FORECAST_CANNOT_EXTRAPOLATE",
              "section": "demand_forecast",
              "message": ("The deployed ContextFlow model cannot project forward: a predict for 2099-06 "
                          "returns exactly 2026-06's value (1397.11669921875). Forward horizons "
                          "3/6/9/12 are published as UNCOMPUTABLE rather than as a replay of history.")})

    W.append({"severity": "critical", "code": "FORECAST_NOT_MATERIAL_GRAIN",
              "section": "demand_forecast",
              "message": ("MATERIAL_ID is not a ContextFlow feature. MAT-000001 and MAT-005999 return "
                          "byte-identical predictions, so no material-level forecast is published. The "
                          "brief's drill-to-material SUCCESS criterion is not met by this experiment.")})

    W.append({"severity": "warn", "code": "HOLDOUT_NOT_TIME_ORDERED",
              "section": "demand_forecast",
              "message": ("ContextFlow used a deterministic RANDOM 20% holdout, not the time-ordered "
                          "6-month holdout the brief requires. Reported accuracy is an optimistic upper "
                          "bound, not forecast accuracy.")})

    W.append({"severity": "warn", "code": "ACCURACY_BELONGS_TO_RUNNER_UP",
              "section": "demand_forecast",
              "message": ("The published WAPE 0.477518 / RMSE 174.086569 belong to WeightedEnsemble_L2 "
                          "(rank 2), not to the deployed champion ExtraTreesMSE (RMSE 172.503385).")})

    W.append({"severity": "warn", "code": "TWO_ENDPOINTS_IN_SERVICE",
              "section": "data_sources",
              "message": ("Two ContextFlow endpoints are in_service on the same asset, 35% apart on "
                          "RMSE. This dashboard pins experiment " + str(exp.get("id")) + ".")})

    for w in F["step1"]["warnings"]:
        W.append(dict(w, section="data_sources", origin="step1"))

    W.append({"severity": "warn", "code": "MRP_TYPE_ABSENT", "section": "mrp_rop",
              "message": F["extra"]["mrp_type"]["reason"]})

    W.append({"severity": "warn", "code": "PLAN_VS_ACTUAL_VALUE_ONLY", "section": "plan_vs_actual",
              "message": F["misc"]["plan_vs_actual_note"]})

    W.append({"severity": "warn", "code": "NO_FORWARD_SHUTDOWN_OR_MAINTENANCE",
              "section": "shutdown_maintenance",
              "message": F["context"]["shutdown_events"]["projected_events_reason"]})

    red = [r for r in kpi_rows if r["status"] == "RED"]
    if red:
        W.append({"severity": "warn", "code": "KPIS_RED", "section": "kpi_scorecard",
                  "message": "RED against target: " + "; ".join(
                      "%s (actual %s vs target %s)" % (r["label"], r["actual"], r["target"]) for r in red)})

    unc = [r for r in kpi_rows if r["status"] == "UNCOMPUTABLE"]
    if unc:
        W.append({"severity": "info", "code": "KPIS_UNCOMPUTABLE", "section": "kpi_scorecard",
                  "message": "UNCOMPUTABLE: " + "; ".join(r["label"] for r in unc)})

    W.append({"severity": "info", "code": "SYNTHETIC_POC_DATA", "section": "data_sources",
              "message": F["context"]["curated_opportunity_2025_12"]["disclaimer_verbatim"]})
    return W


def build():
    F = load_all()
    run_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    kpi_rows = kpis.build(F)
    kpi_summary = kpis.summary(kpi_rows)
    warnings = collect_warnings(F, kpi_rows)

    ev = F["step2"]
    exp = ev.get("experiment_A_authoritative", {})
    T = engine.totals(F)

    S = {
        "kpi_scorecard": sections.kpi_scorecard(F, kpi_rows, kpi_summary),
        "demand_forecast": sections.demand_forecast(F),
        "inventory_health": sections.inventory_health(F),
        "over_understock": sections.over_understock(F),
        "nm_sm": sections.nm_sm(F),
        "shutdown_maintenance": sections.shutdown_maintenance(F),
        "pr_recommendations": sections.pr_recommendations(F),
        "mrp_rop": sections.mrp_rop(F),
        "duplicate_sku": sections.duplicate_sku(F),
        "plan_vs_actual": sections.plan_vs_actual(F),
        "data_sources": sections.data_sources(F, run_ts),
    }
    S["raia"] = sections.raia(F, kpi_rows, kpi_summary, warnings, run_ts)

    bp = engine.by_plant(F)
    gt = engine.group_type(F)
    doc = {
        "meta": {
            "artifact": "dashboard_data.json",
            "step": "step3_model",
            "ticket": "S-8",
            "generated_by": "Liam - Inventory Control Lead, Inventory & Forecasting Cell",
            "generated_at_utc": run_ts,
            "as_of_date": rules.AS_OF,
            "period": {"from": rules.PERIOD_FROM, "to": rules.PERIOD_TO},
            "fiscal_year": rules.FISCAL_YEAR,
            "scope": {"material_type_in": rules.SCOPE_MATERIAL_TYPES,
                      "is_backcast_period": rules.IS_BACKCAST_PERIOD,
                      "plants": engine.PLANTS,
                      "all_plants_rollup_excluded": True,
                      "lines": T["lines"]},
            "measure": {"default": rules.DEFAULT_MEASURE,
                        "default_unit": "base UoM quantity and material-plant line count (SKU)",
                        "toggle": rules.VALUE_MEASURE,
                        "policy": ("QTY is the headline everywhere. INR appears only when the Qty/Value "
                                   "toggle is set to Value. Plan vs Actual is the single exception and "
                                   "says so: the source table has no quantity column.")},
            "source": {"system": "SAP HANA Cloud (read-only)",
                       "schema": "VEDANTA_POC",
                       "host": F["step1"]["source"]["host"]},
            "contextflow": {
                "engine": "ContextFlow AutoML (onprem)",
                "experiment_id": exp.get("id"),
                "experiment_name": exp.get("name"),
                "model_name": exp.get("winner_verbatim", {}).get("bestCandidateId"),
                "endpoint_id": exp.get("endpoint", {}).get("endpointId"),
                "primary_metric": exp.get("dataset", {}).get("primaryMetric"),
                "run_timestamp_utc": run_ts,
                "evidence_file": F["step2_source"],
                "forecast_status": "DEGRADED - no forward horizons, no material grain",
            },
            "badges": [
                {"label": "Source", "value": "SAP HANA VEDANTA_POC", "tone": "neutral"},
                {"label": "Forecast engine", "value": "ContextFlow AutoML", "tone": "neutral"},
                {"label": "Model", "value": str(exp.get("winner_verbatim", {}).get("bestCandidateId")),
                 "tone": "neutral"},
                {"label": "As-of", "value": rules.AS_OF, "tone": "neutral"},
                {"label": "Measure", "value": "QTY (base UoM)", "tone": "accent"},
                {"label": "Forecast", "value": "DEGRADED", "tone": "danger"},
                {"label": "Data", "value": "Synthetic POC", "tone": "warning"},
            ],
            "section_order": SECTION_BUILDERS,
        },
        "filters": {
            "plant": engine.PLANTS,
            "category": sorted({r["category"] for r in gt if r["category"]}),
            "material_group": sorted({r["material_group"] for r in gt}),
            "material_type": rules.SCOPE_MATERIAL_TYPES,
            "criticality": ["VITAL", "ESSENTIAL", "DESIRABLE"],
            "movement_class": engine.CLASSES,
            "shutdown": ["Y", "N"],
            "date_range": {"min": rules.PERIOD_FROM, "max": rules.PERIOD_TO, "months": rules.MONTHS},
            "horizon": [3, 6, 9, 12],
            "measure": ["QTY", "VALUE"],
            "cascade": ["plant", "material_type", "material_group", "material"],
            "cascade_note": ("Plant -> Material Type -> Material Group is backed by the group_type and "
                             "plant_mc aggregates. The Material level resolves stock, ROP, safety stock "
                             "and the PR recommendation from the engine detail, but NOT a forecast "
                             "quantity - see the demand_forecast material_level_forecast block."),
        },
        "kpis": kpi_rows,
        "kpi_summary": kpi_summary,
        "reconciliation": sections.reconciliation_panel(F),
        "warnings": warnings,
        "sections": S,
        "dimensions": {
            "by_plant": bp,
            "by_group_and_type": gt,
            "by_criticality_and_class": engine.crit_mc(F),
            "by_class": engine.by_class(F),
            "totals": T,
        },
    }
    validate(doc)
    return doc


def validate(doc):
    errs = []
    for sid in SECTION_BUILDERS:
        s = doc["sections"].get(sid)
        if not s:
            errs.append("missing section: " + sid)
            continue
        for key in ("id", "title", "description"):
            if not s.get(key):
                errs.append("section %s missing %s" % (sid, key))
        if s.get("id") != sid:
            errs.append("section %s has id %r" % (sid, s.get("id")))
    if len(doc["kpis"]) != 13:
        errs.append("expected 13 KPIs, found %d" % len(doc["kpis"]))
    codes = [k["code"] for k in doc["kpis"]]
    for want in rules.KPI_TARGETS:
        if want not in codes:
            errs.append("KPI missing: " + want)
    for k in doc["kpis"]:
        for f in ("target", "actual", "variance", "status"):
            if f not in k:
                errs.append("KPI %s missing %s" % (k["code"], f))
        if k["actual"] is None and not k.get("uncomputable_reason"):
            errs.append("KPI %s is None without an uncomputable_reason" % k["code"])
        if k["status"] not in ("GREEN", "AMBER", "RED", "INFO", "UNCOMPUTABLE"):
            errs.append("KPI %s has status %r" % (k["code"], k["status"]))
    if not doc["reconciliation"]["items"]:
        errs.append("reconciliation panel is empty")
    if not doc["meta"]["contextflow"]["model_name"]:
        errs.append("ContextFlow model name is missing from meta")
    if not doc["meta"]["contextflow"]["run_timestamp_utc"]:
        errs.append("run timestamp is missing from meta")
    if not doc["warnings"]:
        errs.append("warning banners are empty")

    def walk(o, path):
        if isinstance(o, dict):
            if (o.get("status") == "UNCOMPUTABLE"
                    and not (o.get("reason") or o.get("uncomputable_reason"))):
                errs.append("UNCOMPUTABLE without a reason at " + path)
            for k, v in o.items():
                walk(v, path + "." + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o[:200]):
                walk(v, "%s[%d]" % (path, i))

    walk(doc["sections"], "sections")
    if errs:
        raise SystemExit("dashboard_data.json FAILED validation:\n  " + "\n  ".join(errs))
    return True


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "step3", "dashboard_data.json")
    doc = build()
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False, sort_keys=False)
    size = os.path.getsize(out)
    unc = sum(1 for k in doc["kpis"] if k["status"] == "UNCOMPUTABLE")
    print("wrote %s (%d bytes)" % (out, size))
    print("sections : %d/%d  -> %s" % (len(doc["sections"]), len(SECTION_BUILDERS),
                                       ", ".join(doc["meta"]["section_order"])))
    print("kpis     : %d  %s" % (len(doc["kpis"]), doc["kpi_summary"]["by_status"]))
    print("warnings : %d" % len(doc["warnings"]))
    print("reconcile: %d items" % len(doc["reconciliation"]["items"]))
    print("model    : %s @ %s" % (doc["meta"]["contextflow"]["model_name"],
                                  doc["meta"]["contextflow"]["run_timestamp_utc"]))
    print("uncomputable KPIs: %d" % unc)


if __name__ == "__main__":
    main()
