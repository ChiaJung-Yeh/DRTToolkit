# DRT Planning Toolkit

Integrate observed-service evaluation, explanatory regression, demand generation, passenger-agent simulation and pooled evaluation of proposed services.

**Start with [the practitioner guidebook](docs/DRT_Planning_Guidebook.pdf)**. An editable [Word version](docs/DRT_Planning_Guidebook.docx), a [browser version](docs/GUIDEBOOK.html), editable [Markdown version](docs/GUIDEBOOK.md), [data dictionary](docs/DATA_DICTIONARY.csv), [source audit](docs/SOURCE_AUDIT.md) and [validation report](docs/VALIDATION_REPORT.md) are included.

For a research-oriented introduction, see the [academic overview](docs/DRT_Toolkit_Academic_Introduction.docx), which explains the modelling stages, their inputs and outputs, and the framework's applications.

## Quick start on Windows

Install Python 3.10+ and R with `Rscript` available. Open PowerShell in this folder.

```powershell
.\setup.ps1
.\run_demo.ps1 -Python .\.venv\Scripts\python.exe
```

If executables are not on PATH, pass their full paths:

```powershell
.\setup.ps1 -Python 'C:\path\to\python.exe' -Rscript 'C:\Program Files\R\R-4.4.2\bin\Rscript.exe'
.\run_demo.ps1 -Python .\.venv\Scripts\python.exe -Rscript 'C:\Program Files\R\R-4.4.2\bin\Rscript.exe'
```

The demo evaluates the supplied **442 real historical Taiwan services**. Its demand observations, road network and proposed-service characteristics are **synthetic teaching examples**. Its regression is a smaller demonstration specification. Results from this mixed example are not a planning recommendation.

## Use your own data

1. Copy `data/templates/` into a new `data/user/` folder and populate the CSVs.
2. Copy `config/project_template.json` to `config/my_project.json` and edit the paths, models and service settings.
3. Follow the guide's data-preparation and comparability steps. The production template deliberately requires you to document the simulation-to-evaluation bridge.
4. Run each stage with the same configuration and run ID:

```powershell
.\.venv\Scripts\python.exe -m drt_toolkit validate --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit evaluate --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit tobit --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit demand --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit simulate --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit bridge --config config/my_project.json --run-id study01
.\.venv\Scripts\python.exe -m drt_toolkit compare --config config/my_project.json --run-id study01
```

After inspecting a first run, `python -m drt_toolkit all --config config/my_project.json --run-id study02` runs the sequence. Use a new run ID whenever inputs, code or configuration change. Relative paths resolve from the configured project root, not from the current directory.

`outputs/<run-id>/pooled_comparison.csv` is the main comparison table. Read it alongside passenger waiting times, rejected requests, distances, uncertainty and service coverage.

## Structure

| Location | Purpose |
|---|---|
| `drt_toolkit/evaluation.py` | Licensed-solver-free VRS directional distance DEA, group and meta frontiers |
| `drt_toolkit/r/tobit.R` | Configurable censored Tobit models using observed-service scores |
| `drt_toolkit/prepare_demand.py` | Build OD-hour means and features from local observed counts and grid attributes |
| `drt_toolkit/r/demand.R` | Positive-flow Tweedie GAM and zero-flow binomial GAM |
| `drt_toolkit/simulation.py` | Seeded passenger agents, directed network, feasible vehicle insertion |
| `drt_toolkit/pipeline.py` | Stage orchestration, monthly bridge, pooled comparison, provenance |
| `config/` | Runnable demo and production template |
| `data/example/` | Supplied historical data, SI mapping, clearly labelled synthetic examples |
| `data/templates/` | Empty schemas for practitioners |
| `reference/` | Sanitized reference copies of all five supplied scripts/notebooks |
| `docs/` | Guidebook, field dictionary, source audit and test evidence |
| `tests/` | Analytical DEA, simulation and data-preparation checks |

No live data APIs or commercial solver licence are needed for the runnable toolkit. Original reference notebooks still have their original dependencies. No raw smartcard identifiers are distributed.

An optional `DRT_Toolkit_Walkthrough.ipynb` wraps the same stages for notebook users. Open it from this folder in a Python environment with the toolkit dependencies and Jupyter installed. The command-line workflow does not require Jupyter.
