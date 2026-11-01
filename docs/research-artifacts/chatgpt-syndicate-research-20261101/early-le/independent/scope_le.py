#!/usr/bin/env python3
"""Independent physical accounting for the qualified Syndicate LE profile.

This script imports no fDisBull code. Grammar follows Open Watcom's exeflat.h,
loadflat.c and wdfix.c at 5474be3542af05eee71be05fafc31bbe11f1415b.
It reads an immutable source once, retains physical and virtual coordinates,
and does not execute or rewrite the program. Zero fill is not a deletion rule.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import struct

DW_NAMES = '''version flags num_pages start_obj eip stack_obj esp page_size last_page
fixup_size fixup_cksum loader_size loader_cksum objtab_off num_objects objmap_off
idmap_off rsrc_off num_rsrcs resname_off entry_off moddir_off num_moddirs fixpage_off
fixrec_off impmod_off num_impmods impproc_off cksum_off page_off num_preload
nonres_off nonres_size nonres_cksum autodata_obj debug_off debug_len num_inst_preload
num_inst_demand heapsize stacksize'''.split()
OBJ_FLAGS = {1:'readable',2:'writable',4:'executable',8:'resource',16:'discardable',
 32:'shareable',64:'preload',128:'invalid_pages',256:'permanent_swappable',
 512:'permanent_resident',1024:'long_lockable',4096:'alias16',8192:'default32',
 16384:'conforming',32768:'io_privilege'}


def scope(path: Path) -> tuple[dict, list[dict]]:
    data = path.read_bytes()
    if not 64 <= len(data) <= 64*1024*1024:
        raise ValueError('Bounded source size must be 64 bytes through 64 MiB')

    def take(at: int, size: int) -> bytes:
        if at < 0 or size < 0 or at + size > len(data):
            raise ValueError(f'Out-of-file extent {at:#x}+{size:#x}')
        return data[at:at+size]

    def word(at: int) -> int:
        return struct.unpack('<H',take(at,2))[0]

    def dword(at: int) -> int:
        return struct.unpack('<I',take(at,4))[0]

    if take(0,2) != b'MZ':
        raise ValueError('This scoped profile requires an MZ bootstrap')
    mz_words = struct.unpack('<14H',take(0,28))
    mz_names = ['signature','last_page_bytes','page_count','relocation_count',
      'header_paragraphs','minimum_extra_paragraphs','maximum_extra_paragraphs',
      'initial_ss','initial_sp','checksum','initial_ip','initial_cs',
      'relocation_table_offset','overlay_number']
    mz = dict(zip(mz_names,mz_words))
    mz_header_size = mz['header_paragraphs']*16
    mz_end = (mz['page_count']-1)*512 + (mz['last_page_bytes'] or 512)
    le = dword(60)
    if not 64 <= mz_header_size <= mz_end <= le:
        raise ValueError('Unexpected MZ/LE relationship')
    if take(le,2) != b'LE' or take(le+2,2) != b'\0\0':
        raise ValueError('Only little-endian LE is qualified')
    header = {'signature':'LE','byte_order':data[le+2],'word_order':data[le+3],
      'level':dword(le+4),'cpu_type':word(le+8),'os_type':word(le+10)}
    header.update(zip(DW_NAMES,struct.unpack('<41I',take(le+12,164))))
    header['reserved_bytes_hex'] = take(le+176,20).hex()
    if header['level'] != 0 or header['page_size'] != 4096:
        raise ValueError('Only level-zero 4096-byte LE profile is qualified')
    if not (0 < header['num_objects'] <= 4096 and 0 < header['num_pages'] <= 16384):
        raise ValueError('Object/page budget exceeded')
    # Inactive optional tables are recorded, not guessed into file spans.
    unsupported = [n for n in ('idmap_off','num_rsrcs','num_moddirs','num_impmods',
      'cksum_off','nonres_size','debug_len') if header[n]]
    if unsupported:
        raise ValueError('Active optional tables outside this independent profile: '+', '.join(unsupported))

    segments = []
    def segment(start:int,end:int,kind:str,label:str,**extra):
        take(start,end-start)
        if end > start:
            segments.append({'start':start,'end_exclusive':end,'bytes':end-start,
              'kind':kind,'label':label,**extra})

    segment(0,28,'mz_header','MZ fixed DOS fields')
    segment(28,64,'mz_header','MZ extension/reserved fields and LE pointer')
    reloc_start = mz['relocation_table_offset']
    reloc_end = reloc_start + mz['relocation_count']*4
    if not 64 <= reloc_start <= reloc_end <= mz_header_size:
        raise ValueError('Unexpected MZ relocation table range')
    if reloc_start > 64:
        segment(64,reloc_start,'mz_header_gap','MZ header gap',all_zero=not any(take(64,reloc_start-64)))
    segment(reloc_start,reloc_end,'mz_relocation_table','MZ segment relocation records')
    segment(reloc_end,mz_header_size,'mz_header_padding','MZ paragraph padding',all_zero=not any(take(reloc_end,mz_header_size-reloc_end)))
    segment(mz_header_size,mz_end,'mz_load_image','DOS bootstrap code and data; mixed contents')
    segment(mz_end,le,'inter_image_gap','Zero-filled MZ-to-LE gap',all_zero=not any(take(mz_end,le-mz_end)))
    segment(le,le+196,'le_header','LE fixed header, including 20 reserved bytes')

    mz_relocations=[]
    for i in range(mz['relocation_count']):
        off,seg=struct.unpack('<2H',take(reloc_start+i*4,4))
        source=mz_header_size+seg*16+off
        if not mz_header_size<=source<source+2<=mz_end:
            raise ValueError('MZ relocation outside load image')
        mz_relocations.append({'record_offset':reloc_start+i*4,'segment':seg,
          'offset':off,'source_file_offset':source,'original_word':word(source)})
    mz.update({'header_bytes':mz_header_size,'declared_end_exclusive':mz_end,
      'load_image_bytes':mz_end-mz_header_size,'entry_file_offset':mz_header_size+mz['initial_cs']*16+mz['initial_ip'],
      'relocations':mz_relocations})

    objects=[]
    for i in range(header['num_objects']):
        at=le+header['objtab_off']+24*i
        size,base,flags,first,count,reserved=struct.unpack('<6I',take(at,24))
        objects.append({'ordinal':i+1,'record_offset':at,'virtual_size':size,
          'preferred_base':base,'preferred_end_exclusive':base+size,'flags':flags,
          'flag_names':[name for bit,name in OBJ_FLAGS.items() if flags&bit],
          'first_page_map_index':first,'page_map_count':count,'reserved':reserved})
    if sum(o['virtual_size'] for o in objects)>64*1024*1024:
        raise ValueError('Mapped byte budget exceeded')
    segment(le+header['objtab_off'],le+header['objtab_off']+24*len(objects),'object_table','Four LE object records')
    pages=[]
    memory={o['ordinal']:bytearray(o['virtual_size']) for o in objects}
    ownership={}
    for o in objects:
        for i in range(o['page_map_count']):
            logical=o['first_page_map_index']+i
            if logical in ownership or not 1<=logical<=header['num_pages']:
                raise ValueError('Invalid logical-page ownership')
            ownership[logical]=(o,i)
    for i in range(header['num_pages']):
        at=le+header['objmap_off']+4*i
        record=take(at,4)
        physical=int.from_bytes(record[:3],'big')
        flags=record[3]
        if flags or not 1<=physical<=header['num_pages']:
            raise ValueError('This observed profile contains only enumerated physical pages')
        if i+1 not in ownership:
            raise ValueError('Unowned logical page')
        o,local_page=ownership[i+1]
        off=header['page_off']+(physical-1)*header['page_size']
        storage_size=header['last_page'] if physical==header['num_pages'] else header['page_size']
        if not 0<storage_size<=header['page_size']:
            raise ValueError('Unexpected physical page size')
        take(off,storage_size)
        object_offset=local_page*header['page_size']
        mapped_size=min(storage_size,max(0,o['virtual_size']-object_offset))
        memory[o['ordinal']][object_offset:object_offset+mapped_size]=take(off,mapped_size)
        page={'logical_page':i+1,'record_offset':at,'physical_page':physical,
          'flags':flags,'object':o['ordinal'],'object_offset':object_offset,
          'file_start':off,'physical_bytes':storage_size,'mapped_bytes':mapped_size,
          'virtual_start':o['preferred_base']+object_offset,'slack_bytes':storage_size-mapped_size}
        pages.append(page)
        segment(off,off+mapped_size,'mapped_payload',f"Object {o['ordinal']} file-backed payload",object=o['ordinal'])
        if storage_size>mapped_size:
            segment(off+mapped_size,off+storage_size,'page_slack',f"Object {o['ordinal']} final-page slack",object=o['ordinal'],all_zero=not any(take(off+mapped_size,storage_size-mapped_size)))
    segment(le+header['objmap_off'],le+header['objmap_off']+4*len(pages),'page_map','LE object page map')
    if len({p['physical_page'] for p in pages})!=len(pages):
        raise ValueError('Physical page alias outside this profile')

    # Resident names use length-prefixed bytes followed by a 16-bit ordinal.
    cursor=le+header['resname_off']; names=[]
    while True:
        length=take(cursor,1)[0];cursor+=1
        if not length: break
        text=take(cursor,length);ordinal=word(cursor+length)
        names.append({'name':text.decode('ascii','backslashreplace'),'ordinal':ordinal})
        cursor+=length+2
        if len(names)>4096:raise ValueError('Resident-name budget exceeded')
    segment(le+header['resname_off'],cursor,'resident_names','Resident name and zero terminator')
    # This selected executable has an empty export-entry bundle table.
    entry=le+header['entry_off']
    if take(entry,1)!=b'\0':raise ValueError('Nonempty entry table outside this profile')
    segment(entry,entry+1,'entry_table','Empty entry-table terminator')

    fixpage=le+header['fixpage_off'];fixrec=le+header['fixrec_off']
    fixoffsets=list(struct.unpack('<'+str(len(pages)+1)+'I',take(fixpage,4*(len(pages)+1))))
    if fixoffsets[0]!=0 or any(a>b for a,b in zip(fixoffsets,fixoffsets[1:])):
        raise ValueError('Nonmonotone fixup page table')
    segment(fixpage,fixpage+4*(len(pages)+1),'fixup_page_table','Fixup page offsets and final sentinel')
    segment(fixrec,fixrec+fixoffsets[-1],'fixup_records','Internal offset32 fixup records')
    before_hash={i:sha256(mem).hexdigest() for i,mem in memory.items()}
    fixups=[];writes={};source_flags=Counter();target_flags=Counter();matrix=Counter()
    for p in pages:
        pageindex=p['logical_page']-1
        cursor=fixrec+fixoffsets[pageindex];end=fixrec+fixoffsets[pageindex+1]
        o=objects[p['object']-1]
        while cursor<end:
            start=cursor
            st,tf=take(cursor,2);cursor+=2
            if st!=7 or tf not in (0,16):raise ValueError('Unqualified fixup form')
            source_offset=struct.unpack('<h',take(cursor,2))[0];cursor+=2
            ordinal=take(cursor,1)[0];cursor+=1
            width=4 if tf&16 else 2
            target_offset=int.from_bytes(take(cursor,width),'little');cursor+=width
            if cursor>end or not 1<=ordinal<=len(objects):raise ValueError('Invalid fixup record boundary/ordinal')
            target=objects[ordinal-1]
            if not 0<=target_offset<=target['virtual_size']:raise ValueError('Target outside declared object')
            relative=p['object_offset']+source_offset
            if not 0<=relative<=o['virtual_size']-4:raise ValueError('Source write outside object')
            address=o['preferred_base']+relative
            value=target['preferred_base']+target_offset
            original=int.from_bytes(memory[o['ordinal']][relative:relative+4],'little')
            record={'record_offset':start,'record_bytes':cursor-start,'logical_page':p['logical_page'],
              'source_type':st,'target_flags':tf,'source_page_offset':source_offset,
              'source_object':o['ordinal'],'source_object_offset':relative,'source_address':address,
              'target_object':ordinal,'target_offset':target_offset,'relocated_value':value}
            fixups.append(record);source_flags[st]+=1;target_flags[tf]+=1;matrix[(o['ordinal'],ordinal)]+=1
            if address in writes:
                if writes[address]['value']!=value:raise ValueError('Conflicting duplicate write')
                writes[address]['records'].append(start)
            else:
                writes[address]={'object':o['ordinal'],'offset':relative,'value':value,
                  'original_value':original,'records':[start]}
    addresses=sorted(writes)
    if any(a+4>b for a,b in zip(addresses,addresses[1:])):
        raise ValueError('Nonidentical overlapping relocation writes')
    for address,w in writes.items():
        memory[w['object']][w['offset']:w['offset']+4]=w['value'].to_bytes(4,'little')
    # The empty import-module table occupies zero bytes. Offset zero is reserved
    # in the import procedure-name table, represented by this one zero byte.
    imports=le+header['impproc_off']
    if take(imports,1)!=b'\0':raise ValueError('Unexpected empty import-procedure sentinel')
    segment(imports,imports+1,'import_procedure_table','Empty import-procedure table zero sentinel')

    ordered=sorted(segments,key=lambda x:(x['start'],x['end_exclusive']))
    partition=[];cursor=0
    for s in ordered:
        if s['start']<cursor:raise ValueError('Overlapping physical ownership: '+s['label'])
        if s['start']>cursor:
            gap=take(cursor,s['start']-cursor)
            partition.append({'start':cursor,'end_exclusive':s['start'],'bytes':len(gap),
              'kind':'unassigned_zero_gap' if not any(gap) else 'unexplained_nonzero_gap',
              'label':'Unassigned inter-section gap','all_zero':not any(gap)})
        partition.append(s);cursor=s['end_exclusive']
    if cursor<len(data):
        gap=take(cursor,len(data)-cursor)
        partition.append({'start':cursor,'end_exclusive':len(data),'bytes':len(gap),
          'kind':'unassigned_zero_tail' if not any(gap) else 'unexplained_nonzero_tail',
          'label':'Unassigned trailing bytes','all_zero':not any(gap)})
    # Coalesce adjacent physical runs with identical structural ownership.
    merged=[]
    for s in partition:
        props={k:v for k,v in s.items() if k not in ('start','end_exclusive','bytes')}
        if merged and merged[-1]['end_exclusive']==s['start'] and {k:v for k,v in merged[-1].items() if k not in ('start','end_exclusive','bytes')}==props:
            merged[-1]['end_exclusive']=s['end_exclusive'];merged[-1]['bytes']+=s['bytes']
        else:merged.append(dict(s))
    if not merged or merged[0]['start']!=0 or merged[-1]['end_exclusive']!=len(data) or sum(s['bytes'] for s in merged)!=len(data):
        raise ValueError('Incomplete physical partition')
    for a,b in zip(merged,merged[1:]):
        if a['end_exclusive']!=b['start']:raise ValueError('Gap/overlap in final ledger')

    gaps=[]
    sorted_objects=sorted(objects,key=lambda o:o['preferred_base'])
    for a,b in zip(sorted_objects,sorted_objects[1:]):
        if a['preferred_end_exclusive']>b['preferred_base']:raise ValueError('Overlapping virtual objects')
        if a['preferred_end_exclusive']<b['preferred_base']:
            gaps.append({'start':a['preferred_end_exclusive'],'end_exclusive':b['preferred_base'],
              'bytes':b['preferred_base']-a['preferred_end_exclusive']})
    for o in objects:
        op=[p for p in pages if p['object']==o['ordinal']]
        mapped=sum(p['mapped_bytes'] for p in op)
        o.update({'physical_page_bytes':sum(p['physical_bytes'] for p in op),
          'file_backed_bytes':mapped,'zero_filled_bytes':o['virtual_size']-mapped,
          'unrelocated_mapped_sha256':before_hash[o['ordinal']],
          'relocated_mapped_sha256':sha256(memory[o['ordinal']]).hexdigest()})
    duplicates=[{'source_address':address,**write} for address,write in writes.items() if len(write['records'])>1]
    loader_start=le+header['objtab_off'];loader_end=loader_start+header['loader_size']
    fixup_end=fixpage+header['fixup_size']
    take(loader_start,header['loader_size']);take(fixpage,header['fixup_size'])
    output={'format':'independent-le-physical-scope-1','source_path':str(path),'file_bytes':len(data),
      'basis':'Open Watcom exeflat.h/loadflat.c/wdfix.c at 5474be3542af05eee71be05fafc31bbe11f1415b; no fDisBull imports',
      'mz':mz,'le_header_offset':le,'le_header':header,'objects':objects,'pages':pages,
      'resident_names':names,'entry_bundle_count':0,
      'declared_aggregates':{'loader':{'start':loader_start,'end_exclusive':loader_end,'bytes':header['loader_size']},
        'fixup':{'start':fixpage,'end_exclusive':fixup_end,'bytes':header['fixup_size']},
        'overlap_note':'This executable declares a loader extent containing the fixup extent; aggregate extents must not be added as disjoint byte counts.'},
      'physical_partition':merged,'preferred_virtual_gaps':gaps,
      'fixups':{'record_count':len(fixups),'record_bytes':fixoffsets[-1],'unique_four_byte_writes':len(writes),
        'source_type_counts':dict(source_flags),'target_flag_counts':dict(target_flags),
        'source_target_object_record_counts':[{'source_object':s,'target_object':t,'records':n} for (s,t),n in sorted(matrix.items())],
        'duplicates':duplicates,'one_past_object_target_records':sum(r['target_offset']==objects[r['target_object']-1]['virtual_size'] for r in fixups)},
      'totals':{'accounted_file_bytes':sum(s['bytes'] for s in merged),'physical_payload_bytes':sum(p['physical_bytes'] for p in pages),
        'mapped_source_bytes':sum(o['file_backed_bytes'] for o in objects),'page_slack_bytes':sum(p['slack_bytes'] for p in pages),
        'mapped_virtual_bytes':sum(o['virtual_size'] for o in objects),'zero_filled_virtual_bytes':sum(o['zero_filled_bytes'] for o in objects),
        'unexplained_nonzero_file_bytes':sum(s['bytes'] for s in merged if s['kind'].startswith('unexplained_nonzero')),
        'unassigned_zero_gap_bytes':sum(s['bytes'] for s in merged if s['kind'].startswith('unassigned_zero'))},
      'limits':['Physical accounting is complete for this selected profile; mixed code/data semantics and runtime reachability are not recovered.',
        'The 398-byte zero inter-section gap is accounted but no original linker/consumer deletion experiment was performed.',
        'MZ bootstrap load-image contents are mixed code/data; external extender search/dispatch needs separate instruction evidence.',
        'IBM Revision 11 clarified the historical debug-offset erratum: debug offsets are file-relative. This file has no active debug table, so that parser path is not exercised.',
        'The 524-byte physical page slack lies outside the exact declared object extent, but may still be copied or accessed in a rounded native allocation; neither native behavior nor deletion safety is established.',
        'No native execution, runtime selector mapping, generic LE/LX support or runnable rewriting is claimed.']}
    return output,fixups


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input',type=Path)
    parser.add_argument('output_directory',type=Path)
    args=parser.parse_args()
    report,fixups=scope(args.input)
    args.output_directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    (args.output_directory/'le-physical-scope.json').write_text(json.dumps(report,indent=2)+'\n')
    (args.output_directory/'independent-fixup-records.json').write_text(json.dumps(fixups,separators=(',',':'))+'\n')
    print(json.dumps({'report':str(args.output_directory/'le-physical-scope.json'),
      'totals':report['totals'],'fixup_records':report['fixups']['record_count'],
      'physical_ranges':len(report['physical_partition'])},indent=2))

if __name__=='__main__':main()
