# Compare existing and proposed DRT services


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


# %% Convert daily simulation results to monthly proposed-service indicators.

OUT = run('bridge')
print(pd.read_csv(OUT/'scenario_model_data.csv').to_string(index=False))


# %% Recalculate group and meta frontiers using the 200 existing and eight proposed services.

OUT = run('compare')
comparison = pd.read_csv(OUT/'pooled_comparison.csv')
print(comparison[comparison.Source=='simulated'].to_string(index=False))


# %% Check the explicit statuses of fixed-reference replication scores. Infeasible targets are preserved as failures, not treated as efficiency estimates.

rep = pd.read_csv(OUT/'scenario_replication_scores.csv')
print(rep.status.value_counts())
print('All saved files:',OUT)
