"""Audit the packaged real-data run without reading external source folders."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',default='outputs/verified_case');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=Path(a.run_dir)
    if not out.is_absolute():out=root/out
    cfg=json.loads((root/'config/case_study.json').read_text(encoding='utf-8'))
    historical=pd.read_csv(root/cfg['paths']['historical'])
    socio=pd.read_csv(root/cfg['paths']['tobit_explanatory'])
    scores=pd.read_csv(out/'historical_scores.csv')
    actual=pd.read_csv(out/'tobit_model_data.csv')
    assert len(historical)==len(socio)==len(scores)==len(actual)==200
    assert set(historical.Jurisdiction)==set(cfg['allowed_jurisdictions'])
    assert set(historical.ServiceID)==set(socio.ServiceID)==set(scores.DMU)==set(actual.ServiceID)
    joined=actual.merge(scores,left_on='ServiceID',right_on='DMU',suffixes=('_tobit','_dea'),validate='one_to_one')
    for c in ['MetaEff','GroupEff']:assert np.allclose(joined[c+'_tobit'],joined[c+'_dea'],rtol=0,atol=1e-12)
    # Legacy source scores are optional; current outcomes must match this run's DEA above.
    legacy_scores=[c for c in ['MetaEff','GroupEff'] if c in socio.columns]
    changes={}
    if legacy_scores:
        old=socio[['ServiceID']+legacy_scores].merge(actual,on='ServiceID',suffixes=('_source','_new'),validate='one_to_one')
        changes={c:int((abs(old[c+'_source']-old[c+'_new'])>1e-7).sum()) for c in legacy_scores}
    legacy_check='Compared available legacy score columns' if legacy_scores else 'Not applicable: explanatory input contains no legacy score columns'
    gam=json.loads((out/'demand_diagnostics.json').read_text(encoding='utf-8'))
    assert gam['training_rows']==71801 and gam['positive_converged'] and gam['zero_converged']
    forecast=pd.read_csv(out/'ml_prediction_summary.csv')
    assert set(forecast['case'])=={200,500}
    assert (forecast.reference_max_abs_error<1e-7).all()
    assert set(forecast.rows)=={307530,826540}
    daily=pd.read_csv(out/'simulation_daily.csv')
    assert len(daily)==160 and daily.ServiceID.nunique()==8
    assert (daily.requests==daily.served+daily.rejected).all()
    assert (daily.empty_vkt_km<=daily.vkt_km+1e-8).all()
    for case,z in daily.groupby('demand_case'):
        for rep,zz in z.groupby('replication'):
            assert zz.requests.nunique()==1 and zz.seed.nunique()==1 and len(zz)==4
    for path in out.glob('passengers_*.csv'):
        d=pd.read_csv(path);served=d[d.status=='served']
        assert (served.dropoff_s>=served.pickup_s).all()
        assert (served.pickup_s>=served.request_time_s).all()
        assert (served.pickup_s-served.request_time_s<=cfg['simulation']['max_wait_s']+1e-6).all()
    for path in out.glob('vehicles_*.csv'):
        d=pd.read_csv(path);assert (d.max_onboard<=4).all()
    pooled=pd.read_csv(out/'pooled_comparison.csv')
    assert len(pooled)==208 and (pooled.Source=='simulated').sum()==8
    assert set(pooled.DMU)==set(historical.ServiceID)|{s['ServiceID'] for s in cfg['simulation']['scenarios']}
    specification=json.loads((out/'comparison_specification.json').read_text(encoding='utf-8'))
    assert 'MonthlyTrips' not in specification['inputs'] and 'Util_Rate' not in specification['outputs']
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert all(s['status']=='success' for s in manifest['stages'])
    report=dict(historical_DMUs=200,matched_Tobit_DMUs=200,changed_from_source_national_scores=changes,legacy_score_check=legacy_check,
        GAM_training_rows=71801,forecast_cases=forecast.to_dict('records'),scenario_replications=len(daily),
        pooled_DMUs=208,status='passed')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
