#!/usr/bin/env python3
"""Reproduce an assisted calibration, NOT a blind-agent benchmark.

Only reads exact owned DOS inputs. Generated code retaining source bytes stays
inside a caller-chosen private output directory. No downloads or source edits.
"""
from __future__ import annotations
import argparse, hashlib, json, os, struct, subprocess, time
from pathlib import Path

SOURCE_SHA = 'a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3'
NAMES_SHA = '4bf5ba261f71e9215450801d0ac4b00a66e91b046a3b592516524bea03bd6061'
NET_RANGE = (0x8dbc, 0x8e01)
DATA_BASE = 0x1d9a0
MAPPING = 0x2a2


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resource_sections(data: bytes) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}; current = None
    for line in data.decode('ascii').splitlines():
        line = line.split(';', 1)[0].strip()
        if not line: continue
        if line.startswith('@'):
            current = line[1:]; out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def build(exe: Path, names: Path, private_out: Path) -> dict:
    private_out = private_out.expanduser().resolve()
    if any((parent / '.git').exists() for parent in (private_out, *private_out.parents)):
        raise ValueError('source-retaining output must be outside a Git checkout')
    private_out.mkdir(parents=True, exist_ok=False)
    data = exe.read_bytes(); raw_names = names.read_bytes()
    if sha(data) != SOURCE_SHA or sha(raw_names) != NAMES_SHA:
        raise ValueError('Input identities differ from admitted DOS edition')
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    lo, hi = NET_RANGE
    instructions = list(md.disasm(data[lo:hi], lo))
    if sum(i.size for i in instructions) != hi-lo:
        raise ValueError('Incomplete net-function decode')
    # Static evidence and observed behavior are kept separate.
    mapping = list(struct.unpack('<20b', data[DATA_BASE+MAPPING:DATA_BASE+MAPPING+20]))
    sec = resource_sections(raw_names)
    labels = [line.split(',')[0].strip() for line in sec['CARGO']]
    jobs = [line.split(',')[0].strip() for line in sec['JOB']]
    buildings = [line.split(',')[0].strip() for line in sec['BUILDING']]
    if len(labels) != 20: raise ValueError('Unexpected source name-record count')
    # Actual caller run, independently decoded from an established boundary.
    tail = list(md.disasm(data[0xa642:0xa6a2], 0xa642))
    if sum(i.size for i in tail) != 0x60: raise ValueError('Incomplete caller decode')
    sites = []
    for n, ins in enumerate(tail):
        if ins.mnemonic != 'call' or ins.op_str != '0x8e84': continue
        prev = tail[n-3:n]
        if len(prev) != 3 or any(p.mnemonic != 'push' for p in prev) or prev[2].op_str != 'cs':
            raise ValueError('Unexpected original factory call shape')
        output, ingredient = int(prev[0].op_str,0), int(prev[1].op_str,0)
        if mapping[output] != ingredient: raise ValueError('Caller/table disagree')
        sites.append({'call_file_offset':ins.address, 'output_id':output,'input_id':ingredient})
    cases = [(o, p) for o in range(20) for p in [-1,*range(20)]]
    (private_out/'CASES.BIN').write_bytes(b''.join(struct.pack('<HH',o,p&0xffff) for o,p in cases))
    body = ','.join(str(x) for x in data[lo:hi]); table = ','.join(str(x&255) for x in mapping)
    asm = f'''.code16
.intel_syntax noprefix
.global _start
_start:
 mov ax,cs
 mov ds,ax
 mov es,ax
 mov ss,ax
 mov sp,0xfff0
 mov bx,0x1000
 mov ah,0x4a
 int 0x21
 jc fail
 mov bx,0x1000
 mov ah,0x48
 int 0x21
 jc fail
 mov word ptr [data_segment],ax
 mov es,ax
 xor di,di
 xor ax,ax
 mov cx,0x8000
 cld
 rep stosw
 mov si,offset mapping
 mov di,0x2a2
 mov cx,20
 rep movsb
 mov dx,offset inname
 mov ax,0x3d00
 int 0x21
 jc fail
 mov word ptr [inh],ax
 mov dx,offset outname
 xor cx,cx
 mov ah,0x3c
 int 0x21
 jc fail
 mov word ptr [outh],ax
next_case:
 push cs
 pop ds
 mov bx,word ptr [inh]
 mov cx,4
 mov dx,offset rec
 mov ah,0x3f
 int 0x21
 jc fail
 or ax,ax
 jz done
 cmp ax,4
 jne fail
 mov es,word ptr [data_segment]
 xor bx,bx
 mov ax,100
init_deficits:
 mov word ptr es:[bx+0x8e5a],ax
 inc ax
 add bx,2
 cmp bx,40
 jb init_deficits
 mov bx,word ptr [rec+2]
 cmp bx,0xffff
 je no_perturbation
 shl bx,1
 inc word ptr es:[bx+0x8e5a]
no_perturbation:
 mov bx,word ptr [rec]
 shl bx,1
 mov word ptr es:[bx+0x8dc8],1000
 mov word ptr es:[bx+0x8e0a],37
 mov word ptr es:[0x7000],0x5a5a
 push 0x7000
 push word ptr [rec]
 mov ds,word ptr [data_segment]
 push cs
 call net_body
 add sp,4
 push cs
 pop ds
 mov word ptr [result+4],ax
 mov ax,word ptr [rec]
 mov word ptr [result],ax
 mov ax,word ptr [rec+2]
 mov word ptr [result+2],ax
 mov ax,word ptr es:[0x7000]
 mov word ptr [result+6],ax
 mov bx,word ptr [outh]
 mov dx,offset result
 mov cx,8
 mov ah,0x40
 int 0x21
 jc fail
 cmp ax,8
 jne fail
 jmp next_case
done:
 mov bx,word ptr [inh]
 mov ah,0x3e
 int 0x21
 mov bx,word ptr [outh]
 mov ah,0x3e
 int 0x21
 mov ax,0x4c00
 int 0x21
fail:
 mov ax,0x4c01
 int 0x21
net_body:
 .byte {body}
mapping:
 .byte {table}
data_segment: .word 0
inh: .word 0
outh: .word 0
rec: .space 4
result: .space 8
inname: .asciz "CASES.BIN"
outname: .asciz "RESULTS.BIN"
'''
    (private_out/'probe.s').write_text(asm)
    subprocess.run(['as','--32','-o',str(private_out/'probe.o'),str(private_out/'probe.s')], check=True, timeout=15)
    subprocess.run(['ld','-m','elf_i386','-Ttext','0x100','--oformat','binary','-o',str(private_out/'PROBE.COM'),str(private_out/'probe.o')],check=True,timeout=15)
    edges=[]
    for output, ingredient in enumerate(mapping):
        if ingredient<0: continue
        job = 13 if output==16 else output
        building_id = data[DATA_BASE+0x2f4+job] if job<19 else 255
        edges.append({'output_id':output,'output':labels[output], 'input_id':ingredient,'input':labels[ingredient],
            'interpretation':'self-adjustment dependency; NOT an established ingredient recipe' if ingredient==output else 'production-shortage dependency',
            'job':jobs[job] if ingredient!=output and job<len(jobs) else None,
            'building_entry':buildings[building_id] if ingredient!=output and building_id<len(buildings) else None})
    return {'source_sha256':sha(data),'names_sha256':sha(raw_names),'mapping':mapping,'edges':edges,'cases':cases,
            'caller_pairs':sites, 'direct_consumption_call_sites':[{'file_offset':0xa655,'input_id':5,'demand_from_output':16},{'file_offset':0xa699,'input_id':14,'demand_from_output':15}],
            'net_range':list(NET_RANGE),'net_body_sha256':sha(data[lo:hi]),'instructions':len(instructions),
            'source_table_file_range':[DATA_BASE+MAPPING,DATA_BASE+MAPPING+20],
            'source_job_table_used_range':[DATA_BASE+0x2f4,DATA_BASE+0x2f4+19]}


def run(args):
    evidence=build(args.exe,args.names,args.private_output)
    t=time.perf_counter()
    env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
    cmd=[str(args.backend.resolve()),'-defaultconf','-defaultmapper','-nogui','-c','cycles max','-c',f'mount c "{args.private_output.resolve()}"','-c','c:','-c','PROBE.COM','-c','exit']
    p=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=40)
    (args.private_output/'native.log').write_bytes(p.stdout)
    elapsed=time.perf_counter()-t
    if p.returncode: raise RuntimeError(f'Backend exited {p.returncode}')
    raw=(args.private_output/'RESULTS.BIN').read_bytes()
    if len(raw)!=len(evidence['cases'])*8: raise ValueError('Incomplete original-result stream')
    observed=list(struct.iter_unpack('<4H',raw));checked=[]
    for (o,q),(oo,qq,net,report) in zip(evidence['cases'],observed):
        mapped=evidence['mapping'][o]
        adj=100+mapped+(q==mapped) if mapped>=0 else 0
        expected=(o,q&65535,963-adj,adj if mapped>=0 else 0x5a5a)
        if (oo,qq,net,report)!=expected: raise AssertionError((expected,(oo,qq,net,report)))
        checked.append({'output_id':o,'perturbed_input_id':q,'net':net,'optional_report':report})
    # Intentionally wrong hypothesis: muskets directly consume ore, skipping tools.
    bad=next(r for r in checked if r['output_id']==15 and r['perturbed_input_id']==14)
    bad_expected=963-106
    assert bad['net'] != bad_expected
    args.report.parent.mkdir(parents=True,exist_ok=True)
    result={k:v for k,v in evidence.items() if k!='cases'}
    result.update({'status':'passed','original_function_invocations':len(checked),'original_backend_sha256':sha(args.backend.with_name('dosbox-x').read_bytes()),'backend_exit':p.returncode,'native_execution_seconds':elapsed,'semantic_scope':'final net and optional report under stable supplied tables; no full colony turn or natural gameplay',
        'results_sha256':sha(raw),'results':checked,'wrong_edge_control':{'claim':'ore directly feeds musket shortage','predicted_net':bad_expected,'observed_net':bad['net'],'detected':True},'benchmark_status':'coordinator-assisted calibration only; not either independent worker arm'})
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','original_function_invocations','native_execution_seconds','results_sha256','wrong_edge_control']},indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--exe',type=Path,required=True);ap.add_argument('--names',type=Path,required=True)
    ap.add_argument('--backend',type=Path,required=True);ap.add_argument('--private-output',type=Path,required=True);ap.add_argument('--report',type=Path,required=True)
    run(ap.parse_args())
