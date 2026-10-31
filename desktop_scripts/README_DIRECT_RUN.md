# Run the DRT analysis in Jupyter and RStudio

Use the desktop entry files to evaluate existing services, estimate demand, simulate operational alternatives and compare proposed services. Keep desktop_scripts, drt_toolkit, config and data inside the same toolkit folder. Each Jupyter notebook has a matching .py file for an editor or Spyder.

## Before starting

Select a Python kernel containing the required packages. Use the dependency profile in requirements.txt for the saved demand model. Kernel names may differ on other installations; check the interpreter and compatibility messages printed by the first code cell.

Check desktop_settings.json before execution. It specifies the shared configuration file, the installed Rscript.exe path and a run_id. The default configuration is config/case_study.json and the default run_id is example_run_001. The scripts do not install packages or create environments.

## Run the complete framework

1. Open 00_Run_All.ipynb and select a compatible Python kernel.
2. Run the first cell to check the interpreter, dependency-check messages, Rscript path and result folder.
3. Run the remaining cells in order. Wait for each stage to finish before inspecting its downstream results.
4. Review the principal tables and run the final case-audit cell. Results are saved under outputs/<run_id>.

## Run individual stages

| Order | Entry file | Purpose | Principal output |
|---|---|---|---|
| 1 | 01_Performance_Evaluation.ipynb | Evaluate existing services on group and meta frontiers | historical_scores.csv |
| 2 | 02_Performance_Drivers.R | Estimate explanatory associations with performance | tobit_summary.txt; tobit_coefficients.csv |
| 3 | 03_Demand_Estimation.R | Fit positive-flow and zero-flow demand models | demand_summary.txt; hurdle_tweedie_models.rds |
| 4 | 04_Demand_Prediction.ipynb | Predict scenario demand with the saved demand model | *_demand_200.csv.gz; *_demand_500.csv.gz |
| 5 | 05_Operational_Simulation.ipynb | Simulate requests and vehicle operations | simulation_summary.csv; simulation_daily.csv |
| 6 | 06_Service_Comparison.ipynb | Convert monthly indicators and compare service alternatives | pooled_comparison.csv |

Open an R entry file in RStudio and click Source. Both R files read shared settings through desktop_common.R. Stage 2 requires Stage 1 scores for the same run ID. Stage 3 can run independently of performance evaluation. Notebooks 01 and 04 can also call the corresponding R files; skip these optional cells when the models have already been fitted in RStudio for that run.

## Manage paths and study runs

Use one run ID for all stages belonging to the same study. Choose a new ID when data, code or model settings change. The pipeline rejects changed hashes in an existing run folder. Saved settings are read before each stage call. After a toolkit update, reopen the updated notebook and run its first setup cell to refresh the helper code. Sourcing an R entry file reloads its settings.

Python editor scripts and R entry files locate the toolkit from their entry-file location. Notebooks search their working folder and parents. Open notebooks inside the toolkit. If R discovery fails, set DRT_TOOLKIT_ROOT before sourcing. Set rscript in desktop_settings.json to the installed Rscript.exe. Keep the supporting modules and data with the entry files.

## Interpret the results

The packaged example contains the same 200 DMUs in the operational and Tobit tables. Tobit outcomes are recalculated for this sample. Demand estimation examines relationships and model diagnostics; future operational demand comes from the saved demand model. Sociodemographic variables are prepared inputs, so no catchment analysis is performed.

The DDF uses SciPy HiGHS. The event-driven simulator represents flexible pooled operations; it does not replay recorded vehicle trajectories. Review model assumptions and constraints before transferring the framework to another service. Trip counts and busy-time utilization are different measures, so review the primary harmonized comparison and full-indicator sensitivity together.

Read the [PDF guidebook](../docs/DRT%20Planning%20Toolkit%20Guidebook.pdf) for detailed data preparation, configuration and outputs. For command-line execution, see the [root README](../README.md#run-through-windows-powershell). The [introduction webpage](../docs/DRT%20Planning%20Toolkit.html) and PDF guidebook are stored together in `docs`. The PDF retains reference-installation guidance; this distribution uses automatic root discovery and the initial run ID example_run_001.

The final combined-notebook audit checks the supplied illustrative case, including its reference forecasts and expected record counts. Adapt these checks when using another study. Previous execution outputs are not distributed; run the framework to create a fresh result folder.
