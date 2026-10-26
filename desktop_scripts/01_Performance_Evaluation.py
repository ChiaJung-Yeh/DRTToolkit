# Existing-service DDF performance evaluation


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


# %% Inspect the selected jurisdictions and service types.

historical = pd.read_csv(ROOT/'data/evaluation/Model Data.csv')
print(historical.groupby('COUNTYNAME').size())
print(historical.ServiceType.value_counts())


# %% Run validation and historical evaluation. The mathematical implementation is in drt_toolkit/evaluation.py.

run('validate', 'evaluate')
scores = pd.read_csv(OUT/'historical_scores.csv')
print(scores.head(12).to_string(index=False))


# %% Next: open 02_Performance_Drivers.R in RStudio and click Source. Alternatively run the same R file below.

run_r('02_Performance_Drivers.R')
print((OUT/'tobit_summary.txt').read_text(encoding='utf-8',errors='replace'))
