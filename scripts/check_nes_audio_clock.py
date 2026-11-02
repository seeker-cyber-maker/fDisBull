#!/usr/bin/env python3
"""Execute the production NES service-clock C in a real6502 instruction oracle.

Only audio_request/audio_tick are stubs. They record call order and inject
declared NMI state transitions; the scheduling/queue implementation is real.
Negative controls mutate private copies, never the production source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


HARNESS=r'''
#include <stdio.h>
#include <string.h>
typedef unsigned char u8;
typedef unsigned short u16;
volatile u8 irq_phase,request_head,request_tail,request_kind[16],request_id[16];
extern volatile u16 request_slot[16],audio_due_slots,audio_served_slots;
extern volatile u16 audio_physical_entries,audio_catchup_slots,audio_late_calls,audio_max_owed,audio_late_requests;
u16 audio_clock_limit(u8 producer);
void emit(u8 kind,u8 id);
void irq_audio(void);
#define FRAME (*(volatile u16*)0x7D0)
#define DEBUG_MODE (*(volatile u8*)0x7D4)
#define FAULT (*(volatile u8*)0x7ED)
struct Op {u8 kind,id;u16 slot;};
static struct Op ops[128];
static u16 used,ticks;
static u8 inject_tick,inject_each,inject_request;
static const char *case_name;
static void nmi(void){FRAME++;audio_due_slots+=2;irq_phase=0;}
static void record(u8 kind,u8 id){ops[used].kind=kind;ops[used].id=id;ops[used].slot=(u16)(audio_served_slots+1);used++;}
void audio_request(u8 kind,u8 id){record(kind,id);if(inject_request){inject_request=0;nmi();}}
void audio_tick(void){record(0,0);ticks++;if(inject_each || (inject_tick && ticks==inject_tick))nmi();}
static void reset(u16 due,u16 served,u8 phase){
    memset(ops,0,sizeof(ops));memset((void*)request_kind,0,16);memset((void*)request_id,0,16);memset((void*)request_slot,0,32);
    request_head=request_tail=0;audio_due_slots=due;audio_served_slots=served;irq_phase=phase;
    audio_physical_entries=audio_catchup_slots=audio_late_calls=audio_max_owed=audio_late_requests=0;
    FRAME=100;DEBUG_MODE=FAULT=0;used=ticks=inject_tick=inject_each=inject_request=0;
}
static int require(int condition,const char *why){if(!condition){printf("FAIL %s: %s used%u ticks%u served%u due%u\n",case_name,why,used,ticks,audio_served_slots,audio_due_slots);return 0;}return 1;}
static int op(u16 at,u8 kind,u8 id,u16 slot){return at<used && ops[at].kind==kind && ops[at].id==id && ops[at].slot==slot;}
#define CHECK(condition,why) if(!require((condition),(why)))return 1
#define PASS() printf("PASS %s\n",case_name)
int main(void){
    u8 i;
    case_name="future-half";
    reset(10,8,0);irq_audio();CHECK(used==1 && op(0,0,0,9) && audio_served_slots==9,"phase0 released the future second slot");
    irq_phase=1;irq_audio();CHECK(used==2 && op(1,0,0,10),"second half not released");PASS();

    case_name="lost-half-catchup";
    reset(10,7,0);irq_audio();CHECK(used==2 && op(0,0,0,8) && op(1,0,0,9),"old missed slot did not catch up before current first slot");
    CHECK(audio_catchup_slots==1 && audio_served_slots==9,"catchup count/frontier");PASS();

    case_name="no-retroactive-request";
    reset(10,7,1);emit(2,5);CHECK(request_slot[0]==10,"new event stamped into old backlog");irq_audio();
    CHECK(used==4 && op(0,0,0,8) && op(1,0,0,9) && op(2,2,5,10) && op(3,0,0,10),"event applied to ticks preceding production");PASS();

    case_name="producer-phase2";
    reset(10,8,2);emit(1,3);CHECK(request_slot[0]==11,"post-second-half event not stamped into next first slot");irq_audio();
    CHECK(used==2 && request_tail==0,"future event applied during old-slot catchup");nmi();irq_audio();
    CHECK(used==4 && op(2,1,3,11) && op(3,0,0,11),"future event not applied at legal first slot");PASS();

    case_name="fifo-coincident";
    reset(2,0,0);emit(1,11);emit(2,22);emit(2,33);irq_audio();
    CHECK(used==4 && op(0,1,11,1) && op(1,2,22,1) && op(2,2,33,1) && op(3,0,0,1),"coincident requests reordered or applied after tick");PASS();

    case_name="fifo-head-blocks";
    reset(10,8,1);request_head=2;request_kind[0]=1;request_id[0]=11;request_slot[0]=10;
    request_kind[1]=2;request_id[1]=22;request_slot[1]=9;irq_audio();
    CHECK(used==4 && op(0,0,0,9) && op(1,1,11,10) && op(2,2,22,10) && op(3,0,0,10),"future head skipped or FIFO reordered");
    CHECK(audio_late_requests==1,"late request not counted");PASS();

    case_name="counter-wrap";
    reset(0,65534U,0);request_head=1;request_kind[0]=2;request_id[0]=7;request_slot[0]=0;irq_audio();
    CHECK(used==1 && op(0,0,0,65535U) && request_tail==0,"wrapped future event released too early");irq_phase=1;irq_audio();
    CHECK(used==3 && op(1,2,7,0) && op(2,0,0,0) && audio_served_slots==0,"FFFF-to-zero event/slot ordering");PASS();

    case_name="counter-wrap-nmi";
    reset(65534U,65532U,0);emit(1,1);irq_audio();irq_phase=1;irq_audio();irq_phase=2;emit(2,2);
    CHECK(request_slot[request_tail]==65535U,"next-frame stamp at wrap");nmi();irq_audio();
    CHECK(audio_due_slots==0 && audio_served_slots==65535U,"wrapped NMI first slot");irq_phase=1;irq_audio();
    CHECK(audio_served_slots==0 && used==6 && op(3,2,2,65535U) && op(4,0,0,65535U) && op(5,0,0,0),"wrapped NMI request ordering");PASS();

    case_name="nmi-during-tick";
    reset(10,9,1);inject_tick=1;irq_audio();
    CHECK(used==2 && op(0,0,0,10) && op(1,0,0,11) && audio_served_slots==11,"stale frontier after NMI crossing");
    CHECK(audio_due_slots==12,"injected NMI not preserved");PASS();

    case_name="nmi-during-request";
    reset(10,9,1);emit(2,4);inject_request=1;irq_audio();
    CHECK(used==3 && op(0,2,4,10) && op(1,0,0,10) && op(2,0,0,11),"request-boundary NMI ordering/frontier");PASS();

    case_name="bounded-four";
    reset(10,0,1);request_head=1;request_kind[0]=2;request_id[0]=8;request_slot[0]=7;irq_audio();
    CHECK(used==4 && ticks==4 && audio_served_slots==4 && request_tail==0,"service budget exceeded or future request drained");
    CHECK(audio_late_calls==1 && audio_catchup_slots==3,"backlog diagnostics");PASS();

    case_name="nmi-every-tick-bounded";
    reset(2,0,0);inject_each=1;irq_audio();
    CHECK(ticks==4 && used==4 && audio_served_slots==4 && audio_due_slots==10,"NMI replenishment defeated four-slot cap");PASS();

    case_name="debug-bypass";
    reset(10,8,1);request_head=1;request_kind[0]=2;request_id[0]=9;request_slot[0]=9;DEBUG_MODE=1;irq_audio();emit(1,6);
    CHECK(used==0 && audio_served_slots==8 && request_tail==0 && request_head==1,"debug mode mutated audio clock/queue");
    CHECK(*(volatile u8*)0x7F4==1 && *(volatile u8*)0x7F5==6,"debug emit recording lost");PASS();

    case_name="half-range-ambiguous";
    reset(32768U,0,1);irq_audio();CHECK(used==0,"ambiguous half-range backlog advanced");PASS();

    case_name="ring-wrap-fifo";
    reset(2,0,0);request_head=request_tail=14;emit(1,1);emit(2,2);emit(2,3);irq_audio();
    CHECK(used==4 && request_tail==1 && op(0,1,1,1) && op(1,2,2,1) && op(2,2,3,1),"ring wrap reordered requests");PASS();

    for(i=0;i<16;i++)request_slot[i]=0;
    puts("COMPLETE 15");return 0;
}
'''

MUTATIONS={
    'future-half':('if (phase==0) return due-1;','if (phase==0) return due;'),
    'retroactive-stamp':('request_slot[request_head]=audio_clock_limit(1);','request_slot[request_head]=audio_served_slots+1;'),
    'stale-frontier':('for (service=0;service<4;service=service+1) {\n        frontier=audio_clock_limit(0);',
                      'frontier=audio_clock_limit(0);\n    for (service=0;service<4;service=service+1) {'),
    'unbounded-five':('service<4','service<5'),
}


def verify(root,output,*,source=None):
    root=Path(root).resolve();out=Path(output).resolve()
    if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose a fresh output outside Git')
    source=Path(source).resolve() if source else Path(__file__).resolve().parents[1]/'src/fdisbull/game_sources/nes_audio_clock.c'
    original=source.read_text();source_sha=hashlib.sha256(source.read_bytes()).hexdigest();out.mkdir(parents=True)
    cfg=(root/'cfg/sim6502.cfg').read_text().replace('start = $0200','start = $2000')
    (out/'sim.cfg').write_text(cfg);(out/'harness.c').write_text(HARNESS)
    tool_hashes={name:hashlib.sha256((root/'bin'/name).read_bytes()).hexdigest() for name in ('cl65','cc65','ca65','ld65','sim65')}
    cases=[];controls=[]
    for variant in ('production',*MUTATIONS):
        text=original
        if variant!='production':
            before,after=MUTATIONS[variant]
            if text.count(before)!=1:raise ValueError(f'negative-control mutation no longer matches{variant}')
            text=text.replace(before,after)
        folder=out/variant;folder.mkdir();(folder/'clock.c').write_text(text)
        binary=folder/'clock-check'
        build=subprocess.run([str(root/'bin/cl65'),'-t','sim6502','-Oirs','-DFDISBULL_CLOCK_HOST','-C',str(out/'sim.cfg'),
                              '-o',str(binary),str(folder/'clock.c'),str(out/'harness.c')],capture_output=True,text=True,timeout=60)
        (folder/'build.txt').write_text(build.stdout+build.stderr)
        if build.returncode:raise RuntimeError(build.stderr[-3000:])
        run=subprocess.run([str(root/'bin/sim65'),'-c',str(binary)],capture_output=True,text=True,timeout=30)
        (folder/'run.txt').write_text(run.stdout+run.stderr)
        if variant=='production':
            if run.returncode:raise AssertionError(run.stdout+run.stderr)
            cases=[line[5:] for line in run.stdout.splitlines() if line.startswith('PASS ')]
            if len(cases)!=15:raise AssertionError('clock harness did not complete all contract scenarios')
        else:
            if not run.returncode or 'FAIL ' not in run.stdout:raise AssertionError(f'negative clock control unexpectedly passed:{variant}')
            controls.append({'variant':variant,'exit_code':run.returncode,'observed_failure':next(line for line in run.stdout.splitlines() if line.startswith('FAIL '))})
    if hashlib.sha256(source.read_bytes()).hexdigest()!=source_sha:raise RuntimeError('production clock changed during verification')
    if any(hashlib.sha256((root/'bin'/n).read_bytes()).hexdigest()!=h for n,h in tool_hashes.items()):raise RuntimeError('clock toolchain changed')
    receipt={'format':'fdisbull-nes-audio-clock-check-1','source_sha256':source_sha,'passed':True,'cases':cases,
             'negative_controls':controls,'toolchain_sha256':tool_hashes,
             'harness_sha256':hashlib.sha256(HARNESS.encode()).hexdigest(),
             'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'assumptions':['forward outstanding slot distance is less than32768','NMI is modeled as an indivisible FRAME/due/phase update','only audio_request/audio_tick are stubs'],
             'claim':'actual production C compiled to6502 matches authored temporal/FIFO/wrap/budget scenarios; actual mapper IRQ timing and real-time throughput require a separate console gate'}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cc65-root',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(verify(args.cc65_root,args.output),indent=2))
