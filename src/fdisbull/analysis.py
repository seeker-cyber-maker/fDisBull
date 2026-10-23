"""Fact-driven recursive analysis and shared address presentation.

A queue becoming empty is a fixed point of these implemented rules, not a claim
that every function or indirect reference has been recovered.
"""
import json
from pathlib import Path


def k(a):
    if isinstance(a,bool) or not isinstance(a,int) or not 0<=a<(1<<64):
        raise ValueError('address must be an unsigned 64-bit integer')
    return f'{a:016x}'


def h(a):
    return f'0x{a:x}'


EXTENSION_DDL = """
CREATE TABLE IF NOT EXISTS binary_info(version INTEGER PRIMARY KEY REFERENCES versions(id), document TEXT NOT NULL, source_bytes BLOB);
CREATE TABLE IF NOT EXISTS symbols(version INTEGER NOT NULL, address TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, module TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL, PRIMARY KEY(version,address,kind,module,name));
CREATE TABLE IF NOT EXISTS data_items(version INTEGER NOT NULL, context TEXT NOT NULL, address TEXT NOT NULL, representation TEXT NOT NULL, size INTEGER NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(version,context,address));
CREATE TABLE IF NOT EXISTS definitions(version INTEGER NOT NULL, context TEXT NOT NULL, address TEXT NOT NULL, representation TEXT NOT NULL, size INTEGER NOT NULL, author TEXT NOT NULL, PRIMARY KEY(version,context,address));
CREATE TABLE IF NOT EXISTS investigations(version INTEGER NOT NULL, context TEXT NOT NULL, address TEXT NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', detail TEXT, PRIMARY KEY(version,context,address));
CREATE TABLE IF NOT EXISTS operand_refs(version INTEGER NOT NULL, context TEXT NOT NULL, source TEXT NOT NULL, operand_index INTEGER NOT NULL, role TEXT NOT NULL, target TEXT NOT NULL, width INTEGER, PRIMARY KEY(version,context,source,operand_index,role,target));
CREATE TABLE IF NOT EXISTS analysis_state(version INTEGER PRIMARY KEY REFERENCES versions(id), entry_complete INTEGER NOT NULL DEFAULT 0, seeds_admitted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS recoveries(version INTEGER PRIMARY KEY REFERENCES versions(id), document TEXT NOT NULL);
"""


class AnalysisMixin:
    def _init_information(self, image, version=1):
        from .inspection import inspect_binary
        document = inspect_binary(image.source_bytes)
        if image.format == 'MZ':
            document=self._dos_document_for_image(image,document)
        if image.format == 'raw':
            region = image.regions[0]
            document['sections'] = [dict(name='raw',virtual_address=region.start,virtual_size=len(region.data),file_offset=0,file_size=len(region.data),permissions='rx')]
            document['imports'], document['exports'] = [], []
            for item in document['strings']:
                item['address'] = region.start + item['file_offset']
        document['file_mappings']=image.metadata.get('file_mappings',[])
        self.db.execute('INSERT INTO binary_info VALUES (?,?,?)',(version,json.dumps(document),image.source_bytes))
        self.db.execute('INSERT INTO analysis_state(version) VALUES (?)',(version,))
        self._index_symbols(version, document)
        if image.format=="MZ":
            self._dos_init(image,version)

    def _index_symbols(self, version, document):
        for kind in ('imports','exports'):
            for item in document.get(kind,[]):
                address = item.get('address')
                if address is None:
                    continue
                name = item.get('name') or (f"ordinal_{item['ordinal']}" if item.get('ordinal') is not None else 'unnamed')
                self.db.execute('INSERT OR IGNORE INTO symbols VALUES (?,?,?,?,?,?)',
                    (version,k(address),kind,name,item.get('module') or '',json.dumps(item)))

    def _document(self, version):
        row = self.db.execute('SELECT document FROM binary_info WHERE version=?',(version,)).fetchone()
        if row:
            return json.loads(row[0])
        return dict(header=None,sections=[],imports=[],exports=[],strings=[],warnings=['Original file metadata unavailable in this migrated 0.1 project; reimport to obtain it.'])

    def _mapping(self, version, address):
        return next((r for r in self.regions(version) if r.start <= address < r.start+len(r.data)),None)

    def _label(self, version, address):
        row = self.db.execute("SELECT text FROM annotations WHERE version=? AND context=? AND address=? AND kind='name'",(version,self.context,k(address))).fetchone()
        if row:
            return row[0]
        row = self.db.execute("SELECT module,name FROM symbols WHERE version=? AND address=? ORDER BY CASE kind WHEN 'recovered_import' THEN 0 WHEN 'imports' THEN 1 ELSE 2 END,name LIMIT 1",(version,k(address))).fetchone()
        if row:
            return (row[0]+'!' if row[0] else '')+row[1]
        row = self.db.execute('SELECT name FROM functions WHERE version=? AND context=? AND address=?',(version,self.context,k(address))).fetchone()
        return row[0] if row else f'mem_{address:x}'

    def _presentation(self, version, address):
        row = self.db.execute('SELECT representation,size FROM definitions WHERE version=? AND context=? AND address=?',(version,self.context,k(address))).fetchone()
        if row is None:
            row = self.db.execute('SELECT representation,size FROM data_items WHERE version=? AND context=? AND address=?',(version,self.context,k(address))).fetchone()
        if row is None:
            instruction=self.db.execute('SELECT size FROM instructions WHERE version=? AND context=? AND address=?',(version,self.context,k(address))).fetchone()
            if instruction:
                row=('code',instruction[0])
        return {'name':self._label(version,address),'representation':row[0] if row else None,'size':row[1] if row else None}

    def information(self, topic='summary', version=None, limit=200, offset=0):
        from .project import integer
        limit,offset = integer(limit,'limit',1,10000),integer(offset,'offset',0,(1<<63)-1)
        with self.transaction():
            v = self.version(version)['id']
            doc = self._document(v)
            if topic == 'summary':
                return {'version':v,'header':doc['header'],'counts':{x:len(doc.get(x,[])) for x in ('sections','imports','exports','strings')},'warnings':doc.get('warnings',[])}
            if topic == 'header':
                return {'version':v,'header':doc['header'],'warnings':doc.get('warnings',[])}
            if topic not in ('sections','imports','exports','strings'):
                raise ValueError('unknown information topic')
            items=[]
            for original in doc.get(topic,[])[offset:offset+limit]:
                item=dict(original)
                if item.get('address') is not None:
                    if 'name' in item:
                        item['original_name']=item['name']
                    presentation=self._presentation(v,item['address'])
                    item['name']=presentation['name']
                    item['representation']=presentation['representation']
                    item['representation_size']=presentation['size']
                for field in ('address','virtual_address'):
                    if item.get(field) is not None:
                        item[field]=h(item[field])
                items.append(item)
            result={'version':v,'items':items,'total':len(doc.get(topic,[])),'offset':offset,'has_more':offset+len(items)<len(doc.get(topic,[])),'warnings':doc.get('warnings',[])}
            if topic=='imports':
                row=self.db.execute('SELECT document FROM recoveries WHERE version=?',(v,)).fetchone()
                result['recovery']=json.loads(row[0]) if row else None
            return result

    def _queue_code(self, version, address, reason):
        return self.db.execute('INSERT OR IGNORE INTO work(version,context,address,reason) VALUES (?,?,?,?)',(version,self.context,k(address),reason)).rowcount

    def _queue_data(self, version, address, reason, reopen=False):
        added=self.db.execute('INSERT OR IGNORE INTO investigations(version,context,address,reason) VALUES (?,?,?,?)',(version,self.context,k(address),reason)).rowcount
        if reopen and not added:
            self.db.execute("UPDATE investigations SET state='pending',detail=NULL WHERE version=? AND context=? AND address=?",(version,self.context,k(address)))
        return added

    def _add_xref(self, version, source, target, kind, evidence):
        return self.db.execute('INSERT OR IGNORE INTO xrefs VALUES (?,?,?,?,?,?)',(version,self.context,k(source),k(target),kind,evidence)).rowcount

    def _data_one(self, version, address, regions, document):
        region=next((r for r in regions if r.start<=address<r.start+len(r.data)),None)
        if region is None:
            self.db.execute("UPDATE investigations SET state='outside',detail='outside mapped bytes' WHERE version=? AND context=? AND address=?",(version,self.context,k(address)))
            return
        offset=address-region.start
        data=region.data[offset:offset+4096]
        defined=self.db.execute('SELECT representation,size FROM definitions WHERE version=? AND context=? AND address=?',(version,self.context,k(address))).fetchone()
        symbol=self.db.execute("SELECT kind FROM symbols WHERE version=? AND address=? AND kind IN ('imports','recovered_import') LIMIT 1",(version,k(address))).fetchone()
        string=next((s for s in document.get('strings',[]) if s.get('address')==address),None)
        width=self.bits//8
        representation='scalar'
        value=None
        source='referenced mapped bytes'
        size=min(width,len(data))
        if defined:
            representation,size=defined
            if size>len(data):
                raise ValueError('definition exceeds mapped bytes')
            source='user definition'
        elif symbol:
            representation='import_slot'
        elif string:
            representation=string['encoding']
            size=min(string['size'],len(region.data)-offset)
            try:
                text=data[:size].decode(representation).split('\0',1)[0]
                if len(text)<4 or any(not ch.isprintable() for ch in text):
                    raise ValueError('not a current string')
                value={'text':text,'truncated':True} if size>len(data) else text
                source='snapshot bytes with file string hint'
            except (UnicodeError,ValueError):
                representation,size,value='scalar',min(width,len(data)),None
        else:
            end=data.find(b'\0')
            if end>=4 and all(32<=b<127 or b in (9,10,13) for b in data[:end]):
                representation,size,value='ascii',end+1,data[:end].decode('ascii')
                source='referenced NUL-terminated bytes'
        if representation in ('ascii','utf-16le') and value is None:
            raw=data[:size]
            try:
                value=raw.decode('ascii' if representation=='ascii' else 'utf-16le').rstrip('\0')
            except UnicodeDecodeError as exc:
                raise ValueError('bytes do not match requested string representation') from exc
        elif value is None:
            value=int.from_bytes(data[:size],'little')
        if representation in ('scalar','pointer') and size in (4,8):
            target=int.from_bytes(data[:size],'little')
            target_region=next((r for r in regions if r.start<=target<r.start+len(r.data)),None)
            if target_region:
                representation='pointer' if defined else 'pointer_candidate'
                value={'target':h(target)}
                if self._add_xref(version,address,target,'pointer','static pointer value; candidate unless corroborated'):
                    self._queue_data(version,target,'pointer target')
                # Promote only corroborated indirect control-flow, never an arbitrary pointer.
                sources=self.db.execute("SELECT DISTINCT i.address,i.flow FROM xrefs x JOIN instructions i ON i.version=x.version AND i.context=x.context AND i.address=x.source JOIN operand_refs o ON o.version=x.version AND o.context=x.context AND o.source=x.source AND o.target=x.target WHERE x.version=? AND x.context=? AND x.target=? AND x.kind='data' AND i.flow IN ('indirect_call','indirect_jump') AND o.role='memory' AND o.width=?",(version,self.context,k(address),self.bits//8)).fetchall()
                if sources and target_region.executable:
                    for ins in sources:
                        kind='resolved_call' if ins['flow']=='indirect_call' else 'resolved_branch'
                        self._add_xref(version,int(ins['address'],16),target,kind,'indirect operand + stored pointer value')
                        if kind=='resolved_call':
                            self.db.execute('INSERT OR IGNORE INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',(version,self.context,k(target),f'sub_{target:x}','resolved indirect call'))
                    self._queue_code(version,target,'corroborated indirect pointer')
        self.db.execute('INSERT INTO data_items VALUES (?,?,?,?,?,?,?) ON CONFLICT(version,context,address) DO UPDATE SET representation=excluded.representation,size=excluded.size,value=excluded.value,source=excluded.source',
            (version,self.context,k(address),representation,size,json.dumps(value),source))
        self.db.execute("UPDATE investigations SET state='done',detail=NULL WHERE version=? AND context=? AND address=?",(version,self.context,k(address)))

    def analyze(self, version=None, start=None, max_instructions=10000,cs=None,ds=None,es=None,ss=None):
        if self.meta["format"]=="MZ":
            return self._dos_analyze(version,start,max_instructions,cs,ds,es,ss)
        if any(x is not None for x in (cs,ds,es,ss)):
            raise ValueError("segment registers apply only to DOS MZ")
        from .project import integer,number
        from .decoder import decode
        budget=integer(max_instructions,'max_instructions',1,1_000_000)
        with self.transaction(True):
            v=self.version(version)['id']
            self.db.execute('INSERT OR IGNORE INTO analysis_state(version) VALUES (?)',(v,))
            regions=self.regions(v)
            doc=self._document(v)
            definitions=[(int(r[0],16),r[1],r[2]) for r in self.db.execute('SELECT address,representation,size FROM definitions WHERE version=? AND context=?',(v,self.context))]
            def mapped(a):
                return next((r for r in regions if r.start<=a<r.start+len(r.data)),None)
            def executable(a):
                r=mapped(a)
                return r is not None and (r.executable or any(x<=a<x+s and t=='code' for x,t,s in definitions))
            def blocked(a,size):
                return any(t!='code' and a<x+s and a+size>x for x,t,s in definitions)
            def fact_count():
                return sum(self.db.execute(f'SELECT count(*) FROM {table} WHERE version=?',(v,)).fetchone()[0] for table in ('instructions','xrefs','functions','data_items','operand_refs'))
            if start is not None:
                a=number(start)
                if not executable(a):
                    raise ValueError('analysis start is not in executable mapped bytes')
                self._queue_code(v,a,'user seed')
                self.db.execute('INSERT OR IGNORE INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',(v,self.context,k(a),f'sub_{a:x}','user seed'))
            before=fact_count()
            attempted=decoded=data_processed=passes=0
            while attempted<budget:
                work=self.db.execute("SELECT address FROM work WHERE version=? AND context=? AND state='pending' ORDER BY rowid LIMIT 1",(v,self.context)).fetchone()
                if work:
                    attempted+=1
                    a=int(work[0],16)
                    region=mapped(a)
                    ins=decode(region.data[a-region.start:a-region.start+16],a,self.arch,self.bits) if region and executable(a) else None
                    if ins is None or blocked(a,ins['size']):
                        state='blocked' if ins is not None else 'invalid'
                        self.db.execute('UPDATE work SET state=?,detail=? WHERE version=? AND context=? AND address=?',(state,'user data definition' if state=='blocked' else 'invalid or outside executable mapping',v,self.context,k(a)))
                        continue
                    flow,target=ins['flow'],ins['target']
                    inserted=self.db.execute('INSERT OR IGNORE INTO instructions VALUES (?,?,?,?,?,?,?,?,?)',(v,self.context,k(a),ins['size'],ins['bytes'],ins['mnemonic'],ins['operands'],flow,k(target) if target is not None else None))
                    self.db.execute("UPDATE work SET state='decoded',detail=? WHERE version=? AND context=? AND address=?",('unresolved indirect control flow' if flow.startswith('indirect') else None,v,self.context,k(a)))
                    decoded+=inserted.rowcount
                    if target is not None:
                        kind='call' if flow=='call' else 'branch'
                        self._add_xref(v,a,target,kind,'decoded direct operand')
                        if executable(target):
                            self._queue_code(v,target,kind)
                            if flow=='call':
                                self.db.execute('INSERT OR IGNORE INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',(v,self.context,k(target),f'sub_{target:x}','direct call'))
                    for reference in ins.get('references',[]):
                        self.db.execute('INSERT OR IGNORE INTO operand_refs VALUES (?,?,?,?,?,?,?)',(v,self.context,k(a),reference['operand_index'],reference['role'],k(reference['target']),reference.get('width')))
                    for ref in ins.get('data_refs',[]):
                        inserted=self._add_xref(v,a,ref,'data','decoded static memory operand')
                        if mapped(ref):
                            self._queue_data(v,ref,'decoded memory reference',reopen=bool(inserted))
                    for immediate in ins.get('immediates',[]):
                        ref=immediate['value']
                        if mapped(ref):
                            inserted=self._add_xref(v,a,ref,'offset_candidate','immediate equals mapped address; heuristic offset')
                            self.db.execute('INSERT OR IGNORE INTO operand_refs VALUES (?,?,?,?,?,?,?)',(v,self.context,k(a),immediate['operand_index'],'offset_candidate',k(ref),None))
                            self._queue_data(v,ref,'mapped immediate candidate',reopen=bool(inserted))
                    following=a+ins['size']
                    if flow in ('next','call','conditional','indirect_call') and executable(following):
                        self._queue_code(v,following,'fallthrough')
                        if flow=='conditional':
                            self._add_xref(v,a,following,'fallthrough','decoded conditional fallthrough')
                    continue
                self.db.execute('UPDATE analysis_state SET entry_complete=1 WHERE version=?',(v,))
                task=self.db.execute("SELECT address FROM investigations WHERE version=? AND context=? AND state='pending' ORDER BY rowid LIMIT 1",(v,self.context)).fetchone()
                if task:
                    attempted+=1
                    data_processed+=1
                    self._data_one(v,int(task[0],16),regions,doc)
                    continue
                state=self.db.execute('SELECT seeds_admitted FROM analysis_state WHERE version=?',(v,)).fetchone()[0]
                if not state:
                    # Disconnected symbols/exports are a later recursive seed phase.
                    for row in self.db.execute('SELECT address FROM functions WHERE version=? AND context=? ORDER BY address',(v,self.context)).fetchall():
                        self._queue_code(v,int(row[0],16),'deferred symbol or export seed')
                    for item in doc.get('exports',[]):
                        a=item.get('address')
                        if a is not None and executable(a):
                            self._queue_code(v,a,'deferred export seed')
                    self.db.execute('UPDATE analysis_state SET seeds_admitted=1 WHERE version=?',(v,))
                    passes+=1
                    continue
                break
            pending_code=self.db.execute("SELECT count(*) FROM work WHERE version=? AND state='pending'",(v,)).fetchone()[0]
            pending_data=self.db.execute("SELECT count(*) FROM investigations WHERE version=? AND state='pending'",(v,)).fetchone()[0]
            state=self.db.execute('SELECT entry_complete,seeds_admitted FROM analysis_state WHERE version=?',(v,)).fetchone()
            stable=not pending_code and not pending_data and bool(state[1])
            # If the last item consumed exactly the budget, metadata-only scheduling
            # may still be outstanding; it is deliberately not called stable.
            pending=pending_code+pending_data+(0 if state[1] else 1)
            return dict(version=v,decoded=decoded,attempted=attempted,data_processed=data_processed,new_facts=fact_count()-before,pending=pending,pending_code=pending_code,pending_data=pending_data,entry_complete=bool(state[0]),pending_seed_phase=not bool(state[1]),passes=passes,stable=stable,budget_exhausted=not stable and attempted>=budget)

    def _reset_analysis(self, version):
        if self.meta["format"]=="MZ":
            return self._dos_reset(version)
        for table in ('instructions','xrefs','operand_refs','data_items','work','investigations'):
            self.db.execute(f'DELETE FROM {table} WHERE version=?',(version,))
        self.db.execute("DELETE FROM functions WHERE version=? AND source IN ('direct call','resolved indirect call')",(version,))
        self.db.execute('INSERT INTO analysis_state VALUES (?,0,0) ON CONFLICT(version) DO UPDATE SET entry_complete=0,seeds_admitted=0',(version,))
        self._queue_code(version,self.meta['entry'],'entry')
        for row in self.db.execute("SELECT address FROM definitions WHERE version=? AND representation='code'",(version,)).fetchall():
            self._queue_code(version,int(row[0],16),'user code definition')
        for row in self.db.execute("SELECT address FROM definitions WHERE version=? AND representation!='code'",(version,)).fetchall():
            self._queue_data(version,int(row[0],16),'user data definition')

    def represent(self, address, representation, size=None, author='agent', version=None, max_instructions=10000):
        from .project import number,integer
        a=self._address(address)
        allowed={'code':1,'byte':1,'word':2,'dword':4,'qword':8,'pointer':self.bits//8,'ascii':None,'utf-16le':None}
        if representation not in allowed:
            raise ValueError('representation must be code, byte, word, dword, qword, pointer, ascii or utf-16le')
        if size is None:
            size=allowed[representation]
        size=integer(size,'size',1,4096)
        if allowed[representation] is not None and representation!='code' and size!=allowed[representation]:
            raise ValueError('numeric/pointer representation size must match its width')
        if representation=='utf-16le' and size%2:
            raise ValueError('UTF-16 size must be even')
        if not isinstance(author,str) or not author or len(author)>256:
            raise ValueError('author must contain 1..256 characters')
        with self.transaction(True):
            v=self.version(version)['id']
            r=self._mapping(v,a)
            if not r or a+size>r.start+len(r.data):
                raise ValueError('definition must fit in one mapped region')
            if representation in ('ascii','utf-16le'):
                r.data[a-r.start:a-r.start+size].decode('ascii' if representation=='ascii' else 'utf-16le')
            overlap=self.db.execute('SELECT address,size FROM definitions WHERE version=? AND context=? AND address!=?',(v,self.context,k(a))).fetchall()
            if any(a<int(row[0],16)+row[1] and a+size>int(row[0],16) for row in overlap):
                raise ValueError('definition overlaps another explicit definition')
            self.db.execute('INSERT INTO definitions VALUES (?,?,?,?,?,?) ON CONFLICT(version,context,address) DO UPDATE SET representation=excluded.representation,size=excluded.size,author=excluded.author',(v,self.context,k(a),representation,size,author))
            self._reset_analysis(v)
            analysis=self.analyze(version=v,max_instructions=max_instructions)
            return dict(version=v,address=h(a),representation=representation,size=size,analysis=analysis)

    def items(self, version=None, limit=200, offset=0):
        from .project import integer
        limit,offset=integer(limit,'limit',1,10000),integer(offset,'offset',0,(1<<63)-1)
        with self.transaction():
            v=self.version(version)['id']
            rows=self.db.execute('SELECT * FROM data_items WHERE version=? ORDER BY address LIMIT ? OFFSET ?',(v,limit,offset)).fetchall()
            result=[]
            for r in rows:
                value=json.loads(r['value'])
                if isinstance(value,dict) and 'target' in value:
                    target=int(value['target'],0)
                    value={**value,'target_name':self._label(v,target)}
                result.append(dict(address=h(int(r['address'],16)),**self._presentation(v,int(r['address'],16)),value=value,source=r['source']))
            return result

    def queue(self, version=None, limit=200, offset=0):
        from .project import integer
        limit,offset=integer(limit,'limit',1,10000),integer(offset,'offset',0,(1<<63)-1)
        v=self.version(version)['id']
        rows=self.db.execute("SELECT 'decode' AS kind,address,reason,state,detail FROM work WHERE version=? UNION ALL SELECT 'investigate_data',address,reason,state,detail FROM investigations WHERE version=? ORDER BY kind,address LIMIT ? OFFSET ?",(v,v,limit,offset))
        return [dict(kind=r['kind'],address=h(int(r['address'],16)),reason=r['reason'],state=r['state'],detail=r['detail'],**self._presentation(v,int(r['address'],16))) for r in rows]

    def recover_imports(self, module_exports=None, export_map=None, candidate_slots=None, version=None, max_slots=4096, gap_limit=10):
        from .chimprec import recover_iat
        from .project import number
        if export_map is not None:
            if module_exports is not None:
                raise ValueError('use module_exports or export_map, not both')
            p=Path(export_map)
            if p.stat().st_size>16*1024*1024:
                raise ValueError('export map exceeds 16 MiB')
            module_exports=json.loads(p.read_text())
        if not isinstance(module_exports,list):
            raise ValueError('module_exports must be an export-address list')
        normalized=[{**entry,'address':number(entry['address'])} for entry in module_exports]
        slots=[number(a) for a in candidate_slots] if candidate_slots is not None else None
        with self.transaction(True):
            v=self.version(version)['id']
            analysis=None
            if slots is None:
                analysis=self.analyze(version=v)
                slots=[int(row[0],16) for row in self.db.execute("SELECT DISTINCT target FROM operand_refs WHERE version=? AND context=? AND role='memory' AND width=?",(v,self.context,self.bits//8))]
            result=recover_iat(self.regions(v),self.bits,normalized,slots,max_slots,gap_limit)
            if analysis is not None:
                result['analysis']=analysis
                result['source']['candidate_selection']='recursive decoded memory operands'
                if not analysis['stable']:
                    result['warnings'].append('Recursive analysis is budget-limited; IAT candidate discovery is partial. Resume analysis and repeat recovery.')
            self.db.execute("DELETE FROM symbols WHERE version=? AND kind='recovered_import'",(v,))
            for item in result['entries']:
                if item.get('resolved'):
                    alternatives=item['alternatives']
                    modules={alt['module'] for alt in alternatives}
                    # A combined label preserves alias uncertainty; never arbitrarily pick one.
                    label='|'.join(sorted({alt.get('name') or f"ordinal_{alt.get('ordinal')}" for alt in alternatives}))
                    module=next(iter(modules)) if len(modules)==1 else '{'+ '|'.join(sorted(modules))+'}'
                    self.db.execute('INSERT OR IGNORE INTO symbols VALUES (?,?,?,?,?,?)',(v,k(item['address']),'recovered_import',label,module,json.dumps(item)))
            self.db.execute('INSERT INTO recoveries VALUES (?,?) ON CONFLICT(version) DO UPDATE SET document=excluded.document',(v,json.dumps(result)))
            return result
