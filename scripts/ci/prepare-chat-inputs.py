#!/usr/bin/env python3
"""Prepare measured, local chat-kit inputs from verified same-run artifacts."""
import gzip
import hashlib
import importlib.util
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from email.parser import BytesParser
from email.policy import default

ROOT = Path.cwd()
CHAT = ROOT / '.native/chat'
EVIDENCE = ROOT / 'native-evidence/chat'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity(path):
    path = Path(path)
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'sha256': digest, 'size': path.stat().st_size}


def only(paths, label):
    values = list(paths)
    if len(values) != 1 or not values[0].is_file():
        raise ValueError(f'exactly one {label} required')
    return values[0]


def wheel_pins(directory):
    pins = {}
    for path in sorted(directory.glob('*.whl')):
        with zipfile.ZipFile(path) as z:
            metadata = [n for n in z.namelist() if n.endswith('.dist-info/METADATA') and n.count('/') == 1]
            if len(metadata) != 1:
                raise ValueError(f'invalid wheel metadata: {path}')
            msg = BytesParser(policy=default).parsebytes(z.read(metadata[0]))
            name = re.sub('[-_.]+', '-', msg.get('Name', '')).lower()
            if not name or name in pins or not msg.get('Version'):
                raise ValueError('duplicate or invalid distribution metadata')
            pins[name] = str(msg['Version'])
    return pins


def verify_source_companion(archive, companion, source_commit):
    with tarfile.open(archive, 'r:*') as tar:
        matches = [m for m in tar.getmembers() if m.isfile() and m.name.count('/') == 1 and m.name.endswith('/manifest.json')]
        if len(matches) != 1:
            raise ValueError('legacy kit manifest missing or ambiguous')
        manifest = json.load(tar.extractfile(matches[0]))
    if (manifest.get('source_commit') != source_commit
            or manifest.get('source_companion') != companion.name
            or manifest.get('source_companion_sha256') != identity(companion)['sha256']):
        raise ValueError('DOS source companion does not match legacy kit manifest')


MAX_EXPANDED_RUNTIME_BYTES = 6 * 1024**3


def compress_base(source, output, max_size=MAX_EXPANDED_RUNTIME_BYTES):
    digest = hashlib.sha256()
    size = 0
    with gzip.open(source, 'rb') as src, lzma.open(output, 'xb', preset=6) as dst:
        while block := src.read(8 * 1024**2):
            size += len(block)
            if size > max_size:
                raise ValueError('expanded base exceeds verified runtime budget')
            digest.update(block)
            dst.write(block)
    if not size:
        raise ValueError('empty expanded base')
    return {'sha256': digest.hexdigest(), 'size': size}


def stripped_copy(source, destination, strip):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    original = identity(source)
    subprocess.run([str(strip), '--strip-debug', str(destination)], check=True)
    destination.chmod(0o755)
    return {'original': original, 'derived': identity(destination)}


def full_windows_base(manifest, root):
    """Require the verified full PE32-capable runtime, never the smaller Wine64 base."""
    retained = manifest.get('retained_base')
    if not isinstance(retained, dict) or not isinstance(retained.get('windows_runtime'), dict):
        raise ValueError('Verified full Windows runtime required for offline chat kit')
    receipt = json.loads((root / 'native-evidence/pe/retained-base-preparation.json').read_text())
    if not {'wine64', 'pe32'} <= set(receipt.get('os_capabilities', [])):
        raise ValueError('Offline chat kit requires verified Wine64 and PE32 capabilities')
    ref = retained['windows_runtime']
    path = root / ref['path']
    if path.is_symlink() or not path.is_file() or identity(path) != {k: ref[k] for k in ('sha256', 'size')}:
        raise ValueError('Verified Windows runtime missing or changed')
    return path


def main():
    if sys.platform != 'linux' or sys.version_info[:3] != (3, 13, 5):
        raise ValueError('Linux CPython 3.13.5 required')
    sys.path.insert(0, str(ROOT / 'scripts/ci'))
    unified = load_module('unified_inputs', ROOT / 'scripts/ci/unified-runtime-inputs.py')
    runtime = load_module('chat_runtime', ROOT / 'scripts/prepare_chat_runtimes.py')
    builder = load_module('chat_builder', ROOT / 'scripts/build_chat_offline_kit.py')
    manifest = json.loads((ROOT / 'native-evidence/pe/prepared-inputs.json').read_text())
    sha = os.environ['CI_COMMIT_SHA']
    run = os.environ['FDISBULL_LOCAL_RUN_ID']
    manifest = unified.verify(ROOT, sha, run, manifest['build_job_id'], source_root=ROOT)
    wheel = only((ROOT / 'dist').glob('fdisbull-*.whl'), 'ordinary core wheel')
    if identity(wheel) != {k: manifest['tested_wheel'][k] for k in ('sha256', 'size')}:
        raise ValueError('ordinary core wheel differs from unified preparation')
    version = wheel_pins(CHAT / 'wheels')
    if set(version) != builder.RUNTIME_WHEELS:
        raise ValueError('downloaded wheelhouse does not match runtime distributions')
    prepared = {k: ROOT / v['path'] for k, v in manifest['inputs'].items()}
    source = only((ROOT / '.native/offline/output').glob('*source-companion*'), 'DOS source companion')
    legacy = only((ROOT / '.native/offline/output').glob('*-offline.tar.gz'), 'legacy offline kit')
    verify_source_companion(legacy, source, sha)
    tool_source = only((ROOT / 'dist').glob('fdisbull-*-tool.zip'), 'tool source ZIP')
    CHAT.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    strip = Path('/usr/bin/strip')
    strip_version = subprocess.run([str(strip), '--version'], check=True, capture_output=True, text=True).stdout.splitlines()[0]
    copies = CHAT / 'native'
    dosbox = copies / 'dosbox-x'
    qemu = copies / 'qemu-system-x86_64'
    transforms = {'dosbox': stripped_copy(prepared['FDISBULL_DOSBOX'], dosbox, strip),
                  'qemu': stripped_copy(prepared['FDISBULL_PE_QEMU'], qemu, strip)}
    base = CHAT / 'base.cpio.xz'
    expanded = compress_base(prepared['FDISBULL_PE_INITRAMFS'], base)
    outputs = runtime.materialize(base, CHAT / 'measured-runtimes', dosbox, expanded)
    recipe = CHAT / 'runtime-recipe.json'
    recipe.write_text(json.dumps({'schema': 'fdisbull-chat-runtime-recipe-v1',
                                  'expanded_base': expanded, 'resources': runtime.resource_identities(dosbox),
                                  'outputs': outputs}, indent=2) + '\n')
    windows_source = full_windows_base(manifest, ROOT)
    windows_base = CHAT / 'windows-base.cpio.xz'
    windows_expanded = compress_base(windows_source, windows_base)
    windows_output = runtime.materialize(windows_base, CHAT / 'measured-windows', dosbox, windows_expanded, windows_only=True)['wine']
    windows_recipe = CHAT / 'windows-recipe.json'
    windows_recipe.write_text(json.dumps({'schema': 'fdisbull-chat-windows-recipe-v1',
        'expanded_base': windows_expanded, 'resources': runtime.resource_identities(dosbox)['wine'],
        'output': windows_output}, indent=2) + '\n')
    receipt = EVIDENCE / 'input-provenance.json'
    receipt.write_text(json.dumps({'schema':'fdisbull-chat-inputs-v1', 'source_commit':sha,
                                  'local_run_id':run, 'unified_manifest':identity(ROOT / 'native-evidence/pe/prepared-inputs.json'),
                                  'ordinary_core':identity(wheel), 'strip_version':strip_version,
                                  'stripped':transforms, 'base_source':identity(prepared['FDISBULL_PE_INITRAMFS']), 'base':identity(base), 'recipe':identity(recipe),
                                  'windows_source':identity(windows_source), 'windows_base':identity(windows_base), 'windows_recipe':identity(windows_recipe)}, indent=2) + '\n')
    def item(path, destination, role='payload'):
        return {'source': str(Path(path).resolve(strict=True)), 'destination': destination, 'role': role}
    inputs = [item(dosbox,'native/dosbox-x','dosbox'),
              item(qemu,'native/qemu/bin/qemu-system-x86_64','qemu'),
              item('/lib64/ld-linux-x86-64.so.2','lib/ld-linux-x86-64.so.2','loader'),
              item(prepared['FDISBULL_PE_KERNEL'],'runtime/kernel','kernel'),
              item(prepared['FDISBULL_PE_FIXTURE'],'fixtures/oracle.exe','pe_fixture'),
              item(base,'runtime/base.cpio.xz','runtime_base'), item(recipe,'runtime/recipe.json','runtime_recipe'),
              item(windows_base,'runtime/windows-base.cpio.xz','windows_runtime_base'),
              item(windows_recipe,'runtime/windows-recipe.json','windows_runtime_recipe'),
              item(ROOT/'scripts/prepare_chat_runtimes.py','tools/preparer.py','runtime_preparer'),
              item(ROOT/'scripts/verify_chat_offline_kit.py','tools/verify.py','verifier'),
              item(source,'source/dosbox-companion.tar','source_companion'),
              item(tool_source,'source/fdisbull-tool.zip'),
              item(receipt,'receipts/staging.json','python_receipt'),
              item(ROOT/'native-evidence/layers/backend-identity.json','receipts/dosbox.json','dosbox_receipt'),
              item(ROOT/'native-evidence/pe/backend-identity.json','receipts/qemu.json','qemu_receipt'),
              item(ROOT/'native-evidence/pe/runtime-packages.txt','receipts/wine-packages.txt','wine_receipt')]
    for entry in manifest['firmware']:
        p = ROOT / entry['path']
        relative = p.relative_to(ROOT / 'native-evidence/pe/firmware').as_posix()
        inputs.append(item(p, 'native/qemu/share/qemu/' + relative, 'firmware'))
    notices = sorted(Path('/usr/share/doc').glob('*/copyright'))
    if not notices:
        raise ValueError('system copyright notices unavailable')
    for notice in notices:
        inputs.append(item(notice, 'licenses/' + notice.parent.name + '.txt', 'license'))
    loader = Path('/usr/bin/ldd')
    # Image identity is hash-bound when a specific Wine package version is absent.
    wine = 'runtime-packages-sha256:' + identity(ROOT / 'native-evidence/pe/runtime-packages.txt')['sha256']
    config = {'python_prefix':sys.prefix, 'wheelhouse':str(CHAT/'wheels'), 'ldd':str(loader),
              'identities':{'source_commit':sha, 'test_source_commit':sha, 'python':'3.13.5',
                            'qemu':'9.2.4', 'wine':wine, 'version':version['fdisbull']},
              'wheel_versions':version, 'inputs':inputs}
    (CHAT / 'stage').mkdir()
    (CHAT / 'config.json').write_text(json.dumps(config, indent=2) + '\n')


if __name__ == '__main__':
    main()
