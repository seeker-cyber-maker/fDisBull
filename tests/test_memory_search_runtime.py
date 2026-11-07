"""Public artifact lifecycle, remapping and live-write failure boundaries."""
import base64
from copy import deepcopy
import hashlib
import json
import re
import struct

import pytest

from fdisbull.cli import respond
from fdisbull.memory_search_runtime import MemorySearchSessionMixin
from fdisbull.project import Project


class CaptureSession(MemorySearchSessionMixin):
    """Authored RAM peer; real Project storage and public API stay in the test."""
    def __init__(self, project):
        self.project = project
        self.version = project.version()
        self.run_id = 'authored-memory-run'
        self.metadata = dict(source_sha256=project.meta['source_sha256'], version_sha256=self.version['sha256'])
        self.ram = bytearray(0x10000)
        self.context = dict(cpu_mode='real', cr0='0x0', cr3='0x0', cr4='0x0', a20_enabled=True,
                            paging_enabled=False, code_bits=16, stack_bits=16)
        self.revision = 1
        self.stopped = True
        self.closed = False
        self.writes = []
        self.events = []
        self.after_read = None
        self.after_linear_read = None
        self.write_fault = None
        self._runtime_epoch = 'epoch-1'
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                               (self.run_id, self.version['id'], 'authored', None, 'stopped', json.dumps(self.metadata)))

    def _runtime_state(self):
        return {}

    def call(self, method, params=None):
        if method == 'session.status':
            return dict(state='stopped' if self.stopped else 'running', state_revision=self.revision)
        if method == 'state.get_registers':
            return dict(cpu_mode=self.context['cpu_mode'], address_context=deepcopy(self.context))
        if method == 'memory.read':
            assert re.fullmatch(r'0x[0-9A-F]{8}', params['address']['offset'])
            start = int(params['address']['offset'], 0)
            if params['address']['space'] == 'linear' and self.context['paging_enabled']:
                pte = struct.unpack_from('<I', self.ram, 0x2000 + (start >> 12) * 4)[0]
                start = (pte & ~4095) + (start & 4095)
            data = bytes(self.ram[start:start + params['length']])
            callback, self.after_read = self.after_read, None
            if callback:
                callback()
            if params['address']['space'] == 'linear' and self.after_linear_read is not None:
                callback, self.after_linear_read = self.after_linear_read, None
                callback()
            return dict(data_base64=base64.b64encode(data).decode())
        if method == 'memory.write':
            assert re.fullmatch(r'0x[0-9A-F]{8}', params['address']['offset'])
            start = int(params['address']['offset'], 0)
            data = base64.b64decode(params['data_base64'], validate=True)
            assert hashlib.sha256(self.ram[start:start + len(data)]).hexdigest() == params['expected_sha256']
            self.ram[start:start + len(data)] = data
            self.writes.append((start, data))
            self.revision += 1
            if self.write_fault == 'timeout':
                raise TimeoutError('authored acknowledgment lost after write')
            if self.write_fault == 'corrupt':
                self.ram[start] ^= 1
            return dict(written=len(data))
        raise AssertionError(method)

    def _artifact(self, *args):
        return self.project._debug_artifact(self.run_id, *args)

    def _event(self, operation, evidence):
        self.events.append((operation, deepcopy(evidence)))

    def close(self):
        self.closed = True


@pytest.fixture
def captured(tmp_path):
    binary = tmp_path / 'counter.com'
    binary.write_bytes(bytes.fromhex('90ebfd'))
    with Project.create(tmp_path / 'counter.fdb', binary, image='com') as project:
        yield project, CaptureSession(project)


def snap(session, *, space='linear'):
    return session.memory_snapshot(0x3000, length=8, space=space, task_id='authored-counter')['artifact']


def test_public_search_survives_reopen_and_refines_only_previous_survivors(captured):
    project, session = captured
    session.ram[0x3000:0x3008] = bytes([7, 7, 3, 5, 9, 0, 0, 0])
    first = snap(session)
    started = respond(dict(method='memory-search-start', params=dict(project=str(project.path), snapshot=first, mode='equal', value=7)))
    assert started['ok'], started
    search = started['result']['artifact']
    session.ram[0x3000:0x3008] = bytes([6, 7, 6, 5, 9, 0, 0, 0])
    second = snap(session)
    narrowed = project.memory_search_refine(search, second, mode='decreased')['artifact']
    with Project(project.path) as reopened:
        result = reopened.memory_search_results(narrowed)
        assert result['candidate_count'] == 1
        assert result['rows'][0]['address'] == '0x3000'
        assert result['rows'][0]['value'] == 6 and result['rows'][0]['previous_value'] == 7
    assert project.memory_search_results(search)['candidate_count'] == 2


def prepare_plan(project, session, **options):
    session.ram[0x3000:0x3008] = bytes([7, 2, 3, 4, 5, 6, 8, 9])
    search = project.memory_search_start(snap(session), mode='equal', value=7)['artifact']
    return project.memory_edit_plan(search, offset=0, value=99, **options)['artifact']


def test_apply_revalidates_original_bytes_and_is_single_use(captured):
    project, session = captured
    plan = prepare_plan(project, session)
    result = session.memory_apply(plan)
    assert result['applied'] and result['verified']
    assert session.ram[0x3000] == 99 and len(session.writes) == 1
    with pytest.raises(ValueError, match='already dispatched'):
        session.memory_apply(plan)


@pytest.mark.parametrize('fault', ['value', 'epoch', 'task', 'running'])
def test_stale_plan_refuses_before_dispatch(captured, fault):
    project, session = captured
    plan = prepare_plan(project, session)
    if fault == 'value':
        session.ram[0x3000] = 8
    elif fault == 'epoch':
        session._runtime_epoch = 'epoch-2'
    elif fault == 'task':
        session.context['cpu_mode'] = 'v86'
        session.context['cr0'] = '0x1'
    else:
        session.stopped = False
    with pytest.raises(ValueError):
        session.memory_apply(plan)
    assert not session.writes


@pytest.mark.parametrize('fault', ['timeout', 'corrupt'])
def test_uncertain_write_closes_guest_and_keeps_attempt_evidence(captured, fault):
    from fdisbull.runtime_observations import RuntimeMemoryWriteError
    project, session = captured
    plan = prepare_plan(project, session)
    session.write_fault = fault
    with pytest.raises(RuntimeMemoryWriteError) as error:
        session.memory_apply(plan)
    assert session.closed and len(session.writes) == 1
    assert error.value.result['dispatch_outcome'] == 'unknown'
    assert any(name == 'memory-search-write-attempt' for name, _ in session.events)
    assert any(name == 'memory-search-write-failed' for name, _ in session.events)


def test_false_condition_does_not_write(captured):
    project, session = captured
    plan = prepare_plan(project, session, condition='greater', compare_value=10)
    assert session.memory_apply(plan)['applied'] is False
    assert not session.writes


def test_completion_journal_failure_retains_verified_write_receipt_and_closes_guest(captured):
    from fdisbull.runtime_observations import RuntimeMemoryWriteError
    project, session = captured
    plan = prepare_plan(project, session)
    original_event = session._event

    def fail_completion(operation, evidence):
        if operation == 'memory-search-write':
            raise OSError('authored completion journal failure')
        return original_event(operation, evidence)

    session._event = fail_completion
    with pytest.raises(RuntimeMemoryWriteError) as failed:
        session.memory_apply(plan)
    receipt = failed.value.result
    assert receipt['applied'] and receipt['verified']
    assert receipt['failure_phase'] == 'completion-journal'
    assert receipt['after_hex'] == '63' and session.ram[0x3000] == 99
    assert session.closed and len(session.writes) == 1
    with pytest.raises(ValueError, match='already dispatched'):
        session.memory_apply(plan)


@pytest.mark.parametrize('backend', ['scummvm-agi', 'scummvm-gob', 'wine-qemu'])
def test_engine_or_windows_inherited_surface_cannot_capture_dos_ram(captured, backend):
    _, session = captured
    session.metadata['backend'] = backend
    with pytest.raises(ValueError, match='requires DOSBox'):
        snap(session)
    assert not session.writes


def paged(session):
    session.context.update(cpu_mode='v86', cr0='0x80000001', cr3='0x1000', paging_enabled=True)
    struct.pack_into('<I', session.ram, 0x1000, 0x2007)
    struct.pack_into('<I', session.ram, 0x2000 + 3 * 4, 0x5007)
    session.ram[0x5000:0x5008] = bytes([1, 2, 3, 4, 5, 6, 7, 8])


def test_same_cr3_different_pte_is_a_different_snapshot_identity(captured):
    project, session = captured
    paged(session)
    first = snap(session)
    search = project.memory_search_start(first)['artifact']
    struct.pack_into('<I', session.ram, 0x2000 + 3 * 4, 0x6007)
    second = snap(session)
    with pytest.raises(ValueError, match='context'):
        project.memory_search_refine(search, second, mode='changed')


def test_page_accessed_dirty_activity_is_not_a_remap(captured):
    project, session = captured
    paged(session)
    first = snap(session)
    search = project.memory_search_start(first)['artifact']
    struct.pack_into('<I', session.ram, 0x1000, 0x2027)
    struct.pack_into('<I', session.ram, 0x2000 + 3 * 4, 0x5067)
    second = snap(session)
    narrowed = project.memory_search_refine(search, second, mode='unchanged')
    assert narrowed['results']['candidate_count'] == 8


def test_capture_rejects_mid_read_translation_change(captured):
    project, session = captured
    paged(session)
    session.after_linear_read = lambda: struct.pack_into('<I', session.ram, 0x2000 + 3 * 4, 0x6007)
    with pytest.raises(ValueError, match='changed'):
        snap(session)
    assert project.debug_artifacts()['artifacts'] == []


def test_missing_task_identity_and_unknown_mapping_fail(captured):
    _, session = captured
    with pytest.raises(ValueError, match='task_id'):
        session.memory_snapshot(0x3000, length=8)
    paged(session)
    struct.pack_into('<I', session.ram, 0x2000 + 3 * 4, 0)
    with pytest.raises(ValueError, match='mapping'):
        snap(session)
