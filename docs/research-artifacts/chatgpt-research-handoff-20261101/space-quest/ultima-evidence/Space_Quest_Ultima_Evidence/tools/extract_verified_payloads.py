"""Extract only checksum-verified stored Inno records and GOG zlib members.
This is a purpose-built probe for the supplied installers, not an installer emulator.
No Inno Pascal bytecode, PE executable or helper DLL is executed.
"""
from pathlib import Path
import struct,re,json,hashlib,zlib,sys
ROOT=Path('/mnt/data/game_intake')
INPUT=Path('/mnt/data')
def safe_path(root,name):
 name=name.replace('\\','/');p=Path(name)
 if p.is_absolute() or '..' in p.parts or ':' in name:raise ValueError('unsafe path')
 return root/p

def main(nm):
 records=json.loads((ROOT/nm/'file_table.json').read_text()); entries=json.loads((ROOT/nm/'data_table.json').read_text())
 inst=next(p for p in INPUT.glob('*.exe') if (p.name.startswith('patch') if nm=='patch' else (p.name.startswith('setup_space') if nm=='space_quest' else 'ultima' in p.name)))
 blob=inst.read_bytes();base=192512
 def raw(rec):
  d=rec['data'];p=base+d['chunk_offset']
  assert blob[p:p+4]==b'zlb\x1a'
  assert not d['flags']&0xd0, 'compressed/encrypted/filter not supported in this bounded extractor'
  start=p+4+d['file_offset'];b=blob[start:start+d['file_size']]
  assert len(b)==d['file_size'] and hashlib.sha1(b).hexdigest()==d['sha1'], 'SHA1 mismatch'
  return b
 report={'installer':inst.name,'installer_sha256':hashlib.sha256(blob).hexdigest(),'installer_size':len(blob),'inno_data_records':len(entries),'file_records':len(records),'files':[],'skipped':[]}
 if nm=='patch':
  for r in records:
   b=raw(r);name=r['dest'].replace('\\','/')
   dst=ROOT/nm/'raw'/name.replace('{','').replace('}','');dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b)
   report['files'].append({'entry':r['location'],'destination':name,'stored_size':len(b),'sha1_verified':True,'sha256':hashlib.sha256(b).hexdigest()})
  strings=(ROOT/nm/'header_strings.txt').read_text().splitlines();ops=[]
  for i,s in enumerate(strings):
   if i+3<len(strings) and strings[i+1]=='Target MD5' and re.fullmatch('[a-f0-9]{32}',strings[i+2]) and re.fullmatch('[a-f0-9]{32}',strings[i+3]):
    src=ROOT/nm/'raw/tmp'/strings[i+2];stored=src.read_bytes()
    try:b=zlib.decompress(stored);kind='complete_zlib_replacement'
    except zlib.error:b=stored;kind='other'
    assert hashlib.md5(stored).hexdigest()==strings[i+2]
    assert hashlib.md5(b).hexdigest()==strings[i+3]
    dest=safe_path(ROOT/nm/'payload',s);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
    ops.append({'path':s.replace('\\','/'),'kind':kind,'stored_size':len(stored),'expanded_size':len(b),'stored_md5':strings[i+2],'target_md5':strings[i+3],'sha256':hashlib.sha256(b).hexdigest(),'checks_passed':True})
  (ROOT/nm/'replacement_manifest.json').write_text(json.dumps(ops,indent=2))
  print(nm,'verified',len(report['files']),'records;',len(ops),'full payloads')
 else:
  active=None;groups=[]
  for r in records:
   before=r['before']
   m=re.fullmatch(r"before_install(?:_dependency)?\('([0-9a-f]{32})', '([^']*)', (\d+)\)",before)
   if m:
    active={'md5':m[1],'path':m[2].replace('\\','/'),'count':int(m[3]),'parts':[]};groups.append(active)
   if active and len(active['parts'])<active['count'] and r['after']:
    active['parts'].append(r)
  for group in groups:
   name=group['path']
   if (name.startswith('__redist/') or name.startswith('__support/app/scummvm/') or name.startswith('DOSBOX/')):
    report['skipped'].append({'path':name,'reason':'runtime distribution not required for selected game-data extraction'});continue
   assert len(group['parts'])==group['count']
   pieces=[]
   for r in group['parts']:
    packed=raw(r);filekey=r['dest'].replace('\\','/').rsplit('/',1)[-1]
    assert hashlib.md5(packed).hexdigest()==filekey
    pieces.append(zlib.decompress(packed))
   b=b''.join(pieces)
   assert hashlib.md5(b).hexdigest()==group['md5'], 'GOG final MD5 mismatch: '+name
   dst=safe_path(ROOT/nm/'app',name);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b)
   report['files'].append({'path':name,'size':len(b),'md5':group['md5'],'sha256':hashlib.sha256(b).hexdigest(),'parts':group['count'],'all_checks_passed':True})
  print(nm,'verified extracted',len(report['files']),'skipped',len(report['skipped']))
 (ROOT/nm/'extraction_receipt.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
 for nm in ['patch','space_quest','ultima']:main(nm)
