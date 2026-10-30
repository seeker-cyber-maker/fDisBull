"""Explicit, bounded native x86-16 block execution with declarative adapters.

This is a CPU provider, not a DOS/Win16 process or an automatic semantic lift.
Only caller-declared inputs, outputs and scratch state are exposed to a block.
"""
from __future__ import annotations

import hashlib

_REGS = ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp', 'ds', 'es', 'ss')
_TYPES = {'u8': (1, False), 'i8': (1, True), 'u16': (2, False), 'i16': (2, True), 'bool': (1, False)}


class NativeBlockError(ValueError):
    pass


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise NativeBlockError(f'{label} must be an integer in {low}..{high}')
    return value


def _range_contains(ranges, address, size):
    return any(start <= address and address + size <= end for start, end in ranges)


def _merged_ranges(ranges):
    result = []
    for start, end in sorted(ranges):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def _overlaps(ranges, address, size):
    return any(start < address + size and address < end for start, end in ranges)


def execute_native16(code, implementation, adapter, inputs, input_types, output_types, *, max_steps=10000, caller_registers=None):
    """Run actual retained instructions in an isolated CPU, then restore its ABI.

    Segment-region allocation is realization metadata, never a UIL address.
    Native registers and flags before restoration are retained in the receipt.
    """
    if not isinstance(code, bytes) or not 1 <= len(code) <= 65536:
        raise NativeBlockError('native16 code must contain 1..65536 bytes')
    _integer(max_steps, 1, 100000, 'instruction budget')
    if not isinstance(implementation, dict) or not isinstance(adapter, dict):
        raise NativeBlockError('native16 requires implementation and adapter objects')
    origin = _integer(implementation.get('origin', 0x1000), 0, 65535, 'code origin')
    if origin + len(code) > 65535:
        raise NativeBlockError('native16 source crosses its code segment')
    if set(inputs) != set(input_types):
        raise NativeBlockError('native16 inputs do not match the contract')
    allowed_adapter = {'segments', 'registers', 'inputs', 'outputs', 'relocations', 'preserve_registers', 'scratch', 'initializers', 'flag_inputs'}
    if set(adapter) - allowed_adapter:
        raise NativeBlockError('unknown native16 adapter fields')
    bindings = adapter.get('inputs', {})
    output_bindings = adapter.get('outputs', {})
    flag_inputs=adapter.get('flag_inputs', {})
    if any(not isinstance(item,dict) for item in (bindings,output_bindings,flag_inputs)):
        raise NativeBlockError('native16 port bindings must be objects')
    if set(bindings) & set(flag_inputs) or set(bindings) | set(flag_inputs) != set(input_types) or set(output_bindings) != set(output_types):
        raise NativeBlockError('every native16 input/output needs exactly one binding')
    segments = adapter.get('segments', {'cs': 'code', 'ds': 'data', 'ss': 'data', 'es': 'data'})
    if not isinstance(segments,dict) or set(segments) != {'cs', 'ds', 'ss', 'es'} or segments['cs'] != 'code':
        raise NativeBlockError('native16 segments require CS=code and DS/SS/ES regions')
    if any(not isinstance(value,str) or not value or len(value)>64 for value in segments.values()):
        raise NativeBlockError('invalid native16 region inventory')
    for field in ('relocations','scratch','initializers'):
        if not isinstance(adapter.get(field,[]),list) or any(not isinstance(item,dict) for item in adapter.get(field,[])):
            raise NativeBlockError(f'native16 {field} must contain descriptor objects')
    names = ['code'] + sorted(set(segments.values()) - {'code'})
    for r in adapter.get('relocations', []):
        if r.get('region') not in names:
            names.append(r.get('region'))
    if len(names) > 8 or any(not isinstance(n, str) or not n or len(n) > 64 for n in names):
        raise NativeBlockError('invalid native16 region inventory')
    selectors = {name: 0x1000 + index * 0x2000 for index, name in enumerate(names)}
    register_values = {name: (0xB000 + index * 0x111) & 0xffff for index, name in enumerate(_REGS)}
    register_values.update(bp=0x9000, sp=0x8f00)
    for name, value in (caller_registers or {}).items():
        if name not in _REGS:
            raise NativeBlockError('unknown caller register')
        register_values[name] = _integer(value, 0, 65535, 'caller register')
    caller = dict(register_values)
    adapter_registers=adapter.get('registers', {})
    if not isinstance(adapter_registers,dict):raise NativeBlockError('adapter registers must be an object')
    for name, value in adapter_registers.items():
        if name not in _REGS:
            raise NativeBlockError('unknown adapter register')
        register_values[name] = _integer(value, 0, 65535, 'adapter register')
    for name, region in segments.items():
        if name != 'cs':
            register_values[name] = selectors[region]

    input_register_names={item['register'] for item in bindings.values()
                          if isinstance(item,dict) and isinstance(item.get('register'),str)}

    def location(binding, size):
        if not isinstance(binding, dict) or set(binding) - {'register', 'segment', 'region', 'offset', 'base', 'displacement'}:
            raise NativeBlockError('invalid native16 port location')
        if 'register' in binding:
            if set(binding) != {'register'} or binding['register'] not in ('ax','bx','cx','dx','si','di'):
                raise NativeBlockError('invalid native16 register binding')
            return ('register', binding['register'])
        segment = binding.get('segment')
        region = binding.get('region')
        if ('region' in binding) == ('segment' in binding):raise NativeBlockError('memory port requires one region or segment binding')
        if region is None:
            if segment not in ('ds', 'ss', 'es'):raise NativeBlockError('memory port requires a bound DS/SS/ES')
            region=segments[segment]
        if region not in selectors or region=='code':raise NativeBlockError('memory port needs a declared state region, not code')
        location_key='region' if 'region' in binding else 'segment'
        if 'base' in binding:
            if set(binding) != {location_key, 'base', 'displacement'} or binding['base'] not in _REGS:
                raise NativeBlockError('invalid frame-relative binding')
            if binding['base'] not in adapter_registers or binding['base'] in input_register_names:
                raise NativeBlockError('frame base requires an explicit adapter register, distinct from scalar input carriers')
            offset = register_values[binding['base']] + _integer(binding['displacement'], -65535, 65535, 'frame displacement')
        else:
            if set(binding) != {location_key, 'offset'}:
                raise NativeBlockError('memory port requires an offset')
            offset = _integer(binding['offset'], 0, 65535, 'port offset')
        if not 0 <= offset <= 65536 - size:
            raise NativeBlockError('native16 memory port crosses its segment')
        return ('memory', selectors[region] * 16 + offset)

    readable, writable, init = [], [], []
    input_spans, port_spans = [], []
    register_inputs = {}
    for port, typ in input_types.items():
        if typ not in _TYPES:
            raise NativeBlockError('native16 port type is unsupported')
        size, signed = _TYPES[typ]
        value = inputs[port]
        if typ == 'bool':
            if type(value) is not bool:raise NativeBlockError('invalid boolean input')
        else:_integer(value, -(1 << (8 * size - 1)) if signed else 0, (1 << (8 * size - (1 if signed else 0))) - 1, port)
        if port in flag_inputs:continue
        kind, place = location(bindings[port], size)
        if kind == 'register':
            if place in register_inputs:raise NativeBlockError('native input registers must be distinct')
            register_inputs[place] = int(value) & 0xffff
        else:
            if _overlaps(input_spans,place,size):raise NativeBlockError('native input memory ports overlap')
            input_spans.append((place,place+size));port_spans.append((place,place+size))
            data = int(value).to_bytes(size, 'little', signed=signed)
            init.append((place, data));readable.append((place, place + size))
    output_locations = {}
    for port, typ in output_types.items():
        if typ not in _TYPES:raise NativeBlockError('native16 output type is unsupported')
        loc = location(output_bindings[port], _TYPES[typ][0]);output_locations[port] = loc
        if loc[0] == 'memory':
            span = (loc[1], loc[1] + _TYPES[typ][0]);readable.append(span);writable.append(span);port_spans.append(span)
    for item in adapter.get('scratch', []):
        if set(item) != {'segment', 'offset', 'size'}:raise NativeBlockError('invalid scratch descriptor')
        size = _integer(item['size'], 1, 65536, 'scratch size')
        _, start = location({'segment': item['segment'], 'offset': item['offset']}, size)
        readable.append((start, start + size));writable.append((start, start + size))
    initializer_spans=[]
    for item in adapter.get('initializers', []):
        if set(item) != {'segment', 'offset', 'bytes_hex'}:raise NativeBlockError('invalid initializer')
        if not isinstance(item['bytes_hex'],str) or len(item['bytes_hex'])>131072:raise NativeBlockError('initializer exceeds its byte budget')
        try:data = bytes.fromhex(item['bytes_hex'])
        except (TypeError, ValueError) as exc:raise NativeBlockError('invalid initializer bytes') from exc
        if not data:raise NativeBlockError('empty initializer')
        _, start = location({'segment': item['segment'], 'offset': item['offset']}, len(data))
        if _overlaps(port_spans+initializer_spans,start,len(data)):
            raise NativeBlockError('initializer overlaps a contract port or another initializer')
        initializer_spans.append((start,start+len(data)))
        init.append((start, data));readable.append((start, start + len(data)))
    adapted = bytearray(code);relocations=[];seen=set()
    # The profile admits only segment-word replacements in MOV r16, imm16.
    import iced_x86 as ix
    immediates = set();cursor=0
    while cursor < len(code):
        decoder=ix.Decoder(16, code[cursor:], ip=origin+cursor);ins=decoder.decode()
        if ins.is_invalid:raise NativeBlockError('native16 code contains invalid/truncated instructions')
        offsets=decoder.get_constant_offsets(ins)
        if ins.mnemonic == ix.Mnemonic.MOV and ins.op0_kind == ix.OpKind.REGISTER and offsets.immediate_size == 2:
            immediates.add(cursor+offsets.immediate_offset)
        cursor += ins.len
    for item in adapter.get('relocations', []):
        if set(item) != {'offset', 'expected_hex', 'region'}:raise NativeBlockError('invalid segment relocation')
        off = _integer(item['offset'], 0, len(code)-2, 'relocation offset')
        if off not in immediates or off in seen:raise NativeBlockError('segment relocation must name a distinct MOV immediate16')
        seen.add(off)
        try:expected=bytes.fromhex(item['expected_hex'])
        except (ValueError,TypeError) as exc:raise NativeBlockError('invalid relocation expectation') from exc
        if len(expected)!=2 or code[off:off+2]!=expected:raise NativeBlockError('segment relocation source bytes differ')
        value=selectors[item['region']];adapted[off:off+2]=value.to_bytes(2,'little')
        relocations.append(dict(offset=off,original=expected.hex(),region=item['region'],selector=value))
    preserved=adapter.get('preserve_registers', list(_REGS))
    if not isinstance(preserved,list) or len(set(preserved))!=len(preserved) or any(r not in _REGS for r in preserved):
        raise NativeBlockError('invalid preserved-register inventory')
    flags=2
    bound_flag_bits=set()
    for port, bit in adapter.get('flag_inputs', {}).items():
        if port not in inputs or type(bit) is not int or bit != 0 or inputs[port] not in (0,1):
            raise NativeBlockError('only explicit boolean carry input is supported')
        if bit in bound_flag_bits:raise NativeBlockError('native input flag carriers must be distinct')
        bound_flag_bits.add(bit)
        flags |= int(inputs[port])
    try:
        import unicorn as uc
        from unicorn import x86_const as xr
    except ImportError as exc:
        raise NativeBlockError('native16 execution requires the optional unicorn dependency (install fdisbull[udc])') from exc
    machine=uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_16)
    for name, selector in selectors.items():
        machine.mem_map(selector*16,65536,uc.UC_PROT_READ|uc.UC_PROT_WRITE|(uc.UC_PROT_EXEC if name=='code' else 0))
    begin=selectors['code']*16+origin;end=begin+len(code)
    readable=_merged_ranges(readable+[(begin,end)]);writable=_merged_ranges(writable)
    machine.mem_write(begin,bytes(adapted));machine.mem_protect(selectors['code']*16,65536,uc.UC_PROT_READ|uc.UC_PROT_EXEC)
    for address,data in init:machine.mem_write(address,data)
    registers={name:getattr(xr,'UC_X86_REG_'+name.upper()) for name in _REGS}
    for name,value in register_values.items():machine.reg_write(registers[name],value)
    for name,value in register_inputs.items():machine.reg_write(registers[name],value)
    machine.reg_write(xr.UC_X86_REG_CS,selectors['code']);machine.reg_write(xr.UC_X86_REG_EFLAGS,flags)
    aborted=[];writes=[];steps=[0]
    def abort(reason):
        if not aborted:aborted.append(reason)
        machine.emu_stop()
    allowed_names=('MOV MOVZX MOVSX ADD ADC SUB SBB XOR AND OR CMP TEST SHL SHR SAR ROL ROR RCL RCR MUL IMUL DIV IDIV INC DEC NEG NOT LEA XCHG PUSH POP PUSHF POPF CLC STC CMC CALL RET RETF ENTER LEAVE NOP CBW CWD JMP JO JNO JB JAE JE JNE JBE JA JS JNS JP JNP JL JGE JLE JG JCXZ LOOP LOOPE LOOPNE').split()
    allowed_mnemonics={getattr(ix.Mnemonic,name) for name in allowed_names if hasattr(ix.Mnemonic,name)}
    def step(engine,address,size,userdata):
        if not begin<=address<end or address+size>end:
            abort('native control left the retained block');return
        steps[0]+=1
        if steps[0]>max_steps:abort('native instruction budget exhausted');return
        instruction=ix.Decoder(16,bytes(engine.mem_read(address,size)),ip=address-selectors['code']*16).decode()
        if instruction.mnemonic not in allowed_mnemonics:
            abort('native block requests an unsupported host/device operation')
    def access(engine,kind,address,size,value,userdata):
        if kind == uc.UC_MEM_WRITE:
            if not _range_contains(writable,address,size):abort('native write is outside declared outputs/scratch');return
            if len(writes)<256:writes.append(dict(address=hex(address),size=size,value=value))
        elif not _range_contains(readable,address,size):abort('native read is outside declared inputs/outputs/scratch')
    machine.hook_add(uc.UC_HOOK_CODE,step)
    machine.hook_add(uc.UC_HOOK_MEM_READ|uc.UC_HOOK_MEM_WRITE,access)
    machine.hook_add(uc.UC_HOOK_INTR,lambda engine,number,user:abort('native interrupt is unsupported'))
    try:machine.emu_start(begin,end,timeout=1000000,count=max_steps+1)
    except uc.UcError as exc:raise NativeBlockError(f'native CPU execution failed: {exc}') from exc
    if aborted:raise NativeBlockError(aborted[0])
    if machine.reg_read(xr.UC_X86_REG_CS)!=selectors['code'] or machine.reg_read(xr.UC_X86_REG_IP)!=(origin+len(code)):
        raise NativeBlockError('native block did not reach its exact exit boundary')
    observed={r:machine.reg_read(registers[r]) for r in _REGS}
    outputs={}
    for port,(kind,place) in output_locations.items():
        size,signed=_TYPES[output_types[port]]
        value=machine.reg_read(registers[place])&((1<<(size*8))-1) if kind=='register' else int.from_bytes(machine.mem_read(place,size),'little')
        if signed and value >= 1<<(size*8-1):value-=1<<(size*8)
        if output_types[port]=='bool':
            if value not in (0,1):raise NativeBlockError('native boolean output is not canonical')
            value=bool(value)
        outputs[port]=value
    for name in preserved:machine.reg_write(registers[name],caller[name])
    restored={r:machine.reg_read(registers[r]) for r in preserved}
    if any(restored[r]!=caller[r] for r in preserved):raise NativeBlockError('ABI adapter failed register preservation')
    return dict(outputs=outputs,events=[],execution='unicorn-x86-16',steps=steps[0],
                source_code_sha256=hashlib.sha256(code).hexdigest(),adapted_code_sha256=hashlib.sha256(adapted).hexdigest(),
                relocations=relocations,caller_registers=caller,native_exit_registers=observed,
                restored_registers=restored,memory_writes=writes,
                scope='isolated native block with declared state/ABI adapter; not a DOS or Windows process')
