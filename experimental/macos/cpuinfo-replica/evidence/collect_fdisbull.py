"""Re-read existing private fDisBull facts; never exports original bytes or an FDB."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request

from fdisbull.project import Project
from fdisbull.code_backings import materialize_code_backing

parser = argparse.ArgumentParser()
parser.add_argument('--database', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
with Project(args.database) as project:
    state = project.status()
    capsule = project.code_backings([state['entry']], max_instructions=32)
    for block in capsule['blocks']:
        materialize_code_backing(block)
    names = project.db.execute("SELECT address,kind,name,module FROM symbols WHERE name IN "
        "('_host_processor_info','_host_statistics','_mach_host_self') ORDER BY name,kind").fetchall()
    receipt = {
        'kind':'bounded-source-assisted-replication-evidence',
        'original':{'sha256':state['source_sha256'],'entry':state['entry'],
                    'format':state['format'],'architecture':state['arch'],
                    'version':state['version']['id'],
                    'slice':{k:state['loader_metadata']['macho_slice'][k] for k in
                             ('offset','size','slice_sha256')}},
        'stored_analysis':{'instructions':state['counts']['instructions'],
                           'candidate_functions':state['counts']['functions'],
                           'pending_code':state['analysis']['pending_code'],
                           'stable':state['analysis']['stable']},
        'entry_capsule':{'sha256':capsule['sha256'],'instructions':len(capsule['blocks']),
                         'complete':capsule['complete'],'budget':capsule['budget'],
                         'all_encodings_revalidated':True,
                         'original_bytes_exported':False},
        'retained_import_evidence':[dict(zip(('preferred_address','kind','symbol','module'),row)) for row in names],
        'native_semantic_recovery':'unresolved; imports and source identity do not recover sampling/view logic',
    }
revision = 'd7f9e846909f9775e1d6d03214796dbaff4d5492'
receipt['published_source'] = {'project':'https://github.com/yusukeshib/cpuinfo',
    'tag':'v1.7.0','revision':revision,'correspondence_to_installed_binary':'unproven', 'files':[]}
for path in ('src/Cpuinfo.swift','src/CpuinfoImage.swift','src/CpuinfoDelegate.swift','res/en.lproj/MainMenu.xib','README.md'):
    url='https://raw.githubusercontent.com/yusukeshib/cpuinfo/' + revision + '/' + path
    with urllib.request.urlopen(url, timeout=20) as response:
        content=response.read(256*1024+1)
    if len(content)>256*1024: raise ValueError('source budget exceeded')
    receipt['published_source']['files'].append({'file':path,'url':url,'bytes':len(content),
        'sha256':hashlib.sha256(content).hexdigest()})
Path(args.output).write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'entry_instructions_validated':receipt['entry_capsule']['instructions'],
                  'pending_code':receipt['stored_analysis']['pending_code'],
                  'source_files_hashed':len(receipt['published_source']['files'])}))
