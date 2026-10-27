"""Bounded observed movement, with explicit game controls and stop contracts."""
from copy import deepcopy
import json
import math
import time

from .runtime_observations import capture_observations, validate_observations
from .operation_budget import rpc_budget


def validate_predicate(value,fields,depth=0):
    if not isinstance(value,dict) or depth>8:raise ValueError('Invalid movement predicate')
    if set(value) in ({'all'},{'any'}):
        children=next(iter(value.values()))
        if not isinstance(children,list) or not 1<=len(children)<=32:raise ValueError('Invalid predicate operands')
        for child in children:validate_predicate(child,fields,depth+1)
        return
    if set(value)=={'not'}:validate_predicate(value['not'],fields,depth+1);return
    if set(value)!={'field','op','value'} or value['field'] not in fields or value['op'] not in ('eq','ne','lt','le','gt','ge','in_range'):
        raise ValueError('Predicate requires a known field, op and value')
    v=value['value']
    if value['op']=='in_range':
        if not isinstance(v,list) or len(v)!=2 or any(type(x) is not int for x in v) or v[0]>v[1]:raise ValueError('Invalid movement range')
    elif type(v) not in (int,str,bool):raise ValueError('Invalid movement comparison')


def matches(predicate,values):
    if 'all' in predicate:return all(matches(p,values) for p in predicate['all'])
    if 'any' in predicate:return any(matches(p,values) for p in predicate['any'])
    if 'not' in predicate:return not matches(predicate['not'],values)
    left=values[predicate['field']];right=predicate['value'];op=predicate['op']
    if isinstance(left,str) and type(right) is int:
        left=int(left,0)
    if op=='in_range':return right[0]<=left<=right[1]
    return {'eq':lambda:left==right,'ne':lambda:left!=right,'lt':lambda:left<right,
            'le':lambda:left<=right,'gt':lambda:left>right,'ge':lambda:left>=right}[op]()


def _bounded(value,name,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError(f'{name} must be in {low}..{high}')


def _call(value):
    if not isinstance(value,dict) or set(value)-{'name','args'} or not isinstance(value.get('name'),str):raise ValueError('Movement start/stop require a macro name and args')


def validate_movement(observations,until,progress,settle, *, guest_ms=10000,timeout_ms=10000,slice_ms=50,cleanup_guest_ms=250,max_polls=1000,context=None,position=None,target=None,scene=None,boundary_tolerance=1):
    validate_observations(observations)
    for p in (until,settle):validate_predicate(p,observations)
    if context is not None:validate_predicate(context,observations)
    _bounded(guest_ms,'guest_ms',1,3600000);_bounded(timeout_ms,'timeout_ms',1,600000)
    _bounded(slice_ms,'slice_ms',1,1000);_bounded(cleanup_guest_ms,'cleanup_guest_ms',1,10000)
    _bounded(max_polls,'max_polls',1,10000)
    _bounded(boundary_tolerance,'boundary_tolerance',0,64)
    if not isinstance(progress,dict) or set(progress)-{'fields','samples','frames','frame_field'}:raise ValueError('Invalid progress contract')
    fields=progress.get('fields')
    if not isinstance(fields,list) or not fields or len(set(fields))!=len(fields) or any(f not in observations for f in fields):raise ValueError('Progress needs known fields')
    if ('samples' in progress)==('frames' in progress):raise ValueError('Progress requires exactly one samples or frames window')
    _bounded(progress.get('samples',progress.get('frames')),'progress window',1,1000)
    if 'frames' in progress and progress.get('frame_field') not in observations:raise ValueError('Frame progress needs an explicit frame observation')
    if scene is not None:
        if not isinstance(scene,str) or not isinstance(position,dict) or set(position)!={'x','y'} or any(v not in observations for v in position.values()):raise ValueError('Geometry needs scene and x/y fields')
        if not isinstance(target,list) or len(target)!=2 or any(type(v) is not int for v in target):raise ValueError('Geometry needs explicit target point')
    elif position is not None or target is not None:raise ValueError('Navigation coordinates require a selected scene')


def _refs(value,start):
    if isinstance(value,str) and value.startswith('$start.'):
        current=start
        for key in value[7:].split('.'):current=current[key]
        return current
    if isinstance(value,dict):return {k:_refs(v,start) for k,v in value.items()}
    if isinstance(value,list):return [_refs(v,start) for v in value]
    return value


class MovementSessionMixin:
    @rpc_budget
    def move(self,macro_set, *, start,stop,observations,until,progress,settle,guest_ms=10000,timeout_ms=10000,
             slice_ms=50,cleanup_guest_ms=250,max_polls=1000,context=None,scene=None,position=None,target=None,boundary_tolerance=1):
        validate_movement(observations,until,progress,settle,guest_ms=guest_ms,timeout_ms=timeout_ms,slice_ms=slice_ms,
                          cleanup_guest_ms=cleanup_guest_ms,max_polls=max_polls,context=context,scene=scene,position=position,target=target,boundary_tolerance=boundary_tolerance)
        _call(start);_call(stop)
        # Validate both expansions/capabilities before sending any input. Only
        # typed lease references may depend on the start's runtime result.
        info,start_plan=self._macro_plan(macro_set,start['name'],start.get('args',{}))
        _,stop_plan=self._macro_plan(macro_set,stop['name'],stop.get('args',{}))
        # A deferred stop lease must be a declared output of a key-down in
        # this start plan, not an arbitrary path or unrelated result value.
        outputs=start_plan.get('outputs',{})
        lease_outputs={name for name,ref in outputs.items() if isinstance(ref,str) and any(
            step.get('op')=='keyboard.key-down' and step.get('as') and ref==f"${step['as']}.lease"
            for step in start_plan['script']['steps'])}
        def check_ref(value):
            if isinstance(value,str) and value.startswith('$start.'):
                parts=value.split('.')
                if len(parts)!=3 or parts[1]!='outputs' or parts[2] not in lease_outputs:
                    raise ValueError('stop reference must name a start output from key-down')
            elif isinstance(value,dict):
                for item in value.values():check_ref(item)
            elif isinstance(value,list):
                for item in value:check_ref(item)
        check_ref(stop.get('args',{}))
        physical={'keyboard.press','keyboard.key-down','keyboard.key-up'}
        if any(s['op'] not in physical for plan in (start_plan,stop_plan) for s in plan['script']['steps']):
            raise ValueError('Movement control macros must contain physical input only; movement owns execution budgets')
        if not self.rpc.capabilities.get('timing',{}).get('fast_forward'):raise ValueError('Movement requires measured guest time')
        handle=self.scene(scene) if scene is not None else None
        if handle is not None:handle.navigation_check(target) # validate geometry/schema before input
        began=time.monotonic();deadline=began+timeout_ms/1000
        result={'format':'fdisbull-movement-result-1','run':self.run_id,'version':self.version['id'],'macro_set':info['id'],
                'macro_sha256':info['sha256'],'start':deepcopy(start),'stop':deepcopy(stop),'observations':deepcopy(observations),
                'until':deepcopy(until),'progress':deepcopy(progress),'settle':deepcopy(settle),'context':deepcopy(context),
                'requested_guest_ms':guest_ms,'reserved_cleanup_guest_ms':cleanup_guest_ms,'max_polls':max_polls,'guest_elapsed_ms':0,
                'cleanup_guest_elapsed_ms':0,'polls':[],'runs':[],'ok':False,'complete':False,'outcome':'incomplete',
                'cleanup':{'attempted':False,'settled':False},'diagnostic_frame':None}
        did_start=False;start_result={};terminal_stop=False;diagnostic_taken=False
        def remaining():return max(0,int((deadline-time.monotonic())*1000))
        def wall_budget():
            value=remaining()
            if not value:raise TimeoutError('Movement host-time budget expired')
            return value
        def diagnostic():
            nonlocal diagnostic_taken
            if diagnostic_taken:return
            diagnostic_taken=True
            try:
                frame=self.screenshot('movement-diagnostic.png',hooks=False)
                result['diagnostic_frame']=frame['artifact'];result['diagnostic_metadata']=frame['metadata']
            except Exception as error:result['diagnostic_error']=str(error)
        def observe():
            sample=capture_observations(self,observations)
            sample.update(guest_elapsed_ms=result['guest_elapsed_ms'],host_elapsed_ms=round((time.monotonic()-began)*1000,3))
            result['polls'].append(sample);result['last_observation']=sample
            if not sample['complete']:raise ValueError('Required movement capture is incomplete')
            if context is not None and not matches(context,sample['values']):raise ValueError('Movement context changed')
            return sample
        def geometry(sample):
            if handle is None:return None
            point=[sample['values'][position[k]] for k in ('x','y')]
            if any(type(v) is not int for v in point):raise ValueError('Position observations must be integers')
            nav=handle.navigation_check(point);result['navigation']=nav
            return nav
        try:
            initial=observe();result['initial_observation']=initial
            nav=geometry(initial)
            if nav is not None and nav['classification']!='clear':
                result['outcome']='geometry_disagreement';result['geometry_counterexample']=nav
                raise ValueError('Initial footprint is not qualified clear')
            if matches(until,initial['values']):
                result.update(outcome='already_arrived')
                result['cleanup']['settled']=matches(settle,initial['values'])
                if not result['cleanup']['settled']:result.update(ok=False,complete=False,outcome='initial_motion_not_settled')
                keyboard=self.keyboard_state()['keyboard'];result['cleanup']['keyboard']=keyboard
                if keyboard['pending_events'] or keyboard['owned_keys']:
                    result.update(ok=False,complete=False,outcome='initial_input_not_clear')
                if handle is not None and [initial['values'][position[k]] for k in ('x','y')]!=target:
                    result.update(ok=False,complete=False,outcome='destination_predicate_disagreement')
                if result['outcome']=='already_arrived':result.update(ok=True,complete=True)
            else:
                if not matches(settle,initial['values']):raise ValueError('Movement start requires observed stopped state')
                if handle is not None:
                    preflight=handle.navigation_check(target);result['geometry_preflight']=preflight
                    if preflight['classification']!='clear':
                        result['outcome']='destination_'+preflight['classification'];raise ValueError('Destination footprint is not qualified clear')
                    result['navigation_manifest_sha256']=preflight['manifest_sha256']
                did_start=True
                start_result=self.macro(macro_set,start['name'],args=start.get('args',{}),timeout_ms=wall_budget())
                result['start_result']=start_result
                if not start_result['ok']:raise ValueError('Movement start macro failed')
                last=initial['values'];unchanged=0;last_changed=initial
                first_frame=last.get(progress.get('frame_field'));consumed=False
                while True:
                    if not remaining():result['outcome']='timeout';break
                    if len(result['polls'])>=max_polls:result['outcome']='poll_budget';break
                    budget=guest_ms-result['guest_elapsed_ms']
                    if budget<=0:result['outcome']='guest_budget';break
                    run=self.run(guest_ms=min(slice_ms,budget),timeout_ms=max(1,remaining()),fast_forward=True,stop_on_hook=True)
                    result['runs'].append(run);result['guest_elapsed_ms']+=run.get('guest_elapsed_ms',0)
                    if run['outcome']!='guest_time' or run.get('hook_hits'):
                        result.update(outcome='stopped',stop_result=run);terminal_stop=True;break
                    sample=observe();values=sample['values']
                    nav=geometry(sample)
                    if nav is not None and nav['classification']!='clear':
                        result['outcome']='geometry_disagreement';result['geometry_counterexample']=nav;break
                    # Arrival wins over the final progress-window sample.
                    if matches(until,values):
                        result['outcome']='arrived'
                        if handle is not None and [values[position[k]] for k in ('x','y')]!=target:
                            result['outcome']='destination_predicate_disagreement'
                        break
                    keyboard=self.keyboard_state()['keyboard'];sample['keyboard']=keyboard
                    if keyboard['pending_events']:
                        continue # Delivery accepted is not evidence it was consumed.
                    consumed=True
                    changed=any(values[f]!=last[f] for f in progress['fields'])
                    if changed:
                        unchanged=0;last_changed=sample;first_frame=values.get(progress.get('frame_field'))
                    else:unchanged+=1
                    last=dict(values);result['last_changing_observation']=last_changed
                    if 'samples' in progress:stalled=unchanged>=progress['samples']
                    else:
                        frame=values[progress['frame_field']]
                        if type(frame) is not int or type(first_frame) is not int or frame<first_frame:raise ValueError('Progress frame identity is not monotonic')
                        stalled=frame-first_frame>=progress['frames']
                    if consumed and stalled:
                        result.update(outcome='blocked',classification='blocked_unknown')
                        if handle is not None:
                            from .navigation_geometry import route_first_boundary
                            doc=handle.info['definition']['navigation'];point=[values[position[k]] for k in ('x','y')]
                            boundary=route_first_boundary(doc,[point,target],conditions=nav['conditions'])
                            result['expected_boundary']=boundary
                            if boundary and boundary['result']['classification']=='blocked' and math.dist(point,boundary['result']['point'])<=boundary_tolerance:
                                result['classification']='blocked_known_boundary'
                                result['boundary_claim']='Matches the selected geometry model; not independent proof of engine collision.'
                        break
                if result['outcome']!='arrived':diagnostic()
        except Exception as error:
            result.update(ok=False,complete=False)
            result['error']=str(error)
            if result['outcome'] in ('incomplete','already_arrived'):result['outcome']='observation_error'
            diagnostic()
        finally:
            if did_start and not self.closed:
                result['cleanup']['attempted']=True
                if terminal_stop:
                    # Consuming a game-specific stop could run through the very
                    # debugger stop we must preserve. Close rather than resume.
                    result['cleanup'].update(settled=False,reason='Debugger stop preserved; no cleanup guest execution')
                    self.close()
                else:
                    try:
                        # Finish a queued make/hold/break before asking a latched
                        # profile to send its next complete press. These slices
                        # consume the reserved cleanup budget and preserve stops.
                        while self.keyboard_state()['keyboard']['pending_events']:
                            left=cleanup_guest_ms-result['cleanup_guest_elapsed_ms']
                            if left<=0:raise TimeoutError('Input delivery exceeded cleanup guest budget')
                            run=self.run(guest_ms=min(slice_ms,left),timeout_ms=wall_budget(),fast_forward=True,stop_on_hook=True)
                            result['cleanup_guest_elapsed_ms']+=run.get('guest_elapsed_ms',0)
                            result['cleanup'].setdefault('runs',[]).append(run)
                            if run['outcome']!='guest_time' or run.get('hook_hits'):
                                result['cleanup']['stop']=run;raise ValueError('Debugger stop preserved during input drain')
                        stopped=self.macro(macro_set,stop['name'],args=_refs(stop.get('args',{}),start_result),timeout_ms=wall_budget())
                        result['cleanup']['macro']=stopped
                        if not stopped['ok']:raise ValueError('Stop macro failed')
                        while remaining() and result['cleanup_guest_elapsed_ms']<=cleanup_guest_ms:
                            sample=capture_observations(self,observations);result['cleanup']['last_observation']=sample
                            keyboard=self.keyboard_state()['keyboard'];result['cleanup']['keyboard']=keyboard
                            if sample['complete'] and matches(settle,sample['values']) and not keyboard['pending_events'] and not keyboard['owned_keys']:
                                result['cleanup']['settled']=True
                                if result['outcome']=='arrived':
                                    values=sample['values']
                                    if context is not None and not matches(context,values):result['outcome']='context_not_retained'
                                    elif not matches(until,values):result['outcome']='destination_not_retained'
                                    else:
                                        nav=geometry(sample)
                                        if nav is not None and nav['classification']!='clear':
                                            result['outcome']='geometry_disagreement';result['geometry_counterexample']=nav
                                        elif handle is not None and [values[position[k]] for k in ('x','y')]!=target:
                                            result['outcome']='destination_predicate_disagreement'
                                        else:result.update(ok=True,complete=True)
                                break
                            budget=cleanup_guest_ms-result['cleanup_guest_elapsed_ms']
                            if budget<=0:break
                            run=self.run(guest_ms=min(slice_ms,budget),timeout_ms=max(1,remaining()),fast_forward=True,stop_on_hook=True)
                            result['cleanup_guest_elapsed_ms']+=run.get('guest_elapsed_ms',0)
                            result['cleanup'].setdefault('runs',[]).append(run)
                            if run['outcome']!='guest_time' or run.get('hook_hits'):
                                result['cleanup']['stop']=run;break
                        if not result['cleanup']['settled']:
                            result['cleanup']['reason']='Stop or physical release could not be qualified';self.close()
                    except Exception as error:
                        result['cleanup']['error']=str(error);self.close()
            if not result['ok']:diagnostic()
        result['host_elapsed_ms']=round((time.monotonic()-began)*1000,3)
        result['claim']='Observed bounded route under declared controls, fields and geometry; not deterministic replay or collision-proof navigation.'
        self._event('movement',result)
        artifact=self._artifact('movement-result.json','movement-result',json.dumps(result,indent=2).encode(),{'ok':result['ok'],'outcome':result['outcome']})
        return {**result,'artifact':artifact['artifact']}
