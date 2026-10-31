# Run the complete analysis in the existing Jupyter environment


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


# %% Execute all stages, saving every result and the execution manifest.

OUT = run('all')


# %% Inspect the principal results.

for filename in ['historical_scores.csv','tobit_coefficients.csv','ml_prediction_summary.csv','simulation_summary.csv','pooled_comparison.csv']:
    print('\n'+filename)
    print(pd.read_csv(OUT/filename).head(10).to_string(index=False))


# %% Run the full case audit against this output folder.

import subprocess
subprocess.run([sys.executable,'-B','-m','tests.verify_case','--run-dir',str(OUT)],cwd=ROOT,check=True)
