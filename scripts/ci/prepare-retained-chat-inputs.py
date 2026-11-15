#!/usr/bin/env python3
"""Prepare the pinned 0966 chat kit from retained OVH and Windows components.

No downloads, package installation or native builds occur here. Config schema
fdisbull-chat-retained-inputs-v1 requires application_source_commit/version,
export_root/export_inventory/job_metadata/source_postcheck, python_prefix,
wheelhouse, licenses (absolute files), and full_windows containing image, report,
manifest, capability_receipt, prepared_inputs, resource_receipt. Optional loader,
ldd, strip paths default to Linux tools; harness_source_commit is recorded apart
from application identity. --output must be an existing empty private directory.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import zipfile

HERE = Path(__file__).resolve().parent
SOURCE = '0966c331f653952b638e42bb1bc5a9afff6ada33'
VERSION = '0.34.1'
PIPELINE, JOB = '3060880626', '17979142621'
EXPORT_INVENTORY_SHA = 'cc329287b4a655d5059ba2afed5268a7d9f142f8a5bead2c9d063fb9c6ad62e9'
PREPARATION_SOURCE = 'afd4633b2f1f6e6db114f1e19541ff828905b06b'
ORIGIN_SOURCE = 'cfd28639f0ea492be44d3b1aea1a7f7cf971fba4'
WINDOWS = {'sha256': '2a4dee4b32c4a392f83fe187e65f82d452be6fac1b896f834f2d7361e849f2c0', 'size': 1239330025}
DOCUMENT_PINS = {
    'report': '6350c9bb676d745169a007cc1004a9b4799afd89970079e0847555129f010f38',
    'manifest': '4a6a9454e89fe9816901ce2975c049b5f4b3096543321c7ccdedd242b1698977',
    'capability_receipt': 'd2b84ab97559fdec870110e9f8f24d0fefa06bb74419f7b2a5ceb831ffcf69e2',
    'prepared_inputs': 'e642aed53a6e5d3efb9ccde547fda8cbbbf106294ce2e2910dc2aacbe8445f94',
    'resource_receipt': '7312658670b4417b44a0529ecc9c0a9d6e3f30e50107ca9987aad463e5920764',
}
PINS = {
    'dist/fdisbull-0.34.1-py3-none-any.whl': '897eaa49ff465b0397bd36f9040cbafe9ca2e4dbf6f490d4a9a6825a05668137',
    'dist/fdisbull_player-0.34.1-py3-none-any.whl': 'c4f3a394ea3557802f8002243773087979718d047da18fc2745959d6f9aff878',
    'dist/fdisbull-0.34.1-tool.zip': '77dd5b2b611b54706591b791e14307a151d7a20c8ff248c2666047dd6acc5500',
    '.native/offline/output/fdisbull-0.34.1-linux-x86_64-source-companion.tar': '1caafaaf8b2e10143c8336c5af66898543758853aefce5e7c544ec7ff022156e',
}
INPUTS = {
    'FDISBULL_PE_QEMU': '.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
    'FDISBULL_PE_KERNEL': '.native/pe/linux-amd64',
    'FDISBULL_PE_INITRAMFS': '.native/pe/runtime.cpio.gz',
    'FDISBULL_PE_FIXTURE': '.native/pe/oracle.exe',
    'FDISBULL_DOSBOX': '.native/backends/layers/dosbox-x',
    'FDISBULL_DOS_INITRAMFS': '.native/pe/dos-runtime.cpio.gz',
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = load_module('_retained_chat_helpers', HERE / 'prepare-chat-inputs.py')
runtime = load_module('_retained_chat_runtime', HERE.parent / 'prepare_chat_runtimes.py')
builder = load_module('_retained_chat_builder', HERE.parent / 'build_chat_offline_kit.py')
inventory = load_module('_retained_chat_inventory', HERE.parent / 'prepare_chat_offline_inventory.py')


def regular(value):
    path = Path(value)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('Expected absolute regular non-symlink input: ' + str(path))
    return path


def document(value):
    return json.loads(regular(value).read_text())


def identity(path):
    path = regular(path)
    with path.open('rb') as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return {'size': path.stat().st_size, 'sha256': h.hexdigest()}


def same(actual, expected, label):
    if actual != expected:
        raise ValueError('Retained identity mismatch: ' + label)


def safe_relative(raw):
    if (not isinstance(raw, str) or not raw or '\\' in raw or PurePosixPath(raw).is_absolute()
            or any(p in ('', '.', '..') for p in raw.split('/'))):
        raise ValueError('Unsafe export path')
    return raw


def windows_donor(config):
    paths = config['full_windows']
    for name, expected in DOCUMENT_PINS.items():
        same(identity(paths[name])['sha256'], expected, 'pinned Windows ' + name)
    report = document(paths['report'])
    same(report.get('schema'), 'fdisbull-retained-full-windows-runtime-inventory-1', 'Windows report schema')
    actual = identity(paths['image'])
    same(actual, WINDOWS, 'pinned Windows image')
    candidate = report['candidate']
    same(actual, {'sha256': candidate['sha256_streamed'], 'size': candidate['size_bytes']}, 'Windows report image')
    same(candidate['sha256_expected'], actual['sha256'], 'Windows expected hash')
    schemas = report['resource_schemas']
    for name, report_name in [('manifest', 'retained_base_manifest'), ('capability_receipt', 'capability_receipt'), ('prepared_inputs', 'prepared_inputs')]:
        same(identity(paths[name])['sha256'], schemas[report_name]['sha256'], name)
    same(identity(paths['resource_receipt'])['sha256'], candidate['runtime_preparation_sidecar']['sha256'], 'Windows resource receipt')
    manifest, receipt = document(paths['manifest']), document(paths['capability_receipt'])
    prepared, resource = document(paths['prepared_inputs']), document(paths['resource_receipt'])
    same(manifest.get('schema'), 'fdisbull-retained-runtime-base-1', 'Windows manifest schema')
    same(manifest.get('qualification_claimed'), False, 'original qualification claim')
    origin = manifest['origin_process']
    same(manifest['origin_source_commit'], ORIGIN_SOURCE, 'Windows origin source')
    same(origin['source_commit'], ORIGIN_SOURCE, 'original process source')
    if (type(origin.get('exit_code')) is not int or origin['exit_code'] != 2
            or origin.get('termination') != 'exited' or origin.get('execution_origin') != 'local-linux'
            or origin.get('container_state_after_stop') != 'stopped' or origin.get('job_name') != 'native-unified'):
        raise ValueError('Original failed process lineage differs')
    post = manifest['origin_source_postcheck']
    if post.get('source_commit') != ORIGIN_SOURCE or post.get('expected_source_commit') != ORIGIN_SOURCE or post.get('tracked_worktree_dirty') is not False or post.get('export_success') is not True:
        raise ValueError('Original source postcheck differs')
    same(receipt.get('schema'), 'fdisbull-retained-base-preparation-1', 'Windows capability schema')
    same(prepared.get('schema'), 'fdisbull-unified-runtime-inputs-1', 'Windows preparation schema')
    for value in (receipt, prepared):
        same(value['source_commit'], PREPARATION_SOURCE, 'donor preparation source')
        same(value['build_job_id'], report['source_and_provenance_bindings']['build_job_id'], 'donor build job')
        same(value['local_run_id'], report['source_and_provenance_bindings']['local_run_id'], 'donor run')
    same(receipt['origin_source_commit'], ORIGIN_SOURCE, 'capability origin source')
    same(receipt['origin_job_exit_code'], 2, 'preserved original failed result')
    same(receipt['manifest_sha256'], identity(paths['manifest'])['sha256'], 'capability manifest')
    same(receipt['os_capabilities'], report['capabilities']['os_capabilities'], 'reported Windows capabilities')
    caps = set(receipt['os_capabilities'])
    if not {'wine64', 'pe32'} <= caps or set(manifest['os_inventory']['capabilities']) != caps:
        raise ValueError('Full Windows dependencies absent')
    ref = prepared['retained_base']
    same({k: ref['windows_runtime'][k] for k in ('size', 'sha256')}, actual, 'prepared Windows image')
    same({k: ref['manifest'][k] for k in ('size', 'sha256')}, identity(paths['manifest']), 'prepared manifest edge')
    same({k: ref['preparation'][k] for k in ('size', 'sha256')}, identity(paths['capability_receipt']), 'prepared capability edge')
    same({k: ref['windows_resources'][k] for k in ('size', 'sha256')}, identity(paths['resource_receipt']), 'prepared resource edge')
    same(resource['runtime_sha256'], actual['sha256'], 'Windows resource output')
    same(resource['base_sha256'], manifest['os_base']['sha256'], 'Windows parent base')
    bindings = report['source_and_provenance_bindings']
    for field in ('preparation_source_commit', 'prepared_inputs_source_commit'):
        same(bindings[field], PREPARATION_SOURCE, 'report preparation source')
    process, post = bindings['preparation_process'], bindings['preparation_source_postcheck']
    if (process.get('source_commit') != PREPARATION_SOURCE or process.get('exit_code') != 0
            or type(process.get('exit_code')) is not int or process.get('termination') != 'exited'
            or process.get('local_job_id') != receipt['build_job_id'] or process.get('local_run_id') != receipt['local_run_id']
            or post.get('source_commit') != PREPARATION_SOURCE or post.get('expected_source_commit') != PREPARATION_SOURCE
            or post.get('tracked_worktree_dirty') is not False or post.get('export_success') is not True):
        raise ValueError('Donor preparation result differs')
    if report['qualification_ceiling'].get('qualification_claimed') is not False or report['qualification_ceiling'].get('origin_job_exit_code') != 2:
        raise ValueError('Donor qualification ceiling differs')
    return {'image': str(regular(paths['image'])), 'identity': actual, 'origin_exit_code': 2,
            'qualification_claimed': False, 'documents': {name: identity(paths[name]) for name in paths if name != 'image'},
            'origin_source_commit': ORIGIN_SOURCE, 'preparation_source_commit': PREPARATION_SOURCE,
            'capabilities': sorted(caps)}


def validate(config):
    """Read-only validation; no Linux execution, output writes or installations."""
    same(config.get('schema'), 'fdisbull-chat-retained-inputs-v1', 'config schema')
    same(config.get('application_source_commit'), SOURCE, 'application source')
    same(config.get('application_version'), VERSION, 'application version')
    harness = config.get('harness_source_commit')
    if harness is not None and (not isinstance(harness, str) or not re.fullmatch('[0-9a-f]{40}', harness)):
        raise ValueError('Invalid harness source identity')
    root = Path(config['export_root'])
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError('Unsafe export root')
    metadata, post = document(config['job_metadata']), document(config['source_postcheck'])
    if (metadata.get('schema') != 'fdisbull-ovh-result-export-v1' or metadata.get('source_commit') != SOURCE
            or metadata.get('pipeline_id') != PIPELINE or metadata.get('job_id') != JOB
            or metadata.get('job_name') != 'native-unified' or metadata.get('job_status') != 'success'
            or metadata.get('export_success') is not True):
        raise ValueError('Original hosted export identity differs')
    if post.get('source_commit') != SOURCE or post.get('expected_source_commit') != SOURCE or post.get('tracked_worktree_dirty') is not False or post.get('export_success') is not True:
        raise ValueError('Hosted source postcheck differs')
    same(identity(config['export_inventory'])['sha256'], EXPORT_INVENTORY_SHA, 'pinned hosted inventory')
    entries = document(config['export_inventory'])
    if not isinstance(entries, list) or len(entries) != metadata.get('files'):
        raise ValueError('Closed export inventory missing')
    rows = {}
    for entry in entries:
        name = safe_relative(entry['path'])
        if name in rows:
            raise ValueError('Duplicate export inventory path')
        same(identity(root / name), {k: entry[k] for k in ('size', 'sha256')}, name)
        rows[name] = entry
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(rows) or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Closed export files differ from inventory')
    backend = document(root / 'native-evidence/pe/backend-identity.json')
    same(backend['source_commit'], SOURCE, 'hosted backend source')
    same(backend['version'], VERSION, 'hosted backend version')
    project = PurePosixPath(metadata['project_directory'])
    if not project.is_absolute() or '..' in project.parts:
        raise ValueError('Unsafe original project directory')
    for key, name in INPUTS.items():
        ref = backend['inputs'][key]
        same(str(PurePosixPath(ref['path']).relative_to(project)), name, key + ' original path')
        same({k: ref[k] for k in ('size', 'sha256')}, {k: rows[name][k] for k in ('size', 'sha256')}, key)
    for name, pin in PINS.items():
        same(rows[name]['sha256'], pin, name + ' pinned hash')
    core = next(name for name in PINS if name.endswith('.whl') and '/fdisbull-' in name)
    same({k: backend['wheel'][k] for k in ('size', 'sha256')}, {k: rows[core][k] for k in ('size', 'sha256')}, 'tested core wheel')
    wheelhouse = Path(config['wheelhouse'])
    pins = helpers.wheel_pins(wheelhouse)
    if set(pins) != builder.RUNTIME_WHEELS or pins['fdisbull'] != VERSION or pins['fdisbull-player'] != VERSION:
        raise ValueError('Prepared wheelhouse distribution set differs')
    for name in (n for n in PINS if n.endswith('.whl')):
        same(identity(wheelhouse / Path(name).name), {k: rows[name][k] for k in ('size', 'sha256')}, 'wheelhouse package')
    firmware = sorted(name for name in rows if name.startswith('.native/pe/qemu-9.2.4/pc-bios/'))
    if len(firmware) != 171 or not all('.native/pe/qemu-9.2.4/pc-bios/' + n in rows for n in ('bios-256k.bin', 'vgabios-stdvga.bin')):
        raise ValueError('QEMU firmware set differs')
    prefix = Path(config['python_prefix'])
    if not prefix.is_absolute() or not prefix.is_dir() or prefix.is_symlink():
        raise ValueError('Unsafe Python prefix')
    licenses = [regular(p) for p in config['licenses']]
    if not licenses or len({p.name + str(p.parent) for p in licenses}) != len(licenses):
        raise ValueError('Explicit license inputs required')
    return {'root': root, 'rows': rows, 'backend': backend, 'firmware': firmware,
            'pins': pins, 'windows': windows_donor(config),
            'hosted_origin': {'execution_origin': 'gitlab', 'pipeline_id': PIPELINE, 'job_id': JOB,
                              'source_commit': SOURCE, 'job_status': 'success'},
            'documents': {k: identity(config[k]) for k in ('export_inventory', 'job_metadata', 'source_postcheck')}}


def verify_installed_core(prefix, wheel):
    """Bind the imported guest preparer/resources to the pinned wheel bytes."""
    with zipfile.ZipFile(regular(wheel)) as archive:
        metadata = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA') and name.count('/') == 1]
        if len(metadata) != 1:
            raise ValueError('Invalid installed core wheel metadata')
        dist_info = metadata[0].split('/')[0]
        for member in archive.infolist():
            if member.is_dir() or member.filename.endswith('.dist-info/RECORD'):
                continue
            inventory.installed_wheel_member(prefix, member.filename, archive.read(member), dist_info)


def prepare(config, output):
    output = Path(output)
    if not output.is_absolute() or output.is_symlink() or not output.is_dir() or any(output.iterdir()):
        raise ValueError('Output must be an existing empty absolute directory')
    if sys.platform != 'linux' or platform.machine() != 'x86_64' or sys.version_info[:3] != (3, 13, 5):
        raise ValueError('Materialization requires Linux x86_64 CPython 3.13.5')
    checked = validate(config)
    import fdisbull
    prefix = Path(config['python_prefix']).resolve(strict=True)
    if Path(sys.prefix).resolve() != prefix or not Path(fdisbull.__file__).resolve().is_relative_to(prefix) or fdisbull.__version__ != VERSION:
        raise ValueError('Run with the prepared installed application Python prefix')
    verify_installed_core(prefix, Path(config['wheelhouse']) / 'fdisbull-0.34.1-py3-none-any.whl')
    root = checked['root']
    dosbox, qemu = output / 'dosbox-x', output / 'qemu-system-x86_64'
    strip = regular(Path(config.get('strip', '/usr/bin/strip')).resolve(strict=True))
    transformations = {
        'dosbox': helpers.stripped_copy(root / INPUTS['FDISBULL_DOSBOX'], dosbox, strip),
        'qemu': helpers.stripped_copy(root / INPUTS['FDISBULL_PE_QEMU'], qemu, strip)}
    base, windows = output / 'base.cpio.xz', output / 'windows-base.cpio.xz'
    expanded = helpers.compress_base(root / INPUTS['FDISBULL_PE_INITRAMFS'], base)
    full_expanded = helpers.compress_base(Path(checked['windows']['image']), windows)
    outputs = runtime.materialize(base, output / 'measured-runtimes', dosbox, expanded)
    windows_output = runtime.materialize(windows, output / 'measured-windows', dosbox, full_expanded, windows_only=True)['wine']
    resources = runtime.resource_identities(dosbox)
    recipe, windows_recipe = output / 'runtime-recipe.json', output / 'windows-recipe.json'
    recipe.write_text(json.dumps({'schema': 'fdisbull-chat-runtime-recipe-v1', 'expanded_base': expanded,
                                  'resources': resources, 'outputs': outputs}, indent=2) + '\n')
    windows_recipe.write_text(json.dumps({'schema': 'fdisbull-chat-windows-recipe-v1', 'expanded_base': full_expanded,
                                          'resources': resources['wine'], 'output': windows_output}, indent=2) + '\n')
    provenance = output / 'input-provenance.json'
    harness = config.get('harness_source_commit')
    provenance.write_text(json.dumps({'schema': 'fdisbull-chat-retained-preparation-v1',
        'application_source_commit': SOURCE, 'application_version': VERSION,
        'harness_source_commit': harness, 'producer_sha256': identity(Path(__file__).resolve())['sha256'],
        'qualification': 'not-qualified-by-producer', 'hosted_origin': checked['hosted_origin'],
        'hosted_documents': checked['documents'], 'full_windows_donor': checked['windows'],
        'transformations': transformations, 'runtime_resources': resources,
        'runtime_outputs': outputs, 'windows_output': windows_output}, indent=2) + '\n')
    def item(path, destination, role='payload'):
        return {'source': str(regular(path)), 'destination': destination, 'role': role}
    inputs = [item(dosbox, 'native/dosbox-x', 'dosbox'), item(qemu, 'native/qemu/bin/qemu-system-x86_64', 'qemu'),
        item(Path(config.get('loader', '/lib64/ld-linux-x86-64.so.2')).resolve(strict=True), 'lib/ld-linux-x86-64.so.2', 'loader'),
        item(root / INPUTS['FDISBULL_PE_KERNEL'], 'runtime/kernel', 'kernel'),
        item(root / INPUTS['FDISBULL_PE_FIXTURE'], 'fixtures/oracle.exe', 'pe_fixture'),
        item(base, 'runtime/base.cpio.xz', 'runtime_base'), item(recipe, 'runtime/recipe.json', 'runtime_recipe'),
        item(windows, 'runtime/windows-base.cpio.xz', 'windows_runtime_base'),
        item(windows_recipe, 'runtime/windows-recipe.json', 'windows_runtime_recipe'),
        item(HERE.parent / 'prepare_chat_runtimes.py', 'tools/preparer.py', 'runtime_preparer'),
        item(HERE.parent / 'verify_chat_offline_kit.py', 'tools/verify.py', 'verifier'),
        item(root / next(n for n in PINS if 'source-companion' in n), 'source/dosbox-companion.tar', 'source_companion'),
        item(root / 'dist/fdisbull-0.34.1-tool.zip', 'source/fdisbull-tool.zip'),
        item(provenance, 'receipts/staging.json', 'python_receipt'),
        item(root / 'native-evidence/layers/backend-identity.json', 'receipts/dosbox.json', 'dosbox_receipt'),
        item(root / 'native-evidence/pe/backend-identity.json', 'receipts/qemu.json', 'qemu_receipt'),
        item(root / 'native-evidence/pe/runtime-packages.txt', 'receipts/wine-packages.txt', 'wine_receipt')]
    guide = HERE.parent.parent / 'docs/CHAT_OFFLINE_0966.md'
    if guide.is_file():
        inputs.append(item(guide, 'docs/START_HERE.md', 'documentation'))
    for name in checked['firmware']:
        inputs.append(item(root / name, 'native/qemu/share/qemu/' + name.split('/pc-bios/', 1)[1], 'firmware'))
    for index, path in enumerate(config['licenses']):
        inputs.append(item(path, 'licenses/' + str(index) + '-' + Path(path).parent.name + '.txt', 'license'))
    for name, path in config['full_windows'].items():
        if name != 'image':
            inputs.append(item(path, 'receipts/windows-' + name.replace('_', '-') + '.json'))
    for name in ('export_inventory', 'job_metadata', 'source_postcheck'):
        inputs.append(item(config[name], 'receipts/hosted-' + name.replace('_', '-') + '.json'))
    result = {'python_prefix': str(prefix), 'wheelhouse': str(Path(config['wheelhouse'])),
        'ldd': config.get('ldd', '/usr/bin/ldd'), 'wheel_versions': checked['pins'], 'inputs': inputs,
        'identities': {'source_commit': SOURCE, 'test_source_commit': harness or SOURCE, 'application_source_commit': SOURCE,
                       'application_version': VERSION, 'harness_source_commit': harness, 'python': '3.13.5',
                       'qemu': '9.2.4', 'wine': 'runtime-packages-sha256:' + identity(root / 'native-evidence/pe/runtime-packages.txt')['sha256'], 'version': VERSION}}
    target = output / 'config.json'
    target.write_text(json.dumps(result, indent=2) + '\n')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(prepare(document(args.config), args.output))
