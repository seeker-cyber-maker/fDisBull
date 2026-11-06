"""Authored guest programs; no original game assets or native decoder needed."""
from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.cli import main, respond
from fdisbull.decoder_modules import (AGI2917Module, DecoderInput, DecoderModuleInfo,
                                     DecoderRegistry, analyze_input, builtin_registry, capture_input, lift_input)
from fdisbull.interaction_il import execute_il
from fdisbull.processor import DecodedInstruction, Location, NativeProcessor, ProcessorInfo, Successor
from tests.test_agi import fixture
from tests.test_zmachine_processor import image


AGI = 'fdisbull.agi.2.917.subset'
Z = 'fdisbull.zmachine.v3'


def agi(tmp_path, code=bytes.fromhex('0301070c020d0200')):
    return builtin_registry().open(AGI, fixture(tmp_path, code),
                                   volume_dir=tmp_path, logic=0, profile='2.917')


def test_builtin_module_catalog_and_explicit_registration():
    registry = builtin_registry()
    assert {row['identity'] for row in registry.catalog()} == {AGI, Z, 'fdisbull.westwood.emc2', 'fdisbull.mads.conversation'}
    with pytest.raises(ValueError, match='already registered'):
        registry.register(AGI2917Module())
    with pytest.raises(ValueError, match='trusted'):
        registry.register('some_package:load_me')
    with pytest.raises(ValueError, match='explicitly registered'):
        registry.open('arbitrary.python.module', 'ignored')
    with pytest.raises(ValueError):
        DecoderModuleInfo('', '1', 'format', ('decode',))


def test_native_decoder_is_not_a_dependency_of_agi_path(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('native decoder must not be called')
    monkeypatch.setattr(NativeProcessor, 'decode', forbidden)
    opened = agi(tmp_path)
    result = analyze_input(opened)
    assert result['complete'] and result['runtime_execution'] is False
    assert [row['facts']['mnemonic'] for row in result['instructions']] == ['assignn', 'set', 'reset', 'return']
    lifted = lift_input(opened, initial_state={'$agi_v1': 255, '$agi_f2': True})
    assert lifted['qualification'] == 'state_projection_only'
    assert lifted['snapshot'] == result['snapshot']
    assert execute_il(lifted['uil'])['state'] == {'$agi_v1': 7, '$agi_f2': False}


def test_snapshot_not_filesystem_and_source_copy_isolation(tmp_path):
    opened = agi(tmp_path)
    before = analyze_input(opened)
    metadata = opened.source
    metadata['volume_sha256'] = 'altered copy'
    assert opened.source['volume_sha256'] != 'altered copy'
    with pytest.raises(FrozenInstanceError):
        opened.source_json = '{}'
    with pytest.raises(ValueError, match='program bytes'):
        replace(opened, program=b'\x00')
    (tmp_path / 'VOL.0').unlink()
    assert analyze_input(opened) == before
    # A changed byte snapshot must not reuse the earlier identity or namespace.
    changed = agi(tmp_path, bytes.fromhex('03010800'))
    assert opened.identity != changed.identity
    assert opened.entry.space != changed.entry.space
    assert lift_input(opened, initial_state={'$agi_v1': 0, '$agi_f2': False})['snapshot'] == before['snapshot']


def test_container_occurrence_is_distinct_from_payload_location(tmp_path):
    first = agi(tmp_path)
    # Same selected payload, changed unrelated container bytes.
    with (tmp_path / 'VOL.0').open('ab') as output:
        output.write(b'authored unrelated tail')
    second = builtin_registry().open(AGI, tmp_path/'LOGDIR', volume_dir=tmp_path,
                                     logic=0, profile='2.917')
    assert first.entry == second.entry  # same payload-local location
    assert first.identity != second.identity  # different source occurrence


@pytest.mark.parametrize('code,kind', [
    (b'\xaa\x00', 'unresolved_successor'),
    (b'\x03\x01', 'decode_error'),
    (bytes.fromhex('feffffff000000'), 'overlapping_instruction'),
    (bytes.fromhex('feff7f'), 'unresolved_successor'),
])
def test_incomplete_static_paths_remain_incomplete(tmp_path, code, kind):
    result = analyze_input(agi(tmp_path, code))
    assert not result['complete']
    assert kind in {issue['kind'] for issue in result['issues']}


def test_budget_cycle_and_source_address_validation(tmp_path):
    result = analyze_input(agi(tmp_path), max_instructions=1)
    assert not result['complete'] and result['issues'][-1]['kind'] == 'instruction_budget'
    loop = analyze_input(agi(tmp_path, bytes.fromhex('fefdff')), max_instructions=1)
    assert loop['complete']  # one static self-edge; not a termination claim
    for bad in (True, 0, 1001, 1.5):
        with pytest.raises(ValueError, match='max_instructions'):
            analyze_input(agi(tmp_path), max_instructions=bad)
    with pytest.raises(ValueError, match='source offset'):
        analyze_input(agi(tmp_path), address=True)


def test_zmachine_is_second_independent_front_end(tmp_path):
    story = tmp_path/'NO_EXTENSION'
    story.write_bytes(image())
    opened = builtin_registry().open(Z, story)
    result = analyze_input(opened)
    assert result['complete'] and result['instructions'][0]['facts']['mnemonic'] == 'quit'
    assert opened.entry.offset == 900 and opened.entry.space.startswith('zmachine.v3.sha256:')
    with pytest.raises(ValueError, match='qualified lifter'):
        lift_input(opened, initial_state={})
    story.write_bytes(b'not a story')
    assert analyze_input(opened) == result
    with pytest.raises(ValueError):
        builtin_registry().open(Z, story)


def test_custom_trusted_module_preserves_units_and_spaces():
    class Indexed:
        info = ProcessorInfo('authored.indexed', '1', 'authored.instructions', 'instruction', ('decode','static_successors'), None)
        def decode(self, program, location):
            return DecodedInstruction(location, {'op': 'stop'}, ())
    class Module:
        info = DecoderModuleInfo('authored.indexed', '1', 'authored-test', ('decode','static_successors'))
        def open(self, source):
            processor = Indexed()
            return capture_input(self.info, processor, (), Location(processor.info.address_space, 0), {})
    registry = DecoderRegistry()
    registry.register(Module())
    opened = registry.open('authored.indexed', None)
    assert opened.processor.decode(opened.program, opened.entry).facts == {'op': 'stop'}
    with pytest.raises(ValueError, match='byte address units'):
        analyze_input(opened)
    with pytest.raises(ValueError, match='entry space'):
        replace(opened, entry=Location('native.flat', 0))


def test_registry_descriptor_drift_and_nonfinite_metadata_refused(tmp_path):
    module = AGI2917Module()
    registry = DecoderRegistry()
    registry.register(module)
    module.info = DecoderModuleInfo('changed', '2', 'different', ('decode',))
    assert registry.catalog()[0]['identity'] == AGI
    with pytest.raises(ValueError, match='descriptor changed'):
        registry.open(AGI, None)
    opened = agi(tmp_path)
    with pytest.raises(ValueError, match='capabilities'):
        analyze_input(replace(opened, module=replace(opened.module, capabilities=('decode',))))
    with pytest.raises(ValueError, match='JSON compliant'):
        replace(opened, source_json='{"bad":NaN}')
    with pytest.raises(ValueError):
        replace(opened, source_json='[]')
    opened.processor.info = replace(opened.processor.info, version='changed')
    with pytest.raises(ValueError, match='processor descriptor changed'):
        analyze_input(opened)
    with pytest.raises(ValueError, match='processor descriptor changed'):
        lift_input(opened, initial_state={'$agi_v1':0,'$agi_f2':False})


def test_copied_metadata_cannot_misidentify_captured_lifter_or_code(tmp_path):
    from hashlib import sha256
    opened = agi(tmp_path)
    metadata = opened.source
    metadata['volume_sha256'] = '0'*64
    forged = replace(opened, source_json=json.dumps(metadata))
    for query in (lambda: analyze_input(forged),
                  lambda: lift_input(forged, initial_state={'$agi_v1':0,'$agi_f2':False}),
                  lambda: forged.identity):
        with pytest.raises(ValueError, match='source binding'):
            query()
    metadata = opened.source
    metadata.update(program_sha256=sha256(b'\x00').hexdigest(),code_length=1)
    forged = replace(opened, program=b'\x00',source_json=json.dumps(metadata))
    with pytest.raises(ValueError, match='source binding'):
        analyze_input(forged)
    with pytest.raises(ValueError, match='source binding'):
        lift_input(forged, initial_state={})


def test_cli_json_methods_are_projectless_and_do_not_inherit_default(tmp_path, capsys):
    opened = agi(tmp_path)
    params = dict(module=AGI, path=str(tmp_path/'LOGDIR'), volume_dir=str(tmp_path), logic=0, profile='2.917')
    result = respond({'method':'module-analyze', 'params':params}, default_project='must-not-open.db')
    assert result['ok'] and result['result']['snapshot'] == opened.identity
    result = respond({'method':'module-lift', 'params':dict(params, initial_state={'$agi_v1':0,'$agi_f2':False})})
    assert result['ok'] and result['result']['uil']['role'] == 'uil'
    assert not respond({'method':'decoder-modules','params':{'import':'x'}})['ok']
    state = tmp_path/'state.json'
    state.write_text(json.dumps({'$agi_v1':0,'$agi_f2':False}))
    assert main(['module-lift',AGI,str(tmp_path/'LOGDIR'),'--volume-dir',str(tmp_path),'--logic','0',
                 '--profile','2.917','--state-file',str(state)]) == 0
    assert json.loads(capsys.readouterr().out)['result']['qualification'] == 'state_projection_only'
    assert main(['decoder-modules']) == 0
    assert len(json.loads(capsys.readouterr().out)['result']['modules']) == 4


def test_direct_cli_runs_without_site_packages(tmp_path):
    agi(tmp_path)
    params = dict(module=AGI, path=str(tmp_path/'LOGDIR'), volume_dir=str(tmp_path),
                  logic=0, profile='2.917', initial_state={'$agi_v1':0,'$agi_f2':False})
    # -S uses the genuine interpreter with no site-packages, not fake decoders.
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1]/'src'),
                       PYTHONDONTWRITEBYTECODE='1')
    completed = subprocess.run([sys.executable, '-B', '-S', '-m', 'fdisbull', 'request',
                                json.dumps({'method':'module-lift','params':params})],
                               env=environment, capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)['result']['qualification'] == 'state_projection_only'
