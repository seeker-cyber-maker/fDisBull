"""The live stack seam observes only a bounded stopped-thread SP window."""
import base64
from threading import RLock
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.wine_debugger import PEDebugSession


def _session(*, bits=64, pointer=0x8008, state='stopped', truncated=False):
    session = PEDebugSession.__new__(PEDebugSession)
    session.rpc = SimpleNamespace(lock=RLock())
    session.bits = bits
    session.run_id = 'authored-stack'
    session.version = {'id': 1}
    session.registers = lambda: {'general': {'rsp' if bits == 64 else 'esp': hex(pointer)}, 'thread': 17}
    calls = []
    def call(method, params=None):
        calls.append((method, params))
        if method == 'status':
            return {'state': state}
        assert method == 'read'
        data = bytes(range(params['length'] - int(truncated)))
        return {'data_base64': base64.b64encode(data).decode()}
    session.call = call
    return session, calls


@pytest.mark.parametrize('bits', [32, 64])
def test_stack_read_uses_selected_native_sp_without_project_projection(bits):
    session, calls = _session(bits=bits)
    result = session.stack_memory(offset=-8, length=16)
    assert result['runtime_address'] == '0x8000' and result['stack_pointer'] == '0x8008'
    assert result['hex'] == bytes(range(16)).hex() and result['thread'] == 17
    assert 'project_address' not in result
    assert calls == [('status', None), ('read', {'address': 0x8000, 'length': 16})]


def test_running_or_wrapping_stack_is_refused_before_memory_read():
    session, calls = _session(state='running')
    with pytest.raises(ValueError, match='stopped'):
        session.stack_memory()
    assert calls == [('status', None)]
    session, calls = _session(bits=32, pointer=0xfffffff8)
    with pytest.raises(ValueError, match='address width'):
        session.stack_memory(length=16)
    assert all(method != 'read' for method, _ in calls)


def test_stack_window_bounds_and_short_read_fail_closed():
    session, calls = _session()
    with pytest.raises(ValueError, match='4096'):
        session.stack_memory(offset=4090, length=16)
    assert calls == []
    session, _ = _session(truncated=True)
    with pytest.raises(DebuggerError, match='Incomplete'):
        session.stack_memory(length=8)
