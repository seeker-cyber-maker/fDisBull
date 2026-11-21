#!/usr/bin/env python3
"""Build and test a private native arm64 DotBox development copy on macOS."""
from datetime import datetime, timezone
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import signal
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BREW = Path('/opt/homebrew/bin/brew')
PREREQUISITES = ('/opt/homebrew/bin/brew install autoconf automake pkgconf '
                 'libpng zstd ncurses')
SCOPE = ('Installed-wheel offline doctor plus selected source-checkout native fixtures; '
         'no Police Quest route, complete memory-only rewind or outer desktop takeover qualification')


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _save(work, result):
    temporary = work / 'result.json.tmp'
    temporary.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    temporary.replace(work / 'result.json')


def _work_directory(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('--work-dir must be an absolute path')
    if path.exists() or path.is_symlink():
        raise ValueError('--work-dir must not exist; previous output is never replaced')
    path = path.parent.resolve(strict=True) / path.name
    if path.is_relative_to(ROOT):
        raise ValueError('--work-dir must be outside the DotBox checkout')
    return path


def _stop(process):
    # SIGINT lets the native-test runner clean up its own isolated pytest group.
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=12 if sig == signal.SIGINT else 5)
        except subprocess.TimeoutExpired:
            pass
        # The leader may exit before a compiler child. Check the whole group
        # before deciding that cancellation is complete.
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return


def _run(work, result, stage, command, *, cwd, environment, timeout=None):
    log = work / 'logs' / f'{len(result["steps"]) + 1:02d}-{stage}.log'
    entry = {'stage': stage, 'command': [str(arg) for arg in command],
             'cwd': str(cwd), 'log': str(log), 'started_utc': _timestamp(),
             'timeout_seconds': timeout, 'exit_code': None}
    result['stage'] = stage
    result['steps'].append(entry)
    _save(work, result)
    print(f'{stage}: {log}', flush=True)
    try:
        with log.open('x', encoding='utf-8') as output:
            process = subprocess.Popen(entry['command'], cwd=cwd, env=environment,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                entry['exit_code'] = process.wait(timeout=timeout)
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                _stop(process)
                entry['exit_code'] = process.returncode
                raise
        if entry['exit_code'] != 0:
            raise RuntimeError(f'{stage} exited {entry["exit_code"]}; see {log}')
    except (OSError, RuntimeError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        entry['error'] = str(error) or type(error).__name__
        raise
    finally:
        entry['finished_utc'] = _timestamp()
        _save(work, result)
    return log


def _preflight(mode, environment, run):
    if sys.version_info < (3, 12):
        raise ValueError('Python 3.12 or later is required; use python3.12 or a newer native Python')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Run from a native arm64 macOS terminal, outside Rosetta')
    driver = environment.get('SDL_VIDEODRIVER', '')
    if mode != 'headless' and any(part.strip().lower() in ('dummy', 'offscreen')
                                  for part in driver.split(',')):
        raise ValueError('Visible tests refuse SDL_VIDEODRIVER=' + driver +
                         '; choose a visible desktop environment or --mode headless')
    if not BREW.is_file() or not os.access(BREW, os.X_OK):
        raise ValueError('Native Homebrew is required at /opt/homebrew/bin/brew; '
                         'install it from https://brew.sh, then run: ' + PREREQUISITES)
    environment['PATH'] = str(BREW.parent) + os.pathsep + environment.get('PATH', '')
    tools = ('xcrun', 'git', 'make', 'file', 'otool', 'lipo', 'autoconf',
             'autoheader', 'automake', 'aclocal', 'pkg-config')
    missing = [tool for tool in tools if not shutil.which(tool, path=environment['PATH'])]
    if missing:
        raise ValueError('Missing tools: ' + ', '.join(missing) +
                         '. CLT prerequisite: xcode-select --install. Homebrew prerequisites: ' +
                         PREREQUISITES)
    prefix = run('preflight-brew-prefix', [BREW, '--prefix'], timeout=30).read_text().strip()
    if prefix != '/opt/homebrew':
        raise ValueError('Use native Homebrew with prefix /opt/homebrew')
    sdk = run('preflight-sdk', ['xcrun', '--show-sdk-path'], timeout=30).read_text().strip()
    compilers = {}
    for language, tool in (('CC', 'clang'), ('CXX', 'clang++')):
        compiler = run('preflight-' + tool.replace('+', 'x'),
                       ['xcrun', '--find', tool], timeout=30).read_text().strip()
        if not Path(compiler).is_file() or not os.access(compiler, os.X_OK):
            raise ValueError('Xcode Command Line Tools are unavailable; run: xcode-select --install')
        compilers[language] = compiler
    environment.update(compilers, OBJC=compilers['CC'], OBJCXX=compilers['CXX'], SDKROOT=sdk)
    prefixes = {}
    for formula, header, library in (('libpng', 'png.h', 'png'),
                                     ('zstd', 'zstd.h', 'zstd'),
                                     ('ncurses', 'curses.h', 'ncurses')):
        path = Path(run('preflight-' + formula, [BREW, '--prefix', formula],
                        timeout=30).read_text().strip())
        if (not (path / 'include' / header).is_file() or not any(
                (path / 'lib' / ('lib' + library + suffix)).is_file()
                for suffix in ('.dylib', '.a'))):
            raise ValueError('Missing ' + formula + ' headers/library; run: ' + PREREQUISITES)
        prefixes[formula] = str(path)
    include_flags = ' '.join('-I' + value + '/include' for value in prefixes.values())
    library_flags = ' '.join('-L' + value + '/lib' for value in prefixes.values())
    environment['CPPFLAGS'] = include_flags + ' ' + environment.get('CPPFLAGS', '')
    environment['LDFLAGS'] = library_flags + ' ' + environment.get('LDFLAGS', '')
    environment['PKG_CONFIG_PATH'] = os.pathsep.join(
        [value + '/lib/pkgconfig' for value in prefixes.values()] +
        [prefix + '/lib/pkgconfig', environment.get('PKG_CONFIG_PATH', '')]).rstrip(os.pathsep)
    run('preflight-libraries', ['pkg-config', '--exists', 'libpng', 'libzstd', 'ncurses'], timeout=30)
    versions = {}
    for tool in ('git', 'make', 'autoconf', 'automake', 'pkg-config', compilers['CXX']):
        name = Path(tool).name.replace('+', 'x')
        versions[name] = run('version-' + name, [tool, '--version'], timeout=30).read_text().strip()
    if 'GNU Make' not in versions['make']:
        raise ValueError('The native recipe requires GNU Make (provided by Xcode Command Line Tools)')
    return {'sdk': sdk, 'compilers': compilers, 'dependency_prefixes': prefixes, 'versions': versions}


def _stage_package(destination):
    """Copy only Python sources and declared resources; pip must not build in the checkout."""
    manifest = json.loads((ROOT / 'src/dotbox/resources_manifest.json').read_text())
    names = {'pyproject.toml', 'setup.py', 'MANIFEST.in', 'README.md', 'AGENTS.md', *manifest['files']}
    names.update(str(path.relative_to(ROOT)) for path in (ROOT / 'src/dotbox').rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
    for name in sorted(names):
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise ValueError('Invalid package resource path: ' + name)
        source = ROOT / name
        if any(path.is_symlink() for path in (source, *source.parents) if path != ROOT.parent):
            raise ValueError('Refusing symlinked package input: ' + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _check_pip_destination(python, work, environment):
    """Inspect destinations without retaining index credentials from pip config."""
    if environment.get('PIP_PYTHON'):
        raise ValueError('Pip destination override refused: :env:.python')
    probe_environment = dict(environment, PIP_QUIET='0', PIP_VERBOSE='0')
    command = [str(python), '-I', '-m', 'pip', '--python', str(python),
               '--log', os.devnull, 'config', 'list']
    try:
        process = subprocess.Popen(command, cwd=work, env=probe_environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            output, _ = process.communicate(timeout=30)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            _stop(process)
            raise
    except subprocess.TimeoutExpired:
        raise RuntimeError('Pip configuration inspection timed out; private output was not retained') from None
    except OSError:
        raise RuntimeError('Pip configuration inspection could not start; private output was not retained') from None
    if process.returncode != 0:
        raise RuntimeError('Pip configuration inspection failed; private output was not retained')
    markers = {":env:.quiet='0'", ":env:.verbose='0'"}
    if not markers.issubset(line.strip() for line in output.splitlines()):
        raise ValueError('Pip configuration inspection output is incomplete or suppressed; output withheld')
    settings = {}
    for line in output.splitlines():
        name, separator, value = line.partition('=')
        if not separator:
            raise ValueError('Pip configuration inspection returned an unrecognized line; output withheld')
        name = name.strip()
        section, _, option = name.partition('.')
        if section not in ('global', 'install', ':env:') or option not in ('target', 'prefix', 'root', 'user', 'python'):
            continue
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            raise ValueError('Pip configuration value could not be inspected: ' + name) from None
        if not isinstance(value, str):
            raise ValueError('Pip configuration value is not a string: ' + name)
        settings[name] = value
    effective = {}
    for section in ('global', 'install', ':env:'):
        for name, value in settings.items():
            scope, _, option = name.partition('.')
            # pip ignores empty values rather than using them to clear a lower-priority setting.
            if scope == section and value:
                effective[option] = (name, value)
    unsafe = [name for option, (name, value) in effective.items()
              if option != 'user' or value.lower() not in ('0', 'false', 'no', 'off', 'n', 'f')]
    if unsafe:
        raise ValueError('Pip destination overrides refused: ' + ', '.join(sorted(unsafe)))
    return sorted(name for name, _ in effective.values())


def _build(work, result, mode, upstream):
    environment = os.environ.copy()

    def run(stage, command, *, cwd=work, timeout=None, env=None):
        return _run(work, result, stage, command, cwd=cwd,
                    environment=environment if env is None else env, timeout=timeout)

    result['preflight'] = _preflight(mode, environment, run)
    result['build_environment'] = {name: environment.get(name) for name in (
        'PATH', 'CC', 'CXX', 'OBJC', 'OBJCXX', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
        'LIBS', 'PKG_CONFIG_PATH', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'MAKEFLAGS',
        'SDL_VIDEODRIVER', 'SDL_AUDIODRIVER')}
    result['checkout'] = {
        'path': str(ROOT),
        'commit': run('checkout-commit', ['git', '-C', ROOT, 'rev-parse', 'HEAD'], timeout=30).read_text().strip(),
        'dirty': bool(run('checkout-status', ['git', '-C', ROOT, 'status', '--porcelain'], timeout=30).read_text().strip()),
    }
    run('create-venv', [sys.executable, '-m', 'venv', work / 'venv'])
    python = work / 'venv/bin/python'
    result['stage'] = 'pip-destination-check'
    _save(work, result)
    result['pip_destination_check'] = {'setting_names': _check_pip_destination(python, work, environment),
                                       'checked': True, 'private_config_output_retained': False}
    pip = [python, '-I', '-m', 'pip', '--python', python]
    result['stage'] = 'stage-package'
    _stage_package(work / 'package-source')
    run('build-wheels', pip + ['wheel', '--only-binary=iced-x86,Pillow', '--wheel-dir', work / 'wheels',
                               str(work / 'package-source') + '[test]'])
    wheels = list((work / 'wheels').glob('dotbox-*.whl'))
    if len(wheels) != 1:
        raise ValueError('Expected one newly built DotBox wheel')
    result['wheel'] = {'path': str(wheels[0]), 'sha256': _sha256(wheels[0])}
    run('install-wheel', pip + ['install', '--no-index', '--no-user',
                                '--find-links', work / 'wheels', str(wheels[0]) + '[test]'])
    run('installed-packages', pip + ['freeze'])
    doctor_log = run('installed-doctor', [python, '-I', '-m', 'dotbox', 'doctor'])
    doctor = json.loads(doctor_log.read_text())
    if doctor.get('offline_learning_ready') is not True or doctor.get('resources', {}).get('layout') != 'installed':
        raise ValueError('Installed-wheel doctor did not confirm the installed offline learning kit')
    (work / 'doctor.json').write_text(json.dumps(doctor, indent=2) + '\n')
    result['installed_doctor'] = {'path': str(work / 'doctor.json'), 'offline_learning_ready': True}

    native = work / 'native'
    prepare = [python, ROOT / 'scripts/prepare_native.py', native]
    if upstream:
        prepare.extend(['--upstream', upstream])
    run('prepare-native', prepare)
    run('verify-native-source', [python, ROOT / 'scripts/prepare_native.py', native, '--check'])
    receipt = native / '.dotbox-source.json'
    result['source_receipt'] = {'path': str(receipt), 'sha256': _sha256(receipt), 'binary_attestation': False}

    sdl_source = native / 'vs/sdl2'
    sdl_build = sdl_source / 'linux-build'
    sdl_build.mkdir()
    sdl_environment = dict(environment, ac_cv_header_iconv_h='no', ac_cv_func_iconv='no',
                           ac_cv_lib_iconv_libiconv_open='no')
    run('configure-sdl2', [sdl_source / 'configure', '--srcdir=' + str(sdl_source),
                           '--prefix=' + str(sdl_source / 'linux-host'), '--enable-static',
                           '--disable-shared', '--disable-x11-shared', '--disable-video-x11',
                           '--disable-video-x11-xrandr', '--disable-video-x11-vm', '--disable-video-x11-xv'],
        cwd=sdl_build, env=sdl_environment)
    run('build-sdl2', ['make', '-j2'], cwd=sdl_build)
    run('stage-sdl2', ['make', '-j2', 'install'], cwd=sdl_build)
    recipe = json.loads((ROOT / 'native/build-recipe.json').read_text())
    commands = recipe['build']['commands']
    if len(commands) != 3 or commands[-1] != ['make', '-j2']:
        raise ValueError('Native recipe no longer matches this bounded three-stage build helper')
    for stage, command in zip(('autogen-native', 'configure-native', 'build-native'), commands):
        run(stage, command, cwd=native)
    executable = native / recipe['build']['executable']
    result['executable'] = {'path': str(executable), 'sha256': _sha256(executable)}
    for name in ('config.log', 'config.h'):
        path = native / name
        result.setdefault('configuration', {})[name] = {'path': str(path), 'sha256': _sha256(path)}
    run('binary-file', ['file', executable])
    run('binary-libraries', ['otool', '-L', executable])
    architectures = run('binary-architectures', ['lipo', '-archs', executable]).read_text().split()
    if architectures != ['arm64']:
        raise ValueError('Expected a native arm64 executable; found: ' + ' '.join(architectures))
    result['executable']['architectures'] = architectures
    result['native_build_performed'] = True

    report = work / 'native-tests'
    result['native_tests'] = {'report': str(report / 'result.json'), 'mode': mode,
                              'runtime': 'source checkout; installed wheel is checked separately'}
    run('native-tests', [python, ROOT / 'scripts/test_native.py', '--executable', executable,
                         '--report-dir', report, '--mode', mode, '--source-receipt', receipt,
                         '--timeout-seconds', '300'], timeout=360)
    acceptance = json.loads((report / 'result.json').read_text())
    if acceptance.get('accepted') is not True or acceptance.get('mode') != mode:
        raise ValueError('Native fixture runner did not accept the selected scope')
    tested = acceptance.get('executable', {})
    if (tested.get('path') != str(executable) or any(
            tested.get(field) != result['executable']['sha256']
            for field in ('sha256_before', 'sha256_after'))):
        raise ValueError('Native fixture receipt does not identify the executable just built')
    result['native_tests']['accepted'] = True
    result['status'] = 'succeeded'
    result['stage'] = 'complete'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', required=True, help='new absolute directory outside the checkout')
    parser.add_argument('--mode', choices=('all', 'headless', 'visible'), default='all')
    parser.add_argument('--upstream', help='local DOSBox-X Git object store for offline source preparation')
    args = parser.parse_args(argv)
    try:
        work = _work_directory(args.work_dir)
        upstream = Path(args.upstream).expanduser().resolve(strict=True) if args.upstream else None
        if upstream is not None and not upstream.is_dir():
            raise ValueError('--upstream must be a local Git repository directory')
        work.mkdir(mode=0o700)
        (work / 'logs').mkdir(mode=0o700)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    result = {'format': 'dotbox-local-macos-build-1', 'status': 'running', 'stage': 'preflight',
              'scope': SCOPE, 'mode': args.mode, 'started_utc': _timestamp(), 'steps': [],
              'native_build_performed': False,
              'host': {'system': platform.system(), 'architecture': platform.machine(),
                       'release': platform.release(), 'python': platform.python_version(),
                       'python_executable': sys.executable, 'free_bytes_at_start': shutil.disk_usage(work).free}}
    exit_code = 0
    try:
        _build(work, result, args.mode, upstream)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError,
            subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        result['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
        result['error'] = str(error) or type(error).__name__
        if result['stage'] == 'preflight' or result['stage'].startswith(('preflight-', 'version-')):
            result['prerequisites'] = {'command_line_tools': 'xcode-select --install', 'homebrew': PREREQUISITES}
            exit_code = 2
            print('If missing, install CLT with: xcode-select --install\n'
                  'Homebrew prerequisites: ' + PREREQUISITES, file=sys.stderr)
        else:
            exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
        print(result['error'], file=sys.stderr)
    finally:
        result['finished_utc'] = _timestamp()
        _save(work, result)
    print(json.dumps({'status': result['status'], 'stage': result['stage'],
                      'mode': args.mode, 'report': str(work / 'result.json')}))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
