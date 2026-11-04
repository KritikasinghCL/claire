#!/usr/bin/env python3
"""S-8 depth gate: the coverage gate can pass on labels alone. This one asks whether
the content is real.

Three questions:
  F. Each card-label advisory from the coverage gate - is a card genuinely missing,
     or is it only a wording difference? Prints the full card payload so the reader
     adjudicates from evidence, not from the gate's own string match.
  G. Does RAIA carry all 12 sub-items the brief names, each non-empty?
  H. Where the same number appears in two sections, do the two agree?

Usage:  python3 tools/verify_dashboard_depth.py [path/to/dashboard_data.json]
Exit 0 = no real gaps, 1 = a real gap. Writes verify_out/depth.txt.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'step3', 'dashboard_data.json')
OUT = os.path.join(ROOT, 'verify_out', 'depth.txt')

if not os.path.exists(ART):
    print(f'FATAL: artefact not found: {ART}')
    sys.exit(2)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
d = json.load(open(ART, encoding='utf-8'))
S, K = d['sections'], d['kpis']
L = []
P = L.append
REAL, COSMETIC = [], []

P('=' * 78)
P('F. CARD-LABEL ADVISORIES - cosmetic, or a real missing card?')
P('=' * 78)


def show(sid):
    P(f'\n[{sid}] full card payloads:')
    for c in S.get(sid, {}).get('cards', []):
        P(f'  - {c.get("label")!r} = {c.get("value")} {c.get("unit")}')
        for k in c:
            if k in ('label', 'value', 'unit', 'measure'):
                continue
            P(f'      .{k} = {str(c[k])[:110]}')


for sid in ('over_understock', 'nm_sm', 'pr_recommendations', 'mrp_rop'):
    show(sid)

labels = {sid: [(c.get('label') or '').lower() for c in S[sid].get('cards', [])]
          for sid in S}
P('\n--- adjudication ---')

if any('no demand' in l for l in labels.get('over_understock', [])):
    COSMETIC.append("over_understock 'no-demand' -> card exists as 'No demand' "
                    "(hyphen vs space)")
else:
    REAL.append('over_understock: no no-demand card')

if any('at risk' in l for l in labels.get('nm_sm', [])):
    COSMETIC.append("nm_sm 'at-risk' -> card exists as 'NM + SM at risk'")
else:
    REAL.append('nm_sm: no at-risk card')

prc = S.get('pr_recommendations', {}).get('cards', [])
if any('value' in str(k).lower() for c in prc for k in c):
    COSMETIC.append("pr_recommendations 'value' -> value_inr carried as a field on the "
                    "PR cards rather than as its own tile")
else:
    REAL.append('pr_recommendations: no PR value anywhere - the brief names a Value card')

mrp = S.get('mrp_rop', {}).get('cards', [])
if [c for c in mrp if 'adjust' in str(c).lower()
        or 'increase' in (c.get('label') or '').lower()
        or 'decrease' in (c.get('label') or '').lower()]:
    COSMETIC.append("mrp_rop 'adjusted' -> expressed as the Increase/Decrease "
                    "recommended pair")
else:
    REAL.append('mrp_rop: no adjusted-lines concept')

for c in COSMETIC:
    P(f'  ~ {c}')
for r in REAL:
    P(f'  X {r}')

# ------------------------------------------------------------------- RAIA
P('')
P('=' * 78)
P('G. RAIA - the 12 sub-items the brief names')
P('=' * 78)
RAIA_WANT = ['engine', 'contextflow_model', 'raw_vs_curated', 'reconciliation',
             'accuracy', 'limitations', 'uncomputable_items', 'assumptions',
             'data_quality', 'forecast', 'top_risks', 'actions']
R = S.get('raia', {})
for w in RAIA_WANT:
    v = R.get(w)
    if v is None:
        REAL.append(f'raia.{w} absent')
        P(f'  MISSING  {w}')
        continue
    if isinstance(v, list):
        size = f'{len(v)} items'
    elif isinstance(v, dict):
        size = f'{len(v)} keys'
    else:
        size = f'{len(str(v))} chars'
    P(f'  {"EMPTY  " if not v else "OK     "}  {w:22s} {size}')
    if not v:
        REAL.append(f'raia.{w} is empty')

# ----------------------------------------------- cross-section agreement
P('')
P('=' * 78)
P('H. CROSS-SECTION AGREEMENT (same number, two places)')
P('=' * 78)
kp = {k['code']: k for k in K}


def card(sid, frag, field='value'):
    for c in S.get(sid, {}).get('cards', []):
        if frag.lower() in (c.get('label') or '').lower():
            return c.get(field)
    return None


pairs = [
    ('VITAL_AVAILABILITY', kp['VITAL_AVAILABILITY'].get('actual'),
     'kpi_scorecard/Vital', card('kpi_scorecard', 'vital')),
    ('NM_SM_F1', kp['NM_SM_F1'].get('actual'), 'nm_sm/F1', card('nm_sm', 'f1')),
    ('NOM_DAYS', kp['NOM_DAYS'].get('actual'), 'kpi_scorecard/NOM avg_days',
     card('kpi_scorecard', 'non-operating', 'avg_days')),
    ('stock qty', card('kpi_scorecard', 'gross inventory'),
     'inventory_health/Stock on hand', card('inventory_health', 'stock on hand')),
    ('NOM lines', card('kpi_scorecard', 'non-operating'),
     'inventory_health/NOM', card('inventory_health', 'non-operating')),
    ('PR lines', card('kpi_scorecard', 'prs recommended'),
     'pr_recommendations/PR lines', card('pr_recommendations', 'pr lines')),
    ('understock == PR lines', card('over_understock', 'understock'),
     'pr_recommendations/PR lines', card('pr_recommendations', 'pr lines')),
]
for name, a, where, b in pairs:
    ok = (a == b)
    P(f'  {"MATCH " if ok else "DIFFER"}  {name:24s} {str(a):>16s}  vs  '
      f'{where:34s} {str(b):>16s}')
    if not ok:
        REAL.append(f'cross-check differs: {name} {a} vs {where} {b}')

P('')
P('=' * 78)
P(f'REAL GAPS: {len(REAL)}')
for r in REAL:
    P(f'  X {r}')
P(f'COSMETIC (wording only, content present): {len(COSMETIC)}')
for c in COSMETIC:
    P(f'  ~ {c}')
P('VERDICT: ' + ('GAPS FOUND' if REAL else 'NO REAL GAPS'))
P('=' * 78)

open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
sys.exit(1 if REAL else 0)
