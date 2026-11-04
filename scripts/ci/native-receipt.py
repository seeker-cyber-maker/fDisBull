#!/usr/bin/env python3
"""Write success evidence only after a complete native acceptance job."""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import subprocess
import xml.etree.ElementTree as ET

from execution_identity import execution_identity

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
           **execution_identity(), 'source_commit': os.environ['CI_COMMIT_SHA'],
           'profile': profile, 'python_version': platform.python_version(),
           'node_version': subprocess.check_output(['node', '--version'], text=True).strip(),
           'backend_identity': identity, 'test_results': [digest(p) for p in junit],
           'artifacts': [digest(p) for p in outputs]}
if profile == 'unified' and os.environ.get('FDISBULL_UNIFIED_PREPARED') == '1':
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('unified_runtime_inputs', Path('scripts/ci/unified-runtime-inputs.py'))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    prepared = module.verify()
    receipt['windows_native_cases'] = module.required_windows_cases(Path.cwd(), prepared)
    receipt['prepared_manifest'] = digest(module.MANIFEST)
    receipt['runtime_inputs'] = list(prepared['inputs'].values())
    receipt['artifacts'].extend(receipt['runtime_inputs'])
    receipt['resource_receipts'] = list(prepared['resource_receipts'].values())
    receipt['firmware'] = prepared['firmware']
out = Path('artifacts/receipts')
out.mkdir(parents=True, exist_ok=True)
(out / f'native-{profile}.json').write_text(json.dumps(receipt, indent=2) + '\n')
