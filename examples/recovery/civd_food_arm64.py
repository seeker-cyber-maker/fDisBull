"""Run the fixed food UIL on ARM64 against original CPU/DOSBox observations.

All retained game bytes, databases and native outputs stay in private paths.
Arguments: prior food-swap result directory, verified-build root, new output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import subprocess

from fdisbull.project import Project
from fdisbull.interaction_il import execute_il
from fdisbull.stock_flow import PORTS, native16_adapter, decode_state, commit_state
from fdisbull.udc_layers import digest, register_layer, select_layers, _native_code
from fdisbull.udc_macos_probe import build_macos_block_probe, FORMAT
from fdisbull.udc_native16 import execute_native16
from examples.recovery.civd_food_swap import host_state, frame_values

UIL = "332f84e5067fa7aee5405a001ac68efb991fd644bcf34cd62a232f453df057ed"
TAGS = ("474.01", "474.03", "474.05")
sha = lambda b: hashlib.sha256(b).hexdigest()


def run(previous, builds, output):
    previous, builds, output = map(lambda p: Path(p).resolve(), (previous, builds, output))
    if output.exists() or any((p/".git").exists() for p in (output, *output.parents)):
        raise ValueError("choose a new private output directory outside Git")
    old = json.loads((previous/"report.json").read_text())
    vectors = json.loads((previous/"vectors.json").read_text())
    if digest(vectors) != old["vectors_sha256"] or digest(old["module_uil"]) != UIL:
        raise ValueError("prior vectors or shared UIL changed")
    originals = {tag: builds/tag.replace(".", "")/"CIV.EXE" for tag in TAGS}
    if any(sha(path.read_bytes()) != old["originals"][tag] for tag, path in originals.items()):
        raise ValueError("original executable identity mismatch")
    output.mkdir(mode=0o700)
    project_path = output/"arm64.fdb"
    with sqlite3.connect(previous/"474.05-swap.fdb") as src, sqlite3.connect(project_path) as dst:
        src.backup(dst)
    with Project(project_path) as project:
        layer = register_layer(project, {"format": "fdisbull-udl-layer-1",
            "name": "food.generated-c.arm64", "contract": old["contract_id"],
            "implementation": {"backend": "c-uil", "program": old["contract"]["behavior"]["program"]}})
        selected = select_layers(project, "fixed-food-arm64", {"food": layer["id"]},
            program=old["module_uil"], target="macos-arm64")
        built = build_macos_block_probe(project, selected["id"], output/"native")
    # Reopen the persisted selection before making the execution claim.
    with Project(project_path) as project:
        assert digest(project.udl_selection_info(selected["id"], full=True)["document"]["program"]) == UIL
    invalid = [{**vectors[0], "support_cost": c} for c in (0, 3)]
    invalid += [{**vectors[0], "population": p} for p in (-129, 128)]
    rows = vectors + invalid
    wire = b"".join(struct.pack("<"+"H"*len(built["inputs"]),
        *(v[n] & 0xffff for n in built["inputs"])) for v in rows)
    executable = output/"native/program"
    assert sha(executable.read_bytes()) == built["output_sha256"]
    process = subprocess.run([str(executable)], input=wire, capture_output=True, timeout=30, check=True)
    (output/"native-observations.jsonl").write_bytes(process.stdout)
    (output/"wire.bin").write_bytes(wire)
    frames = [json.loads(s) for s in process.stdout.splitlines()]
    if len(frames) != len(rows) or any(f["format"] != FORMAT or f["index"] != i for i, f in enumerate(frames)):
        raise ValueError("native observation frame count/order differs")
    if any(f["status"] != "complete" for f in frames[:len(vectors)]):
        raise ValueError("admitted native row refused")
    if any(f["status"] != "refused" or f["outputs"] for f in frames[len(vectors):]):
        raise ValueError("native type/domain guard did not refuse")
    actual = [f["outputs"]["new_stock"] for f in frames[:len(vectors)]]
    for i, vector in enumerate(vectors):
        program = old["contract"]["behavior"]["program"]
        state = {k:v["initial"] for k,v in program["variables"].items()}
        state.update({"$"+k:v for k,v in vector.items()})
        modeled = execute_il(program, state=state)
        if modeled["status"] != "complete" or modeled["state"]["$new_stock"] != actual[i]:
            raise ValueError("UIL-to-ARM64 mismatch")
    results = []
    for index, tag in enumerate(TAGS):
        raw = (previous/f"F{index}.OUT").read_bytes()
        if len(raw) != 2*len(vectors):
            raise ValueError("DOSBox oracle payload length changed")
        dos = list(struct.unpack("<"+"h"*len(vectors), raw))
        original_row = next(r for r in old["matrix"] if r["host"] == tag and r["backing"] == tag)
        if sha(raw) != original_row["results_sha256"]:
            raise ValueError("DOSBox payload no longer matches its retained receipt")
        with sqlite3.connect(previous/(tag+"-swap.fdb")) as src, sqlite3.connect(output/(tag+".fdb")) as dst:
            src.backup(dst)
        with Project(output/(tag+".fdb")) as project:
            choice = next(r for r in old["restart"] if r["host"] == tag)["selection"]
            doc = project.udl_selection_info(choice, full=True)["document"]
            native = project.udl_layer_info(doc["bindings"]["food"], full=True)["document"]
            code = _native_code(project, native)
            if sha(code) != original_row["source_code_sha256"]:
                raise ValueError("retained original code changed")
            for i, v in enumerate(vectors):
                record, frame = frame_values(i)
                adapter = native16_adapter(original_row["adapter"], record=record, frame=frame)
                observed = execute_native16(code, native["implementation"], adapter,
                    v, PORTS, {"new_stock": "i16"})["outputs"]["new_stock"]
                if observed != actual[i] or dos[i] != actual[i]:
                    raise ValueError(f"original/UIL/ARM64 mismatch at {tag}:{i}")
                data, stack, _, _ = host_state(original_row["adapter"], v, i)
                if decode_state(original_row["adapter"], data, stack, record=record, frame=frame) != v:
                    raise ValueError("host input adapter changed")
                updated = commit_state(original_row["adapter"], data, actual[i], record=record)
                offset = adapter["outputs"]["new_stock"]["offset"]
                if updated[:offset] != data[:offset] or updated[offset+2:] != data[offset+2:]:
                    raise ValueError("host output adapter changed unrelated memory")
        results.append({"edition": tag, "cases": len(vectors), "mismatches": 0,
            "original_code_sha256": sha(code), "dosbox_output_sha256": sha(raw),
            "results_sha256": digest(actual), "host_adapter_sha256": digest(original_row["adapter"]),
            "original_cpu_execution": True, "host_roundtrips": len(vectors)})
    unchanged = all(sha(path.read_bytes()) == old["originals"][tag] for tag, path in originals.items())
    if not unchanged or sha(executable.read_bytes()) != built["output_sha256"]:
        raise ValueError("an executable changed during comparison")
    result = {"format": "fdisbull-civd-food-arm64-1", "module_uil_sha256": UIL,
        "contract_id": old["contract_id"], "vectors": len(vectors),
        "vectors_sha256": digest(vectors), "native_build": built,
        "matrix": results, "refusals": invalid, "originals_unchanged": unchanged,
        "originals": old["originals"], "native_output_sha256": sha(process.stdout),
        "native_execution": True, "uil_interpreter_cases": len(vectors),
        "scope": "finite original CPU/DOSBox/ARM64 kernel and host-adapter checks; no whole-game claim"}
    (output/"report.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("previous", "builds", "output"):
        p.add_argument(name)
    a = p.parse_args()
    r = run(a.previous, a.builds, a.output)
    print(json.dumps({"editions": len(r["matrix"]), "vectors": r["vectors"],
                      "mismatches": sum(row["mismatches"] for row in r["matrix"])}))
