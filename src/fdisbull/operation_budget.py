"""Propagate a shared operation deadline to nested debugger RPC calls."""
from functools import wraps
from contextlib import contextmanager
import inspect
import time


class RpcAdmissionTimeout(TimeoutError):
    """The shared deadline refused a request before transport dispatch."""


@contextmanager
def deadline_scope(session, deadline, *, rpc_ms=5000, admission_ms=5000, cleanup_ms=5000):
    """Bound nested RPCs, refusing a fresh request that lacks its full allowance."""
    fields = ('_rpc_deadline', '_rpc_timeout_cap_ms', '_rpc_admission_ms', '_rpc_cleanup_grace_ms')
    old = {key: getattr(session, key, None) for key in fields}
    session._rpc_deadline = min(old['_rpc_deadline'], deadline) if old['_rpc_deadline'] is not None else deadline
    session._rpc_timeout_cap_ms = min(old['_rpc_timeout_cap_ms'] or 15000, rpc_ms)
    session._rpc_admission_ms = max(old['_rpc_admission_ms'] or 0, admission_ms)
    session._rpc_cleanup_grace_ms = cleanup_ms
    try:
        yield
    finally:
        for key, value in old.items(): setattr(session, key, value)


@contextmanager
def run_cleanup_scope(session):
    """Keep a bounded pause/stop-readback window after operation admission stops."""
    grace = getattr(session, '_rpc_cleanup_grace_ms', None)
    deadline = getattr(session, '_rpc_deadline', None)
    if not grace or deadline is None:
        yield
        return
    old_cap = getattr(session, '_rpc_timeout_cap_ms', None)
    old_admission = getattr(session, '_rpc_admission_ms', None)
    session._rpc_deadline = deadline + grace / 1000
    session._rpc_admission_ms = 0
    session._rpc_timeout_cap_ms = min(old_cap or 15000, 3000)
    try:
        yield
    finally:
        session._rpc_deadline = deadline
        session._rpc_admission_ms = old_admission
        session._rpc_timeout_cap_ms = old_cap


def rpc_budget(function):
    signature=inspect.signature(function)
    @wraps(function)
    def bounded(session,*args,**kwargs):
        bound=signature.bind(session,*args,**kwargs);bound.apply_defaults()
        milliseconds=bound.arguments['timeout_ms']
        if type(milliseconds) is not int or not 1<=milliseconds<=600000:
            raise ValueError('timeout_ms must be in 1..600000')
        previous=getattr(session,'_rpc_deadline',None)
        deadline=time.monotonic()+milliseconds/1000
        session._rpc_deadline=min(previous,deadline) if previous is not None else deadline
        try:return function(session,*args,**kwargs)
        finally:session._rpc_deadline=previous
    return bounded
