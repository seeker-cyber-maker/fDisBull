"""Named scene advancement against the real source-bound Gob process."""
import os
from pathlib import Path

import pytest
from PIL import Image

from fdisbull.project import Project
from fdisbull.scenes import SceneError


pytestmark = pytest.mark.skipif(
    not (os.environ.get('FDISBULL_GOB_NATIVE') and os.environ.get('FDISBULL_LOSTTIME_EN_DIR')),
    reason='requires patched Gob executable and private original Lost in Time English')


def counter(value):
    return {'compare': {'left': {'engine_variable': {'offset': 12637, 'type': 'i8'}},
                        'op': 'eq', 'right': value}}


def definition(frame, ready, outcome):
    return {'format': 'fdisbull-scene-1', 'width': 320, 'height': 200,
            'mode_id': frame['metadata']['mode_id'], 'reference': frame['artifact'],
            'context': {'state': 'hold poster regression', 'triggers': ['fresh native startup']},
            'match': {'constant': True},
            'objects': [{'name': 'hold.poster',
                         'context': {'state': 'original poster', 'triggers': ['physical inspection']},
                         'area': {'rect': [50, 59, 98, 94]}, 'point': [74, 76],
                         'visible': {'constant': True}, 'enabled': {'constant': True},
                         'ready': counter(ready), 'action': {'kind': 'click'},
                         'outcome': counter(outcome), 'outcome_phase': 'state',
                         'guest_ms': 6000, 'timeout_ms': 10000}]}


def test_native_named_action_wait_and_failed_wait_preserve_single_input(tmp_path, monkeypatch):
    game = Path(os.environ['FDISBULL_LOSTTIME_EN_DIR'])
    database = tmp_path/'named-gob.fdb'
    stored = None
    with Project.create(database, game/'lost.exe') as project:
        with project.debugger(os.environ['FDISBULL_GOB_NATIVE'], game,
                              backend='scummvm-gob', language='us', platform='dos') as engine:
            def advance(ms):
                result = engine.run(guest_ms=ms, timeout_ms=15000, max_instructions=1000000)
                assert result['outcome'] == 'guest_time', result
            advance(5000); engine.keyboard_press('space')
            advance(1500); engine.keyboard_press('escape')
            advance(6000); advance(20000)
            engine.click(160, 178); advance(1500)
            assert engine.read_variable(12637, signed=True)['value'] == 0
            assert engine.native_hooks_available is False
            assert engine.status()['native_hooks_available'] is False
            frame = engine.screenshot('hold.png', hooks=False)
            scene = project.debug_save_scene('gob-poster', definition(frame, 0, 1))
            result = engine.scene(scene['id']).act('hold.poster')
            assert result['status'] == 'matched' and result['complete'], result
            assert result['guest_elapsed_ms'] > 0
            assert result['input'] and engine.read_variable(12637, signed=True)['value'] == 1

            # Dismiss the observed response and force wait() to execute pending input.
            engine.click(160, 178); advance(1500)
            scene = project.debug_save_scene('gob-poster', definition(frame, 2, 3), parent=scene['id'])
            engine.click(74, 76)
            result = engine.scene(scene['id']).wait('hold.poster', guest_ms=6000, timeout_ms=10000)
            assert result['status'] == 'matched' and result['guest_elapsed_ms'] > 0, result
            assert engine.read_variable(12637, signed=True)['value'] == 2
            advance(1500)
            clicks = []
            original_click = engine.click
            def count_click(*args, **kwargs):
                receipt = original_click(*args, **kwargs)
                clicks.append(receipt)
                return receipt
            def failed_run(**kwargs):
                raise RuntimeError('injected host wait failure')
            # The same receipt guarantee applies to an actual queued popup
            # dismissal, before the main object's action is even attempted.
            popup = definition(frame, 2, 3)
            popup['handlers'] = [{'name': 'poster.response', 'when': counter(2),
                                  'action': {'kind': 'click'}, 'point': [160, 178],
                                  'outcome': {'constant': False}}]
            scene = project.debug_save_scene('gob-poster', popup, parent=scene['id'])
            with monkeypatch.context() as patch:
                patch.setattr(engine, 'click', count_click)
                patch.setattr(engine, 'run', failed_run)
                with pytest.raises(SceneError) as failure:
                    engine.scene(scene['id']).act('hold.poster', handle_popups=True)
            assert len(clicks) == 1
            assert failure.value.result['input'] == clicks[0]
            assert failure.value.result['handlers'] == clicks
            assert failure.value.result['handler_name'] == 'poster.response'
            assert failure.value.result['error_type'] == 'RuntimeError'
            assert failure.value.result['before_observation']
            advance(1500)  # Consume the one queued acknowledgment without replay.
            scene = project.debug_save_scene('gob-poster', definition(frame, 2, 3), parent=scene['id'])
            stored = engine.screenshot('poster-second.png', hooks=False)['artifact']
            clicks.clear()

            # A host-side failure after the main object's real queue operation
            # likewise retains its receipt and never submits it a second time.
            with monkeypatch.context() as patch:
                patch.setattr(engine, 'click', count_click)
                patch.setattr(engine, 'run', failed_run)
                with pytest.raises(SceneError) as failure:
                    engine.scene(scene['id']).act('hold.poster')
            assert len(clicks) == 1
            assert failure.value.result['input'] == clicks[0]
            assert failure.value.result['error_type'] == 'RuntimeError'
            assert 'injected host wait failure' in failure.value.result['error']
            assert failure.value.result['complete'] is False
            assert failure.value.result['observation']

            # Execute the already queued third inspection once. Then qualify a
            # real response pixel against the stored empty-caption reference.
            advance(1500)
            assert engine.read_variable(12637, signed=True)['value'] == 3
            response = engine.screenshot('poster-third.png', hooks=False)
            project.debug_export(frame['artifact'], tmp_path/'empty-caption.png')
            project.debug_export(response['artifact'], tmp_path/'third-caption.png')
            with Image.open(tmp_path/'empty-caption.png') as empty, Image.open(tmp_path/'third-caption.png') as text:
                samples = [(x, y) for y in range(150, 200) for x in range(320)
                           if empty.getpixel((x, y)) != text.getpixel((x, y))]
                assert samples, 'Native third response did not produce its caption'
                x, y = samples[len(samples)//2]
                response_pixel = {'pixels': {'samples': [{'x': x, 'y': y,
                                                          'rgb': list(text.getpixel((x, y)))[:3]}]}}
            popup = definition(frame, 3, 4)
            popup['handlers'] = [{'name': 'poster.third-response',
                                  'when': {'all': [counter(3), response_pixel]},
                                  'action': {'kind': 'click'}, 'point': [160, 178],
                                  'outcome': {'not': response_pixel}}]
            scene = project.debug_save_scene('gob-poster', popup, parent=scene['id'])
            success = engine.scene(scene['id']).act('hold.poster', handle_popups=True)
            assert success['status'] == 'matched' and success['complete'], success
            assert len(success['handlers']) == 2  # One acknowledgment plus its outcome.
            assert success['guest_elapsed_ms'] > 0
            assert engine.read_variable(12637, signed=True)['value'] == 4
    # This is project/image persistence, not an unsupported Gob process checkpoint.
    with Project(database) as project:
        assert project.debug_scene_info(scene['id'])['definition']['objects'][0]['name'] == 'hold.poster'
        project.debug_export(stored, tmp_path/'reopened-poster.png')
        assert (tmp_path/'reopened-poster.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
