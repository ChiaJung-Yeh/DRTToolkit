# DRT Planning Toolkit

This toolkit supports transport planners, service operators and analysts in assessing existing demand responsive transport (DRT) services and exploring new or reconfigured services. It combines historical performance evaluation with demand estimation and operational simulation, then compares existing and proposed services on a common basis.

Use the toolkit to examine how changes in fleet size, passenger demand or operational settings affect service outcomes and relative performance. Assess performance scores alongside passenger waiting times, rejected requests, vehicle travel and service coverage when comparing alternatives.

## Start here

Read the [practitioner guidebook](docs/DRT_Planning_Guidebook.pdf) before preparing a local study. It explains the input data, modelling assumptions, workflow and interpretation of results.

Additional resources are available:

- [Editable Word guidebook](docs/DRT_Planning_Guidebook.docx)
- [Browser guidebook](docs/GUIDEBOOK.html) and [Markdown guidebook](docs/GUIDEBOOK.md)
- [Data dictionary](docs/DATA_DICTIONARY.csv)
- [Validation report](docs/VALIDATION_REPORT.md) and [source audit](docs/SOURCE_AUDIT.md)
- [Academic overview](docs/DRT_Toolkit_Academic_Introduction.docx) explaining the overall analysis framework

## Analysis workflow

| Stage | Purpose | Main result |
|---|---|---|
| Historical performance evaluation | Compare the resources and outcomes of existing services | Relative performance scores and peer-service benchmarks |
| Performance associations | Examine how service characteristics and local context relate to observed performance | Evidence to help interpret differences and develop scenarios |
| Demand estimation | Estimate travel demand by origin, destination and service hour | Hourly passenger demand for simulation |
| Operational simulation | Test proposed fleet configurations and operating conditions | Served and rejected requests, waiting times, ride times and vehicle kilometres |
| Comparative evaluation | Assess existing and proposed services using consistent indicators | A common-basis performance comparison |

Before the final comparison, review how simulated outcomes are converted into monthly evaluation indicators. Historical and proposed services must use compatible definitions of vehicle trips, utilization, operating costs and vehicle kilometres. The guidebook explains this review and the assumptions that must be recorded.

## Install and run the demonstration

Install Python 3.10 or later and R. Ensure that `Rscript` is available on PATH, or specify its full path as shown below. Open PowerShell in the toolkit folder.

```powershell
.\setup.ps1
.\run_demo.ps1 -Python .\.venv\Scripts\python.exe
```

The setup script creates a Python environment and installs the required Python and R packages. Internet access and permission to install packages are needed when dependencies are missing.

If Python or R is not on PATH, provide the appropriate executable paths:

```powershell
.\setup.ps1 -Python 'C:\path\to\python.exe' -Rscript 'C:\Program Files\R\R-4.4.2\bin\Rscript.exe'
.\run_demo.ps1 -Python .\.venv\Scripts\python.exe -Rscript 'C:\Program Files\R\R-4.4.2\bin\Rscript.exe'
```

The demonstration includes historical records for **442 Taiwan services**. Its demand observations, road network and proposed-service characteristics are **synthetic examples**, and its explanatory regression uses a simplified specification. Use the demonstration to become familiar with the workflow and outputs; its proposed-service results are not evidence for a real planning decision.

An optional `DRT_Toolkit_Walkthrough.ipynb` provides a notebook interface to the same stages. Open it from the toolkit folder in an environment with the toolkit dependencies and Jupyter installed. Jupyter is not required for the PowerShell workflow.

## Prepare a local study

1. Create a `data/user/` folder and copy the relevant CSV templates from `data/templates/`.
2. Populate the input tables using the definitions in the guidebook and data dictionary.
3. Copy `config/project_template.json` to `config/my_project.json`. Set the input paths, model specifications and proposed-service settings.
4. Review the reporting basis and indicator definitions for the existing and proposed services. Record the comparability assumptions in the configuration before running the monthly conversion stage.
5. Run the analysis stages in sequence, inspecting the outputs before proceeding.

The required data depend on the stages included in the study:

| Input | Required for |
|---|---|
| Historical service indicators and service-intention mapping | Evaluation of existing services and the final comparison |
| Service and contextual explanatory variables | The selected performance-association models |
| Observed travel patterns and local spatial features | Fitting a local demand model |
| Hourly origin–destination forecasts | Operational simulation; forecasts may come from the toolkit or another demand model |
| Directed road network, grid-to-node mapping and depot location | The built-in operational simulation |
| Proposed-service characteristics and reviewed trip/utilization values | Conversion to monthly indicators and comparative evaluation |

The built-in simulator represents flexible pooled on-demand operations. For designs with fixed timetables or route restrictions, use a suitable operational simulator and import its reviewed monthly indicators through the external-scenario option described in the guidebook.

## Run the study

Use the same configuration and run ID for all stages belonging to one study run:

```powershell
.\.venv\Scripts\python.exe -m drt_toolkit validate --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit evaluate --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit tobit --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit demand --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit simulate --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit bridge --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit compare --config config/my_project.json --run-id study01
```

If using an existing demand forecast, set `demand.source` to `provided`, specify the forecast CSV and skip the `demand` command. The `all` command also skips demand-model fitting under this setting.

After reviewing the inputs and a first staged run, run the full sequence with:

```powershell
.\.venv\Scripts\python.exe -m drt_toolkit all --config config/my_project.json --run-id study02
```

Use a new run ID whenever the inputs, code or configuration change. Relative input paths resolve from the project root specified in the configuration. The initial `validate` command checks the historical evaluation table; subsequent stages check their own inputs.

## Review the results

Results are saved under the configured output folder, normally `outputs/<run-id>/`.

| Output | Use |
|---|---|
| `historical_scores.csv` | Review the relative performance of existing services |
| `tobit_summary.txt` | Examine associations between performance and service/contextual characteristics |
| `demand_diagnostics.json` | Review demand-model diagnostics and held-out accuracy when available |
| `simulation_daily.csv` and `simulation_summary.csv` | Compare passenger outcomes and vehicle activity across scenarios and replications |
| `scenario_model_data.csv` | Check the monthly indicators used to represent proposed services |
| `pooled_comparison.csv` | Compare existing and proposed services using a shared reference set |
| `manifest.json` | Check the configuration, input versions and status of each analysis stage |

Interpret relative performance scores together with operational outcomes and the service objectives. A high score alone does not establish that a service meets local travel needs. Review rejected demand, waiting times, coverage and variability before selecting a preferred design.

## Folder reference

| Folder | Contents |
|---|---|
| `config/` | Demonstration configuration and local-study template |
| `data/example/` | Historical Taiwan records, service-intention mapping and labelled synthetic examples |
| `data/templates/` | CSV schemas for local input data |
| `drt_toolkit/` | Python analysis modules and supporting R scripts |
| `docs/` | Guidebooks, academic overview, data dictionary and verification documentation |
| `reference/` | Research reference scripts and notebooks with credentials removed |
| `tests/` | Checks for the evaluation models, simulation and data preparation |
| `outputs/` | Results grouped by run ID |

The reusable workflow requires no live data API connection or commercial optimization-solver licence. Research reference notebooks retain their study-specific dependencies. Raw smartcard identifiers are not included in the example data.
