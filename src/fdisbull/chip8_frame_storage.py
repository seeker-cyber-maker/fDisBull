"""Immutable, lossless renderer-history checkpoint payload storage."""
from copy import deepcopy
import hashlib
import json

from . import frame_state_codec as codec
from .qemu_dos_history import MAX_NODES, MAX_STATE

FORMAT = 'fdisbull-qemu-chip8-frames-v3'
REF_FORMAT = 'fdisbull-chip8-frame-state-1'
DELTA_KIND = 'chip8-frame-state-delta'


def _encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _hex(value):
    return isinstance(value,str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def _deadline(session):
    session._history_remaining_ms()


def stored_size(cp):
    storage = cp.get('storage') if isinstance(cp,dict) else None
    if (not isinstance(storage,dict) or not _integer(storage.get('payload_size'),1,MAX_STATE)
            or not _integer(storage.get('metadata_size'),2,16*1024**2)):
        raise ValueError('Invalid renderer checkpoint retained size')
    return storage['payload_size'] + storage['metadata_size']


def validate_manifest(manifest):
    if (not isinstance(manifest,dict) or manifest.get('format') != FORMAT
            or manifest.get('history_kind') != 'chip8-60hz-samples'
            or not isinstance(manifest.get('id'),str) or not 1 <= len(manifest['id']) <= 128
            or not isinstance(manifest.get('identity'),dict)
            or not _integer(manifest.get('revision'),0,(1 << 63)-1)
            or not isinstance(manifest.get('parent_manifest'),(str,type(None)))
            or not isinstance(manifest.get('pending'),(dict,type(None)))
            or not isinstance(manifest.get('nodes'),list) or len(manifest['nodes']) > MAX_NODES
            or not _integer(manifest.get('max_steps'),1,MAX_NODES)
            or not _integer(manifest.get('max_bytes'),1,1024**3)
            or len(manifest['nodes']) > manifest['max_steps']):
        raise ValueError('Invalid renderer delta history manifest')
    config = manifest.get('frame_config')
    if (not isinstance(config,dict) or config.get('storage_mode') != 'delta'
            or not _integer(config.get('keyframe_interval'),1,MAX_NODES)
            or not _integer(config.get('max_state_bytes'),1,MAX_STATE)
            or not _integer(config.get('max_image_bytes'),1,16*1024**2)
            or not _integer(config.get('max_frames'),1,MAX_NODES)
            or not _integer(config.get('max_captures'),1,MAX_NODES)
            or config.get('max_bytes') != manifest['max_bytes']
            or config.get('period_ns') != 16666667
            or manifest['max_steps'] != min(config['max_frames'],config['max_captures'],MAX_NODES)):
        raise ValueError('Invalid renderer delta storage configuration')
    def ident(value):return isinstance(value,str) and len(value)==32 and all(c in '0123456789abcdef' for c in value)
    if (not ident(manifest['id']) or manifest['revision']<1 or
            manifest['revision']==1 and manifest['parent_manifest'] is not None or
            manifest['revision']>1 and not ident(manifest['parent_manifest'])):
        raise ValueError('Invalid CHIP-8 delta history revision')
    nodes, used = {},0
    for node in manifest['nodes']:
        if (not isinstance(node,dict) or not isinstance(node.get('id'),str)
                or not ident(node['id']) or node['id'] in nodes
                or node.get('parent') not in set(nodes) | {None}
                or nodes and node.get('parent') is None or not isinstance(node.get('edge'),dict)):
            raise ValueError('Invalid renderer delta DAG lineage')
        cp = node.get('checkpoint')
        if (not isinstance(cp,dict) or not ident(cp.get('artifact'))
                or not _hex(cp.get('sha256')) or not _hex(cp.get('metadata_sha256')) or not _integer(cp.get('size'),1,config['max_state_bytes'])):
            raise ValueError('Invalid renderer delta checkpoint identity')
        optional = {'live_disk_bytes_before','live_disk_bytes_after','live_disk_bytes_growth'}
        if (set(cp) - ({'artifact','sha256','size','storage','metadata_sha256'} | optional)
                or any(cp[key] is not None and not _integer(cp[key],0,(1 << 63)-1)
                       for key in optional if key in cp)):
            raise ValueError('Invalid renderer live disk accounting')
        storage = cp.get('storage')
        if (not isinstance(storage,dict) or storage.get('kind') not in ('full','delta')
                or not _hex(storage.get('payload_sha256')) or not _hex(storage.get('metadata_sha256'))
                or not _integer(storage.get('depth'),0,config['keyframe_interval']-1)):
            raise ValueError('Invalid renderer checkpoint storage descriptor')
        used += stored_size(cp)
        if storage['kind'] == 'full':
            if (set(storage) != {'kind','depth','payload_size','payload_sha256','metadata_sha256','metadata_size'}
                    or storage['depth'] != 0 or storage['payload_size'] != cp['size']
                    or storage['payload_sha256'] != cp['sha256']):
                raise ValueError('Invalid full renderer checkpoint descriptor')
        else:
            if set(storage) != {'kind','depth','payload_size','payload_sha256','metadata_sha256','metadata_size','descriptor'}:
                raise ValueError('Invalid renderer delta descriptor fields')
            desc = storage['descriptor']
            parent = nodes.get(node.get('parent'))
            if (parent is None or not isinstance(desc,dict) or set(desc) != codec.FIELDS - {'payload'}
                    or desc.get('format') != codec.FORMAT
                    or not _hex(desc.get('descriptor_sha256'))
                    or _digest(_encoded({k:v for k,v in desc.items() if k != 'descriptor_sha256'})) != desc['descriptor_sha256']
                    or storage['payload_size'] > 16*1024**2
                    or desc.get('base_point') != parent['id']
                    or desc.get('base_sha256') != parent['checkpoint']['sha256']
                    or desc.get('base_size') != parent['checkpoint']['size']
                    or desc.get('result_sha256') != cp['sha256'] or desc.get('result_size') != cp['size']
                    or desc.get('depth') != parent['checkpoint']['storage']['depth'] + 1
                    or storage['depth'] != desc['depth'] or desc.get('payload_sha256') != storage['payload_sha256']):
                raise ValueError('Renderer delta parent identity or depth differs')
        frame = node.get('frame')
        if (not isinstance(frame,dict) or frame.get('completed_guest_frame') is not None
                or frame.get('kind') != ('initial-paused' if node.get('parent') is None else 'native-60hz-sample')):
            raise ValueError('Invalid CHIP-8 sample scope')
        keys=frame.get('keys')
        if not isinstance(keys,list) or any(not isinstance(k,str) or len(k)!=1 or k not in '0123456789abcdef' for k in keys) or keys!=sorted(set(keys)):
            raise ValueError('Invalid CHIP-8 frame keys')
        if frame['kind']=='native-60hz-sample':
            for field in ('virtual_ticks','sampled_ns','stopped_ns','phase_numerator','next_deadline_ns','state_generation','frame_generation','baseline_deadline_ns','baseline_phase'):
                if not _integer(frame.get(field),0,(1<<64)-1):raise ValueError('Invalid CHIP-8 sample timing')
            phase=frame['baseline_phase']
            if (phase>=60 or frame['phase_numerator']!=(phase-20 if phase>=20 else phase+40)
                    or frame['next_deadline_ns']!=frame['baseline_deadline_ns']+(16666667 if phase>=20 else 16666666)
                    or frame['sampled_ns']<frame['baseline_deadline_ns'] or frame['stopped_ns']<frame['sampled_ns']
                    or frame['virtual_ticks']<1 or not _hex(frame.get('pixels_sha256'))):
                raise ValueError('Invalid CHIP-8 sample recurrence')
        image = frame.get('image')
        if (not isinstance(image,dict) or not isinstance(image.get('artifact'),str) or not image['artifact']
                or not _hex(image.get('sha256')) or not _integer(image.get('size'),1,config['max_image_bytes'])):
            raise ValueError('Invalid renderer screenshot reference')
        used += image['size']
        nodes[node['id']] = node
    for key in ('head','cursor'):
        if manifest.get(key) is not None and manifest[key] not in nodes:
            raise ValueError('Renderer history cursor does not name a node')
    journal = manifest.get('input_journal',[])
    pending=manifest.get('pending_inputs')
    if (not isinstance(journal,list) or len(journal)>1024 or not isinstance(pending,list) or
            type(manifest.get('input_dirty')) is not bool or len(pending)>len(journal) or
            pending and pending!=journal[-len(pending):] or manifest['input_dirty']!=bool(pending)):
        raise ValueError('Invalid CHIP-8 input journal')
    used += len(_encoded(journal))
    if used > manifest['max_bytes']:
        raise ValueError('Renderer history exceeds its retained byte budget')
    return used


def _row(session, cp, expected_kind):
    row = session.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(cp['artifact'],)).fetchone()
    if row is None or row['version'] != session.version['id'] or row['kind'] != expected_kind:
        raise ValueError('Renderer checkpoint artifact is missing or belongs to another version')
    storage = cp['storage']
    data = bytes(row['data'])
    try: metadata = json.loads(row['metadata'])
    except (TypeError,ValueError) as error: raise ValueError('Invalid renderer checkpoint metadata') from error
    encoded = _encoded(metadata)
    if (row['sha256'] != storage['payload_sha256'] or len(data) != storage['payload_size']
            or _digest(data) != storage['payload_sha256'] or len(encoded) != storage['metadata_size']
            or _digest(encoded) != storage['metadata_sha256']):
        raise ValueError('Renderer checkpoint payload or metadata hash mismatch')
    return data, metadata


def _full_metadata(session, metadata):
    from .chip8_keys import validate_key_snapshot
    if (not isinstance(metadata,dict) or metadata.get('format')!='fdisbull-qemu-chip8-state-6'
            or metadata.get('identity')!=session.identity or metadata.get('host_files_restored') is not False):
        raise ValueError('CHIP-8 checkpoint identity or scope differs')
    from .qemu_chip8 import _validate_environment
    from .dosbox_rpc import DebuggerError
    try:environment=_validate_environment(metadata.get('environment'))
    except DebuggerError as error:raise ValueError('Invalid CHIP-8 checkpoint environment') from error
    if environment['cpu-subset']!=session.identity['cpu_subset']:
        raise ValueError('CHIP-8 checkpoint environment identity differs')
    validate_key_snapshot(metadata.get('key_state'),environment)


def materialize(session, manifest, node):
    validate_manifest(manifest)
    nodes = {item['id']:item for item in manifest['nodes']}
    if not isinstance(node,dict) or node.get('id') not in nodes or nodes[node['id']] != node:
        raise ValueError('Renderer checkpoint node is not in this history')
    chain = []
    current = node
    while True:
        _deadline(session)
        cp = current['checkpoint']; storage = cp['storage']
        if storage['kind'] == 'full':
            data, metadata = _row(session,cp,'state')
            _full_metadata(session,metadata)
            if _digest(_encoded(metadata))!=cp['metadata_sha256']:raise ValueError('CHIP-8 full metadata identity differs')
            if len(data) != cp['size'] or _digest(data) != cp['sha256']:
                raise ValueError('Full renderer checkpoint differs from its identity')
            break
        if len(chain) >= manifest['frame_config']['keyframe_interval']-1:
            raise ValueError('Renderer checkpoint delta chain exceeds its bound')
        payload, wrapper = _row(session,cp,DELTA_KIND)
        if (not isinstance(wrapper,dict) or set(wrapper) != {'format','history_id','node_id','full_metadata','descriptor'}
                or wrapper['format'] != REF_FORMAT or wrapper['history_id'] != manifest['id']
                or wrapper['node_id'] != current['id'] or wrapper['descriptor'] != storage['descriptor']):
            raise ValueError('Renderer delta artifact binding differs')
        _full_metadata(session,wrapper['full_metadata'])
        if _digest(_encoded(wrapper['full_metadata']))!=cp['metadata_sha256']:raise ValueError('CHIP-8 delta metadata identity differs')
        delta = dict(wrapper['descriptor'],payload=payload)
        codec.validate(delta,result_sha256=cp['sha256'],result_size=cp['size'],
                       max_bytes=manifest['frame_config']['max_state_bytes'],
                       max_depth=manifest['frame_config']['keyframe_interval']-1)
        chain.append((current,delta,wrapper['full_metadata']))
        current = nodes[current['parent']]
    for item, delta, metadata in reversed(chain):
        _deadline(session)
        data = codec.decode(data,delta,max_bytes=manifest['frame_config']['max_state_bytes'],
                            max_depth=manifest['frame_config']['keyframe_interval']-1)
    _deadline(session)
    return dict(data=data,metadata=deepcopy(metadata),sha256=node['checkpoint']['sha256'],
                size=node['checkpoint']['size'],artifact=node['checkpoint']['artifact'])


def store(session, manifest, node_id, parent, captured, *, reserve_bytes=0):
    _deadline(session)
    if not _integer(reserve_bytes,0,1024**3):
        raise ValueError('Renderer checkpoint reserve must be a nonnegative bounded integer')
    if (not isinstance(captured,dict) or captured.get('kind') != 'state'
            or not isinstance(captured.get('name'),str) or not isinstance(captured.get('data'),bytes)
            or captured.get('size') != len(captured['data']) or captured.get('sha256') != _digest(captured['data'])
            or not _integer(captured['size'],1,manifest['frame_config']['max_state_bytes'])
            or not isinstance(node_id,str) or not 1 <= len(node_id) <= 128):
        raise ValueError('Invalid captured renderer checkpoint')
    _full_metadata(session,captured.get('metadata'))
    used = validate_manifest(manifest)
    if any(node['id'] == node_id for node in manifest['nodes']):
        raise ValueError('Renderer history node ID already exists')
    if (parent is None) != (not manifest['nodes']):
        raise ValueError('Renderer checkpoint parent does not identify this history')
    data = captured['data']; metadata = deepcopy(captured['metadata']); kind = 'state'; depth = 0; descriptor = None
    if parent is not None:
        base = materialize(session,manifest,parent)
        depth = parent['checkpoint']['storage']['depth'] + 1
        if depth < manifest['frame_config']['keyframe_interval']:
            delta = codec.encode(base['data'],data,base_point=parent['id'],depth=depth)
            _deadline(session)
            if delta is not None:
                descriptor = codec.descriptor(delta)
                wrapper = dict(format=REF_FORMAT,history_id=manifest['id'],node_id=node_id,
                               full_metadata=metadata,descriptor=descriptor)
                if len(delta['payload']) <= 16*1024**2 and len(delta['payload']) + len(_encoded(wrapper)) < len(data) + len(_encoded(metadata)):
                    data,metadata,kind = delta['payload'],wrapper,DELTA_KIND
                else: descriptor = None
    if descriptor is None: depth = 0
    _deadline(session)
    if used + len(data) + len(_encoded(metadata)) + reserve_bytes > manifest['max_bytes']:
        raise ValueError('Renderer history checkpoint and reserved image exceed the retained byte budget')
    artifact = session._artifact(captured['name'],kind,data,metadata)
    storage = dict(kind='delta' if descriptor is not None else 'full',depth=depth,
                   payload_size=len(data),payload_sha256=_digest(data),
                   metadata_size=len(_encoded(metadata)),metadata_sha256=_digest(_encoded(metadata)))
    if descriptor is not None: storage['descriptor'] = descriptor
    if (not isinstance(artifact,dict) or not isinstance(artifact.get('artifact'),str)
            or not artifact['artifact'] or artifact.get('sha256') != storage['payload_sha256']
            or artifact.get('size') != len(data)):
        raise ValueError('Renderer stored artifact receipt differs from payload')
    return dict(artifact=artifact['artifact'],sha256=captured['sha256'],size=captured['size'],
                metadata_sha256=_digest(_encoded(captured['metadata'])),storage=storage)


def validate_index(session,manifest):
    """Validate every retained row identity/metadata without decoding each chain."""
    validate_manifest(manifest)
    for node in manifest['nodes']:
        cp=node['checkpoint'];storage=cp['storage']
        row=session.project.db.execute('SELECT a.kind,a.sha256,a.metadata,fdb_length(a.data) AS size,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(cp['artifact'],)).fetchone()
        expected='state' if storage['kind']=='full' else DELTA_KIND
        if (row is None or row['kind']!=expected or row['version']!=session.version['id'] or
                row['sha256']!=storage['payload_sha256'] or row['size']!=storage['payload_size']):
            raise ValueError('CHIP-8 frame checkpoint index differs')
        try:metadata=json.loads(row['metadata'])
        except (TypeError,ValueError) as error:raise ValueError('Invalid CHIP-8 frame checkpoint metadata') from error
        encoded=_encoded(metadata)
        if len(encoded)!=storage['metadata_size'] or _digest(encoded)!=storage['metadata_sha256']:
            raise ValueError('CHIP-8 frame stored metadata hash differs')
        if storage['kind']=='delta':
            if (set(metadata)!={'format','history_id','node_id','full_metadata','descriptor'} or
                    metadata['format']!=REF_FORMAT or metadata['history_id']!=manifest['id'] or
                    metadata['node_id']!=node['id'] or metadata['descriptor']!=storage['descriptor']):
                raise ValueError('CHIP-8 delta wrapper binding differs')
            metadata=metadata['full_metadata']
        _full_metadata(session,metadata)
        if _digest(_encoded(metadata))!=cp['metadata_sha256']:
            raise ValueError('CHIP-8 checkpoint full metadata hash differs')
