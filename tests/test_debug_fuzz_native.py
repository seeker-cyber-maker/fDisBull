"""Source-only native-adapter checks with no emulator or guest process."""
import hashlib
import inspect
import json
from copy import deepcopy
from pathlib import Path

import pytest

from fdisbull import debug_fuzz_native as native
from fdisbull.cli import parser


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def native_case(tmp_path, monkeypatch):
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    game_dir = private / 'game'
    game_dir.mkdir(mode=0o700)
    target = game_dir / 'GAME.EXE'
    target.write_bytes(b'private original target bytes')
    fdb = private / 'analysis.fdb'
    fdb.write_bytes(b'fake private project')
    fdb.chmod(0o600)
    runtime = {}
    for name in ('emulator', 'kernel', 'initramfs'):
        path = private / name
        path.write_bytes(name.encode())
        path.chmod(0o700 if name == 'emulator' else 0o600)
        runtime[name] = path
    scratch = private / 'scratch'
    scratch.mkdir(mode=0o700)
    output = private / 'output'
    output.mkdir(mode=0o700)
    monkeypatch.setenv('TMPDIR', str(scratch))
    monkeypatch.setattr(native.tempfile, 'gettempdir', lambda: str(scratch))
    campaign = {'format': 'fdisbull-fuzz-1',
                'base_script': {'format': 'fdisbull-script-1', 'backend': 'wine-ne',
                                'steps': [{'op': 'keyboard.press', 'key': 'a'}]},
                'mutation_sites': [{'index': 0, 'field': 'key', 'choices': ['b']}],
                'max_cases': 2, 'timeout_ms': 1000}
    config = {'format': native.FORMAT, 'campaign': campaign, 'project': str(fdb),
              'executable': str(runtime['emulator']), 'kernel': str(runtime['kernel']),
              'initramfs': str(runtime['initramfs']), 'game_dir': str(game_dir),
              'backend': 'wine-ne', 'output_dir': str(output), 'scratch_dir': str(scratch),
              'files': ['GAME.EXE'], 'boot_timeout_ms': 1000,
              'memory_mib': 64, 'expected_bytes': 64*1024*1024, 'min_free_bytes': 0}
    config_file = private / 'campaign.json'

    def write_config():
        config_file.write_text(json.dumps(config))
        config_file.chmod(0o600)
        return config_file

    class Process:
        def __init__(self):
            self.reaped = False

        def poll(self):
            return 0 if self.reaped else None

    class Session:
        script_operations = {'keyboard.press'}

        def __init__(self, owner):
            self.owner = owner
            self.backend_name = ('wine-ne-qemu' if config['backend'] == 'wine-ne'
                                 else 'wine-qemu')
            self.run_id = f'{len(owner.sessions):032x}'
            self.closed = False
            self.rpc = type('Rpc', (), {'process': Process()})()
            self.metadata = {'source_sha256': _sha(target),
                             'runtime_inputs': {
                                 'qemu': {'sha256': _sha(runtime['emulator'])},
                                 'kernel': {'sha256': _sha(runtime['kernel'])},
                                 'initramfs': {'sha256': _sha(runtime['initramfs'])}},
                             'files': [{'path': name, 'sha256': _sha(game_dir / name)}
                                       for name in config['files']]}

        def keyboard_press(self, key, *, modifiers=(), hold_ms=40, gap_ms=40):
            return {'accepted': True}

        def scene_act(self, scene, object, *, handle_popups=False,
                      timeout_ms=None, slice_ms=100, compact=False):
            return {'accepted': True}

        def script(self, script, *, timeout_ms):
            self.owner.script_timeouts.append(timeout_ms)
            if script['steps'][0]['op'] == 'scene-act':
                self.owner.script_scenes.append(script['steps'][0]['scene'])
                if self.owner.rotate_scenes and len(self.owner.sessions) == 1:
                    self.owner.scene_names.update(poster='c'*32, bilge='d'*32)
                    self.owner.scene_revisions.update({'c'*32: '3'*64, 'd'*32: '4'*64})
            encoded = json.dumps(script, sort_keys=True, separators=(',', ':')).encode()
            result = {'script_sha256': hashlib.sha256(encoded).hexdigest(),
                      'run': self.run_id, 'ok': True, 'completed_steps': 1,
                      'steps': [{'op': script['steps'][0]['op'], 'ok': True,
                                 'result': {'guest_text': 'SECRET GAME TEXT'}}]}
            if self.owner.wrong_script_hash:
                result['script_sha256'] = '0'*64
            if self.owner.native_exception:
                result.update(ok=False, completed_steps=0,
                    steps=[{'op': 'run', 'ok': False, 'error': {'type': 'ValueError'},
                            'result': {'outcome': 'exception',
                            'session': {'stop_reason': {'kind': 'exception',
                                'exception_code': 0xc0000005, 'access_address': '0x0',
                                'first_chance': 0, 'project_address': 'ne:2:0x1234'}}}}])
            if self.owner.mutate_target:
                target.write_bytes(b'changed private original')
            if self.owner.mutate_asset:
                (game_dir / 'ASSET.DAT').write_bytes(b'changed asset')
            return result

        def close(self):
            self.closed = True
            self.rpc.process.reaped = not self.owner.leave_running

    class Project:
        sessions = []
        launch_options = []
        script_timeouts = []
        script_scenes = []
        scene_names = {'poster': 'a'*32, 'bilge': 'b'*32}
        scene_revisions = {'a'*32: '1'*64, 'b'*32: '2'*64}
        rotate_scenes = False
        mutate_target = False
        mutate_asset = False
        leave_running = False
        wrong_script_hash = False
        native_exception = False

        def __init__(self, path):
            self.path = Path(path)
            self.meta = {'format': 'NE' if config['backend'] == 'wine-ne' else 'PE',
                         'filename': 'GAME.EXE',
                         'source_sha256': _sha(target)}
            self.session = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            if self.session is not None and not self.session.closed:
                self.session.close()

        def version(self, version):
            return {'parent': None}

        def debug_scene_info(self, scene, *, version=None):
            ident = self.scene_names.get(scene, scene)
            digest = self.scene_revisions.get(ident)
            if digest is None:
                raise ValueError('Unknown fake scene')
            return {'id': ident, 'sha256': digest}

        def debugger(self, executable, game_directory, **options):
            assert Path(executable) == runtime['emulator']
            assert Path(game_directory) == game_dir
            self.launch_options.append(options)
            self.session = Session(self)
            self.sessions.append(self.session)
            return self.session

    return config, write_config, Project, target, output, scratch


def test_packaged_native_runner_fresh_sessions_private_sanitized_report(native_case):
    config, write_config, Project, target, output, scratch = native_case
    result = native.run_native_fuzz(write_config(), project_factory=Project)
    report = result['report']
    assert report['planned_cases'] == report['executed_cases'] == 2
    assert report['stop_reason'] == 'completed'
    assert len({item['run_id'] for item in report['cases']}) == 2
    assert all(item['owned_process_reaped'] and item['status'] == 'passed'
               for item in report['cases'])
    assert all(session.closed and session.rpc.process.reaped for session in Project.sessions)
    adapter_parts = {'fuzzer': _sha(native.__file__),
                     'planner': _sha(inspect.getfile(native.plan_campaign)),
                     'session': _sha(inspect.getfile(type(Project.sessions[0])))}
    from fdisbull.debug_script import execute_script
    from fdisbull.windows_ui import WindowsUIMixin
    from fdisbull.scenes import SceneSessionMixin
    adapter_parts.update(script=_sha(inspect.getfile(execute_script)),
                         windows_ui=_sha(inspect.getfile(WindowsUIMixin)),
                         scenes=_sha(inspect.getfile(SceneSessionMixin)))
    expected_adapter = hashlib.sha256(json.dumps(adapter_parts, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    assert report['cases'][0]['adapter_sha256'] == expected_adapter
    assert all(options['window'] is False and options['memory_mib'] == 64
               for options in Project.launch_options)
    assert Project.script_timeouts == [1000, 1000]
    serialized = json.dumps(result)
    assert 'SECRET GAME TEXT' not in serialized
    assert 'private original target bytes' not in serialized
    assert 'keyboard.press' in serialized  # stage op only, no raw step values
    assert '"key": "a"' not in serialized and '"key": "b"' not in serialized
    assert (output / result['artifact']['id']).is_file()


def test_native_runner_stops_on_changed_target_and_unreaped_process(native_case):
    _, write_config, Project, target, _, _ = native_case
    Project.mutate_target = True
    result = native.run_native_fuzz(write_config(), project_factory=Project)['report']
    assert result['executed_cases'] == 1
    assert result['stop_reason'] == 'outcome_unknown'
    assert result['cases'][0]['status'] == 'unknown'


def test_native_runner_stops_on_changed_explicit_asset(native_case):
    config, write_config, Project, target, _, _ = native_case
    (target.parent / 'ASSET.DAT').write_bytes(b'private asset')
    config['files'].append('ASSET.DAT')
    Project.mutate_asset = True
    report = native.run_native_fuzz(write_config(), project_factory=Project)['report']
    assert report['executed_cases'] == 1
    assert report['cases'][0]['status'] == 'unknown'


def test_win32_and_win64_route_use_same_wine_adapter_path(native_case):
    config, write_config, Project, _, _, _ = native_case
    config['backend'] = 'wine-qemu'
    config['campaign']['base_script']['backend'] = 'wine-qemu'
    for bits in (32, 64):
        Project.bits = bits
        Project.sessions.clear()
        Project.launch_options.clear()
        report = native.run_native_fuzz(write_config(), project_factory=Project)['report']
        assert report['stop_reason'] == 'completed'
        assert len(Project.sessions) == 2
        assert all(session.owner.bits == bits for session in Project.sessions)
        assert all(options['backend'] == 'wine-qemu' and options['window'] is False
                   for options in Project.launch_options)


def test_scene_names_and_mutation_choices_pin_old_revisions_across_cases(native_case):
    config, write_config, Project, _, _, _ = native_case
    config['campaign']['base_script']['steps'] = [
        {'op': 'scene-act', 'scene': 'poster', 'object': 'chair'}]
    config['campaign']['mutation_sites'] = [
        {'index': 0, 'field': 'scene', 'choices': ['bilge']}]
    Project.rotate_scenes = True
    report = native.run_native_fuzz(write_config(), project_factory=Project)['report']
    assert report['stop_reason'] == 'completed'
    assert Project.script_scenes == ['a'*32, 'b'*32]
    assert Project.scene_names == {'poster': 'c'*32, 'bilge': 'd'*32}
    assert 'poster' not in json.dumps(report) and 'bilge' not in json.dumps(report)


def test_native_runner_stops_when_owned_guest_is_not_reaped(native_case):
    _, write_config, Project, _, _, _ = native_case
    Project.leave_running = True
    result = native.run_native_fuzz(write_config(), project_factory=Project)['report']
    assert result['executed_cases'] == 1
    assert result['stop_reason'] == 'cleanup_unverified'
    assert result['cases'][0]['owned_process_reaped'] is False


def test_native_runner_rejects_unbound_script_receipt_after_reaping(native_case):
    _, write_config, Project, _, _, _ = native_case
    Project.wrong_script_hash = True
    with pytest.raises(RuntimeError, match='native_fuzz_no_bound_script_receipt'):
        native.run_native_fuzz(write_config(), project_factory=Project)
    assert len(Project.sessions) == 1
    assert Project.sessions[0].closed and Project.sessions[0].rpc.process.reaped


def test_native_runner_exception_stop_is_candidate_without_raw_address(native_case):
    _, write_config, Project, _, _, _ = native_case
    Project.native_exception = True
    report = native.run_native_fuzz(write_config(), project_factory=Project)['report']
    assert report['cases'][0]['status'] == 'failed'
    assert report['cases'][0]['fault_family'].startswith('exception-stop-')
    assert 'ne:2:0x1234' not in json.dumps(report)
    assert 'not proven crashes' in report['qualification']


def test_exception_family_accepts_direct_and_scene_wrapped_native_stops_only():
    stop = {'kind': 'exception', 'exception_code': 0xc0000005,
            'first_chance': 0, 'access_address': '0x0',
            'project_address': 'ne:2:0x1234'}
    advance = {'outcome': 'exception', 'session': {'stop_reason': stop}}
    direct = {'op': 'run', 'ok': False, 'error': {'type': 'ValueError'},
              'result': advance}
    candidate = native._fault_family({'steps': [direct]})
    assert candidate is not None and candidate.startswith('exception-stop-')
    other_code = deepcopy(direct)
    other_code['result']['session']['stop_reason']['exception_code'] = 0xc0000006
    assert native._fault_family({'steps': [other_code]}) != candidate
    nonnull_a = deepcopy(direct)
    nonnull_b = deepcopy(direct)
    nonnull_a['result']['session']['stop_reason']['access_address'] = '0x1000'
    nonnull_b['result']['session']['stop_reason']['access_address'] = '0x2000'
    assert native._fault_family({'steps': [nonnull_a]}) == native._fault_family({'steps': [nonnull_b]})
    assert native._fault_family({'steps': [nonnull_a]}) != candidate
    for operation in ('scene-act', 'scene-wait'):
        scene = {'op': operation, 'ok': False, 'error': {'type': 'SceneError'},
                 'result': {'status': 'stopped', 'complete': False, 'stop': deepcopy(advance)}}
        assert native._fault_family({'steps': [scene]}) == candidate
        for change in (
            lambda item: item['error'].__setitem__('type', 'ValueError'),
            lambda item: item['result'].__setitem__('status', 'timeout'),
            lambda item: item['result']['stop'].__setitem__('outcome', 'slice'),
            lambda item: item['result']['stop']['session']['stop_reason'].__setitem__('kind', 'timeout'),
            lambda item: item.__setitem__('ok', True),
        ):
            invalid = deepcopy(scene)
            change(invalid)
            assert native._fault_family({'steps': [invalid]}) is None
    unrelated = {'op': 'scene-check', 'ok': False, 'error': {'type': 'SceneError'},
                 'result': {'status': 'stopped', 'complete': False, 'stop': advance}}
    assert native._fault_family({'steps': [unrelated]}) is None


def test_adapter_identity_changes_when_scene_semantics_change(native_case, monkeypatch):
    _, _, Project, _, _, _ = native_case
    original = native._digest
    before = native._adapter_sha(native._session_class('wine-ne'))
    monkeypatch.setattr(native, '_digest',
        lambda path: '0'*64 if Path(path).name == 'scenes.py' else original(path))
    assert native._adapter_sha(native._session_class('wine-ne')) != before


def test_project_pool_reserve_checked_before_native_launch(native_case, monkeypatch):
    config, write_config, Project, _, _, _ = native_case
    project_parent = Path(config['project']).parent
    monkeypatch.setattr(native.shutil, 'disk_usage',
        lambda path: type('Usage', (), {'free': 0 if Path(path) == project_parent else 10**12})())
    with pytest.raises(ValueError, match='native_fuzz_storage_reserve'):
        native.run_native_fuzz(write_config(), project_factory=Project)
    assert Project.sessions == []


def test_native_preflight_refuses_dos_and_invalid_plan_before_launch(native_case):
    config, write_config, Project, _, _, _ = native_case
    config['backend'] = 'dosbox'
    with pytest.raises(ValueError, match='native_fuzz_unsupported_backend'):
        native.run_native_fuzz(write_config(), project_factory=Project)
    assert Project.sessions == []
    config['backend'] = 'wine-ne'
    config['campaign']['mutation_sites'][0]['choices'] = ['invalid-key']
    with pytest.raises(ValueError):
        native.run_native_fuzz(write_config(), project_factory=Project)
    assert Project.sessions == []


def test_native_preflight_requires_caller_tmpdir_and_storage_budget(native_case, monkeypatch):
    config, write_config, Project, _, _, _ = native_case
    monkeypatch.setenv('TMPDIR', str(config['output_dir']))
    with pytest.raises(ValueError, match='native_fuzz_scratch_tmpdir_unavailable'):
        native.run_native_fuzz(write_config(), project_factory=Project)
    assert Project.sessions == []
    monkeypatch.setenv('TMPDIR', config['scratch_dir'])
    config['min_free_bytes'] = 1024**4
    with pytest.raises(ValueError, match='native_fuzz_storage_reserve'):
        native.run_native_fuzz(write_config(), project_factory=Project)
    assert Project.sessions == []


def test_fuzz_cli_is_one_shot_and_has_no_host_input_switch():
    args = parser().parse_args(['fuzz', '/private/campaign.json'])
    assert args.command == 'fuzz' and args.configuration == '/private/campaign.json'
    assert not hasattr(args, 'fair_play') and not hasattr(args, 'window')
