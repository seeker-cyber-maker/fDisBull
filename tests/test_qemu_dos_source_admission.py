"""Public stopped-LE admission with real projects and native-boundary peers."""
from copy import deepcopy
import hashlib
import json
import threading
from types import SimpleNamespace

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debugger import DebugWorkspace, stamp
from fdisbull.project import Project
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from test_qemu_dos_le_match import fixture as source_fixture


class StoppedPeer:
    """Only QMP/GDB are replaced; session admission and storage are real."""
    architecture = 'i386'

    def __init__(self, cpu, table, memory):
        self.cpu, self.table, self.memory_regions = deepcopy(cpu), table, list(memory)
        self.socket = object()
        self.operation_deadline = None
        self.reads, self.qmp_calls = [], []
        self.register_reads = self.monitor_reads = 0
        self.on_memory = self.on_registers = self.on_monitor = None
        self.running = False
        self.mode = 'protected'

    def registers(self):
        self.register_reads += 1
        if self.on_registers:
            self.on_registers(self)
        return dict(cs=hex(self.cpu['cs']), eip=hex(self.cpu['ip']), eflags='0x2')

    def monitor(self):
        self.monitor_reads += 1
        if self.on_monitor:
            self.on_monitor(self)
        c = self.cpu
        return (f"EIP={c['ip']:08x} EFL=00000002 A20=1\n"
                f"CS ={c['cs']:04x} {c['cs_base']:08x} {c['cs_limit']:08x} {c['cs_attributes']:08x}\n"
                "SS =0010 00000000 ffffffff 00c09300\n"
                f"CR0={'00000001' if self.mode == 'protected' else '00000000'} "
                "CR2=00000000 CR3=00000000 CR4=00000000 EFER=00000000\n"
                f"GDT= 00000800 {len(self.table)-1:08x}\n")

    def call(self, command, arguments=None, **kwargs):
        self.qmp_calls.append((command, deepcopy(arguments)))
        if command == 'query-status':
            return dict(running=self.running)
        assert command == 'human-monitor-command' and arguments == {'command-line': 'info registers'}, command
        return self.monitor()

    def memory(self, address, length, *, space, timeout_ms):
        assert space in ('physical', 'virtual') and 0 < timeout_ms <= 10000
        self.reads.append((address, length, space))
        regions = [(0x800, self.table), *self.memory_regions]
        data = bytes(length)
        for start, content in reversed(regions):
            if start <= address and address + length <= start + len(content):
                data = content[address-start:address-start+length]
                break
        return self.on_memory(self, address, length, space, data) if self.on_memory else data

    def execute(self, *args, **kwargs):
        pytest.fail('Stopped source admission attempted guest execution')

    def set_register(self, *args, **kwargs):
        pytest.fail('Stopped source admission attempted a register write')


@pytest.fixture
def owned(tmp_path, monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    image, cpu, table, memory, _, _ = source_fixture()
    source = tmp_path / 'BOUND.EXE'
    source.write_bytes(image.source_bytes)
    with Project.create(tmp_path / 'bound.fdb', source, image='mz') as project:
        selected = project.version()
        session = QemuDOSProcessSession.__new__(QemuDOSProcessSession)
        peer = StoppedPeer(cpu, table, memory)
        closed = []
        session.vm = SimpleNamespace(lock=threading.RLock(), gdb=peer, qmp=peer,
            process=SimpleNamespace(poll=lambda: None), operation_deadline=None,
            machine_configuration=dict(memory_mib=16, cpus=1),
            debugger=lambda: peer, close=lambda: closed.append(True))
        session.closed, session._deadline = False, None
        session.project, session.version, session.run_id = project, selected, 'source-run'
        session._runtime_epoch = 'source-run:process:1'
        session.metadata = dict(backend='qemu-dos', source_sha256=project.meta['source_sha256'],
                                version_sha256=selected['sha256'])
        session._process = dict(state='active', capture_epoch=session._runtime_epoch,
            psp_segment=0x1800, parent_psp_segment=0x1400,
            source_mapping=dict(status='initial-load-verified', live=True,
                runtime_base=0x18100, static_base=project.regions(1)[0].start,
                live_ranges=[dict(runtime_address=0x18100, project_address=project.regions(1)[0].start,
                                  length=len(project.regions(1)[0].data))]))
        session._layer_active, session._dos_task_monitor = [], None
        session._history_bind()
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (session.run_id, selected['id'], stamp(), None, 'stopped', json.dumps(session.metadata)))
        yield SimpleNamespace(session=session, peer=peer, project=project, source=source,
                              original=deepcopy(session._process), closed=closed)


def artifacts(project):
    return project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]


def test_public_admission_pins_complete_source_and_keeps_initial_mz_mapping(owned):
    s, p = owned.session, owned.project
    original_source = owned.source.read_bytes()
    reply = s.dos_source_admit(expected_source_sha256=p.meta['source_sha256'])
    assert reply['status'] == 'admitted' and reply['source_view'] == 'embedded-le'
    assert reply['source_sha256'] == hashlib.sha256(original_source).hexdigest()
    assert reply['version_sha256'] == p.version(1)['sha256']
    assert reply['capture_epoch'] == s._runtime_epoch and reply['run'] == s.run_id
    assert not reply['lifetime_qualified'] and not reply['live_mapping_installed']
    assert {span['object_id'] for span in reply['observation']['source_spans']} == {'le:1', 'le:2'}
    assert all('project_address' not in span for span in reply['observation']['source_spans'])
    assert s._process == owned.original and owned.source.read_bytes() == original_source
    assert not owned.closed and not owned.peer.running
    assert {c for c, _ in owned.peer.qmp_calls} == {'query-status', 'human-monitor-command'}
    assert len([e for e in p.db.execute('SELECT operation FROM debug_events')
                if e[0] == 'dos-source-admission']) == 1
    exported = owned.source.parent / 'stored-admission.json'
    p.debug_export(reply['artifact'], exported)
    data = exported.read_bytes()
    assert hashlib.sha256(data).hexdigest() == reply['sha256']
    doc = json.loads(data)
    public = deepcopy(doc['observation'])
    public['identity_evidence']['excluded_loader_fixup_count'] = len(public['identity_evidence'].pop('excluded_loader_fixups'))
    public['full_observation_in_artifact'] = True
    assert public == reply['observation'] and not doc['initial_mz_mapping_changed']
    assert set(doc['producer']) == {'le.py', 'qemu_dos_le_match.py', 'qemu_dos_source_admission.py'}
    assert all(any(a == address and n == length and space == kind for a, n, space in owned.peer.reads)
               for address, length in [(r['address'], r['length']) for r in doc['readback']]
               for kind in ('physical', 'virtual'))
    database = p.path
    p.__exit__()
    with Project(database) as cold:
        destination = exported.with_name('cold-admission.json')
        cold.debug_export(reply['artifact'], destination)
        assert destination.read_bytes() == data
        assert cold.meta['format'] == 'MZ' and cold.version(1)['sha256'] == reply['version_sha256']


@pytest.mark.parametrize('kind', ['pin', 'session-source', 'session-version', 'retained-source',
                                  'mapped-bytes', 'patched-version', 'closed', 'exited', 'epoch', 'overlays', 'task-view'])
def test_identity_and_ownership_refusals_publish_no_partial_artifact(owned, kind):
    s, p = owned.session, owned.project
    options = {}
    if kind == 'pin': options['expected_source_sha256'] = 'a' * 64
    elif kind == 'session-source': s.metadata['source_sha256'] = 'b' * 64
    elif kind == 'session-version': s.metadata['version_sha256'] = 'c' * 64
    elif kind == 'retained-source':
        raw = bytearray(owned.source.read_bytes()); raw[-1] ^= 1
        with p.transaction(True):
            p.db.execute('UPDATE binary_info SET source_bytes=? WHERE version=1', (bytes(raw),))
    elif kind == 'mapped-bytes':
        with p.transaction(True):
            p.db.execute('UPDATE regions SET data=? WHERE version=1', (b'changed',))
    elif kind == 'patched-version':
        changed = p.patch(p.regions(1)[0].start, '90')
        s.version = p.version(changed['version'])
    elif kind == 'closed': s.closed = True
    elif kind == 'exited': s._process['state'] = 'exited'
    elif kind == 'epoch': s._process['capture_epoch'] = 'earlier:process:1'
    elif kind == 'overlays': s._layer_active = ['ram-layer']
    else: s._dos_task_monitor = {'task': 'a'}
    with pytest.raises(ValueError):
        s.dos_source_admit(**options)
    assert artifacts(p) == 0 and not owned.peer.reads and not owned.closed


@pytest.mark.parametrize('options', [dict(max_compare_bytes=100), dict(max_scan_bytes=1),
    dict(max_compare_bytes=True), dict(max_scan_bytes=0), dict(timeout_ms=0),
    dict(expected_source_sha256='A'*64), dict(name='../outside.json')])
def test_budget_and_parameter_refusals_never_publish_a_partial_match(owned, options):
    with pytest.raises(ValueError):
        owned.session.dos_source_admit(**options)
    assert artifacts(owned.project) == 0 and owned.session._process == owned.original
    assert not owned.closed


@pytest.mark.parametrize('kind', ['cpu-drift', 'gdt-drift', 'memory-drift', 'physical-virtual', 'changed-code'])
def test_unstable_or_disagreeing_native_observations_refuse_before_publication(owned, kind):
    peer = owned.peer
    if kind == 'cpu-drift':
        def drift(p):
            if p.register_reads == 2: p.cpu['ip'] += 1
        peer.on_registers = drift
    elif kind == 'gdt-drift':
        def drift(p):
            if p.monitor_reads == 4: p.table += bytes(8)
        peer.on_monitor = drift
    elif kind == 'changed-code':
        start, code = peer.memory_regions[0]
        code = bytearray(code); code[0] ^= 1
        peer.memory_regions[0] = (start, bytes(code))
    else:
        def drift(p, address, length, space, data):
            selected = (space == 'virtual' if kind == 'physical-virtual' else
                        sum(a == address and n == length and t == space for a, n, t in p.reads) > 1)
            return bytes([data[0] ^ 1]) + data[1:] if selected else data
        peer.on_memory = drift
    with pytest.raises(ValueError):
        owned.session.dos_source_admit()
    assert artifacts(owned.project) == 0 and owned.session._process == owned.original
    assert not owned.closed


def test_unrelated_stopped_code_is_retained_as_unmatched_not_admitted(owned):
    owned.peer.cpu['ip'] = 0x60000
    reply = owned.session.dos_source_admit()
    assert reply['status'] == 'unmatched' and reply['observation'] is None
    assert reply['qualification'] == 'no-source-match' and not reply['live_mapping_installed']
    assert owned.session._process == owned.original and artifacts(owned.project) == 1


@pytest.mark.parametrize('mode', ['protected', 'real'])
def test_readonly_admission_or_mode_refusal_preserves_histories_and_frozen_undo(owned, mode):
    s = owned.session
    s._qemu_history_live = dict(valid=True, cursor='kept')
    s._qemu_cpu_delta_history = dict(id='undo', valid=True, frozen=True)
    owned.peer.mode = mode
    if mode == 'protected':
        assert s.dos_source_admit()['status'] == 'admitted'
    else:
        with pytest.raises(ValueError, match='protected32'):
            s.dos_source_admit()
    assert s._qemu_history_live == dict(valid=True, cursor='kept')
    assert s._qemu_cpu_delta_history == dict(id='undo', valid=True, frozen=True)


def test_json_method_dispatches_to_live_owned_admission(owned):
    workspace = DebugWorkspace()
    workspace.sessions[owned.session.run_id] = owned.session
    pin = owned.project.meta['source_sha256']
    reply = respond({'id': 1, 'method': 'debug-dos-source-admit', 'params': {
        'run': owned.session.run_id, 'name': 'json-admission.json',
        'expected_source_sha256': pin, 'max_compare_bytes': 524288, 'max_scan_bytes': 16777216,
        'timeout_ms': 5000}}, default_project=str(owned.project.path), debugger=workspace)
    assert reply['ok'] and reply['id'] == 1 and reply['result']['status'] == 'admitted'
    assert reply['result']['source_sha256'] == pin and artifacts(owned.project) == 1
    assert 'debug-dos-source-admit' in METHODS


def test_publication_failure_rolls_back_artifact_and_preserves_guest(owned):
    def failed_journal(operation, value):
        raise OSError('authored admission journal failure')
    owned.session._event = failed_journal
    with pytest.raises(OSError, match='journal failure'):
        owned.session.dos_source_admit()
    assert artifacts(owned.project) == 0
    assert owned.session._process == owned.original and not owned.closed


def test_tracking_status_preserves_history_and_frozen_selected_undo(owned):
    s = owned.session
    s._qemu_history_live = dict(valid=True, cursor='kept')
    s._qemu_cpu_delta_history = dict(id='undo', valid=True, frozen=True)
    assert s.tracking_status() == dict(enabled=False, state='not-attached')
    assert s._qemu_history_live == dict(valid=True, cursor='kept')
    assert s._qemu_cpu_delta_history == dict(id='undo', valid=True, frozen=True)
