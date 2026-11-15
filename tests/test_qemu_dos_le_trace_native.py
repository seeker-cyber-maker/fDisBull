"""Real authored MZ-loader/LE execution and source traces on retained QEMU."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from fdisbull.project import Project
from fdisbull.le import load_runtime_le_carrier
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.qemu_dos_le_fixture import build_fixture
from test_qemu_dos_process_native import launch_options, process_record, process_runtime


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exported(project, artifact, destination):
    project.debug_export(artifact, destination)
    return destination.read_bytes(), json.loads(destination.read_bytes())


def test_authored_carrier_structure_assembles_without_native_execution(tmp_path):
    nasm = os.environ.get('NASM') or shutil.which('nasm')
    if nasm is None:
        pytest.skip('Supply NASM for the authored carrier structure check')
    fixture = build_fixture(tmp_path, nasm)
    image = load_runtime_le_carrier(fixture['path'].read_bytes())
    assert fixture['bootstrap_size']<=448 and fixture['size']<0x7000
    assert image.metadata['le']['carrier']['kind']=='mz-bw-mz-le'
    assert len(image.metadata['le']['fixups'])==9
    assert [(o['bits'],o['executable']) for o in image.metadata['le']['objects']]==[(32,True),(32,False)]
    assert image.metadata['le']['application_source_sha256'] != fixture['sha256']


@pytest.mark.parametrize('profile', ['standard', 'virtual'])
def test_native_loader_le_binding_traces_and_cold_readback(tmp_path, process_runtime, profile):
    runtime = process_runtime
    fixture = build_fixture(tmp_path, runtime['nasm'])
    originals = {str(path):digest(path) for path in
                 (fixture['path'], runtime['executable'], runtime['boot_image'])}
    disk = prepare_dos_baseline(runtime['boot_image'], tmp_path/'le-baseline.img', runtime['mcopy'],
                               config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    database = tmp_path/'le-native.fdb'
    with Project.create(database, fixture['path']) as project:
        assert project.meta['format']=='MZ'
        options = launch_options(runtime, disk)
        if profile=='virtual':
            options['qemu_clock']='virtual'
        with project.debugger(runtime['executable'], tmp_path, **options) as debug:
            active = process_record(debug)
            initial_mapping = deepcopy(active['source_mapping'])
            point = debug.breakpoint(fixture['code_base'])
            stopped = debug.run(timeout_ms=10000)
            assert stopped['outcome']=='breakpoint', stopped
            registers = debug.registers()
            assert registers['cpu_mode']=='protected' and registers['address_state']['code_bits']==32
            assert int(registers['linear_pc'],0)==fixture['code_base']
            debug.delete_breakpoint(point['breakpoint_id'])
            bound = debug.dos_source_bind(expected_source_sha256=fixture['sha256'])
            assert bound['live'] and bound['source_view']=='embedded-le'
            assert debug.dos_process_info()['source_mapping']==initial_mapping
            counted = debug.trace('le-count.json', count=4, bits=32, timeout_ms=10000)
            assert counted['metadata']['complete']
            _, count_doc = exported(project, counted['artifact'], tmp_path/'le-count-warm.json')
            assert len(count_doc['events'])==4 and count_doc['window']['closed']
            first = count_doc['events'][0]
            assert first['execution_bytes']=='b800001300'
            assert first['project_address'] is None and first['identity']['source_location']['object_offset']==0
            assert first['identity']['source_instruction_sha256'] != hashlib.sha256(bytes.fromhex(first['execution_bytes'])).hexdigest()
            if profile=='virtual':
                assert all('clock' in event for event in count_doc['events'])
            matched = debug.trace_until(dict(kind='register',register='eax',equals=3), max_steps=100,
                                         timeout_ms=15000,name='le-match.json')
            assert matched['matched'] and matched['exact_stop'] and matched['source_window_closed'], matched
            assert int(debug.registers()['linear_pc'],0)==fixture['code_base']+fixture['store_offset']
            assert debug.memory(fixture['counter_address'],length=4,space='physical')['hex']=='02000000'
            before_exit = debug.trace_until(dict(kind='mnemonic',equals='jmp'), max_steps=10,
                                            timeout_ms=10000,name='le-jump.json')
            assert before_exit['matched'] and before_exit['exact_stop'], before_exit
            boundary = debug.trace_until(dict(kind='register',register='eax',equals=99), max_steps=4,
                                         timeout_ms=10000,name='le-boundary.json')
            assert boundary['outcome']=='source_boundary' and not boundary['matched']
            assert not boundary['source_window_closed']
            assert int(debug.registers()['linear_pc'],0)==fixture['outside_base']
            assert debug.dos_process_info()['source_mapping']==initial_mapping
            query = project.event_trace_query(counted['artifact'],predicate=dict(kind='mnemonic',equals='mov'))
            assert query['matched_count']==1
            search = project.event_search_start(counted['artifact'])
            search_saved = project.event_search_results(search['artifact'])
            assert search_saved['candidate_count']==4
            match_bytes, match_doc = exported(project, matched['trace_artifact'],tmp_path/'le-match-warm.json')
            count_bytes = (tmp_path/'le-count-warm.json').read_bytes()
        assert debug.closed and debug.vm.process.poll() is not None
    with Project(database) as cold:
        cold.debug_export(counted['artifact'],tmp_path/'le-count-cold.json')
        cold.debug_export(matched['trace_artifact'],tmp_path/'le-match-cold.json')
        assert (tmp_path/'le-count-cold.json').read_bytes()==count_bytes
        assert (tmp_path/'le-match-cold.json').read_bytes()==match_bytes
        assert cold.event_search_results(search['artifact'])==search_saved
        assert cold.event_trace_query(counted['artifact'],predicate=dict(kind='mnemonic',equals='mov'))==query
        assert cold.event_trace_query(boundary['trace_artifact'],predicate=dict(kind='pc-range',space='linear',
            start=fixture['outside_base'],end=fixture['outside_base']+1))['matched_count']==1
    assert {path:digest(path) for path in originals}==originals


@pytest.mark.parametrize('profile', ['standard', 'virtual'])
def test_native_owned_restore_fresh_le_rebind_and_cold_traces(tmp_path, process_runtime, profile):
    """Fresh stopped source admission after native recovery, never MZ authority.

    All changed RAM is written by the authored LE program. The saved archive
    remains an ordinary machine-state; neither a saved handle nor its old
    binding/owner identity is installed by the opt-in re-admission.
    """
    runtime = process_runtime
    tool = os.environ.get('FDISBULL_QEMU_IMG')
    if not tool:
        if any(os.environ.get(name) == '1' for name in
               ('FDISBULL_REQUIRE_QEMU_DOS', 'FDISBULL_REQUIRE_QEMU_DOS_OS', 'FDISBULL_REQUIRE_QEMU_LAYERS')):
            pytest.fail('FDISBULL_QEMU_IMG is required for authored LE machine recovery')
        pytest.skip('Supply FDISBULL_QEMU_IMG for authored LE machine recovery')
    tool = Path(tool).expanduser().resolve(strict=True)
    assert tool.is_file() and os.access(tool, os.X_OK)
    fixture = build_fixture(tmp_path, runtime['nasm'])
    originals = {str(path):digest(path) for path in
                 (fixture['path'], runtime['executable'], runtime['boot_image'], tool)}
    disk = prepare_dos_baseline(runtime['boot_image'], tmp_path/'le-recovery-baseline.img', runtime['mcopy'],
                               config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    options = launch_options(runtime, disk, qemu_checkpoint_tool=str(tool),
                             qemu_clock=profile)
    database = tmp_path/'le-owned-rebind.fdb'

    def canonical(events):
        return [dict(location=event['identity']['source_location'],
                     instruction_sha256=event['identity']['source_instruction_sha256'],
                     context=event['identity']['context'],
                     execution_bytes=event['execution_bytes']) for event in events]

    def assert_rebound(debug, restored, old_owner, previous_epoch, previous_binding, saved_cpu, saved_site):
        assert old_owner.poll() is not None and debug.vm.process is not old_owner
        assert debug.vm.process.poll() is None and not debug.closed
        assert restored['machine_state_restored'] is True
        assert restored['source_binding_restored'] is False
        assert restored['protected_source_rebound'] is True
        assert 'fresh stopped LE admission' in restored['source_revalidation_scope']
        summary = debug.dos_source_binding()
        assert summary == restored['protected_source_binding']
        assert summary['state'] == 'qualified-stopped' and summary['live'] is True
        assert summary['source_view'] == 'embedded-le'
        assert summary['binding_id'] != previous_binding
        assert summary['capture_epoch'] == restored['capture_epoch'] != previous_epoch
        assert summary['last_observation']['qualified'] is True
        for field in ('source_location', 'instruction_sha256', 'linear_pc'):
            assert summary['last_observation'][field] == saved_site[field]
        current = debug.registers()
        for field in ('registers', 'instruction_pointer', 'cpu_mode', 'address_state'):
            assert current[field] == saved_cpu[field]
        assert debug.memory(fixture['counter_address'], length=4, space='physical')['hex'] == '00000000'
        mapping = debug.dos_process_info()['source_mapping']
        assert mapping['live'] is False and mapping['live_ranges'] == []
        # A fresh LE relation never satisfies the stronger COM/MZ save gate.
        with pytest.raises(ValueError, match='retired the DOS source binding'):
            debug.save_state('le-is-not-mz-authority.qcow2')
        assert debug.dos_source_binding()['binding_id'] == summary['binding_id']
        assert debug.vm.process.poll() is None
        return summary

    with Project.create(database, fixture['path']) as project:
        with project.debugger(runtime['executable'], tmp_path, **options) as debug:
            entry = process_record(debug)
            initial_mapping = deepcopy(entry['source_mapping'])
            point = debug.breakpoint(fixture['code_base'])
            reached = debug.run(timeout_ms=10000)
            assert reached['outcome'] == 'breakpoint', reached
            debug.delete_breakpoint(point['breakpoint_id'])
            bound = debug.dos_source_bind(expected_source_sha256=fixture['sha256'])
            assert bound['live'] and bound['last_observation']['qualified']
            saved_site = deepcopy(bound['last_observation'])
            saved_cpu = debug.registers()
            saved_epoch = bound['capture_epoch']
            original_binding = bound['binding_id']
            owner = debug.vm.process
            saved = debug.save_machine_state('le-native-machine.qcow2')
            assert saved['metadata']['format'] == 'fdisbull-qemu-owned-machine-qcow2-v1'
            assert saved['metadata']['source_binding_restored'] is False
            assert debug.dos_process_info()['source_mapping'] == initial_mapping
            assert debug.dos_source_binding()['binding_id'] == original_binding

            old_trace = debug.trace('le-before-machine-restore.json', count=4, bits=32,
                                    source_view='embedded-le', timeout_ms=10000)
            old_bytes, old_document = exported(project, old_trace['artifact'], tmp_path/'le-before-warm.json')
            assert old_trace['metadata']['complete'] and old_document['window']['closed']
            assert len(old_document['events']) == 4
            assert all(event['mapping_id'] == original_binding for event in old_document['events'])
            expected_sites = canonical(old_document['events'])
            advanced = debug.trace_until(dict(kind='register', register='eax', equals=3), max_steps=100,
                source_view='embedded-le', timeout_ms=15000, name='le-changed-before-recovery.json')
            assert advanced['matched'] and advanced['exact_stop'] and advanced['source_window_closed'], advanced
            assert debug.memory(fixture['counter_address'], length=4, space='physical')['hex'] == '02000000'
            assert debug.registers()['registers'] != saved_cpu['registers']
            restored = debug.load_machine_state(saved['artifact'], timeout_ms=60000,
                                                rebind_protected_source=True)
            fresh = assert_rebound(debug, restored, owner, saved_epoch, original_binding, saved_cpu, saved_site)
            fresh_binding = fresh['binding_id']
            fresh_trace = debug.trace('le-after-machine-restore.json', count=4, bits=32,
                                      source_view='embedded-le', timeout_ms=10000)
            fresh_bytes, fresh_document = exported(project, fresh_trace['artifact'], tmp_path/'le-after-warm.json')
            assert fresh_trace['metadata']['complete'] and fresh_document['window']['closed']
            assert canonical(fresh_document['events']) == expected_sites
            assert all(event['mapping_id'] == fresh_binding for event in fresh_document['events'])
            if profile == 'virtual':
                assert all('clock' in event for document in (old_document, fresh_document)
                           for event in document['events'])
            old_query = project.event_trace_query(old_trace['artifact'], predicate=dict(kind='mnemonic', equals='mov'))
            fresh_query = project.event_trace_query(fresh_trace['artifact'], predicate=dict(kind='mnemonic', equals='mov'))
            assert old_query['matched_count'] == fresh_query['matched_count'] == 1

            # The same archive's default restore remains strictly machine-only.
            before_default = debug.vm.process
            default = debug.load_machine_state(saved['artifact'], timeout_ms=60000)
            assert before_default.poll() is not None
            assert default['machine_state_restored'] is True and default['source_binding_restored'] is False
            assert default['protected_source_rebound'] is False
            assert not debug.dos_source_binding()['live']
            assert debug.dos_process_info()['source_mapping']['live_ranges'] == []
            hot_run = debug.run_id
            hot_epoch = debug.dos_process_info()['capture_epoch']
            final_owner = debug.vm.process
        assert final_owner.poll() is not None

    with Project(database) as cold:
        cold.debug_export(old_trace['artifact'], tmp_path/'le-before-cold.json')
        cold.debug_export(fresh_trace['artifact'], tmp_path/'le-after-cold.json')
        assert (tmp_path/'le-before-cold.json').read_bytes() == old_bytes
        assert (tmp_path/'le-after-cold.json').read_bytes() == fresh_bytes
        assert cold.event_trace_query(old_trace['artifact'], predicate=dict(kind='mnemonic', equals='mov')) == old_query
        assert cold.event_trace_query(fresh_trace['artifact'], predicate=dict(kind='mnemonic', equals='mov')) == fresh_query
        state_info = cold.debug_state_info(saved['artifact'])
        assert state_info['sha256'] == saved['sha256']
        assert state_info['metadata']['source_binding_restored'] is False
        with cold.debugger(runtime['executable'], tmp_path, **options) as debug:
            assert debug.run_id != hot_run
            initial_owner = debug.vm.process
            initial_epoch = debug.dos_process_info()['capture_epoch']
            restored = debug.load_machine_state(saved['artifact'], timeout_ms=60000,
                                                rebind_protected_source=True)
            cold_bound = assert_rebound(debug, restored, initial_owner, initial_epoch, fresh_binding,
                                        saved_cpu, saved_site)
            assert cold_bound['binding_id'] != original_binding
            assert cold_bound['capture_epoch'] != hot_epoch
            cold_trace = debug.trace('le-after-cold-machine-restore.json', count=4, bits=32,
                                     source_view='embedded-le', timeout_ms=10000)
            _, cold_document = exported(cold, cold_trace['artifact'], tmp_path/'le-cold-restored-trace.json')
            assert cold_trace['metadata']['complete'] and cold_document['window']['closed']
            assert canonical(cold_document['events']) == expected_sites
            assert all(event['mapping_id'] == cold_bound['binding_id'] for event in cold_document['events'])
            assert cold.event_trace_query(cold_trace['artifact'],
                predicate=dict(kind='mnemonic', equals='mov'))['matched_count'] == 1
            cold_owner = debug.vm.process
        assert cold_owner.poll() is not None
    assert digest(disk['image']) == disk['prepared_sha256']
    assert {path:digest(path) for path in originals} == originals
