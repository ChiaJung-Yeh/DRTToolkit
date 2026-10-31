# Existing-service DDF performance evaluation


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


# %% Inspect the selected jurisdictions and service types.

historical = pd.read_csv(ROOT/get_study_config()['paths']['historical'], dtype={'ServiceID': str})
print(historical.groupby('Jurisdiction').size())
print(historical.ServiceType.value_counts())


# %% Run validation and historical evaluation. The mathematical implementation is in drt_toolkit/evaluation.py.

OUT = run('validate', 'evaluate')
scores = pd.read_csv(OUT/'historical_scores.csv')
print(scores.head(12).to_string(index=False))


# %% Next: open 02_Performance_Drivers.R in RStudio and click Source. Alternatively run the same R file below.

OUT = run_r('02_Performance_Drivers.R')
print((OUT/'tobit_summary.txt').read_text(encoding='utf-8',errors='replace'))
