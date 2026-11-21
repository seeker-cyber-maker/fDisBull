"""Helper command/preflight checks use mocked Mac boundaries, not macOS acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build_local_macos.py'


def _helper():
    spec = importlib.util.spec_from_file_location('dotbox_local_macos_build', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _core_wheel(directory, *, metadata_name='fdisbull-core', metadata_version='0.1.0.dev3',
                dependency=None, kernel=True, transport=True, scene=True):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'fdisbull_core-0.1.0.dev3-py3-none-any.whl'
    metadata = f'Metadata-Version: 2.1\nName: {metadata_name}\nVersion: {metadata_version}\n'
    if dependency:
        metadata += 'Requires-Dist: ' + dependency + '\n'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('fdisbull_core-0.1.0.dev3.dist-info/METADATA', metadata)
        if kernel:
            archive.writestr('fdisbull_core/memory_search.py', '# authored wheel admission fixture\n')
        if transport:
            archive.writestr('fdisbull_core/pipe_rpc.py', '# authored transport admission fixture\n')
        if scene:
            archive.writestr('fdisbull_core/agi_scene.py', '# authored scene admission fixture\n')
    return path


def test_help_does_not_require_build_dependencies():
    result = subprocess.run([sys.executable, '-S', str(SCRIPT), '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert '--work-dir' in result.stdout and '--mode' in result.stdout and '--shared-wheel' in result.stdout


def test_existing_work_is_never_replaced(tmp_path):
    keep = tmp_path / 'keep.txt'
    keep.write_text('retain prior work')
    with pytest.raises(SystemExit) as error:
        _helper().main(['--work-dir', str(tmp_path), '--shared-wheel', str(tmp_path / 'unused.whl')])
    assert error.value.code == 2
    assert list(tmp_path.iterdir()) == [keep]
    assert keep.read_text() == 'retain prior work'


def test_work_must_be_absolute_outside_checkout_including_symlink_parents(tmp_path, monkeypatch):
    helper = _helper()
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(checkout, target_is_directory=True)
    monkeypatch.setattr(helper, 'ROOT', checkout)
    for value in ('relative-output', str(checkout / 'output'), str(alias / 'output')):
        with pytest.raises(ValueError):
            helper._work_directory(value)
    assert list(checkout.iterdir()) == []


def test_monorepo_output_guard_also_excludes_other_products(tmp_path, monkeypatch):
    repository = tmp_path / 'repository'
    product = repository / 'apps/dotbox'
    product.mkdir(parents=True)
    (repository / '.git').write_text('gitdir: /authored/worktree-control\n')
    helper = _helper()
    monkeypatch.setattr(helper, 'ROOT', product)
    assert helper._repository_root() == repository
    for path in (repository / 'build', repository / 'apps/other-build', product / 'build'):
        with pytest.raises(ValueError, match='outside'):
            helper._work_directory(str(path))
    assert helper._work_directory(str(tmp_path / 'outside')) == tmp_path / 'outside'


@pytest.mark.parametrize('alteration', [
    {'metadata_name': 'fdisbull'}, {'metadata_version': '0.2.0'},
    {'dependency': 'fdisbull>=1'}, {'kernel': False}, {'transport': False}, {'scene': False},
])
def test_shared_wheel_requires_the_exact_standalone_core(tmp_path, alteration):
    helper = _helper()
    wheel = _core_wheel(tmp_path, **alteration)
    with pytest.raises(ValueError):
        helper._shared_wheel(wheel)


def test_shared_wheel_is_bound_to_admitted_bytes(tmp_path):
    helper = _helper()
    wheel = _core_wheel(tmp_path / 'inputs')
    identity = helper._shared_wheel(wheel)
    assert identity['distribution'] == 'fdisbull-core'
    assert identity['version'] == '0.1.0.dev3'
    assert identity['sha256'] == helper._sha256(wheel)
    work = tmp_path / 'work'
    work.mkdir()
    wheel.write_bytes(b'changed after admission')
    with pytest.raises(ValueError, match='changed after admission'):
        helper._stage_shared_wheel(work, identity)
    assert not list(work.iterdir())


def test_invalid_shared_wheel_creates_no_build_output(tmp_path):
    wheel = tmp_path / 'fdisbull_core-0.1.0.dev3-py3-none-any.whl'
    wheel.write_bytes(b'not a ZIP wheel')
    work = tmp_path / 'new-build'
    with pytest.raises(SystemExit) as error:
        _helper().main(['--work-dir', str(work), '--shared-wheel', str(wheel)])
    assert error.value.code == 2 and not work.exists()


def test_non_macos_has_failure_receipt_and_runs_no_commands(tmp_path, monkeypatch):
    helper = _helper()
    monkeypatch.setattr(helper.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(helper, '_run', lambda *args, **kwargs: pytest.fail('must not launch a command'))
    work = tmp_path / 'new-build'
    wheel = _core_wheel(tmp_path / 'inputs')
    assert helper.main(['--work-dir', str(work), '--shared-wheel', str(wheel)]) == 2
    report = json.loads((work / 'result.json').read_text())
    assert report['status'] == 'failed' and report['stage'] == 'preflight'
    assert report['native_build_performed'] is False
    assert report['steps'] == []
    assert report['prerequisites']['homebrew'] == helper.PREREQUISITES
    assert not (work / 'native').exists()


@pytest.mark.parametrize('driver', ['dummy', 'offscreen', 'cocoa,dummy', ' OFFSCREEN '])
def test_visible_modes_refuse_inherited_hidden_driver_before_commands(driver, monkeypatch):
    helper = _helper()
    monkeypatch.setattr(helper.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(helper.platform, 'machine', lambda: 'arm64')
    for mode in ('all', 'visible'):
        with pytest.raises(ValueError, match='SDL_VIDEODRIVER'):
            helper._preflight(mode, {'SDL_VIDEODRIVER': driver},
                              lambda *args, **kwargs: pytest.fail('must not launch a command'))


def test_missing_native_brew_reports_exact_install_command(tmp_path, monkeypatch):
    helper = _helper()
    monkeypatch.setattr(helper.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(helper.platform, 'machine', lambda: 'arm64')
    monkeypatch.setattr(helper, 'BREW', tmp_path / 'missing-brew')
    with pytest.raises(ValueError, match='brew install autoconf automake pkgconf libpng zstd ncurses'):
        helper._preflight('headless', {'SDL_VIDEODRIVER': 'dummy'},
                          lambda *args, **kwargs: pytest.fail('must not install anything'))


@pytest.mark.parametrize('inherited_sdk', [None, '/authored/previous-sdk'])
def test_mocked_preflight_selects_sdk_preserves_flags_and_resolves_keg_only_libraries(
        tmp_path, monkeypatch, inherited_sdk):
    helper = _helper()
    monkeypatch.setattr(helper.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(helper.platform, 'machine', lambda: 'arm64')
    executable = tmp_path / 'authored-tool'
    executable.write_text('not executed')
    executable.chmod(0o700)
    monkeypatch.setattr(helper, 'BREW', executable)
    monkeypatch.setattr(helper.shutil, 'which', lambda *args, **kwargs: str(executable))
    sdk = tmp_path / 'Selected SDK.sdk'
    sdk.mkdir()
    monkeypatch.setenv('SDKROOT', '/authored/parent-process-sdk')
    prefixes = {}
    for formula, header, library in [('libpng', 'png.h', 'png'),
                                     ('zstd', 'zstd.h', 'zstd'),
                                     ('ncurses', 'curses.h', 'ncurses')]:
        prefix = tmp_path / formula
        (prefix / 'include').mkdir(parents=True)
        (prefix / 'lib').mkdir()
        (prefix / 'include' / header).write_bytes(b'authored header placeholder')
        (prefix / 'lib' / f'lib{library}.dylib').write_bytes(b'authored library placeholder')
        prefixes[formula] = prefix
    commands = []

    def run(stage, command, **kwargs):
        commands.append([str(arg) for arg in command])
        if command[1:] == ['--prefix']:
            value = '/opt/homebrew'
        elif command[1:2] == ['--prefix']:
            value = str(prefixes[command[2]])
        elif command[1:2] == ['--find']:
            value = str(executable)
        elif command[1:] == ['--show-sdk-path']:
            value = str(sdk)
        else:
            value = 'GNU Make authored tool identity'
        log = tmp_path / (stage + '.log')
        log.write_text(value)
        return log

    environment = {'PATH': '/usr/bin', 'CPPFLAGS': '-DMY_FLAG=1', 'LDFLAGS': '-Wl,my-flag',
                   'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'}
    if inherited_sdk is not None:
        environment['SDKROOT'] = inherited_sdk
    result = helper._preflight('headless', environment, run)
    assert str(prefixes['ncurses']) == result['dependency_prefixes']['ncurses']
    assert '-I' + str(prefixes['ncurses'] / 'include') in environment['CPPFLAGS']
    assert environment['CPPFLAGS'].endswith('-DMY_FLAG=1')
    assert environment['LDFLAGS'].endswith('-Wl,my-flag')
    assert environment['SDL_VIDEODRIVER'] == environment['SDL_AUDIODRIVER'] == 'dummy'
    assert ['pkg-config', '--exists', 'libpng', 'libzstd', 'ncurses'] in commands
    assert all('install' not in command for command in commands)
    assert os.environ['SDKROOT'] == '/authored/parent-process-sdk'
    (tmp_path / 'logs').mkdir()
    probe = helper._run(tmp_path, {'steps': []}, 'child-sdk-probe',
                        [sys.executable, '-I', '-c', 'import os; print(os.environ["SDKROOT"])'],
                        cwd=tmp_path, environment=environment, timeout=10)
    assert probe.read_text().strip() == result['sdk'] == str(sdk)


def _mock_commands(helper, monkeypatch, *, doctor_layout='installed', accept=True,
                   failed_stage=None, wrong_binary=False):
    """Supply authored process outputs only; never build/install/launch native code."""
    commands = []
    monkeypatch.setattr(helper, '_preflight', lambda *args: {'mocked_mac_preflight': True})
    monkeypatch.setattr(helper, '_check_pip_destination', lambda *args: [])
    def stage_package(destination):
        destination.mkdir()
        return {'files': 1, 'sha256': 'a' * 64, 'scope': 'Authored staged inputs'}
    monkeypatch.setattr(helper, '_stage_package', stage_package)

    def run(work, result, stage, command, *, cwd, environment, timeout=None):
        result['stage'] = stage
        command = [str(arg) for arg in command]
        commands.append((stage, command, Path(cwd), dict(environment), timeout))
        log = work / 'logs' / (stage + '.log')
        log.write_text('authored process output\n')
        result['steps'].append({'stage': stage, 'command': command, 'log': str(log)})
        if stage == 'checkout-status':
            log.write_text(' M unrelated-qemu-work.py\n')
        elif stage == 'product-status':
            log.write_text('')
        elif stage == 'checkout-commit':
            log.write_text('c' * 40 + '\n')
        elif stage == 'product-tree':
            log.write_text('d' * 40 + '\n')
        if stage == failed_stage:
            raise RuntimeError('authored failed command at ' + stage)
        if stage == 'build-wheels':
            (work / 'wheels').mkdir()
            (work / 'wheels/dotbox-authored.whl').write_bytes(b'authored wheel placeholder')
        elif stage == 'installed-doctor':
            log.write_text(json.dumps({'offline_learning_ready': True,
                                      'resources': {'layout': doctor_layout}}))
        elif stage == 'prepare-native':
            (work / 'native/vs/sdl2').mkdir(parents=True)
            (work / 'native/.dotbox-source.json').write_text('{"authored_fixture": true}')
        elif stage == 'build-native':
            (work / 'native/src').mkdir()
            (work / 'native/src/dosbox-x').write_bytes(b'authored binary placeholder')
            (work / 'native/config.h').write_text('authored config header')
            (work / 'native/config.log').write_text('authored configure log')
        elif stage == 'binary-architectures':
            log.write_text('arm64\n')
        elif stage == 'native-tests':
            (work / 'native-tests').mkdir()
            mode = command[command.index('--mode') + 1]
            executable = work / 'native/src/dosbox-x'
            digest = 'authored wrong digest' if wrong_binary else helper._sha256(executable)
            (work / 'native-tests/result.json').write_text(json.dumps({
                'accepted': accept, 'mode': mode,
                'executable': {'path': str(executable), 'sha256_before': digest, 'sha256_after': digest}}))
        return log

    monkeypatch.setattr(helper, '_run', run)
    return commands


def test_mocked_command_plan_builds_private_wheel_pinned_sdl_and_exact_recipe(tmp_path, monkeypatch):
    helper = _helper()
    commands = _mock_commands(helper, monkeypatch)
    work = tmp_path / 'new-build'
    upstream = tmp_path / 'upstream'
    upstream.mkdir()
    wheel = _core_wheel(tmp_path / 'inputs')
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    assert helper.main(['--work-dir', str(work), '--mode', 'headless', '--upstream', str(upstream),
                        '--shared-wheel', str(wheel)]) == 0
    planned = {stage: command for stage, command, *_ in commands}
    recipe = json.loads((ROOT / 'native/build-recipe.json').read_text())
    assert [planned[name] for name in ('autogen-native', 'configure-native', 'build-native')] == recipe['build']['commands']
    assert planned['build-sdl2'] == ['make', '-j2']
    assert planned['stage-sdl2'] == ['make', '-j2', 'install']
    assert '--prefix=' + str(work / 'native/vs/sdl2/linux-host') in planned['configure-sdl2']
    assert '--disable-video-x11' in planned['configure-sdl2']
    assert '--only-binary=iced-x86,Pillow' in planned['build-wheels']
    assert str(work / 'package-source') + '[test]' in planned['build-wheels']
    assert str(work / 'shared-wheel' / wheel.name) in planned['build-wheels']
    assert '--no-index' in planned['install-wheel']
    assert '--no-user' in planned['install-wheel']
    for stage in ('build-wheels', 'install-wheel', 'installed-packages'):
        command = planned[stage]
        assert command[command.index('--python') + 1] == str(work / 'venv/bin/python')
    assert planned['installed-doctor'] == [str(work / 'venv/bin/python'), '-I', '-m', 'dotbox', 'doctor']
    assert planned['prepare-native'][-2:] == ['--upstream', str(upstream)]
    assert planned['native-tests'][-2:] == ['--timeout-seconds', '300']
    assert '--source-receipt' in planned['native-tests']
    assert all(environment['SDL_VIDEODRIVER'] == 'dummy' for _, _, _, environment, _ in commands)
    assert all('sudo' not in command and str(helper.BREW) not in command for _, command, *_ in commands)
    assert next(cwd for stage, _, cwd, *_ in commands if stage == 'installed-doctor') == work
    report = json.loads((work / 'result.json').read_text())
    assert report['status'] == 'succeeded' and report['mode'] == 'headless'
    assert report['native_tests']['runtime'].startswith('source checkout')
    assert report['source_receipt']['binary_attestation'] is False
    assert len(report['wheel']['sha256']) == 64
    assert report['shared_core']['sha256'] == helper._sha256(wheel)
    assert Path(report['shared_core']['staged_path']).read_bytes() == wheel.read_bytes()
    assert report['checkout']['path'] == str(helper._repository_root())
    assert report['checkout']['dirty'] is True
    assert report['checkout']['product']['dirty'] is False
    assert report['checkout']['product']['committed_tree'] == 'd' * 40
    assert report['checkout']['product']['package_inputs']['sha256'] == 'a' * 64
    product = helper.ROOT.resolve().relative_to(helper._repository_root()).as_posix()
    assert planned['product-status'][-2:] == ['--', product]


@pytest.mark.parametrize('problem', ['source_doctor', 'compile_failure', 'gate_rejection', 'binary_mismatch'])
def test_mocked_failures_retain_stage_without_claiming_success(tmp_path, monkeypatch, problem):
    helper = _helper()
    commands = _mock_commands(helper, monkeypatch,
                              doctor_layout='source' if problem == 'source_doctor' else 'installed',
                              accept=problem != 'gate_rejection',
                              wrong_binary=problem == 'binary_mismatch',
                              failed_stage='build-native' if problem == 'compile_failure' else None)
    work = tmp_path / problem
    wheel = _core_wheel(tmp_path / 'inputs')
    assert helper.main(['--work-dir', str(work), '--shared-wheel', str(wheel)]) == 1
    report = json.loads((work / 'result.json').read_text())
    assert report['status'] == 'failed'
    expected_stage = {'source_doctor': 'installed-doctor', 'compile_failure': 'build-native',
                      'gate_rejection': 'native-tests', 'binary_mismatch': 'native-tests'}[problem]
    assert report['stage'] == expected_stage
    assert commands[-1][0] == expected_stage
    if problem in ('source_doctor', 'compile_failure'):
        assert report['native_build_performed'] is False
    assert report.get('native_tests', {}).get('accepted') is not True


def test_package_snapshot_contains_declared_resources_without_build_outputs(tmp_path):
    helper = _helper()
    destination = tmp_path / 'package-source'
    identity = helper._stage_package(destination)
    manifest = json.loads((ROOT / 'src/dotbox/resources_manifest.json').read_text())
    canonical = ROOT.parents[1] / 'experimental/dosbox-x'
    shared = {f'native/dosbox-x/{name}' for name in
              ('headless-agent.patch', 'source-manifest.json', 'COPYING')}
    for name in manifest['files']:
        source = ROOT / name
        if name in shared and not source.is_file():
            source = canonical / Path(name).name
        assert (destination / name).read_bytes() == source.read_bytes()
    assert (destination / 'src/dotbox/cli.py').is_file()
    assert not (destination / '.git').exists()
    assert not (destination / 'build').exists()
    assert not list(destination.rglob('*.pyc'))
    assert identity['files'] == len([path for path in destination.rglob('*') if path.is_file()])
    assert len(identity['sha256']) == 64


def test_failed_real_subprocess_retains_log_and_status_without_building(tmp_path):
    helper = _helper()
    (tmp_path / 'logs').mkdir()
    result = {'steps': []}
    with pytest.raises(RuntimeError, match='exited 7'):
        helper._run(tmp_path, result, 'authored-failure',
                    [sys.executable, '-c', 'print("authored failure"); raise SystemExit(7)'],
                    cwd=tmp_path, environment=os.environ.copy())
    saved = json.loads((tmp_path / 'result.json').read_text())
    assert saved['steps'][0]['exit_code'] == 7
    assert Path(saved['steps'][0]['log']).read_text() == 'authored failure\n'


@pytest.mark.skipif(os.name != 'posix', reason='macOS helper owns POSIX process groups')
def test_cancellation_stops_sigint_ignoring_child_after_leader_exits(tmp_path):
    import fcntl
    import select

    child_code = '''import fcntl, signal, sys, time
with open(sys.argv[1], "w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    print("child-ready", flush=True)
    time.sleep(60)
'''
    parent_code = '''import subprocess, sys, time
subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2]])
time.sleep(60)
'''
    lock_path = tmp_path / 'child.lock'
    process = subprocess.Popen([sys.executable, '-c', parent_code, child_code, str(lock_path)],
                               start_new_session=True, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    try:
        assert select.select([process.stdout], [], [], 5)[0], 'authored child failed to become ready'
        assert process.stdout.readline().strip() == 'child-ready'
        with lock_path.open('r') as lock:
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _helper()._stop(process)
            # A dead child's file lock is released even if its orphaned process
            # entry briefly remains a zombie under the container's init process.
            deadline = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        pytest.fail('SIGINT-ignoring child survived cancellation')
                    time.sleep(0.01)
        assert process.returncode is not None
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        process.stdout.close()


def _pip_probe(helper, monkeypatch, text, *, returncode=0, error=None, markers=True):
    commands = []

    class AuthoredProcess:
        def __init__(self, command, **kwargs):
            self.returncode = returncode
            commands.append((command, kwargs))

        def communicate(self, timeout):
            assert timeout == 30
            if error:
                raise error
            marker_text = ":env:.quiet='0'\n:env:.verbose='0'\n" if markers else ''
            return marker_text + text, 'AUTHORED_SECRET_IN_STDERR'

    monkeypatch.setattr(helper.subprocess, 'Popen', AuthoredProcess)
    monkeypatch.setattr(helper, '_stop', lambda process: None)
    return commands


@pytest.mark.parametrize('text', [
    "global.index-url='https://AUTHORED_SECRET@example.invalid/simple'\n",
    "global.target=''\n:env:.prefix=''\ninstall.root=''\ninstall.user='false'\n",
    "global.user='true'\ninstall.user='no'\n",
    "install.user='true'\n:env:.user='0'\n",
])
def test_private_pip_probe_allows_registry_preferences_and_disabled_destinations(tmp_path, monkeypatch, text):
    helper = _helper()
    commands = _pip_probe(helper, monkeypatch, text)
    python = tmp_path / 'venv/bin/python'
    environment = {'PIP_INDEX_URL': 'https://AUTHORED_SECRET@example.invalid/simple',
                   'PIP_QUIET': '1', 'PIP_VERBOSE': '2', 'PIP_LOG': '/authored/private.log'}
    safe_names = helper._check_pip_destination(python, tmp_path, environment)
    command, options = commands[0]
    assert command == [str(python), '-I', '-m', 'pip', '--python', str(python),
                       '--log', os.devnull, 'config', 'list']
    assert options['env'] == dict(environment, PIP_QUIET='0', PIP_VERBOSE='0')
    assert environment['PIP_QUIET'] == '1' and environment['PIP_VERBOSE'] == '2'
    assert 'AUTHORED_SECRET' not in json.dumps(safe_names)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('text, setting', [
    ("global.target='/AUTHORED_SECRET'\n", 'global.target'),
    ("install.prefix='/AUTHORED_SECRET'\n", 'install.prefix'),
    (":env:.root='/AUTHORED_SECRET'\n", ':env:.root'),
    ("install.user='yes'\n", 'install.user'),
    ("global.python='/AUTHORED_SECRET'\n", 'global.python'),
    ("global.target='/AUTHORED_SECRET'\ninstall.target=''\n", 'global.target'),
    ("install.user='false'\n:env:.user='true'\n", ':env:.user'),
])
def test_private_pip_probe_refuses_redirects_without_exposing_values(tmp_path, monkeypatch, text, setting):
    helper = _helper()
    _pip_probe(helper, monkeypatch, text)
    with pytest.raises(ValueError) as error:
        helper._check_pip_destination(tmp_path / 'venv/bin/python', tmp_path, {})
    assert setting in str(error.value)
    assert 'AUTHORED_SECRET' not in str(error.value)
    assert not list(tmp_path.iterdir())


def test_pip_python_environment_redirect_refused_before_probe(tmp_path, monkeypatch):
    helper = _helper()
    monkeypatch.setattr(helper.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('must not invoke redirected pip'))
    with pytest.raises(ValueError, match=':env:.python') as error:
        helper._check_pip_destination(tmp_path / 'venv/bin/python', tmp_path,
                                      {'PIP_PYTHON': '/AUTHORED_SECRET'})
    assert 'AUTHORED_SECRET' not in str(error.value)


@pytest.mark.parametrize('failure', ['exit', 'malformed', 'timeout'])
def test_pip_inspection_errors_fail_closed_without_private_output(tmp_path, monkeypatch, failure):
    helper = _helper()
    _pip_probe(helper, monkeypatch, 'AUTHORED_SECRET_NOT_A_SETTING',
               returncode=1 if failure == 'exit' else 0,
               error=subprocess.TimeoutExpired(['pip', 'config', 'list'], 30,
                                                output='AUTHORED_SECRET') if failure == 'timeout' else None)
    with pytest.raises((RuntimeError, ValueError)) as error:
        helper._check_pip_destination(tmp_path / 'venv/bin/python', tmp_path, {})
    assert 'AUTHORED_SECRET' not in str(error.value)


@pytest.mark.parametrize('text', ['', ":env:.quiet='0'\n", ":env:.quiet='1'\n:env:.verbose='0'\n"])
def test_suppressed_or_incomplete_pip_configuration_is_refused(tmp_path, monkeypatch, text):
    helper = _helper()
    _pip_probe(helper, monkeypatch, text, markers=False)
    with pytest.raises(ValueError, match='incomplete or suppressed'):
        helper._check_pip_destination(tmp_path / 'venv/bin/python', tmp_path, {})


@pytest.mark.parametrize('redirect', [False, True])
def test_read_only_real_pip_probe_overrides_quiet_and_never_writes_config_log(tmp_path, redirect):
    """Read local authored pip settings only: no installation or network operation."""
    environment = os.environ.copy()
    for option in ('PIP_PYTHON', 'PIP_TARGET', 'PIP_PREFIX', 'PIP_ROOT', 'PIP_USER'):
        environment.pop(option, None)
    private_log = tmp_path / 'authored-private.log'
    target = tmp_path / 'outside-target'
    environment.update(PIP_CONFIG_FILE=os.devnull, PIP_QUIET='1', PIP_VERBOSE='2',
                       PIP_LOG=str(private_log),
                       PIP_INDEX_URL='https://AUTHORED_SECRET@example.invalid/simple')
    if redirect:
        environment['PIP_TARGET'] = str(target)
        with pytest.raises(ValueError, match=':env:.target') as error:
            _helper()._check_pip_destination(Path(sys.executable), tmp_path, environment)
        assert 'AUTHORED_SECRET' not in str(error.value)
    else:
        assert _helper()._check_pip_destination(Path(sys.executable), tmp_path, environment) == []
    assert not private_log.exists()
    assert not target.exists()
    assert environment['PIP_QUIET'] == '1' and environment['PIP_VERBOSE'] == '2'
    assert not list(tmp_path.iterdir())
