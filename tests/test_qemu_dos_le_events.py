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


def owned_restore(project, run, launch, epoch):
    """Author the durable manifest/receipt boundary, not a native VM payload."""
    current = deepcopy(launch)
    state = project._debug_artifact(run, 'owned-machine.qcow2', 'machine-state',
        b'authored opaque machine checkpoint', dict(
            format='fdisbull-qemu-owned-machine-qcow2-v1',
            source_sha256=project.meta['source_sha256'],
            version_sha256=project.version(1)['sha256'], origin_run=run,
            sidecar_sha256='c'*64, source_binding_restored=False,
            checkpoint_scope='owned native machine and private disk; no DOS/LE source ownership',
            host_files_restored=False))
    current['process']['capture_epoch'] = epoch
    current['process']['source_mapping'].update(live=False, live_ranges=[],
        status='unqualified-after-owned-machine-restore', current_bytes='not source-qualified')
    current['owned_machine_restore'] = dict(artifact=state['artifact'], sha256=state['sha256'],
        origin_run=run, source_binding_restored=False, runtime_origin=deepcopy(launch['runtime_inputs']))
    result = dict(artifact=state['artifact'], sha256=state['sha256'], origin_run=run,
        machine_state_restored=True, source_binding_restored=False, host_files_restored=False,
        capture_epoch=epoch, checkpoint_epoch=int(epoch.rsplit(':', 1)[1]),
        process=deepcopy(current['process']))
    if launch['machine_configuration'].get('clock_profile', {}).get('profile') == 'virtual':
        result['instrumentation'] = dict(format='fdisbull-instrumented-qemu-state-1',
            source_epoch=launch['machine_configuration']['native_clock_admission']['epoch'],
            native_epoch=2, virtual_ns=5000, windows={}, host_clock_sync_restored=False)
    return current, result


@pytest.fixture
def le_trace(owned, request):
    s, p = owned.session, owned.project
    options = getattr(request, 'param', {})
    launch = metadata(p, run=s.run_id)
    launch['machine_configuration'] = dict(cpus=1, memory_mib=16)
    if options.get('virtual'):
        from fdisbull.qemu_clock import machine_clock_configuration
        launch['machine_configuration'].update(clock_profile=machine_clock_configuration('virtual', 1),
            native_clock_admission={'api-version':1, 'budget-state':'idle', 'budget-supported':True,
                'epoch':1, 'pending-stop':False, 'running':False, 'status':'prelaunch', 'virtual-ns':0})
    s.metadata, s._process = deepcopy(launch), deepcopy(launch['process'])
    s._runtime_epoch = options.get('epoch', launch['process']['capture_epoch'])
    s._process['capture_epoch'] = s._runtime_epoch
    with p.transaction(True):
        p.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?', (json.dumps(launch), s.run_id))
        receipt(p, s.run_id, launch['process'])
    restored = None
    if options.get('owned_restore'):
        launch, restored = owned_restore(p, s.run_id, launch, s._runtime_epoch)
        s.metadata, s._process = deepcopy(launch), deepcopy(launch['process'])
        with p.transaction(True):
            p.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?', (json.dumps(launch), s.run_id))
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
    if restored is not None:
        operation(p, s.run_id, 'load-machine-state', restored)
    mapping = deepcopy(launch)
    if restored is not None and options.get('virtual'):
        mapping['machine_configuration']['native_clock_admission'].update(
            epoch=restored['instrumentation']['native_epoch'],
            **{'virtual-ns':restored['instrumentation']['virtual_ns']})
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
        if options.get('virtual'):
            from test_execution_clock import clock
            admitted = mapping['machine_configuration']['native_clock_admission']
            events[-1]['clock'] = clock(run=s.run_id, epoch='e'*32, native_epoch=admitted['epoch'],
                ns=admitted['virtual-ns']+128*sequence, icount=sequence, sequence=sequence*2-1)
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


@pytest.mark.parametrize('le_trace', [dict(epoch='source-run:process:2', owned_restore=True),
    dict(epoch='source-run:process:2', owned_restore=True, virtual=True)], indirect=True)
def test_fresh_owned_restore_binding_keeps_cold_source_identity(le_trace, tmp_path):
    o = le_trace
    query = o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push'))
    assert query['matched_count'] == 2
    search = o.project.event_search_start(o.trace['artifact'])
    retained = o.project.event_search_results(search['artifact'])
    o.project.debug_export(o.trace['artifact'], tmp_path/'before.json')
    database = o.project.path
    o.project.__exit__(None, None, None)
    with Project(database) as cold:
        assert cold.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push')) == query
        assert cold.event_search_results(search['artifact']) == retained
        cold.debug_export(o.trace['artifact'], tmp_path/'after.json')
        assert (tmp_path/'before.json').read_bytes() == (tmp_path/'after.json').read_bytes()


@pytest.mark.parametrize('le_trace', [{}, dict(virtual=True)], indirect=True)
def test_prior_le_trace_survives_actual_owned_restore_metadata(le_trace):
    o = le_trace
    query = o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push'))
    current = json.loads(o.project.db.execute('SELECT metadata FROM debug_runs WHERE id=?',
                                            (o.session.run_id,)).fetchone()[0])
    # Reusing one archive in two successful loads is valid. Select by epoch,
    # rather than requiring a unique operation for an artifact forever.
    current, restored = owned_restore(o.project, o.session.run_id, current, 'source-run:process:2')
    operation(o.project, o.session.run_id, 'load-machine-state', restored)
    restored['capture_epoch'] = 'source-run:process:3'
    restored['checkpoint_epoch'] += 1
    restored['process']['capture_epoch'] = restored['capture_epoch']
    operation(o.project, o.session.run_id, 'load-machine-state', restored)
    current['process'].update(capture_epoch='source-run:process:4', state='exited', machine_closed=True)
    current['process']['source_mapping'].update(status='invalidated-on-machine-close')
    with o.project.transaction(True):
        o.project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?',
                            (json.dumps(current), o.session.run_id))
    assert o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push')) == query


@pytest.mark.parametrize('le_trace', [dict(epoch='source-run:process:2', owned_restore=True)], indirect=True)
@pytest.mark.parametrize('fault', ['missing-load', 'load-source-authority', 'load-epoch', 'late-load',
    'load-allocation', 'marker-extra', 'marker-hash', 'marker-origin', 'manifest-source',
    'state-kind', 'state-creation', 'current-bytes', 'allocation', 'process-disk'])
def test_owned_restore_exemption_requires_exact_lifecycle_and_immutable_launch(le_trace, fault):
    o = le_trace
    document = deepcopy(o.document)
    marker = document['mapping']['owned_machine_restore']
    load = o.project.db.execute("SELECT sequence,evidence FROM debug_events WHERE operation='load-machine-state'").fetchone()
    result = json.loads(load['evidence'])
    with o.project.transaction(True):
        if fault == 'missing-load':
            o.project.db.execute('DELETE FROM debug_events WHERE sequence=?', (load['sequence'],))
        elif fault in ('load-source-authority', 'load-epoch', 'load-allocation', 'late-load'):
            if fault == 'load-source-authority': result['source_binding_restored'] = True
            elif fault == 'load-epoch': result['capture_epoch'] = 'source-run:process:99'
            elif fault == 'load-allocation': result['process']['allocation']['owner_psp'] += 1
            else:
                o.project.db.execute('UPDATE debug_events SET sequence=sequence+1000 WHERE sequence=?', (load['sequence'],))
            o.project.db.execute('UPDATE debug_events SET evidence=? WHERE sequence=?',
                (json.dumps(result), load['sequence'] + (1000 if fault == 'late-load' else 0)))
        elif fault == 'manifest-source':
            row = o.project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?', (marker['artifact'],)).fetchone()
            manifest = json.loads(row[0]); manifest['source_sha256'] = 'f'*64
            o.project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',
                                (json.dumps(manifest), marker['artifact']))
        elif fault == 'state-kind':
            o.project.db.execute("UPDATE debug_artifacts SET kind='state' WHERE id=?", (marker['artifact'],))
        elif fault == 'state-creation':
            rows = o.project.db.execute("SELECT sequence,evidence FROM debug_events WHERE operation='artifact'").fetchall()
            for row in rows:
                value = json.loads(row['evidence'])
                if value['artifact'] == marker['artifact']:
                    value['sha256'] = 'f'*64
                    o.project.db.execute('UPDATE debug_events SET evidence=? WHERE sequence=?',
                                        (json.dumps(value), row['sequence']))
        elif fault == 'marker-extra': marker['invented_authority'] = True
        elif fault == 'marker-hash': marker['sha256'] = 'f'*64
        elif fault == 'marker-origin': marker['origin_run'] = 'foreign-run'
        elif fault == 'current-bytes': document['mapping']['process']['source_mapping']['current_bytes'] = 'anything'
        elif fault == 'allocation': document['mapping']['process']['allocation']['owner_psp'] += 1
        else: document['mapping']['process_disk']['prepared_boot_image']['sha256'] = 'f'*64
    replace_artifact(o.project, o.trace['artifact'], document)
    with pytest.raises(ValueError):
        o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push'))


@pytest.mark.parametrize('le_trace', [dict(epoch='source-run:process:2', owned_restore=True, virtual=True)], indirect=True)
@pytest.mark.parametrize('fault', ['admission-epoch', 'admission-time', 'native-capability', 'missing-proof',
    'proof-epoch', 'proof-time', 'proof-source-epoch', 'proof-format', 'proof-format-type',
    'clock-before-restore', 'cpus', 'profile', 'other-config'])
def test_restored_le_clock_requires_exact_load_proof_and_immutable_configuration(le_trace, fault):
    from fdisbull.qemu_clock import machine_clock_configuration
    o = le_trace
    document = deepcopy(o.document)
    config = document['mapping']['machine_configuration']
    if fault == 'admission-epoch': config['native_clock_admission']['epoch'] = 3
    elif fault == 'admission-time': config['native_clock_admission']['virtual-ns'] += 1
    elif fault == 'native-capability': config['native_clock_admission']['budget-supported'] = False
    elif fault == 'clock-before-restore':
        from test_execution_clock import clock
        document['events'][0]['clock'] = clock(run=o.session.run_id, epoch='e'*32,
            native_epoch=2, ns=4999, icount=1, sequence=1)
    elif fault == 'cpus': config['cpus'] = 2
    elif fault == 'profile': config['clock_profile'] = machine_clock_configuration('instruction', 1)
    elif fault == 'other-config': config['memory_mib'] += 1
    else:
        row = o.project.db.execute("SELECT sequence,evidence FROM debug_events WHERE operation='load-machine-state'").fetchone()
        result = json.loads(row['evidence'])
        if fault == 'missing-proof': del result['instrumentation']
        elif fault == 'proof-epoch': result['instrumentation']['native_epoch'] = 3
        elif fault == 'proof-time': result['instrumentation']['virtual_ns'] += 1
        elif fault == 'proof-format': result['instrumentation']['format'] = 'fdisbull-instrumented-qemu-state-999'
        elif fault == 'proof-format-type': result['instrumentation']['format'] = []
        else: result['instrumentation']['source_epoch'] = True
        with o.project.transaction(True):
            o.project.db.execute('UPDATE debug_events SET evidence=? WHERE sequence=?',
                                (json.dumps(result), row['sequence']))
    replace_artifact(o.project, o.trace['artifact'], document)
    with pytest.raises(ValueError):
        o.project.event_trace_query(o.trace['artifact'], predicate=dict(kind='mnemonic', equals='push'))


@pytest.mark.parametrize('le_trace', [dict(epoch='source-run:process:2', owned_restore=True, virtual=True)], indirect=True)
@pytest.mark.parametrize('format_version', [1, 3, 4])
def test_restored_le_clock_accepts_valid_stopped_budget_receipt(le_trace, format_version):
    o = le_trace
    row = o.project.db.execute("SELECT sequence,evidence FROM debug_events WHERE operation='load-machine-state'").fetchone()
    result = json.loads(row['evidence'])
    result['instrumentation']['format'] = f'fdisbull-instrumented-qemu-state-{format_version}'
    with o.project.transaction(True):
        o.project.db.execute('UPDATE debug_events SET evidence=? WHERE sequence=?',
                            (json.dumps(result), row['sequence']))
    document = deepcopy(o.document)
    document['mapping']['machine_configuration']['native_clock_admission'].update({
        'budget-state':'cancelled', 'budget-token':'authored-completed-budget',
        'budget-start-ns':100, 'budget-deadline-ns':10000,
        'budget-fired-ns':None, 'budget-stopped-ns':5000, 'status':'paused'})
    replace_artifact(o.project, o.trace['artifact'], document)
    assert o.project.event_trace_query(o.trace['artifact'],
        predicate=dict(kind='mnemonic', equals='push'))['matched_count'] == 2


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
