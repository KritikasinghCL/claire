"""Derive classification, stock position, ROP/MAX, PR recommendations and the 13 KPIs.

Everything here is arithmetic over facts read from HANA. Where an input does not
exist, the output is None and the caller labels it UNCOMPUTABLE with the reason —
no estimate is ever substituted.
"""
import rules
from facts import rows_to_dicts

PLANTS = ["HZL_DEMO_01", "HZL_DEMO_02", "HZL_DEMO_03", "HZL_DEMO_04", "HZL_DEMO_05", "HZL_DEMO_06"]
CLASSES = ["ACTIVE", "SLOW_MOVING", "NON_MOVING", "OBSOLETE"]


def plant_mc(F):
    return rows_to_dicts(F["engine"]["columns_plant_mc"], F["engine"]["plant_mc"])


def crit_mc(F):
    return rows_to_dicts(F["engine"]["columns_crit_mc"], F["engine"]["crit_mc"])


def group_type(F):
    return rows_to_dicts(F["engine"]["columns_group_type"], F["engine"]["group_type"])


def _sum(rows, key, where=None):
    return round(sum(r[key] for r in rows if (where is None or where(r))), 3)


def totals(F):
    """Scope-wide engine totals, QTY first and value only as the toggle field."""
    pm = plant_mc(F)
    t = {
        "lines": sum(r["lines"] for r in pm),
        "stock_qty": _sum(pm, "stock_qty"),
        "stock_value_inr": round(sum(r["stock_val"] for r in pm), 2),
        "safety_stock_qty": _sum(pm, "ss_qty"),
        "rop_qty": _sum(pm, "rop_qty"),
        "max_qty": _sum(pm, "max_qty"),
        "forecast_12m_qty": _sum(pm, "f12_qty"),
        "forecast_3m_qty": _sum(pm, "f3_qty"),
        "overstock_lines": sum(r["over_lines"] for r in pm),
        "overstock_qty": _sum(pm, "over_qty"),
        "overstock_value_inr": round(sum(r["over_val"] for r in pm), 2),
        "understock_lines": sum(r["under_lines"] for r in pm),
        "understock_qty": _sum(pm, "under_qty"),
        "understock_value_inr": round(sum(r["under_val"] for r in pm), 2),
        "below_safety_stock_lines": sum(r["below_ss_lines"] for r in pm),
        "zero_stock_lines": sum(r["zero_stock_lines"] for r in pm),
        "no_demand_lines": sum(r["nodemand_lines"] for r in pm),
        "no_demand_value_inr": round(sum(r["nodemand_val"] for r in pm), 2),
        "rop_within_20pct_lines": sum(r["rop_within_20"] for r in pm),
        "rop_increase_lines": sum(r["rop_increase"] for r in pm),
        "rop_decrease_lines": sum(r["rop_decrease"] for r in pm),
    }
    t["holding_cost_on_overstock_inr"] = round(t["overstock_value_inr"] * rules.HOLDING_COST_PCT, 2)
    return t


def by_class(F):
    pm = plant_mc(F)
    out = {}
    for k in CLASSES:
        rows = [r for r in pm if r["mc"] == k]
        out[k] = {
            "lines": sum(r["lines"] for r in rows),
            "stock_qty": _sum(rows, "stock_qty"),
            "stock_value_inr": round(sum(r["stock_val"] for r in rows), 2),
            "overstock_lines": sum(r["over_lines"] for r in rows),
            "overstock_value_inr": round(sum(r["over_val"] for r in rows), 2),
            "understock_lines": sum(r["under_lines"] for r in rows),
            "forecast_12m_qty": _sum(rows, "f12_qty"),
        }
    return out


def by_plant(F):
    pm = plant_mc(F)
    out = {}
    for p in PLANTS:
        rows = [r for r in pm if r["plant"] == p]
        out[p] = {
            "lines": sum(r["lines"] for r in rows),
            "stock_qty": _sum(rows, "stock_qty"),
            "stock_value_inr": round(sum(r["stock_val"] for r in rows), 2),
            "safety_stock_qty": _sum(rows, "ss_qty"),
            "rop_qty": _sum(rows, "rop_qty"),
            "max_qty": _sum(rows, "max_qty"),
            "forecast_12m_qty": _sum(rows, "f12_qty"),
            "overstock_lines": sum(r["over_lines"] for r in rows),
            "overstock_value_inr": round(sum(r["over_val"] for r in rows), 2),
            "understock_lines": sum(r["under_lines"] for r in rows),
            "understock_value_inr": round(sum(r["under_val"] for r in rows), 2),
            "below_safety_stock_lines": sum(r["below_ss_lines"] for r in rows),
            "zero_stock_lines": sum(r["zero_stock_lines"] for r in rows),
            "avg_lead_time_days": round(
                sum(r["avg_lt_days"] * r["lines"] for r in rows) / max(sum(r["lines"] for r in rows), 1), 3),
            "by_class": {r["mc"]: {"lines": r["lines"], "stock_qty": r["stock_qty"],
                                   "stock_value_inr": r["stock_val"]} for r in rows},
        }
    return out


def nm_sm_confusion(F):
    """Engine movement class vs SAP NM_SM_CLASS, and precision/recall/F1 on the NM+SM
    positive class. The confusion rows come from HANA; the arithmetic is here."""
    cols = F["misc"]["columns_nmsm_confusion"]
    rows = rows_to_dicts(cols, F["misc"]["nmsm_confusion"])
    pos_engine = {"NON_MOVING", "SLOW_MOVING", "OBSOLETE"}
    pos_sap = {"NM", "SM", "OBSOLETE"}
    tp = sum(r["lines"] for r in rows if r["engine_class"] in pos_engine and r["sap_nm_sm_class"] in pos_sap)
    fp = sum(r["lines"] for r in rows if r["engine_class"] in pos_engine and r["sap_nm_sm_class"] not in pos_sap)
    fn = sum(r["lines"] for r in rows if r["engine_class"] not in pos_engine and r["sap_nm_sm_class"] in pos_sap)
    tn = sum(r["lines"] for r in rows if r["engine_class"] not in pos_engine and r["sap_nm_sm_class"] not in pos_sap)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None
    agree = sum(r["lines"] for r in rows
                if (r["engine_class"] in pos_engine) == (r["sap_nm_sm_class"] in pos_sap))
    total = sum(r["lines"] for r in rows)
    return {
        "matrix": rows,
        "positive_class": "NM + SM + OBSOLETE (anything not ACTIVE)",
        "true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn,
        "precision": round(precision, 6) if precision is not None else None,
        "recall": round(recall, 6) if recall is not None else None,
        "f1": round(f1, 6) if f1 is not None else None,
        "agreement_lines": agree, "total_lines": total,
        "agreement_pct": round(100.0 * agree / total, 4) if total else None,
        "note": ("SAP's own NM_SM_CLASS is compared against the brief's day-threshold rule. "
                 "Disagreement is reported, never reconciled away."),
    }


def pr_recommendations(F):
    """PR lines, quantity and value by priority, by week-of-cover and by plant,
    straight from the HANA engine; plus the detailed top-40 below-ROP lines."""
    pri = rows_to_dicts(F["misc"]["columns_pr_priority"], F["misc"]["pr_priority"])
    wk = rows_to_dicts(F["misc"]["columns_pr_week"], F["misc"]["pr_week"])
    pl = rows_to_dicts(F["misc"]["columns_pr_plant"], F["misc"]["pr_plant"])
    detail = rows_to_dicts(F["pr_detail"]["columns"], F["pr_detail"]["rows"])
    return {
        "by_priority": pri,
        "by_weeks_of_cover": wk,
        "by_plant": pl,
        "detail_top_by_value_at_risk": detail,
        "detail_note": F["pr_detail"]["note"],
        "totals": {
            "lines": sum(r["lines"] for r in pri),
            "qty": sum(r["pr_qty"] for r in pri),
            "value_inr": round(sum(r["pr_val_inr"] for r in pri), 2),
            "shutdown_lines": sum(r["lines"] for r in pri if r["shutdown_flag"] == "Y"),
            "shutdown_value_inr": round(sum(r["pr_val_inr"] for r in pri if r["shutdown_flag"] == "Y"), 2),
            "raise_immediately_lines": next((r["lines"] for r in wk if r["weeks_of_cover_bucket"] == "0"), None),
            "raise_immediately_value_inr": next(
                (round(r["pr_val_inr"], 2) for r in wk if r["weeks_of_cover_bucket"] == "0"), None),
        },
        "rules_applied": {
            "trigger": rules.UNDERSTOCK_RULE,
            "quantity": "recommended qty = MAX - stock - open PR, rounded up to MIN_ORDER_QTY and ORDER_MULTIPLE",
            "timing": "weeks of cover = (stock - safety stock) / weekly demand; bucket 0 = raise now",
            "priority": "CRITICAL when stock < safety stock or criticality=VITAL; HIGH on shutdown flag; else MEDIUM",
        },
    }


def duplicates(F):
    d = F["misc"]["duplicates"]
    likely = d["exact_desc_within_group_1.00"]
    review = d["base_token_within_group_0.60"]
    return {
        "method": d["method"],
        "thresholds": {"review": rules.DUPLICATE_REVIEW_THRESHOLD, "likely": rules.DUPLICATE_LIKELY_THRESHOLD},
        "likely_duplicates_ge_080": likely,
        "review_candidates_ge_060": review,
        "clusters_total": likely["clusters"] + review["clusters"],
        "redundant_lines_total": likely["redundant"] + review["redundant"],
        "releasable_value_inr": None,
        "releasable_value_uncomputable_reason": (
            "Releasable value needs the retained-versus-released decision per cluster, which is a "
            "planner judgement not present in VEDANTA_POC. The curated "
            "DUPLICATE_SKU_OPPORTUNITY_INR figure is reported alongside, clearly labelled CURATED."
        ),
    }


def lead_time(F):
    lt = F["misc"]["lead_time"]
    pm = plant_mc(F)
    lines = sum(r["lines"] for r in pm)
    weighted = sum(r["avg_lt_days"] * r["lines"] for r in pm) / max(lines, 1)
    return {
        "rule": rules.LEAD_TIME_RULE,
        "median_pr_to_po_days": rules.MEDIAN_PR_TO_PO_DAYS,
        "lines": lt["lines"],
        "avg_days": lt["avg_days"],
        "median_days": lt["median_days"],
        "line_weighted_avg_days_from_engine": round(weighted, 3),
        "by_plant_class": [{"plant": r["plant"], "movement_class": r["mc"], "avg_lt_days": r["avg_lt_days"]}
                           for r in pm],
    }
