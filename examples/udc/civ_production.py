"""Bounded city shield accumulation and completion from civd 474.05.

Provenance (civd main, 474.05; its CIV.EXE is the same 305,030-byte file as
the pinned DOS target):

* ``CITYMGT.C`` adds this turn's shields to ``shield_box`` (line 639).
* A unit completes when ``cost * cost_scale <= shield_box``; the cost is
  subtracted and the human path clears the box (lines 642-645, 714).
* An improvement completes on the same comparison; the human path subtracts
  and clears (lines 728-752, 768).
* ``cost_scale`` is 10 for the human (line 280). This module takes the already
  multiplied ``needed`` as an input; it does not duplicate that adapter.
* ``book/src/city/production.md``, "Shields and completion", describes the
  unit-excess and human-clear split.

The module is deliberately bounded to 0..32767 for ``shield_box``,
``shields`` and ``needed``. In that range the sign bit of the wrapped
subtraction is the ordinary less-than comparison. The contract has no
admission guard, so callers must enforce that range; tests exercise it.
"""

import ctypes
import hashlib
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from fdisbull.interaction_il import execute_il
from fdisbull.udc_c import generate_c
from fdisbull.udc_layers import (
    build_selection_shell,
    register_contract,
    register_layer,
    run_selection,
    select_layers,
)
from fdisbull.udc_qualify import qualify_uil

NAME = "civ.city.shield-completion"
MAX_BOUNDED = 32767


def _eq(name, value):
    return {"op": "eq", "left": {"var": "$" + name}, "right": value}


def _bit(name, bit):
    return {"op": "bit_test", "value": {"var": "$" + name}, "bit": bit}


def _set(name, value):
    return {"op": "set", "var": "$" + name, "value": value}


def _add(name, value):
    return {"op": "add", "var": "$" + name, "value": value}


def _subtract(name, value):
    return {"op": "subtract", "var": "$" + name, "value": value}


def _if(condition, then, otherwise=None):
    return {"op": "if", "condition": condition, "then": then, "else": otherwise or []}


def _program(body):
    counter = 0

    def identify(blocks):
        nonlocal counter
        result = []
        for block in blocks:
            counter += 1
            block = dict(block, id="civ_shield_" + str(counter))
            if block["op"] == "if":
                block["then"] = identify(block["then"])
                block["else"] = identify(block["else"])
            result.append(block)
        return result

    return {
        "format": "fdisbull-il-1",
        "role": "uil",
        "variables": {
            "$shield_box": {"type": "u16", "initial": 0},
            "$shields": {"type": "u16", "initial": 0},
            "$needed": {"type": "u16", "initial": 0},
            "$clear": {"type": "u8", "initial": 0},
            "$new_box": {"type": "u16", "initial": 0},
            "$complete": {"type": "u8", "initial": 0},
            "$diff": {"type": "u16", "initial": 0},
        },
        "resources": {},
        "body": identify(body),
    }


def program():
    """Return the bounded shield accumulation/completion program."""
    return _program(
        [
            _set("new_box", {"var": "$shield_box"}),
            _add("new_box", {"var": "$shields"}),
            _set("diff", {"var": "$new_box"}),
            _subtract("diff", {"var": "$needed"}),
            _if(
                _bit("diff", 15),
                [_set("complete", 0)],
                [
                    _set("complete", 1),
                    _if(
                        _eq("clear", 1),
                        [_set("new_box", 0)],
                        [_set("new_box", {"var": "$diff"})],
                    ),
                ],
            ),
        ]
    )


def contract():
    """Return the fixed typed contract for one city shield update."""
    return {
        "format": "fdisbull-block-contract-1",
        "name": NAME,
        "inputs": {
            "shield_box": "u16",
            "shields": "u16",
            "needed": "u16",
            "clear": "u8",
        },
        "outputs": {"new_box": "u16", "complete": "u8"},
        "behavior": {"kind": "uil", "program": program()},
        "domain": {},
    }


def layer_document(contract_id, *, backend="c-uil"):
    return {
        "format": "fdisbull-udl-layer-1",
        "name": NAME + "." + backend,
        "contract": contract_id,
        "implementation": {"backend": backend, "program": program()},
    }


def module():
    """Return the generated-C module descriptor for the fixed contract."""
    return {
        "backend": "c-uil",
        "program": program(),
        "state_adapter": {
            "inputs": ["$shield_box", "$shields", "$needed", "$clear"],
            "outputs": ["$new_box", "$complete"],
        },
    }


def register(project):
    """Persist the contract and semantic/native layers."""
    registered_contract = register_contract(project, contract())
    semantic_layer = register_layer(
        project, layer_document(registered_contract["id"], backend="uil")
    )
    native_layer = register_layer(
        project, layer_document(registered_contract["id"], backend="c-uil")
    )
    return {
        "contract": registered_contract["id"],
        "uil_layer": semantic_layer["id"],
        "layer": native_layer["id"],
    }


def select(project, registration, *, backend="c-uil", target=None):
    """Pin either the shared-IL or generated-C layer under ``shield``."""
    layer_key = "uil_layer" if backend == "uil" else "layer"
    if backend not in ("uil", "c-uil"):
        raise ValueError("unsupported Civ production backend")
    return select_layers(
        project, NAME, {"shield": registration[layer_key]}, target=target
    )


def replay_selection(project, selection, inputs):
    """Run the persisted semantic UIL layer for one typed input vector."""
    return run_selection(project, selection, "shield", inputs)


def model(inputs):
    """Evaluate the shared-IL program directly."""
    state = {
        name: declaration["initial"]
        for name, declaration in program()["variables"].items()
    }
    for name in ("shield_box", "shields", "needed", "clear"):
        state["$" + name] = inputs[name]
    result = execute_il(program(), state=state)
    if result.get("status") != "complete":
        raise ValueError(result.get("error", result.get("status")))
    return {
        "outputs": {
            "new_box": result["state"]["$new_box"],
            "complete": result["state"]["$complete"],
        },
        "steps": result["visited"],
    }


def oracle(inputs):
    """The civd 474.05 arithmetic for the admitted bounded domain."""
    shield_box, shields, needed, clear = (
        inputs["shield_box"],
        inputs["shields"],
        inputs["needed"],
        inputs["clear"],
    )
    if any(type(v) is not int for v in (shield_box, shields, needed, clear)):
        raise ValueError("all inputs must be integers")
    if not all(0 <= v <= MAX_BOUNDED for v in (shield_box, shields, needed)):
        raise ValueError(f"bounded inputs must be 0..{MAX_BOUNDED}")
    if clear not in (0, 1):
        raise ValueError("clear must be 0 or 1")
    new_box = (shield_box + shields) & 0xFFFF
    diff = (new_box - needed) & 0xFFFF
    if diff & 0x8000:
        return {"new_box": new_box, "complete": 0}
    if clear:
        return {"new_box": 0, "complete": 1}
    return {"new_box": diff, "complete": 1}


def _compiler(path):
    if not path:
        raise ValueError("explicit clang executable required")
    compiler = Path(path).expanduser()
    if not compiler.is_file():
        found = shutil.which(path)
        if not found:
            raise ValueError("clang executable not found")
        compiler = Path(found)
    return compiler.resolve()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def compile_host(compiler):
    """Generate C, compile a host shared library, and return a caller."""
    compiler = _compiler(compiler)
    source, inputs, outputs = generate_c(module())
    root = Path(tempfile.mkdtemp(prefix="fdisbull-civ-production-"))
    source_path = root / "module.c"
    source_path.write_text(source)
    library = root / ("module.dylib" if platform.system() == "Darwin" else "module.so")
    subprocess.run(
        [
            str(compiler),
            "-std=c11",
            "-O2",
            "-shared",
            "-fPIC",
            "-o",
            str(library),
            str(source_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lib = ctypes.CDLL(str(library))
    function = lib.udc_block
    function.argtypes = [
        ctypes.POINTER(ctypes.c_ushort),
        ctypes.POINTER(ctypes.c_ushort),
    ]
    function.restype = ctypes.c_ulonglong
    return {
        "function": function,
        "inputs": inputs,
        "outputs": outputs,
        "source": source,
        "source_sha256": _sha(source.encode()),
        "library_sha256": _sha(library.read_bytes()),
        "library": str(library),
        "compiler": str(compiler),
    }


def run_host(compiled, inputs):
    """Invoke the compiled C block and decode its word ports."""
    values = [inputs[name.lstrip("$")] for name in compiled["inputs"]]
    in_array = (ctypes.c_ushort * len(values))(*values)
    out_array = (ctypes.c_ushort * len(compiled["outputs"]))()
    result = int(compiled["function"](in_array, out_array))
    status = result >> 32
    outputs = {
        name.lstrip("$"): out_array[index]
        for index, name in enumerate(compiled["outputs"])
    }
    if status != 0:
        raise ValueError(f"generated C refused with status {status}")
    expected = model(inputs)["outputs"]
    if outputs != expected:
        raise ValueError(
            f"generated C differs from the shared-IL model: {outputs!r} != {expected!r}"
        )
    return {
        "outputs": outputs,
        "status": status,
        "source_sha256": compiled["source_sha256"],
        "library_sha256": compiled["library_sha256"],
    }


def replay_host(compiler, inputs):
    """Compile once and execute one vector on the host."""
    return run_host(compile_host(compiler), inputs)


def native_plan(inputs):
    """Return the selected-shell plan for the fixed module."""
    return {
        "format": "fdisbull-native-shell-1",
        "entry": "main",
        "state": {
            "$shield_box": {"type": "u16", "initial": inputs["shield_box"]},
            "$shields": {"type": "u16", "initial": inputs["shields"]},
            "$needed": {"type": "u16", "initial": inputs["needed"]},
            "$clear": {"type": "u8", "initial": inputs["clear"]},
            "$new_box": {"type": "u16", "initial": 0},
            "$complete": {"type": "u8", "initial": 0},
        },
        "resources": {},
        "functions": {
            "main": {
                "body": [{"op": "call", "binding": "shield"}],
                "return": {"var": "$new_box"},
            }
        },
    }


def build_native(
    project, selection, destination, compiler, *, target="linux-x64", inputs=None
):
    """Build a fresh PE/ELF shell from the selected C-UIL layer."""
    if inputs is None:
        raise ValueError("build_native requires the concrete input vector")
    return build_selection_shell(
        project,
        selection,
        native_plan(inputs),
        destination,
        target=target,
        capture_state=target == "linux-x64",
        c_compiler=compiler,
    )


def qualification():
    """Qualify the authored implementation against the fixed contract."""
    return qualify_uil(
        contract(), {"backend": "uil", "program": program()}, timeout_ms=5000
    )
