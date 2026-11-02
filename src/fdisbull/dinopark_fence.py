"""Finite original wood-fence phases and a read-only committed-effect witness."""
from copy import deepcopy
import secrets
import struct

from .dinopark_purchase import PurchaseBudget

PHASE_GUEST_MS=16000
PHASES=('cover','page','tab','price','wood','retab','map','place','confirm',
        'inspect','inspection_close','return','committed')
CURSOR_POINTS={
    'general_store':((270,140),(205,105),(263,165),(160,54)),
    'fence_tab':((160,54),(110,109),(60,85)),
    'fence_selected':((60,85),(160,54),(160,188),(216,187)),
    'fence_map':((160,188),(42,50)),
    'fence_staged':((42,50),(216,187)),
    'fence_reopened':((160,188),(188,187)),
}


def observation_pattern(text,view):
    pattern=text.patterns[view]
    points=CURSOR_POINTS.get(view)
    if points is None:return pattern
    samples=[s for s in pattern['samples'] if not any(
        x-12<=s['x']<=x+20 and y-12<=s['y']<=y+28 for x,y in points)]
    if not samples or len(samples)*2<len(pattern['samples']):
        raise ValueError('Insufficient fence pixels outside cursor regions')
    return {**pattern,'samples':samples,'min_matches':len(samples)}


def native_state(debug):
    from .dinopark_scenes import balances
    raw=bytes.fromhex(debug.memory('4020:4384',length=200)['hex'])
    if len(raw)!=200:raise ValueError('Original fence records are incomplete')
    pens=[]
    for i in range(10):
        fence=struct.unpack_from('<h',raw,i*20+10)[0]
        species,count=struct.unpack_from('<hh',raw,i*20+14)
        if not -2<=fence<=5 or not -1<=species<20 or count<0 or species==-1 and count:
            raise ValueError('Original fence/herd record is unqualified')
        pens.append({'fence':fence,'species':species,'count':count})
    return {'balances':balances(debug),'pens':pens}


def expected_state(order,*,selected=False,committed=False):
    state=deepcopy(order['before'])
    if selected or committed:state['balances']['working_cash']=2250
    if committed:
        state['balances']['cash']=2250
        state['pens'][9]['fence']=0
    return state


def _record_commit(text,state):
    order=text.fence_order;ticket=order.get('inputs',{}).get('confirm',{})
    if (order['run']!=text.debug.run_id or order['source_revision']!=text.locations['general_store'] or ticket.get('accepted') is not True or
            ticket.get('delivery')!='queued' or state!=expected_state(order,committed=True)):
        raise ValueError('Original wood fence commit remains unqualified')
    if not order.get('proof'):
        order['proof']={'order_id':order['id'],'run':order['run'],'price':1000,'pen':10,
                        'before':deepcopy(order['before']),'after':deepcopy(state),'input':deepcopy(ticket)}
        text.event({'phase':'fence_purchase_confirmed','command':'buy wood fence',
                    'proof':deepcopy(order['proof']),'presentation':'not_yet_qualified'})
    return order['proof']


def _read(text,view,goal,*,transient=()):
    from .dinopark_scenes import take_frame,matches
    state=native_state(text.debug)
    if 'confirm' in text.fence_order['inputs'] and state==expected_state(text.fence_order,committed=True):
        _record_commit(text,state)
    if state not in (goal,*transient):
        raise ValueError('Original fence state changed outside its qualified phase: '+repr(state))
    frame,image=take_frame(text.project,text.debug,'fence-'+view,hooks=False)
    mouse=text.debug.call('input.mouse.state')['mouse']
    ready=(state==goal and matches(image,observation_pattern(text,view)) and
           not mouse['buttons'] and not mouse['release_pending'])
    text.event({'phase':'fence_observation','view':view,'frame':frame,'state':state,
                'ready':ready,'input':'not_sent'})
    return ready,frame


def _allowance(text,budget,ms):
    order=text.fence_order;elapsed=order.setdefault('guest_requested_ms',{}).get(order['phase'],0)
    if elapsed+ms>PHASE_GUEST_MS:
        raise TimeoutError('Fence phase guest budget exhausted; original inputs will not be repeated')
    return budget.timeout(),elapsed


def _run(text,budget,ms):
    timeout,elapsed=_allowance(text,budget,ms);order=text.fence_order
    order['guest_requested_ms'][order['phase']]=elapsed+ms
    try:result=text.debug.run(guest_ms=ms,timeout_ms=timeout,fast_forward=True)
    except Exception:
        order['execution_unknown']=True
        raise
    if result.get('outcome')!='guest_time':
        order['execution_unknown']=True
        raise RuntimeError('Original fence execution stopped: '+str(result.get('outcome')))


def _wait(text,budget,view,goal,*,transient=()):
    while True:
        ready,frame=_read(text,view,goal,transient=transient)
        if ready:return frame
        _run(text,budget,500)


def _press(text,budget,phase,point,view,goal):
    from .operation_budget import RpcAdmissionTimeout
    _allowance(text,budget,150)
    ready,_=_read(text,view,goal)
    if not ready:raise ValueError('Fence source is not ready; press withheld')
    moved=text.debug.call('input.mouse.move',{'x':point[0],'y':point[1]})
    if moved.get('accepted') is not True:raise ValueError('Fence pointer move unavailable; press withheld')
    _run(text,budget,150)
    mouse=text.debug.call('input.mouse.state')['mouse']
    if mouse['buttons'] or mouse['release_pending'] or any(mouse[k]!=moved['mouse'][k] for k in ('x','y')):
        raise ValueError('Fence pointer did not settle; press withheld')
    ready,frame=_read(text,view,goal)
    if not ready:raise ValueError('Fence source changed while preparing pointer; press withheld')
    text.event({'phase':'fence_pointer_prepared','purchase_phase':phase,'point':list(point),
                'frame':frame,'press':'not_sent'})
    order=text.fence_order
    previous={k:deepcopy(order.get(k)) for k in ('phase','last_input_phase','last_input')}
    order.update(phase=phase,last_input_phase=phase,last_input=None)
    try:ticket=text.shop_click(point,None,'fence '+phase)
    except RpcAdmissionTimeout:
        order.update(previous)
        raise
    order['last_input']=deepcopy(ticket);order['inputs'][phase]=deepcopy(ticket)
    text.event({'phase':'fence_input_sent','order_id':order['id'],'purchase_phase':phase,'input':ticket})
    _run(text,budget,250)


def qualify_purchase(text):
    """Certify native fence effect and final street without execution/input/restore."""
    order=text.fence_order
    if order['run']!=text.debug.run_id:raise ValueError('Fence belongs to another original run')
    _record_commit(text,native_state(text.debug))
    ready,frame=_read(text,'shop_street',expected_state(order,committed=True))
    if not ready:raise ValueError('Fence return view remains unqualified')
    text.debug.scene_assert(text.street,object='street.office')
    text.current,text.fence_bought='street',True
    order['phase']='committed'
    return {'frame':frame,'proof':order['proof']}


def recovery_view(text):
    order=text.fence_order
    if (order['run']!=text.debug.run_id or order['source_revision']!=text.locations['general_store'] or
            text.debug.call('session.status').get('state')!='stopped'):
        raise ValueError('Fence recovery belongs to another or running context')
    state=native_state(text.debug)
    if state not in [expected_state(order),expected_state(order,selected=True),expected_state(order,committed=True)]:
        raise ValueError('Original fence recovery state remains unqualified')
    return state


def buy(text):
    if text.current!='general_store':return 'That action is not available in this scene.'
    if text.fence_order is not None:return 'This fence order is already recorded. No input was sent; reconcile it.'
    before=native_state(text.debug)
    expected=[{'fence':-2,'species':-1,'count':0} for _ in range(9)]+[{'fence':-1,'species':4,'count':1}]
    if (not text.dinosaur_bought or text.fence_bought or before['balances']!=dict(cash=3250,loan=5000,working_cash=3250) or before['pens']!=expected):
        return 'This fence purchase requires the qualified first dinosaur and $3,250 cash. No input was sent.'
    text.debug.scene_assert(text.locations['general_store'],object='general_store.catalogue')
    text.fence_order={'id':secrets.token_hex(16),'run':text.debug.run_id,
                      'source_revision':text.locations['general_store'],'before':before,'phase':'prepare',
                      'last_input':None,'inputs':{},'proof':None,'execution_unknown':False}
    text.event({'phase':'intent','command':'buy wood fence','order_id':text.fence_order['id'],
                'before':before,'input':'not_yet_sent'})
    budget=PurchaseBudget(label='Fence purchase')
    with budget.bind(text.debug):
        _press(text,budget,'cover',(205,105),'general_store',before)
        return _advance(text,budget)


def resume(text):
    order=text.fence_order
    if (not isinstance(order,dict) or order.get('phase') not in PHASES or order.get('execution_unknown') or
            (order.get('last_input') or {}).get('accepted') is not True or
            (order.get('last_input') or {}).get('delivery')!='queued'):
        raise ValueError('No qualified original fence continuation')
    budget=PurchaseBudget(label='Fence purchase')
    with budget.bind(text.debug):
        recovery_view(text)
        text.event({'phase':'fence_continuation','order_id':order['id'],'original_input':'not_repeated'})
        return _advance(text,budget)


def _advance(text,budget):
    order=text.fence_order;before=expected_state(order);staged=expected_state(order,selected=True)
    committed=expected_state(order,committed=True)
    steps=[('cover','general_store','page',(263,165),before),
           ('page','general_store','tab',(160,54),before),
           ('tab','fence_tab','price',(110,109),before),
           ('price','fence_tab','wood',(60,85),before),
           ('wood','fence_selected','retab',(160,54),before),
           ('retab','fence_selected','map',(160,188),before),
           ('map','fence_map','place',(42,50),before),
           ('place','fence_staged','confirm',(216,187),staged),
           ('confirm','fence_selected','inspect',(160,188),committed),
           ('inspect','fence_reopened','inspection_close',(188,187),committed),
           ('inspection_close','fence_selected','return',(216,187),committed)]
    for phase,view,following,point,goal in steps:
        if order['phase']==phase:
            transient=(before,) if phase=='place' else (staged,) if phase=='confirm' else ()
            _wait(text,budget,view,goal,transient=transient)
            _press(text,budget,following,point,view,goal)
    if order['phase']=='return':_wait(text,budget,'shop_street',committed)
    qualify_purchase(text)
    text.event({'phase':'result','command':'buy wood fence','proof':deepcopy(order['proof'])})
    return 'Wood fence placed around the dinosaur’s pen for $1,000. Cash: $2,250. You are on the street.'
