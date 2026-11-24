"""Host-only tests for AGI reply ownership and uncertainty receipts."""
from contextlib import contextmanager
import threading
from types import SimpleNamespace

import pytest

from fdisbull import cli
from fdisbull.qemu_agi import AGIQemuSession
from fdisbull.qemu_control import QMPCommandError


class QMP:
    def __init__(self, session, failure=None):
        self.session = session
        self.failure = failure
        self.calls = []

    def call(self, method, arguments, **kwargs):
        self.calls.append((method, arguments))
        if self.failure:
            raise self.failure
        self.session.guest = {'status': 'ready', 'pending_effect': None,
                              'retired': 6, 'logic': 2, 'pc': 11}


def prepared(failure=None, fail_event=False):
    session = object.__new__(AGIQemuSession)
    session.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    session.vm = SimpleNamespace(closed=False, process=SimpleNamespace(poll=lambda: 0))
    session.vm.qmp = QMP(session, failure)
    session.cpu_path = '/machine/cpu'
    session.capabilities = {'agi_host_replies': True}
    session._runtime_entry_logic = 2
    session.closed = False
    session.guest = {'status': 'pending', 'retired': 5, 'logic': 2, 'pc': 10,
                     'pending_effect': {'id': 7, 'reply': 'ack', 'opcode': 101,
                                        'logic': 2, 'pc': 10, 'next_pc': 11, 'args': []}}
    session._stopped = lambda: None
    session._state = lambda: {'guest': session.guest}
    lock = threading.Lock()
    @contextmanager
    def budget(owner, deadline):
        with lock:
            yield {}
    session._budget = budget
    def close():
        session.closed = session.vm.closed = True
    session.close = close
    session.events = []
    def event(name, data):
        session.events.append((name, data.copy()))
        if fail_event:
            raise RuntimeError('evidence write failed')
    session._event = event
    return session


def respond(monkeypatch, session):
    monkeypatch.setattr(cli, 'invoke', lambda method, params, debugger:
                        session.reply_host(7, accepted=True))
    return cli.respond({'id': 1, 'method': 'debug-agi-reply', 'params': {}})


def test_correlated_rejection_preserves_owner(monkeypatch):
    session = prepared(QMPCommandError('QMP qom-set: rejected'))
    reply = respond(monkeypatch, session)
    assert not reply['ok']
    assert reply['error']['type'] == 'QMPCommandError'
    evidence = reply['error']['result']
    assert evidence['disposition'] == 'native rejection'
    assert evidence['do_not_replay'] is False
    assert session.guest['pending_effect']['id'] == 7
    assert not session.closed and len(session.vm.qmp.calls) == 1
    assert session.events[0][0] == 'agi-host-reply-rejected'


def test_existing_debug_methods_keep_the_public_qmp_error_type(monkeypatch):
    def refuse(*args):
        raise QMPCommandError('QMP qom-get: unavailable')

    monkeypatch.setattr(cli, 'invoke', refuse)
    reply = cli.respond({'method': 'debug-registers', 'params': {}})
    assert reply['error'] == {'type': 'DebuggerError', 'message': 'QMP qom-get: unavailable'}


@pytest.mark.parametrize('failure', [TimeoutError('timed out'), EOFError('lost reply')])
def test_lost_reply_closes_owner_and_surfaces_no_replay(monkeypatch, failure):
    session = prepared(failure)
    reply = respond(monkeypatch, session)
    assert not reply['ok']
    evidence = reply['error']['result']
    assert evidence['format'] == 'fdisbull-qemu-agi-host-reply-error-1'
    assert evidence['ticket'] == 7 and evidence['do_not_replay'] is True
    assert evidence['owner_closed'] is True and evidence['audit_recorded'] is True
    assert session.closed and len(session.vm.qmp.calls) == 1
    assert session.events[-1][0] == 'agi-host-reply-uncertain'


def test_lost_reply_with_unrelated_result_is_not_mistaken_for_refusal(monkeypatch):
    failure = TimeoutError('lost reply')
    failure.result = {'format': 'unrelated', 'do_not_replay': False}
    session = prepared(failure)
    reply = respond(monkeypatch, session)
    evidence = reply['error']['result']
    assert evidence['format'] == 'fdisbull-qemu-agi-host-reply-error-1'
    assert evidence['do_not_replay'] and evidence['owner_closed']
    assert session.closed and len(session.vm.qmp.calls) == 1


def test_rejection_audit_failure_preserves_pending_owner(monkeypatch):
    session = prepared(QMPCommandError('QMP qom-set: rejected'), fail_event=True)
    reply = respond(monkeypatch, session)
    evidence = reply['error']['result']
    assert evidence['disposition'] == 'native rejection'
    assert evidence['audit_recorded'] is False and evidence['do_not_replay'] is False
    assert session.guest['pending_effect']['id'] == 7
    assert not session.closed and len(session.vm.qmp.calls) == 1


def test_provenance_failure_after_verified_commit_preserves_receipt(monkeypatch):
    session = prepared(fail_event=True)
    reply = respond(monkeypatch, session)
    assert not reply['ok']
    evidence = reply['error']['result']
    assert evidence['do_not_replay'] and evidence['owner_closed']
    assert evidence['audit_recorded'] is False
    assert evidence['receipt']['verified'] is True
    assert evidence['receipt']['after']['retired'] == 6
    assert len(session.vm.qmp.calls) == 1 and session.closed


def test_concurrent_duplicate_dispatches_only_once():
    session = prepared()
    barrier = threading.Barrier(3)
    outcomes = []
    def worker():
        barrier.wait()
        try:
            outcomes.append(session.reply_host(7, accepted=True))
        except ValueError as error:
            outcomes.append(error)
    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(session.vm.qmp.calls) == 1
    assert sum(isinstance(value, ValueError) for value in outcomes) == 1
    assert sum(isinstance(value, dict) and value['verified'] for value in outcomes) == 1


def test_deadline_after_publication_retains_verified_receipt_and_owner(monkeypatch):
    session = prepared()

    @contextmanager
    def expire_on_exit(owner, deadline):
        yield {}
        raise TimeoutError('budget expired after audit')

    session._budget = expire_on_exit
    reply = respond(monkeypatch, session)
    evidence = reply['error']['result']
    assert evidence['do_not_replay'] and evidence['audit_recorded']
    assert evidence['receipt']['verified'] and not session.closed
    assert [name for name, _ in session.events] == ['agi-host-reply']
    assert len(session.vm.qmp.calls) == 1
