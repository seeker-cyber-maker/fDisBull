"""A purchase waits for native phases and retains uncertain input without replay."""
import io
import json
import struct
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes
from fdisbull import dinopark_z as bridge
from fdisbull import dinopark_purchase as purchase
from fdisbull import debugger as native_debugger
from fdisbull.screenshot_hooks import ScreenshotHookSessionMixin, validate_configuration


class NativeShop:
    """Authored boundary fake: time consumes one queued input; host reads do not."""
    run_id = 'original-run'

    def __init__(self):
        self.view = 'coel_page'
        self.money = dict(cash=4500, loan=5000, working_cash=4500)
        self.clicks, self.runs = [], []
        self.queued = None
        self.herd = 0
        self.expense = 0
        self.species, self.price = 4, 1250
        self.release_pending = False

    def memory(self, address, length):
        values = {'4020:5c3a': self.money['cash'], '4020:bfbb': 5000,
                  '4020:bad4': self.money['working_cash'], '4020:68a5': self.species,
                  '4020:45b8': self.price, '4020:ccfe': 0, '4020:3c5c': 65535}
        if address == '4020:4384':
            data = bytearray(200)
            for index in range(10):
                struct.pack_into('<hh', data, index * 20 + 14,
                                 4 if self.herd and index == 9 else -1,
                                 self.herd if index == 9 else 0)
            return {'hex': data.hex()}
        if address == '4020:c30b':
            return {'hex': struct.pack('<12I', self.expense, *([0] * 11)).hex()}
        return {'hex': values[address].to_bytes(length, 'little').hex()}

    def click(self, x, y, hold_ms=150):
        self.queued = (x, y)
        self.clicks.append(self.queued)
        return {'accepted': True, 'delivery': 'queued', 'operation_id': str(len(self.clicks))}

    def run(self, *, guest_ms, **options):
        self.runs.append(guest_ms)
        if self.queued:
            point, self.queued = self.queued, None
            self.view = {(160, 87): 'coel_picked', (160, 103): 'coel_selected',
                         (187, 187): 'placement', (42, 50): 'placed', (188, 187): 'after'}[point]
            if point == (187, 187): self.money['working_cash'] = 3250
            if point == (188, 187):
                self.money['cash'] = 3250
                self.herd, self.expense = 1, 1250
        return {'outcome': 'guest_time'}

    def call(self, method):
        if method == 'session.status': return {'state': 'stopped'}
        assert method == 'input.mouse.state'
        return {'mouse': {'buttons': 0, 'release_pending': self.release_pending}}

    def scene_assert(self, *a, **k): return {'status': 'matched'}
    def registers(self): return {'state_revision': len(self.runs)}


def shop(monkeypatch, *, debug=None):
    debug = NativeShop() if debug is None else debug
    events = []
    project = SimpleNamespace(
        debug_save_scene=lambda *a, **k: {'id': 'qualified-mart'},
        debug_scene_info=lambda *a, **k: {'definition': {'match': {'constant': True}}})
    patterns = {name: {'name': name, 'samples': [{'x': 0, 'y': 0, 'rgb': [0, 0, 0]}],
                       'min_matches': 1, 'tolerance': 0}
                for name in ('coel_page', 'coel_picked', 'coel_selected',
                             'placement', 'placed', 'after', 'street_view')}
    text = scenes.TextScene(debug, None, None, project=project, patterns=patterns, event=events.append)
    text.current, text.land_bought, text.mart, text.street = 'dinomart', True, 'source-mart', 'street'
    text.bounded_purchases = True
    monkeypatch.setattr(scenes, 'prepare_mart_first_page', lambda *a, **k: None)
    monkeypatch.setattr(scenes, 'take_frame', lambda *a, **k: (
        {'artifact': 'saved-frame', 'metadata': {'mode_id': 5}}, debug.view))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: image == pattern['name'])
    return text, debug, events


def test_ready_native_phases_do_not_pay_the_old_37_second_fixed_guest_wait(monkeypatch):
    text, debug, events = shop(monkeypatch)
    result = text.buy_dinosaur()
    assert 'Cash: $3,250' in result and text.dinosaur_bought
    assert debug.clicks == [(160, 87), (160, 103), (187, 187), (42, 50), (188, 187)]
    assert sum(debug.runs) <= 5000
    assert len([e for e in events if e['phase'] == 'coelophysis_purchase_confirmed']) == 1


def test_arrival_waits_for_placement_without_repeating_the_order(monkeypatch):
    text, debug, _ = shop(monkeypatch)
    native_run = debug.run
    remaining = [0]
    def run(**kw):
        ordering = debug.queued == (187, 187)
        if remaining[0] and debug.queued:
            raise AssertionError('A dependent input arrived before the placement view')
        result = native_run(**kw)
        if ordering:
            remaining[0] = 2
            debug.view = 'arrival'
        elif remaining[0]:
            remaining[0] -= 1
            if not remaining[0]: debug.view = 'placement'
        return result
    debug.run = run
    assert 'Cash: $3,250' in text.buy_dinosaur()
    assert debug.clicks.count((187, 187)) == 1
    assert debug.runs.count(500) == 2


def provider(tmp_path, text, events):
    writer = io.StringIO()
    service = bridge.ZService(tmp_path, io.StringIO(), writer)
    service.ready(text)
    def event(value):
        events.append(value)
        service.event(value)
    text.event = event
    service.pending = {'command': 'buy coelophysis', 'session_token': service.session_token,
                       'action': {'verb': 'buy', 'target': 'coelophysis', 'item': None,
                                  'context_token': 'qualified-source'}, 'messages': [], 'events': []}
    return service, writer


def test_application_deadline_holds_queued_input_before_outer_transport_failure(tmp_path, monkeypatch):
    text, debug, events = shop(monkeypatch)
    service, writer = provider(tmp_path, text, events)
    now = [0]
    monkeypatch.setattr(purchase, '_clock', lambda: now[0])
    event = text.event
    def journal(value):
        event(value)
        if value.get('purchase_phase') == 'order': now[0] = purchase.HOST_SECONDS
    text.event = journal
    with pytest.raises(TimeoutError, match='phase deadline') as caught:
        text.buy_dinosaur()
    assert service.action_error(caught.value)
    assert text.dinosaur_order['last_input']['accepted'] is True
    assert text.dinosaur_order['last_input_phase'] == 'order'
    clicks, runs = list(debug.clicks), list(debug.runs)
    result = service.reconcile()
    assert not result['complete'] and result['effects'] == 'unknown'
    assert service.recovery_required and service.observe()['reconciliation_available']
    assert debug.clicks == clicks and debug.runs == runs and not text.dinosaur_bought
    receipt = json.loads((tmp_path/'z-session.json').read_text())
    assert receipt['held_command'] == 'buy coelophysis' and receipt['purchase_phase'] == 'order'


def test_original_commit_survives_followup_failure_and_reconciles_without_execution(tmp_path, monkeypatch):
    text, debug, events = shop(monkeypatch)
    service, writer = provider(tmp_path, text, events)
    saves = []
    def save(*a, **k):
        saves.append(a)
        if len(saves) == 1: raise RuntimeError('declared host scene readback failure')
        return {'id': 'reconciled-mart'}
    text.project.debug_save_scene = save
    with pytest.raises(RuntimeError, match='declared host') as caught:
        text.buy_dinosaur()
    assert service.action_error(caught.value)
    original = (tmp_path/'z-failure.json').read_bytes()
    assert json.loads(writer.getvalue().splitlines()[-1])['effects'] == 'applied-confirmed'
    assert not text.dinosaur_bought and debug.herd == 1 and debug.money['cash'] == 3250
    clicks, runs = list(debug.clicks), list(debug.runs)
    assert not service.reconcile('different-attempt')['complete']
    result = service.reconcile(service.held_action['id'])
    assert result['complete'] and result['effects'] == 'applied-confirmed' and result['read_only']
    assert result['action'] == {'verb': 'buy', 'target': 'coelophysis', 'item': None}
    assert result['witness']['session_token'] == service.session_token
    assert result['witness']['context_id'] == 'dinomart'
    assert debug.clicks == clicks and debug.runs == runs and text.dinosaur_bought
    assert (tmp_path/'z-failure.json').read_bytes() == original
    assert service.reconcile()['status'] == 'not-needed'
    assert 'No input was sent' in text.buy_dinosaur()
    assert debug.clicks == clicks


@pytest.mark.parametrize('fault', ['species', 'expense'])
def test_wrong_species_or_unproved_expense_never_becomes_committed(monkeypatch, fault):
    text, debug, events = shop(monkeypatch)
    if fault == 'species': debug.species = 19
    else:
        native_run = debug.run
        def run(**kw):
            result = native_run(**kw)
            if debug.herd: debug.expense = 0
            return result
        debug.run = run
    with pytest.raises(ValueError): text.buy_dinosaur()
    assert not text.dinosaur_bought
    assert not any(e['phase'] == 'coelophysis_purchase_confirmed' for e in events)
    if fault == 'species': assert (187, 187) not in debug.clicks


def test_confirmed_purchase_with_wrong_final_view_stays_held(tmp_path, monkeypatch):
    text, debug, events = shop(monkeypatch)
    service, _ = provider(tmp_path, text, events)
    text.project.debug_save_scene = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('followup'))
    with pytest.raises(RuntimeError) as caught: text.buy_dinosaur()
    assert service.action_error(caught.value)
    debug.view = 'placement'
    clicks, runs = list(debug.clicks), list(debug.runs)
    result = service.reconcile()
    assert not result['complete'] and result['effects'] == 'applied-confirmed'
    assert service.recovery_required and not text.dinosaur_bought
    assert debug.clicks == clicks and debug.runs == runs


def test_pending_pointer_release_cannot_clear_a_purchase_hold(tmp_path, monkeypatch):
    text, debug, events = shop(monkeypatch)
    service, _ = provider(tmp_path, text, events)
    text.project.debug_save_scene = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('followup'))
    with pytest.raises(RuntimeError) as caught: text.buy_dinosaur()
    assert service.action_error(caught.value)
    debug.release_pending = True
    result = service.reconcile()
    assert not result['complete'] and result['effects'] == 'applied-confirmed'
    assert service.recovery_required and not text.dinosaur_bought


def test_read_only_purchase_reconcile_bypasses_configured_screenshot_execution(tmp_path, monkeypatch):
    from PIL import Image

    # Retain the real helper before shop() replaces frame collection for setup.
    take_frame = scenes.take_frame

    class HookShop(NativeShop, ScreenshotHookSessionMixin):
        screenshot = native_debugger.DebugSession.screenshot
        closed = False

        def screenshot_hooks(self):
            return {'configured': True, 'id': 'active-policy', 'sha256': 'authored-policy',
                    'configuration': validate_configuration({
                        'pre': [{'op': 'run', 'guest_ms': 1, 'timeout_ms': 1000}]})}

        def layers(self, active=None): return {'active': []}
        def _event(self, *args): pass
        def _artifact(self, *args): return {'artifact': 'memory-artifact'}
        def _screenshot_capture(self, *args):
            return {'artifact': 'memory-frame', 'metadata': {'mode_id': 5}}

    debug = HookShop()
    text, debug, events = shop(monkeypatch, debug=debug)
    service, _ = provider(tmp_path, text, events)
    saves = []

    def save(*args, **kwargs):
        saves.append(args)
        if len(saves) == 1:
            raise RuntimeError('qualified commit; host scene publication unavailable')
        return {'id': 'reconciled-mart'}

    text.project.debug_save_scene = save
    with pytest.raises(RuntimeError) as caught:
        text.buy_dinosaur()
    assert service.action_error(caught.value)
    diagnostic = (tmp_path / 'z-failure.json').read_bytes()

    # Positive control exercises the real hook dispatcher and script executor.
    # The native run boundary and all artifact storage remain authored in memory.
    before_control = len(debug.runs)
    debug.screenshot('hook-control.png')
    assert debug.runs[before_control:] == [1]
    image = io.BytesIO()
    Image.new('RGB', (320, 200)).save(image, format='PNG')
    row = SimpleNamespace(fetchone=lambda: {'data': image.getvalue()})
    text.project.path = tmp_path / 'memory.fdb'
    text.project.db = SimpleNamespace(execute=lambda *args: row)
    text.project.debug_export = lambda *args: None
    monkeypatch.setattr(scenes, 'take_frame', take_frame)
    monkeypatch.setattr(scenes, 'matches', lambda *args: True)
    clicks, runs = list(debug.clicks), list(debug.runs)

    result = service.reconcile(service.held_action['id'])

    assert result['complete'] and result['effects'] == 'applied-confirmed'
    assert result['read_only'] and not service.recovery_required
    assert debug.runs == runs, 'Read-only reconciliation dispatched a screenshot execution hook'
    assert debug.clicks == clicks
    assert (tmp_path / 'z-failure.json').read_bytes() == diagnostic


@pytest.mark.parametrize('first_observation', ['action', 'reconciliation'])
def test_native_commit_proof_survives_first_post_commit_frame_failure(
        tmp_path, monkeypatch, first_observation):
    text, debug, events = shop(monkeypatch)
    service, writer = provider(tmp_path, text, events)
    capture = scenes.take_frame
    proofs_at_capture = []

    def frame(*args, **kwargs):
        if debug.herd:
            proofs_at_capture.append(deepcopy(text.dinosaur_order['proof']))
            raise RuntimeError('post-commit frame unavailable')
        return capture(*args, **kwargs)

    monkeypatch.setattr(scenes, 'take_frame', frame)
    if first_observation == 'reconciliation':
        # The original confirm can apply before its run reply/follow-up fails.
        # Reconciliation must retain the proof it subsequently reads even when
        # presentation is still unavailable; it must not resume that run.
        native_run = debug.run

        def run(**kwargs):
            result = native_run(**kwargs)
            if debug.herd:
                raise RuntimeError('confirmation follow-up unavailable')
            return result

        debug.run = run
    with pytest.raises(RuntimeError) as caught:
        text.buy_dinosaur()
    assert service.action_error(caught.value)
    diagnostic = (tmp_path / 'z-failure.json').read_bytes()
    state = purchase.native_state(debug)
    assert state['balances'] == {'cash': 3250, 'loan': 5000, 'working_cash': 3250}
    assert state['pens'] == [{'pen': 10, 'species': 4, 'count': 1}]
    assert state['expenses'][state['month']] == 1250
    assert debug.clicks == [(160, 87), (160, 103), (187, 187), (42, 50), (188, 187)]
    if first_observation == 'action':
        assert json.loads(writer.getvalue().splitlines()[-1])['effects'] == 'applied-confirmed'
    clicks, runs = list(debug.clicks), list(debug.runs)

    result = service.reconcile(service.held_action['id'])

    assert not result['complete'] and result['effects'] == 'applied-confirmed'
    assert text.dinosaur_order['proof'] == purchase.commit_proof(text.dinosaur_order, state)
    assert proofs_at_capture and all(proof is not None for proof in proofs_at_capture)
    assert service.recovery_required and not text.dinosaur_bought
    assert debug.clicks == clicks and debug.runs == runs
    assert (tmp_path / 'z-failure.json').read_bytes() == diagnostic


def test_purchase_deadline_reaches_real_native_rpc_and_preserves_recovery_channel(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(purchase, '_clock', lambda: now[0])
    monkeypatch.setattr(native_debugger.time, 'monotonic', lambda: now[0])

    class ShopRPC:
        closed = False

        def __init__(self, native):
            self.native, self.calls = native, []

        def call(self, method, params=None, timeout_ms=15000):
            # Each read can complete within the real transport's per-RPC cap,
            # while their aggregate crosses the purchase/outer host deadline.
            cost = 3.0 if method in ('memory.read', 'video.screenshot') else 0.05
            self.calls.append({'method': method, 'started': now[0], 'timeout_ms': timeout_ms,
                               'deadline': getattr(self.native, '_rpc_deadline', None)})
            if timeout_ms < cost * 1000:
                self.closed = True
                raise TimeoutError('Authored RPC deadline expired; channel is unusable')
            now[0] += cost
            if method == 'memory.read':
                return NativeShop.memory(self.native, params['address'], params['length'])
            if method == 'input.mouse.click':
                return NativeShop.click(self.native, params['x'], params['y'], params['hold_ms'])
            if method == 'input.mouse.state':
                return {'mouse': {'buttons': 0, 'release_pending': False}}
            if method == 'session.status': return {'state': 'stopped'}
            if method == 'frame.probe': return {'status': 'matched'}
            assert method == 'video.screenshot'
            return {}

    class RPCShop(NativeShop):
        # The actual DebugSession.call sees the deadline on this native object.
        # BankInputSession only forwards to it; no transport or guest is opened.
        call = native_debugger.DebugSession.call
        closed = False
        session_id = 'authored-session'

        def __init__(self):
            super().__init__()
            self.rpc = ShopRPC(self)

        def memory(self, address, length):
            return self.call('memory.read', {'address': address, 'length': length})

        def click(self, x, y, hold_ms=150):
            return self.call('input.mouse.click', {'x': x, 'y': y, 'hold_ms': hold_ms})

        def scene_assert(self, *args, **kwargs): return self.call('frame.probe')

    native = RPCShop()
    wrapped = scenes.BankInputSession(native, lambda event: None)
    text, _, events = shop(monkeypatch, debug=wrapped)
    service, _ = provider(tmp_path, text, events)

    def frame(*args, **kwargs):
        wrapped.call('video.screenshot')
        return {'artifact': 'memory-frame', 'metadata': {'mode_id': 5}}, native.view

    monkeypatch.setattr(scenes, 'take_frame', frame)
    with pytest.raises(TimeoutError) as caught:
        text.buy_dinosaur()
    action_calls = list(native.rpc.calls)

    assert now[0] <= purchase.HOST_SECONDS, (now[0], action_calls)
    assert action_calls and all(call['deadline'] is not None for call in action_calls)
    assert all(call['deadline'] <= purchase.HOST_SECONDS for call in action_calls)
    assert all(call['timeout_ms'] <= 5000 for call in action_calls)
    assert all(call['deadline'] - call['started'] >= 5 for call in action_calls)
    assert all(0 < call['timeout_ms'] <= int((call['deadline'] - call['started']) * 1000)
               for call in action_calls)
    assert not native.rpc.closed and not native.closed
    assert getattr(native, '_rpc_deadline', None) is None
    assert service.action_error(caught.value)
    status = native.rpc.calls[-1]
    assert status['method'] == 'session.status' and 0 < status['timeout_ms'] <= 3000
    assert service.recovery_required and service.held_action is not None
    assert not native.rpc.closed and not native.closed


def test_committed_purchase_finish_without_witness_retains_hold_and_releases_budget(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(purchase, '_clock', lambda: now[0])
    monkeypatch.setattr(native_debugger.time, 'monotonic', lambda: now[0])
    native = NativeShop()
    wrapped = scenes.BankInputSession(native, lambda event: None)
    text, _, events = shop(monkeypatch, debug=wrapped)
    service, writer = provider(tmp_path, text, events)
    service.pending = None  # Dispatch through the public provider boundary below.
    source = service.observe()
    action = {'verb': 'buy', 'target': 'coelophysis', 'item': None,
              'context_token': source['context']['token']}
    request = json.dumps({'op': 'act', 'action': action}) + '\n'
    service.reader = io.StringIO(request)
    original_observe, original_oracle = service.observe, service.oracle
    original_assert, original_call = native.scene_assert, native.call
    observations, oracles, recovery_status = [], [], []
    final_view_unqualified = [False]

    def observe(**kwargs):
        observations.append(getattr(native, '_rpc_deadline', None))
        return original_observe(**kwargs)

    def oracle(phase):
        oracles.append((phase, getattr(native, '_rpc_deadline', None)))
        return original_oracle(phase)

    def scene_assert(*args, **kwargs):
        if final_view_unqualified[0]:
            raise RuntimeError('committed original purchase; final scene unavailable')
        return original_assert(*args, **kwargs)

    def call(method, *args, **kwargs):
        if method == 'session.status':
            recovery_status.append({
                'action_scope': service._action_budget_scope,
                'deadline': getattr(native, '_rpc_deadline', None),
                'cap': getattr(native, '_rpc_timeout_cap_ms', None),
                'admission': getattr(native, '_rpc_admission_ms', None)})
        return original_call(method, *args, **kwargs)

    monkeypatch.setattr(service, 'observe', observe)
    monkeypatch.setattr(service, 'oracle', oracle)
    monkeypatch.setattr(native, 'scene_assert', scene_assert)
    monkeypatch.setattr(native, 'call', call)

    assert service.command() == 'buy coelophysis'
    assert observations == [40.0]  # Budget exists before pre-dispatch observation.
    now[0] = 2.0
    message = text.buy_dinosaur()
    service.output(message)
    assert getattr(native, '_rpc_deadline', None) == 40.0
    pending = deepcopy(service.pending)
    assert any(event.get('phase') == 'coelophysis_purchase_confirmed'
               for event in pending['events'])
    clicks, runs = list(native.clicks), list(native.runs)
    final_view_unqualified[0] = True
    now[0] = 7.0

    service.finish()

    replies = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert len(replies) == 1
    assert replies[0]['status'] == 'incomplete' and not replies[0]['complete']
    assert replies[0]['effects'] == 'applied-confirmed' and replies[0]['recovery_required']
    assert 'witness' not in replies[0]
    assert observations == [40.0, 40.0]
    assert oracles == [('command-complete', 40.0)]
    assert recovery_status == [{'action_scope': None, 'deadline': 10.0, 'cap': 3000, 'admission': 0}]
    assert service.pending is None and service.recovery_required
    assert service.held_action['pending'] == pending
    assert service.held_action['effects'] == 'applied-confirmed'
    assert service.held_action['dinosaur_order']['proof'] == text.dinosaur_order['proof']
    assert service._action_budget_scope is None
    assert all(getattr(native, field, None) is None for field in (
        '_rpc_deadline', '_rpc_timeout_cap_ms', '_rpc_admission_ms', '_rpc_cleanup_grace_ms'))
    assert native.clicks == clicks and native.runs == runs

    # The held intent cannot be sent again through the provider, including with
    # the old context token; reaching EOF only ends this in-memory request list.
    service.reader = io.StringIO(request)
    with pytest.raises(EOFError):
        service.command()
    assert json.loads(writer.getvalue().splitlines()[-1])['status'] == 'rejected'
    assert native.clicks == clicks and native.runs == runs
