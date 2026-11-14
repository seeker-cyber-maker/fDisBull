"""Format-level NES/SNES routing for the shared structural discovery pipeline.

Default bank views are explicitly *possible* maps, not observed startup state.
No game names, target offsets, action labels, or original payloads are embedded.
"""
from __future__ import annotations
from hashlib import sha256
from .rom_nes import parse_nes
from .rom_snes import parse_snes
from .rom_sega import parse_genesis
from .structure_patterns import canonical, match_graph, RULES
from .structure_events import SELECTOR_RULE


def _roots(data, windows, vector_addresses):
    def read(a):
        for w in windows:
            if w['cpu_start']<=a<w['cpu_start']+w['size']:
                return data[w['file_start']+a-w['cpu_start']]
        return None
    roots=[]
    for a in vector_addresses:
        lo,hi=read(a),read(a+1)
        if lo is not None and hi is not None:
            target=lo|(hi<<8)
            if target>=0x8000 and read(target) is not None:roots.append(target)
    return sorted(set(roots))


def profiles(data, *, max_views=8):
    """Return admitted static views and explicit omissions for a ROM header.

    Conventional NES mapper 0/66/227, ordinary SNES LoROM (20/30,
    chipset 0..2, <=4 MiB), and candidate zero-based Genesis ROMs are admitted. Other formats get a useful frontier.
    PRG views do not imply that the original actually selects them.
    """
    if type(max_views) is not int or not 1<=max_views<=64: raise ValueError('console view budget outside 1..64')
    header=parse_nes(data)
    if header:
        diagnostics=[];views=[]
        if not header['valid']:return header,views,['invalid or truncated NES container']
        meta=header['metadata']; mapper=meta['mapper']; size=meta['prg_rom_size']
        if mapper not in (0,66,227) or meta.get('submapper') not in (None,0):
            return header,views,['unsupported/ambiguous mapper; supply a qualified CPU/file view']
        prg=next((r for r in header['regions'] if r['kind']=='prg_rom'),None)
        if not prg:return header,views,['no PRG source region']
        start=prg['file_offset'];possible=[]
        if mapper==0:
            if size not in (16384,32768):return header,views,['mapper 0 PRG size outside NROM-128/256']
            windows=[{'cpu_start':0x8000,'file_start':start,'size':size}]
            if size==16384:windows.append({'cpu_start':0xc000,'file_start':start,'size':16384})
            possible=[('nrom',windows,'header-declared NROM mapping')]
        elif mapper==66:
            if size%32768 or not 32768<=size<=131072:return header,views,['mapper 66 PRG geometry unsupported']
            for bank in range(size//32768):
                possible.append((f'gxrom-prg{bank}',[{'cpu_start':0x8000,'file_start':start+bank*32768,'size':32768}],
                                 'candidate 32-KiB bank; runtime latch and board bus-conflict behavior not inferred'))
        else:
            if size%16384 or not 16384<=size<=2*1024*1024:return header,views,['mapper 227 PRG geometry unsupported']
            # Two common fixed-window interpretations. Variant/unusual latch
            # behavior is deliberately not modeled as an automatic transition.
            for bank in range(size//16384):
                possible.append((f'address-latch-mirror16-{bank}',[
                    {'cpu_start':0x8000,'file_start':start+bank*16384,'size':16384},
                    {'cpu_start':0xc000,'file_start':start+bank*16384,'size':16384}],
                    'candidate mirrored 16-KiB window; live address latch not observed'))
                if bank%2==0 and bank+1<size//16384:
                    possible.append((f'address-latch-pair32-{bank}',[
                        {'cpu_start':0x8000,'file_start':start+bank*16384,'size':32768}],
                        'candidate paired 32-KiB window; mapper variants and fixed-upper-bank modes remain unresolved'))
        for ident,windows,claim in possible[:max_views]:
            entries=_roots(data,windows,(0xfffa,0xfffc,0xfffe))
            if entries:views.append({'platform':'NES','mapping_id':ident,'windows':windows,'entries':entries,
                                     'mapper':mapper,'admission':claim})
            else:diagnostics.append(ident+': no mapped vector root')
        if len(possible)>max_views:diagnostics.append(f'view budget: {len(possible)-max_views} candidate maps not scanned')
        return header,views,diagnostics
    header=parse_genesis(data)
    if header:
        md=header['metadata']
        if not header['valid'] or header['platform']!='Sega Genesis / Mega Drive':
            return header,[],['invalid/incomplete or unsupported Sega cartridge profile']
        if md['rom_start']!=0 or md['rom_end']+1>4*1024*1024:
            return header,[],['Genesis linear-ROM candidate requires zero-based ROM at most 4 MiB']
        size=md['rom_end']+1
        entries=sorted({int.from_bytes(data[a:a+4],'big') for a in range(4,256,4)
                        if 0x200<=int.from_bytes(data[a:a+4],'big')<size and int.from_bytes(data[a:a+4],'big')%2==0})
        if not entries:return header,[],['no in-range even Genesis vector entry']
        return header,[{'platform':header['platform'],'mapping_id':'genesis-linear-cartridge-candidate',
            'windows':[{'cpu_start':0,'file_start':0,'size':size}], 'entries':entries,
            'admission':'header-derived linear ROM candidate; cartridge extensions, SRAM mapping and indirect-store mapping effects not established'}],list(header['warnings'])
    header=parse_snes(data)
    if header:
        meta=header['metadata'];views=[]
        if not header['valid'] or meta['layout']!='LoROM' or meta['map_mode'] not in (0x20,0x30) or meta['chipset'] not in (0,1,2):
            return header,views,['unsupported or ambiguous SNES mapping/coprocessor profile']
        size=meta['observed_rom_size'];copier=meta['copier_header_size']
        if size%32768 or not 32768<=size<=4*1024*1024:
            return header,views,['LoROM source geometry outside admitted whole-bank profile']
        windows=[]
        # Upper-half ordinary LoROM windows only. Low-half and irregular-size
        # mirrors are not silently inferred. Alias addresses keep their CPU bank.
        for bank in range(size//32768):
            for cpu_bank in ((bank,bank+0x80) if bank<0x7e else (bank+0x80,)):
                windows.append({'cpu_start':(cpu_bank<<16)|0x8000,'file_start':copier+bank*32768,'size':32768})
        reset=meta['reset_vector']
        entries=[{'cpu_address':reset,'state':{'e':True,'m8':True,'x8':True,'c':None,'dbr':0,'dp':0}}]
        h=meta['header_offset']
        # Interrupt status is inherited from interrupted code: do not assume
        # reset M/X for native interrupt roots.
        for v in (0x2a,0x2e):
            if h+v+2<=len(data):
                dest=int.from_bytes(data[h+v:h+v+2],'little')
                if dest>=0x8000:entries.append({'cpu_address':dest,'state':{'e':False}})
        return header,[{'platform':'SNES','mapping_id':'ordinary-lorom-upper-windows','windows':windows,
                        'entries':entries,'admission':'conventional header-derived LoROM candidate; not live mapping proof'}],[]
    return None,[],[]


def inspect_console(data, *, max_instructions=30000, max_views=8, max_matches=5000, explicit=None):
    """Route file bytes through the ISA fact producer and unchanged shared rules."""
    header,views,diagnostics=profiles(data,max_views=max_views)
    if header is None:return None
    if explicit is not None:
        if not isinstance(explicit,dict) or set(explicit)!={'source_sha256','views'} or explicit['source_sha256']!=sha256(data).hexdigest():
            raise ValueError('console profile must bind the exact source hash')
        if not isinstance(explicit['views'],list) or not 1<=len(explicit['views'])<=max_views:raise ValueError('explicit view budget')
        views=explicit['views']
        for v in views:
            if not isinstance(v,dict) or set(v)-{'platform','mapping_id','windows','entries','mapper','admission'}:
                raise ValueError('invalid explicit console view')
            if v.get('platform')!=header['platform']:raise ValueError('profile platform mismatch')
            if header['platform']=='NES' and v.get('mapper')!=header['metadata']['mapper']:
                raise ValueError('explicit view cannot change the declared mapper')
        diagnostics=['explicit caller-supplied source-pinned mapping/entry views; not independently authenticated']
    facts=[];matches=[];remaining=max_instructions
    for view in views:
        if remaining<=0:
            diagnostics.append('shared console instruction budget exhausted');break
        allowance=max(1,min(remaining,max(256,max_instructions//max(1,len(views)))))
        if view['platform']=='NES':
            from .structure_6502 import probe
            result=probe(data,view['windows'],view['entries'],mapping_id=view['mapping_id'],budget=allowance,mapper=view.get('mapper'))
        elif view['platform']=='Sega Genesis / Mega Drive':
            from .structure_68000 import probe
            result=probe(data,view['windows'],view['entries'],mapping_id=view['mapping_id'],budget=allowance)
        else:
            from .structure_65816 import probe
            result=probe(data,view['windows'],view['entries'],mapping_id=view['mapping_id'],budget=allowance)
        remaining-=result.get('abstract_states_visited',result['decoded_candidate_instructions'])
        m=match_graph(result['nodes'],result['edges'],rules=RULES+(SELECTOR_RULE,),max_matches=max_matches)
        matches.extend(m['matches'])
        facts.append({'view':{k:v for k,v in view.items() if k!='windows'},'windows':view['windows'],
                      'coverage':{k:v for k,v in result.items() if k not in ('nodes','edges','accesses')},
                      'accesses':result['accesses'],'matches':len(m['matches']),
                      'match_budget_exhausted':m['match_budget_exhausted'],'work_budget_exhausted':m['work_budget_exhausted']})
    return {'header':header,'views':facts,'findings':matches,'diagnostics':diagnostics,
            'runtime_observed':False,'execution_authorized':False}
