"""Offline admission of authored native-shaped DOS trace evidence.

Native execution witnesses live in test_qemu_dos_trace_native.py. These cases
exercise retained identity, relocation and malformed-evidence boundaries that
must remain independently checkable after the emulator has closed.
"""
from copy import deepcopy
import hashlib
import json
import struct

import pytest

from fdisbull import event_search, execution_events
from fdisbull.debug_semantics import contract
from fdisbull.project import Project
from fdisbull.qemu_dos_process import relocated_source
from fdisbull.qemu_trace_identity import load_trace_binding, qualify_instruction


def mz(module, relocations=(1,), *, stack=0x200):
    header_size = (28 + len(relocations) * 4 + 15) & ~15
    size = header_size + len(module)
    header = bytearray(header_size)
    struct.pack_into('<14H', header, 0, 0x5a4d, size % 512, (size + 511) // 512,
                     len(relocations), header_size // 16, 0, 0xffff,
                     0, stack, 0, 0, 0, 28, 0)
    for index, offset in enumerate(relocations):
        struct.pack_into('<HH', header, 28 + index * 4, offset, 0)
    return bytes(header) + module


@pytest.fixture
def project(tmp_path):
    binary = tmp_path / 'OBSERVE.COM'
    binary.write_bytes(bytes.fromhex('b801009090ebfe'))
    with Project.create(tmp_path / 'observations.fdb', binary, image='com') as result:
        yield result


@pytest.fixture
def mz_project(tmp_path):
    binary = tmp_path / 'RELOC.EXE'
    binary.write_bytes(mz(bytes.fromhex('b800009090ebfe')))
    with Project.create(tmp_path / 'relocations.fdb', binary) as result:
        yield result


def metadata(project, *, run='run-a', segment=0x800, initial_ax=0):
    dos = project._document(1)['dos']
    source = bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0])
    is_com = project.meta['format'] == 'COM'
    header = dos['header_fields']
    psp = segment if is_com else segment - 0x10
    entry = dict(cs=segment if is_com else (segment + header['e_cs']) & 0xffff,
                 ip=0x100 if is_com else header['e_ip'],
                 ss=segment if is_com else (segment + header['e_ss']) & 0xffff,
                 sp=0xfffe if is_com else header['e_sp'], ax=initial_ax)
    report = dict(child_psp=psp, entry_cs=entry['cs'], entry_ip=entry['ip'],
        stack_ss=entry['ss'], stack_sp=entry['sp'], raw_stack_sp=(entry['sp'] - 2) & 0xffff,
        initial_ax=initial_ax)
    expected, mapping = relocated_source(source, dos, project.meta['format'], report)
    mapping.update(status='initial-load-verified', current_bytes='not continuously revalidated',
        source_sha256=project.meta['source_sha256'], expected_module_sha256=hashlib.sha256(expected).hexdigest(),
        observed_module_sha256=hashlib.sha256(expected).hexdigest(), live=True,
        live_ranges=[dict(runtime_address=mapping['runtime_base'], project_address=mapping['static_base'],
                          length=len(expected))])
    return dict(backend='qemu-dos', runtime_profile='dos-exec-load-only-v1', context='machine',
        source_sha256=project.meta['source_sha256'], version_sha256=project.version(1)['sha256'],
        runtime_inputs={'qemu': {'sha256': 'a' * 64, 'path': '/authored/native-shaped/qemu'}},
        process_disk=dict(prepared_boot_image={'sha256': 'b' * 64, 'path': '/authored/prepared.img'}),
        process=dict(state='active', psp_segment=psp, parent_psp_segment=0x200,
            entry=entry, source_mapping=mapping, capture_epoch=run + ':process:1',
            command_tail=dict(encoding='cp437', length=0, hex=''), environment='inherited',
            default_fcbs=dict(first='00' * 12, second='00' * 12), dos_version=dict(major=7, minor=10),
            drivers=dict(status='observed', headers=[]), entry_registers=dict(eax=hex(initial_ax)),
            evidence='authored initial entry receipt',
            termination=None, allocation=dict(mcb_segment=psp - 1, segment=psp, owner_psp=psp,
                paragraphs=0x1000, start=psp * 16, end=(psp + 0x1000) * 16, terminal=False)))


def policy():
    return dict(format='fdisbull-qemu-step-policy-1', status='observed', changed=False,
        bits=dict(ENABLE=1, NOIRQ=2, NOTIMER=4), mask=7, enabled=True,
        interrupts_masked=True, timers_masked=True, unknown_mask=0)


def document(project, *, run='run-a', segment=0x800, offsets=(0, 3), closed=True):
    mapping = metadata(project, run=run, segment=segment)
    binding = load_trace_binding(project, 1, mapping)
    process = mapping['process']
    events = []
    for sequence, relative in enumerate(offsets, 1):
        address = binding['mapping']['runtime_base'] + relative
        cs = segment
        ip = address - cs * 16
        code = binding['expected_bytes'][relative:relative + 15]
        qualification = qualify_instruction(binding, address, code, segment=cs, offset=ip)
        assert qualification['qualified']
        code = code[:qualification['instruction_size']].hex()
        pointer = dict(space='segmented', segment=hex(cs), offset=hex(ip))
        events.append(dict(sequence=sequence, address=hex(address), segmented_address=pointer,
            cpu_mode='real', code_bits=16, bytes=code, execution_bytes=code,
            project_address=qualification['project_address'], task_id=process['psp_segment'],
            mapping_id=process['capture_epoch'], registers=dict(eax=hex(sequence), eip=hex(ip), cs=hex(cs),
                ss=hex(process['entry']['ss']), esp=hex(process['entry']['sp']), eflags='0x202'),
            address_context=dict(cpu_mode='real', code_bits=16, paging_enabled=False, cr0='0x10',
                cs=dict(selector=hex(cs), base=hex(cs * 16), limit='0xffff', attributes='0x9b')),
            identity=dict(source_version=1, runtime_address=pointer,
                project_address=qualification['project_address'], context=qualification['context'],
                source_instruction_sha256=qualification['source_instruction_sha256']),
            observation=dict(registers_stage='before-instruction', instruction_completed=None,
                             flags_materialized=True)))
    return dict(version=1, run=dict(run=run), mapping=mapping, capture_epoch=process['capture_epoch'],
        native_process_capture=dict(format='fdisbull-qemu-dos-capture-1',
            capture_epoch=process['capture_epoch'], source_scope='initial verified DOS module', step_policy=policy()),
        observation_contract=contract('qemu-dos'), events=events, requested_count=len(events), complete=closed,
        window=dict(closed=closed, reason='count' if closed else 'source_boundary'))


def receipt(project, run, process):
    return project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
        (run, 'authored', 'dos-process-entry', json.dumps(dict(process=process, native_stop={})))).lastrowid


def save(project, value, *, entry=True):
    run = value['run']['run']
    with project.transaction(True):
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            (run, 1, 'authored', None, 'stopped', json.dumps(value['mapping'])))
        if entry:
            receipt(project, run, deepcopy(value['mapping']['process']))
        return project._debug_artifact(run, 'authored-native-trace.json', 'trace',
            json.dumps(value).encode(), {'complete': value['complete']})['artifact']


def update_run(project, run, value):
    with project.transaction(True):
        project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?', (json.dumps(value), run))


def test_native_linear_segmented_pc_and_canonical_mz_site_across_load_segments(mz_project):
    first = document(mz_project, run='first', segment=0x800)
    second = document(mz_project, run='second', segment=0xa00)
    a = execution_events.normalize_trace(first)['events'][0]
    b = execution_events.normalize_trace(second)['events'][0]
    assert a['pc'] == dict(project=0x10000, linear=0x8000, segment=0x800, offset=0)
    assert a['registers']['eip'] == 0 and a['registers']['cs'] == 0x800
    assert a['instruction_sha256'] != b['instruction_sha256']
    assert a['site'] == b['site']
    assert a['site']['instruction_sha256'] == hashlib.sha256(bytes.fromhex('b80010')).hexdigest()
    a_trace, b_trace = save(mz_project, first), save(mz_project, second)
    search = mz_project.event_search_start(a_trace)['artifact']
    retained = mz_project.event_search_refine(search, b_trace)['artifact']
    rows = mz_project.event_search_results(retained)['rows']
    assert len(rows) == 2 and all(row['support_trials'] == 2 for row in rows)


@pytest.mark.parametrize('state', ['exited', 'resident', 'observation_failed'])
def test_historical_native_trace_and_search_survive_lifecycle_epoch_and_reopen(project, state):
    value = document(project)
    trace = save(project, value)
    search = project.event_search_start(trace)['artifact']
    current = deepcopy(value['mapping'])
    current['process'].update(state=state, capture_epoch='run-a:process:3', machine_closed=True,
                              termination=dict(type='normal', code=0))
    current['process']['source_mapping'].update(status='invalidated-on-machine-close', live=False, live_ranges=[])
    current['runtime_inputs']['qemu']['path'] = '/same-content/moved/qemu'
    current['capabilities'] = dict(execution_trace=True)
    update_run(project, 'run-a', current)
    with Project(project.path) as reopened:
        assert len(reopened.event_search_results(search)['rows']) == 2
        query = reopened.event_trace_query(trace, predicate=dict(kind='register', register='ax', equals=1))
        assert query['matched_count'] == 1


@pytest.mark.parametrize('field', ['command_tail', 'environment', 'default_fcbs', 'dos_version',
                                  'drivers', 'entry_registers', 'evidence', 'process_disk'])
def test_historical_native_trace_still_checks_all_immutable_launch_evidence(project, field):
    value = document(project)
    trace = save(project, value)
    current = deepcopy(value['mapping'])
    if field == 'process_disk':
        current[field]['prepared_boot_image']['sha256'] = 'c' * 64
    else:
        current['process'][field] = 'changed after capture'
    update_run(project, 'run-a', current)
    with pytest.raises(ValueError, match='immutable'):
        project.event_trace_query(trace, predicate=dict(kind='mnemonic', equals='nop'))


@pytest.mark.parametrize('fault', ['exited', 'closed', 'not-live', 'different-status'])
def test_native_capture_requires_an_active_initial_mapping(project, fault):
    value = document(project)
    process = value['mapping']['process']
    if fault == 'exited':
        process['state'] = 'exited'
    elif fault == 'closed':
        process['machine_closed'] = True
    elif fault == 'not-live':
        process['source_mapping']['live'] = False
    else:
        process['source_mapping']['status'] = 'resident-allocation-intersection'
    trace = save(project, value)
    with pytest.raises(ValueError, match='active'):
        project.event_trace_query(trace, predicate=dict(kind='mnemonic', equals='nop'))


@pytest.mark.parametrize('fault', ['retirement', 'paging', 'cr0-pe', 'cr0-pg', 'no-cr0',
                                  'cs-width', 'cs-limit', 'cs-selector', 'cs-base'])
def test_native_source_events_require_observed_real_unpaged_cpu_state(project, fault):
    value = document(project)
    event = value['events'][0]
    context = event['address_context']
    if fault == 'retirement':
        event['observation']['instruction_completed'] = True
    elif fault == 'paging':
        context['paging_enabled'] = True
    elif fault == 'cr0-pe':
        context['cr0'] = '0x11'
    elif fault == 'cr0-pg':
        context['cr0'] = '0x80000010'
    elif fault == 'no-cr0':
        del context['cr0']
    elif fault == 'cs-width':
        context['cs']['attributes'] = '0x40009b'
    elif fault == 'cs-limit':
        context['cs']['limit'] = '0xff'
    elif fault == 'cs-selector':
        context['cs']['selector'] = '0x801'
    else:
        context['cs']['base'] = '0x8010'
    trace = save(project, value)
    with pytest.raises(ValueError):
        project.event_trace_query(trace, predicate=dict(kind='mnemonic', equals='nop'))


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'late', 'wrong-entry', 'wrong-parent'])
def test_original_process_entry_receipt_is_unique_immutable_and_precedes_capture(project, fault):
    value = document(project)
    trace = save(project, value, entry=fault != 'missing')
    with project.transaction(True):
        if fault == 'duplicate':
            receipt(project, 'run-a', value['mapping']['process'])
        elif fault == 'late':
            project.db.execute("UPDATE debug_events SET sequence=1000 WHERE operation='dos-process-entry'")
        elif fault in ('wrong-entry', 'wrong-parent'):
            changed = deepcopy(value['mapping']['process'])
            if fault == 'wrong-entry':
                changed['entry']['ip'] += 1
            else:
                changed['parent_psp_segment'] += 1
            project.db.execute("UPDATE debug_events SET evidence=? WHERE operation='dos-process-entry'",
                               (json.dumps(dict(process=changed)),))
    with pytest.raises((ValueError, RuntimeError)):
        project.event_trace_query(trace, predicate=dict(kind='mnemonic', equals='nop'))


@pytest.mark.parametrize('fault', ['runtime-base', 'project-base', 'loader-write', 'mapping-hash',
                                 'capture-epoch', 'event-epoch', 'task', 'source-hash',
                                 'project-pc', 'linear-pc', 'runtime-pc', 'observed-bytes',
                                 'missing-canonical', 'raw-machine', 'step-policy'])
def test_native_trace_rejects_unverified_mapping_or_instruction_claims(project, fault):
    value = document(project)
    event = value['events'][0]
    mapping = value['mapping']['process']['source_mapping']
    if fault == 'runtime-base':
        mapping['runtime_base'] += 16
    elif fault == 'project-base':
        mapping['static_base'] += 16
    elif fault == 'loader-write':
        mapping['loader_writes'].append(dict(module_offset=0, after_hex='90'))
    elif fault == 'mapping-hash':
        mapping['observed_module_sha256'] = 'f' * 64
    elif fault == 'capture-epoch':
        value['capture_epoch'] = 'run-a:process:2'
    elif fault == 'event-epoch':
        event['mapping_id'] = 'run-a:process:2'
    elif fault == 'task':
        event['task_id'] += 1
    elif fault == 'source-hash':
        event['identity']['source_instruction_sha256'] = 'f' * 64
    elif fault == 'project-pc':
        event['project_address'] += 1
        event['identity']['project_address'] += 1
    elif fault == 'linear-pc':
        event['address'] = hex(int(event['address'], 16) + 1)
    elif fault == 'runtime-pc':
        event['identity']['runtime_address'] = dict(space='segmented', segment='0x900', offset='0x100')
    elif fault == 'observed-bytes':
        event['bytes'] = event['execution_bytes'] = 'b80200'
    elif fault == 'missing-canonical':
        del event['identity']['source_instruction_sha256']
    elif fault == 'raw-machine':
        del value['native_process_capture']
    elif fault == 'step-policy':
        value['native_process_capture']['step_policy']['interrupts_masked'] = False
    trace = save(project, value)
    with pytest.raises(ValueError):
        project.event_trace_query(trace, predicate=dict(kind='mnemonic', equals='nop'))


def test_changed_source_boundary_is_preserved_without_a_cross_run_site(project):
    value = document(project, closed=False)
    event = value['events'][-1]
    event['bytes'] = event['execution_bytes'] = 'cc'
    event['project_address'] = None
    event['identity'].update(project_address=None, context=None)
    del event['identity']['source_instruction_sha256']
    trace = save(project, value)
    _, compiled = event_search._trace(project, trace)
    assert compiled['events'][-1]['site'] is None
    assert compiled['events'][-1]['pc']['linear'] == 0x8103
    query = project.event_trace_query(trace, predicate=dict(kind='mnemonic', equals='int3'))
    assert query['matched_count'] == 1 and not query['complete']
    with pytest.raises(ValueError, match='closed'):
        project.event_search_start(trace)


@pytest.mark.parametrize('fault', ['closed', 'continued'])
def test_unqualified_native_boundary_cannot_close_a_window_or_allow_continuation(project, fault):
    value = document(project, closed=fault == 'closed')
    event = value['events'][-1 if fault == 'closed' else 0]
    event['project_address'] = None
    event['identity'].update(project_address=None, context=None)
    del event['identity']['source_instruction_sha256']
    trace = save(project, value)
    with pytest.raises(ValueError, match='boundary'):
        project.event_trace_query(trace, predicate=dict(kind='mnemonic', equals='nop'))


def test_com_startup_words_are_in_canonical_source_identity(tmp_path):
    binary = tmp_path / 'MAXIMUM.COM'
    binary.write_bytes(b'\x90' * 0xff00)
    with Project.create(tmp_path / 'maximum.fdb', binary, image='com') as project:
        binding = load_trace_binding(project, 1, metadata(project, initial_ax=0x1234))
        assert binding['expected_bytes'][-4:] == bytes.fromhex('34120000')
        assert binding['project_bytes'][-4:] == bytes.fromhex('34120000')
        assert [item['kind'] for item in binding['mapping']['loader_writes']] == [
            'com-near-return-zero', 'load-only-initial-ax']


def test_ordered_overlapping_relocations_and_loader_write_use_independent_canonical_bytes(tmp_path):
    module = bytes.fromhex('b800000090909090')
    binary = tmp_path / 'ORDERED.EXE'
    binary.write_bytes(mz(module, relocations=(1, 1, 2), stack=8))
    with Project.create(tmp_path / 'ordered.fdb', binary) as project:
        binding = load_trace_binding(project, 1, metadata(project, segment=0x800, initial_ax=0xbeef))
        expected = bytearray(module)
        canonical = bytearray(module)
        for offset in (1, 1, 2):
            for result, load_segment in ((expected, 0x800), (canonical, 0x1000)):
                old = struct.unpack_from('<H', result, offset)[0]
                struct.pack_into('<H', result, offset, (old + load_segment) & 0xffff)
        expected[-2:] = canonical[-2:] = bytes.fromhex('efbe')
        assert binding['expected_bytes'] == expected
        assert binding['project_bytes'] == canonical
        qualification = qualify_instruction(binding, 0x8000, bytes(expected[:3]), segment=0x800, offset=0)
        assert not qualification['qualified'] and 'straddles' in qualification['reason']


def test_relocation_that_changes_decode_is_not_a_source_site(tmp_path):
    binary = tmp_path / 'OPCODE.EXE'
    binary.write_bytes(mz(bytes.fromhex('90b80000ebfe'), relocations=(0,)))
    with Project.create(tmp_path / 'opcode.fdb', binary) as project:
        binding = load_trace_binding(project, 1, metadata(project, segment=0x800))
        # This valid NOP includes only half the relocation word. Even though the
        # runtime byte agrees, a whole relocation cannot be assigned to it.
        result = qualify_instruction(binding, 0x8000, binding['expected_bytes'][:1], segment=0x800, offset=0)
        assert not result['qualified'] and 'straddles' in result['reason']
        # Starting at byte one sees a changed opcode from the adjacent fixup.
        result = qualify_instruction(binding, 0x8001, binding['expected_bytes'][1:], segment=0x800, offset=1)
        assert not result['qualified']


def test_instruction_must_be_file_backed_and_ignore_unrelated_data_mutation(mz_project):
    binding = load_trace_binding(mz_project, 1, metadata(mz_project))
    last = binding['mapping']['module_size'] - 1
    result = qualify_instruction(binding, 0x8000 + last, b'\xfe\xc0', segment=0x800, offset=last)
    assert not result['qualified'] and 'outside' in result['reason']
    result = qualify_instruction(binding, 0x8000 + last + 1, b'\x90', segment=0x800, offset=last + 1)
    assert not result['qualified'] and 'outside' in result['reason']
    # A lookahead's later bytes can be writable data; compare only the decoded
    # current instruction, rather than claiming a continuous full-module seal.
    changed = binding['expected_bytes'][:3] + b'\xcc' * 4
    result = qualify_instruction(binding, 0x8000, changed, segment=0x800, offset=0)
    assert result['qualified'] and result['instruction_size'] == 3
