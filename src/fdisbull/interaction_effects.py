"""Explicit model effects with bound host requests and private checkpoints.

No host operation is dispatched here. A supplied completion is a caller claim,
not independently verified evidence that a native engine performed an action.
"""
from copy import deepcopy
from hashlib import sha256
import json

from .interaction_il import ILInvalid, _CAP, _require, _fields, _typed
from .interaction_flow import validate_flow
from .agi_effects import CONTRACT,validate_context,apply_effect,complete_effect


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def execute_effect_flow(document,state,capabilities,max_steps,max_call_depth,
                        effect_context,checkpoint,host_result):
    from .interaction_il import execute_il
    original, original_context = deepcopy(state),deepcopy(effect_context)
    completions=[];work=None;context=None
    try:
        validate_flow(document)
        _require(type(max_steps) is int and max_steps>=0,'invalid step budget')
        _require(type(max_call_depth) is int and 1<=max_call_depth<=64,'invalid call depth')
        _require(isinstance(capabilities,(list,tuple,set,frozenset)) and all(isinstance(x,str) for x in capabilities)
                 and set(capabilities)<=set(_CAP.values()),'invalid capabilities')
        declarations=document['variables'];program_hash=_digest(document)
        def check_state(values):
            _require(isinstance(values,dict) and values.keys()==declarations.keys()
                     and all(_typed(values[k],v['type']) for k,v in declarations.items()),'invalid state')
        def preflight(body,context):
            for b in body:
                _require(b['op']!='opaque','opaque block cannot execute')
                if b['op'] in _CAP:_require(_CAP[b['op']] in capabilities,'missing capability: '+_CAP[b['op']])
                if b['op']=='if':preflight(b['then'],context);preflight(b['else'],context)
                if b['op']=='effect':
                    for name in ('object','first','second'):
                        if name in b['args']:_require(str(b['args'][name]) in context['objects'],'missing object snapshot')
                    if 'view' in b['args']:_require(str(b['args']['view']) in context['views'],'missing view metadata')
                    if b['action']=='ui.print':
                        _require(str(b['args']['message']) in context['messages'].get(b['binding'],{}),'missing bound message')
        if checkpoint is None:
            _require(host_result is None,'host result requires a checkpoint')
            if state is None:state={k:v['initial'] for k,v in declarations.items()}
            check_state(state);original=deepcopy(state)
            context=validate_context(effect_context);original_context=deepcopy(context)
            work=deepcopy(state);stack=[];visited=[];trace=[];events=[];effects=[];completions=[]
            current=document['entry'];body_index=0
        else:
            _require(state is None and effect_context is None,'checkpoint cannot be combined with new state or context')
            _require(isinstance(checkpoint,dict),'invalid effect checkpoint')
            encoded=json.dumps(checkpoint,allow_nan=False).encode()
            _require(len(encoded)<=4*1024*1024,'checkpoint size budget exceeded')
            checkpoint=deepcopy(checkpoint)
            checksum=checkpoint.pop('integrity_sha256',None)
            _require(checksum==_digest(checkpoint),'checkpoint integrity mismatch')
            _fields(checkpoint,('format','program_sha256','original_state','original_context','state','context',
                     'continuation','body_index','stack','visited','control_trace','events','effect_trace',
                     'host_completions','max_steps','max_call_depth','pending','pending_block','request_id'))
            request_payload={k:v for k,v in checkpoint.items() if k!='request_id'}
            _require(checkpoint['request_id']==_digest(request_payload),'checkpoint request identity mismatch')
            _require(checkpoint['format']=='fdisbull-il-effect-suspension-1','invalid effect checkpoint')
            original=checkpoint['original_state'];original_context=validate_context(checkpoint['original_context'])
            check_state(original)
            _require(checkpoint['program_sha256']==program_hash,'checkpoint program mismatch')
            work=checkpoint['state'];check_state(work);context=validate_context(checkpoint['context'])
            current=checkpoint['continuation'];body_index=checkpoint['body_index']
            stack=checkpoint['stack'];visited=checkpoint['visited'];trace=checkpoint['control_trace']
            events=checkpoint['events'];effects=checkpoint['effect_trace'];completions=checkpoint['host_completions']
            _require(type(checkpoint['max_steps']) is int and checkpoint['max_steps']>=0
                     and type(checkpoint['max_call_depth']) is int and 1<=checkpoint['max_call_depth']<=64,
                     'invalid checkpoint limits')
            _require(all(isinstance(items,list) for items in (visited,trace,events,effects,completions)),
                     'invalid checkpoint histories')
            ids=set(document['continuations'])
            def collect_ids(body):
                for block in body:
                    ids.add(block['id'])
                    if block['op']=='if':collect_ids(block['then']);collect_ids(block['else'])
            for item in document['continuations'].values():collect_ids(item['body'])
            _require(all(isinstance(v,str) and v in ids for v in visited),'invalid visited history')
            _require(all(isinstance(v,dict) for v in trace+events+effects+completions),'invalid checkpoint history item')
            max_steps=min(max_steps,checkpoint['max_steps']);max_call_depth=min(max_call_depth,checkpoint['max_call_depth'])
            _require(current in document['continuations'] and type(body_index) is int and
                     1<=body_index<=len(document['continuations'][current]['body']),'invalid suspended body position')
            _require(isinstance(stack,list) and len(stack)<=max_call_depth and
                     all(x is None or x in document['continuations'] for x in stack),'invalid suspended stack')
            pending_block=document['continuations'][current]['body'][body_index-1]
            _require(pending_block['op']=='effect' and pending_block['id']==checkpoint['pending_block'],
                     'checkpoint effect mismatch')
            pending=checkpoint['pending']
            kind={'object.draw':'draw','object.erase':'erase','ui.print':'print'}.get(pending_block['action'])
            _require(isinstance(pending,dict) and kind is not None and pending.get('kind')==kind
                     and pending.get('binding')==pending_block['binding'],'invalid suspended effect kind')
            if kind!='print':_require(pending.get('object')==pending_block['args']['object'],'invalid suspended object')
            _require(effects and effects[-1].get('block_id')==pending_block['id']
                     and effects[-1].get('status')=='pending_host','invalid pending effect trace')
        for continuation in document['continuations'].values():preflight(continuation['body'],context)

        def write_results(block,results):
            _require(results.keys()==block['outputs'].keys(),'effect output ports mismatch')
            for port,value in results.items():
                name=block['outputs'][port]
                _require(_typed(value,declarations[name]['type']),'invalid effect output value')
                work[name]=value
        def result(pending=None,suspension=None):
            host_plans=any(e['op'] in _CAP for e in events)
            waiting=pending is not None or host_plans
            out={'complete':not waiting,'status':'pending_host' if waiting else 'complete',
                 'qualification':'nominal_effect_model_under_caller_bindings',
                 'state':deepcopy(original if waiting else work),'proposed_state':deepcopy(work),
                 'effect_context':deepcopy(original_context if waiting else context),
                 'proposed_effect_context':deepcopy(context),'events':deepcopy(events),'visited':list(visited),
                 'control_trace':deepcopy(trace),'effect_trace':deepcopy(effects),
                 'host_completions':deepcopy(completions),'evidence':deepcopy(document.get('evidence',{})),
                 'native_execution':False}
            if pending is not None:out.update(host_request=pending,checkpoint=suspension)
            else:out['control']={'continuation':current,'call_stack':list(stack),'stop':op}
            return out
        def suspend(block,pending):
            payload=dict(format='fdisbull-il-effect-suspension-1',program_sha256=program_hash,
                         original_state=original,original_context=original_context,state=work,context=context,
                         continuation=current,body_index=body_index,stack=stack,visited=visited,
                         control_trace=trace,events=events,effect_trace=effects,host_completions=completions,
                         max_steps=max_steps,max_call_depth=max_call_depth,pending=pending,pending_block=block['id'])
            request_id=_digest(payload)
            payload['request_id']=request_id;payload['integrity_sha256']=_digest(payload)
            request={'request_id':request_id,'operation':pending['kind'],'block_id':block['id'],
                     'details':deepcopy(pending),'basis':'explicit model host result required','native_execution':False}
            return result(request,deepcopy(payload))
        if checkpoint is not None:
            if host_result is None:
                # Idempotent readback does not replay the pending operation.
                saved=deepcopy(checkpoint);saved['integrity_sha256']=checksum
                request={'request_id':checkpoint['request_id'],'operation':checkpoint['pending']['kind'],
                         'block_id':pending_block['id'],'details':deepcopy(checkpoint['pending']),
                         'basis':'explicit model host result required','native_execution':False}
                return result(request,saved)
            _fields(host_result,('request_id','status','result'))
            _require(host_result['request_id']==checkpoint['request_id'] and host_result['status']=='completed',
                     'matching completed host result required')
            done=complete_effect(checkpoint['pending'],host_result['result'],context)
            write_results(pending_block,done['results']);events.extend(done['events'])
            effects[-1]['status']='host_result_supplied'
            completions.append({'request_id':checkpoint['request_id'],'block_id':pending_block['id'],
                                'basis':'caller_supplied_model_host_result'})
        def val(value):return work[value['var']] if isinstance(value,dict) else value
        def cond(c):
            op=c['op']
            if op=='eq':return val(c['left'])==val(c['right'])
            if op=='lt':return val(c['left'])<val(c['right'])
            if op=='bit_test':return bool(val(c['value'])&(1<<c['bit']))
            if op=='not':return not cond(c['condition'])
            return all(cond(x) for x in c['conditions'])
        while True:
            continuation=document['continuations'][current]
            if body_index==0:
                _require(len(visited)<max_steps,'step budget exceeded');visited.append(current)
                trace.append({'continuation':current,'call_stack':list(stack)})
            while body_index<len(continuation['body']):
                block=continuation['body'][body_index];body_index+=1
                if block['op']=='effect':
                    _require(len(visited)<max_steps,'step budget exceeded');visited.append(block['id'])
                    effect=apply_effect(block,{k:val(v) for k,v in block['args'].items()},context)
                    effects.append({'block_id':block['id'],'action':block['action'],
                                    'status':'pending_host' if effect['pending'] else 'modeled'})
                    if effect['pending'] is not None:return suspend(block,effect['pending'])
                    write_results(block,effect['results']);events.extend(effect['events'])
                else:
                    sub={k:deepcopy(v) for k,v in document.items() if k not in ('entry','continuations')}
                    sub.update(format='fdisbull-il-1',body=[block])
                    evaluated=execute_il(sub,work,capabilities,max_steps-len(visited))
                    _require(evaluated['status']!='refused',evaluated.get('error','body refused'))
                    work=evaluated['proposed_state'];events.extend(evaluated['events']);visited.extend(evaluated['visited'])
            transfer=continuation['transfer'];op=transfer['op'];body_index=0
            if op=='goto':current=transfer['target']
            elif op=='if':current=transfer['then'] if cond(transfer['condition']) else transfer['else']
            elif op=='call':
                _require(len(stack)<max_call_depth,'call depth exceeded');stack.append(transfer['resume']);current=transfer['target']
            elif op=='return' and stack:
                current=stack.pop();_require(current is not None,'unexpected return without continuation')
            else:return result()
    except (ILInvalid,ValueError,TypeError,KeyError,IndexError,RecursionError) as exc:
        refused={'complete':False,'status':'refused','error':str(exc),'state':deepcopy(original),
                 'effect_context':deepcopy(original_context),'events':[],'visited':[],'native_execution':False,
                 'host_completions':deepcopy(completions)}
        if completions:
            # The model transaction remains uncommitted. Caller-supplied host
            # completion claims cannot be rolled back or silently discarded.
            refused.update(recovery_required=True,external_effects='caller_completion_claims_preserved',
                           last_modeled_state=deepcopy(work),last_modeled_effect_context=deepcopy(context))
        if isinstance(host_result,dict):
            refused['received_host_result']={k:host_result.get(k) for k in ('request_id','status')}
            refused['received_host_result']['basis']='caller result; not native execution evidence'
            refused['recovery_required']=True
        return refused
