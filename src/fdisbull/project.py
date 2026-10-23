"""Versioned SQLite store and bounded recursive control-flow traversal."""
from collections import deque
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

from .model import Region

MAX_ADDRESS = (1 << 64) - 1
SCHEMA = 8

def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("address must be an integer or integer string")
    result = int(value, 0) if isinstance(value, str) else int(value)
    if not 0 <= result <= MAX_ADDRESS:
        raise ValueError("address must be an unsigned 64-bit integer")
    return result

def integer(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in {low}..{high}")
    return value

def key(value):
    return f"{number(value):016x}"

def hx(value):
    return f"0x{number(value):x}"

def now():
    return datetime.now(timezone.utc).isoformat()

DDL = """
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE versions(id INTEGER PRIMARY KEY, parent INTEGER REFERENCES versions(id), label TEXT NOT NULL,
    origin TEXT NOT NULL, sha256 TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE regions(version INTEGER REFERENCES versions(id), name TEXT NOT NULL, start TEXT NOT NULL,
    data BLOB NOT NULL, executable INTEGER NOT NULL, writable INTEGER NOT NULL,
    PRIMARY KEY(version,start));
CREATE TABLE functions(version INTEGER REFERENCES versions(id), context TEXT NOT NULL, address TEXT NOT NULL,
    name TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate',
    PRIMARY KEY(version,context,address));
CREATE TABLE instructions(version INTEGER REFERENCES versions(id), context TEXT NOT NULL, address TEXT NOT NULL,
    size INTEGER NOT NULL, bytes TEXT NOT NULL, mnemonic TEXT NOT NULL, operands TEXT NOT NULL,
    flow TEXT NOT NULL, target TEXT, PRIMARY KEY(version,context,address));
CREATE TABLE xrefs(version INTEGER REFERENCES versions(id), context TEXT NOT NULL, source TEXT NOT NULL,
    target TEXT NOT NULL, kind TEXT NOT NULL, evidence TEXT NOT NULL,
    PRIMARY KEY(version,context,source,target,kind));
CREATE INDEX xrefs_target ON xrefs(version,context,target);
CREATE TABLE annotations(version INTEGER REFERENCES versions(id), context TEXT NOT NULL, address TEXT NOT NULL,
    kind TEXT NOT NULL, text TEXT NOT NULL, author TEXT NOT NULL, created TEXT NOT NULL, inherited_from INTEGER,
    PRIMARY KEY(version,context,address,kind));
CREATE TABLE work(version INTEGER REFERENCES versions(id), context TEXT NOT NULL, address TEXT NOT NULL,
    reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', detail TEXT,
    PRIMARY KEY(version,context,address));
"""

from .analysis import AnalysisMixin, EXTENSION_DDL
from .dos_analysis import DOSMixin, DOS_DDL
from .boundaries import BoundaryMixin
from .calls import CallViewsMixin
from .facts import FactsMixin, FACTS_DDL
from .memory import MemoryMixin
from .cfg import CFGMixin
from .typesystem import TypeSystemMixin, TYPE_DDL
from .external_files import ExternalFilesMixin, EXTERNAL_FILES_DDL
from .file_references import FileReferencesMixin, FILE_REFERENCES_DDL
from .shared_labels import SharedLabelsMixin, SHARED_LABELS_DDL
from .dos_state_refresh import DOSStateRefreshMixin
from .incremental import IncrementalMixin, ADVANCED_DDL
from .advanced import AdvancedMixin
from .membership_view import MembershipMixin


class Project(DOSStateRefreshMixin, SharedLabelsMixin, AdvancedMixin, MembershipMixin, FileReferencesMixin, ExternalFilesMixin, TypeSystemMixin, IncrementalMixin, FactsMixin, MemoryMixin, CFGMixin, CallViewsMixin, BoundaryMixin, DOSMixin, AnalysisMixin):
    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise ValueError(f"project does not exist: {self.path}")
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        try:
            meta = dict(self.db.execute("SELECT key,value FROM metadata"))
            if meta.get("application") != "fdisbull" or int(meta.get("schema", -1)) not in (1,2,3,4,5,6,7,SCHEMA):
                raise ValueError("unsupported project schema")
            if int(meta["schema"]) == 1:
                self.db.executescript("BEGIN IMMEDIATE;" + EXTENSION_DDL + "INSERT OR IGNORE INTO analysis_state SELECT id,0,0 FROM versions; UPDATE work SET state='pending',detail=NULL; UPDATE metadata SET value='2' WHERE key='schema'; COMMIT;")
            if int(meta["schema"]) in (1,2):
                self.db.executescript("BEGIN IMMEDIATE;"+DOS_DDL+"UPDATE metadata SET value='3' WHERE key='schema'; COMMIT;")
            else:
                self.db.executescript(DOS_DDL)
            if int(meta["schema"]) != SCHEMA:
                self.db.executescript("BEGIN IMMEDIATE;"+FACTS_DDL+TYPE_DDL+ADVANCED_DDL+EXTERNAL_FILES_DDL+FILE_REFERENCES_DDL+SHARED_LABELS_DDL+"UPDATE metadata SET value='8' WHERE key='schema'; COMMIT;")
            else:
                self.db.executescript(FACTS_DDL+TYPE_DDL+ADVANCED_DDL+EXTERNAL_FILES_DDL+FILE_REFERENCES_DDL+SHARED_LABELS_DDL)
            self.meta = {k:json.loads(v) for k,v in meta.items() if k not in ("application","schema")}
            self.arch, self.bits = self.meta["arch"], self.meta["bits"]
            self.context = f"{self.arch}:{self.bits}:little"
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA busy_timeout=30000")
        except Exception:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    @contextmanager
    def transaction(self, write=False):
        if self.db.in_transaction:
            yield
            return
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    @classmethod
    def create(cls, path, binary, **options):
        from .loader import load_image
        source = Path(binary)
        image = load_image(source, **options)
        return cls._create_image(path,source.name,image)

    @classmethod
    def _create_image(cls,path,filename,image):
        """Persist the exact validated immutable image without rereading its file."""
        # Validate our stable mapping independently of individual loader formats.
        ordered = sorted(image.regions, key=lambda r:r.start)
        end = 0
        for r in ordered:
            if not r.data:
                continue
            number(r.start)
            if r.start < end or r.start + len(r.data) > MAX_ADDRESS + 1:
                raise ValueError("overlapping or out-of-range image mappings")
            end = r.start + len(r.data)
        if not ordered or sum(len(r.data) for r in ordered) > 64 * 1024 * 1024:
            raise ValueError("empty image or mapped bytes exceed 64 MiB")
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb"):
            pass
        try:
            db = sqlite3.connect(target)
            try:
                db.executescript(DDL + EXTENSION_DDL + DOS_DDL + FACTS_DDL + TYPE_DDL + ADVANCED_DDL + EXTERNAL_FILES_DDL + FILE_REFERENCES_DDL + SHARED_LABELS_DDL)
                db.execute("PRAGMA journal_mode=WAL")
                meta = {"arch":image.arch,"bits":image.bits,"format":image.format,"entry":image.entry,
                        "filename":filename,"source_sha256":image.metadata["source_sha256"],
                        "loader_metadata":image.metadata}
                db.executemany("INSERT INTO metadata VALUES (?,?)",
                    [("application","fdisbull"),("schema",str(SCHEMA))] + [(k,json.dumps(v)) for k,v in meta.items()])
                db.execute("INSERT INTO versions VALUES (1,NULL,?,?,?,?)",
                    ("original","file import",cls.digest(image.regions),now()))
                context = f"{image.arch}:{image.bits}:little"
                for r in image.regions:
                    if r.data:
                        db.execute("INSERT INTO regions VALUES (?,?,?,?,?,?)",(1,r.name,key(r.start),r.data,r.executable,r.writable))
                for seed in image.seeds:
                    address = key(seed.address)
                    db.execute("INSERT OR IGNORE INTO functions(version,context,address,name,source) VALUES (1,?,?,?,?)",
                        (context,address,seed.name,seed.source))
                    if seed.address == image.entry:
                        db.execute("INSERT OR IGNORE INTO work(version,context,address,reason) VALUES (1,?,?,?)",
                            (context,address,seed.source))
                db.commit()
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                db.close()
            project = cls(target)
            try:
                with project.transaction(True):
                    project._init_information(image)
                return project
            except BaseException:
                project.db.close()
                raise
        except BaseException:
            target.unlink(missing_ok=True)
            Path(str(target)+"-wal").unlink(missing_ok=True)
            Path(str(target)+"-shm").unlink(missing_ok=True)
            raise

    @staticmethod
    def digest(regions):
        h = hashlib.sha256()
        for r in sorted(regions, key=lambda r:r.start):
            h.update(json.dumps([r.name,r.start,len(r.data),bool(r.executable),bool(r.writable)],separators=(",",":")).encode())
            h.update(r.data)
        return h.hexdigest()

    def version(self, value=None):
        result = self.db.execute("SELECT * FROM versions WHERE id=?",(integer(value,"version",1,(1<<63)-1),)).fetchone() if value is not None else self.db.execute("SELECT * FROM versions ORDER BY id DESC LIMIT 1").fetchone()
        if result is None:
            raise ValueError("unknown code version")
        return dict(result)

    def regions(self, version):
        return [Region(r["name"],int(r["start"],16),bytes(r["data"]),bool(r["executable"]),bool(r["writable"]))
                for r in self.db.execute("SELECT * FROM regions WHERE version=? ORDER BY start",(version,))]

    def managed(self,token=None,version=None,max_instructions=10000):
        from .managed import inspect_managed,disassemble_managed
        with self.transaction():
            v=self.version(version)['id']
            row=self.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(v,)).fetchone()
            if row is None or row[0] is None:
                raise ValueError('original assembly bytes unavailable; use managed with the assembly path')
            data=bytes(row[0])
            result=inspect_managed(data) if token is None else disassemble_managed(data,token,max_instructions=max_instructions)
            return {'version':v,**result}

    def status(self, version=None):
        with self.transaction():
            v = self.version(version)
            counts = {table:self.db.execute(f"SELECT count(*) FROM {table} WHERE version=?",(v["id"],)).fetchone()[0]
                      for table in ("instructions","functions","xrefs","annotations")}
            work = dict(self.db.execute("SELECT state,count(*) FROM work WHERE version=? GROUP BY state",(v["id"],)))
            regions = [{"name":r.name,"start":hx(r.start),"size":len(r.data),"executable":r.executable,"writable":r.writable} for r in self.regions(v["id"])]
            metadata=dict(self.meta)
            if self.meta['format']=='MZ':
                loader=dict(metadata['loader_metadata'])
                dos=dict(loader['dos'])
                dos['relocation_count']=len(dos.pop('relocations',[]))
                dos['segment_candidate_count']=len(dos.pop('segment_candidates',[]))
                loader['dos']=dos
                metadata['loader_metadata']=loader
            return {"project":str(self.path),**metadata,"entry":hx(self.meta["entry"]),"context":self.context,
                    "version":v,"counts":counts,"work":work,"regions":regions,"analysis":self.analysis_status(v['id'])}

    def _stored_analysis_status(self,version=None):
        """Current persisted queue state, independent of historical run receipts."""
        with self.transaction():
            v=self.version(version)['id']
            phase=self.db.execute('SELECT entry_complete,seeds_admitted FROM analysis_state WHERE version=?',(v,)).fetchone()
            pending_code=self.db.execute("SELECT count(*) FROM work WHERE version=? AND state='pending'",(v,)).fetchone()[0]
            pending_data=self.db.execute("SELECT count(*) FROM investigations WHERE version=? AND state='pending'",(v,)).fetchone()[0]
            seed_states={}
            pending_scans=0
            if self.meta['format']=='MZ':
                seed_states=dict(self.db.execute('SELECT state,count(*) FROM dos_seeds WHERE version=? GROUP BY state',(v,)))
                scanned={r[0] for r in self.db.execute('SELECT selector FROM dos_data_scans WHERE version=?',(v,))}
                pending_scans=sum('data' in json.loads(r[1]) and r[0] not in scanned for r in self.db.execute('SELECT selector,roles FROM dos_segments WHERE version=?',(v,)))
            pending_seeds=seed_states.get('deferred',0)
            pending_phase=not phase or not bool(phase[1])
            pending=pending_code+pending_data+pending_seeds+pending_scans+int(pending_phase)
            issues=self.db.execute("SELECT count(*) FROM work WHERE version=? AND (detail IS NOT NULL OR state!='decoded')",(v,)).fetchone()[0]
            clr=self.meta['loader_metadata'].get('managed',{})
            if self.meta['format']=='PE':
                from .managed import managed_kind
                source=self.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(v,)).fetchone()
                if source and source[0] is not None:
                    clr=managed_kind(bytes(source[0]))
            managed=clr.get('recognized') and (clr.get('il_only') or clr.get('status')=='invalid_managed')
            advanced=self.advanced_status(v)
            enabled=self.db.execute('SELECT 1 FROM metadata WHERE key=?',(f'advanced_enabled_{v}',)).fetchone() is not None
            base_stable=None if managed else not pending and bool(phase and phase[0])
            return dict(version=v,stable=base_stable,scope='native code/data discovery queues',advanced=advanced,overall_stable=bool(base_stable and advanced['stable']) if enabled else None,
                        pending=pending,pending_code=pending_code,pending_data=pending_data,
                        pending_seeds=pending_seeds,pending_segment_scans=pending_scans,
                        pending_seed_phase=pending_phase,seed_states=seed_states,issues=issues,
                        mode='managed-on-demand' if managed else 'static',
                        note='Current stored state. A static fixed point does not establish complete code coverage or runtime behavior.')

    def _address(self,value):
        return self._dos_parse_address(value)[0] if self.meta['format']=='MZ' else number(value)

    def segments(self,version=None):
        if self.meta['format']!='MZ':
            raise ValueError('DOS segment inventory requires an MZ project; use sections for other formats')
        return self._dos_segments(version)

    def code_regions(self,version=None):
        if self.meta['format']!='MZ':
            raise ValueError('DOS code-region inventory requires an MZ project')
        return self._dos_regions(version)

    def versions(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM versions ORDER BY id")]

    def functions(self, version=None, limit=200, offset=0):
        if self.meta["format"]=="MZ":
            return self._dos_functions(version,limit,offset)
        v = self.version(version)["id"]
        limit = integer(limit,"limit",1,10000)
        offset = integer(offset,"offset",0,(1<<63)-1)
        rows = self.db.execute("SELECT f.*,a.text AS rename FROM functions f LEFT JOIN annotations a ON a.version=f.version AND a.context=f.context AND a.address=f.address AND a.kind='name' WHERE f.version=? ORDER BY f.address LIMIT ? OFFSET ?",(v,limit,offset))
        return [{"address":hx(int(r["address"],16)),"name":self._label(v,int(r["address"],16)),"source":r["source"],"status":r["status"],"version":v} for r in rows]

    def annotate(self, address, text, kind="comment", author="agent", version=None):
        if kind not in ("name","comment"):
            raise ValueError("annotation kind must be name or comment")
        if not isinstance(text,str) or not text.strip() or len(text)>4096:
            raise ValueError("annotation text must contain 1..4096 characters")
        if kind == "name" and (len(text)>256 or any(ord(c)<32 for c in text)):
            raise ValueError("name must be at most 256 characters with no controls")
        if not isinstance(author,str) or not author or len(author)>256:
            raise ValueError("author must contain 1..256 characters")
        a = self._address(address)
        with self.transaction(True):
            v = self.version(version)["id"]
            if not any(r.start <= a < r.start+len(r.data) for r in self.regions(v)):
                raise ValueError("annotation address is outside image")
            self.db.execute("INSERT INTO annotations VALUES (?,?,?,?,?,?,?,NULL) ON CONFLICT(version,context,address,kind) DO UPDATE SET text=excluded.text,author=excluded.author,created=excluded.created,inherited_from=NULL",
                (v,self.context,key(a),kind,text,author,now()))
            if kind == "name":
                self._rename_linked_native(v,a,text,author)
            return {"version":v,"address":hx(a),"kind":kind,"text":text,"author":author}

    def _stored_xrefs(self, address, direction="to", version=None, limit=200,cs=None):
        if self.meta["format"]=="MZ":
            return self._dos_xrefs(address,direction,version,limit,cs)
        if direction not in ("to","from"):
            raise ValueError("direction must be to or from")
        limit = integer(limit,"limit",1,10000)
        v = self.version(version)["id"]
        column = "target" if direction == "to" else "source"
        rows = self.db.execute(f"SELECT * FROM xrefs WHERE version=? AND context=? AND {column}=? ORDER BY source,target,kind LIMIT ?",(v,self.context,key(address),limit))
        return [{"source":hx(int(r["source"],16)),"target":hx(int(r["target"],16)),"kind":r["kind"],"evidence":r["evidence"],"version":v,"source_name":self._label(v,int(r["source"],16)),"target_name":self._label(v,int(r["target"],16)),"target_representation":self._presentation(v,int(r["target"],16))["representation"]} for r in rows]

    def _stored_disassembly(self, address=None, lines=50, version=None,cs=None):
        if self.meta["format"]=="MZ":
            return self._dos_disassembly(address,lines,version,cs)
        count = integer(lines,"lines",1,500)
        with self.transaction():
            v = self.version(version)
            a = self.meta["entry"] if address is None else number(address)
            rows = self.db.execute("SELECT i.*,n.text AS name,c.text AS comment,c.author AS comment_author,c.inherited_from AS comment_inherited_from FROM instructions i LEFT JOIN annotations n ON n.version=i.version AND n.context=i.context AND n.address=i.address AND n.kind='name' LEFT JOIN annotations c ON c.version=i.version AND c.context=i.context AND c.address=i.address AND c.kind='comment' WHERE i.version=? AND i.context=? AND i.address>=? ORDER BY i.address LIMIT ?",(v["id"],self.context,key(a),count)).fetchall()
            result = []
            for r in rows:
                fn = self.db.execute("SELECT name FROM functions WHERE version=? AND context=? AND address=?",(v["id"],self.context,r["address"])).fetchone()
                address_hex = hx(int(r["address"],16))
                references=[]
                for ref in self.db.execute('SELECT * FROM operand_refs WHERE version=? AND context=? AND source=? ORDER BY operand_index,role',(v['id'],self.context,r['address'])):
                    target=int(ref['target'],16)
                    references.append(dict(operand_index=ref['operand_index'],role=ref['role'],target=hx(target),width=ref['width'],**self._presentation(v['id'],target)))
                display=r['operands']
                if references:
                    display += ' ; ' + ', '.join(ref['name'] + (f" <{ref['representation']}>" if ref['representation'] else '') for ref in references)
                display,file_refs,file_refs_summary=self._file_reference_display(v['id'],self.context,int(r['address'],16),display)
                result.append({"references":references,"file_references":file_refs,"file_reference_summary":file_refs_summary,"display_operands":display,"address":address_hex,"size":r["size"],"bytes":r["bytes"],"mnemonic":r["mnemonic"],"operands":r["operands"],"flow":r["flow"],"target":hx(int(r["target"],16)) if r["target"] else None,"name":self._shared_name(v["id"],("memory","",int(r["address"],16))) or r["name"] or (fn[0] if fn else None),"comment":r["comment"],"comment_author":r["comment_author"],"comment_inherited_from":r["comment_inherited_from"],"xrefs":self.xrefs(address_hex,"to",v["id"]),"context":self.context})
            return {"title":self.meta["filename"],"arch":self.arch,"bits":self.bits,"context":self.context,"version":v["id"],"sha256":v["sha256"],"source_sha256":self.meta["source_sha256"],"address":hx(a),"instructions":result,"analysis":self.analysis_status(v['id']),"view":"stored instructions ordered by address; gaps are not decoded implicitly"}

    def patch(self, address, data, label="patch", origin="agent supplied bytes", version=None):
        a = self._address(address)
        if not isinstance(data,str):
            raise ValueError("patch bytes must be a hexadecimal string")
        try:
            replacement = bytes.fromhex(data)
        except ValueError as e:
            raise ValueError("invalid patch hex") from e
        if not 1 <= len(replacement) <= 1024*1024:
            raise ValueError("patch must contain 1 byte..1 MiB")
        if not isinstance(label,str) or not label.strip() or len(label)>256:
            raise ValueError("label must contain 1..256 characters")
        if not isinstance(origin,str) or not origin.strip() or len(origin)>1024:
            raise ValueError("origin must contain 1..1024 characters")
        with self.transaction(True):
            parent = self.version(version)["id"]
            regions = self.regions(parent)
            match = next((r for r in regions if r.start <= a and a+len(replacement) <= r.start+len(r.data)),None)
            if match is None:
                raise ValueError("patch must fit entirely inside one mapped region")
            patched = [Region(r.name,r.start,r.data[:a-r.start]+replacement+r.data[a-r.start+len(replacement):] if r is match else r.data,r.executable,r.writable) for r in regions]
            cur = self.db.execute("INSERT INTO versions(parent,label,origin,sha256,created) VALUES (?,?,?,?,?)",(parent,label,origin,self.digest(patched),now()))
            v = cur.lastrowid
            for r in patched:
                self.db.execute("INSERT INTO regions VALUES (?,?,?,?,?,?)",(v,r.name,key(r.start),r.data,r.executable,r.writable))
            self.db.execute("INSERT INTO annotations SELECT ?,context,address,kind,text,author,created,? FROM annotations WHERE version=?",(v,parent,parent))
            self.db.execute("INSERT INTO functions SELECT ?,context,address,name,source,status FROM functions WHERE version=? AND source!='direct call'",(v,parent))
            self.db.execute("INSERT INTO definitions SELECT ?,context,address,representation,size,author FROM definitions WHERE version=?",(v,parent))
            info=self.db.execute('SELECT document,source_bytes FROM binary_info WHERE version=?',(parent,)).fetchone()
            if info and self.meta["format"]=="MZ":
                self._dos_patch_document(parent,v,bytes(info[1]),patched)
            elif info:
                document=json.loads(info[0])
                source_bytes=bytes(info[1]) if info[1] is not None else None
                file_offset=None
                if source_bytes is not None:
                    for section in document.get('file_mappings',document.get('sections',[])):
                        va,fs=section.get('virtual_address'),section.get('file_size',0)
                        if va is not None and va <= a and a+len(replacement) <= va+fs:
                            file_offset=section['file_offset']+a-va
                            break
                    if file_offset is not None:
                        source_bytes=source_bytes[:file_offset]+replacement+source_bytes[file_offset+len(replacement):]
                        from .inspection import inspect_binary
                        refreshed=inspect_binary(source_bytes,slice_arch=self.meta['loader_metadata'].get('slice_arch'),image=self.meta['loader_metadata'].get('selected_image'))
                        refreshed['file_mappings']=document.get('file_mappings',[])
                        if refreshed.get('sections') != document.get('sections') or refreshed.get('header') != document.get('header'):
                            refreshed.setdefault('warnings',[]).append('Header/layout changed; stored memory mapping remains the parent mapping. Reimport patched file for a new layout.')
                        if self.meta['format']=='raw':
                            refreshed['sections']=document['sections']
                            refreshed['imports'],refreshed['exports']=[],[]
                            for string in refreshed['strings']:
                                string['address']=regions[0].start+string['file_offset']
                        document=refreshed
                    else:
                        document.setdefault('warnings',[]).append('Mapped-memory patch has no known disk counterpart; file metadata remains inherited from parent.')
                self.db.execute('INSERT INTO binary_info VALUES (?,?,?)',(v,json.dumps(document),source_bytes))
                self._index_symbols(v,document)
            self._copy_interpretations(parent,v)
            self._reset_analysis(v)
            return {"version":v,"parent":parent,"address":hx(a),"bytes":replacement.hex(),"sha256":self.version(v)["sha256"],"annotations":"inherited; semantic validity requires review","analysis":"fresh work queue; previous analysis preserved in parent"}

    def issues(self, version=None, limit=200):
        v = self.version(version)["id"]
        limit = integer(limit,"limit",1,10000)
        return [{"address":hx(int(r["address"],16)),"state":r["state"],"reason":r["reason"],"detail":r["detail"],"context":r["context"]} for r in self.db.execute("SELECT * FROM work WHERE version=? AND (detail IS NOT NULL OR state!='decoded') ORDER BY rowid LIMIT ?",(v,limit))]
