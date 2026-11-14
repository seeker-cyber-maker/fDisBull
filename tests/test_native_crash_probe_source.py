"""Pure owned-cleanup checks; never starts a native process or guest."""
import importlib.util
from pathlib import Path
import signal
from types import SimpleNamespace
import pytest
from fdisbull.dosbox_rpc import DebuggerShutdownError

SPEC = importlib.util.spec_from_file_location('recovered_crash_probe', Path(__file__).resolve().parents[1]/'scripts/check_native_crash_recovery.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def owner(receipt):
    def close(): raise DebuggerShutdownError(receipt)
    return SimpleNamespace(close=close, rpc=SimpleNamespace(process=SimpleNamespace(poll=lambda:-signal.SIGKILL)))


def test_expected_injected_owner_loss_retains_interrupted_receipt():
    receipt = dict(session_terminal=True, closed=False, process_reaped=True, process_returncode=-signal.SIGKILL)
    record = dict(failure_class='injected-owned-backend-SIGKILL', injection={'fired':True}, failed_backend_returncode=-signal.SIGKILL)
    with probe.injected_loss_scope(owner(receipt), record): pass
    assert record['failed_shutdown_receipt']==receipt
    assert record['failed_shutdown_receipt']['closed'] is False


@pytest.mark.parametrize('field,value', [('session_terminal',False),('closed',True),('process_reaped',False),('process_returncode',0)])
def test_unqualified_cleanup_is_not_swallowed(field,value):
    receipt = dict(session_terminal=True, closed=False, process_reaped=True, process_returncode=-signal.SIGKILL)
    receipt[field]=value
    record = dict(failure_class='injected-owned-backend-SIGKILL', injection={'fired':True}, failed_backend_returncode=-signal.SIGKILL)
    with pytest.raises(DebuggerShutdownError):
        with probe.injected_loss_scope(owner(receipt), record): pass
    assert 'failed_shutdown_receipt' not in record
