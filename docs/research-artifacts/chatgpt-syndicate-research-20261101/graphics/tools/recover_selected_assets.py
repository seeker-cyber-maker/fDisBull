"""Hash-matched zlib carving for this retained investigation, not Inno parsing."""
from pathlib import Path
import zlib, re, hashlib, json, time, collections
P=Path(__import__('os').environ['SYNDICATE_RESEARCH']).resolve()
source=Path(__import__('os').environ['SYNDICATE_INSTALLER']).resolve()
raw=source.read_bytes();mv=memoryview(raw)
manifest=json.loads((Path(__file__).resolve().parent.parent/'evidence/asset-identities.json').read_text())
# Paths are prior evidence labels, not newly recovered installer path mappings.
wanted=collections.defaultdict(list)
for row in manifest:
 if row['path'].startswith(('SYNDICAT/','DATADISK/')):
  wanted[row['stored_sha256']].append(row)
out=P/'runtime/game';out.mkdir(exist_ok=False)
receipts=[];seen=set();beg=time.monotonic();candidates=0
for match in re.finditer(b'\x78[\x01\x5e\x9c\xda]',raw):
 candidates+=1;start=match.start();d=zlib.decompressobj();parts=[];n=0;pos=start
 try:
  while pos<len(raw) and pos-start<16*1024*1024 and n<16*1024*1024:
   end=min(pos+65536,len(raw));x=d.decompress(mv[pos:end],16*1024*1024-n);parts.append(x);n+=len(x)
   if d.eof:
    consumed=end-start-len(d.unused_data);break
   if d.unconsumed_tail:break
   pos=end
  if not d.eof:continue
  payload=b''.join(parts);sha=hashlib.sha256(payload).hexdigest()
  if sha not in wanted or sha in seen:continue
  seen.add(sha)
  names=[]
  for row in wanted[sha]:
   rel=Path(row['path'])
   assert not rel.is_absolute() and '..' not in rel.parts and len(payload)==row['stored_size']
   p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(payload);names.append(row['path'])
  receipts.append({'offset':start,'zlib_size':consumed,'output_size':len(payload),'sha256':sha,'prior_manifest_paths':names})
 except zlib.error:pass
 if time.monotonic()-beg>100:break
result={'method':'Bounded zlib carve; exact SHA-256/size correspondence to retained manifest. Prior filenames are labels, not freshly parsed installer metadata.','source_sha256':hashlib.sha256(raw).hexdigest(),'candidates':candidates,'matched_payloads':len(seen),'matched_paths':sum(len(r['prior_manifest_paths']) for r in receipts),'missing_paths':[r['path'] for h,rs in wanted.items() if h not in seen for r in rs],'elapsed_seconds':time.monotonic()-beg,'receipts':receipts}
(P/'asset-recovery.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['receipts','missing_paths']},indent=2));print('missing',result['missing_paths'][:50])
