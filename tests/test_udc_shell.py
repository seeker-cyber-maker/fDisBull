"""Native shell boundaries use authored programs, never original game bytes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import struct
import time

import lief
import pytest

from fdisbull.project import Project
from fdisbull.udc_shell import BASE, FORMAT, build_windows_shell


def wait_for_client_window(debug, *, clock=time.monotonic, timeout=30):
    deadline = clock() + timeout

    def remaining_ms():
        remaining = deadline - clock()
        assert remaining >= 0.001, 'Timed out waiting for a usable client window'
        return max(1, int(remaining * 1000))

    while True:
        probe = debug.call('frame.probe', timeout_ms=remaining_ms())
        remaining_ms()
        assert type(probe) is dict and type(probe.get('available')) is bool, probe
        if probe['available']:
            assert type(probe.get('width')) is int and probe['width'] > 0, probe
            assert type(probe.get('height')) is int and probe['height'] > 0, probe
            return probe
        result = debug.run(timeout_ms=min(250, remaining_ms()))
        assert result['outcome'] == 'timeout', result
        remaining_ms()


def test_window_wait_uses_only_required_slices():
    class Fake:
        def __init__(self, probes): self.probes = iter(probes); self.calls = []
        def run(self, **kwargs):
            self.calls.append(('run', kwargs)); return {'outcome': 'timeout'}
        def call(self, method, **kwargs):
            self.calls.append((method, kwargs)); return next(self.probes)
    visible = {'available': True, 'width': 80, 'height': 40}
    debug = Fake([visible])
    assert wait_for_client_window(debug, clock=lambda: 0) == visible
    assert debug.calls == [('frame.probe', {'timeout_ms': 30000})]
    debug = Fake([{'available': False}, {'available': False}, visible])
    assert wait_for_client_window(debug, clock=lambda: 0) == visible
    assert [item[0] for item in debug.calls] == [
        'frame.probe', 'run', 'frame.probe', 'run', 'frame.probe']
    assert all(item[1]['timeout_ms'] == 250 for item in debug.calls if item[0] == 'run')


def test_window_wait_rejects_stop_and_deadline():
    class Fake:
        def __init__(self): self.calls = []
        def call(self, method, **kwargs):
            self.calls.append((method, kwargs)); return {'available': False}
        def run(self, **kwargs):
            self.calls.append(('run', kwargs)); return {'outcome': 'breakpoint'}
    debug = Fake()
    with pytest.raises(AssertionError, match='breakpoint'):
        wait_for_client_window(debug, clock=lambda: 0)
    assert [item[0] for item in debug.calls] == ['frame.probe', 'run']
    debug = Fake(); times = iter([0, 0.25, 1.01])
    with pytest.raises(AssertionError, match='Timed out'):
        wait_for_client_window(debug, clock=lambda: next(times), timeout=1)
    assert debug.calls == [('frame.probe', {'timeout_ms': 750})]


@pytest.mark.parametrize('probe', [{}, {'available': 1}, {'available': True},
                                  {'available': True, 'width': 1, 'height': 0}])
def test_window_wait_rejects_malformed_probe(probe):
    class Fake:
        def call(self, method, **kwargs): return probe
    with pytest.raises(AssertionError):
        wait_for_client_window(Fake(), clock=lambda: 0)


def example(steps=3):
    program = {'format': 'fdisbull-il-1', 'role': 'uil',
               'variables': {'$count': {'type': 'u16', 'initial': 0},
                             '$outcome': {'type': 'u16', 'initial': 0}},
               'resources': {}, 'body': [
                   {'id': 'advance', 'op': 'add', 'var': '$count', 'value': 1},
                   {'id': 'choose', 'op': 'if', 'condition': {'op': 'eq', 'left': {'var': '$count'}, 'right': 3},
                    'then': [{'id': 'won', 'op': 'set', 'var': '$outcome', 'value': 1}],
                    'else': [{'id': 'lost', 'op': 'set', 'var': '$outcome', 'value': 0}]}]}
    state = {**deepcopy(program['variables']), '$steps': {'type': 'u16', 'initial': steps}}
    plan = {'format': FORMAT, 'entry': 'main', 'state': state,
            'resources': {key: {'kind': 'text', 'text': text}
                          for key, text in [('won', 'Win'), ('lost', 'Lose'), ('unknown', 'Unknown')]},
            'functions': {
                'advance': {'body': [{'op': 'call', 'binding': 'arithmetic'}]},
                'main': {'body': [
                    {'op': 'while', 'condition': {'op': 'not', 'condition': {
                        'op': 'eq', 'left': {'var': '$count'}, 'right': {'var': '$steps'}}},
                     'limit': 4, 'body': [{'op': 'call', 'function': 'advance'}]},
                    {'op': 'notify', 'binding': 'notification', 'value': {'var': '$outcome'}}]}}}
    modules = {'arithmetic': {'backend': 'uil', 'program': program, 'return': '$outcome'},
               'notification': {'backend': 'message-box-a', 'title': 'Native UDC outcome',
                                'messages': {'0': 'lost', '1': 'won'}, 'default': 'unknown', 'style': 64}}
    return plan, modules


def test_real_pe64_structure_source_map_and_lossless_build_capsule(tmp_path):
    plan, modules = example(); before = deepcopy((plan, modules))
    build = build_windows_shell(plan, modules, tmp_path / 'native')
    binary = lief.PE.parse(str(tmp_path / 'native/program.exe'))
    assert binary.header.machine == lief.PE.Header.MACHINE_TYPES.AMD64
    assert binary.optional_header.magic == lief.PE.PE_TYPE.PE32_PLUS
    assert binary.optional_header.addressof_entrypoint == 0x1000
    assert binary.optional_header.subsystem == lief.PE.OptionalHeader.SUBSYSTEM.WINDOWS_GUI
    assert {entry.name for entry in binary.imports} == {'KERNEL32.dll', 'USER32.dll'}
    assert {entry.name for module in binary.imports for entry in module.entries} == {
        'ExitProcess', 'MessageBoxA', 'OutputDebugStringA'}
    assert build['target']['original_binary_wrapped'] is False
    assert build['qualification']['native_execution'] is False
    capsule = json.loads((tmp_path / 'native/capsule.json').read_text())
    assert capsule['plan'] == plan and capsule['modules'] == modules
    assert (plan, modules) == before
    assert build['slots']['module:arithmetic']['source_map']
    with Project.create(tmp_path / 'native.fdb', tmp_path / 'native/program.exe') as project:
        project.analyze(max_instructions=128)
        row = project.disassembly(hex(BASE + 0x1000), lines=1)['instructions'][0]
        assert row['mnemonic'] == 'push' and row['operands'] == 'r12'
    with Project(tmp_path / 'native.fdb') as project:
        assert project.disassembly(hex(BASE + 0x1000), lines=1)['instructions'][0] == row


@pytest.mark.parametrize('provider,style', [('message-box-a', 16), ('debug-string-a', 64)])
def test_provider_swap_preserves_every_other_executable_byte(tmp_path, provider, style):
    plan, modules = example()
    first = build_windows_shell(plan, modules, tmp_path / 'first')
    changed = deepcopy(modules); changed['notification'].update(backend=provider, style=style)
    second = build_windows_shell(plan, changed, tmp_path / 'second')
    a, b = (tmp_path / 'first/program.exe').read_bytes(), (tmp_path / 'second/program.exe').read_bytes()
    slot = first['slots']['module:notification']; start, size = slot['file_offset'], slot['size']
    assert a != b and len(a) == len(b)
    assert a[:start] == b[:start] and a[start + size:] == b[start + size:]
    assert first['plan_sha256'] == second['plan_sha256']
    assert first['slots']['module:arithmetic']['sha256'] == second['slots']['module:arithmetic']['sha256']


def test_input_state_changes_data_without_changing_native_logic(tmp_path):
    plan, modules = example(3)
    first = build_windows_shell(plan, modules, tmp_path / 'three')
    plan['state']['$steps']['initial'] = 2
    second = build_windows_shell(plan, modules, tmp_path / 'two')
    assert {k: s['sha256'] for k, s in first['slots'].items()} == {k: s['sha256'] for k, s in second['slots'].items()}
    a, b = (tmp_path / 'three/program.exe').read_bytes(), (tmp_path / 'two/program.exe').read_bytes()
    assert a != b
    assert sum(x != y for x, y in zip(a, b)) == 1


def test_actual_uil_text_edit_changes_only_its_module_slot(tmp_path):
    plan, modules = example()
    plan['functions']['main']['body'] = [{'op': 'call', 'binding': 'arithmetic'}]
    modules['arithmetic']['program']['resources'] = deepcopy(plan['resources'])
    modules['arithmetic']['program']['body'] = [{'id': 'text', 'op': 'text', 'resource': 'won'}]
    modules['arithmetic']['notification_binding'] = 'notification'
    first = build_windows_shell(plan, modules, tmp_path / 'won')
    modules['arithmetic']['program']['body'][0]['resource'] = 'lost'
    second = build_windows_shell(plan, modules, tmp_path / 'lost')
    a, b = (tmp_path / 'won/program.exe').read_bytes(), (tmp_path / 'lost/program.exe').read_bytes()
    slot = first['slots']['module:arithmetic']; start, size = slot['file_offset'], slot['size']
    assert a != b and a[:start] == b[:start] and a[start + size:] == b[start + size:]
    assert first['plan_sha256'] == second['plan_sha256']
    assert first['slots']['module:notification']['sha256'] == second['slots']['module:notification']['sha256']
    assert modules['arithmetic']['program']['body'][0]['resource'] == 'lost'
    modules['notification']['style'] = 16
    third = build_windows_shell(plan, modules, tmp_path / 'different-provider')
    c = (tmp_path / 'different-provider/program.exe').read_bytes()
    provider = second['slots']['module:notification']; start, size = provider['file_offset'], provider['size']
    assert b != c and b[:start] == c[:start] and b[start + size:] == c[start + size:]
    assert second['slots']['module:arithmetic']['sha256'] == third['slots']['module:arithmetic']['sha256']


def test_unsupported_profiles_fail_before_output_and_never_overwrite(tmp_path):
    plan, modules = example()
    bad = deepcopy(plan); bad['functions']['advance']['body'] = [{'op': 'call', 'function': 'main'}]
    with pytest.raises(ValueError, match='recursive/reentrant'):
        build_windows_shell(bad, modules, tmp_path / 'cycle')
    assert not (tmp_path / 'cycle').exists()
    bad = deepcopy(plan); bad['state']['$count']['type'] = 'u32'
    with pytest.raises(ValueError, match='logical state type'):
        build_windows_shell(bad, modules, tmp_path / 'wide')
    bad = deepcopy(modules); bad['notification']['backend'] = 'no-ui'
    with pytest.raises(ValueError): build_windows_shell(plan, bad, tmp_path / 'silent')
    bad = deepcopy(plan); bad['resources']['won']['text'] = 'Non-ASCII é'
    with pytest.raises(ValueError, match='ASCII'): build_windows_shell(bad, modules, tmp_path / 'codec')
    bad = deepcopy(plan); bad['functions']['main']['body'] = [{'op': 'return', 'value': 1 << 63}]
    with pytest.raises(ValueError, match='signed 64-bit'):
        build_windows_shell(bad, modules, tmp_path / 'literal')
    repository = tmp_path / 'repo'; repository.mkdir(); (repository / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError, match='outside Git'):
        build_windows_shell(plan, modules, repository / 'generated')
    build_windows_shell(plan, modules, tmp_path / 'kept')
    original = (tmp_path / 'kept/program.exe').read_bytes()
    with pytest.raises(ValueError, match='new'): build_windows_shell(plan, modules, tmp_path / 'kept')
    assert (tmp_path / 'kept/program.exe').read_bytes() == original


@pytest.mark.parametrize('case,expected_count,expected_outcome,status', [
    ('win', 3, 1, 0), ('lose', 2, 0, 0), ('atomic-failure', 0, 0, 1),
    ('budget-failure', 1, 0, 2), ('typed-values', 1, 1, 0),
    ('uil-text-win', 1, 0, 0), ('uil-text-lose', 1, 0, 0), ('uil-text-atomic', 0, 0, 1),
    ('uil-text-alternate', 1, 0, 0)])
def test_real_native_windows_calls_state_loop_atomicity_and_notification(tmp_path, case, expected_count, expected_outcome, status):
    names = ('FDISBULL_PE_QEMU', 'FDISBULL_PE_KERNEL', 'FDISBULL_PE_INITRAMFS')
    if any(not os.environ.get(name) for name in names):
        if os.environ.get('FDISBULL_REQUIRE_PE') == '1': pytest.fail('Supply real PE runtime inputs')
        pytest.skip('Supply real PE runtime inputs for generated native shell acceptance')
    plan, modules = example(2 if case == 'lose' else 3)
    if case == 'atomic-failure':
        modules['arithmetic']['program']['body'] = [
            {'id': 'temporary', 'op': 'set', 'var': '$count', 'value': 9},
            {'id': 'refuse', 'op': 'require', 'condition': {'op': 'eq', 'left': 1, 'right': 2}}]
    elif case == 'budget-failure':
        plan['functions']['main']['body'][0]['limit'] = 1
    elif case == 'typed-values':
        declarations = {'$byte': {'type': 'u8', 'initial': 255},
                        '$signed': {'type': 'i16', 'initial': -1},
                        '$wide': {'type': 'u16', 'initial': 65535},
                        '$flag': {'type': 'bool', 'initial': False}}
        plan['state'].update(deepcopy(declarations)); plan['state']['$steps']['initial'] = 1
        program = modules['arithmetic']['program']; program['variables'].update(declarations)
        program['body'] = [
            {'id': 'signed-check', 'op': 'require', 'condition': {'op': 'and', 'conditions': [
                {'op': 'eq', 'left': {'var': '$signed'}, 'right': -1},
                {'op': 'bit_test', 'value': {'var': '$signed'}, 'bit': 63},
                {'op': 'not', 'condition': {'op': 'eq', 'left': {'var': '$signed'}, 'right': {'var': '$wide'}}}]}},
            {'id': 'byte-wrap', 'op': 'add', 'var': '$byte', 'value': 1},
            {'id': 'signed-wrap', 'op': 'subtract', 'var': '$signed', 'value': 32767},
            {'id': 'bool', 'op': 'set', 'var': '$flag', 'value': True},
            {'id': 'step', 'op': 'add', 'var': '$count', 'value': 1},
            {'id': 'outcome', 'op': 'set', 'var': '$outcome', 'value': 1}]
    elif case.startswith('uil-text-'):
        plan['functions']['main']['body'] = [{'op': 'call', 'binding': 'arithmetic'}]
        module = modules['arithmetic']; module['notification_binding'] = 'notification'
        module['program']['resources'] = deepcopy(plan['resources'])
        module['program']['body'] = [
            {'id': 'set', 'op': 'set', 'var': '$count', 'value': 1},
            {'id': 'text', 'op': 'text', 'resource': 'lost' if case == 'uil-text-lose' else 'won'}]
        if case == 'uil-text-atomic':
            module['program']['body'].append(
                {'id': 'fail', 'op': 'require', 'condition': {'op': 'eq', 'left': 1, 'right': 2}})
        if case == 'uil-text-alternate':
            modules['notification']['style'] = 16
    build = build_windows_shell(plan, modules, tmp_path / 'native')
    source = tmp_path / 'native/program.exe'
    qemu, kernel, runtime = (os.environ[name] for name in names)
    with Project.create(tmp_path / 'private.fdb', source) as project:
        project.analyze(max_instructions=256)
        with project.debugger(qemu, source.parent, kernel=kernel, initramfs=runtime, files=['program.exe']) as debug:
            # Successful paths stop at the real service; failures stop immediately
            # before ExitProcess, so failed qualifications cannot be hidden by UI.
            rva = build['slots']['module:notification']['rva'] if status == 0 else build['slots']['entry']['rva'] + 23
            if status == 0 and case.startswith('uil-text-'):
                rva += 0x800
            bp = debug.breakpoint(BASE + rva)
            assert debug.run(timeout_ms=60000)['outcome'] == 'breakpoint'
            count = bytes.fromhex(debug.memory(BASE + build['state']['$count']['rva'], length=2)['hex'])
            outcome = bytes.fromhex(debug.memory(BASE + build['state']['$outcome']['rva'], length=2)['hex'])
            assert struct.unpack('<H', count)[0] == expected_count
            assert struct.unpack('<H', outcome)[0] == expected_outcome
            if case == 'typed-values':
                assert debug.memory(BASE + build['state']['$byte']['rva'], length=2)['hex'] == '0000'
                assert debug.memory(BASE + build['state']['$signed']['rva'], length=2)['hex'] == '0080'
                assert debug.memory(BASE + build['state']['$flag']['rva'], length=2)['hex'] == '0100'
            registers = debug.registers()['general']
            if case.startswith('uil-text-') and status == 0:
                resource = 'lost' if case == 'uil-text-lose' else 'won'
                expected_pointer = BASE + build['resources'][resource]['rva'] + debug.delta
                assert int(registers['rdx'], 16) == expected_pointer
            else:
                assert int(registers['rdx'], 16) & 0xFFFFFFFF == (expected_outcome if status == 0 else status)
            if status == 0:
                # No client window is visible at notification entry in this fixture.
                assert debug.call('frame.probe') == {'available': False}
                assert debug.registers()['general'] == registers
                debug.delete_breakpoint(bp['breakpoint_id'])
                wait_for_client_window(debug)
                frame = debug.screenshot('outcome.png')
                assert frame['metadata']['width'] > 20 and frame['metadata']['height'] > 20
                exit_bp = debug.breakpoint(BASE + build['slots']['entry']['rva'] + 23)
                debug.click(frame['metadata']['width'] // 2, frame['metadata']['height'] - 14,
                            mode_id=frame['metadata']['mode_id'])
                assert debug.run(timeout_ms=60000)['outcome'] == 'breakpoint'
                finished = debug.registers()['general']
                assert int(finished['rdx'], 16) == 0 and int(finished['rcx'], 16) == 0
                debug.delete_breakpoint(exit_bp['breakpoint_id'])
            else:
                debug.delete_breakpoint(bp['breakpoint_id'])
            exited = debug.run(timeout_ms=60000)
            assert exited['outcome'] == 'exited' and exited['session']['exit_code'] == status
        assert debug.rpc.process.poll() is not None
