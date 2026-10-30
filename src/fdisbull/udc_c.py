"""A bounded freestanding-C realization of the existing scalar UIL contract.

Only generator-owned C is compiled. Models, generated C, compiler identity and
native text retain separate hashes; compilation is not a source-equivalence proof.
"""
from pathlib import Path
import hashlib
import subprocess
import tempfile
import struct
import lief
from .interaction_il import validate_il
from .udc_shell import _check, _align, SLOT


def _literal(value):
    _check(type(value) in (int,bool) and -(1<<63)<=int(value)<(1<<63),'C scalar literal outside signed64 profile')
    n=int(value)
    return '(-9223372036854775807LL-1LL)' if n==-(1<<63) else str(n)+'LL'


def generate_c(module):
    """Render typed scalar nodes; no arbitrary source, includes, calls or events."""
    program=module['program'];validate_il(program);variables=program['variables']
    adapter=module.get('state_adapter');inputs=sorted(variables) if adapter is None else list(adapter['inputs'])
    outputs=sorted(variables) if adapter is None else list(adapter['outputs'])
    names={n:'v'+str(i) for i,n in enumerate(sorted(variables))};lines=[];serial=[0]
    def value(v):return names[v['var']] if isinstance(v,dict) else _literal(v)
    def condition(c):
        op=c['op']
        if op=='eq':return '('+value(c['left'])+' == '+value(c['right'])+')'
        if op=='bit_test':return '((((unsigned long long)'+value(c['value'])+') >> '+str(c['bit'])+') & 1ULL)'
        if op=='not':return '!('+condition(c['condition'])+')'
        return '('+' && '.join(condition(x) for x in c['conditions'])+')'
    def emit(body,indent='  '):
        for node in body:
            op=node['op']
            if op=='if':
                lines.append(indent+'if ('+condition(node['condition'])+') {');emit(node['then'],indent+'  ');lines.append(indent+'} else {');emit(node['else'],indent+'  ');lines.append(indent+'}')
            elif op=='require':lines.append(indent+'if (!('+condition(node['condition'])+')) return 1ULL<<32;')
            elif op in ('set','add','subtract'):
                var=node['var'];typ=variables[var]['type'];name=names[var];operand=value(node['value']);serial[0]+=1;temp='t'+str(serial[0])
                bits=1 if typ=='bool' else int(typ[1:]);mask=(1<<bits)-1
                if op=='set':
                    low,high=(-(1<<(bits-1)),(1<<(bits-1))-1) if typ.startswith('i') else (0,mask)
                    lines.append(indent+'long long '+temp+' = '+operand+';')
                    lines.append(indent+'if ('+temp+' < '+_literal(low)+' || '+temp+' > '+_literal(high)+') return 1ULL<<32;')
                    lines.append(indent+name+' = '+temp+';')
                else:
                    sign='+' if op=='add' else '-'
                    lines.append(indent+'unsigned long long '+temp+' = ((unsigned long long)'+name+' '+sign+' (unsigned long long)('+operand+')) & '+str(mask)+'ULL;')
                    expr=('('+temp+' >= '+str(1<<(bits-1))+'ULL ? (long long)'+temp+' - '+str(1<<bits)+'LL : (long long)'+temp+')') if typ.startswith('i') else '(long long)'+temp
                    lines.append(indent+name+' = '+expr+';')
            else:raise ValueError('C backend supports pure scalar UIL only')
    lines.append('__attribute__((used,visibility("default"))) unsigned long long udc_block(const unsigned short *in, unsigned short *out) {')
    for n in sorted(variables):
        typ=variables[n]['type'];_check(typ in ('bool','u8','u16','i16'),'C backend supports logical word types only')
        if n in inputs:
            expression='in['+str(inputs.index(n))+']'
            if typ=='i16':expression='('+expression+' >= 32768 ? (long long)'+expression+' - 65536LL : (long long)'+expression+')'
            elif typ in ('u8','bool'):expression='('+expression+' & '+('255' if typ=='u8' else '1')+')'
        else:expression=_literal(variables[n]['initial'])
        lines.append('  long long '+names[n]+' = '+expression+';')
    emit(program['body'])
    for i,n in enumerate(outputs):lines.append('  out['+str(i)+'] = (unsigned short)((unsigned long long)'+names[n]+' & 65535ULL);')
    lines.append('  return (unsigned long long)'+(names[module['return']] if module.get('return') is not None else '0')+' & 65535ULL;')
    lines.append('}')
    return '\n'.join(lines)+'\n',inputs,outputs


def compile_c(module,compiler):
    source,inputs,outputs=generate_c(module)
    _check(compiler is not None,'C backend requires an explicit clang executable')
    compiler=Path(compiler).expanduser().resolve(strict=True)
    with compiler.open('rb') as stream:before=hashlib.file_digest(stream,'sha256').hexdigest()
    try:version_run=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired) as error:raise ValueError('C compiler version probe failed') from error
    _check(version_run.returncode==0 and version_run.stdout.splitlines(),'C compiler version probe failed')
    version=version_run.stdout.splitlines()[0]
    _check('clang' in version.lower(),'C scalar backend currently requires clang')
    flags=['--target=x86_64-unknown-linux-gnu','-std=c11','-O1','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables','-fno-jump-tables','-fno-vectorize','-fno-slp-vectorize','-mno-red-zone','-mgeneral-regs-only','-fno-pic','-c']
    with tempfile.TemporaryDirectory(prefix='fdisbull-c-') as tmp:
        root=Path(tmp);(root/'module.c').write_text(source)
        try:done=subprocess.run([str(compiler),*flags,'module.c','-o','module.o'],cwd=root,capture_output=True,timeout=30)
        except (OSError,subprocess.TimeoutExpired) as error:raise ValueError('C module compiler invocation failed') from error
        _check(done.returncode==0,'C module compilation failed: '+done.stderr.decode(errors='replace')[:2000])
        raw=(root/'module.o').read_bytes();binary=lief.ELF.parse(list(raw))
        _check(binary is not None and not binary.relocations,'C object needs unsupported relocations; no external/constant-pool dependencies admitted')
        symbols=[s for s in binary.symbols if s.name=='udc_block'];_check(len(symbols)==1,'C object lacks unique udc_block')
        symbol=symbols[0];section=binary.sections[symbol.shndx]
        code=bytes(section.content)[symbol.value:symbol.value+symbol.size]
        _check(0<len(code)<=SLOT//2,'C block exceeds its 2048-byte slot profile')
        import capstone
        decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
        instructions=list(decoder.disasm(code,0))
        _check(sum(i.size for i in instructions)==len(code),'C text contains undecoded bytes')
        for instruction in instructions:
            reads,writes=instruction.regs_access()
            names=[instruction.reg_name(r) for r in (*reads,*writes)]
            _check(not any(n.startswith(('xmm','ymm','zmm','mm','st')) for n in names),'C text uses unsupported FP/SIMD ABI state')
    sha=lambda data:hashlib.sha256(data).hexdigest()
    with compiler.open('rb') as stream:compiler_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    _check(compiler_sha==before,'C compiler changed during build')
    return {'source':source,'source_sha256':sha(source.encode()),'object_sha256':sha(raw),'code_hex':code.hex(),'code_sha256':sha(code),'code_size':len(code),'body_offset':SLOT//2,'inputs':inputs,'outputs':outputs,'compiler':{'path':str(compiler),'sha256':compiler_sha,'version':version,'flags':flags},'abi':'SysV RDI=input-word-array, RSI=output-word-array; RAX=(status<<32)|u16-result','scope':'generated scalar C; compiled native qualification remains separate'}


def lower_c_module(code,module,state,offsets,compiled):
    inputs,outputs=compiled['inputs'],compiled['outputs'];frame=_align(2*(len(inputs)+len(outputs)),16)+32
    end=code.fresh();body=code.fresh()
    code.emit('415457564881ec');code.emit(struct.pack('<I',frame));code.emit('4989cc')
    for i,n in enumerate(inputs):
        code.emit('410fb78424');code.emit(struct.pack('<I',offsets[n]))
        code.emit('66898424');code.emit(struct.pack('<I',32+2*i))
    code.emit('488dbc24');code.emit(struct.pack('<I',32));code.emit('488db424');code.emit(struct.pack('<I',32+2*len(inputs)))
    code.relative('e8',body);code.emit('4989c04889c248c1ea2085d2');code.relative('0f85',end)
    for i,n in enumerate(outputs):
        code.emit('0fb78424');code.emit(struct.pack('<I',32+2*len(inputs)+2*i))
        code.emit('6641898424');code.emit(struct.pack('<I',offsets[n]))
    code.mark(end);code.emit('4489c025ffff00004881c4');code.emit(struct.pack('<I',frame));code.emit('5e5f415cc3')
    _check(len(code.data)<=SLOT//2,'C port adapter exceeds its 2048-byte slot')
    code.emit(b'\xcc'*(SLOT//2-len(code.data)));code.mark(body);code.emit(bytes.fromhex(compiled['code_hex']))
    code.maps.append({'path':'module.C','op':'compiled-C','address':code.base+SLOT//2,'size':compiled['code_size'],'source_sha256':compiled['source_sha256'],'scope':'whole compiled function; no instruction-level source recovery claim'})
