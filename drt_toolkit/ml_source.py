"""OD/hour demand: grouped calibration, regularized hurdle and direct models.

Estimate and validate a demand model using the prepared training data.
From the toolkit root, use the train-ml stage with a new run ID.
For scenario forecasting, use 04_Demand_Prediction.ipynb and the saved model.
"""
from pathlib import Path
import argparse
import json
import warnings
import hashlib

import numpy as np
import pandas as pd
import joblib
from xgboost import XGBClassifier, XGBRegressor
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import GammaRegressor
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    average_precision_score, roc_auc_score, brier_score_loss,
    precision_recall_curve, precision_score, recall_score, fbeta_score,
    mean_absolute_error, mean_squared_error, mean_poisson_deviance,
)

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "ml"
SEED = 42
MINIMUM_RECALL = 0.50
N_JOBS = 4
SELECTION_METRIC = "RMSE"  # Alternatively "Poisson_deviance" or "MAE"; fix before testing.
USE_FR_SHARE = True  # Use historical fixed-route share available before prediction; exclude future information.
RUN_FR_SHARE_SENSITIVITY = True
PREDICTION_BATCH_SIZE = 20000

# Modest, predeclared search. All selection uses validation, never test.
CLASSIFIER_SPECS = [
    {"name": "depth2_unweighted", "max_depth": 2, "n_estimators": 300, "scale_pos_weight": 1.0},
    {"name": "depth2_weight5", "max_depth": 2, "n_estimators": 300, "scale_pos_weight": 5.0},
    {"name": "depth3_weight10", "max_depth": 3, "n_estimators": 400, "scale_pos_weight": 10.0},
]
MAGNITUDE_SPECS = [
    {"name": "tweedie_1.1", "kind": "xgb", "objective": "reg:tweedie", "tweedie_variance_power": 1.1, "max_depth": 3, "n_estimators": 500},
    {"name": "tweedie_1.5", "kind": "xgb", "objective": "reg:tweedie", "tweedie_variance_power": 1.5, "max_depth": 3, "n_estimators": 500},
    {"name": "tweedie_1.9", "kind": "xgb", "objective": "reg:tweedie", "tweedie_variance_power": 1.9, "max_depth": 3, "n_estimators": 500},
]
DIRECT_SPECS = []  # Use the hurdle Tweedie specification for demand prediction.


def read_data(path):
    for encoding in ("utf-8-sig", "cp950", "utf-16"):
        try:
            data = pd.read_csv(path, encoding=encoding)
            data.columns = data.columns.str.strip()
            return data
        except UnicodeError:
            continue
    raise ValueError(f"Cannot decode {path}")


def engineer_features(data, use_fr_share=None):
    """Whitelist inputs: never admit Trips, zero_trip, IDs or previous predictions."""
    use_fr_share = USE_FR_SHARE if use_fr_share is None else use_fr_share
    required = ["GridID_O", "GridID_D", "Hour", "ToCBD", "FromCBD", "euclidist", "DRTRoute", "FixedRoute"]
    if use_fr_share:
        required.append("FR_share")
    paired = ["School", "Shop", "Hospital", "TransportHub", "TotalPop000",
              "Elderly000", "HighSchoolStudent000", "Income_med_10k"]
    required += [f"{base}_{side}" for base in paired for side in ("O", "D")]
    missing = sorted(set(required) - set(data.columns))
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    for col in ["GridID_O", "GridID_D", "Hour"]:
        values = pd.to_numeric(data[col], errors="raise")
        if values.isna().any() or not np.isfinite(values).all() or (values % 1 != 0).any():
            raise ValueError(f"{col} must contain finite integers.")
    hour = pd.to_numeric(data["Hour"], errors="raise")
    if not hour.between(0, 23).all():
        raise ValueError("Hour must range from 0 to 23.")
    x = pd.DataFrame(index=data.index)
    for col in required:
        if col not in ["GridID_O", "GridID_D"]:
            x[col] = pd.to_numeric(data[col], errors="raise")
    for base in ["Amenity", "Income_ave", "Downtown"]:
        if all(f"{base}_{side}" in data for side in ("O", "D")):
            paired.append(base)
            for side in ("O", "D"):
                col = f"{base}_{side}"
                values = data[col]
                if base == "Downtown":
                    values = values.astype(str).str.upper().map(
                        {"TRUE": 1, "FALSE": 0, "1": 1, "0": 0, "1.0": 1, "0.0": 0}
                    )
                    if (data[col].notna() & values.isna()).any():
                        raise ValueError(f"Invalid boolean in {col}")
                x[col] = pd.to_numeric(values, errors="raise")
    if np.isinf(x.to_numpy(dtype=float)).any():
        raise ValueError("Inputs contain infinite values.")
    for flag in ["DRTRoute", "FixedRoute", "ToCBD", "FromCBD"] + (["FR_share"] if use_fr_share else []):
        if x[flag].isna().any() or not x[flag].isin([0, 1]).all():
            raise ValueError(f"{flag} must be a complete binary indicator.")
    if not ((x.DRTRoute + x.FixedRoute) == 1).all():
        raise ValueError("DRTRoute must equal 1 - FixedRoute.")
    x = x.drop(columns="FixedRoute")  # Exact complement already represented by DRTRoute.
    if (x["euclidist"].dropna() < 0).any():
        raise ValueError("Distance cannot be negative.")
    for harmonic in (1, 2):
        x[f"hour_sin_{harmonic}"] = np.sin(2 * np.pi * harmonic * hour / 24)
        x[f"hour_cos_{harmonic}"] = np.cos(2 * np.pi * harmonic * hour / 24)
    x["morning_peak"] = hour.between(7, 9).astype(int)
    x["midday"] = hour.between(11, 14).astype(int)
    x["evening_peak"] = hour.between(16, 18).astype(int)
    x["late_evening"] = hour.between(19, 22).astype(int)
    x["log_distance"] = np.log1p(x["euclidist"])
    for base in paired:
        x[f"{base}_D_minus_O"] = x[f"{base}_D"] - x[f"{base}_O"]
    x["population_interaction"] = x["TotalPop000_O"] * x["TotalPop000_D"]
    x["gravity_population"] = (x["TotalPop000_O"] + .001) * (x["TotalPop000_D"] + .001) / (x["euclidist"] + .5) ** 2
    for purpose, population in [("School", "HighSchoolStudent000"),
                                ("Hospital", "Elderly000"), ("TransportHub", "TotalPop000")]:
        x[f"{purpose}D_populationO"] = x[f"{purpose}_D"] * x[f"{population}_O"]
        x[f"{purpose}O_populationD"] = x[f"{purpose}_O"] * x[f"{population}_D"]
    for variable in ["ToCBD", "FromCBD", "School_O", "School_D", "Shop_O", "Shop_D", "TransportHub_O", "TransportHub_D"]:
        for time in ["morning_peak", "evening_peak"]:
            x[f"{variable}_{time}"] = x[variable] * x[time]
    # Exact cross-population interactions in the attached GAM.
    x["TransportHub_O_Elderly000_D"] = x.TransportHub_O * x.Elderly000_D
    x["TransportHub_D_Elderly000_O"] = x.TransportHub_D * x.Elderly000_O
    x["DRTRoute_euclidist"] = x.DRTRoute * x.euclidist
    x["DRTRoute_log_distance"] = x.DRTRoute * x.log_distance
    if use_fr_share:
        x["DRTRoute_FR_share"] = x.DRTRoute * x.FR_share

    # ML counterparts of s(Hour, by=...) and ti(Hour, Shop_*).
    # These are cyclic products; trees learn nonlinearities, not an identical GAM fit.
    x = x.copy()  # Consolidate blocks before the next feature group (batch performance).
    for variable in ["FromCBD", "ToCBD", "TransportHub_O", "TransportHub_D", "Shop_O", "Shop_D", "DRTRoute"]:
        for harmonic in (1, 2):
            for basis in ("sin", "cos"):
                name = f"hour_{basis}_{harmonic}"
                x[f"{name}_{variable}"] = x[name] * x[variable]
        x[f"Hour_{variable}"] = (hour - 14) / 8 * x[variable]
    for side in ("O", "D"):
        pop = x[f"TotalPop000_{side}"].to_numpy(dtype=float)
        for group in ["Elderly", "HighSchoolStudent"]:
            values = x[f"{group}000_{side}"].to_numpy(dtype=float)
            x[f"{group}_share_{side}"] = np.divide(values, pop, out=np.zeros(len(x)), where=pop > 0)
        x[f"zero_population_{side}"] = (pop == 0).astype(int)
        for subtype in ["elementary", "junior", "senior"]:
            column = f"{subtype}_{side}"
            if column in data:
                x[column] = pd.to_numeric(data[column], errors="raise")
                for peak in ["morning_peak", "evening_peak"]:
                    x[f"{column}_{peak}"] = x[column] * x[peak]
        for variable in [f"TotalPop000_{side}", f"Income_med_10k_{side}", f"Elderly000_{side}"]:
            x[f"DRTRoute_{variable}"] = x.DRTRoute * x[variable]
        x[f"Hospital_{side}_Elderly_share_{side}"] = x[f"Hospital_{side}"] * x[f"Elderly_share_{side}"]
    x["elderly_share_D_minus_O"] = x.Elderly_share_D - x.Elderly_share_O
    x["student_share_D_minus_O"] = x.HighSchoolStudent_share_D - x.HighSchoolStudent_share_O
    x["inverse_distance"] = 1 / (x.euclidist + .5)
    return x.copy()


def pair_groups(data):
    a = pd.to_numeric(data["GridID_O"], errors="raise").astype("int64").astype(str).to_numpy()
    b = pd.to_numeric(data["GridID_D"], errors="raise").astype("int64").astype(str).to_numpy()
    return np.where(a <= b, a + "|" + b, b + "|" + a)


def split_data(x, y, groups):
    outer = GroupShuffleSplit(n_splits=1, test_size=.20, random_state=SEED)
    develop, test = next(outer.split(x, y, groups))
    inner = GroupShuffleSplit(n_splits=1, test_size=.25, random_state=SEED)
    tr, va = next(inner.split(x.iloc[develop], y.iloc[develop], groups[develop]))
    train, valid = develop[tr], develop[va]
    sets = [set(groups[idx]) for idx in (train, valid, test)]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    for name, idx in [("train", train), ("validation", valid), ("test", test)]:
        positive = int((y.iloc[idx] > 0).sum())
        print(f"{name}: {len(idx)} rows; {positive} positives", flush=True)
        if positive < 10 or positive == len(idx):
            raise ValueError(f"Insufficient classes in {name} split.")
    return train, valid, test


def calibrated_classifier(x, binary, groups, spec):
    splits = list(StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED).split(x, binary, groups))
    for tr, ca in splits:
        if len(np.unique(binary.iloc[tr])) != 2 or len(np.unique(binary.iloc[ca])) != 2:
            raise ValueError("Calibration folds need both classes.")
        assert not (set(groups[tr]) & set(groups[ca]))
    params = {key: value for key, value in spec.items() if key != "name"}
    base = make_pipeline(
        SimpleImputer(strategy="median", keep_empty_features=True),
        XGBClassifier(**params, objective="binary:logistic", eval_metric="logloss",
                      learning_rate=.04, min_child_weight=10, subsample=.85,
                      colsample_bytree=.85, reg_alpha=.05, reg_lambda=10,
                      tree_method="hist", random_state=SEED, n_jobs=N_JOBS),
    )
    # Each member is fitted and calibrated on disjoint grid-pair groups.
    model = CalibratedClassifierCV(base, method="sigmoid", cv=splits, ensemble=True, n_jobs=1)
    model.fit(x, binary)
    return model


def magnitude_model(spec):
    if spec["kind"] == "mean":
        return DummyRegressor(strategy="mean")
    if spec["kind"] == "gamma":
        return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
                             StandardScaler(), GammaRegressor(alpha=spec["alpha"], max_iter=3000))
    params = {key: value for key, value in spec.items() if key not in ["kind", "name"]}
    return make_pipeline(
        SimpleImputer(strategy="median", keep_empty_features=True),
        XGBRegressor(**params, learning_rate=.04, min_child_weight=10,
                     reg_alpha=0, reg_lambda=10, subsample=.9, colsample_bytree=.85,
                     tree_method="hist", random_state=SEED, n_jobs=N_JOBS),
    )


def regression_metrics(actual, prediction):
    actual, prediction = np.asarray(actual), np.asarray(prediction)
    positive = actual > 0
    zero = ~positive
    return {
        "MAE": float(mean_absolute_error(actual, prediction)),
        "RMSE": float(np.sqrt(mean_squared_error(actual, prediction))),
        "WAPE": float(np.abs(actual - prediction).sum() / actual.sum()) if actual.sum() else np.nan,
        "Poisson_deviance": float(mean_poisson_deviance(actual, np.maximum(prediction, 1e-12))),
        "positive_MAE": float(np.abs(actual[positive] - prediction[positive]).mean()) if positive.any() else np.nan,
        "zero_MAE": float(prediction[zero].mean()) if zero.any() else np.nan,
        "actual_total": float(actual.sum()), "predicted_total": float(prediction.sum()),
    }


def occurrence_metrics(binary, probability, threshold):
    classified = probability >= threshold
    return {
        "PR_AUC": float(average_precision_score(binary, probability)),
        "ROC_AUC": float(roc_auc_score(binary, probability)) if len(np.unique(binary)) > 1 else np.nan,
        "Brier": float(brier_score_loss(binary, probability)),
        "precision": float(precision_score(binary, classified, zero_division=0)),
        "recall": float(recall_score(binary, classified, zero_division=0)),
        "F2": float(fbeta_score(binary, classified, beta=2, zero_division=0)),
        "observed_positive_fraction": float(np.mean(binary)),
        "mean_probability": float(np.mean(probability)),
    }


def select_threshold(binary, probability, minimum_recall):
    precision, recall, thresholds = precision_recall_curve(binary, probability)
    precision, recall = precision[:-1], recall[:-1]
    f2 = 5 * precision * recall / np.maximum(4 * precision + recall, 1e-15)
    eligible = np.flatnonzero(recall >= minimum_recall)
    if not len(eligible):
        raise ValueError("No threshold satisfies the required validation recall.")
    idx = eligible[np.argmax(f2[eligible])]
    return float(thresholds[idx])


def generation_features(data):
    """One feature vector per origin/hour; no destination count or pair features."""
    cols = ["TotalPop000_O", "Elderly000_O", "HighSchoolStudent000_O",
            "Income_med_10k_O", "Income_ave_O", "School_O", "Shop_O",
            "Hospital_O", "TransportHub_O", "Amenity_O", "elementary_O", "junior_O", "senior_O"]
    x = pd.DataFrame({c: pd.to_numeric(data[c], errors="raise") for c in cols if c in data}, index=data.index)
    if "Downtown_O" in data:
        x["Downtown_O"] = data.Downtown_O.astype(str).str.upper().map({"TRUE": 1, "FALSE": 0, "1": 1, "0": 0, "1.0": 1, "0.0": 0})
    hour = pd.to_numeric(data.Hour, errors="raise")
    x["Hour"] = hour
    for harmonic in [1, 2]:
        x[f"hour_sin_{harmonic}"] = np.sin(2 * np.pi * harmonic * hour / 24)
        x[f"hour_cos_{harmonic}"] = np.cos(2 * np.pi * harmonic * hour / 24)
    x["morning_peak"] = hour.between(7, 9).astype(int)
    x["evening_peak"] = hour.between(16, 18).astype(int)
    for variable in ["TotalPop000_O", "School_O", "Shop_O", "Hospital_O", "TransportHub_O"]:
        if variable in x:
            x[f"log_{variable}"] = np.log1p(x[variable])
            for basis in ["hour_sin_1", "hour_cos_1"]:
                x[f"{variable}_{basis}"] = x[variable] * x[basis]
    return x


def historical_drt_panel(data):
    """Complete recorded DRT OD/hour panel; missing recorded counts are zero."""
    drt = data.loc[data.DRTRoute == 1].copy()
    keys = ["GridID_O", "GridID_D", "Hour"]
    if drt.duplicated(keys).any():
        raise ValueError("Duplicate recorded DRT OD/hour rows.")
    hours = sorted(data.Hour.unique())
    static = drt.drop_duplicates(["GridID_O", "GridID_D"]).drop(columns=["Hour", "Trips", "zero_trip"], errors="ignore")
    panel = static.merge(pd.DataFrame({"Hour": hours}), how="cross")
    panel = panel.merge(drt[keys + ["Trips"]], on=keys, how="left", validate="one_to_one")
    panel["Trips"] = panel.Trips.fillna(0)
    panel["DRTRoute"], panel["FixedRoute"] = 1, 0
    return panel


def new_generation_model(spec):
    from sklearn.linear_model import TweedieRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor
    if spec["kind"] == "ridge":
        return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
            TweedieRegressor(power=spec["power"], alpha=spec["alpha"], link="log", max_iter=3000))
    return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
        HistGradientBoostingRegressor(loss="poisson", max_iter=150, max_leaf_nodes=5,
            min_samples_leaf=25, l2_regularization=10, early_stopping=False, random_state=SEED))


MAX_DAILY_TOTAL_MULTIPLIER = 1.5  # Configured demand-growth ceiling; not an estimated confidence limit.


def regional_historical_panel(original):
    """Observed-market DRT counts, including known origins with no recorded DRT.

    These are historical ridership zeros, not assertions of zero latent demand.
    Unknown origins in dt_predict are never used as zero-labelled training data.
    """
    attributes = original.drop_duplicates("GridID_O")[["GridID_O"] + [c for c in original if c.endswith("_O") and c != "GridID_O"]]
    panel = attributes.merge(pd.DataFrame({"Hour": sorted(original.Hour.unique())}), how="cross")
    recorded = original.loc[original.DRTRoute == 1].groupby(["GridID_O", "Hour"], as_index=False).Trips.sum()
    panel = panel.merge(recorded, on=["GridID_O", "Hour"], how="left", validate="one_to_one")
    panel["Trips"] = panel.Trips.fillna(0)
    return panel


def fit_regional_demand_calibrator(generation, output_dir, max_multiplier=MAX_DAILY_TOTAL_MULTIPLIER):
    """Learn population-exposure trip rates, with origin-grouped validation."""
    from sklearn.model_selection import GroupKFold
    from sklearn.base import clone
    from sklearn.linear_model import TweedieRegressor
    exposure = pd.to_numeric(generation.TotalPop000_O, errors="raise").to_numpy(dtype=float)
    actual = generation.Trips.to_numpy(dtype=float)
    if ((exposure <= 0) & (actual > 0)).any():
        raise ValueError("Historical positive trips at zero-population origins require a different exposure model.")
    fit_mask = exposure > 0
    gx = generation_features(generation)
    columns = gx.columns[gx.loc[fit_mask].nunique(dropna=True) > 1].tolist()
    gx = gx[columns]
    rate = np.divide(actual, exposure, out=np.zeros(len(actual)), where=exposure > 0)
    scale = float(np.median(rate[rate > 0]))
    specs = [{"name": f"population_rate_power{p}_ridge{a}", "power": p, "alpha": a}
             for p in [1.0, 1.5] for a in [1.0, 10.0, 100.0]]
    folds = list(GroupKFold(n_splits=min(5, generation.GridID_O.nunique())).split(gx, groups=generation.GridID_O))
    results, estimators = [], {}
    for spec in specs:
        estimator = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
            TweedieRegressor(power=spec["power"], alpha=spec["alpha"], link="log", max_iter=3000))
        oof = np.zeros(len(actual))
        for train, valid in folds:
            train = train[fit_mask[train]]
            fitted = clone(estimator)
            fold_scale = float(np.median(rate[train][rate[train] > 0]))
            fitted.fit(gx.iloc[train], rate[train] / fold_scale, tweedieregressor__sample_weight=exposure[train])
            train_count = np.maximum(fitted.predict(gx.iloc[train]) * fold_scale, 0) * exposure[train]
            fold_calibration = actual[train].sum() / train_count.sum()
            oof[valid] = np.maximum(fitted.predict(gx.iloc[valid]) * fold_scale, 0) * exposure[valid] * fold_calibration
        results.append({"name": spec["name"], "OOF_total_ratio": float(oof.sum() / actual.sum()),
                        **regression_metrics(actual, oof)})
        estimators[spec["name"]] = estimator
    ranking = pd.DataFrame(results)
    eligible = ranking.loc[ranking.OOF_total_ratio <= max_multiplier]
    if eligible.empty:
        chosen = ranking.sort_values("OOF_total_ratio").iloc[0]
    else:
        chosen = eligible.sort_values("Poisson_deviance").iloc[0]
    ranking["selected"] = ranking.name == chosen["name"]
    ranking.to_csv(Path(output_dir) / "regional_rate_validation.csv", index=False)
    model = estimators[chosen["name"]]
    model.fit(gx.loc[fit_mask], rate[fit_mask] / scale, tweedieregressor__sample_weight=exposure[fit_mask])
    fitted_total = float((np.maximum(model.predict(gx) * scale, 0) * exposure).sum())
    if fitted_total <= 0:
        raise ValueError("Invalid fitted population-rate total.")
    calibrator = {
        "regional_rate_model": model, "regional_rate_features": columns, "regional_rate_scale": scale,
        "regional_rate_calibration": float(actual.sum() / fitted_total),
        "historical_daily_DRT_total": float(actual.sum()),
        "historical_DRT_by_hour": {int(h): float(v) for h,v in generation.groupby("Hour").Trips.sum().items()},
        "max_daily_total_multiplier": float(max_multiplier), "regional_rate_spec": chosen["name"],
        "regional_training_origins": sorted(generation.GridID_O.unique().tolist()),
    }
    report = {"rate_model": chosen["name"], "historical_total": float(actual.sum()),
        "fitted_population_rate_total_before_calibration": fitted_total,
        "historical_calibration_factor": calibrator["regional_rate_calibration"],
        "daily_multiplier_ceiling": float(max_multiplier),
        "daily_ceiling": float(actual.sum() * max_multiplier),
        "historical_market_origins": int(generation.GridID_O.nunique()),
        "origins_with_any_recorded_DRT": int((generation.groupby("GridID_O").Trips.sum() > 0).sum()),
        "ceiling_source": "Configured demand-growth ceiling; not estimated from data",
        "evaluation": "5-fold held-out origins; rate scale and count calibration learned within each training fold"}
    (Path(output_dir) / "regional_rate_training.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fit_table = generation[["GridID_O", "Hour", "Trips", "TotalPop000_O"]].copy()
    fit_table["calibrated_predicted_total"] = np.maximum(model.predict(gx) * scale, 0) * exposure * calibrator["regional_rate_calibration"]
    fit_table.to_csv(Path(output_dir) / "regional_historical_fit.csv", index=False)
    return calibrator


def calibrate_regional_total(bundle, data, result):
    if "regional_rate_model" not in bundle:
        return result
    origins = data.drop_duplicates(["GridID_O", "Hour"])
    exposure = pd.to_numeric(origins.TotalPop000_O, errors="raise").to_numpy(dtype=float)
    if not np.isfinite(exposure).all() or (exposure < 0).any():
        raise ValueError("Invalid population exposure.")
    x = generation_features(origins)[bundle["regional_rate_features"]]
    rate = np.maximum(bundle["regional_rate_model"].predict(x) * bundle["regional_rate_scale"], 0)
    learned_total = float((rate * exposure).sum() * bundle["regional_rate_calibration"])
    hours = set(int(h) for h in origins.Hour.unique())
    baseline = sum(bundle["historical_DRT_by_hour"].get(h, 0) for h in hours)
    upper = float(baseline * bundle["max_daily_total_multiplier"])
    if "baseline_service_od" not in bundle:
        raise ValueError("Retrain deployment model to include baseline_service_od for service expansion.")
    # Preserve observed trips only when their OD/hour remains serviceable.
    keys = ["GridID_O", "GridID_D", "Hour"]
    history = bundle["baseline_service_od"]
    retained = history.merge(data[keys].drop_duplicates(), on=keys, how="inner", validate="one_to_one")
    retained_baseline = float(retained.Trips.sum())
    # Existing DRT origin population is already represented by baseline demand.
    # Estimate extra demand only once for newly covered origin/hour exposure.
    is_new = ~origins.GridID_O.isin(bundle["baseline_service_origins"])
    extra = float((rate * exposure * is_new.to_numpy()).sum() * bundle["regional_rate_calibration"])
    headroom = baseline * max(bundle["max_daily_total_multiplier"] - 1, 0)
    # Bounded, diminishing marginal response; slope at zero equals one.
    # This structural expansion assumption is not a learned causal effect.
    increment = float(-headroom * np.expm1(-extra / headroom)) if headroom > 0 else 0.0
    forecast = min(retained_baseline + increment, upper)
    raw_profile_total = float(result.predicted_trips.sum())
    if raw_profile_total <= 0 and forecast > 0:
        raise ValueError("Cannot allocate positive regional demand to an empty OD profile.")
    factor = forecast / raw_profile_total if raw_profile_total > 0 else 0.0
    result["raw_profile_trips"] = result.predicted_trips
    result["raw_profile_origin_hour_total"] = result.origin_hour_total
    result["predicted_trips"] *= factor
    result["origin_hour_total"] *= factor
    result.attrs["demand_calibration"] = {
        "raw_OD_profile_total": raw_profile_total, "population_rate_unbounded_total": learned_total,
        "historical_matching_hours_total": baseline, "max_multiplier": bundle["max_daily_total_multiplier"],
        "research_ceiling": upper, "ceiling_applied": bool(retained_baseline + extra > upper),
        "total_method": "retained observed baseline plus saturating population-rate increment",
        "retained_baseline_total": retained_baseline,
        "new_origin_population_rate_increment": extra,
        "bounded_increment": increment,
        "saturation_applied": bool(extra > 0 and increment < extra),
        "baseline_OD_coverage_fraction": retained_baseline / baseline if baseline > 0 else None,
        "final_predicted_total": forecast, "OD_profile_scale_factor": factor,
        "rate_model": bundle["regional_rate_spec"],
        "origin_count": int(origins.GridID_O.nunique()),
        "population_unique_origins": float(origins.drop_duplicates("GridID_O").TotalPop_O.sum()),
        "note": "OD shares preserved. Baseline retention and saturating service expansion are explicit scenario assumptions, not empirically identified causal uplift."
    }
    return result


def normalize_od_predictions(bundle, data, result):
    keys = ["GridID_O", "Hour"]
    origins = data.drop_duplicates(keys).copy()
    gx = generation_features(origins)[bundle["generation_features"]]
    volumes = np.maximum(bundle["generation"].predict(gx) * bundle["generation_scale"], 0)
    origins = origins[keys].copy()
    origins["origin_hour_total"] = volumes
    result = result.merge(origins, on=keys, how="left", validate="many_to_one", sort=False)
    totals = result.groupby(keys)["od_attraction_score"].transform("sum")
    size = result.groupby(keys)["od_attraction_score"].transform("size")
    result["destination_probability"] = np.divide(result.od_attraction_score.to_numpy(), totals.to_numpy(),
        out=1 / size.to_numpy(dtype=float), where=totals.to_numpy() > 0)
    result["predicted_trips"] = result.origin_hour_total * result.destination_probability
    result = calibrate_regional_total(bundle, data, result)
    result["thresholded_trips"] = np.where(result.calibrated_probability_positive >= bundle["threshold"], result.predicted_trips, 0)
    result["predicted_positive"] = (result.calibrated_probability_positive >= bundle["threshold"]).astype(int)
    result["training_hour_covered"] = result.Hour.isin(bundle["training_hours"])
    result["hour_extrapolation"] = ~result.training_hour_covered
    result["origin_seen_in_training"] = result.GridID_O.isin(bundle["training_origins"])
    grouped = result.groupby(keys).agg(total=("predicted_trips", "sum"), generated=("origin_hour_total", "first"), p=("destination_probability", "sum"))
    if not np.allclose(grouped.total, grouped.generated) or not np.allclose(grouped.p, 1):
        raise AssertionError("Origin/hour demand was not conserved.")
    if "Trips" not in data:
        result = result.rename(columns={"calibrated_probability_positive": "od_occurrence_score",
            "conditional_trips": "od_positive_magnitude_score", "predicted_positive": "od_score_above_threshold"})
    return result


def attraction_scores(bundle, data):
    features = engineer_features(data, use_fr_share=bundle["use_fr_share"])[bundle["features"]]
    probability = bundle["classifier"].predict_proba(features)[:, 1]
    magnitude = np.maximum(bundle["magnitude"].predict(features) * bundle["target_scale"], 0)
    cols = [c for c in ["GridID_O", "GridID_D", "Hour", "FixedRoute", "DRTRoute", "FR_share", "Trips"] if c in data]
    result = data[cols].copy()
    result["calibrated_probability_positive"] = probability
    result["conditional_trips"] = magnitude
    result["od_attraction_score"] = probability * magnitude
    return result


def predict_bundle(bundle, data, allow_hour_extrapolation=False):
    if not (data.DRTRoute == 1).all() or not (data.FixedRoute == 0).all():
        raise ValueError("This revised model forecasts DRT demand only.")
    if data.duplicated(["GridID_O", "GridID_D", "Hour"]).any():
        raise ValueError("OD/hour must be unique; duplicate matrix rows are not new demand.")
    uncovered = set(data.Hour) - set(bundle["training_hours"])
    if uncovered and not allow_hour_extrapolation:
        raise ValueError(f"Untrained hours: {sorted(uncovered)}")
    return normalize_od_predictions(bundle, data, attraction_scores(bundle, data))


def predict_in_batches(bundle, data, batch_size=PREDICTION_BATCH_SIZE, allow_hour_extrapolation=False):
    if not (data.DRTRoute == 1).all() or not (data.FixedRoute == 0).all():
        raise ValueError("New data must describe DRT.")
    if data.duplicated(["GridID_O", "GridID_D", "Hour"]).any():
        raise ValueError("Duplicate OD/hour rows in full matrix.")
    uncovered = set(data.Hour) - set(bundle["training_hours"])
    if uncovered and not allow_hour_extrapolation:
        raise ValueError(f"Untrained hours: {sorted(uncovered)}")
    batches = []
    for start in range(0, len(data), batch_size):
        part = attraction_scores(bundle, data.iloc[start:start + batch_size])
        part.insert(0, "input_row", np.arange(start, start + len(part)))
        batches.append(part)
        if start % (10 * batch_size) == 0:
            print(f"OD scoring: {start + len(part):,}/{len(data):,}", flush=True)
    # Normalize across the ENTIRE matrix, never independently per batch.
    return normalize_od_predictions(bundle, data, pd.concat(batches, ignore_index=True))


def fit_workflow(data_path, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    original = read_data(data_path)
    data = historical_drt_panel(original)
    if not np.isfinite(data.Trips).all() or (data.Trips < 0).any():
        raise ValueError("Invalid DRT targets.")
    generation = data.groupby(["GridID_O", "Hour"], as_index=False).Trips.sum()
    origin_attrs = data.drop_duplicates("GridID_O")[["GridID_O"] + [c for c in data if c.endswith("_O") and c != "GridID_O"]]
    generation = generation.merge(origin_attrs, on="GridID_O", validate="many_to_one")
    origins = np.sort(generation.GridID_O.unique())
    outer = GroupShuffleSplit(n_splits=1, test_size=.20, random_state=SEED)
    dev_idx, test_idx = next(outer.split(generation, groups=generation.GridID_O))
    inner = GroupShuffleSplit(n_splits=1, test_size=.25, random_state=SEED)
    tr, va = next(inner.split(generation.iloc[dev_idx], groups=generation.iloc[dev_idx].GridID_O))
    gen_train, gen_valid = dev_idx[tr], dev_idx[va]
    train_origins = set(generation.iloc[gen_train].GridID_O)
    valid_origins = set(generation.iloc[gen_valid].GridID_O)
    test_origins = set(generation.iloc[test_idx].GridID_O)
    gx = generation_features(generation)
    gen_cols = gx.columns[gx.iloc[gen_train].nunique(dropna=True) > 1].tolist()
    gx = gx[gen_cols]
    gy = generation.Trips
    gen_scale = float(gy.iloc[gen_train][gy.iloc[gen_train] > 0].median())
    generator_specs = [{"name": f"rate_power{p}_ridge{a}", "kind": "ridge", "power": p, "alpha": a}
                       for p in [1.0, 1.5] for a in [1.0, 10.0, 100.0]]
    generator_specs += [{"name": "shallow_poisson_tree", "kind": "tree"}]
    gen_models, gen_rows = {}, []
    for spec in generator_specs:
        model = new_generation_model(spec)
        model.fit(gx.iloc[gen_train], gy.iloc[gen_train] / gen_scale)
        pred = np.maximum(model.predict(gx.iloc[gen_valid]) * gen_scale, 0)
        gen_models[spec["name"]] = model
        gen_rows.append({"name": spec["name"], **regression_metrics(gy.iloc[gen_valid], pred)})
    gen_ranking = pd.DataFrame(gen_rows).sort_values("RMSE")
    gen_ranking.to_csv(output_dir / "generation_validation.csv", index=False)
    selected_generator = gen_ranking.iloc[0]["name"]
    generator = gen_models[selected_generator]
    print(f"DRT history total={data.Trips.sum():.4f}; origin grids={len(origins)}; generator={selected_generator}", flush=True)
    train = np.flatnonzero(data.GridID_O.isin(train_origins))
    valid = np.flatnonzero(data.GridID_O.isin(valid_origins))
    test = np.flatnonzero(data.GridID_O.isin(test_origins))
    x = engineer_features(data, use_fr_share=USE_FR_SHARE)
    features = x.columns[x.iloc[train].nunique(dropna=True) > 1].tolist()
    x = x[features]
    y, binary = data.Trips, (data.Trips > 0).astype(int)
    scale = float(y.iloc[train][y.iloc[train] > 0].median())
    classifiers, magnitudes, candidates, cls_rows = {}, {}, [], []
    for spec in CLASSIFIER_SPECS:
        print("OD occurrence scoring:", spec["name"], flush=True)
        classifier = calibrated_classifier(x.iloc[train], binary.iloc[train], data.iloc[train].GridID_O.to_numpy(), spec)
        classifiers[spec["name"]] = classifier
        probability = classifier.predict_proba(x.iloc[valid])[:, 1]
        cls_rows.append({"name": spec["name"], "PR_AUC": average_precision_score(binary.iloc[valid], probability), "Brier": brier_score_loss(binary.iloc[valid], probability)})
    for spec in MAGNITUDE_SPECS:
        if spec.get("objective") != "reg:tweedie":
            continue
        magnitude = magnitude_model(spec)
        positive = train[y.iloc[train].to_numpy() > 0]
        magnitude.fit(x.iloc[positive], y.iloc[positive] / scale)
        magnitudes[spec["name"]] = magnitude
        for clf_spec in CLASSIFIER_SPECS:
            classifier = classifiers[clf_spec["name"]]
            bundle = {"classifier": classifier, "magnitude": magnitude, "direct": None,
                "features": features, "target_scale": scale, "threshold": .5,
                "generation": generator, "generation_features": gen_cols, "generation_scale": gen_scale,
                "training_hours": sorted(data.Hour.unique().tolist()), "training_origins": sorted(train_origins),
                "use_fr_share": USE_FR_SHARE}
            predictions = predict_bundle(bundle, data.iloc[valid])
            candidates.append({"name": f"{clf_spec['name']}/{spec['name']}", "classifier": clf_spec["name"],
                "magnitude": spec["name"], **regression_metrics(y.iloc[valid], predictions.predicted_trips)})
    ranking = pd.DataFrame(candidates).sort_values("RMSE")
    ranking.to_csv(output_dir / "validation_candidates.csv", index=False)
    pd.DataFrame(cls_rows).to_csv(output_dir / "validation_occurrence.csv", index=False)
    chosen = ranking.iloc[0]
    classifier, magnitude = classifiers[chosen["classifier"]], magnitudes[chosen["magnitude"]]
    threshold = select_threshold(binary.iloc[valid], classifier.predict_proba(x.iloc[valid])[:, 1], MINIMUM_RECALL)
    eval_bundle = {"classifier": classifier, "magnitude": magnitude, "direct": None,
        "features": features, "target_scale": scale, "threshold": threshold,
        "generation": generator, "generation_features": gen_cols, "generation_scale": gen_scale,
        "training_hours": sorted(data.Hour.unique().tolist()), "training_origins": sorted(train_origins),
        "use_fr_share": USE_FR_SHARE, "framework": "origin-hour generation plus normalized hurdle OD distribution"}
    test_results = predict_bundle(eval_bundle, data.iloc[test])
    test_results["prediction_scope"] = "held_out_origins_DRT"
    gen_test_pred = np.maximum(generator.predict(gx.iloc[test_idx]) * gen_scale, 0)
    report = {"selected": str(chosen["name"]),
        "regression": regression_metrics(y.iloc[test], test_results.predicted_trips),
        "generation": regression_metrics(gy.iloc[test_idx], gen_test_pred),
        "occurrence": occurrence_metrics(binary.iloc[test], test_results.calibrated_probability_positive, threshold),
        "zero_baseline": regression_metrics(y.iloc[test], np.zeros(len(test)))}
    test_results.to_csv(output_dir / "test_predictions.csv", index=False, encoding="utf-8-sig")
    (output_dir / "test_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame([{"FixedRoute": 0, "service": "DRT", "rows": len(test), **report["regression"]}]).to_csv(output_dir / "test_metrics_by_service.csv", index=False)
    joblib.dump(eval_bundle, output_dir / "evaluation_model.joblib")
    splits = data[["GridID_O", "GridID_D", "Hour", "FixedRoute"]].copy()
    splits["group"] = data.GridID_O
    splits["split"] = ""
    for label, idx in [("train", train), ("validation", valid), ("test", test)]:
        splits.loc[idx, "split"] = label
    splits.to_csv(output_dir / "split_assignments.csv", index=False)
    hourly = test_results.groupby("Hour", as_index=False).agg(actual_trips=("Trips", "sum"), predicted_trips=("predicted_trips", "sum"), thresholded_trips=("thresholded_trips", "sum"))
    hourly.to_csv(output_dir / "hourly_test_comparison.csv", index=False)
    gen_spec = next(s for s in generator_specs if s["name"] == selected_generator)
    clf_spec = next(s for s in CLASSIFIER_SPECS if s["name"] == chosen["classifier"])
    mag_spec = next(s for s in MAGNITUDE_SPECS if s["name"] == chosen["magnitude"])
    final_gen = new_generation_model(gen_spec)
    final_gen.fit(gx, gy / gen_scale)
    final_classifier = calibrated_classifier(x, binary, data.GridID_O.to_numpy(), clf_spec)
    final_magnitude = magnitude_model(mag_spec)
    final_magnitude.fit(x.loc[y > 0], y.loc[y > 0] / scale)
    final_bundle = {**eval_bundle, "generation": final_gen, "classifier": final_classifier,
                    "magnitude": final_magnitude, "training_origins": origins.tolist()}
    final_bundle.update(fit_regional_demand_calibrator(regional_historical_panel(original), output_dir, MAX_DAILY_TOTAL_MULTIPLIER))
    baseline_od = original.loc[original.DRTRoute == 1].groupby(["GridID_O", "GridID_D", "Hour"], as_index=False).Trips.sum()
    final_bundle["baseline_service_od"] = baseline_od
    final_bundle["baseline_service_origins"] = sorted(baseline_od.GridID_O.unique().tolist())
    final_bundle["training_source_sha256"] = hashlib.sha256(Path(data_path).read_bytes()).hexdigest()
    final_bundle["bundle_schema_version"] = 2
    joblib.dump(final_bundle, output_dir / "deployment_model.joblib")
    export_feature_importance(final_bundle, output_dir)
    all_results = predict_bundle(final_bundle, data)
    all_results["prediction_scope"] = "historical_DRT_fitted_values"
    all_results.to_csv(output_dir / "all_predictions_for_mapping.csv", index=False, encoding="utf-8-sig")
    generation_out = generation[["GridID_O", "Hour", "Trips"]].copy()
    generation_out["predicted_total"] = np.maximum(final_gen.predict(gx) * gen_scale, 0)
    generation_out.to_csv(output_dir / "historical_origin_hour_totals.csv", index=False)
    metadata = {"framework": final_bundle["framework"], "selected": str(chosen["name"]),
        "magnitude_model": str(chosen["magnitude"]), "generation_model": selected_generator,
        "features": features, "generation_features": gen_cols,
        "training_origins": origins.tolist(), "training_hours": final_bundle["training_hours"],
        "use_fr_share": USE_FR_SHARE, "FR_share_provenance": "Historical fixed-route share available before prediction",
        "n_rows": len(original), "DRT_recorded_rows": int((original.DRTRoute == 1).sum()),
        "DRT_panel_rows": len(data), "DRT_actual_total": float(data.Trips.sum()),
        "all_service_actual_total": float(original.Trips.sum()), "test_rows": len(test),
        "source_sha256": hashlib.sha256(Path(data_path).read_bytes()).hexdigest(),
        "row_key": ["GridID_O", "GridID_D", "Hour"], "data_has_dates": False,
        "note": "Unseen door-to-door origins are spatial extrapolation. Totals are learned origin/hour demand, not a fixed historical budget or OD row count."}
    metadata.update({"regional_rate_model": final_bundle["regional_rate_spec"], "max_daily_total_multiplier": MAX_DAILY_TOTAL_MULTIPLIER, "historical_daily_DRT_total": final_bundle["historical_daily_DRT_total"], "total_ceiling_source": "Configured demand-growth ceiling"})
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return {"data": data, "test_results": test_results, "all_results": all_results,
            "hourly_comparison": hourly, "model_bundle": final_bundle,
            "test_report": report, "validation_ranking": ranking, "output_dir": output_dir}


def export_feature_importance(bundle, output_dir):
    """Separate model-specific importances; none are causal effects."""
    output_dir = Path(output_dir)
    occurrence = np.mean([
        member.estimator.named_steps["xgbclassifier"].feature_importances_
        for member in bundle["classifier"].calibrated_classifiers_
    ], axis=0)
    pd.DataFrame({"feature": bundle["features"], "importance": occurrence}).sort_values(
        "importance", ascending=False
    ).to_csv(output_dir / "occurrence_feature_importance.csv", index=False)
    if bundle["direct"] is not None:
        pd.DataFrame({"feature": bundle["features"], "importance": bundle["direct"].feature_importances_}).sort_values(
            "importance", ascending=False
        ).to_csv(output_dir / "demand_feature_importance.csv", index=False)
    magnitude = bundle["magnitude"]
    if hasattr(magnitude, "named_steps") and "xgbregressor" in magnitude.named_steps:
        pd.DataFrame({"feature": bundle["features"], "importance": magnitude.named_steps["xgbregressor"].feature_importances_}).sort_values(
            "importance", ascending=False
        ).to_csv(output_dir / "conditional_feature_importance.csv", index=False)
    elif hasattr(magnitude, "named_steps") and "gammaregressor" in magnitude.named_steps:
        pd.DataFrame({"feature": bundle["features"], "standardized_coefficient": magnitude.named_steps["gammaregressor"].coef_}).to_csv(
            output_dir / "conditional_gamma_coefficients.csv", index=False)


def attach_coordinates(results, grid_path):
    grids = pd.read_csv(grid_path, sep=None, engine="python")
    grids.columns = grids.columns.str.strip()
    grids = grids[["GridID", "X", "Y"]].copy()
    for col in grids:
        grids[col] = pd.to_numeric(grids[col], errors="raise")
    if grids["GridID"].duplicated().any() or grids.isna().any().any():
        raise ValueError("Grid coordinates require unique IDs and complete values.")
    # Existing source labels X/Y as longitude/latitude. Reject projected coordinates.
    if not grids["X"].between(-180, 180).all() or not grids["Y"].between(-90, 90).all():
        raise ValueError("SA Grid X/Y must be longitude/latitude; transform projected coordinates first.")
    result = results.copy()
    for side in ("O", "D"):
        source = grids.rename(columns={"GridID": f"GridID_{side}", "X": f"longitude_{side}", "Y": f"latitude_{side}"})
        result = result.merge(source, on=f"GridID_{side}", how="left", validate="many_to_one")
    return result


def plot_od_map(results, grid_path, value_col="predicted_trips", hour=7, top_n=100,
                output=None, title="OD demand"):
    import folium
    import html
    from folium.plugins import PolyLineTextPath
    from branca.colormap import linear
    selected = results.loc[results["Hour"] == hour].copy()
    selected = selected.loc[selected[value_col] > 0]
    if top_n is not None:
        selected = selected.nlargest(top_n, value_col)
    selected = attach_coordinates(selected, grid_path)
    coords = ["longitude_O", "latitude_O", "longitude_D", "latitude_D"]
    missing = selected[coords].isna().any(axis=1)
    if missing.any():
        warnings.warn(f"{missing.sum()} map flows lack grid coordinates and were omitted.")
        selected = selected.loc[~missing].copy()
    if selected.empty:
        return None
    lat = pd.concat([selected.latitude_O, selected.latitude_D])
    lon = pd.concat([selected.longitude_O, selected.longitude_D])
    m = folium.Map(location=[lat.mean(), lon.mean()], tiles="OpenStreetMap", zoom_start=11)
    values = selected[value_col]
    colours = linear.YlOrRd_09.scale(float(values.min()), float(max(values.max(), values.min() + 1e-9)))
    colours.caption = f"{title}, hour {hour} (average daily Trips)"
    colours.add_to(m)
    flows = folium.FeatureGroup(name="OD flows and direction", show=True).add_to(m)
    for _, row in selected.iterrows():
        scope = row.get("prediction_scope", "new_data")
        tip = f"{int(row.GridID_O)} → {int(row.GridID_D)}<br>Hour: {hour}<br>{value_col}: {row[value_col]:.5f}<br>Scope: {html.escape(str(scope))}"
        if row.GridID_O == row.GridID_D:
            folium.CircleMarker([row.latitude_O, row.longitude_O], radius=6,
                color=colours(row[value_col]), fill=True, fill_opacity=.7,
                tooltip=tip + "<br>Within-grid OD").add_to(flows)
        else:
            line = folium.PolyLine([[row.latitude_O, row.longitude_O], [row.latitude_D, row.longitude_D]],
                                  color=colours(row[value_col]), weight=1 + 5 * np.sqrt(row[value_col] / values.max()),
                                  opacity=.75, tooltip=tip).add_to(flows)
            PolyLineTextPath(line, "  ➜  ", repeat=True, offset=5,
                             attributes={"fill": colours(row[value_col]), "font-size": "12"}).add_to(flows)
    for side, label, colour in [("O", "Origins", "#2563eb"), ("D", "Destinations", "#16a34a")]:
        layer = folium.FeatureGroup(name=label, show=False).add_to(m)
        points = selected.drop_duplicates(f"GridID_{side}")
        for _, row in points.iterrows():
            folium.CircleMarker([row[f"latitude_{side}"], row[f"longitude_{side}"]],
                radius=4, color=colour, fill=True, fill_color=colour, fill_opacity=.8,
                tooltip=f"{label}: grid {int(row[f'GridID_{side}'])}").add_to(layer)
    folium.LayerControl(collapsed=False).add_to(m)
    banner = f'<div style="position:fixed;top:12px;left:55px;z-index:9999;background:white;padding:10px 14px;border:1px solid #aaa;border-radius:6px;font:14px sans-serif"><b>{html.escape(title)}</b><br>Hour: {hour:02d}:00–{hour:02d}:59<br>Displayed OD: {len(selected):,}<br>Displayed average-daily Trips: {values.sum():.4f}<br>Arrows: origin → destination</div>'
    m.get_root().html.add_child(folium.Element(banner))
    m.fit_bounds([[lat.min(), lon.min()], [lat.max(), lon.max()]])
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        m.save(str(output))
    return m


def export_predicted_od_map(hour, predictions_path=None, grid_path=None, output=None,
                            top_n=100, minimum_trips=0.0, service="DRT"):
    """Read saved FR_share predictions for one hour and return/save a Folium map.

    No model fitting or new inference. top_n=None displays all qualifying OD.
    """
    if isinstance(hour, (bool, np.bool_)):
        raise ValueError("Hour must be an integer from 0 to 23.")
    try:
        hour_number = float(hour)
    except (TypeError, ValueError):
        raise ValueError("Hour must be an integer from 0 to 23.") from None
    if not np.isfinite(hour_number) or hour_number % 1 or not 0 <= hour_number <= 23:
        raise ValueError("Hour must be an integer from 0 to 23.")
    hour = int(hour_number)
    if top_n is not None and (isinstance(top_n, bool) or not isinstance(top_n, (int, np.integer)) or top_n <= 0):
        raise ValueError("top_n must be a positive integer or None.")
    if not np.isfinite(minimum_trips) or minimum_trips < 0:
        raise ValueError("minimum_trips must be a finite nonnegative value.")
    if service not in ("DRT", "FixedRoute", "All"):
        raise ValueError("service must be DRT, FixedRoute or All.")
    result_dir = DEFAULT_ROOT / "optimized_results"
    predictions_path = Path(predictions_path) if predictions_path is not None else result_dir / "new_predictions.csv"
    grid_path = Path(grid_path) if grid_path is not None else DEFAULT_ROOT / "SA Grid.csv"
    if not predictions_path.is_file() or not grid_path.is_file():
        raise FileNotFoundError("Saved predictions and SA Grid.csv are required.")
    metadata_path = predictions_path.parent / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("use_fr_share") is not True:
            raise ValueError("This map requires the latest formal model with FR_share=True.")
        allowed_hours = metadata.get("training_hours", [])
        if allowed_hours and hour not in allowed_hours:
            raise ValueError(f"Hour {hour} is outside available trained hours: {allowed_hours}")
    selected = []
    available_hours = set()
    for chunk in pd.read_csv(predictions_path, encoding="utf-8-sig", chunksize=50000,
            usecols=["GridID_O", "GridID_D", "Hour", "FixedRoute", "predicted_trips"]):
        available_hours.update(chunk.Hour.unique().tolist())
        mask = chunk.Hour == hour
        if service != "All":
            mask &= chunk.FixedRoute == (0 if service == "DRT" else 1)
        if mask.any():
            selected.append(chunk.loc[mask])
    if hour not in available_hours:
        raise ValueError(f"No saved predictions for hour {hour}; available hours: {sorted(available_hours)}")
    if not selected:
        raise ValueError(f"No {service} predictions at hour {hour}.")
    flows = pd.concat(selected, ignore_index=True)
    flows = flows.groupby(["GridID_O", "GridID_D", "Hour"], as_index=False)["predicted_trips"].sum(min_count=1)
    flows = flows.loc[np.isfinite(flows.predicted_trips) & (flows.predicted_trips > minimum_trips)].copy()
    if flows.empty:
        raise ValueError(f"No OD exceeds minimum_trips={minimum_trips} at hour {hour}.")
    flows["prediction_scope"] = "new_data_deployment_FR_share"
    output = Path(output) if output is not None else predictions_path.parent / "predicted_od_maps" / f"predicted_OD_hour_{hour:02d}_{service}.html"
    map_object = plot_od_map(flows, grid_path, hour=hour, top_n=top_n, output=output,
                             title=f"{service} predicted OD (FR_share)")
    if map_object is None:
        raise ValueError("None of the selected OD could be mapped to coordinates.")
    print(f"Hour {hour}: {len(flows):,} qualifying OD; showing up to {top_n if top_n is not None else 'all'}.")
    print(f"Saved map: {output.resolve()}")
    return map_object


def plot_diagnostics(state):
    import matplotlib.pyplot as plt
    hourly = state["hourly_comparison"]
    test = state["test_results"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(hourly.Hour, hourly.actual_trips, "o-", label="Actual")
    axes[0].plot(hourly.Hour, hourly.predicted_trips, "s-", label="Expected")
    axes[0].set(xlabel="Hour", ylabel="Trips (original scale)", title="Held-out grid pairs")
    axes[0].legend()
    prec, rec, _ = precision_recall_curve(test.Trips > 0, test.calibrated_probability_positive)
    axes[1].plot(rec, prec, label="Occurrence model")
    axes[1].axhline((test.Trips > 0).mean(), ls="--", color="gray", label="Positive prevalence")
    axes[1].set(xlabel="Recall", ylabel="Precision", title="Held-out precision–recall")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(state["output_dir"] / "test_diagnostics.png", dpi=160)
    return fig




def prepare_deployment_bundle(data_dir, output_dir):
    """Load the saved deployment bundle; safely upgrade missing baseline metadata.

    The historical source hash and DRT hourly totals must match before upgrading.
    Never substitute an old in-memory model or an evaluation bundle.
    """
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    model_path = output_dir / "deployment_model.joblib"
    if not model_path.is_file():
        raise FileNotFoundError(f"Run training first: missing {model_path}")
    bundle = joblib.load(model_path)
    required = ["regional_rate_model", "regional_rate_features", "regional_rate_scale",
                "regional_rate_calibration", "historical_DRT_by_hour", "historical_daily_DRT_total",
                "max_daily_total_multiplier", "generation", "classifier", "magnitude"]
    missing = [key for key in required if key not in bundle]
    if missing:
        raise ValueError(f"Deployment model lacks {missing}. Execute the current helper and training cells first.")
    historical_path = data_dir / "dt_model.csv"
    digest = hashlib.sha256(historical_path.read_bytes()).hexdigest()
    saved_digest = bundle.get("training_source_sha256")
    metadata_path = output_dir / "metadata.json"
    if saved_digest is None and metadata_path.exists():
        saved_digest = json.loads(metadata_path.read_text(encoding="utf-8")).get("source_sha256")
    if saved_digest is None or saved_digest != digest:
        raise ValueError("dt_model.csv differs from the model training source or cannot be verified. Run the current training cell first.")
    if any(key not in bundle for key in ("baseline_service_od", "baseline_service_origins")):
        original = read_data(historical_path)
        od = original.loc[original.DRTRoute == 1].groupby(["GridID_O", "GridID_D", "Hour"], as_index=False).Trips.sum()
        totals = od.groupby("Hour").Trips.sum().to_dict()
        historical_hours = {int(k): float(v) for k,v in bundle["historical_DRT_by_hour"].items()}
        if not np.isclose(od.Trips.sum(), bundle["historical_daily_DRT_total"]) or set(totals) != set(historical_hours) or any(
                not np.isclose(value, historical_hours[int(hour)]) for hour,value in totals.items()):
            raise ValueError("Historical DRT totals do not match the saved model. Retrain before forecasting.")
        bundle["baseline_service_od"] = od
        bundle["baseline_service_origins"] = sorted(od.GridID_O.unique().tolist())
        bundle["training_source_sha256"] = digest
        bundle["bundle_schema_version"] = 2
        joblib.dump(bundle, model_path)
        print("Verified historical training data; added missing baseline service metadata to saved deployment model.")
    return bundle


def run_prediction_scenarios(bundle, data_dir, output_dir, scenarios=(200, 500)):
    """Write both radius scenarios; no target growth factor or matrix-row multiplier."""
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    needed = ("baseline_service_od", "baseline_service_origins", "regional_rate_model")
    if any(key not in bundle for key in needed):
        # Replace stale in-memory state before any expensive OD scoring.
        bundle = prepare_deployment_bundle(data_dir, output_dir)
    summaries = []
    for radius in scenarios:
        path = data_dir / f"dt_predict_{radius}.csv"
        data = read_data(path)
        result = predict_in_batches(bundle, data)
        report = result.attrs["demand_calibration"].copy()
        result["prediction_scope"] = f"door_to_door_{radius}m_scenario"
        result.to_csv(output_dir / f"new_predictions_{radius}.csv", index=False, encoding="utf-8-sig")
        result.groupby("Hour", as_index=False).predicted_trips.sum().to_csv(
            output_dir / f"new_hourly_predictions_{radius}.csv", index=False)
        result.groupby(["GridID_O", "Hour"], as_index=False).agg(
            generated_trips=("origin_hour_total", "first"), allocated_trips=("predicted_trips", "sum"),
            destination_probability_sum=("destination_probability", "sum")).to_csv(
                output_dir / f"new_origin_hour_totals_{radius}.csv", index=False)
        report.update({"radius_m": radius, "source": str(path.resolve()),
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(data)})
        (output_dir / f"demand_calibration_{radius}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (output_dir / f"prediction_manifest_{radius}.json").write_text(json.dumps({
            "source": report["source"], "sha256": report["sha256"], "rows": len(data),
            "use_fr_share": bundle["use_fr_share"], "total_method": report["total_method"]}, indent=2), encoding="utf-8")
        summaries.append(report)
    # Keep default files synchronized only if dt_predict.csv is byte-identical.
    default = data_dir / "dt_predict.csv"
    if default.exists():
        fingerprint = hashlib.sha256(default.read_bytes()).hexdigest()
        for report in summaries:
            if report["sha256"] == fingerprint:
                import shutil
                radius = report["radius_m"]
                for stem, extension in [("new_predictions", "csv"), ("new_hourly_predictions", "csv"),
                                        ("new_origin_hour_totals", "csv"), ("demand_calibration", "json"),
                                        ("prediction_manifest", "json")]:
                    shutil.copy2(output_dir / f"{stem}_{radius}.{extension}", output_dir / f"{stem}.{extension}")
                break
    table = pd.DataFrame(summaries)
    table.to_csv(output_dir / "scenario_comparison.csv", index=False, encoding="utf-8-sig")
    return table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_ROOT / "dt_model.csv")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "optimized_results")
    args = parser.parse_args()
    state = fit_workflow(args.data, args.output)
    plot_diagnostics(state)
    if all((args.data.parent / f"dt_predict_{r}.csv").exists() for r in (200, 500)):
        print(run_prediction_scenarios(state["model_bundle"], args.data.parent, args.output)[
            ["radius_m", "final_predicted_total"]].to_string(index=False))


if __name__ == "__main__":
    main()
