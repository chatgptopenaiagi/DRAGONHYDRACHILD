"""Bounded Task Scheduler entry point; no donor paths or private arguments."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.dont_write_bytecode = True

if __name__ == '__main__':
    if sys.version_info[:2] != (3, 14):
        raise SystemExit('Python 3.14 required')
    from dragonhydra.child.acquisition import collect_once
    result = collect_once()
    print(json.dumps({key: result.get(key) for key in ('attempt_id', 'status', 'reason', 'storage_status')}, indent=2))
    raise SystemExit(0 if result['status'] in ('COMPLETE', 'NOT_DUE') else 1)
