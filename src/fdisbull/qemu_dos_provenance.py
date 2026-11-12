"""Native, bounded DOS save evidence and opt-in keep service.

The native observer owns call/return and raw-I/O coverage. FAT inventories are
only final byte evidence. Host keep reservations are never part of VM rewind.
"""
from copy import deepcopy
import re
import uuid

from .dos_file_layers import WorkspaceStore
from .dos_keep_policy import KeepPolicyStore
from .qemu_workspace import _dos_path, _json, _sha, _seal_workspace, _generation_receipt
from .qemu_workspace_output import _context, _boundary, _select_output

FORMAT = 'fdisbull-dos-guest-create-1'
CHECKPOINT = 'fdisbull-dos-save-witness-checkpoint-1'
KIND = 'workspace-guest-create-provenance'
ARM = 'x-fdisbull-arm-dos-save-witness'
ARM_SAVE = 'x-fdisbull-arm-dos-save-operations'
QUERY = 'x-fdisbull-query-dos-save-witness'
DISARM = 'x-fdisbull-disarm-dos-save-witness'
COMMANDS = frozenset((ARM, QUERY, DISARM))
MODEL = 'qemu-pc-dos-save-witness-v1'
MAX_BYTES = 65536


def before_host_operation(session,name,args=(),kwargs=None):
    binding=getattr(session,'_dos_save_witness',None)
    if not binding or getattr(session,'_qemu_cpu_delta_full_load_depth',0):return
    name=name.replace('-','_');kwargs=kwargs or {}
    mutation=name in {'write_memory','write_registers','write_runtime_memory','memory_apply',
                      'memory_rule_tick','memory_rule_run','layer_enable','layer_disable','layer_patch'}
    if name in ('layers','dos_task_layers'):
        mutation=kwargs.get('active',args[0] if args else None) is not None
    if name.startswith('dos_task_') and name not in ('dos_task_observe','dos_task_context',
            'dos_task_memory','dos_task_layers','dos_task_scheduler_observe'):
        mutation=True
    if mutation and not binding.get('host_fault'):
        binding['host_fault']='Unobserved host mutation: '+name
        session._event('workspace-provenance-invalidated',dict(reason=binding['host_fault']))


def _number(value, label, maximum=(1 << 64)-1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('Invalid native save witness ' + label)
    return value


def _path(path):
    value = _dos_path(path)
    if ('\\' in value or not re.fullmatch(r"[A-Z0-9_~!#$%&'()@^`{}-]{1,8}(?:\.[A-Z0-9_~!#$%&'()@^`{}-]{1,3})?", value)
            or value.split('.')[0] in ('CON','PRN','AUX','NUL','CLOCK$')
            or re.fullmatch(r'(COM|LPT)[1-9]',value.split('.')[0])):
        raise ValueError('Guest-create witness requires one root D: non-device 8.3 path')
    return value


def validate(info):
    if isinstance(info,dict) and info.get('api-version') == 2:
        from .dos_save_operations import validate_packet
        validate_packet(info)
        return deepcopy(info)
    if (not isinstance(info, dict) or info.get('api-version') != 1 or info.get('model') != MODEL
            or type(info.get('active')) is not bool or type(info.get('valid')) is not bool):
        raise ValueError('Unsupported native DOS save witness response')
    for key in ('epoch','generation','event-count','write-count','bytes-written','child-psp','created-handle'):
        _number(info.get(key),key)
    if info['epoch'] == 0 or info['bytes-written'] > MAX_BYTES:
        raise ValueError('Native save witness epoch or byte bound is invalid')
    events = info.get('events')
    if not isinstance(events,list) or len(events)>256 or len(events)!=info['event-count']:
        raise ValueError('Native save witness event coverage is incomplete')
    for i,event in enumerate(events,1):
        if not isinstance(event,dict) or event.get('sequence') != i or type(event.get('carry')) is not bool:
            raise ValueError('Invalid native save witness event sequence')
        for key in ('function','handle','ax','requested','accepted','caller-pc','return-pc'):
            _number(event.get(key),key,(1<<32)-1)
    if type(info.get('pending')) is not bool:
        raise ValueError('Native save witness pending-call identity is missing')
    try:
        payload = bytes.fromhex(info['payload-hex'])
    except (KeyError,ValueError,TypeError):
        raise ValueError('Invalid native save witness payload') from None
    if len(payload)!=info['bytes-written'] or len(payload)>MAX_BYTES:
        raise ValueError('Native save witness payload length differs')
    if info['active']:
        if not isinstance(info.get('token'),str) or not info['token']:
            raise ValueError('Native save witness has no owner token')
        if info.get('dos-path') != 'D:\\'+_path(info.get('dos-path')):
            raise ValueError('Native save witness path differs')
        ranges=info.get('source-ranges')
        if not isinstance(ranges,list) or not 1<=len(ranges)<=32:
            raise ValueError('Native save witness source ranges are missing')
        for entry in ranges:
            if (not isinstance(entry,dict) or type(entry.get('start')) is not int
                    or type(entry.get('size')) is not int or entry['start']<0
                    or entry['size']<=0 or entry['start']+entry['size']>0xa0000):
                raise ValueError('Native save witness source range is invalid')
    return deepcopy(info)


def query(vm):
    if not COMMANDS <= getattr(vm,'qmp_commands',set()):
        return None
    return validate(vm.qmp.call(QUERY))


def _bound(session,info,binding=None, *, check_workspace=True):
    binding = getattr(session,'_dos_save_witness',None) if binding is None else binding
    if not isinstance(binding,dict) or not info or not info['active']:
        raise ValueError('No active owned DOS save witness')
    expected=dict(token=binding['observer_token'], **{'child-psp':binding['child_psp'],
        'dos-path':'D:\\'+binding['path'],'source-ranges':binding['source_ranges'],
        'int21-vector':binding['int21_vector']})
    if any(info.get(key)!=value for key,value in expected.items()):
        raise ValueError('Native save witness owner/source/path binding changed')
    if binding.get('mode','exclusive') == 'save':
        if (info.get('api-version') != 2
                or info.get('initial-exists') != binding['initial_exists']
                or info.get('initial-payload-hex') != binding['initial_payload_hex']
                or info.get('temporary-path') != ('D:\\'+binding['temporary_path'] if binding['temporary_path'] else '')):
            raise ValueError('Native save-operation preimage/path binding changed')
    elif info.get('api-version') != 1:
        raise ValueError('Native save witness operation mode changed')
    if (binding.get('version') != session.version['id']
            or binding.get('source_sha256') != session.metadata.get('source_sha256')
            or check_workspace and binding.get('base_generation') != session._dos_workspace['base_generation']['artifact']):
        raise ValueError('DOS save witness workspace/source binding changed')
    return binding


def _unprotected(loaded,path):
    manifest=loaded['manifest']
    entry=next((e for e in loaded['entries'] if e['dos_path']==path),None)
    if (path in manifest['protected_dos_paths'] or path.casefold() in manifest['protected_paths']
            or entry and entry['path'].casefold() in manifest['protected_paths']):
        raise ValueError('Save path exists in the protected admission set')
    return entry


def _proof_payload(doc):
    if doc['native'].get('api-version') == 2:
        from .dos_save_operations import replay
        return replay(doc['native'])
    return bytes.fromhex(doc['native']['payload-hex'])


def _stored_proof(session,reference,seen=()):
    if (not isinstance(reference,dict) or not isinstance(reference.get('artifact'),str)
            or reference['artifact'] in seen or len(seen)>=32):
        raise ValueError('Invalid or cyclic save provenance predecessor')
    import json
    store=WorkspaceStore(session)
    row,data=store._row(reference['artifact'],KIND)
    if row['sha256']!=reference.get('sha256'):
        raise ValueError('Guest-create reference hash differs')
    doc=json.loads(data)
    validate_proof_document(doc)
    if (doc.get('version')!=session.version['id']
            or doc.get('source_sha256')!=session.metadata['source_sha256']):
        raise ValueError('Save provenance source/version changed')
    loaded=store.load(doc['generation'])
    if (loaded['manifest']['base'] or loaded['artifact'])!=doc.get('base_generation'):
        raise ValueError('Save provenance base generation changed')
    entry=_select_output(store,doc['generation'],_path(doc['path']))
    payload=_proof_payload(doc)
    if entry['data']!=payload or entry['sha256']!=doc['payload_sha256'] or entry['size']!=doc['size']:
        raise ValueError('Save provenance sealed bytes differ')
    if doc['format']!=FORMAT:
        if doc['binding'].get('base_generation')!=doc['base_generation']:
            raise ValueError('Save proof and preimage workspace bases differ')
        _verify_arm_preimage(session,doc['binding'],seen+(reference['artifact'],))
    return doc,payload


def _save_preimage(session,loaded,path,predecessor,seen=()):
    entry=_unprotected(loaded,path)
    if entry is None:
        if predecessor is not None:raise ValueError('Save predecessor has no current file')
        return False,b''
    if entry['type']!='file' or entry['size']>MAX_BYTES:
        raise ValueError('Existing save is not a bounded ordinary file')
    if predecessor is not None:
        doc,payload=_stored_proof(session,predecessor,seen)
        if (doc['path']!=path or doc['base_generation']!=(loaded['manifest']['base'] or loaded['artifact'])
                or entry['data']!=payload):
            raise ValueError('Existing save differs from its provenance predecessor')
    elif entry['origin']!='new':
        raise ValueError('Existing save needs authored-create or stored provenance predecessor')
    return True,entry['data']


def _verify_arm_preimage(session,binding,seen=()):
    required={'arm_generation','base_generation','version','source_sha256','path',
              'initial_exists','initial_payload_hex','temporary_path'}
    if not isinstance(binding,dict) or not required <= binding.keys():
        raise ValueError('Save preimage binding is incomplete')
    store=WorkspaceStore(session);loaded=store.load(binding['arm_generation'])
    if ((loaded['manifest']['base'] or loaded['artifact'])!=binding['base_generation']
            or binding.get('version')!=session.version['id']
            or binding.get('source_sha256')!=session.metadata['source_sha256']):
        raise ValueError('Save preimage source/base binding changed')
    exists,payload=_save_preimage(session,loaded,binding['path'],binding.get('predecessor'),seen)
    if exists!=binding['initial_exists'] or payload.hex()!=binding['initial_payload_hex']:
        raise ValueError('Save preimage bytes changed')
    temp=binding['temporary_path']
    if temp is not None and _unprotected(loaded,temp) is not None:
        raise ValueError('Temporary save path already exists')


def start(session,path,directory=None, *, mode='exclusive',temporary_path=None,predecessor=None):
    path = _path(path)
    if mode not in ('exclusive','save'):
        raise ValueError('Save provenance mode must be exclusive or save')
    if mode=='exclusive' and (temporary_path is not None or predecessor is not None):
        raise ValueError('Temporary paths and predecessors require save mode')
    temporary_path=_path(temporary_path) if temporary_path is not None else None
    if temporary_path==path:raise ValueError('Temporary save path must differ from final path')
    context = _context(session)
    if not COMMANDS <= session.vm.qmp_commands:
        raise ValueError('Guest-create provenance requires the native DOS save witness extension')
    if mode=='save' and ARM_SAVE not in session.vm.qmp_commands:
        raise ValueError('Save operations require the native N23 extension')
    prior=query(session.vm)
    if prior['active']:
        raise ValueError('Disarm the existing DOS save witness before arming another')
    # The verified helper establishes DOS's current PSP with AH=50h immediately
    # before original target entry. No earlier unobserved guest interval is
    # admitted; the native observer then rejects process/PSP-changing calls.
    session._process_checkpoint_verify_entry()
    state=session._dos_workspace
    base=state['base_generation']['artifact']
    store=WorkspaceStore(session)
    current=store.load(state['generation']['artifact'])
    entry=_unprotected(current,path)
    if mode=='exclusive' and entry is not None:
        raise ValueError('Guest-create path already exists or is protected')
    initial_exists,initial_payload=False,b''
    if mode=='save':
        initial_exists,initial_payload=_save_preimage(session,current,path,predecessor)
        if temporary_path is not None and _unprotected(current,temporary_path) is not None:
            raise ValueError('Temporary save path already exists')
    ranges=[]
    for item in session._process['source_mapping']['live_ranges']:
        start=_number(item['runtime_address'],'source start',0x9ffff)
        size=_number(item['length'],'source size',0xa0000)
        if not size or start+size>0xa0000:
            raise ValueError('Guest-create source range is not conventional RAM')
        ranges.append(dict(start=start,size=size))
    if not 1<=len(ranges)<=32:
        raise ValueError('Guest-create source mapping is unavailable or too fragmented')
    token=uuid.uuid4().hex
    vectors=getattr(session,'_vectors_before',None)
    if not isinstance(vectors,bytes) or len(vectors)!=1024:
        raise ValueError('Original DOS interrupt vector identity is unavailable')
    expected_vector=int.from_bytes(vectors[0x84:0x88],'little')
    policy=None
    if directory is not None:
        policy=KeepPolicyStore(session).create(path,directory,token,base)
    binding=dict(format=CHECKPOINT,observer_token=token,path=path,child_psp=session._ready['child_psp'],
                 int21_vector=expected_vector,
                 source_ranges=ranges,source_sha256=session.metadata['source_sha256'],
                 version=session.version['id'],base_generation=base,arm_context=context,
                 ownership='verified original loader entry; process-changing DOS calls invalidate',
                 policy_id=policy['artifact'] if policy else None)
    if mode=='save':
        binding.update(mode=mode,temporary_path=temporary_path,initial_exists=initial_exists,
                       initial_payload_hex=initial_payload.hex(),predecessor=deepcopy(predecessor),
                       arm_generation=current['artifact'])
    arguments={'token':token,'child-psp':binding['child_psp'],
               'source-ranges':ranges,'dos-path':'D:\\'+path,'int21-vector':expected_vector}
    if mode=='save':
        arguments.update({'initial-exists':initial_exists,'initial-payload-hex':initial_payload.hex(),
                          'temporary-path':'D:\\'+temporary_path if temporary_path else ''})
    try:
        session.vm.qmp.call(ARM_SAVE if mode=='save' else ARM,arguments)
        actual=query(session.vm)
        _bound(session,actual,binding)
        if not actual['valid'] or actual['phase']!='armed':
            raise ValueError('Native save witness did not arm cleanly')
        session._dos_save_witness=binding
        session._event('workspace-provenance-start',binding)
    except BaseException as error:
        error.result=dict(binding=binding,policy=policy,disposition='uncertain; do not replay arm')
        session.close()
        raise
    return dict(format=CHECKPOINT,binding=deepcopy(binding),policy=policy,native=_summary(actual))


def _summary(info):
    value=deepcopy(info)
    payload=bytes.fromhex(value.pop('payload-hex'))
    value['payload-sha256']=_sha(payload)
    return value


def status(session):
    info=query(session.vm)
    if info is None:
        raise ValueError('Native DOS save witness extension is unavailable')
    binding=getattr(session,'_dos_save_witness',None)
    if info['active']:
        _bound(session,info)
    result=dict(format=CHECKPOINT,binding=deepcopy(binding),native=_summary(info))
    if binding and binding.get('policy_id'):
        result['policy']=KeepPolicyStore(session).status(binding['policy_id'])
    return result


def stop(session):
    info=query(session.vm);binding=_bound(session,info)
    session._artifact('workspace-witness-stop.json','workspace-save-witness-record',
                      _json(dict(binding=binding,native=info)),dict(format=CHECKPOINT))
    if binding.get('policy_id'):
        KeepPolicyStore(session).set_enabled(binding['policy_id'],False)
    try:
        session.vm.qmp.call(DISARM,{'token':binding['observer_token'],'expected-generation':info['generation']})
        after=query(session.vm)
        if after['active']:
            raise ValueError('Native DOS save witness remained active')
    except BaseException:
        session.close();raise
    return status(session)


def capture_checkpoint(session):
    info=query(session.vm)
    binding=getattr(session,'_dos_save_witness',None)
    if info is None:
        if binding:raise ValueError('Checkpoint lost its native DOS save witness extension')
        return None
    if info['active']:
        _bound(session,info,binding)
        return dict(format=CHECKPOINT,binding=deepcopy(binding),native=info)
    return None


def validate_checkpoint(session,record):
    if record is None:return
    if not isinstance(record,dict) or record.get('format')!=CHECKPOINT:
        raise ValueError('Invalid DOS save witness checkpoint record')
    info=validate(record.get('native'))
    binding=record.get('binding')
    _bound(session,info,binding,check_workspace=False)
    if binding.get('mode')=='save':_verify_arm_preimage(session,binding)
    WorkspaceStore(session).load(binding['base_generation'])
    if binding.get('policy_id'):
        KeepPolicyStore(session).load(binding['policy_id'])


def verify_loaded(vm,record):
    actual=query(vm)
    if record is None:
        if actual and actual['active']:raise ValueError('Restored an unrecorded DOS save witness')
        return None
    if actual is None:raise ValueError('Fresh QEMU lacks the DOS save witness extension')
    expected=deepcopy(record['native']);left=deepcopy(actual)
    for key in ('epoch','generation'):
        expected.pop(key,None);left.pop(key,None)
    if (left!=expected or actual['epoch']<=record['native']['epoch']
            or actual['generation']<=record['native']['generation']):
        raise ValueError('Restored native DOS save witness differs from checkpoint')
    return actual


def adopt(session,record,actual):
    session._dos_save_witness=deepcopy(record['binding']) if record else None
    if record:_bound(session,actual)


def _ready(session,info):
    binding=_bound(session,info)
    if (binding.get('host_fault') or not info['valid'] or info['phase']!='ready'
            or any(info.get(k) is not True for k in ('close-seen','flush-seen'))
            or info.get('api-version')==1 and not info['create-seen']):
        raise ValueError('Guest-save evidence has no completed owned close/flush witness')
    return binding


def validate_proof_document(doc):
    from .dos_save_operations import FORMAT as SAVE_FORMAT, validate_document
    if isinstance(doc,dict) and doc.get('format')==SAVE_FORMAT:
        return validate_document(doc)
    if not isinstance(doc,dict) or doc.get('format')!=FORMAT:
        raise ValueError('Invalid guest-create provenance document')
    info=validate(doc.get('native'))
    if not isinstance(doc.get('binding',{}),dict) or doc.get('binding',{}).get('host_fault'):
        raise ValueError('Guest-create host mutation coverage is invalid')
    path=_path(doc.get('path'))
    if (not info['active'] or not info['valid'] or info['phase']!='ready' or info.get('pending') is not False
            or any(info.get(k) is not True for k in ('create-seen','close-seen','flush-seen'))
            or info.get('token')!=doc.get('observer_token') or info.get('dos-path')!='D:\\'+path):
        raise ValueError('Guest-create native proof is incomplete or misbound')
    payload=bytes.fromhex(info['payload-hex'])
    if doc.get('payload_sha256')!=_sha(payload) or doc.get('size')!=len(payload):
        raise ValueError('Guest-create accepted payload differs from its receipt')
    created=closed=flushed=False;written=writes=0;committed=False
    handle=info['created-handle']
    for event in info['events']:
        for key in ('caller-pc','return-pc'):
            if not any(r['start']<=event[key]<r['start']+r['size'] for r in info['source-ranges']):
                raise ValueError('Guest-create event is outside its source owner')
        fn=event['function']
        if fn in (0x51,0x62) and event['handle']==info['child-psp']:
            continue
        if fn in (0x01,0x02,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,
                  0x19,0x1a,0x2f,0x30,0x34,0x35,0x36,0x3f,0x4e,0x4f,0x52,0x59):
            continue
        if fn==0x5b and not created and not event['carry'] and event['ax']==handle:
            created=True
        elif fn==0x40 and created and not closed and not event['carry'] and event['handle']==handle:
            if not 1<=event['requested']<=65535 or event['accepted']!=event['requested'] or event['ax']!=event['accepted']:
                raise ValueError('Guest-create write did not complete exactly')
            written+=event['accepted'];writes+=1
        elif fn==0x68 and created and not closed and not event['carry'] and event['handle']==handle:
            committed=True
        elif fn==0x3e and created and not closed and not event['carry'] and event['handle']==handle:
            closed=True
        elif fn==0x0d and closed:
            flushed=True
        else:
            raise ValueError('Guest-create event order or operation is unqualified')
    if (not created or not closed or not flushed or written!=len(payload)
            or writes!=info['write-count'] or committed!=info.get('commit-seen')):
        raise ValueError('Guest-create event coverage or accepted-byte totals differ')
    return info


def provenance(session,sealed=None):
    before=query(session.vm);binding=_ready(session,before)
    if binding.get('mode')=='save':_verify_arm_preimage(session,binding)
    boundary=_boundary(session)
    if sealed is None:sealed=_seal_workspace(session)
    effects=dict(format=FORMAT,checkpoint=sealed['checkpoint'],
                 generation=deepcopy(sealed['workspace']['generation']),
                 export_published=False,receipt_persisted=False)
    try:
        try:
            after=query(session.vm)
            after_boundary=_boundary(session)
        except BaseException:
            session.close()
            raise
        if before!=after or after_boundary!=boundary:
            session.close()
            raise ValueError('Guest-create observer or stopped boundary changed during seal')
        generation=sealed['workspace']['generation']['artifact']
        store=WorkspaceStore(session)
        entry=_select_output(store,generation,binding['path'])
        payload=_proof_payload(dict(native=after))
        if binding.get('temporary_path') and any(e['dos_path']==binding['temporary_path']
                for e in store.load(generation)['entries']):
            raise ValueError('Temporary save still exists in the sealed generation')
        if entry['data']!=payload or entry['sha256']!=_sha(payload):
            raise ValueError('Sealed guest file differs from observed accepted DOS writes')
        checkpoint=session.project.db.execute('SELECT sha256 FROM debug_artifacts WHERE id=?',(sealed['checkpoint'],)).fetchone()
        if checkpoint is None:
            raise ValueError('Guest-create checkpoint receipt is missing')
        from .dos_save_operations import FORMAT as SAVE_FORMAT
        proof_format=SAVE_FORMAT if binding.get('mode')=='save' else FORMAT
        doc=dict(format=proof_format,path=binding['path'],source_sha256=session.metadata['source_sha256'],
                 version=session.version['id'],base_generation=binding['base_generation'],generation=generation,
                 payload_sha256=entry['sha256'],size=entry['size'],observer_token=binding['observer_token'],
                 native=after,binding=deepcopy(binding),boundary=boundary,
                 checkpoint=dict(artifact=sealed['checkpoint'],sha256=checkpoint['sha256']))
        validate_proof_document(doc)
        data=_json(doc);ref=session._artifact('workspace-guest-create.json',KIND,data,
            dict(format=proof_format,generation=generation,path=binding['path']))
        if ref['sha256']!=_sha(data):raise ValueError('Guest-create provenance receipt differs')
        return dict(**ref,format=proof_format,path=binding['path'],generation=generation,
                    payload_sha256=entry['sha256'],payload_size=entry['size'],guest_create_provenance=True)
    except BaseException as error:
        error.result=effects
        raise


def keep_proven(session,path,destination,generation,reference):
    store=WorkspaceStore(session)
    doc,payload=_stored_proof(session,reference)
    if (doc.get('path')!=_path(path) or doc.get('generation')!=generation
            or doc.get('source_sha256')!=session.metadata['source_sha256'] or doc.get('version')!=session.version['id']):
        raise ValueError('Guest-create provenance does not bind this source/path/generation')
    entry=_select_output(store,generation,doc['path'])
    if (entry['data']!=payload
            or entry['sha256']!=doc.get('payload_sha256') or entry['size']!=doc.get('size')):
        raise ValueError('Guest-create proof or file bytes differ')
    result=store.export_file(generation,doc['path'],destination)
    return dict(**result,guest_create_provenance=True,provenance=deepcopy(reference))


def service_policy(session,sealed):
    binding=getattr(session,'_dos_save_witness',None)
    if not binding or not binding.get('policy_id'):return None
    policy=KeepPolicyStore(session)
    current=policy.status(binding['policy_id'])
    if not current.get('enabled',True):return dict(status='disabled',policy=binding['policy_id'])
    info=query(session.vm)
    _bound(session,info)
    if binding.get('host_fault') or not info['valid'] or info['phase']!='ready':
        return dict(status='not-ready',native=_summary(info),policy=binding['policy_id'])
    proof=provenance(session,sealed)
    return policy.apply(binding['policy_id'],proof['generation'],dict(artifact=proof['artifact'],sha256=proof['sha256']))
