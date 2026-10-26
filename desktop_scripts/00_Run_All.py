# Run the complete analysis in the existing Jupyter environment


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


# %% Execute all stages, saving every result and the execution manifest.

run('all')


# %% Inspect the principal results.

for filename in ['historical_scores.csv','tobit_coefficients.csv','ml_prediction_summary.csv','simulation_summary.csv','pooled_comparison.csv']:
    print('\n'+filename)
    print(pd.read_csv(OUT/filename).head(10).to_string(index=False))


# %% Run the full case audit against this output folder.

import subprocess
subprocess.run([sys.executable,'-B','-m','tests.verify_case','--run-dir',str(OUT)],cwd=ROOT,check=True)
