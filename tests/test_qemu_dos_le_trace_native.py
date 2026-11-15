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
