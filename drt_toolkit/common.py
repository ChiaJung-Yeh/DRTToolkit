import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd


def read_csv(path, required=()):
    identifiers = ['ServiceID','DMU','GridID','GridID_O','GridID_D','node_id','from_node','to_node','Date','Split']
    df = pd.read_csv(path, encoding='utf-8-sig', dtype={c:str for c in identifiers})
    missing = set(required) - set(df)
    if missing:
        raise ValueError(f'{path}: missing columns {sorted(missing)}')
    if df.empty:
        raise ValueError(f'{path}: table is empty')
    return df


def numeric(df, cols, lower=0, upper=None):
    for col in cols:
        x = pd.to_numeric(df[col], errors='raise').to_numpy(float)
        if not np.isfinite(x).all() or (x < lower).any() or (upper is not None and (x > upper).any()):
            raise ValueError(f'{col}: expected finite values in [{lower}, {upper}]')


def unique(df, cols):
    if df[list(cols)].isna().any().any() or df.duplicated(list(cols)).any():
        raise ValueError(f'Null or duplicate identifier: {cols}')


def load_config(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text(encoding='utf-8-sig'))
    if cfg['demand']['source'] not in ['trained','provided','ml']:
        raise ValueError('demand.source must be trained, provided or ml')
    root = (path.parent / cfg.get('project_root', '..')).resolve()
    for k, v in cfg['paths'].items():
        if v:
            cfg['paths'][k] = str((root / v).resolve())
    cfg['_config'] = str(path)
    cfg['_root'] = str(root)
    return cfg


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
