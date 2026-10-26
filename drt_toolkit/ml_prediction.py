"""Forecast with the packaged source ML implementation and verified deployment bundle."""
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from .common import file_hash,write_json


def predict_scenarios(cfg,out):
    if sklearn.__version__!='1.5.1' or xgboost.__version__!='2.1.0':
        raise ValueError('The bundled ML model requires scikit-learn==1.5.1 and xgboost==2.1.0. Install requirements.txt in an isolated environment.')
    from . import ml_source
    model_path=Path(cfg['paths']['ml_model'])
    expected=cfg['demand']['deployment_model_sha256']
    if file_hash(model_path)!=expected:
        raise ValueError('ML deployment bundle hash changed; review the model configuration explicitly')
    bundle=joblib.load(model_path)
    if file_hash(cfg['paths']['demand_training'])!=bundle.get('training_source_sha256'):
        raise ValueError('dt_model.csv does not match the training source recorded in the ML bundle')
    if bundle.get('bundle_schema_version')!=2:
        raise ValueError('Expected the verified version-2 deployment bundle')
    summaries=[]
    for radius in cfg['demand']['prediction_cases']:
        case=str(radius)
        source=Path(cfg['paths']['ml_features_'+case])
        data=ml_source.read_data(source)
        if data.duplicated(['Hour','GridID_O','GridID_D']).any():
            raise ValueError(f'Duplicate OD-hour prediction rows for {case}')
        if not (data.DRTRoute==1).all():
            raise ValueError('Scenario prediction features must describe the DRT service')
        result=ml_source.predict_in_batches(bundle,data)
        rates=result.predicted_trips.to_numpy(float)
        if not np.isfinite(rates).all() or (rates<0).any():
            raise ValueError('ML generated invalid demand')
        slim=result[['Hour','GridID_O','GridID_D','predicted_trips']].rename(columns={'predicted_trips':'PredTrips'})
        slim.to_csv(out/f'ml_demand_{case}.csv.gz',index=False,compression='gzip')
        slim.groupby('Hour',as_index=False).PredTrips.sum().to_csv(out/f'ml_hourly_{case}.csv',index=False)
        calibration=result.attrs['demand_calibration'].copy()
        calibration.update(case=case,source_sha256=file_hash(source),rows=len(data),model_sha256=expected)
        reference=cfg['paths'].get('reference_demand_'+case)
        if reference:
            old=pd.read_csv(reference)
            merged=slim.merge(old,on=['Hour','GridID_O','GridID_D'],suffixes=('_new','_reference'),validate='one_to_one')
            if len(merged)!=len(slim) or len(merged)!=len(old):
                raise ValueError('Reference forecast keys do not match regenerated forecasts')
            max_error=float((merged.PredTrips_new-merged.PredTrips_reference).abs().max())
            calibration['reference_max_abs_error']=max_error
            if max_error>1e-7:
                raise ValueError(f'Regenerated ML forecast differs from the source forecast: {max_error}')
        write_json(out/f'ml_calibration_{case}.json',calibration)
        summaries.append(dict(case=case,rows=len(slim),total_daily_demand=float(rates.sum()),
            reference_max_abs_error=calibration.get('reference_max_abs_error'),source_sha256=file_hash(source)))
        del data,result,slim
    pd.DataFrame(summaries).to_csv(out/'ml_prediction_summary.csv',index=False)
    write_json(out/'ml_runtime.json',dict(numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__,xgboost=xgboost.__version__,joblib=joblib.__version__))
