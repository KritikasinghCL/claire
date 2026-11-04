#!/usr/bin/env python3
"""Validate the step-1 data contract.

Everything downstream — the ContextFlow forecast, the KPI scorecard, the
dashboard — reads step1_data.json and the aggregates. This script fails the
build if any of that drifts from what step 1 actually measured against
SAP HANA, so a silent change cannot reach the dashboard as a wrong number.

Run:  python3 tools/validate_step1.py
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STEP1 = ROOT / "step1"
AGG = STEP1 / "aggregates"

MONTHS = [f"{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
PLANTS = [f"HZL_DEMO_0{i}" for i in range(1, 7)]

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))
        failures.append(label)


def load(path: pathlib.Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


print("step-1 data contract")
print("=" * 60)

# --- every artefact exists and is valid JSON -------------------------------
print("\nfiles")
expected = [
    STEP1 / "step1_data.json",
    STEP1 / "reconciliation.md",
    STEP1 / "sql" / "step1_demand_material_plant_month.sql",
    STEP1 / "sql" / "step1_reconciliation.sql",
    AGG / "plant_month.json",
    AGG / "type_group_month.json",
    AGG / "criticality_month.json",
    AGG / "top_material_plant_series.json",
]
for path in expected:
    check(f"{path.relative_to(ROOT)} exists", path.is_file())

if failures:
    print(f"\n{len(failures)} missing file(s); cannot continue.")
    sys.exit(1)

for path in [p for p in expected if p.suffix == ".json"]:
    try:
        load(path)
        check(f"{path.name} parses", True)
    except json.JSONDecodeError as exc:  # pragma: no cover - the point is to fail loudly
        check(f"{path.name} parses", False, str(exc))

data = load(STEP1 / "step1_data.json")

# --- scope is the one the brief fixed --------------------------------------
print("\nscope")
scope = data["scope"]
check("material types are ZSPR + ZSPN", sorted(scope["material_type_in"]) == ["ZSPN", "ZSPR"])
check("backcast rows excluded", scope["is_backcast_period"] == "N")
check("period is Jan-2024..Dec-2025",
      (scope["period_from"], scope["period_to"]) == ("2024-01-01", "2025-12-31"))
check("as-of is 2025-12-31", scope["as_of_date"] == "2025-12-31")
check("fiscal year is Apr-Mar", scope["fiscal_year"] == "Apr-Mar")
check("default measure is QTY, not INR", scope["default_measure"].startswith("QTY"))

# --- demand identity: net = issues - returns -------------------------------
print("\ndemand")
totals = data["demand_definition"]["in_scope_movement_totals"]
net = round(totals["261"]["qty"] - totals["262"]["qty"], 2)
check("NET_DEMAND == 261 qty - 262 qty",
      net == totals["net_demand_qty_total"],
      f"{net} != {totals['net_demand_qty_total']}")
check("grain is Material x Plant x Month",
      data["demand_definition"]["grain"] == "MATERIAL_ID x PLANT_ID x POSTING_MONTH")
check("101/102/701/702 are excluded from demand",
      set(totals["other_types_present_not_demand"]) == {"101", "102", "701", "702"})

# --- reconciliation arithmetic must hold ------------------------------------
print("\nreconciliation")
items = {item["id"]: item for item in data["reconciliation"]["items"]}
check("R1..R4 all present", {"R1", "R1b", "R1c", "R2", "R3", "R4"} <= set(items))

for rid in ("R1", "R1b", "R1c", "R4"):
    item = items[rid]
    expect = round(item["curated"] - item["raw"], 2)
    check(f"{rid} diff == curated - raw", expect == round(item["diff"], 2),
          f"{expect} != {item['diff']}")

r1 = items["R1"]
by_plant = sum(p["curated_qty"] for p in r1["by_plant"])
check("R1 plant quantities sum to the total",
      round(by_plant, 1) == round(r1["curated"], 1),
      f"{by_plant} != {r1['curated']}")
check("R1 covers all six physical plants",
      sorted(p["plant"] for p in r1["by_plant"]) == PLANTS)
check("R1 excludes the ALL_PLANTS rollup",
      all(p["plant"] != "ALL_PLANTS" for p in r1["by_plant"]))

r3 = items["R3"]
for cls in r3["by_class"]:
    check(f"R3 {cls['class']} diff == curated - raw",
          cls["curated"] - cls["raw"] == cls["diff"])
check("R3 reclassification nets to zero (lines move between classes, none vanish)",
      sum(c["diff"] for c in r3["by_class"]) == 0)
check("R3 curated classes total 34,717 lines",
      sum(c["curated"] for c in r3["by_class"]) == 34717)
check("R3 raw classes total 34,717 lines",
      sum(c["raw"] for c in r3["by_class"]) == 34717)

r4 = items["R4"]
check("R4 tolerance buckets total 34,717 lines",
      r4["lines_within_20pct_tolerance"] + r4["lines_outside_20pct_tolerance"] == 34717)

summary = data["reconciliation"]["summary"]
statuses = [i["status"].split(" ")[0] for i in items.values()]
check("summary MATCH count agrees with the items",
      statuses.count("MATCH") == summary["match"])
check("summary DIFFERENCE count agrees with the items",
      statuses.count("DIFFERENCE") == summary["difference"])

# --- a difference must never be reported without its cause -------------------
print("\ndisclosure")
for rid, item in items.items():
    if item["status"].startswith("DIFFERENCE"):
        check(f"{rid} states a root cause", bool(item.get("root_cause", "").strip()))
        check(f"{rid} states a resolution", bool(item.get("resolution", "").strip()))

check("every warning carries a code and a message",
      all(w.get("code") and w.get("message") for w in data["warnings"]))
check("every uncomputable item states its reason",
      all(u.get("reason", "").strip() for u in data["uncomputable"]))
check("the known rule mismatches are both flagged",
      {"MOVEMENT_CLASS_RULE_MISMATCH", "ROP_BASIS_MISMATCH"}
      <= {w["code"] for w in data["warnings"]})
check("the ALL_PLANTS double-count trap is flagged",
      "ALL_PLANTS_ROLLUP_ROW" in {w["code"] for w in data["warnings"]})

# --- aggregates are complete and on the stated grain -------------------------
print("\naggregates")
plant_month = load(AGG / "plant_month.json")
rows = plant_month["rows"]
check("plant_month has 6 plants x 24 months = 144 rows", len(rows) == 144, str(len(rows)))
check("plant_month covers every plant-month exactly once",
      sorted((r[0], r[1]) for r in rows) == sorted((p, m) for p in PLANTS for m in MONTHS))
check("plant_month excludes the ALL_PLANTS rollup",
      all(r[0] != "ALL_PLANTS" for r in rows))
bad_net = [r for r in rows if round(r[2] - r[3], 3) != round(r[4], 3)]
check("plant_month NET_DEMAND == 261 - 262 on every row",
      not bad_net, f"{len(bad_net)} row(s) disagree")

for name in ("type_group_month.json", "criticality_month.json"):
    agg = load(AGG / name)
    check(f"{name} months[] is the full 24-month window", agg["months"] == MONTHS)
    wrong = [k for k, v in agg["series"].items() if len(v) != 24]
    check(f"{name} every series aligns to months[]", not wrong, f"misaligned: {wrong}")

crit = load(AGG / "criticality_month.json")
check("criticality covers VITAL/ESSENTIAL/DESIRABLE",
      sorted(crit["series"]) == ["DESIRABLE", "ESSENTIAL", "VITAL"])
check("service levels are 98/95/90",
      crit["service_level_target_pct"] == {"VITAL": 98, "ESSENTIAL": 95, "DESIRABLE": 90})

tms = load(AGG / "top_material_plant_series.json")
check("top series carries 30 material-plant pairs", len(tms["rows"]) == 30)
check("top series months are inside the window",
      all(m in MONTHS for r in tms["rows"] for m in r["series"]))
check("top series months_with_demand matches the series length",
      all(r["months_with_demand"] == len(r["series"]) for r in tms["rows"]))
check("top series is sorted by 24-month total, descending",
      [r["total_24m"] for r in tms["rows"]]
      == sorted((r["total_24m"] for r in tms["rows"]), reverse=True))
check("sparse months are documented as gaps, not zeros",
      "not a zero" in tms.get("note", "").lower())

# --- the aggregate index must describe the files that exist -------------------
print("\nindex")
for name, entry in data["aggregates_index"].items():
    path = ROOT / entry["path"]
    check(f"index entry {name} points at a real file", path.is_file())

print("\n" + "=" * 60)
if failures:
    print(f"FAILED — {len(failures)} of {checks} checks:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)

print(f"OK — {checks} checks passed.")
