"""Native macOS arm64 realization of one shared-UIL plan."""

import json
import platform
import shutil
import subprocess
import sys
from copy import deepcopy

import pytest

from fdisbull.udc_layers import (
    build_selection_shell,
    register_contract,
    register_layer,
    select_layers,
)
from fdisbull.udc_macos import OBSERVATION_FORMAT, build_macos_shell

NATIVE = sys.platform == "darwin" and platform.machine() == "arm64"
CLANG = shutil.which("clang")
requires_native = pytest.mark.skipif(
    not (NATIVE and CLANG),
    reason="real arm64 Mach-O execution requires macOS arm64 and clang",
)


def _program():
    return {
        "format": "fdisbull-il-1",
        "role": "uil",
        "variables": {
            "$box": {"type": "i16", "initial": 0},
            "$delta": {"type": "i16", "initial": 3},
        },
        "resources": {},
        "body": [{"id": "add", "op": "add", "var": "$box", "value": {"var": "$delta"}}],
    }


def _plan():
    return {
        "format": "fdisbull-native-shell-1",
        "entry": "main",
        "state": {
            "$box": {"type": "i16", "initial": 5},
            "$delta": {"type": "i16", "initial": 3},
            "$outcome": {"type": "u16", "initial": 0},
        },
        "resources": {
            "ok": {"kind": "text", "text": "OK\n"},
            "bad": {"kind": "text", "text": "REFUSED\n"},
        },
        "functions": {
            "main": {
                "body": [
                    {"op": "call", "binding": "step"},
                    {"op": "notify", "binding": "notice", "value": {"var": "$box"}},
                    {
                        "op": "if",
                        "condition": {"op": "eq", "left": {"var": "$box"}, "right": 8},
                        "then": [{"op": "set", "var": "$outcome", "value": 1}],
                        "else": [],
                    },
                    {"op": "return", "value": {"var": "$outcome"}},
                ]
            }
        },
    }


def _modules():
    return {
        "step": {
            "backend": "uil",
            "program": _program(),
            "state_adapter": {"inputs": ["$box", "$delta"], "outputs": ["$box"]},
        },
        "notice": {
            "backend": "macos-stdout",
            "title": "t",
            "messages": {"8": "ok"},
            "default": "bad",
        },
    }


ADAPTER = {"notice": {"backend": "macos-stdout", "acknowledgment": "none"}}


@requires_native
def test_plan_compiles_to_real_arm64_and_executes(tmp_path):
    build = build_macos_shell(
        _plan(),
        _modules(),
        tmp_path / "out",
        service_adapters=ADAPTER,
        c_compiler=CLANG,
    )
    assert build["target"]["arch"] == "arm64"
    assert build["qualification"]["native_execution"] is False
    assert build["function_symbols"]["main"] is not None
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        "capsule.json",
        "program",
    ]
    done = subprocess.run(
        [str(tmp_path / "out/program")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0
    lines = done.stdout.strip().splitlines()
    assert lines[0] == "OK"
    frame = json.loads(lines[1])
    assert frame["format"] == OBSERVATION_FORMAT
    assert frame["status"] == 0 and frame["value"] == 1
    assert frame["state"] == {"$box": 8, "$delta": 3, "$outcome": 1}


@requires_native
def test_selected_shell_macos_target_runs_and_pins_capsules(tmp_path):
    source = tmp_path / "authored.bin"
    source.write_bytes(b"\xc3" + bytes(31))
    primitive = _program()
    contract = {
        "format": "fdisbull-block-contract-1",
        "name": "macos.box.step",
        "inputs": {"box": "i16", "delta": "i16"},
        "outputs": {"box": "i16"},
        "behavior": {"kind": "uil", "program": deepcopy(primitive)},
        "domain": {},
    }
    from fdisbull.project import Project

    with Project.create(
        tmp_path / "authored.fdb", source, arch="x86", bits=16, base=0x1000
    ) as project:
        contract_record = register_contract(project, contract)
        layer = register_layer(
            project,
            {
                "format": "fdisbull-udl-layer-1",
                "name": "macos-step",
                "contract": contract_record["id"],
                "implementation": {"backend": "uil", "program": deepcopy(primitive)},
            },
        )
        module = {
            "format": "fdisbull-module-uil-1",
            "role": "uil",
            "variables": deepcopy(primitive["variables"]),
            "resources": {},
            "body": [
                {
                    "id": "invoke",
                    "op": "invoke",
                    "binding": "step",
                    "contract": contract_record["id"],
                    "inputs": {"box": {"var": "$box"}, "delta": {"var": "$delta"}},
                    "outputs": {"box": "$box"},
                }
            ],
        }
        selection = select_layers(
            project,
            "macos-plan",
            {"step": layer["id"]},
            program=module,
            target="macos-arm64",
        )
        plan = _plan()
        # The selection carries only the arithmetic module, so this plan has no
        # notification binding; observation is state-only.
        plan["functions"]["main"]["body"] = [
            {"op": "call", "binding": "step"},
            {"op": "return", "value": {"var": "$box"}},
        ]
        build = build_selection_shell(
            project,
            selection["id"],
            plan,
            tmp_path / "native",
            target="macos-arm64",
        )
    assert build["selection"] == selection["id"]
    assert build["native_build_qualification"]["native_execution"] is False
    done = subprocess.run(
        [str(tmp_path / "native/program")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0
    frame = json.loads(done.stdout.strip().splitlines()[0])
    assert frame["state"]["$box"] == 8 and frame["status"] == 0 and frame["value"] == 8
    capsule = json.loads((tmp_path / "native/selection-capsule.json").read_text())
    assert capsule["selection"] == selection["id"]


def test_macos_shell_refuses_missing_adapter_and_reused_destination(tmp_path):
    plan, modules = _plan(), _modules()
    with pytest.raises(ValueError, match="adapter"):
        build_macos_shell(plan, modules, tmp_path / "no-adapter")
    assert not (tmp_path / "no-adapter").exists()
    modules["step"].pop("state_adapter")
    with pytest.raises(ValueError, match="state_adapter"):
        build_macos_shell(
            plan, modules, tmp_path / "no-adapter-step", service_adapters=ADAPTER
        )
    modules = _modules()
    destination = tmp_path / "kept"
    destination.mkdir()
    (destination / "keep").write_text("x")
    with pytest.raises(ValueError, match="new"):
        build_macos_shell(plan, modules, destination, service_adapters=ADAPTER)
    assert (destination / "keep").read_text() == "x"
