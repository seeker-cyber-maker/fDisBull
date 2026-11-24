"""Native AGI host replies, with bounded dispatch and readback evidence."""
import hashlib
import json
import re
import time

from .debugger import stamp
from .dosbox_rpc import DebuggerError
from .qemu_control import QMPCommandError

FORMAT = 'fdisbull-qemu-agi-host-reply-1'
ERROR_FORMAT = 'fdisbull-qemu-agi-host-reply-error-1'
MAX_GUEST_SNAPSHOT_BYTES = 8 * 1024 * 1024


def _inputs(ticket, accepted, text, number, snapshot_hex):
    if type(ticket) is not int or not 1 <= ticket <= 0xffffffffffffffff:
        raise ValueError('AGI host reply ticket must be a positive uint64')
    if type(accepted) is not bool:
        raise ValueError('AGI host reply accepted must be a boolean')
    if text is not None and (type(text) is not str or len(text) > 40):
        raise ValueError('AGI host reply text must be a string of at most 40 CP437 characters')
    if number is not None and (type(number) is not int or not 0 <= number <= 255):
        raise ValueError('AGI host reply number must be a byte')
    if snapshot_hex is not None:
        if (type(snapshot_hex) is not str or not snapshot_hex or
                len(snapshot_hex) > 2 * MAX_GUEST_SNAPSHOT_BYTES or len(snapshot_hex) % 2 or
                re.fullmatch(r'[0-9a-fA-F]+', snapshot_hex) is None):
            raise ValueError('AGI guest snapshot must be bounded hexadecimal bytes')
        snapshot_hex = snapshot_hex.lower()
    return snapshot_hex


def _prepare(before, ticket, accepted, text, number, snapshot_hex):
    if not isinstance(before, dict):
        raise DebuggerError('Invalid AGI host reply guest state')
    pending = before.get('pending_effect')
    if (before.get('status') != 'pending' or not isinstance(pending, dict) or
            type(pending.get('id')) is not int or pending['id'] != ticket):
        raise ValueError('AGI host reply ticket does not match the current pending effect')
    reply = pending.get('reply')
    if reply not in ('ack', 'text', 'number', 'choice', 'menu', 'restore'):
        raise DebuggerError('Invalid AGI host reply type')
    restore = accepted and reply == 'restore'
    if restore != (snapshot_hex is not None):
        raise ValueError('Accepted AGI restore requires a guest snapshot, and other replies forbid it')
    expected = ('text' if accepted and reply == 'text' else
                'number' if accepted and reply in ('number', 'menu') else 'none')
    if ((expected == 'text' and (text is None or number is not None)) or
            (expected == 'number' and (number is None or text is not None)) or
            (expected == 'none' and (text is not None or number is not None))):
        raise ValueError('AGI host reply payload does not match the pending reply type')
    args, opcode, next_pc = pending.get('args'), pending.get('opcode'), pending.get('next_pc')
    logic, pc, retired = before.get('logic'), before.get('pc'), before.get('retired')
    if (type(opcode) is not int or type(next_pc) is not int or not 0 <= next_pc <= 65536 or
            type(logic) is not int or not 0 <= logic <= 255 or type(pc) is not int or not 0 <= pc <= 65536 or
            not isinstance(args, list) or any(type(x) is not int or not 0 <= x <= 255 for x in args)):
        raise DebuggerError('Invalid AGI host reply request observation')
    if (type(pending.get('logic')) is not int or pending['logic'] != logic or
            type(pending.get('pc')) is not int or pending['pc'] != pc):
        raise DebuggerError('AGI host reply pending position differs from guest')
    if text is not None:
        try:
            encoded = text.encode('cp437')
        except UnicodeEncodeError as error:
            raise ValueError('AGI host reply text must be CP437 encodable') from error
        if len(args) < 5 or args[0] >= 25:
            raise DebuggerError('Invalid AGI host text request bounds or destination')
        if b'\0' in encoded or len(encoded) > min(40, args[4]):
            raise ValueError('AGI host reply text exceeds the request bounds or contains NUL')
    if accepted and reply == 'number' and opcode != 124 and len(args) < 2:
        raise DebuggerError('Invalid AGI number request destination')
    if type(retired) is not int or not 0 <= retired < 0xffffffffffffffff:
        raise DebuggerError('Invalid AGI host reply retirement state')
    next_id = before.get('next_effect_id')
    if restore and (type(next_id) is not int or next_id <= ticket):
        raise DebuggerError('Invalid AGI restore effect sequence')
    command = (dict(action='restore', id=ticket, snapshot=snapshot_hex) if restore else
               dict(action='complete', id=ticket, accepted=accepted))
    if text is not None:
        command['text'] = text
    if number is not None:
        command['number'] = number
    receipt = dict(format=FORMAT, ticket=ticket, accepted=accepted, reply_type=reply, timestamp=stamp(),
                   before=dict(status='pending', pending_effect=pending, retired=retired, logic=logic, pc=pc),
                   payload={key: command[key] for key in ('text', 'number') if key in command})
    if restore:
        snapshot = bytes.fromhex(snapshot_hex)
        receipt['snapshot'] = dict(sha256=hashlib.sha256(snapshot).hexdigest(), size=len(snapshot))
    return command, receipt


def _readback(after, before, receipt, entry_logic):
    pending = before['pending_effect']
    accepted, reply = receipt['accepted'], receipt['reply_type']
    payload, args, opcode = receipt['payload'], pending['args'], pending['opcode']
    restore = accepted and reply == 'restore'
    if (not isinstance(after, dict) or 'pending_effect' not in after or after['pending_effect'] is not None or
            type(after.get('retired')) is not int or not 0 <= after['retired'] <= 0xffffffffffffffff or
            type(after.get('logic')) is not int or
            not 0 <= after['logic'] <= 255 or type(after.get('pc')) is not int or not 0 <= after['pc'] <= 65536):
        raise DebuggerError('AGI host reply native readback differs')
    if restore:
        flags, next_id = after.get('flags'), after.get('next_effect_id')
        if (after.get('status') not in ('ready', 'return') or type(next_id) is not int or
                next_id < before['next_effect_id'] or not isinstance(flags, list) or len(flags) <= 12 or flags[12] != 1):
            raise DebuggerError('AGI guest restore readback differs')
    else:
        expected_status = 'quit' if accepted and opcode == 134 else 'ready'
        restart = accepted and opcode == 128
        if (after.get('status') != expected_status or after['retired'] != before['retired'] + 1 or
                after['pc'] != (0 if restart else pending['next_pc']) or
                after['logic'] != (entry_logic if restart else before['logic'])):
            raise DebuggerError('AGI host reply execution position or retirement differs')
    if accepted and reply == 'text':
        values = after.get('strings')
        if not isinstance(values, list) or args[0] >= len(values) or values[args[0]] != payload['text']:
            raise DebuggerError('AGI host reply text readback differs')
    if reply == 'number' and (accepted or opcode == 124):
        values = after.get('variables')
        index = 25 if opcode == 124 else args[1]
        if not isinstance(values, list) or index >= len(values) or values[index] != (payload['number'] if accepted else 255):
            raise DebuggerError('AGI host reply number readback differs')
    if accepted and reply == 'menu':
        values, number = after.get('controllers'), payload['number']
        if not isinstance(values, list) or number >= len(values) or values[number] != 1:
            raise DebuggerError('AGI host reply menu readback differs')
    result = dict(status=after['status'], pending_effect=None, retired=after['retired'],
                  logic=after['logic'], pc=after['pc'])
    if restore:
        result.update(next_effect_id=after['next_effect_id'], restored_flag=flags[12])
    return result


def _uncertain(session, error, receipt, disposition):
    evidence = dict(format=ERROR_FORMAT, ticket=receipt['ticket'], reply_type=receipt['reply_type'],
                    accepted=receipt['accepted'], timestamp=receipt['timestamp'],
                    do_not_replay=True, disposition=disposition)
    if receipt.get('verified'):
        evidence['receipt'] = receipt
    try:
        session._event('agi-host-reply-uncertain', evidence)
        evidence['audit_recorded'] = True
    except BaseException:
        evidence['audit_recorded'] = False
    try:
        session.close()
    except BaseException:
        pass
    evidence['owner_closed'] = session._owner_reaped()
    error.result = evidence


def reply_host(session, ticket, *, accepted, text, number, snapshot_hex, timeout_ms):
    from .qemu_agi import _remaining, _timeout
    _timeout(timeout_ms)
    snapshot_hex = _inputs(ticket, accepted, text, number, snapshot_hex)
    if session.project.db.in_transaction:
        raise ValueError('AGI host reply requires no caller transaction')
    deadline = time.monotonic() + timeout_ms / 1000
    published = None
    try:
        with session._budget(session.vm, deadline):
            if not session.capabilities.get('agi_host_replies'):
                raise ValueError('AGI native host reply interface is unavailable')
            session._stopped()
            before = session._state().get('guest')
            command, receipt = _prepare(before, ticket, accepted, text, number, snapshot_hex)
            params = dict(path=session.cpu_path, property='agi-runtime-command',
                          value=json.dumps(command, sort_keys=True, separators=(',', ':')))
            remaining = _remaining(deadline)
            try:
                session.vm.qmp.call('qom-set', params, timeout_ms=remaining)
            except QMPCommandError as error:
                # The native reply setter rolls back on a correlated refusal.
                evidence = dict(format=ERROR_FORMAT, ticket=ticket, disposition='native rejection',
                                do_not_replay=False)
                try:
                    session._event('agi-host-reply-rejected', receipt)
                    evidence['audit_recorded'] = True
                except BaseException:
                    evidence['audit_recorded'] = False
                error.result = evidence
                raise
            except BaseException as error:
                _uncertain(session, error, receipt, 'dispatch uncertain')
                raise

            try:
                after = session._state().get('guest')
                receipt['after'] = _readback(after, before, receipt, session._runtime_entry_logic)
                receipt['verified'] = True
                session._event('agi-host-reply', receipt)
                published = receipt
            except BaseException as error:
                disposition = ('completion verified but audit failed' if receipt.get('verified')
                               else 'completion acknowledged but readback unverified')
                _uncertain(session, error, receipt, disposition)
                raise
    except BaseException as error:
        if published is not None:
            # The owner lock may already have passed to the next operation.
            error.result = dict(format=ERROR_FORMAT, ticket=ticket, receipt=published,
                                disposition='completion verified and audited before budget exit failed',
                                do_not_replay=True, audit_recorded=True)
        raise
    return published
