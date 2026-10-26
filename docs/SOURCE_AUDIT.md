# Source and implementation audit

Naming revision note: execution evidence below predates the English-label and stage-filename update. No analysis was rerun; previous run folders and original execution reports remain unchanged. See naming_revision.json.

Version 1.1, revised 26 October 2026.

## Prepared inputs and sample scope

The historical operational table is filtered to Tainan City, Kaohsiung City, Yilan County, Hualien County, Taitung County and New Taipei City, producing 200 DMUs. The same RouteID set is selected from tobit_socio.csv, with county identity checked for every match. Original field strings and values are preserved in both filtered source copies.

The explanatory file already contains area, density, population shares, operator indicators and public-transport overlap. These variables are used directly. No catchment or demographic feature-construction stage is included. Historical scores stored in the explanatory file are explicitly discarded before joining fresh restricted-sample DEA results.

The demand table dt_model.csv is copied byte-for-byte. Its 71,801 observations include both fixed-route and DRT records; it is a separate model sample from the 200 service-level DMUs. Both future-feature tables are included in lossless gzip form, with decompressed hashes checked against the source files.

## Model implementation

| Component | Source and retained method | Revision |
|---|---|---|
| Historical DEA | Original meta/group directional-distance notebooks; variable returns to scale and intention-selected output directions | Same mathematical model on the restricted 200-DMU reference set; numerical distances within 1e-9 of a bound are snapped for consistent censoring |
| Tobit | FR, FFR and pooled formulas from the original Taiwan R analysis | Supplied tobit_socio variables matched by RouteID; new scores joined; two group-constant predictors omitted and logged |
| Regression demand | Both GAM formulas in add FR.R, including DRTRoute, FR_share and CBD interactions | Estimation-only stage on supplied prepared data; source threshold grid 0.800–0.860; no catchment or smartcard processing blocks copied |
| ML forecast | trip_estimation_optimized.py and deployment_model.joblib from the specified ML folder | Source algorithm preserved; only DEFAULT_ROOT made project-relative; original sklearn/XGBoost versions pinned; model/training hashes verified |
| Simulation | Existing portable passenger-agent insertion implementation | Real roads, speed factors, spatial grids, four depots and all eight source fleet/area combinations; faster source-wise shortest paths; complete passenger accounting |
| Monthly evaluation | Existing prepared proposal characteristics and Economic Output.xlsx parameters | No proposal catchment recalculation; new daily outcomes and unit costs; explicit separation of tours, passengers and busy time |

## Important indicator correction

The source simulation export labels passenger counts as MonthlyTrips and vehicle busy-time utilization as Util_Rate. The historical operational dataset uses vehicle trips and the share of trips with passengers. Converting percentages to fractions does not resolve that conceptual mismatch.

Legacy exports are retained only under data/reference. The new simulator records dispatch tours, passenger-carrying tours, empty VKT and busy time separately. The main pooled specification omits MonthlyTrips and Util_Rate, using fleet, VKT and unit cost inputs with patronage and the shared intention outputs. Historical-only comparison scores are recomputed on this same specification. The complete original indicator set is exported as a sensitivity result based on explicit dispatch-tour accounting.

## Scope of reproduction

The ML forecasts are regenerated from the saved deployment bundle over every row of both feature tables and checked against the original calibrated forecasts. The GAM formulas are transcribed from add FR.R and fitted on the complete source demand table. Tobit uses the supplied explanatory values but fresh 200-DMU scores, so results intentionally differ from a national-sample regression.

All eight area/fleet scenarios run through the portable event-driven simulator with the documented assumptions. Exact stochastic trajectories from the legacy 30-second notebook are not claimed. Representative access nodes, waiting/ride constraints and source cost assumptions are explicit in the configuration and guidebook.

No standalone P2P Tobit is fitted because all 29 group scores equal one. SI_Tourism is constant in FR and Operator_NGO is constant in FFR; their exclusions are recorded. The sparse uncensored FR sample and large standard errors are retained in the outputs rather than hidden.

## File integrity and portability

docs/data_provenance.json records source locations, source hashes, transformations and packaged hashes. These source locations are provenance records only. Runtime configuration paths refer to packaged files. FILE_MANIFEST.sha256 covers the published inputs, code, documentation and verified outputs; the manifest itself is excluded from its own hash list.

The preceding toolkit version is preserved in a dated archive outside the active toolkit folder. Old synthetic inputs, full-national evaluation outputs and obsolete catchment-preparation instructions are not part of the active case.
