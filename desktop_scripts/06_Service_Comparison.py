# Compare existing and proposed DRT services


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


# %% Convert daily simulation results to monthly proposed-service indicators.

run('bridge')
print(pd.read_csv(OUT/'scenario_model_data.csv').to_string(index=False))


# %% Recalculate group and meta frontiers using the 200 existing and eight proposed services.

run('compare')
comparison = pd.read_csv(OUT/'pooled_comparison.csv')
print(comparison[comparison.Source=='simulated'].to_string(index=False))


# %% Check the explicit statuses of fixed-reference replication scores. Infeasible targets are preserved as failures, not treated as efficiency estimates.

rep = pd.read_csv(OUT/'scenario_replication_scores.csv')
print(rep.status.value_counts())
print('All saved files:',OUT)
