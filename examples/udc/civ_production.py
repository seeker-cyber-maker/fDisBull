"""Signed city shield completion from civd 474.05.

Authority:

* ``CIV.H`` declares ``shield_box`` as a signed DOS ``int`` (the recovered
  16-bit storage field).
* ``CITYMGT.C`` resets ``shield_box`` to zero when it is negative or greater
  than 999 before adding this turn's shield balance (lines 227-229, 639).
* Unit and improvement completion compare the resulting signed box with the
  positive cost threshold and then subtract or clear it (lines 642-645,
  714, 728-752, 768).

The UIL implementation and the independent Python oracle both model signed
16-bit storage. The source-shaped reference UIL is intentionally separate
from the implementation UIL. The admitted limits are explicit in
``INPUT_LIMITS`` and are also enforced by IL ``require`` guards and every
public module entry point. The release gate requires shared-UIL qualification
and an independent oracle comparison; a native artifact is not emitted when
either check fails.
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
I16_MIN = -(1 << 15)
I16_MAX = (1 << 15) - 1
SHIELD_RESET_MAX = 999


def _input_limits():
    return {
        "shield_box": {"min": I16_MIN, "max": I16_MAX},
        "shields": {"min": I16_MIN, "max": I16_MAX},
        "needed": {"min": 0, "max": I16_MAX},
        "clear": {"min": 0, "max": 1},
    }


def _eq(name, value):
    return {"op": "eq", "left": {"var": "$" + name}, "right": value}


def _bit(name, bit):
    return {"op": "bit_test", "value": {"var": "$" + name}, "bit": bit}


def _not(condition):
    return {"op": "not", "condition": condition}


def _and(*conditions):
    return {"op": "and", "conditions": list(conditions)}


def _require(condition):
    return {"op": "require", "condition": condition}


def _set(name, value):
    return {"op": "set", "var": "$" + name, "value": value}


def _add(name, value):
    return {"op": "add", "var": "$" + name, "value": value}


def _subtract(name, value):
    return {"op": "subtract", "var": "$" + name, "value": value}


def _if(condition, then, otherwise=None):
    return {"op": "if", "condition": condition, "then": then, "else": otherwise or []}


def _variables(*, include_stored=False):
    variables = {
        "$shield_box": {"type": "i16", "initial": 0},
        "$shields": {"type": "i16", "initial": 0},
        "$needed": {"type": "i16", "initial": 0},
        "$clear": {"type": "u8", "initial": 0},
        "$new_box": {"type": "i16", "initial": 0},
        "$complete": {"type": "u8", "initial": 0},
        "$diff": {"type": "i16", "initial": 0},
    }
    if include_stored:
        variables["$stored"] = {"type": "i16", "initial": 0}
    return variables


def _program(body, *, include_stored=False):
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
        "variables": _variables(include_stored=include_stored),
        "resources": {},
        "body": identify(body),
    }


def program():
    """Return the implementation UIL program."""
    return _program(
        [
            _require(_not(_bit("needed", 15))),
            _require(
                _not(
                    _and(
                        _not(_eq("clear", 0)),
                        _not(_eq("clear", 1)),
                    )
                )
            ),
            _set("new_box", {"var": "$shield_box"}),
            _if(
                _bit("new_box", 15),
                [_set("new_box", 0)],
                [
                    _set("diff", {"var": "$new_box"}),
                    _subtract("diff", 1000),
                    _if(
                        _bit("diff", 15),
                        [],
                        [_set("new_box", 0)],
                    ),
                ],
            ),
            _add("new_box", {"var": "$shields"}),
            _if(
                _bit("new_box", 15),
                [_set("complete", 0)],
                [
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
                ],
            ),
        ]
    )


def reference_program():
    """Return a source-shaped reference UIL program for qualification."""
    return _program(
        [
            _require(_not(_bit("needed", 15))),
            _require(
                _not(
                    _and(
                        _not(_eq("clear", 0)),
                        _not(_eq("clear", 1)),
                    )
                )
            ),
            _set("stored", {"var": "$shield_box"}),
            _if(
                _bit("stored", 15),
                [_set("stored", 0)],
                [
                    _set("diff", {"var": "$stored"}),
                    _subtract("diff", 1000),
                    _if(
                        _bit("diff", 15),
                        [],
                        [_set("stored", 0)],
                    ),
                ],
            ),
            _set("new_box", {"var": "$stored"}),
            _add("new_box", {"var": "$shields"}),
            _if(
                _bit("new_box", 15),
                [_set("complete", 0)],
                [
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
                ],
            ),
        ],
        include_stored=True,
    )


def contract():
    """Return the signed, reset-aware city shield contract."""
    return {
        "format": "fdisbull-block-contract-1",
        "name": NAME,
        "inputs": {
            "shield_box": "i16",
            "shields": "i16",
            "needed": "i16",
            "clear": "u8",
        },
        "outputs": {"new_box": "i16", "complete": "u8"},
        "behavior": {"kind": "uil", "program": reference_program()},
        # The generic native-shell profile currently cannot carry a separate
        # domain object. The typed IL guards and module API enforce these
        # exact limits before release/native emission.
        "domain": {},
        "evidence": {
            "authority": "civd-474.05-CITYMGT.C",
            "input_limits": _input_limits(),
            "storage": "signed-int16",
            "preproduction_reset": "shield_box < 0 or shield_box > 999 => 0",
            "release_gate": "shared UIL qualification plus independent oracle",
        },
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
    _validate_inputs(inputs)
    return run_selection(project, selection, "shield", inputs)


def _validate_inputs(inputs):
    if type(inputs) is not dict or set(inputs) != set(_input_limits()):
        raise ValueError("Civ production inputs must match the fixed ports")
    for name, bound in _input_limits().items():
        value = inputs[name]
        if type(value) is not int or not bound["min"] <= value <= bound["max"]:
            raise ValueError(
                f"{name} must be an integer in {bound['min']}..{bound['max']}"
            )


def model(inputs):
    """Evaluate the implementation UIL program."""
    _validate_inputs(inputs)
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


def _wrap_i16(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def oracle(inputs):
    """Independent civd arithmetic using signed storage and direct comparison."""
    _validate_inputs(inputs)
    shield_box, shields, needed, clear = (
        inputs["shield_box"],
        inputs["shields"],
        inputs["needed"],
        inputs["clear"],
    )
    if shield_box < 0 or shield_box > SHIELD_RESET_MAX:
        shield_box = 0
    new_box = _wrap_i16(shield_box + shields)
    if needed > new_box:
        return {"new_box": new_box, "complete": 0}
    if clear == 1:
        return {"new_box": 0, "complete": 1}
    return {
        "new_box": _wrap_i16(new_box - needed),
        "complete": 1,
    }


def oracle_vectors():
    """Return deterministic edge and wrap vectors for oracle comparison."""
    signed_edges = (I16_MIN, -1000, -1, 0, 1, SHIELD_RESET_MAX, 1000, I16_MAX)
    needed_edges = (0, 1, SHIELD_RESET_MAX, 1000, I16_MAX)
    result = []
    for shield_box in signed_edges:
        for shields in signed_edges:
            for needed in needed_edges:
                for clear in (0, 1):
                    result.append(
                        {
                            "shield_box": shield_box,
                            "shields": shields,
                            "needed": needed,
                            "clear": clear,
                        }
                    )
    for index in range(256):
        result.append(
            {
                "shield_box": _wrap_i16(index * 7919 + 17),
                "shields": _wrap_i16(index * 6151 - 31),
                "needed": (index * 1543) % (I16_MAX + 1),
                "clear": index & 1,
            }
        )
    return result


def compare_oracle():
    """Compare the implementation UIL against the independent source oracle."""
    mismatches = []
    vectors = oracle_vectors()
    for inputs in vectors:
        observed = model(inputs)["outputs"]
        expected = oracle(inputs)
        if observed != expected:
            mismatches.append(
                {"inputs": inputs, "implementation": observed, "oracle": expected}
            )
            if len(mismatches) == 8:
                break
    return {
        "status": "matched_independent_oracle" if not mismatches else "counterexample",
        "vector_count": len(vectors),
        "mismatches": mismatches,
        "input_limits": _input_limits(),
        "authority": "civd-474.05-CITYMGT.C",
    }


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
    """Invoke the compiled C block and decode its typed word ports."""
    _validate_inputs(inputs)
    values = [inputs[name.lstrip("$")] for name in compiled["inputs"]]
    in_array = (ctypes.c_ushort * len(values))(*values)
    out_array = (ctypes.c_ushort * len(compiled["outputs"]))()
    result = int(compiled["function"](in_array, out_array))
    status = result >> 32
    declarations = module()["program"]["variables"]
    outputs = {}
    for index, name in enumerate(compiled["outputs"]):
        value = int(out_array[index])
        typ = declarations[name]["type"]
        if typ.startswith("i") and value >= 1 << (int(typ[1:]) - 1):
            value -= 1 << int(typ[1:])
        outputs[name.lstrip("$")] = value
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
    _validate_inputs(inputs)
    return {
        "format": "fdisbull-native-shell-1",
        "entry": "main",
        "state": {
            "$shield_box": {"type": "i16", "initial": inputs["shield_box"]},
            "$shields": {"type": "i16", "initial": inputs["shields"]},
            "$needed": {"type": "i16", "initial": inputs["needed"]},
            "$clear": {"type": "u8", "initial": inputs["clear"]},
            "$new_box": {"type": "i16", "initial": 0},
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
    """Build a fresh PE/ELF shell only after the release gate passes."""
    if inputs is None:
        raise ValueError("build_native requires the concrete input vector")
    gate = release_gate()
    if not gate["eligible"]:
        raise ValueError("Civ production release gate blocked native emission")
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
    """Qualify shared UIL, then require independent-oracle agreement."""
    shared = qualify_uil(
        contract(), {"backend": "uil", "program": program()}, timeout_ms=5000
    )
    independent = compare_oracle()
    release_ready = (
        shared["status"] == "equivalent_under_contract"
        and independent["status"] == "matched_independent_oracle"
    )
    return {
        **shared,
        "independent_oracle": independent,
        "release_ready": release_ready,
        "release_reason": (
            "shared UIL and independent oracle agree"
            if release_ready
            else "shared UIL and independent oracle must both agree"
        ),
        "input_limits": _input_limits(),
    }


def release_gate():
    """Return the explicit gate used before native artifact emission."""
    result = qualification()
    return {
        "status": "eligible" if result["release_ready"] else "blocked",
        "eligible": result["release_ready"],
        "qualification": result,
    }
