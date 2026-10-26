# DRT service planning toolkit

Use this toolkit to connect evidence about existing demand responsive transport (DRT) services with the appraisal of new or reconfigured services. The framework combines ex-post performance evaluation and ex-ante demand estimation and operational simulation. It supports questions about fleet provision, service design, resource use and service quality.

For a new case study, first define the planning question, prepare compatible data and review the model assumptions. Then register the study in a separate configuration file and select an execution route. The packaged case is a format reference and worked example; its geographic scope, fitted relationships and operating values are not universal defaults.

The [general practitioner guidebook](docs/DRT_Planning_Guidebook_General_v2.1.docx) gives detailed preparation and execution instructions. Browser and text editions are available as [HTML](docs/GUIDEBOOK.html) and [Markdown](docs/GUIDEBOOK.md).

## Define the study and analysis workflow

Specify the study area, reporting period, included services, policy objectives and proposed alternatives. Define the decision-making unit (DMU) consistently, for example one service over a common observation period. Assign each record a unique **ServiceID**, stored as text. A service observed over several periods needs distinct identifiers or consistent aggregation. Proposed alternatives must have identifiers distinct from historical records.

The five conceptual stages use six numbered desktop entries because demand estimation and prediction have separate entry files. The combined [00_Run_All.ipynb](desktop_scripts/00_Run_All.ipynb) runs the complete sequence. Individual notebooks and R scripts support staged execution and inspection.

| Framework stage | Desktop entry | Inputs | Outputs and application |
|---|---|---|---|
| Historical performance evaluation | [01_Performance_Evaluation.ipynb](desktop_scripts/01_Performance_Evaluation.ipynb); directional distance function | Historical service resource inputs, outcomes, service types, intentions and prepared contextual indicators | Group and meta-frontier scores and peers for benchmarking |
| Analysis of performance associations | [02_Performance_Drivers.R](desktop_scripts/02_Performance_Drivers.R); Tobit regression | Recalculated scores and service-level explanatory records matched by ServiceID and jurisdiction | Estimates and diagnostics for interpreting performance associations |
| Demand estimation and prediction | [03_Demand_Estimation.R](desktop_scripts/03_Demand_Estimation.R); hurdle Tweedie regression; [04_Demand_Prediction.ipynb](desktop_scripts/04_Demand_Prediction.ipynb) | Observed OD-hour demand, prepared explanatory features, scenario features and a validated fitted demand model | Explanatory relationships and diagnostics; separate hourly scenario forecasts for simulation |
| Operational simulation | [05_Operational_Simulation.ipynb](desktop_scripts/05_Operational_Simulation.ipynb); agent-based model | Forecast demand, directed roads, grid access nodes, depots, fleet and service constraints | Served and rejected requests, waits, ride times, vehicle kilometres and vehicle activity |
| Pooled comparative evaluation | [06_Service_Comparison.ipynb](desktop_scripts/06_Service_Comparison.ipynb); monthly conversion and directional distance function | Historical and proposed indicators with compatible periods and definitions, costs and service intentions | Historical-only baselines and pooled comparative scores for service alternatives |

Historical scores feed the Tobit models. Scenario demand forecasts feed simulation, whose outcomes are converted to monthly indicators before pooled evaluation. Explanatory demand-model fits support interpretation and diagnostics; they are not automatically the simulation forecasts. Associations do not establish causal effects.

## Prepare the software and workspace

Keep `desktop_scripts`, `drt_toolkit`, `config`, `data` and `tests` together under the toolkit root. Use Python 3.10–3.12, Jupyter or a compatible editor, and R. Review [requirements.txt](requirements.txt) for the reference dependency versions and compatibility with the fitted demand model. R must load AER, mgcv and jsonlite. Optional spatial preparation dependencies are listed in [requirements-spatial.txt](requirements-spatial.txt).

With compatible existing installations, select the appropriate notebook kernel and set the installed `Rscript.exe` location in [desktop_settings.json](desktop_scripts/desktop_settings.json). The desktop entries check dependencies; they do not reset the environment. If the toolkit moves, set `DRT_TOOLKIT_ROOT` before sourcing an R entry, or revise its root setting. Open notebooks from within the toolkit folder.

For a dedicated environment, run the optional setup from PowerShell in the toolkit root:

```powershell
.\setup.ps1 -Python 'C:\path\to\python.exe' `
  -Rscript 'C:\path\to\Rscript.exe'
```

This creates `.venv`, installs Python requirements and checks or installs missing R packages in the selected R installation. Select or register that environment as a Jupyter kernel before using it in notebooks.

## Prepare the data for a new case study

Create a study subfolder such as `data/project_A/`. Use [DATA_DICTIONARY.csv](docs/DATA_DICTIONARY.csv) and the packaged tables to check formats, then prepare the study's own records. Use UTF-8 CSV files, preserve identifiers as text and use consistent units, dates and missing-value conventions. Prepared demographic and spatial-context features must already be available; catchment analysis and raw smartcard processing are outside the toolkit.

| Input group | Preparation requirements |
|---|---|
| Historical service table | One row per unique ServiceID, with ServiceType, COUNTYNAME, configured resource inputs and outcomes, binary service-intention flags and required contextual indicators. Use finite nonnegative indicators and a common reporting basis. The current preparation code checks Util_Rate as a fraction from 0 to 1 even when excluded from a comparison specification. |
| Performance explanatory table | Exactly match the selected historical ServiceID set and COUNTYNAME labels. Include variables used by the Tobit formulas; review missing values, constant predictors, collinearity and uncensored score variation. Scores are joined from the selected evaluation, rather than reused from another reference frontier. |
| Observed demand table | Prepare GridID_O, GridID_D, Hour, observed Trips and all configured explanatory features. The regression's zero_trip flag is 1 for zero Trips and 0 otherwise. Keep feature transformations and units consistent. |
| Demand scenario inputs | Prepare complete OD-hour features for each scenario and register a compatible, validated fitted demand model. Review calibration, expansion and growth assumptions for the new study. Alternatively, supply independently validated hourly forecasts through the provided-demand interface. |
| Road and spatial inputs | Directed network columns: from_node, to_node, travel_time_s and distance_km. Require positive times and nonnegative distances. Prepare GridID-to-node_id mappings and valid depot nodes; confirm directed connectivity. Supply configured spatial reference files and consistent coordinate systems. |
| Proposed services and costs | Give each scenario a unique ServiceID and matching service-characteristics record. Define fleet, capacity, hours, constraints, replications, operating days and cost assumptions. Prepare all service-intention/contextual outputs needed for pooled comparison. |

The standard hourly forecast interface is `Hour`, `GridID_O`, `GridID_D`, `PredTrips`. PredTrips represents expected passenger requests per OD pair during that hour. If using provided forecasts, set `demand.source` to `provided` and `paths.provided_od` to their file. Run selected stages if demand-estimation inputs are unavailable; the complete sequence still fits the explanatory demand model.

Use **ServiceID** consistently in operational, explanatory and scenario tables and in scenario configuration objects. DEA score and peer exports retain `DMU` as the analytical label for the same service identifier; the R join converts that label to ServiceID. GridID and passenger/vehicle identifiers have separate meanings and must not be renamed to ServiceID.

## Register the case and review settings

Copy [project_template.json](config/project_template.json) to a study-specific file, for example `config/project_A.json`. The template is a populated reference configuration. Review every inherited value before use, including paths, formulas, jurisdictions, scenarios, fitted-model checks and costs.

| Configuration area | Set for the study |
|---|---|
| paths and allowed_counties | Study input files and included jurisdiction labels. Use matching labels across service tables. Keep configuration files directly under config and use toolkit-root-relative paths, forward slashes and project_root set to `..` for the standard layout. |
| evaluation and comparison_evaluation | Resource inputs, desirable outputs and policy-direction indicators. Prepare a matching service-intention mapping with at least one output for each intention. |
| tobit.models | Estimable group formulas and available explanatory variables. Review whether each group has adequate sample size and score variation. |
| demand | Estimation formulas, forecast case identifiers, compatible model and feature files, calibration and integrity settings. Clear reference-demand paths to null unless matching study-specific forecasts exist. |
| simulation | Scenarios with ServiceID, demand_case and fleet_size; capacity, operating hours, depot nodes, dwell, waiting/ride constraints, dispatch weights, seed and replication count. |
| bridge | Reporting-day conversion, costs, trip accounting and comparability review. Set comparable_trip_definition_confirmed to false during review; replace the example note and confirm only after definitions are compatible. |

Update demand case identifiers, feature-file paths, scenario demand_case values and spatial mappings together. Update both the depot table and `simulation.depot_nodes`; deployment uses the configuration's node list. Choose replication counts through stability checks and justify operating-day and cost assumptions from the study context.

For desktop execution, edit `desktop_scripts/desktop_settings.json`:

```json
{
  "config": "config/project_A.json",
  "run_id": "project_A_001",
  "rscript": "C:/path/to/Rscript.exe"
}
```

Restart the notebook kernel after changing settings. Keep `paths.outputs` as `outputs` with the current desktop helpers and standalone R entries; another output location requires coordinated reader/writer changes. Use one run ID across the stages of a run and a new ID after changing data, code or configuration. Existing run manifests reject changed hashes.

## Adjust scripts when the study requires it

Changing file paths alone is sufficient only when the data and assumptions already satisfy the existing interfaces. Review these components when adapting the framework:

- **Service classifications:** revise the group mapping in `drt_toolkit/evaluation.py` and related formulas for labels beyond Fixed-Route, Flexible Fixed-Route and Point-to-Point.
- **Regression specifications:** review both the standalone R entries and the corresponding models in `drt_toolkit/r/` when changing model logic or complex formula terms.
- **Demand model:** fit and validate a suitable model when populations, feature definitions or calibration change. Register its model file and integrity information together with compatible training and scenario inputs.
- **Spatial identifiers and operations:** revise the input adapter in `drt_toolkit/simulation.py` if the grid-ID scheme differs from the example. Timetables, corridors, grouped bookings, shifts or different dispatch rules require corresponding operational logic; evaluation labels do not impose those rules.
- **Accounting and comparison:** review the bridge in `drt_toolkit/pipeline.py` for different reporting periods, costs or KPI definitions. Patronage, dispatch tours, passenger-carrying trips, busy time and seat occupancy are distinct measures. Passenger-kilometres, promised-time delays, farebox revenue and subsidy require additional calculations.
- **Inspection and validation:** update example paths in preview cells, particularly notebooks 01 and 05. Replace the example-only final audit in notebook 00 and fixed checks in `tests/verify_case.py` with checks appropriate to the study. Keep paired notebook and .py entries consistent.

For externally modelled operational results, prepare reviewed monthly indicators and run comparison separately. The standard combined sequence includes the built-in simulation and bridge.

## Run and review the study

| Route | How to run | Typical use |
|---|---|---|
| Desktop | Open 00_Run_All.ipynb or numbered notebooks with the selected kernel; source R entries in RStudio or through optional notebook calls | Inspect intermediate data, diagnostics and results interactively |
| Windows PowerShell | Supply Python, Rscript, Config and RunId to run_case.ps1, or use individual pipeline commands | Repeat a configured analysis or execute stages in a batch |

From PowerShell in the toolkit root:

```powershell
.\run_case.ps1 `
  -Python 'C:\path\to\python.exe' `
  -Rscript 'C:\path\to\Rscript.exe' `
  -Config 'config/project_A.json' `
  -RunId 'project_A_001'
```

For one stage, use the compatible Python executable:

```powershell
& 'C:\path\to\python.exe' -m drt_toolkit evaluate `
  --config config/project_A.json --run-id project_A_001
```

Other stages are validate, tobit, demand, predict, simulate, bridge and compare. Some pipeline stages read historical service inputs even when demand is the immediate task. The standalone demand-estimation R entry supports independent estimation. In desktop execution, skip optional R calls if the corresponding model has already been fitted for the run.

Both routes should use the same inputs, specifications and seed policy when comparing results. Review files in `outputs/<run_id>/`: historical scores and peers, regression summaries, demand diagnostics and forecasts, simulation summaries and passenger/vehicle details, monthly indicators and pooled results. Pipeline manifests record versions, hashes and stage status; standalone R runs retain fitted objects, summaries and session information.

Check input coverage, matching keys, estimation convergence, forecast plausibility, network routing, request conservation and service constraints. Confirm that historical and proposed indicators use compatible definitions before interpreting pooled scores. Software execution establishes internal consistency; validation against the study context is still required. Read waiting times and rejected demand alongside efficiency scores.

## Use the illustrative data as a reference

The example includes matched historical operational and explanatory tables, prepared OD-hour demand observations, scenario features, a fitted demand model, directed roads, grid/depot mappings, spatial references, scenario characteristics and costs. Inspect `data/evaluation/`, `data/tobit/`, `data/demand/`, `data/simulation/`, `data/spatial/` and `data/scenarios/`, together with the paths selected in the example configuration. Compressed CSV.gz tables can be read directly by pandas.

Use these files to understand schemas and information flow. Preserve them while preparing a separate study. The example sample, geographic labels, fitted relationships, fleets and accounting assumptions require reassessment before transfer. Appendix A of the general guidebook describes the example separately from the main preparation instructions.

Recorded example outputs have had their ServiceID field naming migrated; this does not constitute a new analytical run. Their manifests describe the original execution and original hashes. Use a fresh run ID for future runs after this schema change. See [the schema migration record](docs/SERVICE_ID_MIGRATION.json) for changed files and preservation details.

## Further documentation

- [General Word guidebook](docs/DRT_Planning_Guidebook_General_v2.1.docx), [HTML](docs/GUIDEBOOK.html) and [Markdown](docs/GUIDEBOOK.md): detailed study preparation, settings and step-by-step execution.
- [Desktop instructions](desktop_scripts/README_DIRECT_RUN.md): entry files and environment selection.
- [Academic framework description](docs/DRT_Toolkit_Desktop_Academic_Description.docx): modelling roles, information flows and interpretation.
- [Data dictionary](docs/DATA_DICTIONARY.csv), [inventory](docs/data_inventory.json) and [provenance](docs/data_provenance.json): fields and packaged data sources.
- [Recorded validation report](docs/VALIDATION_REPORT.md) and [source audit](docs/SOURCE_AUDIT.md): earlier execution evidence and implementation details. Earlier guidebook editions remain preserved as historical records.
