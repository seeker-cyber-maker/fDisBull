"""No guest is needed to test post-dispatch receipt transport."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from fdisbull import cli
from fdisbull.qemu_agi import AGIQemuSession, EXECUTION_ERROR_FORMAT


class Remote:
    def __init__(self, reply=b'T05'):
        self.calls = []
        self.reply = reply

    def execute(self, command, timeout_ms):
        self.calls.append(command)
        return self.reply, False


def prepared(reply=b'T05'):
    session = object.__new__(AGIQemuSession)
    session.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    session.vm = SimpleNamespace(closed=False, process=SimpleNamespace(poll=lambda: 0))
    session.closed = False
    remote = Remote(reply)
    session._stopped = lambda: remote
    states = iter([{'guest': {'retired': 0, 'status': 'ready'}},
                   {'guest': {'retired': 1, 'status': 'running'}}])
    session._state = lambda: next(states)
    session.registers = lambda: {'registers': {'pc': '0x0'}}
    @contextmanager
    def budget(owner, deadline):
        yield {}
    session._budget = budget
    def close():
        session.closed = session.vm.closed = True
    session.close = close
    def event(*args):
        raise RuntimeError('evidence write failed')
    session._event = event
    return session, remote


def test_post_step_write_failure_produces_json_receipt_without_replay(monkeypatch):
    session, remote = prepared()
    monkeypatch.setattr(cli, 'invoke', lambda method, params, debugger: session.step())
    reply = cli.respond({'id': 7, 'method': 'debug-step', 'params': {}})
    assert reply['ok'] is False
    receipt = reply['error']['result']
    assert receipt['format'] == EXECUTION_ERROR_FORMAT
    assert receipt['execution']['outcome'] == 'step'
    assert receipt['execution']['retired'] == 1
    assert receipt['do_not_replay'] is True and receipt['owner_closed'] is True
    assert remote.calls == ['s'] and session.closed


def test_invalid_native_reply_is_uncertain_and_closes():
    session, remote = prepared(b'invalid')
    with pytest.raises(Exception) as caught:
        session.step()
    receipt = caught.value.result
    assert receipt['format'] == EXECUTION_ERROR_FORMAT
    assert 'uncertain' in receipt['execution']['disposition']
    assert receipt['do_not_replay'] and receipt['owner_closed']
    assert remote.calls == ['s']
