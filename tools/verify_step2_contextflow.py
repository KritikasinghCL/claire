#!/usr/bin/env python3
"""Gate the step-2 ContextFlow evidence.

This does NOT trust step2/contextflow_evidence.json as prose. It re-derives
every arithmetic claim in it and enforces the stewardship rule the cell works
to: a DEFECT cannot be published without evidence and a consequence, and an
accuracy figure cannot be published without the candidate it belongs to.

Run:  python3 tools/verify_step2_contextflow.py
Exit: 0 all checks pass, 1 otherwise.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "step2" / "contextflow_evidence.json"

checks = 0
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}: {detail}" if detail else label)


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def main() -> int:
    if not EVIDENCE.exists():
        print(f"FAIL — {EVIDENCE} is missing", file=sys.stderr)
        return 1
    ev = json.loads(EVIDENCE.read_text())

    # ---- the deliverable this ticket was meant to verify -------------------
    ds = ev["deliverable_status"]
    check(
        "step2_forecast.json status is stated, not assumed",
        ds["step2_forecast_json"] in {"ABSENT", "PRESENT"},
        f"got {ds['step2_forecast_json']!r}",
    )
    check(
        "an ABSENT deliverable records where it was searched for",
        ds["step2_forecast_json"] != "ABSENT" or len(ds.get("searched", [])) >= 2,
    )

    A = ev["experiment_A_authoritative"]
    lb = A["full_leaderboard_rmse"]
    win = A["winner_verbatim"]
    diag = A["holdout_diagnostics_verbatim"]
    V = ev["validations_required_by_the_brief"]

    # ---- the leaderboard is internally consistent -------------------------
    check("leaderboard has 11 candidates", len(lb) == A["candidates_trained"] == 11)
    check(
        "ranks are 1..n with no gaps",
        [c["rank"] for c in lb] == list(range(1, len(lb) + 1)),
    )
    check(
        "leaderboard is sorted ascending by RMSE (lower is better)",
        all(lb[i]["rmse"] <= lb[i + 1]["rmse"] for i in range(len(lb) - 1)),
    )
    check(
        "bestCandidateId is the rank-1 row — ContextFlow chose it, we did not",
        win["bestCandidateId"] == lb[0]["id"] == "ExtraTreesMSE",
    )
    check(
        "the winner's quoted RMSE equals its leaderboard RMSE",
        close(win["rmse_holdout"], lb[0]["rmse"]),
        f"{win['rmse_holdout']} vs {lb[0]['rmse']}",
    )
    check(
        "the deployed endpoint serves the rank-1 candidate",
        A["endpoint"]["candidateId"] == win["bestCandidateId"],
    )
    check(
        "the 'why it won' statement cites the real runner-up margin",
        f"{lb[1]['rmse']:.6f}" in A["why_it_ranked_first_verbatim"],
    )

    # ---- D2: the diagnostics block belongs to rank 2, and we say so -------
    check(
        "D2 is real: diagnostics RMSE matches rank 2, not the champion",
        close(diag["rmse"], lb[1]["rmse"]) and not close(diag["rmse"], lb[0]["rmse"]),
        f"diag {diag['rmse']} / rank1 {lb[0]['rmse']} / rank2 {lb[1]['rmse']}",
    )
    check(
        "D2 is real: diagnostics r2 matches rank 2 too",
        close(diag["r2"], lb[1]["r2"]),
    )
    check(
        "the diagnostics block carries the mismatch WARNING rather than hiding it",
        "WARNING" in diag and lb[1]["id"] in diag["WARNING"],
    )

    # ---- the three validations the brief demands --------------------------
    for key in ("task_is_regression_not_classification", "target_is_a_quantity",
                "model_chosen_by_contextflow_not_by_us"):
        check(f"brief validation '{key}' passes", V[key]["verdict"] == "PASS")
        check(f"brief validation '{key}' cites evidence", len(V[key]["evidence"]) > 40)

    check(
        "problemType is regression on the dataset AND the endpoint",
        A["dataset"]["problemType"] == A["endpoint"]["problemType"] == "regression",
    )
    check(
        "the target column is the quantity, consistently",
        A["dataset"]["targetColumn"] == A["endpoint"]["targetColumn"] == "actual_qty",
    )

    # ---- D1: holdout is random, not the required 6-month time split -------
    check("D1 recorded as FAIL", V["six_month_holdout"]["verdict"] == "FAIL")
    check(
        "D1 evidence names the actual split strategy",
        A["dataset"]["splitStrategy"] == "deterministic_random_holdout",
    )
    check(
        "D1 holdout fraction and diagnostics row count agree with the dataset size",
        close(diag["rows"], A["dataset"]["rows"] * A["dataset"]["holdoutFraction"]),
        f"{diag['rows']} vs {A['dataset']['rows']}*{A['dataset']['holdoutFraction']}",
    )

    # ---- D3: MATERIAL_ID is not a feature ---------------------------------
    feats = A["dataset"]["featureColumns"]
    check("D3 is real: MATERIAL_ID is absent from featureColumns", "MATERIAL_ID" not in feats)
    check(
        "the endpoint's featureColumns match the dataset's",
        A["endpoint"].get("featureColumns", feats) == feats
        or "MATERIAL_ID" not in A["endpoint"].get("featureColumns", feats),
    )
    check(
        "D3 is evidenced empirically, not asserted",
        "1290.1533203125" in V["grain_material_x_plant_x_month"]["evidence"],
    )
    check(
        "every feature in featureImportance is a declared feature, and all are scored",
        {f["feature"] for f in A["featureImportance"]} == set(feats),
    )

    # ---- D4: the extrapolation test actually demonstrates the flattening --
    ex = {r["month"]: r["prediction"] for r in ev["extrapolation_test"]["results"]}
    check(
        "D4 is real: a month 73 years past training returns the same leaf as 2026-06",
        close(ex["2099-06"], ex["2026-06"]),
        f"2099-06 {ex['2099-06']} vs 2026-06 {ex['2026-06']}",
    )
    check(
        "D4 test includes at least one in-training month as a control",
        any(m.startswith(("2024-", "2025-")) for m in ex),
    )
    check(
        "the in-training control differs from the forward values (the model did learn something)",
        not close(ex["2024-06"], ex["2026-06"]),
    )

    # ---- D5: two live endpoints -------------------------------------------
    B = ev["experiment_B_second_run"]
    check("D5 is real: both experiments report in_service",
          A["endpoint"]["status"] == B["endpoint_status"] == "in_service")
    check("D5 is real: the two champions differ", B["bestCandidateId"] != win["bestCandidateId"])
    check(
        "the second experiment is genuinely worse on the same primary metric",
        B["winner_rmse"] > win["rmse_holdout"],
        f"{B['winner_rmse']} vs {win['rmse_holdout']}",
    )

    # ---- D6: the KPI arithmetic -------------------------------------------
    qa = V["qty_accuracy_kpi_1_minus_wape"]
    check(
        "Qty Accuracy is exactly 1 - WAPE, recomputed not copied",
        close(qa["value"], 1 - diag["wape"]),
        f"{qa['value']} vs {1 - diag['wape']}",
    )
    check("D6: Qty Accuracy is below the >90% target and is flagged RED",
          qa["value"] < 0.90 and qa["status"].startswith("RED"))

    # ---- MAPE must be labelled uncomputable, with the reason ---------------
    check(
        "MAPE is not published as a clean number — the zero-target reason is recorded",
        "UNCOMPUTABLE" in V["metrics_wape_mape_rmse"]["caveat_mape"],
    )

    # ---- HANA re-verification of the step-2 grain -------------------------
    hv = ev["hana_reverification_of_the_step2_grain"]
    check("every HANA claim was checked", len(hv["claims_checked"]) >= 7)
    check(
        "every HANA claim passed — a failure here invalidates the forecast input",
        all(c["verdict"].startswith("PASS") for c in hv["claims_checked"]),
        str([c["claim"] for c in hv["claims_checked"] if not c["verdict"].startswith("PASS")]),
    )
    extra = hv["additional_facts_for_step_3"]
    ho = extra["time_ordered_holdout_2025_07_to_2025_12"]
    check(
        "the correct time-ordered holdout share is arithmetically consistent",
        close(round(ho["rows"] / 30861 * 100, 2), ho["share_of_grain_pct"], 0.01),
        f"{round(ho['rows'] / 30861 * 100, 2)} vs {ho['share_of_grain_pct']}",
    )
    check(
        "zero and negative demand months are counted, not silently clipped",
        extra["cohort_month_rows_with_zero_net_demand"] > 0
        and extra["cohort_month_rows_with_negative_net_demand"] > 0,
    )

    # ---- the stewardship rule, as a test ----------------------------------
    verdict = ev["verdict"]
    check("the overall verdict is stated plainly", verdict["overall"].startswith("BLOCKED"))
    check("every blocking defect D1..D6 is listed", len(verdict["blocking_defects"]) == 6)
    for i in range(1, 7):
        check(
            f"defect D{i} is named in the verdict",
            any(d.startswith(f"D{i} ") for d in verdict["blocking_defects"]),
        )
    check("a BLOCKED verdict carries a recommended resolution",
          len(verdict["recommended_resolution"]) > 60)
    check("what is sound is recorded alongside what is broken",
          len(verdict["what_is_sound"]) >= 3)

    if failures:
        print(f"FAIL — {len(failures)} of {checks} checks failed:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"OK — {checks} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
