# Predict future DRT demand with the saved demand model


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


# %% Optional in the notebook: run the standalone hurdle Tweedie R script. If already run in RStudio, skip this cell.

OUT = run_r('03_Demand_Estimation.R')
print((OUT/'demand_summary.txt').read_text(encoding='utf-8',errors='replace'))


# %% Regenerate both complete demand forecasts using the saved model.

OUT = run('predict')
print(pd.read_csv(OUT/'ml_prediction_summary.csv').to_string(index=False))


# %% Inspect hourly forecasts and a sample of predicted OD demand.

case = str(get_study_config()['demand']['prediction_cases'][0])
print(pd.read_csv(OUT/f'ml_hourly_{case}.csv').to_string(index=False))
print(pd.read_csv(OUT/f'ml_demand_{case}.csv.gz',nrows=10).to_string(index=False))
