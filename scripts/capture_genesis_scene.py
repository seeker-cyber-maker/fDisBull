#!/usr/bin/env python3
"""Capture original Genesis scene state in a fresh private directory.

This is a bounded observation of the pinned core, not recovered game semantics.
VRAM/CRAM/VSRAM/register/RAM/state payloads are private experiment inputs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CORE_SHA = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'


def trace_ranges(values, *, memory=False):
    """Parse bounded numeric filters; generated observers never evaluate text."""
    if len(values) > 16:
        raise ValueError('at most 16 trace ranges per kind')
    result = []
    for value in values:
        try:
            fields = value.split(':')
            if len(fields) != 2:
                raise ValueError
            start, end = (int(n, 0) for n in fields)
        except (TypeError, ValueError) as exc:
            raise ValueError('trace ranges require numeric start:exclusive-end') from exc
        if not (0xff0000 if memory else 0) <= start < end <= 0x1000000:
            raise ValueError('trace range outside the selected address domain')
        result.append((start, end))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'core', 'output', 'inputs'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--patches', type=Path, help='explicit assisted finite memory interventions for testing')
    p.add_argument('--frames', type=int, default=1800)
    p.add_argument('--captures', default='299,599,899,1199,1499,1799')
    p.add_argument('--trace-start', type=int, help='optional frame to observe work-RAM writes')
    p.add_argument('--trace-end', type=int)
    p.add_argument('--trace-pc-range', action='append', default=[],
                   help='observed writer-PC start:exclusive-end; replaces the default filter')
    p.add_argument('--trace-memory-range', action='append', default=[],
                   help='observed work-RAM start:exclusive-end; combines with writer-PC filters')
    a = p.parse_args()
    captures = [int(n) for n in a.captures.split(',')]
    pc_ranges = trace_ranges(a.trace_pc_range)
    memory_ranges = trace_ranges(a.trace_memory_range, memory=True)
    if (pc_ranges or memory_ranges) and a.trace_start is None:
        raise ValueError('custom filters require a finite trace interval')
    if not 1 <= a.frames <= 10000 or not 1 <= len(captures) <= 64 or any(
            n < 0 or n >= a.frames for n in captures) or len(set(captures)) != len(captures):
        raise ValueError('invalid finite capture budget')
    if a.trace_start is not None and not (
            0 <= a.trace_start < (a.trace_end or 0) <= a.frames):
        raise ValueError('trace requires a bounded start/end interval')
    out = a.output.resolve()
    if out.exists() or not out.parent.is_dir() or any(
            (q / '.git').exists() for q in (out, *out.parents)):
        raise ValueError('choose a new private directory outside Git')
    paths = {'rom': a.rom.resolve(), 'core': a.core.resolve(),
             'inputs': a.inputs.resolve(), 'host': ROOT / 'scripts/check_console_udc.py'}
    if a.patches is not None:
        paths['patches'] = a.patches.resolve()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    identities = {k: {'sha256': sha(v.read_bytes()), 'size': v.stat().st_size}
                  for k, v in paths.items()}
    if identities['core']['sha256'] != CORE_SHA:
        raise ValueError('unsupported core identity')
    out.mkdir()
    host = paths['host'].read_text()
    anchor = '        frames_ran=i+1'
    if host.count(anchor) != 1:
        raise ValueError('host capture point changed')
    injected = '''        if i in CAPTURES:
            folder=out/('scene-%06d'%i)
            folder.mkdir()
            for symbol,length in (('vram',65536),('cram',128),('vsram',128),('reg',32)):
                data=bytes((C.c_ubyte*length).in_dll(lib,symbol))
                (folder/(symbol+'.bin')).write_bytes(data)
            ram=C.string_at(memory_slice(2,0,65536),65536)
            (folder/'ram.bin').write_bytes(ram)
            lib.retro_serialize_size.restype=C.c_size_t
            n=lib.retro_serialize_size()
            snapshot=C.create_string_buffer(n)
            lib.retro_serialize.argtypes=[C.c_void_p,C.c_size_t]
            lib.retro_serialize.restype=C.c_bool
            if not lib.retro_serialize(snapshot,n):raise RuntimeError('scene serialization failed')
            (folder/'state.bin').write_bytes(snapshot.raw)
            lib.m68k_get_reg.argtypes=[C.c_uint]
            lib.m68k_get_reg.restype=C.c_uint
            data={'frame':i,'pc':lib.m68k_get_reg(16),'input_mask':masks[i],
                  'ram_mapping':'pinned-core architectural byte address xor1',
                  'vdp_storage':'raw pinned-core representation; interpret explicitly'}
            (folder/'scene.json').write_text(json.dumps(data,indent=2)+'\\n')
        frames_ran=i+1'''.replace('CAPTURES', repr(set(captures)))
    host = host.replace(anchor, injected)
    if a.trace_start is not None:
        setup = '''    ram_write_events=[]
    ram_write_dropped=[0]
    hook_refs=[]
    class SceneMemoryMap(C.Structure):
        _fields_=[(name,C.c_void_p) for name in ('base','read8','read16','write8','write16')]
    class SceneCpu(C.Structure):
        _fields_=[('maps',SceneMemoryMap*256)]
    cpu=SceneCpu.in_dll(lib,'m68k')
    lib.m68k_get_reg.argtypes=[C.c_uint]
    lib.m68k_get_reg.restype=C.c_uint
    write_sig=C.CFUNCTYPE(None,C.c_uint,C.c_uint)
    page=cpu.maps[255]
    for field,width in (('write8',1),('write16',2)):
        old=getattr(page,field)
        forward=write_sig(old) if old else None
        def make_observer(forward,width):
            @write_sig
            def observed(address,value):
                pc=lib.m68k_get_reg(16)
                if (
                        0xb300<=pc<0xc004 or 0xffdd00<=(address&0xffffff)<0xffdd40
                        or 0xffddc6<=(address&0xffffff)<0xffddca
                        or 0xffdf50<=(address&0xffffff)<0xffdf60
                        or 0xff0100<=(address&0xffffff)<0xff0200):
                    if len(ram_write_events)<100000:
                        ram_write_events.append({'frame':i,'pc':pc,'address':address,'value':value,
                           'width':width,'a0':lib.m68k_get_reg(8),
                           'd0':lib.m68k_get_reg(0),'d5':lib.m68k_get_reg(5),'d6':lib.m68k_get_reg(6)})
                    else:ram_write_dropped[0]+=1
                if forward:forward(address,value)
                elif width==1:C.c_ubyte.from_address(page.base+((address&65535)^1)).value=value
                else:C.c_ushort.from_address(page.base+(address&65535)).value=value
            return observed
        callback=make_observer(forward,width)
        hook_refs.append((field,old,callback))
    frames_ran=0
'''
        if host.count('    frames_ran=0\n') != 1:
            raise ValueError('host setup point changed')
        if pc_ranges or memory_ranges:
            start = setup.index('                if (\n')
            end = setup.index('                    if len(ram_write_events)', start)
            condition = ('any(lo <= pc < hi for lo,hi in ' + repr(pc_ranges) + ') or '
                         'any(lo <= (address&0xffffff) < hi for lo,hi in ' + repr(memory_ranges) + ')')
            setup = setup[:start] + '                if ' + condition + ':\n' + setup[end:]
        host = host.replace('    frames_ran=0\n', setup)
        run_anchor = '        lib.retro_run()\n'
        run_inject = '''        if i==TRACE_START:
            for field,old,callback in hook_refs:setattr(page,field,C.cast(callback,C.c_void_p).value)
        if i==TRACE_END:
            for field,old,callback in hook_refs:setattr(page,field,old)
        lib.retro_run()
'''.replace('TRACE_START', str(a.trace_start)).replace('TRACE_END', str(a.trace_end))
        if host.count(run_anchor) != 1:
            raise ValueError('host runtime point changed')
        host = host.replace(run_anchor, run_inject)
        tail = '    trace_bytes = (json.dumps('
        host = host.replace(tail, "    for field,old,callback in hook_refs:setattr(page,field,old)\n    (out/'ram-writes.json').write_text(json.dumps(ram_write_events)+'\\n')\n    (out/'ram-write-budget.json').write_text(json.dumps({'limit':100000,'recorded':len(ram_write_events),'dropped':ram_write_dropped[0],'complete':not ram_write_dropped[0]})+'\\n')\n" + tail)
    (out / 'worker.py').write_text(host)
    command = [sys.executable, str(out / 'worker.py'), '--core', str(paths['core']),
               '--rom', str(paths['rom']), '--system', 'genesis', '--frames', str(a.frames),
               '--inputs', str(paths['inputs']), '--frame-images', ','.join(map(str, captures)),
               '--output', str(out / 'native'), '--capture-audio']
    if a.patches is not None:
        command.extend(['--patches', str(paths['patches'])])
    run = subprocess.run(command, capture_output=True, text=True, timeout=300)
    (out / 'run.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError(run.stderr[-3000:])
    if a.trace_start is not None:
        budget = json.loads((out / 'native/ram-write-budget.json').read_text())
        if not budget['complete']:
            raise RuntimeError('RAM-write observation budget exhausted; retained trace is incomplete')
    if any(sha(v.read_bytes()) != identities[k]['sha256'] for k, v in paths.items()):
        raise RuntimeError('capture input changed')
    files = {str(f.relative_to(out)): {'size': f.stat().st_size, 'sha256': sha(f.read_bytes())}
             for f in out.rglob('*') if f.is_file()}
    receipt = {'format': 'fdisbull-private-genesis-scenes-1', 'inputs': identities,
               'frames': a.frames, 'captures': captures, 'files': files,
               'assistance': ('ordinary controller schedule; no memory patches' if a.patches is None else
                              'assisted finite memory interventions before declared frames'),
               'ram_write_observer': {'start': a.trace_start, 'end': a.trace_end,
                                      'custom_pc_ranges': pc_ranges,
                                      'custom_memory_ranges': memory_ranges,
                                      'neutrality': 'not established by capture alone'},
               'scope': 'captured original state; no scene/rule interpretation established'}
    (out / 'capture.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(out / 'capture.json')


if __name__ == '__main__':
    main()
