"""Nine original-backed stock-kernel selections under one fixed module UIL.

Inputs are the private verified-build mapping run and hash-pinned toolchain.
Original blocks remain unchanged. DOSBox executes isolated test harnesses, not
the whole game; generated binaries and byte-bearing receipts stay private.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import sqlite3
import struct
import subprocess
import time

from fdisbull.project import Project
from fdisbull.source_native import unpack_exepack
from fdisbull.stock_flow import (PORTS, maintenance_contract, maintenance_module,
                                native16_adapter, decode_state, commit_state)
from fdisbull.udc_blueprint import execute_module_uil
from fdisbull.udc_layers import (digest, register_contract, register_layer,
                                select_layers, run_selection, LayerQualificationError)
from fdisbull.udc_native16 import NativeBlockError, execute_native16


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def cases():
    values = (-32768, -1, 0, 1, 32767)
    result = [dict(zip(PORTS, (stock, produced, population, supported, cost)))
              for stock, produced, population, supported, cost in itertools.product(
                  values, values, (-128, -1, 0, 1, 127), values, (1, 2))]
    result += [dict(stock=10, produced=12, population=p, supported=3, support_cost=c)
               for p in range(-128, 128) for c in (1, 2)]
    rng = random.Random(0xc17d)
    result += [dict(stock=rng.randrange(-32768, 32768), produced=rng.randrange(-32768, 32768),
                    population=rng.randrange(-128, 128), supported=rng.randrange(-32768, 32768),
                    support_cost=rng.choice((1, 2))) for _ in range(256)]
    return result


def layout(binding):
    return dict(records=binding['linked_symbols']['_townbuf']['offset'],
                stride=binding['city_record_stride'],
                population_field=binding['city_population_field_offset'],
                stock_field=binding['city_food_stock_field_offset'],
                produced=binding['linked_symbols']['_town_res_sums']['offset'],
                supported=binding['linked_symbols']['_colonist_homed']['offset'],
                cost_frame_offset=binding['settler_food_cost_bp_offset'],
                record_frame_offset=binding['city_argument_bp_offset'], record_count=128)


def frame_values(index):
    return (0, 1, 63, 127)[index % 4], (0x8800, 0x9000)[index % 2]


def host_state(binding, inputs, index):
    record, frame = frame_values(index)
    adapter = native16_adapter(binding, record=record, frame=frame)
    data, stack = bytearray(b'\xa5' * 65536), bytearray(b'\x5a' * 65536)
    for name, port in adapter['inputs'].items():
        arena = data if port['segment'] == 'ds' else stack
        offset = port.get('offset', frame + port.get('displacement', 0))
        size = 1 if PORTS[name] == 'i8' else 2
        arena[offset:offset+size] = inputs[name].to_bytes(size, 'little', signed=True)
    argument = adapter['initializers'][0]
    stack[argument['offset']:argument['offset']+2] = bytes.fromhex(argument['bytes_hex'])
    return data, stack, record, frame


def oracle_asm(code, binding, vectors, output_name):
    """Own MASM harness; CS cases/output, separate DS data and SS frame arenas."""
    if not 1 <= len(vectors) <= 2500:
        raise ValueError('oracle harness supports 1..2500 vectors')
    rows = []
    for i, inputs in enumerate(vectors):
        record, _ = frame_values(i)
        raw = struct.pack('<Hhhbhh', record, *(inputs[k] for k in PORTS))
        rows.append('db ' + ','.join(str(v) for v in raw))
    # The wrapper supplies the same source ABI. Only the RET after the retained
    # half-open block is added; no instruction within the original block changes.
    return f"""DATASEG segment para public 'DATA'
db 65534 dup(?)
DATASEG ends
FRAMESEG segment para stack 'STACK'
db 65534 dup(?)
FRAMESEG ends
CODESEG segment para public 'CODE'
assume cs:CODESEG,ds:DATASEG,ss:FRAMESEG
start:
mov ax,DATASEG
mov ds,ax
mov ax,FRAMESEG
cli
mov ss,ax
mov sp,0fffeh
sti
mov bp,09000h
xor bx,bx
xor di,di
mov cx,{len(vectors)}
case_loop:
mov ax,word ptr cs:input_cases[bx]
mov word ptr [bp+{binding['record_frame_offset']}],ax
mov dx,{binding['stride']}
imul dx
mov si,ax
mov ax,word ptr cs:input_cases[bx+2]
mov word ptr [si+{binding['records']+binding['stock_field']}],ax
mov ax,word ptr cs:input_cases[bx+4]
mov word ptr ds:[{binding['produced']}],ax
mov al,byte ptr cs:input_cases[bx+6]
mov byte ptr [si+{binding['records']+binding['population_field']}],al
mov ax,word ptr cs:input_cases[bx+7]
mov word ptr ds:[{binding['supported']}],ax
mov ax,word ptr cs:input_cases[bx+9]
mov word ptr [bp{binding['cost_frame_offset']:+}],ax
push cx
call food_block
pop cx
mov ax,word ptr [si+{binding['records']+binding['stock_field']}]
mov word ptr cs:results[di],ax
add di,2
add bx,11
loop case_loop
push cs
pop ds
xor cx,cx
mov dx,offset filename
mov ah,03ch
int 021h
jc failed
mov bx,ax
mov cx,{len(vectors)*2}
mov dx,offset results
mov ah,040h
int 021h
jc failed
cmp ax,cx
jne failed
mov ah,03eh
int 021h
mov ax,04c00h
int 021h
failed:
mov ax,04c01h
int 021h
food_block:
db {','.join(str(v) for v in code)}
ret
filename db '{output_name}',0
input_cases:
{chr(10).join(rows)}
results dw {len(vectors)} dup(0)
CODESEG ends
end start
"""


def dos_oracle(output, sources, vectors, tools, dosbox):
    tools, dosbox = Path(tools).resolve(), Path(dosbox).resolve()
    batch = ['@echo off', 'set PATH=C:\\BIN;Z:\\']
    for index, (edition, item) in enumerate(sorted(sources.items())):
        name = f'F{index}'
        (output / (name+'.ASM')).write_text(oracle_asm(item['code'], item['layout'], vectors, name+'.OUT'))
        batch += [f'masm {name}.ASM; >{name}A.LOG', 'if errorlevel 1 goto failed',
                  f'link {name}.OBJ,{name}.EXE,NUL; >{name}L.LOG',
                  'if errorlevel 1 goto failed', name+'.EXE', 'if errorlevel 1 goto failed']
    batch += ['echo 0>EXIT.TXT', 'goto done', ':failed', 'echo 1>EXIT.TXT', ':done']
    (output/'ORACLE.BAT').write_bytes(('\r\n'.join(batch)+'\r\n').encode())
    (output/'oracle.conf').write_text('[sdl]\noutput=surface\n[cpu]\ncore=normal\ncycles=100000\n[mixer]\nnosound=true\n')
    command = [str(dosbox), '-defaultconf', '-defaultmapper', '-silent', '-fastlaunch',
               '-conf', str(output/'oracle.conf'),
               '-nopromptfolder', '-nolog', '-time-limit', '90',
               '-c', f'mount c "{tools}"', '-c', f'mount d "{output.resolve()}"',
               '-c', 'd:', '-c', 'call ORACLE.BAT', '-c', 'exit']
    with (output/'dosbox.log').open('wb') as log:
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy'), timeout=110)
    if process.returncode or not (output/'EXIT.TXT').is_file() or (output/'EXIT.TXT').read_text().strip() != '0':
        raise ValueError('DOS oracle failed; inspect retained assembler/linker/runtime logs')
    results = {}
    for index, edition in enumerate(sorted(sources)):
        raw = (output/f'F{index}.OUT').read_bytes()
        if len(raw) != len(vectors)*2:
            raise ValueError('DOS oracle output is incomplete')
        results[edition] = list(struct.unpack('<'+'h'*len(vectors), raw))
    return results, dict(execution='dosbox-x-original-block-harness', command=command,
        dosbox_sha256=sha(dosbox.read_bytes()),
        masm_sha256=sha((tools/'BIN/MASM.EXE').read_bytes()),
        linker_sha256=sha((tools/'BIN/LINK.EXE').read_bytes()),
        returncode=process.returncode, vectors_per_edition=len(vectors),
        whole_game=False, blocks_unchanged=True)


def run(mapping_run, output, tools, dosbox):
    start = time.monotonic()
    mapping_run, output = Path(mapping_run).resolve(), Path(output).resolve()
    if any((p/'.git').exists() for p in (output, *output.parents)):
        raise ValueError('byte-bearing outputs must be outside Git')
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    report = json.loads((mapping_run/'report.json').read_text())
    bindings = {b['edition']: layout(b) for b in json.loads((mapping_run/'food-bindings.json').read_text())}
    sources = {}
    tool_pins = {}
    for spec in report['specs']:
        build = json.loads((Path(spec['directory'])/'build-receipt.json').read_text())
        if build.get('verified') is not True:
            raise ValueError('source build witness is not verified')
        for entry in build['toolchain']:
            if entry['path'] in ('BIN/MASM.EXE','BIN/LINK.EXE'):
                if entry['path'] in tool_pins and tool_pins[entry['path']]!=entry['sha256']:
                    raise ValueError('source editions disagree on oracle tool identity')
                tool_pins[entry['path']]=entry['sha256']
        edition = spec['edition']
        matches = [m for m in report['maps'] if m['edition']==edition and m['family']=='food_stock_update']
        if len(matches)!=1:
            raise ValueError('food mapping missing or ambiguous')
        mapped = matches[0]; doc = mapped['document']
        original = Path(spec['original_path']); raw = original.read_bytes()
        if sha(raw)!=doc['original_sha256']:
            raise ValueError('original identity differs from verified mapping')
        view = unpack_exepack(raw); span, = doc['spans']; packed, = span['packed_spans']
        code = view['module'][span['module_offset']:span['module_offset']+span['size']]
        offset = packed['packed_offset']
        if packed['kind']!='literal' or raw[offset:offset+span['size']]!=code or sha(code)!=span['sha256']:
            raise ValueError('source original literal bytes do not match decoded block')
        if any(span['module_offset'] <= seg*16+off < span['module_offset']+span['size']
               for off,seg in view['relocations']):
            raise ValueError('this pilot refuses a kernel with loader relocations')
        sources[edition] = dict(code=code, original=original, original_sha256=sha(raw),
            offset=offset, span=span, mapping=mapped['id'], endpoint=doc['analysis_endpoint'],
            layout=bindings[edition], canonical_project=mapping_run/(edition+'-resident.fdb'))
    if len(sources)!=3:
        raise ValueError('pilot requires three independently verified editions')
    vectors = cases()
    # Admit the half-open execution boundary in the guarded CPU before the
    # separate DOS process. No control transfer or host operation is admitted.
    import iced_x86 as ix
    profile = 'MOV IMUL MOV MOV CBW SHL MOV MOV IMUL MOV SUB SUB ADD'.split()
    for item in sources.values():
        decoded=list(ix.Decoder(16,item['code'],ip=item['span']['offset']))
        if len(item['code'])!=36 or [i.mnemonic for i in decoded]!=[getattr(ix.Mnemonic,n) for n in profile]:
            raise ValueError('original block differs from the reviewed 13-instruction profile')
        probe=execute_native16(item['code'],{'origin':item['span']['offset']},
            native16_adapter(item['layout']),dict(stock=10,produced=12,population=3,supported=3,support_cost=1),
            PORTS,{'new_stock':'i16'})
        if probe['steps']!=13 or probe['outputs']!={'new_stock':13}:
            raise ValueError('original block fails guarded admission')
    if len(tool_pins)!=2 or any(sha((Path(tools)/p).read_bytes())!=s for p,s in tool_pins.items()):
        raise ValueError('oracle tools differ from verified period-toolchain pins')
    (output/'vectors.json').write_text(json.dumps(vectors))
    expected, oracle = dos_oracle(output, sources, vectors, tools, dosbox)
    if any(sha((Path(tools)/p).read_bytes())!=s for p,s in tool_pins.items()):
        raise ValueError('oracle toolchain changed during execution')
    oracle['period_tool_pins_checked']=True
    oracle['guarded_cpu_preflight']=True
    # This independent closed-form calculation cross-checks the oracle; it
    # neither replaces original CPU execution nor serves as the UDC backing.
    arithmetic = [((v['stock']+v['produced']-2*v['population']-v['supported']*v['support_cost']+32768)%65536)-32768
                  for v in vectors]
    if any(values!=arithmetic for values in expected.values()):
        raise ValueError('original CPU oracle differs from the declared word arithmetic')
    rows, negatives, restart, relations = [], [], [], []
    modules, contracts = set(), set()
    for host, original in sorted(sources.items()):
        path = output/(host+'-swap.fdb')
        with sqlite3.connect(path) as destination, sqlite3.connect(
            'file:'+str(original['canonical_project'])+'?mode=ro', uri=True) as source:
            source.backup(destination)
        selections = {}
        with Project(path) as project:
            c = register_contract(project, maintenance_contract(), author='CivD food swap')
            contracts.add(c['id']); module = maintenance_module(c['id']); modules.add(digest(module))
            for backing, item in sorted(sources.items()):
                attached = 'original-'+backing
                project.attach_file(item['original'], name=attached, kind='original_source')
                snippet = project.capture_snippet('food-'+backing, [
                    {'file': attached, 'offset': item['offset'], 'size': len(item['code'])}],
                    version=1, boundary='compiler source line; original literal bytes; isolated projection',
                    evidence={'source_native_map': item['mapping'], 'original_sha256': item['original_sha256']},
                    author='CivD food swap')
                # One stored realization per indexed record/frame context. They
                # share the exact contract and original backing snippet.
                for record, frame in (frame_values(i) for i in range(4)):
                    adapter = native16_adapter(item['layout'], record=record, frame=frame)
                    layer = register_layer(project, {'format':'fdisbull-udl-layer-1',
                        'name':f'food-{backing}-record-{record}-frame-{frame}',
                        'contract':c['id'], 'snippet':snippet['id'],
                        'implementation':{'backend':'x86-16','origin':item['span']['offset']},
                        'adapter':adapter, 'assurance':'candidate',
                        'evidence':{'source_native_map':item['mapping'], 'flags':'unobserved',
                                    'execution':'isolated native block, not whole-game substitution'}})
                    selected = select_layers(project, f'{host}-uses-{backing}-{record}-{frame}',
                        {'food':layer['id']}, program=module,
                        target={'host_edition':host, 'backing_edition':backing}, author='CivD food swap')
                    selections[(backing, record, frame)] = selected['id']
                results = []
                for index, vector in enumerate(vectors):
                    data, stack, record, frame = host_state(original['layout'], vector, index)
                    inputs = decode_state(original['layout'], data, stack, record=record, frame=frame)
                    if inputs!=vector:
                        raise ValueError('host adapter changed logical inputs')
                    state = {k:v['initial'] for k,v in module['variables'].items()}
                    state.update({'$'+k:v for k,v in inputs.items()})
                    result = execute_module_uil(project, module, selections[(backing,record,frame)], state=state)
                    if result['status']!='complete':
                        raise ValueError('selected original backing refused: '+result.get('error','unknown'))
                    value = result['state']['$new_stock']; call, = result['calls']
                    if value!=expected[host][index] or value!=expected[backing][index]:
                        raise ValueError('swapped UDC differs from original DOS CPU oracle')
                    if call['source_code_sha256']!=sha(item['code']) or call['adapted_code_sha256']!=sha(item['code']):
                        raise ValueError('original kernel bytes changed during realization')
                    if call['steps']!=13 or len(call['memory_writes'])!=1 or call['memory_writes'][0]['size']!=2:
                        raise ValueError('unexpected native effect boundary')
                    if call['restored_registers']!=call['caller_registers']:
                        raise ValueError('ABI register restoration failed')
                    after = commit_state(original['layout'], data, value, record=record)
                    at = original['layout']['records']+record*original['layout']['stride']+original['layout']['stock_field']
                    if after[:at]!=data[:at] or after[at+2:]!=data[at+2:]:
                        raise ValueError('host commit changed a non-output byte')
                    results.append(value)
                rows.append(dict(host=host, backing=backing, invocations=len(results),
                    mismatches=0, results_sha256=sha(struct.pack('<'+'h'*len(results),*results)),
                    source_code_sha256=sha(item['code']), original_bytes_unchanged=True,
                    adapter=item['layout'], selections={str(k[1:]):v for k,v in selections.items() if k[0]==backing}))
                if host!=backing:
                    relations.append(project.link_snippets([original['endpoint']], [snippet['id']],
                        kind='tested-stock-projection', domain={'support_cost':[1,2], 'vector_set_sha256':digest(vectors)},
                        evidence={'native_original_block_oracle':oracle['execution'],'invocations':len(vectors),
                                  'source_map':item['mapping'],'module_uil_sha256':digest(module)},
                        adapters={'source_layout':original['layout'],'target_layout':item['layout'],
                                  'logical_contract':c['id']},
                        assurance='finite-execution-evidence', unknowns=['whole-game effects','flags','untested input combinations']))
            # Change a diagnostic byte copy, never an original or canonical map.
            bad = bytearray(original['code'])
            if bad[-4]!=1:
                raise ValueError('negative control needs the decoded ADD memory16 boundary')
            bad[-4]=0x29
            adapter = native16_adapter(original['layout'])
            wrong = register_layer(project, {'format':'fdisbull-udl-layer-1','name':'diagnostic-subtract',
                'contract':c['id'],'implementation':{'backend':'x86-16','code_hex':bad.hex()},
                'adapter':adapter,'evidence':{'diagnostic':'ADD changed to SUB in a disposable byte copy'}})
            probe = dict(stock=10,produced=12,population=3,supported=3,support_cost=1)
            try:
                run_selection(project, select_layers(project,'diagnostic',{'food':wrong['id']})['id'],'food',probe)
            except LayerQualificationError as exc:
                negatives.append(dict(host=host, kind='changed-operation', rejected=True,
                    expected=exc.receipt['expected']['outputs'],observed=exc.receipt['outputs']))
            else:
                raise ValueError('counterexample control was not detected')
            # A wrong frame local must be refused rather than silently reading
            # zero-filled ambient state.
            wrong_adapter = native16_adapter(original['layout'])
            wrong_adapter['inputs']['support_cost']['displacement']-=2
            broken = register_layer(project, {'format':'fdisbull-udl-layer-1','name':'diagnostic-frame',
                'contract':c['id'],'implementation':{'backend':'x86-16','code_hex':original['code'].hex()},
                'adapter':wrong_adapter})
            try:
                run_selection(project, select_layers(project,'wrong-frame',{'food':broken['id']})['id'],'food',probe)
            except NativeBlockError as exc:
                negatives.append(dict(host=host,kind='wrong-frame-local',rejected=True,error=str(exc)))
            else:
                raise ValueError('unbound frame read was not refused')
            if project.version()['id']!=1 or project.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('native byte version or database integrity changed')
        with Project(path) as project:
            choice = selections[(host,0,0x8800)]
            result = run_selection(project,choice,'food',probe)
            if result['outputs']!={'new_stock':13}:
                raise ValueError('reopened selection differs')
            restart.append(dict(host=host,selection=choice,outputs=result['outputs'],version=project.version()['id']))
    unchanged = all(sha(s['original'].read_bytes())==s['original_sha256'] for s in sources.values())
    if len(modules)!=1 or len(contracts)!=1 or not unchanged:
        raise ValueError('shared UIL/contract or original immutability invariant failed')
    result = dict(format='fdisbull-civd-food-swap-1',seconds=time.monotonic()-start,
        contract=c['document'],contract_id=next(iter(contracts)),
        module_uil=module,module_uil_sha256=next(iter(modules)),
        vectors=len(vectors),vectors_sha256=digest(vectors),matrix=rows,negative_controls=negatives,
        oracle=oracle,restart=restart,snippet_links=relations,originals_unchanged=unchanged,
        originals={k:v['original_sha256'] for k,v in sources.items()},
        scope='Finite original-block CPU/DOSBox projection checks with authored adapters; no whole-game replacement or all-input proof')
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(output),invocations=sum(x['invocations'] for x in rows),
        matrices=len(rows),vectors=len(vectors),seconds=result['seconds'],mismatches=0,originals_unchanged=True)))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping-run',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--tools',required=True,type=Path)
    parser.add_argument('--dosbox',required=True,type=Path)
    args=parser.parse_args()
    run(args.mapping_run,args.output,args.tools,args.dosbox)
