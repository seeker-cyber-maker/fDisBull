"""Finite original-program fuzz campaigns using owned debugger sessions.

The public receipt contains no script, guest output, file bytes, or raw fault
address. Full route results remain in the private FDB written by session.script.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

from .debug_fuzz import plan_campaign, run_campaign
from .guest_assets import uploads
from .output_artifacts import OutputArtifactStore, _json_decode, _private_directory
from .project import Project


FORMAT = 'fdisbull-native-fuzz-1'
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_KEYS = frozenset({'format', 'campaign', 'project', 'executable', 'game_dir',
    'backend', 'kernel', 'initramfs', 'output_dir', 'scratch_dir', 'files',
    'memory_mib', 'boot_timeout_ms', 'expected_bytes', 'min_free_bytes'})


def _digest(path: Path) -> str:
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _file(value, *, executable=False) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError('native_fuzz_invalid_path')
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file() or (executable and not os.access(path, os.X_OK)):
        raise ValueError('native_fuzz_invalid_file')
    return path


def _private_path(value) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError('native_fuzz_invalid_private_path')
    path = Path(os.path.abspath(os.path.expanduser(value)))
    if not path.parent.is_dir():
        raise ValueError('native_fuzz_invalid_private_path')
    _private_directory(path.parent)
    if path.is_symlink():
        raise ValueError('native_fuzz_unsafe_file')
    return _file(str(path))


def _private_file(path: Path) -> None:
    _private_directory(path.parent)
    if path.is_symlink():
        raise ValueError('native_fuzz_unsafe_file')
    st = path.stat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
            or stat.S_IMODE(st.st_mode) & 0o077):
        raise ValueError('native_fuzz_file_not_private')


def _session_class(backend: str):
    if backend == 'wine-ne':
        from .win16_debugger import Win16DebugSession
        return Win16DebugSession
    if backend == 'wine-qemu':
        from .wine_debugger import PEDebugSession
        return PEDebugSession
    raise ValueError('native_fuzz_unsupported_backend')


def _adapter_sha(session_class) -> str:
    """Bind all source modules that select, execute, and score the route."""
    from .debug_script import execute_script
    from .windows_ui import WindowsUIMixin
    from .scenes import SceneSessionMixin
    parts = {'fuzzer': _digest(Path(__file__).resolve()),
             'planner': _digest(Path(inspect.getfile(plan_campaign)).resolve()),
             'session': _digest(Path(inspect.getfile(session_class)).resolve()),
             'script': _digest(Path(inspect.getfile(execute_script)).resolve()),
             'windows_ui': _digest(Path(inspect.getfile(WindowsUIMixin)).resolve()),
             'scenes': _digest(Path(inspect.getfile(SceneSessionMixin)).resolve())}
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _runtime_sha(hashes: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _load_configuration(path) -> dict:
    config_path = _private_path(os.fspath(path))
    _private_file(config_path)
    if config_path.stat().st_size > 1024 * 1024:
        raise ValueError('native_fuzz_config_too_large')
    try:
        document = _json_decode(config_path.read_bytes())
    except ValueError:
        raise ValueError('native_fuzz_invalid_json') from None
    if (not isinstance(document, dict) or document.get('format') != FORMAT
            or set(document) - _KEYS or not isinstance(document.get('campaign'), dict)):
        raise ValueError('native_fuzz_invalid_configuration')
    required = {'project', 'executable', 'game_dir', 'backend', 'output_dir', 'scratch_dir'}
    if not required <= set(document):
        raise ValueError('native_fuzz_missing_configuration')
    backend = document['backend']
    if backend not in ('wine-ne', 'wine-qemu'):
        raise ValueError('native_fuzz_unsupported_backend')
    # This validates the entire finite mutation set before any guest launch.
    plan_campaign(document['campaign'])
    script_backend = document['campaign']['base_script'].get('backend')
    if script_backend != backend:
        raise ValueError('native_fuzz_script_backend_mismatch')
    timeout = document.get('boot_timeout_ms', 240000)
    if type(timeout) is not int or not 1000 <= timeout <= 600000:
        raise ValueError('native_fuzz_invalid_boot_timeout')
    memory = document.get('memory_mib')
    if memory is not None and (type(memory) is not int or not 16 <= memory <= 8192):
        raise ValueError('native_fuzz_invalid_memory')
    files = document.get('files')
    if files is not None and (not isinstance(files, list) or not 1 <= len(files) <= 1024):
        raise ValueError('native_fuzz_invalid_files')
    if not {'kernel', 'initramfs', 'expected_bytes', 'min_free_bytes'} <= set(document):
        raise ValueError('native_fuzz_windows_runtime_missing')
    expected_bytes = document['expected_bytes']
    min_free_bytes = document['min_free_bytes']
    if (type(expected_bytes) is not int or not 64*1024*1024 <= expected_bytes <= 64*1024**3
            or type(min_free_bytes) is not int or not 0 <= min_free_bytes <= 1024**4):
        raise ValueError('native_fuzz_invalid_storage_budget')
    output = _private_directory(document['output_dir'])
    scratch = _private_directory(document['scratch_dir'])
    if output == scratch or output in scratch.parents or scratch in output.parents:
        raise ValueError('native_fuzz_output_scratch_overlap')
    project = _private_path(document['project'])
    _private_file(project)
    game_dir = Path(document['game_dir']).expanduser().resolve(strict=True)
    if not game_dir.is_dir():
        raise ValueError('native_fuzz_invalid_game_dir')
    executable = _file(document['executable'], executable=True)
    runtime_paths = {'emulator': executable,
                     'kernel': _file(document['kernel']),
                     'initramfs': _file(document['initramfs'])}
    return {'campaign': document['campaign'], 'backend': backend, 'project': project,
            'game_dir': game_dir, 'output_dir': output, 'scratch_dir': scratch,
            'runtime_paths': runtime_paths, 'files': files, 'memory_mib': memory,
            'boot_timeout_ms': timeout, 'expected_bytes': expected_bytes,
            'min_free_bytes': min_free_bytes}


def _manifest(settings: dict, project_factory) -> dict:
    with project_factory(settings['project']) as project:
        expected = {'wine-ne': ('NE',),
                    'wine-qemu': ('PE',)}[settings['backend']]
        if project.meta['format'] not in expected or project.version(None)['parent'] is not None:
            raise ValueError('native_fuzz_project_backend_mismatch')
        target = project.meta['filename']
        staged = uploads(project, settings['game_dir'], target, settings['files'])
        asset_hashes = {item['path']: item['sha256'] for item in staged}
        source = project.meta['source_sha256']
        if not _SHA.fullmatch(source):
            raise ValueError('native_fuzz_invalid_source_identity')
        pinned_campaign, scene_pins = _pin_campaign(project, settings['campaign'])
        # Revalidation covers rewritten names and every generated candidate.
        plan_campaign(pinned_campaign)
        settings['campaign'] = pinned_campaign
    runtime_hashes = {name: _digest(path) for name, path in settings['runtime_paths'].items()}
    return {'target': target, 'source': source, 'asset_hashes': asset_hashes,
            'scene_pins': scene_pins,
            'runtime_hashes': runtime_hashes,
            'runtime_sha': _runtime_sha(runtime_hashes),
            'adapter_sha': _adapter_sha(_session_class(settings['backend']))}


def _pin_campaign(project, document: dict) -> tuple[dict, dict[str, str]]:
    pinned = deepcopy(document)
    revisions: dict[str, str] = {}

    def revision(value):
        info = project.debug_scene_info(value)
        ident, digest = info.get('id'), info.get('sha256')
        if (not isinstance(ident, str) or not re.fullmatch(r'[0-9a-f]{32}', ident)
                or not isinstance(digest, str) or not _SHA.fullmatch(digest)):
            raise ValueError('native_fuzz_invalid_scene_revision')
        by_id = project.debug_scene_info(ident)
        if by_id.get('id') != ident or by_id.get('sha256') != digest:
            raise ValueError('native_fuzz_ambiguous_scene_revision')
        old = revisions.setdefault(ident, digest)
        if old != digest:
            raise ValueError('native_fuzz_scene_revision_changed')
        return ident

    steps = pinned['base_script']['steps']
    for step in steps:
        if step['op'] in ('scene-act', 'scene-check', 'scene-wait'):
            step['scene'] = revision(step['scene'])
    for site in pinned['mutation_sites']:
        if site['field'] == 'scene':
            site['choices'] = [revision(choice) for choice in site['choices']]
    return pinned, revisions


def _scenes_unchanged(project, revisions: dict[str, str]) -> None:
    for ident, digest in revisions.items():
        info = project.debug_scene_info(ident)
        if info.get('id') != ident or info.get('sha256') != digest:
            raise ValueError('native_fuzz_scene_revision_changed')


def _files_unchanged(settings: dict, manifest: dict) -> bool:
    try:
        for name, expected in manifest['asset_hashes'].items():
            path = settings['game_dir'] / name
            if (any(parent.is_symlink() for parent in (path, *path.parents)
                    if parent != settings['game_dir'].parent) or not path.is_file()
                    or not path.resolve().is_relative_to(settings['game_dir'])):
                return False
            if _digest(path) != expected:
                return False
        for name, path in settings['runtime_paths'].items():
            if _digest(path) != manifest['runtime_hashes'][name]:
                return False
        return True
    except (OSError, ValueError):
        return False


def _validate_scratch_tmpdir(scratch: Path) -> None:
    """Require the caller to select external scratch before this process starts."""
    selected = os.environ.get('TMPDIR')
    if (not selected or Path(selected).expanduser().resolve() != scratch
            or Path(tempfile.gettempdir()).resolve() != scratch):
        raise ValueError('native_fuzz_scratch_tmpdir_unavailable')


def _storage_admitted(settings: dict) -> None:
    required = settings['expected_bytes'] + settings['min_free_bytes']
    for path in (settings['scratch_dir'], settings['output_dir'], settings['project'].parent):
        if shutil.disk_usage(path).free < required:
            raise ValueError('native_fuzz_storage_reserve')


def _live_identity(session, manifest: dict, settings: dict) -> tuple[str, str, str]:
    metadata = session.metadata
    source = metadata.get('source_sha256')
    if source != manifest['source']:
        raise ValueError('native_fuzz_live_source_mismatch')
    inputs = metadata.get('runtime_inputs')
    if not isinstance(inputs, dict):
        raise ValueError('native_fuzz_live_runtime_missing')
    observed = {name: inputs.get('qemu' if name == 'emulator' else name, {}).get('sha256')
                for name in settings['runtime_paths']}
    recorded = metadata.get('files')
    if (not isinstance(recorded, list) or
            {item.get('path'): item.get('sha256') for item in recorded if isinstance(item, dict)}
            != manifest['asset_hashes']):
        raise ValueError('native_fuzz_live_assets_mismatch')
    if observed != manifest['runtime_hashes']:
        raise ValueError('native_fuzz_live_runtime_mismatch')
    return source, _runtime_sha(observed), _adapter_sha(type(session))


def _exception_stop(record: dict) -> dict | None:
    """Recognize only direct run or retained SceneError advancement stops."""
    if not isinstance(record, dict) or record.get('ok') is not False:
        return None
    observed = record.get('result')
    if not isinstance(observed, dict):
        return None
    if record.get('op') == 'run':
        advance = observed
    elif (record.get('op') in ('scene-act', 'scene-wait')
          and isinstance(record.get('error'), dict)
          and record['error'].get('type') == 'SceneError'
          and observed.get('status') == 'stopped'
          and observed.get('complete') is False):
        advance = observed.get('stop')
    else:
        return None
    if not isinstance(advance, dict) or advance.get('outcome') != 'exception':
        return None
    session = advance.get('session')
    if not isinstance(session, dict):
        return None
    stop = session.get('stop_reason')
    return stop if isinstance(stop, dict) and stop.get('kind') == 'exception' else None


def _fault_family(result: dict) -> str | None:
    """Only an explicit unexpected native exception creates a candidate."""
    for record in reversed(result.get('steps', [])):
        stop = _exception_stop(record)
        if stop is None:
            continue
        code = stop.get('exception_code')
        try:
            number = int(code, 0) if isinstance(code, str) else code
        except ValueError:
            continue
        if type(number) is not int or not 0 <= number <= 0xffffffff:
            continue
        access = stop.get('access_code')
        if type(access) is not int or not 0 <= access <= 8:
            access = None
        source = stop.get('project_address')
        source_kind = 'mapped' if isinstance(source, str) and len(source) <= 128 else 'unmapped'
        address = stop.get('access_address')
        if address is None:
            address_kind = 'unknown'
        else:
            try:
                access_number = address if type(address) is int else int(address, 0)
                address_kind = 'null' if access_number == 0 else 'non-null'
            except (TypeError, ValueError):
                address_kind = 'unknown'
        chance = stop.get('first_chance')
        chance = chance if chance in (0, 1, False, True) else None
        # Hash any qualified address so the receipt does not disclose it.
        value = {'code': number, 'access': access, 'source_kind': source_kind,
                 'source': source if source_kind == 'mapped' else None,
                 'access_address_kind': address_kind, 'first_chance': chance}
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]
        return 'exception-stop-' + digest
    return None


def _run_case(case, settings: dict, manifest: dict, project_factory) -> dict:
    _storage_admitted(settings)
    if not _files_unchanged(settings, manifest):
        raise ValueError('native_fuzz_inputs_changed_before_launch')
    receipt = {'status': 'unknown', 'source_sha256': manifest['source'],
               'runtime_sha256': manifest['runtime_sha'],
               'adapter_sha256': manifest['adapter_sha'], 'completed_steps': 0,
               'stage_ids': [], 'fault_family': None, 'owned_process_reaped': False}
    session = process = result = None
    bound = False
    uncertain = False
    try:
        with project_factory(settings['project']) as project:
            try:
                if project.meta['source_sha256'] != manifest['source']:
                    raise ValueError('native_fuzz_project_source_changed')
                _scenes_unchanged(project, manifest['scene_pins'])
                kwargs = {'backend': settings['backend'], 'boot_timeout_ms': settings['boot_timeout_ms'],
                          'window': False}
                kwargs.update(kernel=settings['runtime_paths']['kernel'],
                              initramfs=settings['runtime_paths']['initramfs'],
                              files=list(manifest['asset_hashes']), memory_mib=settings['memory_mib'])
                session = project.debugger(settings['runtime_paths']['emulator'], settings['game_dir'], **kwargs)
                process = getattr(getattr(session, 'rpc', None), 'process', None)
                receipt['run_id'] = session.run_id
                receipt['source_sha256'], receipt['runtime_sha256'], receipt['adapter_sha256'] = _live_identity(session, manifest, settings)
                from .debug_script import validate_script
                validate_script(case.script, session=session)
                result = session.script(case.script, timeout_ms=case.timeout_ms)
                receipt['script_sha256'] = result.get('script_sha256')
                receipt['run_id'] = result.get('run')
                if (receipt['script_sha256'] != case.script_sha256
                        or receipt['run_id'] != session.run_id):
                    raise ValueError('native_fuzz_script_receipt_mismatch')
                bound = True
                completed = result.get('completed_steps')
                if type(completed) is not int or not 0 <= completed <= len(case.script['steps']):
                    raise ValueError('native_fuzz_invalid_script_result')
                records = result.get('steps')
                if not isinstance(records, list) or len(records) > len(case.script['steps']):
                    raise ValueError('native_fuzz_invalid_script_records')
                receipt['completed_steps'] = completed
                receipt['stage_ids'] = [f"s{index}.{case.script['steps'][index]['op']}"
                                        for index, item in enumerate(records) if item.get('ok') is True]
                if type(result.get('ok')) is not bool:
                    raise ValueError('native_fuzz_invalid_script_result')
                receipt['status'] = ('passed' if completed == len(case.script['steps'])
                                     else 'unknown') if result['ok'] else 'failed'
                if receipt['status'] == 'failed':
                    receipt['fault_family'] = _fault_family(result)
            finally:
                if session is not None and not getattr(session, 'closed', False):
                    session.close()
        # Project closes its live sessions on context exit. Process ownership is
        # verified below; there is no guest to reuse for the next case.
    except Exception:
        uncertain = True
    finally:
        if session is not None and not getattr(session, 'closed', False):
            try:
                session.close()
            except Exception:
                uncertain = True
        try:
            receipt['owned_process_reaped'] = process is not None and process.poll() is not None
        except Exception:
            receipt['owned_process_reaped'] = False
        if not _files_unchanged(settings, manifest):
            uncertain = True
        if uncertain or not receipt['owned_process_reaped']:
            receipt.update(status='unknown', fault_family=None, completed_steps=0, stage_ids=[])
    if not bound:
        raise RuntimeError('native_fuzz_no_bound_script_receipt')
    return receipt


def run_native_fuzz(configuration, *, project_factory=Project) -> dict:
    """Run one private, finite, source-bound campaign and store its safe report."""
    settings = _load_configuration(configuration)
    manifest = _manifest(settings, project_factory)
    if not _files_unchanged(settings, manifest):
        raise ValueError('native_fuzz_inputs_changed_before_launch')
    _validate_scratch_tmpdir(settings['scratch_dir'])
    report = run_campaign(settings['campaign'],
        lambda case: _run_case(case, settings, manifest, project_factory))
    report['qualification'] = ('source-bound; native outcome only where case receipts show a reaped owned process; '
                               'exception-stop families are candidates, not proven crashes')
    encoded = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    artifact = OutputArtifactStore(settings['output_dir']).put_stream([encoded])
    return {'ok': True, 'report': report, 'artifact': artifact}
