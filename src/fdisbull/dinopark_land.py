"""Bounded first-desert-plot interaction over the original DOS game.

The qualified slice changes record 10's allocation marker from -2 to -1 and
commits $500. The other 198 pen bytes must remain identical. A reservation,
queued click, or SOLD artwork alone is not a completed purchase.
"""
from copy import deepcopy
import secrets
import struct

from .dinopark_purchase import PurchaseBudget

PEN_MARKER_OFFSET = 190
PHASE_GUEST_MS = 16000
# The retained profiles include the original software hand. Exclude its
# reference position and the next prepared control, then require EVERY other
# authored sample. These masks do not replace native phase/allocation checks.
CURSOR_POINTS = {'estate':((60,140),(60,100)), 'choice':((60,100),(145,187)),
                 'inventory':((145,187),(172,187)), 'plot':((172,187),(42,52)),
                 'plot_staged':((42,52),(201,187))}


def observation_pattern(text, view):
    pattern = text.patterns[view]
    points = CURSOR_POINTS.get(view)
    if points is None:
        return pattern
    samples = [sample for sample in pattern['samples'] if not any(
        x-12 <= sample['x'] <= x+20 and y-12 <= sample['y'] <= y+28 for x,y in points)]
    if not samples or len(samples)*2 < len(pattern['samples']):
        raise ValueError('Insufficient land pixels outside the cursor regions')
    return {**pattern, 'samples':samples, 'min_matches':len(samples)}


def native_state(debug):
    from .dinopark_scenes import balances
    raw = bytes.fromhex(debug.memory('4020:4384', length=200)['hex'])
    if len(raw) != 200:
        raise ValueError('Original land allocation data is incomplete')
    return {'balances':balances(debug), 'pens':raw.hex()}


def expected_state(order, *, selected=False, committed=False):
    state = deepcopy(order['before'])
    if committed:
        raw = bytearray.fromhex(state['pens'])
        struct.pack_into('<h', raw, PEN_MARKER_OFFSET, -1)
        state['pens'] = raw.hex()
    if selected or committed:
        state['balances']['working_cash'] = 4500
    if committed:
        state['balances']['cash'] = 4500
    return state


def _record_commit(text, state):
    order = text.land_order
    ticket = order.get('last_input') or {}
    if (order['run'] != text.debug.run_id or order.get('last_input_phase') != 'confirm' or
            ticket.get('accepted') is not True or ticket.get('delivery') != 'queued' or
            state != expected_state(order, committed=True)):
        raise ValueError('Original land purchase remains unqualified')
    if not order.get('proof'):
        order['proof'] = {'order_id':order['id'], 'run':order['run'], 'price':500,
                          'pen':10, 'before':deepcopy(order['before']), 'after':deepcopy(state),
                          'input':deepcopy(ticket)}
        text.event({'phase':'land_purchase_confirmed', 'command':'buy desert plot',
                    'proof':deepcopy(order['proof']), 'presentation':'not_yet_qualified'})
    return order['proof']


def _read(text, view, goal, *, transient=()):
    from .dinopark_scenes import matches, take_frame
    state = native_state(text.debug)
    if text.land_order['phase'] == 'confirm' and state == expected_state(text.land_order, committed=True):
        _record_commit(text, state)  # Preserve the effect before the first display read.
    if state not in (goal, *transient):
        raise ValueError('Original land state changed outside the qualified phase: ' + repr(state))
    if view == 'plot_staged' and state == goal:
        draft = bytes.fromhex(text.debug.memory('4020:b91c', length=200)['hex']).hex()
        if draft != expected_state(text.land_order, committed=True)['pens']:
            raise ValueError('Original draft land allocation is unqualified; confirmation withheld')
        text.land_order['selection_proof'] = {'draft_address':'4020:b91c', 'draft_pens':draft,
                                              'committed_state':deepcopy(state)}
    frame,image = take_frame(text.project, text.debug, 'land-' + view, hooks=False)
    mouse = text.debug.call('input.mouse.state')['mouse']
    ready = (state == goal and matches(image, observation_pattern(text, view)) and
             not mouse['buttons'] and not mouse['release_pending'])
    text.event({'phase':'land_observation', 'view':view, 'frame':frame,
                'state':state, 'ready':ready, 'input':'not_sent'})
    return ready,frame


def _allowance(text, budget, ms):
    order = text.land_order
    phase = order['phase']
    elapsed = order.setdefault('guest_requested_ms', {}).get(phase, 0)
    if elapsed + ms > PHASE_GUEST_MS:
        raise TimeoutError('Land phase guest budget exhausted; original inputs will not be repeated')
    return budget.timeout(),elapsed  # Admission executes no guest code or input.


def _run(text, budget, ms):
    timeout,elapsed = _allowance(text,budget,ms)
    order = text.land_order
    phase = order['phase']
    order['guest_requested_ms'][phase] = elapsed + ms
    try:
        result = text.debug.run(guest_ms=ms, timeout_ms=timeout, fast_forward=True)
    except Exception:
        # A run is a composed operation. Even a later admission rejection does
        # not prove that its earlier execution requests were undispatched.
        order['execution_unknown'] = True
        raise
    if result.get('outcome') != 'guest_time':
        order['execution_unknown'] = True
        raise RuntimeError('Original land execution stopped: ' + str(result.get('outcome')))


def _wait(text, budget, view, goal, *, transient=()):
    while True:
        ready,frame = _read(text, view, goal, transient=transient)
        if ready:
            return frame
        _run(text, budget, 500)


def _press(text, budget, phase, point, view, goal):
    from .operation_budget import RpcAdmissionTimeout
    _allowance(text,budget,150)  # Do not queue motion when preparation cannot run.
    ready,_ = _read(text, view, goal)
    if not ready:
        raise ValueError('Land control source is not ready; press withheld')
    moved = text.debug.call('input.mouse.move', {'x':point[0], 'y':point[1]})
    if moved.get('accepted') is not True:
        raise ValueError('Land pointer move was not accepted; press withheld')
    _run(text, budget, 150)
    mouse = text.debug.call('input.mouse.state')['mouse']
    if (mouse['buttons'] or mouse['release_pending'] or
            any(mouse[k] != moved['mouse'][k] for k in ('x','y'))):
        raise ValueError('Land pointer has not settled; press withheld')
    ready,frame = _read(text, view, goal)
    if not ready:
        raise ValueError('Land source changed while preparing the pointer; press withheld')
    text.event({'phase':'land_pointer_prepared', 'purchase_phase':phase,
                'point':list(point), 'frame':frame, 'mouse':mouse, 'press':'not_sent'})
    order = text.land_order
    previous = {k:deepcopy(order.get(k)) for k in ('phase','last_input_phase','last_input')}
    order.update(phase=phase, last_input_phase=phase, last_input=None)
    try:
        ticket = text.shop_click(point, None, 'land ' + phase)
    except RpcAdmissionTimeout:
        order.update(previous)  # Only this single input RPC is proven undispatched.
        raise
    order['last_input'] = deepcopy(ticket)
    text.event({'phase':'land_input_sent', 'order_id':order['id'],
                'purchase_phase':phase, 'input':ticket})
    _run(text, budget, 250)


def qualify_purchase(text):
    """Read the paused original purchase and street; no execution or new input."""
    state = native_state(text.debug)
    _record_commit(text, state)
    ready,frame = _read(text, 'shop_street', expected_state(text.land_order, committed=True))
    if not ready:
        raise ValueError('Committed land purchase presentation remains unqualified')
    text.debug.scene_assert(text.street, object='street.office')
    text.land_bought = True
    text.land_order['phase'] = 'committed'
    return {'frame':frame, 'proof':text.land_order['proof']}


def recovery_view(text):
    order = text.land_order
    if order['run'] != text.debug.run_id or order['source_revision'] != text.street:
        raise ValueError('Land order belongs to another original context')
    state = native_state(text.debug)
    if state not in [expected_state(order), expected_state(order, selected=True),
                     expected_state(order, committed=True)]:
        raise ValueError('Original land order state is unqualified')
    return state


def buy(text):
    if text.current != 'street':
        return 'That action is not available in this scene.'
    if text.land_order is not None:
        return 'This land order is already recorded. No input was sent; reconcile an uncertain result.'
    before = native_state(text.debug)
    raw = bytes.fromhex(before['pens'])
    if (text.land_bought or before['balances'] != dict(cash=5000, loan=5000, working_cash=5000) or
            any(struct.unpack_from('<h',raw,i*20+10)[0] != -2 for i in range(10))):
        return 'This land purchase is not qualified for the current state; no input was sent.'
    text.debug.scene_assert(text.street, object='street.office')
    text.land_order = {'id':secrets.token_hex(16), 'run':text.debug.run_id,
                       'source_revision':text.street, 'before':before, 'phase':'prepare',
                       'last_input':None, 'proof':None, 'execution_unknown':False}
    text.event({'phase':'intent', 'command':'buy desert plot', 'before':before,
                'order_id':text.land_order['id'], 'input':'not_yet_sent'})
    budget = PurchaseBudget(label='Land purchase')
    with budget.bind(text.debug):
        _press(text,budget,'enter',(60,140),'shop_street',before)
        return _advance(text,budget)


def resume(text):
    order = text.land_order
    if (not isinstance(order,dict) or order.get('execution_unknown') or
            order.get('phase') not in ('enter','type','inventory','map','select','confirm','committed') or
            (order.get('last_input') or {}).get('accepted') is not True or
            (order.get('last_input') or {}).get('delivery') != 'queued'):
        raise ValueError('No qualified original land continuation')
    budget = PurchaseBudget(label='Land purchase')
    with budget.bind(text.debug):
        recovery_view(text)
        text.event({'phase':'land_continuation', 'order_id':order['id'], 'original_input':'not_repeated'})
        return _advance(text,budget)


def _advance(text,budget):
    order = text.land_order
    before,staged = expected_state(order),expected_state(order,selected=True)
    steps = [('enter','estate','type',(60,100)),
             ('type','choice','inventory',(145,187)),
             ('inventory','inventory','map',(172,187)),
             ('map','plot','select',(42,52)),
             ('select','plot_staged','confirm',(201,187))]
    for phase,view,following,point in steps:
        if order['phase'] == phase:
            goal = staged if phase == 'select' else before
            _wait(text,budget,view,goal,transient=(before,) if phase == 'select' else ())
            _press(text,budget,following,point,view,goal)
    if order['phase'] == 'confirm':
        _wait(text,budget,'shop_street',expected_state(order,committed=True),transient=(staged,))
    qualify_purchase(text)
    text.event({'phase':'result','command':'buy desert plot', 'proof':deepcopy(order['proof'])})
    return 'Desert plot purchased for $500. Cash: $4,500. You are on the street.'
