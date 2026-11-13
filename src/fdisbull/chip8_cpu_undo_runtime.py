"""Stopped CHIP-8 selected CPU/RAM projection and guarded inverse."""
from copy import deepcopy

from .chip8_layers import _chunks

REGISTERS = (*tuple(f'v{i:x}' for i in range(16)), 'i', 'pc')
SIZE = 4096
MAX = (1 << 64) - 1


def validate_registers(registers=None, *, allow_references=False):
    if registers is None:
        return list(REGISTERS)
    if allow_references and isinstance(registers,str) and registers.startswith('$'):
        return None
    if not isinstance(registers,list) or not registers or len(registers)>len(REGISTERS):
        raise ValueError('CHIP-8 undo requires selected registers')
    seen=set()
    for name in registers:
        if allow_references and isinstance(name,str) and name.startswith('$'):
            continue
        if not isinstance(name,str) or name not in REGISTERS or name in seen:
            raise ValueError('Invalid or duplicate CHIP-8 undo register')
        seen.add(name)
    return list(registers)


def validate_ranges(ranges, *, allow_references=False):
    reference=lambda v: allow_references and isinstance(v,str) and v.startswith('$')
    if reference(ranges): return None
    if not isinstance(ranges,list) or not 1<=len(ranges)<=64:
        raise ValueError('CHIP-8 undo requires 1..64 RAM ranges')
    result=[];intervals=[];total=0;unknown=False
    for item in ranges:
        if reference(item): unknown=True;continue
        if not isinstance(item,dict) or set(item)!={'address','length'}:
            raise ValueError('CHIP-8 undo range requires address and length')
        address=item['address'];length=item['length']
        if reference(address) or reference(length):
            unknown=True
            if not reference(length):
                if type(length) is not int or not 1<=length<=SIZE:
                    raise ValueError('CHIP-8 undo range length invalid')
                total+=length
            if not reference(address):
                try: address=int(address,0) if isinstance(address,str) else address
                except ValueError: raise ValueError('Invalid CHIP-8 undo address') from None
                if type(address) is not int or not 0<=address<SIZE:
                    raise ValueError('CHIP-8 undo address outside 4 KiB')
            continue
        try: address=int(address,0) if isinstance(address,str) else address
        except ValueError: raise ValueError('Invalid CHIP-8 undo address') from None
        if type(address) is not int or type(length) is not int or length<1 or address<0 or address+length>SIZE:
            raise ValueError('CHIP-8 undo range must fit 4 KiB')
        total+=length;intervals.append((address,address+length))
        result.append({'address':hex(address),'linear':hex(address),'length':length})
    intervals.sort()
    if total>SIZE or any(a[1]>b[0] for a,b in zip(intervals,intervals[1:])):
        raise ValueError('CHIP-8 undo ranges overlap or exceed 4 KiB')
    return None if unknown else result


def normalize_ranges(session, ranges):
    return validate_ranges(ranges)


def observe(session, ranges, registers):
    session._stopped(); session._chip8_frame_idle()
    layer = session._chip8_layer_query(); keys = session._chip8_keys_query()
    if layer['generation'] != session._layer_generation or not layer['backing-valid'] or layer['faulted']:
        raise ValueError('CHIP-8 fetch layer conflict prevents selected undo')
    snapshot = session.registers(); full_cpu = {k:int(v, 16) for k,v in snapshot['registers'].items()}
    ram = session._memory(0, SIZE)
    binding = dict(identity=deepcopy(session.identity), owner=session.vm.history_epoch,
                   layers=session._chip8_layer_state(),
                   fetch={k:layer[k] for k in ('execute-mask-hex','execute-bytes-hex','execute-base-hex')},
                   hooks=session._chip8_hook_state(),
                   keys={k:keys[k] for k in ('epoch','active','generation','accepted-edges','held-mask','key-mask')})
    return dict(cpu={name:full_cpu[name] for name in registers},
                ram=[ram[int(r['address'],0):int(r['address'],0)+r['length']] for r in ranges],
                binding=binding, register_snapshot=snapshot, all_cpu=full_cpu, all_ram=ram,
                environment=session.chip8_environment(), native_layer=layer)


def prepare(session, ranges, observed, target_cpu, target_ram):
    before=observed['all_ram']; after=bytearray(before)
    for region,data in zip(ranges,target_ram):
        address=int(region['address'],0)
        if not isinstance(data,bytes) or len(data)!=region['length']:
            raise ValueError('Invalid selected CHIP-8 target RAM')
        after[address:address+len(data)]=data
    if set(target_cpu)!=set(observed['cpu']) or any(type(v) is not int or not 0<=v<=(255 if k.startswith('v') else 65535) for k,v in target_cpu.items()):
        raise ValueError('Invalid selected CHIP-8 target registers')
    native=observed['native_layer'];env=observed['environment']
    edits={k:v for k,v in target_cpu.items() if v!=observed['cpu'][k]}
    if env['state-generation'] > MAX - (1 + len(edits)) or native['generation']==MAX:
        raise ValueError('CHIP-8 undo generation exhausted')
    writes={i:after[i] for i in range(SIZE) if before[i]!=after[i]}
    mask=bytes.fromhex(native['execute-mask-hex']); data=bytes.fromhex(native['execute-bytes-hex'])
    execute={i:data[i] for i in range(SIZE) if mask[i]}
    ram_chunks=_chunks(before,writes);execute_chunks=_chunks(after,execute)
    if len(ram_chunks)+len(execute_chunks)>256:
        raise ValueError('CHIP-8 undo native patch limit exceeded')
    return dict(observed=observed,ranges=ranges,target_cpu=target_cpu,target_ram=bytes(after),edits=edits,
                arguments={'expected-generation':native['generation'],
                           'expected-state-generation':env['state-generation'],
                           'ram':ram_chunks,'execute':execute_chunks})


def apply(session, plan):
    before=plan['observed']; native=before['native_layer']; args=plan['arguments']
    result=None
    try:
        result=session.vm.qmp.call('x-chip8-configure-layers',args)
        layer=session._chip8_layer_query()
        if result!=layer or layer['generation']!=native['generation']+1 or not layer['backing-valid'] or layer['faulted']:
            raise ValueError('CHIP-8 inverse layer transition differs')
        mask=bytes.fromhex(native['execute-mask-hex'])
        if (layer['execute-mask-hex']!=native['execute-mask-hex'] or
                layer['execute-bytes-hex']!=native['execute-bytes-hex'] or
                bytes.fromhex(layer['execute-base-hex'])!=bytes(plan['target_ram'][i] if mask[i] else 0 for i in range(SIZE))):
            raise ValueError('CHIP-8 inverse fetch view differs')
        session._layer_generation=layer['generation']
        if plan['edits']:
            session.write_registers({k:{'expected':before['all_cpu'][k],'value':v} for k,v in plan['edits'].items()})
        after_cpu={k:int(v,16) for k,v in session.registers()['registers'].items()}
        expected_cpu=dict(before['all_cpu'],**plan['edits'])
        after_ram=session._memory(0,SIZE)
        env=session.chip8_environment()
        if (env['state-generation'] != before['environment']['state-generation']+1+len(plan['edits']) or
                env['layer-generation'] != native['generation']+1):
            raise ValueError('CHIP-8 inverse generation readback differs')
        prior=dict(before['environment']); later=dict(env)
        for value in (prior,later):
            value.pop('state-generation',None);value.pop('layer-generation',None)
        if after_cpu!=expected_cpu or after_ram!=plan['target_ram'] or prior!=later:
            raise ValueError('CHIP-8 inverse changed an unselected CPU, RAM or device value')
        observed_after=observe(session,plan['ranges'],list(plan['target_cpu']))
        keys=session._chip8_keys_query()
        if keys['state-generation']!=env['state-generation']:
            raise ValueError('CHIP-8 key and CPU generation differ')
        old_binding=deepcopy(before['binding']);new_binding=deepcopy(observed_after['binding'])
        old_binding['layers']['generation']=new_binding['layers']['generation']
        old_binding['fetch']['execute-base-hex']=new_binding['fetch']['execute-base-hex']
        if old_binding!=new_binding:
            raise ValueError('CHIP-8 inverse changed layer, hook or key ownership')
        return dict(observation=observed_after,ram_transition=layer)
    except BaseException as error:
        error.result=dict(native_receipt=deepcopy(result),arguments=deepcopy(args),
                          cause_result=getattr(error,'result',None),
                          disposition='inverse outcome uncertain; do not replay')
        raise
