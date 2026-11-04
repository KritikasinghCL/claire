"""Load every step-3 input fact. No computation here, no defaults, no invention.

Inputs:
  step1/step1_data.json          profile, reconciliation, warnings  (Arjun, step 1)
  step2/contextflow_evidence.json  ContextFlow model evidence        (Omar/Maya, step 2)
  step3/facts/engine_full_lt.json  HANA engine aggregates, full lead-time rule
  step3/facts/plant_mc.json        HANA engine aggregates, planned-only lead time
  step3/facts/misc.json            demand, PR, duplicates, NM/SM confusion, plan vs actual
  step3/facts/pr_detail.json       top below-ROP lines
  step3/facts/context.json         KPI monthly series, seasonality, shutdown, SAP mapping
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"required input missing: {rel}. Step 3 does not fabricate inputs; "
            f"produce it first or the affected sections are UNCOMPUTABLE."
        )
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_all():
    bundle = {
        "step1": _load("step1/step1_data.json"),
        "engine": _load("step3/facts/engine_full_lt.json"),
        "plant_mc_planned": _load("step3/facts/plant_mc.json"),
        "misc": _load("step3/facts/misc.json"),
        "pr_detail": _load("step3/facts/pr_detail.json"),
        "context": _load("step3/facts/context.json"),
        "extra": _load("step3/facts/step3_extra.json"),
    }
    # step2_forecast.json was never produced (S-3 blocked). The ContextFlow evidence
    # file is what exists; record which of the two we actually read.
    forecast_path = os.path.join(ROOT, "step2/step2_forecast.json")
    if os.path.exists(forecast_path):
        bundle["step2"] = _load("step2/step2_forecast.json")
        bundle["step2_source"] = "step2/step2_forecast.json"
    else:
        bundle["step2"] = _load("step2/contextflow_evidence.json")
        bundle["step2_source"] = "step2/contextflow_evidence.json"
        bundle["step2_missing"] = (
            "step2_forecast.json does not exist in the workspace or on the remote. "
            "S-3 is blocked. The ContextFlow model evidence file is used instead, so "
            "model identity and holdout accuracy are available but forward horizon "
            "quantities are not."
        )
    return bundle


def rows_to_dicts(cols, rows):
    return [dict(zip(cols, r)) for r in rows]
