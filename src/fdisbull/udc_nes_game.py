"""Native MMC3 backend for the procedural UIL game profile.

The external cc65 toolchain is explicit and receipt-bound.  Procedures compile
to banked native 6502 code, with statically acyclic calls; no 68000 or UIL
interpreter is embedded in the cartridge.  Original data remains external to
the distributed Python package.
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
from .udl_miniplanets_full import globe_assets, checked_rom, lift_full_game
from .miniplanets_audio import recover_audio, encode_sona

BANK_SIZE = 8192
PRG_BANKS = 64
SOURCE_DIR = Path(__file__).with_name('game_sources')
GAME_INTRINSICS=frozenset(('update_subpixel','mace_x','mace_y','get_tile',
                          'get_collision','set_tile','collides_player'))


def native_index_generator(tree):
    """Use byte offsets for reviewed, in-bounds flat arrays of <=256 bytes.

    cc65 otherwise widens ordinary byte indices during C integer promotion.
    This changes only address calculation in the qualified native domain;
    reference UIL retains its dynamic bounds checks and original syntax tree.
    The element pointer retains signedness and const/volatile qualification.
    """
    _, generators, _ = _parser()
    sizes={'char':1,'signed char':1,'unsigned char':1,'short':2,'signed short':2,
           'unsigned short':2,'int':2,'signed int':2,'unsigned int':2,
           'long':4,'signed long':4,'unsigned long':4}
    aliases={name:(width,name,[]) for name,width in sizes.items()}
    arrays={}
    for node in tree.ext:
        if type(node).__name__=='Typedef' and type(node.type).__name__=='TypeDecl' and type(node.type.type).__name__=='IdentifierType':
            key=' '.join(node.type.type.names)
            if key in aliases:
                width,base,inherited=aliases[key]
                aliases[node.name]=(width,base,[*inherited,*node.quals,*node.type.quals])
        if type(node).__name__!='Decl' or type(node.type).__name__!='ArrayDecl':continue
        arr=node.type
        if type(arr.type).__name__!='TypeDecl' or type(arr.type.type).__name__!='IdentifierType' or type(arr.dim).__name__!='Constant':continue
        name=' '.join(arr.type.type.names)
        info=aliases.get(name)
        try:
            literal=re.sub('[uUlL]+$','',arr.dim.value)
            length=int(literal,16 if literal.lower().startswith('0x') else 8 if literal.startswith('0') and literal!='0' else 10)
        except ValueError:continue
        if info and 0<length*info[0]<=256:
            width,base,inherited=info
            qualifiers=' '.join(dict.fromkeys([*inherited,*node.quals,*arr.type.quals]))
            arrays[node.name]=(width,(qualifiers+' '+base).strip(),(qualifiers+' unsigned char').strip())
    class NativeGenerator(generators.CGenerator):
        hidden=frozenset()
        def visit_FuncDef(self,node):
            saved=self.hidden
            names=set()
            def declarations(item):
                if type(item).__name__ in ('Decl','Typedef') and item.name is not None:names.add(item.name)
                for _,child in item.children():declarations(child)
            declarations(node.decl.type)
            declarations(node.body)
            self.hidden=frozenset(names)
            try:return super().visit_FuncDef(node)
            finally:self.hidden=saved
        def visit_ArrayRef(self,node):
            if type(node.name).__name__=='ID' and node.name.name in arrays and node.name.name not in self.hidden:
                width,element,byte=arrays[node.name.name]
                index=self.visit(node.subscript)
                if width==1:return f'{node.name.name}[(unsigned char)({index})]'
                return f'(*(({element} *)(({byte} *)&{node.name.name} + (unsigned char)(({index}) * {width}U))))'
            return super().visit_ArrayRef(node)
    return NativeGenerator()


def _run(argv, work):
    process = subprocess.run([str(x) for x in argv], cwd=work, capture_output=True,
                             text=True, timeout=120)
    if process.returncode:
        raise ValueError(f'Native game build failed ({Path(str(argv[0])).name}):\n{process.stderr[-12000:]}\n{process.stdout[-2000:]}')
    return process.stdout


def _instrument(source, prefix, external_banked=()):
    """Assign each native procedure its own linkable bank-aware code segment."""
    _, generator, parser = _parser()
    source = re.sub(r'_Pragma\s*\(\s*"(?:\\.|[^"\\])*"\s*\)', '', source)
    tree = parser.CParser().parse(source)
    gen = native_index_generator(tree)
    functions = [node for node in tree.ext if type(node).__name__ == 'FuncDef']
    names = {node.decl.name for node in functions}
    prelude = ['void banked_call(void);']
    for node in tree.ext:
        if type(node).__name__ == 'FuncDef': continue
        if type(node).__name__ == 'Decl' and type(node.type).__name__ == 'FuncDecl' and node.name in names: continue
        if type(node).__name__ == 'Decl' and type(node.type).__name__ == 'FuncDecl' and node.name in external_banked:
            prelude.extend(('#pragma wrapped-call(push,banked_call,bank)',gen.visit(node)+';','#pragma wrapped-call(pop)'))
        else:
            prelude.append(gen.visit(node) + ';')
    prelude.append('void banked_call(void);')
    for node in functions:
        if prefix in ('A','R'):
            # Each hardware adapter is placed wholly in one code bank below;
            # internal calls therefore use ordinary native JSR/RTS directly.
            prelude.append(gen.visit(node.decl)+';')
        else:
            prelude.extend(('#pragma wrapped-call(push,banked_call,bank)', gen.visit(node.decl) + ';', '#pragma wrapped-call(pop)'))
    segments = {}
    for index, node in enumerate(functions):
        if prefix=='G' and node.decl.name in GAME_INTRINSICS:
            # Exact-profile intrinsic, independently checked for every phase.
            # The UIL body remains the reference; GAMEFAST supplies its native
            # bit-reversal lookup implementation without changing state/API.
            continue
        segment = f'{prefix}{index:03d}'
        segments[segment] = node.decl.name
        prelude.extend((f'#pragma code-name(push,"{segment}")', gen.visit(node), '#pragma code-name(pop)'))
    return '\n'.join(prelude) + '\n', segments, tree


def _api(tree):
    _, generator, _ = _parser()
    gen = generator.CGenerator()
    lines = ['void banked_call(void);']
    for node in tree.ext:
        if type(node).__name__ == 'Typedef': lines.append(gen.visit(node) + ';')
    for node in tree.ext:
        kind = type(node).__name__
        if kind == 'Decl' and type(node.type).__name__ != 'FuncDecl' and node.name is not None:
            import copy
            declaration = copy.deepcopy(node)
            declaration.init = None
            declaration.storage = ['extern']
            lines.append(gen.visit(declaration) + ';')
        elif kind == 'FuncDef':
            lines.extend(('#pragma wrapped-call(push,banked_call,bank)', gen.visit(node.decl) + ';', '#pragma wrapped-call(pop)'))
    for declaration in ('void audio_init(void)', 'void audio_request(unsigned char kind,unsigned char id)',
                        'void audio_tick(void)', 'unsigned char audio_busy(void)',
                        'void draw_game(void)'):
        lines.extend(('#pragma wrapped-call(push,banked_call,bank)', declaration + ';', '#pragma wrapped-call(pop)'))
    return '\n'.join(lines) + '\n'


class _DataBanks:
    def __init__(self): self.blocks = []
    def add(self, name, data, *, aligned=False, page_fit=False):
        data = bytes(data)
        if page_fit and len(data)>BANK_SIZE:raise ValueError('Page-fit data is larger than one bank')
        if page_fit and self.blocks and len(self.blocks[-1])+len(data)>BANK_SIZE:aligned=True
        if aligned or not self.blocks: self.blocks.append(bytearray())
        bank, offset = len(self.blocks)-1, len(self.blocks[-1])
        for value in data:
            if len(self.blocks[-1]) == BANK_SIZE: self.blocks.append(bytearray())
            self.blocks[-1].append(value)
        return {'name': name, 'relative_bank': bank, 'offset': offset, 'length': len(data)}


def _header_bytes(name, values, typ='unsigned char'):
    return f'static const {typ} {name}[{len(values)}]={{' + ','.join(str(x) for x in values) + '};\n'


def build_nes_game(program, rom, output, *, cc65_root=None):
    """Build a new private cartridge directory, preserving input identity."""
    checked_rom(rom)
    tree = validate_program(program)
    expected = lift_full_game(rom)['program']
    baseline = lift_full_game(rom,variant='baseline')['program']
    actual_ext=program['tree'].get('ext',[])
    qualified=(len(actual_ext)==len(expected['tree']['ext']) and
               all(actual==efficient or actual==original for actual,efficient,original in
                   zip(actual_ext,expected['tree']['ext'],baseline['tree']['ext'])))
    if (not qualified or program.get('regions') != expected['regions']
            or {key:value for key,value in program['tree'].items() if key!='ext'} !=
               {key:value for key,value in expected['tree'].items() if key!='ext'}):
        raise ValueError('Native game backend accepts only the reviewed Miniplanets source-bound profile')
    machine = GameMachine(program, {0: rom})
    root = Path(cc65_root or os.environ.get('FDISBULL_CC65_ROOT', '')).expanduser().resolve()
    binaries = {name: root/'bin'/name for name in ('cc65','ca65','ld65','od65')}
    if any(not path.is_file() or not os.access(path, os.X_OK) for path in binaries.values()) or not (root/'lib/nes.lib').is_file():
        raise ValueError('Set cc65_root or FDISBULL_CC65_ROOT to a prepared private cc65 toolchain')
    out = Path(output).expanduser().resolve()
    if any((parent/'.git').exists() for parent in (out,*out.parents)):
        raise ValueError('Native game output must be outside Git worktrees')
    if out.exists(): raise ValueError('Native game output must be a new private directory')
    out.mkdir(parents=True)
    work = out/'build';work.mkdir()
    adapter_names=('miniplanets_audio_nes.c','nes_globe_renderer.c','nes_game_platform.c',
                   'nes_game_start.s','miniplanets_audio_fast.s','nes_globe_fast.s','nes_game_fast.s','nes_audio_clock.c')
    adapter_sources={name:(SOURCE_DIR/name).read_bytes() for name in adapter_names}
    tool_hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in binaries.items()}
    runtime_library=(root/'lib/nes.lib').read_bytes()
    (work/'nes.lib').write_bytes(runtime_library)
    for name,raw in adapter_sources.items():(work/name).write_bytes(raw)
    (out/'program.json').write_bytes(canonical(program) + b'\n')
    (work/'game_api.h').write_text(_api(tree))
    source, game_segments, _ = _instrument(emit_c(program), 'G')
    (work/'game.c').write_text(source)
    # Hardware audio/renderer adapters are not game UIL and may use pointers,
    # hardware registers and multidimensional voice state. Preprocessing is
    # confined to explicitly shipped adapter sources and this private build.
    segments = dict(game_segments)
    for name, prefix in (('miniplanets_audio_nes','A'), ('nes_globe_renderer','R')):
        original = work/(name+'.c')
        preprocessed = work/(name+'.i')
        _run([binaries['cc65'],'-E','-t','nes','-I',work,original,'-o',preprocessed],work)
        clean = '\n'.join(line for line in preprocessed.read_text().splitlines() if not line.lstrip().startswith('#'))
        external_banked = {x.decl.name for x in tree.ext if type(x).__name__=='FuncDef'} | {'audio_init','audio_request','audio_tick','audio_busy','audio_render_tick','audio_render_reset','draw_game'}
        adapted, mapping, _ = _instrument(clean, prefix,external_banked)
        segments.update(mapping)
        (work/(name+'.c')).write_text(adapted)
    objects = []
    for name in ('game','miniplanets_audio_nes','nes_globe_renderer'):
        args = [binaries['cc65'],'-t','nes','-Oirs','-I',work,'-g',work/(name+'.c'),'-o',work/(name+'.s')]
        args.insert(4,'--static-locals')
        _run(args,work)
        obj = work/(name+'.o')
        _run([binaries['ca65'],'-t','nes','-g',work/(name+'.s'),'-o',obj],work)
        objects.append(obj)
    special_sizes={}
    for name,segment in (('nes_game_fast','GAMEFAST'),('nes_globe_fast','RENDERFAST')):
        obj=work/(name+'.o')
        _run([binaries['ca65'],'-t','nes','-g',work/(name+'.s'),'-o',obj],work)
        objects.append(obj)
        report=_run([binaries['od65'],'-S',obj],work)
        match=re.search(r'^\s*'+segment+r':\s*(\d+)\s*$',report,re.M)
        if not match:raise ValueError(f'Missing native hot-loop segment: {segment}')
        special_sizes[segment]=int(match.group(1))
    sizes = {}
    for obj in objects:
        report = _run([binaries['od65'],'-S',obj],work)
        for name, size in re.findall(r'^\s*([A-Z][A-Z0-9_]+):\s*(\d+)\s*$',report,re.M):
            if name in segments: sizes[name] = int(size)
    if set(sizes) != set(segments):
        (work/'sizes-debug.txt').write_text('\n'.join(_run([binaries['od65'],'-S',x],work) for x in objects))
        raise ValueError('Could not obtain every native procedure size')
    # First-fit decreasing uses exact assembled sizes. Calls carry ld65's bank
    # attribute, so this placement is independent of procedure source ordering.
    source_sines=rom[0x658F8:0x65B88]
    if len(source_sines)!=656 or source_sines[512:]!=source_sines[:144]:
        raise ValueError('Qualified sine periodicity assumption failed')
    math_data=(bytes(source_sines[i*2+1] for i in range(256))+
               bytes(source_sines[i*2] for i in range(256))+rom[0xA514:0xA614])
    code_used, placements = [special_sizes['GAMEFAST']+len(math_data)], {}
    for name in sorted((x for x in sizes if x.startswith('G')),key=lambda x:(-sizes[x],x)):
        if sizes[name] > BANK_SIZE: raise ValueError(f'Procedure {segments[name]} exceeds an 8KiB code bank')
        bank = next((i for i,n in enumerate(code_used) if n+sizes[name] <= BANK_SIZE),len(code_used))
        if bank == len(code_used): code_used.append(0)
        placements[name]=bank;code_used[bank]+=sizes[name]
    for prefix in ('A','R'):
        members=[x for x in sizes if x.startswith(prefix)]
        total=sum(sizes[x] for x in members)+(special_sizes['RENDERFAST'] if prefix=='R' else 0)
        if total>BANK_SIZE:raise ValueError(f'Native {prefix} adapter exceeds its single-bank direct-call contract')
        bank=len(code_used);code_used.append(total)
        placements.update({name:bank for name in members})
    assets, audio = globe_assets(rom), recover_audio(rom)
    (out/'audio.uil.json').write_bytes(canonical(audio)+b'\n')
    data = _DataBanks()
    bindings = {name:data.add(name,assets[name],aligned=True) for name in ('projection','objects','rafts','ending')}
    atlases=[data.add(f'atlas{i}',frame,page_fit=True) for i,frame in enumerate(assets['terrain_frames'])]
    tracks = [data.add(f'audio{entry["track"]}',encode_sona(entry['event_program']),page_fit=True) for entry in audio['tracks']]
    instrument = [x for item in audio['instruments'] for x in item['nes_meta']]
    bindings['instruments'] = data.add('instruments',instrument,page_fit=True)
    periods = b''.join(x.to_bytes(2,'little') for name in ('pulse_periods','triangle_periods','psg_pulse_periods','psg_triangle_periods') for x in audio[name])
    bindings['periods'] = data.add('periods',periods,aligned=True)
    contract = json.loads(Path(__file__).with_name('data').joinpath('miniplanets_full_contract.json').read_text())
    pages = sorted({address//BANK_SIZE for start,end in contract['immutable_ranges'].values()
                    for address in range(start//BANK_SIZE*BANK_SIZE,end,BANK_SIZE)})
    source_pages = {page:data.add(f'source_page{page}',rom[page*BANK_SIZE:(page+1)*BANK_SIZE],aligned=True) for page in pages}
    first_data = len(code_used)
    if first_data + len(data.blocks) > 62: raise ValueError('Game code and qualified data exceed MMC3 512KiB capacity')
    def physical(binding): return (first_data+binding['relative_bank'])*BANK_SIZE+binding['offset']
    generated = ['#define FIRST_DATA_BANK '+str(first_data)]
    for name,binding in bindings.items():
        generated.extend((f'#define DATA_{name.upper()} {physical(binding)}UL',
                          f'#define BANK_{name.upper()} {physical(binding)//BANK_SIZE}',
                          f'#define OFFSET_{name.upper()} {physical(binding)%BANK_SIZE}'))
    generated.append(_header_bytes('source_page_banks',[first_data+source_pages[i]['relative_bank'] if i in source_pages else 255 for i in range(64)]).replace('static const','const'))
    generated.append(_header_bytes('audio_banks',[physical(x)//BANK_SIZE for x in tracks]))
    generated.append(_header_bytes('audio_starts',[physical(x)%BANK_SIZE for x in tracks],'unsigned int'))
    generated.append(_header_bytes('audio_sizes',[x['length'] for x in tracks],'unsigned int'))
    generated.append(_header_bytes('terrain_palette',[1 if i==3 or i>=23 else 3 if i in (4,9,10,15,18,24) else 2 if i in (1,2,7,16,19,21,22) else 0 for i in range(35)]))
    generated.append(_header_bytes('atlas_offsets',[physical(x) for x in atlases],'unsigned long'))
    generated.append(_header_bytes('ending_ids',assets['ending_ids']).replace('static const','const'))
    generated.append('const unsigned char tile_palette[35]={'+','.join(str(1 if i==3 or i>=23 else 3 if i in (4,9,10,15,18,24) else 2 if i in (1,2,7,16,19,21,22) else 0) for i in range(35))+'};')
    (work/'game_data.h').write_text('\n'.join(generated)+'\n')
    # Debug dispatch is native, uses the same banked calls and typed ABI, and is
    # only entered after the explicit private harness command flag is set.
    _, generator, _ = _parser();gen=generator.CGenerator()
    procedures = [x for x in tree.ext if type(x).__name__=='FuncDef']
    if len(procedures)>=250:raise ValueError('Native game debug procedure budget exceeded')
    debug = ['#include "game_api.h"','unsigned long debug_arg(unsigned char index);',
             'volatile unsigned long *debug_result=(volatile unsigned long*)0x7F0;',
             'void debug_dispatch(unsigned char id){unsigned int audio_i;switch(id){']
    for index,proc in enumerate(procedures):
        params=proc.decl.type.args.params if proc.decl.type.args else []
        if len(params)==1 and type(params[0]).__name__=='Typename':params=[]
        args=','.join(f'debug_arg({i})' for i in range(len(params)))
        call=f'{proc.decl.name}({args})'
        ret=gen.visit(proc.decl.type.type)
        debug.append(f'case {index}: '+(f'{call};*debug_result=0;' if ret.startswith('void') else f'*debug_result={call};')+'break;')
    debug.extend(('case 250:audio_init();*debug_result=0;break;',
                  'case 251:audio_request((unsigned char)debug_arg(0),(unsigned char)debug_arg(1));*debug_result=0;break;',
                  'case 252:for(audio_i=0;audio_i<(unsigned int)debug_arg(0) && audio_i<256;audio_i++)audio_tick();*debug_result=audio_i;break;',
                  'default:*debug_result=0xFFFFFFFFUL;break;}}'))
    (work/'debug.c').write_text('\n'.join(debug))
    # The dispatch itself is banked too; it is absent from the ordinary game
    # hot path and doesn't consume fixed-bank code capacity.
    _run([binaries['cc65'],'-E','-t','nes','-I',work,work/'debug.c','-o',work/'debug.i'],work)
    clean='\n'.join(x for x in (work/'debug.i').read_text().splitlines() if not x.lstrip().startswith('#'))
    # Keep generated banked-call pragmas: unlike hardware source they are the
    # public ABI, so compile debug directly into a dedicated code segment.
    debug_bank=first_data+len(data.blocks)
    if debug_bank+1>=62:raise ValueError('No MMC3 banks available for assisted verifier and fast audio')
    _run([binaries['cc65'],'-t','nes','-Oirs','--code-name','DEBUG','-I',work,work/'debug.c','-o',work/'debug.s'],work)
    _run([binaries['ca65'],'-t','nes',work/'debug.s','-o',work/'debug.o'],work);objects.append(work/'debug.o')
    # Compile the captured adapter bytes, even if another worker edits a source
    # file later. The manifest binds these exact captured bytes, not a reread.
    _run([binaries['cc65'],'-t','nes','-Oirs','-I',work,work/'nes_game_platform.c','-o',work/'platform.s'],work)
    _run([binaries['cc65'],'-t','nes','-Oirs','-I',work,work/'nes_audio_clock.c','-o',work/'clock.s'],work)
    for name in ('platform','clock','nes_game_start','miniplanets_audio_fast'):
        filename=work/(name+'.s')
        _run([binaries['ca65'],'-t','nes','-g',filename,'-o',work/(name+'.o')],work);objects.append(work/(name+'.o'))
    bank_asm=[]
    (work/'native-math.bin').write_bytes(math_data)
    bank_asm.extend(('.segment "GAMEFASTDATA"',
                     '.export _native_sine_lo, _native_sine_hi, _native_collision',
                     '_native_sine_lo: .incbin "native-math.bin",0,256',
                     '_native_sine_hi: .incbin "native-math.bin",256,256',
                     '_native_collision: .incbin "native-math.bin",512,256'))
    for index, block in enumerate(data.blocks):
        filename=f'data{index:02d}.bin';(work/filename).write_bytes(bytes(block).ljust(BANK_SIZE,b'\xff'))
        bank_asm.extend((f'.segment "D{index:03d}"',f'.incbin "{filename}"'))
    (work/'dmc.bin').write_bytes(bytes.fromhex(audio['dpcm_bank_hex']))
    bank_asm.extend(('.segment "DMC"','.incbin "dmc.bin"'))
    (work/'data.s').write_text('\n'.join(bank_asm)+'\n')
    _run([binaries['ca65'],work/'data.s','-o',work/'data.o'],work);objects.append(work/'data.o')
    memory=['MEMORY {','ZP: start=$0002,size=$001A,type=rw,file="";',
            'SRAM: start=$6000,size=$1800,type=rw,file="",define=yes;']
    for i in range(62):memory.append(f'B{i:02d}: start=$8000,size=$2000,file=%O,fill=yes,fillval=$FF,bank={i};')
    memory.extend(('SAMPLES: start=$C000,size=$2000,file=%O,fill=yes,fillval=$55,bank=62;',
                   'FIXED: start=$E000,size=$1FFA,file=%O,fill=yes,fillval=$FF,bank=63;',
                   'VECTOR: start=$FFFA,size=6,file=%O,fill=yes,bank=63;','}','SEGMENTS {',
                   'ZEROPAGE: load=ZP,type=zp;', 'BSS: load=SRAM,type=bss,define=yes;',
                   'DATA: load=FIXED,run=SRAM,type=rw,define=yes;',
                   'STARTUP: load=FIXED,type=ro;', 'CODE: load=FIXED,type=ro;',
                   'RODATA: load=FIXED,type=ro;', 'VECTORS: load=VECTOR,type=ro;',
                   'DMC: load=SAMPLES,type=ro;',f'DEBUG: load=B{debug_bank:02d},type=ro;',
                   f'AUDIOFAST: load=B{debug_bank+1:02d},type=ro;'))
    memory.extend(('GAMEFAST: load=B00,type=ro;','GAMEFASTDATA: load=B00,type=ro;',
                   f'RENDERFAST: load=B{len(code_used)-1:02d},type=ro;'))
    for segment,bank in placements.items():memory.append(f'{segment}: load=B{bank:02d},type=ro;')
    for index in range(len(data.blocks)):memory.append(f'D{index:03d}: load=B{first_data+index:02d},type=ro;')
    memory.append('}')
    (work/'game.cfg').write_text('\n'.join(memory)+'\n')
    _run([binaries['ld65'],'-C',work/'game.cfg','-m',work/'game.map','-Ln',work/'labels.txt',
          '-o',work/'prg.bin',*objects,work/'nes.lib'],work)
    prg=(work/'prg.bin').read_bytes()
    if len(prg)!=PRG_BANKS*BANK_SIZE:raise ValueError('Unexpected MMC3 output size')
    if any(hashlib.sha256(path.read_bytes()).hexdigest()!=tool_hashes[name] for name,path in binaries.items()):
        raise ValueError('Native toolchain changed during compilation')
    cartridge=b'NES\x1a'+bytes((32,1,0x43,0,1,0,0,0,0,0,0,0))+prg+assets['chr']
    (out/'program.nes').write_bytes(cartridge)
    labels={name:int(address,16) for address,name in re.findall(r'^al\s+([0-9A-Fa-f]+)\s+\.?(_[A-Za-z0-9_]+)$',(work/'labels.txt').read_text(),re.M)}
    layout={}
    for name,typ in machine.global_types.items():
        if isinstance(typ[0],tuple):element,length=typ;bits,signed=element
        else:bits,signed=typ;length=1
        address=labels.get('_'+name)
        if address is None or not 0x6000<=address<0x7800:raise ValueError(f'Missing game state label: {name}')
        layout[name]={'address':address,'memory_id':0,'offset':address-0x6000,
                      'length':length*(bits//8),'element_bits':bits,'signed':signed,'array_length':length}
    manifest={'format':'fdisbull-nes-game-1','target':'nes-mmc3','rom_sha256':hashlib.sha256(cartridge).hexdigest(),
              'source_rom_sha256':hashlib.sha256(rom).hexdigest(),'program_sha256':hashlib.sha256(canonical(program)).hexdigest(),
              'program_file_sha256':hashlib.sha256((out/'program.json').read_bytes()).hexdigest(),
              'authoring_variant':'efficient' if program['tree']==expected['tree'] else 'baseline' if program['tree']==baseline['tree'] else 'mixed-qualified',
              'integer_model':program['integer_model'],'mapper':4,'prg_bytes':len(prg),'chr_bytes':len(assets['chr']),
              'state_layout':layout,'procedures':{p.decl.name:i for i,p in enumerate(procedures)},
              'code_banks':code_used,'data_banks':len(data.blocks),'native_procedure_bytes':sum(sizes.values())+sum(special_sizes.values()),
              'native_intrinsics':{'procedures':sorted(GAME_INTRINSICS),
                  'contract':'exact-profile equivalent native bodies; original UIL references retained',
                  'source_sine_sha256':hashlib.sha256(source_sines).hexdigest(),
                  'sine_periodic_extension_words':72,'math_data_sha256':hashlib.sha256(math_data).hexdigest()},
              'address_lowering':'8-bit byte offsets for reviewed in-bounds flat arrays up to256bytes; qualifiers retained',
              'renderer':assets['metrics'],'audio':{'tracks':len(audio['tracks']),'instruments':len(audio['instruments']),
              'dpcm_used_bytes':audio['dpcm_used_bytes'],'arrangement':audio['arrangement']},
              'toolchain':{name:{'sha256':digest} for name,digest in tool_hashes.items()},
              'runtime_resources':{'nes.lib':{'sha256':hashlib.sha256(runtime_library).hexdigest(),
                                            'length':len(runtime_library),'captured_path':'build/nes.lib'}},
              'adapter_sources':{name:hashlib.sha256(raw).hexdigest() for name,raw in adapter_sources.items()},
              'audio_clock':{name:{'memory_id':0,'address':labels['_'+name],'offset':labels['_'+name]-0x6000,'length':2}
                             for name in ('audio_due_slots','audio_served_slots','audio_physical_entries',
                                          'audio_catchup_slots','audio_late_calls','audio_max_owed','audio_late_requests')},
              'debug':{'memory_id':2,'base':0x7D0,'frame_counter':0x7D0,'logic_epoch':0x7D2,
                       'mode':0x7D4,'command':0x7D5,'procedure':0x7D6,'args':0x7D9,'result':0x7F0,
                       'hv_count':0x7EA,'hv_position':0x7EB,'sound_busy':0x7EC,'fault':0x7ED,
                       'audio_init_procedure':250,'audio_request_procedure':251,'audio_ticks_procedure':252,
                       'audio_tick_batch_limit':256},
              'publication':{'memory_id':2,'base':0x700,'slots':4,'stride':48,'head':0x7C0,
                  'hv_count_offset':41,'hv_recording':{'memory_id':0,'offset':0x1F00,'slots':4,'stride':64,'max_words':32,'byte_order':'big'},
                  'sequence':0,'version':1,'epoch':2,'fields':{
                  'input_buttons':[4,1],'joy_hold':[5,1],'joy_press':[6,1],'mode':[7,1],
                  'stage':[8,1],'stage_name':[9,1],'player_x':[10,1],'player_y':[11,1],
                  'player_angle':[12,1],'player_action':[13,1],'player_jump':[14,1],
                  'player_spring':[15,1],'player_win':[16,1],'player_die':[17,1],
                  'keys_left':[18,1],'ingame_status':[19,1],'end_game':[20,1],
                  'time_secs':[21,1],'time_frames':[22,1],'lives':[23,1],'score':[24,4],
                  'anim':[28,2],'subpixel':[30,2],'rng_seed':[32,2],'shake_timer':[34,1],
                  'ending_phase':[35,1],'ending_timer':[36,1],'current_sfx':[37,1],
                  'sfx_to_play':[38,1],'current_bgm':[39,1],'bgm_to_play':[40,1],
                  'ending_fade':[42,1],'clear_phase':[43,1],'clear_timer':[44,1],
                  'sound_busy_input':[45,1],'input_frame':[46,2]}},
              'qualification':'native compiled artifact; requires fresh core execution and original comparisons'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def write_nes_game(program, rom, output, *, cc65_root=None):
    """Publish a build only after all native compile/link checks succeed."""
    from .console_udc import _private_directory
    destination=_private_directory(output)
    temporary=Path(tempfile.mkdtemp(prefix='.nes-game-',dir=destination.parent))
    try:
        result=build_nes_game(program,rom,temporary/'cartridge',cc65_root=cc65_root)
        if destination.exists():raise ValueError('Native output appeared during build')
        (temporary/'cartridge').rename(destination)
    finally:shutil.rmtree(temporary,ignore_errors=True)
    return {'output_directory':str(destination),**result}
