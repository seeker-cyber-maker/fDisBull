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


def test_unqualified_ne_register_write_is_rejected_before_earlier_script_effect():
    class Session:
        register_edits_available = False
        def status(self):
            raise AssertionError('An unsupported later operation allowed an earlier effect')
        def write_registers(self, registers):
            raise AssertionError('Unqualified register write dispatched')
    script = {'format': 'fdisbull-script-1', 'steps': [
        {'op': 'status'}, {'op': 'write-registers', 'registers': {
            'eax': {'expected': 0, 'value': 1}}}]}
    with pytest.raises(ValueError, match='not qualified'):
        execute_script(Session(), script)
