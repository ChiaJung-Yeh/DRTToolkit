# DRT operation simulation


from pathlib import Path
import sys
# Locate the toolkit from the working folder, its parents, or the configured fallback.
ROOT = next((p for p in [Path.cwd(), *Path.cwd().parents,
    Path(r'E:\On-demand Transport Service\Analysis\7_Toolkit')]
    if (p/'desktop_scripts/desktop_helpers.py').is_file()), None)
if ROOT is None: raise FileNotFoundError('Cannot locate the toolkit folder')
sys.path.insert(0, str(ROOT/'desktop_scripts'))
from desktop_helpers import check_environment, run, run_r, OUT
import pandas as pd
versions = check_environment()


# %% Inspect the eight scenarios. Complete notebook 04 first.

import json
cfg = json.loads((ROOT/'config/case_study.json').read_text(encoding='utf-8'))
print(pd.DataFrame(cfg['simulation']['scenarios']).to_string(index=False))
print('Replications per scenario:',cfg['simulation']['replications'])


# %% Simulate all scenarios using the road network and forecast demand. Source: drt_toolkit/simulation.py.

run('simulate')
summary = pd.read_csv(OUT/'simulation_summary.csv')
print(summary.to_string(index=False))


# %% Review passenger conservation and replications.

daily = pd.read_csv(OUT/'simulation_daily.csv')
assert (daily.requests == daily.served + daily.rejected).all()
print('Daily scenario-replication rows:',len(daily))
print(daily.groupby('ServiceID')[['requests','served','rejected','vkt_km']].mean().to_string())
