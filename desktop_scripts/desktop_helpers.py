"""Read study settings, check dependencies and run stages with the selected interpreter."""
from pathlib import Path
import json, sys, subprocess, importlib.metadata

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SETTINGS=json.loads((ROOT/'desktop_scripts/desktop_settings.json').read_text(encoding='utf-8-sig'))
RUN_ID=SETTINGS['run_id']
if not RUN_ID or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in RUN_ID):
    raise ValueError('Use letters, numbers, underscores or hyphens for run_id')
CONFIG=ROOT/SETTINGS['config']
OUT=ROOT/'outputs'/RUN_ID

def check_environment():
    import numpy, pandas, scipy, sklearn, xgboost, joblib
    versions={m.__name__:m.__version__ for m in (numpy,pandas,scipy,sklearn,xgboost,joblib)}
    print('Python interpreter:',sys.executable)
    print('Dependencies loaded. Compatibility is checked against the saved demand model.')
    print('Results:',OUT)
    if sklearn.__version__!='1.5.1' or xgboost.__version__!='2.1.0':
        raise RuntimeError('The selected interpreter is incompatible with the saved demand model. Use the dependency versions listed in requirements.txt.')
    if not Path(SETTINGS['rscript']).is_file():
        raise FileNotFoundError('Set rscript in desktop_settings.json to the installed Rscript.exe path')
    return versions

def run(*stages):
    # Run each stage with the selected Jupyter interpreter and the shared study settings.
    OUT.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    cfg['project_root']=str(ROOT)
    cfg['rscript']=SETTINGS['rscript']
    resolved=OUT/'desktop_config.json'
    content=json.dumps(cfg,indent=2,ensure_ascii=False)
    if not resolved.exists() or resolved.read_text(encoding='utf-8')!=content:
        resolved.write_text(content,encoding='utf-8')
    for stage in stages:
        print('\nStage:',stage,flush=True)
        result=subprocess.Popen([sys.executable,'-u','-B','-m','drt_toolkit',stage,
            '--config',str(resolved),'--run-id',RUN_ID],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        for line in result.stdout: print(line,end='',flush=True)
        if result.wait():
            raise RuntimeError(f'{stage} failed. Inspect logs in {OUT}. Review the selected interpreter, configuration and stage log before retrying.')
    return OUT

def run_r(filename):
    # Execute an R stage with Rscript; the same file can be sourced in RStudio.
    result=subprocess.run([SETTINGS['rscript'],str(ROOT/'desktop_scripts'/filename)],cwd=ROOT)
    if result.returncode: raise RuntimeError(f'{filename} failed')
    return OUT
