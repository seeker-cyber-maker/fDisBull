"""Opt-in native acceptance for QEMU scene-1 retained-frame waits.

Uses the authored video witness and the existing pinned QEMU clock/boot
fixtures. The stored scene is built from a captured native source raster; the
wait then checks its declared pixels through the retained native frame probe.
"""
from __future__ import annotations

import os

import pytest

from support.qemu_video_frame_fixture import HEIGHT, WIDTH, expected_rgb, frame_schedule
from fdisbull.scenes import SceneError
from test_qemu_clock_budget_native import clock_disk, clock_runtime
from test_qemu_video_frame_native import (
    _assert_frame, _complete, _timing, video_witness,
)


GATE = 'FDISBULL_REQUIRE_QEMU_SCENE1_FRAME_WAIT'
pytestmark = pytest.mark.skipif(
    os.environ.get(GATE) != '1',
    reason=f'Set {GATE}=1 with the pinned native QEMU clock and DOS boot inputs',
)


def _scene(project, reference, metadata, rgb, *, name='native-frame-wait'):
    # A small, deliberately discriminating native sample set. SceneHandle's
    # shared evaluator issues the actual retained-frame pixel probe.
    points = ((0, 0), (1, 100), (319, 199))
    samples = [dict(x=x, y=y,
                    rgb=list(rgb[(y * WIDTH + x) * 3:(y * WIDTH + x + 1) * 3]))
               for x, y in points]
    context = dict(state='authored QEMU VGA source raster',
                   triggers=['authored video-frame witness and retained native probe'])
    return project.debug_save_scene(name, dict(
        format='fdisbull-scene-1', width=WIDTH, height=HEIGHT,
        mode_id=metadata['mode_id'], reference=reference, context=context,
        match={'pixels': {'samples': samples}},
        objects=[dict(name='raster', context=context,
            area={'rect': [0, 0, 1, 1]}, point=[0, 0],
            visible={'constant': True}, ready={'constant': True},
            enabled={'constant': True}, action={'kind': 'click'},
            outcome={'constant': True})]))


def test_native_scene1_frame_wait_matches_immediately_and_honors_first_stop(
        video_witness):
    with video_witness() as (project, debug, symbols, _):
        before = debug.clock_observe()
        started = debug.video_frame_start(timeout_ms=1000)
        schedule = frame_schedule(_timing(debug, symbols), before['virtual_ns'])
        native = _complete(debug, schedule)
        frame = _assert_frame(native, schedule, expected_rgb())
        captured = debug.capture_video_frame(
            'scene-wait-reference.png', stream=started['stream'],
            frame_id=frame['frame-id'], timeout_ms=1000)
        metadata = captured['metadata']
        assert metadata['source'] == 'qemu_completed_source_raster'
        assert metadata['frame_id'] == frame['frame-id']
        saved = _scene(project, captured['artifact'], metadata, expected_rgb())
        assert saved['definition']['format'] == 'fdisbull-scene-1'

        matched = debug.scene_wait(saved['id'], object='raster',
                                   guest_ms=5, slice_ms=1, timeout_ms=5000)
        assert matched['status'] == 'matched' and matched['complete']
        assert matched['wait']['outcome'] == 'predicate'
        assert matched['wait']['guest_elapsed_ns'] == 0
        assert matched['wait']['polls'] == [dict(
            frame_id=frame['frame-id'], status='matched')]
        assert matched['wait']['runs'] == []
        assert matched['frame']['format'] == 'rgb-samples'
        assert matched['frame']['frame_id'] == frame['frame-id']
        assert matched['frame']['samples'] == [
            dict(x=0, y=0, rgb=[255, 0, 0]),
            dict(x=1, y=100, rgb=[4, 85, 170]),
            dict(x=319, y=199, rgb=[0, 255, 0]),
        ]

        # Make a scene that cannot match, then stop the first wait slice at the
        # guest's dispatch instruction. The native stop must end the wait
        # without a second frame probe.
        wrong = bytearray(expected_rgb())
        wrong[(100 * WIDTH + 1) * 3] ^= 1
        stopped_scene = _scene(project, captured['artifact'], metadata, bytes(wrong),
                               name='native-frame-wait-stop')
        point = debug.breakpoint(symbols['dispatch'])
        try:
            with pytest.raises(SceneError) as failure:
                debug.scene_wait(stopped_scene['id'], object='raster',
                                 guest_ms=5, slice_ms=1, timeout_ms=5000)
            result = failure.value.result
            assert result and result['status'] == 'stopped', result
            assert result['wait']['polls'] == [dict(
                frame_id=frame['frame-id'], status='mismatch')]
            assert len(result['wait']['runs']) == 1
            assert result['wait']['runs'][0]['outcome'] == 'breakpoint'
            assert result['frame']['frame_id'] == frame['frame-id']
        finally:
            debug.delete_breakpoint(point['breakpoint_id'])
