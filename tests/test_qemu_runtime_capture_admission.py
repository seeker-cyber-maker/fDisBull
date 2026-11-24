"""Host checks for bounded QEMU source capture admission."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from fdisbull.qemu_runtime_capture import qualify_qemu_source_capture, validate_qemu_source_capture


@pytest.fixture
def capture(monkeypatch):
    monkeypatch.setattr('fdisbull.qemu_dos_trace._ownership', lambda session, binding: None)
    mapping = dict(status='initial-load-verified', live=True, source_sha256='source',
                   expected_module_sha256='module', observed_module_sha256='module',
                   static_base=0x10000, runtime_base=0x20000, delta=0x10000,
                   module_size=0x100, load_segment=0x2000,
                   live_ranges=[dict(project_address=0x10000, runtime_address=0x20000, length=0x100)])
    state = dict(cpu_mode='real', code_bits=16, paging=False,
                 register_context_match=True, machine_vcpus=1)
    project = SimpleNamespace(meta=dict(format='MZ', source_sha256='source'), arch='x86', bits=16,
                              debug_layer_info=lambda i: {'sha256': 'layer'})
    session = SimpleNamespace(project=project, run_id='run', version=dict(id=1, sha256='version'),
        _runtime_epoch='run:process:1', _process=dict(state='active', source_mapping=mapping,
            capture_epoch='run:process:1', psp_segment=0x1ff0),
        metadata=dict(backend='qemu-dos', runtime_profile='dos-exec-load-only-v1',
            source_sha256='source', version_sha256='version', runtime_inputs={'qemu_image': {'sha256': 'native'},
            'firmware': {'sha256': 'firmware', 'files': [{'name': 'bios', 'sha256': 'bios'}]},
            'boot_image': {'sha256': 'boot'}}),
        registers=lambda: dict(cpu_mode='real', address_state=state))
    # MZ entry CS is two paragraphs beyond the image load segment.
    observed = dict(space='source', project_address='0x10020', runtime_address='0x20020',
        length=3, backing=[dict(physical_address='0x20020', length=3)],
        project_cs='0x1002', runtime_cs='0x2002', instruction_pointer='0x0',
        active_layers=['overlay'], view='execute', hex='b80100', sha256='unused', generation=1)
    session.metadata['process'] = deepcopy(session._process)
    return session, observed


def test_relative_mz_selector_and_nested_input_identities(capture):
    session, observed = capture
    result = qualify_qemu_source_capture(session, observed)
    assert result['identity']['project_cs'] == 0x1002
    assert result['identity']['runtime_cs'] == 0x2002
    assert result['identity']['backend_sha256'] == 'native'
    assert result['identity']['runtime_inputs']['firmware'] == 'firmware'
    assert result['identity']['runtime_inputs']['boot_image'] == 'boot'
    session.metadata['runtime_inputs']['firmware']['files'][0]['sha256'] = 'changed'
    assert result['identity']['runtime_inputs']['firmware'] == 'firmware'


@pytest.mark.parametrize('change', ['backing', 'cpu', 'epoch', 'producer', 'mapping', 'inputs', 'selector'])
def test_offline_rejects_inconsistent_persisted_facts(capture, change):
    session, observed = capture
    result = qualify_qemu_source_capture(session, observed)
    if change == 'backing': result['backing'][0]['physical_address'] = '0x30020'
    elif change == 'cpu': result['capture_registers']['address_state']['cpu_mode'] = 'protected'
    elif change == 'epoch': result['identity']['process_epoch'] = 'other:process:1'
    elif change == 'producer': result['identity']['backend_sha256'] = 'other'
    elif change == 'mapping': result['identity']['source_mapping']['module_size'] += 1
    elif change == 'inputs': result['identity']['runtime_inputs']['firmware'] = 'other'
    elif change == 'selector': result['runtime_cs'] = '0x2003'
    with pytest.raises(ValueError, match='QEMU capture'):
        validate_qemu_source_capture(result, session.metadata)


def test_offline_does_not_require_final_live_epoch(capture):
    session, observed = capture
    result = qualify_qemu_source_capture(session, observed)
    session.metadata['process']['capture_epoch'] = 'run:process:9'
    session.metadata['process']['state'] = 'exited'
    session.metadata['process']['source_mapping']['live'] = False
    session.metadata['process']['source_mapping']['live_ranges'] = []
    validate_qemu_source_capture(result, session.metadata)


@pytest.mark.parametrize('change', ['stale', 'unbound', 'wrong_source', 'split_extent',
                                   'remapped', 'bad_selector', 'malformed', 'task', 'protected'])
def test_unqualified_receipts_remain_opaque(capture, change):
    session, observed = capture
    mapping = session._process['source_mapping']
    if change == 'stale': session._process['capture_epoch'] = 'old'
    elif change == 'unbound': session._process = None
    elif change == 'wrong_source': mapping['source_sha256'] = 'other'
    elif change == 'split_extent': mapping['live_ranges'].append(deepcopy(mapping['live_ranges'][0]))
    elif change == 'remapped': observed['backing'][0]['physical_address'] = '0x30020'
    elif change == 'bad_selector': observed['runtime_cs'] = '0x2003'
    elif change == 'malformed': del observed['backing']
    elif change == 'task': session._dos_task_binding = {'id': 'private'}
    elif change == 'protected': session.registers = lambda: dict(cpu_mode='protected', address_state={})
    assert qualify_qemu_source_capture(session, observed) is None


def test_changed_process_owner_remains_unqualified(capture, monkeypatch):
    def changed(*args):
        raise ValueError('DOS allocation ownership changed')
    monkeypatch.setattr('fdisbull.qemu_dos_trace._ownership', changed)
    assert qualify_qemu_source_capture(*capture) is None


@pytest.mark.parametrize('change', ['backing', 'cpu', 'epoch', 'producer', 'mapping', 'extended'])
def test_promotion_rejects_tamper_even_with_recomputed_artifact_hash(tmp_path, capture, change):
    from fdisbull.project import Project
    from test_dos_loader import mz_file
    session, observed = capture
    binary = tmp_path / 'sample.exe'
    binary.write_bytes(mz_file(bytes.fromhex('90') * 256, ss=0, sp=0x100))
    with Project.create(tmp_path / 'sample.fdb', binary) as project:
        session.project = project
        session.version = project.version()
        session._process['source_mapping']['source_sha256'] = project.meta['source_sha256']
        session.metadata['source_sha256'] = project.meta['source_sha256']
        session.metadata['version_sha256'] = session.version['sha256']
        session.metadata['process'] = deepcopy(session._process)
        observed.update(active_layers=[], hex='909090', sha256=hashlib.sha256(b'\x90'*3).hexdigest())
        result = qualify_qemu_source_capture(session, observed)
        if change == 'backing': result['backing'][0]['physical_address'] = '0x30020'
        elif change == 'cpu': result['capture_registers']['address_state']['cpu_mode'] = 'protected'
        elif change == 'epoch': result['identity']['process_epoch'] = 'other:process:1'
        elif change == 'producer': result['identity']['backend_sha256'] = 'other'
        elif change == 'mapping': result['identity']['source_mapping']['module_size'] += 1
        elif change == 'extended':
            result['hex'] += '90'
            result['sha256'] = hashlib.sha256(bytes.fromhex(result['hex'])).hexdigest()
        data = json.dumps(result).encode()
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                ('run', session.version['id'], 'now', None, 'stopped', json.dumps(session.metadata)))
            project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
                ('capture', 'run', 'code.json', 'qemu-code-snapshot', hashlib.sha256(data).hexdigest(), data, '{}'))
        with pytest.raises(ValueError, match='QEMU capture'):
            project.debug_promote_code('capture')
