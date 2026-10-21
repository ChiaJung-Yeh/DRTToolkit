"""Numerical reproduction check against the supplied research's saved results."""
from pathlib import Path
import json
import pandas as pd
from drt_toolkit.evaluation import evaluate

root=Path(__file__).resolve().parents[1]
config=json.loads((root/'config/demo.json').read_text())
data=pd.read_csv(root/'data/example/historical_taiwan.csv')
mapping=pd.read_csv(root/'data/example/si_mapping.csv')
actual,_=evaluate(data,mapping,config['evaluation'])
expected=pd.read_csv(root/'data/example/reference_MetaDDF.csv')
joined=actual.merge(expected,on='DMU',suffixes=('_toolkit','_source'),validate='one_to_one')
assert len(joined)==len(data)==len(expected)==442
errors={c:float((joined[c+'_toolkit']-joined[c+'_source']).abs().max()) for c in ['MetaEff','GroupEff','TGR']}
assert max(errors.values())<1e-7,errors
print(json.dumps(dict(matched_routes=len(joined),maximum_absolute_differences=errors),indent=2))
