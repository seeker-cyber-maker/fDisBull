"""Banked native controls for bounded Shadowrun actor and arena models.

The assisted arena has stationary and moving presets; both stop at unsupported
states. The separate static-NPC NROM profile remains available. These targets do
not claim unrestricted AI, a natural encounter, or original timing parity.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .game_il import canonical
from .shadowrun_ai_play import emit_reachable_c, lift_actor_service
from .shadowrun_nes_ai import build_directional_actor_profile
from .shadowrun_assisted_arena import lift_assisted_arena, assisted_arena_from_capture
from .shadowrun_play import machine_from_capture
from .shadowrun_nes_play import build_play
from .shadowrun_play import lift_play
from .shadowrun_replay import _read_rom
from .udc_nes_game import _instrument
from . import shadowrun_ai_play, udc_nes_game, shadowrun_nes_rom_reader
from .shadowrun_nes_rom_reader import emit_arena_reader

BANK_SOURCE=Path(__file__).parent/'game_sources/shadowrun_nes_bank.s'


def _sha(data):return hashlib.sha256(data).hexdigest()


def build_banked_control(manifest_path, *, rom_path, capture, cc65_root, output):
    """Build a private mapper-4 static-play control using banked procedures."""
    return _build(manifest_path,rom_path=rom_path,capture=capture,cc65_root=cc65_root,output=output,profile='static')


def build_banked_directional_control(manifest_path, *, rom_path, capture, cc65_root, output):
    """Build a separate mapper-4 directional diagnostic; actions refuse."""
    return _build(manifest_path,rom_path=rom_path,capture=capture,cc65_root=cc65_root,output=output,profile='directional')


def build_banked_assisted_arena(manifest_path, *, rom_path, capture, cc65_root, output, moving=False):
    """Build the bounded assisted arena; unsupported source states stop."""
    return _build(manifest_path,rom_path=rom_path,capture=capture,cc65_root=cc65_root,output=output,profile='arena',moving=moving)


def _build(manifest_path, *, rom_path, capture, cc65_root, output, profile, moving=False):
    directional=profile=='directional';arena=profile=='arena'
    rom=_read_rom(rom_path);program=lift_assisted_arena(rom) if arena else lift_actor_service(rom) if directional else lift_play(rom)
    entry='shadowrun_arena_frame' if arena else 'shadowrun_ai_frame' if directional else 'shadowrun_play_frame'
    native,selection=emit_reachable_c(program,roots=[entry])
    own=Path(__file__).read_bytes();shim=BANK_SOURCE.read_bytes()
    selector=Path(shadowrun_ai_play.__file__).read_bytes()
    banking=Path(udc_nes_game.__file__).read_bytes()
    reader=Path(shadowrun_nes_rom_reader.__file__).read_bytes()
    root=Path(cc65_root).expanduser().resolve();out=Path(output).expanduser().resolve()
    tools=[root/'bin'/x for x in ('cc65','ca65','ld65','od65','cl65')]+[root/'lib/nes.lib']
    hashes={str(p):_sha(p.read_bytes()) for p in tools}
    if directional:
        base=build_directional_actor_profile(manifest_path,rom_path=rom_path,capture=capture,cc65_root=cc65_root,output=out)
    else:
        base=build_play(manifest_path,rom_path=rom_path,capture=capture,cc65_root=cc65_root,output=out)
    baseline=(out/'play.nes').read_bytes();(out/'baseline.nes').write_bytes(baseline)
    (out/'baseline-receipt.json').write_bytes((out/'play-receipt.json').read_bytes())
    env={k:v for k,v in os.environ.items() if not k.startswith(('CC65_','LD_','DYLD_'))};env['LC_ALL']='C'
    def run(argv):
        result=subprocess.run([str(x) for x in argv],cwd=out,env=env,capture_output=True,text=True,timeout=120)
        if result.returncode:raise ValueError('Banked control build failed: '+result.stderr[-4000:])
        return result.stdout
    source,segments,_=_instrument(native,'S')
    (out/'bank-bootstrap.c').write_text(source)
    run([root/'bin/cc65','-t','nes','-Oirs','--static-locals','bank-bootstrap.c','-o','bank-bootstrap.s'])
    run([root/'bin/ca65','-t','nes','bank-bootstrap.s','-o','bank-bootstrap.o'])
    report=run([root/'bin/od65','-S','bank-bootstrap.o'])
    sizes={k:int(v) for k,v in re.findall(r'^\s*(S\d+):\s*(\d+)\s*$',report,re.M) if k in segments}
    if set(sizes)!=set(segments):raise ValueError('Missing procedure sizes')
    used=[];placement={}
    for seg in sorted(sizes,key=lambda s:(-sizes[s],s)):
        if sizes[seg]>8192:raise ValueError('Procedure exceeds one bank')
        bank=next((i for i,x in enumerate(used) if x+sizes[seg]<=8192),len(used))
        if bank==len(used):used.append(0)
        placement[seg]=bank;used[bank]+=sizes[seg]
    banks={name:placement[seg] for seg,name in segments.items()};objects=[]
    for bank in range(len(used)):
        chunk,mapping,_=_instrument(native,'S',bank=bank,procedure_banks=banks)
        prefix=f'bank-{bank:02d}'
        (out/(prefix+'.c')).write_text(chunk)
        run([root/'bin/cc65','-t','nes','-Oirs','--static-locals',prefix+'.c','-o',prefix+'.s'])
        run([root/'bin/ca65','-t','nes',prefix+'.s','-o',prefix+'.o'])
        report=run([root/'bin/od65','-S',prefix+'.o'])
        actual={k:int(v) for k,v in re.findall(r'^\s*(S\d+):\s*(\d+)\s*$',report,re.M) if k in mapping}
        if set(actual)!=set(mapping) or sum(actual.values())>8192:raise ValueError('Frozen bank placement overflow')
        objects.append(prefix+'.o')
    # The directional seed is kept in its own bank so per-slot initialization
    # does not consume the small fixed-code window.
    if directional or arena:placement['SEEDAI']=len(used)
    data_bank=len(used)+1 if arena else None
    if arena:placement['DATAARENA']=data_bank
    required=len(used)+(1 if directional else 2 if arena else 0)
    # Use a power-of-two PRG size: MMC3 cores may mask fixed-bank indices.
    total=4
    while total<required+2:total*=2
    count=total-2
    platform=(out/'platform.c').read_text()
    def replace_once(text,old,new):
        if text.count(old)!=1:raise ValueError('Arena platform seam changed: '+old[:64])
        return text.replace(old,new,1)
    old=('extern void shadowrun_ai_frame(u8);' if directional else
         'extern void shadowrun_play_frame(u8),shadowrun_seed_scene(void);')
    new=('void banked_call(void);\n#pragma wrapped-call(push,banked_call,bank)\n'
         f'extern void {entry}(u8);\n#pragma wrapped-call(pop)\n'
         + ('extern void shadowrun_bank_init(void);' if directional else
            'extern void shadowrun_seed_scene(void),shadowrun_bank_init(void);'))
    if platform.count(old)!=1 or platform.count('    shadowrun_seed_scene();')!=1:raise ValueError('Platform changed')
    platform=platform.replace(old,new).replace('    shadowrun_seed_scene();','    shadowrun_bank_init();\n    shadowrun_seed_scene();')
    if arena:
        if platform.count('static void play_selection(void) {')!=1 or platform.count('void main(void) {')!=1:
            raise ValueError('Arena platform layout changed')
        platform=platform.replace('static void play_selection(void) {',
            '#pragma code-name(push,"FIXEXTRA")\nstatic void play_selection(void) {',1)
        platform=platform.replace('void main(void) {','#pragma code-name(pop)\nvoid main(void) {',1)
        platform=replace_once(platform,'pad=read_pad();shadowrun_play_frame(pad);',
            'pad=read_pad();if(PUBLICATION[124]) continue;'
            'if(shadowrun_arena_frame_status==3U && (pad&128U)) shadowrun_arena_restart();'
            'shadowrun_arena_frame(pad);'
            'if(shadowrun_arena_frame_status==2U) {'
            'PUBLICATION[124]=1;OAM[40]=8;OAM[41]=1;OAM[42]=1;OAM[43]=240;OAMADDR=0;OAMDMA=2;continue;}')
        platform=replace_once(platform,'PUBLICATION[22]=0;PUBLICATION[23]=0;',
            'PUBLICATION[22]=0;PUBLICATION[23]=0;PUBLICATION[124]=0;')
        platform='extern void shadowrun_arena_restart(void);\n'+platform
        state=assisted_arena_from_capture(rom,Path(capture)/'native/scene-005999',moving=moving).snapshot()
        base_state=machine_from_capture(rom,Path(capture)/'native/scene-005999').snapshot()
        declarations=[];assignments=[]
        from .game_il import GameMachine
        types=GameMachine(program,{0:rom}).global_types
        for name,value in state.items():
            previous=base_state.get(name, [0]*len(value) if isinstance(value,list) else 0)
            if value==previous:continue
            typ=types[name];element=typ[0] if isinstance(typ[0],tuple) else typ
            ctype={8:'u8',16:'u16',32:'u32'}[element[0]];suffix='UL' if element[0]==32 else 'U'
            declarations.append(f'extern {ctype} {name}'+('[];' if isinstance(value,list) else ';'))
            if isinstance(value,list):assignments.extend(f'    {name}[{i}]={v}{suffix};' for i,v in enumerate(value) if v!=previous[i])
            else:assignments.append(f'    {name}={value}{suffix};')
        declarations.append('extern u8 shadowrun_arena_frame_status,shadowrun_arena_burst_active;')
        declarations.append('extern u32 shadowrun_burst_x,shadowrun_burst_y;')
        declarations.append('extern u16 shadowrun_burst_rng,shadowrun_burst_anim_word,shadowrun_reaction_animation,shadowrun_reaction_action_timer;')
        declarations.append('extern u8 shadowrun_burst_counter,shadowrun_burst_lifetime,shadowrun_reaction_counter;')
        declarations.append('extern u16 shadowrun_attack_animation,shadowrun_attack_service_timer,shadowrun_attack_action_timer;')
        declarations.append('extern u16 shadowrun_hostile_x,shadowrun_hostile_y;')
        declarations.append('extern u32 shadowrun_attack_callback;')
        declarations.append('extern u8 shadowrun_attack_counter;')
        platform=platform.replace('#define PPUCTRL','\n'.join(declarations)+'\n#define PPUCTRL',1)
        anchor='    for(i=0;i<256;i++)OAM[i]=0xf0;'
        if platform.count(anchor)!=1:raise ValueError('Arena seed boundary changed')
        platform=platform.replace(anchor,'\n'.join(assignments)+'\n'+anchor,1)
        platform=replace_once(platform,'        PUBLICATION[23]++;PUBLICATION[22]++;',
            '        PUBLICATION[84]=shadowrun_arena_hp;PUBLICATION[85]=shadowrun_arena_frame_status;'
            'PUBLICATION[86]=shadowrun_arena_player_ready;PUBLICATION[87]=shadowrun_arena_burst_active;'
            'PUBLICATION[88]=shadowrun_hostile_ammo;PUBLICATION[89]=shadowrun_play_actor_hp[0];\n'
            '        for(i=0;i<4;i++) {PUBLICATION[90+i]=(u8)(shadowrun_burst_x>>(i*8));PUBLICATION[94+i]=(u8)(shadowrun_burst_y>>(i*8));}\n'
            '        PUBLICATION[98]=(u8)shadowrun_burst_rng;PUBLICATION[99]=(u8)(shadowrun_burst_rng>>8);'
            'PUBLICATION[100]=(u8)shadowrun_burst_anim_word;PUBLICATION[101]=(u8)(shadowrun_burst_anim_word>>8);'
            'PUBLICATION[102]=shadowrun_burst_counter;PUBLICATION[103]=shadowrun_burst_lifetime;'
            'PUBLICATION[104]=(u8)shadowrun_reaction_animation;PUBLICATION[105]=(u8)(shadowrun_reaction_animation>>8);'
            'PUBLICATION[106]=shadowrun_reaction_counter;PUBLICATION[107]=(u8)shadowrun_reaction_action_timer;'
            'PUBLICATION[108]=(u8)(shadowrun_reaction_action_timer>>8);'
            'PUBLICATION[109]=(u8)shadowrun_attack_animation;PUBLICATION[110]=(u8)(shadowrun_attack_animation>>8);'
            'PUBLICATION[111]=(u8)shadowrun_attack_service_timer;PUBLICATION[112]=(u8)(shadowrun_attack_service_timer>>8);'
            'PUBLICATION[113]=(u8)shadowrun_attack_action_timer;PUBLICATION[114]=(u8)(shadowrun_attack_action_timer>>8);'
            'PUBLICATION[115]=shadowrun_attack_counter;'
            'for(i=0;i<4;i++)PUBLICATION[116+i]=(u8)(shadowrun_attack_callback>>(i*8));'
            'PUBLICATION[120]=(u8)shadowrun_hostile_x;PUBLICATION[121]=(u8)(shadowrun_hostile_x>>8);'
            'PUBLICATION[122]=(u8)shadowrun_hostile_y;PUBLICATION[123]=(u8)(shadowrun_hostile_y>>8);\n'
            '        PUBLICATION[23]++;PUBLICATION[22]++;')
        platform=replace_once(platform,'            OAMADDR=0;OAMDMA=2;\n            PPUCTRL=8|',
            '            OAM[52]=8;OAM[53]=2+(shadowrun_arena_hp>>4);OAM[54]=0;OAM[55]=8;'
            'OAM[56]=8;OAM[57]=2+(shadowrun_arena_hp&15);OAM[58]=0;OAM[59]=16;\n'
            '            OAMADDR=0;OAMDMA=2;\n            PPUCTRL=8|')
    if directional or arena:
        start='    shadowrun_seed_scene();\n'
        end='    for(i=0;i<256;i++)OAM[i]=0xf0;'
        if platform.count(start)!=1 or platform.count(end)!=1:raise ValueError('Actor seed layout changed')
        before,tail=platform.split(start,1); seed,after=tail.split(end,1)
        platform=before+start+'    shadowrun_ai_seed_extra();\n'+end+after
        marker='void main(void) {'
        extra=('void banked_call(void);\n#pragma wrapped-call(push,banked_call,bank)\n'
               'void shadowrun_ai_seed_extra(void);\n#pragma wrapped-call(pop)\n'
               '#pragma code-name(push,"SEEDAI")\nvoid shadowrun_ai_seed_extra(void) {\n'+seed+'}\n#pragma code-name(pop)\n')
        if platform.count(marker)!=1:raise ValueError('Platform main changed')
        platform=platform.replace(marker,extra+marker)
    if arena:
        spans=[(0x62b0,0x63f8),(0x6ed0,0x6f30),(0x7320,0x7380),(0x77d4,0x7834),
               (0x8ec4,0x8f04),(0x8ffc,0x9004),(0x9354,0x9360),(0x9e8e,0x9e92),
               (0xa30e,0xa41e),(0xbd72,0xc082),(0x13e7c,0x13f7c),
               (0xa9c6a,0xa9c6c),(0xace14,0xace16),(0xad026,0xad028),(0xad238,0xad23a),
               (0xad24a,0xad24c),(0xad45c,0xad45e),(0xad46e,0xad470),(0xad600,0xad602),(0xad612,0xad614),
               (0xd4540,0xd4780),(0xd4d50,0xd4ea0),(0x166ad4,0x166ad7)]
        if moving:
            spans.extend([(0x8ff4,0x9004),(0x9034,0x90d4),(0x9254,0x9374),
                          (0x9f1e,0x9f20),(0xaa2fa,0xaa2fc)])
            merged=[]
            for lo,hi in sorted(spans):
                if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
                else:merged.append((lo,hi))
            spans=merged
        blob=b''.join(rom[lo:hi] for lo,hi in spans)
        if len(blob)>8192:raise ValueError('Arena data exceeds one bank')
        (out/'arena-tables.bin').write_bytes(blob)
        with (out/'data.s').open('a') as f:f.write('\n.segment "DATAARENA"\n.export _shadowrun_arena_tables\n_shadowrun_arena_tables: .incbin "arena-tables.bin"\n')
        native_reader=emit_arena_reader(spans,data_bank)
        platform=platform.replace('#define PPUCTRL',native_reader.declarations+'#define PPUCTRL',1)
        platform=replace_once(platform,'u8 rom8(u8 region,u32 offset) {','u8 rom8(u8 region,u32 offset) {\n'+native_reader.byte_lookup)
        platform=replace_once(platform,'    if(region!=0) {rom_fault=1;return 0;}\n',
            '    if(region!=0) {rom_fault=1;return 0;}\n'+
            native_reader.word_lookup)
        platform=replace_once(platform,'static void wait_vblank(void)',
            'u32 rom32(u8 region,u32 offset) {return ((u32)rom16(region,offset)<<16)|rom16(region,offset+2UL);}\nstatic void wait_vblank(void)')
    (out/'platform.c').write_text(platform);(out/'bank.s').write_bytes(shim)
    memory=['MEMORY {','ZP: file="", start=$0002, size=$001A, type=rw, define=yes;',
            'HEADER: file=%O,start=$0000,size=$0010,fill=yes;']
    memory += [f'B{i:02d}: file=%O,start=${"A000" if i==data_bank else "8000"},size=$2000,fill=yes,fillval=$FF,bank={i};' for i in range(count)]
    memory += ['FIXDATA: file=%O,start=$C000,size=$2000,fill=yes,fillval=$FF;',
               'FIXCODE: file=%O,start=$E000,size=$1FFA,fill=yes,fillval=$FF;',
               'ROMV: file=%O,start=$FFFA,size=$0006,fill=yes;',
               'ROM1: file=%O,start=$0000,size=$2000,fill=yes;',
               'RAM2: file="",start=$0400,size=$0400,define=yes;',
               'RAM: file="",start=$6000,size=$1E00,define=yes;',
               'STACK: file="",start=$7E00,size=$0200,define=yes;','}',
               'SYMBOLS { __STACKSIZE__: type=weak,value=$0200; }','SEGMENTS {',
               'ZEROPAGE: load=ZP,type=zp;','HEADER: load=HEADER,type=ro;',
               'STARTUP: load=FIXDATA,type=ro,define=yes;',
               'LOWCODE: load=FIXCODE,type=ro,optional=yes;',
               'ONCE: load=FIXDATA,type=ro,optional=yes;',
               'CODE: load=FIXCODE,type=ro,define=yes;',
               'RODATA: load=FIXDATA,type=ro,define=yes;',
               'FIXEXTRA: load=FIXDATA,type=ro,optional=yes;',
               'DATA: load=FIXDATA,run=RAM,type=rw,define=yes;',
               'VECTORS: load=ROMV,type=ro;','CHARS: load=ROM1,type=ro;',
               'BSS: load=RAM,type=bss,define=yes;','BSS2: load=RAM2,type=bss,optional=yes,define=yes;']
    memory += [f'{seg}: load=B{bank:02d},type=ro;' for seg,bank in sorted(placement.items())]
    memory += ['}','FEATURES {','CONDES: type=constructor,label=__CONSTRUCTOR_TABLE__,count=__CONSTRUCTOR_COUNT__,segment=ONCE;',
               'CONDES: type=destructor,label=__DESTRUCTOR_TABLE__,count=__DESTRUCTOR_COUNT__,segment=RODATA;',
               'CONDES: type=interruptor,label=__INTERRUPTOR_TABLE__,count=__INTERRUPTOR_COUNT__,segment=RODATA,import=__CALLIRQ__;','}']
    (out/'banked.cfg').write_text('\n'.join(memory)+'\n')
    run([root/'bin/cl65','-t','nes','-Oirs','-C','banked.cfg','--lib-path',root/'lib',
         '-I',root/'include','-m','banked.map','-Ln','banked-labels.txt','-o','banked.nes',
         *objects,'platform.c','seed.c','data.s','bank.s'])
    built=(out/'banked.nes').read_bytes()
    expected=16+(count+2)*8192+8192
    if built[:4]!=b'NES\x1a' or len(built)!=expected:raise ValueError('Unexpected banked image layout')
    header=bytearray(built[:16]);header[4]=(count+2)//2;header[5]=1
    header[6]=(baseline[6]&0x0f)|0x40;header[7]=0
    image=bytes(header)+built[16:16+(count+2)*8192]+baseline[16+32768:]
    (out/'play.nes').write_bytes(image)
    fresh=lift_assisted_arena(rom) if arena else lift_actor_service(rom) if directional else lift_play(rom)
    if (_read_rom(rom_path)!=rom or canonical(fresh)!=canonical(program) or
        Path(__file__).read_bytes()!=own or BANK_SOURCE.read_bytes()!=shim or
        Path(shadowrun_ai_play.__file__).read_bytes()!=selector or
        Path(udc_nes_game.__file__).read_bytes()!=banking or
        Path(shadowrun_nes_rom_reader.__file__).read_bytes()!=reader or
        any(_sha(p.read_bytes())!=hashes[str(p)] for p in tools)):
        raise ValueError('Banked control inputs changed during build')
    receipt={'format':'fdisbull-shadowrun-mmc3-assisted-arena-1' if arena else 'fdisbull-shadowrun-mmc3-directional-control-1' if directional else 'fdisbull-shadowrun-mmc3-static-control-1','source_rom_sha256':_sha(rom),
             'program_sha256':_sha(canonical(program)),'baseline_sha256':_sha(baseline),
             'output_sha256':_sha(image),'selection':selection,'code_banks':len(used),
             'bank_usage':used,'toolchain_sha256':hashes,'baseline_program_sha256':base['program_sha256'],
             'selector_source_sha256':_sha(selector),'banking_source_sha256':_sha(banking),
             'rom_reader_source_sha256':_sha(reader),
             'scope':'assisted isolated arena; bounded combat and explicit unsupported stops' if arena else 'directional actor mapper diagnostic; actions refuse' if directional else 'static-NPC mapper control; no dynamic AI','executed':False}
    if arena:receipt['arena_preset']='moving' if moving else 'stationary'
    (out/'play-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
