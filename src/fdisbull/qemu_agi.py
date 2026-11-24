"""Owned, source-bound QEMU AGI raw LOGIC debugger session."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import uuid

from .debugger import stamp
from .dosbox_rpc import DebuggerError
from .gdb_rpc import GDBRemote
from .native_cpu import inspect_native_cpu
from .qemu_control import QemuControl
from .qemu_diagnostics import QemuInspectionMixin
from .qemu_agi_checkpoint import AGICheckpointMixin, checkpoint_capabilities
from .anchor_stones import AnchorStoneSessionMixin

BACKEND = 'qemu-agi'
EXECUTION_ERROR_FORMAT = 'fdisbull-qemu-agi-execution-error-1'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _remaining(deadline):
    value = int((deadline - time.monotonic()) * 1000)
    if value < 1:
        raise TimeoutError('AGI operation deadline expired')
    return min(value, 600000)


def _timeout(value):
    if type(value) is not int or not 1 <= value <= 600000:
        raise ValueError('AGI timeout must be 1..600000 ms')


class _Owner:
    def __init__(self, executable, data, *, deadline, runtime_package=None, on_spawn=None):
        self.process = self.qmp = self.gdb = None
        self.lock = threading.RLock()
        self.closed = False
        self._diagnostic_id = uuid.uuid4().hex
        self.inspection_target = 'agi'
        self.inspection_qom_cpu_type = 'agi-cpu'
        self.temporary = None
        self.log = None
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix='fdisbull-agi-')
            root = Path(self.temporary.name)
            self.qemu_log_path = root / 'qemu.log'
            rom = root / 'logic.bin'
            rom.write_bytes(data)
            if _sha(rom.read_bytes()) != _sha(data):
                raise ValueError('Private AGI source copy differs')
            qmp_path, gdb_path = root / 'qmp.sock', root / 'gdb.sock'
            machine = 'agi-test'
            if runtime_package is not None:
                package_path = root / 'runtime.json'
                package_path.write_bytes(runtime_package)
                if _sha(package_path.read_bytes()) != _sha(runtime_package):
                    raise ValueError('Private AGI runtime package copy differs')
                machine += ',runtime-package=' + str(package_path)
            cmd = [str(executable), '-machine', machine, '-accel', 'tcg',
                   '-nodefaults', '-no-user-config', '-nic', 'none', '-no-reboot',
                   '-display', 'none', '-monitor', 'none', '-S', '-kernel', str(rom),
                   '-qmp', f'unix:{qmp_path},server=on,wait=off',
                   '-gdb', f'unix:{gdb_path},server=on,wait=off']
            self.log = self.qemu_log_path.open('wb')
            self.process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=self.log)
            if on_spawn is not None:
                on_spawn(self.process)
            self.qmp = QemuControl(qmp_path, self.process, deadline)
            self.gdb = GDBRemote(gdb_path, self.process, deadline)
            if (self.gdb.architecture != 'agi' or
                    self.gdb.register_description != [dict(name='pc', number=0, size=4)]):
                raise DebuggerError('QEMU AGI GDB register description differs')
            if self.qmp.call('query-status', timeout_ms=_remaining(deadline)).get('running') is not False:
                raise DebuggerError('QEMU AGI did not start stopped')
            inventory = inspect_native_cpu(self.qmp, expected_target='agi',
                                           expected_cpu_type='agi-cpu', timeout_ms=_remaining(deadline))
            paths = inventory['cpu_paths']
            if len(paths) != 1:
                raise DebuggerError('Expected exactly one AGI CPU')
            self.cpu_path = paths[0] if isinstance(paths[0], str) else paths[0]['qom_path']
            for name, value in (('agi-observation-capacity', 4096), ('agi-observation-mask', 2)):
                self.qmp.call('qom-set', {'path': self.cpu_path, 'property': name, 'value': value},
                              timeout_ms=_remaining(deadline))
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            for channel in (self.gdb, self.qmp):
                if channel is not None:
                    try:
                        channel.close()
                    except Exception:
                        pass
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
        finally:
            if self.log is not None:
                self.log.close()
            if self.temporary is not None:
                self.temporary.cleanup()


class AGIQemuSession(AGICheckpointMixin, AnchorStoneSessionMixin, QemuInspectionMixin):
    """One live AGI machine, bound to a retained original raw source."""
    backend_id = BACKEND
    capabilities = dict(registers=True, step=True, run=True, qemu_diagnostics=True,
                        native_cpu_inventory=None, memory=False, breakpoints=False,
                        runtime_scene_observation=True, scene_planes=False,
                        save_states=False, save_states_runtime_stops=False, input=False,
                        agi_host_replies=False, agi_guest_saves=False)

    def __init__(self, project, executable, *, version=None, timeout_ms=30000, runtime_package=None, _on_spawn=None):
        _timeout(timeout_ms)
        deadline = time.monotonic() + timeout_ms / 1000
        selected = project.version(version)
        source_info = project.source_info(selected['id'])
        row = project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',
                                 (selected['id'],)).fetchone()
        if not source_info.get('verified') or row is None or row[0] is None:
            raise ValueError('AGI requires verified retained source bytes')
        data = bytes(row[0])
        regions = project.regions(selected['id'])
        if (selected.get('parent') is not None or project.meta.get('format') != 'raw'
                or project.meta.get('arch') != 'agi' or project.meta.get('bits') != 32
                or project.meta.get('entry') != 0 or len(regions) != 1
                or regions[0].start != 0 or not regions[0].executable
                or regions[0].data != data or not 1 <= len(data) <= 65536
                or _sha(data) != project.source_sha256(selected['id'])):
            raise ValueError('AGI requires an original unpatched raw LOGIC project mapped at zero')
        executable = Path(executable).expanduser().resolve(strict=True)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError('Expected an executable QEMU AGI binary')
        package_data = None
        if runtime_package is not None:
            package_path = Path(runtime_package).expanduser().resolve(strict=True)
            if not package_path.is_file() or not 1 <= package_path.stat().st_size <= 64*1024*1024:
                raise ValueError('AGI runtime package must be a bounded file')
            package_data = package_path.read_bytes()
            if not 1 <= len(package_data) <= 64*1024*1024:
                raise ValueError('AGI runtime package exceeds its byte bound')
        binary_sha = _sha(executable.read_bytes())
        version_line = subprocess.check_output([str(executable), '--version'], text=True,
                    stderr=subprocess.STDOUT, timeout=_remaining(deadline)/1000).splitlines()[0]
        self.project, self.version = project, selected
        self._executable, self._source_data, self._runtime_package = executable, data, package_data
        self.identity = dict(source_sha256=_sha(data), version_sha256=selected['sha256'],
                             qemu_sha256=binary_sha, qemu_version=version_line,
                             machine='agi-test', source_size=len(data),
                             runtime_package_sha256=_sha(package_data) if package_data is not None else None)
        self.capabilities = dict(type(self).capabilities, scene_planes=package_data is not None)
        self.run_id = uuid.uuid4().hex
        self.closed = False
        self.metadata = dict(backend=BACKEND, identity=self.identity, capabilities=self.capabilities)
        self.vm = _Owner(executable, data, deadline=deadline, runtime_package=package_data, on_spawn=_on_spawn)
        self.rpc = self.vm
        self.cpu_path = self.vm.cpu_path
        try:
            self.capabilities.update(checkpoint_capabilities(self.vm, deadline, runtime=package_data is not None))
            state = self._state()
            source = state.get('source', {})
            if package_data is None:
                source_valid = source.get('sha256') == self.identity['source_sha256'] and source.get('size') == len(data)
            else:
                source_valid = (source.get('sha256') == self.identity['runtime_package_sha256']
                                and source.get('logic_sha256') == self.identity['source_sha256']
                                and source.get('profile') == 'agi-2917-runtime-1'
                                and type(source.get('logic_id')) is int and 0 <= source['logic_id'] <= 255)
            if not source_valid:
                raise DebuggerError('QEMU AGI source identity differs')
            self._runtime_entry_logic = source.get('logic_id') if package_data is not None else None
            if _sha(executable.read_bytes()) != binary_sha:
                raise ValueError('QEMU binary changed during startup')
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id, selected['id'], stamp(), None, 'stopped', json.dumps(self.metadata)))
            project._live_debuggers.append(self)
        except BaseException:
            self.vm.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.closed:
            return
        if not self.vm.lock.acquire(timeout=10):
            raise TimeoutError('AGI machine is busy during close')
        try:
            if self.closed:
                return
            self.closed = True
            try:
                self.vm.close()
                with self.project.transaction(True):
                    self.project.db.execute('UPDATE debug_runs SET ended=?,state=? WHERE id=?',
                                            (stamp(), 'exited', self.run_id))
            finally:
                if self in self.project._live_debuggers:
                    self.project._live_debuggers.remove(self)
        finally:
            self.vm.lock.release()

    @contextmanager
    def _budget(self, owner, deadline):
        receipt = {}
        try:
            with self._inspection_owner(_remaining(deadline)) as (selected, check):
                if selected is not owner:
                    raise ValueError('AGI machine owner changed')
                channels = [c for c in (owner.qmp, owner.gdb) if c is not None]
                saved = [getattr(c, 'operation_deadline', None) for c in channels]
                try:
                    for channel, previous in zip(channels, saved):
                        channel.operation_deadline = min(deadline, previous) if previous is not None else deadline
                    yield receipt
                finally:
                    for channel, previous in zip(channels, saved):
                        channel.operation_deadline = previous
        except BaseException as error:
            if 'result' in receipt and getattr(error, 'result', None) is None:
                try:
                    self.close()
                except BaseException:
                    pass
                error.result = dict(format=EXECUTION_ERROR_FORMAT, execution=receipt['result'],
                                    do_not_replay=True, owner_closed=self._owner_reaped())
            raise

    def _stopped(self):
        if self.closed or self.vm.closed or self.vm.process.poll() is not None:
            raise DebuggerError('AGI machine is closed')
        if self.vm.qmp.call('query-status').get('running') is not False:
            raise ValueError('AGI machine must be stopped')
        return self.vm.gdb

    def _json_property(self, name):
        raw = self.vm.qmp.call('qom-get', {'path': self.cpu_path, 'property': name}, max_reply_bytes=4*1024*1024)
        if not isinstance(raw, str):
            raise DebuggerError('Invalid AGI observation')
        try:
            result = json.loads(raw)
        except (ValueError, TypeError) as error:
            raise DebuggerError('Invalid AGI observation JSON') from error
        if not isinstance(result, dict):
            raise DebuggerError('Invalid AGI observation envelope')
        return result

    def _state(self):
        return self._json_property('agi-state-json')

    def _events(self):
        return self._json_property('agi-events-json')

    def state(self, *, timeout_ms=10000):
        _timeout(timeout_ms)
        with self._budget(self.vm, time.monotonic()+timeout_ms/1000):
            self._stopped()
            return self._state()

    def events(self, *, timeout_ms=10000):
        _timeout(timeout_ms)
        with self._budget(self.vm, time.monotonic()+timeout_ms/1000):
            self._stopped()
            return self._events()

    def reply_host(self, ticket, *, accepted, text=None, number=None, snapshot_hex=None,
                   guest_save_artifact=None, timeout_ms=10000):
        """Complete one current native host request without resuming execution."""
        from .qemu_agi_reply import reply_host
        return reply_host(self, ticket, accepted=accepted, text=text, number=number,
                          snapshot_hex=snapshot_hex, guest_save_artifact=guest_save_artifact,
                          timeout_ms=timeout_ms)

    def capture_guest_save(self, ticket, *, name='agi-guest-save.bin', timeout_ms=10000):
        """Capture the pending save.game snapshot in a private project artifact."""
        from .qemu_agi_guest_save import capture
        return capture(self, ticket, name=name, timeout_ms=timeout_ms)

    def scene_observe(self, *, timeout_ms=10000):
        from .qemu_agi_scene import observe
        return observe(self, timeout_ms=timeout_ms)

    def registers(self, *, timeout_ms=10000):
        _timeout(timeout_ms)
        with self._budget(self.vm, time.monotonic()+timeout_ms/1000):
            values = self._stopped().registers()
            if set(values) != {'pc'} or values['pc'] is None:
                raise DebuggerError('AGI GDB register reply is incomplete')
            pc = int(values['pc'], 16)
            if not 0 <= pc <= 0xffffffff:
                raise DebuggerError('AGI PC is out of range')
            state = self._state()
            guest, source = state.get('guest', {}), state.get('source', {})
            logical_pc = guest.get('pc')
            logic_id = source.get('logic_id')
            if type(logical_pc) is not int or not 0 <= logical_pc <= 65536 or type(logic_id) is not int:
                raise DebuggerError('Invalid AGI logical execution position')
            runtime = self.identity['runtime_package_sha256'] is not None
            return dict(context='machine', architecture='agi', registers=values,
                        instruction_pointer=hex(pc), linear_pc=None if runtime else hex(pc),
                        cpu_mode='agi', address_context=('native runtime trampoline' if runtime else 'raw LOGIC byte offset'),
                        logical_position=dict(logic_id=logic_id, pc=logical_pc,
                                              source_sha256=source.get('logic_sha256') if runtime else source.get('sha256')))

    def contexts(self):
        self._refresh_inspection_capability()
        return dict(run=self.run_id, selected='machine', contexts=[dict(id='machine', kind='machine', capabilities=self.capabilities)])

    def context(self, name):
        if name != 'machine':
            raise ValueError('Unknown AGI machine context')
        return self

    def status(self):
        self._refresh_inspection_capability()
        if self.closed:
            return dict(context='machine', run=self.run_id, state='exited', capabilities=self.capabilities)
        with self._budget(self.vm, time.monotonic()+10):
            native = self.vm.qmp.call('query-status')
            return dict(context='machine', run=self.run_id, version=self.version['id'],
                        state='running' if native.get('running') else 'stopped', native=native,
                        capabilities=self.capabilities, mapping=self.metadata)

    def _owner_reaped(self):
        process = self.vm.process
        return bool(self.closed and self.vm.closed and process is not None and process.poll() is not None)

    def _event(self, operation, value):
        with self.project.transaction(True):
            self.project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                                    (self.run_id, stamp(), operation, json.dumps(value)))

    def _execute(self, command, timeout_ms):
        _timeout(timeout_ms)
        if self.project.db.in_transaction:
            raise ValueError('AGI execution requires no caller transaction')
        deadline = time.monotonic()+timeout_ms/1000
        with self._budget(self.vm, deadline) as receipt:
            prior = self.registers()
            before = self._state()
            guest = before.get('guest', {})
            retired = guest.get('retired')
            status = guest.get('status')
            if type(retired) is not int or retired < 0 or not isinstance(status, str):
                raise DebuggerError('Invalid AGI retirement state')
            terminal = {'return': 'return', 'quit': 'quit', 'fault': 'fault',
                        'pending': 'pending', 'effect': 'pending'}
            if status in terminal:
                outcome = terminal[status]
                return dict(context='machine', outcome=outcome, timed_out=False,
                            prior_registers=prior, registers=prior, retired=0,
                            session=dict(state='stopped', stop_reason=dict(kind=outcome,
                                address=None, breakpoint_ids=[], classification_complete=True)),
                            stop=dict(trigger=outcome, context='machine'))
            remaining = _remaining(deadline)
            execute_ms = remaining - min(100, max(2, remaining//4))
            if execute_ms < 1:
                raise TimeoutError('AGI execution budget cannot reserve stop observation')
            result = None
            try:
                reply, timed_out = self._stopped().execute(command, execute_ms)
                if not re.match(rb'^[TSWX][0-9a-fA-F]{2}', reply):
                    raise DebuggerError('Invalid AGI GDB stop reply')
                exited = reply[:1] in (b'W', b'X')
                outcome = 'exited' if exited else 'timeout' if timed_out else 'stopped'
                result = dict(context='machine', outcome=outcome, timed_out=timed_out,
                              prior_registers=prior, registers=None, retired=None,
                              session=dict(state='exited' if exited else 'stopped',
                                  stop_reason=dict(kind=outcome, address=None, breakpoint_ids=[],
                                                   native_reply=reply.decode('ascii'), classification_complete=False)),
                              stop=dict(trigger=outcome, context='machine'))
                if not exited:
                    result['registers'] = self.registers()
                    after = self._state()
                    current = after.get('guest', {})
                    after_retired, after_status = current.get('retired'), current.get('status')
                    if type(after_retired) is not int or after_retired < retired or not isinstance(after_status, str):
                        raise DebuggerError('Invalid AGI stop retirement state')
                    delta = after_retired-retired
                    result['retired'] = delta
                    if after_status in terminal:
                        outcome = terminal[after_status]
                    elif timed_out:
                        outcome = 'timeout'
                    elif command == 's' and delta == 1 and reply[1:3].lower() == b'05':
                        outcome = 'step'
                    else:
                        outcome = 'stopped'
                    result['outcome'] = outcome
                    result['stop']['trigger'] = outcome
                    result['session']['stop_reason'].update(kind=outcome, classification_complete=(outcome in (*terminal.values(), 'step')))
                receipt['result'] = result
                self._event('machine-step' if command == 's' else 'machine-run', result)
                _remaining(deadline)
                return result
            except BaseException as error:
                if result is None:
                    result = dict(prior_registers=prior, disposition='execution outcome uncertain; do not replay')
                try:
                    self.close()
                except BaseException:
                    pass
                error.result = dict(format=EXECUTION_ERROR_FORMAT, execution=result,
                                    do_not_replay=True, owner_closed=self._owner_reaped())
                raise

    def step(self, *, timeout_ms=10000):
        return self._execute('s', timeout_ms)

    def run(self, *, timeout_ms=10000):
        return self._execute('c', timeout_ms)
