"""Compare host and Linux-controller tracing on the authored PE GUI fixture.

Compile tests/wine_gui_fixture.c privately with MinGW; supply the advanced
fixture (checkpoint and experiment_value exports). All generated files,
including the project database, go to the new private --output directory.
This is a bounded trace-collection benchmark, not a static-analysis benchmark.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import time
from types import MethodType

import lief

from fdisbull.project import Project
from fdisbull.wine_execution import PEExecutionMixin


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('qemu','kernel','initramfs','fixture','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--backend',choices=('ida-wine-qemu','wine-qemu'),default='ida-wine-qemu')
    parser.add_argument('--remote-server',type=Path)
    args=parser.parse_args()
    if args.backend=='ida-wine-qemu' and args.remote_server is None:
        parser.error('The IDA backend requires --remote-server')
    args.output.mkdir(parents=True,exist_ok=False)
    fixture=args.fixture.resolve(strict=True)
    binary=lief.PE.parse(str(fixture));base=binary.optional_header.imagebase
    exports={e.name:base+e.address for e in binary.get_export().entries}
    loop=exports['experiment_value'];checkpoint=exports['checkpoint']
    report={'backend':args.backend,'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
            'server_sha256':hashlib.sha256(args.remote_server.read_bytes()).hexdigest() if args.remote_server else None,
            'runtime_sha256':hashlib.sha256(args.initramfs.read_bytes()).hexdigest(),
            'scope':'same VM, same thread, same NOP/NOP/JMP loop; no static-analysis or cross-engine claim',
            'samples':[]}
    database=args.output/'benchmark.fdb'
    with Project.create(database,fixture) as project:
        project.analyze(start=checkpoint,max_instructions=32)
        options={'remote_server':args.remote_server} if args.backend=='ida-wine-qemu' else {}
        with project.debugger(args.qemu,fixture.parent,backend=args.backend,kernel=args.kernel,
                              initramfs=args.initramfs,**options) as debug:
            print('READY',flush=True)
            bp=debug.breakpoint(checkpoint)
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            debug.delete_breakpoint(bp['breakpoint_id'])
            before=debug.registers();raw=debug.memory(loop,length=4)['hex'];assert raw=='b8010000'
            debug.layer_patch('bounded benchmark loop',loop,expected_hex=raw,data_hex='9090ebfc',kind='ram')
            runtime=hex(loop+debug.delta)
            debug.write_registers({'rip':{'expected':before['rip'],'value':runtime}})
            default_collector=debug._trace_native
            original_call=debug.rpc.call
            metrics=defaultdict(list)
            def measured(method,params=None,**options):
                start=time.monotonic()
                try:return original_call(method,params,**options)
                finally:metrics[method].append((time.monotonic()-start)*1000)
            debug.rpc.call=measured
            # Alternate order to avoid attributing warm-up to one collector.
            cases=[(24,('host','linux')),(96,('linux','host')),(96,('host','linux'))] if args.backend=='ida-wine-qemu' else [(24,('host',)),(96,('host',)),(96,('host',))]
            for count,order in cases:
                for mode in order:
                    debug._trace_native=MethodType(PEExecutionMixin._trace_native,debug) if mode=='host' else default_collector
                    regs=debug.registers();metrics.clear();start=time.monotonic()
                    artifact=debug.trace(f'{mode}-{count}-{len(report["samples"])}.json',count=count,timeout_ms=120000)
                    elapsed=(time.monotonic()-start)*1000
                    samples={name:list(values) for name,values in metrics.items()}
                    after=debug.registers()
                    assert artifact['metadata']['complete']
                    assert regs['general']==after['general'] and regs['rip']==after['rip']==runtime
                    assert (int(regs['rflags'],16)^int(after['rflags'],16))&0xcd5==0
                    trace=json.loads(bytes(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(artifact['artifact'],)).fetchone()[0]))
                    assert [e['bytes'] for e in trace['events']]==['90','90','ebfc']*(count//3)
                    assert [int(e['address'],16) for e in trace['events']]==[loop+debug.delta+i for i in (0,1,2)]*(count//3)
                    sample=dict(mode=mode,count=count,elapsed_ms=elapsed,requests=sum(map(len,samples.values())),
                                methods={name:dict(count=len(values),median_ms=statistics.median(values)) for name,values in samples.items()},
                                completed=True,same_gprs_and_pc=True,arithmetic_and_direction_flags_unchanged=True,
                                artifact=artifact['artifact'])
                    report['samples'].append(sample);print(json.dumps(sample),flush=True)
            debug._trace_native=default_collector
            debug.rpc.call=original_call
            report['mapping']=debug.metadata
            debug.layers([]);current=debug.registers()
            assert debug.memory(loop,length=4)['hex']==raw
            debug.write_registers({'rip':{'expected':current['rip'],'value':before['rip']}})
            if args.backend=='ida-wine-qemu':
                verify_batch_stops(debug,checkpoint,report)
            debug.screenshot('after-benchmark-grid8.png',grid=True,grid_step=8)
        assert debug.rpc.process.poll() is not None
    with Project(database) as reopened:
        for artifact in reopened.debug_artifacts()['artifacts']:
            reopened.debug_export(artifact['id'],args.output/artifact['name'])
        report['offline_exports']=True
    (args.output/'benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    print('BENCHMARK PASS',flush=True)


def verify_batch_stops(debug,checkpoint,report):
    # Original checkpoint prologue: push rbp; mov rbp,rsp; nop ...
    # Use analyzed, unchanged code for the disassembly breakpoint guard.
    bp=debug.breakpoint(checkpoint+4)
    first=debug.trace('breakpoint-boundary.json',count=10,timeout_ms=30000)
    assert first['metadata']['event_count']==2 and not first['metadata']['complete']
    state=debug.status();assert state['stop_reason']['kind']=='breakpoint'
    assert state['stop_reason']['native_event']['eid']==6
    second=debug.trace('breakpoint-resume.json',count=1,timeout_ms=30000)
    assert second['metadata']['event_count']==1 and second['metadata']['complete']
    assert debug.registers()['rip']==hex(checkpoint+5+debug.delta)
    debug.delete_breakpoint(bp['breakpoint_id'])
    # A budget shorter than the first register read must leave the CPU stopped.
    pc=debug.registers()['rip']
    timeout=debug.trace('deadline.json',count=10000,timeout_ms=1)
    assert not timeout['metadata']['complete'] and timeout['metadata']['event_count']==0
    payload=json.loads(bytes(debug.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(timeout['artifact'],)).fetchone()[0]))
    assert payload['session']['state']=='stopped' and payload['session']['stop_reason']['kind']=='timeout'
    assert debug.status()['state']=='stopped' and debug.registers()['rip']==pc
    report.update(breakpoint_boundary_instructions=[2,1],deadline_stopped_without_execution=True)

if __name__=='__main__':main()
