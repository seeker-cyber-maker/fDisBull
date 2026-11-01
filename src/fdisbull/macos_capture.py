"""Bounded transport to the shipped native macOS observation helper."""
from __future__ import annotations

import fcntl
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

_SOURCE = Path(__file__).with_name('data') / 'FdisbullMacCapture.swift'
_LIMIT = 512 * 1024


def _run(command, *, data=None, timeout=30, check=True):
    """Reap the helper before session rollback, including Ctrl-C and SIGTERM."""
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(data, timeout=timeout)
    except BaseException:
        with suppress(ProcessLookupError):
            process.kill()
        process.communicate()
        raise
    if len(stdout) > _LIMIT or len(stderr) > _LIMIT:
        raise ValueError('native helper output exceeded the reply budget')
    if check and process.returncode:
        raise ValueError('native helper failed: ' + stderr[-2000:].decode(errors='replace'))
    return stdout


def prepare_helper(*, cache=None):
    if platform.system() != 'Darwin':
        raise ValueError('native screen capture requires macOS 14 or later')
    version = platform.mac_ver()[0].split('.')
    if not version or not version[0].isdigit() or int(version[0]) < 14:
        raise ValueError('native screen capture requires macOS 14 or later')
    try:
        compiler = _run(['/usr/bin/xcrun', '--find', 'swiftc'], timeout=10).decode().strip()
        sdk = _run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'], timeout=10).decode().strip()
    except (subprocess.TimeoutExpired, UnicodeDecodeError) as exc:
        raise ValueError('Apple Swift compiler discovery failed') from exc
    if not compiler or not Path(compiler).is_file() or not sdk or not Path(sdk).is_dir():
        raise ValueError('Apple Swift compiler is unavailable')
    source = _SOURCE.read_bytes()
    target = platform.machine() + '-apple-macosx14.0'
    identity = {'source_sha256': hashlib.sha256(source).hexdigest(), 'compiler':compiler, 'sdk':sdk, 'target':target,
                'compiler_mtime_ns':Path(compiler).stat().st_mtime_ns,
                'system':platform.mac_ver()[0], 'machine':platform.machine()}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    folder = (Path(cache) if cache is not None else
              Path.home() / 'Library/Application Support/fDisBull/native-capture') / key
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    binary, receipt = folder / 'fdisbull-macos-capture', folder / 'build.json'
    with (folder / 'build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            saved = json.loads(receipt.read_text())
            if saved['identity'] == identity and saved['binary_sha256'] == hashlib.sha256(binary.read_bytes()).hexdigest():
                return binary
        except (OSError, ValueError, KeyError):
            pass
        with tempfile.TemporaryDirectory(prefix='build-', dir=folder) as temporary:
            output = Path(temporary) / 'helper'
            try:
                _run([compiler, '-parse-as-library', '-target', target, '-sdk', sdk, str(_SOURCE), '-o', str(output),
                      '-framework', 'AppKit', '-framework', 'ApplicationServices',
                      '-framework', 'ScreenCaptureKit', '-framework', 'ImageIO'], timeout=90)
            except subprocess.TimeoutExpired as exc:
                raise ValueError('native capture helper compilation timed out') from exc
            output.chmod(0o700)
            os.replace(output, binary)
        receipt.write_text(json.dumps({'identity':identity,
            'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}, indent=2) + '\n')
    return binary


class NativeCapture:
    """One request per process; no persistent controller or implicit permission prompt."""
    def __init__(self, *, timeout=20, cache=None):
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise ValueError('native timeout must be in (0,60] seconds')
        self.timeout = timeout
        self.helper = prepare_helper(cache=cache)
        self.identity = {'helper_sha256':hashlib.sha256(self.helper.read_bytes()).hexdigest(),
                         'source_sha256':hashlib.sha256(_SOURCE.read_bytes()).hexdigest(),
                         'transport':'one bounded native process per request'}

    def __call__(self, operation, **parameters):
        if operation not in {'snapshot', 'capture', 'press_status', 'dismiss_menu', 'prefs_get', 'prefs_set'}:
            raise ValueError('unknown native operation')
        request = json.dumps({'op':operation, **parameters}, allow_nan=False).encode()
        if len(request) > 128 * 1024:
            raise ValueError('native request exceeded its budget')
        try:
            raw = _run([str(self.helper)], data=request, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('native operation timed out; inspect session effects before retrying') from exc
        try:
            reply = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError('native helper returned invalid JSON') from exc
        if not isinstance(reply, dict) or reply.get('ok') is not True:
            error = reply.get('error', {}) if isinstance(reply, dict) else {}
            raise ValueError('native operation refused: ' + str(error.get('message', 'invalid reply'))[:2000])
        if not isinstance(reply.get('result'), dict):
            raise ValueError('native helper returned an invalid result')
        return reply['result']
