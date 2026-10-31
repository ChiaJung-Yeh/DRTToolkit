# DRT Planning Toolkit

An integrated framework for connecting evidence about existing demand responsive transport (DRT) with the appraisal of new or reconfigured services.

The toolkit combines **ex-post performance evaluation** and **ex-ante demand estimation and operational simulation**. Use it to benchmark existing provision, explore performance associations, test service alternatives and compare observed and proposed services using compatible indicators.

Start with the [introduction webpage](docs/DRT%20Planning%20Toolkit.html) for an overview, or read the [practitioner PDF guidebook](docs/DRT%20Planning%20Toolkit%20Guidebook.pdf) for data preparation, configuration and execution.

## What the framework supports

- **Benchmark existing services:** assess resource use and outcomes against service-group and overall reference frontiers.
- **Understand performance associations:** examine how service characteristics, operator attributes and local context relate to recalculated performance.
- **Appraise future services:** estimate prospective travel patterns and test fleet, depot and operating assumptions before implementation.
- **Compare alternatives:** bring simulated operations onto a common reporting basis and evaluate them alongside historical services.

Define the planning question, study area, reporting period, evaluation unit and policy objectives before preparing inputs. The models support appraisal; choosing a preferred service also requires local priorities and operational judgement.

## Analysis workflow

Five conceptual stages are implemented through six numbered desktop entries. The demand stage has separate estimation and prediction files.

| Stage and approach | Desktop entry | Primary inputs | Outputs and application |
|---|---|---|---|
| 1. Historical performance evaluation — directional distance function | [01_Performance_Evaluation.ipynb](desktop_scripts/01_Performance_Evaluation.ipynb) | Service resource inputs, operational outcomes, service types, intentions and prepared contextual indicators | Group and meta-frontier scores and peers for benchmarking |
| 2. Performance associations — Tobit regression | [02_Performance_Drivers.R](desktop_scripts/02_Performance_Drivers.R) | Recalculated scores and explanatory records matched by ServiceID | Model estimates, specifications and diagnostics for interpreting observed differences |
| 3. Demand estimation — hurdle Tweedie regression and scenario forecasting | [03_Demand_Estimation.R](desktop_scripts/03_Demand_Estimation.R) and [04_Demand_Prediction.ipynb](desktop_scripts/04_Demand_Prediction.ipynb) | Observed OD-hour demand, prepared features, prospective features and a compatible reviewed demand model | Explanatory relationships and diagnostics; separate hourly forecasts for simulation |
| 4. Operational simulation — agent-based model | [05_Operational_Simulation.ipynb](desktop_scripts/05_Operational_Simulation.ipynb) | Hourly forecasts, directed roads, grid access nodes, depots, fleets, capacities and service constraints | Served and rejected requests, waits, ride times, vehicle kilometres and vehicle activity |
| 5. Pooled comparative evaluation — monthly conversion and directional distance function | [06_Service_Comparison.ipynb](desktop_scripts/06_Service_Comparison.ipynb) | Historical and proposed indicators, costs, intentions and reviewed reporting definitions | Monthly proposed-service indicators, historical-only baselines, pooled scores and peers |

Historical scores feed the performance-association models. Scenario forecasts feed simulation. Simulated outcomes are converted into monthly indicators before comparison. Explanatory demand-model fits support interpretation and diagnostics; they are not automatically the deployed scenario forecasts.

## Prepare the software and workspace

Keep `desktop_scripts`, `drt_toolkit`, `config`, `data` and `tests` together under one toolkit root. For another study, create `data/project_A/`, copy [config/project_template.json](config/project_template.json) to `config/project_A.json`, and retain the example inputs as a format reference.

Use a compatible Python 3.10–3.12 interpreter, Jupyter or a compatible editor, and R. Check [requirements.txt](requirements.txt) against the fitted demand model's dependency profile. R must load `AER`, `mgcv` and `jsonlite`. Optional spatial dependencies are listed in [requirements-spatial.txt](requirements-spatial.txt).

Existing compatible installations can be used directly. The desktop entries check dependencies without installing packages or resetting environments. If a dedicated environment is required, open PowerShell in the toolkit root and run:

```powershell
.\setup.ps1 -Python 'C:\path\to\python.exe' `
  -Rscript 'C:\path\to\Rscript.exe'
```

Replace the placeholders with installed executable paths. Setup creates `.venv`, installs Python requirements and checks or installs missing R packages. It can require internet access. Select or register `.venv` as a Jupyter kernel separately if using it in notebooks.

## Prepare study data

Save CSV files in UTF-8. Preserve identifiers as text, including prefixes and leading zeros. Prepare the following inputs using consistent units, geographic support and reporting periods.

| Dataset | Primary fields and preparation | Registered through |
|---|---|---|
| Historical service indicators | Unique ServiceID, Jurisdiction, ServiceType, configured input/output indicators, binary service intentions and contextual fields | paths.historical |
| Service-intention mapping | ServiceIntention and binary policy-output columns; every intention maps to at least one output | paths.si_mapping |
| Performance explanatory data | One record per selected historical ServiceID, matching jurisdiction labels and all configured predictors | paths.tobit_explanatory; optional paths.exogenous |
| Observed demand | GridID_O, GridID_D, Hour, Trips, zero_trip and all required explanatory features; include zero observations | paths.demand_training |
| Scenario demand inputs | Complete prospective OD-hour features and a compatible reviewed fitted model, or independently validated hourly forecasts | Existing model/feature path entries, demand.prediction_cases; alternatively paths.provided_od |
| Directed network | from_node, to_node, travel_time_s and distance_km; valid directions and connectivity | paths.network |
| Grids and depots | GridID-to-node_id access assignments, valid depot nodes and configured spatial references | paths.grid_nodes, paths.depots and simulation.depot_nodes |
| Proposed-service characteristics | Unique proposed ServiceID, classification, FleetNum, KMCost, intention flags and contextual outputs; match configured alternatives | paths.scenario_characteristics |
| Costs | Consistent currency and price basis for fuel cost, driver wages and wage operating days | paths.cost_parameters |

Use **ServiceID** across service tables and scenario settings, and **Jurisdiction** for administrative labels. Generated efficiency tables retain `DMU` for the corresponding service identifier; the regression entry maps it to ServiceID. Passenger, grid and road-node IDs remain separate identifiers.

`PredTrips` represents expected requests for an OD pair during an hour, rather than a per-second rate. `KMCost` is cost per vehicle kilometre, rather than monthly total cost. Historical `MonthlyPatronage` represents boardings; simulated monthly patronage is derived from served requests. Review these definitions before comparison.

The toolkit consumes prepared demographic and spatial-context features. It does not retrieve raw smartcard records, construct catchments or allocate population to service areas. Appendix A of the guidebook describes primary fields, units and data locations. The [data dictionary](docs/DATA_DICTIONARY.csv) provides a broader source inventory; the active CSV headers and configuration determine the fields required by the selected study.

## Configure and adapt a new case

The supplied template contains example settings rather than universal defaults. Review every inherited path and assumption.

| Configuration area | Review for the study |
|---|---|
| project_root, rscript and paths | Keep the configuration directly under config with project_root set to `..`; use forward slashes and toolkit-relative input paths. Select the intended R executable. Every non-null input path must exist. |
| allowed_jurisdictions | Exact jurisdiction labels matching the selected service records |
| evaluation and comparison_evaluation | Resource inputs, desirable outputs, policy mapping and compatible comparison definitions |
| tobit.models | Group selections, formulas, sample sizes, score variation and predictor coding |
| demand | Formulas, feature transformations, forecast cases, fitted-model compatibility and source/integrity checks |
| simulation | ServiceID, demand_case, fleet_size, capacity, depots, hours, dwell, waiting/ride constraints, dispatch weights and replications; seed is a top-level setting |
| bridge | Monthly operating days, cost accounting and a documented comparability review |

Update demand cases, feature paths, scenario demand_case values and spatial mappings together. Clear example forecast-reference paths to `null` unless matching study-specific references are available. Update both the depot dataset and `simulation.depot_nodes`; the configured node list controls deployment.

Changing a study can require script revisions. Review the example-specific grid-ID adapter in `drt_toolkit/simulation.py`, service-group mapping in `drt_toolkit/evaluation.py`, formulas in both standalone and packaged R implementations, and accounting logic in `drt_toolkit/pipeline.py`. A new observed-demand file requires a compatible fitted prediction model and matching source information; changing a hash alone does not adapt the model.

The simulator represents flexible pooled operations. Service-type labels do not add timetables or corridor rules. Prepare or revise the operational logic when different rules are needed. Replace example-specific notebook audit counts and `tests/verify_case.py` checks with study-appropriate checks. Keep paired notebook and Python entries consistent when modifying executable cells.

## Run through desktop scripts

1. Open notebooks from within the toolkit folder and select a compatible Jupyter kernel.
2. Edit [desktop_settings.json](desktop_scripts/desktop_settings.json) to select the configuration, fresh run ID and installed Rscript executable.
3. Open [00_Run_All.ipynb](desktop_scripts/00_Run_All.ipynb), run the first setup cell and then execute the remaining cells in order. Use the numbered entries for staged analysis.

```json
{
  "config": "config/project_A.json",
  "run_id": "project_A_001",
  "rscript": "C:/path/to/Rscript.exe"
}
```

The R entries can be called from the notebooks or sourced in RStudio. Skip optional R calls if those models have already been fitted for the selected run. The copied R entry files locate the toolkit from their own location. If automatic discovery fails, set `DRT_TOOLKIT_ROOT` before sourcing an R entry. Keep `paths.outputs` as `outputs` with the current desktop helpers; relocating outputs requires coordinated reader/writer revisions.

After a toolkit update, reopen the updated notebook and run its setup cell to reload the helper. Saved settings are refreshed before stage calls. Starting validation, evaluation or the complete sequence can preserve an incompatible old run and save a fresh run selection. Confirm the printed Results path. For downstream mismatches, restart from notebook 00 or 01.

## Run through Windows PowerShell

Open PowerShell in the toolkit root. Select compatible executable paths, the study configuration and a new run ID:

```powershell
.\run_case.ps1 `
  -Python 'C:\path\to\python.exe' `
  -Rscript 'C:\path\to\Rscript.exe' `
  -Config 'config/project_A.json' `
  -RunId 'project_A_001'
```

PowerShell uses command arguments rather than `desktop_settings.json`. Keep the R executable in the study JSON consistent with the selected installation. Backticks must be the final characters on continued lines.

The complete command runs `validate → evaluate → tobit → demand → predict → simulate → bridge → compare`. For an individual stage:

```powershell
& 'C:\path\to\python.exe' -m drt_toolkit evaluate `
  --config config/project_A.json --run-id project_A_001
```

Use the same run ID for dependent stages with unchanged inputs and settings. Choose a new ID after changing data, configuration or analytical code; existing manifests reject incompatible changes.

For provided hourly forecasts, set `demand.source` to `provided` and register `paths.provided_od`. The complete sequence skips prediction but still runs explanatory demand estimation. For externally prepared monthly service indicators, register `paths.external_scenarios`, complete the comparability review and execute comparison separately; the standard complete sequence still includes built-in simulation and monthly conversion.

## Review and interpret outputs

Read the selected `outputs/<run_id>/` folder and confirm its configuration, input versions and stage status before interpretation.

| Output | Review |
|---|---|
| historical_scores.csv and historical_peers.csv | Sample coverage, grouping, indicators and reference services |
| Tobit samples, estimates and specifications | Matched records, current scores, predictor variation and estimation diagnostics |
| Demand diagnostics and hourly forecasts | Convergence, feature definitions, OD-hour completeness and plausible magnitudes |
| simulation_daily.csv and passenger/vehicle records | Requests = served + rejected; capacity, chronology, waits, rides and vehicle distance |
| scenario_model_data.csv | Monthly conversion, costs and compatible indicator definitions |
| pooled_comparison.csv and replication scores | Historical-only versus pooled changes, peers and feasibility statuses |
| manifest.json and console logs | Inputs, software, analytical code and successful completion of required stages |

Read waiting times and rejected demand alongside relative efficiency. Tobit estimates describe associations rather than causal effects. Retain infeasibility statuses and reasons rather than replacing failed scores with zeros. Execution and accounting checks establish internal consistency; demand and operational behaviour still require validation against the study context.

## Explore the illustrative example

The packaged case contains **200 matched historical services across six jurisdictions** in Taiwan: Tainan City, Kaohsiung City, Yilan County, Hualien County, Taitung County and New Taipei City. It includes **71,801 prepared demand observations**, two demand cases and eight fleet alternatives.  

Use [config/case_study.json](config/case_study.json) to locate the matched service tables, demand and scenario features, fitted model, roads, grids, depots and costs. Inspect formats and information flow before creating a separate study folder. Preserve the example files and review its fitted relationships, geographic conventions and operating assumptions before reuse.

The illustrative inputs support testing and learning the analysis framework. They do not establish the actual performance of the illustrated services, and reproduced results need not match the author’s thesis.

## Documentation and repository contents

- [PDF guidebook](https://github.com/ChiaJung-Yeh/DRTToolkit/blob/main/docs/DRT%20Planning%20Toolkit%20Guidebook.pdf): data definitions, configuration and execution.
- [Introduction webpage](https://chiajung-yeh.github.io/DRTToolkit/): integrated framework and interactive examples.
- [Desktop execution instructions](desktop_scripts/README_DIRECT_RUN.md).
- [Data dictionary](docs/DATA_DICTIONARY.csv).

