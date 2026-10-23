"""One-shot JSON CLI and line-oriented agent protocol over stdin/stdout."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .project import Project, number
from . import __version__

METHODS = {
    'link-labels': 'Link corresponding native/file byte ranges; left,right,evidence,[size,name,version,author]',
    'rename-file': 'Rename a file field and every linked identity; file,offset,name,[version,author]',
    'label-info': 'Resolve a shared field label and its evidence chain; endpoint,[version]',
    'attach-file': 'Snapshot an external data/save/resource file; path,[name,kind,version,author]',
    'files': 'Attached file identities, hashes and type bindings; [version,limit,offset]',
    'file-bytes': 'Read bounded attached-file hex and text; name,[offset,size,version]',
    'apply-file-type': 'Bind a structural type in file-offset space; file,type_name,[offset,name,version,author]',
    'file-data': 'Read an exact typed attached-file binding; file,[offset,version,max_items]',
    'file-reference': 'Author an instruction-to-file relationship; address,file,evidence,[offset,width,count,stride,access,cs,version,author]',
    'file-xrefs': 'Query authored references to attached-file bytes; file,[offset,size,version,limit,page_offset,include_stale]',
    'refresh-dos-state': 'Rebuild legacy DOS states and dependent facts; [version,max_instructions]',
    'auto-analyze': 'Run persistent native and derived analysis to a bounded fixed point; [version,start,cs,ds,es,ss,max_instructions,max_functions,max_steps,max_entries,max_rounds,abi]',
    'advanced-status': 'Derived job states, pending entries and fixed point; [version]',
    'function-analysis': 'Stored frame, indirect-target, signature and effect evidence; address,[version,cs]',
    'function-membership': 'Shared instruction/block membership from candidate entries; [version,max_work,max_instructions]',
    'define-type': 'Register or revise a scalar/pointer/array/struct; name,definition,[version,author]',
    'apply-type': 'Bind a type to shared data identity; address,type_name,[name,version,author]',
    'types': 'Registered layouts and data bindings; [version]',
    'typed-data': 'Interpret a bound data object; address,[version,max_items]',
    'set-summary': 'Register a qualified function contract; address,name,[prototype,summary,abi,version,cs,author]',
    'summaries': 'Registered and signature-qualified function contracts; [version]',
    'add-signature': 'Register an exact or relocation-masked full-body signature; signature,[version]',
    'signatures': 'Builtin and registered function signatures; [version]',
    'call-effects': 'Qualified memory effects at call sites; [address,size,access,version,include_unresolved,limit,offset]',
    "libraries": "Declared dependency names and load ordinals; [version,limit,offset]",
    "relocations": "Static relocation records with symbol/addend provenance; [version,limit,offset]",
    "linkage": "GOT/PLT or dyld slot/stub metadata; [version]",
    "refresh-metadata": "Reinspect retained ELF/Mach-O/PE bytes and invalidate consumers; [version]",
    "analyze-module": "Offline DLL/shared-library analysis; path,project,[export,entry,max_instructions,slice_arch,image]",
    "analysis-status": "Current persisted queues, seed states and fixed-point status; [version]",
    "cfg": "Reachable stored CFG from exact entry; address,[version,cs,max_instructions,highlights]",
    "render-cfg": "Export reachable basic-block CFG as SVG; address,output,[version,cs,max_instructions,highlights]",
    "memory-accesses": "Read/write/overlap and unresolved memory evidence; address,[size,version,access,limit,offset,include_unresolved]",
    "refresh-facts": "Backfill persisted fallthrough and memory-access facts from stored instructions; [version]",
    "calls": "Grouped native function/library calls with incoming xrefs; [version,limit,offset,kind]",
    "locate": "Byte position in stored instructions/data and unexplored memory; address,[version,cs]",
    "function-patterns": "Candidate prologue/epilogue evidence; [version,limit,offset,scan_unexplored]",
    "managed": "Inspect .NET metadata or disassemble one CIL method; path or project,[token,max_instructions,version]",
    "decoder-check": "Compare x86 iced/Capstone proposals without execution; data,[bits,address,scan_offsets,max_candidates]",
    "import": "Create a new project from binary; params: project, path, [arch,bits,base,entry,load_segment,slice_arch,image]",
    "segments": "DOS inferred segment inventory; [version]",
    "code-regions": "DOS decoded instruction runs by CS; [version]",
    "identify": "Identify file header from bytes; path; no project required",
    "inspect": "Parse file metadata; path; no project required",
    "info": "Parsed container summary; [version]",
    "header": "Parsed header fields; [version]",
    "sections": "Disk and virtual section layout; [version,limit,offset]",
    "imports": "Static imports and persisted IAT recovery; [version,limit,offset]",
    "exports": "Export addresses, ordinals and forwarders; [version,limit,offset]",
    "strings": "File-backed ASCII/UTF16 strings; [version,limit,offset]",
    "items": "Investigated memory locations; [version,limit,offset]",
    "queue": "Code/data investigation work; [version,limit,offset]",
    "represent": "Shared data/code/unexplored definition; address,representation,[size,author,version,max_instructions,defer]",
    "recover-imports": "Offline CHimpREC-derived recovery; module_exports or export_map,[candidate_slots,version,max_slots,gap_limit]",
    "status": "Image mappings, hashes, counts and remaining work; [version]",
    "analyze": "Recursive code/data analysis; [version,start,max_instructions,cs,ds,es,ss]",
    "functions": "Candidate function entries; [version,limit,offset]",
    "disasm": "Stored decoded rows; [version,address,lines,cs]",
    "xrefs": "Direct control/data references; address, [version,direction,limit,cs]",
    "rename": "Persistent address label; address,name,[version,author]",
    "comment": "Persistent evidence note; address,text,[version,author]",
    "versions": "Immutable mapped-byte snapshots and provenance",
    "patch": "Create a new snapshot, preserve parent; address,data,[version,label,origin]",
    "issues": "Pending/rejected/unresolved work; [version,limit]",
    "render": "Export stored rows as SVG/PNG; output,[version,address,lines,format,cs]",
    "help": "List methods; all project operations require project path",
}

def invoke(method, params):
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    if not isinstance(params,dict):
        raise ValueError("params must be an object")
    p = dict(params)
    for field in ("base", "entry"):
        if field in p and p[field] is not None:
            p[field] = number(p[field])
    if method == "help":
        return {"application":"fDisBull","version":__version__,"protocol":"JSON lines, one response per request; not MCP/JSON-RPC","methods":METHODS}
    if method=='analyze-module':
        from .modules import analyze_module
        return analyze_module(**p)
    if method=='decoder-check':
        from .decoder_check import compare_decoders
        data=p.pop('data')
        if not isinstance(data,str):
            raise ValueError('data must be hexadecimal bytes')
        return compare_decoders(bytes.fromhex(data),**p)
    if method=='managed' and 'path' in p:
        from .managed import inspect_managed,disassemble_managed
        path=Path(p.pop('path'))
        if not path.is_file() or not 0<path.stat().st_size<=64*1024*1024:
            raise ValueError('expected one nonempty input file at most 64 MiB')
        with path.open('rb') as stream:
            data=stream.read(64*1024*1024+1)
        token=p.pop('token',None)
        if token is not None:
            return disassemble_managed(data,token,**p)
        if p:
            raise ValueError('unexpected managed inspection options')
        return inspect_managed(data)
    if method in ('identify','inspect'):
        from .inspection import identify_header, inspect_binary
        path=Path(p.pop('path'))
        slice_arch=p.pop('slice_arch',None)
        image=p.pop('image',None)
        if p or (method=='identify' and (slice_arch is not None or image is not None)) or not path.is_file() or path.stat().st_size>64*1024*1024:
            raise ValueError('expected one regular input file at most 64 MiB')
        with path.open('rb') as stream:
            data=stream.read(64*1024*1024+1)
        return identify_header(data) if method=='identify' else inspect_binary(data,slice_arch=slice_arch,image=image)
    project = p.pop("project",None)
    if not project:
        raise ValueError("project path is required")
    if method == "import":
        binary = p.pop("path",None)
        if binary is None:
            raise ValueError("path is required for import")
        with Project.create(project,binary,**p) as db:
            return db.status()
    with Project(project) as db:
        if method in ('link-labels','rename-file','label-info'):return getattr(db,method.replace('-','_'))(**p)
        if method=='refresh-dos-state':return db.refresh_dos_state(**p)
        file_methods={'attach-file':'attach_file','files':'external_files','file-bytes':'file_bytes','apply-file-type':'apply_file_type','file-data':'typed_file','file-reference':'file_reference','file-xrefs':'file_xrefs'}
        if method in file_methods:return getattr(db,file_methods[method])(**p)
        if method in ('define-type','add-signature','set-summary'):
            for field in ('definition','signature','prototype','summary'):
                filename=p.pop(field+'_file',None)
                if filename is not None:
                    path=Path(filename)
                    if not path.is_file() or path.stat().st_size>1024*1024:raise ValueError('expected a JSON file at most 1 MiB')
                    p[field]=json.loads(path.read_text())
        if method in ('auto-analyze', 'advanced-status', 'function-analysis', 'function-membership', 'define-type', 'apply-type', 'types', 'typed-data', 'set-summary', 'summaries', 'add-signature', 'signatures', 'call-effects'):
            return getattr(db,method.replace('-','_'))(**p)
        if method=="memory-accesses":
            return db.memory_accesses(**p)
        if method=="refresh-facts":
            return db.refresh_facts(**p)
        if method=="render-cfg":
            from .cfg_render import render_cfg
            destination=Path(p.pop("output")).expanduser().resolve()
            protected=[db.path,Path(str(db.path)+"-wal"),Path(str(db.path)+"-shm")]
            if any(destination==item or (destination.exists() and item.exists() and destination.samefile(item)) for item in protected):
                raise ValueError("render output cannot overwrite a project database or SQLite sidecar")
            return render_cfg(db.cfg(**p),destination)
        if method=="code-regions":
            return db.code_regions(**p)
        if method=="function-patterns":
            return db.function_patterns(**p)
        if method=='analysis-status':
            return db.analysis_status(**p)
        if method=='refresh-metadata':return db.refresh_metadata(**p)
        if method in ('info','header','sections','imports','exports','strings','libraries','relocations','linkage'):
            return db.information(topic='summary' if method=='info' else method,**p)
        if method=='recover-imports':
            return db.recover_imports(**p)
        if method == "rename":
            p["text"] = p.pop("name")
            return db.annotate(kind="name",**p)
        if method == "comment":
            return db.annotate(kind="comment",**p)
        if method == "disasm":
            return db.disassembly(**p)
        if method == "render":
            from .render import render_snapshot
            output = p.pop("output")
            fmt = p.pop("format",None)
            if fmt is not None and (not isinstance(fmt,str) or fmt not in ("svg","png")):
                raise ValueError("format must be svg or png")
            destination = Path(output).expanduser().resolve()
            protected = [db.path,Path(str(db.path)+"-wal"),Path(str(db.path)+"-shm")]
            if any(destination == item or (destination.exists() and item.exists() and destination.samefile(item)) for item in protected):
                raise ValueError("render output cannot overwrite a project database or SQLite sidecar")
            snapshot = db.disassembly(**p)
            if not snapshot["instructions"]:
                raise ValueError("no stored instructions at this address; run analyze first")
            return render_snapshot(snapshot,destination,fmt)
        return getattr(db,method)(**p)

def public_addresses(value, field=None):
    address_fields={'address','virtual_address','entrypoint','imagebase','target','start','end','source','concrete_target','interval_start','interval_end','possible_start','possible_end','slot','stub','slot_address','stub_address','storage_address','resolver_address','source_address','target_address','next_address'}
    if isinstance(value,dict):
        return {key:public_addresses(item,key) for key,item in value.items()}
    if isinstance(value,list):
        return [public_addresses(item,'address' if field in ('addresses','stub_addresses') else None) for item in value]
    if field in address_fields and isinstance(value,int) and not isinstance(value,bool):
        return hex(value)
    return value


def respond(request, default_project=None):
    request_id = request.get("id") if isinstance(request,dict) else None
    try:
        if not isinstance(request,dict) or not isinstance(request.get("method"),str):
            raise ValueError("request must be an object with method and optional params/id")
        params = request.get("params",{})
        standalone=request['method'] in ('identify','inspect','help','decoder-check') or request['method']=='managed' and isinstance(params,dict) and 'path' in params
        if default_project is not None and isinstance(params,dict) and not standalone:
            params = {"project":default_project,**params}
        return {"id":request_id,"ok":True,"result":public_addresses(invoke(request["method"],params))}
    except (ValueError,TypeError,KeyError,OSError,sqlite3.Error,OverflowError,AttributeError,RecursionError) as e:
        return {"id":request_id,"ok":False,"error":{"type":type(e).__name__,"message":str(e)}}

def load_request(value):
    def invalid_constant(value):
        raise ValueError(f"non-finite JSON number is not supported: {value}")
    return json.loads(value,parse_constant=invalid_constant)

def emit(value):
    print(json.dumps(value,ensure_ascii=True,separators=(",",":")),flush=True)

def serve(default_project=None):
    while True:
        line = sys.stdin.buffer.readline(1024*1024+1)
        if not line:
            return 0
        if len(line)>1024*1024:
            emit({"id":None,"ok":False,"error":{"type":"ValueError","message":"request exceeds 1 MiB; stream closed"}})
            return 1
        try:
            request = load_request(line)
        except (ValueError,UnicodeDecodeError,RecursionError) as e:
            emit({"id":None,"ok":False,"error":{"type":"InvalidJSON","message":str(e)}})
            continue
        emit(respond(request,default_project))

def parser():
    root = argparse.ArgumentParser(prog="fdisbull",description="Agent-first disassembly with SQLite persistence and headless image export")
    root.add_argument("--version",action="version",version=__version__)
    sub = root.add_subparsers(dest="command",required=True)
    for name in ('identify','inspect'):
        c=sub.add_parser(name,help=METHODS[name])
        c.add_argument('path')
        if name=='inspect':
            c.add_argument('--slice-arch',choices=['x86','x86_64','arm64'])
            c.add_argument('--image',choices=['auto','pe','mz'])
    c = sub.add_parser("import",help="create project from executable or explicit raw code")
    c.add_argument("path")
    c.add_argument("project")
    c.add_argument("--arch",choices=["x86","arm64"],help="explicit raw mode (bypasses executable loader)")
    c.add_argument("--bits",type=int,choices=[16,32,64])
    c.add_argument("--base",default=0,type=lambda s:int(s,0))
    c.add_argument("--entry",type=lambda s:int(s,0))
    c.add_argument("--load-segment",type=lambda s:int(s,0),default=0x1000)
    c.add_argument('--image',choices=['auto','pe','mz'],help='select a PE native image or its DOS MZ image')
    c.add_argument('--slice-arch',choices=['x86','x86_64','arm64'],help='select a thin/universal Mach-O CPU slice')
    c.add_argument('--module',action='store_true',help='allow a library without an executable entry')
    c=sub.add_parser('analyze-module',help=METHODS['analyze-module'])
    c.add_argument('path');c.add_argument('project')
    c.add_argument('--image',choices=['auto','pe','mz'])
    c.add_argument('--slice-arch',choices=['x86','x86_64','arm64'])
    c.add_argument('--export');c.add_argument('--entry',type=lambda s:int(s,0))
    c.add_argument('--max-instructions',type=int,default=10000)
    c=sub.add_parser('managed',help=METHODS['managed'])
    c.add_argument('path');c.add_argument('--token',type=lambda s:int(s,0))
    c.add_argument('--max-instructions',type=int)
    c=sub.add_parser('decoder-check',help=METHODS['decoder-check'])
    c.add_argument('data');c.add_argument('--bits',type=int,choices=[16,32,64],default=64)
    c.add_argument('--address',type=lambda s:int(s,0),default=0)
    c.add_argument('--scan-offsets',action='store_true');c.add_argument('--max-candidates',type=int,default=16)
    for name in ["status","analyze","functions","disasm","xrefs","rename","comment","versions","patch","issues","render","info","header","sections","imports","exports","strings","items","queue","represent","recover-imports","segments","code-regions","locate","function-patterns","analysis-status","calls","cfg","render-cfg","memory-accesses","refresh-facts","libraries","relocations","linkage","refresh-metadata","refresh-dos-state"]:
        c = sub.add_parser(name,help=METHODS[name])
        c.add_argument("project")
        if name != "versions":
            c.add_argument("--version",type=int)
        if name in ("xrefs","rename","comment","patch","represent","locate","cfg","render-cfg","memory-accesses"):
            c.add_argument("address")
        if name in ('analyze','disasm','xrefs','render','locate','cfg','render-cfg'):
            c.add_argument('--cs',type=lambda s:int(s,0))
        if name=='analyze':
            for register in ('ds','es','ss'):
                c.add_argument('--'+register,type=lambda s:int(s,0))
        if name in ("analyze","represent","cfg","render-cfg","refresh-dos-state"):
            if name=="analyze":
                c.add_argument("--start")
            c.add_argument("--max-instructions",type=int,default=10000)
        if name in ("functions","xrefs","issues","sections","imports","exports","strings","items","queue","function-patterns","calls","memory-accesses","libraries","relocations"):
            c.add_argument("--limit",type=int,default=200)
        if name in ("functions","sections","imports","exports","strings","items","queue","function-patterns","calls","memory-accesses","libraries","relocations"):
            c.add_argument("--offset",type=int,default=0)
        if name in ("disasm","render"):
            c.add_argument("--address")
            c.add_argument("--lines",type=int,default=40)
        if name == "xrefs":
            c.add_argument("--direction",choices=["to","from"],default="to")
        if name == "rename":
            c.add_argument("name")
        if name == "comment":
            c.add_argument("text")
        if name in ("rename","comment","represent"):
            c.add_argument("--author",default="agent")
        if name=='represent':
            c.add_argument('representation',choices=['code','byte','word','dword','qword','pointer','ascii','utf-16le','unexplored'])
            c.add_argument('--size',type=int)
            c.add_argument('--defer',action='store_true',help='change representation and leave reanalysis queued')
        if name in ('cfg','render-cfg'):
            c.add_argument('--highlight',dest='highlights',action='append')
        if name=='render-cfg':
            c.add_argument('output')
        if name=='memory-accesses':
            c.add_argument('--size',type=int,default=1)
            c.add_argument('--access',choices=['all','read','write'],default='all')
            c.add_argument('--no-unresolved',dest='include_unresolved',action='store_false')
        if name=='function-patterns':
            c.add_argument('--scan-unexplored',action='store_true')
        if name=='calls':
            c.add_argument('--kind',choices=['all','function','library','unresolved'],default='all')
        if name=='recover-imports':
            c.add_argument('export_map',help='JSON list of runtime module export addresses')
            c.add_argument('--max-slots',type=int,default=4096)
            c.add_argument('--gap-limit',type=int,default=10)
        if name == "patch":
            c.add_argument("data",help="replacement hex bytes; creates child version")
            c.add_argument("--label",default="patch")
            c.add_argument("--origin",default="agent supplied bytes")
        if name == "render":
            c.add_argument("output")
            c.add_argument("--format",choices=["svg","png"])
    for name in ('auto-analyze', 'advanced-status', 'function-analysis', 'function-membership', 'define-type', 'apply-type', 'types', 'typed-data', 'set-summary', 'summaries', 'add-signature', 'signatures', 'call-effects'):
        c=sub.add_parser(name,help=METHODS[name]);c.add_argument('project');c.add_argument('--version',type=int)
        if name in ('function-analysis','apply-type','typed-data','set-summary'):c.add_argument('address')
        if name in ('function-analysis','set-summary','auto-analyze'):c.add_argument('--cs',type=lambda s:int(s,0))
        if name=='auto-analyze':
            c.add_argument('--start');c.add_argument('--abi')
            for field,default in [('max-instructions',10000),('max-functions',200),('max-steps',100000),('max-entries',256),('max-rounds',8)]:c.add_argument('--'+field,type=int,default=default)
            for register in ('ds','es','ss'):c.add_argument('--'+register,type=lambda s:int(s,0))
        if name=='function-membership':
            c.add_argument('--max-work',type=int,default=1000000);c.add_argument('--max-instructions',type=int,default=100000)
        if name=='define-type':c.add_argument('name');c.add_argument('definition_file')
        if name=='apply-type':c.add_argument('type_name');c.add_argument('--name')
        if name=='typed-data':c.add_argument('--max-items',type=int,default=256)
        if name=='set-summary':
            c.add_argument('name');c.add_argument('--abi');c.add_argument('--prototype-file');c.add_argument('--summary-file')
        if name=='add-signature':c.add_argument('signature_file')
        if name in ('define-type','apply-type','set-summary'):c.add_argument('--author',default='agent')
        if name=='call-effects':
            c.add_argument('--address');c.add_argument('--size',type=int,default=1)
            c.add_argument('--access',choices=['all','read','write'],default='all')
            c.add_argument('--no-unresolved',dest='include_unresolved',action='store_false')
            c.add_argument('--limit',type=int,default=200);c.add_argument('--offset',type=int,default=0)
    for name in ('attach-file','files','file-bytes','apply-file-type','file-data','file-reference','file-xrefs'):
        c=sub.add_parser(name,help=METHODS[name]);c.add_argument('project');c.add_argument('--version',type=int)
        if name=='attach-file':
            c.add_argument('path');c.add_argument('--name');c.add_argument('--kind',default='data')
        elif name=='files':
            c.add_argument('--limit',type=int,default=200);c.add_argument('--offset',type=int,default=0)
        elif name=='file-bytes':
            c.add_argument('name');c.add_argument('--offset',type=lambda s:int(s,0),default=0);c.add_argument('--size',type=lambda s:int(s,0),default=64)
        else:
            if name=='file-reference':c.add_argument('address')
            c.add_argument('file')
            if name in ('file-reference','file-xrefs'):c.add_argument('offset',type=lambda s:int(s,0))
            else:c.add_argument('--offset',type=lambda s:int(s,0),default=0)
            if name=='apply-file-type':c.add_argument('type_name');c.add_argument('--name')
            if name=='file-data':c.add_argument('--max-items',type=int,default=256)
            if name=='file-reference':
                c.add_argument('--width',type=lambda s:int(s,0),default=1);c.add_argument('--count',type=int,default=1)
                c.add_argument('--stride',type=lambda s:int(s,0));c.add_argument('--access',choices=['read','write','read_write','address','unknown'],default='unknown')
                c.add_argument('--evidence',required=True);c.add_argument('--cs',type=lambda s:int(s,0))
            if name=='file-xrefs':
                c.add_argument('--size',type=lambda s:int(s,0),default=1);c.add_argument('--limit',type=int,default=200)
                c.add_argument('--page-offset',type=int,default=0);c.add_argument('--active-only',dest='include_stale',action='store_false')
        if name in ('attach-file','apply-file-type','file-reference'):c.add_argument('--author',default='agent')
    for name in ('link-labels','rename-file','label-info'):
        c=sub.add_parser(name,help=METHODS[name]);c.add_argument('project');c.add_argument('--version',type=int)
        if name=='link-labels':
            c.add_argument('left',type=json.loads);c.add_argument('right',type=json.loads)
            c.add_argument('--size',type=lambda s:int(s,0),default=1);c.add_argument('--evidence',required=True)
            c.add_argument('--name');c.add_argument('--author',default='agent')
        elif name=='rename-file':
            c.add_argument('file');c.add_argument('offset',type=lambda s:int(s,0));c.add_argument('name');c.add_argument('--author',default='agent')
        else:c.add_argument('endpoint',type=json.loads)
    c = sub.add_parser("serve",help="JSON-lines stdin/stdout protocol; no listening socket")
    c.add_argument("--project")
    c = sub.add_parser("request",help="one JSON request")
    c.add_argument("json")
    sub.add_parser("methods",help="describe JSON methods")
    return root

def main(argv=None):
    args = vars(parser().parse_args(argv))
    command = args.pop("command")
    if command == "serve":
        return serve(args["project"])
    if command == "request":
        try:
            request = load_request(args["json"])
        except (ValueError,RecursionError) as e:
            emit({"id":None,"ok":False,"error":{"type":"InvalidJSON","message":str(e)}})
            return 1
    else:
        request = {"method":"help" if command=="methods" else command,"params":{k:v for k,v in args.items() if v is not None}}
    result = respond(request)
    emit(result)
    return 0 if result["ok"] else 1
