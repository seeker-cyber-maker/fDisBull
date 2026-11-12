"""Bounded, source-bound LLDB observation of an explicitly supplied Mach-O.

This is a one-shot native observation, not a persistent debugger session.  LLDB
is a separate Apple tool, and its facts remain distinct from fDisBull's stored
static analysis and from any later UIL interpretation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

from .macho_slices import MAX_MACHO_SIZE, select_macho_slice


_SCHEMA = 'fdisbull.macos-lldb-observation.v1'
_ENV_CONFIG = 'FDISBULL_LLDB_OBSERVATION_CONFIG'
_MAX_OUTPUT = 2048
_MAX_RESULT = 128 * 1024


def _source_still_matches(path: Path, *, size: int, sha256: str) -> bool:
    """Recheck exact bytes without an unbounded post-launch file read."""
    try:
        digest = hashlib.sha256()
        remaining = size
        with path.open('rb') as stream:
            while remaining:
                block = stream.read(min(remaining, 1024 * 1024))
                if not block:
                    return False
                digest.update(block)
                remaining -= len(block)
            if stream.read(1):
                return False
        return path.stat().st_size == size and digest.hexdigest() == sha256
    except OSError:
        return False


def _log_tail(path: Path) -> str:
    try:
        with path.open('rb') as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - _MAX_OUTPUT))
            return stream.read(_MAX_OUTPUT).decode('utf-8', errors='replace')
    except OSError:
        return ''


def _source_uuid(thin: bytes) -> str | None:
    """Read LC_UUID from a validated, little-endian arm64 thin Mach-O."""
    import struct

    count, command_bytes = struct.unpack_from('<II', thin, 16)
    position, end = 32, 32 + command_bytes
    for _ in range(count):
        command, size = struct.unpack_from('<II', thin, position)
        if command == 0x1B and size >= 24:
            return str(uuid.UUID(bytes=thin[position + 8:position + 24])).upper()
        position += size
        if position > end:
            break
    return None


def _failure(receipt: dict, status: str, reason: str) -> dict:
    receipt.update(status=status, reason=reason)
    return receipt


def _terminate_own_session(process: subprocess.Popen) -> None:
    """Stop only the LLDB session spawned by this call, never a named PID."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def observe_macos_arm64_launch(
    executable: str | os.PathLike[str],
    *,
    symbol: str,
    argv: tuple[str, ...] | list[str] = (),
    timeout_seconds: float = 20,
    memory_bytes: int = 32,
    instruction_count: int = 8,
    lldb_path: str | os.PathLike[str] | None = None,
) -> dict:
    """Launch one named arm64 Mach-O under Apple LLDB and return a JSON receipt.

    The caller must explicitly authorize executing ``executable``.  A resolved
    symbol breakpoint is required before launch.  The target is stopped once,
    observed and killed by the LLDB driver.  No attach or continuing is offered.
    Unsupported hosts, missing symbols, launch denials, non-breakpoint stops and
    timeouts are reported as distinct outcomes; none produces invented facts.
    """
    if not isinstance(symbol, str) or not 1 <= len(symbol) <= 256 or '\x00' in symbol:
        raise ValueError('symbol must contain 1..256 characters and no NUL')
    if not isinstance(argv, (tuple, list)) or len(argv) > 32 or any(
        not isinstance(item, str) or len(item) > 4096 or '\x00' in item for item in argv
    ):
        raise ValueError('argv must contain at most 32 bounded strings')
    if not 1 <= timeout_seconds <= 120:
        raise ValueError('timeout_seconds must be in 1..120')
    if not 0 <= memory_bytes <= 256 or not 0 <= instruction_count <= 32:
        raise ValueError('memory_bytes must be in 0..256 and instruction_count in 0..32')

    started = time.time()
    receipt: dict = {
        'schema': _SCHEMA,
        'run_id': str(uuid.uuid4()),
        'observed_at_unix': started,
        'backend': 'apple-lldb',
        'request': {'symbol': symbol, 'argv_count': len(argv),
                    'argv_sha256': hashlib.sha256(json.dumps(list(argv)).encode()).hexdigest(),
                    'timeout_seconds': timeout_seconds,
                    'memory_bytes': memory_bytes, 'instruction_count': instruction_count},
        'source': None,
        'status': 'error',
    }
    try:
        path = Path(executable).expanduser().resolve(strict=True)
        if not path.is_file():
            return _failure(receipt, 'unsupported', 'executable is not a regular file')
        size = path.stat().st_size
        if not 4 <= size <= MAX_MACHO_SIZE:
            return _failure(receipt, 'unsupported', 'Mach-O is outside the supported 4-byte to 64-MiB range')
        with path.open('rb') as stream:
            data = stream.read(MAX_MACHO_SIZE + 1)
        if len(data) > MAX_MACHO_SIZE:
            return _failure(receipt, 'unsupported', 'Mach-O grew beyond the 64-MiB input limit')
        receipt['source'] = {'path': str(path), 'size': len(data),
                             'sha256': hashlib.sha256(data).hexdigest()}
        thin, selected = select_macho_slice(data, 'arm64')
        if selected['endian'] != 'little' or selected['bits'] != 64:
            return _failure(receipt, 'unsupported', 'selected Mach-O is not little-endian arm64')
    except (OSError, ValueError) as exc:
        return _failure(receipt, 'unsupported', f'cannot select an arm64 Mach-O: {exc}')

    source = {
        'path': str(path),
        'size': len(data),
        'sha256': selected['source_sha256'],
        'slice_offset': selected['slice_offset'],
        'slice_size': selected['slice_size'],
        'slice_sha256': selected['slice_sha256'],
        'architecture': 'arm64',
        'cpu_subtype': selected['cpu_subtype'],
        'file_type': selected['file_type'],
        'uuid': _source_uuid(thin),
    }
    receipt['source'] = source
    if selected['file_type'] != 2:
        return _failure(receipt, 'unsupported', 'selected Mach-O is not an MH_EXECUTE image')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        return _failure(receipt, 'unsupported', 'one-shot launch requires an arm64 macOS host')
    resolved_lldb = Path(lldb_path).expanduser() if lldb_path else Path(shutil.which('lldb') or '')
    if not str(resolved_lldb) or not resolved_lldb.is_file():
        return _failure(receipt, 'unsupported', 'Apple LLDB executable is unavailable')
    resolved_lldb = resolved_lldb.resolve()
    receipt['backend_executable'] = str(resolved_lldb)

    driver = Path(__file__).with_name('_macos_lldb_driver.py')
    with tempfile.TemporaryDirectory(prefix='fdisbull-macos-lldb-') as directory:
        root = Path(directory)
        config_path, result_path = root / 'config.json', root / 'result.json'
        config_path.write_text(json.dumps({
            'executable': str(path), 'symbol': symbol, 'argv': list(argv),
            'memory_bytes': memory_bytes, 'instruction_count': instruction_count,
            'result_path': str(result_path),
        }), encoding='utf-8')
        # Keep inherited credentials and user LLDB init commands out of the probe.
        environment = {key: os.environ[key] for key in (
            'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER', 'SHELL',
            'DEVELOPER_DIR', 'SDKROOT',
        ) if key in os.environ}
        environment[_ENV_CONFIG] = str(config_path)
        command = [str(resolved_lldb), '--no-lldbinit', '--batch',
                   '-o', f'command script import "{driver}"', '-o', 'quit']
        with (root / 'lldb.stdout').open('wb') as stdout, (root / 'lldb.stderr').open('wb') as stderr:
            try:
                process = subprocess.Popen(command, cwd=root, env=environment,
                                           stdout=stdout, stderr=stderr, start_new_session=True)
            except PermissionError as exc:
                return _failure(receipt, 'permission_denied', f'cannot start LLDB: {exc}')
            except OSError as exc:
                return _failure(receipt, 'error', f'cannot start LLDB: {exc}')
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                _terminate_own_session(process)
                return _failure(receipt, 'timeout', 'Apple LLDB observation exceeded the declared wall-time limit')
            finally:
                _terminate_own_session(process)
        if not result_path.is_file():
            diagnostic = _log_tail(root / 'lldb.stderr')
            if not diagnostic:
                diagnostic = _log_tail(root / 'lldb.stdout')
            return _failure(receipt, 'error', f'LLDB produced no structured observation (exit {process.returncode}): {diagnostic}')
        try:
            with result_path.open('rb') as stream:
                raw_result = stream.read(_MAX_RESULT + 1)
            if len(raw_result) > _MAX_RESULT:
                return _failure(receipt, 'error', 'LLDB observation exceeds the result-size limit')
            observed = json.loads(raw_result.decode('utf-8'))
        except (OSError, ValueError) as exc:
            return _failure(receipt, 'error', f'LLDB observation is unreadable: {exc}')

    receipt.update(observed)
    source_unchanged = _source_still_matches(path, size=source['size'], sha256=source['sha256'])
    runtime = receipt.get('runtime')
    if isinstance(runtime, dict):
        image = runtime.get('main_image') or {}
        runtime['source_unchanged'] = source_unchanged
        runtime['source_uuid_match'] = (source['uuid'].upper() == image['uuid'].upper()
                                        if source['uuid'] and image.get('uuid') else None)
        runtime['source_path_match'] = bool(image.get('path') and
                                            Path(image['path']).resolve() == path)
        runtime['source_identity_confirmed'] = bool(
            source_unchanged and runtime['source_uuid_match'] is True and runtime['source_path_match'])
        if receipt.get('status') == 'ok' and not runtime['source_identity_confirmed']:
            status = ('identity_unconfirmed' if runtime['source_uuid_match'] is None
                      else 'identity_mismatch')
            return _failure(receipt, status, 'runtime main-image identity could not be confirmed')
    return receipt
