#!/usr/bin/env python3
"""Read-only patch study on user-supplied SQ1 VGA resources.

The explicit patch recipes below transcribe selected upstream ScummVM signature/
write operations into a bounded manifest. They do NOT stand in for GOG's missing
2018 installer. Analysis is SCI VM bytecode, not native x86. C is a bounded
stack-to-expression lifting, not a general decompiler or independent oracle.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from collections import Counter
import argparse, copy, difflib, hashlib, json, random, statistics, struct, time
ROOT=Path(__file__).resolve().parent
H=lambda s:list(bytes.fromhex(s))
def sha(b): return hashlib.sha256(b).hexdigest()
def save(p,obj): p.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
def require(x,msg):
    if not x: raise ValueError(msg)

def recipes(selectors):
    sid=lambda s: selectors.index(s)
    return [
      dict(id='timepod_cel',script=45,signature=[0x39,sid('cel')]+H('78 39 0a 38 a0 00'),
           writes=[(3,H('39 09'))],slices=[(0,8)],
           effect='One message-construction argument changes from 10 to 9; the send is outside this selected slice.',
           upstream_signature='sq1vgaSignatureUlenceFlatsTimepodGfxGlitch',upstream_patch='sq1vgaPatchUlenceFlatsTimepodGfxGlitch',source_profile='v2.2.0'),
      dict(id='generator_branch',script=45,signature=H('1a 30 f4 cd'),writes=[(1,H('32 00 00'))],slices=[(0,4)],
           effect='The false conditional edge to offset 0xf000 is replaced with an unconditional zero-displacement continuation.',
           upstream_signature='sq1vgaSignatureUlenceFlatsGeneratorGlitch',upstream_patch='sq1vgaPatchUlenceFlatsGeneratorGlitch',source_profile='v2.2.0'),
      dict(id='id_card_counter',script=58,signature=[0x38,*struct.pack('<H',sid('timesShownID')),0x78,0x38,*struct.pack('<H',sid('timesShownID'))]+H('76 51 7c 4a 04 36 35 01 02 36 51 7c 4a 06 36 35 03 22'),
           writes=[(0,[0x38,*struct.pack('<H',sid('timesShownID'))]+H('76 51 7c 4a 04 36 35 01 02 36')+[0x38,*struct.pack('<H',sid('timesShownID'))]+H('78 36 51 7c 4a 06 35 03 22'))],slices=[(0,25)],
           effect='Comparison input changes from a class/object reference to the incremented counter saved on the VM stack.',
           upstream_signature='sq1vgaSignatureEgoShowsCard',upstream_patch='sq1vgaPatchEgoShowsCard',source_profile='v2.2.0'),
      dict(id='bar_detail_predicate',script=43,signature=[0x38,None,None]+H('76 81 01 4a 04 36 35 02 24'),writes=[(11,[0x1e])],slices=[(0,12)],
           effect='Signed comparison changes from <= 2 to > 2.',
           upstream_signature='sq1vgaSignatureBarPatronAnimation',upstream_patch='sq1vgaPatchBarPatronAnimation',source_profile='retrieved_master_excerpt'),
      dict(id='orat_state_storage',script=28,signature=[0x8b,7,0x39,sid('cel')]+H('76 81 00 4a 04 1c')+[None]*177+[0x39,sid('cel')]+H('76 81 00 4a 04 a3 07'),
           writes=[(0,H('67 1a')),(194,H('65 1a'))],slices=[(0,2),(194,196)],
           effect='Selected read and write move from local slot 7 to self property byte offset 0x1a. The intervening 192 bytes are opaque here.',
           upstream_signature='sq1vgaSignatureOratSounds',upstream_patch='sq1vgaPatchOratSounds',source_profile='retrieved_master_excerpt')
    ]

def apply_patch(raw,r):
    p=r['signature'];offsets=[i for i in range(len(raw)-len(p)+1) if all(v is None or raw[i+j]==v for j,v in enumerate(p))]
    require(len(offsets)==1,f"{r['id']}: expected exactly one signature, found {len(offsets)}")
    base=offsets[0]; new=bytearray(raw);allowed=set()
    for rel,vals in r['writes']:
        require(base+rel+len(vals)<=len(raw),'patch write outside resource')
        for j,v in enumerate(vals):new[base+rel+j]=v;allowed.add(base+rel+j)
    changed={i for i,(x,y) in enumerate(zip(raw,new)) if x!=y}
    require(changed <= allowed,'patch changed an undeclared byte')
    require(len(raw)==len(new),'length-changing recipe unsupported')
    return bytes(new),base,sorted(changed),sorted(allowed)

# Only opcodes needed by the explicitly selected slices. Unknowns stop decoding.
OPS={0x01:('add',False),0x0d:('eq',False),0x0f:('gt',False),0x11:('lt',False),0x12:('le',False),
     0x18:('bnt',True),0x19:('jmp',True),0x1a:('ldi',True),0x1b:('push',False),
     0x1c:('pushi',True),0x25:('send',True),0x28:('class',True),0x32:('aTop',True),
     0x33:('pTos',True),0x3b:('push0',False),0x3c:('push1',False),0x3d:('push2',False),
     0x40:('lag',True),0x45:('lsl',True),0x51:('sal',True)}
def decode(b,origin=0):
    out=[];i=0
    while i<len(b):
        start=i;op=b[i];i+=1
        require(op>>1 in OPS,f'unsupported opcode {op:#x} at {origin+start:#x}')
        name,hasarg=OPS[op>>1];arg=None
        if hasarg:
            width=1 if op&1 else 2
            # SCI1 send count stays one byte even for extOpcode 0x4a.
            if name=='send':width=1
            require(i+width<=len(b),'truncated operand')
            arg=int.from_bytes(b[i:i+width],'little',signed=name in ('ldi','pushi','bnt','jmp'))
            i+=width
        else:width=0
        target=((origin+i+arg)&0xffff) if name in ('bnt','jmp') else None
        out.append(dict(offset=origin+start,relative=start,size=i-start,name=name,arg=arg,
                        target=target,operand_width=width,raw=b[start:i].hex()))
    return out

def normalize(instructions,origin):
    result=[]
    for x in instructions:
        row=[x['name']]
        if x['arg'] is not None:
            # Preserve immediates and storage banks. Only the address presentation changes.
            row.append(x['arg'])
        if x['target'] is not None: row.append(('relative_target',(x['target']-origin)&0xffff))
        result.append(row)
    return result

# Expressions are typed enough to keep object references out of integer comparisons.
def e(op,*args):return (op,*args)
def const(n):return e('integer',n&0xffff)
def c_expr(x):
    op,*a=x
    if op=='integer':return str(a[0])
    if op in ('input','snapshot'):return a[0]
    if op=='class_ref':return f'class_ref({a[0]})'
    if op=='global_ref':return f'global_ref({a[0]})'
    if op=='read_selector':return f'read_selector({c_expr(a[0])}, {a[1]})'
    if op=='read_local':return f'read_local({a[0]})'
    if op=='read_property':return f'read_property(self, 0x{a[0]:x})'
    if op=='add16':return f'wrap16({c_expr(a[0])} + {c_expr(a[1])})'
    if op in ('eq','le','gt','lt'):
        sign={'eq':'==','le':'<=','gt':'>','lt':'<'}[op]
        if op!='eq' and (a[0][0] in ('class_ref','global_ref') or a[1][0] in ('class_ref','global_ref')):
            return f'UNRESOLVED_object_numeric_{op}({c_expr(a[0])}, {c_expr(a[1])})'
        cast='' if op=='eq' else 's16'
        render=lambda q:f's16({c_expr(q)})' if cast else c_expr(q)
        return f'({render(a[0])} {sign} {render(a[1])})'
    if op=='not':return f'!({c_expr(a[0])})'
    raise ValueError(f'unhandled expression {op}')

def lift(instructions,prestack=()):
    stack=list(prestack);acc=e('input','acc_in');prev=e('input','prev_in');events=[]
    for x in instructions:
        op=x['name'];a=x['arg']
        if op=='pushi':stack.append(const(a))
        elif op.startswith('push') and op[-1:] in '012':stack.append(const(int(op[-1])))
        elif op=='push':stack.append(acc)
        elif op=='ldi':acc=const(a)
        elif op=='class':acc=e('class_ref',a)
        elif op=='lag':acc=e('global_ref',a)
        elif op=='lsl':stack.append(e('read_local',a))
        elif op=='pTos':stack.append(e('read_property',a))
        elif op in ('aTop','sal'):
            events.append((('write_property' if op=='aTop' else 'write_local'),a,acc,x['offset']))
        elif op=='send':
            require(a%2==0,'odd send frame');n=a//2
            require(len(stack)>=n,'missing send frame')
            frame=stack[-n:];del stack[-n:]
            require(len(frame)>=2 and frame[0][0]=='integer' and frame[1][0]=='integer','unknown selector frame')
            sid,argc=frame[0][1],frame[1][1]
            require(n==argc+2,'multi-selector send not supported by this slice lifter')
            if argc==0:
                name=f'read_{sum(v[0]=="read_selector" for v in events)}'; events.append(('read_selector',acc,sid,name,x['offset']));acc=e('snapshot',name)
            elif argc==1:
                events.append(('write_selector',acc,sid,frame[2],x['offset']))
                # Explicit summary: property selector store does not replace accumulator.
            else: raise ValueError('non-property send requires a method summary')
        elif op in ('add','eq','le','gt','lt'):
            require(stack,'missing VM stack input')
            left=stack.pop()
            if op=='add':acc=e('add16',left,acc)
            else:prev=acc;acc=e(op,left,acc)
        elif op=='bnt':events.append(('conditional_edge',e('not',acc),x['target'],x['offset']))
        elif op=='jmp':events.append(('unconditional_edge',x['target'],x['offset']))
        else:raise ValueError(op)
    return dict(acc=acc,prev=prev,stack=stack,events=events)

def render_c(ir):
    out=[]
    for event in ir['events']:
        tag,*a=event
        if tag=='read_selector':out.append(f'unsigned int {a[2]} = read_selector({c_expr(a[0])}, {a[1]});')
        elif tag=='write_selector':out.append(f'write_selector({c_expr(a[0])}, {a[1]}, {c_expr(a[2])});')
        elif tag=='write_local':out.append(f'write_local({a[0]}, {c_expr(a[1])});')
        elif tag=='write_property':out.append(f'write_property(self, 0x{a[0]:x}, {c_expr(a[1])});')
        elif tag=='conditional_edge':out.append(f'next_pc = ({c_expr(a[0])}) ? {a[1]} : {a[2]+3};')
        elif tag=='unconditional_edge':out.append(f'next_pc = {a[0]};')
    out += [f'acc_out = {c_expr(ir["acc"])};', f'prev_out = {c_expr(ir["prev"])};']
    out += [f'stack_out[{i}] = {c_expr(x)};' for i,x in enumerate(ir['stack'])]
    return '\n'.join(out)+'\n'

def byte_compare(a,b):
    require(len(a)==len(b),'equal-size scope only')
    return [(i,x,y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]

def asm_compare(a,b,origin):
    da,db=decode(a,origin),decode(b,origin)
    na,nb=normalize(da,origin),normalize(db,origin)
    edits=difflib.SequenceMatcher(a=[str(x) for x in na],b=[str(x) for x in nb],autojunk=False).get_opcodes()
    return da,db,[x for x in edits if x[0]!='equal']
def c_compare(a,b,origin,prestack=()):
    old,new=lift(decode(a,origin),prestack),lift(decode(b,origin),prestack)
    normalized=lambda ir:{**ir,'events':[ev[:-1] for ev in ir['events']]}
    return old,new,normalized(old)!=normalized(new)

def c_tree_compare(a,b,origin,prestack=()):
    # Compare parsed, coordinate-free C ASTs, preserving operators, types and order.
    from pycparser import c_parser
    global C_PARSER
    if 'C_PARSER' not in globals(): C_PARSER=c_parser.CParser()
    def tree(x):
        return (type(x).__name__,tuple((a,getattr(x,a)) for a in x.attr_names),tuple((k,tree(v)) for k,v in x.children()))
    oa,ob,_=c_compare(a,b,origin,prestack)
    ta=tree(C_PARSER.parse('void slice(void) {\n'+render_c(oa)+'}'))
    tb=tree(C_PARSER.parse('void slice(void) {\n'+render_c(ob)+'}'))
    return ta!=tb

def benchmark(rows):
    rng=random.Random(419);samples={k:[] for k in ['bytewise','asm_instruction_compare','asm_symbolic_effect_compare','c_lift_parse_ast_compare']}
    for a,b,o,s in rows:c_tree_compare(a,b,o,s)
    for repeat in range(21):
        order=list(samples);rng.shuffle(order)
        for name in order:
            start=time.perf_counter_ns()
            for _ in range(30):
                for a,b,origin,stack in rows:
                    if name=='bytewise':byte_compare(a,b)
                    elif name=='asm_instruction_compare':asm_compare(a,b,origin)
                    elif name=='asm_symbolic_effect_compare':c_compare(a,b,origin,stack)
                    else:c_tree_compare(a,b,origin,stack)
            samples[name].append((time.perf_counter_ns()-start)/30/1e6)
    return {name:dict(unit='ms_per_corpus',iterations_per_batch=30,batches=21,median=statistics.median(v),min=min(v),max=max(v),samples=v) for name,v in samples.items()}

def main():
    out=ROOT/'results';out.mkdir(exist_ok=True)
    selectors=json.loads((ROOT/'selectors.json').read_text());reports=[];rows=[];controls=[]
    for r in recipes(selectors):
        b=(ROOT/f'resources/script.{r["script"]:03}').read_bytes()
        p,off,changed,writes=apply_patch(b,r)
        # Every selected signature must start within a real script code block.
        at=0;blocks=[]
        while at+4<=len(b):
            typ,sz=struct.unpack_from('<HH',b,at)
            if typ==0:break
            require(sz>=4 and at+sz<=len(b),'invalid script block')
            if typ==2:blocks.append((at+4,at+sz))
            at+=sz
        require(any(a<=off and off+len(r['signature'])<=z for a,z in blocks),'match not within code block')
        record={**r,'offset':off,'original_size':len(b),'before_sha256':sha(b),'after_sha256':sha(p),
                'changed_offsets':changed,'declared_written_offsets':writes,'selected_spans':[]}
        case=out/r['id'];case.mkdir(exist_ok=True)
        for j,(a,z) in enumerate(r['slices']):
            old,new=b[off+a:off+z],p[off+a:off+z];origin=off+a
            pre=(e('input','stack_top_in'),) if r['id']=='generator_branch' else ()
            da,db,edits=asm_compare(old,new,origin);ia,ib,_=c_compare(old,new,origin,pre)
            asm=lambda d:'\n'.join(f'{x["offset"]:04x}  {x["raw"]:<12} {x["name"]}'+(' '+str(x['arg']) if x['arg'] is not None else '')+(f' -> {x["target"]:#06x}' if x['target'] is not None else '') for x in d)+'\n'
            (case/f'{j}_before.asm').write_text(asm(da));(case/f'{j}_after.asm').write_text(asm(db))
            (case/f'{j}_before.c.txt').write_text(render_c(ia));(case/f'{j}_after.c.txt').write_text(render_c(ib))
            same_bag=Counter((x['name'],x['arg']) for x in da)==Counter((x['name'],x['arg']) for x in db)
            record['selected_spans'].append(dict(start=origin,size=z-a,byte_changes=byte_compare(old,new),asm_edits=edits,
                    before_instruction_count=len(da),after_instruction_count=len(db),unordered_instruction_bag_equal=same_bag,before_effects=ia,after_effects=ib))
            rows.append((old,new,origin,pre))
        save(case/'comparison.json',record);reports.append(record)
        # Patch correspondence checks are independent of normalized/C reports.
        for desc,bad in [('wrong source signature',b[:off]+bytes([b[off]^1])+b[off+1:]),('duplicate signature',b+b)]:
            try:apply_patch(bad,r)
            except ValueError:controls.append(dict(case=r['id'],test=desc,passed=True))
            else:raise AssertionError('bad patch application accepted')
        require(set(changed)<=set(writes),'write boundary');controls.append(dict(case=r['id'],test='all non-written bytes preserved',passed=True))
    # Fail-closed unsupported decode; raw-byte comparison may still succeed.
    try:decode(bytes([0xff]))
    except ValueError:controls.append(dict(test='unsupported opcode refuses semantic decode',passed=True))
    else:raise AssertionError('unsupported opcode hidden')
    for a,b,o,s in rows:
        require(not byte_compare(a,a),'identity bytes')
        require(not asm_compare(a,a,o)[2],'identity asm')
        require(not c_compare(a,a,o,s)[2],'identity effects');require(not c_tree_compare(a,a,o,s),'identity C tree')
        require(normalize(decode(a,o),o)==normalize(decode(a,o+0x100),o+0x100),'display relocation')
    controls += [dict(test='all unchanged span controls pass',count=len(rows),passed=True),dict(test='display-address relocation preserves normalized instructions',count=len(rows),passed=True)]
    save(out/'comparison_summary.json',dict(cases=reports,controls=controls,source_role='ScummVM game-logic patches applied in private copies; NOT GOG 20261-to-88857 predecessor recovery',
           c_status='bounded original stack-expression lifter; shares SCI decoder with ASM; selected effect boundary only',
           model_assumptions=['SCI1 16-bit integer operations','selected selectors resolve to properties, not arbitrary methods','property stores preserve accumulator','object-vs-number relational comparison stays unresolved','no caller/callee, full-method, native-runtime, or scene equivalence claim']))
    save(out/'benchmarks.json',dict(scope='warm in-process analysis of identical selected spans; includes decode/lift, excludes source acquisition, authoring and archive extraction',corpus_bytes=sum(len(a) for a,b,o,s in rows),spans=len(rows),case_count=len(reports),timings=benchmark(rows)))
    for r in reports:
        print(r['id'],hex(r['offset']),'changed',len(r['changed_offsets']),'of',r['original_size'], 'bag_equal',[s['unordered_instruction_bag_equal'] for s in r['selected_spans']])
    print('controls',len(controls),'passed')
if __name__=='__main__':main()
