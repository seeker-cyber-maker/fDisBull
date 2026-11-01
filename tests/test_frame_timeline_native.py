"""Frame/input and durable-state contracts against a real prepared DOS backend."""
import base64
import hashlib
import os
from pathlib import Path
import runpy

import pytest

from fdisbull.project import Project
from fdisbull.debugger import DebugWorkspace


def raw(debug, address, length):
    result = debug.call('memory.read', {'address': {'space': 'linear', 'offset': f'0x{address:08X}'}, 'length': length})
    return base64.b64decode(result['data_base64'], validate=True)


def projection(debug):
    registers = debug.registers()
    cpu = {key: registers[key] for key in ('cpu_mode', 'general', 'segments', 'instruction_pointer', 'flags')}
    ds = int(registers['segments']['ds'], 16) * 16
    return cpu, raw(debug, ds, 65536)


@pytest.fixture
def frame_native(tmp_path, monkeypatch):
    executable = os.environ.get('FDISBULL_FRAME_DOSBOX')
    if not executable:
        if os.environ.get('FDISBULL_REQUIRE_FRAME_NATIVE'):
            pytest.fail('FDISBULL_FRAME_DOSBOX is required for frame qualification')
        pytest.skip('Set FDISBULL_FRAME_DOSBOX for real native frame checks')
    fixture = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/benchmark_frame_timeline.py'))
    game = tmp_path / 'game'; game.mkdir()
    target = game / 'FRAMES.COM'; target.write_bytes(fixture['authored_com']())
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    with Project.create(tmp_path / 'frames.fdb', target, image='com') as project:
        with project.debugger(executable, game, version=1) as debug:
            assert debug.rpc.capabilities.get('frame_timeline')
            debug.advance_frames(frames=4)
            yield project, debug, game


def test_full_frame_rewind_branches_input_and_exports_after_project_restart(frame_native, tmp_path):
    project, debug, game = frame_native
    original = (game / 'FRAMES.COM').read_bytes()
    workspace = DebugWorkspace(); workspace.sessions[debug.run_id] = debug
    start = workspace.invoke('debug-timeline-start', project.path, {'run': debug.run_id, 'max_frames': 8})
    initial = projection(debug)
    initial_png = debug.timeline_image('initial.png')
    debug.timeline_advance(frames=4, inputs=[
        {'frame': 0, 'edges': [{'key': 'a', 'pressed': True}]},
        {'frame': 2, 'edges': [{'key': 'a', 'pressed': False}]},
    ])
    endpoint = projection(debug)
    debug.timeline_rewind(frames=4)
    assert projection(debug) == initial
    restored_png = debug.timeline_image('restored.png')
    assert restored_png['sha256'] == initial_png['sha256']
    assert debug.timeline_status()['point'] == start['point']
    debug.timeline_advance(frames=4, inputs=[
        {'frame': 0, 'edges': [{'key': 'a', 'pressed': True}]},
        {'frame': 2, 'edges': [{'key': 'a', 'pressed': False}]},
    ])
    assert projection(debug) == endpoint
    pin = debug.timeline_pin('durable-frame.sav')
    debug.timeline_rewind(frames=4)
    debug.timeline_advance(frames=4, inputs=[
        {'frame': 0, 'edges': [{'key': 'b', 'pressed': True}]},
        {'frame': 2, 'edges': [{'key': 'b', 'pressed': False}]},
    ])
    assert projection(debug) != endpoint
    assert debug.timeline_status()['cursor'] == 4
    debug.load_anchor_stone(pin['artifact'])
    debug.advance_frames(frames=3)
    future = projection(debug)
    future_png = debug.call('video.screenshot')['sha256']
    path = project.path; executable = debug.metadata['executable']
    debug.close()
    assert debug.timeline_status()['retained_points'] == 0
    # Static version changes cannot alter the source or its cached native state.
    child = project.patch('1000:0100', '90', version=1)
    assert project.version(1)['sha256'] != child['sha256']
    assert (game / 'FRAMES.COM').read_bytes() == original
    with Project(path) as reopened:
        image = reopened.debug_export(restored_png['artifact'], tmp_path / 'offline-restored.png')
        assert hashlib.sha256(Path(image['output']).read_bytes()).hexdigest() == restored_png['sha256']
        with reopened.debugger(executable, game, version=1) as fresh:
            fresh.load_anchor_stone(pin['artifact'])
            assert projection(fresh) == endpoint
            assert not fresh.timeline_status()['valid']
            fresh.advance_frames(frames=3)
            assert projection(fresh) == future
            assert fresh.call('video.screenshot')['sha256'] == future_png


def test_held_frame_keys_survive_native_anchor_restore_without_reinjection(frame_native):
    _, debug, _ = frame_native
    debug.frame_inputs([{'key': 'shift', 'pressed': True}, {'key': 'a', 'pressed': True}])
    debug.advance_frames(frames=2)
    stone = debug.save_anchor_stone('held.sav')
    assert sorted(stone['metadata']['frame_keys']) == ['a', 'shift']
    debug.advance_frames(frames=48)
    endpoint = projection(debug)
    assert int.from_bytes(endpoint[1][0x204:0x206], 'little') > 1
    debug.frame_inputs([{'key': 'a', 'pressed': False}, {'key': 'shift', 'pressed': False}])
    debug.advance_frames(frames=3)
    debug.load_anchor_stone(stone['artifact'])
    assert sorted(debug.keyboard_state()['keyboard']['frame_keys']) == ['a', 'shift']
    debug.advance_frames(frames=48)
    assert projection(debug) == endpoint
    debug.frame_inputs([{'key': 'a', 'pressed': False}, {'key': 'shift', 'pressed': False}])


def test_preserved_runtime_ram_outside_original_com_mapping_and_full_recovery(frame_native):
    _, debug, _ = frame_native
    debug.timeline_start(max_frames=16)
    stone = debug.timeline_pin('base.sav')
    initial = projection(debug)
    debug.timeline_advance(frames=8)
    # BIOS timer low word is a guest-written, conventional-RAM location outside
    # the original COM mapping. It stands in for a caller-declared RNG range.
    current = raw(debug, 0x46c, 2)
    result = debug.timeline_rewind(frames=8, policy={
        'name': 'preserve-observed-bios-counter',
        'preserve_memory': [{'address': '0x46c', 'length': 2}],
        'allow_partial_resume': True,
    })
    assert raw(debug, 0x46c, 2) == current
    assert projection(debug) == initial
    assert result['execution_allowed'] and not result['resume_safe']
    debug.timeline_advance(frames=1)
    derived = debug.timeline_pin('derived.sav')
    assert derived['metadata']['timeline_experiment']['resume_safe'] is False
    debug.load_anchor_stone(stone['artifact'])
    assert projection(debug) == initial
    assert 'timeline_experiment' not in debug.metadata
