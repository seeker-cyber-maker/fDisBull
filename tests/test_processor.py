"""The seam dispatches actual decoders without claiming a guest project store."""
import struct

import pytest

from fdisbull.decoder import decode
from fdisbull.processor import (CILMethodProcessor, DecodedInstruction, Location,
                                 NativeProcessor, ProcessorInfo, Successor, decode_instruction)
from fdisbull.project import Project


class ToyProcessor:
    # Authored test language, not an existing machine or game.
    info = ProcessorInfo('test.toy', '1', 'toy.instructions', 'instruction',
                         ('decode', 'static_successors'), 'counter: integer')

    def decode(self, program, location):
        if location.offset >= len(program):
            return None
        op, argument = program[location.offset]
        if op == 'if':
            edges = (Successor('branch', Location(location.space, argument), 'condition true'),
                     Successor('fallthrough', Location(location.space, location.offset + 1), 'condition false'))
        elif op == 'stop':
            edges = ()
        else:
            raise ValueError('unknown toy opcode')
        return DecodedInstruction(location, {'mnemonic': op}, edges)


def test_same_dispatch_handles_native_and_instruction_indexed_toy():
    native = NativeProcessor('x86', 64)
    location = Location('native.flat', 0x1000)
    result = decode_instruction(native, bytes.fromhex('7502'), location)
    assert result.facts == decode(bytes.fromhex('7502'), 0x1000, 'x86', 64)
    assert [(s.kind, s.target.offset) for s in result.successors] == [('branch', 0x1004), ('fallthrough', 0x1002)]
    toy = ToyProcessor()
    result = decode_instruction(toy, [('if', 2), ('stop', None), ('stop', None)], Location('toy.instructions', 0))
    assert result.facts['mnemonic'] == 'if'
    assert [(s.kind, s.target.offset) for s in result.successors] == [('branch', 2), ('fallthrough', 1)]
    assert toy.info.address_unit == 'instruction' and toy.info.state_schema == 'counter: integer'
    with pytest.raises(ValueError, match='address space'):
        decode_instruction(toy, [], Location('native.flat', 0))


def test_real_cil_switch_retains_method_space_and_multiple_edges():
    pytest.importorskip('dnfile')
    pytest.importorskip('dncil')
    from fdisbull.managed import disassemble_managed
    from test_managed import with_method_body
    code = b'\x16\x45' + struct.pack('<Iii', 2, 0, 1) + b'\0\x2a'
    processor = CILMethodProcessor(with_method_body(code), 0x06000001)
    method = processor.method
    space = processor.info.address_space
    assert space.endswith(':method:0x06000001')
    result = decode_instruction(processor, method, Location(space, 1))
    assert result.facts['mnemonic'] == 'switch'
    assert [(s.kind, s.target) for s in result.successors] == [
        ('branch', Location(space, 14)), ('branch', Location(space, 15)),
        ('fallthrough', Location(space, 14))]
    assert processor.info.state_schema is None
    with pytest.raises(ValueError, match='address space'):
        decode_instruction(processor, method, Location('cil.method:0x06000002', 1))


def test_guest_processor_is_not_silently_admitted_to_native_project(tmp_path):
    source = tmp_path / 'toy.bin'
    source.write_bytes(b'\x00')
    with pytest.raises(ValueError, match='architecture'):
        Project.create(tmp_path / 'toy.fdb', source, arch='toy')


def test_flat_analyzer_really_dispatches_through_native_adapter(tmp_path, monkeypatch):
    import fdisbull.processor as module
    original = module.decode_instruction
    calls = []
    def spy(processor, program, location):
        calls.append((processor.info.identity, location))
        return original(processor, program, location)
    monkeypatch.setattr(module, 'decode_instruction', spy)
    source = tmp_path / 'native.bin'
    source.write_bytes(bytes.fromhex('7501c3c3'))
    with Project.create(tmp_path / 'native.fdb', source, arch='x86', bits=64, base=0x1000) as project:
        assert project.analyze()['stable']
        assert {location.offset for _, location in calls} == {0x1000, 0x1002, 0x1003}
        assert {identity for identity, _ in calls} == {'fdisbull.native.x86.64'}
        assert {row['kind'] for row in project.db.execute("SELECT kind FROM xrefs WHERE source='0000000000001000'")} >= {'branch', 'fallthrough'}


def test_cil_negative_branch_target_remains_unresolved():
    pytest.importorskip('dnfile')
    pytest.importorskip('dncil')
    from fdisbull.managed import disassemble_managed
    from test_managed import with_method_body
    processor = CILMethodProcessor(with_method_body(bytes.fromhex('2b802a')), 0x06000001)
    method = processor.method
    instruction = decode_instruction(processor, method, Location(processor.info.address_space, 0))
    assert instruction.successors[0].target is None
    assert 'target offset -126' in instruction.successors[0].evidence


def test_cil_invalid_and_unverified_positive_targets_are_not_traversable():
    pytest.importorskip('dnfile')
    pytest.importorskip('dncil')
    from fdisbull.managed import disassemble_managed
    from test_managed import with_method_body
    adapter = CILMethodProcessor(with_method_body(bytes.fromhex('2b7f2a')), 0x06000001)
    outside = adapter.method
    branch = decode_instruction(adapter, outside, Location(adapter.info.address_space, 0)).successors[0]
    assert branch.target is None and 'target offset 129' in branch.evidence
    # The target is in the method, but the instruction budget did not reach it.
    adapter = CILMethodProcessor(with_method_body(bytes.fromhex('2b01002a')), 0x06000001, max_instructions=1)
    partial = adapter.method
    assert partial['branch_references'][0]['target_is_instruction'] is None
    branch = decode_instruction(adapter, partial, Location(adapter.info.address_space, 0)).successors[0]
    assert branch.target is None and 'unverified' in branch.evidence


def test_cil_jmp_is_not_a_returning_call():
    pytest.importorskip('dnfile')
    pytest.importorskip('dncil')
    from test_managed import with_method_body
    adapter = CILMethodProcessor(with_method_body(bytes.fromhex('27020000062a')), 0x06000001)
    result = decode_instruction(adapter, adapter.method, Location(adapter.info.address_space, 0))
    assert result.facts['flow'] == 'call'  # preserve legacy decoder facts
    assert [(edge.kind, edge.target) for edge in result.successors] == [('branch', None)]


def test_cil_same_token_different_assemblies_have_distinct_spaces():
    pytest.importorskip('dnfile')
    pytest.importorskip('dncil')
    from test_managed import with_method_body
    first = CILMethodProcessor(with_method_body(bytes.fromhex('002a')), 0x06000001)
    second = CILMethodProcessor(with_method_body(bytes.fromhex('162a')), 0x06000001)
    assert first.info.address_space != second.info.address_space
    with pytest.raises(ValueError, match='address space'):
        decode_instruction(first, first.method, Location(second.info.address_space, 0))


def test_dispatch_rejects_malformed_descriptor_and_result():
    class Bad(ToyProcessor):
        info = ProcessorInfo('', '1', 'toy.instructions', 'instruction', ('decode',), None)
    with pytest.raises(ValueError, match='descriptor'):
        decode_instruction(Bad(), [], Location('toy.instructions', 0))
    class BadResult(ToyProcessor):
        def decode(self, program, location):
            return DecodedInstruction(location, {}, (Successor('branch', 5, 'bad target'),))
    with pytest.raises(ValueError, match='instruction result'):
        decode_instruction(BadResult(), [], Location('toy.instructions', 0))
