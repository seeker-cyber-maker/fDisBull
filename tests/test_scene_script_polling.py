"""Reject malformed later scene timing before an earlier script side effect."""
import pytest
from fdisbull.debug_script import execute_script


@pytest.mark.parametrize('operation', ['scene-act', 'scene-click'])
@pytest.mark.parametrize('slice_ms', [0, 1001, True, 1.5, '1000'])
def test_scene_poll_interval_preflight_before_any_script_operation(operation, slice_ms):
    class Session:
        def status(self):
            raise AssertionError('A malformed later step allowed an earlier operation')
        def scene_act(self, scene, object, *, slice_ms=100):
            raise AssertionError('A malformed scene action was dispatched')
        scene_click = scene_act

    script = {'format': 'fdisbull-script-1', 'steps': [
        {'op': 'status'}, {'op': operation, 'scene': 'scene',
                          'object': 'step', 'slice_ms': slice_ms}]}
    with pytest.raises(ValueError, match='slice_ms'):
        execute_script(Session(), script)
