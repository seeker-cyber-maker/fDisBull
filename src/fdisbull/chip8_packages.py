"""Deterministic, source-bound CHIP-8 ISA/environment package closure.

Definitions are declarations, not semantic qualification or runtime proof.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .chip8 import PROFILE
from .chip8_intake import inspect_project

CATALOG_FORMAT='fdisbull-chip8-package-catalog-1'
FORMAT='fdisbull-chip8-closure-1'
ISA_ID='isa:chip8-classic-qemu-v6:1'
ENV_ID='env:chip8-qemu-v6:1'
_HEX64=re.compile(r'[0-9a-f]{64}\Z')
_TABLES=('instructions','functions','xrefs','work','analysis_state')
_MAX_ROWS=4096
_MAX_ANALYSIS=4*1024*1024


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def _sha(data):return hashlib.sha256(data).hexdigest()


def _package(identifier,kind,contract,evidence):
    definition=dict(id=identifier,kind=kind,version=1,contract=contract,evidence=evidence)
    return {**definition,'sha256':_sha(_canonical(definition))}


def catalog():
    """Return source-independent definitions; never decode or execute a target."""
    decoder=Path(__file__).with_name('chip8.py').read_bytes()
    if len(decoder)>1024*1024:raise ValueError('CHIP-8 decoder source exceeds the bounded reader identity')
    isa=_package(ISA_ID,'architecture',dict(
        profile=PROFILE,isa='chip8',word_bits=16,instruction_endian='big',family_count=34,
        registers=dict(v_count=16,v_bits=8,index_bits=16,pc_bits=16,stack_entries=16,stack_entry_bits=16),
        quirks=dict(shift_source='vy',logic_vf='clear',load_store_i='increment',jump_offset='v0',
                    add_i_vf='preserve',operand_alias='read-before-write'),
        faults=dict(aligned_fetch=True,memory_bytes=4096,invalid_instruction='sticky-atomic',
                    out_of_range='sticky-atomic',stack_bounds='sticky-atomic'),
        extensions=dict(legacy_sys=False,schip=False,xo=False)),
        dict(status='declared-not-semantically-qualified',decoder_source_sha256=_sha(decoder),
             source='on-disk fdisbull/chip8.py; no running-code attestation or semantic qualification'))
    env=_package(ENV_ID,'environment',dict(
        profile=PROFILE,
        memory=dict(size=4096,rom_base=512,entry=512),
        display=dict(width=64,height=32,format='monochrome',origin='wrap',sprite_edges='clip',
                     blend='xor',collision='vf',font_base=80),
        keypad=dict(keys=16,range_min=0,range_max=15,wait='lowest-held-including-zero',
                    empty_wait='debug-stop-explicit-resume',invalid_key='unpressed',typematic=False),
        clock=dict(timer_hz=60,source='qemu-virtual-rational',stopped_manual_ticks=True,
                   manual_advances_virtual_time=False,wall_clock_cpu_rate='unqualified'),
        rng=dict(model='fdisbull-lcg32-high8-v1',bits=32,default_seed=0,multiplier=1664525,
                 increment=1013904223,output='high8',zero_mask_consumes_draw=True),
        audio=dict(sound_active=True,waveform=False)),
        dict(status='declared-not-semantically-qualified',source='fdisbull CHIP-8 v6 documented native contract',
             compatibility='not a claim of historical interpreter or arbitrary ROM compatibility'))
    return dict(format=CATALOG_FORMAT,packages=[isa,env])


def _requirements(value,packages):
    if value is None:return {}
    if not isinstance(value,dict) or set(value)-{'architecture','environment'}:
        raise ValueError('CHIP-8 requirements must use architecture/environment keys')
    def check(wanted,actual,path):
        if not isinstance(wanted,dict):raise ValueError('CHIP-8 requirements must be nested objects at '+path)
        for key,want in wanted.items():
            if not isinstance(key,str) or key not in actual:raise ValueError('Unknown CHIP-8 requirement: '+path+'.'+str(key))
            have=actual[key]
            if isinstance(want,dict):
                if not isinstance(have,dict):raise ValueError('CHIP-8 requirement mismatch: '+path+'.'+key)
                check(want,have,path+'.'+key)
            elif type(want) is not type(have) or want!=have:
                raise ValueError('CHIP-8 requirement mismatch: '+path+'.'+key)
    for kind,wanted in value.items():check(wanted,packages[kind]['contract'],kind)
    return deepcopy(value)


def _runtime(value):
    if value is None:return None
    fields={'profile','cpu_subset','env_model','machine','memory','qemu_sha256','qemu_version','checkpoint_tool_sha256'}
    if not isinstance(value,dict) or set(value)!=fields:raise ValueError('CHIP-8 runtime declaration fields differ')
    expected=dict(profile=PROFILE,cpu_subset='fdisbull-chip8-frame-keys-6',
                  env_model='fdisbull-chip8-display-keypad-timers-rng-layers-frames-keys-5',
                  machine='chip8-test',memory=4096)
    if any(type(value.get(k)) is not type(v) or value[k]!=v for k,v in expected.items()):
        raise ValueError('CHIP-8 runtime declaration profile or machine differs')
    if not isinstance(value['qemu_sha256'],str) or not _HEX64.fullmatch(value['qemu_sha256']):
        raise ValueError('Invalid CHIP-8 runtime SHA-256')
    tool=value['checkpoint_tool_sha256']
    if tool is not None and (not isinstance(tool,str) or not _HEX64.fullmatch(tool)):
        raise ValueError('Invalid CHIP-8 checkpoint tool SHA-256')
    version=value['qemu_version']
    if (not isinstance(version,str) or not version.strip() or len(version)>256 or
            any(ord(c)<32 or ord(c)==127 for c in version) or '/' in version or '\\' in version):
        raise ValueError('Invalid CHIP-8 runtime version declaration')
    return dict(declaration=deepcopy(value),verification='caller-declared-unverified')


def _field(value):
    if value is None:return None
    if type(value) is int:return value
    if isinstance(value,str):
        data=value.encode('utf-8');return dict(type='text',size=len(data),sha256=_sha(data))
    if isinstance(value,bytes):return dict(type='bytes',size=len(value),sha256=_sha(value))
    raise ValueError('Unsupported CHIP-8 analysis field')


def _analysis(project,source):
    total=0;tables={};status={'entry_complete':'unknown','seeds_admitted':'unknown','pending_work':0,'other_work':0}
    version=source['project']['version']
    for table in _TABLES:
        schema=project.db.execute('PRAGMA table_info('+table+')').fetchall()
        if not schema or not any(row['name']=='version' for row in schema):raise ValueError('CHIP-8 analysis table unavailable')
        count=project.db.execute('SELECT count(*) AS count FROM '+table+' WHERE version=?',(version,)).fetchone()['count']
        if type(count) is not int or count>_MAX_ROWS:raise ValueError('CHIP-8 analysis row limit exceeded')
        text_columns=[row['name'] for row in schema if str(row['type']).upper() in ('TEXT','BLOB')]
        for column in text_columns:
            # Column names come only from the five explicitly selected local schemas.
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',column):raise ValueError('Invalid CHIP-8 analysis column')
            size=project.db.execute('SELECT coalesce(sum(fdb_length("'+column+'")),0) AS n FROM '+table+' WHERE version=?',(version,)).fetchone()['n']
            total+=size
            if total>_MAX_ANALYSIS:raise ValueError('CHIP-8 analysis snapshot byte budget exceeded')
        encoded=[]
        for row in project.db.execute('SELECT * FROM '+table+' WHERE version=?',(version,)):
            if table=='instructions':
                encoded_bytes=row['bytes'];size=row['size']
                if (type(size) is not int or not 1<=size<=16 or not isinstance(encoded_bytes,str) or
                        len(encoded_bytes)!=2*size or any(c not in '0123456789abcdef' for c in encoded_bytes)):
                    raise ValueError('CHIP-8 analysis instruction bytes are unavailable or invalid')
            doc={key:_field(row[key]) for key in row.keys()}
            item=_canonical(doc);total+=len(item)
            if total>_MAX_ANALYSIS:raise ValueError('CHIP-8 analysis snapshot byte budget exceeded')
            encoded.append(item)
            if table=='work':
                status['pending_work' if row['state']=='pending' else 'other_work']+=1
            if table=='analysis_state':
                for key in ('entry_complete','seeds_admitted'):
                    if type(row[key]) is not int or row[key] not in (0,1):raise ValueError('Invalid CHIP-8 analysis status')
                    status[key]=bool(row[key])
        encoded.sort();tables[table]=dict(count=count,sha256=_sha(b'\n'.join(encoded)))
    return dict(format='fdisbull-chip8-analysis-snapshot-1',source_sha256=source['source']['sha256'],
                mapped_sha256=source['project']['mapped_sha256'],tables=tables,status=status,
                scope='existing original-version static records only; no new analysis or semantic proof')


def _source_guard(project,version):
    """Hash source-related stored values again inside the owned write transaction."""
    specs=(('metadata',"SELECT key,value FROM metadata ORDER BY key",()),
           ('version','SELECT * FROM versions WHERE id=?',(version,)),
           ('source','SELECT document FROM target_sources WHERE version=?',(version,)),
           ('binary','SELECT source_bytes FROM binary_info WHERE version=?',(version,)),
           ('regions','SELECT * FROM regions WHERE version=? ORDER BY start',(version,)))
    result={}
    for label,query,args in specs:
        rows=project.db.execute(query,args).fetchall()
        result[label]=[{k:_field(row[k]) for k in row.keys()} for row in rows]
    return _sha(_canonical(result))


def _graph(source,packages,runtime,analysis):
    refs={kind:dict(id=package['id'],sha256=package['sha256']) for kind,package in packages.items()}
    target_identity=dict(intake_sha256=source['intake_sha256'],source_sha256=source['source']['sha256'],
                         mapped_sha256=source['project']['mapped_sha256'],packages=refs)
    target='target:chip8:'+_sha(_canonical(target_identity));base=[ISA_ID,ENV_ID]
    nodes=[dict(id=ISA_ID,kind='architecture',depends_on=[]),dict(id=ENV_ID,kind='environment',depends_on=[]),
           dict(id=target,kind='target',depends_on=base)]
    if runtime is not None:
        nodes.append(dict(id='runtime:chip8:'+_sha(_canonical(dict(runtime=runtime,packages=refs))),kind='runtime',depends_on=base))
    if analysis is not None:
        nodes.append(dict(id='analysis:chip8:'+_sha(_canonical(dict(analysis=analysis,target=target))),kind='analysis',depends_on=[target]))
    _validate_graph(nodes)
    return nodes


def _validate_graph(nodes):
    if not isinstance(nodes,list) or not 3<=len(nodes)<=5:raise ValueError('Invalid CHIP-8 closure graph')
    mapping={}
    for node in nodes:
        if not isinstance(node,dict) or set(node)!={'id','kind','depends_on'} or not isinstance(node['id'],str) or node['id'] in mapping or not isinstance(node['depends_on'],list) or len(set(node['depends_on']))!=len(node['depends_on']):
            raise ValueError('Invalid CHIP-8 closure node')
        mapping[node['id']]=node
    visiting=set();done=set()
    def visit(identifier):
        if identifier not in mapping or identifier in visiting:raise ValueError('CHIP-8 closure has a missing or cyclic dependency')
        if identifier in done:return
        visiting.add(identifier)
        for dependency in mapping[identifier]['depends_on']:visit(dependency)
        visiting.remove(identifier);done.add(identifier)
    for identifier in mapping:visit(identifier)


def _definitions():
    values=catalog()['packages'];return {'architecture':values[0],'environment':values[1]}


def _document(source,packages,requirements,runtime,analysis):
    refs={kind:dict(id=value['id'],sha256=value['sha256']) for kind,value in packages.items()}
    target=dict(intake_sha256=source['intake_sha256'],source_sha256=source['source']['sha256'],
                mapped_sha256=source['project']['mapped_sha256'])
    return dict(format=FORMAT,source=target,packages=refs,requirements=requirements,runtime=runtime,analysis=analysis,
                graph=_graph(source,packages,runtime,analysis),
                claims=dict(compatibility='exact declared package contracts only',semantics='not independently qualified',
                            runtime='caller declaration is not execution proof',g2_g8='not run'))


def _existing(project,table,identifier,expected):
    present=project.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
    if not present:return False
    try:row=project.db.execute('SELECT sha256,document FROM '+table+' WHERE id=?',(identifier,)).fetchone()
    except sqlite3.OperationalError as error:raise ValueError('Invalid CHIP-8 closure storage schema') from error
    if row is None:return False
    if row['sha256']!=_sha(expected) or row['document']!=expected.decode('utf-8'):
        raise ValueError('Stored CHIP-8 package or closure differs')
    return True


def resolve(project,*,environment,version=None,requirements=None,pins=None,runtime=None,include_analysis=False,expected_intake_sha256=None):
    if project.db.in_transaction:raise ValueError('CHIP-8 closure requires no caller transaction')
    selected_version=project.version(version)['id']
    before_guard=_source_guard(project,selected_version)
    source=inspect_project(project,version,expected_intake_sha256=expected_intake_sha256)
    if source['project']['version']!=selected_version or _source_guard(project,selected_version)!=before_guard:
        raise ValueError('CHIP-8 source changed during closure admission')
    if environment!=ENV_ID:raise ValueError('Explicit supported CHIP-8 environment package required')
    if type(include_analysis) is not bool:raise ValueError('include_analysis must be boolean')
    packages=_definitions();wanted=_requirements(requirements,packages);declared=_runtime(runtime)
    expected_pins={p['id']:p['sha256'] for p in packages.values()}
    if pins is not None and (not isinstance(pins,dict) or pins!=expected_pins):
        raise ValueError('CHIP-8 package pins missing, unknown or mismatched')
    analysis=_analysis(project,source) if include_analysis else None
    document=_document(source,packages,wanted,declared,analysis);raw=_canonical(document);digest=_sha(raw);identifier='closure:'+digest
    guard=_source_guard(project,source['project']['version'])
    if guard!=before_guard:raise ValueError('CHIP-8 source changed during closure preflight')
    expected=[(p['id'],_canonical(p)) for p in packages.values()]
    for ident,data in expected:_existing(project,'chip8_package_definitions',ident,data)
    _existing(project,'chip8_package_closures',identifier,raw)
    with project.transaction(True):
        if _definitions()!=packages:raise ValueError('CHIP-8 package definitions changed before publication')
        if _source_guard(project,source['project']['version'])!=guard:
            raise ValueError('CHIP-8 source changed before closure publication')
        if analysis is not None and _analysis(project,source)!=analysis:
            raise ValueError('CHIP-8 analysis changed before closure publication')
        project.db.execute('CREATE TABLE IF NOT EXISTS chip8_package_definitions (id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,document TEXT NOT NULL)')
        project.db.execute('CREATE TABLE IF NOT EXISTS chip8_package_closures (id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,document TEXT NOT NULL)')
        for ident,data in expected:
            if not _existing(project,'chip8_package_definitions',ident,data):
                project.db.execute('INSERT INTO chip8_package_definitions VALUES (?,?,?)',(ident,_sha(data),data.decode('utf-8')))
        if not _existing(project,'chip8_package_closures',identifier,raw):
            project.db.execute('INSERT INTO chip8_package_closures VALUES (?,?,?)',(identifier,digest,raw.decode('utf-8')))
        if (_definitions()!=packages or _source_guard(project,source['project']['version'])!=guard or
                analysis is not None and _analysis(project,source)!=analysis):
            raise ValueError('CHIP-8 source or analysis changed during closure publication')
    return {'closure':identifier,'sha256':digest,**document}


def info(project,closure,version=None,expected_intake_sha256=None):
    if project.db.in_transaction:raise ValueError('CHIP-8 closure requires no caller transaction')
    if not isinstance(closure,str) or not closure.startswith('closure:') or not _HEX64.fullmatch(closure[8:]):
        raise ValueError('Invalid CHIP-8 closure identity')
    selected_version=project.version(version)['id'];before_guard=_source_guard(project,selected_version)
    source=inspect_project(project,version,expected_intake_sha256=expected_intake_sha256)
    if source['project']['version']!=selected_version or _source_guard(project,selected_version)!=before_guard:
        raise ValueError('CHIP-8 source changed during closure inspection')
    exists=project.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chip8_package_closures'").fetchone()
    if not exists:raise ValueError('CHIP-8 closure is unavailable')
    try:row=project.db.execute('SELECT sha256,document FROM chip8_package_closures WHERE id=?',(closure,)).fetchone()
    except sqlite3.OperationalError as error:raise ValueError('Invalid CHIP-8 closure storage schema') from error
    if row is None or not isinstance(row['document'],str):raise ValueError('CHIP-8 closure is unavailable')
    try:doc=json.loads(row['document']);raw=_canonical(doc)
    except (ValueError,TypeError,UnicodeError):raise ValueError('Invalid CHIP-8 closure document') from None
    if raw.decode('utf-8')!=row['document'] or row['sha256']!=_sha(raw) or closure!='closure:'+row['sha256']:
        raise ValueError('CHIP-8 closure hash differs')
    if not isinstance(doc,dict) or set(doc)!={'format','source','packages','requirements','runtime','analysis','graph','claims'} or doc['format']!=FORMAT:
        raise ValueError('Invalid CHIP-8 closure document')
    packages=_definitions()
    for package in packages.values():
        if not _existing(project,'chip8_package_definitions',package['id'],_canonical(package)):
            raise ValueError('CHIP-8 package definition unavailable')
    wanted=_requirements(doc['requirements'],packages)
    runtime=doc['runtime']
    if runtime is not None:
        if not isinstance(runtime,dict) or set(runtime)!={'declaration','verification'} or _runtime(runtime['declaration'])!=runtime:
            raise ValueError('Invalid CHIP-8 stored runtime declaration')
    analysis=_analysis(project,source) if doc['analysis'] is not None else None
    if doc['analysis']!=analysis:raise ValueError('CHIP-8 source analysis snapshot is stale')
    expected=_document(source,packages,wanted,runtime,analysis)
    if doc!=expected:raise ValueError('CHIP-8 closure source, dependencies or contract differ')
    _validate_graph(doc['graph'])
    if (_definitions()!=packages or _source_guard(project,selected_version)!=before_guard or
            analysis is not None and _analysis(project,source)!=analysis):
        raise ValueError('CHIP-8 source or package changed during closure inspection')
    return {'closure':closure,'sha256':row['sha256'],**doc}
