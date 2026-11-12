"""Bounded PE64 tracing next to the native debugger, without host round trips."""
import time

from .ida_wire import ProtocolError


def pe_registers(client):
    result = client.registers()
    required = {'rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp','rip','efl', *(f'r{i}' for i in range(8,16))}
    if not required <= result.keys():
        raise ProtocolError('IDA target did not provide the PE64 integer register set')
    return dict(rip=hex(result['rip']), rflags=hex(result['efl']), thread=client.pending['tid'],
                general={name:hex(result[name]) for name in sorted(required-{'rip','efl'})})


def collect_trace(client, count, timeout_ms):
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError('Trace count must be 1..10000')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Trace timeout must be 1..600000 ms')
    start = time.monotonic()
    deadline = start + timeout_ms / 1000
    events = []
    state = client.last_state
    expired = False
    try:
        with client.step_scope():
            before = pe_registers(client)
            owner = before['thread']
            while len(events) < count:
                if time.monotonic() >= deadline:
                    expired = True
                    break
                # Read afresh for every fetch: a loop can modify its own code.
                raw = client.read_code(int(before['rip'],16))
                remaining = int((deadline-time.monotonic())*1000)
                if remaining <= 0:
                    expired = True
                    break
                state = client.step(remaining)
                if state['stop_reason']['kind'] != 'step':
                    break
                if state['stop_reason']['thread'] != owner:
                    raise ProtocolError('Trace step belongs to another thread')
                events.append(dict(address=before['rip'], bytes=raw.hex(), registers=before))
                before = pe_registers(client)
                state = client.breakpoint_boundary(int(before['rip'],16))
                if state['stop_reason']['kind'] != 'step':
                    break
    except (TimeoutError, ProtocolError):
        client.close()
        raise
    complete = len(events) == count
    if expired:
        stop = dict(state['stop_reason'], native_kind=state['stop_reason']['kind'], kind='timeout', stop_origin='trace-deadline')
        state = client.last_state = dict(state, stop_reason=stop)
    return dict(events=events, complete=complete, session=state,
                statistics=dict(collector='linux-controller', completed_instructions=len(events),
                                elapsed_ms=round((time.monotonic()-start)*1000,3),
                                peer_threads='held across bounded batch; newly started peers held before continuation'))
