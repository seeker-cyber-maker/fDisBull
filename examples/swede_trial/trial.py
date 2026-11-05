"""Fixed local experiment tool: describe -> task -> check -> register -> lookup.

This compiles only deliberately authored trial sources with the supplied scaffold.
It is not a production UDC loader, a compiler plugin, or a hostile-code sandbox.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "udc_registry"))
from registry import Registry, REPRESENTATION
from fixture import BLOCKS, DOMAINS, MODES, cases, catalog, contracts, evaluate, semantic_ids
from fdisbull.common_uil import canonical_bytes, digest
from fdisbull.uil_link import make_module, make_provider, make_requirement

OPS = {"normalize": 0, "award": 1, "apply": 2, "pair": 3, "turn": 4}
TARGET = "linux-x64"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def framework_hashes():
    names = ["fixture.py", "abi.h", "scaffold.c", "trial.py", "README.md"]
    result = {name: sha(HERE / name) for name in names}
    result["../udc_registry/registry.py"] = sha(HERE.parent / "udc_registry" / "registry.py")
    import fdisbull.common_uil, fdisbull.uil_catalog, fdisbull.uil_runtime, fdisbull.uil_link
    for module in (fdisbull.common_uil, fdisbull.uil_catalog, fdisbull.uil_runtime, fdisbull.uil_link):
        result[module.__name__] = sha(Path(module.__file__))
    return result


def compiler():
    path = shutil.which("gcc")
    if path is None or platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("prepare-backend: this trial requires existing gcc on Linux x86_64")
    version = subprocess.run([path, "--version"], text=True, capture_output=True, timeout=10, check=True)
    return {"path": path, "version": version.stdout.splitlines()[0], "target": TARGET}


def state_dir(work):
    work.mkdir(parents=True, exist_ok=True)
    state = work / "trial-results"
    state.mkdir(exist_ok=True)
    return state


def source_hashes(mode, work):
    result = {}
    for name in MODES[mode]["files"]:
        path = work / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 262144:
            raise ValueError("supply bounded authored source: " + name)
        result[name] = sha(path)
    return result


def open_registry(state):
    path = state / "registry.sqlite"
    new = not path.exists()
    db = Registry(path, create=new)
    if new:
        db.import_catalog(catalog())
    return db


def describe(mode):
    return {
        "experiment": "authored collect-coins, bounded C sweding",
        "mode": mode, "target": TARGET, "files_to_author": MODES[mode]["files"],
        "header": str(HERE / "abi.h"), "contracts": contracts(),
        "semantic_ids": semantic_ids(), "domains": DOMAINS,
        "behavior": {
            "normalize": "raw:i16 [-8,8] -> count:u16, clamp raw to 0..3 before unsigned conversion",
            "award": "count:u16 [0,3] -> points:u16, twice count plus one when count is three",
            "apply": "score:u16 [0,10], points:u16 [0,7] -> next_score:u16 capped at ten; won:bool iff next_score equals ten",
            "pair": "raw -> normalize -> award; return count and points",
            "turn": "raw -> normalize -> award; apply(score,points); return count,points,next_score,won",
        },
        "effects": "none; no hidden mutable state, allocation, I/O or host calls in the authored blocks",
        "scope": "declared finite domains only; no out-of-domain behavior or whole-game claim",
        "next_action": "task",
    }


def task(mode, state):
    packets = {}
    with open_registry(state) as db:
        for name in MODES[mode]["blocks"]:
            packets[name] = db.generate_swede_task(
                semantic_ids()[name], TARGET, domain=DOMAINS[name],
                reason="User requests an independently authored C backing for a controlled sweding experiment.",
                candidate_exclusions=[])
    document = {"mode": mode, "description": describe(mode), "registry_tasks": packets,
                "execution_authority": "The user-authorized experiment runner may compile and execute these authored sources; the registry grants no authority.",
                "framework_sha256": digest(framework_hashes())}
    path = state / "task.json"
    write_json(path, document)
    return {"status": "task-ready", "packet": str(path), "task_sha256": digest(document),
            "known_model_alternatives_retained": True, "absence_established": False,
            "files_to_author": MODES[mode]["files"], "next_action": "author sources, then check"}


def expected_rows(mode):
    names = list(MODES[mode]["blocks"])
    if mode == "pair":
        names.append("pair")
    if mode == "triple":
        names.append("turn")
    return [(name, args, evaluate(name, args)) for name in names for args in cases(name)]


def compare_rows(rows, output):
    lines = output.splitlines()
    if len(lines) != len(rows):
        return {"kind": "row-count", "expected": len(rows), "actual": len(lines)}
    for index, ((name, args, expected), line) in enumerate(zip(rows, lines)):
        try:
            actual = [int(part) for part in line.split()]
        except ValueError:
            return {"kind": "invalid-result", "row": index, "contract": name, "inputs": list(args), "actual": line[:200]}
        if actual != [int(x) for x in expected]:
            return {"kind": "behavior-mismatch", "row": index, "contract": name,
                    "inputs": list(args), "expected": expected, "actual": actual}
    return None


def substitution_checks(mode, rows, output):
    values = {(name, args): [int(x) for x in line.split()]
              for (name, args, _), line in zip(rows, output.splitlines())}
    checked = 0
    for raw, score in cases("turn"):
        expected = [int(x) for x in evaluate("turn", (raw, score))]
        if mode == "singles":
            # Replace one logical block at a time in the rest of the UIL graph.
            for replaced in BLOCKS + ("all",):
                count = (values[("normalize", (raw,))] if replaced in ("normalize", "all") else evaluate("normalize", (raw,)))[0]
                points = (values[("award", (count,))] if replaced in ("award", "all") else evaluate("award", (count,)))[0]
                tail = values[("apply", (score, points))] if replaced in ("apply", "all") else evaluate("apply", (score, points))
                assert [count, points] + [int(x) for x in tail] == expected
                checked += 1
        elif mode == "pair":
            count, points = values[("pair", (raw,))]
            assert [count, points] == values[("normalize", (raw,))] + values[("award", (count,))]
            assert [count, points] + [int(x) for x in evaluate("apply", (score, points))] == expected
            checked += 1
        else:
            count, points, next_score, won = values[("turn", (raw, score))]
            assert [count] == values[("normalize", (raw,))]
            assert [points] == values[("award", (count,))]
            assert [next_score, won] == values[("apply", (score, points))]
            assert [count, points, next_score, won] == expected
            checked += 1
    return checked


def check(mode, work, state):
    hashes = source_hashes(mode, work)
    info = compiler()
    number = len(list(state.glob("attempt-*"))) + 1
    attempt = state / f"attempt-{number:03d}"
    attempt.mkdir()
    for name in hashes:
        shutil.copyfile(work / name, attempt / name)
    binary = attempt / "candidate"
    command = [info["path"], "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
               f"-DTRIAL_MODE={MODES[mode]['macro']}", "-I", str(HERE), str(HERE / "scaffold.c"),
               *[str(attempt / name) for name in hashes], "-o", str(binary)]
    build = subprocess.run(command, capture_output=True, text=True, timeout=30)
    build_receipt = {"compiler": info, "command": command, "exit_code": build.returncode,
                     "stdout": build.stdout[:12000], "stderr": build.stderr[:12000],
                     "source_sha256": hashes, "framework_sha256": digest(framework_hashes())}
    write_json(attempt / "build.json", build_receipt)
    result = {"status": "failed", "mode": mode, "attempt": number,
              "source_sha256": hashes, "framework_sha256": build_receipt["framework_sha256"],
              "build_receipt_sha256": sha(attempt / "build.json"), "build_receipt": str(attempt / "build.json"),
              "scope": "native gcc/Linux x86_64, supplied authored scaffold, declared finite domains only",
              "next_action": "repair-source then check"}
    if build.returncode:
        result["failure"] = {"kind": "compile", "diagnostic": build.stderr[:12000]}
    else:
        rows = expected_rows(mode)
        repeated = rows + list(reversed(rows))
        input_text = "".join(f"{OPS[name]} {args[0]} {args[1] if len(args) == 2 else 0}\n" for name, args, _ in repeated)
        execution = subprocess.run([str(binary)], input=input_text, text=True, capture_output=True, timeout=5)
        failure = compare_rows(repeated, execution.stdout)
        if execution.returncode or execution.stderr:
            failure = {"kind": "process", "exit_code": execution.returncode, "stderr": execution.stderr[:2000]}
        result.update(artifact_sha256=sha(binary), unique_native_cases=len(rows), native_result_rows=len(repeated),
                      repeated_order="forward then reverse in one process", effects_exercised=False)
        if failure:
            result["failure"] = failure
        else:
            result.update(status="passed", composition_substitution_cases=substitution_checks(mode, rows, execution.stdout),
                          next_action="register", behavioral_evidence="exhaustive comparison over declared finite domains; repeated order check")
    write_json(attempt / "check.json", result)
    latest = {"receipt": str(attempt / "check.json"), "receipt_sha256": sha(attempt / "check.json")}
    write_json(state / "latest-check.json", latest)
    return {**result, **latest}


def register(mode, work, state):
    latest = read_json(state / "latest-check.json")
    receipt_path = Path(latest["receipt"])
    result = read_json(receipt_path)
    if sha(receipt_path) != latest["receipt_sha256"] or result["status"] != "passed" or result["mode"] != mode:
        raise ValueError("qualification missing: run check successfully for this mode")
    if result["source_sha256"] != source_hashes(mode, work) or result["framework_sha256"] != digest(framework_hashes()):
        raise ValueError("stale qualification: source or framework changed; run check again")
    if result["artifact_sha256"] != sha(receipt_path.parent / "candidate"):
        raise ValueError("stale artifact: run check again")
    names = MODES[mode]["blocks"]
    requirements = []
    documents = contracts()
    for name in names:
        fn = documents[name]["program"]["functions"][0]
        requirements.append(make_requirement("trial.coin." + name,
            inputs=[fn["variables"][n] for n in fn["inputs"]], outputs=[fn["variables"][n] for n in fn["outputs"]],
            abi="swede-trial-c-1"))
    metadata = {"experiment": "collect-coins", "mode": mode, "source_manifest_sha256": digest(result["source_sha256"])}
    module = make_module("trial.coin." + mode, requirements, metadata=metadata)
    provider = make_provider("trial.coin.c." + mode, requirements, target=TARGET, metadata=metadata)
    source = {}
    for name in names:
        filename = name + ".c" if mode == "singles" else MODES[mode]["files"][0]
        source[name] = {"filename": filename, "sha256": result["source_sha256"][filename],
                        "size": (work / filename).stat().st_size,
                        "association": "author declaration checked only over the recorded trial domain"}
    submitted_catalog = catalog(source)
    receipts = []
    with open_registry(state) as db:
        db.import_catalog(submitted_catalog)
        db.register_components([module], [provider], target=TARGET)
        for name in names:
            group = next(g for g in submitted_catalog["groups"] if g["semantic_id"] == semantic_ids()[name])
            record = {"format": REPRESENTATION, "implementation": group["implementations"][0]["id"],
                      "module": module["id"], "provider": provider["id"], "target": TARGET,
                      "representation_language": "c", "domain": DOMAINS[name], "availability": "artifact-present",
                      "backend": "available", "origin": "authored collect-coins swede trial " + mode,
                      "distribution": "authored-review-requested", "artifact_sha256": result["artifact_sha256"],
                      "evidence": [{"scope": "build", "sha256": result["build_receipt_sha256"]},
                                   {"scope": "target-execution", "sha256": latest["receipt_sha256"]}]}
            receipts.append({"block": name, **db.register_representation(record)})
    document = {"status": "registered-locally", "receipts": receipts, "module": module, "provider": provider,
                "check_receipt": latest, "registry_evidence_status": "unverified-references",
                "next_action": "lookup", "execution_authorized_by_registry": False}
    write_json(state / "registration.json", document)
    return document


def lookup(mode, state):
    with open_registry(state) as db:
        results = {name: db.query(semantic_ids()[name], TARGET, domain=DOMAINS[name]) for name in MODES[mode]["blocks"]}
    return {"status": "looked-up-after-open", "blocks": results,
            "note": "review-evidence is expected after registration: the registry does not verify the submitted receipts."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--work", required=True, type=Path, help="Your own writable directory outside a Git checkout; contains sources and private results.")
    parser.add_argument("command", choices=("doctor", "describe", "task", "check", "register", "lookup"))
    args = parser.parse_args()
    state = state_dir(args.work.resolve())
    started = time.time()
    event = {"at": datetime.now(timezone.utc).isoformat(), "mode": args.mode, "command": args.command}
    try:
        if args.command == "doctor":
            result = {"status": "ready", "compiler": compiler(), "framework_sha256": digest(framework_hashes()), "next_action": "describe"}
        elif args.command == "describe":
            result = describe(args.mode)
        elif args.command == "task":
            result = task(args.mode, state)
        elif args.command == "check":
            result = check(args.mode, args.work.resolve(), state)
        elif args.command == "register":
            result = register(args.mode, args.work.resolve(), state)
        else:
            result = lookup(args.mode, state)
        code = 0 if result.get("status") != "failed" else 1
    except (ValueError, OSError, subprocess.SubprocessError, AssertionError) as exc:
        result = {"status": "error", "error_type": type(exc).__name__, "error": str(exc),
                  "next_action": "inspect the stated error; repair owned source or report a tool blocker"}
        code = 2
    event.update(elapsed_seconds=round(time.time() - started, 6), exit_code=code, result=result)
    with (state / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
