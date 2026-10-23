"""Durable dependency invalidation for derived analysis and structural edits."""
import json
from collections import deque

ADVANCED_DDL = """
CREATE TABLE IF NOT EXISTS advanced_jobs(version INTEGER NOT NULL,context TEXT NOT NULL,address TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',generation INTEGER NOT NULL DEFAULT 0,reason TEXT NOT NULL,PRIMARY KEY(version,context,address));
CREATE TABLE IF NOT EXISTS advanced_results(version INTEGER NOT NULL,context TEXT NOT NULL,address TEXT NOT NULL,generation INTEGER NOT NULL,document TEXT NOT NULL,PRIMARY KEY(version,context,address));
CREATE TABLE IF NOT EXISTS advanced_dependencies(version INTEGER NOT NULL,context TEXT NOT NULL,address TEXT NOT NULL,kind TEXT NOT NULL,dependency_context TEXT NOT NULL,start TEXT NOT NULL,last TEXT NOT NULL,PRIMARY KEY(version,context,address,kind,dependency_context,start,last));
CREATE INDEX IF NOT EXISTS advanced_dependency_range ON advanced_dependencies(version,start,last);
CREATE TABLE IF NOT EXISTS advanced_edges(version INTEGER NOT NULL,owner_context TEXT NOT NULL,owner_address TEXT NOT NULL,source_context TEXT NOT NULL,source TEXT NOT NULL,target TEXT NOT NULL,target_context TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(version,owner_context,owner_address,source_context,source,target,target_context,kind));
CREATE TABLE IF NOT EXISTS function_summaries(version INTEGER NOT NULL,context TEXT NOT NULL,address TEXT NOT NULL,document TEXT NOT NULL,author TEXT NOT NULL,PRIMARY KEY(version,context,address));
CREATE TABLE IF NOT EXISTS library_signatures(version INTEGER NOT NULL,name TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(version,name));
"""


def _key(a):return f'{a:016x}'


class IncrementalMixin:
    def _derived_dependency(self,v,context,address,kind,start,size=1,dependency_context=''):
        if not isinstance(start,int) or size<=0 or start<0 or start+size>1<<64:return
        self.db.execute('INSERT OR IGNORE INTO advanced_dependencies VALUES (?,?,?,?,?,?,?)',(v,context,_key(address),kind,dependency_context,_key(start),_key(start+size-1)))

    def _retract_advanced_edges(self,v,identities):
        for context,address in identities:
            owned=self.db.execute('SELECT * FROM advanced_edges WHERE version=? AND owner_context=? AND owner_address=?',(v,context,address)).fetchall()
            self.db.execute('DELETE FROM advanced_edges WHERE version=? AND owner_context=? AND owner_address=?',(v,context,address))
            for edge in owned:
                args=(v,edge['source_context'],edge['source'],edge['target'],edge['target_context'],edge['kind'])
                other=self.db.execute('SELECT 1 FROM advanced_edges WHERE version=? AND source_context=? AND source=? AND target=? AND target_context=? AND kind=? LIMIT 1',args).fetchone()
                if other:continue
                self.db.execute('DELETE FROM xrefs WHERE version=? AND context=? AND source=? AND target=? AND kind=?',(v,edge['source_context'],edge['source'],edge['target'],edge['kind']))
                self.db.execute('DELETE FROM dos_edges WHERE version=? AND source_context=? AND source=? AND target=? AND target_context=? AND kind=?',args)
                if edge['kind']=='resolved_call':
                    remaining=self.db.execute("SELECT 1 FROM xrefs WHERE version=? AND target=? AND kind IN ('call','resolved_call') LIMIT 1",(v,edge['target'])).fetchone()
                    if not remaining:
                        removed=self.db.execute("DELETE FROM functions WHERE version=? AND context=? AND address=? AND source='bounded indirect call candidate'",(v,edge['target_context'],edge['target'])).rowcount
                        if removed:
                            target_identity=(edge['target_context'],edge['target'])
                            self.db.execute("UPDATE advanced_jobs SET state='orphaned',reason='supporting call retracted' WHERE version=? AND context=? AND address=?",(v,*target_identity))
                            self._retract_advanced_edges(v,[target_identity])

    def _invalidate_derived(self,v,start=None,size=1,reason='dependency changed',context=None):
        if start is None:
            affected={(r['context'],r['address']) for r in self.db.execute("SELECT context,address FROM advanced_jobs WHERE version=? AND state!='orphaned'",(v,))}
        else:
            rows=self.db.execute('SELECT context,address,dependency_context FROM advanced_dependencies WHERE version=? AND start<=? AND last>=?',(v,_key(start+size-1),_key(start)))
            affected={(r['context'],r['address']) for r in rows if context is None or not r['dependency_context'] or r['dependency_context']==context}
        # Callers depend on summaries/effects at their callees' exact entries.
        queue=deque(affected)
        while queue:
            dep_context,dep_address=queue.popleft()
            for row in self.db.execute("SELECT context,address,dependency_context FROM advanced_dependencies WHERE version=? AND kind='call' AND start<=? AND last>=?",(v,dep_address,dep_address)):
                identity=(row['context'],row['address'])
                if identity not in affected and (not row['dependency_context'] or row['dependency_context']==dep_context):affected.add(identity);queue.append(identity)
        self._retract_advanced_edges(v,affected)
        for ctx,address in affected:
            self.db.execute("DELETE FROM function_summaries WHERE version=? AND context=? AND address=? AND json_extract(document,'$.source.kind')='exact_signature'",(v,ctx,address))
            self.db.execute("UPDATE advanced_jobs SET state='pending',reason=? WHERE version=? AND context=? AND address=? AND state!='orphaned'",(reason,v,ctx,address))
        return [f'{ctx}@0x{int(address,16):x}' for ctx,address in sorted(affected)]

    def _reset_derived(self,v):
        self.db.execute("DELETE FROM function_summaries WHERE version=? AND json_extract(document,'$.source.kind')='exact_signature'",(v,))
        self.db.execute("DELETE FROM functions WHERE version=? AND source='bounded indirect call candidate'",(v,))
        for table in ('advanced_jobs','advanced_results','advanced_dependencies','advanced_edges'):
            self.db.execute(f'DELETE FROM {table} WHERE version=?',(v,))

    def _copy_interpretations(self,parent,child):
        for table,columns in [('type_definitions','name,document,author,revision'),('type_bindings','address,name,type_name,size,author'),('function_summaries','context,address,document,author'),('library_signatures','name,document')]:
            predicate=" AND COALESCE(json_extract(document,'$.source.kind'),'')!='exact_signature'" if table=='function_summaries' else ''
            self.db.execute(f'INSERT INTO {table} SELECT ?,{columns} FROM {table} WHERE version=?'+predicate,(child,parent))
        for table,columns in [('external_files','name,filename,kind,sha256,data,author'),('file_type_bindings','file,offset,name,type_name,size,author'),('file_references','context,source,file,file_offset,width,count,stride,access,instruction_bytes,evidence,author'),('label_links','id,left_space,left_file,left_offset,left_last,right_space,right_file,right_offset,right_last,size,evidence,author'),('shared_label_names','space,file,offset,name,author,created')]:
            self.db.execute(f'INSERT INTO {table} SELECT ?,{columns} FROM {table} WHERE version=?',(child,parent))

    def _incremental_representation(self,v,start,size):
        """Retract dependency-indexed routine slices; legacy projects fall back.

        Retractions preserve separate candidates and re-seed their saved entry
        assumptions. Newly held bytes stay blocked by the existing decoder rules.
        """
        jobs=self.db.execute("SELECT * FROM advanced_jobs WHERE version=? AND state='done'",(v,)).fetchall()
        if not jobs:return None
        # A complete index is necessary to avoid retaining unidentified consumers.
        missing=self.db.execute('SELECT 1 FROM instructions i WHERE i.version=? AND NOT EXISTS (SELECT 1 FROM advanced_dependencies d WHERE d.version=i.version AND d.kind=\'instruction\' AND d.dependency_context=i.context AND d.start=i.address) LIMIT 1',(v,)).fetchone()
        if missing:return None
        changed=self._invalidate_derived(v,start,size,'representation changed')
        affected={(r['context'],r['address']) for r in self.db.execute("SELECT context,address FROM advanced_jobs WHERE version=? AND state='pending'",(v,))}
        # Retraction includes each affected routine slice. Shared instructions
        # make their other owners dependent too; close that relation before edits.
        identities=set()
        while True:
            for ctx,entry in affected:
                for r in self.db.execute("SELECT dependency_context,start FROM advanced_dependencies WHERE version=? AND context=? AND address=? AND kind='instruction'",(v,ctx,entry)):
                    identities.add((r['dependency_context'],r['start']))
            for ctx,address in identities:
                changed+=self._invalidate_derived(v,int(address,16),reason='shared instruction retraction',context=ctx)
            expanded={(r['context'],r['address']) for r in self.db.execute("SELECT context,address FROM advanced_jobs WHERE version=? AND state='pending'",(v,))}
            if expanded==affected:break
            affected=expanded
        # Handle explicitly held data even when no decoded routine refers to it.
        for r in self.db.execute('SELECT context,address,size FROM instructions WHERE version=? AND address<?',(v,_key(start+size))):
            if int(r['address'],16)+r['size']>start:identities.add((r['context'],r['address']))
        saved={}
        if self.meta['format']=='MZ':
            for ctx,entry in affected:
                row=self.db.execute('SELECT registers FROM dos_states WHERE version=? AND context=? AND address=?',(v,ctx,entry)).fetchone()
                saved[(ctx,entry)]=json.loads(row[0]) if row else {}
        for ctx,address in identities:
            for table,column in [('instructions','address'),('xrefs','source'),('operand_refs','source'),('memory_refs','source'),('work','address'),('dos_states','address')]:
                self.db.execute(f'DELETE FROM {table} WHERE version=? AND context=? AND {column}=?',(v,ctx,address))
            self.db.execute('DELETE FROM dos_edges WHERE version=? AND source_context=? AND source=?',(v,ctx,address))
            self.db.execute('DELETE FROM dos_constants WHERE version=? AND source=?',(v,address))
        overlapping=[r for r in self.db.execute('SELECT context,address,size FROM data_items WHERE version=? AND address<=?',(v,_key(start+size-1))) if int(r['address'],16)+r['size']>start]
        for row in overlapping:
            self.db.execute("DELETE FROM xrefs WHERE version=? AND context=? AND source=? AND kind='pointer'",(v,row['context'],row['address']))
            self.db.execute('DELETE FROM data_items WHERE version=? AND context=? AND address=?',(v,row['context'],row['address']))
            self.db.execute('DELETE FROM investigations WHERE version=? AND context=? AND address=?',(v,row['context'],row['address']))
        self.db.execute('DELETE FROM investigations WHERE version=? AND address>=? AND address<=?',(v,_key(start),_key(start+size-1)))
        # Stored input bytes are unchanged, so unrelated memory/access facts stay valid.
        for ctx,entry in affected:
            if self.meta['format']=='MZ' and ':cs=' in ctx:
                self._dos_enqueue(v,int(ctx.rsplit('=',1)[1],16),int(entry,16),saved.get((ctx,entry),{}),'dependency reanalysis',force=True)
            else:self._queue_code(v,int(entry,16),'dependency reanalysis')
        if self.meta['format']=='MZ':
            self.db.execute('DELETE FROM dos_data_scans WHERE version=?',(v,));self._dos_scanned_segments=set()
        definition=self.db.execute('SELECT representation FROM definitions WHERE version=? AND address=?',(v,_key(start))).fetchone()
        if definition and definition[0]=='code':
            if self.meta['format']=='MZ':
                contexts=[ctx for ctx,_ in identities if ':cs=' in ctx and 0<=start-int(ctx.rsplit('=',1)[1],16)*16<=65535]
                if not contexts:
                    metadata=self._dos_metadata(v);contexts=[f"x86:16:little:cs={metadata.get('selected_entry_cs',metadata['entry_cs']):04x}"]
                for ctx in set(contexts):self._dos_enqueue(v,int(ctx.rsplit('=',1)[1],16),start,{},'explicit code representation',force=True)
            else:self._queue_code(v,start,'explicit code representation')
        elif definition and definition[0]!='unexplored':self._queue_data(v,start,'explicit data representation')
        return dict(mode='dependency_index',invalidated_tasks=sorted(set(changed)),retracted_instructions=len(identities),preserved_instructions=self.db.execute('SELECT count(*) FROM instructions WHERE version=?',(v,)).fetchone()[0])
