"""Paired stopped code inspection, execution and offline analysis of an authored COM."""
import hashlib

import pytest

from fdisbull.project import Project
from test_qemu_dosbox_parity_native import _launch_qemu, _word, parity_inputs


# MOV AX,1234h; MOV BX,[0101h] (read that immediate as ordinary data); JMP $.
PROGRAM = bytes.fromhex("b834128b1e0101ebfe")


def _capture_views(project, directory, runtime, backend):
    qemu = backend == "qemu-dos"
    source_address = project.regions(1)[0].start
    source_space = {"space": "source"} if qemu else {}
    session = (_launch_qemu(project, runtime, directory) if qemu else
               project.debugger(str(runtime["dosbox"]), directory))
    with session as debug:
        assert debug.contexts()["selected"] == ("machine" if qemu else "dos-cpu")
        layer = debug.layer_patch("Execute overlay", hex(source_address + 1),
                                  expected_hex="3412", data_hex="efbe", kind="execute", **source_space)
        ids = {}
        for view, expected in (("ram", "b83412"), ("execute", "b8efbe")):
            observed = debug.code(hex(source_address), length=3, view=view, **source_space)
            assert observed["hex"] == expected
            insn = observed["instructions"][0]
            assert insn["bytes"] == expected
            assert insn["cs"] == observed["runtime_cs"]
            assert int(insn["ip"], 16) == 0x100
            assert int(observed["project_address"], 16) == source_address
            assert observed["active_layers"] == [layer["layer"]]
            capture = debug.capture_code(hex(source_address), length=3, view=view, **source_space)
            ids[view] = capture["artifact"]

        runtime_address = int(observed["runtime_address"], 16)
        debug.breakpoint((runtime_address if qemu else source_address) + 7)
        stopped = debug.run(timeout_ms=10000)
        assert stopped["outcome"] == "breakpoint", stopped
        registers = debug.registers()
        assert _word(registers, "ax", "eax", "rax") == 0xBEEF
        assert _word(registers, "bx", "ebx", "rbx") == 0x1234

        unqualified = []
        if qemu:
            for space in ("physical", "linear"):
                capture = debug.capture_code(runtime_address, length=3, space=space)
                assert capture["metadata"]["static_promotion"] == "unqualified"
                unqualified.append(capture["artifact"])
    return ids, unqualified


def test_paired_native_runtime_code_views_capture_and_promotion(tmp_path, parity_inputs):
    source = tmp_path / "CODEVIEW.COM"
    source.write_bytes(PROGRAM)
    database = tmp_path / "codeview.fdb"
    with Project.create(database, source, image="com") as project:
        project.analyze(max_instructions=32)
        original = project.version()["id"]
        address = project.regions(original)[0].start
        captures = {backend: _capture_views(project, tmp_path, parity_inputs, backend)
                    for backend in ("dosbox", "qemu-dos")}

    with Project(database) as project:
        for backend, (ids, unqualified) in captures.items():
            for artifact in unqualified:
                with pytest.raises(ValueError, match="qualified source mapping"):
                    project.debug_promote_code(artifact)
            for view, artifact in ids.items():
                result = project.debug_promote_code(artifact, max_instructions=32)
                child = result["version"]
                assert result["parent"] == original
                row = project.disassembly(address, version=child, lines=1)["instructions"][0]
                assert row["bytes"] == ("b83412" if view == "ram" else "b8efbe")
                identity = project.runtime_version_info(child)["identity"]
                assert identity["backend"] == backend
                assert identity["source_sha256"] == hashlib.sha256(PROGRAM).hexdigest()
                assert project.debug_promote_code(artifact)["version"] == child
        assert project.disassembly(address, version=original, lines=1)["instructions"][0]["bytes"] == "b83412"
        assert len(project.debug_runs(version=original)["runs"]) == 2
        assert len(project.versions()) == 5
    assert source.read_bytes() == PROGRAM
