"""Select study settings and execute desktop stages with retained console logs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _refresh_settings():
    global SETTINGS, RUN_ID, CONFIG, OUT
    SETTINGS = json.loads((ROOT/'desktop_scripts/desktop_settings.json').read_text(encoding='utf-8-sig'))
    RUN_ID = SETTINGS['run_id']
    if not RUN_ID or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in RUN_ID):
        raise ValueError('Use letters, numbers, underscores or hyphens for run_id')
    CONFIG = ROOT/SETTINGS['config']
    OUT = ROOT/'outputs'/RUN_ID
    return OUT


def get_output_dir():
    """Return the current output path after reading the saved desktop settings."""
    return _refresh_settings()


def get_study_config():
    """Read the selected study configuration for notebook input previews."""
    _refresh_settings()
    return _runtime_config()[0]


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _runtime_config():
    cfg = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    cfg['project_root'] = str(ROOT)
    cfg['rscript'] = SETTINGS['rscript']
    return cfg, json.dumps(cfg, indent=2, ensure_ascii=False)


def _conflict(cfg, content):
    manifest_path = OUT/'manifest.json'
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    resolved = OUT/'desktop_config.json'
    # Compare the actual saved bytes: Windows may store text with CRLF even
    # though read_text normalises it to LF. The pipeline hashes those bytes.
    if (not resolved.exists() or resolved.read_text(encoding='utf-8') != content
            or manifest.get('config_sha256') != _hash(resolved)):
        return 'the study configuration has changed'
    inputs = {key: _hash(ROOT/value) for key, value in cfg['paths'].items()
              if value and (ROOT/value).is_file()}
    code = {str(p.relative_to(ROOT)): _hash(p) for p in (ROOT/'drt_toolkit').rglob('*')
            if p.suffix in ['.py', '.R']}
    if manifest.get('input_sha256') != inputs:
        return 'the study inputs have changed'
    if manifest.get('code_sha256') != code:
        return 'the analysis code has changed'
    return None


def _prepare(stages):
    _refresh_settings()
    cfg, content = _runtime_config()
    reason = _conflict(cfg, content)
    if reason:
        previous = OUT
        if not any(s in ['validate', 'evaluate', 'all'] for s in stages):
            raise RuntimeError(f'Cannot continue {RUN_ID}: {reason}. Start a complete run in notebook 00 or restart the staged sequence from notebook 01. Previous results remain in {previous}.')
        # Allocate before writing anything into the old run folder. Persist the
        # selection so the standalone R entries and later notebooks use it too.
        selected = dict(SETTINGS)
        selected['run_id'] = RUN_ID[:48]+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (ROOT/'desktop_scripts/desktop_settings.json').write_text(json.dumps(selected, indent=2)+'\n', encoding='utf-8')
        _refresh_settings()
        print(f'Created new run {RUN_ID} because {reason}. Previous results retained in {previous}.', flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    resolved = OUT/'desktop_config.json'
    if not resolved.exists() or resolved.read_text(encoding='utf-8') != content:
        resolved.write_text(content, encoding='utf-8')
    return resolved


def check_environment():
    _refresh_settings()
    import numpy, pandas, scipy, sklearn, xgboost, joblib
    versions = {m.__name__: m.__version__ for m in (numpy, pandas, scipy, sklearn, xgboost, joblib)}
    print('Python interpreter:', sys.executable)
    print('Dependencies loaded. Compatibility is checked against the saved demand model.')
    print('Selected run:', RUN_ID)
    print('Results:', OUT)
    if sklearn.__version__ != '1.5.1' or xgboost.__version__ != '2.1.0':
        raise RuntimeError('The selected interpreter is incompatible with the saved demand model. Use the dependency versions listed in requirements.txt.')
    if not Path(SETTINGS['rscript']).is_file():
        raise FileNotFoundError('Set rscript in desktop_settings.json to the installed Rscript.exe path')
    return versions


def _execute(command, label, log):
    tail = []
    with log.open('w', encoding='utf-8') as handle:
        result = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding='utf-8', errors='replace')
        for line in result.stdout:
            print(line, end='', flush=True)
            handle.write(line)
            handle.flush()
            tail.append(line.rstrip())
            tail = tail[-18:]
        returncode = result.wait()
    if returncode:
        detail = '\n'.join(tail)
        raise RuntimeError(f'{label} failed (exit {returncode}). Run: {RUN_ID}. Console log: {log}\n{detail}')


def run(*stages):
    """Read current settings and run stages, returning the selected result folder."""
    if not stages:
        raise ValueError('Select at least one analysis stage')
    resolved = _prepare(stages)
    print('Results:', OUT, flush=True)
    for stage in stages:
        print('\nStage:', stage, flush=True)
        _execute([sys.executable, '-u', '-B', '-m', 'drt_toolkit', stage,
                  '--config', str(resolved), '--run-id', RUN_ID], stage, OUT/(stage+'_desktop_console.log'))
    return OUT


def run_r(filename):
    """Execute the same standalone R entry that can be sourced in RStudio."""
    _prepare(())
    _execute([SETTINGS['rscript'], str(ROOT/'desktop_scripts'/filename)], filename,
             OUT/(Path(filename).stem+'_desktop_console.log'))
    return OUT


_refresh_settings()
