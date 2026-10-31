"""Experimental first-party console semantics and guarded code selection.

Only the exported subset is implemented. This is not a complete console runtime.
"""
from .model import Admission, Bindings, NativeBacking, RecoveredBlock, Refused, StaleSelection
from .recover import recover
from .mapping import CodeMap, Lease, Checkpoint
from .targets import emit_c, emit_javascript, compile_c

__all__ = ['Admission','Bindings','NativeBacking','RecoveredBlock','Refused',
           'StaleSelection','recover','CodeMap','Lease','Checkpoint',
           'emit_c','emit_javascript','compile_c']
from .compare import Difference, first_difference
__all__ += ['Difference', 'first_difference']

from .targets import emit_retained
__all__ += ['emit_retained']
