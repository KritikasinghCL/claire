"""Master rules for the Inventory Control Center engine (step 3).

Every constant here comes from the goal brief, not from the data. Nothing in this
module reads a file; it exists so the rules are stated once and quoted verbatim in
the Data Sources and RAIA sections of dashboard_data.json.
"""

AS_OF = "2025-12-31"
PERIOD_FROM = "2024-01"
PERIOD_TO = "2025-12"
MONTHS = [f"{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
SCOPE_MATERIAL_TYPES = ["ZSPR", "ZSPN"]
IS_BACKCAST_PERIOD = "N"
DEFAULT_MEASURE = "QTY"
VALUE_MEASURE = "INR"
FISCAL_YEAR = "Apr-Mar"

# Movement classes, by days since last 261 consumption.
MOVEMENT_CLASS_RULES = [
    {"klass": "ACTIVE", "rule": "days_since_last_consumption <= 90", "max_days": 90},
    {"klass": "SLOW_MOVING", "rule": "90 < days_since_last_consumption <= 180", "max_days": 180},
    {"klass": "NON_MOVING", "rule": "180 < days_since_last_consumption <= 365", "max_days": 365},
    {"klass": "OBSOLETE", "rule": "days_since_last_consumption > 365", "max_days": None},
    {"klass": "NON_MOVING", "rule": "never issued (no 261 ever) => NON_MOVING, not OBSOLETE", "max_days": None},
]

# Service levels and their normal-distribution z values.
SERVICE_LEVEL = {"VITAL": 98.0, "ESSENTIAL": 95.0, "DESIRABLE": 90.0}
Z = {"VITAL": 2.054, "ESSENTIAL": 1.645, "DESIRABLE": 1.282}

LEAD_TIME_RULE = "MAX(PLANNED_DELIVERY_DAYS, median actual PO->GR per material) + median PR->PO"
MEDIAN_PR_TO_PO_DAYS = 24
SAFETY_STOCK_RULE = "SS = z(criticality) * sigma_monthly_net_demand * sqrt(LT_days / 30.44)"
ROP_RULE = "ROP = lead-time demand + safety stock = (net 12m demand / 365) * LT + SS"
MAX_RULE = "MAX = ROP + 3-month forecast"
OVERSTOCK_RULE = "overstock when stock > max(MAX, 12-month forecast)"
UNDERSTOCK_RULE = "understock when stock < ROP"
NM_SM_HORIZON_DAYS = 90
HOLDING_COST_PCT = 0.08
DUPLICATE_REVIEW_THRESHOLD = 0.60
DUPLICATE_LIKELY_THRESHOLD = 0.80
ROP_FLAG_TOLERANCE = 0.20

# 13 KPIs: code -> (label, target, unit, direction, section)
KPI_TARGETS = {
    "GROSS_INVENTORY_REDUCTION": ("Gross inventory reduction", 10.0, "%", "higher_is_better"),
    "NMI": ("Non-moving inventory reduction (NMI)", 10.0, "%", "higher_is_better"),
    "SMI": ("Slow-moving inventory reduction (SMI)", 20.0, "%", "higher_is_better"),
    "OBSOLETE_REDUCTION": ("Obsolete inventory reduction", 5.0, "%", "higher_is_better"),
    "QTY_ACCURACY": ("Quantity forecast accuracy (1 - WAPE)", 90.0, "%", "higher_is_better"),
    "INVENTORY_FORECAST_ACCURACY": ("Inventory forecast accuracy", 90.0, "%", "higher_is_better"),
    "NM_SM_F1": ("NM/SM classification F1", 0.90, "ratio", "higher_is_better"),
    "VITAL_AVAILABILITY": ("Critical (VITAL) spares availability", 95.0, "%", "higher_is_better"),
    "ROP_COVERAGE": ("ROP coverage of in-scope lines", 100.0, "%", "higher_is_better"),
    "DUPLICATE_SKU": ("Duplicate SKU clusters identified", 0.0, "clusters", "informational"),
    "PR_DATE_ADHERENCE": ("PR date adherence", 95.0, "%", "higher_is_better"),
    "PR_COUNT_YOY": ("PR count YoY change", 10.0, "%", "lower_is_better"),
    "NOM_DAYS": ("Non-Operating-Material days", 90.0, "days", "lower_is_better"),
}

SECTIONS = [
    ("kpi_scorecard", "KPI Scorecard"),
    ("demand_forecast", "Demand Forecast"),
    ("inventory_health", "Inventory Health"),
    ("over_understock", "Over / Understock"),
    ("nm_sm", "Non-Moving / Slow-Moving"),
    ("shutdown_maintenance", "Shutdown & Maintenance"),
    ("pr_recommendations", "PR Recommendations"),
    ("mrp_rop", "MRP / ROP"),
    ("duplicate_sku", "Duplicate SKU"),
    ("plan_vs_actual", "Plan vs Actual"),
    ("data_sources", "Data Sources"),
    ("raia", "RAIA"),
]


def status_for(actual, target, direction, amber_band=0.10):
    """GREEN / AMBER / RED against a target. UNCOMPUTABLE actuals stay UNCOMPUTABLE."""
    if actual is None:
        return "UNCOMPUTABLE"
    if direction == "informational":
        return "INFO"
    if direction == "higher_is_better":
        if actual >= target:
            return "GREEN"
        return "AMBER" if actual >= target * (1 - amber_band) else "RED"
    if actual <= target:
        return "GREEN"
    return "AMBER" if actual <= target * (1 + amber_band) else "RED"


def variance(actual, target):
    return None if actual is None else round(actual - target, 4)
