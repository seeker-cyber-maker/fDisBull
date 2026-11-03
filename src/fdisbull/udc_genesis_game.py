"""Compile the reviewed procedural game UIL to native 68000 Genesis code.

Game rules are generated C, not the original game executable. The exact Sona
hardware driver is retained as a source-bound native audio intrinsic; unused
original code remains inert in the preserved ROM prefix. Presentation uses
the quantized cross-console adapter and is qualified separately.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .game_il import GameMachine, canonical, emit_c, validate_program, _parser
from .udl_miniplanets_full import checked_rom, lift_full_game, globe_assets
from .udc_nes_game import _api

SOURCE_DIR=Path(__file__).with_name('game_sources')
ADAPTERS=('genesis_game_platform.c','genesis_game_start.s','genesis_game_renderer.c',
          'genesis_game_audio.c','genesis_game_audio.S','genesis_game_copy.s')
FLAGS=('-m68000','-mshort','-funsigned-char','-fwrapv','-fno-builtin',
       '-ffreestanding','-fno-pic','-fno-pie','-fno-common','-O2',
       '-ffunction-sections','-fdata-sections','-Wno-unknown-pragmas')
TOOLS=('gcc','as','ld','nm','objcopy','readelf')
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def _run(args,cwd):
    env=os.environ.copy()
    for name in tuple(env):
        if name.startswith(('DYLD_','LD_','GCC_')):
            env.pop(name,None)
    for name in ('GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH',
                 'C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH'):
        env.pop(name,None)
    env['LC_ALL']='C'
    r=subprocess.run([str(x) for x in args],cwd=cwd,env=env,
                     capture_output=True,text=True,timeout=180)
    with (cwd/'commands.log').open('a') as f:
        f.write(json.dumps([str(x) for x in args])+'\n'+r.stdout+r.stderr+'\n')
    if r.returncode:raise ValueError('Genesis native build failed:\n'+r.stderr[-8000:])
    return r.stdout


def _qualify(program,rom):
    tree=validate_program(program)
    expected=lift_full_game(rom)['program']
    baseline=lift_full_game(rom,variant='baseline')['program']
    nodes=program['tree']['ext']
    if (len(nodes)!=len(expected['tree']['ext']) or
            any(a!=b and a!=c for a,b,c in zip(nodes,expected['tree']['ext'],baseline['tree']['ext'])) or
            {k:v for k,v in program['tree'].items() if k!='ext'}!=
            {k:v for k,v in expected['tree'].items() if k!='ext'} or
            program['regions']!=expected['regions']):
        raise ValueError('Genesis full-game target requires a reviewed Miniplanets procedural profile')
    return tree,expected,baseline


def _state_info(machine):
    result={};cursor=0
    for name,typ in machine.global_types.items():
        if isinstance(typ[0],tuple):element,count=typ;bits,signed=element
        else:bits,signed=typ;count=1
        length=count*(bits//8)
        result[name]={'length':length,'element_bits':bits,'signed':signed,
                      'array_length':count,'packed_offset':cursor}
        cursor+=length
    if cursor>624:raise ValueError('Genesis publication state exceeds its profile slot')
    return result,cursor


def build_genesis_game(program,rom,output,*,m68k_root):
    rom=checked_rom(rom)
    tree,expected,baseline=_qualify(program,rom)
    machine=GameMachine(program,{0:rom})
    info,state_size=_state_info(machine)
    root=Path(m68k_root).expanduser().resolve()
    binaries={name:root/'bin'/('m68k-elf-'+name) for name in TOOLS}
    if any(not p.is_file() for p in binaries.values()):raise ValueError('Expected a prepared trusted m68k-elf toolchain')
    versions=sorted((root/'lib'/'gcc'/'m68k-elf').glob('*'))
    versions=[p for p in versions if p.is_dir() and (p/'m68000'/'libgcc.a').is_file()]
    if len(versions)!=1:raise ValueError('Expected one qualified m68000 GCC runtime version')
    version=versions[0].name
    prefixes=[root/'libexec'/'gcc'/'m68k-elf'/version,
              root/'m68k-elf'/'bin',versions[0]]
    if not (prefixes[0]/'cc1').is_file() or not (prefixes[0]/'collect2').is_file():
        raise ValueError('Missing trusted GCC compiler helpers')
    compiler_flags=[*FLAGS,*('-B'+str(p)+'/' for p in prefixes)]
    out=Path(output).expanduser().resolve()
    if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):
        raise ValueError('Genesis native output must be new and outside Git')
    out.mkdir(parents=True);work=out/'build';work.mkdir()
    sources={name:(SOURCE_DIR/name).read_bytes() for name in ADAPTERS}
    tools={name:sha(p.read_bytes()) for name,p in binaries.items()}
    for name,raw in sources.items():(work/name).write_bytes(raw)
    (out/'program.json').write_bytes(canonical(program)+b'\n')
    (work/'game.c').write_text(emit_c(program))
    (work/'game_api.h').write_text(_api(tree))
    (work/'original.bin').write_bytes(rom)
    asset=globe_assets(rom)
    arrays={
        'genesis_source_rom':rom,
        'genesis_projection':asset['projection'],
        'genesis_terrain':b''.join(asset['terrain_frames']),
        'genesis_object_projection':asset['objects'],
        'genesis_raft_projection':asset['rafts'],
        'genesis_ending_projection':asset['ending'],
        'genesis_ending_ids':bytes(asset['ending_ids']),
        'genesis_tile_palette':bytes(1 if i==3 or i>=23 else
            3 if i in (4,9,10,15,18,24) else
            2 if i in (1,2,7,16,19,21,22) else 0 for i in range(35)),
        'genesis_chr':asset['chr'],
    }
    asm=['.section .original,"a"','.incbin "original.bin",512',
         '.section .rodata.assets,"a"']
    for name,raw in arrays.items():
        filename=name+'.bin';(work/filename).write_bytes(raw)
        asm.extend(('.even','.globl '+name,name+':',f'.incbin "{filename}"'))
    (work/'assets.s').write_text('\n'.join(asm)+'\n')
    _,gen_module,_=_parser();gen=gen_module.CGenerator()
    functions=[node for node in tree.ext if type(node).__name__=='FuncDef']
    debug=['#include "game_api.h"',
           '#define PROC (*(volatile u16*)0xff1f06UL)',
           '#define ARG ((volatile u32*)0xff1f08UL)',
           '#define RESULT (*(volatile u32*)0xff1f18UL)',
           'void genesis_debug_dispatch(void){switch(PROC){']
    for i,node in enumerate(functions):
        params=node.decl.type.args.params if node.decl.type.args else []
        params=[p for p in params if type(p).__name__!='Typename']
        if len(params)>4:raise ValueError('Genesis diagnostic ABI has four arguments')
        args=','.join('('+gen.visit(p.type)+')ARG['+str(j)+']' for j,p in enumerate(params))
        expression=node.decl.name+'('+args+')'
        returns=gen.visit(node.decl.type.type)
        debug.append(f'case {i}: '+(expression+';RESULT=0;' if returns=='void' else
                                   'RESULT=(u32)'+expression+';')+'break;')
    debug.extend(('default:RESULT=0xffffffffUL;*(volatile u8*)0xff1f1fUL=2;break;','}}'))
    (work/'debug.c').write_text('\n'.join(debug))
    publication=['#include "game_api.h"',
                 'void genesis_copy_bytes(volatile u8 *,const volatile u8 *,u16);',
                 'void genesis_publish_state(void){',
                 'u8 n;volatile u8 *p;const u8 *s;',
                 'u16 epoch=*(volatile u16*)0xff1f02UL;',
                 'p=(volatile u8*)(0xff0000UL+(u32)(epoch&3)*704UL);',
                 'p[0]=(u8)(p[0]+1);p[1]=1;p[2]=(u8)(epoch>>8);p[3]=(u8)epoch;',
                 'p[4]=*(volatile u8*)0xff1f26UL;p[5]=*(volatile u8*)0xff1f27UL;',
                 'p[6]=input_buttons;p[7]=*(volatile u8*)0xff1f1dUL;',
                 'p[8]=*(volatile u8*)0xff1f24UL;']
    for name,item in info.items():
        publication.append(f's=(const u8*)&{name};')
        if item['length']<=4:
            publication.extend(f'p[{16+item["packed_offset"]+i}]=s[{i}];'
                               for i in range(item['length']))
        else:
            publication.append(f'genesis_copy_bytes(p+{16+item["packed_offset"]},s,{item["length"]});')
    publication.extend(('n=p[7];if(n>32)n=32;',
                        f'genesis_copy_bytes(p+{16+state_size},(const volatile u8*)0xff1e00UL,(u16)n*2);',
                        'p[0]=(u8)(p[0]+1);','}'))
    (work/'publication.c').write_text('\n'.join(publication))
    linker='''MEMORY { ROM (rx) : ORIGIN = 0, LENGTH = 4M
 RAM (rwx) : ORIGIN = 0xff2000, LENGTH = 0xd000 }
SECTIONS {
 .vectors 0 : { KEEP(*(.vectors)) } > ROM
 .original 0x200 : { KEEP(*(.original)) } > ROM
 .text 0x80000 : { *(.text.startup) *(.text*) *(.rodata*) } > ROM
 .data : { __data_start = .; *(.data*) __data_end = .; } > RAM AT> ROM
 __data_load = LOADADDR(.data);
 .bss (NOLOAD): { __bss_start = .; *(.bss*) *(COMMON) __bss_end = .; } > RAM
 /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}'''
    (work/'game.ld').write_text(linker)
    objects=[]
    for name in ('game.c',*ADAPTERS,'debug.c','publication.c','assets.s'):
        obj=work/(name.replace('.','_')+'.o')
        _run([binaries['gcc'],*compiler_flags,'-I',work,'-c',work/name,'-o',obj],work)
        objects.append(obj)
    lib=Path(_run([binaries['gcc'],*compiler_flags,'-print-libgcc-file-name'],work).strip()).resolve()
    if not lib.is_file() or not lib.is_relative_to(root):
        raise ValueError('Missing m68k runtime library inside the trusted toolchain')
    (work/'libgcc.a').write_bytes(lib.read_bytes())
    _run([binaries['gcc'],*compiler_flags,'-nostdlib','-Wl,-T,'+str(work/'game.ld'),
          '-Wl,-Map,'+str(work/'game.map'),'-Wl,--gc-sections',*objects,
          work/'libgcc.a','-o',work/'program.elf'],work)
    _run([binaries['objcopy'],'-O','binary',work/'program.elf',work/'raw.bin'],work)
    raw=(work/'raw.bin').read_bytes()
    size=1
    while size<len(raw):size*=2
    if size>4*1024*1024:raise ValueError('Genesis cartridge exceeds unbanked mapping')
    cartridge=bytearray(raw.ljust(size,b'\xff'))
    cartridge[0x100:0x110]=b'SEGA GENESIS    '
    for start in (0x120,0x150):cartridge[start:start+48]=b'FDISBULL UIL MINIPLANETS'.ljust(48,b' ')
    cartridge[0x180:0x18e]=b'GM FDIS-000001'
    cartridge[0x190:0x1a0]=b'J'.ljust(16,b' ')
    cartridge[0x1a0:0x1a4]=(0).to_bytes(4,'big')
    cartridge[0x1a4:0x1a8]=(size-1).to_bytes(4,'big')
    cartridge[0x1a8:0x1ac]=(0xff0000).to_bytes(4,'big')
    cartridge[0x1ac:0x1b0]=(0xffffff).to_bytes(4,'big')
    cartridge[0x1f0:0x200]=b'JUE'.ljust(16,b' ')
    checksum=sum(int.from_bytes(cartridge[i:i+2],'big') for i in range(0x200,size,2))&65535
    cartridge[0x18e:0x190]=checksum.to_bytes(2,'big')
    nm=_run([binaries['nm'],'-n',work/'program.elf'],work)
    (work/'labels.txt').write_text(nm)
    labels={name:int(address,16) for address,kind,name in
            re.findall(r'^([0-9a-fA-F]+)\s+(\S)\s+(\S+)$',nm,re.M)}
    layout={}
    for name,item in info.items():
        address=labels.get(name)
        if address is None or not 0xff2000<=address<0xfff000:raise ValueError('Missing Genesis state symbol: '+name)
        layout[name]={'address':address,'offset':address&65535,'memory_id':2,**item}
    if any(sha((SOURCE_DIR/n).read_bytes())!=sha(raw) for n,raw in sources.items()):
        raise ValueError('Genesis adapter changed during compilation')
    if any(sha(p.read_bytes())!=tools[n] for n,p in binaries.items()):
        raise ValueError('Genesis toolchain changed during compilation')
    (out/'program.md').write_bytes(cartridge)
    manifest={'format':'fdisbull-genesis-game-1','target':'genesis',
              'rom_sha256':sha(cartridge),'source_rom_sha256':sha(rom),
              'program_sha256':sha(canonical(program)),'integer_model':'cc65-int16-long32',
              'state_layout':layout,'procedures':{p.decl.name:i for i,p in enumerate(functions)},
              'adapter_sources':{n:sha(b) for n,b in sources.items()},
              'toolchain':{n:{'sha256':d} for n,d in tools.items()},
              'runtime_resources':{'libgcc.a':{'sha256':sha((work/'libgcc.a').read_bytes())}},
              'compiler_flags':list(FLAGS),'rom_size':size,
              'compiler_environment':'LC_ALL=C; compiler, include-path and dynamic-loader overrides removed',
              'native_rule_entries':{n:labels[n] for n in ('game_boot','game_frame')},
              'debug':{'memory_id':2,'base':0x1f00,'frame_counter':0x1f00,
                       'logic_epoch':0x1f02,'mode':0x1f04,'command':0x1f05,
                       'procedure':0x1f06,'procedure_bytes':2,'args':0x1f08,
                       'result':0x1f18,'hv_count':0x1f1c,'hv_position':0x1f1d,
                       'sound_busy':0x1f1e,'fault':0x1f1f,'events_count':0x1f20,
                       'event_kind':0x1f22,'event_id':0x1f23,'hv_tape':0x1e00,'max_hv_words':32},
              'publication':{'memory_id':2,'base':0,'slots':4,'stride':704,'sequence':0,
                             'version':1,'epoch':2,'input_frame':4,'input_buttons':6,
                             'hv_count':7,'sound_busy_input':8,'state_offset':16,
                             'state_size':state_size,'hv_offset':16+state_size,'max_hv_words':32,
                             'state_fields':{n:{**i,'offset':i['packed_offset']} for n,i in info.items()}},
              'architectural_byte_order':'big','host_ram_mapping':'pinned-core absolute architectural address xor1',
              'presentation':'adapted quantized globe; not original Genesis pixel parity',
              'audio':'original Sona device driver retained at original addresses; autonomous Z80 timing',
              'retained_original_code':{'range':[0x200,0x80000],
                  'purpose':'preserve exact audio driver/data addresses; old game code is not the compiled rule implementation',
                  'allowed_audio_entrypoints':[0xd5c,0xed0,0xee4,0xf2c,0xfb6],
                  'execution_qualified':False},
              'execution':'not run by compiler; separate full-state, native display/audio and instruction-fetch qualification required'}
    (out/'manifest.json').write_bytes(canonical(manifest)+b'\n')
    return manifest


def write_genesis_game(program,rom,output,*,m68k_root):
    from .console_udc import _private_directory
    destination=_private_directory(output)
    temporary=Path(tempfile.mkdtemp(prefix='.genesis-game-',dir=destination.parent))
    staging=temporary/'cartridge'
    try:
        result=build_genesis_game(program,rom,staging,m68k_root=m68k_root)
        if destination.exists():raise ValueError('Genesis output appeared during compilation')
        staging.rename(destination)
    finally:shutil.rmtree(temporary,ignore_errors=True)
    return {'output_directory':str(destination),**result}
