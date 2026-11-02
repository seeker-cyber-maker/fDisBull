"""Authored stock fixtures test signed-byte admission and real ARM64 output."""
import copy
import json
import platform
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull.project import Project
from fdisbull.stock_flow import maintenance_contract, maintenance_module
from fdisbull.udc_layers import register_contract, register_layer, select_layers, digest
from fdisbull.udc_macos_probe import build_macos_block_probe

NATIVE = sys.platform == "darwin" and platform.machine() == "arm64" and shutil.which("clang")


def selection(project, mutate=None, domain=None):
    contract = maintenance_contract()
    stored = register_contract(project, contract)
    program = copy.deepcopy(contract["behavior"]["program"])
    if mutate:
        mutate(program)
    layer = {"format": "fdisbull-udl-layer-1", "name": "stock.c",
             "contract": stored["id"],
             "implementation": {"backend": "c-uil", "program": program}}
    if domain:
        layer["domain"] = domain
    retained = register_layer(project, layer)
    module = maintenance_module(stored["id"])
    return select_layers(project, "stock-arm64", {"food": retained["id"]},
                         program=module)["id"], module


def project_at(tmp_path):
    source = tmp_path/"authored.com"; source.write_bytes(bytes.fromhex("b8004ccd21"))
    return Project.create(tmp_path/"authored.fdb", source, image="com")


def test_wrong_rule_is_refused_before_native_emission(tmp_path):
    with project_at(tmp_path) as project:
        choice, _ = selection(project, lambda p: p["body"].append(
            {"id": "wrong", "op": "set", "var": "$new_stock", "value": 0}))
        with pytest.raises(ValueError, match="qualification"):
            build_macos_block_probe(project, choice, tmp_path/"bad")
    assert not (tmp_path/"bad").exists()


@pytest.mark.skipif(not NATIVE, reason="requires real macOS ARM64 and clang")
def test_native_signed_population_overflow_guards_and_persisted_uil(tmp_path):
    with project_at(tmp_path) as project:
        choice, module = selection(project)
        before = digest(module)
        built = build_macos_block_probe(project, choice, tmp_path/"native")
        assert built["module_uil_sha256"] == before
        assert built["native_execution"] is False
    with Project(tmp_path/"authored.fdb") as project:
        assert digest(project.udl_selection_info(choice, full=True)["document"]["program"]) == before
    # Independent authored expected values, including signed-byte widening and wrap.
    valid = [
        ({"stock": 10, "produced": 9, "population": 3, "supported": 2, "support_cost": 1}, 11),
        ({"stock": 10, "produced": 9, "population": 3, "supported": 2, "support_cost": 2}, 9),
        ({"stock": 32767, "produced": 32767, "population": -128, "supported": -32768, "support_cost": 2}, 254),
        ({"stock": -32768, "produced": -32768, "population": 127, "supported": 32767, "support_cost": 1}, 32515)]
    invalid = [{**valid[0][0], "population": n} for n in (-129, 128)]
    invalid += [{**valid[0][0], "support_cost": n} for n in (0, 3)]
    vectors = [v for v, _ in valid] + invalid
    wire = b"".join(struct.pack("<5H", *(v[k]&65535 for k in built["inputs"])) for v in vectors)
    done = subprocess.run([str(tmp_path/"native/program")], input=wire, capture_output=True, check=True)
    frames = [json.loads(s) for s in done.stdout.splitlines()]
    assert [f["index"] for f in frames] == list(range(8))
    assert [f["outputs"]["new_stock"] for f in frames[:4]] == [n for _, n in valid]
    assert all(f["status"] == "refused" and f["outputs"] == {} for f in frames[4:])
    truncated = subprocess.run([str(tmp_path/"native/program")], input=wire[:3], capture_output=True)
    assert truncated.returncode == 2 and not truncated.stdout


@pytest.mark.skipif(not NATIVE, reason="requires real macOS ARM64 and clang")
def test_native_guard_keeps_additional_layer_domain(tmp_path):
    with project_at(tmp_path) as project:
        choice, _ = selection(project, domain={"support_cost": {"min": 2, "max": 2}})
        built = build_macos_block_probe(project, choice, tmp_path/"narrow")
    vectors = [dict(stock=10, produced=9, population=3, supported=2, support_cost=n) for n in (1, 2)]
    wire = b"".join(struct.pack("<5H", *(v[k]&65535 for k in built["inputs"])) for v in vectors)
    done = subprocess.run([str(tmp_path/"narrow/program")], input=wire, capture_output=True, check=True)
    frames = [json.loads(s) for s in done.stdout.splitlines()]
    assert frames[0]["status"] == "refused" and frames[0]["outputs"] == {}
    assert frames[1]["outputs"] == {"new_stock": 9}
