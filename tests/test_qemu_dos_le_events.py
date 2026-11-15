"""Cold, source-grounded LE event reconstruction; no guest or game bytes."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull import event_search, execution_events
from fdisbull.debug_semantics import contract
from fdisbull.project import Project
from fdisbull.qemu_dos_le_identity import (
    BINDING_FORMAT, CAPTURE_FORMAT, SOURCE_SCOPE, make_recipe, qualify_instruction,
)
from test_qemu_dos_le_match import fixture as source_fixture
from test_qemu_dos_source_admission import owned
from test_qemu_trace_identity import metadata, policy, receipt


def stored(project, identifier):
    return json.loads(bytes(project.db.execute(
        'SELECT data FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()[0]))


def replace_artifact(project, identifier, document):
    """Reseal an authored mutation, including its receipt, to test semantics."""
    data = json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
    digest = hashlib.sha256(data).hexdigest()
    with project.transaction(True):
        project.db.execute('UPDATE debug_artifacts SET data=?,sha256=? WHERE id=?',
                           (data, digest, identifier))
        rows = project.db.execute("SELECT sequence,evidence FROM debug_events WHERE operation='artifact'").fetchall()
        for row in rows:
            value = json.loads(row['evidence'])
            if value.get('artifact') == identifier:
                value.update(sha256=digest, size=len(data))
                project.db.execute('UPDATE debug_events SET evidence=? WHERE sequence=?',
                                   (json.dumps(value), row['sequence']))


def operation(project, run, name, document):
    with project.transaction(True):
        return project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
            (run, 'authored', name, json.dumps(document))).lastrowid


@pytest.fixture
def le_trace(owned, request):
    s, p = owned.session, owned.project
    launch = metadata(p, run=s.run_id)
    launch['machine_configuration'] = dict(cpus=1, memory_mib=16)
    s.metadata, s._process = deepcopy(launch), deepcopy(launch['process'])
    options = getattr(request, 'param', {})
    s._runtime_epoch = options.get('epoch', launch['process']['capture_epoch'])
    s._process['capture_epoch'] = s._runtime_epoch
    with p.transaction(True):
        p.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?', (json.dumps(launch), s.run_id))
        receipt(p, s.run_id, launch['process'])
    admission = s.dos_source_admit()
    initial = stored(p, admission['artifact'])
    image, cpu, gdt, memory, _, source_read = source_fixture()
    cpu.update(gdtr_base=0x800, gdtr_limit=len(gdt)-1)
    recipe = make_recipe(image, initial, binding_id='authored-le-binding')
    binding_document = dict(format=BINDING_FORMAT, recipe=recipe,
        admission={key: admission[key] for key in ('artifact', 'sha256', 'size')},
        gdt_hex=gdt.hex(), producer={'qemu_dos_le_identity.py': 'e'*64})
    binding = p._debug_artifact(s.run_id, 'binding.json', 'dos-source-binding',
                               json.dumps(binding_document).encode(), {})
    operation(p, s.run_id, 'dos-source-bind', dict(artifact=binding['artifact'],
        sha256=binding['sha256'], binding_id=recipe['binding_id'],
        capture_epoch=recipe['capture_epoch'], admission=binding_document['admission']))
    mapping = deepcopy(launch)
    mapping['process'] = deepcopy(s._process)
    mapping.update(protected_source_binding=recipe,
        protected_source_binding_artifact={key: binding[key] for key in ('artifact', 'sha256', 'size')},
        protected_source_binding_material=dict(gdt_hex=gdt.hex()))
    events = []
    for sequence, offset in enumerate(options.get('offsets', (64, 66)), 1):
        current = dict(cpu, ip=0x50000+offset)
        reads = []
        def read(address, length):
            data = source_read(address, length)
            reads.append(dict(address=address, length=length, hex=data.hex()))
            return data
        qualification = qualify_instruction(image, recipe, current, gdt, read)
        assert qualification['qualified'], qualification
        pointer = dict(space='segmented', segment=hex(current['cs']), offset=hex(current['ip']))
        events.append(dict(sequence=sequence, address=hex(current['ip']), segmented_address=pointer,
            cpu_mode='protected', code_bits=32, bytes=qualification['execution_bytes'],
            execution_bytes=qualification['execution_bytes'], project_address=None, task_id=None,
            mapping_id=recipe['binding_id'], registers=dict(eax=hex(sequence), eip=hex(current['ip']),
                cs=hex(current['cs']), eflags='0x2'),
            address_context=dict(cpu_mode='protected', code_bits=32, paging_enabled=False, a20=True,
                cr0=1, cr2=0, cr3=0, cr4=0,
                cs=dict(selector=current['cs'], base=current['cs_base'], limit=current['cs_limit'],
                        attributes=current['cs_attributes'])),
            identity=dict(source_version=1, runtime_address=pointer, project_address=None,
                source_location=qualification['source_location'], context=qualification['context'],
                source_instruction_sha256=qualification['source_instruction_sha256']),
            source_qualification={key: value for key, value in qualification.items() if key!='execution_bytes'},
            le_source_witness=dict(cpu=current, gdt_sha256=hashlib.sha256(gdt).hexdigest(), readback=reads),
            observation=dict(registers_stage='before-instruction', instruction_completed=None,
                             flags_materialized=True)))
    document = dict(version=1, run=dict(run=s.run_id), mapping=mapping,
        capture_epoch=recipe['capture_epoch'], native_process_capture=dict(format=CAPTURE_FORMAT,
            source_scope=SOURCE_SCOPE, binding_id=recipe['binding_id'],
            capture_epoch=recipe['capture_epoch'], step_policy=policy()),
        observation_contract=contract('qemu-dos'), events=events, requested_count=2,
        complete=True, window=dict(closed=True, reason='count'))
    artifact = p._debug_artifact(s.run_id, 'le-trace.json', 'trace', json.dumps(document).encode(), {})
    owned.document, owned.trace = document, artifact
    owned.binding_document, owned.binding = binding_document, binding
    owned.admission, owned.recipe = admission, recipe
    yield owned


def test_embedded_sites_keep_object_namespace_and_runtime_predicates(le_trace):
    o = le_trace
    _, compiled = event_search._trace(o.project, o.trace['artifact'])
    first = compiled['events'][0]
    assert first['pc'] == dict(project=None, linear=0x50040, segment=8, offset=0x50040)
    assert first['site']['space'] == 'embedded-le' and first['site']['address'] == 64
    assert first['site']['object_id'] == 'le:1'
    assert first['site']['application_source_sha256'] == o.recipe['application_source_sha256']
    assert first['site']['instruction_sha256'] == o.document['events'][0]['identity']['source_instruction_sha256']
    assert compiled['regions'] == []
    for predicate, count in ((dict(kind='mnemonic', equals='push'), 2),
                             (dict(kind='register', register='eax', equals=1), 1),
                             (dict(kind='pc-range', space='linear', start=0x50040, end=0x50042), 1)):
        assert o.project.event_trace_query(o.trace['artifact'], predicate=predicate)['matched_count'] == count
    query = o.project.event_trace_query(o.trace['artifact'],
        predicate=dict(kind='pc-range', space='project', start=0, end=2**32))
    assert query['matched_count'] == 0 and query['unknown_count'] == 2


def test_embedded_search_and_exact_export_survive_cold_reopen(le_trace, tmp_path):
    o, p = le_trace, le_trace.project
    search = p.event_search_start(o.trace['artifact'])
    retained = p.event_search_refine(search['artifact'], o.trace['artifact'])
    before = p.event_search_results(retained['artifact'])
    assert before['candidate_count'] == 2
    p.debug_export(o.trace['artifact'], tmp_path/'warm.json')
    original = (tmp_path/'warm.json').read_bytes()
    path = p.path
    p.__exit__()
    with Project(path) as cold:
        cold.debug_export(o.trace['artifact'], tmp_path/'cold.json')
        assert (tmp_path/'cold.json').read_bytes() == original
        assert cold.event_search_results(retained['artifact']) == before
        assert cold.event_trace_query(o.trace['artifact'],
            predicate=dict(kind='mnemonic', equals='push'))['matched_count'] == 2


@pytest.mark.parametrize('fault', ['location', 'context', 'digest', 'runtime-bytes', 'readback',
    'missing-read', 'cpu', 'gdt', 'task', 'project', 'qualification'])
def test_resealed_source_claim_tampering_cannot_qualify(le_trace, fault):
    o = le_trace; document = deepcopy(o.document); event = document['events'][0]
    if fault == 'location': event['identity']['source_location']['object_offset'] += 2
    elif fault == 'context': event['identity']['context'] = 'embedded-le:'+'f'*64+':le:1:32'
    elif fault == 'digest': event['identity']['source_instruction_sha256'] = 'f'*64
    elif fault == 'runtime-bytes': event['bytes'] = event['execution_bytes'] = '9090'
    elif fault == 'readback':
        row = event['le_source_witness']['readback'][0]
        row['hex'] = '90'+row['hex'][2:]
    elif fault == 'missing-read': event['le_source_witness']['readback'] = []
    elif fault == 'cpu': event['le_source_witness']['cpu']['cs_base'] = 16
    elif fault == 'gdt': event['le_source_witness']['gdt_sha256'] = 'f'*64
    elif fault == 'task': event['task_id'] = 1
    elif fault == 'project': event['project_address'] = 0x10000
    elif fault == 'qualification': event['source_qualification']['instruction_size'] = 1
    replace_artifact(o.project, o.trace['artifact'], document)
    with pytest.raises(ValueError):
        o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push'))


@pytest.mark.parametrize('fault', ['binding-hash', 'admission-hash', 'binding-order', 'admission-order',
    'binding-recipe', 'gdt-material', 'source-pin'])
def test_binding_admission_and_order_are_independently_retained(le_trace, fault):
    o = le_trace; document = deepcopy(o.document)
    if fault == 'binding-hash': document['mapping']['protected_source_binding_artifact']['sha256'] = 'f'*64
    elif fault == 'admission-hash':
        value = deepcopy(o.binding_document); value['admission']['sha256'] = 'f'*64
        replace_artifact(o.project, o.binding['artifact'], value)
    elif fault in ('binding-order', 'admission-order'):
        name = 'dos-source-bind' if fault == 'binding-order' else 'dos-source-admission'
        with o.project.transaction(True):
            o.project.db.execute('UPDATE debug_events SET sequence=sequence+10000 WHERE operation=?', (name,))
    elif fault == 'binding-recipe': document['mapping']['protected_source_binding']['binding_id'] = 'forged'
    elif fault == 'gdt-material': document['mapping']['protected_source_binding_material']['gdt_hex'] = '00'
    elif fault == 'source-pin': document['mapping']['protected_source_binding']['source_sha256'] = 'f'*64
    replace_artifact(o.project, o.trace['artifact'], document)
    with pytest.raises(ValueError):
        o.project.event_search_start(o.trace['artifact'])


def test_embedded_search_site_schema_refuses_resealed_namespace_changes(le_trace):
    compiled = execution_events.normalize_trace(le_trace.document)
    state = execution_events.start_search(compiled)
    assert execution_events.validate_search(state) == state
    altered = deepcopy(state); altered['candidates'][0]['site']['space'] = 'project'
    payload = {key:value for key,value in altered.items() if key!='state_sha256'}
    altered['state_sha256'] = execution_events._hash(payload)
    with pytest.raises(ValueError, match='candidate site'):
        execution_events.validate_search(altered)


@pytest.mark.parametrize('le_trace', [dict(offsets=(0, 5))], indirect=True)
def test_whole_relocated_operand_uses_canonical_source_identity(le_trace):
    o = le_trace
    _, compiled = event_search._trace(o.project, o.trace['artifact'])
    first = compiled['events'][0]
    assert first['mnemonic'] == 'mov' and first['size'] == 5
    assert first['site']['address'] == 0
    assert first['instruction_sha256'] != first['site']['instruction_sha256']
    event = deepcopy(o.document['events'][0])
    assert event['execution_bytes'] == 'b800000700'
    document = deepcopy(o.document)
    document['events'][0]['execution_bytes'] = document['events'][0]['bytes'] = 'b801000700'
    replace_artifact(o.project, o.trace['artifact'], document)
    with pytest.raises(ValueError):
        o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='mov'))


@pytest.mark.parametrize('le_trace', [dict(epoch='source-run:process:2')], indirect=True)
def test_fresh_restore_epoch_binding_and_prior_trace_remain_historical(le_trace):
    o = le_trace
    assert o.recipe['capture_epoch'] == 'source-run:process:2'
    before = o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push'))
    row = o.project.db.execute('SELECT metadata FROM debug_runs WHERE id=?', (o.session.run_id,)).fetchone()
    current = json.loads(row[0])
    current['checkpoint_restore'] = dict(artifact='later-checkpoint', sha256='e'*64)
    current['process'].update(capture_epoch='source-run:process:3', state='exited', machine_closed=True)
    current['process']['source_mapping']['live'] = False
    with o.project.transaction(True):
        o.project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?',
                             (json.dumps(current), o.session.run_id))
    assert o.project.event_trace_query(o.trace['artifact'],
        predicate=dict(kind='mnemonic', equals='push')) == before


def test_terminal_mode_boundary_is_queryable_without_source_site(le_trace):
    o = le_trace; document = deepcopy(o.document); event = document['events'][-1]
    event.update(address='0x20000', segmented_address=dict(space='segmented', segment='0x2000', offset='0x0'),
        cpu_mode='real', code_bits=16, bytes='', execution_bytes='',
        registers=dict(cs='0x2000', eip='0x0', eax='0x2', eflags='0x2'),
        address_context=dict(cpu_mode='real', code_bits=16, paging_enabled=False, a20=True,
            cr0=0, cs=dict(selector=0x2000, base=0x20000, limit=65535, attributes=0x9300)))
    event['identity'].update(runtime_address=event['segmented_address'], source_location=None,
                             source_instruction_sha256=None, context=None)
    event['source_qualification'] = dict(qualified=False, reason='mode-changed')
    event.pop('le_source_witness')
    document.update(complete=False, window=dict(closed=False, reason='source_boundary'))
    replace_artifact(o.project, o.trace['artifact'], document)
    _, compiled = event_search._trace(o.project, o.trace['artifact'])
    assert compiled['events'][-1]['site'] is None and not compiled['window']['closed']
    assert o.project.event_trace_query(o.trace['artifact'],
        predicate=dict(kind='pc-range', space='linear', start=0x20000, end=0x20001))['matched_count'] == 1
    with pytest.raises(ValueError, match='closed'):
        o.project.event_search_start(o.trace['artifact'])
    document['events'].append(deepcopy(o.document['events'][-1]))
    document['events'][-1]['sequence'] = 3
    replace_artifact(o.project, o.trace['artifact'], document)
    with pytest.raises(ValueError, match='continued'):
        o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push'))
