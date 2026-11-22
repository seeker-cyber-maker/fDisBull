"""Bounded pending-event delivery through the actual QMP framing/delegate.

The socket peer is authored. These checks do not qualify QEMU monitor timing,
throttle cardinality, or actual guest frame/key behavior.
"""
from copy import deepcopy
import json
import threading
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_observation_authority import ObservationAuthority, _Admission
from fdisbull.qemu_pending_events import (
    COMMAND, MODEL, BOUNDARY, MAX_REPLY, MAX_WIRE, validate_events, validate_reply,
)
from fdisbull.qemu_session_revision import SessionRevision


def event(name='RTC_CHANGE', **data):
    return {'event': name, 'data': data}


def response(events=(), *, request_id=1, status='paused'):
    return {'id': request_id, 'return': {
        'model': MODEL, 'boundary': BOUNDARY,
        'monitor-id': '01234567-89ab-cdef-0123-456789abcdef',
        'monitor-epoch': 1, 'status': status,
        'event-count': len(events), 'events': list(events),
    }}


def line(value):
    return json.dumps(value, ensure_ascii=True).encode('ascii')+b'\n'


class Wire:
    def __init__(self):
        self.buffer = bytearray()
        self.requests, self.recv_sizes = [], []
        self.closed = 0
        self.reply = response()
        self.prefix = self.suffix = b''
        self.fragment = 65536

    def settimeout(self, value):
        assert value > 0

    def sendall(self, data):
        self.requests.append(json.loads(data))
        reply = self.reply(self.requests[-1]) if callable(self.reply) else self.reply
        if type(reply) is dict:
            reply = dict(reply, id=self.requests[-1]['id'])
            reply = line(reply)
        self.buffer.extend(self.prefix+reply+self.suffix)

    def recv(self, size):
        self.recv_sizes.append(size)
        count = min(size, self.fragment)
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def close(self):
        self.closed += 1


@pytest.fixture
def peer(monkeypatch):
    wire, qmp = Wire(), QemuControl.__new__(QemuControl)
    qmp.socket, qmp.buffer, qmp.sequence = wire, bytearray(), 0
    qmp.lock, qmp.operation_deadline = threading.Lock(), None
    vm = SimpleNamespace(qmp=qmp, gdb=None, lock=threading.RLock(),
        operation_deadline=None, transport='pipe', qmp_commands={COMMAND})
    authority = vm.observation_authority = ObservationAuthority(vm)
    authority.bind(qmp=qmp)
    seen, identities = [], []
    original = _Admission.event
    def observe(admission, value):
        seen.append(deepcopy(value))
        identities.append(value)
        original(admission, value)
    monkeypatch.setattr(_Admission, 'event', observe)
    return SimpleNamespace(vm=vm, authority=authority, revision=vm.session_revision,
        qmp=qmp, wire=wire, seen=seen, identities=identities, observe=observe)


@pytest.mark.parametrize('values', [[], [event(offset=0)],
    [event(offset=0), event(offset=0)], [event('UNKNOWN_EVENT', flag=True, empty=None)],
    [event(offset=n) for n in range(64)]], ids=['empty','rtc','equal-rtc','unknown','maximum'])
def test_original_objects_delivered_once_with_real_revision_effects(peer, values):
    peer.wire.reply = response(values)
    before = peer.revision.snapshot()['state_revision']
    result = peer.qmp.call(COMMAND)
    assert peer.seen == values
    assert all(left is right for left, right in zip(peer.identities, result['events']))
    assert peer.revision.snapshot()['state_revision'] == before+len(values)
    assert peer.wire.requests == [{'execute': COMMAND, 'id': 1}]
    assert peer.qmp.socket is peer.wire and not peer.wire.closed


@pytest.mark.parametrize('bad', [
    {'event': ''}, {'event': 'é'}, {'event': 'x\0'}, {'event': 'x'*129},
    {'event':'X', 'data':[]}, {'event':'X', 'extra':1},
    {'event':'X', 'data':{'x':1.0}}, {'event':'X', 'data':{'x':1<<64}},
    {'event':'X', 'data':{'x':-(1<<63)-1}},
    {'event':'X', 'timestamp':{'seconds':True, 'microseconds':0}},
    {'event':'X', 'timestamp':{'seconds':0, 'microseconds':1000000}},
    {'event':'X', 'data':{'x':'a'*4097}},
    {'event':'X', 'data':{str(i):i for i in range(65)}},
], ids=['empty-name','unicode','nul','long-name','data-array','extra-field',
    'float','uint-overflow','int-underflow','bool-time','microseconds','long-string','object-size'])
def test_invalid_final_event_prevents_every_retained_delegate(peer, bad):
    peer.wire.reply = response([event(offset=0),bad])
    with pytest.raises((DebuggerError, ValueError)) as caught:
        peer.qmp.call(COMMAND)
    assert peer.seen == []
    assert caught.value.pending_events['batch_callbacks_started'] == 0
    assert peer.wire.closed == 1 and peer.qmp.socket is None


@pytest.mark.parametrize('edit', [
    lambda x:x.pop('model'), lambda x:x.update(extra=0),
    lambda x:x.update(**{'event-count':False}), lambda x:x.update(**{'monitor-epoch':True}),
    lambda x:x.update(**{'monitor-id':'01234567-89AB-cdef-0123-456789abcdef'}),
    lambda x:x.update(status='running'), lambda x:x.update(**{'event-count':2}),
], ids=['missing-field','extra-field','boolean-count','boolean-epoch','uppercase-uuid','running','count-mismatch'])
def test_exact_return_shape(peer, edit):
    reply = response([event()]); edit(reply['return']); peer.wire.reply = reply
    with pytest.raises(DebuggerError): peer.qmp.call(COMMAND)
    assert not peer.seen and peer.wire.closed == 1


@pytest.mark.parametrize('raw', [
    b'{"id":true,"return":{}}\n', b'{"id":1.0,"return":{}}\n',
    b'{"id":"1","return":{}}\n', b'{"id":2,"return":{}}\n',
    b'{"id":1,"id":1,"return":{}}\n', b'[]\n',
    b'{"id":1,"return":{},"error":{}}\n', b'{"id":1,"error":{}}\n',
    b'{"id":1,"return":{"x":NaN}}\n',
    b'{"id":1,"return":{}} {"id":1,"return":{}}\n',
], ids=['bool-id','float-id','string-id','wrong-id','duplicate-id','array',
    'conflicting-result','malformed-error','nan','two-packets-one-line'])
def test_strict_matching_packet_cannot_be_reused(peer, raw):
    peer.wire.reply = raw
    with pytest.raises((DebuggerError,ValueError)): peer.qmp.call(COMMAND)
    assert not peer.seen and peer.wire.closed == 1 and peer.qmp.socket is None


def test_typed_native_refusal_preserves_owner_and_is_not_empty_success(peer):
    peer.wire.reply = {'id':1,'error':{'class':'GenericError','desc':'not eligible'}}
    with pytest.raises(DebuggerError, match='not eligible') as caught:
        peer.qmp.call(COMMAND)
    assert not peer.seen and not peer.wire.closed and peer.qmp.socket is peer.wire
    assert caught.value.pending_events['validated_count'] == 0


@pytest.mark.parametrize('fragment', [1,17,65536])
def test_fragmented_bare_prefix_and_read_ahead_stay_separate(peer, fragment):
    bare, retained, later = event('BARE'), event('RETAINED'), event('LATER')
    peer.wire.fragment = fragment
    peer.wire.prefix, peer.wire.suffix = line(bare), line(later)
    peer.wire.reply = response([retained])
    result = peer.qmp.call(COMMAND)
    assert peer.seen == [bare,retained] and result['events'] == [retained]
    assert bytes(peer.qmp.buffer)+bytes(peer.wire.buffer) == line(later)
    assert all(size <= 65536 for size in peer.wire.recv_sizes)


def test_malformed_batch_does_not_erase_delivered_bare_prefix(peer):
    peer.wire.prefix = line(event('BARE'))
    peer.wire.reply = response([event(), {'event':''}])
    with pytest.raises(DebuggerError) as caught: peer.qmp.call(COMMAND)
    assert peer.seen == [event('BARE')]
    diagnostic = caught.value.pending_events
    assert diagnostic['bare_callbacks_started'] == diagnostic['bare_callbacks_returned'] == 1
    assert diagnostic['batch_callbacks_started'] == diagnostic['batch_callbacks_returned'] == 0


@pytest.mark.parametrize('change', ['list','event','nested','first','id','count','append','drop','reorder',
                                   'handler','equal-handler','lock','revision','monitor'])
def test_callback_mutations_refuse_before_next_delegate(peer, monkeypatch, change):
    peer.wire.reply = response([event(value=[0]),event(value=[1])])
    original_lock = peer.qmp.lock
    def mutate(admission, value):
        peer.observe(admission, value)
        packet = admission.reply
        if change == 'list': packet['return']['events'] = deepcopy(packet['return']['events'])
        elif change == 'event': packet['return']['events'][1] = deepcopy(packet['return']['events'][1])
        elif change == 'nested': value['data'] = deepcopy(value['data'])
        elif change == 'first': value['data']['value'][0] = 7
        elif change == 'id': packet['id'] = True
        elif change == 'count': packet['return']['event-count']=1
        elif change == 'append': packet['return']['events'].append(event())
        elif change == 'drop': packet['return']['events'].pop()
        elif change == 'reorder': packet['return']['events'].reverse()
        elif change == 'handler': admission.event = lambda value: None
        elif change == 'equal-handler':
            class EqualFunction:
                def __eq__(self,other):return True
            admission.event=SimpleNamespace(__self__=admission,__func__=EqualFunction())
        elif change == 'lock': peer.qmp.lock = threading.Lock()
        elif change == 'revision': peer.vm.session_revision = SessionRevision()
        else: peer.qmp._pending_event_monitor = ('foreign',1)
    monkeypatch.setattr(_Admission,'event',mutate)
    with pytest.raises(DebuggerError) as caught: peer.qmp.call(COMMAND)
    assert len(peer.seen) == 1 and caught.value.pending_events['batch_callbacks_returned'] == 1
    assert peer.wire.closed == 1 and not original_lock.locked()


def test_falsey_callback_error_retains_identity_and_honest_prefix(peer,monkeypatch):
    class FalseyError(RuntimeError):
        def __bool__(self): return False
    primary = FalseyError('callback changed state then failed')
    peer.wire.reply = response([event(n=0),event(n=1),event(n=2)])
    def fail(admission,value):
        peer.observe(admission,value)
        if len(peer.seen) == 2: raise primary
    monkeypatch.setattr(_Admission,'event',fail)
    with pytest.raises(FalseyError) as caught: peer.qmp.call(COMMAND)
    assert caught.value is primary and len(peer.seen) == 2
    assert primary.pending_events['batch_callbacks_started'] == 2
    assert primary.pending_events['batch_callbacks_returned'] == 1
    assert peer.wire.closed == 1


@pytest.mark.parametrize('fault', ['events','depth','nodes','total-nodes','strings','alias',
                                 'encoded-event','encoded-list'])
def test_batch_structural_budgets(fault):
    values = [event()]
    if fault == 'events': values *= 65
    elif fault == 'depth':
        value=0
        for _ in range(8): value=[value]
        values=[event(value=value)]
    elif fault == 'nodes': values=[event(value=list(range(256)))]
    elif fault == 'total-nodes': values=[event(value=list(range(200))) for _ in range(21)]
    elif fault == 'strings': values=[event(value='x'*4096) for _ in range(8)]
    elif fault == 'encoded-event': values=[event(value='\x7f'*3000)]
    elif fault == 'encoded-list': values=[event(value='\x7f'*2100) for _ in range(11)]
    else: values=[event(value=[])]*2
    with pytest.raises(DebuggerError): validate_events(values)


def test_numeric_extremes_and_depth_boundary():
    value = 0
    for _ in range(5): value=[value]
    validate_events([event(a=-(1<<63),b=(1<<64)-1,c=True,d=None,deep=value)])
    with pytest.raises(DebuggerError): validate_events([event(deep=[value])])
    validate_events([event(value=list(range(252)))])
    with pytest.raises(DebuggerError):validate_events([event(value=list(range(253)))])


def test_prebuffered_wire_bound_refuses_before_dispatch(peer):
    peer.qmp.buffer = bytearray(b' '*(MAX_WIRE+1))
    with pytest.raises(DebuggerError): peer.qmp.call(COMMAND)
    assert peer.wire.requests == [] and not peer.wire.closed


@pytest.mark.parametrize('fault',['line','bare-count','bare-bytes'])
def test_incoming_wire_budgets(peer, fault):
    if fault == 'line': peer.wire.reply = b' '*(MAX_REPLY+1)+b'\n'
    elif fault == 'bare-count': peer.wire.prefix=line(event())*65
    elif fault == 'bare-bytes': peer.wire.prefix=line(event(value='x'*4096))*64
    with pytest.raises(DebuggerError): peer.qmp.call(COMMAND)
    assert peer.wire.closed == 1


def test_initial_buffer_and_final_read_ahead_share_exact_total_wire_budget(peer):
    bare=line(event()).rstrip(b'\n')
    padded_bare=bare+b' '*(4095-len(bare))+b'\n'
    reply=line(response()).rstrip(b'\n')
    partial_reply=reply+b' '*(MAX_REPLY-1-len(reply))
    peer.qmp.buffer=bytearray(padded_bare*64+partial_reply)
    assert len(peer.qmp.buffer)==MAX_WIRE-1
    later=line(event('LATER'))
    peer.wire.reply=b'\n'+later
    peer.qmp.call(COMMAND)
    assert peer.wire.recv_sizes==[1]
    assert len(peer.seen)==64 and bytes(peer.wire.buffer)==later
    assert not peer.qmp.buffer and not peer.wire.closed


@pytest.mark.parametrize('advertised',[False,True])
@pytest.mark.parametrize('arguments',[None,{}])
def test_only_advertised_exact_noarg_dispatch_is_passive(peer,advertised,arguments):
    peer.vm.qmp_commands={COMMAND} if advertised else set()
    before=peer.revision.snapshot()['state_revision']
    peer.qmp.call(COMMAND,arguments)
    assert peer.revision.snapshot()['state_revision']==before+int(not advertised)


@pytest.mark.parametrize('arguments',[[],False,{'events':[]},{'unexpected':None}])
def test_argument_bearing_cut_refuses_before_send(peer,arguments):
    with pytest.raises(ValueError):peer.qmp.call(COMMAND,arguments)
    assert peer.wire.requests==[] and not peer.wire.closed


def test_captured_request_id_is_independent_of_mutable_client_sequence(peer,monkeypatch):
    peer.wire.reply=response([event(),event()])
    def delivered(admission,value):
        peer.observe(admission,value)
        peer.qmp.sequence=700
    monkeypatch.setattr(_Admission,'event',delivered)
    result=peer.qmp.call(COMMAND)
    assert len(result['events'])==len(peer.seen)==2 and peer.qmp.sequence==700
