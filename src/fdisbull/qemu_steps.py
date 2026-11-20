"""Compose observed native step stops without claiming instruction retirement."""
from copy import deepcopy
import re
import time

from .dosbox_rpc import DebuggerError


MAX_STEP_COUNT = 10000
FORMAT = 'fdisbull-machine-step-sequence-1'


def validate_step_count(count):
    if type(count) is not int or not 1 <= count <= MAX_STEP_COUNT:
        raise ValueError('Machine step count must be an integer in 1..10000')


def validate_step_parameters(*, count=1, timeout_ms=10000):
    validate_step_count(count)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Machine step timeout_ms must be an integer in 1..600000')


def admit_step_sequence_input(context):
    # These checks are passive. Run before lock/guard admission, then again
    # under the owned lock. Ordinary one-step behavior remains unchanged.
    context._execution_input_preflight('s')
    if context._input_schedule_bound():
        raise ValueError('Counted steps require scheduled input to be resolved first')


def _observed_step(context, result):
    state = result.get('session')
    if not isinstance(state, dict):return False
    reason = state.get('stop_reason')
    if not isinstance(reason, dict) or not isinstance(reason.get('native_reply'), str):return False
    return (result.get('timed_out') is False and state.get('state') == 'stopped'
            and reason.get('kind') == 'step' and reason.get('classification_complete') is not False
            and re.match(r'^[TS]05(?:;|$|thread:)', reason.get('native_reply', '')) is not None
            and isinstance(result.get('registers'), dict)
            and result.get('breakpoints') == []
            and getattr(context.vm, 'machine_stopped', False)
            and not getattr(context.vm, '_fdisbull_control_quarantine', None))


def step_sequence(context, count, deadline):
    """Use the existing execution adapter once per requested native stop.

The caller owns one lock and an intersected absolute session/transport bound.
Each successful child still runs the normal source/lifecycle/publication path;
the first non-step or uncertain observation terminates this composition.
"""
    admit_step_sequence_input(context)
    completed, attempted, terminal, uncertain = [], 0, None, False

    def receipt(outcome, *, failure=None):
        return dict(format=FORMAT, context='machine', requested_count=count,
                    completed_count=len(completed), attempted_count=attempted,
                    complete=failure is None and len(completed) == count,
                    outcome=outcome,
                    timed_out=(outcome == 'timeout' or isinstance(failure, TimeoutError)
                               or isinstance(terminal, dict) and terminal.get('timed_out') is True),
                    steps=completed, terminal_stop=deepcopy(terminal),
                    instruction_completed=None,
                    semantics='Count fully observed native step stops, not retired instructions. '
                              'attempted_count counts execution-adapter calls, not proven native dispatches. '
                              'steps retains the completed prefix; terminal_stop preserves the last known '
                              'observation, including a first non-step stop or failed observation.')

    try:
        for _ in range(count):
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining < 1:
                return receipt('timeout')
            attempted += 1
            # Use the selected adapter, including DOS process return and source
            # lifecycle handling. Never bypass it with a raw GDB loop.
            terminal = context._execute('s', remaining)
            if not isinstance(terminal, dict) or not isinstance(terminal.get('outcome'), str):
                uncertain = True
                raise DebuggerError('Native step returned an incomplete stop receipt')
            if terminal['outcome'] != 'step':
                return receipt(terminal['outcome'])
            if not _observed_step(context, terminal):
                uncertain = True
                raise DebuggerError('Native step returned an incomplete stop receipt')
            completed.append(deepcopy(terminal))
        return receipt('step')
    except BaseException as error:
        # Preserve the primary exception and any arrived child receipt. A late
        # register/journal failure must not erase either the prefix or first stop.
        observed = getattr(error, 'result', None)
        if observed is not None:
            terminal = observed
        error.result = receipt('error', failure=error)
        if uncertain:
            context.vm._fdisbull_control_quarantine = 'incomplete counted-step observation'
            try:
                context.vm.close()
            except BaseException as cleanup:
                error.machine_cleanup_error = type(cleanup).__name__
        raise
