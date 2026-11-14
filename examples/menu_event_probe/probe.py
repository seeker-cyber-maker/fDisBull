"""Bounded menu experiment collector over an already-owned fDisBull session.

The caller supplies calibrated fdisbull-scene-1 revisions, selected field readers,
qualified input readiness, and one input operation. No title-specific selectors,
addresses or action recipes live here. This is an experiment helper, not an
unattended menu crawler or a replacement for SceneHandle.act().
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import time
from fdisbull.structure_patterns import canonical
from fdisbull.structure_events import classify_episode


def collect_episode(session, *, contexts, action, expected_context, record,
                    fields=None, slice_ms=100, samples=16, idle_samples=3,
                    readiness_evidence, input_ready=None):
    """Observe idle, guard once, submit once, then retain a fixed observation burst.

    ``record(kind, payload)`` must durably store the payload and return a reference.
    ``action(before)`` sends one admitted input using before's fresh frame/mode.
    A failure after submission propagates and is never retried here. Readiness
    callbacks are caller qualifications, not inferred from a stable picture.
    """
    if not isinstance(contexts,dict) or not 1<=len(contexts)<=8:
        raise ValueError('require 1..8 named scene revisions')
    if expected_context not in contexts:raise ValueError('missing expected context')
    for v,low,high in ((slice_ms,1,1000),(samples,1,128),(idle_samples,1,32)):
        if type(v) is not int or not low<=v<=high:raise ValueError('invalid observation budget')
    if not isinstance(readiness_evidence,dict) or any(not readiness_evidence.get(k) for k in contexts):
        raise ValueError('each context requires an explicit readiness qualification')
    fields=fields or {}
    if len(fields)>64:raise ValueError('selected-field budget')
    identity={'source_sha256':session.metadata['source_sha256'],
              'run':session.run_id,'epoch':getattr(session,'_runtime_epoch',None) or 'initial'}
    if identity['epoch'] is None:raise ValueError('runtime epoch unavailable')
    def current_identity():
        return {'source_sha256':session.metadata['source_sha256'],
                'run':session.run_id,'epoch':getattr(session,'_runtime_epoch',None) or 'initial'}
    def observe():
        if current_identity()!=identity:raise ValueError('run or restoration epoch changed')
        status=session.call('session.status')
        if status['state']!='stopped' or status.get('last_stop',{}).get('kind') not in (None,'entry','pause'):
            raise ValueError('unexpected/unowned guest stop')
        checks={k:session.scene_check(v,compact=True) for k,v in contexts.items()}
        matched=[k for k,v in checks.items() if v.get('status')=='matched' and v.get('scene_matched') is True]
        context=matched[0] if len(matched)==1 else None
        # A fresh sparse probe supplies the frame key for native admission.
        frame=session.frame_probe([])
        tick=session.call('execution.timing')['guest_ticks']
        values={k:f() for k,f in fields.items()}
        keyboard=session.keyboard.state()['keyboard']
        released=not any(keyboard.get(k) for k in ('pending_events','owned_keys','frame_keys'))
        ready=(context is not None and released and (input_ready is None or bool(input_ready(tick))))
        witness={'identity':identity,'tick':tick,'context':context,'fields':values,
                 'ready':ready,'frame':frame,'scene_checks':checks,
                 'readiness_evidence':readiness_evidence.get(context),'input_released':released}
        witness['evidence']=record('observation',deepcopy(witness))
        if not witness['evidence']:raise ValueError('observation was not retained')
        return witness
    def advance():
        r=session.run(guest_ms=slice_ms,timeout_ms=10000,fast_forward=True,stop_on_hook=True)
        record('continuation',r)
        if r.get('outcome')!='guest_time' or r.get('hook_hits'):raise ValueError('unexpected continuation stop')
    idle=[]
    for _ in range(idle_samples):
        idle.append(observe());advance()
    before=observe()
    if before['context']!=expected_context or before['ready'] is not True:
        raise ValueError('fresh pre-input guard did not qualify the requested context')
    intent=record('input-intent',{'before':before['evidence'],'identity':identity})
    if not intent:raise ValueError('input intent was not retained')
    started=time.perf_counter()
    try:
        sent=action(before);record('input-receipt',sent)
        after=[]
        for _ in range(samples):
            advance();after.append(observe())
    except BaseException as exc:
        record('interrupted',{'intent':intent,'error':str(exc),'retry_authorized':False})
        raise
    episode={'format':'fdisbull-observed-interaction-pilot-1','before':before,'idle':idle,'after':after,
             'action_receipt':sent,'input_intent':intent,
             'collection':'original session; sparse scene checks; caller-qualified context/field bindings'}
    result=classify_episode(episode)
    result['wall_seconds']=time.perf_counter()-started
    record('episode',episode);record('classification',result)
    return episode,result
