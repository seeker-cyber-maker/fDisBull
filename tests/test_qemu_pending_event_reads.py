"""Public frame and status routes with actual bounded QMP pending replies."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_observation_authority import _Admission
from fdisbull.qemu_pending_events import COMMAND
from fdisbull.qemu_session_revision import SessionRevision
from test_qemu_pending_events import response, event, line
from test_qemu_frame_admission import (retained, read, metadata, ROUTES,
    assert_original_closed_once, observe_admission, on_command)
from test_qemu_video_frame import audio, observation, video


def install_batch(o, values, *, status='paused'):
    o.vm.transport='pipe'
    o.vm.qmp_commands=frozenset((*o.vm.qmp_commands,COMMAND))
    o.wire.calls.clear()
    send = o.wire.sendall
    cuts = []
    def respond(data):
        request = json.loads(data)
        if request['execute'] != COMMAND:
            return send(data)
        cuts.append(request)
        o.wire.calls.append((COMMAND, deepcopy(request.get('arguments'))))
        o.wire.buffer.extend(line(response(deepcopy(values), request_id=request['id'],status=status)))
        o.wire.pending_delay = 0
    o.wire.sendall = respond
    return cuts


@pytest.mark.parametrize('route',ROUTES)
@pytest.mark.parametrize('held',[[],['right']])
def test_all_frame_routes_cut_once_before_admission_without_touching_owned_keys(retained,monkeypatch,route,held):
    o=retained
    o.vm._frame_key_owner={'token':'authored-token','held':held,'generation':7,'fifo':[1,2]}
    before_keys=deepcopy(o.vm._frame_key_owner)
    values=[event(offset=0),event(offset=0),event('UNKNOWN_EVENT')]
    cuts=install_batch(o,values)
    admitted=observe_admission(o,monkeypatch)
    before=o.revision.snapshot()
    result=read(o,route)
    actual=metadata(result,route)
    assert len(cuts)==len(admitted)==1
    assert actual['state_revision']==before['state_revision']+3
    assert actual['state_revision']==o.revision.snapshot()['state_revision']
    assert o.vm._frame_key_owner==before_keys
    assert not any(name in ('stop','cont','x-fdisbull-frame-keys') for name,_ in o.wire.calls)
    assert not o.vm.closed


@pytest.mark.parametrize('route',ROUTES)
def test_bad_final_batch_member_refuses_before_frame_admission_or_artifact(retained,monkeypatch,route):
    o=retained
    install_batch(o,[event(),{'event':''}])
    admitted=observe_admission(o,monkeypatch)
    with pytest.raises(DebuggerError) as caught: read(o,route)
    assert admitted==[]
    assert caught.value.pending_events['batch_callbacks_started']==0
    assert_original_closed_once(o)


@pytest.mark.parametrize('route',ROUTES)
def test_later_bare_event_still_invalidates_admitted_frame(retained,monkeypatch,route):
    o=retained
    install_batch(o,[event()])
    original=o.session._frame_contract_admit
    def after(vm,identity):
        value=original(vm,identity)
        o.wire.buffer[:0]=line(event('LATER'))
        return value
    monkeypatch.setattr(o.session,'_frame_contract_admit',after)
    with pytest.raises(DebuggerError,match='changed'): read(o,route)
    assert_original_closed_once(o)


@pytest.mark.parametrize('replacement',['vm','revision','authority','project','process','context','qmp','gdb','lock'])
def test_retained_callback_replacement_refuses_and_closes_only_original(retained,monkeypatch,replacement):
    o=retained
    install_batch(o,[event(),event()])
    original=_Admission.event
    delegates=[]
    def mutate(admission,value):
        delegates.append(value)
        original(admission,value)
        if replacement=='vm': o.session.vm=SimpleNamespace(closed=False)
        elif replacement=='revision': o.vm.session_revision=SessionRevision()
        elif replacement=='authority': o.vm.observation_authority=SimpleNamespace(_active=object())
        elif replacement=='project': o.session.project=object()
        elif replacement=='process': o.session._process={}
        elif replacement=='context': o.vm.context=object()
        elif replacement=='qmp': o.vm.qmp=SimpleNamespace(socket=object())
        elif replacement=='gdb': o.vm.gdb=SimpleNamespace(socket=object())
        else: o.vm.lock=object()
    monkeypatch.setattr(_Admission,'event',mutate)
    with pytest.raises(DebuggerError): read(o,'probe')
    assert len(delegates)==1
    assert_original_closed_once(o)


def test_status_refreshes_after_tracker_and_cut_effects(retained):
    o=retained
    cuts=install_batch(o,[event(),event()])
    def project():
        o.revision.effect()
        return {'value':'current'}
    o.session._automatic_runtime_tracker=SimpleNamespace(status=project,close=lambda *args:None)
    before=o.revision.snapshot()['state_revision']
    result=o.session.status()
    assert len(cuts)==1 and result['automatic_runtime_tracking']=={'value':'current'}
    assert result['state_revision']==before+3==o.revision.snapshot()['state_revision']
    assert result['pending_events']['event-count']==2


def test_running_status_never_takes_cut(retained):
    o=retained
    cuts=install_batch(o,[event()])
    send=o.wire.sendall
    def running(data):
        request=json.loads(data)
        if request['execute']=='query-status':
            o.wire.calls.append(('query-status',None))
            o.wire.buffer.extend(line({'id':request['id'],'return':{'running':True,'status':'running'}}))
            o.wire.pending_delay=0
        else: send(data)
    o.wire.sendall=running
    result=o.session.status()
    assert result['state']=='running' and cuts==[] and 'pending_events' not in result


def test_status_cut_state_disagreement_preserves_batch_and_closes_original(retained):
    o=retained
    cuts=install_batch(o,[event()],status='debug')
    with pytest.raises(DebuggerError,match='disagrees') as caught:o.session.status()
    assert len(cuts)==1
    assert caught.value.pending_cut['status']=='debug'
    assert caught.value.pending_cut['events']==[event()]
    assert caught.value.result['native_state']['status']=='paused'
    assert_original_closed_once(o)


@pytest.mark.parametrize('running',[0,1,None,'false'])
def test_supported_status_requires_exact_running_boolean(retained,running):
    o=retained
    cuts=install_batch(o,[])
    send=o.wire.sendall
    def malformed(data):
        request=json.loads(data)
        if request['execute']=='query-status':
            o.wire.calls.append(('query-status',None))
            o.wire.buffer.extend(line({'id':request['id'],'return':{'running':running,'status':'paused'}}))
            o.wire.pending_delay=0
        else: send(data)
    o.wire.sendall=malformed
    with pytest.raises(DebuggerError): o.session.status()
    assert cuts==[]
    assert [name for name,_ in o.wire.calls]==['query-status']


def test_earlier_status_is_not_rebased_to_later_frame(retained):
    o=retained
    install_batch(o,[event()])
    status=o.session.status()
    saved=deepcopy(status)
    frame=read(o,'probe')
    assert frame['state_revision']==status['state_revision']+1
    assert status==saved


def test_strict_observation_rejects_cut_before_send(retained):
    o=retained
    cuts=install_batch(o,[])
    with pytest.raises(DebuggerError,match='unadmitted protocol'):
        with o.authority.observe(o.session,deadline=o.clock.now+1):
            o.qmp.call(COMMAND)
    assert cuts==[]


@pytest.mark.parametrize('unsupported',['missing-command','unix'])
def test_unsupported_status_adds_no_speculative_query(retained,unsupported):
    o=retained
    cuts=install_batch(o,[])
    if unsupported=='missing-command':o.vm.qmp_commands=frozenset()
    else:o.vm.transport='unix'
    result=o.session.status()
    assert result['state']=='stopped' and cuts==[]
    assert [name for name,_ in o.wire.calls]==['query-status']
    assert 'pending_events' not in result


@pytest.mark.parametrize('boundary',['lock-wait','receive','last-callback','snapshot','restore','release'])
def test_status_original_deadline_survives_every_completion_boundary(retained,monkeypatch,boundary):
    o=retained
    cuts=install_batch(o,[event(),event()])
    o.session._rpc_deadline=o.clock.now+1
    fired=[]
    def expire():
        assert not fired
        fired.append(True);o.clock.advance(2)
    if boundary=='lock-wait':
        acquire=o.original_lock.acquire
        def delayed(*args,**kwargs):
            value=acquire(*args,**kwargs)
            if not fired:expire()
            return value
        monkeypatch.setattr(o.original_lock,'acquire',delayed)
    elif boundary=='receive':
        recv=o.wire.recv
        def delayed(size):
            value=recv(size)
            if cuts and not fired:expire()
            return value
        monkeypatch.setattr(o.wire,'recv',delayed)
    elif boundary=='last-callback':
        deliver=_Admission.event
        seen=[]
        def delayed(admission,value):
            deliver(admission,value);seen.append(value)
            if len(seen)==2:expire()
        monkeypatch.setattr(_Admission,'event',delayed)
    elif boundary=='snapshot':
        snapshot=SessionRevision.snapshot
        def delayed(revision):
            value=snapshot(revision)
            if revision is o.revision and cuts and not fired:expire()
            return value
        monkeypatch.setattr(SessionRevision,'snapshot',delayed)
    elif boundary=='restore':o.gdb.after_restore=expire
    else:o.original_lock.after_release=expire
    with pytest.raises(TimeoutError) as caught:o.session.status()
    assert fired and len(cuts)==int(boundary!='lock-wait')
    if boundary=='last-callback':
        assert caught.value.pending_events['batch_callbacks_started']==2
        assert caught.value.pending_events['batch_callbacks_returned']==2
        assert caught.value.pending_events['validated_reply']['return']['event-count']==2
    if boundary=='receive':
        assert caught.value.pending_events['last_received_chunk']
        assert caught.value.pending_events['batch_callbacks_started']==0
    if boundary in ('restore','release'):
        assert caught.value.result['pending_events']['event-count']==2
    assert_original_closed_once(o)
