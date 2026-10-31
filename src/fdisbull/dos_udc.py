"""Immutable COM UDC plans and explicit native implementation selections.

Experimental replacements are not assumed equivalent. No host executable is
run and no resource or output file is read or written by this module.
"""
from copy import deepcopy
import hashlib
import json
import re
import uuid

import iced_x86 as ix

from .code_backings import validate_source
from .decoder import decode
from .native_udc import _load as _load_native
from .udc import _name
from .udl_blocks import lift_asm_block, verify_block

FORMAT = 'fdisbull-dos-udc-definition-1'
IMPL_FORMAT = 'fdisbull-dos-udc-implementation-1'
MAX_DOCUMENT = 4 * 1024 * 1024
DDL = (
    '''CREATE TABLE IF NOT EXISTS dos_udc_definitions(
        id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
        native_definition TEXT NOT NULL REFERENCES native_udc_definitions(id),
        name TEXT NOT NULL, parent TEXT REFERENCES dos_udc_definitions(id),
        sha256 TEXT NOT NULL, document TEXT NOT NULL, author TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS dos_udc_implementations(
        id TEXT PRIMARY KEY, definition TEXT NOT NULL REFERENCES dos_udc_definitions(id),
        block TEXT NOT NULL, parent TEXT REFERENCES dos_udc_implementations(id),
        sha256 TEXT NOT NULL, document TEXT NOT NULL, author TEXT NOT NULL)''',
)


def _encoded(value):
    try: return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError('invalid DOS UDC JSON') from exc


def _sha(data): return hashlib.sha256(data).hexdigest()


def _definition_digest(version,native,name,parent,author,doc):
    return _sha(_encoded({'version':version,'native_definition':native,'name':name,'parent':parent,'author':author,'document':doc}))


def _implementation_digest(definition,block,parent,author,doc):
    return _sha(_encoded({'definition':definition,'block':block,'parent':parent,'author':author,'document':doc}))


def _bounded(doc):
    raw=_encoded(doc)
    if len(raw)>MAX_DOCUMENT: raise ValueError('DOS UDC metadata exceeds 4 MiB')
    return raw.decode()


def _id(value):
    if not isinstance(value,str) or not 1<=len(value)<=256 or not value.strip(): raise ValueError('invalid identity')
    return value


def _references(value, *, replacement=False):
    if value is None:return []
    if not isinstance(value,list) or len(value)>4096:raise ValueError('invalid reference list')
    result=[];sites=set()
    for ref in value:
        if not isinstance(ref,dict):raise ValueError('invalid reference')
        kind=ref.get('kind')
        if kind=='near-code-pointer' and not replacement:
            required={'kind','data','offset','target','expected_hex'};optional=set()
            site=(_id(ref.get('data')),ref.get('offset'))
        elif kind in ('data-immediate','code-immediate'):
            required={'kind','field_offset','target','expected_hex'} | (set() if replacement else {'instruction'})
            optional={'addend'}
            site=('',ref.get('field_offset')) if replacement else (_id(ref.get('instruction')),ref.get('field_offset'))
        else:raise ValueError('unsupported reference kind')
        if not required<=set(ref) or set(ref)-required-optional:raise ValueError('invalid reference fields')
        _id(ref['target']); offset=site[1]
        if type(offset) is not int or offset<0:raise ValueError('invalid reference offset')
        if 'addend' in ref and (type(ref['addend']) is not int or ref['addend'] != 0):raise ValueError('only zero addend supported')
        if not isinstance(ref['expected_hex'],str) or not re.fullmatch('[0-9a-f]{4}',ref['expected_hex']):raise ValueError('reference requires two expected bytes')
        if any(site[0]==other[0] and abs(site[1]-other[1])<2 for other in sites):raise ValueError('overlapping reference sites')
        sites.add(site);result.append(deepcopy(ref))
    return result


def _identity(project, native_id):
    row,native=_load_native(project,native_id);capsule=native['capsule'];plan=native['plan']
    if project.meta['format']!='COM' or project.arch!='x86' or project.bits!=16 or row['version']!=1 or native['original'] is None:
        raise ValueError('DOS UDC requires original version-1 x86-16 COM source')
    contexts={block['context'] for block in capsule['blocks']}
    segment=project.meta['loader_metadata']['dos']['load_segment']
    if contexts!={f'x86:16:little:cs={segment:04x}'} or not capsule['complete'] or not plan['complete']:
        raise ValueError('DOS UDC requires a complete single-CS graph')
    validate_source(project,capsule,version=1)
    original=project.db.execute('SELECT data FROM native_udc_sources WHERE sha256=?',(native['original']['sha256'],)).fetchone()
    if original is None:raise ValueError('original COM source unavailable')
    return row,native,bytes(original['data']),segment


def _data(project, raw, segment, capsule, data):
    if data is None:data=[]
    if not isinstance(data,list) or len(data)>4096:raise ValueError('invalid data declarations')
    code=set()
    for b in capsule['blocks']:
        start=int(b['address'],16)-segment*16
        code.update(range(start,start+b['instruction']['size']))
    # Project-wide stored instruction and explicit code facts can cover entries
    # outside the chosen graph (or a different segment alias of the same byte).
    for table, condition in (('instructions', ''), ('definitions', " AND representation='code'")):
        for row in project.db.execute(f'SELECT address,size FROM {table} WHERE version=1'+condition):
            start=int(row['address'],16)-segment*16
            lo=max(0x100,start);hi=min(0x10000,start+row['size'])
            if lo < hi: code.update(range(lo,hi))
    result=[];seen=set();used=set()
    for item in data:
        if not isinstance(item,dict) or set(item)!={'id','ip','size'}:raise ValueError('data requires id, ip and size')
        name=_id(item['id']);ip=item['ip'];size=item['size']
        if name in seen or type(ip) is not int or type(size) is not int or size<1 or ip<0x100 or ip+size>0x10000 or ip-0x100+size>len(raw):raise ValueError('data range outside original COM')
        spans=set(range(ip,ip+size))
        if spans & code or spans & used:raise ValueError('data overlaps code or another data range')
        region=project._mapping(1,segment*16+ip);b=raw[ip-0x100:ip-0x100+size]
        if region is None or region.data[segment*16+ip-region.start:segment*16+ip-region.start+size]!=b:raise ValueError('data differs from original COM')
        result.append({'id':name,'ip':ip,'bytes':b.hex(),'sha256':_sha(b)})
        seen.add(name);used.update(spans)
    return result


def _reference_bindings(refs, data, native, *, candidate=None):
    chunks={d['id']:bytes.fromhex(d['bytes']) for d in data}
    atoms={b['id']:bytes.fromhex(b['bytes']) for b in native['capsule']['blocks']}
    groups={b['id'] for b in native['plan']['blocks']}
    for ref in refs:
        kind=ref['kind']; target=ref['target']
        if (kind=='data-immediate' and target not in chunks) or (kind in ('near-code-pointer','code-immediate') and target not in groups):
            raise ValueError('reference target is not declared')
        if kind=='near-code-pointer':
            if ref['data'] not in chunks:raise ValueError('reference data is not declared')
            raw=chunks[ref['data']];offset=ref['offset']
        else:
            if candidate is None:
                if ref['instruction'] not in atoms:raise ValueError('reference instruction is not captured')
                raw=atoms[ref['instruction']]
            else:raw=candidate
            offset=ref['field_offset']
        if raw[offset:offset+2].hex()!=ref['expected_hex']:
            raise ValueError('reference expected bytes differ from backing')


def define_dos_udc(project,name,native_definition,*,data=None,references=None,parent=None,author='agent'):
    _name(name);_name(author)
    with project.transaction(True):
        nr,nd,raw,segment=_identity(project,native_definition)
        chunks=_data(project,raw,segment,nd['capsule'],data);refs=_references(references)
        _reference_bindings(refs,chunks,nd)
        doc={'format':FORMAT,'native_definition_sha256':nr['sha256'],'source_sha256':nd['source_sha256'],
             'version_sha256':nd['version_sha256'],'capsule_sha256':nd['capsule']['sha256'],
             'plan_sha256':nd['plan']['sha256'],'segment':segment,'data':chunks,'references':refs,
             'scope':'Explicit COM code and data; no inferred behavior or native execution.'}
        encoded=_bounded(doc)
        for statement in DDL:project.db.execute(statement)
        last=project.db.execute('SELECT id FROM dos_udc_definitions WHERE name=? ORDER BY rowid DESC LIMIT 1',(name,)).fetchone()
        if (last is None and parent is not None) or (last is not None and last['id']!=parent):raise ValueError('DOS definition requires latest same-name parent')
        ident=uuid.uuid4().hex;sha=_definition_digest(1,native_definition,name,parent,author,doc)
        project.db.execute('INSERT INTO dos_udc_definitions VALUES (?,?,?,?,?,?,?,?)',(ident,1,native_definition,name,parent,sha,encoded,author))
        return dos_udc_info(project,ident)


def _load(project,definition):
    try:row=project.db.execute('SELECT * FROM dos_udc_definitions WHERE id=?',(definition,)).fetchone()
    except Exception as exc:
        if 'no such table' in str(exc):raise ValueError('no DOS UDC definitions') from exc
        raise
    if row is None:raise ValueError('unknown DOS UDC definition')
    try:
        doc=json.loads(row['document'])
        if len(row['document'].encode())>MAX_DOCUMENT or doc.get('format')!=FORMAT or row['version']!=1 or _definition_digest(row['version'],row['native_definition'],row['name'],row['parent'],row['author'],doc)!=row['sha256']:
            raise ValueError('DOS definition integrity mismatch')
        nr,nd,raw,seg=_identity(project,row['native_definition'])
        if (nr['sha256']!=doc['native_definition_sha256'] or nd['source_sha256']!=doc['source_sha256'] or nd['version_sha256']!=doc['version_sha256'] or nd['capsule']['sha256']!=doc['capsule_sha256'] or nd['plan']['sha256']!=doc['plan_sha256'] or seg!=doc['segment']):
            raise ValueError('DOS definition source identity mismatch')
        raw_data=doc['data']; declarations=[{'id':d['id'],'ip':d['ip'],'size':len(bytes.fromhex(d['bytes']))} for d in raw_data]
        if _data(project,raw,seg,nd['capsule'],declarations)!=raw_data or _references(doc['references'])!=doc['references']:
            raise ValueError('DOS definition data/reference integrity mismatch')
        _reference_bindings(doc['references'],raw_data,nd)
        return row,doc,nd
    except (KeyError,TypeError,IndexError,RecursionError) as exc:raise ValueError('malformed DOS UDC definition') from exc


def dos_udc_info(project,definition,*,include_blocks=False):
    if type(include_blocks) is not bool:raise ValueError('include_blocks must be boolean')
    with project.transaction():
        row,doc,native=_load(project,definition)
        result={'id':row['id'],'name':row['name'],'parent':row['parent'],'author':row['author'],'version':row['version'],
                'sha256':row['sha256'],'format':FORMAT,'native_definition':row['native_definition'],
                'native_definition_sha256':doc['native_definition_sha256'],'capsule_sha256':doc['capsule_sha256'],
                'plan_sha256':doc['plan_sha256'],'source_sha256':doc['source_sha256'],'version_sha256':doc['version_sha256'],
                'blocks':len(native['plan']['blocks']),'data_regions':len(doc['data']),'references':len(doc['references']),
                'semantic_qualification':'unverified','native_execution':False}
        if include_blocks:result['document']=deepcopy(doc);result['plan']=deepcopy(native['plan'])
        return result


def _candidate(raw):
    if not isinstance(raw,str) or not re.fullmatch(r'(?:[0-9a-f]{2}){1,4096}',raw):raise ValueError('candidate requires 1..4096 bytes as lowercase hex')
    data=bytes.fromhex(raw);decoder=ix.Decoder(16,data,ip=0);cursor=0
    while cursor<len(data):
        inst=decoder.decode();part=data[cursor:cursor+inst.len]
        facts=decode(part,cursor,'x86',16)
        if inst.is_invalid or not inst.len or facts is None or facts['size']!=inst.len or facts['flow']!='next' or inst.flow_control!=ix.FlowControl.NEXT:
            raise ValueError('candidate must be complete straight-line native NEXT instructions')
        cursor+=inst.len
    if cursor!=len(data):raise ValueError('truncated candidate')
    return data


def _group(native,block):
    matches=[b for b in native['plan']['blocks'] if b['id']==block]
    if len(matches)!=1:raise ValueError('unknown logical block')
    group=matches[0];atoms={b['id']:b for b in native['capsule']['blocks']};last=atoms[group['instructions'][-1]]
    if len(group['exits'])!=1 or group['exits'][0]['kind'] not in ('fallthrough','branch','resolved_branch') or last['flow'] not in ('next','jump'):
        raise ValueError('replacement requires one explicit successor port')
    return group,last


def _unrelocated_projection(doc, group):
    members=set(group['instructions'])
    if any(ref.get('kind') in ('code-immediate','data-immediate') and ref.get('instruction') in members
           for ref in doc['references']):
        raise ValueError('register projection with source immediate fixups is unsupported')


def _prove(native,group,last,raw,projection):
    if not isinstance(projection,dict) or set(projection)!={'bindings','inputs','outputs'}:raise ValueError('register projection requires bindings, inputs and outputs')
    source=bytes.fromhex(group['bytes'])
    if last['flow']=='jump':source=source[:-last['instruction']['size']]
    if not source:raise ValueError('empty source projection unsupported')
    kwargs={'inputs':projection['inputs'],'outputs':projection['outputs']}
    left=lift_asm_block(source,projection['bindings'],**kwargs);right=lift_asm_block(raw,projection['bindings'],**kwargs)
    result=verify_block(left,right['uil'])
    if result['status']!='equivalent_under_assumptions':raise ValueError('register projection not proved: '+result['status'])
    return {'status':result['status'],'source_sha256':left['sha256'],'candidate_sha256':right['sha256'],
            'scope':'Declared 16-bit register outputs only; flags, memory, control flow, ABI, timing and partial effects excluded.',
            'proof':result}


def register_dos_implementation(project,definition,block,code,*,expected_block_revision,purpose='experiment',projection=None,references=None,parent=None,author='agent'):
    _name(author);_id(block);raw=_candidate(code);refs=_references(references,replacement=True)
    if purpose not in ('experiment','register-equivalence'):raise ValueError('unknown implementation purpose')
    if purpose=='experiment' and projection is not None:raise ValueError('experiment cannot claim a projection')
    if purpose=='register-equivalence' and refs:raise ValueError('register projection with rewritten candidate references is unsupported')
    with project.transaction(True):
        row,doc,native=_load(project,definition);group,last=_group(native,block)
        if expected_block_revision!=group['block_revision']:raise ValueError('source block revision mismatch')
        _reference_bindings(refs,doc['data'],native,candidate=raw)
        if purpose=='register-equivalence':_unrelocated_projection(doc,group)
        qualification=(_prove(native,group,last,raw,projection) if purpose=='register-equivalence' else
                       {'status':'unverified','scope':'Experimental candidate; no behavior or effect equivalence asserted.'})
        item={'format':IMPL_FORMAT,'bytes':raw.hex(),'sha256':_sha(raw),'expected_block_revision':expected_block_revision,
              'references':refs,'purpose':purpose,'projection':deepcopy(projection),'qualification':qualification}
        encoded=_bounded(item)
        lastrow=project.db.execute('SELECT id FROM dos_udc_implementations WHERE definition=? AND block=? ORDER BY rowid DESC LIMIT 1',(definition,block)).fetchone()
        if (lastrow is None and parent is not None) or (lastrow is not None and lastrow['id']!=parent):raise ValueError('implementation requires latest same-block parent')
        ident=uuid.uuid4().hex;sha=_implementation_digest(definition,block,parent,author,item)
        project.db.execute('INSERT INTO dos_udc_implementations VALUES (?,?,?,?,?,?,?)',(ident,definition,block,parent,sha,encoded,author))
        return dos_implementation_info(project,ident)


def _load_impl(project,implementation):
    try:row=project.db.execute('SELECT * FROM dos_udc_implementations WHERE id=?',(implementation,)).fetchone()
    except Exception as exc:
        if 'no such table' in str(exc):raise ValueError('no DOS implementations') from exc
        raise
    if row is None:raise ValueError('unknown DOS implementation')
    try:
        item=json.loads(row['document'])
        if len(row['document'].encode())>MAX_DOCUMENT or item.get('format')!=IMPL_FORMAT or _implementation_digest(row['definition'],row['block'],row['parent'],row['author'],item)!=row['sha256']:
            raise ValueError('implementation integrity mismatch')
        _,doc,native=_load(project,row['definition']);group,last=_group(native,row['block']);raw=_candidate(item['bytes'])
        if item['sha256']!=_sha(raw) or item['expected_block_revision']!=group['block_revision'] or _references(item['references'],replacement=True)!=item['references']:
            raise ValueError('implementation source or candidate mismatch')
        _reference_bindings(item['references'],doc['data'],native,candidate=raw)
        if item['purpose']=='register-equivalence':
            if item['references']:raise ValueError('register projection with rewritten candidate references is unsupported')
            _unrelocated_projection(doc,group)
            if item['qualification']['status']!='equivalent_under_assumptions':raise ValueError('implementation qualification mismatch')
            # A digest is not an authentication token: regenerate proof before
            # returning any qualified claim, including readback and compilation.
            item['qualification']=_prove(native,group,last,raw,item['projection'])
        elif item['purpose']!='experiment' or item['projection'] is not None or item['qualification']['status']!='unverified':raise ValueError('implementation purpose mismatch')
        return row,item,native,group,last
    except (KeyError,TypeError,IndexError,RecursionError) as exc:raise ValueError('malformed DOS implementation') from exc


def dos_implementation_info(project,implementation):
    with project.transaction():
        row,item,_,_,_=_load_impl(project,implementation)
        return {'id':row['id'],'definition':row['definition'],'block':row['block'],'parent':row['parent'],
                'author':row['author'],'sha256':row['sha256'],'candidate_sha256':item['sha256'],
                'expected_block_revision':item['expected_block_revision'],'purpose':item['purpose'],
                'projection':deepcopy(item['projection']),'qualification':deepcopy(item['qualification']),
                'reference_count':len(item['references'])}


def compile_dos_udc(project,definition,*,implementations=None,entry=None,block_order=None,assumptions=None,code_base=None,container='com'):
    """Emit a bounded DOS code layout with an explicit COM or MZ container."""
    if container not in ('com', 'mz'):
        raise ValueError('container must be com or mz')
    if implementations is None:implementations={}
    if not isinstance(implementations,dict) or len(implementations)>4096:raise ValueError('invalid implementation selection')
    with project.transaction():
        row,doc,native=_load(project,definition)
        validate_source(project,native['capsule'],version=row['version'])
        chosen={};identities={}
        for block,ident in implementations.items():
            _id(block);_id(ident)
            ir,item,_,group,last=_load_impl(project,ident)
            if ir['definition']!=definition or ir['block']!=block:raise ValueError('implementation does not match definition/block')
            qualification=item['qualification']
            chosen[block]={'id':ident,'bytes':item['bytes'],'sha256':item['sha256'],
                           'expected_block_revision':item['expected_block_revision'],'references':deepcopy(item['references']),
                           'qualification':deepcopy(qualification)}
            identities[block]={'id':ident,'sha256':ir['sha256'],'candidate_sha256':item['sha256'],
                               'purpose':item['purpose'],'projection':deepcopy(item['projection']),
                               'qualification':deepcopy(qualification)}
        from .dos_udc_layout import compile_dos_com
        result=compile_dos_com(native['capsule'],native['plan'],deepcopy(doc['data']),references=deepcopy(doc['references']),
                               replacements=chosen,entry=entry,block_order=block_order,assumptions=assumptions,code_base=code_base)
        if container == 'mz':
            from .dos_mz_udc import wrap_com_layout
            result = wrap_com_layout(result)
        return {**deepcopy(result),'definition':row['id'],'definition_sha256':row['sha256'],
                'native_definition':row['native_definition'],'native_definition_sha256':doc['native_definition_sha256'],
                'source_sha256':doc['source_sha256'],'version_sha256':doc['version_sha256'],
                'capsule_sha256':doc['capsule_sha256'],'plan_sha256':doc['plan_sha256'],
                'implementations':identities,'native_execution':False}
