# Verification report

Naming revision note: execution evidence below predates the English-label and stage-filename update. No analysis was rerun; previous run folders and original execution reports remain unchanged. See naming_revision.json.

Version 1.1, revised 26 October 2026. The complete verified study is included under outputs/verified_case.

## Data scope and matching

The evaluation table contains 200 DMUs: Tainan City 31, Kaohsiung City 68, Yilan County 9, Hualien County 31, Taitung County 41 and New Taipei City 20. Operational groups contain 80 FR, 91 FFR and 29 P2P services. The explanatory table contains the identical 200 RouteIDs and county identities, with all 81 source columns and no missing cells.

Restricted-sample DEA scores are used as Tobit outcomes. Compared with the national-sample scores stored in the explanatory source, 25 MetaEff values and 23 GroupEff values change by more than 1e-7. The regression's exported outcome columns agree with the new DEA table within 1e-12. Source national scores are not reused.

## Model execution

The historical DEA, FR/FFR/pooled Tobit and source-specification hurdle Tweedie stages complete. Constant SI_Tourism in FR and Operator_NGO in FFR are excluded and recorded; no nonconstant predictor is removed by a significance rule.

The demand model uses all 71,801 rows, including 2,879 positive-flow observations. Both GAMs converge. The zero-share threshold selected from the source 0.800–0.860 search is 0.838. The observed total is 374.5 and fitted total about 386.55. These are estimation-sample diagnostics, not independent prediction accuracy measures.

The FR Tobit uses 80 rows but only seven uncensored scores; some standard errors are large. FFR uses 91 rows with 46 uncensored scores, and the pooled model uses 200 rows with 64 uncensored scores. All 29 P2P group scores equal one, so a separate P2P regression is not attempted.

## ML forecast reproduction

| Case | OD-hour rows | Daily forecast | Maximum absolute row difference from source |
|---|---:|---:|---:|
| 200 m | 307,530 | 36.1036610637 | 1.8647684612e-10 |
| 500 m | 826,540 | 38.3517959863 | 9.5487904042e-11 |

The saved model loads without compatibility warnings under scikit-learn 1.5.1 and XGBoost 2.1.0. Its training-source hash matches the packaged dt_model.csv. Both complete future-feature tables are predicted using the included source implementation. All final rates are finite and nonnegative. Source calibration assumptions, including retained baseline and saturating growth, are preserved.

The optional ML retraining command also completed on the included data, selecting depth3_weight10/tweedie_1.9. Its test metrics are recorded in ml_retraining_verification.json. This separate training run did not replace the supplied deployment bundle.

## Network and simulation

The package includes 74,276 source links, normalized to 74,274 directed arcs after selecting the fastest duplicate pairs, and 34,006 nodes. All forecast access nodes and four depots are mutually routable. Both full and scenario-specific grid polygons are included, as are source speed weights and access-node snap distances.

All eight 200/500 m by 2/3/4/5-vehicle scenarios complete for 20 replications each, yielding 160 daily outcome rows. Checks confirm requests equal served plus rejected, pickup/drop-off chronology, the configured waiting-time bound, capacity at every vehicle's recorded maximum, and empty VKT not exceeding total VKT. Fleet alternatives within each case/replication share the request count and seed.

The main pooled result has 208 DMUs, including all 200 existing services and eight proposals, using the documented harmonized indicator specification. The original full-indicator variant is retained as a sensitivity output. In the fixed-reference replication scoring, 43 rows are optimal and 117 are infeasible under nonnegative directional distance; all statuses and reasons are retained. These results are not presented as a complete confidence interval.

## Automated checks

Twelve focused tests pass, covering a known VRS DEA solution, group/meta ordering, active indicator universes, passenger accounting, capacity, waiting rejection, zero-request operation, deterministic request generation, directed disconnections, distance along the fastest path, external-scenario input and the exact packaged sample/scenario scope.

The separate case audit checks every passenger/vehicle output, all 160 daily records, model convergence, exact Tobit joins, source-forecast reproduction, common-random-number accounting and the final 208-DMU comparison. Run from the toolkit root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tests.verify_case --run-dir outputs/verified_case
```

## Application limits

Successful execution establishes software and data consistency for the included case. It does not establish causal effects, validate forecasts in newly served locations, update the source cost assumptions or reproduce the legacy simulator's trajectories. Local calibration and an explicit review of service definitions remain necessary when adapting the framework. No catchment analysis is performed or required by the packaged workflow.
