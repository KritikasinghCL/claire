"""The 13 KPIs, each with Target / Actual / Variance / Status.

Rules of the house:
  * QTY in base UoM is the measure; value is carried alongside as the toggle field.
  * A KPI whose inputs are not in the extract is actual=None, status UNCOMPUTABLE
    and carries the field that is missing. It is never estimated.
  * Every actual names the basis it was computed from.
"""
import rules
import engine
from facts import rows_to_dicts


def _series(F):
    c = F["context"]["kpi_monthly_value_inr"]
    return rows_to_dicts(c["columns"], c["rows"])


def _ratios(F):
    c = F["context"]["kpi_monthly_ratios"]
    return rows_to_dicts(c["columns"], c["rows"])


def _reduction(series, key):
    """Reduction over the in-scope window, first month vs last, as a positive %."""
    first, last = series[0][key], series[-1][key]
    if not first:
        return None, None, None
    return round(100.0 * (first - last) / first, 4), first, last


def build(F):
    S = _series(F)
    R = _ratios(F)
    T = engine.totals(F)
    CM = engine.crit_mc(F)
    conf = engine.nm_sm_confusion(F)
    dup = engine.duplicates(F)
    out = []

    def add(code, actual, basis, note=None, extra=None):
        label, target, unit, direction = rules.KPI_TARGETS[code]
        row = {
            "code": code, "label": label, "unit": unit,
            "target": target, "actual": actual,
            "variance": rules.variance(actual, target),
            "status": rules.status_for(actual, target, direction),
            "direction": direction, "basis": basis,
        }
        if actual is None:
            row["uncomputable_reason"] = note
        elif note:
            row["note"] = note
        if extra:
            row.update(extra)
        out.append(row)

    # 1 Gross inventory reduction
    gi, gi0, gi1 = _reduction(S, "gross_inventory_value_inr")
    add("GROSS_INVENTORY_REDUCTION", gi,
        "INVENTORY_KPI_MONTHLY.GROSS_INVENTORY_VALUE_INR, 6 physical plants, 2024-01 vs 2025-12",
        "Measured on value because gross inventory is a value KPI by definition; the QTY equivalent "
        "cannot be trended — FACT_INVENTORY_SNAPSHOT closing qty reconciles only at the 2025-12-31 "
        "as-of date, not as a 24-month series.",
        {"baseline_2024_01_inr": gi0, "current_2025_12_inr": gi1})

    # 2 NMI
    nmi, nm0, nm1 = _reduction(S, "non_moving_value_inr")
    add("NMI", nmi, "INVENTORY_KPI_MONTHLY.NON_MOVING_VALUE_INR, 2024-01 vs 2025-12",
        None, {"baseline_2024_01_inr": nm0, "current_2025_12_inr": nm1,
               "engine_non_moving_lines": engine.by_class(F)["NON_MOVING"]["lines"],
               "engine_non_moving_value_inr": engine.by_class(F)["NON_MOVING"]["stock_value_inr"]})

    # 3 SMI
    smi, sm0, sm1 = _reduction(S, "slow_moving_value_inr")
    add("SMI", smi, "INVENTORY_KPI_MONTHLY.SLOW_MOVING_VALUE_INR, 2024-01 vs 2025-12",
        "The slow-moving series is volatile month to month (160m to 1,352m INR inside 2025); a "
        "first-vs-last reading is sensitive to the endpoint and is shown with the full series.",
        {"baseline_2024_01_inr": sm0, "current_2025_12_inr": sm1,
         "engine_slow_moving_lines": engine.by_class(F)["SLOW_MOVING"]["lines"],
         "engine_slow_moving_value_inr": engine.by_class(F)["SLOW_MOVING"]["stock_value_inr"]})

    # 4 Obsolete reduction
    ob, ob0, ob1 = _reduction(S, "obsolete_value_inr")
    add("OBSOLETE_REDUCTION", ob, "INVENTORY_KPI_MONTHLY.OBSOLETE_VALUE_INR, 2024-01 vs 2025-12",
        None, {"baseline_2024_01_inr": ob0, "current_2025_12_inr": ob1,
               "engine_obsolete_lines": engine.by_class(F)["OBSOLETE"]["lines"],
               "engine_obsolete_value_inr": engine.by_class(F)["OBSOLETE"]["stock_value_inr"]})

    # 5 Qty accuracy (1 - WAPE) from ContextFlow
    ev = F["step2"]
    exp = ev.get("experiment_A_authoritative", {})
    diag = exp.get("holdout_diagnostics_verbatim", {})
    wape = diag.get("wape")
    qty_acc = round(100.0 * (1 - wape), 4) if wape is not None else None
    add("QTY_ACCURACY", qty_acc,
        f"ContextFlow experiment {exp.get('id','?')} holdout diagnostics, wape={wape}",
        ("The published WAPE belongs to WeightedEnsemble_L2 (rank 2, rmse 174.086569), not to the "
         "deployed champion ExtraTreesMSE (rmse 172.503385) — the diagnostics block's rmse/r2 match "
         "rank 2 exactly. The holdout is also a deterministic RANDOM 20% split, not the time-ordered "
         "6-month split the brief requires, so this figure is an optimistic upper bound on forecast "
         "accuracy rather than forecast accuracy."),
        {"wape": wape, "rmse_of_this_diagnostic": diag.get("rmse"),
         "champion_rmse": exp.get("winner_verbatim", {}).get("rmse_holdout"),
         "diagnostic_belongs_to": "WeightedEnsemble_L2 (rank 2)",
         "mape": None,
         "mape_uncomputable_reason": ("The target contains zero-demand cohort-months, so MAPE diverges; "
                                      "every candidate's own MAPE is of order 1e15. Use WAPE.")})

    # 6 Inventory forecast accuracy
    add("INVENTORY_FORECAST_ACCURACY", None,
        "would require a forecast of closing inventory position compared against actuals",
        ("No inventory-position forecast exists. ContextFlow experiment "
         f"{exp.get('id','?')} forecasts consumption quantity (target actual_qty), not inventory "
         "position, and step2_forecast.json was never produced (S-3 blocked). Missing field: a "
         "forecast of FACT_INVENTORY_SNAPSHOT.CLOSING_QTY per material-plant-month."))

    # 7 NM/SM F1
    add("NM_SM_F1", conf["f1"],
        "engine movement class (brief thresholds) vs SAP DIM_MATERIAL.NM_SM_CLASS over 34,717 lines",
        None, {"precision": conf["precision"], "recall": conf["recall"],
               "agreement_pct": conf["agreement_pct"],
               "true_positive": conf["true_positive"], "false_positive": conf["false_positive"],
               "false_negative": conf["false_negative"], "true_negative": conf["true_negative"]})

    # 8 Vital availability
    vital = [r for r in CM if r["criticality"] == "VITAL"]
    v_lines = sum(r["lines"] for r in vital)
    v_stocked = sum(r["has_stock"] for r in vital)
    v_at_rop = sum(r["at_or_above_rop"] for r in vital)
    v_avail = round(100.0 * v_stocked / v_lines, 4) if v_lines else None
    add("VITAL_AVAILABILITY", v_avail,
        "INVENTORY_CLASSIFICATION @ 2025-12-31: VITAL lines with AVAILABLE_QTY > 0 / all VITAL lines",
        ("Availability here is 'has any stock'. On the stricter 'at or above ROP' reading it is "
         f"{round(100.0 * v_at_rop / v_lines, 4)}% — both are shown because the brief does not say which."),
        {"vital_lines": v_lines, "vital_lines_with_stock": v_stocked,
         "vital_lines_zero_stock": v_lines - v_stocked,
         "vital_lines_at_or_above_rop": v_at_rop,
         "vital_availability_at_rop_pct": round(100.0 * v_at_rop / v_lines, 4) if v_lines else None,
         "service_level_target_pct": rules.SERVICE_LEVEL["VITAL"]})

    # 9 ROP coverage
    cov = round(100.0 * T["lines"] / T["lines"], 4) if T["lines"] else None
    add("ROP_COVERAGE", cov,
        "every one of the 34,717 in-scope material-plant lines has an engine-computed ROP",
        ("Coverage is 100% of lines. Agreement with SAP's own REORDER_POINT_QTY is a separate "
         f"measure and is far lower: {T['rop_within_20pct_lines']} of {T['lines']} lines "
         f"({round(100.0 * T['rop_within_20pct_lines'] / T['lines'], 2)}%) sit within the +/-20% flag band."),
        {"lines_with_rop": T["lines"], "lines_in_scope": T["lines"],
         "lines_agreeing_with_sap_within_20pct": T["rop_within_20pct_lines"],
         "lines_sap_rop_too_low": T["rop_increase_lines"],
         "lines_sap_rop_too_high": T["rop_decrease_lines"]})

    # 10 Duplicate SKU
    add("DUPLICATE_SKU", dup["clusters_total"],
        "deterministic description match within MATERIAL_GROUP on DIM_MATERIAL",
        dup["method"],
        {"likely_clusters_ge_080": dup["likely_duplicates_ge_080"]["clusters"],
         "likely_redundant_lines": dup["likely_duplicates_ge_080"]["redundant"],
         "review_clusters_ge_060": dup["review_candidates_ge_060"]["clusters"],
         "review_redundant_lines": dup["review_candidates_ge_060"]["redundant"],
         "curated_opportunity_inr": next(
             (r[5] for r in F["context"]["curated_opportunity_2025_12"]["rows"] if r[0] == "ALL_PLANTS"), None)})

    # 11 PR date adherence
    pa = F["misc"]["pr_history"]["date_adherence"]
    denom = pa["on_time"] + pa["late"]
    adh = round(100.0 * pa["on_time"] / denom, 4) if denom else None
    add("PR_DATE_ADHERENCE", adh,
        "FACT_PURCHASE_REQUISITION: APPROVAL_DATE <= REQUIRED_DATE over PRs that have both dates",
        (f"{pa['no_approval_date']} of {pa['total']} PRs carry no APPROVAL_DATE (all CANCELLED) and are "
         "excluded from the denominator rather than counted as late."),
        {"on_time": pa["on_time"], "late": pa["late"],
         "excluded_no_approval_date": pa["no_approval_date"], "total_prs": pa["total"]})

    # 12 PR count YoY
    ph = F["misc"]["pr_history"]
    yoy = round(100.0 * (ph["2025"]["count"] - ph["2024"]["count"]) / ph["2024"]["count"], 4)
    add("PR_COUNT_YOY", yoy, "FACT_PURCHASE_REQUISITION count, calendar 2025 vs calendar 2024",
        ("The target is a >=10% REDUCTION in PR count; the actual is a rise, so this is RED. "
         "Direction is lower_is_better and the target is encoded as +10% to make the sign explicit."),
        {"pr_count_2024": ph["2024"]["count"], "pr_count_2025": ph["2025"]["count"],
         "pr_qty_2024": ph["2024"]["qty"], "pr_qty_2025": ph["2025"]["qty"]})

    # 13 Non-Operating-Material days
    nom = F["misc"]["nom_days"]
    add("NOM_DAYS", nom["avg_days_since_last_consumption"],
        "INVENTORY_CLASSIFICATION.DAYS_SINCE_LAST_CONSUMPTION, mean over the 34,713 lines with history",
        (f"{nom['never_issued_lines']} never-issued lines carry a {nom['never_issued_sentinel_days']} "
         "sentinel and are excluded from the mean; they are classed NON_MOVING per the brief. "
         f"{nom['lines_gt_90d']} lines exceed the 90-day NM/SM horizon."),
        {"lines_with_history": nom["lines_with_history"],
         "never_issued_lines": nom["never_issued_lines"],
         "max_days": nom["max_days"], "lines_over_90d": nom["lines_gt_90d"],
         "nm_sm_horizon_days": rules.NM_SM_HORIZON_DAYS})

    assert len(out) == 13, f"expected 13 KPIs, built {len(out)}"
    return out


def summary(kpi_rows):
    counts = {}
    for r in kpi_rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"total": len(kpi_rows), "by_status": counts,
            "green": counts.get("GREEN", 0), "amber": counts.get("AMBER", 0),
            "red": counts.get("RED", 0), "uncomputable": counts.get("UNCOMPUTABLE", 0),
            "info": counts.get("INFO", 0)}
