#!/usr/bin/env python3
"""Experimental fdisbull-il-2 -> Linux C/ELF trace-provider PoC.

This is deliberately narrow. It realizes scalar continuation control and a
headless ui.print provider. It does not embed resource text, render an AGI
screen, or claim original-interpreter parity. The provider acknowledges print
completion using fDisBull's nominal AGI effect contract and emits message IDs.
"""
from __future__ import annotations
import argparse, json, re, subprocess
from pathlib import Path


def _cname(name: str) -> str:
    return "v_" + re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_")


def _expr(expr):
    if isinstance(expr, bool): return "1" if expr else "0"
    if type(expr) is int: return str(expr)
    if isinstance(expr, dict) and set(expr)=={"var"}: return "s."+_cname(expr["var"])
    if not isinstance(expr,dict): raise ValueError("unsupported expression")
    op=expr.get("op")
    if op=="eq": return f"({_expr(expr['left'])}=={_expr(expr['right'])})"
    if op=="lt": return f"({_expr(expr['left'])}<{_expr(expr['right'])})"
    if op=="not": return f"(!{_expr(expr['condition'])})"
    if op=="and": return "("+"&&".join(_expr(x) for x in expr["conditions"])+")"
    raise ValueError("unsupported expression op: "+str(op))


def emit_c(projection: dict, *, source_logic=None, source_sha256=None) -> str:
    doc=projection.get("uil",projection)
    if doc.get("format")!="fdisbull-il-2" or doc.get("role")!="uil":
        raise ValueError("expected fdisbull-il-2 UIL")
    cont=doc["continuations"]
    ids={name:i for i,name in enumerate(cont)}
    lines=["#include <stdio.h>","#include <stdlib.h>","#include <stdint.h>","#include <string.h>"]
    if source_logic is not None: lines.append(f"#define SOURCE_LOGIC {int(source_logic)}")
    if source_sha256 is not None: lines.append('#define SOURCE_SHA256 "'+source_sha256+'"')
    lines += ["typedef struct {"]
    for name,desc in doc["variables"].items():
        if desc["type"] not in ("u8","bool"): raise ValueError("only u8/bool variables are supported")
        lines.append(f"  uint8_t {_cname(name)};")
    lines += ["} State;",""]
    lines += ["static void emit_print(unsigned message){",
              '  printf("{\\\"effect\\\":\\\"ui.print\\\",\\\"message\\\":%u}\\n",message);',"}",""]
    lines += ["int main(int argc,char **argv){","  State s={0};"]
    for name,desc in doc["variables"].items():
        val=desc["initial"]
        lines.append(f"  s.{_cname(name)}={(1 if val is True else 0 if val is False else int(val))};")
    lines += ["  for(int i=1;i<argc;i++){","    char *eq=strchr(argv[i],'='); if(!eq) continue; *eq=0; unsigned long n=strtoul(eq+1,NULL,0);"]
    for j,name in enumerate(doc["variables"]):
        kw="if" if j==0 else "else if"
        lines.append(f'    {kw}(!strcmp(argv[i],"{name}")) s.{_cname(name)}=(uint8_t)n;')
    lines += ["  }",f"  int pc={ids[doc['entry']]};","  for(unsigned steps=0;steps<4096;steps++){","    switch(pc){"]
    for cid,c in cont.items():
        lines.append(f"    case {ids[cid]}: {{ /* {cid} */")
        for b in c["body"]:
            op=b["op"]
            if op=="effect":
                if b.get("action")!="ui.print" or type(b.get("args",{}).get("message")) is not int:
                    raise ValueError("PoC provider supports ui.print(message-id) only")
                args=b.get("args",{}); outputs=b.get("outputs",{})
                if set(args)!={"message","output_mode","window_timer"} or set(outputs)!={"output_mode","window_timer"}:
                    raise ValueError("ui.print ports differ from the qualified AGI effect contract")
                mode=_expr(args["output_mode"]); timer=_expr(args["window_timer"])
                lines.append(f"      uint8_t prior_mode=(uint8_t)({mode});")
                lines.append(f"      uint8_t prior_timer=(uint8_t)({timer});")
                lines.append(f"      emit_print({b['args']['message']});")
                lines.append(f"      s.{_cname(outputs['output_mode'])}=0;")
                lines.append(f"      s.{_cname(outputs['window_timer'])}=prior_mode?prior_timer:0;")
            elif op=="set": lines.append(f"      s.{_cname(b['var'])}=(uint8_t)({_expr(b['value'])});")
            elif op in ("add","subtract"):
                sign="+" if op=="add" else "-"
                lines.append(f"      s.{_cname(b['var'])}=(uint8_t)(s.{_cname(b['var'])}{sign}({_expr(b['value'])}));")
            else: raise ValueError("unsupported body op: "+op)
        t=c["transfer"]
        if t["op"]=="goto": lines.append(f"      pc={ids[t['target']]}; break;")
        elif t["op"]=="if": lines.append(f"      pc=({_expr(t['condition'])})?{ids[t['then']]}:{ids[t['else']]}; break;")
        elif t["op"]=="return": lines.append('      puts("{\\\"return\\\":true}"); return 0;')
        elif t["op"]=="stop": lines.append("      return 0;")
        else: raise ValueError("unsupported transfer: "+t["op"])
        lines.append("    }")
    lines += ["    default: return 3;","    }","  }","  return 4;","}"]
    return "\n".join(lines)+"\n"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("projection",type=Path)
    ap.add_argument("output",type=Path)
    ap.add_argument("--source-only",action="store_true")
    ap.add_argument("--static",action="store_true")
    ns=ap.parse_args()
    projection=json.loads(ns.projection.read_text())
    source=projection.get("source",{})
    c=emit_c(projection,source_logic=source.get("logic"),source_sha256=source.get("resource_sha256"))
    cpath=ns.output.with_suffix(".c");cpath.write_text(c)
    if not ns.source_only:
        cmd=["gcc","-O2","-std=c11","-Wall","-Wextra","-Werror"]
        if ns.static: cmd.append("-static")
        cmd += [str(cpath),"-o",str(ns.output)]
        subprocess.run(cmd,check=True)
    print(json.dumps({"source":str(cpath),"output":None if ns.source_only else str(ns.output),
                      "qualification":"native compact-UIL control plus nominal ui.print provider PoC; not AGI runtime parity"}))

if __name__=="__main__": main()
