"""Read-only, bounded Inno 5.x metadata probe. Not a general installer implementation.
Layout cross-checked against dscharrer/innoextract src/{setup,stream}; never runs setup code.
"""
from pathlib import Path
import re,struct,lzma,zlib,json,hashlib
ROOT=Path('/mnt/data/game_intake')
INPUT=Path('/mnt/data')
def u32(b,p):return struct.unpack_from('<I',b,p)[0]
def lzma1(b):
 prop=b[0];ds=u32(b,1)
 if prop>=225 or ds>1<<29:raise ValueError('bad LZMA1 properties')
 return lzma.decompress(b[5:],format=lzma.FORMAT_RAW,filters=[dict(id=lzma.FILTER_LZMA1,dict_size=ds,lc=prop%9,lp=prop//9%5,pb=prop//45)])
def block(b,q):
 crc,n,c=struct.unpack_from('<IIB',b,q)
 if zlib.crc32(b[q+4:q+9])!=crc or q+9+n>len(b):raise ValueError('block header')
 x=b[q+9:q+9+n]; parts=[]
 for st in range(0,len(x),4100):
  p=x[st:st+4100]
  if len(p)<4 or zlib.crc32(p[4:])!=u32(p,0):raise ValueError('block CRC')
  parts.append(p[4:])
 d=b''.join(parts)
 return (lzma1(d) if c else d),q+9+n

def file_record(b,q,maxindex):
 start=q;ss=[]
 for k in range(10):
  n=u32(b,q);q+=4
  if n>16384 or n%2 or q+n>len(b):raise ValueError('string size')
  ss.append(b[q:q+n].decode('utf-16le'));q+=n
 if not re.match(r'^\{[^}]+\}[/\\]',ss[1]):raise ValueError('not destination')
 q+=20
 location,attrs,external,permission,flags,typ=struct.unpack_from('<IIQhIB',b,q);q+=23
 if location>=maxindex or typ not in (0,1):raise ValueError('location')
 return dict(start=start,end=q,source=ss[0],dest=ss[1],font=ss[2],assembly=ss[3],components=ss[4],tasks=ss[5],languages=ss[6],check=ss[7],after=ss[8],before=ss[9],location=location,attributes=attrs,external=external,permission=permission,flags=flags,type=typ),q

def main():
 for p in INPUT.glob('*.exe'):
  if not (p.name.startswith('patch_space_quest_1_') or p.name.startswith('setup_space_quest_1_') or p.name.startswith('setup_ultima_iv_')):continue
  b=p.read_bytes();name='patch' if p.name.startswith('patch') else ('ultima' if 'ultima' in p.name else 'space_quest');out=ROOT/name
  off=json.loads((out/'offsets.json').read_text());h0=(out/'header0.bin').read_bytes();h1,end=block(b,off['header1']);(out/'header1.bin').write_bytes(h1)
  print(name,'secondary',len(h1),'records if74',len(h1)/74,'end',end)
  assert len(h1)%74==0
  entries=[]
  for i in range(len(h1)//74):
   r=h1[i*74:(i+1)*74];first,last,co,fo,fs,cs=struct.unpack_from('<IIIQQQ',r)
   e=dict(index=i,first_slice=first,last_slice=last,chunk_offset=co,file_offset=fo,file_size=fs,chunk_size=cs,sha1=r[36:56].hex(),filetime=int.from_bytes(r[56:64],'little'),flags=int.from_bytes(r[72:74],'little'))
   assert first==last==0
   entries.append(e)
  candidates={}
  for m in re.finditer(b'\\{\\x00',h0):
   # source is empty for these compiled installers; verify full record and later chain.
   st=m.start()-8
   if st<0 or u32(h0,st)!=0:continue
   try:
    rec,_=file_record(h0,st,len(entries));candidates[st]=rec
   except Exception:pass
  # longest exact contiguous chain is the Files table, not script literals.
  chains=[]
  for st in candidates:
   c=[];q=st
   while q in candidates:
    c.append(candidates[q]);q=c[-1]['end']
   chains.append(c)
  chain=max(chains,key=len)
  if {c['location'] for c in chain} != set(range(len(entries))):raise ValueError('file table does not cover all data records')
  print('files',len(chain),'indices',len(set(c['location'] for c in chain)),'range',chain[0]['start'],chain[-1]['end'])
  for r in chain:r['data']=entries[r['location']]
  (out/'file_table.json').write_text(json.dumps(chain,indent=2))
  (out/'data_table.json').write_text(json.dumps(entries,indent=2))
  print('\n'.join(f"{c['location']:3d} {c['data']['file_size']:10d} {c['dest']}" for c in chain[:70]))
  print('first entries',entries[:2]);print('chunk signatures',[(m.start(),b[m.start()+4:m.start()+14].hex()) for m in list(re.finditer(b'zlb\\x1a',b))[:5]])
if __name__=='__main__':main()
