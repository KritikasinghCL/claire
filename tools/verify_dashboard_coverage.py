#!/usr/bin/env python3
"""S-8 gate: does step3/dashboard_data.json actually COVER the 12 sections and 13 KPIs?

tools/validate_step3.py proves the KEYS exist. This proves the CONTENT behind them is
real: every section carries cards and content blocks, cards carry the labels the brief
names, every KPI has a numeric actual or an explicit uncomputable reason plus a basis,
no container is a hollow stub, and the reconciliation / warning / provenance panels are
populated.

Usage:  python3 tools/verify_dashboard_coverage.py [path/to/dashboard_data.json]
Exit 0 = PASS, 1 = blocking gap found. Writes verify_out/coverage.txt.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'step3', 'dashboard_data.json')
OUT = os.path.join(ROOT, 'verify_out', 'coverage.txt')

if not os.path.exists(ART):
    print(f'FATAL: artefact not found: {ART}')
    print('step3/dashboard_data.json is produced by S-8 (inv-step3-kpis). '
          'This gate cannot run until it is committed.')
    sys.exit(2)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
d = json.load(open(ART, encoding='utf-8'))
L = []
P = L.append
BLOCK, WARN = [], []

S = d.get('sections', {})
K = d.get('kpis', [])

# ---------------------------------------------------------------- 1. sections
SECTIONS = ['kpi_scorecard', 'demand_forecast', 'inventory_health', 'over_understock',
            'nm_sm', 'shutdown_maintenance', 'pr_recommendations', 'mrp_rop',
            'duplicate_sku', 'plan_vs_actual', 'data_sources', 'raia']

P('=' * 78)
P('A. SECTION COVERAGE - 12 required')
P('=' * 78)
P(f'sections present: {len(S)}')
for sid in SECTIONS:
    s = S.get(sid)
    if not s:
        BLOCK.append(f'section absent: {sid}')
        P(f'  MISSING  {sid}')
        continue
    counters = {'rows': 0, 'unc': 0}

    def walk(o):
        if isinstance(o, dict):
            if o.get('status') == 'UNCOMPUTABLE':
                counters['unc'] += 1
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            if o and isinstance(o[0], dict):
                counters['rows'] += len(o)
            for v in o:
                walk(v)

    charts = 0
    for k, v in s.items():
        if k in ('id', 'title', 'description'):
            continue
        walk(v)
        if isinstance(v, (list, dict)) and v:
            charts += 1
    cards = len(s.get('cards', []))
    P(f'  OK       {sid:22s} cards={cards:<3d} blocks={charts:<3d} '
      f'datarows={counters["rows"]:<5d} uncomputable={counters["unc"]}')
    if charts == 0:
        BLOCK.append(f'{sid}: no content blocks beyond title/description')
    if sid != 'raia' and cards == 0:
        BLOCK.append(f'{sid}: zero cards')

# ------------------------------------------------- 2. cards named by the brief
WANT = {
    'kpi_scorecard': ['gross inv', 'reduction opportunity', 'non-operating', 'turnover',
                      'vital', 'pr'],
    'demand_forecast': ['3-month', '6-month', '9-month', '12-month', 'last 12'],
    'inventory_health': ['non-operating', 'turnover'],
    'over_understock': ['overstock', 'no demand', 'understock', 'vital'],
    'nm_sm': ['at risk', 'value', 'precision', 'recall', 'f1'],
    'pr_recommendations': ['recommended', 'raise', 'priority', 'shutdown'],
    'mrp_rop': ['lines', 'vb', 'pd', 'increase', 'decrease'],
    'duplicate_sku': ['clusters', 'stock', 'releasable', 'review'],
    'plan_vs_actual': ['plan', 'po', 'gr', 'variance'],
    'shutdown_maintenance': ['history', 'projected', 'need', 'maintenance'],
    'data_sources': ['as-of', 'run', 'lines', 'tables', 'columns', 'sap'],
}
P('')
P('=' * 78)
P('B. CARDS THE BRIEF NAMES, PER SECTION')
P('=' * 78)
for sid, want in WANT.items():
    cards = S.get(sid, {}).get('cards', [])
    blob = ' | '.join((c.get('label') or '') for c in cards).lower()
    miss = [w for w in want if w not in blob]
    P(f'\n[{sid}]  {len(cards)} cards')
    for c in cards:
        v = c.get('value')
        vs = 'UNCOMPUTABLE' if v is None else f'{v}'
        P(f'    - {(c.get("label") or "?"):38s} = {vs:>20s}  '
          f'{c.get("unit", ""):10s} {c.get("status", "")}')
    if miss:
        WARN.append(f'{sid}: brief card terms not in labels: {miss}')
        P(f'    !! not found: {miss}')

# ------------------------------------------------------------------- 3. KPIs
CODES = ['GROSS_INVENTORY_REDUCTION', 'NMI', 'SMI', 'OBSOLETE_REDUCTION', 'QTY_ACCURACY',
         'INVENTORY_FORECAST_ACCURACY', 'NM_SM_F1', 'VITAL_AVAILABILITY', 'ROP_COVERAGE',
         'DUPLICATE_SKU', 'PR_DATE_ADHERENCE', 'PR_COUNT_YOY', 'NOM_DAYS']
P('')
P('=' * 78)
P('C. THE 13 KPIs - target / actual / variance / status')
P('=' * 78)
have = {k.get('code'): k for k in K}
P(f'kpis present: {len(K)}')
P(f'{"CODE":32s} {"TARGET":>12s} {"ACTUAL":>14s} {"VARIANCE":>12s}  STATUS')
for c in CODES:
    k = have.get(c)
    if not k:
        BLOCK.append(f'KPI absent: {c}')
        P(f'{c:32s}  *** MISSING ***')
        continue
    t, a, v, st = k.get('target'), k.get('actual'), k.get('variance'), k.get('status')
    P(f'{c:32s} {str(t):>12s} {str(a):>14s} {str(v):>12s}  {st}')
    if a is None and not k.get('uncomputable_reason'):
        BLOCK.append(f'KPI {c}: null actual with no reason')
    if a is None and st != 'UNCOMPUTABLE':
        BLOCK.append(f'KPI {c}: null actual but status {st}')
    if not k.get('basis'):
        BLOCK.append(f'KPI {c}: no basis')
extra = [c for c in have if c not in CODES]
if extra:
    WARN.append(f'unexpected extra KPI codes: {extra}')

by_status = {}
for k in K:
    by_status[k.get('status')] = by_status.get(k.get('status'), 0) + 1
P('')
P(f'status mix: {by_status}')
P('UNCOMPUTABLE KPIs and why:')
for k in K:
    if k.get('actual') is None:
        P(f'  - {k.get("code")}: {(k.get("uncomputable_reason") or "")[:150]}')

# -------------------------------------------------- 4. hollow-stub detection
P('')
P('=' * 78)
P('D. HOLLOW BLOCKS (key present, no content behind it)')
P('=' * 78)
hollow = []


def scan(o, path):
    if isinstance(o, dict):
        if not o:
            hollow.append(path)
        else:
            for k, v in o.items():
                scan(v, f'{path}.{k}')
    elif isinstance(o, list):
        if not o:
            hollow.append(path)


for sid in SECTIONS:
    scan(S.get(sid, {}), sid)
if hollow:
    for h in hollow:
        P(f'  EMPTY  {h}')
    WARN.append(f'{len(hollow)} empty containers')
else:
    P('  none - every container carries content')

# ------------------------------------------------- 5. reconciliation + warnings
P('')
P('=' * 78)
P('E. RECONCILIATION / WARNINGS / PROVENANCE')
P('=' * 78)
R = d.get('reconciliation', {}).get('items', [])
P(f'reconciliation items: {len(R)}')
for it in R:
    P(f'  {str(it.get("item"))[:46]:46s} curated={str(it.get("curated")):>18s} '
      f'raw={str(it.get("raw")):>18s} diff={str(it.get("diff")):>14s} '
      f'{str(it.get("diff_pct")):>9s}%  {it.get("status")}')
if len(R) < 6:
    BLOCK.append(f'reconciliation has only {len(R)} items, brief wants >=6')

W = d.get('warnings', [])
P('')
P(f'warning banners: {len(W)}')
for w in W:
    P(f'  [{w.get("severity"):8s}] {w.get("code")}: {str(w.get("message"))[:120]}')
if len(W) < 5:
    BLOCK.append(f'only {len(W)} warnings')

cf = d.get('meta', {}).get('contextflow', {})
P('')
P(f'ContextFlow model : {cf.get("model_name")}')
P(f'experiment_id     : {cf.get("experiment_id")}')
P(f'run_timestamp_utc : {cf.get("run_timestamp_utc")}')
P(f'as_of_date        : {d.get("meta", {}).get("as_of_date")}')
P(f'default measure   : {d.get("meta", {}).get("measure", {}).get("default")}')
for fld in ('model_name', 'experiment_id', 'run_timestamp_utc'):
    if not cf.get(fld):
        BLOCK.append(f'meta.contextflow.{fld} empty')
if d.get('meta', {}).get('measure', {}).get('default') != 'QTY':
    BLOCK.append('default measure is not QTY')

# ------------------------------------------------------------------ verdict
P('')
P('=' * 78)
P(f'BLOCKING: {len(BLOCK)}')
for b in BLOCK:
    P(f'  X {b}')
P(f'ADVISORY: {len(WARN)}')
for w in WARN:
    P(f'  ! {w}')
P('VERDICT: ' + ('FAIL' if BLOCK else 'PASS'))
P('=' * 78)

open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
sys.exit(1 if BLOCK else 0)
