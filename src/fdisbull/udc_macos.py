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
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .udc_c import generate_c
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
