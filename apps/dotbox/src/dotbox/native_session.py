# Adapted from fDisBull commit 9853c99952c2c0b77f2d9e33f99a05f0a242882b.
# Source: https://github.com/seeker-cyber-maker/fDisBull
# Original modules: debugger.py (original DOS launch/call/close), dos.py,
# dos_launch.py and image_views.py. Analysis/database layers are not included.
"""Own one original COM/MZ DOSBox process without an analysis project.

Source hashing records byte identity, not publisher authenticity. Runtime
attestation covers entry registers and explicitly reported file-backed samples;
it does not identify later dynamic code or establish whole-game recovery.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import time
import uuid

from .native_rpc import DOSBoxRPC, DebuggerError, DebuggerShutdownError
from .operation_budget import RpcAdmissionTimeout, deadline_scope


MAX_SOURCE_BYTES = 64 * 1024 * 1024
_HEADER_NAMES = ('e_magic', 'e_cblp', 'e_cp', 'e_crlc', 'e_cparhdr',
                 'e_minalloc', 'e_maxalloc', 'e_ss', 'e_sp', 'e_csum',
                 'e_ip', 'e_cs', 'e_lfarlc', 'e_ovno')


def _snapshot(path, *, retain=False, limit=None):
    """Hash one stable regular file, with a bounded retained source payload."""
    with path.open('rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or not before.st_size:
            raise ValueError('Expected a nonempty regular file: ' + str(path))
        if limit is not None and before.st_size > limit:
            raise ValueError('DOS source must be at most 64 MiB')
        digest, blocks, size = hashlib.sha256(), [], 0
        for block in iter(lambda: source.read(1024 * 1024), b''):
            size += len(block)
            if limit is not None and size > limit:
                raise ValueError('DOS source grew beyond 64 MiB')
            digest.update(block)
            if retain:
                blocks.append(block)
        after = os.fstat(source.fileno())

    def key(info):
        return (info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    if key(before) != key(after) or key(after) != key(path.stat()) or size != after.st_size:
        raise ValueError('Input changed during hashing: ' + str(path))
    identity = {'path': str(path), 'size': size, 'sha256': digest.hexdigest()}
    return identity, b''.join(blocks) if retain else None


def _image(data, filename):
    """Parse only the original DOS launch contract, without an analyzer."""
    if not data.startswith(b'MZ'):
        if filename.lower().endswith('.com') and not data.startswith(b'ZM') and 1 <= len(data) <= 0xff00:
            return {'format': 'COM', 'header_fields': {}, 'module': data,
                    'module_size': len(data), 'allocation_size': len(data),
                    'relocation_offsets': [], 'entry_cs': 0, 'entry_ip': 0x100,
                    'entry_module_offset': 0}
        raise ValueError('Standalone launch requires a classic MZ image or a 1..65280-byte .COM source')
    if len(data) < 28:
        raise ValueError('Truncated MZ header: at least 28 bytes are required')
    header = dict(zip(_HEADER_NAMES, struct.unpack_from('<14H', data)))
    if not header['e_cp'] or header['e_cblp'] > 511:
        raise ValueError('Invalid MZ page count or last-page byte count')
    declared = header['e_cp'] * 512
    if header['e_cblp']:
        declared -= 512 - header['e_cblp']
    header_size = header['e_cparhdr'] * 16
    if declared > len(data):
        raise ValueError('Truncated MZ image')
    if header_size < 28 or header_size >= declared:
        raise ValueError('MZ header must cover its fixed fields and leave a nonempty module')
    count, table = header['e_crlc'], header['e_lfarlc']
    if count and (table < 28 or table + count * 4 > header_size):
        raise ValueError('MZ relocation table must fit wholly inside the header')
    # Older relocations can overlap the later e_lfanew field. Only an
    # independently referenced recognizable signature selects a secondary view.
    independent_secondary = not (count and table < 64 and table + count * 4 > 60)
    if header_size >= 64 and independent_secondary:
        secondary = struct.unpack_from('<I', data, 60)[0]
        if 64 <= secondary < len(data) - 1 and any(
                data[secondary:secondary + 4].startswith(marker)
                for marker in (b'PE\0\0', b'NE', b'LE', b'LX')):
            raise ValueError('Secondary executable headers are outside the classic DOS MZ launch profile')
    module = data[header_size:declared]
    allocation = ((len(module) + 15) & ~15) + header['e_minalloc'] * 16
    if allocation > 0x100000 - 0x100:
        raise ValueError('MZ minimum allocation exceeds unwrapped real-mode memory')
    relocations = []
    for index in range(count):
        offset, segment = struct.unpack_from('<HH', data, table + index * 4)
        position = segment * 16 + offset
        if position + 2 > len(module):
            raise ValueError('MZ relocation target must be a complete file-backed word')
        relocations.append(position)
    # DOS relocates CS with 16-bit segment addition. Packed MZ images can
    # therefore express the module start as FFF0:0100. Normalize the relative
    # image offset here; runtime attestation must still reject actual A20 wrap.
    entry_offset = (header['e_cs'] * 16 + header['e_ip']) & 0xfffff
    if entry_offset >= allocation:
        raise ValueError('MZ entry must be inside the loaded image')
    return {'format': 'MZ', 'header_fields': header, 'module': module,
            'module_size': len(module), 'allocation_size': allocation,
            'relocation_offsets': relocations, 'entry_cs': header['e_cs'],
            'entry_ip': header['e_ip'], 'entry_module_offset': entry_offset}


def _guest_name(filename, digest, image_format):
    extensions = r'com' if image_format == 'COM' else r'(?:exe|com)'
    if re.fullmatch(r'[A-Za-z0-9_-]{1,8}\.' + extensions, filename, re.IGNORECASE):
        return filename
    return 'DB' + digest[:6].upper() + ('.COM' if image_format == 'COM' else '.EXE')


class _LaunchAlias:
    """Own a disposable copy; preserve replacements and guest modifications."""
    def __init__(self, directory, name, data):
        self.path = directory / name
        self.sha256 = hashlib.sha256(data).hexdigest()
        if any(path.name.casefold() == name.casefold() for path in directory.iterdir()):
            raise ValueError('DOS launch alias collides with an existing file: ' + name)
        with self.path.open('xb') as stream:
            info = os.fstat(stream.fileno())
            self.identity = (info.st_dev, info.st_ino)
            try:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
                stream.flush()
            except BaseException:
                self.close()
                raise

    def _unchanged(self, path):
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == self.identity
                and info.st_size <= MAX_SOURCE_BYTES
                and hashlib.sha256(path.read_bytes()).hexdigest() == self.sha256)

    def close(self):
        try:
            unchanged = self._unchanged(self.path)
        except FileNotFoundError:
            return {'status': 'absent', 'path': str(self.path)}
        except OSError as error:
            return {'status': 'retained_changed', 'path': str(self.path), 'error': str(error)}
        if not unchanged:
            return {'status': 'retained_changed', 'path': str(self.path)}
        try:
            directory = Path(tempfile.mkdtemp(prefix='.dotbox-alias-', dir=self.path.parent))
        except OSError as error:
            return {'status': 'retained_changed', 'path': str(self.path), 'error': str(error)}
        parked = directory / self.path.name
        try:
            self.path.rename(parked)
        except FileNotFoundError:
            directory.rmdir()
            return {'status': 'absent', 'path': str(self.path)}
        except OSError as error:
            directory.rmdir()
            return {'status': 'retained_changed', 'path': str(self.path), 'error': str(error)}
        try:
            if self._unchanged(parked):
                parked.unlink()
                directory.rmdir()
                return {'status': 'removed', 'path': str(self.path)}
            os.link(parked, self.path, follow_symlinks=False)
            parked.unlink()
            directory.rmdir()
            return {'status': 'retained_changed', 'path': str(self.path)}
        except OSError as error:
            return {'status': 'retained_changed', 'path': str(parked),
                    'original_alias': str(self.path), 'error': str(error)}


class NativeSession:
    """Start and own one DOSBox native session, stopped at original entry."""
    def __init__(self, executable, game_dir, program, *, window=True, window_scale=None, source_sha256=None):
        if type(window) is not bool:
            raise ValueError('window must be boolean')
        if window_scale is not None:
            if type(window_scale) is not int or not 2 <= window_scale <= 5:
                raise ValueError('window_scale must be an integer from 2 to 5')
            if not window:
                raise ValueError('window_scale requires window=True')
        if source_sha256 is not None and (
                not isinstance(source_sha256, str) or re.fullmatch('[0-9a-f]{64}', source_sha256) is None):
            raise ValueError('source_sha256 must be a lowercase SHA-256 identity')
        self.rpc = None
        self.session_id = None
        self.run_id = uuid.uuid4().hex
        self.closed = False
        self.close_receipt = None
        self._launch_alias = None
        self.game_dir = Path(game_dir).expanduser().resolve(strict=True)
        if not self.game_dir.is_dir():
            raise ValueError('game_dir must be a directory')
        source = Path(program).expanduser()
        source = (self.game_dir / source if not source.is_absolute() else source).resolve(strict=True)
        if source.parent != self.game_dir:
            raise ValueError('program must be a regular file directly inside game_dir')
        source_identity, data = _snapshot(source, retain=True, limit=MAX_SOURCE_BYTES)
        if source_sha256 is not None and source_identity['sha256'] != source_sha256:
            raise ValueError('Game executable does not match the recorded source hash')
        image = _image(data, source.name)
        executable = Path(executable).expanduser().resolve(strict=True)
        emulator_identity, _ = _snapshot(executable)
        target = _guest_name(source.name, source_identity['sha256'], image['format'])
        self.metadata = {'format': 'dotbox-native-session-1', 'source_sha256': source_identity['sha256'],
                         'source': source_identity, 'source_filename': source.name,
                         'image_format': image['format'], 'executable': str(executable),
                         'emulator_sha256': emulator_identity['sha256'], 'emulator': emulator_identity,
                         'game_dir': str(self.game_dir), 'target': target,
                         'target_aliased': target != source.name, 'window_requested': window,
                         'window_scale_requested': window_scale,
                         'runtime_profile': 'real-normal-com-v1' if image['format'] == 'COM' else 'real-normal-v1'}
        try:
            if target != source.name:
                self._launch_alias = _LaunchAlias(self.game_dir, target, data)
            options = {} if window_scale is None else {'window_scale': window_scale}
            self.rpc = DOSBoxRPC(executable, self.game_dir, window=window, **options)
            # Process startup/capability negotiation must not create a blind
            # interval in the original source identity check.
            if _snapshot(source, limit=MAX_SOURCE_BYTES)[0] != source_identity:
                raise ValueError('Game executable changed before session start')
            result = self.rpc.call('session.start', {
                'target': {'command': target, 'arguments': []},
                'mounts': [{'drive': 'C', 'host_path': str(self.game_dir)}], 'break_at': 'entry'})
            identifier = result.get('session_id')
            if not isinstance(identifier, str) or not identifier:
                raise DebuggerError('Native start did not identify the owned session')
            self.session_id = identifier
            self._attest_entry(image)
            self.metadata.update(capabilities=deepcopy(self.rpc.capabilities), pid=self.rpc.process.pid,
                                 launch=deepcopy(result))
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.launch_cleanup_errors = [{'phase': 'native-session-close',
                                                'type': type(cleanup_error).__name__,
                                                'message': str(cleanup_error)}]
            error.launch_cleanup_receipt = deepcopy(self.close_receipt)
            raise

    def _attest_entry(self, image):
        registers = self.call('state.get_registers')
        if registers.get('cpu_mode') != 'real':
            raise DebuggerError('Expected real-mode DOS entry')
        is_com = image['format'] == 'COM'
        try:
            cs = int(registers['segments']['cs'], 16)
            ip = int(registers['instruction_pointer'], 16)
        except (KeyError, TypeError, ValueError) as error:
            raise DebuggerError('Native entry registers are incomplete or invalid') from error
        if not 0 <= cs <= 0xffff or not 0 <= ip <= 0xffff:
            raise DebuggerError('Native entry registers must be 16-bit values')
        load = (cs - image['entry_cs']) & 0xffff
        if not (0 if is_com else 0x10) <= load <= 0xffff or ip != image['entry_ip']:
            raise DebuggerError('Runtime entry does not establish an unwrapped DOS load segment')
        base = load * 16 + (0x100 if is_com else 0)
        if base + image['allocation_size'] > 0x100000:
            raise DebuggerError('Runtime image would require A20 wrapping')
        entry = image['entry_module_offset']
        if cs * 16 + ip != base + entry:
            raise DebuggerError('Runtime entry would require A20 wrapping or leave the loaded image')
        if not is_com and ((load + image['header_fields']['e_ss']) * 16
                           + image['header_fields']['e_sp'] > 0x100000):
            raise DebuggerError('Runtime stack would require A20 wrapping')
        if is_com:
            try:
                same_segments = all(int(registers['segments'][name], 16) == load for name in ('ds', 'es', 'ss'))
            except (KeyError, TypeError, ValueError) as error:
                raise DebuggerError('COM startup segment registers are incomplete or invalid') from error
            if not same_segments:
                raise DebuggerError('COM startup DS, ES and SS must equal the PSP segment')
        expected = bytearray(image['module'])
        for offset in image['relocation_offsets']:
            original = struct.unpack_from('<H', expected, offset)[0]
            struct.pack_into('<H', expected, offset, (original + load) & 0xffff)
        # Preserve the source debugger's bounded COM sample. Also attest the
        # relocated MZ prefix and its file-backed entry when those differ.
        starts = [0]
        if 0 < entry < len(expected):
            starts.append(entry)
        samples = []
        for offset in starts:
            length = min(16, len(expected) - offset)
            observed = self.call('memory.read', {
                'address': {'space': 'linear', 'offset': f'0x{base + offset:08X}'}, 'length': length})
            try:
                payload = base64.b64decode(observed['data_base64'], validate=True)
            except (KeyError, TypeError, ValueError) as error:
                raise DebuggerError('Invalid native entry-byte response') from error
            if payload != expected[offset:offset + length]:
                raise DebuggerError('Runtime entry bytes differ from the original DOS source')
            samples.append({'module_offset': offset, 'runtime_address': base + offset,
                            'length': length, 'sha256': hashlib.sha256(payload).hexdigest()})
        self.metadata.update(runtime_load_segment=load, runtime_base=base,
                             module_size=image['module_size'], entry_registers=deepcopy(registers),
                             entry_bytes_verified=sum(sample['length'] for sample in samples),
                             attestation={'scope': 'entry registers and bounded original file-backed samples only',
                                          'samples': samples},
                             mapping_scope='Original file-backed span only; PSP, stack and later dynamic or overwritten code are not identified by address alone')

    def call(self, method, params=None):
        """Retain native contracts and intersect every call with its outer budget."""
        if self.closed:
            raise DebuggerError('Native session is closed')
        if not self.session_id:
            raise DebuggerError('Native session has not started')
        if params is not None and not isinstance(params, Mapping):
            raise ValueError('Native RPC parameters must be an object')
        parameters = dict(params or {})
        if 'session_id' in parameters and parameters['session_id'] != self.session_id:
            raise ValueError('Cannot address a different native session')
        parameters['session_id'] = self.session_id
        options = {}
        deadline = getattr(self, '_rpc_deadline', None)
        if deadline is not None:
            remaining = int((deadline - time.monotonic()) * 1000)
            admission = getattr(self, '_rpc_admission_ms', None) or 0
            if remaining <= 0 or remaining < admission:
                raise RpcAdmissionTimeout('Shared native host-time budget expired before RPC dispatch')
            options['timeout_ms'] = min(getattr(self, '_rpc_timeout_cap_ms', None) or 15000, remaining)
        return self.rpc.call(method, parameters, **options)

    def close(self):
        """Stop once and reap the owned child; uncertain dispatch is never replayed."""
        if self.closed:
            receipt = deepcopy(self.close_receipt)
            if receipt is not None and not receipt['closed']:
                raise DebuggerShutdownError(receipt)
            return receipt
        native_stop = {'state': 'interrupted', 'reason': 'session start was not acknowledged'}
        cleanup_errors, interrupted = [], None
        transport = None
        try:
            if self.rpc is not None and self.session_id is not None:
                # Shutdown has its own finite allowance. It must still reap an
                # owned process when an enclosing gameplay deadline expired.
                saved = {name: getattr(self, name, None) for name in (
                    '_rpc_deadline', '_rpc_timeout_cap_ms', '_rpc_admission_ms')}
                try:
                    self._rpc_deadline = None
                    self._rpc_timeout_cap_ms = None
                    self._rpc_admission_ms = None
                    with deadline_scope(self, time.monotonic() + 3, rpc_ms=3000, admission_ms=0):
                        operation = self.call('session.stop')
                        native_stop = self.call('execution.wait', {
                            'operation_id': operation['operation_id'], 'timeout_ms': 3000})
                finally:
                    for name, value in saved.items():
                        setattr(self, name, value)
        except BaseException as error:
            native_stop = {'state': 'interrupted', 'error': str(error)}
            if not isinstance(error, Exception):
                interrupted = error
        finally:
            try:
                if self.rpc is not None:
                    transport = self.rpc.close()
            except BaseException as error:
                cleanup_errors.append({'phase': 'rpc.close', 'type': type(error).__name__, 'message': str(error)})
                if not isinstance(error, Exception) and interrupted is None:
                    interrupted = error
            self.closed = True
            alias = None
            if self._launch_alias is not None:
                try:
                    alias = self._launch_alias.close()
                except BaseException as error:
                    cleanup_errors.append({'phase': 'launch-alias', 'type': type(error).__name__, 'message': str(error)})
                    if not isinstance(error, Exception) and interrupted is None:
                        interrupted = error
            code = None
            process = getattr(self.rpc, 'process', None)
            try:
                if process is not None:
                    code = process.poll()
            except BaseException as error:
                cleanup_errors.append({'phase': 'process-status', 'type': type(error).__name__, 'message': str(error)})
            stopped = native_stop.get('state') == 'exited' and not native_stop.get('running')
            reaped = code is not None if process is not None else None
            clean = stopped and reaped is True and type(code) is int and code == 0 and not cleanup_errors
            receipt = {'format': 'dotbox-shutdown-1', 'run': self.run_id,
                       'guest_stop': deepcopy(native_stop), 'guest_stop_complete': stopped,
                       'process_reaped': reaped, 'process_returncode': code,
                       'termination_signal': -code if type(code) is int and code < 0 else None,
                       'session_terminal': True, 'closed': clean,
                       'status': 'closed' if clean else 'interrupted',
                       'state': 'exited' if clean else 'interrupted'}
            if cleanup_errors:
                receipt['cleanup_errors'] = cleanup_errors
            if alias is not None:
                receipt['launch_alias_cleanup'] = alias
            if not clean:
                diagnostics = transport if transport is not None else getattr(self.rpc, 'close_evidence', None)
                if diagnostics is not None:
                    receipt['diagnostics'] = deepcopy(diagnostics)
            self.close_receipt = deepcopy(receipt)
        if interrupted is not None:
            interrupted.receipt = deepcopy(self.close_receipt)
            raise interrupted
        if not self.close_receipt['closed']:
            raise DebuggerShutdownError(self.close_receipt)
        return deepcopy(self.close_receipt)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            self.close()
        except Exception:
            if not args or args[0] is None:
                raise
