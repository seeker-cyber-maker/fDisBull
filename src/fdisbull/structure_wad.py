"""Read-only classic Doom-family WAD directory and linked-map discovery.

Format-level reader, not a game, renderer, pathfinder or semantic lifter.
Field layout checked against id Software's published doomdata.h / w_wad.h.
No title names, known map counts or original payloads select behavior.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from hashlib import sha256
import re
import struct

MAP_NAME = re.compile(r'(?:E[0-9]M[0-9]|MAP[0-9]{2})\Z')
ORDER = ('THINGS','LINEDEFS','SIDEDEFS','VERTEXES','SEGS','SSECTORS','NODES','SECTORS','REJECT','BLOCKMAP')
STRIDES = {'THINGS':10,'LINEDEFS':14,'SIDEDEFS':30,'VERTEXES':4,'SEGS':12,'SSECTORS':4,'NODES':28,'SECTORS':26}


def _name(raw: bytes) -> str:
    return raw.split(b'\0',1)[0].decode('ascii',errors='backslashreplace')


def inspect_wad(data: bytes, *, max_lumps: int=100000, max_maps: int=256,
                max_records: int=1000000, max_map_bytes: int=128*1024*1024) -> dict | None:
    """Retain directory order/aliases and qualify only the declared classic joins.

    Empty markers are allowed. Duplicate names are not collapsed. No merged
    IWAD/PWAD namespace or active runtime spawn population is inferred.
    """
    if not isinstance(data,bytes): raise TypeError('immutable bytes required')
    if data[:4] not in (b'IWAD',b'PWAD'):return None
    for v,hi in ((max_lumps,100000),(max_maps,1024),(max_records,2000000),(max_map_bytes,512*1024*1024)):
        if type(v) is not int or not 1<=v<=hi:raise ValueError('invalid WAD budget')
    if not 12<=len(data)<=64*1024*1024:raise ValueError('WAD size outside bounded profile')
    count,at=struct.unpack_from('<ii',data,4)
    if not 0<=count<=max_lumps or at<12 or at+count*16>len(data):raise ValueError('WAD directory bounds')
    directory=[]
    for index in range(count):
        pos,size,raw=struct.unpack_from('<ii8s',data,at+index*16)
        if pos<0 or size<0 or pos+size>len(data):raise ValueError(f'lump {index} outside source')
        directory.append({'index':index,'name':_name(raw),'offset':pos,'size':size})
    markers=[i for i,r in enumerate(directory) if MAP_NAME.fullmatch(r['name'])]
    maps=[];unresolved=[];used=0;map_bytes=0
    def payload(r):return data[r['offset']:r['offset']+r['size']]
    for ordinal,index in enumerate(markers):
        if ordinal>=max_maps:
            unresolved.append({'reason':'map budget','remaining_maps':len(markers)-ordinal});break
        marker=directory[index];end=markers[ordinal+1] if ordinal+1<len(markers) else count
        block=directory[index+1:end]
        if any(r['name'] in ('BEHAVIOR','TEXTMAP') for r in block):
            unresolved.append({'directory_index':index,'name':marker['name'],'reason':'extended/UDMF map needs a separate layout profile'});continue
        if tuple(r['name'] for r in block[:10])!=ORDER:
            unresolved.append({'directory_index':index,'name':marker['name'],'reason':'incomplete or nonclassic map lump sequence'});continue
        lumps={r['name']:r for r in block[:10]}
        payload_bytes=sum(r['size'] for r in lumps.values())
        if map_bytes+payload_bytes>max_map_bytes:
            unresolved.append({'directory_index':index,'name':marker['name'],'reason':'map payload work budget'});break
        map_bytes+=payload_bytes
        bad=[n for n,s in STRIDES.items() if lumps[n]['size']%s]
        if bad:
            unresolved.append({'directory_index':index,'name':marker['name'],'reason':'partial fixed-width map record','tables':bad});continue
        counts={n:lumps[n]['size']//s for n,s in STRIDES.items()}
        if used+sum(counts.values())>max_records:
            unresolved.append({'directory_index':index,'name':marker['name'],'reason':'record budget'});break
        used+=sum(counts.values())
        vertices=list(struct.iter_unpack('<hh',payload(lumps['VERTEXES'])))
        lines=list(struct.iter_unpack('<7H',payload(lumps['LINEDEFS'])))
        sides=list(struct.iter_unpack('<hh8s8s8sH',payload(lumps['SIDEDEFS'])))
        sectors=list(struct.iter_unpack('<hh8s8shhh',payload(lumps['SECTORS'])))
        things=list(struct.iter_unpack('<5h',payload(lumps['THINGS'])))
        issues=[];adjacency=[];events=[];tagged=defaultdict(list)
        for si,s in enumerate(sectors):tagged[s[6]].append(si)
        for si,s in enumerate(sides):
            if s[5]>=len(sectors):issues.append({'table':'SIDEDEFS','row':si,'field':'sector','value':s[5]})
        for li,row in enumerate(lines):
            v1,v2,flags,special,tag,front,back=row
            if v1>=len(vertices) or v2>=len(vertices):issues.append({'table':'LINEDEFS','row':li,'field':'vertex'})
            valid_sides=True
            for side in (front,back):
                if side!=65535 and side>=len(sides):
                    valid_sides=False;issues.append({'table':'LINEDEFS','row':li,'field':'side','value':side})
            if front==65535:issues.append({'table':'LINEDEFS','row':li,'field':'front-side-missing'})
            if valid_sides and front!=65535 and back!=65535:
                a,b=sides[front][5],sides[back][5]
                if a<len(sectors) and b<len(sectors):
                    adjacency.append({'line':li,'sectors':[a,b],'flags':flags,'walkable':None})
            if special:
                signed_tag=tag if tag<32768 else tag-65536
                events.append({'line':li,'special_raw':special,'tag_raw':tag,
                    'nonzero_tag_sector_candidates':tagged.get(signed_tag,[]) if tag else [],
                    'trigger':None,'effect':None,'handler':None})
        for si,row in enumerate(struct.iter_unpack('<6H',payload(lumps['SEGS']))):
            if row[0]>=len(vertices) or row[1]>=len(vertices) or row[3]>=len(lines) or row[4]>1:
                issues.append({'table':'SEGS','row':si,'field':'reference'})
        for si,(n,first) in enumerate(struct.iter_unpack('<HH',payload(lumps['SSECTORS']))):
            if first+n>counts['SEGS']:issues.append({'table':'SSECTORS','row':si,'field':'segment extent'})
        for ni,row in enumerate(struct.iter_unpack('<12h2H',payload(lumps['NODES']))):
            for child in row[-2:]:
                limit=counts['SSECTORS'] if child&0x8000 else counts['NODES']
                value=child&0x7fff if child&0x8000 else child
                if value>=limit:issues.append({'table':'NODES','row':ni,'field':'child','value':child})
        maps.append({'id':f"directory:{index}:{marker['name']}",'name':marker['name'],
            'directory_index':index,'counts':counts,'bounds':None if not vertices else {
                'min_x':min(v[0] for v in vertices),'max_x':max(v[0] for v in vertices),
                'min_y':min(v[1] for v in vertices),'max_y':max(v[1] for v in vertices)},
            'tables':{n:{**r,'stride':STRIDES.get(n),'sha256':sha256(payload(r)).hexdigest()} for n,r in lumps.items()},
            'entity_definitions':[{'id':i,'x':t[0],'y':t[1],'angle':t[2],'type_raw':t[3],'options_raw':t[4]&65535,'active':None} for i,t in enumerate(things)],
            'entity_type_histogram':dict(sorted(Counter(t[3] for t in things).items())),
            'sector_adjacency_candidates':adjacency,'event_candidates':events,
            'selected_reference_checks_pass':not issues,'reference_issues':issues,
            'unchecked':['BSP acyclicity/reachability','BLOCKMAP/REJECT contents','texture/resource resolution',
                         'spawn eligibility','movement clearance','special dispatch and runtime effects']})
    duplicate_names={n:c for n,c in Counter(r['name'] for r in directory).items() if c>1}
    return {'format':'classic-wad-discovery-1','container':data[:4].decode(),'source_sha256':sha256(data).hexdigest(),
            'directory_offset':at,'directory':directory,'duplicate_names':duplicate_names,
            'maps':maps,'map_markers':len(markers),'decoded_record_positions':used,'decoded_map_payload_bytes':map_bytes,'unresolved':unresolved,
            'runtime_observed':False,'execution_authorized':False,
            'qualification':'source/spec-assisted layout and selected references, not executable scenes or original equivalence'}
