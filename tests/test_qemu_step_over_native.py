"""Finite authored CALL witnesses, including the exact prior DOSBox control.

This module is source-only until a separately reviewed owner gate admits its
exact host, binaries, media, nodes and lifecycle limits. The expected CALL,
return IP, AX and stack effects come from ten authored bytes, not the adapter's
decoded instruction or proposed return target.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
import sys

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from test_qemu_dosbox_parity_native import _ip, _word, parity_inputs


# 0100 XOR AX,AX; 0102 CALL 0108; 0105 NOP; 0106 JMP $;
# 0108 INC AX; 0109 RET. Exact previously passed legacy control bytes.
PROGRAM = bytes.fromhex('31c0e8030090ebfe40c3')
FORMAT = 'fdisbull-machine-step-over-1'


@pytest.fixture(scope='module', autouse=True)
def require_owned_step_over_gate(request):
    if os.environ.get('FDISBULL_REQUIRE_QEMU_STEP_OVER') != '1':
        pytest.skip('Requires the separately admitted native CALL step-over owner gate')
    assert getattr(request.config, '_fdisbull_step_over_owned_gate', None) == 'fdisbull-step-over-owned-gate-1'
    assert request.config.option.maxfail == 1
    assert not getattr(request.config.option, 'numprocesses', None)


def retain(directory, name, value):
    with (directory / name).open('x') as output:
        json.dump(value, output, indent=2)
        output.write('\n')


@contextmanager
def launch(tmp_path, runtime, backend):
    directory = tmp_path / backend
    directory.mkdir()
    source = directory / 'STEPOVER.COM'
    source.write_bytes(PROGRAM)
    process = None
    with Project.create(directory / 'call.fdb', source, image='com') as project:
        options = {} if backend == 'dosbox' else dict(
            backend='qemu-dos', dos_boot_image=str(runtime['boot']['image']),
            dos_mcopy=str(runtime['mcopy']), dos_startup_batch='FDAUTO.BAT',
            qemu_transport='pipe', qemu_firmware=os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE'),
            qemu_clock='virtual', qemu_retrace='precise', boot_timeout_ms=15000)
        try:
            with project.debugger(str(runtime['dosbox' if backend == 'dosbox' else 'qemu']),
                                  directory, **options) as debug:
                process = debug.rpc.process if backend == 'dosbox' else debug.vm.process
                assert _ip(debug.registers()) == 0x100
                yield directory, debug
        finally:
            if process is not None:
                assert process.poll() is not None, 'Original native owner was not reaped'
    assert source.read_bytes() == PROGRAM
    assert hashlib.sha256(runtime['boot_image'].read_bytes()).hexdigest() == runtime['boot_sha256']
    assert hashlib.sha256(runtime['boot']['image'].read_bytes()).hexdigest() == runtime['boot']['prepared_sha256']


@contextmanager
def dispatches(debug, directory):
    remote = debug.vm.gdb
    execute = remote.execute
    calls = []

    def observed(command, timeout_ms, **kwargs):
        row = dict(command=command, timeout_ms=timeout_ms)
        calls.append(row)
        reply, timed_out = execute(command, timeout_ms, **kwargs)
        row.update(native_reply=reply.decode('ascii'), timed_out=timed_out)
        return reply, timed_out

    remote.execute = observed
    try:
        yield calls
    finally:
        primary = sys.exception()
        remote.execute = execute
        try:
            retain(directory, 'native-dispatches.json', calls)
            if primary is not None and getattr(primary, 'result', None) is not None:
                retain(directory, 'native-error-result.json', primary.result)
        except BaseException as error:
            if primary is None:
                raise
            primary.add_note('CALL witness retention failed: ' + repr(error))


def at_call(debug):
    result = debug.step(mode='into', timeout_ms=5000)
    assert result['outcome'] == 'step' and result.get('format') != FORMAT
    before = debug.registers()
    assert _ip(before) == 0x102 and _word(before, 'ax', 'eax', 'rax') == 0
    return before


def raw_register(registers, name):
    value = registers['registers'][name]
    if isinstance(value, str):
        return int(value, 0) if value.lower().startswith('0x') else int(value, 16)
    assert type(value) is int
    return value


def base(debug):
    # Real-mode CS and offset are independent observed address inputs.
    return _word(debug.registers(), 'cs') * 16


def stack_slot(debug, registers):
    address = _word(registers, 'ss') * 16 + _word(registers, 'sp', 'esp', 'rsp') - 2
    return address, debug.memory(address, length=2, space='physical')['hex']


def accepted(debug, result, before, aliases, next_identifier, calls):
    assert result['format'] == FORMAT and result['mode'] == 'over' and result['count'] == 1
    assert result['step_over_completed'] is True and result['kind'] == 'call'
    assert result['outcome'] == result['native_result']['outcome'] == 'breakpoint'
    assert result['instruction_completed'] is None and result['owner_exited'] is False
    assert result['native_result']['session']['stop_reason']['native_reply'] == calls[-1]['native_reply']
    assert result['control']['released'] is True
    assert result['control']['breakpoint_id'] not in debug.breakpoints
    assert debug.breakpoints == aliases and debug.next_bp == next_identifier
    assert getattr(debug.vm, '_active_step_over', None) is None
    after = debug.registers()
    assert _ip(after) == 0x105 and _word(after, 'ax', 'eax', 'rax') == 1
    for name in ('cs', 'ss'):
        assert _word(after, name) == _word(before, name)
    assert _word(after, 'sp', 'esp', 'rsp') == _word(before, 'sp', 'esp', 'rsp')
    assert stack_slot(debug, before)[1] == '0501'
    return after


def legacy_step(debug, mode, kind):
    result = debug.call('execution.step', dict(mode=mode))
    assert result['stop_reason']['kind'] == kind and 'operation_id' not in result
    if kind == 'breakpoint':
        assert 'breakpoint_id' not in result['stop_reason']
    status = debug.call('session.status')
    assert status['state'] == 'stopped' and status['last_stop'] == result['stop_reason']
    assert status['session_id'] == result['session_id'] == result['registers']['session_id']
    assert status['state_revision'] == result['state_revision'] == result['registers']['state_revision']
    return result


def test_native_paired_direct_call_preserves_legacy_register_and_stack_contract(tmp_path, parity_inputs):
    observations = {}
    with launch(tmp_path, parity_inputs, 'dosbox') as (directory, debug):
        into = legacy_step(debug, 'into', 'step')
        before = debug.registers()
        assert _ip(before) == 0x102 and _word(before, 'eax', 'ax') == 0
        over = legacy_step(debug, 'over', 'breakpoint')
        after = debug.registers()
        assert _ip(after) == 0x105 and _word(after, 'eax', 'ax') == 1
        for name in ('cs', 'ss'):
            assert _word(after, name) == _word(before, name)
        assert _word(after, 'esp', 'sp') == _word(before, 'esp', 'sp')
        final = legacy_step(debug, 'into', 'step')
        assert _ip(debug.registers()) == 0x106
        retain(directory, 'legacy-call.json', dict(into=into, before=before, over=over, after=after, final=final))
        observations['dosbox'] = dict(return_ip=0x105, ax=1, stack_restored=True, next_ip=0x106)
    # The DOSBox owner is closed and reaped before QEMU construction.
    with launch(tmp_path, parity_inputs, 'qemu-dos') as (directory, debug):
        with dispatches(debug, directory) as calls:
            before = at_call(debug)
            aliases, next_identifier = deepcopy(debug.breakpoints), debug.next_bp
            result = debug.step(mode='over', timeout_ms=5000)
            retain(directory, 'qemu-call.json', result)
            accepted(debug, result, before, aliases, next_identifier, calls)
            assert debug.step(mode='into', timeout_ms=5000)['outcome'] == 'step'
            assert _ip(debug.registers()) == 0x106
            assert [row['command'] for row in calls] == ['s', 'c', 's']
            observations['qemu'] = dict(return_ip=0x105, ax=1, stack_restored=True, next_ip=0x106)
    assert observations['qemu'] == observations['dosbox']
    retain(tmp_path, 'paired-call.json', dict(program_sha256=hashlib.sha256(PROGRAM).hexdigest(),
        common=observations, differences='Backend/source/CS/stack addresses and raw schemas retain their actual identities.'))


@pytest.mark.parametrize('route', ['json', 'script'])
def test_native_call_over_public_routes(tmp_path, parity_inputs, route):
    with launch(tmp_path, parity_inputs, 'qemu-dos') as (directory, debug):
        before = at_call(debug)
        aliases, next_identifier = deepcopy(debug.breakpoints), debug.next_bp
        with dispatches(debug, directory) as calls:
            if route == 'json':
                workspace = DebugWorkspace()
                workspace.sessions[debug.run_id] = debug
                try:
                    response = respond(dict(id=1, method='debug-step', params=dict(
                        project=str(debug.project.path), run=debug.run_id, mode='over', timeout_ms=5000)),
                        debugger=workspace)
                    retain(directory, 'json-call.json', response)
                    assert response['ok'], response
                    result = response['result']
                finally:
                    workspace.sessions.clear()
            else:
                report = debug.script(dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                    dict(op='step', mode='over', timeout_ms=5000, **{'as': 'call'}),
                    dict(op='assert', value='$call.step_over_completed', equals=True),
                    dict(op='registers'),
                ]), timeout_ms=8000)
                retain(directory, 'script-call.json', report)
                assert report['ok'] and report['completed_steps'] == 3, report
                result = report['steps'][0]['result']
            accepted(debug, result, before, aliases, next_identifier, calls)
            assert [row['command'] for row in calls] == ['c']


@pytest.mark.parametrize('kind', ['breakpoint', 'fallthrough-alias', 'hook', 'watchpoint'])
def test_native_call_over_preserves_first_stop_and_owned_cleanup(tmp_path, parity_inputs, kind):
    with launch(tmp_path, parity_inputs, 'qemu-dos') as (directory, debug):
        before = at_call(debug)
        origin = base(debug)
        if kind == 'hook':
            register = next(name for name in ('rax', 'eax', 'ax') if name in before['registers'])
            unchanged = raw_register(before, register)
            point = debug.hook(origin + 0x108, space='linear', actions=[{
                'op': 'registers', 'registers': {register: {'expected': unchanged, 'value': unchanged}}}])
        else:
            address = stack_slot(debug, before)[0] if kind == 'watchpoint' else origin + (
                0x105 if kind == 'fallthrough-alias' else 0x108)
            point = debug.breakpoint(address, access='w' if kind == 'watchpoint' else 'x',
                                     length=2 if kind == 'watchpoint' else 1)
        aliases, next_identifier = deepcopy(debug.breakpoints), debug.next_bp
        with dispatches(debug, directory) as calls:
            if kind == 'breakpoint':
                report = debug.script(dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                    dict(op='step', mode='over', timeout_ms=5000),
                    dict(op='write-memory', address=origin + 0x105, data_hex='f4', expected_hex='90'),
                ]), timeout_ms=8000)
                retain(directory, 'interrupted-script.json', report)
                assert not report['ok'] and report['completed_steps'] == 0 and len(report['steps']) == 1
                result = report['steps'][0]['result']
                assert debug.memory(origin + 0x105, length=1, space='physical')['hex'] == '90'
            else:
                result = debug.step(mode='over', timeout_ms=5000)
            retain(directory, 'interrupted-call.json', result)
            assert result['format'] == FORMAT and result['step_over_completed'] is False
            outcome = 'breakpoint' if kind == 'fallthrough-alias' else kind
            assert result['outcome'] == result['native_result']['outcome'] == outcome
            assert result['control']['released'] is True
            assert result['control']['breakpoint_id'] not in debug.breakpoints
            assert debug.next_bp == next_identifier and getattr(debug.vm, '_active_step_over', None) is None
            if kind == 'hook':
                assert result['native_result']['hook_hits'][0]['hook'] == point['hook']
                assert _ip(debug.registers()) == 0x108 and _word(debug.registers(), 'rax', 'eax', 'ax') == 0
                assert debug.hooks()['hooks'] == []
            else:
                assert point['breakpoint_id'] in result['native_result']['breakpoints']
                assert debug.breakpoints == aliases
                debug.delete_breakpoint(point['breakpoint_id'])
            assert [row['command'] for row in calls] == ['c']


def test_native_call_over_displaces_an_actual_pending_call_hook(tmp_path, parity_inputs):
    with launch(tmp_path, parity_inputs, 'qemu-dos') as (directory, debug):
        origin = base(debug)
        # No register action is needed to manufacture the native pending hook;
        # a bounded repeat hook performs a checked no-op on AX at CALL entry.
        initial = debug.registers()
        register = next(name for name in ('rax', 'eax', 'ax') if name in initial['registers'])
        # XOR AX,AX clears only the low word. Keep the observed upper bits in
        # the checked no-op, without assuming a zero-extended boot register.
        at_entry = raw_register(initial, register) & ~0xFFFF
        point = debug.hook(origin + 0x102, space='linear', once=False, max_hits=2, actions=[{
            'op': 'registers', 'registers': {register: {'expected': at_entry, 'value': at_entry}}}])
        hit = debug.run(timeout_ms=5000, stop_on_hook=True)
        assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hook'] == point['hook']
        before = debug.registers()
        assert _ip(before) == 0x102 and _word(before, 'rax', 'eax', 'ax') == 0
        aliases, next_identifier = deepcopy(debug.breakpoints), debug.next_bp
        with dispatches(debug, directory) as calls:
            result = debug.step(mode='over', timeout_ms=5000)
            retain(directory, 'pending-call-hook.json', dict(initial_hit=hit, over=result))
            accepted(debug, result, before, aliases, next_identifier, calls)
            assert [row['command'] for row in calls] == ['s', 'c']
            assert debug.hooks()['hooks'][0]['hook'] == point['hook']
        debug.delete_hook(point['hook'])
