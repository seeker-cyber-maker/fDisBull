"""Verified, bounded observations for source-bound native QEMU trials."""
from copy import deepcopy
import hashlib
import io
import json

from .debug_experiments import validate_observations as _legacy_observations

FORMAT = 'fdisbull-qemu-trial-observations-1'
_MAX_ARTIFACT = 16 * 1024 * 1024


def validate_observations(items):
    return _legacy_observations(items)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _digest(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _cpu(value):
    if not isinstance(value,dict) or not isinstance(value.get('registers'),dict) or not value['registers']:
        raise ValueError('Native trial requires a complete selected CPU register observation')
    state=value.get('address_state')
    if (not isinstance(state,dict) or state.get('register_context_match') is not True
            or state.get('machine_vcpus') != 1 or value.get('cpu_mode') not in ('real','v86','protected','long')
            or value.get('linear_pc') is None or not isinstance(state.get('control'),dict)
            or not isinstance(state.get('segments'),dict) or not state['segments'].get('cs')
            or type(state.get('a20')) is not bool or type(state.get('paging')) is not bool
            or state.get('code_bits') not in (16,32,64)):
        raise ValueError('Native trial CPU mode or address context is unqualified')
    registers={}; unavailable=[]
    for key,item in value['registers'].items():
        if not isinstance(key,str): raise ValueError('Invalid native register name')
        if item is None:
            unavailable.append(key)
            continue
        try: number=int(item,0) if isinstance(item,str) else item
        except ValueError: raise ValueError('Invalid native register value') from None
        if type(number) is not int or not 0 <= number < 1 << 8192:
            raise ValueError('Invalid native register value')
        registers[key]=number
    if not registers or not ({'rip','eip'} & set(registers)):
        raise ValueError('Native trial lacks an exposed instruction pointer')
    return dict(registers=registers,unavailable_registers=sorted(unavailable),linear_pc=value['linear_pc'],cpu_mode=value['cpu_mode'],
        address_state={key:deepcopy(state.get(key)) for key in ('control','segments','a20','paging',
            'code_bits','stack_bits','register_context_match','machine_vcpus')})


def _artifact(session, ref, kind):
    if not isinstance(ref,dict) or not isinstance(ref.get('artifact'),str) or not ref['artifact']:
        raise ValueError('Trial artifact receipt is missing')
    row=session.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(ref['artifact'],)).fetchone()
    if row is None or row['kind'] != kind or row['version'] != session.version['id'] or row['run'] != session.run_id:
        raise ValueError('Trial artifact kind or source version differs')
    data=bytes(row['data'])
    if not 0 < len(data) <= _MAX_ARTIFACT or _hash(data) != row['sha256'] or ref.get('sha256') != row['sha256']:
        raise ValueError('Trial artifact bytes or receipt hash differ')
    if ref.get('size') is not None and ref['size'] != len(data):
        raise ValueError('Trial artifact receipt length differs')
    try: metadata=json.loads(row['metadata'])
    except (TypeError,ValueError) as error: raise ValueError('Trial artifact metadata is malformed') from error
    if not isinstance(metadata,dict): raise ValueError('Trial artifact metadata is malformed')
    return data,metadata


def _view_identity(context,evidence,normalized):
    descriptor=context.get('qemu_memory_view') if isinstance(context,dict) else None
    if (not isinstance(descriptor,dict) or descriptor.get('format') != 'fdisbull-qemu-memory-view-1'
            or descriptor.get('view') != 'ram' or descriptor.get('scope') not in ('machine','task-private')
            or not isinstance(context.get('mapping_id'),str) or len(context['mapping_id']) != 64
            or not isinstance(evidence,dict) or not isinstance(evidence.get('pages'),list)):
        raise ValueError('Trial source RAM lacks an explicit validated view or mapping')
    task=deepcopy(descriptor.get('task_identity'))
    if descriptor['scope']=='task-private' and (not isinstance(task,dict) or
            any(key not in task for key in ('monitor_uuid','cookie','incarnation','task_id'))):
        raise ValueError('Trial task-private view lacks native task identity')
    return dict(scope=descriptor['scope'],view='ram',task_identity=task,
                mapping_id=context['mapping_id'],backings=deepcopy(descriptor.get('backings')),
                physical_spans=deepcopy(normalized['spans']))


def capture_state(session, observations):
    observations=validate_observations(observations)
    from .qemu_cpu_undo_runtime import normalize_ranges
    from .memory_search_runtime import _capture
    before=session.registers(); registers=_cpu(before)
    memory=[]; raw=[]
    for requested in observations:
        normalized=normalize_ranges(session,[requested])[0]
        task=None
        if getattr(session,'_dos_task_monitor',None):
            from .qemu_dos_task_views import selected_view
            task=selected_view(session)['binding']['task_id']
        data,context,evidence=_capture(session,int(normalized['linear'],16),normalized['length'],'linear',task,view='ram')
        if not isinstance(data,bytes) or len(data) != normalized['length']:
            raise ValueError('Trial source RAM capture is incomplete')
        memory.append(dict(project_address=normalized['address'],project_cs=requested.get('cs'),
            length=len(data),hex=data.hex(),sha256=_hash(data),
            context=_view_identity(context,evidence,normalized)))
        raw.append(dict(request=deepcopy(requested),normalized=deepcopy(normalized),
                        context=deepcopy(context),evidence=deepcopy(evidence)))
    after=session.registers()
    if _cpu(after) != registers: raise ValueError('Native trial CPU changed across endpoint capture')
    from .qemu_dos_checkpoint import _compatibility, _origin, _verify_process
    _verify_process(session,session._process,_origin(session))
    process=session._process
    mapping=process.get('source_mapping')
    if not isinstance(mapping,dict) or mapping.get('live') is not True or not mapping.get('live_ranges'):
        raise ValueError('Native trial source mapping is not live and qualified')
    mapping=deepcopy(mapping)
    if 'capture_epoch' in mapping:
        if mapping['capture_epoch'] != getattr(session,'_runtime_epoch',None):
            raise ValueError('Native trial source mapping capture epoch is stale')
        mapping.pop('capture_epoch')
    task=None
    if getattr(session,'_dos_task_binding',None) is not None:
        from .qemu_dos_tasks import observe_task
        task=observe_task(session)['task_identity']
        if not isinstance(task,dict): raise ValueError('Native trial selected task identity is unavailable')
    identity=dict(source_sha256=session.metadata['source_sha256'],version=session.version['id'],
                  version_sha256=session.metadata['version_sha256'],runtime=_compatibility(session),
                  source_mapping=mapping,allocation=deepcopy(process.get('allocation')),
                  task_identity=deepcopy(task))
    return dict(registers=registers,memory=memory,identity=identity,
                provenance=dict(raw_registers=deepcopy(before),memory=raw,run=session.run_id,
                                capture_epoch=getattr(session,'_runtime_epoch',None)))


def _control_map(controls,session):
    if not isinstance(controls,dict): raise ValueError('Restored trial controls are missing')
    result={}
    for kind in ('breakpoints','hooks'):
        mapping=controls.get(kind,{})
        if not isinstance(mapping,dict): raise ValueError('Invalid restored trial controls')
        for logical,current in mapping.items():
            if not isinstance(logical,str): raise ValueError('Invalid logical trial control')
            if isinstance(current,dict): current=current.get('breakpoint_id' if kind=='breakpoints' else 'hook')
            if not isinstance(current,str) or not current: raise ValueError('Invalid restored trial control identity')
            if (kind,current) in result: raise ValueError('Ambiguous restored trial controls')
            result[(kind,current)]=logical
    registry=controls.get('hook_registry')
    if registry is None:
        if controls.get('hooks'): raise ValueError('Restored trial hook registry snapshot is missing')
        registry=[]
    if isinstance(registry,dict): registry=list(registry.values())
    if not isinstance(registry,list): raise ValueError('Restored trial hook registry is malformed')
    for control in registry:
        if not isinstance(control,dict): raise ValueError('Malformed native trial hook registry')
        logical=result.get(('hooks',control.get('hook')))
        if logical is not None:
            result.setdefault(('hook_breakpoints',control.get('breakpoint_id')),set()).add(logical)
    return result


def _layer_effect(session, identifier):
    definition=session.project.debug_layer_info(identifier)
    if definition.get('version') != session.version['id']:
        raise ValueError('Hook action layer belongs to another source version')
    binding=deepcopy(definition.get('native_binding'))
    if binding is not None:
        if binding.get('run') != session.run_id or binding.get('epoch') != session._layer_epoch():
            raise ValueError('Hook action layer owner is stale')
        binding.pop('run');binding.pop('epoch')
    return dict(kind=definition.get('kind'),patches=deepcopy(definition.get('patches')),native_binding=binding)


def _hook_actions(session, actions):
    normalized=[]
    for action in actions:
        if not isinstance(action,dict) or not isinstance(action.get('result'),dict):
            raise ValueError('Native trial hook action receipt is malformed')
        op=action.get('op');result=action['result']
        if op in ('layers','task-layers'):
            active=result.get('active')
            if not isinstance(active,list) or any(not isinstance(i,str) for i in active):
                raise ValueError('Native trial hook layer action is incomplete')
            normalized.append(dict(op=op,task_id=result.get('task_id'),
                                   active=[_layer_effect(session,i) for i in active]))
        elif op in ('registers','redirect'):
            normalized.append(dict(op=op,result=_cpu(result)))
        else:
            raise ValueError('Unsupported native trial hook action')
    return normalized


def _stop(result, controls, session):
    if not isinstance(result,dict) or not isinstance(result.get('outcome'),str) or type(result.get('timed_out')) is not bool:
        raise ValueError('Native trial stop receipt is malformed')
    session=result.get('session'); stop=session.get('stop_reason') if isinstance(session,dict) else None
    if not isinstance(stop,dict) or not isinstance(stop.get('kind'),str) or not isinstance(stop.get('breakpoint_ids'),list):
        raise ValueError('Native trial stop classification is incomplete')
    reply=stop.get('native_reply')
    if (stop.get('classification_complete') is False or not isinstance(reply,str)
            or len(reply)<3 or reply[0] not in 'TSWX'
            or any(c not in '0123456789abcdefABCDEF' for c in reply[1:3])):
        raise ValueError('Native trial native stop signal is malformed or incomplete')
    ids=[];hits=[]
    for hit in result.get('hook_hits',[]):
        if not isinstance(hit,dict) or type(hit.get('hit')) is not int or hit['hit'] < 1:
            raise ValueError('Native trial hook hit receipt is malformed')
        logical=controls.get(('hooks',hit.get('hook')))
        candidates=controls.get(('hook_breakpoints',hit.get('breakpoint_id')),set())
        if logical is None or logical not in candidates:
            raise ValueError('Native trial hook hit is not a restored logical hook')
        actions=hit.get('actions')
        if not isinstance(actions,list) or any(not isinstance(a,dict) or not isinstance(a.get('op'),str) for a in actions):
            raise ValueError('Native trial hook actions are malformed')
        task=hit.get('task')
        hits.append(dict(hook=logical,hit=hit['hit'],task_identity=deepcopy(task.get('task_identity')) if isinstance(task,dict) else None,
                         actions=_hook_actions(session,actions)))
    for identifier in stop['breakpoint_ids']:
        logical=controls.get(('breakpoints',identifier))
        if logical is not None: ids.append(logical);continue
        matched=[h['hook'] for h in hits if h['hook'] in controls.get(('hook_breakpoints',identifier),set())]
        if not matched: raise ValueError('Native trial stopped at an untracked breakpoint')
        ids.extend('hook:'+name for name in matched)
    return dict(outcome=result['outcome'],timed_out=result['timed_out'],kind=stop['kind'],
                address=stop.get('address'),breakpoints=sorted(ids),hook_hits=hits,
                signal=reply[:3].upper())


def _trace(session,step,result):
    data,metadata=_artifact(session,result,'trace')
    try: document=json.loads(data)
    except (TypeError,ValueError) as error: raise ValueError('Native trial trace is malformed') from error
    mapping=document.get('mapping') if isinstance(document,dict) else None
    native=document.get('native_process_capture') if isinstance(document,dict) else None
    if (not isinstance(document,dict) or document.get('version') != session.version['id']
            or document.get('run') != {'run':session.run_id}
            or document.get('capture_epoch') != getattr(session,'_runtime_epoch',None)
            or not isinstance(native,dict) or native.get('capture_epoch') != getattr(session,'_runtime_epoch',None)
            or not isinstance(mapping,dict) or mapping.get('source_sha256') != session.metadata['source_sha256']
            or mapping.get('version_sha256') != session.metadata['version_sha256']
            or metadata.get('context') != 'dos-process'
            or metadata.get('capture_kind') != 'stopped-boundary-count'
            or not isinstance(document.get('events'),list)
            or type(document.get('complete')) is not bool or type(document.get('requested_count')) is not int
            or not 1 <= document['requested_count'] <= 10000
            or not isinstance(document.get('window'),dict)):
        raise ValueError('Native trial trace completeness is malformed')
    events=[]; qualified=True
    for event in document['events']:
        if not isinstance(event,dict) or not isinstance(event.get('registers'),dict) or not event['registers']:
            raise ValueError('Native trial trace event is malformed')
        observation=event.get('observation')
        if (not isinstance(observation,dict) or 'instruction_completed' not in observation
                or observation['instruction_completed'] is not None and observation['instruction_completed'] is not False):
            raise ValueError('Native trial trace retirement scope is malformed')
        qualification=event.get('source_qualification')
        if not isinstance(qualification,dict) or type(qualification.get('qualified')) is not bool:
            raise ValueError('Native trial trace lacks source qualification')
        if qualification['qualified'] and (not isinstance(qualification.get('context'),str)
                or not qualification['context'] or not _digest(qualification.get('source_instruction_sha256'))):
            raise ValueError('Native trial trace source qualification is incomplete')
        qualified &= qualification['qualified']
        raw=event.get('execution_bytes',event.get('bytes'))
        if (not isinstance(raw,str) or not raw or len(raw)%2 or len(raw)>30
                or qualification['qualified'] and event.get('project_address') is None
                or event.get('cpu_mode') not in ('real','v86','protected','long')
                or type(event.get('code_bits')) is not int):
            raise ValueError('Native trial trace event identity is incomplete')
        try:
            if bytes.fromhex(raw).hex() != raw.lower(): raise ValueError()
        except ValueError: raise ValueError('Native trial trace instruction bytes are malformed') from None
        events.append(dict(project_address=event['project_address'],address=event.get('address'),
            segmented_address=deepcopy(event.get('segmented_address')),execution_bytes=raw.lower(),
            registers=deepcopy(event['registers']),cpu_mode=event['cpu_mode'],code_bits=event['code_bits'],
            address_context=deepcopy(event.get('address_context')),
            task_id=event.get('task_id'),source_context=qualification.get('context'),
            source_instruction_sha256=qualification.get('source_instruction_sha256'),
            instruction_completed=observation['instruction_completed']))
    complete=(document['complete'] and document['window'].get('closed') is True and qualified
              and len(events)==document['requested_count'] and metadata.get('complete') is True)
    return dict(step=step,artifact=result['artifact'],sha256=result['sha256'],events=events,
                semantics='source-qualified stopped boundaries; retirement unqualified',
                requested_count=document['requested_count'],complete=complete,
                provenance=dict(metadata=metadata,window=deepcopy(document['window'])))


def _screenshot(session,step,result):
    from PIL import Image
    data,metadata=_artifact(session,result,'screenshot')
    try:
        with Image.open(io.BytesIO(data)) as image:
            width,height=image.size
            if image.format != 'PNG' or not 1<=width<=8192 or not 1<=height<=8192 or width*height*3>16*1024**2:
                raise ValueError('Native trial screenshot dimensions exceed bounds')
            pixels=_hash(image.convert('RGB').tobytes())
    except ValueError: raise
    except Exception as error: raise ValueError('Native trial screenshot is malformed') from error
    if metadata.get('width') != width or metadata.get('height') != height:
        raise ValueError('Native trial screenshot metadata dimensions differ')
    if (metadata.get('source') != 'qemu_display_surface' or metadata.get('stopped') is not True
            or metadata.get('selected_cpu_unchanged') is not True or metadata.get('run') != session.run_id
            or metadata.get('sha256') != result['sha256']):
        raise ValueError('Native trial screenshot lacks stopped surface identity')
    if metadata.get('pixel_sha256') is not None and metadata['pixel_sha256'] != pixels:
        raise ValueError('Native trial screenshot pixel hash differs')
    return dict(step=step,artifact=result['artifact'],sha256=result['sha256'],width=width,height=height,
                pixel_sha256=pixels,source=metadata.get('source'),provenance=metadata)


def capture_trial(session, document, report, controls):
    if not isinstance(report,dict) or type(report.get('ok')) is not bool or not isinstance(report.get('steps'),list):
        raise ValueError('Native trial script report is malformed')
    if not isinstance(document,dict) or not isinstance(document.get('script'),dict):
        raise ValueError('Native trial experiment document is malformed')
    if (document.get('version') != session.version['id']
            or document.get('source_sha256') != session.metadata['source_sha256']):
        raise ValueError('Native trial experiment source or version differs')
    if 'observations' not in document:
        raise ValueError('Native trial experiment lacks explicit observations')
    validate_observations(document['observations'])
    steps=document['script'].get('steps')
    if not isinstance(steps,list) or type(report.get('requested_steps')) is not int or report['requested_steps'] != len(steps):
        raise ValueError('Native trial script length differs from its experiment')
    if type(report.get('completed_steps')) is not int or not isinstance(report.get('artifact'),str):
        raise ValueError('Native trial script completion receipt is incomplete')
    encoded_script=json.dumps(document['script'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if report.get('script_sha256') != _hash(encoded_script):
        raise ValueError('Native trial script hash differs from its experiment')
    script_row=session.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(report.get('script_artifact'),)).fetchone()
    if (script_row is None or script_row['kind'] != 'script' or script_row['version'] != session.version['id']
            or script_row['run'] != session.run_id or bytes(script_row['data']) != encoded_script
            or script_row['sha256'] != report['script_sha256']):
        raise ValueError('Native trial script artifact is missing or corrupt')
    supported={'step','run','registers','memory','trace','screenshot','capture-surface',
               'assert','delete-breakpoint','delete-hook'}
    if any(not isinstance(step,dict) or step.get('op') not in supported for step in steps):
        raise ValueError('Native trial script contains an unsupported observation operation')
    row=session.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(report['artifact'],)).fetchone()
    if (row is None or row['kind'] != 'script-result' or row['version'] != session.version['id'] or row['run'] != session.run_id
            or len(row['data']) > _MAX_ARTIFACT or _hash(bytes(row['data'])) != row['sha256']):
        raise ValueError('Native trial script result artifact is missing or corrupt')
    try: saved_report=json.loads(bytes(row['data']))
    except (TypeError,ValueError) as error: raise ValueError('Native trial script artifact is malformed') from error
    try:
        receipt=json.loads(json.dumps({k:v for k,v in report.items() if k != 'artifact'},allow_nan=False))
    except (TypeError,ValueError) as error:
        raise ValueError('Native trial script receipt is not JSON safe') from error
    if saved_report != receipt:
        raise ValueError('Native trial script receipt differs from its artifact')
    mapping=_control_map(controls,session)
    reasons=[];traces=[];screenshots=[];observed=[]
    if not report['ok'] or report['completed_steps'] != len(steps) or len(report['steps']) != len(steps): reasons.append('script_incomplete')
    for index,record in enumerate(report['steps']):
        if (not isinstance(record,dict) or record.get('index') != index or index >= len(steps)
                or record.get('op') != steps[index].get('op') or type(record.get('ok')) is not bool):
            raise ValueError('Native trial script step alignment differs')
        if not record['ok']: reasons.append('script_step_failed'); continue
        op=record['op'];result=record.get('result')
        if not isinstance(result,dict): raise ValueError('Native trial script step lacks its result')
        if op in ('step','run'):
            stop=_stop(result,mapping,session)
            if stop['timed_out']: reasons.append('execution_timeout')
            observed.append(dict(step=index,op=op,value=stop))
        elif op == 'registers': observed.append(dict(step=index,op=op,value=_cpu(result)))
        elif op == 'memory':
            raw=result.get('hex')
            if not isinstance(raw,str) or not raw or len(raw)%2: raise ValueError('Native trial memory observation is malformed')
            try: data=bytes.fromhex(raw)
            except ValueError: raise ValueError('Native trial memory bytes are malformed') from None
            if result.get('length') != len(data) or result.get('space') not in ('physical','virtual'):
                raise ValueError('Native trial memory domain or length is malformed')
            observed.append(dict(step=index,op=op,value=dict(address=result.get('address'),space=result['space'],hex=data.hex())))
        elif op == 'trace':
            trace=_trace(session,index,result);traces.append(trace)
            if not trace['complete']: reasons.append('trace_incomplete')
        elif op in ('screenshot','capture-surface','capture-display'):
            screenshots.append(_screenshot(session,index,result))
        elif op == 'assert':
            if result.get('matched') is not True:
                raise ValueError('Native trial assertion receipt is incomplete')
        elif op in ('delete-breakpoint','delete-hook'):
            if result.get('deleted') is not True:
                raise ValueError('Native trial control deletion receipt is incomplete')
            if op == 'delete-hook' and ('hooks',result.get('hook')) not in mapping:
                raise ValueError('Native trial deleted an untracked hook')
    state=capture_state(session,document['observations']) if not session.closed else None
    if state is None: reasons.append('owner_closed')
    return dict(format=FORMAT,ok=report['ok'],complete=not reasons,incomplete_reasons=sorted(set(reasons)),
        error=deepcopy(report.get('error')),script_report=report['artifact'],
        registers=state['registers'] if state else None,memory=state['memory'] if state else [],
        identity=state['identity'] if state else None,observations=observed,traces=traces,screenshots=screenshots,
        capture_plan=dict(memory_count=len(document['observations']),
            traces=[i for i,s in enumerate(steps) if s.get('op')=='trace'],
            screenshots=[i for i,s in enumerate(steps) if s.get('op') in ('screenshot','capture-surface','capture-display')],
            observations=[i for i,s in enumerate(steps) if s.get('op') in ('step','run','registers','memory')]),
        provenance=dict(**(state['provenance'] if state else dict(run=session.run_id)),
                        raw_script_steps=deepcopy(report['steps'])))


def compare_trials(baseline, layer):
    for trial in (baseline,layer):
        if (not isinstance(trial,dict) or trial.get('format') != FORMAT or type(trial.get('ok')) is not bool
                or type(trial.get('complete')) is not bool or not isinstance(trial.get('incomplete_reasons'),list)
                or not isinstance(trial.get('script_report'),str) or not trial['script_report']
                or not isinstance(trial.get('provenance'),dict)):
            raise ValueError('Malformed native trial envelope')
        for key in ('memory','observations','traces','screenshots'):
            if not isinstance(trial.get(key),list): raise ValueError('Missing native trial observation list: '+key)
    complete=all(t['ok'] and t['complete'] and not t['incomplete_reasons'] for t in (baseline,layer))
    if not complete:
        return dict(complete=False,observed_difference=None,registers=[],memory=[],traces=[],screenshots=[],steps=[],
                    scope='Incomplete captured observations cannot establish equality')
    for trial in (baseline,layer):
        identity=trial.get('identity');cpu=trial.get('registers');plan=trial.get('capture_plan')
        if (not isinstance(identity,dict) or not _digest(identity.get('source_sha256'))
                or not _digest(identity.get('version_sha256'))
                or not (type(identity.get('version')) is int and identity['version'] > 0
                        or isinstance(identity.get('version'),str) and bool(identity['version']))
                or not isinstance(identity.get('runtime'),dict)
                or not isinstance(identity.get('source_mapping'),dict)
                or identity['source_mapping'].get('live') is not True
                or not isinstance(identity.get('allocation'),dict) or 'task_identity' not in identity
                or not isinstance(cpu,dict) or not isinstance(cpu.get('registers'),dict)
                or not ({'rip','eip'} & set(cpu['registers'])) or cpu.get('linear_pc') is None
                or cpu.get('cpu_mode') not in ('real','v86','protected','long')
                or not isinstance(cpu.get('address_state'),dict)
                or not isinstance(cpu.get('unavailable_registers'),list)
                or cpu['address_state'].get('register_context_match') is not True
                or cpu['address_state'].get('machine_vcpus') != 1
                or type(cpu['address_state'].get('a20')) is not bool
                or type(cpu['address_state'].get('paging')) is not bool
                or cpu['address_state'].get('code_bits') not in (16,32,64)):
            raise ValueError('Complete native trial lacks endpoint identity or CPU')
        if (not isinstance(plan,dict) or type(plan.get('memory_count')) is not int
                or plan['memory_count'] != len(trial['memory'])
                or any(not isinstance(plan.get(k),list) or plan[k] != [v.get('step') for v in trial[k]]
                       for k in ('traces','screenshots','observations'))):
            raise ValueError('Complete native trial capture count or plan differs')
    if baseline['capture_plan'] != layer['capture_plan']:
        raise ValueError('Native trial capture plans differ')
    if baseline['identity'] != layer['identity']:
        raise ValueError('Native trial source or version identity differs')
    differences={key:[] for key in ('registers','memory','traces','screenshots','steps')}
    if baseline['registers'] != layer['registers']:
        differences['registers'].append(dict(baseline=baseline['registers'],layer=layer['registers']))
    for key,out in (('memory','memory'),('observations','steps'),('traces','traces'),('screenshots','screenshots')):
        left,right=baseline[key],layer[key]
        if len(left) != len(right): raise ValueError('Native trial capture count differs: '+key)
        seen=set()
        for a,b in zip(left,right,strict=True):
            if not isinstance(a,dict) or not isinstance(b,dict): raise ValueError('Malformed native trial capture')
            if key=='memory':
                fields=('project_address','project_cs','length','context')
            else:
                fields=('step','op') if key=='observations' else ('step',)
                if type(a.get('step')) is not int or a['step'] in seen: raise ValueError('Duplicate or invalid native trial capture index')
                seen.add(a['step'])
            if any(field not in a or field not in b or a[field] != b[field] for field in fields):
                raise ValueError('Native trial capture identity differs: '+key)
            if key=='memory':
                for x in (a,b):
                    context=x.get('context')
                    if (not isinstance(context,dict) or context.get('view') != 'ram'
                            or context.get('scope') not in ('machine','task-private')
                            or not _digest(context.get('mapping_id'))
                            or not isinstance(context.get('backings'),list)
                            or not isinstance(context.get('physical_spans'),list)
                            or not context['physical_spans']):
                        raise ValueError('Malformed native trial RAM-view identity')
                    spans=context['physical_spans']
                    if (any(not isinstance(s,dict) or type(s.get('address')) is not int or s['address'] < 0
                            or type(s.get('length')) is not int or s['length'] < 1 for s in spans)
                            or sum(s['length'] for s in spans) != x['length']
                            or context['scope']=='machine' and context.get('task_identity') is not None
                            or context['scope']=='task-private' and not isinstance(context.get('task_identity'),dict)):
                        raise ValueError('Malformed native trial RAM-view physical spans')
                    try: data=bytes.fromhex(x['hex'])
                    except (KeyError,TypeError,ValueError): raise ValueError('Malformed native trial memory bytes') from None
                    if len(data)!=x['length'] or x.get('sha256')!=_hash(data): raise ValueError('Native trial memory hash differs')
                changed=a['hex'] != b['hex']
            elif key=='observations':
                if not isinstance(a.get('value'),dict) or not isinstance(b.get('value'),dict):
                    raise ValueError('Malformed native trial step observation')
                if a['op'] in ('step','run') and any(
                        not isinstance(x['value'].get('outcome'),str)
                        or type(x['value'].get('timed_out')) is not bool
                        or not isinstance(x['value'].get('kind'),str)
                        or not isinstance(x['value'].get('breakpoints'),list)
                        or not isinstance(x['value'].get('signal'),str)
                        for x in (a,b)):
                    raise ValueError('Malformed native trial stop observation')
                changed=a['value'] != b['value']
            elif key=='traces':
                if (a.get('complete') is not True or b.get('complete') is not True
                        or a.get('semantics') != b.get('semantics') or not isinstance(a.get('events'),list)
                        or not isinstance(b.get('events'),list) or not a['events'] or not b['events']
                        or any(not isinstance(x.get('artifact'),str) or not x['artifact']
                               or not _digest(x.get('sha256')) for x in (a,b))
                        or a.get('requested_count') != len(a['events']) or b.get('requested_count') != len(b['events'])):
                    raise ValueError('Incomplete or mismatched native trial trace')
                for event in a['events']+b['events']:
                    if (not isinstance(event,dict) or event.get('project_address') is None
                            or not isinstance(event.get('registers'),dict) or not event['registers']
                            or event.get('cpu_mode') not in ('real','v86','protected','long')
                            or type(event.get('code_bits')) is not int
                            or not isinstance(event.get('source_context'),str) or not event['source_context']
                            or not _digest(event.get('source_instruction_sha256'))
                            or not isinstance(event.get('address_context'),dict)
                            or type(event.get('task_id')) is not int
                            or not isinstance(event.get('execution_bytes'),str) or not event['execution_bytes']):
                        raise ValueError('Malformed native trial trace boundary')
                    try: bytes.fromhex(event['execution_bytes'])
                    except ValueError: raise ValueError('Malformed native trial trace bytes') from None
                changed=a['events'] != b['events']
                if changed:
                    first=None
                    for index,(left_event,right_event) in enumerate(zip(a['events'],b['events'])):
                        if left_event != right_event:
                            first=dict(index=index,
                                fields=sorted(k for k in left_event.keys() | right_event.keys()
                                              if left_event.get(k) != right_event.get(k)),
                                baseline=deepcopy(left_event),layer=deepcopy(right_event))
                            break
                    differences[out].append(dict(step=a['step'],
                        baseline_artifact=a['artifact'],layer_artifact=b['artifact'],
                        baseline_sha256=a['sha256'],layer_sha256=b['sha256'],
                        baseline_count=len(a['events']),layer_count=len(b['events']),
                        count_differs=len(a['events']) != len(b['events']),
                        semantics=a['semantics'],first_observed_difference=first))
                continue
            else:
                for x in (a,b):
                    if (not _digest(x.get('sha256')) or not _digest(x.get('pixel_sha256'))
                            or type(x.get('width')) is not int or not 1 <= x['width'] <= 8192
                            or type(x.get('height')) is not int or not 1 <= x['height'] <= 8192
                            or x.get('source') != 'qemu_display_surface'):
                        raise ValueError('Malformed native trial screenshot')
                changed=any(a.get(field)!=b.get(field) for field in ('sha256','pixel_sha256','width','height','source'))
            if changed: differences[out].append(dict(baseline=deepcopy(a),layer=deepcopy(b)))
    return dict(complete=True,observed_difference=any(differences.values()),**differences,
                scope='Captured qualified observations only; no deterministic replay or full-machine equivalence')
