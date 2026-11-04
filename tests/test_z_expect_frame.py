from pathlib import Path
import json

import pytest
from PIL import Image, ImageDraw

from test_z_controller import make_controller, SOURCE


@pytest.fixture
def frame_controller(tmp_path):
    controller, actions, project, session = make_controller(tmp_path, SOURCE)
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (12, 10), (100, 150, 200)).save(reference)
    actual = Image.new('RGB', (12, 10), (255, 0, 0))
    ImageDraw.Draw(actual).rectangle((2, 2, 5, 5), fill=(100, 150, 200))

    def export(artifact, path):
        project.exports.append((artifact, path))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        actual.save(path)

    project.debug_export = export
    yield controller, actions, session, actual
    controller.close()


def test_frame_check_uses_stable_rectangle_and_no_input_or_guest_run(frame_controller):
    controller, _, session, _ = frame_controller
    reply = controller.handle({'verb': 'expect-frame', 'params': {
        'reference': 'reference.png', 'box': [2, 2, 6, 6]}})
    assert reply['ok'], reply
    result = reply['result']
    assert result['matched'] is True and result['mean_error'] == 0
    assert result['box'] == [2, 2, 6, 6]
    assert Path(result['frame']['path']).is_file()
    assert Path(result['path']).is_file()
    assert json.loads(Path(result['path']).read_text())['mean_error'] == 0
    assert [name for name, _ in session.calls] == ['screenshot']
    assert 'scene' not in controller.ctx.state


def test_frame_mismatch_stops_python_route_and_retains_diagnostic(frame_controller):
    controller, actions, session, actual = frame_controller
    ImageDraw.Draw(actual).rectangle((2, 2, 5, 5), fill=(130, 150, 200))
    actions.write_text(SOURCE + '''
def guarded(ctx):
    ctx.expect_frame('reference.png', [2, 2, 6, 6], max_mean_error=9)
    ctx.run(guest_ms=50)
    ctx.state['continued'] = True
ACTIONS['guarded'] = {'handler': guarded}
''')
    reply = controller.handle({'verb': 'guarded'})
    assert not reply['ok']
    assert reply['error']['type'] == 'FrameExpectationError'
    result = reply['frame_expectation']
    assert result['matched'] is False and result['mean_error'] == 10
    assert result['reason'] == 'mean_error_exceeded'
    assert result['frame']['path'] in reply['error']['message']
    assert Path(result['frame']['path']).is_file()
    assert Path(result['path']).is_file()
    retained = json.loads(Path(result['path']).read_text())
    assert retained['mean_error'] == 10 and retained['frame'] == result['frame']
    assert 'continued' not in controller.ctx.state
    assert [name for name, _ in session.calls] == ['screenshot']


def test_frame_threshold_is_inclusive_and_list_describes_it(frame_controller):
    controller, _, session, actual = frame_controller
    ImageDraw.Draw(actual).rectangle((2, 2, 5, 5), fill=(130, 150, 200))
    result = controller.ctx.expect_frame('reference.png', (2, 2, 6, 6), max_mean_error=10)
    assert result['matched'] is True and result['mean_error'] == 10
    listing = controller.handle({'verb': 'list'})['result']['builtin_parameters']['expect-frame']
    assert listing['required'] == ['reference', 'box']
    assert listing['optional']['max_mean_error'] == 0
    assert [name for name, _ in session.calls] == ['screenshot']


@pytest.mark.parametrize('box', [None, [0, 0, 2], [-1, 0, 2, 2], [2, 0, 2, 2],
                                  [0, 2, 2, 1], [0, 0, 13, 10], [0, 0, 2.0, 2],
                                  [False, 0, 2, 2]])
def test_bad_box_fails_before_capturing(frame_controller, box):
    controller, _, session, _ = frame_controller
    reply = controller.handle({'verb': 'expect-frame', 'params': {
        'reference': 'reference.png', 'box': box}})
    assert not reply['ok'] and reply['error']['type'] == 'ValueError'
    assert 'box' in reply['error']['message']
    assert session.calls == []


def test_image_size_mismatch_keeps_actual_frame(frame_controller):
    controller, _, session, actual = frame_controller
    Image.new('RGB', (20, 10)).save(controller.ctx.root / 'reference.png')
    reply = controller.handle({'verb': 'expect-frame', 'params': {
        'reference': 'reference.png', 'box': [2, 2, 6, 6]}})
    assert not reply['ok']
    result = reply['frame_expectation']
    assert result['reason'] == 'image_size_mismatch'
    assert result['reference_size'] == [20, 10]
    assert result['frame_size'] == list(actual.size)
    assert result['mean_error'] is None
    assert Path(result['frame']['path']).is_file()
    assert [name for name, _ in session.calls] == ['screenshot']


@pytest.mark.parametrize('threshold', [-1, 256, True, '5'])
def test_bad_threshold_fails_before_capturing(frame_controller, threshold):
    controller, _, session, _ = frame_controller
    reply = controller.handle({'verb': 'expect-frame', 'params': {
        'reference': 'reference.png', 'box': [2, 2, 6, 6], 'max_mean_error': threshold}})
    assert not reply['ok'] and 'max_mean_error' in reply['error']['message']
    assert session.calls == []


def test_captured_recipe_stops_at_failed_frame_check(frame_controller):
    controller, _, session, actual = frame_controller
    actual.paste((0, 0, 0), (0, 0, 12, 10))
    captured = controller.handle({'verb': 'capture-action', 'params': {
        'name': 'checked-step', 'steps': [
            {'verb': 'expect-frame', 'params': {'reference': 'reference.png', 'box': [2, 2, 6, 6]}},
            {'verb': 'step'}]}})
    assert captured['ok'], captured
    reply = controller.handle({'verb': 'checked-step'})
    assert not reply['ok'] and reply['frame_expectation']['matched'] is False
    assert reply['recipe_progress'][0]['active_step'] == 0
    assert 'count' not in controller.ctx.state
    assert [name for name, _ in session.calls] == ['screenshot']
