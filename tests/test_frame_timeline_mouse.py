"""Mouse input must be released before a checkpoint can promise resumability."""
from types import SimpleNamespace

import pytest

from fdisbull.debugger import DebugSession
from test_debug_timeline import Session, start


@pytest.mark.parametrize('field', ['buttons', 'owned_buttons', 'pending_release_buttons', 'release_pending'])
def test_timeline_refuses_mouse_input_before_capture(field):
    debug = Session()
    original = debug.call

    def call(method, params=None):
        if method == 'input.mouse.state':
            return {'mouse': {field: 1}}
        return original(method, params)

    debug.call = call
    try:
        with pytest.raises(ValueError, match='mouse'):
            start(debug)
        assert debug.captures == 0 and debug.cpu == 0
        assert not debug.closed
    finally:
        debug.db.close()


@pytest.mark.parametrize('field', ['buttons', 'owned_buttons', 'pending_release_buttons', 'release_pending'])
def test_manual_checkpoint_refuses_mouse_input_before_native_save(field):
    calls = []

    def call(method, params=None):
        calls.append(method)
        assert method == 'input.mouse.state'
        return {'mouse': {field: 1}}

    debug = SimpleNamespace(rpc=SimpleNamespace(capabilities={'save_states': True}), call=call)
    with pytest.raises(ValueError, match='mouse'):
        DebugSession._capture_native_checkpoint(debug)
    assert calls == ['input.mouse.state']
