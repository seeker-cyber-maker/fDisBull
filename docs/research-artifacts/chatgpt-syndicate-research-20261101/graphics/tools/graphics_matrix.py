"""Original-code caller probes with an independent pixel-level oracle.
Diagnostic setup only; no DOS/device execution or ordinary-game reachability.
"""
from pathlib import Path
import os,sys,json,struct,hashlib,itertools,zlib,time
from probe_cpu64 import run,ROOT
OUT=ROOT/'evidence'/'graphics-caller-v1'
OUT.mkdir(exist_ok=False)
B0=0x1001000; B1=0x1041000; N=32000*4; GUARD=32
PAT=bytes(((i*37+(i//80)*13)^0x5A)&255 for i in range(N))
REG={'eax':0x12345678,'ebx':0x89abcdef,'ecx':0x87654321,'edx':0x76543210,'esi':0x1234,'edi':0x2345,'ebp':0x3456}
ENTRIES=[('hline-a',0x41eee,False,B0),('hline-b',0x42173,False,B1),('rect-a',0x423f8,True,B0),('rect-b',0x4276b,True,B1)]
STOPS=[0x41fd2,0x42257,0x4257d,0x428f0]
SAMPLES=STOPS+[0x42b98,0x42d70]
def ints(*vs):return struct.pack('<'+'I'*len(vs),*[v&0xffffffff for v in vs])
def expected(args,rect,viewport):
    ox,oy,vw,vh=viewport
    # These arithmetic semantics mirror recovered endpoint admission. The pixel
    # implementation does not use the original mask tables or dispatch routines.
    if rect:
        x,y,w,h,col=args
        if w<0:w=-w;x-=w
        if h<0:h=-h;y-=h
        if not w or not h:return bytearray(PAT)
        l=max(x,0);r=min(x+w,vw);t=max(y,0);b=min(y+h,vh)
    else:
        a,z,y,col=args
        z+=1
        if a>=z:a,z=z,a
        l=max(a,0);r=min(z,vw);t=y;b=y+1
        if y<0 or y>=vh:return bytearray(PAT)
    dst=bytearray(PAT)
    for y in range(t,b):
        for x in range(l,r):
            X=x+ox;Y=y+oy
            if not (0<=X<640 and 0<=Y<400):raise ValueError('oracle domain')
            at=Y*80+(X>>3);mask=128>>(X&7)
            for plane in range(4):
                pos=at+plane*32000
                dst[pos]=(dst[pos]|mask) if col&(1<<plane) else (dst[pos]&(~mask&255))
    return dst
records=[]
for family,entry,rect,selected in ENTRIES:
    cases=[]
    # Ensure every tail-table index 0..16 is selected at least once.
    for k in range(17):
        args=(0,10,8+k,3,k%16) if rect else (0,7+k,10,k%16)
        cases.append(('remainder-'+str(k),args,(0,0,640,400)))
    for col in range(16):
        args=(3,17,49,2,col) if rect else (3,51,17,col)
        cases.append(('color-'+str(col),args,(0,0,640,400)))
    edges=[(-9,3,17,4,7),(635,398,10,6,8),(10,12,-9,-5,4),(0,0,0,4,5),(-20,2,4,3,2),(5,500,6,3,3),(2,-5,19,8,11),(3,4,1,1,15),(1,1,63,7,9),(4,3,40,2,6)] if rect else [(-9,17,3,7),(635,647,399,8),(17,3,20,4),(3,2,10,5),(-20,-2,4,2),(5,7,500,3),(2,19,-1,11),(3,3,4,15),(1,63,7,9),(4,40,3,6)]
    for i,args in enumerate(edges):cases.append(('edge-'+str(i),args,(0,0,640,400)))
    cases.append(('translated-viewport',(1,2,37,3,9) if rect else (1,37,2,9),(25,16,50,25)))
    for name,args,vp in cases:
        want=bytes(expected(args,rect,vp));bounds=ints(*vp)
        writes={B0-GUARD:b'\xA7'*GUARD+PAT+b'\xA7'*GUARD,B1-GUARD:b'\xB9'*GUARD+PAT+b'\xB9'*GUARD,
                0x55368:ints(B0),0x55374:ints(B1),0x55380:bounds,0x80105:b'\2',0x200ff04:ints(*args)}
        r=run(entry,registers=REG,writes=writes,observe=[(B0-GUARD,N+2*GUARD),(B1-GUARD,N+2*GUARD),(0x200ff04,4*len(args))],sample_at=SAMPLES,max_steps=12000,seconds=15)
        observations={b:bytes.fromhex(r['observations'][hex(b-GUARD)]['after']) for b in (B0,B1)}
        checks={}
        for b,can in [(B0,0xA7),(B1,0xB9)]:
            got=observations[b];expect=want if b==selected else PAT
            checks['buffer_'+hex(b)]=got[GUARD:-GUARD]==expect
            checks['canary_'+hex(b)]=got[:GUARD]==bytes([can])*GUARD and got[-GUARD:]==bytes([can])*GUARD
        checks['returned']=r['reason']=='returned'
        checks['preserved_registers']=all(int(r['final_regs'][k],16)==v for k,v in REG.items())
        checks['reaped']=r['owned_child_reaped']
        tail=[int(s['registers']['edi'],16) for s in r['samples'] if int(s['pc'],16) in STOPS]
        checks['tail_bounds']=all(0<=v<=16 for v in tail)
        # Retain all exact native observations privately; publish only identities
        # and results from the authored input/output comparison.
        f=OUT/f'{family}-{name}.json.zlib';f.write_bytes(zlib.compress(json.dumps(r).encode(),9))
        summary={'family':family,'case':name,'args':args,'viewport':vp,'reason':r['reason'],'steps':r['steps'],'tail_indices':tail,'checks':checks,'all_pass':all(checks.values()),'receipt_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'buffer_sha256':hashlib.sha256(observations[selected][GUARD:-GUARD]).hexdigest(),'arg_after':r['observations']['0x200ff04']['after']}
        if not summary['all_pass']:
            got=observations[selected][GUARD:-GUARD];diff=[i for i,(a,b) in enumerate(zip(got,want)) if a!=b];summary['mismatch_count']=len(diff);summary['first_diffs']=[(i,got[i],want[i]) for i in diff[:12]]
            print('FAIL',summary,flush=True)
        records.append(summary)
    print('family done',family,len(cases),sum(x['all_pass'] for x in records if x['family']==family),flush=True)
(OUT/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
print('TOTAL',len(records),'PASS',sum(r['all_pass'] for r in records),flush=True)
