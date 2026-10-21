"""VRS meta/group DDF, algebraically matching the supplied Gurobi model."""
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from .common import read_csv, numeric, unique

GROUPS = {'Fixed-Route': 'FR', 'Flexible Fixed-Route': 'FFR', 'Point-to-Point': 'P2P'}


def prepare(df, mapping, spec):
    unique(df, ['RouteID'])
    if not df.ServiceType.isin(GROUPS).all():
        raise ValueError(f'ServiceType must be one of {list(GROUPS)}')
    unique(mapping, ['ServiceIntention'])
    flags = mapping.ServiceIntention.tolist()
    numeric(df, flags, upper=1)
    if not df[flags].isin([0, 1]).all().all() or (df[flags].sum(axis=1) == 0).any():
        raise ValueError('Each route needs binary service intentions and at least one active intention')
    metric_cols = [x for x in mapping if x != 'ServiceIntention']
    if not mapping[metric_cols].isin([0, 1]).all().all():
        raise ValueError('SI mapping must contain binary metric indicators')
    if (mapping[metric_cols].sum(axis=1) == 0).any():
        raise ValueError('Each intention must map to at least one output')
    active_mapping = mapping[mapping.ServiceIntention.isin([f for f in flags if df[f].any()])]
    outputs = sorted(set(spec.get('output_universe', spec['outputs'])) |
                     set(spec['outputs']) | {c for c in metric_cols if active_mapping[c].any()})
    inputs = spec['inputs']
    missing = set(inputs + outputs + flags + ['RouteID', 'ServiceType']) - set(df)
    if missing:
        raise ValueError(f'Missing evaluation columns {sorted(missing)}')
    numeric(df, inputs + outputs)
    numeric(df, ['Util_Rate'], upper=1)
    if (df[inputs].sum(axis=1) <= 0).any():
        raise ValueError('Every route must have a positive input direction')
    mask = np.zeros((len(df), len(outputs)))
    lookup = mapping.set_index('ServiceIntention')
    for r, (_, row) in enumerate(df.iterrows()):
        selected = set(spec['outputs'])
        for flag in flags:
            if row[flag] == 1:
                selected.update(c for c in metric_cols if lookup.loc[flag, c] == 1)
        mask[r] = [float(c in selected) for c in outputs]
    return inputs, outputs, mask


def solve_ddf(X, Y, directions, target, refs):
    """max beta; X lambda + beta*x0 <= x0; -Y lambda + beta*gy <= -y0."""
    x0, y0 = X[target], Y[target]
    # Unit scaling improves numerics without changing the feasible set.
    sx = np.maximum(np.max(X, axis=0), 1)
    sy = np.maximum(np.max(Y, axis=0), 1)
    aub = np.vstack([np.column_stack([X[refs].T / sx[:, None], x0 / sx]),
                     np.column_stack([-Y[refs].T / sy[:, None], y0 * directions[target] / sy])])
    bub = np.r_[x0 / sx, -y0 / sy]
    eq = np.r_[np.ones(len(refs)), 0][None, :]
    objective = np.r_[np.zeros(len(refs)), -1]
    res = linprog(objective, A_ub=aub, b_ub=bub, A_eq=eq, b_eq=[1],
                  bounds=[(0, None)] * (len(refs) + 1), method='highs')
    if not res.success:
        raise ValueError(f'DDF target row {target}: {res.message}. Use pooled mode if a fixed-reference target is infeasible.')
    violation = max(float(np.max(aub @ res.x - bub)), abs((eq @ res.x - 1).item()))
    if violation > 1e-6:
        raise ValueError(f'DDF feasibility residual {violation}')
    beta = float(res.x[-1])
    if beta < -1e-7 or beta > 1+1e-7:
        raise ValueError(f'DDF beta outside its input-implied range: {beta}')
    # Snap only solver tolerance at exact bounds; retain interior estimates.
    beta = min(1., max(0., beta))
    return beta, res.x[:-1], violation


def evaluate(df, mapping, spec, reference_ids=None, target_ids=None):
    inputs, outputs, direction = prepare(df, mapping, spec)
    X, Y = df[inputs].to_numpy(float), df[outputs].to_numpy(float)
    groups = df.ServiceType.map(GROUPS).to_numpy()
    ids = df.RouteID.astype(str).to_numpy()
    refs = np.arange(len(df)) if reference_ids is None else np.flatnonzero(np.isin(ids, reference_ids))
    rows, peers = [], []
    for i, route in enumerate(ids):
        if target_ids is not None and route not in target_ids:
            continue
        group_refs = refs[groups[refs] == groups[i]]
        if not len(group_refs):
            raise ValueError(f'No reference DMUs for group {groups[i]}')
        meta, ml, mr = solve_ddf(X, Y, direction, i, refs)
        group, gl, gr = solve_ddf(X, Y, direction, i, group_refs)
        me, ge = 1 - meta, 1 - group
        if me > ge + 1e-6 or min(me, ge) < -1e-6:
            raise ValueError('Unexpected meta/group score ordering')
        rows.append(dict(DMU=route, ClusterName=groups[i], MetaBeta=meta, GroupBeta=group,
                         MetaEff=me, GroupEff=ge, TGR=me/ge if ge > 1e-10 else np.nan,
                         MaxResidual=max(mr, gr)))
        for level, rr, weights in [('meta', refs, ml), ('group', group_refs, gl)]:
            peers.extend(dict(DMU=route, Frontier=level, Peer=ids[j], Weight=float(w))
                         for j, w in zip(rr, weights) if w > 1e-8)
    return pd.DataFrame(rows), pd.DataFrame(peers)


def read_evaluation(cfg):
    return (read_csv(cfg['paths']['historical'], ['RouteID', 'ServiceType']),
            read_csv(cfg['paths']['si_mapping'], ['ServiceIntention']))
