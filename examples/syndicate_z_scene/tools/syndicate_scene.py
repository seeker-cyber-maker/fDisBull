"""Source-informed Syndicate mission projection and explicit diagnostic relocation.

This is a research adapter, not a complete engine or a generic scene extractor.
Original assets and raw snapshots stay outside this module and public packages.
"""
from __future__ import annotations
from collections import Counter, deque
from dataclasses import dataclass
import hashlib, json, math, struct
from pathlib import Path
from typing import Any

GAME_SIZE = 116010
ROOT_BASE = 6
ENTITY_ORIGIN = 0x8006
TABLES = {'person': (0x8008, 92, 256, 1), 'vehicle': (0xdc08,42,64,2),
          'object': (0xe688,30,400,5), 'weapon': (0x11568,36,512,4),
          'effect': (0x15d68,30,256,3)}
ROLE_NAMES = {1:'civilian',2:'agent',4:'police',8:'guard'}
OBJECT_NAMES = {12:'door',18:'window-open-class',19:'window-closed-class',22:'tree'}
TERRAIN_NAMES = {0:'empty',1:'slope-1',2:'slope-2',3:'slope-3',4:'slope-4',5:'flat',6:'roadside-6',7:'roadside-7',8:'roadside-8',9:'roadside-9',10:'wall',11:'road-curve',12:'handrail/light',13:'roof',14:'crosswalk',15:'road',16:'other-empty-class'}
FLAT_CLASSES = {5,6,7,8,9,11,13,14,15}
CLEAR_CLASSES = {0,12,16}

def u16(b: bytes|bytearray, off:int)->int: return struct.unpack_from('<H', b, off)[0]
def put16(b:bytearray,off:int,value:int)->None: struct.pack_into('<H',b,off,value)
def canonical(x:Any)->str: return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def identify_offset(offset:int)->tuple[str,int,int]|None:
    at=ENTITY_ORIGIN+offset
    if offset==0:return None
    for family,(base,stride,count,_) in TABLES.items():
        rel=at-base
        if 0<=rel<count*stride and rel%stride==0:return family,rel//stride,at
    return None

@dataclass
class Mission:
    data:bytes
    def __post_init__(self):
        if len(self.data)!=GAME_SIZE:raise ValueError('Expected exact selected GAME extent')
    def entities(self)->list[dict]:
        out=[]
        for family,(base,stride,count,kind) in TABLES.items():
            for i in range(count):
                at=base+i*stride;r=self.data[at:at+stride]
                if r[24]!=kind:continue
                rawpos=struct.unpack_from('<HHH',r,4)
                item={'id':f'{family}-{i}','family':family,'slot':i,'source_offset':at,
                      'offset_reference':at-ENTITY_ORIGIN,'next':u16(r,0),'previous':u16(r,2),
                      'position_raw':list(rawpos),'position':[rawpos[0]/256,rawpos[1]/256,rawpos[2]/128],
                      'registered':bool(r[10]&4),'flags':list(r[10:12]),'status_raw':r[25],
                      'health_raw':struct.unpack_from('<h',r,20)[0], 'life_state':'unqualified',
                      'category':OBJECT_NAMES.get(r[25],f'object-class-{r[25]}') if family=='object' else family}
                if family=='person':
                    role=r[28]
                    item.update(role_raw=role,category=ROLE_NAMES.get(role,f'person-class-{role}'),
                                team_member=i<4 and role==2,vehicle_refs=[u16(r,36),u16(r,44)],
                                inventory_head=u16(r,58),selected_weapon_ref=u16(r,68),
                                target_position_raw=list(struct.unpack_from('<HHH',r,46)),
                                stimulants_raw={'adrenaline':list(r[71:74]),'intelligence':list(r[75:78]),'perception':list(r[79:82])})
                elif family=='vehicle':
                    item.update(occupant_ref_candidate=u16(r,28), gate_state='unknown',boarding='unqualified')
                elif family=='weapon':
                    item.update(owner_ref=u16(r,32),inventory_next=u16(r,28),inventory_previous=u16(r,30))
                out.append(item)
        return out
    def graph(self)->dict:
        """Check every live cell chain, including weapons and effects, not just people."""
        seen={};errors=[];chains={}
        for cell in range(128*128):
            ref=u16(self.data,ROOT_BASE+2*cell)
            if not ref:continue
            chain=[];previous=0
            while ref:
                ident=identify_offset(ref)
                if ident is None:
                    errors.append(f'cell {cell}: invalid reference {ref}');break
                if ref in seen:
                    errors.append(f'cell {cell}: repeated/cyclic reference {ref}');break
                family,slot,at=ident
                if len(chain)>1536:raise ValueError('Cell chain traversal budget exceeded')
                r=self.data[at:at+TABLES[family][1]]
                seen[ref]=cell;chain.append(ref)
                if u16(r,2)!=previous:errors.append(f'{ref}: previous link mismatch')
                if not r[10]&4:errors.append(f'{ref}: linked without membership flag')
                if r[24]!=TABLES[family][3]:errors.append(f'{ref}: unexpected kind in active chain')
                expected=((u16(r,6)>>8)&127)*128+((u16(r,4)>>8)&127)
                if expected!=cell:errors.append(f'{ref}: coordinate-cell mismatch')
                previous,ref=ref,u16(r,0)
            chains[cell]=chain
        entities=self.entities()
        flagged={e['offset_reference'] for e in entities if e['registered']}
        if flagged-set(seen):errors.append(f'{len(flagged-set(seen))} flagged entities absent from root chains')
        return {'valid':not errors,'errors':errors,'membership':seen,'chains':chains,
                'entity_count':len(seen),'occupied_cells':len(chains)}
    def objectives(self)->list[dict]:
        """Eight native-consumer records, not ten external-description records."""
        out=[]
        for i in range(8):
            state=struct.unpack_from('<I',self.data,0x1bd32+i*14)[0]
            kind,ref,x,y,z=struct.unpack_from('<HHHHH',self.data,0x1bd36+i*14)
            ident=identify_offset(ref)
            if kind or ref or state:
                out.append({'id':f'objective-{i}','state_raw':state,'type_raw':kind,
                            'target_id':f'{ident[0]}-{ident[1]}' if ident else None,
                            'target_reference':ref,'position_raw':[x,y,z],
                            'interpretation':'assassination candidate' if kind==2 else 'unresolved objective type'})
        return out
    def summary(self, selected='person-0')->dict:
        graph=self.graph()
        if not graph['valid']:raise ValueError('Spatial graph not coherent: '+str(graph['errors'][:5]))
        entities=self.entities();byid={e['id']:e for e in entities};sel=byid[selected]
        active=[e for e in entities if e['offset_reference'] in graph['membership']]
        objectives=self.objectives();targetids={x['target_id'] for x in objectives if x['target_id']}
        ref_ids={e['offset_reference']:e['id'] for e in entities}
        for e in entities:
            e['mission_critical']=e['id'] in targetids
            if e['family']=='weapon':e['owner_id']=ref_ids.get(e['owner_ref'])
            if e['family']=='person':e['inventory_head_id']=ref_ids.get(e['inventory_head'])
        counts=Counter(e['category'] for e in active)
        nearest={}
        for cat in sorted(set(counts)|{'civilian','police','guard','agent','vehicle','door'}):
            candidates=[e for e in active if e['category']==cat and e['id']!=selected]
            if candidates:
                e=min(candidates,key=lambda e:(sum((e['position'][j]-sel['position'][j])**2 for j in (0,1)),e['id']))
                nearest[cat]={'id':e['id'],'position':e['position'],
                              'distance_xy':math.hypot(e['position'][0]-sel['position'][0],e['position'][1]-sel['position'][1]),
                              'same_elevation':e['position'][2]==sel['position'][2],
                              'path_distance':None,'reachable':'unqualified'}
            else:nearest[cat]=None
        return {'schema':'syndicate-diagnostic-scene-research-1','source_state_sha256':digest(self.data),
                'map_number':u16(self.data,0x1bd28),'selected':selected,
                'coordinates':{'x_y_units_per_tile':256,'z_units_per_level':128,'screen_coordinates':False},
                'scope':'global diagnostic registered-entity census; not line-of-sight or alive-count proof',
                'team':[e for e in entities if e.get('team_member')],
                'counts':dict(sorted(counts.items())),'nearest':nearest,'objectives':objectives,
                'entities':active,'spatial_index':{k:graph[k] for k in ['valid','entity_count','occupied_cells']},
                'coverage':{'partial':True,'static_code_complete':False,'visibility':'unknown',
                            'vehicle_gate_relationship':'unqualified','inventory_complete':False}}

class Terrain:
    def __init__(self,map_bytes:bytes,classes:bytes):
        if len(classes)!=256 or len(map_bytes)<12:raise ValueError('Invalid map/class extent')
        self.nx,self.ny,self.nz=struct.unpack_from('<III',map_bytes)
        if not(1<=self.nx<=128 and 1<=self.ny<=128 and 2<=self.nz<=32):raise ValueError('Unsupported dimensions')
        size=self.nx*self.ny
        if len(map_bytes)<12+size*4:raise ValueError('Truncated map directory')
        offsets=struct.unpack_from('<'+'I'*size,map_bytes,12)
        if any(o<size*4 or o+self.nz>len(map_bytes)-12 for o in offsets):raise ValueError('Out-of-bounds map column')
        self.columns=[tuple(classes[t] for t in map_bytes[12+o:12+o+self.nz]) for o in offsets]
        self.map_sha256=digest(map_bytes);self.classes_sha256=digest(classes)
    def column(self,x:int,y:int):
        if not(0<=x<self.nx and 0<=y<self.ny):raise ValueError('Map coordinate out of range')
        return self.columns[y*self.nx+x]
    def classify(self,x:int,y:int,z:int)->dict:
        col=self.column(x,y)
        if not 1<=z<self.nz:return {'candidate':False,'reason':'outside level range'}
        support,occupy=col[z-1],col[z]
        return {'candidate':support in FLAT_CLASSES and occupy in CLEAR_CLASSES,
                'support_class':support,'occupant_class':occupy,
                'reason':'conditional flat support and clearance' if support in FLAT_CLASSES and occupy in CLEAR_CLASSES else 'excluded or unresolved surface/clearance'}
    def plane(self,z:int)->list[list[bool]]:
        return [[self.classify(x,y,z)['candidate'] for x in range(self.nx)] for y in range(self.ny)]
    def components(self,z:int)->dict:
        grid=self.plane(z);labels={};sizes=[]
        for y in range(self.ny):
            for x in range(self.nx):
                if not grid[y][x] or (x,y) in labels:continue
                label=len(sizes);q=deque([(x,y)]);labels[x,y]=label;size=0
                while q:
                    a,b=q.popleft();size+=1
                    for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                        n=(a+dx,b+dy)
                        if 0<=n[0]<self.nx and 0<=n[1]<self.ny and grid[n[1]][n[0]] and n not in labels:
                            labels[n]=label;q.append(n)
                sizes.append(size)
        return {'labels':labels,'sizes':sizes,'grid':grid}
    def path(self,start:tuple[int,int,int],end:tuple[int,int,int])->list|None:
        if start[2]!=end[2]:return None
        z=start[2];a=start[:2];b=end[:2];grid=self.plane(z)
        if not all(0<=x<self.nx and 0<=y<self.ny and grid[y][x] for x,y in (a,b)):return None
        q=deque([a]);prev={a:None}
        while q:
            p=q.popleft()
            if p==b:
                path=[]
                while p is not None:path.append([*p,z]);p=prev[p]
                return path[::-1]
            for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                n=(p[0]+dx,p[1]+dy)
                if 0<=n[0]<self.nx and 0<=n[1]<self.ny and grid[n[1]][n[0]] and n not in prev:prev[n]=p;q.append(n)
        return None

def relocate(data:bytes,entity_id:str,position:tuple[int,int,int])->tuple[bytes,list[dict]]:
    """Model the recovered entity move list operations. Does NOT prove traversability.

    Native source 0x29530 owns the same unlink/relink operations and position
    writes. This deliberately refuses its edge-wrap domain instead of guessing.
    It does not run native code; live application is guarded and separately tested.
    """
    m=Mission(data);g=m.graph()
    if not g['valid']:raise ValueError('Refuse relocation of incoherent spatial lists')
    e=next((e for e in m.entities() if e['id']==entity_id),None)
    if e is None or not e['registered'] or e['family']!='person':raise ValueError('Requires registered person')
    if not e.get('team_member') or e['status_raw']!=0 or any(e['target_position_raw']):
        raise ValueError('Relocation is qualified only for the observed on-foot team raw-state profile')
    if any(e['vehicle_refs']):raise ValueError('Vehicle membership needs an adapter; not an on-foot teleport')
    x,y,z=position
    if any(type(v) is not int for v in position) or not (256<=x<127*256 and 256<=y<95*256 and 0<=z<4096):raise ValueError('Outside admitted relocation domain')
    out=bytearray(data);at=e['source_offset'];ref=e['offset_reference']
    oldcell=g['membership'][ref];newcell=(y>>8)*128+(x>>8)
    if oldcell!=newcell:
        nxt,prev=e['next'],e['previous']
        put16(out,ENTITY_ORIGIN+prev if prev else ROOT_BASE+2*oldcell,nxt)
        if nxt:put16(out,ENTITY_ORIGIN+nxt+2,prev)
        head=u16(out,ROOT_BASE+2*newcell)
        put16(out,at,head);put16(out,at+2,0)
        if head:put16(out,ENTITY_ORIGIN+head+2,ref)
        put16(out,ROOT_BASE+2*newcell,ref)
    struct.pack_into('<HHH',out,at+4,x,y,z)
    after=Mission(bytes(out)).graph()
    if not after['valid'] or after['entity_count']!=g['entity_count']:raise ValueError('Relocation model corrupted spatial index')
    changes=[];i=0
    while i<len(data):
        if data[i]==out[i]:i+=1;continue
        begin=i
        while i<len(data) and data[i]!=out[i]:i+=1
        changes.append({'file_offset':begin,'old_hex':data[begin:i].hex(),'new_hex':bytes(out[begin:i]).hex()})
    return bytes(out),changes
