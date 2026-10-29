"""Bounded, explicitly qualified spatial action policy for native sessions.

A map checker and assisted plan builder are supplied by the caller at their
stable integration seams. They do not execute an action on the guest's behalf.
"""
from copy import deepcopy
import base64
import hashlib
import time

from .movement import matches, validate_predicate
from .runtime_observations import capture_observations, validate_observations
from .keyboard_input import validate_keyboard


def _predicate_fields(value):
    if 'field' in value: return {value['field']}
    if 'not' in value: return _predicate_fields(value['not'])
    return set().union(*(_predicate_fields(child) for child in next(iter(value.values()))))


class SpatialActionHandle:
    def __init__(self, session, map_revision, *, mode='physical', fair_play=False,
                 check_point=None, choose_anchor=None, travel_plan=None, actor_recipe=None, qualify_context=None):
        if mode not in ('physical', 'assisted', 'story'):
            raise ValueError('Unknown spatial mode')
        if type(fair_play) is not bool or ((fair_play or getattr(session,'_fair_play',False)) and mode != 'physical'):
            raise ValueError('Fair play requires physical mode')
        locked_mode=getattr(session,'_spatial_mode',None)
        if locked_mode is not None and locked_mode!=mode:
            raise ValueError('Spatial action mode differs from session policy')
        if not isinstance(map_revision, str) or not map_revision:
            raise ValueError('A pinned spatial map revision is required')
        self.session, self.map_revision, self.mode = session, map_revision, mode
        self.check_point, self.choose_anchor, self.travel_plan = check_point, choose_anchor, travel_plan
        self.actor_recipe = deepcopy(actor_recipe)
        if qualify_context is not None and not callable(qualify_context): raise ValueError('Context qualifier must be callable')
        self.qualify_context = qualify_context

    def interact(self, definition, *, timeout_ms=10000):
        d = deepcopy(definition)
        result = {'format':'fdisbull-spatial-action-result-1', 'mode':self.mode,
                  'map_revision':self.map_revision, 'ok':False, 'complete':False,
                  'status':'incomplete', 'runs':[], 'inputs':[], 'guards':[], 'rollback':None}
        original = None
        resource_patches = []
        active_owned = False
        start = time.monotonic()
        try:
            if getattr(self.session,'_spatial_guard_active',False):
                raise ValueError('A spatial guard is already active')
            if ((getattr(self.session,'_fair_play',False) and self.mode!='physical')
                or getattr(self.session,'_spatial_mode',self.mode)!=self.mode):
                raise ValueError('Spatial session policy changed')
            if getattr(self.session,'_spatial_guard_failed',False) or getattr(self.session,'closed',False):
                raise ValueError('Session is unavailable after an incomplete guard restoration')
            required = {'format','id','version','map_revision','observations','context','nonspatial_before',
                        'nonspatial_after','outcome','position','proximity','inputs','guest_ms','slice_ms',
                        'stationary','spatial_guards'}
            if not isinstance(d,dict) or set(d) != required or d['format'] != 'fdisbull-spatial-action-1':
                raise ValueError('Invalid spatial action definition')
            if not isinstance(d['id'],str) or not d['id'] or d['version'] != self.session.version['id'] or d['map_revision'] != self.map_revision:
                raise ValueError('Action version or map revision mismatch')
            result['action'] = d['id']
            validate_observations(d['observations'])
            for name in ('context','nonspatial_before','nonspatial_after','outcome','proximity'):
                validate_predicate(d[name],d['observations'])
            pos = d['position']
            if not isinstance(pos,dict) or set(pos) != {'x','y'} or any(v not in d['observations'] for v in pos.values()) or pos['x']==pos['y']:
                raise ValueError('Position requires distinct observed x and y fields')
            for name in ('context','nonspatial_before','nonspatial_after'):
                if _predicate_fields(d[name]) & set(pos.values()):
                    raise ValueError('Room and nonspatial predicates cannot depend on position')
            if type(d['stationary']) is not bool or type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000:
                raise ValueError('Invalid stationary flag or timeout')
            if type(d['guest_ms']) is not int or not 1 <= d['guest_ms'] <= 120000 or type(d['slice_ms']) is not int or not 1 <= d['slice_ms'] <= 1000:
                raise ValueError('Invalid action budget')
            if not isinstance(d['inputs'],list) or not 1 <= len(d['inputs']) <= 16:
                raise ValueError('Original keyboard input is required')
            for step in d['inputs']:
                if not isinstance(step,dict): raise ValueError('Invalid keyboard input')
                validate_keyboard(**step)
            guards=d['spatial_guards']
            if not isinstance(guards,list) or len(guards)>16: raise ValueError('Invalid spatial guard list')
            if self.mode == 'story' and not guards: raise ValueError('Story requires source-identified spatial guards')
            for guard in guards:
                if not isinstance(guard,dict) or guard.get('kind') != 'spatial-resource':
                    raise ValueError('A story guard needs explicit spatial source provenance')
                expected_keys = {'binding','offset','expected_hex','data_hex','provenance','kind'}
                if set(guard)!=expected_keys or not isinstance(guard['provenance'],dict):
                    raise ValueError('Invalid spatial guard')
                provenance=guard['provenance']
                metadata=getattr(self.session,'metadata',{})
                if (not provenance.get('source_sha256') or not provenance.get('version_sha256')
                    or not provenance.get('evidence') or provenance['source_sha256']!=metadata.get('source_sha256')
                    or provenance['version_sha256']!=metadata.get('version_sha256')):
                    raise ValueError('Spatial guard source identity does not match session')
                before=bytes.fromhex(guard['expected_hex']); after=bytes.fromhex(guard['data_hex'])
                if not before or len(before)!=len(after) or before==after:
                    raise ValueError('Invalid spatial guard bytes')
                if (not isinstance(guard['binding'],str) or not guard['binding'] or type(guard['offset']) is not int
                    or guard['offset']<2 or len(before)!=6 or before[0] not in (11,16,17,18) or before[1]!=0
                    or before[2]>before[4] or before[3]>before[5] or before[4]>159 or before[5]>167
                    or after!=before[:2]+b'\x00\x00\x9f\xa7'
                    or not isinstance(provenance.get('file'),str) or not provenance['file']
                    or not isinstance(provenance.get('resource_sha256'),str)
                    or provenance.get('resource_offset')!=guard['offset']):
                    raise ValueError('Only an AGI ego position rectangle may be widened')
            def observe():
                item=capture_observations(self.session,d['observations'])
                if item.get('complete') is not True: raise ValueError('Observation incomplete')
                if self.qualify_context is not None:
                    qualification=self.qualify_context()
                    if not isinstance(qualification,dict) or qualification.get('qualified') is not True:
                        raise ValueError('Spatial map context is not qualified')
                    item['map_context']=deepcopy(qualification)
                if not matches(d['context'],item['values']): raise ValueError('Room or context changed')
                return item
            def point(item): return [item['values'][pos['x']],item['values'][pos['y']]]
            def clear(p):
                if not callable(self.check_point): raise ValueError('Qualified spatial map checker unavailable')
                check=self.check_point(self.map_revision,p)
                if not isinstance(check,dict) or check.get('classification')!='clear': raise ValueError('Map position is not known clear')
                return check
            before=observe(); result['before']=before
            if not matches(d['nonspatial_before'],before['values']): raise ValueError('Nonspatial preconditions failed')
            if self.mode=='physical' and not matches(d['proximity'],before['values']): raise ValueError('Target is out of reach')
            if self.mode=='assisted':
                if not callable(self.choose_anchor) or not callable(self.travel_plan): raise ValueError('Qualified assisted anchor unavailable')
                anchor=self.choose_anchor(self.map_revision,deepcopy(d),deepcopy(before))
                if not isinstance(anchor,(tuple,list)) or len(anchor)!=2 or any(type(v) is not int for v in anchor): raise ValueError('Invalid assisted anchor')
                anchor=list(anchor); result['anchor']=anchor; result['anchor_check']=clear(anchor)
                plan=self.travel_plan(deepcopy(d),anchor,deepcopy(before))
                recipe=self.actor_recipe
                if not isinstance(recipe,dict) or set(recipe)!={'x','y','refresh'} or not isinstance(recipe['refresh'],list):
                    raise ValueError('Assisted actor write recipe unavailable')
                expected=[]
                for axis,value in zip(('x','y'),anchor):
                    field=recipe[axis]
                    if not isinstance(field,dict) or set(field)!={'binding','offset','type'}: raise ValueError('Invalid actor coordinate recipe')
                    ref=d['observations'][pos[axis]].get('runtime_memory')
                    if not isinstance(ref,dict) or any(ref.get(k,0 if k=='offset' else None)!=field[k] for k in ('binding','offset','type')):
                        raise ValueError('Actor recipe does not match observed coordinate binding')
                    expected.append(field|{'value':value})
                for field in recipe['refresh']:
                    if not isinstance(field,dict) or set(field)!={'binding','offset','type','set_bits'}: raise ValueError('Invalid actor refresh recipe')
                    expected.append(field)
                if not isinstance(plan,dict) or plan.get('kind')!='within-room' or plan.get('writes')!=expected:
                    raise ValueError('Travel plan exceeds qualified actor write recipe')
                if plan.get('inputs') or 'cleanup' in plan:
                    raise ValueError('Assisted placement cannot send action input')
                destination=plan.get('destination',{})
                if not isinstance(destination,dict) or destination.get('room_field') not in _predicate_fields(d['context']):
                    raise ValueError('Assisted placement must protect the observed room field')
                travel=self.session.assisted_travel(plan,timeout_ms=timeout_ms); result['travel']=travel
                if travel.get('ok') is not True or travel.get('complete') is not True: raise ValueError('Assisted placement did not settle')
                before=observe(); result['after_placement']=before
                if point(before)!=anchor or not matches(d['proximity'],before['values']) or not matches(d['nonspatial_before'],before['values']): raise ValueError('Assisted placement failed requalification')
                result['settled_check']=clear(point(before))
            initial_point=point(before)
            keyboard=self.session.keyboard_state()['keyboard']
            if keyboard.get('pending_events')!=0 or keyboard.get('owned_keys')!=0: raise ValueError('Keyboard is not neutral')
            if self.mode=='story':
                original=list(self.session.layers()['active']); result['original_layers']=original
                layers=[]
                # Preflight every resource before any writes, including a full
                # immutable-file comparison and the runtime binding witness.
                prepared=[]
                for guard in guards:
                    key=self.session._runtime_names.get(guard['binding'],guard['binding'])
                    binding=self.session._runtime_bindings.get(key)
                    if not binding: raise ValueError('Unknown resource binding')
                    length=binding['length']; offset=guard['offset']; witness=bytes.fromhex(binding['expected_hex'])
                    if not 2<=len(witness)<=offset or length>65536 or offset+6>length:
                        raise ValueError('Resource binding or identity witness is invalid')
                    file=self.session.project.file_bytes(guard['provenance']['file'],offset=0,size=length,version=d['version'])
                    source=bytes.fromhex(file['bytes'])
                    if (file['complete'] is not True or len(source)!=length
                        or file['sha256']!=guard['provenance']['resource_sha256']
                        or hashlib.sha256(source).hexdigest()!=file['sha256']
                        or int.from_bytes(source[:2],'little')+2>length
                        or offset+6>int.from_bytes(source[:2],'little')+2
                        or source[offset:offset+6]!=bytes.fromhex(guard['expected_hex'])):
                        raise ValueError('Resource source does not match the guard')
                    from .agi_layout import logic_layout
                    condition=logic_layout(source)['conditions'].get(offset)
                    if (not condition or condition['opcode']!=source[offset]
                        or condition['end']!=offset+6 or condition['negated']):
                        raise ValueError('Guard is not a non-negated decoded AGI position condition')
                    observed=self.session.runtime_memory(guard['binding'],offset=0,length=length)
                    if bytes.fromhex(observed['hex'])!=source: raise ValueError('Runtime resource differs from attached source')
                    address=binding['address']+offset
                    if any(address<item['address']+6 and item['address']<address+6 for item in prepared):
                        raise ValueError('Resource guards overlap')
                    prepared.append({'guard':guard,'address':address,'source':source,'length':length})
                # This is a session interop marker, not a concurrency lock.
                # Set before the first activation or write, including failures.
                self.session._spatial_guard_active=True
                active_owned=True
                if layers:self.session.layers(original+layers)
                for item in prepared:
                    guard=item['guard']; offset=guard['offset']; old=bytes.fromhex(guard['expected_hex']); new=bytes.fromhex(guard['data_hex'])
                    # Record before write: even an exception may follow a partial
                    # backend operation and needs a guarded restoration attempt.
                    record={'guard':deepcopy(guard),'address':item['address'],'write_outcome':'unknown','restored':False}
                    resource_patches.append(record); result['guards'].append(record)
                    self.session.call('memory.write',{'address':{'space':'linear','offset':f"0x{item['address']:08X}"},
                        'expected_sha256':hashlib.sha256(old).hexdigest(),'data_base64':base64.b64encode(new).decode()})
                    record['write_outcome']='acknowledged'
                    actual=self.session.runtime_memory(guard['binding'],offset=offset,length=6)
                    if bytes.fromhex(actual['hex'])!=new: raise ValueError('Resource guard write readback differs')
            elapsed=0
            def keyboard_drained():
                keyboard=self.session.keyboard_state()['keyboard']
                counts=(keyboard.get('pending_events'),keyboard.get('owned_keys'))
                if any(type(value) is not int or value<0 for value in counts):
                    raise ValueError('Invalid keyboard queue state')
                return counts==(0,0)
            def run_slice():
                nonlocal elapsed
                remaining=timeout_ms-int((time.monotonic()-start)*1000)
                if remaining<=0 or elapsed>=d['guest_ms']: raise TimeoutError('Action budget expired')
                stop=self.session.run(guest_ms=min(d['slice_ms'],d['guest_ms']-elapsed),timeout_ms=remaining,fast_forward=True,stop_on_hook=True)
                result['runs'].append(stop)
                if stop.get('outcome')!='guest_time' or stop.get('hook_hits'):
                    result.update(status='stopped',stop=stop)
                    return None
                delta=stop.get('guest_elapsed_ms')
                if type(delta) is not int or delta<=0: raise ValueError('Guest time did not advance')
                elapsed+=delta; result['guest_elapsed_ms']=elapsed
                if elapsed>d['guest_ms'] or (time.monotonic()-start)*1000>=timeout_ms: raise TimeoutError('Action budget expired')
                after=observe(); result['after']=after
                if self.mode=='story' and d['stationary'] and point(after)!=initial_point: raise ValueError('Story action unexpectedly moved actor')
                return after
            stopped=False
            for index,step in enumerate(d['inputs']):
                if elapsed>=d['guest_ms'] or (time.monotonic()-start)*1000>=timeout_ms:
                    raise TimeoutError('Action budget expired before input')
                response=(self.session.keyboard_type(**step) if 'text' in step else self.session.keyboard_press(**step))
                result['inputs'].append({'input':step,'result':response})
                if index+1<len(d['inputs']):
                    # Even an initially empty queue needs one guest slice to
                    # ensure the previous input was actually delivered.
                    while True:
                        after=run_slice()
                        if after is None:
                            stopped=True; break
                        if not matches(d['nonspatial_before'],after['values']):
                            raise ValueError('Nonspatial preconditions changed during input')
                        if keyboard_drained(): break
                    if stopped: break
            if not stopped:
                while elapsed<d['guest_ms']:
                    after=run_slice()
                    if after is None: break
                    if matches(d['outcome'],after['values']) and keyboard_drained():
                        if not matches(d['nonspatial_after'],after['values']): raise ValueError('Nonspatial postconditions failed')
                        result.update(ok=True,complete=True,status='success'); break
        except Exception as error:
            result['error']=str(error)
        finally:
            resource_restore=[]
            for record in reversed(resource_patches):
                guard=record['guard']; old=bytes.fromhex(guard['expected_hex']); new=bytes.fromhex(guard['data_hex'])
                try:
                    current=bytes.fromhex(self.session.runtime_memory(guard['binding'],offset=guard['offset'],length=6)['hex'])
                    if current==new:
                        self.session.call('memory.write',{'address':{'space':'linear','offset':f"0x{record['address']:08X}"},
                            'expected_sha256':hashlib.sha256(new).hexdigest(),'data_base64':base64.b64encode(old).decode()})
                    elif current!=old: raise ValueError('Resource guard bytes changed unexpectedly')
                    actual=bytes.fromhex(self.session.runtime_memory(guard['binding'],offset=guard['offset'],length=6)['hex'])
                    if actual!=old: raise ValueError('Resource guard restoration readback differs')
                    record['restored']=True; resource_restore.append({'address':record['address'],'ok':True})
                except Exception as error:
                    resource_restore.append({'address':record['address'],'ok':False,'error':str(error)})
                    result.update(ok=False,complete=False,status='incomplete')
                    # Do not allow later work or checkpointing on an uncertain guest.
                    self.session._spatial_guard_failed=True
                    try: self.session.close()
                    except Exception: pass
            if resource_patches: result['resource_rollback']=resource_restore
            if original is not None:
                try:
                    self.session.layers(original)
                    active=self.session.layers()['active']
                    if active!=original: raise ValueError('Layer stack readback mismatch')
                    result['rollback']={'ok':True,'active':active}
                except Exception as error:
                    result['rollback']={'ok':False,'error':str(error)}
                    result.update(ok=False,complete=False,status='incomplete')
                    self.session._spatial_guard_failed=True
                    try: self.session.close()
                    except Exception: pass
            if active_owned:
                failed=(any(not item['ok'] for item in resource_restore)
                        or (result['rollback'] is not None and not result['rollback']['ok']))
                if not failed or (getattr(self.session,'closed',False) and getattr(self.session,'_spatial_guard_failed',False)):
                    self.session._spatial_guard_active=False
            result['host_elapsed_ms']=round((time.monotonic()-start)*1000,3)
            if hasattr(self.session,'_event'): self.session._event('spatial-action',deepcopy(result))
        return result
