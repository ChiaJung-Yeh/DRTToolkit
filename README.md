# DRT planning toolkit

This toolkit connects **ex-post evaluation of existing demand responsive transport services** with **ex-ante assessment of new or reconfigured services**. Use it to benchmark current provision, examine performance associations, estimate travel demand, test operational alternatives and compare proposed services with an observed reference set.

The framework can support studies of fleet provision, service areas, unmet demand and policy-oriented service objectives. Its role is decision support: interpret comparative efficiency alongside waiting times, rejected requests, resource requirements and local mobility goals. The included case is a worked example, not a universal set of indicators or calibrated models for every locality.

## Analysis workflow through the desktop scripts

The framework has five conceptual stages. The demand stage has separate estimation and prediction entries, so the desktop implementation contains six numbered stages. All notebooks have matching .py files; the two R stages can be sourced directly in RStudio. Use [00_Run_All.ipynb](desktop_scripts/00_Run_All.ipynb) for the complete sequence or the individual entries below for staged analysis.

| Framework stage | Desktop entry and modelling approach | Inputs to prepare | Main outputs and use |
|---|---|---|---|
| Historical performance evaluation | [01_Performance_Evaluation.ipynb](desktop_scripts/01_Performance_Evaluation.ipynb); directional distance DEA | Service-level resource and outcome indicators, service types, service intentions and prepared contextual measures | Group and meta-frontier scores and peers for benchmarking within service types and across the reference set |
| Analysis of performance associations | [02_Performance_Drivers.R](desktop_scripts/02_Performance_Drivers.R); Tobit regression | Recalculated scores and matched service, operator, demographic and transport-context variables | Estimated associations that help interpret observed performance differences; they are not causal effects |
| Demand estimation and prediction | [03_Demand_Estimation.R](desktop_scripts/03_Demand_Estimation.R); hurdle Tweedie GAMs. [04_Demand_Prediction.ipynb](desktop_scripts/04_Demand_Prediction.ipynb); saved ML predictor | Observed OD-hour travel patterns, prepared origin/destination and temporal features, future-scenario feature tables and a suitable fitted predictor | Explanatory model estimates and diagnostics, followed by separate hourly OD forecasts used by simulation |
| Operational simulation | [05_Operational_Simulation.ipynb](desktop_scripts/05_Operational_Simulation.ipynb); event-driven agent-based model | Forecast demand, directed road network, grid access points, depot nodes, fleet size/capacity, operating hours and service constraints | Served/rejected requests, waiting and ride times, vehicle kilometres, activity measures and variation across replications |
| Pooled comparative evaluation | [06_Service_Comparison.ipynb](desktop_scripts/06_Service_Comparison.ipynb); monthly conversion and directional distance DEA | Historical indicators, comparable monthly indicators for proposals, costs, service types and service intentions | Performance comparison on common reference frontiers, historical-only baselines and indicator sensitivity results |

Historical scores feed the Tobit models. **ML forecasts feed operational simulation; GAM fitted values do not.** Simulation outcomes are converted to monthly indicators before pooled evaluation. Performance associations and explanatory demand relationships help interpret the study and formulate alternatives; they are not automatically converted into causal scenario rules.

The built-in simulator represents flexible pooled operations. A timetable, fixed corridor or different dispatch policy requires corresponding operational-model revisions. The broad framework can also accommodate additional passenger, operator and economic KPIs. Passenger-kilometres, promised-time delays, farebox revenue and net subsidy are **not standard exported summaries**; add the required data, definitions and calculations before reporting them.

## Environment setup

Use Python 3.10–3.12, Jupyter or a compatible editor, and R. The saved example ML bundle requires **scikit-learn 1.5.1 and XGBoost 2.1.0**. The Python analysis also uses NumPy, pandas, SciPy and joblib. R requires **AER, mgcv and jsonlite**. See [requirements.txt](requirements.txt) for the compatible pinned example environment.

1. Select an existing Python kernel with compatible packages. The reference installation uses the ArcPy-labelled Anaconda base kernel; this label does not make ArcGIS a toolkit requirement. Check the interpreter and versions printed by the notebook's first cell. The desktop scripts check dependencies but do not install or reset environments.
2. Set the installed Rscript.exe path in [desktop_settings.json](desktop_scripts/desktop_settings.json). Confirm the same R installation can load the required R packages. Open the R entry files in RStudio and choose **Source**, or allow the notebooks to call them through Rscript.
3. Keep desktop_scripts, drt_toolkit, config and data inside the toolkit folder. If the toolkit is moved, review the R toolkit_root setting or set DRT_TOOLKIT_ROOT; update the configured paths as needed. The modules do not need an editable pip installation.

For a new computer or a separate software environment, the alternative packaged setup is available:

```powershell
.\setup.ps1 -Python 'C:\path\to\python.exe' -Rscript 'C:\path\to\Rscript.exe'
```

This optional setup creates a dedicated .venv and installs its Python requirements; it also checks and installs missing R packages in the selected R installation. It is unnecessary when a compatible existing environment is already available. To use the dedicated environment in Jupyter, select or register its kernel. Optional packages in requirements-spatial.txt support spatial inspection and rebuilding access mappings; they are not required for the prepared example.

## Prepare the data before running another study

Start with [DATA_DICTIONARY.csv](docs/DATA_DICTIONARY.csv) and the example tables as schema references. Prepare data outside the models before changing paths. The toolkit does not acquire raw smartcard data or perform catchment analysis. Demographic, destination, overlap and other spatial/contextual variables must already be calculated at the relevant service or OD level.

| Input group | Preparation requirements |
|---|---|
| Historical service indicators | One record per unique RouteID. Supply configured resource inputs, outcomes, service type, jurisdiction and binary service-intention flags. Use consistent reporting periods and cost units; numeric indicators must be finite and nonnegative. Util_Rate is a fraction from 0 to 1. |
| Tobit explanatory table | Match RouteID and COUNTYNAME exactly to the evaluation sample. Prepare all variables used in the chosen formulas. Recalculate sample-specific efficiency outcomes rather than importing scores from an unrelated frontier. Review missing values, constant predictors, sample size and variation in uncensored scores. |
| Observed demand | Prepare OD-hour records with consistent origin/destination IDs, time units, observed Trips and the required service, demographic, destination and spatial features. The example zero_trip flag equals 1 when Trips is zero. Follow the model's feature definitions and scaling. |
| Future demand features and model | Prepare complete OD-hour features for each proposed service area. Ensure feature names, transformations and ID conventions match the reviewed predictive model. A saved example model is not automatically transferable to new data. |
| Spatial and routing inputs | Prepare directed links with from_node, to_node, positive travel_time_s and distance_km, plus GridID-to-node_id mappings and valid depot nodes. Keep identifiers and coordinate reference systems consistent. Supply configured spatial reference files or revise unused optional paths. |
| Proposed-service settings | Define scenario IDs, service types, demand cases, fleet/capacity, operating hours, service constraints, replication count, operating days and costs. Prepare the contextual service indicators used in pooled evaluation on the same basis as historical indicators. |

Historical and proposed indicators must have compatible definitions. A passenger count is not a vehicle-trip count, and busy-time utilization is not the share of trips carrying passengers. Review these distinctions before choosing evaluation outputs or converting daily simulation outcomes into monthly measures.

## Adapt the configuration and scripts to the input data

**Replacing file paths alone is insufficient when a new dataset changes variables, identifiers, model structure or service assumptions.** Review and revise the relevant scripts and model specifications before interpreting results.

- Copy config/case_study.json for the new study and select it in desktop_settings.json. Update paths, allowed_counties, evaluation indicators, service-intention mapping, Tobit formulas and a new run_id. The six jurisdictions in the example are not a required study boundary. Update inspection cells that read example paths directly, including the operational preview in notebook 01 and scenario preview in notebook 05; execution uses the configuration selected in desktop_settings.json.
- Check drt_toolkit/evaluation.py when using service-type labels other than Fixed-Route, Flexible Fixed-Route and Point-to-Point. Revise the R formulas and supporting model code when explanatory variables, interactions or model assumptions differ.
- Refit and validate the demand models when the study population or feature definitions change. The optional train-ml pipeline stage can fit the ML workflow to prepared training data. Review its fitted bundle before deployment, update ml_model and deployment_model_sha256, and provide matching future features. The training-source hash must match the bundle. Set the reference-demand paths to null unless matching study-specific forecasts are available.
- Review drt_toolkit/simulation.py for a different dispatch policy, service logic or grid-ID convention. The example converts numeric forecast grid IDs to ILA-prefixed identifiers. Update prediction_cases, ml_features_CASE paths, scenario demand_case values and spatial mappings together when changing cases or identifiers. Update both depot_nodes.csv and simulation.depot_nodes consistently.
- Review monthly conversion, cost assumptions, operating days and indicator definitions before pooled evaluation. For external operational-model results, prepare reviewed monthly indicators and run the comparison stage separately rather than the built-in simulation and bridge.
- Adapt or skip the final example-only audit cell in 00_Run_All.ipynb for another study. tests/verify_case.py checks fixed example counts and reference forecasts; it is not a universal audit for all datasets. Replace it with checks appropriate to the new sample, models and scenarios.

Use one run ID across the stages of a study and a new ID when data, code or configuration changes. Restart the notebook kernel after changing desktop_settings.json. The pipeline records hashes and intentionally rejects changed inputs or code in an existing run folder.

## Run and review the analysis

For a complete run, open 00_Run_All.ipynb, select a compatible kernel, check the environment cell and run the analysis cells in order. For staged execution, follow entry files 01 to 06 in the workflow table. Stage 2 needs Stage 1 scores. Stage 3 can run independently of performance evaluation. Notebooks 01 and 04 optionally execute the corresponding R models; skip those cells if the same models have already been fitted in RStudio for the selected run ID.

Results are written to outputs/<run_id>. Review historical_scores.csv, tobit_summary.txt, demand_diagnostics.json, ml_prediction_summary.csv, simulation_summary.csv and pooled_comparison.csv alongside the detailed passenger/vehicle files and model diagnostics. Pipeline runs retain manifest.json, settings, stage status, package versions and input/code hashes. Standalone R runs retain model objects, summaries and R session information.

Software checks establish execution and internal consistency. Study-specific validation is still required for demand, network assumptions, service behaviour and indicator interpretation. Read rejected demand and waiting outcomes alongside comparative scores; a frontier rank alone does not establish an acceptable service design.

## Example data and how to use them

The packaged example illustrates the complete framework. First reproduce it with unchanged inputs to understand the data interfaces and outputs. Then use its schemas as a starting point for a separate, explicitly configured study. The example data, fitted models and scenario assumptions are not defaults that can be assumed valid in another setting.

Historical evaluation and Tobit regression use the same **200 DMUs**: Tainan City 31, Kaohsiung City 68, Yilan County 9, Hualien County 31, Taitung County 41 and New Taipei City 20. The operational table retains 64 source columns and the explanatory table 81; the demand-estimation sample is separate and contains **71,801 prepared OD-hour observations**.

| Example location | Contents and usage |
|---|---|
| data/evaluation/ and data/tobit/ | Matched service-level operational and explanatory data for benchmarking and regression |
| data/demand/dt_model.csv | Prepared observed-demand table for explanatory estimation and optional ML training |
| data/ml/ | Saved deployment model and complete 307,530-row and 826,540-row future-feature tables for the 200 m and 500 m cases |
| data/simulation/ and data/spatial/ | Prepared roads, access-node mappings, four depots, 884 source grid polygons and case subsets of 135 and 221 grids |
| data/scenarios/ | Eight scenario definitions, prepared contextual characteristics, costs and reference demand forecasts |
| data/reference/ | Historical source examples and legacy indicator exports for checking provenance; not substitutes for harmonized current inputs |

The example combines the two service-area cases with fleets of two, three, four and five vehicles, each with four seats. At 20 replications per scenario this yields 160 daily scenario-replication rows. The pooled comparison contains 200 existing and eight proposed services. CSV.gz files contain complete compressed tables and can be read directly by pandas.

The historical evaluation uses four resource inputs and two operational outputs plus service-intention outputs. The primary pooled example specification uses fleet size, vehicle kilometres and unit operating cost as inputs, patronage as its operational output, and the relevant service-intention outputs. MonthlyTrips and Util_Rate are excluded from the primary pooled model because legacy observed and simulated exports used different definitions; pooled_full_indicator_sensitivity.csv provides the alternative fuller comparison. The FR Tobit has few uncensored observations and the P2P group scores are all one, limiting separate regression interpretation.

Existing outputs/verified_case and outputs/desktop_run folders provide recorded example results. The default for a future desktop run is desktop_run_en; choose another new ID if that folder already contains a run with different input or code hashes. Historical reports describe their recorded versions and may contain earlier labels or entry names.

## Documentation

- [Practitioner Word guidebook](docs/DRT_Planning_Guidebook_v1.3.docx), [browser guide](docs/GUIDEBOOK.html) and [Markdown guide](docs/GUIDEBOOK.md): detailed setup, stage inputs/outputs, model assumptions and desktop-versus-packaged execution.
- [Academic description of the desktop framework](docs/DRT_Toolkit_Desktop_Academic_Description.docx): thesis-oriented explanation of the application, modelling stages, information flows and limitations.
- [Data dictionary](docs/DATA_DICTIONARY.csv), [inventory](docs/data_inventory.json) and [provenance](docs/data_provenance.json): input definitions and example origins.
- [Validation report](docs/VALIDATION_REPORT.md) and [implementation audit](docs/SOURCE_AUDIT.md): recorded execution checks and modelling choices. Earlier guidebooks remain under docs/archive.
