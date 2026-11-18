import json
from pathlib import Path
root = Path('/home/sxtr/Projects/Major Project-instinct-recovery')
for folder in sorted((root/'testbed/outputs').iterdir()):
    if not folder.is_dir():
        continue
    plan = folder/'dry_run_plan.json'
    man = folder/'run_manifest.json'
    if not plan.exists():
        continue
    p = json.loads(plan.read_text())
    m = json.loads(man.read_text()) if man.exists() else {}
    metrics = sorted(folder.glob('e*/metrics.json'))
    types = {}
    for f in metrics:
        data = json.loads(f.read_text())
        kind = data.get('rule_update_method', 'not_recorded')
        types[kind] = types.get(kind, 0)+1
    print(folder.name, 'planned_runs',len(p.get('runs',[])), 'metrics',len(metrics),'methods',types,'scenario',m.get('scenario_path'))
    if folder.name in ('ce01-smoke','rate-diag-p1'):
        print('  recorded plans',p.get('runs'))
for path in [root/'testbed/scenarios/switch_calibration_v2.json', root/'testbed/scenarios/smoke.json']:
    s = json.loads(path.read_text())
    print(path.name, 'events',len(s['events']), 'capacity_events',sum('capacity_mbps' in e for e in s['events']))
