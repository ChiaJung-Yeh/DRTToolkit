"""Build model-ready OD features from local daily counts and grid attributes.

All calendar dates must be complete observed days of one chosen day type.
Only supplied feasible OD pairs are expanded, so a missing card record is
treated as zero only within a declared observation period and OD universe.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from .common import read_csv, numeric, unique


def prepare(trips, calendar, grids, pairs, hours):
    unique(calendar, ['Date']); unique(grids, ['GridID']); unique(pairs, ['GridID_O','GridID_D'])
    if set(calendar.Split) != {'train','test'}:
        raise ValueError('Calendar needs both train and test dates, labelled Split')
    if not set(trips.Date) <= set(calendar.Date):
        raise ValueError('Trips include dates outside the complete observed calendar')
    required = ['TotalPop','Elderly','HighSchoolStudent','Income_med','School','Shop','Hospital','TransportHub','X_m','Y_m']
    numeric(grids, [x for x in required if x not in ['X_m','Y_m']])
    for c in ['X_m','Y_m']:
        if not np.isfinite(grids[c].to_numpy(float)).all():
            raise ValueError('Projected centroid coordinates must be finite')
    numeric(trips, ['Trips']); numeric(trips, ['Hour'], upper=23)
    if not (trips.Trips % 1 == 0).all() or not (trips.Hour % 1 == 0).all():
        raise ValueError('Daily observed counts and hours must be integers')
    if not set(trips.Hour) <= set(hours):
        raise ValueError('Filter trip hours to the requested service hours before preparation')
    if not (set(pairs.GridID_O) | set(pairs.GridID_D)) <= set(grids.GridID):
        raise ValueError('Feasible pairs include unknown grid IDs')
    pair_set = set(zip(pairs.GridID_O,pairs.GridID_D))
    if not set(zip(trips.GridID_O,trips.GridID_D)) <= pair_set:
        raise ValueError('Trip observations outside declared feasible OD pairs')
    x = pairs.merge(pd.DataFrame({'Hour':hours}), how='cross')
    for side, key in [('O','GridID_O'),('D','GridID_D')]:
        z=grids.rename(columns={c:f'{c}_{side}' for c in grids})
        x=x.merge(z,left_on=key,right_on=f'GridID_{side}',validate='many_to_one')
        x[f'TotalPop000_{side}']=x[f'TotalPop_{side}']/1000
        x[f'Elderly000_{side}']=x[f'Elderly_{side}']/1000
        x[f'HighSchoolStudent000_{side}']=x[f'HighSchoolStudent_{side}']/1000
        # Source Income_med is in thousands of local currency; /10 yields ten-thousands.
        x[f'Income_med_10k_{side}']=x[f'Income_med_{side}']/10
    x['euclidist']=np.hypot(x.X_m_O-x.X_m_D,x.Y_m_O-x.Y_m_D)/1000
    prediction=x.copy()
    joined=trips.merge(calendar,on='Date',validate='many_to_one')
    days=calendar.groupby('Split').size()
    tables=[]
    keys=['Hour','GridID_O','GridID_D']
    for split in ['train','test']:
        means=joined[joined.Split==split].groupby(keys,as_index=False).Trips.sum()
        means.Trips=means.Trips/days[split]
        z=x.merge(means,on=keys,how='left',validate='one_to_one')
        z['Trips']=z.Trips.fillna(0);z['Split']=split
        tables.append(z)
    return pd.concat(tables,ignore_index=True),prediction


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['trips','calendar','grids','pairs','out']:
        p.add_argument('--'+name,required=True)
    p.add_argument('--hours',default='6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22')
    a=p.parse_args()
    hours=[int(x) for x in a.hours.split(',')]
    if len(hours)!=len(set(hours)) or not hours or min(hours)<0 or max(hours)>23:
        raise ValueError('Hours must be unique integers 0..23')
    trip=read_csv(a.trips,['Date','Hour','GridID_O','GridID_D','Trips'])
    cal=read_csv(a.calendar,['Date','Split'])
    grids=read_csv(a.grids,['GridID','TotalPop','Elderly','HighSchoolStudent','Income_med','School','Shop','Hospital','TransportHub','X_m','Y_m'])
    pairs=read_csv(a.pairs,['GridID_O','GridID_D'])
    train,pred=prepare(trip,cal,grids,pairs,hours)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    train.to_csv(out/'demand_training.csv',index=False)
    pred.to_csv(out/'demand_features.csv',index=False)
    print(f'Prepared {len(train)} training/test OD-hours and {len(pred)} prediction OD-hours in {out}')


if __name__=='__main__':main()
