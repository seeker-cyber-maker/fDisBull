"""Persistent coordination of architecture-neutral analysis passes.

Only decoder adapters and ABI profile selection know the target machine. Results
are bounded static candidates; neither CFG closure nor a fixed point proves full
coverage, source function ownership, or feasible runtime behavior.
"""
import hashlib
import json
from .semantics import instruction_semantics
from .flowdata import analyze_flow
from .frames import analyze_frame, _select_abi
from .indirect import recover_indirect
from .summaries import (builtin_signatures, validate_signature, match_signatures,
                        resolve_summary, instantiate_effects)


def _key(a):return f'{a:016x}'
def _selector(context):return int(context.rsplit('=',1)[1],16) if context and ':cs=' in context else None

def _dump(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def _automatic_summary(contract):
    source=contract.get('source') if isinstance(contract,dict) else None
    return isinstance(source,dict) and source.get('kind')=='exact_signature'


class AdvancedMixin:
    def _advanced_identity(self,address,cs=None,version=None):
        v=self.version(version)['id']
        if self.meta['format']=='MZ':
            a,selector=self._dos_parse_address(address,cs)
            if selector is None:
                contexts=[r[0] for r in self.db.execute('SELECT context FROM instructions WHERE version=? AND address=?',(v,_key(a)))]
                if len(contexts)!=1:raise ValueError('choose an exact DOS CS:IP or supply cs')
                context=contexts[0]
            else:context=f'x86:16:little:cs={selector:04x}'
        else:
            from .project import number
            if cs is not None:raise ValueError('CS applies only to DOS MZ')
            a,context=number(address),self.context
        return v,context,a

    def _sync_advanced_jobs(self,v):
        self.db.execute("INSERT OR IGNORE INTO advanced_jobs(version,context,address,reason) SELECT f.version,f.context,f.address,'candidate entry' FROM functions f JOIN instructions i ON i.version=f.version AND i.context=f.context AND i.address=f.address WHERE f.version=?",(v,))
        self.db.execute("UPDATE advanced_jobs SET state='pending',reason='candidate entry restored' WHERE version=? AND state='orphaned' AND EXISTS(SELECT 1 FROM functions f JOIN instructions i ON i.version=f.version AND i.context=f.context AND i.address=f.address WHERE f.version=advanced_jobs.version AND f.context=advanced_jobs.context AND f.address=advanced_jobs.address)",(v,))

    def advanced_status(self,version=None):
        with self.transaction():
            v=self.version(version)['id']
            states=dict(self.db.execute('SELECT state,count(*) FROM advanced_jobs WHERE version=? GROUP BY state',(v,)))
            missing=self.db.execute('SELECT count(*) FROM functions f JOIN instructions i ON i.version=f.version AND i.context=f.context AND i.address=f.address WHERE f.version=? AND NOT EXISTS(SELECT 1 FROM advanced_jobs j WHERE j.version=f.version AND j.context=f.context AND j.address=f.address)',(v,)).fetchone()[0]
            pending=states.get('pending',0)+states.get('partial',0)+missing
            return dict(version=v,states=states,unregistered_entries=missing,pending=pending,
                        stable=bool(set(states)-{'orphaned'}) and pending==0,scope='implemented derived-analysis jobs',
                        note='A fixed point is not complete binary coverage. Unknown transfers and semantic operations remain explicit.')

    def function_analysis(self,address,version=None,cs=None):
        with self.transaction():
            v,context,a=self._advanced_identity(address,cs,version)
            job=self.db.execute('SELECT * FROM advanced_jobs WHERE version=? AND context=? AND address=?',(v,context,_key(a))).fetchone()
            result=self.db.execute('SELECT document FROM advanced_results WHERE version=? AND context=? AND address=?',(v,context,_key(a))).fetchone()
            return dict(version=v,context=context,address=hex(a),state=job['state'] if job else 'missing',
                        generation=job['generation'] if job else 0,reason=job['reason'] if job else 'run auto-analyze',
                        stale=job is None or job['state']!='done',result=json.loads(result[0]) if result else None)

    def set_summary(self,address,name,version=None,cs=None,prototype=None,summary=None,abi=None,author='agent'):
        if not isinstance(author,str) or not 0<len(author)<=256:raise ValueError('author must contain 1..256 characters')
        contract=resolve_summary(name,source=dict(kind='user_confirmed',author=author),prototype=prototype,summary=summary)
        if contract is None:raise ValueError('unknown library identity requires an explicit prototype or summary')
        if abi is not None:
            _select_abi(dict(arch=self.arch,bits=self.bits),{},abi)
            contract['abi']=abi
        with self.transaction(True):
            v,context,a=self._advanced_identity(address,cs,version)
            if self._mapping(v,a) is None:raise ValueError('summary address must be mapped')
            old=self.db.execute('SELECT document FROM function_summaries WHERE version=? AND context=? AND address=?',(v,context,_key(a))).fetchone()
            document=_dump(contract)
            invalidated=[]
            if old is None or old[0]!=document:
                self.db.execute('INSERT OR REPLACE INTO function_summaries VALUES (?,?,?,?,?)',(v,context,_key(a),document,author))
                invalidated=self._invalidate_derived(v,a,reason='function summary changed',context=context)
            return dict(version=v,address=hex(a),context=context,summary=contract,invalidated_tasks=invalidated)

    def summaries(self,version=None):
        v=self.version(version)['id']
        return dict(version=v,items=[dict(address=hex(int(r['address'],16)),context=r['context'],author=r['author'],summary=json.loads(r['document'])) for r in self.db.execute('SELECT * FROM function_summaries WHERE version=? ORDER BY context,address',(v,))])

    def add_signature(self,signature,version=None):
        document=validate_signature(signature)
        with self.transaction(True):
            v=self.version(version)['id']
            self.db.execute('INSERT OR REPLACE INTO library_signatures VALUES (?,?,?)',(v,document['id'],_dump(document)))
            invalidated=self._invalidate_derived(v,reason='signature catalog changed')
            return dict(version=v,signature=document,invalidated_tasks=invalidated)

    def signatures(self,version=None):
        v=self.version(version)['id']
        return dict(version=v,builtin=builtin_signatures(),registered=[json.loads(r[0]) for r in self.db.execute('SELECT document FROM library_signatures WHERE version=? ORDER BY name',(v,))])

    def _summary_at(self,v,context,a):
        row=self.db.execute('SELECT document FROM function_summaries WHERE version=? AND context=? AND address=?',(v,context,_key(a))).fetchone()
        if row:
            contract=json.loads(row[0])
            if not _automatic_summary(contract):return contract
            # Byte-derived identities belong to their qualified analysis result,
            # rather than being authored interpretations that survive a patch.
            qualified=self.db.execute('SELECT r.document FROM advanced_results r JOIN advanced_jobs j ON j.version=r.version AND j.context=r.context AND j.address=r.address WHERE r.version=? AND r.context=? AND r.address=? AND j.state=\'done\'',(v,context,_key(a))).fetchone()
            if qualified:
                document=json.loads(qualified[0]);signature_id=contract['source'].get('id')
                if any(m.get('signature_id')==signature_id and m.get('name')==contract.get('name') for m in document.get('signature_matches',[])):
                    return contract
        from .linkage import canonical_library_name
        rows=self.db.execute("SELECT name,kind,module,detail FROM symbols WHERE version=? AND address=? AND kind IN ('imports','exports','recovered_import','import_stubs') ORDER BY kind",(v,_key(a))).fetchall()
        recovered=[row for row in rows if row['kind']=='recovered_import']
        if recovered:rows=recovered
        contracts=[]
        for row in rows:
            detail=json.loads(row['detail'])
            identities=detail.get('alternatives',[detail])
            for identity in identities:
                if identity.get('callable') is False or identity.get('addend',0)!=0:return None
                if row['kind']=='exports' and identity.get('code_seed_eligible',identity.get('is_code',identity.get('is_function',True))) is False:return None
                original=identity.get('name',row['name'])
                if not isinstance(original,str) or not original:return None
                name=canonical_library_name(original,self.meta['format'])
                source=dict(kind='export' if row['kind']=='exports' else 'import',module=identity.get('module') or row['module'],original_name=original,
                            binding_kind=identity.get('kind'),version=identity.get('version'),evidence=identity.get('evidence'))
                contract=resolve_summary(name,source=source)
                # Every competing identity must support the same contract;
                # dropping unknown aliases would turn ambiguity into certainty.
                if contract is None:return None
                contracts.append(contract)
        if len({r['name'] for r in contracts})==1:return contracts[0]
        return None

    def _default_abi(self):
        # Selection is explicit evidence at the boundary; the algorithms consume
        # a profile, never a file format or CPU-specific mnemonic.
        fmt=self.meta['format']
        if self.arch=='x86' and self.bits==64:
            return 'x86_64_win64' if fmt=='PE' else 'x86_64_sysv' if fmt in ('ELF','Mach-O') else None
        if self.arch=='arm64' and fmt=='ELF':return 'aarch64_aapcs64'
        if self.arch=='arm64' and fmt=='Mach-O':return 'aarch64_darwin'
        return None

    def _advanced_one(self,v,job,options):
        context,address=job['context'],int(job['address'],16)
        snapshot=self.cfg(address,v,cs=_selector(context),max_instructions=options['max_instructions'])
        semantics={n['id']:instruction_semantics(bytes.fromhex(n['bytes']),int(n['address'],16),self.arch,self.bits,cs=_selector(n['context'])) for n in snapshot['nodes']}
        regions=self.regions(v)
        dependencies=set()
        recovered_slots={int(r[0],16) for r in self.db.execute("SELECT address FROM symbols WHERE version=? AND kind='recovered_import'",(v,))}
        unresolved_slots=[]
        for row in self.db.execute("SELECT address,detail FROM symbols WHERE version=? AND kind='imports'",(v,)):
            detail=json.loads(row['detail']);slot=int(row['address'],16)
            if slot not in recovered_slots and detail.get('binding_state')=='runtime_unresolved':
                unresolved_slots.append((slot,slot+detail.get('pointer_width',self.bits//8)))
        def dependency(kind,a,size=1,ctx=''):
            if isinstance(a,int) and isinstance(size,int) and size>0 and 0<=a<a+size<=1<<64:dependencies.add((kind,a,size,ctx))
        def read_memory(a,size):
            dependency('memory',a,size)
            if not isinstance(a,int) or not isinstance(size,int) or not 1<=size<=4096:return None
            if any(a<last and a+size>first for first,last in unresolved_slots):return None
            if any(t=='unexplored' and a<x+s and a+size>x for x,s,t in definitions):return None
            region=next((r for r in regions if r.start<=a and a+size<=r.start+len(r.data)),None)
            return region.data[a-region.start:a-region.start+size] if region else None
        definitions=[(int(r[0],16),r[1],r[2]) for r in self.db.execute('SELECT address,size,representation FROM definitions WHERE version=?',(v,))]
        def executable(a):
            r=next((r for r in regions if r.start<=a<r.start+len(r.data)),None)
            return bool(r and (r.executable or any(x<=a<x+s and t=='code' for x,s,t in definitions)) and not any(x<=a<x+s and t!='code' for x,s,t in definitions))
        initial={}
        if self.meta['format']=='MZ':
            row=self.db.execute('SELECT registers FROM dos_states WHERE version=? AND context=? AND address=?',(v,context,_key(address))).fetchone()
            if row:initial={k:value for k,value in json.loads(row[0]).items() if type(value) is int and k in ('ds','es','ss','fs','gs','sp','bp')}
        previous=self.db.execute('SELECT document FROM function_summaries WHERE version=? AND context=? AND address=?',(v,context,_key(address))).fetchone()
        previous_contract=json.loads(previous[0]) if previous else None
        contract=self._summary_at(v,context,address)
        selected_abi=(contract or {}).get('abi',options.get('abi'))
        profile,_,_=_select_abi(snapshot,semantics,selected_abi)

        bindings_by_source={}
        def call_targets(call):
            if call['source'] in bindings_by_source:
                return [(context,b['target'],b['target_kind']) for b in bindings_by_source[call['source']]]
            if call.get('target_address'):
                return [(call.get('target_context') or context,int(call['target_address'],16),'code')]
            return [(context,int(r[0],16),'import_slot') for r in self.db.execute("SELECT o.target FROM operand_refs o JOIN symbols s ON s.version=o.version AND s.address=o.target AND s.kind IN ('imports','recovered_import') WHERE o.version=? AND o.context=? AND o.source=? AND o.role='memory'",(v,call['context'],_key(int(call['address'],16))))]

        # The callee's qualified calling convention determines effects at this
        # call. A routine's own ABI does not establish every callee's ABI.
        call_profiles={}
        for call in snapshot['calls']:
            source=call['source']
            candidates=call_profiles.setdefault(source,[])
            targets=call_targets(call)
            if not targets:candidates.append(None)
            for callee_context,callee,_ in targets:
                callee_contract=self._summary_at(v,callee_context,callee)
                if callee_contract is None or not callee_contract.get('abi'):
                    candidates.append(None)
                    continue
                call_profile,_,_=_select_abi(snapshot,semantics,callee_contract['abi'])
                candidates.append(dict(profile=call_profile,source=dict(address=hex(callee),context=callee_context,identity=callee_contract['source'])))
        for source,candidates in call_profiles.items():
            if candidates and all(c is not None for c in candidates) and len({_dump(c['profile']) for c in candidates})==1:
                semantics[source]['call_abi']=candidates[0]['profile']
                semantics[source]['call_abi_source']=[c['source'] for c in candidates]
        flow=analyze_flow(snapshot['nodes'],snapshot['edges'],snapshot['entry'],semantics,initial=initial,read_memory=read_memory,abi=profile if selected_abi else None,max_steps=options['max_steps'])
        from .linkage import import_call_bindings
        bindings=import_call_bindings(snapshot,semantics,flow,self._document(v).get('imports',[]),self.bits//8)
        for binding in bindings:
            bindings_by_source.setdefault(binding['source'],[]).append(binding)
            source=int(binding['source_address'],16);target=binding['target']
            dependency('call',target,1,context)
            exists=self.db.execute("SELECT 1 FROM xrefs WHERE version=? AND context=? AND source=? AND target=? AND kind='import_call'",(v,binding['source_context'],_key(source),_key(target))).fetchone()
            if not exists:
                self.db.execute('INSERT INTO xrefs VALUES (?,?,?,?,?,?)',(v,binding['source_context'],_key(source),_key(target),'import_call',_dump(binding)))
            owned=self.db.execute("SELECT 1 FROM advanced_edges WHERE version=? AND source_context=? AND source=? AND target=? AND kind='import_call'",(v,binding['source_context'],_key(source),_key(target))).fetchone()
            if not exists or owned:
                self.db.execute('INSERT OR IGNORE INTO advanced_edges VALUES (?,?,?,?,?,?,?,?)',(v,context,_key(address),binding['source_context'],_key(source),_key(target),context,'import_call'))
        frame=analyze_frame(snapshot,semantics,flow,abi=selected_abi)
        indirect=recover_indirect(snapshot,semantics,flow,read_memory,executable,max_entries=options['max_entries'])
        added=0
        for candidate in indirect['candidates']:
            target=candidate['target'];target_context=candidate.get('target_context') or candidate['source_context']
            selector=_selector(target_context)
            dependency('target',target,1,target_context)
            r=next((r for r in regions if r.start<=target<r.start+len(r.data)),None)
            decoded=instruction_semantics(r.data[target-r.start:target-r.start+16],target,self.arch,self.bits,cs=selector) if r else {}
            blocked=not decoded.get('valid') or any(t!='code' and target<x+s and target+decoded.get('size',1)>x for x,s,t in definitions)
            if self.meta['format']=='MZ' and (selector is None or not 0<=target-selector*16<=65535):blocked=True
            if blocked:
                candidate.update(admitted=False,rejection='invalid_native_target_or_explicit_representation')
                continue
            kind='resolved_call' if candidate['flow']=='indirect_call' else 'resolved_branch'
            source=int(candidate['source_address'],16);source_context=candidate['source_context']
            exists=self.db.execute('SELECT 1 FROM xrefs WHERE version=? AND context=? AND source=? AND target=? AND kind=?',(v,source_context,_key(source),_key(target),kind)).fetchone()
            evidence=_dump(dict(rule='bounded_indirect',candidate=candidate))
            if not exists:
                self.db.execute('INSERT OR IGNORE INTO xrefs VALUES (?,?,?,?,?,?)',(v,source_context,_key(source),_key(target),kind,evidence))
                if selector is not None:self._dos_edge(v,source_context,source,target,selector,kind,evidence)
                added+=1
            owned=self.db.execute('SELECT 1 FROM advanced_edges WHERE version=? AND source_context=? AND source=? AND target=? AND target_context=? AND kind=?',(v,source_context,_key(source),_key(target),target_context,kind)).fetchone()
            if not exists or owned:
                self.db.execute('INSERT OR IGNORE INTO advanced_edges VALUES (?,?,?,?,?,?,?,?)',(v,context,_key(address),source_context,_key(source),_key(target),target_context,kind))
            known=self.db.execute('SELECT 1 FROM instructions WHERE version=? AND context=? AND address=?',(v,target_context,_key(target))).fetchone()
            if not known:
                if selector is not None:
                    state=flow['in_states'].get(candidate['source'],{}).get('registers',{})
                    values={k:e['value'] for k,e in state.items() if isinstance(e,dict) and e.get('op')=='const' and k in ('ds','es','ss','bp','sp')}
                    self._dos_enqueue(v,selector,target,values,'bounded indirect target')
                else:self._queue_code(v,target,'bounded indirect target')
            if kind=='resolved_call':
                self.db.execute('INSERT OR IGNORE INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',(v,target_context,_key(target),f'sub_{target:x}','bounded indirect call candidate'))
            candidate.update(admitted=True,native_validation=dict(size=decoded['size'],context=target_context))
        registered=[json.loads(r[0]) for r in self.db.execute('SELECT document FROM library_signatures WHERE version=?',(v,))]
        rows=[dict(n,address=int(n['address'],16)) for n in sorted(snapshot['nodes'],key=lambda n:int(n['address'],16))]
        signature_scope=bool(snapshot['graph_closed'] and rows and rows[0]['address']==address and all(n['context']==context for n in rows))
        matches=match_signatures(rows,builtin_signatures()+registered,arch=self.arch,bits=self.bits) if signature_scope else []
        if not contract and len({m['name'] for m in matches})==1:
            match=matches[0]
            source=dict(kind='exact_signature',id=match['signature_id'],match=match['match'],
                        input_sha256=hashlib.sha256(bytes.fromhex(match['input_hex'])).hexdigest(),
                        masked_offsets=match.get('masked_offsets',[]))
            contract=resolve_summary(match['name'],source=source,confidence=match.get('confidence'))
            if contract:
                if match.get('abi'):contract['abi']=match['abi']
                if previous_contract!=contract:
                    # Invalidation retracts derived contracts too. Publish the
                    # newly qualified identity only after its consumers are stale.
                    self._invalidate_derived(v,address,reason='qualified signature identity',context=context)
                self.db.execute('INSERT OR REPLACE INTO function_summaries VALUES (?,?,?,?,?)',(v,context,_key(address),_dump(contract),'exact signature'))
                if contract.get('abi')!=selected_abi:
                    selected_abi=contract.get('abi',selected_abi)
                    frame=analyze_frame(snapshot,semantics,flow,abi=selected_abi)
        elif contract is None and _automatic_summary(previous_contract):
            self.db.execute('DELETE FROM function_summaries WHERE version=? AND context=? AND address=?',(v,context,_key(address)))
            self._invalidate_derived(v,address,reason='signature identity no longer qualified',context=context)
        effects=[];frame_by_abi={str(selected_abi):frame}
        for call in snapshot['calls']:
            targets=call_targets(call)
            for callee_context,callee,kind in targets:
                dependency('call',callee,1,callee_context)
                summary=self._summary_at(v,callee_context,callee)
                if summary is None:continue
                call_abi=summary.get('abi',selected_abi)
                if str(call_abi) not in frame_by_abi:frame_by_abi[str(call_abi)]=analyze_frame(snapshot,semantics,flow,abi=call_abi)
                observed=next((c for c in frame_by_abi[str(call_abi)]['calls'] if c['instruction']==call['source']),None)
                if observed is None:continue
                # Near DOS pointers require segment-aware prototypes. Do not
                # reinterpret a 16-bit offset as a physical address implicitly.
                state=dict(flow['in_states'].get(call['source'],{}),pointer_bits=self.bits)
                instantiated=instantiate_effects(summary,observed,state)
                for effect in instantiated['effects']:
                    effect.update(call_site=call['address'],context=call['context'],callee=hex(callee),callee_context=callee_context,callee_kind=kind,summary_name=summary['name'],summary_source=summary['source'],binding_evidence=bindings_by_source.get(call['source'],[]),conditions=instantiated['conditions']+(['Declared import binding is unchanged and resolves to the named contract.'] if summary['source'].get('kind')=='import' else []),abi=call_abi,arguments=observed['argument_values'])
                    if self.meta['format']=='MZ':
                        effect.update(resolved=False,address=None,end_exclusive=None,address_space='near_offset_unresolved_segment')
                        # These are useful offset facts, but none is a physical
                        # DOS byte range until a pointer segment is established.
                        for key in ('address_range','possible_range'):
                            if key in effect:effect['offset_'+key]=effect.pop(key)
                    elif effect['address'] is not None and effect['size']:
                        dependency('effect',effect['address'],effect['size'])
                    effects.append(effect)
                if instantiated['diagnostics']:effects.append(dict(call_site=call['address'],context=call['context'],callee=hex(callee),summary_name=summary['name'],resolved=False,diagnostics=instantiated['diagnostics']))
        for node in snapshot['nodes']:
            dependency('instruction',int(node['address'],16),node['size'],node['context'])
            for reference in node['references']:dependency('data_reference',int(reference['target'],16),reference.get('width') or 1)
        for gap in snapshot['gaps']+snapshot['frontier']:dependency('frontier',int(gap['address'],16),1,gap.get('context') or '')
        self.db.execute('DELETE FROM advanced_dependencies WHERE version=? AND context=? AND address=?',(v,context,_key(address)))
        for kind,start,size,dep_context in dependencies:self._derived_dependency(v,context,address,kind,start,size,dep_context)
        partial=bool(snapshot['budget_exhausted'] or flow['budget_exhausted'] or indirect['budget']['partial'])
        result=dict(version=v,entry=snapshot['entry'],address=hex(address),context=context,status='candidate',
                    graph=dict(instructions=snapshot['instruction_count'],blocks=snapshot['block_count'],closed=snapshot['graph_closed'],gaps=snapshot['gaps'],unresolved=snapshot['unresolved'],frontier=snapshot['frontier']),
                    dataflow=dict(stable=flow['stable'],steps=flow['steps'],unresolved=flow['unresolved'],budget_exhausted=flow['budget_exhausted']),
                    frame=frame,indirect=indirect,import_calls=bindings,signature_matches=matches,summary=contract,call_effects=effects,
                    dependencies=len(dependencies),budget_exhausted=partial,assumptions=snapshot['assumptions']+['Memory reads use immutable snapshot bytes; recovered targets are conditional static candidates.'])
        generation=job['generation']+1
        state='partial' if partial else 'pending' if added else 'done'
        self.db.execute('INSERT OR REPLACE INTO advanced_results VALUES (?,?,?,?,?)',(v,context,_key(address),generation,_dump(result)))
        self.db.execute('UPDATE advanced_jobs SET state=?,generation=?,reason=? WHERE version=? AND context=? AND address=?',(state,generation,'budget exhausted' if partial else 'new control-flow facts' if added else 'derived fixed point',v,context,_key(address)))
        return dict(address=hex(address),context=context,state=state,generation=generation,added_edges=added,budget_exhausted=partial)

    def auto_analyze(self,version=None,start=None,cs=None,ds=None,es=None,ss=None,max_instructions=10000,max_functions=200,max_steps=100000,max_entries=256,max_rounds=8,abi=None):
        from .project import integer
        for name,value,maximum in [('max_instructions',max_instructions,100000),('max_functions',max_functions,10000),('max_steps',max_steps,1000000),('max_entries',max_entries,65536),('max_rounds',max_rounds,100)]:integer(value,name,1,maximum)
        with self.transaction(True):
            v=self.version(version)['id']
            enable_key=f'advanced_enabled_{v}'
            legacy_retracted=0
            if not self.db.execute('SELECT 1 FROM metadata WHERE key=?',(enable_key,)).fetchone():
                # The older shallow analyzer treated file pointer bytes as a
                # snapshot assumption. Advanced recovery requires reaching-state
                # and write-history evidence instead, including on migration.
                self._invalidate_derived(v,reason='advanced memory-state analysis enabled')
                legacy_retracted=self.db.execute("DELETE FROM xrefs WHERE version=? AND kind IN ('resolved_call','resolved_branch') AND evidence='indirect operand + stored pointer value'",(v,)).rowcount
                self.db.execute("DELETE FROM functions WHERE version=? AND source='resolved indirect call'",(v,))
                if self.meta['format']=='MZ':
                    # DOS's earlier path-specific register/pointer resolver used
                    # call/branch edge names. Retain its bytes and operand
                    # observations, but require normalized reaching-state proof
                    # before these indirect edges participate in the new CFG.
                    predicate="EXISTS(SELECT 1 FROM instructions i WHERE i.version=dos_edges.version AND i.context=dos_edges.source_context AND i.address=dos_edges.source AND i.flow IN ('indirect_call','indirect_jump'))"
                    self.db.execute("DELETE FROM dos_edges WHERE version=? AND kind IN ('call','branch') AND "+predicate,(v,))
                    predicate="EXISTS(SELECT 1 FROM instructions i WHERE i.version=xrefs.version AND i.context=xrefs.context AND i.address=xrefs.source AND i.flow IN ('indirect_call','indirect_jump'))"
                    legacy_retracted+=self.db.execute("DELETE FROM xrefs WHERE version=? AND kind IN ('call','branch') AND "+predicate,(v,)).rowcount
                    self.db.execute("DELETE FROM functions WHERE version=? AND source IN ('file-backed near/far pointer under known segment state','segmented decoded operand') AND NOT EXISTS(SELECT 1 FROM dos_edges d WHERE d.version=functions.version AND d.target=functions.address AND d.target_context=functions.context AND d.kind IN ('call','resolved_call'))",(v,))
                self.db.execute("UPDATE advanced_jobs SET state='orphaned',reason='legacy snapshot candidate retracted' WHERE version=? AND NOT EXISTS(SELECT 1 FROM functions f WHERE f.version=advanced_jobs.version AND f.context=advanced_jobs.context AND f.address=advanced_jobs.address)",(v,))
                self.db.execute('INSERT INTO metadata VALUES (?,?)',(enable_key,'true'))
            option_key=f'advanced_options_{v}'
            stored=self.db.execute('SELECT value FROM metadata WHERE key=?',(option_key,)).fetchone()
            previous=json.loads(stored[0]) if stored else {}
            selected=abi if abi is not None else previous.get('abi',self._default_abi())
            _select_abi(dict(arch=self.arch,bits=self.bits),{},selected)
            options=dict(max_instructions=max_instructions,max_steps=max_steps,max_entries=max_entries,abi=selected)
            if previous and previous!=options:self._invalidate_derived(v,reason='analysis options changed')
            self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(option_key,_dump(options)))
            self.db.execute("UPDATE advanced_jobs SET state='pending' WHERE version=? AND state='partial'",(v,))
            receipts=[];base_runs=[];rounds=0;partial=set()
            for round_index in range(max_rounds):
                rounds+=1
                if round_index==0 or self.analysis_status(v)['pending']:
                    base_runs.append(self.analyze(v,start if round_index==0 else None,max_instructions,cs if round_index==0 else None,ds if round_index==0 else None,es if round_index==0 else None,ss if round_index==0 else None))
                self._sync_advanced_jobs(v)
                jobs=self.db.execute("SELECT * FROM advanced_jobs WHERE version=? AND state='pending' ORDER BY generation,address,context",(v,)).fetchall()
                for job in jobs:
                    if len(receipts)>=max_functions:break
                    identity=(job['context'],job['address'])
                    if identity in partial:continue
                    receipt=self._advanced_one(v,job,options);receipts.append(receipt)
                    if receipt['budget_exhausted']:partial.add(identity)
                status=self.advanced_status(v);base=self.analysis_status(v)
                if status['stable'] and base['stable']:break
                if len(receipts)>=max_functions or (not base['pending'] and not self.db.execute("SELECT 1 FROM advanced_jobs WHERE version=? AND state='pending' LIMIT 1",(v,)).fetchone()):break
            status=self.advanced_status(v);base=self.analysis_status(v)
            stable=bool(base['stable'] and status['stable'])
            return dict(version=v,stable=stable,budget_exhausted=not stable,rounds=rounds,processed_jobs=len(receipts),jobs=receipts,
                        analysis=base,advanced=status,base_runs=base_runs,options=options,
                        legacy_snapshot_edges_retracted=legacy_retracted,
                        note='Resumable fixed point of implemented static rules; unknown targets and semantic ambiguity remain in function-analysis.')

    def call_effects(self,address=None,size=1,access='all',version=None,include_unresolved=True,limit=200,offset=0):
        from .project import integer
        integer(size,'size',1,1<<20);integer(limit,'limit',1,10000);integer(offset,'offset',0,1<<63)
        if access not in ('all','read','write'):raise ValueError('access must be all, read or write')
        if not isinstance(include_unresolved,bool):raise ValueError('include_unresolved must be a boolean')
        a=self._address(address) if address is not None else None
        if a is not None and a+size>1<<64:raise ValueError('queried interval exceeds the 64-bit address range')
        v=self.version(version)['id'];items=[];seen=set();stale=0
        for row in self.db.execute('SELECT r.document,j.state FROM advanced_results r JOIN advanced_jobs j ON j.version=r.version AND j.context=r.context AND j.address=r.address WHERE r.version=?',(v,)):
            if row['state']!='done':stale+=1;continue
            for effect in json.loads(row['document']).get('call_effects',[]):
                if access!='all' and effect.get('access') not in (access,'read_write'):continue
                resolved=effect.get('resolved',False)
                if not resolved and not include_unresolved:continue
                if resolved and access!='all' and (effect.get('end_exclusive') is None or effect.get('address') is None or effect['end_exclusive']<=effect['address']):continue
                if a is not None and resolved:
                    start,end=effect.get('address'),effect.get('end_exclusive')
                    if start is None or end is None or end<=start or not (start<a+size and end>a):continue
                if a is not None and not resolved:
                    possible=effect.get('possible_range')
                    if isinstance(possible,dict) and isinstance(possible.get('start'),int) and isinstance(possible.get('end_exclusive'),int):
                        low,high=possible['start'],possible['end_exclusive']
                        if high<=low or not (low<a+size and high>a):continue
                identity=_dump(effect)
                if identity in seen:continue
                seen.add(identity);items.append(effect)
        return dict(version=v,address=hex(a) if a is not None else None,size=size,items=items[offset:offset+limit],total=len(items),offset=offset,limit=limit,stale_jobs_excluded=stale,analysis=self.advanced_status(v),note='Qualified call-contract effects; combine with memory-accesses for instruction-level accesses. Unresolved effects remain possible candidates, not proven overlaps.')
