"""Source-assisted ORIGINAL game workloads, paired across DOSBox-X and QEMU.

Both targets are eligible repository fixtures and have no external assets or
saved files. These cases do not qualify asset I/O, mouse controls, exact clock
equivalence, full-raster equivalence, or a converted/replacement game.
Native execution is opt-in and belongs to the caller's finite guest controller.
"""
from copy import deepcopy
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline


FIXTURES = Path(__file__).parents[1] / 'fixtures/freeware-games'
DICE = FIXTURES / 'five-dice/original/learner/DICE.COM'
DICE_SHA = '10aa501c3856565427b6a3e48a3488b279778a7a4cd249b10529bd05c9e9bfcb'
SNAKE = FIXTURES / 'snake/original/learner/SNAKE.EXE'
SNAKE_SHA = 'f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be'


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def workload_runtime(tmp_path):
    """Reuse the accepted game lane's explicit immutable input paths."""
    configured = dict(dosbox=os.environ.get('FDISBULL_DOSBOX'),
        qemu=os.environ.get('FDISBULL_QEMU_DOS'),
        boot_image=os.environ.get('FDISBULL_QEMU_DOS_BOOT_IMAGE'),
        mcopy=os.environ.get('FDISBULL_QEMU_DOS_MCOPY') or shutil.which('mcopy'),
        firmware=os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE'))
    missing = [name for name, value in configured.items() if not value]
    if missing:
        message = 'Paired original workload inputs missing: ' + ', '.join(missing)
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail(message)
        pytest.skip(message)
    runtime = {name: Path(value).expanduser().resolve(strict=True)
               for name, value in configured.items() if name != 'mcopy'}
    # mtools is a multicall executable: its selected argv0 must remain mcopy.
    runtime['mcopy'] = Path(configured['mcopy']).expanduser().absolute()
    for name in ('dosbox', 'qemu', 'mcopy'):
        assert runtime[name].is_file() and os.access(runtime[name], os.X_OK)
    assert runtime['firmware'].is_dir()
    runtime['boot_sha256'] = _sha(runtime['boot_image'])
    return runtime


def _launch(project, directory, runtime, *, qemu, workspace_root=None):
    if not qemu:
        return project.debugger(str(runtime['dosbox']), directory)
    options = dict(backend='qemu-dos', dos_mcopy=str(runtime['mcopy']),
        qemu_transport='pipe', qemu_firmware=str(runtime['firmware']),
        qemu_clock='virtual', boot_timeout_ms=60000)
    if workspace_root is None:
        options.update(dos_boot_image=str(runtime['boot']['image']), dos_startup_batch='FDAUTO.BAT')
    else:
        component = os.environ.get('FDISBULL_FREEDOS_RUNTIME')
        checkpoint_tool = os.environ.get('FDISBULL_QEMU_IMG')
        missing = [name for name, value in [('FDISBULL_FREEDOS_RUNTIME', component),
                                           ('FDISBULL_QEMU_IMG', checkpoint_tool)] if not value]
        if missing:
            message = 'Snake directory launch requires ' + ', '.join(missing)
            if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
                pytest.fail(message)
            pytest.skip(message)
        options.update(freedos_runtime=component, qemu_checkpoint_tool=checkpoint_tool,
                       dos_directory=str(workspace_root))
    return project.debugger(str(runtime['qemu']), directory, **options)


def _advance(debug, *, qemu, milliseconds=750):
    if qemu:
        result = debug.clock_advance(milliseconds * 1_000_000, timeout_ms=10000)
        assert result['clock_budget']['deadline_reached'], result
    else:
        result = debug.run(timeout_ms=10000, guest_ms=milliseconds, fast_forward=True)
        assert result['outcome'] == 'guest_time', result
    return result


def _press(debug, key, *, qemu, terminal=False):
    accepted = debug.keyboard_press(key, hold_ms=80, gap_ms=80)
    assert accepted
    if terminal:
        result = (debug.clock_advance(750_000_000, timeout_ms=10000) if qemu else
                  debug.run(timeout_ms=10000, guest_ms=750, fast_forward=True))
        # The source breakpoint is earlier than the requested clock endpoint.
        # It is a positive stop, never a reason to replay this physical input.
        assert result['outcome'] == 'breakpoint', result
    else:
        result = _advance(debug, qemu=qemu)
    return result


def _base(debug, *, qemu):
    if not qemu:
        return debug.static_base
    process = debug.dos_process_info()
    assert process['state'] == 'active', process
    value = process['source_mapping']['runtime_base']
    return int(value, 0) if isinstance(value, str) else value


def _read(debug, offset, length, *, qemu):
    options = dict(length=length)
    if qemu:
        options['space'] = 'physical'
    return bytes.fromhex(debug.memory(_base(debug, qemu=qemu) + offset, **options)['hex'])


def _physical(debug, address, length, *, qemu):
    if qemu:
        return bytes.fromhex(debug.memory(address, length=length, space='physical')['hex'])
    result = debug.call('memory.read', dict(address=dict(space='linear', offset=f'0x{address:08x}'), length=length))
    return base64.b64decode(result['data_base64'], validate=True)


def _frame(project, debug, output, name):
    frame = debug.screenshot(name + '.png')
    receipt = project.debug_export(frame['artifact'], output / (name + '.png'))
    assert Path(receipt['output']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    return receipt


def _resolve_terminal_input(debug):
    """Cancel only an interrupted suffix and queue explicit held-key releases.

    The terminal key has already changed the game and reached its breakpoint.
    It must never be pressed again. The one later run dispatches only these
    explicit release edges while continuing to the real DOS exit.
    """
    observed = debug.input_schedule_observe()
    recovery = dict(observed=observed, cancelled=None, releases=[])
    if not observed['requires_resolution']:
        return recovery
    assert observed['state'] == 'cancelled'
    assert 1 <= observed['press']['dispatched_count'] <= 2
    cancelled = debug.input_cancel_pending()
    recovery['cancelled'] = cancelled
    retained = cancelled['retained_dispatched_holds']
    assert len(retained) <= 1  # Each terminal press has one key and no modifiers.
    state = debug.input_state()
    assert set(state['leases']) == set(retained) and state['pending_edges'] == 0
    for token in retained:
        lease = state['leases'][token]
        assert lease['device'] == 'keyboard' and lease['make'] == 'native_dispatched'
        assert lease['release'] is None
        recovery['releases'].append(debug.keyboard_key_up(token))
    queued = debug.input_state()
    assert not queued['schedule']['requires_resolution']
    assert queued['pending_edges'] == len(retained)
    assert all(row['event']['type'] == 'key' and row['event']['data']['down'] is False
               for row in queued['pending'])
    recovery['queued_release_edges'] = queued['pending_edges']
    return recovery


def _exit(debug, point, *, qemu):
    recovery = _resolve_terminal_input(debug) if qemu else None
    debug.delete_breakpoint(point['breakpoint_id'])
    result = debug.run(timeout_ms=10000, **({} if qemu else dict(guest_ms=1000, fast_forward=True)))
    assert result['outcome'] == 'guest_exit', result
    code = (result['process']['termination']['code'] if qemu else
            result['session']['stop_reason']['guest_exit']['requested_exit_code'])
    assert code == 0
    return dict(outcome='guest_exit', exit_code=code, terminal_input_recovery=recovery)


def _tree(root):
    return {str(path.relative_to(root)): _sha(path) for path in root.rglob('*') if path.is_file()}


def _dice_state(debug, *, qemu):
    # Verified original data tail: seed,total,scores[3],turn,rolls,holds,dice[5].
    raw = _read(debug, 0x2c9, 18, qemu=qemu)
    return dict(seed=int.from_bytes(raw[0:2], 'little'), total=int.from_bytes(raw[2:4], 'little'),
        scores=list(struct.unpack_from('<3H', raw, 4)), turn=raw[10], rolls=raw[11],
        holds=raw[12], dice=list(raw[13:18]))


def test_paired_original_five_dice_completed_game_and_rng(tmp_path, workload_runtime):
    """Seven physical commands complete SUM/PAIR/FIVE with identical native RNG."""
    original = DICE.read_bytes()
    assert len(original) == 731 and hashlib.sha256(original).hexdigest() == DICE_SHA
    assert original[2:8] == bytes.fromhex('c706c9033930')  # source-bound seed initializer
    assert original.count(bytes.fromhex('b8004ccd21')) == 1
    assert original.index(bytes.fromhex('b8004ccd21')) == 0x13b
    workload_runtime['boot'] = prepare_dos_baseline(workload_runtime['boot_image'],
        tmp_path / 'dice-baseline.img', workload_runtime['mcopy'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    assert _sha(workload_runtime['boot_image']) == workload_runtime['boot_sha256']
    expected = [
        dict(seed=27202,total=0,scores=[0,0,0],turn=0,rolls=1,holds=0,dice=[3,4,1,6,5]),
        dict(seed=27202,total=0,scores=[0,0,0],turn=0,rolls=1,holds=1,dice=[3,4,1,6,5]),
        dict(seed=37566,total=0,scores=[0,0,0],turn=0,rolls=2,holds=1,dice=[3,6,5,6,1]),
        dict(seed=57466,total=0,scores=[0,0,0],turn=0,rolls=3,holds=1,dice=[3,6,5,6,5]),
        dict(seed=57466,total=0,scores=[0,0,0],turn=0,rolls=3,holds=1,dice=[3,6,5,6,5]),
        dict(seed=58439,total=25,scores=[25,0,0],turn=1,rolls=1,holds=0,dice=[6,1,4,1,6]),
        dict(seed=51464,total=37,scores=[25,12,0],turn=2,rolls=1,holds=0,dice=[1,4,1,4,3]),
        dict(seed=51464,total=37,scores=[25,12,0],turn=3,rolls=1,holds=0,dice=[1,4,1,4,3]),
    ]
    paired = []
    for backend in ('dosbox', 'qemu-dos'):
        qemu = backend == 'qemu-dos'
        root = tmp_path / backend; root.mkdir()
        source = root / 'DICE.COM'; source.write_bytes(original)
        before = _tree(root)
        output = tmp_path / (backend + '-output'); output.mkdir()
        database = tmp_path / (backend + '.fdb')
        with Project.create(database, source, image='com') as project:
            project.analyze(max_instructions=4096)
            with _launch(project, root, workload_runtime, qemu=qemu) as debug:
                process = debug.vm.process if qemu else debug.rpc.process
                _advance(debug, qemu=qemu, milliseconds=300)
                observations = [_dice_state(debug, qemu=qemu)]
                assert observations == expected[:1]
                for index, key in enumerate(('1', 'r', 'r', 'r', 's', 's', 's'), 1):
                    point = debug.breakpoint(_base(debug, qemu=qemu) + 0x13b) if index == 7 else None
                    _press(debug, key, qemu=qemu, terminal=point is not None)
                    observations.append(_dice_state(debug, qemu=qemu))
                    assert observations[-1] == expected[index]
                image = _frame(project, debug, output, 'completed-scorecard')
                ended = _exit(debug, point, qemu=qemu)
                run = debug.run_id
            assert process.poll() is not None
        with Project(database) as reopened:
            row = next(row for row in reopened.debug_runs()['runs'] if row['id'] == run)
            assert row['ended'] is not None and row['metadata']['source_sha256'] == DICE_SHA
        assert _tree(root) == before and source.read_bytes() == original
        (output / 'observations.json').write_text(json.dumps(dict(backend=backend,
            source_sha256=DICE_SHA, states=observations, completion=ended, screenshot=image,
            external_assets=0, saved_game_files=0), indent=2) + '\n')
        paired.append(observations)
    assert paired[0] == paired[1] == expected
    assert _sha(DICE) == DICE_SHA and _sha(workload_runtime['boot_image']) == workload_runtime['boot_sha256']


def _snake_state(debug, *, qemu):
    # Original source MAP: DGROUP is module paragraph007Ah; public words start04B0h.
    raw = _read(debug, 0x7a0, 0x4cc, qemu=qemu)
    names = ('snake_length','direction','pending_direction','paused','game_status','score',
             'rng_seed','tick_count','key_events','mouse_events','frame_count','mouse_present',
             'food_cell','turn_queued')
    all_words = dict(zip(names, struct.unpack_from('<14H', raw, 0x4b0), strict=True))
    assert 1 <= all_words['snake_length'] <= 600
    selected = {key: all_words[key] for key in ('snake_length','direction','pending_direction','paused',
        'game_status','score','rng_seed','tick_count','food_cell','turn_queued')}
    selected['cells'] = list(struct.unpack_from('<' + 'H' * all_words['snake_length'], raw))
    return selected


def test_paired_original_snake_keyboard_growth_clock_and_exit(tmp_path, workload_runtime):
    """MZ nested-directory launch, paused growth, VGA, BIOS clock and real exit."""
    original = SNAKE.read_bytes()
    assert len(original) == 3851 and hashlib.sha256(original).hexdigest() == SNAKE_SHA
    header_size = int.from_bytes(original[8:10], 'little') * 16
    module = original[header_size:]
    exit_bytes = bytes.fromhex('b80300cd10b8004ccd21')
    assert header_size == 512 and module.count(exit_bytes) == 1
    assert module.index(exit_bytes) + 5 == 0xcd
    initial = dict(cells=[308,307,306],snake_length=3,direction=1,pending_direction=1,
        paused=1,game_status=0,score=0,rng_seed=4660,tick_count=0,food_cell=312,turn_queued=0)
    paired = []
    for backend in ('dosbox', 'qemu-dos'):
        qemu = backend == 'qemu-dos'
        root = tmp_path / backend; directory = root / 'GAMES/SNAKE'; directory.mkdir(parents=True)
        source = directory / 'SNAKE.EXE'; source.write_bytes(original)
        before = _tree(root)
        output = tmp_path / (backend + '-output'); output.mkdir()
        database = tmp_path / (backend + '.fdb')
        with Project.create(database, source) as project:
            project.analyze(max_instructions=6000)
            with _launch(project, directory, workload_runtime, qemu=qemu, workspace_root=root) as debug:
                process = debug.vm.process if qemu else debug.rpc.process
                if qemu:
                    workspace = debug.workspace_status()
                    assert workspace['mode'] == 'checkpointed'
                    assert workspace['source_dospath'] == 'GAMES\\SNAKE\\SNAKE.EXE'
                _advance(debug, qemu=qemu, milliseconds=300)
                observations = [_snake_state(debug, qemu=qemu)]
                assert observations[-1] == initial
                vram = _physical(debug, 0xa0000, 64000, qemu=qemu)
                for x,y,color in ((72,104,10),(64,104,2),(56,104,2),(104,104,12),(6,22,8),(8,24,0)):
                    assert vram[y*320+x] == color
                images = [_frame(project, debug, output, 'initial-graphics')]
                for tick in range(1,5):
                    _press(debug, 'n', qemu=qemu)
                    state = _snake_state(debug, qemu=qemu)
                    expected = dict(initial, tick_count=tick,
                        cells=[308+tick,307+tick,306+tick])
                    if tick == 4:
                        expected.update(cells=[312,311,310,309],snake_length=4,score=1,
                                        rng_seed=10589,food_cell=389)
                    assert state == expected
                    observations.append(state)
                vram = _physical(debug, 0xa0000, 64000, qemu=qemu)
                assert vram[104*320+104] == 10 and vram[120*320+240] == 12
                images.append(_frame(project, debug, output, 'ordinary-growth'))
                _press(debug, 'up', qemu=qemu)
                queued = _snake_state(debug, qemu=qemu)
                assert queued == dict(observations[-1],pending_direction=0,turn_queued=1)
                _press(debug, 'n', qemu=qemu)
                turned = dict(observations[-1], cells=[282,312,311,310], direction=0,
                              pending_direction=0,tick_count=5)
                assert _snake_state(debug, qemu=qemu) == turned
                observations.extend([queued,turned])
                _press(debug, 'r', qemu=qemu)
                assert _snake_state(debug, qemu=qemu) == initial
                observations.append(deepcopy(initial))
                _press(debug, 'p', qemu=qemu)
                running = _snake_state(debug, qemu=qemu)
                assert running['paused'] == 0 and running['game_status'] == 0 and running['tick_count'] > 0
                _press(debug, 'p', qemu=qemu)
                paused = _snake_state(debug, qemu=qemu)
                assert paused['paused'] == 1 and paused['game_status'] == 0
                assert paused['tick_count'] >= running['tick_count']
                _advance(debug, qemu=qemu, milliseconds=600)
                assert _snake_state(debug, qemu=qemu) == paused
                point = debug.breakpoint(_base(debug, qemu=qemu) + 0xcd)
                _press(debug, 'escape', qemu=qemu, terminal=True)
                assert _physical(debug, 0x449, 1, qemu=qemu) == b'\x03'
                ended = _exit(debug, point, qemu=qemu)
                run = debug.run_id
            assert process.poll() is not None
        with Project(database) as reopened:
            row = next(row for row in reopened.debug_runs()['runs'] if row['id'] == run)
            assert row['ended'] is not None and row['metadata']['source_sha256'] == SNAKE_SHA
        assert _tree(root) == before and source.read_bytes() == original
        (output / 'observations.json').write_text(json.dumps(dict(backend=backend,
            source_sha256=SNAKE_SHA, paired_manual_states=observations, running=running,
            paused=paused, completion=ended, screenshots=images, external_assets=0,
            saved_game_files=0, exact_cross_backend_timer_counts=False), indent=2) + '\n')
        paired.append(observations)
    assert paired[0] == paired[1]
    assert _sha(SNAKE) == SNAKE_SHA and _sha(workload_runtime['boot_image']) == workload_runtime['boot_sha256']
