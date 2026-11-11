"""Immutable, lossless renderer-history checkpoint payload storage."""
from copy import deepcopy
import hashlib
import json

from . import frame_state_codec as codec
from .qemu_dos_history import MAX_NODES, MAX_STATE

FORMAT = 'fdisbull-qemu-renderer-history-2'
REF_FORMAT = 'fdisbull-qemu-frame-state-1'
DELTA_KIND = 'qemu-frame-state-delta'


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
            or manifest.get('history_kind') != 'renderer-frames'
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
            or not _integer(config.get('period_ns'),1_000_000,1_000_000_000)
            or manifest['max_steps'] != min(config['max_frames'],config['max_captures'],MAX_NODES)):
        raise ValueError('Invalid renderer delta storage configuration')
    nodes, used = {},0
    for node in manifest['nodes']:
        if (not isinstance(node,dict) or not isinstance(node.get('id'),str)
                or not 1 <= len(node['id']) <= 128 or node['id'] in nodes
                or node.get('parent') not in set(nodes) | {None}
                or nodes and node.get('parent') is None or not isinstance(node.get('edge'),dict)):
            raise ValueError('Invalid renderer delta DAG lineage')
        cp = node.get('checkpoint')
        if (not isinstance(cp,dict) or not isinstance(cp.get('artifact'),str) or not cp['artifact']
                or not _hex(cp.get('sha256')) or not _integer(cp.get('size'),1,config['max_state_bytes'])):
            raise ValueError('Invalid renderer delta checkpoint identity')
        optional = {'live_disk_bytes_before','live_disk_bytes_after','live_disk_bytes_growth'}
        if (set(cp) - ({'artifact','sha256','size','storage'} | optional)
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
                or frame.get('kind') != ('initial-paused' if node.get('parent') is None else 'renderer-update')):
            raise ValueError('Invalid renderer publication scope')
        if frame['kind'] == 'renderer-update' and (
                not _integer(frame.get('width'),1,8192) or not _integer(frame.get('height'),1,8192)
                or frame['width'] * frame['height'] * 3 > 16*1024**2
                or not _integer(frame.get('update_id'),1,(1 << 64)-1)
                or not _integer(frame.get('published_ns'),0,(1 << 63)-1)
                or not _hex(frame.get('pixel_sha256'))):
            raise ValueError('Invalid renderer publication identity')
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
    if not isinstance(journal,list) or len(journal) > 1024:
        raise ValueError('Invalid renderer input journal')
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
    from .qemu_dos_checkpoint import FORMAT as PROCESS_FORMAT
    if (not isinstance(metadata,dict) or metadata.get('format') != PROCESS_FORMAT
            or metadata.get('host_files_restored') is not False
            or metadata.get('source_sha256') != session.metadata['source_sha256']
            or metadata.get('version_sha256') != session.metadata['version_sha256']):
        raise ValueError('Renderer checkpoint source, version or scope differs')


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
    return dict(artifact=artifact['artifact'],sha256=captured['sha256'],size=captured['size'],storage=storage)
