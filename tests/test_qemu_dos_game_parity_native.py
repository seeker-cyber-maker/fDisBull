"""Bounded real-game comparisons across DOSBox and native QEMU.

The first opt-in test compares one physical Q move in the original hash-pinned
ATTT.COM. A second retained witness exercises QEMU-only cold recovery. The
paired full-round witness compares the same win/recovery/replay/reset/exit
workload and observed text characters in both backends. Stored screenshots
remain backend-specific; these cases do not claim whole-game or frame-timing
equivalence.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest
from PIL import Image

from fdisbull.project import Project
from fdisbull.dosbox_rpc import DebuggerError
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline


_ATTT = Path(__file__).parents[1] / "fixtures/freeware-games/tic-tac-toe/original/learner/ATTT.COM"
_ATTT_SHA256 = "b582a31d28d9a265c38d29ed09dffe0396f47e6bf4497569766c036f6674fc43"
_BOARD_OFFSET = 3  # First of nine initialized space bytes, immediately after the entry jump.


def _number(value):
    return int(value, 0) if isinstance(value, str) else value


@pytest.fixture
def game_runtime(tmp_path):
    required = os.environ.get("FDISBULL_REQUIRE_QEMU_DOS_OS") == "1"
    configured = {
        "dosbox": os.environ.get("FDISBULL_DOSBOX"),
        "qemu": os.environ.get("FDISBULL_QEMU_DOS"),
        "boot_image": os.environ.get("FDISBULL_QEMU_DOS_BOOT_IMAGE"),
        "mcopy": os.environ.get("FDISBULL_QEMU_DOS_MCOPY") or shutil.which("mcopy"),
    }
    missing = [key for key, value in configured.items() if not value]
    if missing:
        message = "Native game parity inputs missing: " + ", ".join(missing)
        if required:
            pytest.fail(message)
        pytest.skip(message)
    result = {
        "dosbox": Path(configured["dosbox"]).expanduser().resolve(strict=True),
        "qemu": Path(configured["qemu"]).expanduser().resolve(strict=True),
        "boot_image": Path(configured["boot_image"]).expanduser().resolve(strict=True),
        # mcopy may be an mtools multicall symlink; preserve its invocation name.
        "mcopy": Path(configured["mcopy"]).expanduser().absolute(),
    }
    for key in ("dosbox", "qemu", "mcopy"):
        assert result[key].is_file() and os.access(result[key], os.X_OK), result[key]
    assert result["boot_image"].is_file(), result["boot_image"]
    source = _ATTT.read_bytes()
    assert hashlib.sha256(source).hexdigest() == _ATTT_SHA256
    source_copy = tmp_path / "ATTT.COM"
    source_copy.write_bytes(source)
    boot_before = hashlib.sha256(result["boot_image"].read_bytes()).hexdigest()
    result["boot"] = prepare_dos_baseline(
        result["boot_image"], tmp_path / "game-dos-baseline.img", result["mcopy"],
        config=b"SWITCHES=/F\r\n" + BASELINE_CONFIG,
    )
    assert hashlib.sha256(result["boot_image"].read_bytes()).hexdigest() == boot_before
    result.update(source=source_copy, source_bytes=source, source_sha256=_ATTT_SHA256,
                  boot_sha256=boot_before)
    return result


def _launch_qemu(project, directory, runtime, *, checkpoint_tool=None):
    return project.debugger(
        str(runtime["qemu"]), directory,
        backend="qemu-dos",
        dos_boot_image=str(runtime["boot"]["image"]),
        dos_mcopy=str(runtime["mcopy"]),
        dos_startup_batch="FDAUTO.BAT",
        qemu_transport="pipe",
        qemu_firmware=os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE"),
        qemu_clock="virtual",
        qemu_checkpoint_tool=checkpoint_tool,
        boot_timeout_ms=15000,
    )


def _read_dosbox_image(debug, length):
    return bytes.fromhex(debug.memory(debug.static_base, length=length)["hex"])


def _read_qemu_image(debug, length):
    process = debug.dos_process_info()
    assert process["state"] == "active", process
    base = _number(process["source_mapping"]["runtime_base"])
    return bytes.fromhex(debug.memory(base, length=length, space="physical")["hex"])


def _play_one_move(debug, key, *, qemu):
    receipt = debug.keyboard_press(key, hold_ms=80, gap_ms=80)
    assert receipt
    if qemu:
        # Each engine advances its own guest clock; no timer values are compared.
        result = debug.clock_advance(750_000_000, timeout_ms=5000)
        assert result["clock_budget"]["deadline_reached"], result
        assert result["input_delivery"]["state"] == "dispatched", result
    else:
        debug.run(timeout_ms=5000, guest_ms=750, fast_forward=True)


def _observe_dosbox(project, runtime, directory):
    with project.debugger(str(runtime["dosbox"]), directory) as debug:
        assert debug.contexts()["selected"] == "dos-cpu"
        startup = _read_dosbox_image(debug, len(runtime["source_bytes"]))
        _play_one_move(debug, "q", qemu=False)
        moved = _read_dosbox_image(debug, len(runtime["source_bytes"]))
        run_id = debug.run_id
    return {"startup": startup, "after_q": moved, "run_id": run_id}


def _observe_qemu(project, runtime, directory):
    with _launch_qemu(project, directory, runtime) as debug:
        process = debug.dos_process_info()
        assert process["state"] == "active", process
        startup = _read_qemu_image(debug, len(runtime["source_bytes"]))
        _play_one_move(debug, "q", qemu=True)
        moved = _read_qemu_image(debug, len(runtime["source_bytes"]))
        run_id = debug.run_id
        native = debug.vm.process
    assert native.poll() is not None
    return {"startup": startup, "after_q": moved, "run_id": run_id}


def test_original_tic_tac_toe_one_physical_move_has_paired_com_state(
        tmp_path, game_runtime):
    source = game_runtime["source"]
    original = game_runtime["source_bytes"]
    with Project.create(tmp_path / "attt-parity.fdb", source, image="com") as project:
        # Needed by the established DOSBox source projection before it starts.
        project.analyze(max_instructions=4096)
        dosbox = _observe_dosbox(project, game_runtime, tmp_path)
        qemu = _observe_qemu(project, game_runtime, tmp_path)

        # Same exact original fixture, initial loaded image, and one documented
        # Player 1 Q move. The independent game contract maps Q to the top-left
        # square; ATTT's nine initialized board bytes begin at COM offset 0103h.
        assert dosbox["startup"] == qemu["startup"]
        assert dosbox["after_q"] == qemu["after_q"]
        assert dosbox["startup"][_BOARD_OFFSET:_BOARD_OFFSET + 9] == b" " * 9
        assert dosbox["after_q"][_BOARD_OFFSET:_BOARD_OFFSET + 9] == b"x" + b" " * 8
        assert source.read_bytes() == original
        runs = {row["id"]: row for row in project.debug_runs()["runs"]}
        for observation in (dosbox, qemu):
            row = runs[observation["run_id"]]
            assert row["metadata"]["source_sha256"] == _ATTT_SHA256
            # We closed both debuggers with the game still running. Their
            # terminal history labels differ; neither proves a guest DOS exit.
            assert row["ended"] is not None
        assert len(project.debug_runs()["runs"]) == 2
    assert hashlib.sha256(game_runtime["boot_image"].read_bytes()).hexdigest() == game_runtime["boot_sha256"]


def test_original_tic_tac_toe_cold_restore_winning_round_and_guest_exit(tmp_path, game_runtime):
    """A real round, reversible assisted RAM edit, cold restore and DOS exit."""
    tool = os.environ.get('FDISBULL_QEMU_IMG')
    if not tool:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail('Native game workflow needs the explicit checkpoint tool')
        pytest.skip('Set FDISBULL_QEMU_IMG for the cold game workflow')
    source = game_runtime['source']; database = tmp_path / 'attt-workflow.fdb'
    def board(debug):
        return _read_qemu_image(debug, 22)[3:12]
    with Project.create(database, source, image='com') as project:
        with _launch_qemu(project, tmp_path, game_runtime, checkpoint_tool=tool) as debug:
            assert board(debug) == b' ' * 9
            debug.keyboard_press('q', hold_ms=80, gap_ms=80)
            with pytest.raises(ValueError, match='schedule|released machine input'):
                debug.save_state()
            with pytest.raises(DebuggerError, match='no pending native input schedule'):
                debug.vm.qmp.call('x-fdisbull-instrumented-checkpoint-export')
            first = debug.clock_advance(750_000_000, timeout_ms=5000)
            assert first['clock_budget']['deadline_reached']
            assert first['input_delivery']['state'] == 'dispatched'
            assert board(debug) == b'x' + b' ' * 8
            for key in ('4', 'w', '5'):
                _play_one_move(debug, key, qemu=True)
            assert board(debug) == b'xx oo    '
            saved = debug.save_state()
            assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']
            static = project.regions(1)[0].start
            changed = debug.layer_patch('assisted-last-square', static + 11,
                expected_hex='20', data_hex='78', kind='ram')['layer']
            assert changed in debug.layers()['active'] and board(debug) == b'xx oo   x'
        # The old machine is closed. A new project and guest must load the
        # retained checkpoint; saved history alone does not reconnect a guest.
    with Project(database) as project:
        with _launch_qemu(project, tmp_path, game_runtime, checkpoint_tool=tool) as debug:
            old = debug.vm.process
            assert debug.load_state(saved['artifact'])['source_binding_restored']
            assert old.poll() is not None
            assert debug.layers()['active'] == [] and board(debug) == b'xx oo    '
            _play_one_move(debug, 'e', qemu=True)
            state = _read_qemu_image(debug, 22)
            assert state[3:12] == b'xxxoo    '
            assert state[17] == 1 and state[19] == 1 and state[21] == 5
            image = debug.screenshot()['artifact']
            destination = tmp_path / 'winning-round.png'
            project.debug_export(image, destination)
            assert destination.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            debug.load_state(saved['artifact'])
            assert board(debug) == b'xx oo    '
            _play_one_move(debug, 'e', qemu=True)
            assert _read_qemu_image(debug, 22) == state
            _play_one_move(debug, 'space', qemu=True)
            assert board(debug) == b' ' * 9
            debug.keyboard_press('escape', hold_ms=80, gap_ms=80)
            ended = debug.run(timeout_ms=5000)
            assert ended['outcome'] == 'guest_exit' and ended['process']['termination']['code'] == 0
            run_id = debug.run_id
            native = debug.vm.process
        assert native.poll() is not None
    with Project(database) as project:
        completed = next(row for row in project.debug_runs()['runs'] if row['id'] == run_id)
        assert completed['ended'] is not None
    assert hashlib.sha256(source.read_bytes()).hexdigest() == _ATTT_SHA256
    assert hashlib.sha256(game_runtime['boot_image'].read_bytes()).hexdigest() == game_runtime['boot_sha256']


def _round_state(debug, *, qemu):
    image = (_read_qemu_image if qemu else _read_dosbox_image)(debug, 22)
    # The original fixture's declared data layout: board, current player,
    # winner, starting player, the two win counters and completed move count.
    return dict(board=image[3:12].decode('ascii'), player=image[16], winner=image[17],
                starts=image[18], wins=[image[19], image[20]], turns=image[21])


def _text_screen(debug, *, qemu, diagnostic_dir, label):
    """Read public text-mode RAM, without treating rendered pixels as equal."""
    def read(address, length):
        if qemu:
            return bytes.fromhex(debug.memory(address, length=length, space='physical')['hex'])
        result = debug.call('memory.read', dict(
            address=dict(space='linear', offset=f'0x{address:08x}'), length=length))
        return base64.b64decode(result['data_base64'], validate=True)

    video = read(0x449, 7)
    mode, columns = video[0], int.from_bytes(video[1:3], 'little')
    rows = read(0x484, 1)[0] + 1
    page = int.from_bytes(video[5:7], 'little')
    expected = mode == 3 and columns == 80 and rows == 25 and page < 0x8000
    diagnostic = dict(bda_0449_hex=video.hex(), mode=mode, columns=columns,
                      rows=rows, page_offset=page)
    if not expected:
        # Preserve this backend observation rather than relaxing the source
        # oracle: ATTT prints with INT21h and contains no video-mode switch.
        try:
            captured = debug.screenshot(name=label+'-unexpected-video.png')
            output = diagnostic_dir / (label+'-unexpected-video.png')
            debug.project.debug_export(captured['artifact'], output)
            diagnostic['screenshot'] = dict(artifact=captured['artifact'],
                sha256=captured['sha256'], output=str(output))
        except Exception as error:
            diagnostic['capture_error'] = dict(type=type(error).__name__, message=str(error))
        (diagnostic_dir/(label+'-unexpected-video.json')).write_text(
            json.dumps(diagnostic, sort_keys=True, indent=2)+'\n')
    assert expected, diagnostic
    cells = read(0xb8000 + page, rows * columns * 2)[::2]
    # Attributes, fonts, raster dimensions and cursor blinking are renderer
    # observations. Compare the game characters, retaining every nonblank row.
    text = cells.decode('cp437').replace('\0', ' ')
    lines = [text[start:start+columns].rstrip() for start in range(0, len(text), columns)]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    assert lines
    return '\n'.join(lines)


def _stored_frame(project, debug, directory, label):
    captured = debug.screenshot(name=label+'.png')
    output = directory / (label+'-warm.png')
    project.debug_export(captured['artifact'], output)
    raw = output.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == captured['sha256']
    with Image.open(output) as image:
        assert image.format == 'PNG' and image.width > 0 and image.height > 0
        image.load()
        dimensions = list(image.size)
    return dict(artifact=captured['artifact'], sha256=captured['sha256'],
                label=label, dimensions=dimensions)


def _cold_frames(project, frames, directory, suffix):
    for frame in frames:
        output = directory / (frame['label']+'-'+suffix+'.png')
        project.debug_export(frame['artifact'], output)
        assert hashlib.sha256(output.read_bytes()).hexdigest() == frame['sha256']
        with Image.open(output) as image:
            assert image.format == 'PNG' and list(image.size) == frame['dimensions']
            image.load()


def _complete_round(root, runtime, *, qemu, checkpoint_tool):
    """Run the same physical-input workload through each public debugger."""
    root.mkdir()
    game = root / 'game'
    game.mkdir()
    source = game / 'ATTT.COM'
    source.write_bytes(runtime['source_bytes'])
    database = root / 'round.fdb'
    backend = 'qemu-dos' if qemu else 'dosbox'
    frames, observations, run_ids = [], [], []

    def launch(project):
        if qemu:
            return _launch_qemu(project, game, runtime, checkpoint_tool=checkpoint_tool)
        return project.debugger(str(runtime['dosbox']), game)

    def observe(debug, label):
        state = _round_state(debug, qemu=qemu)
        observations.append(dict(label=label, state=state, text=_text_screen(
            debug, qemu=qemu, diagnostic_dir=root, label=label)))
        return state

    with Project.create(database, source, image='com') as project:
        project.analyze(max_instructions=4096)
        with launch(project) as debug:
            run_ids.append(debug.run_id)
            if qemu:
                settled = debug.clock_advance(750_000_000, timeout_ms=5000)
                assert settled['clock_budget']['deadline_reached']
            else:
                debug.run(timeout_ms=5000, guest_ms=750, fast_forward=True)
            assert observe(debug, 'initial') == dict(board=' '*9, player=1, winner=0,
                starts=1, wins=[0, 0], turns=0)
            frames.append(_stored_frame(project, debug, root, 'initial'))
            for key, board in [('q', 'x        '), ('4', 'x  o     '),
                               ('w', 'xx o     '), ('5', 'xx oo    ')]:
                _play_one_move(debug, key, qemu=qemu)
                assert observe(debug, key)['board'] == board
            midpoint = observations[-1]['state']
            assert midpoint == dict(board='xx oo    ', player=1, winner=0,
                starts=1, wins=[0, 0], turns=4)
            frames.append(_stored_frame(project, debug, root, 'midpoint'))
            saved = debug.save_state(name='round-checkpoint.qcow2' if qemu else 'round-checkpoint.sav')
            assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']
        assert debug.closed

    # FDB, screenshots and exports live outside the immutable game directory.
    # In particular they must not change DOSBox's mounted-file state identity.
    with Project(database) as project:
        _cold_frames(project, frames, root, 'first-cold')
        assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']
        with launch(project) as debug:
            run_ids.append(debug.run_id)
            restored = debug.load_state(saved['artifact'])
            assert restored['artifact'] == saved['artifact']
            assert observe(debug, 'restored') == midpoint
            _play_one_move(debug, 'e', qemu=qemu)
            winning = observe(debug, 'win')
            assert winning == dict(board='xxxoo    ', player=1, winner=1,
                starts=1, wins=[1, 0], turns=5)
            assert 'WINS' in observations[-1]['text']
            frames.append(_stored_frame(project, debug, root, 'win'))
            debug.load_state(saved['artifact'])
            assert observe(debug, 'reloaded') == midpoint
            _play_one_move(debug, 'e', qemu=qemu)
            assert observe(debug, 'replayed-win') == winning
            assert observations[-1]['text'] == next(o['text'] for o in observations if o['label'] == 'win')
            frames.append(_stored_frame(project, debug, root, 'replayed-win'))
            _play_one_move(debug, 'space', qemu=qemu)
            assert observe(debug, 'reset') == dict(board=' '*9, player=2, winner=0,
                starts=2, wins=[1, 0], turns=0)
            frames.append(_stored_frame(project, debug, root, 'reset'))
            debug.keyboard_press('escape', hold_ms=80, gap_ms=80)
            ended = debug.run(timeout_ms=5000) if qemu else debug.run(
                timeout_ms=5000, guest_ms=750, fast_forward=True)
            assert ended['outcome'] == 'guest_exit'
            code = (ended['process']['termination']['code'] if qemu else
                    ended['session']['stop_reason']['guest_exit']['requested_exit_code'])
            assert code == 0
        assert debug.closed

    with Project(database) as cold:
        _cold_frames(cold, frames, root, 'final-cold')
        runs = cold.debug_runs()['runs']
        assert len(runs) == 2 and {row['id'] for row in runs} == set(run_ids)
        assert all(row['ended'] is not None and row['metadata']['source_sha256'] == _ATTT_SHA256
                   for row in runs)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == _ATTT_SHA256
    assert hashlib.sha256(runtime['boot_image'].read_bytes()).hexdigest() == runtime['boot_sha256']
    report = dict(backend=backend, observations=observations,
        terminal=dict(outcome='guest_exit', code=code), frames=frames,
        checkpoint=dict(artifact=saved['artifact'], sha256=saved['sha256']),
        source_sha256=_ATTT_SHA256, cold_run_count=2,
        timing_scope='backend-specific 750 ms bounded advances; no clock or frame-timing equivalence',
        frame_scope='decoded stored screenshots with exact cold artifact exports; no cross-backend pixel equality')
    (root/'workflow.json').write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    return report


def test_original_tic_tac_toe_complete_round_cold_restore_replay_reset_and_exit_are_paired(
        tmp_path, game_runtime):
    """Same complete round on both backends, each using its own native state."""
    tool = os.environ.get('FDISBULL_QEMU_IMG')
    if not tool:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail('Paired complete game workflow requires FDISBULL_QEMU_IMG')
        pytest.skip('Set FDISBULL_QEMU_IMG for paired cold game workflows')
    dosbox = _complete_round(tmp_path/'dosbox-round', game_runtime,
                            qemu=False, checkpoint_tool=tool)
    qemu = _complete_round(tmp_path/'qemu-round', game_runtime,
                          qemu=True, checkpoint_tool=tool)
    assert dosbox['observations'] == qemu['observations']
    assert dosbox['terminal'] == qemu['terminal']
    assert dosbox['source_sha256'] == qemu['source_sha256'] == _ATTT_SHA256


def _fresh_complete_round(root, runtime, *, qemu):
    """A separate fresh-game gate; no state save/load or recovery is performed."""
    root.mkdir()
    game = root/'game'
    game.mkdir()
    source = game/'ATTT.COM'
    source.write_bytes(runtime['source_bytes'])
    database = root/'fresh-round.fdb'
    observations, frames = [], []
    with Project.create(database, source, image='com') as project:
        project.analyze(max_instructions=4096)
        session = (_launch_qemu(project, game, runtime) if qemu else
                   project.debugger(str(runtime['dosbox']), game))
        with session as debug:
            run_id = debug.run_id

            def observe(label):
                state = _round_state(debug, qemu=qemu)
                observations.append(dict(label=label, state=state, text=_text_screen(
                    debug, qemu=qemu, diagnostic_dir=root, label=label)))
                return state

            def frame(label):
                captured = _stored_frame(project, debug, root, label)
                with Image.open(root/(label+'-warm.png')) as image:
                    rgb = image.convert('RGB')
                    # A decoded but uniformly black/blank surface is not a
                    # useful rendering witness for this text-and-board game.
                    assert any(low != high for low, high in rgb.getextrema()), captured
                    captured['pixel_sha256'] = hashlib.sha256(rgb.tobytes()).hexdigest()
                frames.append(captured)

            if qemu:
                settled = debug.clock_advance(750_000_000, timeout_ms=5000)
                assert settled['clock_budget']['deadline_reached']
            else:
                debug.run(timeout_ms=5000, guest_ms=750, fast_forward=True)
            assert observe('initial') == dict(board=' '*9, player=1, winner=0,
                starts=1, wins=[0, 0], turns=0)
            frame('initial')
            for key, board in [('q', 'x        '), ('4', 'x  o     '),
                               ('w', 'xx o     '), ('5', 'xx oo    ')]:
                _play_one_move(debug, key, qemu=qemu)
                assert observe(key)['board'] == board
            assert observations[-1]['state'] == dict(board='xx oo    ', player=1,
                winner=0, starts=1, wins=[0, 0], turns=4)
            frame('midpoint')
            _play_one_move(debug, 'e', qemu=qemu)
            assert observe('win') == dict(board='xxxoo    ', player=1, winner=1,
                starts=1, wins=[1, 0], turns=5)
            assert 'WINS' in observations[-1]['text']
            frame('win')
            _play_one_move(debug, 'space', qemu=qemu)
            assert observe('reset') == dict(board=' '*9, player=2, winner=0,
                starts=2, wins=[1, 0], turns=0)
            frame('reset')
            assert frames[1]['pixel_sha256'] != frames[2]['pixel_sha256']
            assert frames[2]['pixel_sha256'] != frames[3]['pixel_sha256']
            debug.keyboard_press('escape', hold_ms=80, gap_ms=80)
            ended = debug.run(timeout_ms=5000) if qemu else debug.run(
                timeout_ms=5000, guest_ms=750, fast_forward=True)
            assert ended['outcome'] == 'guest_exit'
            code = (ended['process']['termination']['code'] if qemu else
                    ended['session']['stop_reason']['guest_exit']['requested_exit_code'])
            assert code == 0
        assert debug.closed
    with Project(database) as cold:
        _cold_frames(cold, frames, root, 'cold-export')
        runs = cold.debug_runs()['runs']
        assert len(runs) == 1 and runs[0]['id'] == run_id and runs[0]['ended'] is not None
        assert runs[0]['metadata']['source_sha256'] == _ATTT_SHA256
    assert hashlib.sha256(source.read_bytes()).hexdigest() == _ATTT_SHA256
    assert hashlib.sha256(runtime['boot_image'].read_bytes()).hexdigest() == runtime['boot_sha256']
    report = dict(backend='qemu-dos' if qemu else 'dosbox', observations=observations,
        terminal=dict(outcome='guest_exit', code=code), frames=frames,
        source_sha256=_ATTT_SHA256, run_count=1, checkpoint_restore_performed=False,
        timing_scope='same input sequence with backend-specific 750 ms advances; no clock/frame-timing equivalence',
        frame_scope='nonuniform stored PNGs and changed winning/reset images; no cross-backend pixel equality')
    (root/'fresh-workflow.json').write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    return report


def test_original_tic_tac_toe_fresh_complete_round_reset_and_guest_exit_are_paired(
        tmp_path, game_runtime):
    """Fresh full-round compatibility is separate from the strict cold gate."""
    dosbox = _fresh_complete_round(tmp_path/'dosbox-fresh', game_runtime, qemu=False)
    qemu = _fresh_complete_round(tmp_path/'qemu-fresh', game_runtime, qemu=True)
    assert dosbox['observations'] == qemu['observations']
    assert dosbox['terminal'] == qemu['terminal']
    assert dosbox['source_sha256'] == qemu['source_sha256'] == _ATTT_SHA256
