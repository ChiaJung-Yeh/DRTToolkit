# Predict future DRT demand with the saved demand model


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


# %% Optional in the notebook: run the standalone hurdle Tweedie R script. If already run in RStudio, skip this cell.

run_r('03_Demand_Estimation.R')
print((OUT/'demand_summary.txt').read_text(encoding='utf-8',errors='replace'))


# %% Regenerate both complete demand forecasts using the saved model.

run('predict')
print(pd.read_csv(OUT/'ml_prediction_summary.csv').to_string(index=False))


# %% Inspect hourly forecasts and a sample of predicted OD demand.

print(pd.read_csv(OUT/'ml_hourly_200.csv').to_string(index=False))
print(pd.read_csv(OUT/'ml_demand_200.csv.gz',nrows=10).to_string(index=False))
