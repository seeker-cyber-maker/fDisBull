"""Persisted selection-to-native bridge; source bytes are authored fixtures."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from fdisbull import udc_layers
from fdisbull.udc_layers import register_contract, register_layer, select_layers, build_selection_shell
from test_udc_shell import notification_frame


def setup(project, *, contract_domain=False, layer_domain=False, mapping=False, service='ui.notify'):
    program = {'format': 'fdisbull-il-1', 'role': 'uil',
               'variables': {name: {'type': 'u16', 'initial': 0}
                             for name in ('$left', '$right', '$sum', '$scratch')},
               'resources': {}, 'body': [
                   {'id': 'copy', 'op': 'set', 'var': '$sum', 'value': {'var': '$left'}},
                   {'id': 'add', 'op': 'add', 'var': '$sum', 'value': {'var': '$right'}}]}
    contract = {'format': 'fdisbull-block-contract-1', 'name': 'arithmetic.add',
                'inputs': {'left': 'u16', 'right': 'u16'}, 'outputs': {'sum': 'u16'},
                'behavior': {'kind': 'uil', 'program': program}}
    if contract_domain: contract['domain'] = {'left': {'min': 0, 'max': 20}}
    cid = register_contract(project, contract)['id']
    implementation = {'backend': 'uil', 'program': program, 'return': '$sum',
                      'inputs': {'left': '$left', 'right': '$right'}, 'outputs': {'sum': '$sum'}}
    if mapping: implementation['inputs'] = {'left': '$right', 'right': '$left'}
    layer = {'format': 'fdisbull-udl-layer-1', 'name': 'portable.add', 'contract': cid,
             'implementation': implementation}
    if layer_domain: layer['domain'] = {'right': {'min': 0, 'max': 10}}
    lid = register_layer(project, layer)['id']
    notification = register_contract(project, {'format': 'fdisbull-block-contract-1', 'name': 'presentation',
        'inputs': {'value': 'u16'}, 'outputs': {}, 'behavior': {'kind': 'service', 'service': service}})['id']
    provider = register_layer(project, {'format': 'fdisbull-udl-layer-1', 'name': 'notification',
        'contract': notification, 'implementation': {'backend': 'message-box-a', 'title': 'Selected UDC',
            'messages': {'1': 'won'}, 'default': 'lost', 'style': 64}})['id']
    selection = select_layers(project, 'native', {'math': lid, 'present': provider}, program=program)
    plan = {'format': 'fdisbull-native-shell-1', 'entry': 'main',
            'state': {'$left': {'type': 'u16', 'initial': 65535}, '$right': {'type': 'u16', 'initial': 2},
                      '$sum': {'type': 'u16', 'initial': 60000}},
            'resources': {'won': {'kind': 'text', 'text': 'Win'}, 'lost': {'kind': 'text', 'text': 'Lose'}},
            'functions': {'main': {'body': [{'op': 'call', 'binding': 'math'},
                {'op': 'notify', 'binding': 'present', 'value': {'var': '$sum'}}]}}}
    return selection, plan, cid, lid


def create(tmp_path):
    source = tmp_path / 'authored.bin'; source.write_bytes(b'\xc3' + bytes(31))
    return Project.create(tmp_path / 'authored.fdb', source, arch='x86', bits=16, base=0x1000)


def test_selected_build_after_restart_retains_ids_proofs_and_explicit_function_adapter(tmp_path):
    with create(tmp_path) as project:
        selection, plan, cid, lid = setup(project)
        original = project.meta['source_sha256']
    with Project(tmp_path / 'authored.fdb') as project:
        result = build_selection_shell(project, selection['id'], plan, tmp_path / 'native')
        assert result['selection'] == selection['id']
        assert result['layer_ids']['math'] == lid and result['contract_ids']['math'] == cid
        assert result['qualification']['math']['status'] == 'equivalent_under_contract'
        assert result['native_build_qualification']['native_execution'] is False
        assert project.meta['source_sha256'] == original and len(project.versions()) == 1
    capsule = json.loads((tmp_path / 'native/selection-capsule.json').read_text())
    assert capsule['complete'] and capsule['selection_sha256'] == selection['sha256']
    assert capsule['state_adapters']['math'] == {'inputs': ['$left', '$right'], 'outputs': ['$sum']}
    assert capsule['layers']['math']['id'] == lid and capsule['contracts'][cid]['id'] == cid
    assert capsule['native_build_capsule_sha256'] == hashlib.sha256((tmp_path / 'native/capsule.json').read_bytes()).hexdigest()
    native = json.loads((tmp_path / 'native/capsule.json').read_text())
    module = native['modules']['math']
    assert 'inputs' not in module and 'outputs' not in module
    assert module['state_adapter'] == capsule['state_adapters']['math']
    # An activation-local does not need a caller state cell or acquire one merely
    # because its spelling resembles a persistent global.
    assert '$scratch' in module['program']['variables'] and '$scratch' not in plan['state']


@pytest.mark.parametrize('option', ['contract_domain', 'layer_domain', 'mapping'])
def test_unrealized_domains_and_noncanonical_ports_refuse_before_output(tmp_path, option):
    with create(tmp_path) as project:
        selected, plan, _, _ = setup(project, **{option: True})
        with pytest.raises(ValueError, match='domain|canonical'):
            build_selection_shell(project, selected['id'], plan, tmp_path / 'rejected')
        assert not (tmp_path / 'rejected').exists()


def test_unknown_service_meaning_cannot_be_realized_as_a_notification(tmp_path):
    with create(tmp_path) as project:
        selected, plan, _, _ = setup(project, service='file.read')
        with pytest.raises(ValueError, match='notifications only'):
            build_selection_shell(project, selected['id'], plan, tmp_path / 'rejected')
        assert not (tmp_path / 'rejected').exists()


def test_scalar_return_is_derived_from_the_fixed_contract(tmp_path):
    with create(tmp_path) as project:
        selected, plan, _, lid = setup(project)
        layer = deepcopy(project.udl_layer_info(lid, full=True)['document'])
        layer['name'] = 'no-optional-return'; layer['implementation'].pop('return')
        replacement = register_layer(project, layer)
        bindings = deepcopy(project.udl_selection_info(selected['id'], full=True)['document']['bindings'])
        bindings['math'] = replacement['id']; selected = select_layers(project, 'derived-return', bindings)
        build_selection_shell(project, selected['id'], plan, tmp_path / 'native')
    capsule = json.loads((tmp_path / 'native/capsule.json').read_text())
    assert capsule['modules']['math']['return'] == '$sum'


def test_ambiguous_multioutput_scalar_return_refuses_before_output(tmp_path):
    with create(tmp_path) as project:
        selected, plan, cid, lid = setup(project)
        contract = deepcopy(project.contract_info(cid, full=True)['document'])
        contract['name'] = 'multiple.outputs'; contract['outputs']['right'] = 'u16'
        c = register_contract(project, contract)
        layer = deepcopy(project.udl_layer_info(lid, full=True)['document'])
        layer['name'] = 'ambiguous.return'; layer['contract'] = c['id']
        layer['implementation']['outputs']['right'] = '$right'
        replacement = register_layer(project, layer)
        bindings = deepcopy(project.udl_selection_info(selected['id'], full=True)['document']['bindings'])
        bindings['math'] = replacement['id']; selected = select_layers(project, 'ambiguous-return', bindings)
        with pytest.raises(ValueError, match='exactly one'):
            build_selection_shell(project, selected['id'], plan, tmp_path / 'rejected')
        assert not (tmp_path / 'rejected').exists()


def test_selected_capsule_prevalidates_before_native_emission(tmp_path, monkeypatch):
    original = udc_layers._json
    def reject_capsule(document):
        if document.get('format') == 'fdisbull-selected-shell-capsule-1':
            raise ValueError('selected capsule budget')
        return original(document)
    with create(tmp_path) as project:
        selected, plan, _, _ = setup(project)
        monkeypatch.setattr(udc_layers, '_json', reject_capsule)
        with pytest.raises(ValueError, match='selected capsule budget'):
            build_selection_shell(project, selected['id'], plan, tmp_path / 'not-emitted')
    assert not (tmp_path / 'not-emitted').exists()


def test_selected_capsule_write_failure_removes_only_new_owned_output(tmp_path, monkeypatch):
    original = Path.open
    def fail_selected(path, *args, **kwargs):
        if path.name == 'selection-capsule.json': raise OSError('simulated capsule write failure')
        return original(path, *args, **kwargs)
    with create(tmp_path) as project:
        selected, plan, _, _ = setup(project)
        monkeypatch.setattr(Path, 'open', fail_selected)
        with pytest.raises(OSError, match='capsule write'):
            build_selection_shell(project, selected['id'], plan, tmp_path / 'not-complete')
    assert not (tmp_path / 'not-complete').exists()


def test_selection_capsule_does_not_remove_a_competing_replacement_directory(tmp_path, monkeypatch):
    original = Path.open; destination = tmp_path / 'native'; parked = tmp_path / 'parked'
    def replace_before_failure(path, *args, **kwargs):
        if path.name == 'selection-capsule.json':
            destination.rename(parked); destination.mkdir()
            (destination / 'other-owner').write_text('preserve')
            raise OSError('simulated concurrent replacement')
        return original(path, *args, **kwargs)
    with create(tmp_path) as project:
        selected, plan, _, _ = setup(project)
        monkeypatch.setattr(Path, 'open', replace_before_failure)
        with pytest.raises(OSError, match='concurrent replacement'):
            build_selection_shell(project, selected['id'], plan, destination)
    assert (destination / 'other-owner').read_text() == 'preserve'
    assert (parked / 'program.exe').is_file()


def test_selected_failure_preserves_unknown_files_and_replaced_native_file(tmp_path, monkeypatch):
    original = Path.open; destination = tmp_path / 'native'
    def introduce_unowned_files(path, *args, **kwargs):
        if path.name == 'selection-capsule.json':
            (destination / 'program.exe').rename(destination / 'parked-program.exe')
            (destination / 'program.exe').write_bytes(b'other program')
            (destination / 'other-owner').write_text('preserve')
            raise OSError('simulated competing file')
        return original(path, *args, **kwargs)
    with create(tmp_path) as project:
        selected, plan, _, _ = setup(project)
        monkeypatch.setattr(Path, 'open', introduce_unowned_files)
        with pytest.raises(OSError, match='competing file'):
            build_selection_shell(project, selected['id'], plan, destination)
    assert (destination / 'program.exe').read_bytes() == b'other program'
    assert (destination / 'other-owner').read_text() == 'preserve'
    assert (destination / 'parked-program.exe').is_file()
    assert not (destination / 'capsule.json').exists()


def test_selected_capsule_readback_mismatch_is_not_success(tmp_path, monkeypatch):
    original = Path.read_bytes
    def corrupt_readback(path):
        return b'wrong bytes' if path.name == 'selection-capsule.json' else original(path)
    with create(tmp_path) as project:
        selected, plan, _, _ = setup(project)
        monkeypatch.setattr(Path, 'read_bytes', corrupt_readback)
        with pytest.raises(ValueError, match='readback'):
            build_selection_shell(project, selected['id'], plan, tmp_path / 'not-complete')
    assert not (tmp_path / 'not-complete').exists()


def selected_addition(project, order):
    selected, plan, cid, lid = setup(project)
    layer = deepcopy(project.udl_layer_info(lid, full=True)['document'])
    a, b = ('$left', '$right') if order == 'left-first' else ('$right', '$left')
    layer['name'] = 'portable.add.' + order
    layer['implementation']['program']['body'] = [
        {'id': 'copy', 'op': 'set', 'var': '$sum', 'value': {'var': a}},
        {'id': 'add', 'op': 'add', 'var': '$sum', 'value': {'var': b}},
        {'id': 'local-default', 'op': 'add', 'var': '$sum', 'value': {'var': '$scratch'}},
        {'id': 'private-input', 'op': 'set', 'var': '$left', 'value': 17},
        {'id': 'private-local', 'op': 'set', 'var': '$scratch', 'value': 23}]
    chosen = register_layer(project, layer)
    bindings = deepcopy(selected['document']['bindings']) if 'document' in selected else {
        **project.udl_selection_info(selected['id'], full=True)['document']['bindings']}
    bindings['math'] = chosen['id']
    fixed = project.contract_info(cid, full=True)['document']['behavior']['program']
    selection = select_layers(project, order, bindings, program=fixed)
    # The caller's equal-spelled scratch field is separate from the callee's
    # initialized activation local, which deliberately changes before return.
    plan['state']['$scratch'] = {'type': 'u16', 'initial': 12345}
    return selection, plan


@pytest.mark.parametrize('order', ['left-first', 'right-first'])
@pytest.mark.parametrize('backend', ['uil', 'c-uil'])
def test_real_selected_database_qualifier_adapter_pe_and_native_notification(tmp_path, order,backend):
    names = ('FDISBULL_PE_QEMU', 'FDISBULL_PE_KERNEL', 'FDISBULL_PE_INITRAMFS')
    if any(not os.environ.get(name) for name in names):
        if os.environ.get('FDISBULL_REQUIRE_PE') == '1': pytest.fail('Supply real PE runtime inputs')
        pytest.skip('Supply real PE runtime inputs for selected-shell acceptance')
    with create(tmp_path) as project:
        selected, plan = selected_addition(project, order)
        if backend=='c-uil':
            layer=deepcopy(project.udl_layer_info(selected['document']['bindings']['math'],full=True)['document'])
            layer['implementation']['backend']='c-uil';replacement=register_layer(project,layer)
            selected=select_layers(project,order+'.C',{**selected['document']['bindings'],'math':replacement['id']},program=selected['document']['program'])
        source_hash = project.meta['source_sha256']
    with Project(tmp_path / 'authored.fdb') as project:
        built = build_selection_shell(project, selected['id'], plan, tmp_path / 'native',c_compiler=__import__('shutil').which('clang'))
        assert built['qualification']['math']['status'] == 'equivalent_under_contract'
        assert built['qualification']['math']['method'] == 'bounded-scalar-z3'
        assert project.meta['source_sha256'] == source_hash
    qemu, kernel, runtime = (os.environ[name] for name in names)
    base = 0x140000000
    with Project.create(tmp_path / 'native.fdb', tmp_path / 'native/program.exe') as project:
        project.analyze(max_instructions=256)
        with project.debugger(qemu, tmp_path / 'native', kernel=kernel, initramfs=runtime, files=['program.exe']) as debug:
            stop = debug.breakpoint(base + built['slots']['module:present']['rva'])
            assert debug.run(timeout_ms=60000)['outcome'] == 'breakpoint'
            expected = {'$left': 65535, '$right': 2, '$sum': 1, '$scratch': 12345}
            for name, value in expected.items():
                data = debug.memory(base + built['state'][name]['rva'], length=2)['hex']
                assert int.from_bytes(bytes.fromhex(data), 'little') == value
            assert int(debug.registers()['general']['rdx'], 16) == 1
            debug.delete_breakpoint(stop['breakpoint_id'])
            assert debug.run(timeout_ms=2000)['outcome'] == 'timeout'
            frame = notification_frame(debug, 'selected-win.png')
            assert frame['metadata']['width'] > 20
            debug.click(frame['metadata']['width'] // 2, frame['metadata']['height'] - 14,
                        mode_id=frame['metadata']['mode_id'])
            exited = debug.run(timeout_ms=60000)
            assert exited['outcome'] == 'exited' and exited['session']['exit_code'] == 0
        assert debug.rpc.process.poll() is not None


def test_linux_bridge_preserves_pinned_definitions_and_requires_service_profile(tmp_path):
 from fdisbull.cli import respond
 with create(tmp_path) as p:
  s,plan,cid,lid=setup(p)
 r=respond({'method':'build-udc-shell','params':{'project':str(tmp_path/'authored.fdb'),'selection':s['id'],'plan':plan,'destination':str(tmp_path/'linux'),'target':'linux-x64','service_adapters':{'present':{'backend':'linux-stdout','acknowledgment':'none'}},'capture_state':True}})
 assert r['ok'],r
 assert r['result']['target']['format']=='ELF64' and r['result']['layer_ids']['math']==lid
 capsule=json.loads((tmp_path/'linux/selection-capsule.json').read_text());assert capsule['selection']==s['id']
 with Project(tmp_path/'authored.fdb') as p:
  doc=deepcopy(p.contract_info(cid,full=True)['document'])
  with pytest.raises(ValueError,match='unsupported native shell target'):build_selection_shell(p,s['id'],plan,tmp_path/'bad',target='unknown')
  with pytest.raises(ValueError,match='cannot be ignored'):build_selection_shell(p,s['id'],plan,tmp_path/'bad',capture_state=True)


def test_native_service_cannot_silently_drop_contract_profile_obligations(tmp_path):
 with create(tmp_path) as p:
  s,plan,cid,lid=setup(p);service=p.udl_layer_info(s['document']['bindings']['present'],full=True)['document']
  c=p.contract_info(service['contract'],full=True)['document'];c['behavior']['profile']={'acknowledgment':'required'}
  new=register_contract(p,c);service['contract']=new['id'];layer=register_layer(p,service)
  chosen=select_layers(p,'profile',{'math':lid,'present':layer['id']})
  with pytest.raises(ValueError,match='profile obligations'):
   build_selection_shell(p,chosen['id'],plan,tmp_path/'bad',target='linux-x64',service_adapters={'present':{'backend':'linux-stdout','acknowledgment':'none'}})
 assert not (tmp_path/'bad').exists()
