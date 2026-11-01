"""A bounded stdin/stdout analysis scaffold over one fixed UIL invocation.

Reuses the macOS C renderer/compiler/linker; it never runs an output. The wire
ABI is a canonical little-endian word per sorted input port. Signed bytes must
be sign-extended into that word. Every row is admitted before its block runs.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile

from .udc_c import generate_c
from .udc_layers import _validate_layer, digest
from .udc_macos import _compiler, _compile, _link, DEFAULT_TARGET, PROFILE
from .udc_qualify import qualify_uil

FORMAT = "fdisbull-macos-block-probe-1"
BOUNDS = {"bool": (0, 1), "i8": (-128, 127), "u8": (0, 255),
          "i16": (-32768, 32767), "u16": (0, 65535)}


def _decode(expr, typ):
    if typ in ("i16", "i8"):
        return "(int)(short)(" + expr + ")"
    return "(int)(" + expr + ")"


def build_macos_block_probe(project, selection, destination, *, c_compiler=None):
    """Build one qualified pure block, with native typed/domain guards.

    Admits one canonical module-UIL invoke and one selected UIL/C-UIL layer.
    There are no services, effects, native16 emulation or ambient state. This
    is an analysis scaffold, not a general game-host or process-equivalence gate.
    """
    selected_info = project.udl_selection_info(selection, full=True)
    selected = selected_info["document"]
    if len(selected["bindings"]) != 1:
        raise ValueError("block probe requires exactly one selected binding")
    binding, layer_id = next(iter(selected["bindings"].items()))
    info = project.udl_layer_info(layer_id, full=True)
    layer = info["document"]
    contract = _validate_layer(project, layer)
    impl = deepcopy(layer["implementation"])
    if impl["backend"] not in ("uil", "c-uil") or contract["behavior"]["kind"] != "uil":
        raise ValueError("block probe requires pure supplied UIL")
    if contract.get("effects") or layer.get("adapter") or impl.get("notification_binding"):
        raise ValueError("block probe cannot ignore extra effects or adapters")
    for descriptor in (contract["behavior"], impl):
        for side in ("inputs", "outputs"):
            canonical = {name: "$" + name for name in contract[side]}
            if descriptor.get(side, canonical) != canonical:
                raise ValueError("block probe requires canonical port mappings")
    if not contract["inputs"] or not contract["outputs"]:
        raise ValueError("block probe requires input/output ports")
    if any(t not in BOUNDS for side in ("inputs", "outputs") for t in contract[side].values()):
        raise ValueError("block probe supports byte/word ports only")
    module = selected.get("program")
    from .udc_blueprint import validate_module_uil
    validate_module_uil(project, module)
    invoke = {"id": module["body"][0]["id"] if module["body"] else "",
              "op": "invoke", "binding": binding, "contract": layer["contract"],
              "inputs": {k: {"var": "$"+k} for k in contract["inputs"]},
              "outputs": {k: "$"+k for k in contract["outputs"]}}
    if module["body"] != [invoke] or module.get("resources"):
        raise ValueError("block probe requires one canonical UIL invocation")
    proof = qualify_uil(contract, {**impl, "backend": "uil"})
    if proof["status"] != "equivalent_under_contract":
        raise ValueError("block probe implementation lacks model qualification")
    impl.pop("inputs", None); impl.pop("outputs", None)
    inputs, outputs = sorted(contract["inputs"]), sorted(contract["outputs"])
    impl["state_adapter"] = {"inputs": ["$"+n for n in inputs],
                             "outputs": ["$"+n for n in outputs]}
    source, actual_in, actual_out = generate_c(impl, "udc_block")
    if actual_in != impl["state_adapter"]["inputs"] or actual_out != impl["state_adapter"]["outputs"]:
        raise ValueError("C word ABI differs from declared port order")
    guards = []
    for i, name in enumerate(inputs):
        value = _decode("in["+str(i)+"]", contract["inputs"][name])
        low, high = BOUNDS[contract["inputs"][name]]
        guards.append(f"({value} < {low} || {value} > {high})")
        for domain in (contract.get("domain", {}), layer.get("domain", {})):
            if name in domain:
                lo, hi = domain[name]["min"], domain[name]["max"]
                guards.append(f"({value} < {int(lo)} || {value} > {int(hi)})")
    lines = ["#include <unistd.h>", "#include <stdio.h>",
             "extern unsigned long long udc_block(const unsigned short *, unsigned short *);",
             "int main(void) {", f"unsigned char raw[{2*len(inputs)}];",
             f"unsigned short in[{len(inputs)}], out[{len(outputs)}];",
             "for (unsigned row=0; row<10000; ++row) {",
             "unsigned n=0; while(n<sizeof(raw)) {",
             "long got=read(0,raw+n,sizeof(raw)-n);",
             "if(got==0) return n ? 2 : 0; if(got<0) return 2; n+=(unsigned)got; }",
             f"for(unsigned i=0;i<{len(inputs)};++i) in[i]=raw[2*i]|((unsigned)raw[2*i+1]<<8);",
             "unsigned long long status=1ULL<<32;",
             "if(!("+" || ".join(guards)+")) status=udc_block(in,out);",
             'printf("{\\"format\\":\\"'+FORMAT+'\\",\\"index\\":%u,\\"status\\":\\"%s\\",\\"outputs\\":{",row,status>>32 ? "refused" : "complete");',
             "if(!(status>>32)) {"]
    for i, name in enumerate(outputs):
        value = _decode("out["+str(i)+"]", contract["outputs"][name])
        lines.append('printf("'+("," if i else "")+'\\"'+name+'\\":%d",'+value+");")
    lines += ['} puts("}}");', "}", "unsigned char extra; return read(0,&extra,1)==0 ? 0 : 2;", "}"]
    wrapper = "\n".join(lines)+"\n"
    destination = Path(destination).expanduser().resolve()
    if destination.exists() or any((p/".git").exists() for p in (destination, *destination.parents)):
        raise ValueError("block probe requires a new private output outside Git")
    compiler, compiler_info = _compiler(c_compiler or shutil.which("clang"))
    with tempfile.TemporaryDirectory(prefix="fdisbull-arm64-probe-") as tmp:
        root = Path(tmp)
        block = _compile(compiler, source, root, "block", DEFAULT_TARGET)
        shell = _compile(compiler, wrapper, root, "shell", DEFAULT_TARGET)
        image = _link(compiler, [block["object"], shell["object"]], root, DEFAULT_TARGET)
        import lief
        parsed = lief.MachO.parse(list(image)).at(0)
        if parsed.header.cpu_type != lief.MachO.Header.CPU_TYPE.ARM64:
            raise ValueError("block probe output is not ARM64")
    import hashlib
    sha = lambda b: hashlib.sha256(b).hexdigest()
    receipt = {"format": FORMAT, "backend_profile": PROFILE,
               "selection": selected_info["id"], "selection_sha256": selected_info["sha256"],
               "module_uil_sha256": digest(module), "layer": info["id"],
               "layer_sha256": info["sha256"], "contract": layer["contract"],
               "contract_sha256": digest(contract), "qualification": proof,
               "block_source_sha256": block["source_sha256"],
               "block_object_sha256": block["object_sha256"],
               "shell_source_sha256": shell["source_sha256"],
               "output_sha256": sha(image), "compiler": compiler_info,
               "inputs": inputs, "outputs": outputs, "row_limit": 10000,
               "wire": "little-endian uint16 words; signed inputs sign-extended; sorted ports",
               "native_execution": False, "source_to_uil": False,
               "scope": "one pure fixed UIL invoke; guarded word ABI; stdin/stdout analysis scaffold"}
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    (destination/"program").write_bytes(image); (destination/"program").chmod(0o700)
    (destination/"block.c").write_text(source); (destination/"shell.c").write_text(wrapper)
    (destination/"build.json").write_text(json.dumps(receipt, indent=2)+"\n")
    return receipt
