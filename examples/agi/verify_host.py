"""Private DOS KQ1 logic103 differential trial. Supply your own original game.

This is a diagnostic invocation, not ordinary gameplay: a guarded temporary
caller operand selects logic103. The selected logic and original files remain
unchanged. Output contains private checkpoints/resources; never add it to Git.
"""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path

from examples.agi.spatial_trial import native_game, read, require
from fdisbull.agi import load_logic
from fdisbull.agi_dos import AGIDOSMonitor, FETCH
from fdisbull.agi_host import AGIDOSHostAdapter, capture_state
from fdisbull.agi_lift import lift_logic

NAMES=[f'$agi_v{n}' for n in (0,1,5,21,40,41,60,61,94,107)]+[
       f'$agi_f{n}' for n in (5,15,40,42,43,63,66,68,75,76,79,207)]


def diagnostic_state(case):
    """Authored branch probes, deliberately not claims of reachable saves."""
    values={name:False if name.startswith('$agi_f') else 0 for name in NAMES}
    if case in ('print','blocking-print'):
        values.update({'$agi_f5':True,'$agi_v0':17,'$agi_v1':18,'$agi_v40':35,
            '$agi_v41':2,'$agi_f75':True,'$agi_f43':True,'$agi_v94':1,
            '$agi_f15':case=='print'})
    elif case=='erase':
        values.update({'$agi_v0':39,'$agi_v1':10,'$agi_v40':24,'$agi_f66':True,
            '$agi_f15':True,'$agi_v107':1,'$agi_f75':True,'$agi_f68':True,
            '$agi_f79':True,'$agi_v5':1})
    return values


def verify(args):
    source=args.source.resolve();output=args.output.resolve()
    resource=load_logic(source/'LOGDIR',source,103,profile='2.917')
    with native_game('kq1',source,output,args.backend.resolve()) as (p,d,obs,restore,frame,report,game):
        regs=report['resolution']['registers'];cs=int(regs['segments']['cs'],16);ds=int(regs['segments']['ds'],16)
        def write(address,data):
            before=read(d,address,len(data))
            d.call('memory.write',{'address':{'space':'linear','offset':f'0x{address:08X}'},
                'expected_sha256':sha256(before).hexdigest(),'data_base64':base64.b64encode(data).decode()})
            require(read(d,address,len(data))==data,'Diagnostic write readback differs')
            return before
        def bp(offset):
            return d.call('breakpoints.create',{'kind':'execution','once':False,
                'address':{'space':'segmented','segment':f'0x{cs:04X}','offset':f'0x{offset:08X}'}})['breakpoint_id']
        def stop(offset):
            result=d.run(guest_ms=1000,timeout_ms=10000,fast_forward=True,stop_on_hook=True)
            r=d.registers()
            require(result['outcome']=='breakpoint' and int(r['segments']['cs'],16)==cs
                    and int(r['instruction_pointer'],16)==offset,'Unexpected diagnostic preparation stop')
            return r
        def scalars(values):
            for name,value in values.items():
                n=int(name[6:])
                if name.startswith('$agi_v'):write(ds*16+9+n,bytes([value]))
                else:
                    address=ds*16+0x109+n//8;mask=0x80>>(n&7);old=read(d,address,1)[0]
                    write(address,bytes([(old|mask) if value else (old&~mask)]))
            report['interventions'].append({'kind':'synthetic scalar state','values':values})
        first=bp(0x125a);r=stop(0x125a)
        address=ds*16+(int(r['general']['esi'],16)&65535)
        require(read(d,address-1,2)==bytes([22,101]),'Expected exact original caller occurrence')
        old=write(address,bytes([103]));d.call('breakpoints.delete',{'breakpoint_id':first})
        report['interventions']=[{'kind':'guarded temporary caller operand','old_logic':101,'new_logic':103}]
        try:
            loaded=bp(0x1303);stop(0x1303)
            record=int.from_bytes(read(d,ds*16+0x979,2),'little')
            descriptor=read(d,ds*16+record,8)
            code_offset=int.from_bytes(descriptor[4:6],'little')
            require(descriptor[2]==103 and read(d,ds*16+code_offset,len(resource.code))==resource.code,
                    'Original logic resource record is not qualified')
            require(int.from_bytes(descriptor[6:8],'little')==code_offset,'Nonzero cached scan start is outside this trial')
            # The selected call already has its argument. Restore the original
            # caller byte before any selected logic instruction runs.
            require(read(d,address,1)==bytes([103]),'Caller operand changed unexpectedly')
            write(address,old)
            d.call('breakpoints.delete',{'breakpoint_id':loaded})
            if args.case in ('initialize','horizon','erase','interrupt'):
                flags=read(d,ds*16+0x109,1);write(ds*16+0x109,bytes([flags[0]|4]))
                report['interventions'].append({'kind':'synthetic initial state','flag':5,'value':True})
            if args.case=='horizon':
                pointer=int.from_bytes(read(d,ds*16+0x963,2),'little')
                horizon=read(d,ds*16+0x12d,2);write(ds*16+pointer+13*43+5,horizon)
                report['interventions'].append({'kind':'synthetic object position','object':13,'y':'horizon'})
            if args.case in ('print','blocking-print'):scalars(diagnostic_state(args.case))
            entry=bp(FETCH);stop(FETCH);d.call('breakpoints.delete',{'breakpoint_id':entry})
            def trial():
                m=AGIDOSMonitor(d,resource,cs=cs,ds=ds,code_offset=code_offset)
                initial=capture_state(m,NAMES)
                projection=lift_logic(resource,initial_state=initial,control_flow='compact',effect_profile='agi-2.917')
                adapter=AGIDOSHostAdapter(m,projection,viewdir=source/'VIEWDIR',volume_dir=source)
                result=adapter.run()
                (output/f'trial-{len(list(output.glob("trial-*.private.json")))}.private.json').write_text(json.dumps(result,indent=2)+'\n')
                require(adapter.run()==result and adapter.readback()==result,'Host readback changed or replayed')
                return result
            before=frame('host-before.png')
            interruption=bp(0x09ea) if args.case=='interrupt' else None
            try:result=trial()
            finally:
                if interruption:d.call('breakpoints.delete',{'breakpoint_id':interruption})
            if args.case=='erase':
                require(result['status']=='verified','First invocation did not complete')
                report['setup_trial']=result
                r=d.registers();stack=int(r['segments']['ss'],16)*16+(int(r['general']['esp'],16)&65535)
                require(int(r['segments']['cs'],16)==cs and int(r['instruction_pointer'],16)==0x1306
                    and read(d,stack,2)==read(d,ds*16+0x979,2),'Completed call frame did not match')
                require(read(d,ds*16+code_offset,len(resource.code))==resource.code,'Selected code changed')
                # A new diagnostic call, after the prior one completed. The
                # original native CALL builds its own frame from its argument.
                d.call('state.set_register',{'register':'EIP','value':0x1303})
                require(int(d.registers()['instruction_pointer'],16)==0x1303,'Callsite edit readback differs')
                report['interventions'].append({'kind':'new diagnostic invocation','from':0x1306,'to':0x1303,'completed_frame_checked':True})
                scalars(diagnostic_state('erase'))
                entry=bp(FETCH);stop(FETCH);d.call('breakpoints.delete',{'breakpoint_id':entry})
                result=trial()
            after=frame('host-after.png')
            report['host_trial']=result;report['frames']=[before,after]
            (output/'trial.private.json').write_text(json.dumps(result,indent=2)+'\n')
            for completion in result['host_completions']:
                p.debug_export(completion['frame']['artifact'],output/f'host-effect-{completion["source_offset"]}.png')
            print(json.dumps({k:result[k] for k in ('status','complete','error','source_offsets','differences','excluded_fields') if k in result}))
            negative=args.case in ('blocking-print','interrupt')
            require(result['status']==('incomplete' if negative else 'verified'),'Unexpected host trial outcome')
            if negative:
                require(result.get('recovery_required') and not result['complete'],'Interrupted route was reported complete')
                require(all(c['operation']!='print' for c in result['host_completions']),'Blocked print was falsely completed')
        finally:
            current=read(d,address,1)
            if current==bytes([103]):write(address,old)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--backend',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',choices=['baseline','initialize','horizon','print','blocking-print','erase','interrupt'],default='initialize')
    verify(parser.parse_args())
