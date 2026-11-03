#!/usr/bin/env python3
"""Write success evidence only after a complete native acceptance job."""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET

profile = sys.argv[1]
if profile not in {'stable', 'layers', 'unified'}:
    raise SystemExit('unknown native profile')
root = Path('native-evidence')
identity_path = root / ('pe/backend-identity.json' if profile == 'unified' else f'{profile}/backend-identity.json')
identity = json.loads(identity_path.read_text())
if identity['source_commit'] != os.environ['CI_COMMIT_SHA']:
    raise SystemExit('native identity is for a different source commit')

def digest(path):
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError as exc:
        raise SystemExit(f'native artifact outside project: {path}') from exc
    return {'path': relative.as_posix(), 'sha256': checksum, 'size': path.stat().st_size}

junit = ([root / 'pe/tests.xml', root / 'unified/tests.xml'] if profile == 'unified'
         else [root / profile / 'tests.xml'])
outputs = ([Path(os.environ['FDISBULL_DOSBOX'])] + sorted(Path('.native/offline/output').glob('*')) if profile == 'layers'
           else sorted(Path('.native/pe/packages').glob('*.whl')) if profile == 'unified'
           else [Path(os.environ['FDISBULL_DOSBOX'])])
if not outputs or (profile == 'layers' and len(outputs) < 2):
    raise SystemExit('required native outputs are missing')
for path in junit:
    tree = ET.parse(path).getroot()
    suites = [tree] if tree.tag == 'testsuite' else list(tree.findall('testsuite'))
    totals = {key: sum(int(s.get(key, '0')) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    if totals['tests'] <= 0 or totals['skipped'] or totals['failures'] or totals['errors']:
        raise SystemExit(f'native test results not passing: {path}: {totals}')
receipt = {'status': 'passed',
           'pipeline_id': os.environ['CI_PIPELINE_ID'], 'job_id': os.environ['CI_JOB_ID'],
           'job_name': os.environ['CI_JOB_NAME'], 'source_commit': os.environ['CI_COMMIT_SHA'],
           'profile': profile, 'python_version': platform.python_version(),
           'backend_identity': identity, 'test_results': [digest(p) for p in junit],
           'artifacts': [digest(p) for p in outputs]}
out = Path('artifacts/receipts')
out.mkdir(parents=True, exist_ok=True)
(out / f'native-{profile}.json').write_text(json.dumps(receipt, indent=2) + '\n')
