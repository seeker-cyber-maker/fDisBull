"""Opt-in real DOSBox execution of authored event-search programs only."""
import hashlib
import os

import pytest

from fdisbull.project import Project


def backend():
    path = os.environ.get('FDISBULL_DOSBOX')
    if not path:
        pytest.skip('Supply FDISBULL_DOSBOX for native execution-event qualification')
    return path


def button_program():
    """Two clickable horizontal regions feed one authored register dispatcher."""
    code = bytearray()
    labels, fixups = {}, []

    def emit(value):
        code.extend(bytes.fromhex(value))

    def label(name):
        labels[name] = len(code) + 0x100

    def jump(opcode, name, width=1):
        emit(opcode)
        fixups.append((len(code), name, width))
        code.extend(bytes(width))

    # Mode 13h, mouse reset, explicit horizontal mouse coordinate range 0..319.
    emit('b81300cd1031c0cd33b8070031c9ba3f01cd33')
    label('poll')
    emit('b80300cd33f7c30100')
    jump('74', 'poll')
    emit('81f9a000')
    jump('73', 'button_b')
    emit('b80100')
    jump('eb', 'dispatch')
    label('button_b')
    emit('b80200')
    label('dispatch')
    jump('e8', 'handler', width=2)
    label('wait')
    jump('eb', 'wait')
    label('handler')
    emit('a3')
    sentinel_fixup = len(code)
    emit('0000c3')
    label('sentinel')
    emit('0000')
    code[sentinel_fixup:sentinel_fixup + 2] = labels['sentinel'].to_bytes(2, 'little')
    for offset, name, width in fixups:
        displacement = labels[name] - (0x100 + offset + width)
        code[offset:offset + width] = displacement.to_bytes(width, 'little', signed=True)
    return bytes(code), labels


def test_native_predicates_stop_before_effect_and_preserve_hook(tmp_path):
    executable = backend()
    disk = tmp_path / 'disk'
    disk.mkdir()
    target = disk / 'EVENT.COM'
    # MOV AX,7; MOV [120],AX; INC AX; JMP 10b; NOP; NOP; NOP; JMP $.
    original = bytes.fromhex('b80700a3200140eb02909090ebfe').ljust(34, b'\0')
    target.write_bytes(original)
    database = tmp_path / 'event.fdb'
    with Project.create(database, target, image='com') as project:
        project.analyze(max_instructions=64)
        with project.debugger(executable, disk) as debug:
            initial = debug.trace_until({'kind': 'register', 'register': 'ip', 'equals': 0x100},
                action={'op': 'click', 'x': 20, 'y': 20})
            assert initial['matched'] and initial['steps'] == 0
            assert initial['action']['dispatch'] == 'skipped_initial_match'
            first = debug.trace_until({'kind': 'register', 'register': 'ax', 'equals': 7})
            assert first['matched'] and first['exact_stop'] and first['steps'] == 1
            assert int(debug.registers()['instruction_pointer'], 16) == 0x103
            assert debug.memory('1000:0120', length=2)['hex'] == '0000'
            changed = debug.trace_until({'kind': 'region-change'}, regions=[
                dict(id='setup', space='project', start=0x10100, end=0x10106),
                dict(id='body', space='project', start=0x10106, end=0x1010e)])
            assert changed['matched'] and changed['steps'] == 1
            assert int(debug.registers()['instruction_pointer'], 16) == 0x106
            assert debug.memory('1000:0120', length=2)['hex'] == '0700'
            transferred = debug.trace_until({'kind': 'nonsequential'})
            assert transferred['matched'] and transferred['steps'] == 2
            assert int(debug.registers()['instruction_pointer'], 16) == 0x10b
            mnemonic = debug.trace_until({'kind': 'mnemonic', 'equals': 'nop'})
            assert mnemonic['matched'] and mnemonic['steps'] == 0
            budget = debug.trace_until({'kind': 'register', 'register': 'ax', 'equals': 99}, max_steps=3)
            assert budget['outcome'] == 'step_budget' and budget['steps'] == 3
            before_hooks = debug.hook('1000:010c', actions=[{'op': 'redirect', 'address': '1000:010b'}], once=True)
            hook_state = debug.hooks()
            stop = debug.trace_until({'kind': 'register', 'register': 'ip', 'equals': 0x10c})
            assert stop['outcome'] == 'foreign_stop' and not stop['matched']
            assert stop['attempted_steps'] == 0 and debug.hooks() == hook_state
            debug.delete_hook(before_hooks['hook'])
            historical = project.event_trace_query(first['trace_artifact'],
                predicate={'kind': 'register', 'register': 'ax', 'equals': 7})
            assert historical['matched_count'] == 1
            assert 'Retrospective' in historical['scope']
            assert int(debug.registers()['instruction_pointer'], 16) == 0x10c
        search = project.event_search_start(first['trace_artifact'], feature='register-value', registers=['ax'])
        saved = project.event_search_results(search['artifact'])
        assert saved['candidate_count'] == 2
    with Project(database) as project:
        assert project.event_search_results(search['artifact']) == saved
    assert hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(original).digest()


def test_native_click_trials_keep_shared_handler_register_value(tmp_path):
    executable = backend()
    disk = tmp_path / 'disk'
    disk.mkdir()
    original, labels = button_program()
    target = disk / 'BUTTONS.COM'
    target.write_bytes(original)
    database = tmp_path / 'buttons.fdb'
    with Project.create(database, target, image='com') as project:
        project.analyze(max_instructions=128)
        with project.debugger(executable, disk) as debug:
            # Let the graphics mode commit before capturing full native state.
            assert debug.run(guest_ms=50, timeout_ms=10000, fast_forward=True)['outcome'] == 'guest_time'
            point = debug.breakpoint(f"1000:{labels['poll']:04x}")
            assert debug.run(timeout_ms=10000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            debug.call('execution.step', {'mode': 'into'})
            checkpoint = debug.save_state(max_bytes=64 * 1024 * 1024)
            trials = {}
            for label, x in [('A:1', 40), ('A:2', 40), ('B:1', 240), ('idle', None)]:
                debug.load_state(checkpoint['artifact'])
                # Restore invalidates the completed video frame. Advance a
                # bounded idle interval, then return to the same polling PC.
                assert debug.run(guest_ms=40, timeout_ms=10000, fast_forward=True)['outcome'] == 'guest_time'
                ready = debug.breakpoint(f"1000:{labels['poll']:04x}")
                assert debug.run(timeout_ms=10000)['outcome'] == 'breakpoint'
                debug.delete_breakpoint(ready['breakpoint_id'])
                debug.call('execution.step', {'mode': 'into'})
                options = {} if x is None else {'action': {'op': 'click', 'x': x, 'y': 40}}
                result = debug.trace_until({'kind': 'pc-range', 'space': 'project',
                    'start': 0x10000 + labels['handler'] + 3, 'end': 0x10000 + labels['handler'] + 4},
                    max_steps=500, timeout_ms=10000, label=label, **options)
                assert result['outcome'] == ('step_budget' if x is None else 'predicate'), result
                if x is not None:
                    expected = 1 if label.startswith('A') else 2
                    assert debug.memory(f"1000:{labels['sentinel']:04x}", length=2)['hex'] == f'{expected:02x}00'
                    assert result['action']['dispatch'] == 'queued'
                trials[label] = result['trace_artifact']
            registers = project.event_search_start(trials['A:1'], feature='register-value',
                registers=['ax'], label='A:1')
            sites = project.event_search_start(trials['A:1'], label='A:1')
            for trial, mode in [('A:2', 'retain'), ('B:1', 'exclude'), ('idle', 'exclude')]:
                registers = project.event_search_refine(registers['artifact'], trials[trial], mode=mode, label=trial)
                sites = project.event_search_refine(sites['artifact'], trials[trial], mode=mode, label=trial)
            register_results = project.event_search_results(registers['artifact'])
            site_results = project.event_search_results(sites['artifact'])
            handler = 0x10000 + labels['handler']
            assert any(row['site']['address'] == handler and row['value'] == 1
                       for row in register_results['rows']), register_results
            assert all(row['site']['address'] != handler for row in site_results['rows'])
        saved = project.event_search_results(registers['artifact'])
    with Project(database) as project:
        assert project.event_search_results(registers['artifact']) == saved
    assert target.read_bytes() == original


def test_native_bios_keyboard_status_callback_does_not_invent_input(tmp_path):
    executable = backend()
    disk = tmp_path / 'disk'
    disk.mkdir()
    target = disk / 'NOKEY.COM'
    # Force ZF=0, then INT16/AH=1 must set ZF=1 when no key is present.
    # The skipped-callback raw-step defect would follow the wrong JNZ path.
    target.write_bytes(bytes.fromhex('b8000109c0cd167508c70630010000eb06c70630010100ebfe').ljust(50, b'\0'))
    with Project.create(tmp_path / 'keyboard.fdb', target, image='com') as project:
        with project.debugger(executable, disk) as debug:
            result = debug.trace_until({'kind': 'pc-range', 'space': 'project',
                'start': 0x10117, 'end': 0x10119}, max_steps=100, timeout_ms=10000)
            assert result['matched'] and result['exact_stop'], result
            assert debug.memory('1000:0130', length=2)['hex'] == '0000'


def test_native_guest_exit_callback_is_terminal_not_a_predicate_match(tmp_path):
    executable = backend()
    disk = tmp_path / 'disk'
    disk.mkdir()
    target = disk / 'FINISH.COM'
    target.write_bytes(bytes.fromhex('b8004ccd2190ebfe'))
    with Project.create(tmp_path / 'exit.fdb', target, image='com') as project:
        with project.debugger(executable, disk) as debug:
            result = debug.trace_until({'kind': 'register', 'register': 'ax', 'equals': 0xffff},
                                       max_steps=100, timeout_ms=10000)
            assert result['outcome'] == 'exited', result
            assert not result['matched'] and not result['complete'] and not result['exact_stop']
            assert result['trace_artifact']
