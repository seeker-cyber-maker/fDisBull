"""Native macOS arm64 realization of a shared-UIL plan through generated C.

This is an explicit *sweding* profile: the UIL maintains intention, typed state
effects and event order, while the machinery changes from fixed x86-64 slot
lowering to generator-owned C compiled for the local Apple arm64 target. The
result links libSystem for ``write`` and C runtime startup, so it is not a
freestanding image; that dependency, the stdout service adapter and the absence
of a native-execution claim by the builder are recorded in every receipt.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import platform
import struct
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .udc_c import generate_c
from . import game_il
from .shadowrun_replay import _new_private_directory
from .udc_shell import (
    FORMAT,
    NOTIFICATION_BACKENDS,
    _check,
    _json,
    _remove_owned_output,
    _text,
    _validate,
)

PROFILE = "macos-arm64-c-plan-libsystem-1"
FORMAT_NAME = "fdisbull-native-shell-build-1"
DEFAULT_TARGET = "arm64-apple-macos11"
OBSERVATION_FORMAT = "fdisbull-macos-observation-1"
COMPILE_FLAGS = [
    "-std=c11",
    "-O1",
    "-ffreestanding",
    "-fno-builtin",
    "-fno-stack-protector",
    "-fno-asynchronous-unwind-tables",
]
BOUNDS = {"bool": (0, 1), "u8": (0, 255), "u16": (0, 65535), "i16": (-32768, 32767)}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _cname(name: str) -> str:
    _check(isinstance(name, str) and name, "state cell name required")
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", name)
    return "v_" + cleaned.lstrip("_")


def _fn_name(name: str) -> str:
    return "fn_" + _cname(name)[2:]


def _block_name(name: str) -> str:
    return "blk_" + _cname(name)[2:]


def _emit_name(name: str) -> str:
    return "emit_" + _cname(name)[2:]


def _cstr(text: str) -> str:
    _check(all(ord(ch) < 128 for ch in text), "native text resources must be ASCII")
    _check(
        all(ch >= " " or ch in "\n\t" for ch in text), "unsupported control character"
    )
    return (
        '"'
        + text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        + '"'
    )


def _value(item, cells: dict) -> str:
    if isinstance(item, dict):
        _check(set(item) == {"var"} and item["var"] in cells, "unknown plan variable")
        return _cname(item["var"])
    _check(type(item) in (int, bool), "invalid plan literal")
    return str(int(item))


def _condition(item, cells: dict) -> str:
    op = item["op"]
    if op == "eq":
        return (
            "("
            + _value(item["left"], cells)
            + " == "
            + _value(item["right"], cells)
            + ")"
        )
    if op == "bit_test":
        return (
            "((((unsigned long long)"
            + _value(item["value"], cells)
            + ") >> "
            + str(item["bit"])
            + ") & 1ULL)"
        )
    if op == "not":
        return "(!(" + _condition(item["condition"], cells) + "))"
    return (
        "("
        + " && ".join(_condition(child, cells) for child in item["conditions"])
        + ")"
    )


def _wrapper(body, cells, modules, bindings, counter, indent="  "):
    """Render plan statements. ``counter`` is a one-item mutable step index."""
    lines = []
    for item in body:
        op = item["op"]
        if op in ("set", "add", "subtract"):
            cell = item["var"]
            typ = cells[cell]["type"]
            name = _cname(cell)
            operand = _value(item["value"], cells)
            if op == "set":
                low, high = BOUNDS[typ]
                lines.append(indent + "{ long long t = " + operand + ";")
                lines.append(
                    indent
                    + f"  if (t < {low} || t > {high}) {{ g_status = 1; return 0; }}"
                )
                lines.append(indent + f"  {name} = t; }}")
            else:
                sign = "+" if op == "add" else "-"
                cast = {
                    "u8": "unsigned char",
                    "u16": "unsigned short",
                    "i16": "short",
                    "bool": "unsigned char",
                }[typ]
                lines.append(
                    indent
                    + "{ long long t = "
                    + name
                    + " "
                    + sign
                    + " ("
                    + operand
                    + ");"
                )
                lines.append(indent + f"  {name} = (long long)({cast})t; }}")
        elif op == "if":
            lines.append(indent + "if (" + _condition(item["condition"], cells) + ") {")
            lines.extend(
                _wrapper(item["then"], cells, modules, bindings, counter, indent + "  ")
            )
            lines.append(indent + "} else {")
            lines.extend(
                _wrapper(item["else"], cells, modules, bindings, counter, indent + "  ")
            )
            lines.append(indent + "}")
        elif op == "while":
            counter[0] += 1
            guard = "guard_" + str(counter[0])
            lines.append(
                indent + "{ long long " + guard + " = " + str(item["limit"]) + ";"
            )
            lines.append(
                indent + "  while (!(" + _condition(item["condition"], cells) + ")) {"
            )
            lines.append(
                indent + f"    if ({guard}-- <= 0) {{ g_status = 2; return 0; }}"
            )
            lines.extend(
                _wrapper(
                    item["body"], cells, modules, bindings, counter, indent + "    "
                )
            )
            lines.append(indent + "  } }")
        elif op == "return":
            lines.append(indent + "return " + _value(item["value"], cells) + ";")
        elif op == "call":
            if "function" in item:
                lines.append(indent + "if (g_status) return 0;")
                lines.append(indent + _fn_name(item["function"]) + "();")
            else:
                binding = item["binding"]
                module = modules[binding]
                adapter = module["state_adapter"]
                inputs = adapter["inputs"]
                outputs = adapter["outputs"]
                ins = ", ".join(
                    "(unsigned short)(" + _cname(name) + " & 0xffff)" for name in inputs
                )
                lines.append(indent + "{")
                lines.append(
                    indent
                    + "  unsigned short in["
                    + str(max(1, len(inputs)))
                    + "] = {"
                    + (ins or "0")
                    + "};"
                )
                lines.append(
                    indent + "  unsigned short out[" + str(max(1, len(outputs))) + "];"
                )
                lines.append(
                    indent
                    + "  unsigned long long r = "
                    + _block_name(binding)
                    + "(in, out);"
                )
                lines.append(
                    indent + "  if ((r >> 32) != 0) { g_status = 1; return 0; }"
                )
                for index, name in enumerate(outputs):
                    typ = cells[name]["type"]
                    cast = {
                        "u8": "unsigned char",
                        "u16": "unsigned short",
                        "i16": "short",
                        "bool": "unsigned char",
                    }[typ]
                    suffix = " & 1" if typ == "bool" else ""
                    lines.append(
                        indent
                        + f"  {_cname(name)} = (long long)({cast})out[{index}]{suffix};"
                    )
                lines.append(indent + "}")
        elif op == "notify":
            lines.append(
                indent
                + _emit_name(item["binding"])
                + "("
                + _value(item["value"], cells)
                + ");"
            )
        else:
            raise ValueError("unsupported macos plan statement: " + str(op))
    return lines


def _render(plan: dict, modules: dict) -> dict:
    cells = plan["state"]
    functions = plan["functions"]
    services = {
        name
        for name, module in modules.items()
        if module["backend"] not in ("uil", "c-uil")
    }
    lines = [
        "/* generated by fdisbull; do not edit */",
        "extern int write(int, const void *, unsigned long);",
        "typedef unsigned long size_t_;",
        "static int g_status;",
    ]
    for name in modules:
        lines.append(
            "unsigned long long "
            + _block_name(name)
            + "(const unsigned short *, unsigned short *);"
        )
    for name in functions:
        lines.append("long long " + _fn_name(name) + "(void);")
    for name, cell in cells.items():
        lines.append("static long long " + _cname(name) + ";")
    lines.append("static char obuf[2048];")
    lines.append("static int olen;")
    lines += [
        "static void oput(const char *s) { while (*s) obuf[olen++] = *s++; }",
        "static void oputn(long long v) {",
        "  char tmp[24]; int n = 0; unsigned long long u = v < 0 ? (unsigned long long)(-v) : (unsigned long long)v;",
        "  if (v < 0) obuf[olen++] = '-';",
        "  if (u == 0) tmp[n++] = '0';",
        "  while (u) { tmp[n++] = (char)('0' + (u % 10)); u /= 10; }",
        "  while (n) obuf[olen++] = tmp[--n];",
        "}",
        "static void oquoted(const char *s) { obuf[olen++] = '\"'; while (*s) obuf[olen++] = *s++; obuf[olen++] = '\"'; }",
    ]
    for binding in sorted(services):
        module = modules[binding]
        lines.append("static void " + _emit_name(binding) + "(long long value) {")
        lines.append("  const char *text;")
        ordered = sorted(module["messages"].items(), key=lambda pair: int(pair[0]))
        if ordered:
            for index, (key, resource) in enumerate(ordered):
                prefix = "if" if index == 0 else "else if"
                lines.append(
                    f"  {prefix} (value == {int(key)}) text = {_cstr(plan['resources'][resource]['text'])};"
                )
            lines.append(
                "  else text = "
                + _cstr(plan["resources"][module["default"]]["text"])
                + ";"
            )
        else:
            lines.append(
                "  text = " + _cstr(plan["resources"][module["default"]]["text"]) + ";"
            )
        lines.append(
            "  { const char *p = text; size_t_ n = 0; while (*p++) n++; write(1, text, n); }"
        )
        lines.append("}")
    counter = [0]
    for name, function in functions.items():
        lines.append("long long " + _fn_name(name) + "(void) {")
        body = _wrapper(function["body"], cells, modules, functions, list(counter))
        if body:
            lines.extend(body)
        lines.append("  return 0;")
        lines.append("}")
    lines.append("int main(void) {")
    for name, cell in cells.items():
        lines.append("  " + _cname(name) + " = " + str(int(cell["initial"])) + ";")
    lines.append("  g_status = 0;")
    lines.append("  long long result = " + _fn_name(plan["entry"]) + "();")
    lines.append("  if (g_status == 0 && result < 0) g_status = 0;")
    lines.append(
        '  oput("{\\"format\\":\\"");oput("' + OBSERVATION_FORMAT + '");oput("\\"");'
    )
    lines.append('  oput(",\\"status\\":");oputn(g_status);')
    lines.append('  oput(",\\"value\\":");oputn(result);')
    lines.append('  oput(",\\"state\\":{");')
    lines.append("  { int first = 1;")
    for name in cells:
        lines.append('    if (!first) oput(","); first = 0;')
        lines.append(
            "    oquoted(" + _cstr(name) + '); oput(":"); oputn(' + _cname(name) + ");"
        )
    lines.append("  }")
    lines.append('  oput("}}\\n");')
    lines.append("  write(1, obuf, (unsigned long)olen);")
    lines.append("  return g_status;")
    lines.append("}")
    return {"source": "\n".join(lines) + "\n", "services": services}


def _compiler(path) -> tuple[Path, dict]:
    _check(path is not None, "macOS shell requires an explicit clang executable")
    compiler = Path(path).expanduser().resolve(strict=True)
    raw = compiler.read_bytes()
    try:
        probe = subprocess.run(
            [str(compiler), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("compiler version probe failed") from error
    _check(
        probe.returncode == 0 and probe.stdout.splitlines(),
        "compiler version probe failed",
    )
    version = probe.stdout.splitlines()[0]
    _check("clang" in version.lower(), "macOS shell requires clang")
    return compiler, {"path": str(compiler), "sha256": _sha(raw), "version": version}


def _compile(compiler: Path, source: str, root: Path, name: str, target: str) -> dict:
    path = root / (name + ".c")
    path.write_text(source)
    flags = ["--target=" + target, *COMPILE_FLAGS, "-c", path.name, "-o", name + ".o"]
    try:
        done = subprocess.run(
            [str(compiler), *flags],
            cwd=root,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("macOS module compilation failed") from error
    _check(
        done.returncode == 0,
        "macOS C compilation failed: " + done.stderr.decode(errors="replace")[:1200],
    )
    return {
        "source": source,
        "source_sha256": _sha(source.encode()),
        "object": name + ".o",
        "object_sha256": _sha((root / (name + ".o")).read_bytes()),
        "flags": flags,
    }


def _link(compiler: Path, objects: list[str], root: Path, target: str) -> bytes:
    command = [str(compiler), "--target=" + target, *objects, "-o", "image"]
    try:
        done = subprocess.run(
            command, cwd=root, capture_output=True, timeout=120, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("macOS link failed") from error
    _check(
        done.returncode == 0,
        "macOS link failed: " + done.stderr.decode(errors="replace")[:1200],
    )
    return (root / "image").read_bytes()


def build_macos_shell(
    plan, modules, destination, *, service_adapters=None, c_compiler=None, target=None
):
    """Emit a native arm64 Mach-O program for one validated shared-UIL plan.

    Builders never execute the output. The entry state, module adapters, service
    text and C compiler identity are retained; native observation is separate.
    """
    plan, modules = deepcopy(plan), deepcopy(modules)
    target = DEFAULT_TARGET if target is None else target
    _check(
        isinstance(target, str) and target.startswith("arm64-apple-macos"),
        "unsupported macOS target; expected arm64-apple-macos*",
    )
    admitted = NOTIFICATION_BACKENDS + ("macos-stdout",)
    _validate(plan, modules, admitted)
    services = {
        name
        for name, module in modules.items()
        if module["backend"] not in ("uil", "c-uil")
    }
    service_adapters = deepcopy(service_adapters or {})
    _check(
        set(service_adapters) == services,
        "macOS needs an explicit adapter for every native notification",
    )
    for adapter in service_adapters.values():
        _check(
            adapter == {"backend": "macos-stdout", "acknowledgment": "none"},
            "unsupported macOS presentation adapter",
        )
    for name, module in modules.items():
        if module["backend"] in ("uil", "c-uil"):
            _check(
                isinstance(module.get("state_adapter"), dict),
                f"macOS module {name} requires an explicit state_adapter",
            )
            adapter = module["state_adapter"]
            _check(
                set(adapter) == {"inputs", "outputs"}, "invalid module state adapter"
            )
            for side in ("inputs", "outputs"):
                _check(
                    all(name_ in plan["state"] for name_ in adapter[side]),
                    "module adapter must reference declared plan state",
                )
    destination = Path(destination).expanduser().resolve()
    _check(not destination.exists(), "macOS output must be new")
    _check(
        not any(
            (parent / ".git").exists() for parent in (destination, *destination.parents)
        ),
        "macOS output must be outside Git",
    )
    compiler, compiler_info = _compiler(c_compiler or shutil.which("clang"))
    rendered = _render(plan, modules)
    compiled_modules, sources = {}, {}
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    owned = destination.stat()
    files: dict[str, tuple[int, int]] = {}
    try:
        objects = []
        scratch = tempfile.TemporaryDirectory(prefix="fdisbull-macos-")
        work = Path(scratch.name)
        for name, module in modules.items():
            if module["backend"] not in ("uil", "c-uil"):
                continue
            symbol = _block_name(name)
            source, inputs, outputs = generate_c(module, symbol)
            record = _compile(compiler, source, work, "mod_" + _cname(name)[2:], target)
            compiled_modules[name] = {
                "symbol": symbol,
                "source_sha256": record["source_sha256"],
                "object_sha256": record["object_sha256"],
                "inputs": inputs,
                "outputs": outputs,
                "backend": module["backend"],
            }
            sources[name] = record["source"]
            objects.append(record["object"])
        plan_record = _compile(compiler, rendered["source"], work, "plan", target)
        sources["plan"] = rendered["source"]
        objects.append(plan_record["object"])
        image = _link(compiler, objects, work, target)
        import lief

        parsed = lief.MachO.parse(str(work / "image")).at(0)
        _check(
            parsed.header.cpu_type == lief.MachO.Header.CPU_TYPE.ARM64,
            "output is not arm64",
        )
        _check(
            parsed.header.file_type == lief.MachO.Header.FILE_TYPE.EXECUTE,
            "output is not an executable",
        )
        symbol_table = {symbol.name: symbol.value for symbol in parsed.symbols}
        functions = {
            name: symbol_table.get("_" + _fn_name(name)) for name in plan["functions"]
        }
        _check(functions[plan["entry"]] is not None, "entry function symbol is missing")
        manifest = {
            "format": FORMAT_NAME,
            "profile": PROFILE,
            "plan_sha256": _sha(_json(plan)),
            "modules_sha256": _sha(_json(modules)),
            "c_modules": compiled_modules,
            "target": {
                "format": "Mach-O",
                "arch": "arm64",
                "triple": target,
                "linkage": "dyld + libSystem (write, C runtime startup)",
                "original_binary_wrapped": False,
            },
            "output": {
                "path": "program",
                "absolute_path": str(destination / "program"),
                "sha256": _sha(image),
                "size": len(image),
            },
            "entry_symbol": "_main",
            "function_symbols": functions,
            "state": {
                name: {"type": cell["type"], "initial": cell["initial"]}
                for name, cell in plan["state"].items()
            },
            "service_adapters": service_adapters,
            "observation": {
                "stream": "stdout",
                "format": OBSERVATION_FORMAT,
                "frame": "single JSON line; status, value, typed state",
            },
            "compiler": compiler_info,
            "qualification": {
                "native_execution": False,
                "source_to_uil": False,
                "scope": "generated C plan and declared stdout presentation; "
                "no MessageBox/console equivalence or native-run claim",
            },
        }
        capsule = {
            "format": "fdisbull-native-shell-capsule-1",
            "plan": plan,
            "modules": modules,
            "build": manifest,
            "generated": {"plan_c": rendered["source"], "modules_c": sources},
        }
        payload = _json(capsule) + b"\n"
        for name, raw in (("program", image), ("capsule.json", payload)):
            path = destination / name
            with path.open("xb") as stream:
                stat = os.fstat(stream.fileno())
                files[name] = (stat.st_dev, stat.st_ino)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(path, 0o700 if name == "program" else 0o600)
            _check(path.read_bytes() == raw, "macOS output readback mismatch")
    except BaseException:
        _remove_owned_output(destination, (owned.st_dev, owned.st_ino), files)
        raise
    finally:
        if "scratch" in locals():
            scratch.cleanup()
    return {
        **manifest,
        "directory": str(destination),
        "capsule": str(destination / "capsule.json"),
        "source_format": FORMAT,
    }

HEADER = '''#ifndef FDISBULL_NATIVE_H
#define FDISBULL_NATIVE_H
#include <stdint.h>
typedef struct fdisbull_context fdisbull_context;
int fdisbull_create(const char *rom_path, fdisbull_context **out);
void fdisbull_destroy(fdisbull_context *ctx);
int fdisbull_reset(fdisbull_context *ctx);
int fdisbull_step(fdisbull_context *ctx, uint8_t pad);
int fdisbull_state_get(const fdisbull_context *ctx, const char *name, uint32_t index, int64_t *out);
int fdisbull_state_set(fdisbull_context *ctx, const char *name, uint32_t index, int64_t value);
const char *fdisbull_error(const fdisbull_context *ctx);
#endif
'''

RUNTIME = r'''
#include "fdisbull_native.h"
#include <CommonCrypto/CommonDigest.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
typedef struct { int64_t n; unsigned bits, sign; } V;
struct fdisbull_context { struct state s; unsigned char *rom; uint32_t rom_len; const unsigned char *regions[256]; uint32_t region_lengths[256]; jmp_buf trap; unsigned steps; const char *error; uint32_t scratch; };
static V cv(uint64_t x,unsigned bits,unsigned sign) {
    V v; if (!bits) { v.n=0;v.bits=0;v.sign=0;return v; }
    uint64_t mask=(UINT64_C(1)<<bits)-1; x &= mask;
    v.n=(sign && (x & (UINT64_C(1)<<(bits-1)))) ? (int64_t)x-(int64_t)(UINT64_C(1)<<bits) : (int64_t)x;
    v.bits=bits;v.sign=sign;return v;
}
static V prom(V a) {return a.bits<16 ? cv((uint64_t)a.n,16,1) : a;}
static void fault(fdisbull_context*c,const char *msg){c->error=msg;longjmp(c->trap,1);}
static void tick(fdisbull_context*c){if (++c->steps>2000000U)fault(c,"operation budget exhausted");}
static V bin(fdisbull_context*c,int op,V a,V b) {
    a=prom(a);b=prom(b);
    if(op==8||op==9) {if(b.n<0 || b.n>=a.bits)fault(c,"invalid shift");
        if(op==8)return cv((uint64_t)a.n << b.n,a.bits,a.sign);
        return cv((uint64_t)(a.n >> b.n),a.bits,a.sign);}
    unsigned bits=a.bits>b.bits?a.bits:b.bits;
    unsigned sign=a.bits==b.bits ? (a.sign&&b.sign) : (a.bits>b.bits?a.sign:b.sign);
    a=cv((uint64_t)a.n,bits,sign);b=cv((uint64_t)b.n,bits,sign);
    switch(op){
      case 0:return cv((uint64_t)a.n+(uint64_t)b.n,bits,sign);
      case 1:return cv((uint64_t)a.n-(uint64_t)b.n,bits,sign);
      case 2:return cv((uint64_t)a.n*(uint64_t)b.n,bits,sign);
      case 3:if(!b.n)fault(c,"division by zero");return cv((uint64_t)(a.n/b.n),bits,sign);
      case 4:if(!b.n)fault(c,"division by zero");return cv((uint64_t)(a.n%b.n),bits,sign);
      case 5:return cv((uint64_t)a.n&(uint64_t)b.n,bits,sign);
      case 6:return cv((uint64_t)a.n|(uint64_t)b.n,bits,sign);
      case 7:return cv((uint64_t)a.n^(uint64_t)b.n,bits,sign);
      case 10:return cv(a.n==b.n,16,1);case 11:return cv(a.n!=b.n,16,1);
      case 12:return cv(a.n<b.n,16,1);case 13:return cv(a.n<=b.n,16,1);
      case 14:return cv(a.n>b.n,16,1);case 15:return cv(a.n>=b.n,16,1);
    } fault(c,"unknown operation");return cv(0,16,1);
}
static V compound(fdisbull_context*c,int op,V a,V b) {
    if(op==8||op==9) {
        a=prom(a);b=prom(b);unsigned bits=a.bits>b.bits?a.bits:b.bits;
        unsigned sign=a.bits==b.bits?(a.sign&&b.sign):(a.bits>b.bits?a.sign:b.sign);
        a=cv((uint64_t)a.n,bits,sign);b=cv((uint64_t)b.n,bits,sign);
    }
    return bin(c,op,a,b);
}
static uint32_t *at(fdisbull_context*c,uint32_t *p,uint32_t n,V i) {
    if(i.n<0 || (uint64_t)i.n>=n)fault(c,"array index out of bounds");return p+i.n;
}
static V readrom(fdisbull_context*c,V region,V offset,unsigned width){
    tick(c);if(region.n<0 || region.n>255 || !c->regions[region.n] || offset.n<0 || (uint64_t)offset.n+width>c->region_lengths[region.n])fault(c,"ROM read out of bounds");
    uint32_t x=0;for(unsigned i=0;i<width;i++)x=(x<<8)|c->regions[region.n][offset.n+i];return cv(x,width*8,0);
}
'''
OPS = {'+':0,'-':1,'*':2,'/':3,'%':4,'&':5,'|':6,'^':7,'<<':8,'>>':9,'==':10,'!=':11,'<':12,'<=':13,'>':14,'>=':15}

class _Compiler:
    def __init__(self, program, seed, *, entry='shadowrun_arena_frame', unsupported_status=None,
                 immutable_regions=None):
        self.tree=game_il.validate_program(program)
        self.machine=game_il.GameMachine(program,_validated_tree=self.tree,_validate_only=True)
        if set(seed)!=set(self.machine.globals):raise ValueError('Seed must contain every GameIL global exactly once')
        self.machine.set_state(seed)
        self.immutable_regions=dict(immutable_regions or {})
        bindings={r['id']:r for r in program.get('regions',[])}
        if set(self.immutable_regions)!=set(bindings)-{0}:
            raise ValueError('Native build requires every extra immutable region exactly once')
        for identifier,raw in self.immutable_regions.items():
            binding=bindings[identifier]
            if (type(identifier) is not int or not isinstance(raw,bytes)
                    or len(raw)!=binding['length']
                    or hashlib.sha256(raw).hexdigest()!=binding['sha256']):
                raise ValueError('Native immutable region identity mismatch')
        self.functions=self.machine.functions;self.globals=self.machine.global_types
        if not isinstance(entry,str) or entry not in self.functions:
            raise ValueError('Native backend requires entry procedure '+str(entry))
        frame=self.functions[entry]
        params=frame.decl.type.args.params if frame.decl.type.args else []
        if (len(params)!=1 or type(params[0]).__name__!='Decl'
                or type(params[0].type).__name__!='TypeDecl'
                or self.machine._type(params[0].type)[0] not in (8,16,32)
                or self.machine._type(frame.decl.type.type)!=(0,False)):
            raise ValueError('Native entry must return void and accept one integer logical pad')
        self.entry=entry
        if unsupported_status is None:
            candidate=entry+'_status'
            unsupported_status=candidate if candidate in self.globals else None
        if unsupported_status is not None:
            status_type=self.globals.get(unsupported_status) if isinstance(unsupported_status,str) else None
            if status_type is None or isinstance(status_type[0],tuple):
                raise ValueError('Native unsupported status must name a scalar global')
        self.unsupported_status=unsupported_status
        calls={name:set() for name in self.functions}
        def scan(node, owner):
            if type(node).__name__=='FuncCall' and node.name.name in calls:
                calls[owner].add(node.name.name)
            for _,child in node.children():scan(child,owner)
        for name,function in self.functions.items():scan(function.body,name)
        depths={}
        def depth(name):
            if name not in depths:depths[name]=1+max((depth(n) for n in calls[name]),default=0)
            return depths[name]
        if any(depth(name)>128 for name in calls):
            raise ValueError('Native GameIL call path exceeds the 128-frame limit')
        self.constants=self.machine.constants;self.local={};self.ret=(0,False);self.loop_stack=[];self.loop_id=0
    @staticmethod
    def raw(value,typ): return str(value & ((1<<typ[0])-1))+'U'
    def var(self,name):
        if name in self.local:return 'l_'+name,self.local[name]
        if name in self.globals:return 'c->s.g_'+name,self.globals[name]
        raise ValueError('Unknown GameIL variable '+name)
    def ref(self,node):
        if type(node).__name__=='ID':
            s,t=self.var(node.name)
            if isinstance(t[0],tuple):raise ValueError('Array requires index')
            return '&'+s,t
        if type(node).__name__=='ArrayRef' and type(node.name).__name__=='ID':
            s,t=self.var(node.name.name)
            if not isinstance(t[0],tuple):raise ValueError('Expected array')
            return f'at(c,{s},{t[1]}U,{self.expr(node.subscript)})',t[0]
        raise ValueError('Unsupported GameIL lvalue')
    def expr(self,node):
        k=type(node).__name__
        if k=='Constant':
            v=self.machine._expr(node);body=f'cv({self.raw(v.number,(v.bits,v.signed))},{v.bits},{int(v.signed)})'
        elif k=='ID':
            if node.name in self.constants:
                v=self.constants[node.name];body=f'cv({self.raw(v.number,(v.bits,v.signed))},{v.bits},{int(v.signed)})'
            else:
                s,t=self.var(node.name)
                if isinstance(t[0],tuple):raise ValueError('Array requires index')
                body=f'cv({s},{t[0]},{int(t[1])})'
        elif k=='ArrayRef':
            p,t=self.ref(node);body=f'cv(*({p}),{t[0]},{int(t[1])})'
        elif k=='Cast':
            t=self.machine._type(node.to_type);body=f'({{V a={self.expr(node.expr)};cv((uint64_t)a.n,{t[0]},{int(t[1])});}})'
        elif k=='BinaryOp':
            a=self.expr(node.left);b=self.expr(node.right)
            if node.op=='&&':body=f'({{V a={a};a.n?cv(({b}).n!=0,16,1):cv(0,16,1);}})'
            elif node.op=='||':body=f'({{V a={a};a.n?cv(1,16,1):cv(({b}).n!=0,16,1);}})'
            else:body=f'({{V a={a};V b={b};bin(c,{OPS[node.op]},a,b);}})'
        elif k=='UnaryOp':
            if node.op in ('++','--','p++','p--'):
                p,t=self.ref(node.expr);d='1' if '+' in node.op else '-1';ret='old' if node.op.startswith('p') else 'cv(*p,'+str(t[0])+','+str(int(t[1]))+')'
                body=f'({{uint32_t *p={p};V old=cv(*p,{t[0]},{int(t[1])});*p=(uint32_t)cv((uint64_t)(old.n+({d})),{t[0]},{int(t[1])}).n;{ret};}})'
            else:
                op=node.op;v=self.expr(node.expr)
                x={'!':'cv(!a.n,16,1)','+':'a','-':'cv((uint64_t)(-a.n),a.bits,a.sign)','~':'cv(~(uint64_t)a.n,a.bits,a.sign)'}[op]
                body=f'({{V a=prom({v});{x};}})'
        elif k=='FuncCall':
            name=node.name.name;args=list(node.args.exprs) if node.args else [];prefix=''.join(f'V a{i}={self.expr(x)};' for i,x in enumerate(args));a=','.join('a'+str(i) for i in range(len(args)))
            if name.startswith('rom'):
                if len(args)!=2:raise ValueError('ROM arity')
                call=f'readrom(c,a0,a1,{int(name[3:])//8}U)'
            elif name in ('hv16','sound_busy'):
                raise ValueError('Native backend requires an explicit environment adapter for '+name)
            elif name=='emit':
                if len(args)!=2:raise ValueError('emit arity')
                call='({tick(c);if(c->s.event_count>=4096U)fault(c,"event queue overflow");c->s.event_kind[c->s.event_count]=(uint8_t)a0.n;c->s.event_id[c->s.event_count++]=(uint8_t)a1.n;cv(0,0,0);})' 
            else:call=f'f_{name}(c'+(','+a if a else '')+')'
            body=f'({{{prefix}{call};}})'
        else:raise ValueError('Unsupported native expression '+k)
        return '({tick(c);'+body+';})'
    def stmt(self,node):
        if node is None:return ';'
        k=type(node).__name__;prefix='tick(c);'
        if k=='Compound':return '{'+prefix+''.join(self.stmt(x) for x in node.block_items or [])+'}'
        if k=='Decl':
            if type(node.type).__name__=='ArrayDecl':
                typ=self.machine._type(node.type.type);n=self.machine._expr(node.type.dim).number;self.local[node.name]=(typ,n)
                if node.init:raise ValueError('Local array initializers unsupported')
                return prefix+f'uint32_t l_{node.name}[{n}]={{0}};'
            typ=self.machine._type(node.type)
            val=f'(uint32_t)cv((uint64_t)({self.expr(node.init)}).n,{typ[0]},{int(typ[1])}).n' if node.init else '0'
            self.local[node.name]=typ
            return prefix+f'uint32_t l_{node.name}={val};'
        if k=='Assignment':
            p,t=self.ref(node.lvalue);v=self.expr(node.rvalue)
            if node.op=='=':val='rhs'
            else:val=f'compound(c,{OPS[node.op[:-1]]},cv(*p,{t[0]},{int(t[1])}),rhs)'
            return prefix+f'{{uint32_t *p={p};V rhs={v};V value={val};*p=(uint32_t)cv((uint64_t)value.n,{t[0]},{int(t[1])}).n;}}'
        if k=='If':return prefix+f'if(({self.expr(node.cond)}).n){{'+self.stmt(node.iftrue)+'}'+(('else {'+self.stmt(node.iffalse)+'}') if node.iffalse else '')
        if k=='For':
            self.loop_id+=1;label='loop_next_'+str(self.loop_id)
            init=self.stmt(node.init);nxt=self.stmt(node.next);cond=f'({self.expr(node.cond)}).n' if node.cond else '1'
            self.loop_stack.append(label);body=self.stmt(node.stmt);self.loop_stack.pop()
            return prefix+'{'+init+'unsigned __loops=0; for(;;){if(__loops++>=65536U)fault(c,"loop budget exhausted");if(!('+cond+'))break;'+body+label+':;'+nxt+'}}' 
        if k=='Return':return prefix+('return cv((uint64_t)('+self.expr(node.expr)+f').n,{self.ret[0]},{int(self.ret[1])});' if node.expr else 'return cv(0,0,0);')
        if k=='Break':return prefix+'break;'
        if k=='Continue':
            if not self.loop_stack:raise ValueError('Continue outside loop')
            return prefix+'goto '+self.loop_stack[-1]+';'
        if k=='EmptyStatement':return prefix+';'
        if k in ('FuncCall','UnaryOp'):return prefix+'(void)'+self.expr(node)+';'
        if k=='ExprList':return prefix+''.join(self.stmt(x) for x in node.exprs)
        raise ValueError('Unsupported native statement '+k)
    def generate(self,program):
        g=[];seed=[];gets=[];sets=[]
        snap=self.machine.snapshot()
        for name,t in self.globals.items():
            if isinstance(t[0],tuple):
                typ,n=t;g.append(f'uint32_t g_{name}[{n}];')
                for i,v in enumerate(snap[name]):
                    if v:seed.append(f'c->s.g_{name}[{i}]={self.raw(v,typ)};')
                gets.append(f'if(!strcmp(name,"{name}")){{if(index>={n}U)return 1;*out=cv(c->s.g_{name}[index],{typ[0]},{int(typ[1])}).n;return 0;}}')
                sets.append(f'if(!strcmp(name,"{name}")){{if(index>={n}U)return 1;c->s.g_{name}[index]=(uint32_t)cv((uint64_t)value,{typ[0]},{int(typ[1])}).n;return 0;}}')
            else:
                g.append(f'uint32_t g_{name};')
                if snap[name]:seed.append(f'c->s.g_{name}={self.raw(snap[name],t)};')
                gets.append(f'if(!strcmp(name,"{name}")){{if(index)return 1;*out=cv(c->s.g_{name},{t[0]},{int(t[1])}).n;return 0;}}')
                sets.append(f'if(!strcmp(name,"{name}")){{if(index)return 1;c->s.g_{name}=(uint32_t)cv((uint64_t)value,{t[0]},{int(t[1])}).n;return 0;}}')
        decl='struct state {'+''.join(g)+'uint32_t event_count;uint8_t event_kind[4096],event_id[4096];};\n'
        protos=[];bodies=[]
        for name,f in self.functions.items():
            params=f.decl.type.args.params if f.decl.type.args else []
            if len(params)==1 and type(params[0]).__name__=='Typename' and self.machine._type(params[0])==(0,False):params=[]
            sig=f'static V f_{name}(fdisbull_context*c'+''.join(f',V arg_{i}' for i in range(len(params)))+')'
            protos.append(sig+';')
            self.local={};self.ret=self.machine._type(f.decl.type.type);init='tick(c);'
            for i,param in enumerate(params):
                typ=self.machine._type(param.type);self.local[param.name]=typ
                init+=f'uint32_t l_{param.name}=(uint32_t)cv((uint64_t)arg_{i}.n,{typ[0]},{int(typ[1])}).n;'
            body=self.stmt(f.body)
            bodies.append(sig+'{'+init+body+f'return cv(0,{self.ret[0]},{int(self.ret[1])});'+'}')
        regions={region['id']:region for region in program.get('regions',[])}
        if 0 not in regions:raise ValueError('Native backend requires caller ROM as immutable region0')
        r=regions[0];digest=','.join('0x'+r['sha256'][i:i+2] for i in range(0,64,2))
        extra='\n'.join(f'static const unsigned char region_{identifier}[]={{'+','.join(str(x) for x in raw)+'};' for identifier,raw in sorted(self.immutable_regions.items()))
        bind=''.join(f'c->regions[{identifier}]=region_{identifier};c->region_lengths[{identifier}]={len(raw)}U;' for identifier,raw in sorted(self.immutable_regions.items()))
        fail=f'if(c->s.g_{self.unsupported_status}==2U){{c->s=backup;c->error="unsupported model state";return 1;}}' if self.unsupported_status is not None else ''
        api=f'''
static void seed(fdisbull_context*c){{memset(&c->s,0,sizeof(c->s));{''.join(seed)}}}
int fdisbull_create(const char*path,fdisbull_context**out){{
 if(!out||!path)return 1;*out=NULL;FILE*f=fopen(path,"rb");if(!f)return 1;
 if(fseek(f,0,SEEK_END)||ftell(f)!={r['length']}L||fseek(f,0,SEEK_SET)){{fclose(f);return 1;}}
 fdisbull_context*c=calloc(1,sizeof(*c));if(!c){{fclose(f);return 2;}}
 c->rom=malloc({r['length']}U);if(!c->rom){{fclose(f);free(c);return 2;}}
 if(fread(c->rom,1,{r['length']}U,f)!={r['length']}U){{fclose(f);free(c->rom);free(c);return 1;}}fclose(f);
 unsigned char hash[CC_SHA256_DIGEST_LENGTH];static const unsigned char wanted[32]={{{digest}}};
 CC_SHA256(c->rom,{r['length']}U,hash);if(memcmp(hash,wanted,32)){{free(c->rom);free(c);return 1;}}
 c->rom_len={r['length']}U;c->regions[0]=c->rom;c->region_lengths[0]=c->rom_len;{bind}seed(c);*out=c;return 0;
}}
void fdisbull_destroy(fdisbull_context*c){{if(c){{free(c->rom);free(c);}}}}
int fdisbull_reset(fdisbull_context*c){{if(!c)return 1;seed(c);c->error=NULL;return 0;}}
int fdisbull_step(fdisbull_context*c,uint8_t pad){{if(!c)return 1;struct state backup=c->s;c->steps=0;c->error=NULL;
 if(setjmp(c->trap)){{c->s=backup;return 2;}}f_{self.entry}(c,cv(pad,32,1));{fail}return 0;}}
int fdisbull_state_get(const fdisbull_context*c,const char*name,uint32_t index,int64_t*out){{if(!c||!name||!out)return 1;{''.join(gets)}return 1;}}
int fdisbull_state_set(fdisbull_context*c,const char*name,uint32_t index,int64_t value){{if(!c||!name)return 1;{''.join(sets)}return 1;}}
const char*fdisbull_error(const fdisbull_context*c){{return c&&c->error?c->error:"";}}
'''
        return '#include <stdint.h>\n'+decl+RUNTIME+extra+'\n'+'\n'.join(protos)+'\n'+'\n'.join(bodies)+api


def build_macos(program, seed, output, *, clang=None,
                entry='shadowrun_arena_frame', unsupported_status=None,
                immutable_regions=None):
    """Build one seed-specific private arm64 Mach-O dylib from validated UIL.

    ``entry`` receives an eight-bit logical input selected by the source adapter.
    A scalar named ``entry + '_status'`` is checked automatically when present;
    an explicit ``unsupported_status`` selects another scalar. Status 2 refuses
    the update and restores the entire context. The legacy Genesis entry and
    generated C ABI remain the defaults.
    Extra immutable regions must be supplied as exact hash-bound bytes. They
    are embedded in the private build, which must not be published with the
    tool source or packages.
    """
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('Native backend requires macOS arm64')
    compiler=Path(clang or shutil.which('clang') or '').resolve()
    if not compiler.is_file():raise ValueError('Clang is unavailable')
    out=_new_private_directory(output);out.mkdir(mode=0o700)
    generator=_Compiler(program,seed,entry=entry,unsupported_status=unsupported_status,
                        immutable_regions=immutable_regions)
    source=generator.generate(program)
    (out/'fdisbull_native.h').write_text(HEADER);(out/'fdisbull_native.c').write_text(source)
    cmd=[str(compiler),'-dynamiclib','-arch','arm64','-std=gnu11','-O2','-Wno-deprecated-declarations','-Wl,-install_name,@rpath/libfdisbull_native.dylib','fdisbull_native.c','-o','libfdisbull_native.dylib']
    result=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=300)
    if result.returncode:raise ValueError('Native clang failed: '+result.stderr[-6000:])
    artifact=(out/'libfdisbull_native.dylib').read_bytes()
    if len(artifact)<32:raise ValueError('Clang output is not a Mach-O dylib')
    magic,cputype,_,filetype=struct.unpack_from('<IIII',artifact)
    if (magic,cputype,filetype)!=(0xfeedfacf,0x0100000c,6):raise ValueError('Clang output is not an arm64 Mach-O dylib')
    with compiler.open('rb') as stream:compiler_sha256=hashlib.file_digest(stream,'sha256').hexdigest()
    version=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,check=True,timeout=10).stdout.splitlines()[0]
    result={'compiler_sha256':compiler_sha256,'compiler_version':version,'macho_cputype':'arm64','macho_filetype':'dylib','format':'fdisbull-macos-native-1','program_sha256':hashlib.sha256(game_il.canonical(program)).hexdigest(),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'header_sha256':hashlib.sha256(HEADER.encode()).hexdigest(),'dylib_sha256':hashlib.sha256(artifact).hexdigest(),'seed_sha256':hashlib.sha256(json.dumps(seed,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'integer_model':'cc65-int16-long32','architecture':'arm64','artifact':'libfdisbull_native.dylib','header':'fdisbull_native.h'}
    result['entry']=generator.entry
    result['unsupported_status']=generator.unsupported_status
    result['logical_input_bits']=8
    result['immutable_regions']=[{**r,'storage':'caller-ROM' if r['id']==0 else 'private-embedded'} for r in program.get('regions',[])]
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');return result
