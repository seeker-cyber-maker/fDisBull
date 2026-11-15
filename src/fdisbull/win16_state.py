"""Hash-bound Win16 stopped-context checkpoint requalification."""
from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from .dosbox_rpc import DebuggerError
from .external_files import _file_name
from .wine_state import FORMAT, file_hash, get_state, sidecar


def _signature(value):
    return tuple(value[k] for k in ('selector', 'base', 'limit', 'present', 'default_big', 'type', 'dpl'))


def _address(value):
    if type(value) is int and value >= 0: return value
    if isinstance(value, str):
        try: return int(value, 0)
        except ValueError: pass
    raise ValueError('Invalid Win16 control address')


def _control_inventory(session, pending):
    if session.rpc.capabilities.get('control_inventory') is not True:
        raise ValueError('Win16 checkpoint requires guest control inventory')
    inventory = session.call('control-inventory')
    if not isinstance(inventory, dict) or inventory.get('format') != 'fdisbull-debug-controls-1':
        raise DebuggerError('Win16 guest control inventory unavailable')
    for key in ('breakpoints', 'watchpoints', 'overlays', 'pages', 'threads'):
        if not isinstance(inventory.get(key), list): raise DebuggerError('Win16 guest control inventory incomplete')
    if inventory.get('pending_event') != pending:
        raise DebuggerError('Win16 pending event and control inventory differ')
    for category, owned in (('breakpoints', session.breakpoints), ('watchpoints', session.watchpoints)):
        rows = inventory[category]
        if any(not isinstance(row, dict) or not isinstance(row.get('id'), str) for row in rows):
            raise DebuggerError('Invalid Win16 guest control entry')
        by_id = {row['id']:row for row in rows}
        if len(by_id) != len(rows) or set(by_id) != set(owned):
            raise DebuggerError('Win16 guest controls differ from owned controls')
        for key, control in owned.items():
            row = by_id[key]
            logical = control.get('address')
            if type(logical) is not int or logical < 0:
                raise DebuggerError('Invalid Win16 owned control identity')
            binding = session.bindings.get(logical >> 16)
            if (not isinstance(binding,dict) or control.get('binding_generation') != binding.get('generation')
                    or _address(control['runtime_address']) != binding['base'] + (logical & 65535)):
                raise DebuggerError('Win16 owned control source binding changed')
            if _address(row.get('address')) != _address(control['runtime_address']):
                raise DebuggerError('Win16 guest control address differs')
            if category == 'watchpoints' and (row.get('length') != control['length'] or row.get('access') != control['access']):
                raise DebuggerError('Win16 guest watchpoint differs')
            if category == 'breakpoints' and (type(row.get('armed')) is not bool or
                    not isinstance(row.get('original_hex'), str) or re.fullmatch('[0-9a-f]{2}',row['original_hex']) is None):
                raise DebuggerError('Win16 guest breakpoint state incomplete')
    for row in inventory['overlays']:
        if not isinstance(row,dict) or type(row.get('index')) is not int or type(row.get('length')) is not int or row['length'] <= 0:
            raise DebuggerError('Invalid Win16 execution overlay')
        _address(row.get('address'))
    for row in inventory['pages']:
        if not isinstance(row,dict) or type(row.get('protection')) is not int or type(row.get('armed')) is not bool:
            raise DebuggerError('Invalid Win16 watched page')
        _address(row.get('address'))
    for row in inventory['threads']:
        if not isinstance(row,dict) or type(row.get('id')) is not int or type(row.get('suspended')) is not bool:
            raise DebuggerError('Invalid Win16 tracked thread')
    for key, field in (('overlays','index'),('pages','address'),('threads','id')):
        identities = [row[field] for row in inventory[key]]
        if len(set(identities)) != len(identities):
            raise DebuggerError('Duplicate Win16 guest control identity')
    normalized = deepcopy(inventory)
    for key in ('breakpoints', 'watchpoints', 'overlays', 'pages', 'threads'):
        normalized[key].sort(key=lambda row:json.dumps(row, sort_keys=True, separators=(',', ':')))
    return normalized


def checkpoint_observation(session):
    """Capture stopped task, LDT and current bytes; never run or bind from original bytes."""
    if session.rpc.capabilities.get('context_diagnostics') is not True:
        raise ValueError('Win16 checkpoint requires pending debug-event diagnostics')
    task = deepcopy(session.metadata.get('task_identity'))
    if not isinstance(task, dict) or not task.get('epoch') or not session.bindings:
        raise ValueError('Win16 checkpoint requires an already qualified source-bound task')
    if hashlib.sha256(session.source).hexdigest() != session.metadata.get('source_sha256'):
        raise DebuggerError('Win16 retained source identity differs')
    status = session.call('status')
    diagnostics = session.call('context-diagnostics')
    pending = diagnostics.get('pending_event', {})
    fields = ('pending', 'event', 'process', 'thread', 'target_bits', 'state_revision',
              'module_revision', 'continuation', 'stepping_thread', 'breakpoint_hit', 'guard_pending')
    if (status.get('state') != 'stopped' or pending.get('pending') is not True
            or any(field not in pending for field in fields)
            or pending['target_bits'] != 32 or not pending['thread'] or not pending['process']
            or pending['thread'] != status.get('stop_reason', {}).get('thread')
            or pending['state_revision'] != status.get('state_revision')):
        raise DebuggerError('Win16 checkpoint requires an unambiguous stopped pending event')
    inventory = _control_inventory(session, {k:pending[k] for k in fields})
    if session.metadata.get('target_pid') is not None and pending['process'] != session.metadata['target_pid']:
        raise DebuggerError('Win16 checkpoint process identity differs')
    regs = session.call('registers')
    required = ('thread', 'context_source', 'cs', 'ds', 'ss', 'es', 'fs', 'gs', 'eip', 'eflags', 'general')
    if any(name not in regs for name in required) or regs['thread'] != pending['thread']:
        raise DebuggerError('Win16 checkpoint register context is incomplete')
    if regs['context_source'] != 'native-ldt-low32':
        raise DebuggerError('Win16 checkpoint requires the native-qualified 16-bit context')
    register_selectors = {}
    for name in ('cs','ds','ss','es','fs','gs'):
        selector = _address(regs[name])
        if selector & 4:
            descriptor = session._selector(selector)
            register_selectors[name] = list(_signature(descriptor))
    modules = session.call('modules')
    if modules.get('module_revision') != pending['module_revision']:
        raise DebuggerError('Win16 checkpoint module revision differs from pending event')
    if not any(m.get('bits') == 32 and int(str(m['base']), 0) == int(str(task['loader_module_base']), 0)
               and m.get('generation') == task['loader_module_generation'] for m in modules.get('modules', [])):
        raise DebuggerError('Win16 checkpoint loader generation mismatch')
    psp = session._selector(task['psp_selector'])
    if _signature(psp) != _signature(task['psp_descriptor']):
        raise DebuggerError('Win16 checkpoint task selector mismatch')
    segments = {}
    for index, binding in session.bindings.items():
        if (binding['segment_index'] != index or binding['task_epoch'] != task['epoch']
                or binding['source_sha256'] != session.metadata['source_sha256']):
            raise DebuggerError('Win16 checkpoint binding identity mismatch')
        segment = session._segments[index]
        source = session.source[segment['file_offset']:segment['file_offset']+segment['file_size']]
        if hashlib.sha256(source).hexdigest() != binding['source_segment_sha256']:
            raise DebuggerError('Win16 checkpoint source segment mismatch')
        current = session._selector(binding['selector'])
        if _signature(current) != _signature(binding['descriptor']):
            raise DebuggerError('Win16 checkpoint selector changed')
        size = segment['allocation_size']
        if type(size) is not int or not 0 < size <= 65536 or size > current['limit'] + 1:
            raise DebuggerError('Win16 checkpoint segment extent invalid')
        data = session._read_runtime(current['base'], size)
        if len(data) != size: raise DebuggerError('Win16 checkpoint memory incomplete')
        if _signature(session._selector(binding['selector'])) != _signature(current):
            raise DebuggerError('Win16 checkpoint selector changed during read')
        segments[str(index)] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': size}
    if _signature(session._selector(task['psp_selector'])) != _signature(psp):
        raise DebuggerError('Win16 checkpoint task changed during read')
    for name, signature in register_selectors.items():
        if list(_signature(session._selector(_address(regs[name])))) != signature:
            raise DebuggerError('Win16 register selector changed during checkpoint observation')
    if session.call('status') != status or _control_inventory(session, {k:pending[k] for k in fields}) != inventory:
        raise DebuggerError('Win16 stopped control state changed during checkpoint observation')
    return {'schema':'fdisbull-win16-checkpoint-context-1', 'source_sha256':session.metadata['source_sha256'],
            'status':status, 'pending':{k:pending[k] for k in fields},
            'registers':{k:deepcopy(regs[k]) for k in required}, 'register_selectors':register_selectors, 'task':task,
            'bindings':{str(k):deepcopy(v) for k,v in session.bindings.items()},
            'binding_epoch':session._binding_epoch, 'segments':segments, 'controls':inventory,
            'breakpoints':deepcopy(session.breakpoints), 'watchpoints':deepcopy(session.watchpoints),
            'loader_ds_selector':getattr(session,'_loader_ds_selector',None),
            'edits':{str(k):v for k,v in session._edits.items()}}


def requalify(session, saved):
    if not isinstance(saved, dict) or saved.get('schema') != 'fdisbull-win16-checkpoint-context-1':
        raise ValueError('Invalid Win16 checkpoint context')
    if saved.get('source_sha256') != session.metadata.get('source_sha256'):
        raise ValueError('Win16 checkpoint source mismatch')
    previous = (session.bindings, session._edits, session._binding_epoch, session.metadata.get('task_identity'),
                session.breakpoints, session.watchpoints, getattr(session,'_loader_ds_selector',None))
    try:
        session.bindings = {int(k):deepcopy(v) for k,v in saved['bindings'].items()}
        session._edits = {int(k):v for k,v in saved['edits'].items()}
        session._binding_epoch = saved['binding_epoch']
        session.metadata['task_identity'] = deepcopy(saved['task'])
        session.breakpoints = deepcopy(saved['breakpoints']); session.watchpoints = deepcopy(saved['watchpoints'])
        session._loader_ds_selector = saved['loader_ds_selector']
        observed = checkpoint_observation(session)
        if observed != saved:
            raise DebuggerError('Win16 restored task, controls, registers or segment bytes differ from checkpoint')
    except BaseException:
        session.bindings, session._edits, session._binding_epoch, task, session.breakpoints, session.watchpoints, session._loader_ds_selector = previous
        if task is None: session.metadata.pop('task_identity', None)
        else: session.metadata['task_identity'] = task
        raise
    return observed


def _program_inputs(session):
    from .guest_assets import uploads
    names = [item['path'] for item in session.metadata['files']]
    staged = uploads(session.project, session.game_dir, session.target, names)
    return [{'path':item['path'], 'sha256':item['sha256']} for item in staged]


def _verify_inputs(session, metadata):
    if (metadata.get('backend') != 'wine-ne-qemu' or metadata.get('runtime_profile') != 'wine11-ne-selector-1'
            or metadata.get('source_sha256') != session.project.meta['source_sha256']
            or metadata.get('version_sha256') != session.version['sha256']):
        raise ValueError('Win16 checkpoint source or runtime profile mismatch')
    if _program_inputs(session) != metadata.get('files'):
        raise ValueError('Win16 checkpoint program inputs changed')
    if session.metadata['files'] != metadata['files']:
        raise ValueError('Win16 checkpoint program input identity mismatch')
    for name in ('qemu', 'kernel', 'initramfs'):
        current = session.rpc.inputs[name]
        if (current['sha256'] != metadata['runtime_inputs'][name]['sha256']
                or file_hash(current['path']) != current['sha256']):
            raise ValueError('Win16 checkpoint backend identity mismatch: ' + name)


def save_state(session, name='checkpoint.sav', *, max_bytes=None):
    _file_name(name)
    if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= 2*1024**3):
        raise ValueError('Win16 native state max_bytes must be 1..2 GiB')
    with session.rpc.lock:
        _verify_inputs(session, session.metadata)
        if session.rpc.capabilities.get('keyboard'):
            keys = session.call('keyboard-state')
            if keys.get('pending') or keys.get('held'):
                raise ValueError('Win16 checkpoint requires released keys and an empty input queue')
        observed = checkpoint_observation(session)
        directory = sidecar(session.project)
        if shutil.disk_usage(directory).free < 2*1024**3:
            raise ValueError('Native VM capture requires at least 2 GiB of free space')
        if sum(p.stat().st_size for p in directory.glob('*.mig.gz')) > 6*1024**3:
            raise ValueError('Project native checkpoints exceed 6 GiB budget')
        try:
            with tempfile.TemporaryDirectory(prefix='.capture-', dir=directory) as temporary:
                path = Path(temporary) / 'machine.mig.gz'
                capture = session.rpc.capture(path)
                size = path.stat().st_size
                if not 0 < size <= 2*1024**3:
                    raise ValueError('Native checkpoint exceeds 2 GiB compressed budget')
                if sum(p.stat().st_size for p in directory.glob('*.mig.gz')) + size > 6*1024**3:
                    raise ValueError('Project native checkpoint budget exceeds 6 GiB')
                expanded = 0
                with gzip.open(path, 'rb') as stream:
                    while chunk := stream.read(8*1024**2):
                        expanded += len(chunk)
                        if expanded > 8*1024**3: raise ValueError('Native checkpoint exceeds expanded budget')
                if checkpoint_observation(session) != observed:
                    raise DebuggerError('Win16 stopped context changed during checkpoint capture')
                digest = file_hash(path)
                metadata = {**deepcopy(session.metadata), 'format':FORMAT, 'native_sha256':digest,
                            'native_size':size, 'storage':'private-project-sidecar', 'capture':capture,
                            'target_paused':True, 'host_files_restored':False}
                document = {'format':FORMAT, 'machine_sha256':digest, 'machine_size':size,
                            'metadata':metadata, 'host':{'win16_context':observed}}
                data = json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
                if max_bytes is not None and size + len(data) > max_bytes:
                    raise ValueError('Win16 native state exceeds remaining byte budget')
                dest = directory / (digest + '.mig.gz')
                if dest.is_symlink(): raise ValueError('Native sidecar cannot be a symbolic link')
                if dest.exists():
                    if not dest.is_file() or file_hash(dest) != digest: raise ValueError('Existing native sidecar hash mismatch')
                else:
                    path.replace(dest); dest.chmod(0o400)
            result = session._artifact(name, 'state', data, metadata)
            result['native_size'] = size
            return result
        except BaseException:
            session.close()
            raise


def load_state(session, artifact):
    with session.rpc.lock:
        row, document, path = get_state(session.project, artifact, session.version['id'])
        metadata = document['metadata']
        _verify_inputs(session, metadata)
        context = document['host'].get('win16_context')
        if not isinstance(context, dict): raise ValueError('Win16 checkpoint context missing')
        options = [session.rpc.inputs[n]['path'] for n in ('qemu', 'kernel', 'initramfs')]
        session.rpc.close()
        try:
            replacement = session.rpc_type(*options, restore=path, memory_mib=metadata.get('memory_mib',4096))
            session.rpc = replacement
            _verify_inputs(session, metadata)
            if any(replacement.inputs[n]['sha256'] != metadata['runtime_inputs'][n]['sha256'] for n in ('qemu','kernel','initramfs')):
                raise ValueError('Win16 checkpoint restored backend identity mismatch')
            requalify(session, context)
            replacement.capabilities.update(backend=session.backend_name, architecture='x86', bits=16,
                carrier_bits=32, source_bound_ne_selectors=True, save_states=True, code_layers=False,
                native_hooks=False, register_edit=session.register_edits_available,
                register_context=session.register_context_contract)
            session.metadata['task_identity'] = deepcopy(context['task'])
            session.metadata['selector_bindings'] = list(deepcopy(session.bindings).values())
            session.metadata['runtime_inputs'] = replacement.inputs
            session.metadata['qemu_pid'] = replacement.process.pid
            session.metadata['restored_from'] = artifact
            session._frame = None
            session.mode_id += 1
            session._windows_invalidate_input_leases()
            result = {'artifact':artifact, 'sha256':row['sha256'], 'state':'stopped',
                      'registers':deepcopy(context['registers']), 'native_size':document['machine_size'],
                      'source_selector_requalified':True, 'target_execution_during_requalification':False}
            with session.project.transaction(True):
                session.project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?', (json.dumps(session.metadata),session.run_id))
            session._event('load-state', result)
            return result
        except BaseException:
            session.close()
            raise
