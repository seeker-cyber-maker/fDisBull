import importlib.util
import pathlib
import tempfile
import uuid

GUARD_PATH = pathlib.Path('/Users/tiga/.codex/bin/container_storage_guard.py')
SPEC = importlib.util.spec_from_file_location('container_storage_guard', GUARD_PATH)
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def configure_paths(tmp_path):
    GUARD.ROOT = str(tmp_path / 'external' / 'AppleContainer')
    GUARD.HOST_PLISTS = str(tmp_path / 'internal' / 'apple-container-launchd')
    pathlib.Path(GUARD.ROOT, 'containers').mkdir(parents=True)
    pathlib.Path(GUARD.HOST_PLISTS).mkdir(parents=True)


def test_preseeded_service_link_is_followed_and_preserved(tmp_path):
    configure_paths(tmp_path)
    args = ['run', '--name', 'named-probe', 'python:3.13-slim', 'python', '-c', 'pass']

    GUARD._prepare_container_service_link(args)

    external = pathlib.Path(GUARD.ROOT, 'containers', 'named-probe', 'service.plist')
    target = pathlib.Path(GUARD.HOST_PLISTS, 'containers__named-probe__service.plist')
    assert external.is_symlink()
    assert external.resolve() == target
    external.write_text('plist payload')
    assert target.read_text() == 'plist payload'
    assert external.is_symlink()


def test_existing_named_container_path_is_not_overwritten(tmp_path):
    configure_paths(tmp_path)
    container_dir = pathlib.Path(GUARD.ROOT, 'containers', 'already-there')
    container_dir.mkdir()
    config = container_dir / 'config.json'
    config.write_text('{"preserve": true}')
    service = container_dir / 'service.plist'
    service.write_text('existing external file')
    args = ['create', '--name', 'already-there', 'python:3.13-slim']
    before = list(args)

    GUARD._prepare_container_service_link(args)

    assert args == before
    assert config.read_text() == '{"preserve": true}'
    assert service.read_text() == 'existing external file'
    assert not service.is_symlink()


def test_unsafe_name_is_refused_before_path_creation(tmp_path):
    configure_paths(tmp_path)
    args = ['run', '--name', '../escape', 'python:3.13-slim']

    try:
        GUARD._prepare_container_service_link(args)
    except RuntimeError as exc:
        assert 'unsafe' in str(exc)
    else:
        raise AssertionError('unsafe container name was accepted')

    assert not (pathlib.Path(GUARD.ROOT).parent / 'escape').exists()


def test_payload_name_after_image_is_not_parsed_as_container_name(tmp_path):
    configure_paths(tmp_path)
    args = ['run', 'python:3.13-slim', '--name', 'payload']

    GUARD._prepare_container_service_link(args)

    assert args[1] == '--name'
    generated = args[2]
    assert str(uuid.UUID(generated)) == generated
    assert args[-2:] == ['--name', 'payload']
    assert (pathlib.Path(GUARD.ROOT, 'containers', generated, 'service.plist')).is_symlink()
    assert not (pathlib.Path(GUARD.ROOT, 'containers', 'payload')).exists()


def test_value_options_and_separator_keep_name_and_payload_arguments(tmp_path):
    configure_paths(tmp_path)
    args = [
        'run', '-e', 'K=V', '--memory', '1G', '--name', 'chosen-name',
        'python:3.13-slim', '--', '--name', 'payload',
    ]
    before = list(args)

    GUARD._prepare_container_service_link(args)

    assert args == before
    assert (pathlib.Path(GUARD.ROOT, 'containers', 'chosen-name', 'service.plist')).is_symlink()
    assert not (pathlib.Path(GUARD.ROOT, 'containers', 'payload')).exists()


def test_help_request_does_not_preseed_a_service(tmp_path):
    configure_paths(tmp_path)
    args = ['run', '--name', 'help-probe', '--help']
    before = list(args)

    GUARD._prepare_container_service_link(args)

    assert args == before
    assert not pathlib.Path(GUARD.ROOT, 'containers', 'help-probe').exists()
    assert not pathlib.Path(GUARD.HOST_PLISTS, 'containers__help-probe__service.plist').exists()


def test_missing_name_value_does_not_preseed_a_service(tmp_path):
    configure_paths(tmp_path)
    args = ['run', '--name']
    before = list(args)

    GUARD._prepare_container_service_link(args)

    assert args == before
    assert list(pathlib.Path(GUARD.ROOT, 'containers').iterdir()) == []


def test_abandoned_owned_preseed_is_valid_and_safe_for_bridge_sweep(tmp_path):
    configure_paths(tmp_path)
    args = ['run', '--name', 'abandoned-probe', 'python:3.13-slim']

    GUARD._prepare_container_service_link(args)

    external = pathlib.Path(GUARD.ROOT, 'containers', 'abandoned-probe', 'service.plist')
    target = pathlib.Path(GUARD.HOST_PLISTS, 'containers__abandoned-probe__service.plist')
    marker = GUARD.PREPARED_SERVICE_MARKER
    payload = __import__('plistlib').load(open(target, 'rb'))
    assert payload[marker] == GUARD.PREPARED_SERVICE_VALUE
    assert external.is_symlink()

    mapping = GUARD.bridge_plists()

    assert mapping == {}
    assert external.is_symlink()
    assert __import__('plistlib').load(open(target, 'rb')) == payload


def test_duplicate_name_options_use_apple_parser_last_value(tmp_path):
    configure_paths(tmp_path)
    args = ['run', '--name', 'first-name', '--name=last-name', 'python:3.13-slim']

    GUARD._prepare_container_service_link(args)

    assert (pathlib.Path(GUARD.ROOT, 'containers', 'last-name', 'service.plist')).is_symlink()
    assert not (pathlib.Path(GUARD.ROOT, 'containers', 'first-name')).exists()


def test_single_character_name_is_rejected_like_apple_container(tmp_path):
    configure_paths(tmp_path)
    args = ['run', '--name', 'A', 'python:3.13-slim']

    try:
        GUARD._prepare_container_service_link(args)
    except RuntimeError as exc:
        assert 'unsafe' in str(exc)
    else:
        raise AssertionError('one-character name was accepted')

    assert list(pathlib.Path(GUARD.ROOT, 'containers').iterdir()) == []


def test_unrelated_task_plist_is_not_parsed_or_rewritten(tmp_path):
    configure_paths(tmp_path)
    unrelated = pathlib.Path(GUARD.ROOT, 'task-results', 'pytest-fixture.plist')
    unrelated.parent.mkdir()
    unrelated.write_text('not a plist; preserve exact fixture bytes')
    before = unrelated.read_bytes()

    mapping = GUARD.bridge_plists()

    assert mapping == {}
    assert unrelated.read_bytes() == before


def test_malformed_managed_service_plist_is_reported(tmp_path):
    configure_paths(tmp_path)
    managed = pathlib.Path(GUARD.ROOT, 'containers', 'managed-bad', 'service.plist')
    managed.parent.mkdir()
    managed.write_text('not a plist')

    try:
        GUARD.bridge_plists()
    except __import__('plistlib').InvalidFileException:
        pass
    else:
        raise AssertionError('malformed managed launch plist was ignored')

    assert managed.read_text() == 'not a plist'


def test_official_network_and_plugin_state_services_are_bridged(tmp_path):
    configure_paths(tmp_path)
    plistlib = __import__('plistlib')
    expected = {}
    for subtree, identifier, label in [
        ('networks', 'fixture-network', 'com.apple.container.network.fixture'),
        ('plugin-state', 'fixture-plugin', 'com.apple.container.plugin.fixture'),
    ]:
        service = pathlib.Path(GUARD.ROOT, subtree, identifier, 'service.plist')
        service.parent.mkdir(parents=True)
        service.write_bytes(plistlib.dumps({'Label': label, 'ProgramArguments': ['/usr/local/bin/container-plugin-fixture', 'start']}))
        expected[label] = str(pathlib.Path(GUARD.HOST_PLISTS, f'{subtree}__{identifier}__service.plist'))

    mapping = GUARD.bridge_plists()

    for label, target in expected.items():
        assert mapping[label] == target
        assert pathlib.Path(target).is_file()
        assert pathlib.Path(GUARD.HOST_PLISTS, target.rsplit('/', 1)[-1]).stat().st_mode & 0o777 == 0o600


def test_prepare_rejects_symlinked_external_container_parent(tmp_path):
    configure_paths(tmp_path)
    containers = pathlib.Path(GUARD.ROOT, 'containers')
    outside = tmp_path / 'outside-containers'
    containers.rename(outside)
    containers.symlink_to(outside, target_is_directory=True)
    args = ['run', '--name', 'escaped-parent', 'python:3.13-slim']

    try:
        GUARD._prepare_container_service_link(args)
    except RuntimeError as exc:
        assert 'real directory' in str(exc)
    else:
        raise AssertionError('symlinked external container parent was accepted')

    assert list(outside.iterdir()) == []


def test_prepare_rejects_symlinked_internal_launch_directory(tmp_path):
    configure_paths(tmp_path)
    internal = pathlib.Path(GUARD.HOST_PLISTS)
    outside = tmp_path / 'outside-launchd'
    internal.rename(outside)
    internal.symlink_to(outside, target_is_directory=True)
    args = ['run', '--name', 'escaped-internal', 'python:3.13-slim']

    try:
        GUARD._prepare_container_service_link(args)
    except RuntimeError as exc:
        assert 'real directory' in str(exc)
    else:
        raise AssertionError('symlinked internal launch directory was accepted')

    assert list(outside.iterdir()) == []


def test_prepare_rejects_symlinked_existing_container_bundle(tmp_path):
    configure_paths(tmp_path)
    outside = tmp_path / 'outside-bundle'
    outside.mkdir()
    pathlib.Path(GUARD.ROOT, 'containers', 'existing-link').symlink_to(outside, target_is_directory=True)
    args = ['run', '--name', 'existing-link', 'python:3.13-slim']

    try:
        GUARD._prepare_container_service_link(args)
    except RuntimeError as exc:
        assert 'must not be a symlink' in str(exc)
    else:
        raise AssertionError('symlinked existing bundle was accepted')

    assert list(outside.iterdir()) == []


def test_all_supported_value_options_and_payload_name_are_parsed(tmp_path):
    configure_paths(tmp_path)
    args = [
        'run', '--platform', 'linux/arm64', '--os', 'linux', '--progress', 'plain',
        '--masked-path', '/proc', '--read-only-path', '/tmp', '--name', 'chosen-name',
        'python:3.13-slim', '--name', 'payload-name',
    ]
    before = list(args)

    GUARD._prepare_container_service_link(args)

    assert args == before
    assert pathlib.Path(GUARD.ROOT, 'containers', 'chosen-name', 'service.plist').is_symlink()
    assert not pathlib.Path(GUARD.ROOT, 'containers', 'payload-name').exists()


def test_global_debug_before_run_does_not_skip_preparation(tmp_path):
    configure_paths(tmp_path)
    args = ['--debug', 'run', '--name', 'debugged-name', 'python:3.13-slim']

    GUARD._prepare_container_service_link(args)

    assert pathlib.Path(GUARD.ROOT, 'containers', 'debugged-name', 'service.plist').is_symlink()


def test_guarded_start_does_not_wait_on_full_system_status(tmp_path, monkeypatch):
    configure_paths(tmp_path)
    calls = []
    monkeypatch.setattr(GUARD, 'bridge_plists', lambda: {'com.apple.container.apiserver': '/internal/apiserver.plist'})

    class Result:
        returncode = 0

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(GUARD.subprocess, 'run', run)

    GUARD.start_guarded_api()

    assert calls == [(['/bin/launchctl', 'list', 'com.apple.container.apiserver'], {'capture_output': True, 'timeout': 8})]
    assert all(args[:2] != [GUARD.REAL_CLI, 'system'] for args, _ in calls)


def test_guarded_start_uses_finite_bootstrap_when_api_not_loaded(tmp_path, monkeypatch):
    configure_paths(tmp_path)
    calls = []
    monkeypatch.setattr(GUARD, 'bridge_plists', lambda: {'com.apple.container.apiserver': '/internal/apiserver.plist'})

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return Result(1 if len(calls) == 1 else 0)

    monkeypatch.setattr(GUARD.subprocess, 'run', run)

    GUARD.start_guarded_api()

    assert calls == [
        (['/bin/launchctl', 'list', 'com.apple.container.apiserver'], {'capture_output': True, 'timeout': 8}),
        (['/bin/launchctl', 'bootstrap', 'gui/' + str(__import__('os').getuid()), '/internal/apiserver.plist'], {'check': True, 'timeout': 8}),
    ]
