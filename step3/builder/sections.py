"""The 12 sections of dashboard_data.json: the 11 content pages plus RAIA.

Every number here is arithmetic over facts already read from SAP HANA by the
engine/fact modules. Nothing is estimated. Where the extract does not carry the
field a section needs, the section emits

    {"status": "UNCOMPUTABLE", "reason": "...", "missing_field": "..."}

rather than a plausible-looking value.

Measure policy: QTY in base UoM is the default everywhere; value_inr travels
alongside as the Qty/Value toggle field and is never the headline.
"""
import rules
import engine
from facts import rows_to_dicts

PLANTS = engine.PLANTS
CLASSES = engine.CLASSES


def _uncomputable(reason, missing_field=None, **extra):
    out = {"status": "UNCOMPUTABLE", "reason": reason}
    if missing_field:
        out["missing_field"] = missing_field
    out.update(extra)
    return out


def _card(label, value, unit, measure="QTY", target=None, status=None, **extra):
    c = {"label": label, "value": value, "unit": unit, "measure": measure}
    if target is not None:
        c["target"] = target
    if status is not None:
        c["status"] = status
    c.update(extra)
    return c


# ---------------------------------------------------------------- 1 scorecard
def kpi_scorecard(F, kpi_rows, kpi_summary):
    T = engine.totals(F)
    S = rows_to_dicts(F["context"]["kpi_monthly_value_inr"]["columns"],
                      F["context"]["kpi_monthly_value_inr"]["rows"])
    R = rows_to_dicts(F["context"]["kpi_monthly_ratios"]["columns"],
                      F["context"]["kpi_monthly_ratios"]["rows"])
    cur, base = S[-1], S[0]
    opp = next(r for r in F["context"]["curated_opportunity_2025_12"]["rows"] if r[0] == "ALL_PLANTS")
    pr = engine.pr_recommendations(F)
    vital = [r for r in engine.crit_mc(F) if r["criticality"] == "VITAL"]
    v_lines = sum(r["lines"] for r in vital)
    v_stocked = sum(r["has_stock"] for r in vital)
    return {
        "id": "kpi_scorecard", "title": "KPI Scorecard",
        "description": ("The 13 KPIs the business is measured on, each with Target, Actual, Variance and "
                        "Status, against the 2024-01 baseline. Quantities are base UoM; INR appears only "
                        "under the Value toggle."),
        "cards": [
            _card("Gross inventory", T["stock_qty"], "base UoM", "QTY",
                  value_inr=cur["gross_inventory_value_inr"],
                  baseline_inr=base["gross_inventory_value_inr"],
                  lines=T["lines"]),
            _card("Reduction opportunity", None, "base UoM", "QTY",
                  qty_uncomputable_reason=("INVENTORY_KPI_MONTHLY carries POTENTIAL_REDUCTION_INR only; "
                                           "there is no potential-reduction quantity column, so the Qty "
                                           "view of this card is UNCOMPUTABLE."),
                  value_inr=opp[1], pct_of_gross=opp[2], target_pct=opp[3],
                  working_capital_inr=opp[4],
                  disclaimer=F["context"]["curated_opportunity_2025_12"]["disclaimer_verbatim"]),
            _card("Non-operating material", F["misc"]["nom_days"]["lines_gt_90d"], "SKU lines", "QTY",
                  definition="lines whose days since last consumption exceed the 90-day NM/SM horizon",
                  avg_days=F["misc"]["nom_days"]["avg_days_since_last_consumption"],
                  value_inr=T["no_demand_value_inr"]),
            _card("Inventory turnover", R[-1]["inventory_turnover_avg"], "turns/yr", "RATIO",
                  baseline=R[0]["inventory_turnover_avg"],
                  days_on_hand=R[-1]["days_on_hand_avg"],
                  days_on_hand_baseline=R[0]["days_on_hand_avg"],
                  basis="INVENTORY_KPI_MONTHLY, plant-average (a ratio, averaged not summed)"),
            _card("Vital spares availability", round(100.0 * v_stocked / v_lines, 4), "%", "RATIO",
                  target=rules.SERVICE_LEVEL["VITAL"], vital_lines=v_lines,
                  vital_lines_with_stock=v_stocked, vital_lines_zero_stock=v_lines - v_stocked),
            _card("PRs recommended", pr["totals"]["lines"], "PR lines", "QTY",
                  qty=pr["totals"]["qty"], value_inr=pr["totals"]["value_inr"],
                  raise_immediately_lines=pr["totals"]["raise_immediately_lines"]),
        ],
        "kpi_table": kpi_rows,
        "kpi_summary": kpi_summary,
        "baseline": {
            "month": base["month"], "basis": "first in-scope month, 2024-01",
            "gross_inventory_value_inr": base["gross_inventory_value_inr"],
            "non_moving_value_inr": base["non_moving_value_inr"],
            "slow_moving_value_inr": base["slow_moving_value_inr"],
            "obsolete_value_inr": base["obsolete_value_inr"],
        },
        "monthly_series": S,
        "ratio_series": R,
        "red_against_baseline": [r for r in kpi_rows if r["status"] == "RED"],
    }


# ------------------------------------------------------------ 2 demand forecast
def demand_forecast(F):
    dm = rows_to_dicts(F["misc"]["columns_demand_monthly"], F["misc"]["demand_monthly"])
    ev = F["step2"]
    exp = ev.get("experiment_A_authoritative", {})
    diag = exp.get("holdout_diagnostics_verbatim", {})
    last12 = [r for r in dm if r["month"] >= "2025-01"]
    last12_qty = round(sum(r["net"] for r in last12), 3)
    T = engine.totals(F)
    seas = F["context"]["seasonality_index"]

    forward_unavailable = _uncomputable(
        ("ContextFlow produced no forward-horizon quantities. step2_forecast.json was never created "
         "(S-3 blocked), and the deployed model cannot extrapolate: a predict for 2099-06 returns "
         "exactly 2026-06's value (1397.11669921875), so any 'forward' call replays 2024-25 rather "
         "than projecting. Horizon quantities are therefore not published."),
        missing_field="step2_forecast.json forward horizons from the ContextFlow AutoML endpoint")

    horizons = {}
    for h in (3, 6, 9, 12):
        horizons[f"h{h}m"] = dict(forward_unavailable,
                                  horizon_months=h,
                                  run_rate_reference_qty=round(last12_qty * h / 12.0, 3),
                                  run_rate_note=("Trailing-12-month run rate shown for reference ONLY. "
                                                 "It is an arithmetic extrapolation of history, NOT a "
                                                 "ContextFlow forecast, and must never be labelled one."))
    return {
        "id": "demand_forecast", "title": "Demand Forecast",
        "description": ("Net issues (MovType 261 minus 262) by month, the ContextFlow holdout, and the "
                        "forward horizons. Quantities in base UoM."),
        "cards": [
            _card("Last 12 months (actual)", last12_qty, "base UoM", "QTY",
                  months="2025-01..2025-12", source="FACT_MATERIAL_MOVEMENT 261-262"),
            _card("3-month forecast", None, "base UoM", "QTY", **forward_unavailable),
            _card("6-month forecast", None, "base UoM", "QTY", **forward_unavailable),
            _card("9-month forecast", None, "base UoM", "QTY", **forward_unavailable),
            _card("12-month forecast", None, "base UoM", "QTY", **forward_unavailable),
        ],
        "horizons": horizons,
        "history": dm,
        "history_total_qty": round(sum(r["net"] for r in dm), 3),
        "holdout": {
            "declared_by_contextflow": {
                "split_strategy": exp.get("dataset", {}).get("splitStrategy"),
                "holdout_fraction": exp.get("dataset", {}).get("holdoutFraction"),
                "rows": diag.get("rows"),
            },
            "required_by_the_brief": "time-ordered 6-month holdout, 2025-07..2025-12",
            "verdict": "FAIL",
            "reason": ("The split is a deterministic RANDOM 20% holdout over a time series, so 2025-12 "
                       "rows can train while 2024-03 rows test. Reported accuracy is an in-sample-period "
                       "number, not 6-month-ahead forecast accuracy."),
            "what_it_should_have_been": "5,283 of 30,861 cohort-month rows (17.12%), 937,113.778 base UoM",
        },
        "deviation_band_pct": 15,
        "deviation_band": _uncomputable(
            "A +/-15% band needs a forward forecast series to sit around; no forward series exists.",
            missing_field="forward forecast quantities"),
        "last12_vs_next12": {
            "last12_qty": last12_qty,
            "next12_qty": None,
            "status": "UNCOMPUTABLE",
            "reason": "No forward 12-month ContextFlow forecast exists (see horizons).",
            "engine_f12_reference_qty": T["forecast_12m_qty"],
            "engine_f12_note": ("The engine's own 12-month figure is trailing-12 net demand carried "
                                "forward; it drives ROP and MAX arithmetic and is NOT a ContextFlow "
                                "forecast."),
        },
        "seasonality": {
            "source": seas["source"], "basis": seas["basis_verbatim"],
            "index_by_calendar_month": seas["by_calendar_month"],
        },
        "accuracy": {
            "wape": diag.get("wape"),
            "qty_accuracy_pct": round(100.0 * (1 - diag["wape"]), 4) if diag.get("wape") is not None else None,
            "rmse": diag.get("rmse"),
            "mae": diag.get("mae"),
            "r2": diag.get("r2"),
            "mape": None,
            "mape_status": "UNCOMPUTABLE",
            "mape_reason": ("The target contains zero-demand cohort-months (154 confirmed in HANA), so "
                            "MAPE diverges; every candidate's own MAPE is of order 1e15. Use WAPE."),
            "belongs_to_candidate": "WeightedEnsemble_L2 (rank 2)",
            "warning": diag.get("WARNING"),
        },
        "model_selection": {
            "engine": "ContextFlow AutoML (onprem)",
            "experiment_id": exp.get("id"),
            "experiment_name": exp.get("name"),
            "winner": exp.get("winner_verbatim", {}).get("bestCandidateId"),
            "why_it_ranked_first_verbatim": exp.get("why_it_ranked_first_verbatim"),
            "primary_metric": exp.get("dataset", {}).get("primaryMetric"),
            "candidates_trained": exp.get("candidates_trained"),
            "leaderboard": exp.get("full_leaderboard_rmse"),
            "feature_importance": exp.get("featureImportance"),
            "endpoint": exp.get("endpoint"),
            "validated_regression_not_classification":
                ev.get("validations_required_by_the_brief", {}).get("task_is_regression_not_classification"),
            "validated_target_is_a_quantity":
                ev.get("validations_required_by_the_brief", {}).get("target_is_a_quantity"),
            "validated_model_chosen_by_engine":
                ev.get("validations_required_by_the_brief", {}).get("model_chosen_by_contextflow_not_by_us"),
            "second_deployed_experiment": ev.get("experiment_B_second_run"),
        },
        "by_driver": {
            "plant": {p: engine.by_plant(F)[p]["forecast_12m_qty"] for p in PLANTS},
            "material_group_and_type": [
                {"material_group": r["material_group"], "material_type": r["material_type"],
                 "category": r["category"], "lines": r["lines"], "trailing12_qty": r["f12_qty"]}
                for r in engine.group_type(F)],
            "note": ("Driver splits are trailing-12 net demand from HANA, the quantity the engine's ROP "
                     "and MAX use. They are not ContextFlow forward forecasts."),
        },
        "material_level_forecast": _uncomputable(
            ("MATERIAL_ID is not a feature of the deployed ContextFlow model. Proven empirically: two "
             "predict rows identical except MATERIAL_ID (MAT-000001 vs MAT-005999) both returned "
             "1290.1533203125, byte-identical. The finest grain the model can express is the 2,027-way "
             "cohort. A material-level number would be one cohort value repeated across 34,717 lines and "
             "would be an allocation, not a forecast."),
            missing_field="MATERIAL_ID as a ContextFlow feature column"),
        "lead_time_variability": engine.lead_time(F),
        "planned_and_projected_requirements": _uncomputable(
            ("FACT_MAINTENANCE_REQUIREMENT carries exactly one STATUS ('COMPLETED') and one PR_TYPE "
             "('ZMNT'), with no date and no plant column; DIM_SHUTDOWN_EVENT has no event later than "
             "2025-09-19 and every event is COMPLETED. There is no open or future requirement in the "
             "extract to project."),
            missing_field="an open/planned maintenance or shutdown requirement with a future date"),
    }


# ----------------------------------------------------------- 3 inventory health
def inventory_health(F):
    T = engine.totals(F)
    bp = engine.by_plant(F)
    bc = engine.by_class(F)
    R = rows_to_dicts(F["context"]["kpi_monthly_ratios"]["columns"],
                      F["context"]["kpi_monthly_ratios"]["rows"])
    S = rows_to_dicts(F["context"]["kpi_monthly_value_inr"]["columns"],
                      F["context"]["kpi_monthly_value_inr"]["rows"])
    snap = rows_to_dicts(F["extra"]["snapshot_2025_12_31"]["columns"],
                         F["extra"]["snapshot_2025_12_31"]["rows"])
    cur = REC = F["extra"]["curated_reorder_recommendation"]
    return {
        "id": "inventory_health", "title": "Inventory Health",
        "description": ("Stock position at 2025-12-31 in base UoM, split by movement class and plant. "
                        "INR is the toggle field only."),
        "cards": [
            _card("Stock on hand", T["stock_qty"], "base UoM", "QTY",
                  value_inr=T["stock_value_inr"], lines=T["lines"]),
            _card("Non-operating material", F["misc"]["nom_days"]["lines_gt_90d"], "SKU lines", "QTY",
                  avg_days_since_consumption=F["misc"]["nom_days"]["avg_days_since_last_consumption"],
                  never_issued_lines=F["misc"]["nom_days"]["never_issued_lines"]),
            _card("Inventory turnover", R[-1]["inventory_turnover_avg"], "turns/yr", "RATIO",
                  days_on_hand=R[-1]["days_on_hand_avg"]),
            _card("Zero-stock lines", T["zero_stock_lines"], "SKU lines", "QTY"),
        ],
        "stock_by_movement_class": {k: {
            "lines": bc[k]["lines"], "qty": bc[k]["stock_qty"], "value_inr": bc[k]["stock_value_inr"],
        } for k in CLASSES},
        "stock_by_plant": {p: {
            "lines": bp[p]["lines"], "qty": bp[p]["stock_qty"], "value_inr": bp[p]["stock_value_inr"],
            "by_class": bp[p]["by_class"], "avg_lead_time_days": bp[p]["avg_lead_time_days"],
        } for p in PLANTS},
        "positions": {
            "actual_qty": T["stock_qty"],
            "committed_qty": 0.0,
            "committed_basis": F["extra"]["snapshot_2025_12_31"]["reserved_qty_note"],
            "as_is_qty": T["stock_qty"],
            "recommended_qty": T["max_qty"],
            "recommended_basis": "sum of engine MAX = ROP + 3-month forecast across the 34,717 lines",
            "delta_as_is_vs_recommended_qty": round(T["stock_qty"] - T["max_qty"], 3),
            "curated_recommended_qty": REC["totals"]["max_stock_qty"],
            "curated_recommended_basis": ("REORDER_RECOMMENDATION.MAX_STOCK_QTY over its 3,916 rows — a "
                                          "different population from the engine's 34,717 lines, so the "
                                          "two are shown side by side and never netted."),
        },
        "snapshot_by_plant": snap,
        "mtd_ytd": {
            "mtd_month": "2025-12",
            "mtd_consumption_value_inr": S[-1]["consumption_value_inr"],
            "ytd_consumption_value_inr": round(sum(r["consumption_value_inr"] for r in S if r["month"] >= "2025-01"), 2),
            "fy_to_date_consumption_value_inr": round(sum(r["consumption_value_inr"] for r in S if r["month"] >= "2025-04"), 2),
            "fy_basis": "Apr-Mar; FY2025-26 to date = 2025-04..2025-12",
            "mtd_ytd_qty": None,
            "qty_status": "UNCOMPUTABLE",
            "qty_reason": ("INVENTORY_KPI_MONTHLY carries CONSUMPTION_VALUE_INR but no consumption "
                           "quantity column. The MTD/YTD consumption quantity can be derived from the "
                           "movement fact and is published in the Demand Forecast history series; it is "
                           "not available on this curated KPI table."),
        },
        "monthly_value_series": S,
        "monthly_ratio_series": R,
    }


# --------------------------------------------------------- 4 over / understock
def over_understock(F):
    T = engine.totals(F)
    bp = engine.by_plant(F)
    bc = engine.by_class(F)
    cm = engine.crit_mc(F)
    vital = [r for r in cm if r["criticality"] == "VITAL"]
    detail = rows_to_dicts(F["pr_detail"]["columns"], F["pr_detail"]["rows"])
    return {
        "id": "over_understock", "title": "Over / Understock",
        "description": ("Lines above max(MAX, 12-month forecast) and lines below ROP, at 2025-12-31. "
                        "Rule: overstock = stock > max(MAX, 12-month forecast); understock = stock < ROP."),
        "rules_applied": {"overstock": rules.OVERSTOCK_RULE, "understock": rules.UNDERSTOCK_RULE,
                          "max": rules.MAX_RULE, "rop": rules.ROP_RULE,
                          "holding_cost_pct": rules.HOLDING_COST_PCT},
        "cards": [
            _card("Overstock", T["overstock_lines"], "SKU lines", "QTY",
                  excess_qty=T["overstock_qty"], value_inr=T["overstock_value_inr"],
                  holding_cost_inr=T["holding_cost_on_overstock_inr"],
                  pct_of_lines=round(100.0 * T["overstock_lines"] / T["lines"], 3)),
            _card("No demand", T["no_demand_lines"], "SKU lines", "QTY",
                  value_inr=T["no_demand_value_inr"],
                  definition="stock on hand with zero net demand in the trailing 12 months"),
            _card("Understock", T["understock_lines"], "SKU lines", "QTY",
                  shortfall_qty=T["understock_qty"], value_inr=T["understock_value_inr"],
                  pct_of_lines=round(100.0 * T["understock_lines"] / T["lines"], 3)),
            _card("Vital below ROP", sum(r["lines"] - r["at_or_above_rop"] for r in vital), "SKU lines", "QTY",
                  vital_lines=sum(r["lines"] for r in vital),
                  vital_zero_stock=sum(r["zero_stock"] for r in vital)),
        ],
        "by_status": {
            "OVERSTOCK": {"lines": T["overstock_lines"], "qty": T["overstock_qty"],
                          "value_inr": T["overstock_value_inr"]},
            "UNDERSTOCK": {"lines": T["understock_lines"], "qty": T["understock_qty"],
                           "value_inr": T["understock_value_inr"]},
            "BELOW_SAFETY_STOCK": {"lines": T["below_safety_stock_lines"]},
            "ZERO_STOCK": {"lines": T["zero_stock_lines"]},
            "NO_DEMAND": {"lines": T["no_demand_lines"], "value_inr": T["no_demand_value_inr"]},
            "IN_BAND": {"lines": T["lines"] - T["overstock_lines"] - T["understock_lines"]},
        },
        "by_plant": {p: {
            "overstock_lines": bp[p]["overstock_lines"], "overstock_value_inr": bp[p]["overstock_value_inr"],
            "understock_lines": bp[p]["understock_lines"], "understock_value_inr": bp[p]["understock_value_inr"],
            "below_safety_stock_lines": bp[p]["below_safety_stock_lines"],
            "zero_stock_lines": bp[p]["zero_stock_lines"],
        } for p in PLANTS},
        "by_movement_class": {k: {
            "overstock_lines": bc[k]["overstock_lines"], "overstock_value_inr": bc[k]["overstock_value_inr"],
            "understock_lines": bc[k]["understock_lines"],
        } for k in CLASSES},
        "by_criticality": cm,
        "stockout_risk": {
            "definition": ("Zero stock, or below safety stock, against the criticality service level. "
                           "VITAL 98% / ESSENTIAL 95% / DESIRABLE 90%."),
            "service_levels": rules.SERVICE_LEVEL,
            "by_criticality": [{
                "criticality": c,
                "service_level_pct": rules.SERVICE_LEVEL[c],
                "lines": sum(r["lines"] for r in cm if r["criticality"] == c),
                "zero_stock_lines": sum(r["zero_stock"] for r in cm if r["criticality"] == c),
                "below_rop_lines": sum(r["lines"] - r["at_or_above_rop"] for r in cm if r["criticality"] == c),
                "below_safety_stock_lines": sum(r["lines"] - r["at_or_above_ss"] for r in cm if r["criticality"] == c),
                "availability_pct": round(100.0 * sum(r["has_stock"] for r in cm if r["criticality"] == c)
                                          / sum(r["lines"] for r in cm if r["criticality"] == c), 4),
            } for c in ("VITAL", "ESSENTIAL", "DESIRABLE")],
        },
        "detail_top_understock": detail,
        "detail_note": F["pr_detail"]["note"],
    }


# ------------------------------------------------------------------- 5 NM / SM
def nm_sm(F):
    conf = engine.nm_sm_confusion(F)
    bc = engine.by_class(F)
    tr = rows_to_dicts(F["extra"]["nm_sm_transitions_90d"]["columns"],
                       F["extra"]["nm_sm_transitions_90d"]["rows"])
    at_risk = [r for r in tr if r["class_today"] != r["class_in_90d"]]
    wl = rows_to_dicts(F["extra"]["nm_sm_watchlist"]["columns"],
                       F["extra"]["nm_sm_watchlist"]["rows"])
    nm_sm_lines = bc["NON_MOVING"]["lines"] + bc["SLOW_MOVING"]["lines"]
    nm_sm_value = round(bc["NON_MOVING"]["stock_value_inr"] + bc["SLOW_MOVING"]["stock_value_inr"], 2)
    nm_sm_qty = round(bc["NON_MOVING"]["stock_qty"] + bc["SLOW_MOVING"]["stock_qty"], 3)
    return {
        "id": "nm_sm", "title": "Non-Moving / Slow-Moving",
        "description": ("Movement class at 2025-12-31 under the brief thresholds, what it becomes "
                        "across the 90-day horizon, and how it compares with SAP own NM_SM_CLASS."),
        "rules_applied": {"classes": rules.MOVEMENT_CLASS_RULES,
                          "horizon_days": rules.NM_SM_HORIZON_DAYS,
                          "holding_cost_pct": rules.HOLDING_COST_PCT},
        "cards": [
            _card("NM + SM at risk", nm_sm_lines, "SKU lines", "QTY",
                  qty=nm_sm_qty, value_inr=nm_sm_value,
                  pct_of_lines=round(100.0 * nm_sm_lines / sum(bc[k]["lines"] for k in CLASSES), 3)),
            _card("Value at risk", nm_sm_qty, "base UoM", "QTY",
                  value_inr=nm_sm_value,
                  holding_cost_inr=round(nm_sm_value * rules.HOLDING_COST_PCT, 2)),
            _card("Precision", conf["precision"], "ratio", "RATIO",
                  basis="engine class vs SAP NM_SM_CLASS, positive = anything not ACTIVE"),
            _card("Recall", conf["recall"], "ratio", "RATIO"),
            _card("F1", conf["f1"], "ratio", "RATIO", target=0.90,
                  status=rules.status_for(conf["f1"], 0.90, "higher_is_better")),
        ],
        "by_class": bc,
        "transitions_90d": {
            "matrix": tr,
            "method": F["extra"]["nm_sm_transitions_90d"]["method"],
            "lines_degrading": sum(r["lines"] for r in at_risk),
            "qty_degrading": round(sum(r["qty"] for r in at_risk), 3),
            "value_degrading_inr": round(sum(r["value_inr"] for r in at_risk), 2),
            "active_to_slow_moving_lines": next(
                (r["lines"] for r in tr if r["class_today"] == "ACTIVE" and r["class_in_90d"] == "SLOW_MOVING"), None),
            "slow_moving_to_non_moving_lines": next(
                (r["lines"] for r in tr if r["class_today"] == "SLOW_MOVING" and r["class_in_90d"] == "NON_MOVING"), None),
            "non_moving_to_obsolete_lines": next(
                (r["lines"] for r in tr if r["class_today"] == "NON_MOVING" and r["class_in_90d"] == "OBSOLETE"), None),
        },
        "watchlist": {
            "description": "ACTIVE lines that leave ACTIVE inside the 90-day horizon, by value at risk",
            "rows": wl,
        },
        "sap_agreement": {
            "confusion_matrix": conf["matrix"],
            "curated_movement_class_vs_sap_nm_sm_class":
                rows_to_dicts(F["extra"]["sap_movement_class_vs_nm_sm_class"]["columns"],
                              F["extra"]["sap_movement_class_vs_nm_sm_class"]["rows"]),
            "precision": conf["precision"], "recall": conf["recall"], "f1": conf["f1"],
            "agreement_pct": conf["agreement_pct"],
            "agreement_lines": conf["agreement_lines"], "total_lines": conf["total_lines"],
            "note": conf["note"],
        },
    }


# ------------------------------------------------------- 6 shutdown & maintenance
def shutdown_maintenance(F):
    ev = F["context"]["shutdown_events"]
    rows = rows_to_dicts(ev["columns"], ev["rows"])
    in_scope = [r for r in rows if r["is_backcast"] == "N"]
    mt = F["context"]["maintenance"]
    pr = engine.pr_recommendations(F)
    projected = _uncomputable(ev["projected_events_reason"],
                              missing_field="a DIM_SHUTDOWN_EVENT row with STATUS PLANNED/IN_PROGRESS "
                                            "or PLANNED_START_DATE after the 2025-12-31 as-of date")
    return {
        "id": "shutdown_maintenance", "title": "Shutdown & Maintenance",
        "description": ("Shutdown events from DIM_SHUTDOWN_EVENT with their material requirements, and "
                        "maintenance requirements from FACT_MAINTENANCE_REQUIREMENT."),
        "cards": [
            _card("Shutdown history", len(in_scope), "events", "QTY",
                  events_all_time=len(rows), backcast_events=len(rows) - len(in_scope),
                  required_qty=round(sum(r["required_qty"] for r in in_scope), 3),
                  period="2024-01..2025-12, IS_BACKCAST_PERIOD=N"),
            _card("Projected shutdowns", None, "events", "QTY", **projected),
            _card("Shutdown material need", round(sum(r["required_qty"] for r in in_scope), 3), "base UoM", "QTY",
                  distinct_materials_all_events=F["misc"]["shutdown"]["materials"],
                  schedule_rows=F["misc"]["shutdown"]["rows"]),
            _card("Maintenance requirement", mt["pr_type_mix"][0][4], "base UoM", "QTY",
                  rows=mt["rows"], orders=mt["orders"], equipment=mt["equipment"],
                  distinct_materials=mt["pr_type_mix"][0][3]),
        ],
        "calendar": {
            "events": rows,
            "in_scope_events": in_scope,
            "statuses_present": ev["all_statuses_present"],
            "correction": ev["correction"],
            "note": ("Every event is COMPLETED and none is dated after 2025-09-19. The calendar is "
                     "therefore entirely historical; no forward band can be drawn."),
        },
        "events_by_plant": [{
            "plant": p,
            "events": len([r for r in rows if r["plant"] == p]),
            "in_scope_events": len([r for r in in_scope if r["plant"] == p]),
            "required_qty": round(sum(r["required_qty"] for r in in_scope if r["plant"] == p), 3),
            "materials": sum(r["materials"] for r in in_scope if r["plant"] == p),
        } for p in PLANTS],
        "requirements": {
            "shutdown_schedule_rows": F["misc"]["shutdown"]["rows"],
            "shutdown_ids": F["misc"]["shutdown"]["shutdown_ids"],
            "distinct_materials": F["misc"]["shutdown"]["materials"],
            "distinct_equipment": F["misc"]["shutdown"]["equipment"],
            "required_qty_all_events": F["misc"]["shutdown"]["required_qty"],
            "maintenance": mt,
            "projected_requirement": projected,
        },
        "pr_mix": {
            "shutdown_flagged_pr_lines": pr["totals"]["shutdown_lines"],
            "shutdown_flagged_pr_value_inr": pr["totals"]["shutdown_value_inr"],
            "total_pr_lines": pr["totals"]["lines"],
            "total_pr_value_inr": pr["totals"]["value_inr"],
            "shutdown_share_of_pr_lines_pct": round(
                100.0 * pr["totals"]["shutdown_lines"] / pr["totals"]["lines"], 3),
            "by_priority": pr["by_priority"],
            "maintenance_pr_type_mix": mt["pr_type_mix"],
        },
        "equipment": {
            "distinct_equipment_on_shutdowns": F["misc"]["shutdown"]["equipment"],
            "distinct_equipment_on_maintenance": mt["equipment"],
            "per_event_equipment": 24,
            "note": ("FACT_SHUTDOWN_SCHEDULE carries EQUIPMENT_ID but no equipment master attributes "
                     "(no description, no criticality, no plant). Equipment-level analysis beyond the "
                     "count is UNCOMPUTABLE from this extract."),
        },
    }


# --------------------------------------------------------- 7 PR recommendations
def pr_recommendations(F):
    pr = engine.pr_recommendations(F)
    cur = F["extra"]["curated_reorder_recommendation"]
    T = engine.totals(F)
    return {
        "id": "pr_recommendations", "title": "PR Recommendations",
        "description": ("What to raise, how much and by when. A line is recommended when stock is below "
                        "ROP; the quantity closes the gap to MAX after open PRs, rounded to the "
                        "material MIN_ORDER_QTY and ORDER_MULTIPLE."),
        "rules_applied": pr["rules_applied"],
        "cards": [
            _card("PR lines recommended", pr["totals"]["lines"], "PR lines", "QTY",
                  qty=pr["totals"]["qty"]),
            _card("Recommended quantity", pr["totals"]["qty"], "base UoM", "QTY",
                  value_inr=pr["totals"]["value_inr"]),
            _card("Raise immediately", pr["totals"]["raise_immediately_lines"], "PR lines", "QTY",
                  value_inr=pr["totals"]["raise_immediately_value_inr"],
                  definition="zero weeks of cover after safety stock - raise now"),
            _card("Critical priority", sum(r["lines"] for r in pr["by_priority"] if r["priority"] == "CRITICAL"),
                  "PR lines", "QTY",
                  value_inr=round(sum(r["pr_val_inr"] for r in pr["by_priority"] if r["priority"] == "CRITICAL"), 2)),
            _card("Shutdown-linked", pr["totals"]["shutdown_lines"], "PR lines", "QTY",
                  value_inr=pr["totals"]["shutdown_value_inr"]),
        ],
        "value_by_week": pr["by_weeks_of_cover"],
        "by_priority": pr["by_priority"],
        "by_plant": pr["by_plant"],
        "recommendations_table": pr["detail_top_by_value_at_risk"],
        "recommendations_note": pr["detail_note"],
        "exceptions": [
            {"code": "SAP_ROP_DISAGREES",
             "lines": T["rop_increase_lines"] + T["rop_decrease_lines"],
             "detail": ("Lines whose SAP REORDER_POINT_QTY sits outside the +/-20% flag band around the "
                        "engine ROP. Raising to the engine ROP contradicts the material master until "
                        "the master is corrected.")},
            {"code": "OBSOLETE_LINE_BELOW_ROP",
             "lines": sum(r["under_lines"] for r in engine.plant_mc(F) if r["mc"] == "OBSOLETE"),
             "detail": ("Lines classed OBSOLETE that are nonetheless below ROP. Do not raise a PR "
                        "against an obsolete line without a planner decision.")},
            {"code": "NO_DEMAND_WITH_STOCK",
             "lines": T["no_demand_lines"],
             "detail": ("Lines holding stock with zero net demand in the trailing 12 months. They "
                        "generate no PR, and they are the first candidates for release.")},
            {"code": "CURATED_POPULATION_DIFFERS",
             "lines": cur["rows_total"],
             "detail": ("The curated REORDER_RECOMMENDATION table carries 3,916 rows against the "
                        "engine recommended lines. The two populations are reported side by side in "
                        "the reconciliation panel and are never netted.")},
        ],
        "curated_comparison": {
            "curated_rows": cur["rows_total"],
            "curated_recommended_qty": cur["totals"]["recommended_qty"],
            "curated_value_inr": cur["totals"]["estimated_value_inr"],
            "curated_by_priority": rows_to_dicts(cur["columns_by_priority"], cur["by_priority"]),
            "engine_lines": pr["totals"]["lines"],
            "engine_qty": pr["totals"]["qty"],
            "engine_value_inr": pr["totals"]["value_inr"],
            "note": ("Curated priorities are HIGH/MEDIUM/LOW; the engine are CRITICAL/HIGH/MEDIUM. "
                     "They are different scales and are not mapped onto each other."),
        },
    }


# ----------------------------------------------------------------- 8 MRP / ROP
def mrp_rop(F):
    T = engine.totals(F)
    bp = engine.by_plant(F)
    pm = engine.plant_mc(F)
    cur = F["extra"]["curated_reorder_recommendation"]
    mrp = F["extra"]["mrp_type"]
    mrp_unavailable = _uncomputable(mrp["reason"], missing_field="MRP type (SAP MARC-DISMM)")
    within = T["rop_within_20pct_lines"]
    return {
        "id": "mrp_rop", "title": "MRP / ROP",
        "description": ("Engine reorder point and maximum level per material-plant line, against the SAP "
                        "material master. A line is flagged when the two differ by more than +/-20%."),
        "rules_applied": {"lead_time": rules.LEAD_TIME_RULE,
                          "median_pr_to_po_days": rules.MEDIAN_PR_TO_PO_DAYS,
                          "safety_stock": rules.SAFETY_STOCK_RULE,
                          "rop": rules.ROP_RULE, "max": rules.MAX_RULE,
                          "service_levels": rules.SERVICE_LEVEL, "z_values": rules.Z,
                          "flag_tolerance": rules.ROP_FLAG_TOLERANCE},
        "cards": [
            _card("Lines with an ROP", T["lines"], "SKU lines", "QTY",
                  coverage_pct=100.0, lines_in_scope=T["lines"]),
            _card("MRP type VB", None, "SKU lines", "QTY", **mrp_unavailable),
            _card("MRP type PD", None, "SKU lines", "QTY", **mrp_unavailable),
            _card("Within +/-20% of SAP", within, "SKU lines", "QTY",
                  pct=round(100.0 * within / T["lines"], 3)),
            _card("Increase recommended", T["rop_increase_lines"], "SKU lines", "QTY",
                  definition="SAP ROP is more than 20% below the engine ROP",
                  pct=round(100.0 * T["rop_increase_lines"] / T["lines"], 3)),
            _card("Decrease recommended", T["rop_decrease_lines"], "SKU lines", "QTY",
                  definition="SAP ROP is more than 20% above the engine ROP",
                  pct=round(100.0 * T["rop_decrease_lines"] / T["lines"], 3)),
        ],
        "mrp_type_split": mrp_unavailable,
        "rop_vs_master": {
            "lines_total": T["lines"],
            "within_tolerance": within,
            "increase": T["rop_increase_lines"],
            "decrease": T["rop_decrease_lines"],
            "tolerance_pct": rules.ROP_FLAG_TOLERANCE * 100,
            "engine_rop_qty": T["rop_qty"],
            "engine_safety_stock_qty": T["safety_stock_qty"],
            "engine_max_qty": T["max_qty"],
            "flag_detail_basis": F["misc"]["rop_flag"]["note"],
            "sap_rop_present_lines": F["misc"]["rop_flag"]["has_sap_rop"],
            "sap_rop_missing_lines": F["misc"]["rop_flag"]["no_sap_rop"],
            "curated_rop_qty": cur["totals"]["reorder_point_qty"],
            "curated_safety_stock_qty": cur["totals"]["safety_stock_qty"],
            "curated_max_qty": cur["totals"]["max_stock_qty"],
            "curated_rows": cur["rows_total"],
            "curated_note": ("REORDER_RECOMMENDATION covers 3,916 of the 34,717 in-scope lines, so its "
                             "totals are not comparable with the engine totals line for line."),
        },
        "by_plant": {p: {
            "lines": bp[p]["lines"], "safety_stock_qty": bp[p]["safety_stock_qty"],
            "rop_qty": bp[p]["rop_qty"], "max_qty": bp[p]["max_qty"],
            "avg_lead_time_days": bp[p]["avg_lead_time_days"],
        } for p in PLANTS},
        "by_plant_class": [{
            "plant": r["plant"], "movement_class": r["mc"], "lines": r["lines"],
            "safety_stock_qty": r["ss_qty"], "rop_qty": r["rop_qty"], "max_qty": r["max_qty"],
            "avg_lead_time_days": r["avg_lt_days"],
            "rop_within_20": r["rop_within_20"], "rop_increase": r["rop_increase"],
            "rop_decrease": r["rop_decrease"],
        } for r in pm],
        "parameters": {
            "lead_time": engine.lead_time(F),
            "sigma_basis": F["engine"]["sigma"],
            "z_values": F["engine"]["z"],
            "as_of": rules.AS_OF,
        },
    }


# ------------------------------------------------------------- 9 duplicate SKU
def duplicate_sku(F):
    d = engine.duplicates(F)
    dc = F["extra"]["duplicate_clusters"]
    st = dc["scope_totals"]
    return {
        "id": "duplicate_sku", "title": "Duplicate SKU",
        "description": ("Materials whose description is identical inside one material group. Exact match "
                        "scores 1.00 and sits in the >=0.80 likely tier; the base-token variant sits in "
                        "the >=0.60 review tier."),
        "thresholds": {"review": rules.DUPLICATE_REVIEW_THRESHOLD,
                       "likely": rules.DUPLICATE_LIKELY_THRESHOLD},
        "method": dc["method"],
        "cards": [
            _card("Likely duplicate clusters", st["clusters"], "clusters", "QTY",
                  member_materials=st["member_materials"],
                  redundant_materials=st["redundant_materials"],
                  similarity=">= 0.80 (exact description match = 1.00)"),
            _card("Stock in clusters", st["stock_qty"], "base UoM", "QTY",
                  value_inr=st["stock_value_inr"], lines=st["material_plant_lines"]),
            _card("Releasable value", None, "INR", "VALUE",
                  **_uncomputable(d["releasable_value_uncomputable_reason"],
                                  missing_field="a retain-versus-release decision per cluster",
                                  curated_reference_inr=next(
                                      (r[5] for r in F["context"]["curated_opportunity_2025_12"]["rows"]
                                       if r[0] == "ALL_PLANTS"), None))),
            _card("Review candidates", d["review_candidates_ge_060"]["clusters"], "clusters", "QTY",
                  redundant_materials=d["review_candidates_ge_060"]["redundant"],
                  similarity=">= 0.60"),
        ],
        "clusters": {
            "likely_ge_080": d["likely_duplicates_ge_080"],
            "review_ge_060": d["review_candidates_ge_060"],
            "clusters_total": d["clusters_total"],
            "redundant_lines_total": d["redundant_lines_total"],
            "top_by_value": rows_to_dicts(dc["columns_top_clusters"], dc["top_clusters_by_value"]),
        },
        "pairs": {
            "note": ("Each cluster of N materials implies N-1 redundant materials. Pair-level similarity "
                     "scores between 0.60 and 1.00 are not produced: no fuzzy or embedding scorer is "
                     "available in-session, so only the deterministic exact and base-token tiers exist."),
            "rows": [{"material_group": r[0], "description": r[1], "members": r[2],
                      "material_id_min": r[3], "material_id_max": r[4],
                      "similarity": 1.0, "tier": "LIKELY",
                      "stock_qty": r[5], "stock_value_inr": r[6]}
                     for r in dc["top_clusters_by_value"]],
        },
        "releasable_by_plant": rows_to_dicts(dc["columns_by_plant"], dc["by_plant"]),
        "releasable_by_plant_note": ("Stock held against duplicate clusters, by plant. It is stock AT "
                                     "RISK of being redundant, not a releasable figure: releasing it "
                                     "needs the retain/release decision named above."),
    }


# ------------------------------------------------------------ 10 plan vs actual
def plan_vs_actual(F):
    rows = rows_to_dicts(F["misc"]["columns_plan_vs_actual"], F["misc"]["plan_vs_actual_monthly"])
    bp = rows_to_dicts(F["extra"]["plan_vs_actual_by_plant"]["columns"],
                       F["extra"]["plan_vs_actual_by_plant"]["rows"])

    def fy_of(m):
        y, mo = int(m[:4]), int(m[5:7])
        return "FY%d-%02d" % ((y - 1, y % 100) if mo <= 3 else (y, (y + 1) % 100))

    fys = {}
    for r in rows:
        f = fy_of(r["month"])
        a = fys.setdefault(f, {"fy": f, "months": 0, "plan_value_inr": 0.0,
                               "actual_po_value_inr": 0.0, "actual_gr_value_inr": 0.0})
        a["months"] += 1
        a["plan_value_inr"] += r["plan_value_inr"]
        a["actual_po_value_inr"] += r["actual_po_value_inr"]
        a["actual_gr_value_inr"] += r["actual_gr_value_inr"]
    for a in fys.values():
        for k in ("plan_value_inr", "actual_po_value_inr", "actual_gr_value_inr"):
            a[k] = round(a[k], 2)
        a["variance_po_vs_plan_inr"] = round(a["actual_po_value_inr"] - a["plan_value_inr"], 2)
        a["variance_po_vs_plan_pct"] = round(
            100.0 * a["variance_po_vs_plan_inr"] / a["plan_value_inr"], 4) if a["plan_value_inr"] else None
        a["variance_gr_vs_plan_inr"] = round(a["actual_gr_value_inr"] - a["plan_value_inr"], 2)
        a["partial"] = a["months"] < 12
    fy_rows = [fys[k] for k in sorted(fys)]

    plan = round(sum(r["plan_value_inr"] for r in rows), 2)
    po = round(sum(r["actual_po_value_inr"] for r in rows), 2)
    gr = round(sum(r["actual_gr_value_inr"] for r in rows), 2)
    qty_unavailable = _uncomputable(
        F["extra"]["plan_vs_actual_by_plant"]["columns_note"],
        missing_field="a planned-quantity column on BUSINESS_PLAN_VS_ACTUAL")
    return {
        "id": "plan_vs_actual", "title": "Plan vs Actual",
        "description": ("Procurement plan against actual PO and GR. This is the one section where value "
                        "is the only available measure: the table carries no quantity column."),
        "fiscal_year": rules.FISCAL_YEAR,
        "fy_selector": [a["fy"] for a in fy_rows],
        "measure_note": ("Default measure QTY is UNCOMPUTABLE for this section. The Qty/Value toggle is "
                         "locked to Value on this page and the reason is shown in the UI."),
        "qty_view": qty_unavailable,
        "cards": [
            _card("Plan", plan, "INR", "VALUE", months=len(rows), qty_status="UNCOMPUTABLE"),
            _card("Actual PO", po, "INR", "VALUE",
                  variance_vs_plan_inr=round(po - plan, 2),
                  variance_vs_plan_pct=round(100.0 * (po - plan) / plan, 4)),
            _card("Actual GR", gr, "INR", "VALUE",
                  variance_vs_plan_inr=round(gr - plan, 2),
                  variance_vs_plan_pct=round(100.0 * (gr - plan) / plan, 4)),
            _card("Variance (PO vs plan)", round(po - plan, 2), "INR", "VALUE",
                  pct=round(100.0 * (po - plan) / plan, 4)),
        ],
        "monthly": [dict(r,
                         variance_po_vs_plan_inr=round(r["actual_po_value_inr"] - r["plan_value_inr"], 2),
                         variance_gr_vs_plan_inr=round(r["actual_gr_value_inr"] - r["plan_value_inr"], 2))
                    for r in rows],
        "by_fy": fy_rows,
        "by_plant": bp,
        "variance_table": [{
            "month": r["month"], "plan_value_inr": r["plan_value_inr"],
            "actual_po_value_inr": r["actual_po_value_inr"],
            "actual_gr_value_inr": r["actual_gr_value_inr"],
            "variance_po_inr": round(r["actual_po_value_inr"] - r["plan_value_inr"], 2),
            "variance_po_pct": round(100.0 * (r["actual_po_value_inr"] - r["plan_value_inr"]) / r["plan_value_inr"], 4),
            "variance_gr_inr": round(r["actual_gr_value_inr"] - r["plan_value_inr"], 2),
            "variance_gr_pct": round(100.0 * (r["actual_gr_value_inr"] - r["plan_value_inr"]) / r["plan_value_inr"], 4),
        } for r in rows],
        "note": F["misc"]["plan_vs_actual_note"],
    }


# ------------------------------------------------------------- 11 data sources
def data_sources(F, run_ts):
    s1 = F["step1"]
    ev = F["step2"]
    exp = ev.get("experiment_A_authoritative", {})
    T = engine.totals(F)
    mapping = F["context"]["sap_field_mapping"]
    return {
        "id": "data_sources", "title": "Data Sources",
        "description": ("Every table, rule and mapping behind the figures on the other pages, with the "
                        "RAW-versus-CURATED position stated rather than smoothed over."),
        "cards": [
            _card("As-of date", rules.AS_OF, "date", "META",
                  period=f"{rules.PERIOD_FROM}..{rules.PERIOD_TO}", fiscal_year=rules.FISCAL_YEAR),
            _card("Run timestamp", run_ts, "UTC", "META"),
            _card("SKU lines", T["lines"], "material-plant lines", "QTY",
                  materials=s1["profile"]["materials_in_scope"],
                  plants=len(PLANTS), material_groups=s1["profile"]["material_groups_in_scope"]),
            _card("Tables discovered", s1["source"]["tables_discovered"], "tables", "META",
                  schema=s1["source"]["schema"]),
            _card("Columns in schema", 377, "columns", "META",
                  basis="SYS.TABLE_COLUMNS over the 42 VEDANTA_POC tables"),
            _card("SAP field mappings", len(mapping["rows"]), "mappings", "META",
                  status=mapping["mapping_status_verbatim"]),
        ],
        "connection": s1["source"],
        "scope": s1["scope"],
        "tables_used": {
            "RAW": ["FACT_MATERIAL_MOVEMENT_PART_001..004", "FACT_INVENTORY_SNAPSHOT_PART_001..003",
                    "FACT_PURCHASE_REQUISITION", "FACT_PURCHASE_ORDER", "FACT_GOODS_RECEIPT",
                    "FACT_SHUTDOWN_SCHEDULE", "FACT_MAINTENANCE_REQUIREMENT",
                    "DIM_MATERIAL", "DIM_PLANT", "DIM_SHUTDOWN_EVENT", "DIM_MAINTENANCE_ORDER",
                    "CATEGORY_MAP", "SEASONALITY_INPUT", "BUSINESS_PLAN_VS_ACTUAL",
                    "MATERIAL_PLANT_CLASSIFICATION", "SAP_FIELD_MAPPING"],
            "CURATED": ["INVENTORY_KPI_MONTHLY", "INVENTORY_CLASSIFICATION", "REORDER_RECOMMENDATION"],
        },
        "schema_traps": s1["schema_traps"],
        "provenance": {
            "step1": {"file": "step1/step1_data.json", "by": s1["generated_by"],
                      "at": s1["generated_at_utc"]},
            "step2": {"file": F["step2_source"], "by": ev.get("verified_by"),
                      "at": ev.get("verified_at_utc"),
                      "missing": F.get("step2_missing")},
            "step3": {"sql": "step3/sql/engine_base.sql",
                      "facts": ["step3/facts/engine_full_lt.json", "step3/facts/plant_mc.json",
                                "step3/facts/misc.json", "step3/facts/pr_detail.json",
                                "step3/facts/context.json", "step3/facts/step3_extra.json"],
                      "at": run_ts},
        },
        "movement_class_rules": rules.MOVEMENT_CLASS_RULES,
        "business_rules": {
            "demand": "NET_DEMAND = SUM(MovType 261 qty) - SUM(MovType 262 qty) by material/plant/month",
            "service_levels": rules.SERVICE_LEVEL, "z_values": rules.Z,
            "lead_time": rules.LEAD_TIME_RULE,
            "median_pr_to_po_days": rules.MEDIAN_PR_TO_PO_DAYS,
            "safety_stock": rules.SAFETY_STOCK_RULE,
            "rop": rules.ROP_RULE, "max": rules.MAX_RULE,
            "overstock": rules.OVERSTOCK_RULE, "understock": rules.UNDERSTOCK_RULE,
            "nm_sm_horizon_days": rules.NM_SM_HORIZON_DAYS,
            "holding_cost_pct": rules.HOLDING_COST_PCT,
            "duplicate_review_threshold": rules.DUPLICATE_REVIEW_THRESHOLD,
            "duplicate_likely_threshold": rules.DUPLICATE_LIKELY_THRESHOLD,
            "rop_flag_tolerance": rules.ROP_FLAG_TOLERANCE,
            "unit": "material-plant line count (SKU) plus base UoM quantity; INR only under the toggle",
        },
        "sap_mapping": {"status": mapping["mapping_status_verbatim"],
                        "source": mapping["source"], "rows": mapping["rows"]},
        "contextflow": {
            "engine": ev.get("contextflow_engine"),
            "experiment_id": exp.get("id"),
            "model": exp.get("winner_verbatim", {}).get("bestCandidateId"),
            "endpoint": exp.get("endpoint", {}).get("endpointId"),
            "experiments_found": ev.get("experiments_found"),
        },
    }


def reconciliation_panel(F):
    s1 = F["step1"]
    T = engine.totals(F)
    cur = F["extra"]["curated_reorder_recommendation"]
    items = []
    for it in s1["reconciliation"]["items"]:
        it = dict(it)
        # Step 1 published R3 as a per-class breakdown with no roll-up. The panel
        # contract is CURATED / RAW / Diff / Diff% on every row, so roll it up from
        # the breakdown it already carries rather than restating it by hand.
        if "curated" not in it and it.get("by_class"):
            cur_by_class = {r["class"]: r["curated"] for r in it["by_class"]}
            raw_by_class = {r["class"]: r["raw"] for r in it["by_class"]}
            moved = sum(abs(r["diff"]) for r in it["by_class"]) // 2
            total = sum(cur_by_class.values())
            it["curated"] = cur_by_class
            it["raw"] = raw_by_class
            it["diff"] = {r["class"]: r["diff"] for r in it["by_class"]}
            it["diff_pct"] = round(100.0 * moved / total, 4) if total else None
            it["diff_basis"] = ("lines reclassified between classes, as a percentage of all "
                                "%d in-scope lines" % total)
        items.append(it)
    items.append({
        "id": "R7", "item": "Reorder point total (engine vs curated REORDER_RECOMMENDATION)",
        "curated_source": "REORDER_RECOMMENDATION.REORDER_POINT_QTY, 3,916 rows",
        "raw_source": "engine ROP = lead-time demand + safety stock over 34,717 lines",
        "curated": cur["totals"]["reorder_point_qty"],
        "raw": T["rop_qty"],
        "diff": round(T["rop_qty"] - cur["totals"]["reorder_point_qty"], 3),
        "diff_pct": round(100.0 * (T["rop_qty"] - cur["totals"]["reorder_point_qty"])
                          / cur["totals"]["reorder_point_qty"], 4),
        "status": "DIFFERENCE - DIFFERENT POPULATIONS",
        "note": ("The curated table covers 3,916 material-plant pairs; the engine covers all 34,717 "
                 "in-scope lines. The difference is mostly population, not method, and the two are "
                 "never netted. Shown because the brief says never hide a difference."),
    })
    items.append({
        "id": "R8", "item": "Movement-class counts (engine rule vs curated MOVEMENT_CLASS)",
        "curated_source": "INVENTORY_CLASSIFICATION.MOVEMENT_CLASS @ 2025-12-31",
        "raw_source": "brief thresholds applied to DAYS_SINCE_LAST_CONSUMPTION",
        "curated": {"ACTIVE": 18723, "SLOW_MOVING": 9196, "NON_MOVING": 2934, "OBSOLETE": 3864},
        "raw": {k: engine.by_class(F)[k]["lines"] for k in CLASSES},
        "diff": {"NON_MOVING": engine.by_class(F)["NON_MOVING"]["lines"] - 2934,
                 "OBSOLETE": engine.by_class(F)["OBSOLETE"]["lines"] - 3864},
        "diff_pct": None,
        "status": "DIFFERENCE - 1,199 lines (3.45%)",
        "note": ("1,195 lines aged 181-365 days are curated OBSOLETE but are NON_MOVING under the "
                 "brief; 4 never-issued lines are curated OBSOLETE but are NON_MOVING under the brief. "
                 "ACTIVE and SLOW_MOVING agree exactly. The engine rule governs every figure here."),
    })
    return {
        "policy": s1["reconciliation"]["policy"],
        "as_of": s1["reconciliation"]["as_of"],
        "items": items,
        "summary": dict(s1["reconciliation"]["summary"], items_checked=len(items),
                        difference=s1["reconciliation"]["summary"]["difference"] + 2),
        "note": ("CURATED / RAW / Diff / Diff% for every item. Where the two disagree the engine rule "
                 "from the brief governs, and the curated figure is still shown."),
    }


# -------------------------------------------------------------------- 12 RAIA
def raia(F, kpi_rows, kpi_summary, warnings, run_ts):
    ev = F["step2"]
    exp = ev.get("experiment_A_authoritative", {})
    diag = exp.get("holdout_diagnostics_verbatim", {})
    T = engine.totals(F)
    bc = engine.by_class(F)
    conf = engine.nm_sm_confusion(F)
    cm = engine.crit_mc(F)
    uncomputable = [{"item": r["label"], "reason": r.get("uncomputable_reason")}
                    for r in kpi_rows if r["status"] == "UNCOMPUTABLE"]
    uncomputable += [
        {"item": "Forward forecast horizons 3/6/9/12 months",
         "reason": ("step2_forecast.json was never produced and the deployed model cannot extrapolate "
                    "(2099-06 returns 2026-06 exactly).")},
        {"item": "Material-level forecast",
         "reason": "MATERIAL_ID is not a ContextFlow feature; two different materials return byte-identical predictions."},
        {"item": "MAPE", "reason": "Zero-demand cohort-months make MAPE diverge (~1e15). WAPE is used."},
        {"item": "MRP type VB/PD split",
         "reason": "No MRP-type column exists in VEDANTA_POC; SAP MARC-DISMM is not in the extract."},
        {"item": "Plan vs Actual in QTY",
         "reason": "BUSINESS_PLAN_VS_ACTUAL carries value columns only; there is no planned-quantity column."},
        {"item": "Projected shutdown and maintenance requirement",
         "reason": "Every shutdown event is COMPLETED and dated no later than 2025-09-19; every maintenance row is COMPLETED."},
        {"item": "Duplicate SKU releasable value",
         "reason": "Needs a retain-versus-release decision per cluster, which is a planner judgement absent from the extract."},
        {"item": "Reduction-opportunity quantity",
         "reason": "INVENTORY_KPI_MONTHLY carries POTENTIAL_REDUCTION_INR only, with no quantity counterpart."},
    ]
    top_over = sorted([{"plant": r["plant"], "movement_class": r["mc"], "lines": r["over_lines"],
                        "qty": r["over_qty"], "value_inr": r["over_val"]}
                       for r in engine.plant_mc(F)], key=lambda x: -x["value_inr"])[:8]
    top_under = sorted(rows_to_dicts(F["pr_detail"]["columns"], F["pr_detail"]["rows"]),
                       key=lambda r: -r["pr_value_inr"])[:8]
    return {
        "id": "raia", "title": "RAIA - Responsible AI Assessment",
        "description": ("What the engine is, what it was allowed to conclude, and every place the data "
                        "would not support a conclusion."),
        "engine": {
            "forecast_engine": "ContextFlow AutoML (onprem), reached over MCP",
            "status": ev.get("contextflow_engine", {}).get("statusHint"),
            "problem_types_available": ev.get("contextflow_engine", {}).get("onprem_problem_types"),
            "inventory_engine": ("Deterministic arithmetic over SAP HANA VEDANTA_POC, executed in HANA "
                                 "(step3/sql/engine_base.sql). No model, no imputation, no estimate."),
            "run_timestamp_utc": run_ts,
        },
        "contextflow_model": {
            "experiment_id": exp.get("id"),
            "model": exp.get("winner_verbatim", {}).get("bestCandidateId"),
            "why_it_won_verbatim": exp.get("why_it_ranked_first_verbatim"),
            "primary_metric": exp.get("dataset", {}).get("primaryMetric"),
            "candidates": exp.get("candidates_trained"),
            "validation_regression_not_classification":
                ev.get("validations_required_by_the_brief", {}).get("task_is_regression_not_classification"),
            "validation_target_is_quantity":
                ev.get("validations_required_by_the_brief", {}).get("target_is_a_quantity"),
            "validation_engine_selected":
                ev.get("validations_required_by_the_brief", {}).get("model_chosen_by_contextflow_not_by_us"),
            "endpoint_pinned": exp.get("endpoint", {}).get("endpointId"),
            "second_endpoint_warning": ev.get("experiment_B_second_run", {}).get("significance"),
        },
        "raw_vs_curated": {
            "position": ("RAW governs. Where the curated tables disagree with the brief's rules the "
                         "engine recomputes from RAW and the curated figure is shown beside it."),
            "known_divergences": [
                "Movement class: 1,199 of 34,717 lines (3.45%) - curated OBSOLETE where the brief says NON_MOVING.",
                "ROP: curated REORDER_RECOMMENDATION covers 3,916 lines against the engine's 34,717, on a gross-issues rather than net-demand basis.",
                "Gross inventory qty and value, and line count, reconcile EXACTLY (diff 0.0).",
            ],
        },
        "reconciliation": reconciliation_panel(F),
        "accuracy": {
            "qty_accuracy_pct": round(100.0 * (1 - diag["wape"]), 4) if diag.get("wape") is not None else None,
            "wape": diag.get("wape"), "rmse": diag.get("rmse"), "r2": diag.get("r2"),
            "target_pct": 90.0,
            "verdict": "RED",
            "caveats": [
                "The published WAPE belongs to WeightedEnsemble_L2 (rank 2), not to the deployed champion ExtraTreesMSE.",
                "The holdout is a deterministic RANDOM 20% split, not the time-ordered 6-month split the brief requires, so the figure is an optimistic upper bound.",
                "MAPE is UNCOMPUTABLE because the target contains zeros.",
            ],
        },
        "limitations": [
            "No forward forecast: the model replays history rather than projecting it.",
            "No material grain: MATERIAL_ID is not a feature, so the brief's drill-to-material SUCCESS criterion is not met by a forecast, only by an allocation.",
            "Training file is 6,000 rows against 34,717 real material-plant lines.",
            "Two in_service ContextFlow endpoints differ by 35% on RMSE; the dashboard pins experiment " + str(exp.get("id")) + ".",
            "Every figure is synthetic HZL_DEMO POC data, not Vedanta or Hindustan Zinc performance.",
        ],
        "uncomputable_items": uncomputable,
        "assumptions": [
            "Sigma for safety stock is the zero-filled monthly net-demand sigma over the 24 in-scope months.",
            "Median PR-to-PO is 24 days, applied uniformly because the extract gives no per-material PR-to-PO median.",
            "The 12-month forecast used in ROP/MAX arithmetic is trailing-12 net demand carried forward; it is labelled as such everywhere and is not a ContextFlow forecast.",
            "Vital availability is reported both as 'has any stock' and as 'at or above ROP' because the brief does not say which.",
            "The 90-day NM/SM transition is an ageing projection, not a prediction of consumption.",
        ],
        "data_quality": {
            "warnings_from_step1": F["step1"]["warnings"],
            "never_issued_lines": F["misc"]["nom_days"]["never_issued_lines"],
            "never_issued_sentinel_days": F["misc"]["nom_days"]["never_issued_sentinel_days"],
            "zero_demand_cohort_months": 154,
            "reserved_qty_all_zero": True,
            "all_plants_rollup": "excluded from every sum and filter",
            "lines_in_scope": T["lines"],
        },
        "forecast": {
            "status": "DEGRADED",
            "what_exists": "A regression model on quantity, engine-selected, validated, with holdout diagnostics.",
            "what_does_not": "Forward horizons, material grain, and a time-ordered holdout.",
            "consequence": ("Sections that need a forward quantity publish UNCOMPUTABLE with the reason. "
                            "No run-rate number is ever presented as a forecast."),
        },
        "top_risks": {
            "overstock": top_over,
            "understock": top_under,
            "non_moving": {"lines": bc["NON_MOVING"]["lines"], "qty": bc["NON_MOVING"]["stock_qty"],
                           "value_inr": bc["NON_MOVING"]["stock_value_inr"]},
            "slow_moving": {"lines": bc["SLOW_MOVING"]["lines"], "qty": bc["SLOW_MOVING"]["stock_qty"],
                            "value_inr": bc["SLOW_MOVING"]["stock_value_inr"]},
            "obsolete": {"lines": bc["OBSOLETE"]["lines"], "qty": bc["OBSOLETE"]["stock_qty"],
                         "value_inr": bc["OBSOLETE"]["stock_value_inr"]},
            "vital_below_rop_lines": sum(r["lines"] - r["at_or_above_rop"] for r in cm if r["criticality"] == "VITAL"),
            "nm_sm_classifier_f1": conf["f1"],
        },
        "actions": [
            {"priority": "high", "action": "Re-run the ContextFlow experiment with MATERIAL_ID as a feature and a time-ordered 2025-07..2025-12 holdout",
             "reason": "Without both, neither the material drill nor a trustworthy accuracy number is reachable.",
             "owner": "Forecasting (S-7)"},
            {"priority": "high", "action": "Raise the " + str(T["understock_lines"]) + " below-ROP lines, starting with the zero-cover bucket",
             "reason": "Zero weeks of cover against a 69.7-day average lead time.",
             "owner": "Inventory Control"},
            {"priority": "high", "action": "Correct the material master on the lines where SAP ROP is outside the +/-20% band",
             "reason": str(T["rop_increase_lines"]) + " lines sit more than 20% below the engine ROP.",
             "owner": "Master Data"},
            {"priority": "medium", "action": "Review the " + str(bc["OBSOLETE"]["lines"]) + " obsolete lines for write-down or release",
             "reason": "They carry " + str(bc["OBSOLETE"]["stock_value_inr"]) + " INR at an 8% holding cost.",
             "owner": "Stores"},
            {"priority": "medium", "action": "Resolve the 205 likely-duplicate clusters",
             "reason": "223 redundant materials holding stock across six plants.",
             "owner": "Master Data"},
            {"priority": "medium", "action": "Reconcile the curated movement class with the brief rule",
             "reason": "1,199 lines are classed OBSOLETE that are NON_MOVING under the brief, distorting NMI and the obsolete KPI.",
             "owner": "Data Engineering"},
        ],
        "warnings": warnings,
        "kpi_summary": kpi_summary,
        "disclaimer": F["context"]["curated_opportunity_2025_12"]["disclaimer_verbatim"],
    }
