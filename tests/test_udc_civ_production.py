import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from examples.udc import civ_production as civ
from fdisbull.project import Project


def project_at(tmp_path):
    source = tmp_path / "authored-source.bin"
    source.write_bytes(b"\xc3" + bytes(31))
    return Project.create(
        tmp_path / "civ-production.fdb", source, arch="x86", bits=16, base=0x1000
    )


def vectors():
    result = [
        {"shield_box": 0, "shields": 0, "needed": 0, "clear": 0},
        {"shield_box": 0, "shields": 0, "needed": 0, "clear": 1},
        {"shield_box": 5, "shields": 10, "needed": 10, "clear": 0},
        {"shield_box": 5, "shields": 10, "needed": 10, "clear": 1},
        {"shield_box": 100, "shields": 50, "needed": 150, "clear": 0},
        {"shield_box": 100, "shields": 50, "needed": 150, "clear": 1},
        {"shield_box": 100, "shields": 0, "needed": 99, "clear": 0},
        {"shield_box": 100, "shields": 0, "needed": 100, "clear": 1},
        {"shield_box": 32767, "shields": 0, "needed": 32767, "clear": 0},
        {"shield_box": 0, "shields": 32767, "needed": 32767, "clear": 1},
    ]
    rng = random.Random(0xC1D)
    for _ in range(250):
        result.append(
            {
                "shield_box": rng.randrange(civ.MAX_BOUNDED + 1),
                "shields": rng.randrange(civ.MAX_BOUNDED + 1),
                "needed": rng.randrange(civ.MAX_BOUNDED + 1),
                "clear": rng.randrange(2),
            }
        )
    return result


def test_shared_uil_matches_civd_arithmetic():
    for inputs in vectors():
        assert civ.model(inputs)["outputs"] == civ.oracle(inputs)


def test_persisted_uil_layer_matches_civd_arithmetic(tmp_path):
    with project_at(tmp_path) as project:
        registration = civ.register(project)
        selection = civ.select(project, registration, backend="uil")
        for inputs in vectors()[:30]:
            observed = civ.replay_selection(project, selection["id"], inputs)
            assert observed["outputs"] == civ.oracle(inputs)
            assert observed["comparison"] == "matched_reference_uil"


def test_generated_c_executes_and_matches_shared_uil():
    compiler = shutil.which("clang")
    if compiler is None:
        pytest.skip("clang is required for generated-C execution")
    compiled = civ.compile_host(compiler)
    assert len(compiled["source_sha256"]) == 64
    for inputs in vectors():
        observed = civ.run_host(compiled, inputs)
        assert observed["status"] == 0
        assert observed["outputs"] == civ.oracle(inputs)


def test_uil_qualification_is_contract_equivalent():
    pytest.importorskip("z3")
    result = civ.qualification()
    assert result["status"] == "equivalent_under_contract"
    assert (
        result["programs"]["reference_sha256"]
        == result["programs"]["implementation_sha256"]
    )


def test_uil_export_is_cli_validated_and_deterministic(tmp_path):
    encoded = json.dumps(
        civ.program(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    assert (
        hashlib.sha256(encoded).hexdigest()
        == hashlib.sha256(
            json.dumps(
                civ.program(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    program = tmp_path / "civ-production-uil.json"
    program.write_bytes(encoded)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "fdisbull", "il-check", str(program)],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout)["status"] == "valid"


def test_linux_native_shell_is_emitted(tmp_path):
    pytest.importorskip("z3")
    compiler = shutil.which("clang")
    if compiler is None:
        pytest.skip("clang is required for native shell emission")
    with project_at(tmp_path) as project:
        registration = civ.register(project)
        selection = civ.select(project, registration, target="linux-x64")
        result = civ.build_native(
            project,
            selection["id"],
            tmp_path / "native",
            compiler,
            inputs={"shield_box": 5, "shields": 10, "needed": 10, "clear": 0},
        )
        output = Path(result["directory"]) / result["output"]["path"]
        assert output.read_bytes()[:4] == b"\x7fELF"
        assert Path(result["selection_capsule"]).is_file()
        assert result["native_build_qualification"]["native_execution"] is False
