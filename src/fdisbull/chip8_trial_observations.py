"""Hash-checked observations of bounded CHIP-8 comparative trials."""
from copy import deepcopy
import hashlib
import json

from .dosbox_rpc import DebuggerError

FORMAT='fdisbull-chip8-trial-observations-1'
SEMANTIC=('rng-model','rng-seed','rng-state','rng-draws','delay-timer','sound-timer',
          'sound-active','pixels-sha256','key-mask','key-wait')


def _sha(data):return hashlib.sha256(data).hexdigest()


def _artifact(session,identifier,kind):
    row=session.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(identifier,)).fetchone()
    if row is None or row['kind']!=kind or row['version']!=session.version['id'] or row['run']!=session.run_id:
        raise ValueError('CHIP-8 trial artifact identity differs')
    data=bytes(row['data'])
    if not data or len(data)>16*1024*1024 or _sha(data)!=row['sha256']:
        raise ValueError('CHIP-8 trial artifact is missing or corrupt')
    return row,data


def _stop(value):
    if type(value.get('timed_out')) is not bool or not isinstance(value.get('outcome'),str):raise ValueError('Invalid CHIP-8 stop')
    hits=value.get('hook_hits',[])
    if not isinstance(hits,list):raise ValueError('Invalid CHIP-8 hook stop')
    normalized=[]
    for hit in hits:
        if not isinstance(hit,dict) or not isinstance(hit.get('hook'),str) or type(hit.get('hit')) is not int or not isinstance(hit.get('actions'),list):
            raise ValueError('Invalid CHIP-8 hook evidence')
        actions=[]
        for action in hit['actions']:
            result=action.get('result') if isinstance(action,dict) else None
            if not isinstance(result,dict) or action.get('op') not in ('layers','registers'):
                raise ValueError('Invalid CHIP-8 hook action evidence')
            if action['op']=='layers': semantic={'active':result.get('active')}
            else:
                regs=result.get('registers')
                if not isinstance(regs,dict):raise ValueError('Invalid CHIP-8 hook register evidence')
                semantic={k:int(v,16) for k,v in regs.items()}
            actions.append(dict(op=action['op'],result=semantic))
        normalized.append(dict(hook=hit['hook'],hit=hit['hit'],actions=actions))
    registers=value.get('registers')
    pc=registers.get('linear_pc') if isinstance(registers,dict) else None
    if value['outcome']!='exited' and not value['timed_out'] and not isinstance(pc,str):raise ValueError('CHIP-8 stop PC missing')
    return dict(outcome=value['outcome'],timed_out=value['timed_out'],pc=pc,hook_hits=normalized)


def capture_trial(session,document,report):
    if not isinstance(report,dict) or type(report.get('ok')) is not bool or not isinstance(report.get('steps'),list):
        raise ValueError('Malformed CHIP-8 trial report')
    steps=document['script']['steps'];reasons=[];screenshots=[];intermediate=[]
    if report.get('run')!=session.run_id:raise ValueError('CHIP-8 trial report run differs')
    if report.get('requested_steps')!=len(steps) or type(report.get('completed_steps')) is not int:
        raise ValueError('CHIP-8 trial step count differs')
    raw=json.dumps(document['script'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if report.get('script_sha256')!=_sha(raw):raise ValueError('CHIP-8 trial script hash differs')
    _,saved_script=_artifact(session,report.get('script_artifact'),'script')
    if saved_script!=raw:raise ValueError('CHIP-8 trial script artifact differs')
    _,saved_report=_artifact(session,report.get('artifact'),'script-result')
    if json.loads(saved_report)!=json.loads(json.dumps({k:v for k,v in report.items() if k!='artifact'},allow_nan=False)):
        raise ValueError('CHIP-8 trial report artifact differs')
    if not report['ok'] or report['completed_steps']!=len(steps) or len(report['steps'])!=len(steps):reasons.append('script_incomplete')
    for index,record in enumerate(report['steps']):
        if not isinstance(record,dict) or record.get('index')!=index or index>=len(steps) or record.get('op')!=steps[index].get('op') or type(record.get('ok')) is not bool:
            raise ValueError('CHIP-8 trial step alignment differs')
        if not record['ok']:reasons.append('script_step_failed');continue
        op=record['op'];value=record.get('result')
        if not isinstance(value,dict):raise ValueError('CHIP-8 trial step result missing')
        if op=='screenshot':
            row,png=_artifact(session,value.get('artifact'),'screenshot')
            if len(png)>1024*1024 or value.get('sha256')!=row['sha256']:raise ValueError('CHIP-8 screenshot receipt differs')
            from PIL import Image
            import io
            with Image.open(io.BytesIO(png)) as image:
                if image.format!='PNG' or image.size!=(64,32) or image.mode!='RGBA':raise ValueError('Invalid CHIP-8 screenshot')
                image.load();pixel_sha=_sha(image.tobytes())
            try:metadata=json.loads(row['metadata'])
            except (ValueError,TypeError):raise ValueError('Invalid CHIP-8 screenshot metadata') from None
            if (metadata.get('format')!='chip8-frame-png-1' or metadata.get('width')!=64 or metadata.get('height')!=32 or
                    metadata.get('identity')!=session.identity or metadata.get('environment')!=value.get('environment') or
                    metadata.get('pixel_sha256')!=pixel_sha or value.get('pixel_sha256')!=pixel_sha):
                raise ValueError('CHIP-8 screenshot pixel or source proof differs')
            try:
                from .qemu_chip8 import _validate_environment
                environment=_validate_environment(metadata['environment'])
                pixels=bytes.fromhex(environment['pixels-hex'])
                rgba=b''.join(b'\xff\xff\xff\xff' if p else b'\x00\x00\x00\xff' for p in pixels)
            except (KeyError,TypeError,ValueError,DebuggerError) as error:
                raise ValueError('Invalid CHIP-8 screenshot environment') from error
            if _sha(rgba)!=pixel_sha:raise ValueError('CHIP-8 screenshot differs from native pixels')
            screenshots.append(dict(step=index,artifact=value['artifact'],sha256=row['sha256'],pixel_sha256=pixel_sha))
        elif op in ('step','run'):
            normalized=_stop(value)
            if normalized['timed_out']:reasons.append('execution_timeout')
            intermediate.append(dict(step=index,op=op,value=normalized))
        elif op=='registers':
            regs=value.get('registers')
            if not isinstance(regs,dict) or not regs:raise ValueError('Invalid CHIP-8 intermediate registers')
            intermediate.append(dict(step=index,op=op,value={k:int(v,16) for k,v in regs.items()}))
        elif op=='memory':
            try:data=bytes.fromhex(value['hex'])
            except (KeyError,ValueError,TypeError):raise ValueError('Invalid CHIP-8 intermediate memory') from None
            try:
                requested=steps[index]['address'];requested=int(requested,0) if isinstance(requested,str) else requested
                received=value['address'];received=int(received,0) if isinstance(received,str) else received
            except (KeyError,ValueError,TypeError):raise ValueError('Invalid CHIP-8 memory address receipt') from None
            if (type(requested) is not int or type(received) is not int or requested!=received or
                    len(data)!=value.get('length') or len(data)!=steps[index].get('length',16) or
                    value.get('space')!=steps[index].get('space','physical')):
                raise ValueError('CHIP-8 intermediate memory receipt differs')
            intermediate.append(dict(step=index,op=op,value=dict(address=value['address'],length=len(data),hex=data.hex())))
        elif op=='assert' and value.get('matched') is not True:raise ValueError('CHIP-8 assertion receipt differs')
        elif op=='delete-hook' and value.get('deleted') is not True:raise ValueError('CHIP-8 hook deletion receipt differs')
    snapshot=session._chip8_experiment_snapshot(document['observations']) if not session.closed else None
    if snapshot is None:reasons.append('owner_closed')
    return dict(format=FORMAT,ok=report['ok'],complete=not reasons,incomplete_reasons=reasons,
        script_report=report['artifact'],registers=snapshot['cpu'] if snapshot else None,
        memory=snapshot['memory'] if snapshot else [],screenshots=screenshots,observations=intermediate,
        devices=snapshot['semantic'] if snapshot else None,identity=deepcopy(snapshot['identity']) if snapshot else None,
        capture_plan=dict(script_sha256=document['script_sha256'],memory=deepcopy(document['observations']),
            observations=[dict(step=i,op=step['op']) for i,step in enumerate(steps) if step['op'] in ('step','run','registers','memory')],
            screenshots=[i for i,step in enumerate(steps) if step['op']=='screenshot']),
        provenance=dict(report=deepcopy(report),snapshot=snapshot))


def _digest(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _complete_evidence(trial):
    from .qemu_chip8 import REGISTER_NAMES, RNG_MODEL
    cpu=trial.get('registers');devices=trial.get('devices');plan=trial.get('capture_plan');provenance=trial.get('provenance')
    if not isinstance(cpu,dict) or set(cpu)!=set(REGISTER_NAMES):raise ValueError('CHIP-8 trial CPU schema differs')
    for key,value in cpu.items():
        maximum=16 if key=='sp' else 255 if key.startswith('v') else 65535
        if type(value) is not int or not 0<=value<=maximum:raise ValueError('CHIP-8 trial CPU value differs')
    if not isinstance(devices,dict) or set(devices)!=set(SEMANTIC)|{'accepted-edges','held-mask','fault'}:
        raise ValueError('CHIP-8 trial device schema differs')
    if (devices['rng-model']!=RNG_MODEL or not _digest(devices['pixels-sha256']) or
            type(devices['sound-active']) is not bool or type(devices['key-wait']) is not bool):
        raise ValueError('CHIP-8 trial device proof differs')
    limits={'rng-seed':0xffffffff,'rng-state':0xffffffff,'rng-draws':(1<<64)-1,
            'delay-timer':255,'sound-timer':255,'key-mask':65535,'held-mask':65535,'accepted-edges':(1<<64)-1}
    if any(type(devices[k]) is not int or not 0<=devices[k]<=v for k,v in limits.items()):
        raise ValueError('CHIP-8 trial device value differs')
    if devices['sound-active']!=(devices['sound-timer']>0):raise ValueError('CHIP-8 trial sound state differs')
    fault=devices['fault']
    if not isinstance(fault,dict) or type(fault.get('faulted')) is not bool or any(type(fault.get(k)) is not int for k in ('fault-code','fault-pc','fault-opcode')):
        raise ValueError('CHIP-8 trial fault proof differs')
    if not isinstance(plan,dict) or not _digest(plan.get('script_sha256')) or not isinstance(plan.get('memory'),list) or not isinstance(plan.get('observations'),list) or not isinstance(plan.get('screenshots'),list):
        raise ValueError('CHIP-8 trial capture plan differs')
    if not isinstance(provenance,dict) or not isinstance(provenance.get('snapshot'),dict) or not isinstance(provenance.get('report'),dict):
        raise ValueError('CHIP-8 trial provenance missing')
    snapshot=provenance['snapshot'];report=provenance['report'];identity=trial.get('identity')
    if (not isinstance(identity,dict) or identity.get('cpu_subset')!='fdisbull-chip8-frame-keys-6' or
            identity.get('profile')!='chip8-classic-pilot-default-v1' or
            any(not _digest(identity.get(k)) for k in ('source_sha256','version_sha256','qemu_sha256')) or
            snapshot.get('identity')!=identity):
        raise ValueError('CHIP-8 trial source/runtime identity differs')
    if (snapshot.get('cpu')!=cpu or snapshot.get('memory')!=trial.get('memory') or snapshot.get('semantic')!=devices or
            report.get('script_sha256')!=plan['script_sha256'] or report.get('artifact')!=trial.get('script_report')):
        raise ValueError('CHIP-8 trial provenance differs')
    try:
        from .qemu_chip8 import _validate_environment
        environment=_validate_environment(snapshot['environment'])
        registers={k:int(v,16) for k,v in snapshot['registers']['registers'].items()}
        raw_ram=bytes.fromhex(snapshot['ram_hex']);key_native=snapshot['key_native']
        semantic={**{k:environment[k] for k in SEMANTIC},'accepted-edges':key_native['accepted-edges'],
                  'held-mask':key_native['held-mask'],'fault':snapshot['fault']}
    except (KeyError,TypeError,ValueError,DebuggerError,AttributeError) as error:
        raise ValueError('CHIP-8 trial snapshot proof malformed') from error
    if (registers!=cpu or len(raw_ram)!=4096 or semantic!=devices or
            key_native.get('key-mask')!=environment['key-mask'] or
            key_native.get('state-generation')!=environment['state-generation']):
        raise ValueError('CHIP-8 trial snapshot proof differs')
    memory=trial.get('memory');observations=trial.get('observations');screenshots=trial.get('screenshots')
    if not isinstance(memory,list) or len(memory)!=len(plan['memory']) or not isinstance(observations,list) or not isinstance(screenshots,list):
        raise ValueError('CHIP-8 trial observations missing')
    for entry,requested in zip(memory,plan['memory']):
        if not isinstance(entry,dict) or not isinstance(requested,dict) or entry.get('address')!=requested.get('address') or entry.get('length')!=requested.get('length'):
            raise ValueError('CHIP-8 trial RAM plan differs')
        try:data=bytes.fromhex(entry['hex'])
        except (KeyError,ValueError,TypeError):raise ValueError('CHIP-8 trial RAM bytes malformed') from None
        try:address=int(entry['address'],0) if isinstance(entry['address'],str) else entry['address']
        except ValueError:raise ValueError('CHIP-8 trial RAM address malformed') from None
        if (type(address) is not int or address<0 or address+len(data)>4096 or len(data)!=entry['length'] or
                _sha(data)!=entry.get('sha256') or raw_ram[address:address+len(data)]!=data):
            raise ValueError('CHIP-8 trial RAM proof differs')
    if len(observations)!=len(plan['observations']) or any(not isinstance(a,dict) or not isinstance(b,dict) or a.get('step')!=b.get('step') or a.get('op')!=b.get('op') or 'value' not in a for a,b in zip(observations,plan['observations'])):
        raise ValueError('CHIP-8 intermediate observation plan differs')
    records=report.get('steps')
    if not isinstance(records,list) or report.get('ok') is not True or report.get('completed_steps')!=report.get('requested_steps') or len(records)!=report.get('requested_steps'):
        raise ValueError('CHIP-8 trial report completion differs')
    if (any(not isinstance(record,dict) or record.get('index')!=i or record.get('ok') is not True for i,record in enumerate(records)) or
            plan['observations']!=[dict(step=i,op=record['op']) for i,record in enumerate(records) if record.get('op') in ('step','run','registers','memory')] or
            plan['screenshots']!=[i for i,record in enumerate(records) if record.get('op')=='screenshot']):
        raise ValueError('CHIP-8 trial report capture plan differs')
    seen=set()
    for entry in observations:
        index=entry['step'];op=entry['op']
        if type(index) is not int or index<0 or index>=len(records) or index in seen:
            raise ValueError('CHIP-8 intermediate index differs')
        seen.add(index);record=records[index]
        if not isinstance(record,dict) or record.get('index')!=index or record.get('op')!=op or record.get('ok') is not True or not isinstance(record.get('result'),dict):
            raise ValueError('CHIP-8 intermediate provenance differs')
        raw=record['result']
        try:
            if op in ('step','run'):expected=_stop(raw)
            elif op=='registers':expected={k:int(v,16) for k,v in raw['registers'].items()}
            elif op=='memory':expected=dict(address=raw['address'],length=raw['length'],hex=bytes.fromhex(raw['hex']).hex())
            else:raise ValueError('Unsupported CHIP-8 intermediate observation')
        except (KeyError,TypeError,ValueError):raise ValueError('CHIP-8 intermediate provenance malformed') from None
        if entry['value']!=expected:raise ValueError('CHIP-8 intermediate value differs from report')
    if len(screenshots)!=len(plan['screenshots']) or any(not isinstance(a,dict) or a.get('step')!=b or not isinstance(a.get('artifact'),str) or not _digest(a.get('sha256')) or not _digest(a.get('pixel_sha256')) for a,b in zip(screenshots,plan['screenshots'])):
        raise ValueError('CHIP-8 screenshot plan differs')
    for image in screenshots:
        index=image['step']
        if type(index) is not int or index<0 or index>=len(records):raise ValueError('CHIP-8 screenshot index differs')
        record=records[index];value=record.get('result') if isinstance(record,dict) else None
        if (record.get('op')!='screenshot' or record.get('ok') is not True or not isinstance(value,dict) or
                any(image.get(k)!=value.get(k) for k in ('artifact','sha256','pixel_sha256'))):
            raise ValueError('CHIP-8 screenshot provenance differs')


def compare_trials(baseline, layer):
    for trial in (baseline,layer):
        if (not isinstance(trial,dict) or trial.get('format')!=FORMAT or type(trial.get('ok')) is not bool or
                type(trial.get('complete')) is not bool or not isinstance(trial.get('incomplete_reasons'),list)):
            raise ValueError('Malformed CHIP-8 trial')
    if not all(t['ok'] and t['complete'] and not t['incomplete_reasons'] for t in (baseline,layer)):
        return dict(complete=False,observed_difference=None,registers=[],memory=[],screenshots=[],steps=[],devices=[],
                    scope='Incomplete captured observations cannot establish equality')
    for trial in (baseline,layer):_complete_evidence(trial)
    if baseline['capture_plan']!=layer['capture_plan'] or baseline['identity']!=layer['identity']:
        raise ValueError('CHIP-8 trial capture plans or source identity differ')
    differences={}
    for key in ('registers','memory','observations','devices'):
        differences[key]=[] if baseline[key]==layer[key] else [dict(baseline=baseline[key],layer=layer[key])]
    a=baseline['screenshots'];b=layer['screenshots']
    differences['screenshots']=[dict(step=x['step'],baseline_artifact=x['artifact'],layer_artifact=y['artifact'],
        baseline_sha256=x['sha256'],layer_sha256=y['sha256'],different=x['pixel_sha256']!=y['pixel_sha256']) for x,y in zip(a,b)]
    different=any(differences[k] for k in ('registers','memory','observations','devices')) or any(x['different'] for x in differences['screenshots'])
    return dict(complete=True,observed_difference=different,registers=differences['registers'],memory=differences['memory'],
                screenshots=differences['screenshots'],steps=differences['observations'],devices=differences['devices'],
                scope='Only captured CPU, declared RAM, stops, screenshots and selected device fields; no deterministic replay claim')
