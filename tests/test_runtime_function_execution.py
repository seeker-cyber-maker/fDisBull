"""Stored CPU evidence binds code epochs without changing native source IDs.

These are authored Unicorn peers for the capture contract, not a Wine run.
"""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

pytest.importorskip('z3')
pytest.importorskip('unicorn')

from fdisbull.project import Project
from fdisbull.runtime_code import qualify_capture
from fixtures_formats import pe64
import test_pe_function_execution as cpu_fixture


SITE = 0x140001000
RUN = 'authored-call-smc-cpu'


def _store(project, identifier, kind, document, *, run=RUN):
    raw = json.dumps(document, sort_keys=True).encode()
    project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
        (identifier, run, identifier + '.json', kind,
         hashlib.sha256(raw).hexdigest(), raw, '{}'))
    project.db.commit()


def _stored_path(project, name, x, *, unused_change=False):
    path = cpu_fixture._path(x)
    trace = deepcopy(path['trace'])
    trace['mapping'].update(source_sha256=project.meta['source_sha256'],
        version_sha256=project.version(1)['sha256'])
    trace['observation_contract'] = {'provider': 'authored-unicorn-replay'}
    trace['run'] = RUN
    for event in trace['events']:
        event['registers']['cpu_mode'] = 'long64'
    epochs = path['code']['versions']
    segments, versions = [], []
    for i, epoch in enumerate(epochs):
        begin = epoch['after_event']
        end = epochs[i + 1]['after_event'] if i + 1 < len(epochs) else len(trace['events'])
        identifier = name + '-' + str(i)
        raw = bytes.fromhex(epoch['image'][0]['hex'])
        if unused_change:
            # The RET after the observed caller NOP is not in the trace. It is
            # nevertheless part of the complete captured initial code image.
            raw = raw[:-1] + b'\x90'
        session = SimpleNamespace(project=project, version=project.version(1),
            run_id=RUN, static_base=0x140000000, runtime_base=0x140000000,
            delta=0, metadata={'backend': 'wine-qemu'},
            registers=lambda: trace['events'][begin]['registers'])
        capture = qualify_capture(session, {'project_address': hex(SITE),
            'runtime_address': hex(SITE), 'hex': raw.hex(),
            'sha256': hashlib.sha256(raw).hexdigest(), 'view': 'ram',
            'active_layers': [], 'generation': 0})
        _store(project, identifier + '-capture', 'code-snapshot', capture)
        version = project.debug_promote_code(identifier + '-capture', max_instructions=256)['version']
        _, labels = cpu_fixture._program()
        project.analyze(version=version, start=labels['smc_gate_return'], max_instructions=2)
        segment_trace = deepcopy(trace)
        segment_trace['events'] = segment_trace['events'][begin:end]
        _store(project, identifier + '-trace', 'trace', segment_trace)
        segments.append({'trace': identifier + '-trace', 'version': version})
        versions.append({'after_event': begin, 'version': version})
    return {'segments': segments, 'memory': path['memory'], 'code_versions': versions}


@pytest.fixture
def execution(tmp_path, monkeypatch):
    monkeypatch.setattr(cpu_fixture, 'BASE', SITE)
    source = tmp_path / 'authored.exe'
    source.write_bytes(pe64())
    database = tmp_path / 'analysis.fdb'
    with Project.create(database, source) as project:
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            (RUN, 1, 'authored', 'authored', 'closed', '{}'))
        project.db.commit()
        paths = [_stored_path(project, 'accept', 3), _stored_path(project, 'reject', 11)]
        yield project, paths


def _compare(project, paths, other=None):
    version = paths[0]['segments'][0]['version']
    other = paths if other is None else other
    return project.debug_compare_runtime_functions(version,
        other[0]['segments'][0]['version'], paths, other,
        contract=cpu_fixture._contract(), execution_mode=cpu_fixture.MODE)


def test_stored_epochs_compose_and_survive_project_reopen(execution):
    project, paths = execution
    frozen = deepcopy(paths)
    before = [tuple(row) for row in project.db.execute(
        'SELECT id,sha256,data FROM debug_artifacts ORDER BY id')]
    result = _compare(project, paths)
    assert result['function']['status'] == 'equivalent_under_contract', result
    accepted = result['function']['baseline_recovery']['cases'][0]
    assert len(accepted['ordered_accesses']) == 14
    assert len(accepted['internal_calls']) == 4
    assert len(accepted['code_versions']) == 2
    assert max(c['depth'] for c in accepted['internal_calls']) == 2
    assert all(segment['source_version'] == 1 and segment['execution_proven'] is False
        for path in result['baseline']['paths'] for segment in path['segments'])
    assert paths == frozen
    assert before == [tuple(row) for row in project.db.execute(
        'SELECT id,sha256,data FROM debug_artifacts ORDER BY id')]
    with Project(project.path) as reopened:
        assert _compare(reopened, paths)['function']['status'] == 'equivalent_under_contract'


def test_wrong_segment_epoch_cannot_supply_modified_instruction(execution):
    project, paths = execution
    changed = deepcopy(paths)
    changed[0]['segments'][1]['version'] = changed[0]['segments'][0]['version']
    with pytest.raises(ValueError, match='match.*observed capture'):
        _compare(project, changed)


def test_equal_fresh_initial_capture_keeps_its_distinct_identity(execution):
    project, paths = execution
    fresh = _stored_path(project, 'fresh', 3)
    assert fresh['segments'][0]['version'] != paths[0]['segments'][0]['version']
    result = _compare(project, paths, [fresh, paths[1]])
    assert result['function']['status'] == 'equivalent_under_contract', result
    assert result['layer']['paths'][0]['segments'][0]['version'] == fresh['segments'][0]['version']


def test_initial_capture_mismatch_in_unused_bytes_is_rejected(execution):
    project, paths = execution
    different = _stored_path(project, 'unused-change', 3, unused_change=True)
    with pytest.raises(ValueError, match='complete initial code image'):
        _compare(project, paths, [different, paths[1]])


@pytest.mark.parametrize('mutation', ['missing', 'wrong_count', 'reordered'])
def test_every_capture_boundary_is_required_in_execution_order(execution, mutation):
    project, paths = execution
    changed = deepcopy(paths)
    if mutation == 'missing':
        changed[0]['code_versions'].pop()
    elif mutation == 'wrong_count':
        changed[0]['code_versions'][1]['after_event'] += 1
    else:
        changed[0]['code_versions'].reverse()
    with pytest.raises(ValueError, match='boundary|boundaries|execution order'):
        _compare(project, changed)


def test_trace_run_cannot_be_reassigned_to_a_matching_code_capture(execution):
    project, paths = execution
    identifier = paths[0]['segments'][1]['trace']
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()
    trace = json.loads(bytes(row[0]))
    trace['run'] = 'foreign-run'
    _store(project, 'foreign-trace', 'trace', trace)
    changed = deepcopy(paths)
    changed[0]['segments'][1]['trace'] = 'foreign-trace'
    with pytest.raises(ValueError, match='owning source and run'):
        _compare(project, changed)


def test_source_identity_cannot_be_reassigned(execution):
    project, paths = execution
    identifier = paths[0]['segments'][1]['trace']
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()
    trace = json.loads(bytes(row[0]))
    trace['mapping']['source_sha256'] = '0' * 64
    _store(project, 'foreign-source', 'trace', trace)
    changed = deepcopy(paths)
    changed[0]['segments'][1]['trace'] = 'foreign-source'
    with pytest.raises(ValueError, match='owning source and run'):
        _compare(project, changed)


@pytest.mark.parametrize('case', ['return_slot', 'future_guard_code_write'])
def test_symbolic_execution_obligations_are_not_path_guards(case):
    """A valid sample or later guard cannot conceal earlier arbitrary writes."""
    import unicorn
    from unicorn import x86_const as reg
    from fdisbull.debug_semantics import normalize_trace, PE_TRACE_SEMANTICS
    from fdisbull.pe_function_recovery import compare_pe_functions
    from fdisbull.wine_arch import register_names
    if case == 'return_slot':
        # CALL's return word is replaced by unconstrained entry RAX. The sample
        # returns correctly, but the frame must hold for every admitted input.
        code = bytes.fromhex('e801000000 c3 48890424 c3 90')
        caller_offset, sample_rax, expected_kind = 11, 0x1005, 'balanced_return'
    else:
        # Store RAX into eight unused code bytes BEFORE CMP RAX,0 / JNE +0.
        # The observed zero store changes no bytes. A later path guard RAX==0
        # cannot retrospectively prove that the earlier epoch is constant.
        code = bytes.fromhex('48890508000000 4883f800 7500 c3 90') + bytes(8)
        caller_offset, sample_rax, expected_kind = 14, 0, 'stable_code_epoch'
    entry, stack = 0x1000, 0x8008
    caller = entry + caller_offset
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    cpu.mem_map(entry, 4096)
    cpu.mem_map(0x8000, 4096)
    cpu.mem_write(entry, code)
    cpu.mem_write(stack, caller.to_bytes(8, 'little'))
    cpu.reg_write(reg.UC_X86_REG_RSP, stack)
    cpu.reg_write(reg.UC_X86_REG_RAX, sample_rax)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
    def memory():
        return [{'address': hex(stack - 8), 'hex': bytes(cpu.mem_read(stack - 8, 16)).hex()}]
    before, events = memory(), []
    def observe(guest, address, size, _):
        events.append({'address': hex(address), 'project_address': hex(address),
            'bytes': bytes(guest.mem_read(address, size)).hex(),
            'registers': {'rip': hex(address), 'rflags': hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)),
                'thread': 17, 'general': {name: hex(guest.reg_read(
                    getattr(reg, 'UC_X86_REG_' + name.upper())))
                    for name in register_names(64) - {'rip', 'rflags'}}}})
    cpu.hook_add(unicorn.UC_HOOK_CODE, observe)
    cpu.emu_start(entry, caller + 1, count=16)
    normalize_trace('wine-qemu', events, version=1)
    image = [{'address': hex(entry), 'hex': code.hex()}]
    versions = [{'after_event': 0, 'image': image}]
    if case == 'future_guard_code_write':
        versions.append({'after_event': 1, 'image': image})
    path = {'trace': {'mapping': {'backend': 'wine-qemu', 'bits': 64,
            'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64}, 'version': 1,
            'semantics': PE_TRACE_SEMANTICS, 'complete': True, 'events': events},
        'memory': {'entry': before, 'exit': memory()},
        'code': {'entry': image, 'exit': image, 'versions': versions}}
    contract = {'entry_registers': {'rsp': hex(stack)},
        'memory_model': 'private_ordinary_ram',
        'memory_ranges': [{'address': hex(stack - 8), 'length': 16}],
        'entry_memory': [{'address': hex(stack), 'hex': caller.to_bytes(8, 'little').hex()}]}
    result = compare_pe_functions([path], [path], contract=contract,
        execution_mode=cpu_fixture.MODE)
    assert result['status'] == 'unknown', result
    assert result['execution_counterexample']['kind'] == expected_kind, result
