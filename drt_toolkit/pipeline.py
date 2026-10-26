import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import pandas as pd
from .common import load_config, read_csv, numeric, unique, write_json, file_hash
from .evaluation import read_evaluation, evaluate, prepare
from .simulation import run_simulations
from .ml_prediction import predict_scenarios


def r_stage(cfg, stage, out):
    exe = cfg.get('rscript', 'Rscript')
    if not (Path(exe).is_file() or shutil.which(exe)):
        raise ValueError('Rscript not found. Set rscript in the JSON configuration to the installed Rscript.exe path.')
    script = Path(__file__).resolve().parent / 'r' / f'{stage}.R'
    resolved = out/'resolved_config.json'
    write_json(resolved, cfg)
    result = subprocess.run([exe, str(script), str(resolved), str(out)], capture_output=True, text=True)
    (out/f'{stage}_console.txt').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
    if result.returncode:
        raise ValueError(f'{stage} failed. See {out / (stage+"_console.txt")}')


def bridge(cfg, daily):
    spec = cfg['bridge']
    if not spec['comparable_trip_definition_confirmed']:
        raise ValueError('Bridge requires review of MonthlyTrips and Util_Rate against historical trip definitions. See guidebook.')
    if not spec.get('comparability_note', '').strip():
        raise ValueError('Document the comparability review in bridge.comparability_note')
    simulated_accounting = spec.get('use_simulated_trip_accounting',False)
    required = ['RouteID','ServiceType','FleetNum','KMCost']
    if not simulated_accounting:
        required += ['MonthlyTrips','Util_Rate']
    chars = read_csv(cfg['paths']['scenario_characteristics'],required)
    unique(chars, ['RouteID'])
    expected = {s['RouteID'] for s in cfg['simulation']['scenarios']}
    if set(chars.RouteID) != expected:
        raise ValueError('Scenario characteristics must match all simulation scenario RouteIDs exactly')
    numeric(chars, ['FleetNum','KMCost'])
    if not simulated_accounting:
        numeric(chars,['MonthlyTrips']);numeric(chars,['Util_Rate'],upper=1)
        if (chars.MonthlyTrips<=0).any():
            raise ValueError('MonthlyTrips must be positive')
    for s in cfg['simulation']['scenarios']:
        if chars.set_index('RouteID').loc[s['RouteID'], 'FleetNum'] != s['fleet_size']:
            raise ValueError('FleetNum differs between simulation and scenario characteristics')
    days = float(spec['operating_days_per_month'])
    if not 0 < days <= 31:
        raise ValueError('operating_days_per_month must be in (0,31]')
    metrics = ['served','vkt_km']+(['dispatch_tours','trips_with_passengers'] if simulated_accounting else [])
    means = daily.groupby('RouteID')[metrics].mean()
    chars = chars.drop(columns=['MonthlyPatronage','MonthlyVKT'], errors='ignore').merge(means, left_on='RouteID', right_index=True)
    chars['MonthlyPatronage'] = chars.served * days
    chars['MonthlyVKT'] = chars.vkt_km * days
    if simulated_accounting:
        chars['MonthlyTrips'] = chars.dispatch_tours*days
        chars['Util_Rate'] = np.divide(chars.trips_with_passengers,chars.dispatch_tours,
            out=np.zeros(len(chars)),where=chars.dispatch_tours>0)
        costs=json.loads(Path(cfg['paths']['cost_parameters']).read_text(encoding='utf-8'))
        if (chars.vkt_km<=0).any():
            raise ValueError('A scenario has no VKT; unit cost cannot be estimated')
        chars['KMCost'] = costs['fuel_cost_per_km'] + chars.FleetNum*costs['monthly_driver_wage']/costs['wage_operating_days']/chars.vkt_km
    return chars.drop(columns=metrics)


def run_stage(cfg, stage, out):
    historical, mapping = read_evaluation(cfg)
    if stage == 'validate':
        inputs, outputs, _ = prepare(historical, mapping, cfg['evaluation'])
        for name,path in cfg['paths'].items():
            if path and name!='outputs' and not Path(path).exists():
                raise ValueError(f'Missing packaged input {name}: {path}')
        write_json(out/'validation.json', dict(routes=len(historical), inputs=inputs, outputs=outputs,
                    missing_values=int(historical.isna().sum().sum()), groups=historical.ServiceType.value_counts().to_dict(),
                    counties=historical.COUNTYNAME.value_counts().to_dict() if 'COUNTYNAME' in historical else {},
                    scenarios=[s['RouteID'] for s in cfg['simulation']['scenarios']]))
    elif stage == 'evaluate':
        scores, peers = evaluate(historical, mapping, cfg['evaluation'])
        scores.to_csv(out/'historical_scores.csv', index=False)
        peers.to_csv(out/'historical_peers.csv', index=False)
    elif stage == 'tobit':
        if not (out/'historical_scores.csv').exists():
            raise ValueError('Run evaluate first with the same --run-id')
        r_stage(cfg, 'tobit', out)
    elif stage == 'demand':
        r_stage(cfg, 'demand', out)
    elif stage == 'predict':
        predict_scenarios(cfg,out)
    elif stage == 'train-ml':
        from .ml_source import fit_workflow
        fit_workflow(Path(cfg['paths']['demand_training']),out/'ml_refit')
    elif stage == 'simulate':
        if int(cfg['simulation']['replications']) != cfg['simulation']['replications'] or int(cfg['simulation']['replications']) < 1 or cfg['simulation']['demand_scale'] <= 0:
            raise ValueError('Use positive replications and demand scale')
        od_path = cfg['paths'].get('provided_od')
        run_simulations(cfg, od_path, out)
    elif stage == 'bridge':
        daily = read_csv(out/'simulation_daily.csv', ['RouteID','served','vkt_km'])
        chars = bridge(cfg, daily)
        prepare(chars, mapping, cfg['evaluation'])
        if set(chars.RouteID) & set(historical.RouteID):
            raise ValueError('Scenario RouteIDs must differ from historical IDs; use a new version suffix for reconfigurations')
        chars.to_csv(out/'scenario_model_data.csv', index=False)
    elif stage == 'compare':
        external = cfg['paths'].get('external_scenarios')
        if external:
            if not cfg['bridge']['comparable_trip_definition_confirmed'] or not cfg['bridge'].get('comparability_note','').strip():
                raise ValueError('External scenarios also require the bridge comparability review and note')
            scenarios = read_csv(external, ['RouteID','ServiceType'])
        else:
            scenarios = read_csv(out/'scenario_model_data.csv', ['RouteID','ServiceType'])
        unique(pd.concat([historical[['RouteID']], scenarios[['RouteID']]]), ['RouteID'])
        combined = pd.concat([historical, scenarios], ignore_index=True)
        # Recompute both frontiers on the same indicator universe and pooled set.
        base_spec = cfg.get('comparison_evaluation',cfg['evaluation'])
        _, universe, _ = prepare(combined,mapping,base_spec)
        comparison_spec = {**base_spec,'output_universe':universe}
        write_json(out/'comparison_specification.json',comparison_spec)
        before, _ = evaluate(historical, mapping, comparison_spec)
        after, peers = evaluate(combined, mapping, comparison_spec)
        after['Source'] = np.where(after.DMU.isin(historical.RouteID), 'observed', 'simulated')
        after = after.merge(before[['DMU','MetaEff','GroupEff']].rename(columns={'MetaEff':'HistoricalOnlyMetaEff','GroupEff':'HistoricalOnlyGroupEff'}), on='DMU', how='left')
        after['MetaEffChange'] = after.MetaEff - after.HistoricalOnlyMetaEff
        after['MetaRank'] = after.MetaEff.rank(method='min', ascending=False)
        after.to_csv(out/'pooled_comparison.csv', index=False)
        peers.to_csv(out/'pooled_peers.csv', index=False)
        combined.to_csv(out/'pooled_model_data.csv', index=False)
        if cfg.get('comparison_evaluation'):
            sensitivity,_ = evaluate(combined,mapping,cfg['evaluation'])
            sensitivity.to_csv(out/'pooled_full_indicator_sensitivity.csv',index=False)
        # One score per scenario/replication, always using the same mean pooled frontier.
        # This isolates variation in scenario outcomes from changing reference sets.
        if external:
            write_json(out/'replication_score_status.json', dict(status='not_run', reason='Externally supplied monthly scenarios; daily replications are not available'))
            return
        daily = read_csv(out/'simulation_daily.csv')
        rep_scores = []
        for s in scenarios.RouteID:
            for r in daily[daily.RouteID == s].itertuples():
                candidate = scenarios[scenarios.RouteID == s].copy()
                candidate['RouteID'] = f'__target_{s}_{r.replication}'
                candidate['MonthlyPatronage'] = r.served * cfg['bridge']['operating_days_per_month']
                candidate['MonthlyVKT'] = r.vkt_km * cfg['bridge']['operating_days_per_month']
                if cfg['bridge'].get('use_simulated_trip_accounting'):
                    candidate['MonthlyTrips']=r.dispatch_tours*cfg['bridge']['operating_days_per_month']
                    candidate['Util_Rate']=r.trips_with_passengers/r.dispatch_tours if r.dispatch_tours else 0
                    costs=json.loads(Path(cfg['paths']['cost_parameters']).read_text(encoding='utf-8'))
                    candidate['KMCost']=costs['fuel_cost_per_km']+candidate.FleetNum*costs['monthly_driver_wage']/costs['wage_operating_days']/r.vkt_km
                # Some replication targets lie beyond a fixed technology and are infeasible with beta>=0.
                try:
                    scored, _ = evaluate(pd.concat([combined, candidate], ignore_index=True), mapping,
                                         comparison_spec, reference_ids=combined.RouteID.tolist(), target_ids=candidate.RouteID.tolist())
                    row = scored.iloc[-1].to_dict()
                    row.update(RouteID=s, replication=r.replication, status='optimal')
                except ValueError as exc:
                    row = dict(RouteID=s, replication=r.replication, status='infeasible_or_failed', reason=str(exc))
                rep_scores.append(row)
        pd.DataFrame(rep_scores).to_csv(out/'scenario_replication_scores.csv', index=False)
    else:
        raise ValueError(stage)


def main():
    p = argparse.ArgumentParser(description='Integrated DRT planning toolkit')
    p.add_argument('stage', choices=['validate','evaluate','tobit','demand','predict','train-ml','simulate','bridge','compare','all'])
    p.add_argument('--config', default='config/case_study.json')
    p.add_argument('--run-id', default=None, help='Reuse one ID for sequential stages; use a new ID for each new study run')
    args = p.parse_args()
    cfg = load_config(args.config)
    run_id = args.run_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if not run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in run_id):
        raise ValueError('run-id can contain only letters, digits, underscores and hyphens')
    out = Path(cfg['paths']['outputs'])/run_id
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'stages': []}
    config_hash = file_hash(cfg['_config'])
    if manifest.get('config_sha256', config_hash) != config_hash:
        raise ValueError('Config changed for an existing run. Use a new --run-id.')
    input_hashes = {k:file_hash(v) for k,v in cfg['paths'].items() if v and Path(v).is_file()}
    code_hashes = {str(x.relative_to(Path(__file__).resolve().parents[1])):file_hash(x)
                   for x in Path(__file__).resolve().parent.rglob('*') if x.suffix in ['.py','.R']}
    for key, value in [('input_sha256',input_hashes),('code_sha256',code_hashes)]:
        if key in manifest and manifest[key] != value:
            raise ValueError(f'{key} changed for an existing run. Use a new --run-id.')
    import scipy,sklearn,xgboost,joblib
    manifest.update(config_sha256=config_hash, config=cfg, python=sys.version,
        dependencies=dict(numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,sklearn=sklearn.__version__,xgboost=xgboost.__version__,joblib=joblib.__version__),
        input_sha256=input_hashes, code_sha256=code_hashes)
    stages = ['validate','evaluate','tobit','demand','predict','simulate','bridge','compare'] if args.stage == 'all' else [args.stage]
    if args.stage == 'all' and cfg['demand']['source'] == 'provided':
        stages.remove('predict')
    for stage in stages:
        record = dict(stage=stage, started_utc=datetime.now(timezone.utc).isoformat())
        try:
            print(f'Running {stage} ...', flush=True)
            run_stage(cfg, stage, out)
            record['status'] = 'success'
        except Exception as exc:
            record.update(status='failed', error=str(exc))
            raise
        finally:
            record['finished_utc'] = datetime.now(timezone.utc).isoformat()
            manifest['stages'].append(record)
            write_json(manifest_path, manifest)
    print(f'Completed: {out}')


if __name__ == '__main__':
    main()
