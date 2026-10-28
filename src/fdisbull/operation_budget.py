"""Propagate a shared operation deadline to nested debugger RPC calls."""
from functools import wraps
import inspect
import time


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
