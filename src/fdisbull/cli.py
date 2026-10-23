"""One-shot JSON CLI and line-oriented agent protocol over stdin/stdout."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .project import Project, number
from . import __version__

METHODS = {
    "import": "Create a new project from binary; params: project, path, [arch,bits,base,entry]",
    "status": "Image mappings, hashes, counts and remaining work; [version]",
    "analyze": "Follow pending direct control flow; [version,start,max_instructions]",
    "functions": "Candidate function entries; [version,limit,offset]",
    "disasm": "Stored decoded rows; [version,address,lines]",
    "xrefs": "Direct control/data references; address, [version,direction,limit]",
    "rename": "Persistent address label; address,name,[version,author]",
    "comment": "Persistent evidence note; address,text,[version,author]",
    "versions": "Immutable mapped-byte snapshots and provenance",
    "patch": "Create a new snapshot, preserve parent; address,data,[version,label,origin]",
    "issues": "Pending/rejected/unresolved work; [version,limit]",
    "render": "Export stored rows as SVG/PNG; output,[version,address,lines,format]",
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

def respond(request, default_project=None):
    request_id = request.get("id") if isinstance(request,dict) else None
    try:
        if not isinstance(request,dict) or not isinstance(request.get("method"),str):
            raise ValueError("request must be an object with method and optional params/id")
        params = request.get("params",{})
        if default_project is not None and isinstance(params,dict):
            params = {"project":default_project,**params}
        return {"id":request_id,"ok":True,"result":invoke(request["method"],params)}
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
    c = sub.add_parser("import",help="create project from executable or explicit raw code")
    c.add_argument("path")
    c.add_argument("project")
    c.add_argument("--arch",choices=["x86","arm64"],help="explicit raw mode (bypasses executable loader)")
    c.add_argument("--bits",type=int,choices=[16,32,64])
    c.add_argument("--base",default=0,type=lambda s:int(s,0))
    c.add_argument("--entry",type=lambda s:int(s,0))
    for name in ["status","analyze","functions","disasm","xrefs","rename","comment","versions","patch","issues","render"]:
        c = sub.add_parser(name,help=METHODS[name])
        c.add_argument("project")
        if name != "versions":
            c.add_argument("--version",type=int)
        if name in ("xrefs","rename","comment","patch"):
            c.add_argument("address")
        if name == "analyze":
            c.add_argument("--start")
            c.add_argument("--max-instructions",type=int,default=10000)
        if name in ("functions","xrefs","issues"):
            c.add_argument("--limit",type=int,default=200)
        if name == "functions":
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
        if name in ("rename","comment"):
            c.add_argument("--author",default="agent")
        if name == "patch":
            c.add_argument("data",help="replacement hex bytes; creates child version")
            c.add_argument("--label",default="patch")
            c.add_argument("--origin",default="agent supplied bytes")
        if name == "render":
            c.add_argument("output")
            c.add_argument("--format",choices=["svg","png"])
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
