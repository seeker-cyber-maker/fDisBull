"""Bounded Coelophysis input phases and read-only original commit qualification."""
from copy import deepcopy
from contextlib import contextmanager
import secrets
import struct
import time

HOST_SECONDS = 40
_clock = time.monotonic


def native_session(debug):
    from .dinopark_scenes import BankInputSession
    while isinstance(debug, BankInputSession):
        debug = debug.native
    return debug


@contextmanager
def recovery_budget(text):
    from .operation_budget import deadline_scope
    with deadline_scope(native_session(text.debug), _clock() + 3,
                        rpc_ms=3000, admission_ms=0, cleanup_ms=0):
        yield


class PurchaseBudget:
    def __init__(self):
        self.deadline = _clock() + HOST_SECONDS

    def timeout(self):
        remaining = self.deadline - _clock()
        if remaining <= 5:
            raise TimeoutError('Coelophysis phase deadline; provider must stay paused for reconciliation')
        return min(15000, max(1, int((remaining - 1) * 1000)))

    @contextmanager
    def bind(self, debug):
        from .operation_budget import deadline_scope
        native = native_session(debug)
        with deadline_scope(native, self.deadline):
            self.deadline = native._rpc_deadline
            yield

    def run(self, debug, ms):
        result = debug.run(guest_ms=ms, timeout_ms=self.timeout(), fast_forward=True)
        if result.get('outcome') != 'guest_time':
            raise RuntimeError('Coelophysis wait stopped: ' + str(result.get('outcome')))


def native_state(debug):
    from .dinopark_scenes import balances
    raw = bytes.fromhex(debug.memory('4020:4384', length=200)['hex'])
    pens = []
    for index in range(10):
        species, count = struct.unpack_from('<hh', raw, index * 20 + 14)
        if count < 0 or not -1 <= species < 20 or species == -1 and count:
            raise ValueError('Unqualified original pen record')
        if count:
            pens.append({'pen': index + 1, 'species': species, 'count': count})
    month = int.from_bytes(bytes.fromhex(debug.memory('4020:ccfe', length=2)['hex']), 'little')
    if not 0 <= month < 12:
        raise ValueError('Unqualified original purchase month')
    return {'balances': balances(debug), 'pens': pens, 'month': month,
            'expenses': list(struct.unpack('<12I', bytes.fromhex(
                debug.memory('4020:c30b', length=48)['hex'])))}


def commit_proof(order, after):
    before = order['before']
    ticket = order.get('last_input', {})
    if (order.get('last_input_phase') != 'confirm' or ticket.get('accepted') is not True or
            ticket.get('delivery') != 'queued' or order.get('species') != 4 or order.get('price') != 1250 or
            before['balances'] != {'cash': 4500, 'loan': 5000, 'working_cash': 4500} or before['pens'] or
            after['balances'] != {'cash': 3250, 'loan': 5000, 'working_cash': 3250} or
            after['pens'] != [{'pen': 1, 'species': 4, 'count': 1}] or after['month'] != before['month']):
        raise ValueError('Coelophysis commit remains unqualified')
    expected = list(before['expenses'])
    expected[before['month']] += 1250
    if after['expenses'] != expected:
        raise ValueError('Coelophysis expense remains unqualified')
    return {'order_id': order['id'], 'price': 1250, 'species': 4,
            'before': before, 'after': after, 'input': deepcopy(ticket)}


def _record_commit(text, after):
    order = text.dinosaur_order
    proof = commit_proof(order, after)
    if not order.get('proof'):
        order['proof'] = proof
        text.event({'phase': 'coelophysis_purchase_confirmed', 'command': 'buy coelophysis',
                    'proof': proof, 'presentation': 'not_yet_qualified'})
    return proof


def selected_card_offsets(image, pattern):
    """Keep BUY fixed while requiring every card anchor at one bounded offset."""
    from .dinopark_scenes import matches
    card = [sample for sample in pattern['samples'] if sample['y'] < 170]
    button = [sample for sample in pattern['samples'] if sample['y'] >= 170]
    if len(card) != 35 or len(button) != 13 or pattern['min_matches'] != 48:
        return [0] if matches(image, pattern) else []
    fixed = {'samples': button, 'min_matches': len(button), 'tolerance': pattern['tolerance'],
             'reject': pattern.get('reject', [])}
    if not matches(image, fixed):
        return []
    return [offset for offset in range(-24, 25) if all(
        0 <= sample['x'] + offset < image.width and all(
            abs(a - b) <= pattern['tolerance'] for a, b in zip(
                image.getpixel((sample['x'] + offset, sample['y'])), sample['rgb']))
        for sample in card)]


def _wait(text, budget, view, expected, *, transient=(), guest_ms=12000):
    from .dinopark_scenes import balances, matches, take_frame
    waits = text.dinosaur_order.setdefault('wait_guest_ms', {})
    elapsed = waits.get(view, 0)
    while True:
        budget.timeout()
        state = None
        if text.dinosaur_order.get('last_input_phase') == 'confirm':
            try:
                state = native_state(text.debug)
                commit_proof(text.dinosaur_order, state)
            except ValueError:
                pass  # A paused instruction interval is not necessarily the completed effect.
            else:
                _record_commit(text, state)
        money = state['balances'] if state is not None else balances(text.debug)
        if money not in (expected, *transient):
            raise RuntimeError('Unexpected original Coelophysis balances; outcome unknown')
        budget.timeout()
        frame, image = take_frame(text.project, text.debug, 'coelophysis-' + view, hooks=False)
        mouse = text.debug.call('input.mouse.state')['mouse']
        offsets = selected_card_offsets(image, text.patterns[view]) if view == 'coel_selected' else None
        visible = bool(offsets) if offsets is not None else matches(image, text.patterns[view])
        ready = (money == expected and visible and
                 not mouse['buttons'] and not mouse['release_pending'])
        text.event({'phase': 'coelophysis_observation', 'view': view, 'frame': frame,
                    'matched': ready, 'balances': money, 'guest_ms': elapsed,
                    **({'selected_card_offsets': offsets} if offsets is not None else {})})
        if ready:
            return frame
        if elapsed >= guest_ms:
            raise TimeoutError('Coelophysis phase guest budget; outcome remains unqualified')
        step = min(500, guest_ms - elapsed)
        waits[view] = elapsed + step
        budget.run(text.debug, step)
        elapsed += step


def _press(text, budget, phase, point, name):
    from .operation_budget import RpcAdmissionTimeout
    budget.timeout()
    order = text.dinosaur_order
    previous = {key: deepcopy(order.get(key)) for key in ('phase', 'last_input_phase', 'last_input')}
    order.update(phase=phase, last_input_phase=phase, last_input=None)
    # A failed click without a returned ticket remains unknown; never repeat it.
    try:
        ticket = text.shop_click(point, None, name)
    except RpcAdmissionTimeout:
        # Only this exception proves that the new input never reached transport.
        order.update(previous)
        raise
    order['last_input'] = deepcopy(ticket)
    text.event({'phase': 'coelophysis_input_sent', 'order_id': order['id'],
                'purchase_phase': phase, 'input': ticket})
    budget.run(text.debug, 250)  # Consume the one queued press and its release before checking readiness.


def _qualify_catalogue(text, frame):
    from .dinopark_scenes import definition, pixel_predicate
    predicate = pixel_predicate(text.patterns['after'])
    selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                           'hex': text.debug.memory('4020:3c5c', length=2)['hex']}}
    street = text.project.debug_scene_info(text.street)['definition']['match']
    document = definition(frame, 'DinoMart after Coelophysis purchase', predicate, selector,
                          'mart.back', [216, 187], street)
    text.mart = text.project.debug_save_scene('dinomart', document, parent=text.mart)['id']
    text.dinosaur_bought = True
    text.dinosaur_order['phase'] = 'committed'
    return {'frame': frame, 'proof': text.dinosaur_order['proof']}


def qualify_purchase(text):
    """Read the paused original effect and display; no input, execution or restore."""
    from .dinopark_scenes import matches, take_frame
    order = text.dinosaur_order
    if order['run'] != text.debug.run_id:
        raise ValueError('Purchase belongs to another original run')
    after = native_state(text.debug)
    _record_commit(text, after)
    frame, image = take_frame(text.project, text.debug, 'coelophysis-reconciled', hooks=False)
    if not matches(image, text.patterns['after']):
        raise ValueError('Committed purchase presentation is not qualified')
    mouse = text.debug.call('input.mouse.state')['mouse']
    if mouse['buttons'] or mouse['release_pending']:
        raise ValueError('Original purchase pointer release remains pending')
    return _qualify_catalogue(text, frame)


def buy(text):
    budget = PurchaseBudget()
    with budget.bind(text.debug):
        return _buy(text, budget)


def _buy(text, budget):
    from .dinopark_scenes import prepare_mart_first_page
    if text.current != 'dinomart':
        return 'That action is not available in this scene.'
    if text.dinosaur_order is not None:
        return 'This dinosaur order is already recorded. No input was sent; reconcile an uncertain result.'
    before = native_state(text.debug)
    if (not text.land_bought or text.dinosaur_bought or before['pens'] or
            before['balances'] != {'cash': 4500, 'loan': 5000, 'working_cash': 4500}):
        return 'This purchase is not qualified for the current balances or herd. No input was sent.'
    budget.timeout()
    text.dinosaur_order = {'id': secrets.token_hex(16), 'run': text.debug.run_id,
                          'source_revision': text.mart, 'before': before, 'phase': 'prepare',
                          'last_input': None, 'proof': None}
    text.event({'phase': 'intent', 'command': 'buy coelophysis', 'before': before,
                'input': 'not_yet_sent', 'order_id': text.dinosaur_order['id']})
    prepare_mart_first_page(text, budget=budget)
    text.debug.scene_assert(text.mart, object='mart.back')
    unchanged = before['balances']
    _press(text, budget, 'select', (160, 87), 'select dinosaur')
    return _advance(text, budget)


def recovery_view(text):
    """Qualify the owned pending intent; its continuation checks each next input."""
    order = text.dinosaur_order
    if order['run'] != text.debug.run_id:
        raise ValueError('Order belongs to another guest')
    state = native_state(text.debug)
    if state['balances'] not in (
            {'cash':4500, 'loan':5000, 'working_cash':4500},
            {'cash':4500, 'loan':5000, 'working_cash':3250},
            {'cash':3250, 'loan':5000, 'working_cash':3250}):
        raise ValueError('Original order balances changed outside the qualified intent')
    if state['pens'] not in ([], [{'pen':1, 'species':4, 'count':1}]):
        raise ValueError('Original order herd is not qualified')
    return state


def resume(text):
    order = text.dinosaur_order
    if (not isinstance(order, dict) or order['phase'] not in ('select','price','order','place','confirm','committed') or
            not order.get('last_input') or order['last_input'].get('accepted') is not True or
            order['last_input'].get('delivery') != 'queued'):
        raise ValueError('No qualified original order continuation')
    budget = PurchaseBudget()
    with budget.bind(text.debug):
        recovery_view(text)
        text.event({'phase':'coelophysis_continuation','order_id':order['id'],
                    'purchase_phase':order['phase'],'original_input':'not_repeated'})
        return _advance(text, budget)


def _advance(text, budget):
    order = text.dinosaur_order
    unchanged = order['before']['balances']
    if order['phase'] == 'select':
        _wait(text, budget, 'coel_picked', unchanged)
        _press(text, budget, 'price', (160, 103), 'select price')
    if order['phase'] == 'price':
        _wait(text, budget, 'coel_selected', unchanged)
        selected = int.from_bytes(bytes.fromhex(text.debug.memory('4020:68a5', length=2)['hex']), 'little')
        price = int.from_bytes(bytes.fromhex(text.debug.memory('4020:45b8', length=4)['hex']), 'little')
        order.update(species=selected, price=price)
        text.event({'phase': 'dinosaur_selection', 'species': selected, 'price': price, 'purchase_input': 'not_sent'})
        if selected != 4 or price != 1250:
            raise ValueError('Original species or price is not the qualified Coelophysis order; BUY withheld')
        _press(text, budget, 'order', (187, 187), 'order dinosaur')
    staged = {'cash': 4500, 'loan': 5000, 'working_cash': 3250}
    if order['phase'] == 'order':
        _wait(text, budget, 'placement', staged, transient=(unchanged,), guest_ms=20000)
        _press(text, budget, 'place', (42, 50), 'place dinosaur')
    if order['phase'] == 'place':
        _wait(text, budget, 'placed', staged)
        _press(text, budget, 'confirm', (188, 187), 'confirm dinosaur placement')
    committed = {'cash': 3250, 'loan': 5000, 'working_cash': 3250}
    frame = _wait(text, budget, 'after', committed, transient=(staged,))
    _record_commit(text, native_state(text.debug))
    _qualify_catalogue(text, frame)
    text.event({'phase': 'result', 'command': 'buy coelophysis',
                'before': unchanged, 'after': committed, 'persistence': 'unknown'})
    return 'Coelophysis placed in the desert plot for $1,250. Cash: $3,250.'
