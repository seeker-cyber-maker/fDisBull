"""Build-only portable scalar UDC profiles over one qualified UIL invocation.

No executable identity, game layout, browser service or implicit state commit
enters the lowerer. Byte/word arithmetic uses explicit logical-width wrapping.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
from fdisbull.interaction_il import validate_il
from fdisbull.udc_layers import validate_contract

FORMAT = "fdisbull-web-block-1"
TARGETS = ("wasm32-scalar-1", "webgpu-wgsl-scalar-1")
BOUNDS = {"bool":(0,1),"u8":(0,255),"i8":(-128,127),
          "u16":(0,65535),"i16":(-32768,32767)}


class Lowerer:
    def __init__(self, contract, program=None, *, domain=None):
        self.contract = validate_contract(contract)
        if contract["behavior"]["kind"] != "uil" or contract.get("effects"):
            raise ValueError("pure UIL contracts only")
        self.program = deepcopy(self.contract["behavior"]["program"] if program is None else program)
        self.domain = deepcopy(domain or {})
        validate_il(self.program)
        if self.program["resources"]:
            raise ValueError("resources need explicit host adapters")
        self.variables = self.program["variables"]
        if any(v["type"] not in BOUNDS for v in self.variables.values()):
            raise ValueError("byte/word logical types only in this profile")
        self.inputs, self.outputs = sorted(contract["inputs"]), sorted(contract["outputs"])
        if not self.inputs or not self.outputs:
            raise ValueError("input/output ports required")
        if max(len(self.inputs), len(self.outputs)) > 64 or len(self.variables) > 256:
            raise ValueError("scalar profile port/variable limit exceeded")
        for side in ("inputs","outputs"):
            if contract["behavior"].get(side, {k:"$"+k for k in contract[side]}) != {k:"$"+k for k in contract[side]}:
                raise ValueError("canonical port maps only")
        self.names = {k:"v"+str(i) for i,k in enumerate(sorted(self.variables))}
        self.audit(self.program["body"])

    @classmethod
    def from_selection(cls, project, ident):
        from fdisbull.udc_layers import _validate_layer, digest
        from fdisbull.udc_qualify import qualify_uil
        selected=project.udl_selection_info(ident,full=True)
        doc=selected["document"]
        if doc.get("target") not in TARGETS:
            raise ValueError("unsupported selected target")
        if len(doc["bindings"])!=1:raise ValueError("one selected binding required")
        binding,layer_id=next(iter(doc["bindings"].items()))
        layer=project.udl_layer_info(layer_id,full=True)["document"]
        contract=_validate_layer(project,layer)
        if layer.get("adapter"):
            raise ValueError("additional adapters need an explicit realization")
        impl=layer["implementation"]
        if impl["backend"]!="uil" or impl.get("notification_binding") or impl.get("return") is not None:
            raise ValueError("language-neutral pure UIL layer required")
        for side in ("inputs","outputs"):
            if impl.get(side,{k:"$"+k for k in contract[side]})!={k:"$"+k for k in contract[side]}:
                raise ValueError("canonical implementation ports required")
        module=doc.get("program")
        if not isinstance(module,dict):
            raise ValueError("one canonical module UIL program required")
        from fdisbull.udc_blueprint import validate_module_uil
        validate_module_uil(project, module)
        call={"id":module["body"][0]["id"] if module["body"] else "",
            "op":"invoke","binding":binding,"contract":layer["contract"],
            "inputs":{k:{"var":"$"+k} for k in contract["inputs"]},
            "outputs":{k:"$"+k for k in contract["outputs"]}}
        if module["body"]!=[call] or module["resources"]:
            raise ValueError("one canonical invocation required")
        proof=qualify_uil(contract,impl)
        if proof["status"]!="equivalent_under_contract":raise ValueError("selected model not qualified")
        result=cls(contract,impl["program"],domain=layer.get("domain"))
        result.capsule={"selection":selected["id"],"selection_sha256":selected["sha256"],
            "target":doc["target"],"layer":layer_id,"contract":layer["contract"],
            "layer_sha256":project.udl_layer_info(layer_id)["sha256"],
            "contract_sha256":digest(contract),
            "module_uil_sha256":digest(module),"program_sha256":digest(impl["program"]),
            "qualification":proof,"scope":"model-to-model only; emitted execution checked separately"}
        return result

    def literal(self, value):
        if type(value) not in (int,bool) or not -(1<<31) <= int(value) < 1<<31:
            raise ValueError("literal outside i32 profile")
        return int(value)

    def audit(self, body):
        def operand(v):
            if not isinstance(v, dict): self.literal(v)
        def condition(c):
            if c["op"]=="eq": operand(c["left"]);operand(c["right"])
            elif c["op"]=="bit_test":
                if c["bit"]>=32: raise ValueError("bit tests above 31 need a wider realization")
                operand(c["value"])
            elif c["op"]=="not":condition(c["condition"])
            elif c["op"]=="and":
                for x in c["conditions"]:condition(x)
            else:raise ValueError("unsupported condition")
        for n in body:
            if n["op"] in ("if","require"):condition(n["condition"])
            if n["op"]=="if":self.audit(n["then"]);self.audit(n["else"])
            elif n["op"] in ("set","add","subtract"):operand(n["value"])
            elif n["op"]!="require":raise ValueError("pure scalar nodes only")

    def guards(self):
        result=[]
        for port in self.inputs:
            variable="$"+port
            bounds=[BOUNDS[self.contract["inputs"][port]]]
            for domain in (self.contract.get("domain",{}), self.domain):
                if port in domain:
                    b=domain[port];bounds.append((int(b["min"]),int(b["max"])))
            for low,high in bounds:result.append((variable,low,high))
        return result

    def wat(self):
        def value(v):
            return "(local.get $"+self.names[v["var"]]+")" if isinstance(v,dict) else "(i32.const "+str(self.literal(v))+")"
        def get(n):return "(local.get $"+self.names[n]+")"
        def cond(c):
            op=c["op"]
            if op=="eq":return "(i32.eq "+value(c["left"])+" "+value(c["right"])+")"
            if op=="bit_test":return "(i32.and (i32.shr_u "+value(c["value"])+" (i32.const "+str(c["bit"])+")) (i32.const 1))"
            if op=="not":return "(i32.eqz "+cond(c["condition"])+")"
            x=[cond(i) for i in c["conditions"]];r=x[0]
            for item in x[1:]:r="(i32.and "+r+" "+item+")"
            return r
        refuse="(return (i32.const 1) "+" ".join("(i32.const 0)" for _ in self.outputs)+")"
        def wrap(expression,typ):
            bits=1 if typ=="bool" else int(typ[1:])
            if typ.startswith("i"):
                return f"(i32.shr_s (i32.shl {expression} (i32.const {32-bits})) (i32.const {32-bits}))"
            return f"(i32.and {expression} (i32.const {(1<<bits)-1}))"
        def body(nodes):
            lines=[]
            for n in nodes:
                op=n["op"]
                if op=="if":
                    lines+=["(if "+cond(n["condition"])+" (then",*body(n["then"]),") (else",*body(n["else"]),"))"]
                elif op=="require":lines+=["(if (i32.eqz "+cond(n["condition"])+") (then "+refuse+"))"]
                else:
                    var=n["var"];v=value(n["value"]);typ=self.variables[var]["type"]
                    if op=="set":
                        lo,hi=BOUNDS[typ]
                        lines+=["(if (i32.or (i32.lt_s "+v+f" (i32.const {lo})) (i32.gt_s "+v+f" (i32.const {hi}))) (then "+refuse+"))"]
                    else:
                        v=wrap("(i32."+("add" if op=="add" else "sub")+" "+get(var)+" "+v+")",typ)
                    lines+=["(local.set $"+self.names[var]+" "+v+")"]
            return lines
        lines=["(module (func (export \"block\")",
               *["(param $"+self.names["$"+p]+" i32)" for p in self.inputs],
               "(result "+" ".join("i32" for _ in range(1+len(self.outputs)))+")",
               *["(local $"+self.names[n]+" i32)" for n in sorted(self.variables) if n not in {"$"+p for p in self.inputs}]]
        for n,d in sorted(self.variables.items()):
            if n not in {"$"+p for p in self.inputs}:lines+=["(local.set $"+self.names[n]+" (i32.const "+str(int(d["initial"]))+"))"]
        for var,lo,hi in self.guards():
            lines+=["(if (i32.or (i32.lt_s "+get(var)+f" (i32.const {lo})) (i32.gt_s "+get(var)+f" (i32.const {hi}))) (then "+refuse+"))"]
        lines+=body(self.program["body"])
        lines+=["(i32.const 0)",*[get("$"+p) for p in self.outputs],"))"]
        return "\n".join(lines)+"\n"

    def wasm(self):
        """Encode the admitted instruction subset without an external assembler.

        Every emitted module is separately validated by its executing host.
        WAT is emitted alongside it for inspection and independent assembly.
        """
        def leb(value, signed=False):
            out = bytearray()
            while True:
                byte = value & 127
                value >>= 7
                done = (value == 0 and not (byte & 64)) or (value == -1 and bool(byte & 64)) if signed else value == 0
                out.append(byte if done else byte | 128)
                if done: return bytes(out)
        def vec(values): return leb(len(values)) + b''.join(values)
        def section(number,data): return bytes([number]) + leb(len(data)) + data
        ports = ['$'+p for p in self.inputs]
        locals_ = sorted(set(self.variables)-set(ports))
        indices = {name:i for i,name in enumerate(ports+locals_)}
        def const(value): return b'\x41'+leb(self.literal(value),True)
        def get(name): return b'\x20'+leb(indices[name])
        def operand(value): return get(value['var']) if isinstance(value,dict) else const(value)
        refuse = const(1)+b''.join(const(0) for _ in self.outputs)+b'\x0f'
        def when(condition,yes,no=None):
            return condition+b'\x04\x40'+yes+(b'\x05'+no if no is not None else b'')+b'\x0b'
        def condition(c):
            op = c['op']
            if op=='eq': return operand(c['left'])+operand(c['right'])+b'\x46'
            if op=='bit_test': return operand(c['value'])+const(c['bit'])+b'\x76'+const(1)+b'\x71'
            if op=='not': return condition(c['condition'])+b'\x45'
            parts = [condition(x) for x in c['conditions']]
            return parts[0]+b''.join(p+b'\x71' for p in parts[1:])
        def outside(value,low,high):
            return value+const(low)+b'\x48'+value+const(high)+b'\x4a\x72'
        def body(nodes):
            out = b''
            for n in nodes:
                op = n['op']
                if op=='if': out += when(condition(n['condition']),body(n['then']),body(n['else']))
                elif op=='require': out += when(condition(n['condition'])+b'\x45',refuse)
                else:
                    name = n['var']; typ = self.variables[name]['type']; value = operand(n['value'])
                    if op=='set': out += when(outside(value,*BOUNDS[typ]),refuse)
                    else:
                        bits = 1 if typ=='bool' else int(typ[1:])
                        value = get(name)+value+(b'\x6a' if op=='add' else b'\x6b')
                        value += const(32-bits)+b'\x74'+const(32-bits)+b'\x75' if typ.startswith('i') else const((1<<bits)-1)+b'\x71'
                    out += value+b'\x21'+leb(indices[name])
            return out
        code = (leb(1)+leb(len(locals_))+b'\x7f') if locals_ else leb(0)
        for name in locals_: code += const(int(self.variables[name]['initial']))+b'\x21'+leb(indices[name])
        for name,low,high in self.guards(): code += when(outside(get(name),low,high),refuse)
        code += body(self.program['body'])+const(0)+b''.join(get('$'+p) for p in self.outputs)+b'\x0b'
        signature = b'\x60'+vec([b'\x7f']*len(self.inputs))+vec([b'\x7f']*(len(self.outputs)+1))
        export = leb(5)+b'block\x00\x00'
        return (b'\0asm\x01\0\0\0'+section(1,vec([signature]))+section(3,vec([leb(0)]))
                +section(7,vec([export]))+section(10,vec([leb(len(code))+code])))

    def wgsl(self):
        def literal(n):
            v=self.literal(n)
            return "(-2147483647i - 1i)" if v==-(1<<31) else str(v)+"i"
        def value(v):return self.names[v["var"]] if isinstance(v,dict) else literal(v)
        def cond(c):
            op=c["op"]
            if op=="eq":return "("+value(c["left"])+" == "+value(c["right"])+")"
            if op=="bit_test":return "(((bitcast<u32>("+value(c["value"])+") >> "+str(c["bit"])+"u) & 1u) != 0u)"
            if op=="not":return "!("+cond(c["condition"])+")"
            return "("+" && ".join(cond(x) for x in c["conditions"])+")"
        refuse="out_data[base] = 1i; return;"
        def body(nodes):
            lines=[]
            for n in nodes:
                op=n["op"]
                if op=="if":lines+=["if ("+cond(n["condition"])+") {",*body(n["then"]),"} else {",*body(n["else"]),"}"]
                elif op=="require":lines+=["if (!("+cond(n["condition"])+")) { "+refuse+" }"]
                else:
                    var=n["var"];name=self.names[var];v=value(n["value"]);typ=self.variables[var]["type"]
                    if op=="set":
                        lo,hi=BOUNDS[typ];lines+=["if ("+v+" < "+literal(lo)+" || "+v+" > "+literal(hi)+") { "+refuse+" }"]
                    else:
                        bits=1 if typ=="bool" else int(typ[1:])
                        v="(bitcast<u32>("+name+") "+("+" if op=="add" else "-")+" bitcast<u32>("+v+"))"
                        v="(bitcast<i32>("+v+f" << {32-bits}u) >> {32-bits}u)" if typ.startswith("i") else "i32("+v+f" & {(1<<bits)-1}u)"
                    lines+=[name+" = "+v+";"]
            return lines
        lines=["@group(0) @binding(0) var<storage, read> in_data: array<i32>;",
               "@group(0) @binding(1) var<storage, read_write> out_data: array<i32>;",
               "@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) id: vec3<u32>) {",
               f"let row = id.x; if (row >= arrayLength(&in_data)/{len(self.inputs)}u) {{ return; }}",
               f"let base = row * {len(self.outputs)+1}u;"]
        for n,d in sorted(self.variables.items()):
            init=f"in_data[row*{len(self.inputs)}u + {self.inputs.index(n[1:])}u]" if n[1:] in self.inputs else literal(d["initial"])
            lines+=["var "+self.names[n]+": i32 = "+init+";"]
        for var,lo,hi in self.guards():
            v=self.names[var]
            lines+=["if ("+v+" < "+literal(lo)+" || "+v+" > "+literal(hi)+") { "+refuse+" }"]
        lines+=body(self.program["body"])
        for i,p in enumerate(self.outputs):lines+=["out_data[base + "+str(i+1)+"u] = "+self.names["$"+p]+";"]
        lines+=["out_data[base] = 0i;","}"]
        return "\n".join(lines)+"\n"


def build_web_block(project, selection, destination):
    """Resolve and emit one persisted scalar selection; never execute it."""
    destination = Path(destination).expanduser().absolute()
    if os.path.lexists(destination):
        raise ValueError('web block requires a new private output outside Git')
    destination = destination.resolve()
    if os.path.lexists(destination) or any((p/'.git').exists() for p in (destination,*destination.parents)):
        raise ValueError('web block requires a new private output outside Git')
    lower = Lowerer.from_selection(project,selection)
    target = lower.capsule['target']
    artifacts = {'host.mjs':files('fdisbull').joinpath('web_runtime/block.mjs').read_bytes()}
    if target=='wasm32-scalar-1':
        artifacts.update({'block.wasm':lower.wasm(),'block.wat':lower.wat().encode()})
    else:
        artifacts['block.wgsl'] = lower.wgsl().encode()
    receipt = {'format':FORMAT, **lower.capsule,
        'abi':{'format':'fdisbull-web-scalar-abi-1','inputs':lower.inputs,'outputs':lower.outputs,
               'row_limit':8192,'carrier':'signed i32; logical byte/word guards; status 0=complete, 1=refused'},
        'artifacts':{name:hashlib.sha256(data).hexdigest() for name,data in artifacts.items()},
        'execution':False,'source_to_uil':False,
        'scope':'one pure canonical UIL invoke; no services or application state commit'}
    destination.mkdir(parents=True,mode=0o700,exist_ok=False)
    for name,data in artifacts.items(): (destination/name).write_bytes(data)
    (destination/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
