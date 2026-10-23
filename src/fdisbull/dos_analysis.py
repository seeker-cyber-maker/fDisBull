"""Recursive real-mode analysis with CS-keyed states and relocation seeds."""
import itertools
import json
import struct

from .dos_views import DOSViewsMixin

# Revision 2 stops promoting mutable far-descriptor file bytes to known state.
DOS_POINTER_REVISION = 2

DOS_DDL = """
CREATE TABLE IF NOT EXISTS dos_states(version INTEGER,context TEXT,address TEXT,registers TEXT NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(version,context,address));
CREATE TABLE IF NOT EXISTS dos_segments(version INTEGER,selector INTEGER,base TEXT,end TEXT,roles TEXT,sources TEXT,PRIMARY KEY(version,selector));
CREATE TABLE IF NOT EXISTS dos_edges(version INTEGER,source_context TEXT,source TEXT,target TEXT,target_context TEXT,kind TEXT,evidence TEXT,PRIMARY KEY(version,source_context,source,target,target_context,kind));
CREATE TABLE IF NOT EXISTS dos_seeds(version INTEGER,cs INTEGER,address TEXT,reason TEXT,evidence TEXT,state TEXT,PRIMARY KEY(version,cs,address,reason));
CREATE TABLE IF NOT EXISTS dos_constants(version INTEGER,address TEXT,width INTEGER,value INTEGER,kind TEXT,source TEXT,PRIMARY KEY(version,address,width,value,kind));
CREATE TABLE IF NOT EXISTS dos_data_scans(version INTEGER,selector INTEGER,PRIMARY KEY(version,selector));
CREATE INDEX IF NOT EXISTS work_pending ON work(version,state);
"""


def key(a):
    if not isinstance(a,int) or not 0<=a<0x100000:
        raise ValueError('DOS address requires an unwrapped linear value below 1 MiB')
    return f'{a:016x}'


def ctx(cs):
    return f'x86:16:little:cs={cs:04x}'


class DOSMixin(DOSViewsMixin):
    def _label(self,version,address):
        return self._dos_label(version,address) if self.meta['format']=='MZ' else super()._label(version,address)

    def _presentation(self,version,address):
        return self._dos_presentation(version,address) if self.meta['format']=='MZ' else super()._presentation(version,address)

    def _dos_prepare(self,version):
        self._dos_cached_v=version
        self._dos_cached_document=self._document(version)
        self._dos_cached_meta=self._dos_cached_document.get('dos',self.meta['loader_metadata'].get('dos',{}))
        self._dos_cached_regions=self.regions(version)
        self._dos_cached_sites={r['linear_address'] for r in self._dos_cached_meta.get('relocations',[])}
        self._dos_scanned_segments={r[0] for r in self.db.execute('SELECT selector FROM dos_data_scans WHERE version=?',(version,))}
        self._dos_startup_addresses=set()
        from .dos_decoder import decode_dos
        metadata=self._dos_cached_meta
        entry_cs=metadata.get('selected_entry_cs',metadata['entry_cs'])
        address=self.meta['entry']
        state=dict(ds=metadata['psp_segment'],es=metadata['psp_segment'],ss=metadata['stack_ss'],sp=metadata['sp'])
        for _ in range(128):
            region=next((r for r in self._dos_cached_regions if r.start<=address<r.start+len(r.data)),None)
            if region is None or not 0<=address-entry_cs*16<=65535:
                break
            ins=decode_dos(region.data[address-region.start:address-region.start+15],address,entry_cs,state)
            if ins is None:
                break
            self._dos_startup_addresses.add(address)
            if ins['flow']!='next':
                break
            state=ins['next_registers']
            address=ins['next_address']

    def _dos_metadata(self,version):
        if getattr(self,'_dos_cached_v',None)!=version:
            self._dos_prepare(version)
        return self._dos_cached_meta

    def _mapping(self,version,address):
        if self.meta['format']!='MZ':
            return super()._mapping(version,address)
        if getattr(self,'_dos_cached_v',None)!=version:
            self._dos_prepare(version)
        return next((r for r in self._dos_cached_regions if r.start<=address<r.start+len(r.data)),None)

    def _dos_init(self,image,version=1):
        metadata=image.metadata['dos']
        self._dos_prepare(version)
        with self.transaction(True):
            self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(f'dos_pointer_revision_{version}',json.dumps(DOS_POINTER_REVISION)))
            self.db.execute('DELETE FROM work WHERE version=?',(version,))
            self.db.execute('DELETE FROM functions WHERE version=?',(version,))
            candidates=metadata['segment_candidates']
            bases=sorted({item['linear_base'] for item in candidates if image.regions[0].start<=item['linear_base']<image.regions[0].start+len(image.regions[0].data)})
            end=image.regions[0].start+len(image.regions[0].data)
            for item in candidates:
                base=item['linear_base']
                if base>=end or base<image.regions[0].start:
                    continue
                bound=min([end,base+65536]+[n for n in bases if n>base])
                self.db.execute('INSERT OR IGNORE INTO dos_segments VALUES (?,?,?,?,?,?)',(version,item['segment'],key(base),key(bound) if bound<0x100000 else f'{bound:016x}',json.dumps(['candidate']),json.dumps(item['sources'][:16])))
            cs=metadata.get('selected_entry_cs',metadata['entry_cs'])
            if not 0<=image.entry-cs*16<=65535:
                candidates_cs=[item['segment'] for item in candidates if 0<=image.entry-item['segment']*16<=65535]
                if not candidates_cs:
                    raise ValueError('entry override has no available DOS CS context')
                cs=max(candidates_cs)
            self._dos_note_segment(version,cs,'code',{'kind':'MZ entry'})
            self._dos_note_segment(version,metadata['stack_ss'],'stack',{'kind':'MZ initial SS'})
            regs={'ds':metadata['psp_segment'],'es':metadata['psp_segment'],'ss':metadata['stack_ss'],'sp':metadata['sp']}
            self._dos_enqueue(version,cs,image.entry,regs,'MZ entry')
            self._dos_function(version,cs,image.entry,'entry','MZ entry')
            self.db.execute('INSERT OR REPLACE INTO analysis_state VALUES (?,0,0)',(version,))
            self._dos_catalog(version)

    def _dos_note_segment(self,v,cs,role,source):
        base=cs*16
        region=self._mapping(v,base)
        if not region:
            return False
        row=self.db.execute('SELECT roles,sources FROM dos_segments WHERE version=? AND selector=?',(v,cs)).fetchone()
        if row:
            roles,sources=json.loads(row[0]),json.loads(row[1])
            changed=role not in roles
            if not changed:
                return False
            roles.append(role)
            if len(sources)<24:
                sources.append(source)
            self.db.execute('UPDATE dos_segments SET roles=?,sources=? WHERE version=? AND selector=?',(json.dumps(sorted(set(roles))),json.dumps(sources),v,cs))
        else:
            bound=min(region.start+len(region.data),base+65536)
            self.db.execute('INSERT INTO dos_segments VALUES (?,?,?,?,?,?)',(v,cs,key(base),f'{bound:016x}',json.dumps([role]),json.dumps([source])))
            changed=True
        if role=='code' and changed:
            metadata=self._dos_metadata(v)
            already_catalogued=cs==metadata.get('selected_entry_cs',metadata['entry_cs']) or self.db.execute('SELECT 1 FROM dos_seeds WHERE version=? AND cs=? LIMIT 1',(v,cs)).fetchone()
            if not already_catalogued:
                # A newly corroborated indirect target can make previously
                # unclassified relocated data words into callback candidates.
                self.db.execute('DELETE FROM dos_data_scans WHERE version=?',(v,))
                self._dos_scanned_segments=set()
        return changed

    def _dos_function(self,v,cs,address,name,source):
        self.db.execute('INSERT OR IGNORE INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',(v,ctx(cs),key(address),name,source))

    def _dos_enqueue(self,v,cs,address,registers,reason,force=False):
        if not 0<=cs<=65535 or not 0<=address-cs*16<=65535 or not self._mapping(v,address):
            return False
        context=ctx(cs)
        row=self.db.execute('SELECT registers,state FROM dos_states WHERE version=? AND context=? AND address=?',(v,context,key(address))).fetchone()
        merged=dict(registers)
        if row and not force:
            old=json.loads(row[0])
            merged={}
            for name,value in old.items():
                if name not in registers:
                    continue
                incoming=registers[name]
                if name in ('ds','es','ss'):
                    values=set(value if isinstance(value,list) else [value])|set(incoming if isinstance(incoming,list) else [incoming])
                    if len(values)<=4:
                        merged[name]=next(iter(values)) if len(values)==1 else sorted(values)
                elif value==incoming:
                    merged[name]=value
            if old==merged:
                return False
        self.db.execute('INSERT INTO dos_states VALUES (?,?,?,?,?,?) ON CONFLICT(version,context,address) DO UPDATE SET registers=excluded.registers,state=excluded.state,reason=excluded.reason',(v,context,key(address),json.dumps(merged,sort_keys=True),'pending',reason))
        self.db.execute("INSERT INTO work(version,context,address,reason) VALUES (?,?,?,?) ON CONFLICT(version,context,address) DO UPDATE SET state='pending',detail=NULL",(v,context,key(address),reason))
        return True

    def _dos_add_seed(self,v,cs,address,reason,evidence):
        if not self._mapping(v,address) or not 0<=address-cs*16<=65535:
            return
        self.db.execute('INSERT OR IGNORE INTO dos_seeds VALUES (?,?,?,?,?,?)',(v,cs,key(address),reason,json.dumps(evidence,sort_keys=True),'deferred'))

    def _dos_catalog(self,v):
        metadata=self._dos_metadata(v)
        for relocation in metadata.get('relocations',[]):
            site=relocation['linear_address']
            raw=self._dos_read(v,site-3,5,file_backed=True)
            if raw and raw[0] in (0x9a,0xea):
                offset,selector=struct.unpack_from('<HH',raw,1)
                self._dos_add_seed(v,selector,selector*16+offset,'relocation-backed far-call pattern',{'site':hex(site-3),'file_offset':relocation['file_offset']-3,'kind':'candidate ISA pattern anchored by segment fixup'})

    def _dos_read(self,v,address,size,file_backed=False):
        if address is None or size<=0:
            return None
        metadata=self._dos_metadata(v)
        if file_backed and not metadata['image_base']<=address<=metadata['image_base']+metadata['module_size']-size:
            return None
        r=self._mapping(v,address)
        if not r or address+size>r.start+len(r.data):
            return None
        return r.data[address-r.start:address-r.start+size]

    def _dos_data_pointer_seeds(self,v,selector):
        if selector in self._dos_scanned_segments:
            return
        segment=self.db.execute('SELECT base,end FROM dos_segments WHERE version=? AND selector=?',(v,selector)).fetchone()
        if not segment:
            return
        self.db.execute('INSERT OR IGNORE INTO dos_data_scans VALUES (?,?)',(v,selector))
        self._dos_scanned_segments.add(selector)
        low,high=int(segment[0],16),int(segment[1],16)
        code_cs={row[0] for row in self.db.execute('SELECT DISTINCT cs FROM dos_seeds WHERE version=?',(v,))}
        code_cs.update(row[0] for row in self.db.execute('SELECT selector,roles FROM dos_segments WHERE version=?',(v,)) if 'code' in json.loads(row[1]))
        metadata=self._dos_metadata(v)
        code_cs.add(metadata.get('selected_entry_cs',metadata['entry_cs']))
        for relocation in self._dos_metadata(v).get('relocations',[]):
            site=relocation['linear_address']
            if not low+2<=site<high or (site-2)%2:
                continue
            raw=self._dos_read(v,site-2,4,file_backed=True)
            if raw:
                offset,cs=struct.unpack('<HH',raw)
                if cs in code_cs:
                    self._dos_add_seed(v,cs,cs*16+offset,'relocated data far-pointer candidate',{'slot':hex(site-2),'data_segment':f'{selector:04x}','kind':'callback candidate; not an observed call'})

    def _dos_edge(self,v,context,source,target,target_cs,kind,evidence):
        target_context=ctx(target_cs) if target_cs is not None else ''
        self.db.execute('INSERT OR IGNORE INTO dos_edges VALUES (?,?,?,?,?,?,?)',(v,context,key(source),key(target),target_context,kind,evidence))
        self.db.execute('INSERT OR IGNORE INTO xrefs VALUES (?,?,?,?,?,?)',(v,context,key(source),key(target),kind,evidence))

    def _dos_variants(self,registers):
        varying=[(name,value) for name,value in registers.items() if name in ('ds','es','ss') and isinstance(value,list)]
        if not varying:
            return [registers]
        result=[]
        for values in itertools.product(*(item[1] for item in varying)):
            state=dict(registers)
            state.update({varying[i][0]:value for i,value in enumerate(values)})
            result.append(state)
        return result

    def _dos_transfer_extras(self,v,ins,before):
        after=dict(ins['next_registers'])
        stack=[] if ins.get('stack_reset') else list(before.get('_stack',[]))
        if not ins.get('stack_reset') and 'push_value' in ins and ins.get('push_width',2)==2:
            stack=(stack+[ins['push_value']])[-16:]
        elif not ins.get('stack_reset') and ins.get('pop_register') and ins.get('pop_width',2)==2:
            value=stack.pop() if stack else None
            if value is not None:
                after[ins['pop_register']]=value
        if stack:
            after['_stack']=stack
        load=ins.get('load_far')
        if load and load.get('register'):
            # The descriptor's initial file bytes can have been overwritten by
            # an allocator return or file read before this routine is invoked.
            # Native decoding already killed both destinations. Without a
            # write-aware reaching definition, keep them unknown rather than
            # resurrecting even a nonzero snapshot pointer as an exact address.
            ins['unresolved'].append('far-pointer descriptor value is unknown; initial file bytes are not a proven reaching definition')
        return after

    def _dos_store_seed(self,v,cs,address,ins):
        # Only literal word stores, not arbitrary emulation or guessed runtime memory.
        import iced_x86 as ix
        native=ix.Decoder(16,bytes.fromhex(ins['bytes']),ip=ins['ip']).decode()
        if native.mnemonic!=ix.Mnemonic.MOV or native.op0_kind!=ix.OpKind.MEMORY or ix.MemorySizeExt.size(native.memory_size)!=2:
            return
        refs=[r for r in ins['references'] if r['operand_index']==0 and r['role']=='memory']
        immediates=[i for i in ins['immediates'] if i['operand_index']==1]
        if not refs or not immediates:
            return
        dest=refs[0]['target']
        if not self._mapping(v,dest):
            return
        relocated=any(site in self._dos_cached_sites for site in range(address,address+ins['size']))
        self.db.execute('INSERT OR IGNORE INTO dos_constants VALUES (?,?,?,?,?,?)',(v,key(dest),2,immediates[0]['value']&65535,'relocated_segment' if relocated else 'immediate',key(address)))
        for base in (dest,dest-2):
            if base<0:
                continue
            offsets=self.db.execute("SELECT DISTINCT value FROM dos_constants WHERE version=? AND address=? AND kind='immediate'",(v,key(base))).fetchall()
            segments=self.db.execute("SELECT DISTINCT value FROM dos_constants WHERE version=? AND address=? AND kind='relocated_segment'",(v,key(base+2))).fetchall()
            if len(offsets)==len(segments)==1:
                target_cs=segments[0][0]
                metadata=self._dos_metadata(v)
                known_code=target_cs==metadata.get('selected_entry_cs',metadata['entry_cs']) or self.db.execute("SELECT 1 FROM dos_seeds WHERE version=? AND cs=? AND reason='relocation-backed far-call pattern' LIMIT 1",(v,target_cs)).fetchone()
                if known_code:
                    self._dos_add_seed(v,target_cs,target_cs*16+offsets[0][0],'relocated far-pointer initialization',{'slot':hex(base),'source':hex(address),'kind':'candidate paired literal stores'})

    def _dos_analyze(self,version=None,start=None,max_instructions=10000,cs=None,ds=None,es=None,ss=None):
        from .project import integer
        from .dos_decoder import decode_dos
        budget=integer(max_instructions,'max_instructions',1,1_000_000)
        with self.transaction(True):
            v=self.version(version)['id']
            self._dos_prepare(v)
            metadata=self._dos_metadata(v)
            if not self.db.execute('SELECT 1 FROM dos_states WHERE version=?',(v,)).fetchone():
                self._dos_reset(v)
            preferred_work=None
            if start is not None or any(x is not None for x in (cs,ds,es,ss)):
                address,selector=self._dos_parse_address(start if start is not None else self.meta['entry'],cs)
                if start is None and selector is None:
                    selector=metadata.get('selected_entry_cs',metadata['entry_cs'])
                if selector is None:
                    selectors=[r[0] for r in self.db.execute('SELECT selector FROM dos_segments WHERE version=? AND base<=? AND end>? ORDER BY base DESC',(v,key(address),key(address)))]
                    selector=selectors[0] if selectors else metadata['entry_cs']
                state={}
                for name,value in (('ds',ds),('es',es),('ss',ss)):
                    if value is not None:
                        state[name]=integer(value,name,0,65535)
                if self._dos_enqueue(v,selector,address,state,'user segmented seed',force=True):
                    preferred_work=(ctx(selector),key(address))
                self._dos_function(v,selector,address,f'sub_{selector:04x}_{address-selector*16:04x}','user seed')
            fact_tables=('instructions','dos_edges','operand_refs','functions','data_items','dos_seeds','dos_constants')
            before=sum(self.db.execute(f'SELECT count(*) FROM {t} WHERE version=?',(v,)).fetchone()[0] for t in fact_tables)
            attempted=decoded=data_processed=0
            while attempted<budget:
                # Decode the requested seed within this call's budget, then resume
                # the persistent queue without discarding or starving older work.
                work=None
                if preferred_work is not None:
                    work=self.db.execute("SELECT context,address FROM work WHERE version=? AND context=? AND address=? AND state='pending'",(v,*preferred_work)).fetchone()
                    preferred_work=None
                if work is None:
                    work=self.db.execute("SELECT context,address FROM work WHERE version=? AND state='pending' ORDER BY rowid LIMIT 1",(v,)).fetchone()
                if work:
                    context,a=work[0],int(work[1],16)
                    if ':cs=' not in context:
                        self.db.execute("UPDATE work SET state='outside',detail='missing DOS CS context' WHERE version=? AND context=? AND address=?",(v,context,key(a)))
                        continue
                    selector=int(context.rsplit('=',1)[1],16)
                    row=self.db.execute('SELECT registers FROM dos_states WHERE version=? AND context=? AND address=?',(v,context,key(a))).fetchone()
                    registers=json.loads(row[0]) if row else {}
                    attempted+=1
                    raw=self._dos_read(v,a,min(15,metadata['image_base']+metadata['allocation_size']-a))
                    messages=[]
                    variants=self._dos_variants(registers)
                    self._clear_memory_facts(v,context,a)
                    self.db.execute("UPDATE work SET state='decoded',detail=NULL WHERE version=? AND context=? AND address=?",(v,context,key(a)))
                    for state in variants:
                        ins=decode_dos(raw,a,selector,state) if raw else None
                        blocked=self.db.execute("SELECT address,size FROM definitions WHERE version=? AND representation!='code'",(v,)).fetchall()
                        if ins is None or any(a<int(b[0],16)+b[1] and a+(ins['size'] if ins else 1)>int(b[0],16) for b in blocked):
                            self.db.execute("UPDATE work SET state='invalid',detail='invalid bytes, CS boundary or explicit data definition' WHERE version=? AND context=? AND address=?",(v,context,key(a)))
                            continue
                        inserted=self.db.execute('INSERT OR IGNORE INTO instructions VALUES (?,?,?,?,?,?,?,?,?)',(v,context,key(a),ins['size'],ins['bytes'],ins['mnemonic'],ins['operands'],ins['flow'],key(ins['target']) if ins['target'] is not None and ins['target']<0x100000 else None))
                        decoded+=inserted.rowcount
                        self._memory_facts(v,context,a,bytes.fromhex(ins['bytes']),selector,state)
                        self._dos_note_segment(v,selector,'code',{'kind':'recursive instruction decode'})
                        after=self._dos_transfer_extras(v,ins,state)
                        segment=after.get('ds')
                        if a in self._dos_startup_addresses and selector==metadata.get('selected_entry_cs',metadata['entry_cs']) and isinstance(segment,int) and self._mapping(v,segment*16) and 'primary_data_segment' not in metadata:
                            metadata['primary_data_segment']=segment
                            metadata['primary_data_segment_source']=hex(a)
                            document=self._document(v)
                            document['dos']=metadata
                            self.db.execute('UPDATE binary_info SET document=? WHERE version=?',(json.dumps(document),v))
                        for name in ('ds','es'):
                            segment=after.get(name)
                            if isinstance(segment,int) and name=='ds':
                                self._dos_note_segment(v,segment,'data',{'kind':'statically established DS','instruction':hex(a)})
                        messages.extend(ins['unresolved'])
                        target,target_cs=ins['target'],ins['target_cs']
                        indirect=ins.get('indirect')
                        normalized=self.db.execute('SELECT 1 FROM metadata WHERE key=?',(f'advanced_enabled_{v}',)).fetchone() is not None
                        if normalized and ins['flow'] in ('indirect_call','indirect_jump'):target,target_cs=None,None
                        if not normalized and target is None and indirect and indirect.get('pointer_address') is not None:
                            width=indirect['offset_size']+(2 if indirect['far'] else 0)
                            pointer=self._dos_read(v,indirect['pointer_address'],width,file_backed=True)
                            if pointer:
                                off=int.from_bytes(pointer[:indirect['offset_size']],'little')
                                if off<=65535:
                                    target_cs=int.from_bytes(pointer[indirect['offset_size']:],'little') if indirect['far'] else selector
                                    target=target_cs*16+off
                        if target is not None and target<0x100000:
                            kind='call' if ins['flow'] in ('call','indirect_call') else 'branch'
                            evidence='segmented decoded operand' if not indirect else 'file-backed near/far pointer under known segment state'
                            self._dos_edge(v,context,a,target,target_cs,kind,evidence)
                            if self._mapping(v,target):
                                callee=dict(after)
                                callee.pop('_stack',None)
                                if 'sp' in callee:
                                    if kind=='call' and 'call_stack_adjust' in ins:
                                        callee['sp']=(callee['sp']+ins['call_stack_adjust'])&65535
                                    elif kind=='call':
                                        callee.pop('sp')
                                self._dos_enqueue(v,target_cs,target,callee,kind)
                                if kind=='call':
                                    self._dos_function(v,target_cs,target,f'sub_{target_cs:04x}_{target-target_cs*16:04x}',evidence)
                        for reference in ins['references']:
                            ref=reference['target']
                            if ref>=0x100000:
                                messages.append('reference beyond supported unwrapped 1 MiB memory')
                                continue
                            self.db.execute('INSERT OR IGNORE INTO operand_refs VALUES (?,?,?,?,?,?,?)',(v,context,key(a),reference['operand_index'],reference['role'],key(ref),reference.get('width')))
                            if reference['role']!='code':
                                self._dos_edge(v,context,a,ref,None,'data','known segmented effective address; path-state alternatives retained')
                                if self._mapping(v,ref):
                                    self._queue_data(v,ref,'DOS segmented reference')
                        if target is not None and target<0x100000 and not any(r['target']==target and r['role']=='code' for r in ins['references']):
                            self.db.execute('INSERT OR IGNORE INTO operand_refs VALUES (?,?,?,?,?,?,?)',(v,context,key(a),0,'code',key(target),4 if ins['far'] else 2))
                        self._dos_store_seed(v,selector,a,ins)
                        if ins['flow'] in ('next','call','conditional','indirect_call'):
                            caller=dict(after)
                            if ins['flow'] in ('call','indirect_call'):
                                caller={name:value for name,value in caller.items() if name in ('ds','ss','sp','bp')}
                            evidence=('permitted call-return fallthrough; return is assumed' if ins['flow'] in ('call','indirect_call') else '16-bit conditional CS/IP fallthrough' if ins['flow']=='conditional' else '16-bit straight-line CS/IP fallthrough')
                            if 0<=ins['next_address']<0x100000:
                                self._dos_edge(v,context,a,ins['next_address'],selector,'fallthrough',evidence)
                            else:
                                messages.append('fallthrough beyond supported unwrapped 1 MiB memory')
                            self._dos_enqueue(v,selector,ins['next_address'],caller,'fallthrough')
                    self.db.execute("UPDATE dos_states SET state='done' WHERE version=? AND context=? AND address=?",(v,context,key(a)))
                    if messages:
                        self.db.execute('UPDATE work SET detail=? WHERE version=? AND context=? AND address=?',(json.dumps(sorted(set(messages))),v,context,key(a)))
                    continue
                self.db.execute('UPDATE analysis_state SET entry_complete=1 WHERE version=?',(v,))
                unscanned=[r[0] for r in self.db.execute('SELECT selector,roles FROM dos_segments WHERE version=?',(v,)) if 'data' in json.loads(r[1]) and r[0] not in self._dos_scanned_segments]
                if unscanned:
                    attempted+=1
                    self._dos_data_pointer_seeds(v,unscanned[0])
                    continue
                task=self.db.execute("SELECT address FROM investigations WHERE version=? AND state='pending' ORDER BY rowid LIMIT 1",(v,)).fetchone()
                if task:
                    attempted+=1
                    data_processed+=1
                    # The shared classifier honors definitions and current string bytes.
                    # Its flat-pointer rule requires width 4/8, so 16-bit DOS words
                    # retain their raw offset rather than inventing a segment.
                    a=int(task[0],16)
                    self._data_one(v,a,self._dos_cached_regions,self._dos_cached_document)
                    continue
                seeds=self.db.execute("SELECT cs,address,reason FROM dos_seeds WHERE version=? AND state='deferred' ORDER BY rowid",(v,)).fetchall()
                if seeds:
                    data_segments=[r[0] for r in self.db.execute('SELECT selector,roles FROM dos_segments WHERE version=?',(v,)) if 'data' in json.loads(r[1])]
                    for seed in seeds:
                        # Explicit roots restored by a policy refresh keep
                        # their identity, not stale inferred segment values.
                        state={} if seed['reason']=='user seed' else {'ss':metadata['stack_ss']}
                        if seed['reason']!='user seed':
                            if metadata.get('primary_data_segment') is not None:
                                state['ds']=metadata['primary_data_segment']
                            elif len(data_segments)==1:
                                state['ds']=data_segments[0]
                        a=int(seed['address'],16)
                        self._dos_enqueue(v,seed['cs'],a,state,'deferred '+seed['reason'])
                        self._dos_function(v,seed['cs'],a,f'sub_{seed["cs"]:04x}_{a-seed["cs"]*16:04x}',seed['reason'])
                    self.db.execute("UPDATE dos_seeds SET state='admitted' WHERE version=? AND state='deferred'",(v,))
                    continue
                self.db.execute('UPDATE analysis_state SET seeds_admitted=1 WHERE version=?',(v,))
                break
            pending_code=self.db.execute("SELECT count(*) FROM work WHERE version=? AND state='pending'",(v,)).fetchone()[0]
            pending_data=self.db.execute("SELECT count(*) FROM investigations WHERE version=? AND state='pending'",(v,)).fetchone()[0]
            pending_seeds=self.db.execute("SELECT count(*) FROM dos_seeds WHERE version=? AND state='deferred'",(v,)).fetchone()[0]
            pending_scans=sum('data' in json.loads(r[1]) and r[0] not in self._dos_scanned_segments for r in self.db.execute('SELECT selector,roles FROM dos_segments WHERE version=?',(v,)))
            state=self.db.execute('SELECT entry_complete,seeds_admitted FROM analysis_state WHERE version=?',(v,)).fetchone()
            stable=not(pending_code+pending_data+pending_seeds+pending_scans) and bool(state[1])
            after=sum(self.db.execute(f'SELECT count(*) FROM {t} WHERE version=?',(v,)).fetchone()[0] for t in fact_tables)
            return dict(version=v,decoded=decoded,attempted=attempted,data_processed=data_processed,new_facts=after-before,pending=pending_code+pending_data+pending_seeds+pending_scans+(0 if state[1] else 1),pending_code=pending_code,pending_data=pending_data,pending_seeds=pending_seeds,pending_segment_scans=pending_scans,entry_complete=bool(state[0]),stable=stable,budget_exhausted=not stable and attempted>=budget,assumptions=['Static minimum allocation; no PSP memory fabricated.','Call fallthrough preserves DS/SS/BP/SP by conventional DOS C calling convention; general registers and ES are unknown.','Deferred relocation candidates may assume startup DS (or the unique observed DS); candidate provenance is retained.','Stability covers implemented static rules; unresolved indirect/dynamic code remains explicit.'])

    def _dos_reset(self,v):
        self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(f'dos_pointer_revision_{v}',json.dumps(DOS_POINTER_REVISION)))
        for table in ('instructions','xrefs','operand_refs','data_items','work','investigations','dos_states','dos_edges','dos_constants','dos_seeds','dos_data_scans','functions','memory_refs','analysis_facts_revision'):
            self.db.execute(f'DELETE FROM {table} WHERE version=?',(v,))
        self._fresh_facts(v)
        self._dos_scanned_segments=set()
        self.db.execute('INSERT INTO analysis_state VALUES (?,0,0) ON CONFLICT(version) DO UPDATE SET entry_complete=0,seeds_admitted=0',(v,))
        metadata=self._dos_metadata(v)
        metadata.pop('primary_data_segment',None)
        metadata.pop('primary_data_segment_source',None)
        document=self._document(v)
        document['dos']=metadata
        self.db.execute('UPDATE binary_info SET document=? WHERE version=?',(json.dumps(document),v))
        original_candidates={item['segment']:item['sources'][:16] for item in metadata.get('segment_candidates',[])}
        for row in self.db.execute('SELECT selector FROM dos_segments WHERE version=?',(v,)).fetchall():
            sources=original_candidates.get(row[0],[{'kind':'prior inferred selector; roles require revalidation'}])
            self.db.execute('UPDATE dos_segments SET roles=?,sources=? WHERE version=? AND selector=?',(json.dumps(['candidate']),json.dumps(sources),v,row[0]))
        cs=metadata.get('selected_entry_cs',metadata['entry_cs'])
        self._dos_note_segment(v,cs,'code',{'kind':'MZ selected entry'})
        self._dos_note_segment(v,metadata['stack_ss'],'stack',{'kind':'MZ initial SS'})
        registers=dict(ds=metadata['psp_segment'],es=metadata['psp_segment'],ss=metadata['stack_ss'],sp=metadata['sp'])
        self._dos_enqueue(v,cs,self.meta['entry'],registers,'MZ entry')
        self._dos_function(v,cs,self.meta['entry'],'entry','MZ entry')
        self._dos_catalog(v)
        for row in self.db.execute('SELECT address,representation FROM definitions WHERE version=?',(v,)).fetchall():
            a=int(row[0],16)
            if row[1]=='code':
                choices=[r[0] for r in self.db.execute('SELECT selector FROM dos_segments WHERE version=? AND base<=? AND end>? ORDER BY base DESC',(v,key(a),key(a)))]
                if choices:
                    self._dos_enqueue(v,choices[0],a,{},'user code definition')
            elif row[1]!='unexplored':
                self._queue_data(v,a,'user data definition')

    def _dos_document_for_image(self,image,document):
        metadata=image.metadata['dos']
        document['dos']=metadata
        document['header'].update(dos_header=metadata['header_fields'],relocation_count=len(metadata['relocations']),load_segment=metadata['load_segment'],entrypoint=image.entry,entry_cs=metadata['entry_cs'],entry_ip=metadata['entry_ip'],selected_entry_cs=metadata.get('selected_entry_cs',metadata['entry_cs']),selected_entry_ip=image.entry-16*metadata.get('selected_entry_cs',metadata['entry_cs']))
        document['sections']=[dict(name='DOS load module (unclassified)',virtual_address=metadata['image_base'],virtual_size=metadata['allocation_size'],file_offset=metadata['header_size'],file_size=metadata['module_size'],permissions='rwx; possible code/data, not classification')]
        document['file_mappings']=image.metadata['file_mappings']
        document['warnings']=[s for s in document.get('warnings',[]) if 'structural metadata unavailable' not in s]
        document['warnings'].append('MZ has no explicit code/data section permissions; segment roles and bounds are inferred from references.')
        for item in document['strings']:
            offset=item['file_offset']-metadata['header_size']
            item['address']=metadata['image_base']+offset if 0<=offset and offset+item['size']<=metadata['module_size'] else None
        return document

    def _dos_patch_document(self,parent,version,source_bytes,patched):
        from .dos import load_mz
        from .inspection import inspect_binary
        from dataclasses import replace
        metadata=self._dos_metadata(parent)
        # Undo every fixup in reverse loader order. This also handles duplicates
        # and overlapping relocation words without writing relocated segments to disk.
        module=bytearray(patched[0].data[:metadata['module_size']])
        for relocation in reversed(metadata['relocations']):
            offset=relocation['linear_address']-metadata['image_base']
            word=int.from_bytes(module[offset:offset+2],'little')
            module[offset:offset+2]=((word-metadata['load_segment'])&65535).to_bytes(2,'little')
        source=source_bytes[:metadata['header_size']]+bytes(module)+source_bytes[metadata['declared_file_size']:]
        image=load_mz(source,load_segment=metadata['load_segment'],entry=self.meta['entry'],allow_secondary=metadata.get('secondary_format') is not None)
        image.metadata['dos']['selected_entry_cs']=metadata.get('selected_entry_cs',metadata['entry_cs'])
        image.metadata['dos']['selected_entry_ip']=self.meta['entry']-16*image.metadata['dos']['selected_entry_cs']
        image.metadata['dos']['selected_entry_cs_source']='inherited selected entry context from parent version'
        image=replace(image,regions=patched)
        document=self._dos_document_for_image(image,inspect_binary(source,image='mz' if metadata.get('secondary_format') else None))
        if patched[0].data[metadata['module_size']:]!=bytes(metadata['allocation_size']-metadata['module_size']):
            document['warnings'].append('Allocation-only memory edits are retained in the project snapshot and have no disk file counterpart.')
        self.db.execute('INSERT INTO binary_info VALUES (?,?,?)',(version,json.dumps(document),source))
        self._dos_prepare(version)
        self._dos_init(image,version)
