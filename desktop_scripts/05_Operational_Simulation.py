# DRT operation simulation


from pathlib import Path
import sys
# Open notebooks within the toolkit; editor scripts can also locate their own folder.
_entry_dir = Path(__file__).resolve().parent if '__file__' in globals() else Path.cwd()
ROOT = next((p for p in [_entry_dir, *_entry_dir.parents, Path.cwd(), *Path.cwd().parents]
    if (p/'desktop_scripts/desktop_helpers.py').is_file()), None)
if ROOT is None:
    raise FileNotFoundError('Open the notebook from inside the toolkit folder, then rerun this cell.')
sys.path.insert(0, str(ROOT/'desktop_scripts'))
import importlib
import desktop_helpers
importlib.reload(desktop_helpers)
from desktop_helpers import check_environment, run, run_r, get_output_dir, get_study_config
import pandas as pd
versions = check_environment()
OUT = get_output_dir()


# %% Inspect the eight scenarios. Complete notebook 04 first.

import json
cfg = get_study_config()
print(pd.DataFrame(cfg['simulation']['scenarios']).to_string(index=False))
print('Replications per scenario:',cfg['simulation']['replications'])


# %% Simulate all scenarios using the road network and forecast demand. Source: drt_toolkit/simulation.py.

OUT = run('simulate')
summary = pd.read_csv(OUT/'simulation_summary.csv')
print(summary.to_string(index=False))


# %% Review passenger conservation and replications.

daily = pd.read_csv(OUT/'simulation_daily.csv')
assert (daily.requests == daily.served + daily.rejected).all()
print('Daily scenario-replication rows:',len(daily))
print(daily.groupby('ServiceID')[['requests','served','rejected','vkt_km']].mean().to_string())
